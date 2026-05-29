"""Generate WorldForge dependency audit evidence as JSON and Markdown."""

from __future__ import annotations

import argparse
import json
import re
import shlex
import subprocess
import tempfile
from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_DIR = ROOT / ".worldforge" / "dependency-audit"
DEFAULT_JSON_OUTPUT = DEFAULT_OUTPUT_DIR / "dependency-audit.json"
DEFAULT_MARKDOWN_OUTPUT = DEFAULT_OUTPUT_DIR / "dependency-audit.md"
DEPENDENCY_AUDIT_EVIDENCE_SCHEMA_VERSION = 1
MAX_CAPTURE_CHARS = 4_000

SECRET_PATTERN = re.compile(
    r"(api[_-]?key|authorization|bearer\s+[a-z0-9._~-]+|password|secret|signature|token=|"
    r"x-amz-signature|runwayml_api_secret|nvidia_api_key)",
    re.IGNORECASE,
)
HOST_PATH_PATTERN = re.compile(r"(?<![A-Za-z0-9:])/(?:Users|private|Volumes|var/folders)/[^\s)`|]+")
SIGNED_URL_PATTERN = re.compile(
    r"https?://[^\s)`|]*(?:X-Amz-Signature|sig=|signature=|token=|secret=)[^\s)`|]*",
    re.IGNORECASE,
)


@dataclass(frozen=True, slots=True)
class CommandResult:
    command: tuple[str, ...]
    exit_code: int | None
    stdout: str = ""
    stdout_tail: str = ""
    stderr_tail: str = ""
    error: str = ""

    @property
    def unavailable(self) -> bool:
        return self.exit_code is None or self.exit_code == 127

    def to_dict(self) -> dict[str, Any]:
        return {
            "command": shlex.join(self.command),
            "exit_code": self.exit_code,
            "stdout_tail": _sanitize_text(self.stdout_tail),
            "stderr_tail": _sanitize_text(self.stderr_tail),
            "error": _sanitize_text(self.error),
        }


@dataclass(frozen=True, slots=True)
class DependencyAuditEvidence:
    status: str
    payload: dict[str, Any]
    markdown: str


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--json-output",
        type=Path,
        default=DEFAULT_JSON_OUTPUT,
        help="JSON evidence path. Defaults to .worldforge/dependency-audit/dependency-audit.json.",
    )
    parser.add_argument(
        "--markdown-output",
        type=Path,
        default=DEFAULT_MARKDOWN_OUTPUT,
        help=(
            "Markdown evidence path. Defaults to .worldforge/dependency-audit/dependency-audit.md."
        ),
    )
    parser.add_argument(
        "--ignore-advisory",
        action="append",
        default=[],
        metavar="ADVISORY=RATIONALE",
        help=(
            "Explicit advisory ignore with rationale. The advisory id is passed to pip-audit "
            "--ignore-vuln and the rationale is preserved in evidence. Can be repeated."
        ),
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    evidence = generate_dependency_audit_evidence(
        ignored_advisories=_parse_ignored_advisories(tuple(args.ignore_advisory)),
    )
    json_output = args.json_output.expanduser().resolve()
    markdown_output = args.markdown_output.expanduser().resolve()
    json_output.parent.mkdir(parents=True, exist_ok=True)
    markdown_output.parent.mkdir(parents=True, exist_ok=True)
    json_output.write_text(json.dumps(evidence.payload, indent=2, sort_keys=True) + "\n")
    markdown_output.write_text(evidence.markdown, encoding="utf-8")
    print(f"wrote {_display_path(json_output)}")
    print(f"wrote {_display_path(markdown_output)}")
    return 0 if evidence.status == "passed" else 1


def generate_dependency_audit_evidence(
    *,
    ignored_advisories: tuple[dict[str, str], ...] = (),
    runner: Any = subprocess.run,
    now_utc: Any | None = None,
) -> DependencyAuditEvidence:
    """Run the dependency audit flow and return JSON plus Markdown evidence."""

    generated_at = _isoformat_utc((now_utc or _utc_now)())
    uv_version = _run_command(("uv", "--version"), runner=runner)
    pip_audit_version = _run_command(
        ("uvx", "--from", "pip-audit", "pip-audit", "--version"),
        runner=runner,
    )
    export_result: CommandResult | None = None
    audit_result: CommandResult | None = None
    audit_payload: dict[str, Any] | None = None
    requirements_summary = _empty_requirements_summary()

    with tempfile.TemporaryDirectory(prefix="worldforge-dependency-audit-") as tmp_dir:
        requirements_path = Path(tmp_dir) / "requirements-audit.txt"
        export_command = (
            "uv",
            "export",
            "--frozen",
            "--all-groups",
            "--no-emit-project",
            "--no-hashes",
            "-o",
            str(requirements_path),
        )
        export_result = _run_command(export_command, runner=runner)
        if export_result.exit_code == 0 and requirements_path.exists():
            requirements_summary = _requirements_summary(requirements_path)
            audit_command = _pip_audit_command(requirements_path, ignored_advisories)
            audit_result = _run_command(audit_command, runner=runner)
            audit_payload = _parse_audit_json(audit_result.stdout)
        elif export_result.unavailable:
            audit_result = None
        else:
            audit_result = None

    status = _audit_status(
        uv_version=uv_version,
        pip_audit_version=pip_audit_version,
        export_result=export_result,
        audit_result=audit_result,
        audit_payload=audit_payload,
    )
    vulnerability_summary, findings = _vulnerability_summary(audit_payload)
    payload = {
        "schema_version": DEPENDENCY_AUDIT_EVIDENCE_SCHEMA_VERSION,
        "generated_at": generated_at,
        "status": status,
        "safe_to_attach": True,
        "requirements": requirements_summary,
        "tool_versions": {
            "uv": _version_text(uv_version),
            "pip_audit": _version_text(pip_audit_version),
        },
        "commands": {
            "uv_version": uv_version.to_dict(),
            "pip_audit_version": pip_audit_version.to_dict(),
            "uv_export": export_result.to_dict(),
            "pip_audit": audit_result.to_dict() if audit_result is not None else None,
        },
        "ignored_advisories": list(ignored_advisories),
        "vulnerability_summary": vulnerability_summary,
        "vulnerabilities": findings,
        "first_triage_step": _first_triage_step(status),
        "claim_boundary": (
            "This artifact records a local dependency audit against the exported locked "
            "development dependency set. It is not a remote vulnerability scanning service, "
            "does not create suppression policy, and does not preserve the temporary "
            "requirements file."
        ),
    }
    payload = _sanitize_json(payload)
    markdown = render_dependency_audit_markdown(payload)
    return DependencyAuditEvidence(status=status, payload=payload, markdown=markdown)


def render_dependency_audit_markdown(payload: dict[str, Any]) -> str:
    """Render dependency audit evidence as Markdown."""

    summary = payload["vulnerability_summary"]
    requirements = payload["requirements"]
    dependency_names = ", ".join(f"`{name}`" for name in requirements["dependency_names"]) or "-"
    lines = [
        "# WorldForge Dependency Audit Evidence",
        "",
        f"- Schema version: `{payload['schema_version']}`",
        f"- Generated at: `{payload['generated_at']}`",
        f"- Status: `{payload['status']}`",
        f"- Safe to attach: `{str(payload['safe_to_attach']).lower()}`",
        f"- First triage step: {payload['first_triage_step']}",
        "",
        "## Dependency Set",
        "",
        f"- Requirements source: `{requirements['source']}`",
        f"- Requirements SHA-256: `{requirements['sha256']}`",
        f"- Requirement count: {requirements['requirement_count']}",
        f"- Dependency names: {dependency_names}",
        "- Temporary requirements file preserved: `false`",
        "",
        "## Tool Versions",
        "",
        f"- uv: `{payload['tool_versions']['uv']}`",
        f"- pip-audit: `{payload['tool_versions']['pip_audit']}`",
        "",
        "## Vulnerability Summary",
        "",
        f"- Dependencies audited: {summary['dependency_count']}",
        f"- Vulnerable dependencies: {summary['vulnerable_dependency_count']}",
        f"- Vulnerabilities: {summary['vulnerability_count']}",
        f"- Ignored advisories with rationale: {len(payload['ignored_advisories'])}",
        "",
        "## Vulnerability Findings",
        "",
    ]
    findings = payload["vulnerabilities"]
    if findings:
        lines.extend(
            [
                "| Dependency | Version | Advisory | Fix versions | Summary |",
                "| --- | --- | --- | --- | --- |",
            ]
        )
        lines.extend(
            (
                "| {dependency} | {version} | {advisory} | {fix_versions} | {summary} |".format(
                    dependency=f"`{finding['dependency']}`",
                    version=f"`{finding['version']}`",
                    advisory=f"`{finding['id']}`",
                    fix_versions=", ".join(f"`{item}`" for item in finding["fix_versions"]) or "-",
                    summary=finding["summary"],
                )
            )
            for finding in findings
        )
    else:
        lines.append("- No vulnerability findings reported by pip-audit.")

    lines.extend(["", "## Ignored Advisories", ""])
    if payload["ignored_advisories"]:
        lines.extend(
            f"- `{item['id']}`: {item['rationale']}" for item in payload["ignored_advisories"]
        )
    else:
        lines.append("- No advisory ignores were requested.")

    lines.extend(
        [
            "",
            "## Commands",
            "",
            "| Step | Command | Exit |",
            "| --- | --- | ---: |",
        ]
    )
    for step, record in payload["commands"].items():
        if record is None:
            lines.append(f"| {step} | not run | - |")
        else:
            lines.append(f"| {step} | `{record['command']}` | {record['exit_code']} |")

    lines.extend(
        [
            "",
            "## Claim Boundary",
            "",
            payload["claim_boundary"],
            "",
        ]
    )
    return "\n".join(lines)


def _run_command(command: tuple[str, ...], *, runner: Any) -> CommandResult:
    try:
        completed = runner(command, cwd=ROOT, capture_output=True, text=True)
    except OSError as exc:
        return CommandResult(command=command, exit_code=None, error=str(exc))
    return CommandResult(
        command=command,
        exit_code=int(completed.returncode),
        stdout=completed.stdout or "",
        stdout_tail=_capture_tail(completed.stdout),
        stderr_tail=_capture_tail(completed.stderr),
    )


def _pip_audit_command(
    requirements_path: Path,
    ignored_advisories: tuple[dict[str, str], ...],
) -> tuple[str, ...]:
    command = [
        "uvx",
        "--from",
        "pip-audit",
        "pip-audit",
        "-r",
        str(requirements_path),
        "--format",
        "json",
        "--no-deps",
        "--disable-pip",
        "--progress-spinner",
        "off",
    ]
    for advisory in ignored_advisories:
        command.extend(("--ignore-vuln", advisory["id"]))
    return tuple(command)


def _requirements_summary(path: Path) -> dict[str, Any]:
    raw = path.read_text(encoding="utf-8")
    requirements = [
        line.strip()
        for line in raw.splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]
    dependency_names = sorted(
        {
            match.group(1).lower()
            for requirement in requirements
            if (match := re.match(r"([A-Za-z0-9_.-]+)", requirement))
        }
    )
    return {
        "source": "temporary uv export file removed after audit",
        "sha256": "sha256:" + sha256(raw.encode("utf-8")).hexdigest(),
        "requirement_count": len(requirements),
        "dependency_names": dependency_names,
        "temporary_file_preserved": False,
    }


def _empty_requirements_summary() -> dict[str, Any]:
    return {
        "source": "not generated",
        "sha256": None,
        "requirement_count": 0,
        "dependency_names": [],
        "temporary_file_preserved": False,
    }


def _parse_audit_json(stdout: str) -> dict[str, Any] | None:
    if not stdout.strip():
        return None
    try:
        payload = json.loads(stdout)
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None


def _vulnerability_summary(
    audit_payload: dict[str, Any] | None,
) -> tuple[dict[str, int], list[dict[str, Any]]]:
    dependencies = audit_payload.get("dependencies", []) if audit_payload else []
    findings: list[dict[str, Any]] = []
    dependency_count = 0
    vulnerable_dependencies = 0
    if isinstance(dependencies, list):
        dependency_count = len(dependencies)
        for dependency in dependencies:
            if not isinstance(dependency, dict):
                continue
            vulns = dependency.get("vulns", [])
            if not isinstance(vulns, list) or not vulns:
                continue
            vulnerable_dependencies += 1
            for vuln in vulns:
                if not isinstance(vuln, dict):
                    continue
                findings.append(_finding_record(dependency, vuln))
    summary = {
        "dependency_count": dependency_count,
        "vulnerable_dependency_count": vulnerable_dependencies,
        "vulnerability_count": len(findings),
    }
    return summary, findings


def _finding_record(dependency: dict[str, Any], vuln: dict[str, Any]) -> dict[str, Any]:
    fix_versions = vuln.get("fix_versions") or vuln.get("fixes") or []
    if not isinstance(fix_versions, list):
        fix_versions = []
    advisory_id = str(vuln.get("id") or vuln.get("vulnerability_id") or "unknown")
    summary = str(vuln.get("description") or vuln.get("summary") or "")
    return {
        "dependency": str(dependency.get("name") or "unknown"),
        "version": str(dependency.get("version") or "unknown"),
        "id": advisory_id,
        "aliases": [str(item) for item in vuln.get("aliases", []) if isinstance(item, str)],
        "fix_versions": [str(item) for item in fix_versions],
        "summary": _sanitize_text(summary[:500]),
    }


def _audit_status(
    *,
    uv_version: CommandResult,
    pip_audit_version: CommandResult,
    export_result: CommandResult,
    audit_result: CommandResult | None,
    audit_payload: dict[str, Any] | None,
) -> str:
    if uv_version.unavailable or pip_audit_version.unavailable or export_result.unavailable:
        return "tool-unavailable"
    if export_result.exit_code != 0:
        return "failed"
    if audit_result is None:
        return "failed"
    if audit_result.unavailable:
        return "tool-unavailable"
    _summary, findings = _vulnerability_summary(audit_payload)
    if findings:
        return "findings"
    if audit_result.exit_code == 0:
        return "passed"
    if _looks_tool_unavailable(audit_result):
        return "tool-unavailable"
    return "failed"


def _looks_tool_unavailable(result: CommandResult) -> bool:
    message = f"{result.stderr_tail}\n{result.error}".lower()
    return "not found" in message or "no such file" in message or "command not found" in message


def _first_triage_step(status: str) -> str:
    if status == "passed":
        return (
            "Attach the JSON and Markdown evidence to release review if dependency audit is cited."
        )
    if status == "findings":
        return "Review each advisory, upgrade or document the dependency decision, then rerun."
    if status == "tool-unavailable":
        return "Install uv or run pip-audit through uvx, then rerun the evidence command."
    return "Inspect the failed command row, fix the audit/export failure, then rerun."


def _version_text(result: CommandResult) -> str:
    if result.exit_code == 0 and result.stdout_tail.strip():
        return _sanitize_text(result.stdout_tail.strip().splitlines()[-1])
    if result.error:
        return "unavailable"
    return "unknown"


def _parse_ignored_advisories(values: tuple[str, ...]) -> tuple[dict[str, str], ...]:
    parsed: list[dict[str, str]] = []
    for raw in values:
        if "=" not in raw:
            raise SystemExit("--ignore-advisory must use ADVISORY=RATIONALE")
        advisory_id, rationale = raw.split("=", 1)
        advisory_id = advisory_id.strip()
        rationale = rationale.strip()
        if not advisory_id or not rationale:
            raise SystemExit("--ignore-advisory must include both advisory id and rationale")
        parsed.append({"id": _sanitize_text(advisory_id), "rationale": _sanitize_text(rationale)})
    return tuple(parsed)


def _capture_tail(value: str | None) -> str:
    if not value:
        return ""
    stripped = value.strip()
    if len(stripped) <= MAX_CAPTURE_CHARS:
        return _sanitize_text(stripped)
    return _sanitize_text(stripped[-MAX_CAPTURE_CHARS:])


def _sanitize_json(value: Any) -> Any:
    if isinstance(value, str):
        return _sanitize_text(value)
    if isinstance(value, list):
        return [_sanitize_json(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _sanitize_json(item) for key, item in value.items()}
    return value


def _sanitize_text(value: str) -> str:
    sanitized = SIGNED_URL_PATTERN.sub("[redacted-url]", value)
    sanitized = HOST_PATH_PATTERN.sub("<host-local-path>", sanitized)
    return SECRET_PATTERN.sub("[redacted]", sanitized)


def _display_path(path: Path) -> str:
    resolved = path.expanduser().resolve()
    try:
        return str(resolved.relative_to(ROOT))
    except ValueError:
        return f"<host-local-path>/{resolved.name}"


def _utc_now() -> datetime:
    return datetime.now(UTC).replace(microsecond=0)


def _isoformat_utc(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC).replace(microsecond=0).isoformat()


if __name__ == "__main__":
    raise SystemExit(main())

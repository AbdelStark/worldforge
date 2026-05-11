"""Generate a local WorldForge quality dashboard from existing gate outputs."""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from generate_release_evidence import CHECKOUT_SAFE_GATES, LIVE_PROVIDER_ENV  # noqa: E402

QUALITY_DASHBOARD_SCHEMA_VERSION = 1
DEFAULT_OUTPUT_DIR = ROOT / ".worldforge" / "quality-dashboard"
DEFAULT_JSON_OUTPUT = DEFAULT_OUTPUT_DIR / "quality-dashboard.json"
DEFAULT_MARKDOWN_OUTPUT = DEFAULT_OUTPUT_DIR / "quality-dashboard.md"
DEFAULT_RELEASE_EVIDENCE = ROOT / ".worldforge" / "release-evidence" / "release-evidence.json"
DEFAULT_DEPENDENCY_AUDIT = ROOT / ".worldforge" / "dependency-audit" / "dependency-audit.json"
DEFAULT_CORE_PERFORMANCE = ROOT / ".worldforge" / "core-performance" / "core-performance.json"
DASHBOARD_STATUSES = ("passed", "failed", "warning", "skipped", "not-run")

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
class GateRecord:
    """Normalized dashboard row for one quality signal."""

    name: str
    status: str
    command: str
    source: str
    summary: str
    first_triage_step: str
    category: str
    started_at: str | None = None
    finished_at: str | None = None
    host_owned: bool = False
    raw_details: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "status": self.status,
            "command": self.command,
            "source": self.source,
            "summary": self.summary,
            "first_triage_step": self.first_triage_step,
            "category": self.category,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "host_owned": self.host_owned,
            "raw_details": _sanitize_json(self.raw_details or {}),
        }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--release-evidence",
        type=Path,
        default=DEFAULT_RELEASE_EVIDENCE,
        help=(
            "Release evidence JSON to read. Defaults to "
            ".worldforge/release-evidence/release-evidence.json."
        ),
    )
    parser.add_argument(
        "--dependency-audit",
        type=Path,
        default=DEFAULT_DEPENDENCY_AUDIT,
        help=(
            "Dependency audit JSON to read. Defaults to "
            ".worldforge/dependency-audit/dependency-audit.json."
        ),
    )
    parser.add_argument(
        "--core-performance",
        type=Path,
        default=DEFAULT_CORE_PERFORMANCE,
        help=(
            "Core performance JSON to read. Defaults to "
            ".worldforge/core-performance/core-performance.json."
        ),
    )
    parser.add_argument(
        "--json-output",
        type=Path,
        default=DEFAULT_JSON_OUTPUT,
        help=(
            "JSON dashboard path. Defaults to .worldforge/quality-dashboard/quality-dashboard.json."
        ),
    )
    parser.add_argument(
        "--markdown-output",
        type=Path,
        default=DEFAULT_MARKDOWN_OUTPUT,
        help=(
            "Markdown dashboard path. Defaults to "
            ".worldforge/quality-dashboard/quality-dashboard.md."
        ),
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Exit non-zero when any gate is failed, warning, skipped, or not-run.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    dashboard = build_quality_dashboard(
        release_evidence=args.release_evidence,
        dependency_audit=args.dependency_audit,
        core_performance=args.core_performance,
    )
    json_output = args.json_output.expanduser().resolve()
    markdown_output = args.markdown_output.expanduser().resolve()
    json_output.parent.mkdir(parents=True, exist_ok=True)
    markdown_output.parent.mkdir(parents=True, exist_ok=True)
    json_output.write_text(json.dumps(dashboard, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    markdown_output.write_text(render_quality_dashboard_markdown(dashboard), encoding="utf-8")
    print(f"wrote {_display_path(json_output)}")
    print(f"wrote {_display_path(markdown_output)}")
    if dashboard["status"] == "failed" or (args.strict and dashboard["status"] != "passed"):
        return 1
    return 0


def build_quality_dashboard(
    *,
    release_evidence: Path = DEFAULT_RELEASE_EVIDENCE,
    dependency_audit: Path = DEFAULT_DEPENDENCY_AUDIT,
    core_performance: Path = DEFAULT_CORE_PERFORMANCE,
    now_utc: Any | None = None,
) -> dict[str, Any]:
    """Return a normalized dashboard payload from existing quality artifacts."""

    generated_at = _isoformat_utc((now_utc or _utc_now)())
    release_path = release_evidence.expanduser().resolve()
    dependency_path = dependency_audit.expanduser().resolve()
    performance_path = core_performance.expanduser().resolve()

    release_payload = _load_json_artifact(release_path)
    dependency_payload = _load_json_artifact(dependency_path)
    performance_payload = _load_json_artifact(performance_path)

    gates = [
        *_release_gate_records(release_path, release_payload),
        *_live_provider_records(release_path, release_payload),
        _dependency_audit_record(dependency_path, dependency_payload),
        _core_performance_record(performance_path, performance_payload),
    ]
    summary = _summary_counts(gates)
    first_failed = next((gate for gate in gates if gate.status == "failed"), None)
    dashboard = {
        "schema_version": QUALITY_DASHBOARD_SCHEMA_VERSION,
        "generated_at": generated_at,
        "status": _overall_status(summary),
        "summary": summary,
        "first_failed_gate": first_failed.to_dict() if first_failed else None,
        "gates": [gate.to_dict() for gate in gates],
        "sources": {
            "release_evidence": _source_record(release_path, release_payload),
            "dependency_audit": _source_record(dependency_path, dependency_payload),
            "core_performance": _source_record(performance_path, performance_payload),
        },
        "claim_boundary": (
            "This local dashboard summarizes existing gate outputs. It does not execute gates, "
            "publish a hosted badge, replace raw artifacts, or strengthen release claims beyond "
            "the linked release evidence and run manifests."
        ),
    }
    return _sanitize_json(dashboard)


def render_quality_dashboard_markdown(payload: dict[str, Any]) -> str:
    """Render a quality dashboard payload as Markdown."""

    first_failed = payload.get("first_failed_gate")
    first_failed_text = first_failed["name"] if isinstance(first_failed, dict) else "-"
    lines = [
        "# WorldForge Quality Dashboard",
        "",
        f"- Schema version: `{payload['schema_version']}`",
        f"- Generated at: `{payload['generated_at']}`",
        f"- Status: `{payload['status']}`",
        f"- First failed gate: `{first_failed_text}`",
        "",
        "This local dashboard reads existing gate outputs and normalizes them for review. It is "
        "not a hosted dashboard, badge service, release approval, or replacement for release "
        "evidence. Release evidence remains the artifact for release claims, artifact hashes, and "
        "linked live-smoke manifests; this dashboard is the at-a-glance quality index.",
        "",
        "## Summary",
        "",
        "| Status | Count |",
        "| --- | ---: |",
    ]
    lines.extend(
        f"| `{status}` | {payload['summary'].get(status, 0)} |" for status in DASHBOARD_STATUSES
    )

    lines.extend(
        [
            "",
            "## Gates",
            "",
            "| Gate | Category | Status | Command | Source | First triage step |",
            "| --- | --- | --- | --- | --- | --- |",
        ]
    )
    for gate in payload["gates"]:
        command = f"`{gate['command']}`" if gate["command"] else "-"
        source = gate["source"] or "-"
        lines.append(
            f"| {gate['name']} | {gate['category']} | `{gate['status']}` | {command} | "
            f"{source} | {gate['first_triage_step']} |"
        )

    lines.extend(["", "## Raw Failure Details", ""])
    issue_gates = [
        gate for gate in payload["gates"] if gate["status"] in {"failed", "warning", "not-run"}
    ]
    if issue_gates:
        for gate in issue_gates:
            lines.extend(
                [
                    f"### {gate['name']}",
                    "",
                    f"- Status: `{gate['status']}`",
                    f"- Source: {gate['source'] or '-'}",
                    f"- Summary: {gate['summary']}",
                    f"- First triage step: {gate['first_triage_step']}",
                    "",
                    "```json",
                    json.dumps(gate["raw_details"], indent=2, sort_keys=True),
                    "```",
                    "",
                ]
            )
    else:
        lines.append("- No failed, warning, or not-run gates.")

    skipped = [gate for gate in payload["gates"] if gate["status"] == "skipped"]
    lines.extend(["", "## Skipped Checks", ""])
    if skipped:
        for gate in skipped:
            host_owned = " host-owned" if gate.get("host_owned") else ""
            lines.append(f"- `{gate['name']}`:{host_owned} {gate['summary']}")
    else:
        lines.append("- No skipped checks.")

    lines.extend(["", "## Claim Boundary", "", payload["claim_boundary"], ""])
    return "\n".join(lines)


def _release_gate_records(path: Path, payload: dict[str, Any] | None) -> list[GateRecord]:
    expected = {gate.name: gate for gate in CHECKOUT_SAFE_GATES}
    records_by_name: dict[str, dict[str, Any]] = {}
    if payload is not None:
        raw_gates = payload.get("validation_gates", [])
        if isinstance(raw_gates, list):
            records_by_name = {
                str(gate.get("name")): gate
                for gate in raw_gates
                if isinstance(gate, dict) and gate.get("name")
            }

    records: list[GateRecord] = []
    for gate in CHECKOUT_SAFE_GATES:
        raw = records_by_name.pop(gate.name, None)
        if raw is None:
            source = _display_path(path) if payload is not None else ""
            records.append(
                GateRecord(
                    name=gate.name,
                    status="not-run",
                    command=gate.command,
                    source=source,
                    summary=(
                        "Release evidence is missing."
                        if payload is None
                        else "No release evidence row was found for this expected gate."
                    ),
                    first_triage_step=(
                        "Run `uv run python scripts/generate_release_evidence.py --run-gates`."
                    ),
                    category=_gate_category(gate.name),
                    raw_details={
                        "expected_command": gate.command,
                        "source_path": _display_path(path),
                        "reason": "missing-release-evidence" if payload is None else "missing-row",
                    },
                )
            )
            continue
        records.append(_release_gate_record(path, raw, expected.get(gate.name, gate)))

    for name, raw in sorted(records_by_name.items()):
        records.append(_release_gate_record(path, raw, expected.get(name)))
    return records


def _release_gate_record(path: Path, raw: dict[str, Any], expected: Any | None) -> GateRecord:
    raw_status = str(raw.get("status") or "")
    status = _normalize_release_status(raw_status)
    command = str(raw.get("command") or getattr(expected, "command", ""))
    triage = str(raw.get("triage_step") or getattr(expected, "triage_step", "Inspect source."))
    name = str(raw.get("name") or getattr(expected, "name", "Unknown gate"))
    exit_code = raw.get("exit_code")
    summary_parts = [f"release gate reported `{raw_status or status}`"]
    if exit_code is not None:
        summary_parts.append(f"exit code {exit_code}")
    if raw.get("duration_ms") is not None:
        summary_parts.append(f"duration {raw['duration_ms']} ms")
    return GateRecord(
        name=name,
        status=status,
        command=command,
        source=_display_path(path),
        summary=", ".join(summary_parts),
        first_triage_step=triage,
        category=_gate_category(name),
        started_at=_optional_str(raw.get("started_at")),
        finished_at=_optional_str(raw.get("finished_at")),
        raw_details={
            "source_path": _display_path(path),
            "release_status": raw_status,
            "exit_code": exit_code,
            "duration_ms": raw.get("duration_ms"),
            "stdout_tail": raw.get("stdout_tail", ""),
            "stderr_tail": raw.get("stderr_tail", ""),
            "triage_step": triage,
        },
    )


def _live_provider_records(path: Path, payload: dict[str, Any] | None) -> list[GateRecord]:
    if payload is None:
        return [
            GateRecord(
                name=f"Optional live provider: {provider}",
                status="skipped",
                command="uv run python scripts/generate_release_evidence.py --run-manifest <path>",
                source="",
                summary="No release evidence was available; host-owned live evidence was not read.",
                first_triage_step=(
                    "Link a prepared-host run_manifest.json through release evidence."
                ),
                category="optional-runtime",
                host_owned=True,
                raw_details={
                    "provider": provider,
                    "reason": "missing-release-evidence",
                    "source_path": _display_path(path),
                },
            )
            for provider in sorted(LIVE_PROVIDER_ENV)
        ]

    rows: list[dict[str, Any]] = []
    for key in ("live_provider_evidence", "extra_live_provider_evidence"):
        value = payload.get(key, [])
        if isinstance(value, list):
            rows.extend(item for item in value if isinstance(item, dict))
    records: list[GateRecord] = []
    for row in rows:
        provider = str(row.get("provider") or "unknown")
        provider_status = str(row.get("status") or "")
        status, host_owned = _normalize_live_provider_status(provider_status)
        reason = str(row.get("reason") or "")
        records.append(
            GateRecord(
                name=f"Optional live provider: {provider}",
                status=status,
                command="uv run python scripts/generate_release_evidence.py --run-manifest <path>",
                source=_display_path(path),
                summary=reason or f"release evidence reported `{provider_status}`",
                first_triage_step=(
                    "Link a prepared-host run_manifest.json or keep the host-owned skip explicit."
                    if host_owned or status == "skipped"
                    else "Inspect the linked run_manifest.json and provider smoke output."
                ),
                category="optional-runtime",
                host_owned=host_owned,
                raw_details={
                    "source_path": _display_path(path),
                    "provider": provider,
                    "release_status": provider_status,
                    "reason": reason,
                    "manifests": row.get("manifests", []),
                },
            )
        )
    return records


def _dependency_audit_record(path: Path, payload: dict[str, Any] | None) -> GateRecord:
    command = "uv run python scripts/generate_dependency_audit_evidence.py"
    if payload is None:
        return GateRecord(
            name="Dependency audit artifact",
            status="not-run",
            command=command,
            source="",
            summary="Dependency audit evidence JSON was not found.",
            first_triage_step="Run `uv run python scripts/generate_dependency_audit_evidence.py`.",
            category="security",
            raw_details={"source_path": _display_path(path), "reason": "missing-artifact"},
        )
    raw_status = str(payload.get("status") or "")
    status = {
        "passed": "passed",
        "findings": "failed",
        "tool-unavailable": "warning",
        "failed": "failed",
    }.get(raw_status, "warning")
    summary = payload.get("vulnerability_summary", {})
    if isinstance(summary, dict):
        vulnerability_count = summary.get("vulnerability_count", 0)
        summary_text = (
            f"dependency audit reported `{raw_status}` with {vulnerability_count} findings"
        )
    else:
        summary_text = f"dependency audit reported `{raw_status}`"
    return GateRecord(
        name="Dependency audit artifact",
        status=status,
        command=command,
        source=_display_path(path),
        summary=summary_text,
        first_triage_step=str(
            payload.get("first_triage_step") or "Inspect dependency audit output."
        ),
        category="security",
        started_at=_optional_str(payload.get("generated_at")),
        raw_details={
            "source_path": _display_path(path),
            "dependency_audit_status": raw_status,
            "vulnerability_summary": payload.get("vulnerability_summary", {}),
            "vulnerabilities": payload.get("vulnerabilities", [])[:10]
            if isinstance(payload.get("vulnerabilities", []), list)
            else [],
            "commands": payload.get("commands", {}),
            "ignored_advisories": payload.get("ignored_advisories", []),
        },
    )


def _core_performance_record(path: Path, payload: dict[str, Any] | None) -> GateRecord:
    command = (
        "uv run python scripts/check_core_performance.py "
        "--workspace-dir .worldforge/core-performance "
        "--output .worldforge/core-performance/core-performance.json"
    )
    if payload is None:
        return GateRecord(
            name="Core performance artifact",
            status="not-run",
            command=command,
            source="",
            summary="Core performance JSON was not found.",
            first_triage_step=(
                "Run `uv run python scripts/check_core_performance.py --output <path>`."
            ),
            category="performance",
            raw_details={"source_path": _display_path(path), "reason": "missing-artifact"},
        )
    passed = bool(payload.get("passed"))
    results = payload.get("results", [])
    failed_results = (
        [result for result in results if isinstance(result, dict) and result.get("passed") is False]
        if isinstance(results, list)
        else []
    )
    summary = (
        f"{len(failed_results)} performance budget rows failed"
        if failed_results
        else "all recorded core performance rows passed"
    )
    return GateRecord(
        name="Core performance artifact",
        status="passed" if passed else "failed",
        command=command,
        source=_display_path(path),
        summary=summary,
        first_triage_step="Inspect the failing result row before changing budgets.",
        category="performance",
        raw_details={
            "source_path": _display_path(path),
            "passed": passed,
            "failed_results": failed_results,
            "results": results,
            "preserved_workspace": payload.get("preserved_workspace"),
        },
    )


def _load_json_artifact(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {
            "status": "invalid-json",
            "error": f"{_display_path(path)} is not valid JSON.",
        }
    if isinstance(payload, dict):
        return payload
    return {"status": "invalid-json", "error": "not object"}


def _source_record(path: Path, payload: dict[str, Any] | None) -> dict[str, Any]:
    return {
        "path": _display_path(path),
        "status": "present" if payload is not None else "missing",
        "schema_version": payload.get("schema_version") if payload is not None else None,
    }


def _normalize_release_status(status: str) -> str:
    if status in {"passed", "failed", "skipped"}:
        return status
    if status in {"not-run", "not_run"}:
        return "not-run"
    return "warning"


def _normalize_live_provider_status(status: str) -> tuple[str, bool]:
    if status == "host-owned":
        return "skipped", True
    if status in {"passed", "failed", "skipped"}:
        return status, False
    return "warning", False


def _gate_category(name: str) -> str:
    lower = name.lower()
    if "doc" in lower or "provider catalog" in lower:
        return "docs"
    if "test" in lower or "coverage" in lower:
        return "tests"
    if "package" in lower or "build" in lower:
        return "package"
    if "dependency" in lower:
        return "security"
    if "performance" in lower:
        return "performance"
    if "import" in lower or "wrapper" in lower or "lint" in lower or "format" in lower:
        return "quality"
    return "release"


def _summary_counts(gates: list[GateRecord]) -> dict[str, int]:
    summary = dict.fromkeys(DASHBOARD_STATUSES, 0)
    for gate in gates:
        summary[gate.status] = summary.get(gate.status, 0) + 1
    return summary


def _overall_status(summary: dict[str, int]) -> str:
    if summary.get("failed", 0):
        return "failed"
    if summary.get("warning", 0) or summary.get("not-run", 0):
        return "warning"
    if summary.get("passed", 0):
        return "passed"
    if summary.get("skipped", 0):
        return "skipped"
    return "not-run"


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    return str(value)


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

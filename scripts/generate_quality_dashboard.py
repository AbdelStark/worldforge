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
SRC = ROOT / "src"
for path in (SCRIPTS, SRC):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from generate_release_evidence import (  # noqa: E402
    CHECKOUT_SAFE_GATES,
    LIVE_PROVIDER_ENV,
    ReleaseGate,
)

from worldforge.artifact_io import write_json_artifact  # noqa: E402
from worldforge.models import dump_json  # noqa: E402

QUALITY_DASHBOARD_SCHEMA_VERSION = 1
DEFAULT_OUTPUT_DIR = ROOT / ".worldforge" / "quality-dashboard"
DEFAULT_JSON_OUTPUT = DEFAULT_OUTPUT_DIR / "quality-dashboard.json"
DEFAULT_MARKDOWN_OUTPUT = DEFAULT_OUTPUT_DIR / "quality-dashboard.md"
DEFAULT_RELEASE_EVIDENCE = ROOT / ".worldforge" / "release-evidence" / "release-evidence.json"
DEFAULT_DEPENDENCY_AUDIT = ROOT / ".worldforge" / "dependency-audit" / "dependency-audit.json"
DEFAULT_CORE_PERFORMANCE = ROOT / ".worldforge" / "core-performance" / "core-performance.json"
CORE_PERFORMANCE_COMMAND = (
    "uv run python scripts/check_core_performance.py "
    "--workspace-dir .worldforge/core-performance "
    "--output .worldforge/core-performance/core-performance.json"
)
CORE_PERFORMANCE_REGENERATE_STEP = (
    "Regenerate the artifact with `uv run python scripts/check_core_performance.py "
    "--output <path>`."
)
LIVE_PROVIDER_EVIDENCE_COMMAND = (
    "uv run python scripts/generate_release_evidence.py --run-manifest <path>"
)
DASHBOARD_STATUSES = ("passed", "failed", "warning", "skipped", "not-run")
GATE_CATEGORY_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("docs", ("doc", "provider catalog")),
    ("tests", ("test", "coverage")),
    ("package", ("package", "build")),
    ("security", ("dependency",)),
    ("performance", ("performance",)),
    ("quality", ("import", "wrapper", "lint", "format")),
)

SECRET_PATTERN = re.compile(
    r"(api[_-]?key|authorization|bearer\s+[a-z0-9._~-]+|password|secret|signature|token=|"
    r"x-amz-signature|nvidia_api_key)",
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
    write_json_artifact(json_output, dashboard)
    markdown_output.parent.mkdir(parents=True, exist_ok=True)
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

    lines = _dashboard_header_lines(payload)
    lines.extend(_dashboard_summary_lines(payload))
    lines.extend(_dashboard_gate_table_lines(payload))
    lines.extend(_dashboard_raw_failure_lines(payload))
    lines.extend(_dashboard_skipped_check_lines(payload))
    lines.extend(["", "## Claim Boundary", "", payload["claim_boundary"], ""])
    return "\n".join(lines)


def _dashboard_header_lines(payload: dict[str, Any]) -> list[str]:
    first_failed = payload.get("first_failed_gate")
    first_failed_text = first_failed["name"] if isinstance(first_failed, dict) else "-"
    return [
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
    ]


def _dashboard_summary_lines(payload: dict[str, Any]) -> list[str]:
    lines = [
        "## Summary",
        "",
        "| Status | Count |",
        "| --- | ---: |",
    ]
    lines.extend(
        f"| `{status}` | {payload['summary'].get(status, 0)} |" for status in DASHBOARD_STATUSES
    )
    return lines


def _dashboard_gate_table_lines(payload: dict[str, Any]) -> list[str]:
    lines = [
        "",
        "## Gates",
        "",
        "| Gate | Category | Status | Command | Source | First triage step |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    lines.extend(_dashboard_gate_table_row(gate) for gate in payload["gates"])
    return lines


def _dashboard_gate_table_row(gate: dict[str, Any]) -> str:
    command = f"`{gate['command']}`" if gate["command"] else "-"
    source = gate["source"] or "-"
    return (
        f"| {gate['name']} | {gate['category']} | `{gate['status']}` | {command} | "
        f"{source} | {gate['first_triage_step']} |"
    )


def _dashboard_raw_failure_lines(payload: dict[str, Any]) -> list[str]:
    lines = ["", "## Raw Failure Details", ""]
    issue_gates = _dashboard_issue_gates(payload)
    if issue_gates:
        for gate in issue_gates:
            lines.extend(_dashboard_issue_gate_lines(gate))
    else:
        lines.append("- No failed, warning, or not-run gates.")
    return lines


def _dashboard_issue_gates(payload: dict[str, Any]) -> list[dict[str, Any]]:
    return [gate for gate in payload["gates"] if gate["status"] in {"failed", "warning", "not-run"}]


def _dashboard_issue_gate_lines(gate: dict[str, Any]) -> list[str]:
    return [
        f"### {gate['name']}",
        "",
        f"- Status: `{gate['status']}`",
        f"- Source: {gate['source'] or '-'}",
        f"- Summary: {gate['summary']}",
        f"- First triage step: {gate['first_triage_step']}",
        "",
        "```json",
        dump_json(gate["raw_details"], indent=2),
        "```",
        "",
    ]


def _dashboard_skipped_check_lines(payload: dict[str, Any]) -> list[str]:
    lines = ["", "## Skipped Checks", ""]
    skipped = _dashboard_skipped_gates(payload)
    if skipped:
        lines.extend(_dashboard_skipped_gate_line(gate) for gate in skipped)
    else:
        lines.append("- No skipped checks.")
    return lines


def _dashboard_skipped_gates(payload: dict[str, Any]) -> list[dict[str, Any]]:
    return [gate for gate in payload["gates"] if gate["status"] == "skipped"]


def _dashboard_skipped_gate_line(gate: dict[str, Any]) -> str:
    host_owned = " host-owned" if gate.get("host_owned") else ""
    return f"- `{gate['name']}`:{host_owned} {gate['summary']}"


def _release_gate_records(path: Path, payload: dict[str, Any] | None) -> list[GateRecord]:
    expected = _expected_release_gates()
    records_by_name = _validation_gate_rows_by_name(payload)

    records: list[GateRecord] = []
    for gate in CHECKOUT_SAFE_GATES:
        raw = records_by_name.pop(gate.name, None)
        records.append(
            _release_gate_record_for_expected_gate(
                path,
                gate,
                raw,
                payload_available=payload is not None,
            )
        )

    for name, raw in sorted(records_by_name.items()):
        records.append(_release_gate_record(path, raw, expected.get(name)))
    return records


def _expected_release_gates() -> dict[str, ReleaseGate]:
    return {gate.name: gate for gate in CHECKOUT_SAFE_GATES}


def _validation_gate_rows_by_name(payload: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    if payload is None:
        return {}
    raw_gates = payload.get("validation_gates", [])
    if not isinstance(raw_gates, list):
        return {}
    return {
        str(gate.get("name")): gate
        for gate in raw_gates
        if isinstance(gate, dict) and gate.get("name")
    }


def _release_gate_record_for_expected_gate(
    path: Path,
    gate: ReleaseGate,
    raw: dict[str, Any] | None,
    *,
    payload_available: bool,
) -> GateRecord:
    if raw is not None:
        return _release_gate_record(path, raw, gate)
    return _missing_release_gate_record(path, gate, payload_available=payload_available)


def _missing_release_gate_record(
    path: Path,
    gate: ReleaseGate,
    *,
    payload_available: bool,
) -> GateRecord:
    return GateRecord(
        name=gate.name,
        status="not-run",
        command=gate.command,
        source=_display_path(path) if payload_available else "",
        summary=(
            "No release evidence row was found for this expected gate."
            if payload_available
            else "Release evidence is missing."
        ),
        first_triage_step="Run `uv run python scripts/generate_release_evidence.py --run-gates`.",
        category=_gate_category(gate.name),
        raw_details={
            "expected_command": gate.command,
            "source_path": _display_path(path),
            "reason": "missing-row" if payload_available else "missing-release-evidence",
        },
    )


def _release_gate_record(
    path: Path,
    raw: dict[str, Any],
    expected: ReleaseGate | None,
) -> GateRecord:
    raw_status = _release_gate_raw_status(raw)
    status = _normalize_release_status(raw_status)
    command = _release_gate_command(raw, expected)
    triage = _release_gate_triage_step(raw, expected)
    name = _release_gate_name(raw, expected)
    return GateRecord(
        name=name,
        status=status,
        command=command,
        source=_display_path(path),
        summary=_release_gate_summary(raw, raw_status=raw_status, status=status),
        first_triage_step=triage,
        category=_gate_category(name),
        started_at=_optional_str(raw.get("started_at")),
        finished_at=_optional_str(raw.get("finished_at")),
        raw_details=_release_gate_raw_details(path, raw, raw_status=raw_status, triage=triage),
    )


def _release_gate_raw_status(raw: dict[str, Any]) -> str:
    return str(raw.get("status") or "")


def _release_gate_command(raw: dict[str, Any], expected: ReleaseGate | None) -> str:
    return str(raw.get("command") or _expected_release_gate_command(expected))


def _expected_release_gate_command(expected: ReleaseGate | None) -> str:
    if expected is None:
        return ""
    return expected.command


def _release_gate_triage_step(raw: dict[str, Any], expected: ReleaseGate | None) -> str:
    return str(raw.get("triage_step") or _expected_release_gate_triage_step(expected))


def _expected_release_gate_triage_step(expected: ReleaseGate | None) -> str:
    if expected is None:
        return "Inspect source."
    return expected.triage_step


def _release_gate_name(raw: dict[str, Any], expected: ReleaseGate | None) -> str:
    return str(raw.get("name") or _expected_release_gate_name(expected))


def _expected_release_gate_name(expected: ReleaseGate | None) -> str:
    if expected is None:
        return "Unknown gate"
    return expected.name


def _release_gate_summary(
    raw: dict[str, Any],
    *,
    raw_status: str,
    status: str,
) -> str:
    summary_parts = [f"release gate reported `{raw_status or status}`"]
    if raw.get("exit_code") is not None:
        summary_parts.append(f"exit code {raw['exit_code']}")
    if raw.get("duration_ms") is not None:
        summary_parts.append(f"duration {raw['duration_ms']} ms")
    return ", ".join(summary_parts)


def _release_gate_raw_details(
    path: Path,
    raw: dict[str, Any],
    *,
    raw_status: str,
    triage: str,
) -> dict[str, Any]:
    return {
        "source_path": _display_path(path),
        "release_status": raw_status,
        "exit_code": raw.get("exit_code"),
        "duration_ms": raw.get("duration_ms"),
        "stdout_tail": raw.get("stdout_tail", ""),
        "stderr_tail": raw.get("stderr_tail", ""),
        "triage_step": triage,
    }


def _live_provider_records(path: Path, payload: dict[str, Any] | None) -> list[GateRecord]:
    if payload is None:
        return _missing_live_provider_records(path)
    return [_live_provider_record(path, row) for row in _live_provider_rows(payload)]


def _missing_live_provider_records(path: Path) -> list[GateRecord]:
    return [_missing_live_provider_record(path, provider) for provider in sorted(LIVE_PROVIDER_ENV)]


def _missing_live_provider_record(path: Path, provider: str) -> GateRecord:
    return GateRecord(
        name=f"Optional live provider: {provider}",
        status="skipped",
        command=LIVE_PROVIDER_EVIDENCE_COMMAND,
        source="",
        summary="No release evidence was available; host-owned live evidence was not read.",
        first_triage_step="Link a prepared-host run_manifest.json through release evidence.",
        category="optional-runtime",
        host_owned=True,
        raw_details={
            "provider": provider,
            "reason": "missing-release-evidence",
            "source_path": _display_path(path),
        },
    )


def _live_provider_rows(payload: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for key in ("live_provider_evidence", "extra_live_provider_evidence"):
        rows.extend(_dict_rows(payload.get(key, [])))
    return rows


def _dict_rows(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _live_provider_record(path: Path, row: dict[str, Any]) -> GateRecord:
    provider = str(row.get("provider") or "unknown")
    provider_status = str(row.get("status") or "")
    status, host_owned = _normalize_live_provider_status(provider_status)
    reason = str(row.get("reason") or "")
    return GateRecord(
        name=f"Optional live provider: {provider}",
        status=status,
        command=LIVE_PROVIDER_EVIDENCE_COMMAND,
        source=_display_path(path),
        summary=_live_provider_summary(reason, provider_status, status),
        first_triage_step=_live_provider_triage_step(status, host_owned),
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


def _live_provider_summary(reason: str, provider_status: str, status: str) -> str:
    if reason:
        return reason
    return f"release evidence reported `{provider_status or status}`"


def _live_provider_triage_step(status: str, host_owned: bool) -> str:
    if host_owned or status == "skipped":
        return "Link a prepared-host run_manifest.json or keep the host-owned skip explicit."
    return "Inspect the linked run_manifest.json and provider smoke output."


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
    if payload is None:
        return _missing_core_performance_record(path)
    shape_error = _core_performance_shape_error(path, payload)
    if shape_error is not None:
        return shape_error
    return _valid_core_performance_record(path, payload)


def _core_performance_shape_error(path: Path, payload: dict[str, Any]) -> GateRecord | None:
    if payload.get("status") == "invalid-json" or not isinstance(payload.get("passed"), bool):
        return _invalid_core_performance_passed_record(path, payload)
    results = payload.get("results", [])
    if not isinstance(results, list):
        return _invalid_core_performance_results_record(path, results)
    return None


def _valid_core_performance_record(path: Path, payload: dict[str, Any]) -> GateRecord:
    results = _core_performance_results(payload)
    passed = payload.get("passed") is True
    failed_results = _failed_core_performance_results(results)
    incoherent_pass = passed and bool(failed_results)
    incoherent_failure = not passed and not failed_results
    return GateRecord(
        name="Core performance artifact",
        status=_core_performance_status(passed=passed, failed_results=failed_results),
        command=CORE_PERFORMANCE_COMMAND,
        source=_display_path(path),
        summary=_core_performance_summary(
            failed_results=failed_results,
            incoherent_pass=incoherent_pass,
            incoherent_failure=incoherent_failure,
        ),
        first_triage_step="Inspect the failing result row before changing budgets.",
        category="performance",
        raw_details={
            "source_path": _display_path(path),
            "passed": passed,
            "failed_results": failed_results,
            "results": results,
            "incoherent_pass": incoherent_pass,
            "incoherent_failure": incoherent_failure,
            "preserved_workspace": payload.get("preserved_workspace"),
        },
    )


def _core_performance_results(payload: dict[str, Any]) -> list[Any]:
    results = payload.get("results", [])
    return results if isinstance(results, list) else []


def _missing_core_performance_record(path: Path) -> GateRecord:
    return GateRecord(
        name="Core performance artifact",
        status="not-run",
        command=CORE_PERFORMANCE_COMMAND,
        source="",
        summary="Core performance JSON was not found.",
        first_triage_step="Run `uv run python scripts/check_core_performance.py --output <path>`.",
        category="performance",
        raw_details={"source_path": _display_path(path), "reason": "missing-artifact"},
    )


def _invalid_core_performance_passed_record(
    path: Path,
    payload: dict[str, Any],
) -> GateRecord:
    return GateRecord(
        name="Core performance artifact",
        status="warning",
        command=CORE_PERFORMANCE_COMMAND,
        source=_display_path(path),
        summary="Core performance JSON is missing a boolean passed field.",
        first_triage_step=CORE_PERFORMANCE_REGENERATE_STEP,
        category="performance",
        raw_details={
            "source_path": _display_path(path),
            "reason": "invalid-shape",
            "error": payload.get("error"),
            "passed": payload.get("passed"),
        },
    )


def _invalid_core_performance_results_record(path: Path, results: object) -> GateRecord:
    return GateRecord(
        name="Core performance artifact",
        status="warning",
        command=CORE_PERFORMANCE_COMMAND,
        source=_display_path(path),
        summary="Core performance JSON is missing a results list.",
        first_triage_step=CORE_PERFORMANCE_REGENERATE_STEP,
        category="performance",
        raw_details={
            "source_path": _display_path(path),
            "reason": "invalid-shape",
            "results_type": type(results).__name__,
        },
    )


def _failed_core_performance_results(results: list[Any]) -> list[dict[str, Any]]:
    return [
        result for result in results if isinstance(result, dict) and result.get("passed") is False
    ]


def _core_performance_status(
    *,
    passed: bool,
    failed_results: list[dict[str, Any]],
) -> str:
    return "failed" if failed_results or not passed else "passed"


def _core_performance_summary(
    *,
    failed_results: list[dict[str, Any]],
    incoherent_pass: bool,
    incoherent_failure: bool,
) -> str:
    if incoherent_pass:
        return (
            f"top-level passed=true contradicted by {len(failed_results)} failed performance "
            "budget rows"
        )
    if failed_results:
        return f"{len(failed_results)} performance budget rows failed"
    if incoherent_failure:
        return "top-level passed=false without failed performance budget rows"
    return "all recorded core performance rows passed"


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
    for category, keywords in GATE_CATEGORY_RULES:
        if any(keyword in lower for keyword in keywords):
            return category
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
        sanitized: dict[str, Any] = {}
        for key, item in value.items():
            sanitized_key = _sanitize_text(str(key))
            unique_key = sanitized_key
            suffix = 2
            while unique_key in sanitized:
                unique_key = f"{sanitized_key}#{suffix}"
                suffix += 1
            sanitized[unique_key] = _sanitize_json(item)
        return sanitized
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

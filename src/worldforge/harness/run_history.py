"""Textual-free preserved-run history helpers for TheWorldHarness."""

from __future__ import annotations

import json
import re
import shlex
from dataclasses import dataclass, replace
from datetime import date, datetime
from pathlib import Path

from worldforge.harness.models import HarnessFlow, HarnessMetric, HarnessRun, HarnessStep
from worldforge.harness.workspace import list_run_workspaces
from worldforge.models import CAPABILITY_NAMES, JSONDict, WorldForgeError

_SAFE_ARTIFACT_SUFFIXES = {"json", "jsonl", "md", "csv", "txt"}
_SECRET_FLAG_PATTERN = re.compile(
    r"^(--?.*(api[-_]?key|token|secret|password|signature).*)$",
    re.IGNORECASE,
)
_SECRET_ASSIGNMENT_PATTERN = re.compile(
    r"^([^=\s]*(api[-_]?key|token|secret|password|signature)[^=\s]*)=.*$",
    re.IGNORECASE,
)
_UNSAFE_URL_PATTERN = re.compile(
    r"^https?://[^\s\"']+[?&](token|signature|sig|key|api_key)=",
    re.IGNORECASE,
)


@dataclass(frozen=True, slots=True)
class RunHistoryFilter:
    """Filter values for preserved harness run history."""

    provider: str | None = None
    capability: str | None = None
    status: str | None = None
    created_from: date | None = None
    created_to: date | None = None
    artifact_type: str | None = None

    @classmethod
    def from_strings(
        cls,
        *,
        provider: str | None = None,
        capability: str | None = None,
        status: str | None = None,
        created_from: str | None = None,
        created_to: str | None = None,
        artifact_type: str | None = None,
    ) -> RunHistoryFilter:
        """Build a filter from CLI/TUI string fields."""

        return cls(
            provider=_clean_filter(provider),
            capability=_clean_filter(capability),
            status=_clean_filter(status),
            created_from=parse_history_date(created_from),
            created_to=parse_history_date(created_to),
            artifact_type=_clean_filter(artifact_type),
        )


@dataclass(frozen=True, slots=True)
class RunHistoryRecord:
    """A checkout-safe preserved-run summary for CLI and TUI views."""

    run_id: str
    kind: str
    status: str
    provider: str
    operation: str
    capability: str
    capabilities: tuple[str, ...]
    created_at: str
    created_date: date | None
    command: str
    rerun_command: str
    failure_summary: str
    safe_artifact_types: tuple[str, ...]
    artifact_count: int
    event_count: int
    path: Path
    display_path: str
    issue_bundle_command: str
    issue_bundle_path: str
    comparison_command: str | None
    recovery_command: str | None

    def to_dict(self) -> JSONDict:
        return {
            "run_id": self.run_id,
            "kind": self.kind,
            "status": self.status,
            "provider": self.provider,
            "operation": self.operation,
            "capability": self.capability,
            "capabilities": list(self.capabilities),
            "created_at": self.created_at,
            "command": self.command,
            "rerun_command": self.rerun_command,
            "failure_summary": self.failure_summary,
            "safe_artifact_types": list(self.safe_artifact_types),
            "artifact_count": self.artifact_count,
            "event_count": self.event_count,
            "path": self.display_path,
            "issue_bundle_command": self.issue_bundle_command,
            "issue_bundle_path": self.issue_bundle_path,
            "comparison_command": self.comparison_command,
            "recovery_command": self.recovery_command,
        }


def parse_history_date(value: str | None) -> date | None:
    """Parse an ISO date value used by run-history filters."""

    if value is None or not value.strip():
        return None
    try:
        return date.fromisoformat(value.strip())
    except ValueError as exc:
        raise WorldForgeError(f"run history date must use YYYY-MM-DD: {value}") from exc


def list_run_history(
    workspace_dir: Path,
    *,
    filters: RunHistoryFilter | None = None,
    limit: int | None = None,
) -> tuple[RunHistoryRecord, ...]:
    """Return preserved run summaries sorted newest first."""

    records = tuple(
        _record_from_manifest(manifest, workspace_dir=workspace_dir)
        for manifest in list_run_workspaces(workspace_dir)
    )
    active_filter = filters or RunHistoryFilter()
    filtered = tuple(record for record in records if _matches_filter(record, active_filter))
    if limit is not None:
        return filtered[:limit]
    return filtered


def preserved_run_from_path(path: Path, *, state_dir: Path) -> HarnessRun:
    """Open a preserved run workspace as a ``HarnessRun`` without invoking providers."""

    run_path = _run_path_from_input(path)
    manifest = _load_manifest(run_path)
    report_path = _report_json_path(run_path, manifest)
    if report_path is not None and str(manifest.get("kind", "")) in {"eval", "benchmark"}:
        from worldforge.harness.flows import report_run_from_path

        return replace(
            report_run_from_path(report_path, state_dir=state_dir),
            workspace_path=run_path,
        )

    workspace_dir = run_path.parent.parent
    record = _record_from_manifest({**manifest, "path": str(run_path)}, workspace_dir=workspace_dir)
    inspector = _read_json(run_path / "results" / "inspector.json")
    flow = _flow_from_record(record, inspector)
    steps = _steps_from_record(record, inspector)
    metrics = _metrics_from_record(record, inspector)
    provider_events = _provider_events_from_inspector(inspector)
    validation_errors = _validation_errors_from_manifest(manifest)
    return HarnessRun(
        flow=flow,
        state_dir=state_dir,
        summary={
            "run_id": record.run_id,
            "kind": record.kind,
            "status": record.status,
            "provider": record.provider,
            "operation": record.operation,
            "rerun_command": record.rerun_command,
            "issue_bundle_command": record.issue_bundle_command,
            "recovery_command": record.recovery_command,
            "failure_summary": record.failure_summary,
        },
        steps=steps,
        metrics=metrics,
        transcript=_transcript_from_record(record),
        kind="flow" if record.kind == "flow" else record.kind,  # type: ignore[arg-type]
        workspace_path=run_path,
        provider_events=provider_events,
        validation_errors=tuple(validation_errors),
    )


def run_history_markdown(records: tuple[RunHistoryRecord, ...]) -> str:
    """Render preserved run history as Markdown."""

    lines = [
        "# TheWorldHarness Run History",
        "",
        "| Run | Kind | Status | Provider | Capability | Artifacts | Recovery |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for record in records:
        artifacts = ", ".join(record.safe_artifact_types) or "-"
        recovery = f"`{record.recovery_command}`" if record.recovery_command else "-"
        lines.append(
            "| `{run_id}` | {kind} | {status} | {provider} | {capability} | {artifacts} | "
            "{recovery} |".format(
                run_id=record.run_id,
                kind=record.kind or "-",
                status=record.status or "-",
                provider=record.provider or "-",
                capability=record.capability or "-",
                artifacts=artifacts,
                recovery=recovery,
            )
        )
    if not records:
        lines.append("| - | - | - | - | - | - | - |")
    lines.extend(
        [
            "",
            "## Rerun Commands",
            "",
        ]
    )
    if records:
        lines.extend(f"- `{record.run_id}`: `{record.rerun_command}`" for record in records)
    else:
        lines.append("- No preserved runs matched the filter.")
    return "\n".join(lines) + "\n"


def _record_from_manifest(manifest: JSONDict, *, workspace_dir: Path) -> RunHistoryRecord:
    run_id = str(manifest.get("run_id") or Path(str(manifest.get("path", ""))).name)
    kind = str(manifest.get("kind") or "")
    status = str(manifest.get("status") or "")
    provider = _provider_label(manifest)
    operation = str(manifest.get("operation") or "")
    capabilities = _capabilities(manifest)
    capability = capabilities[0] if capabilities else ""
    created_at = str(manifest.get("created_at") or "")
    created_date = _date_from_created_at(created_at)
    command = str(manifest.get("command") or "").strip()
    workspace_display = _workspace_display(workspace_dir)
    display_path = f"{workspace_display}/runs/{run_id}"
    issue_bundle_command = (
        f"worldforge runs bundle {shlex.quote(run_id)} --workspace-dir "
        f"{shlex.quote(workspace_display)}"
    )
    comparison_command = None
    if kind in {"eval", "benchmark"}:
        comparison_command = f"worldforge runs compare {shlex.quote(display_path)} <other-run>"
    failure_summary = _failure_summary(manifest)
    recovery_command = (
        issue_bundle_command if status in {"failed", "cancelled", "skipped"} else None
    )
    run_path = Path(str(manifest.get("path") or Path(workspace_dir) / "runs" / run_id))
    return RunHistoryRecord(
        run_id=run_id,
        kind=kind,
        status=status,
        provider=provider,
        operation=operation,
        capability=capability,
        capabilities=capabilities,
        created_at=created_at,
        created_date=created_date,
        command=command,
        rerun_command=_rerun_command(manifest, workspace_display=workspace_display),
        failure_summary=failure_summary,
        safe_artifact_types=_safe_artifact_types(manifest),
        artifact_count=len(manifest.get("artifact_paths", {}) or {}),
        event_count=int(manifest.get("event_count", 0) or 0),
        path=run_path,
        display_path=display_path,
        issue_bundle_command=issue_bundle_command,
        issue_bundle_path=f"{workspace_display}/issue-bundles/{run_id}",
        comparison_command=comparison_command,
        recovery_command=recovery_command,
    )


def _matches_filter(record: RunHistoryRecord, filters: RunHistoryFilter) -> bool:
    if filters.provider and filters.provider.lower() not in record.provider.lower():
        return False
    if filters.capability:
        capability = filters.capability.lower()
        if capability not in {item.lower() for item in record.capabilities}:
            return False
    if filters.status and filters.status.lower() != record.status.lower():
        return False
    if filters.created_from and (
        record.created_date is None or record.created_date < filters.created_from
    ):
        return False
    if filters.created_to and (
        record.created_date is None or record.created_date > filters.created_to
    ):
        return False
    if filters.artifact_type:
        artifact_type = filters.artifact_type.lower()
        if artifact_type not in {item.lower() for item in record.safe_artifact_types}:
            return False
    return True


def _provider_label(manifest: JSONDict) -> str:
    provider = manifest.get("provider")
    if isinstance(provider, str) and provider.strip():
        return provider.strip()
    input_summary = manifest.get("input_summary")
    if isinstance(input_summary, dict):
        providers = input_summary.get("providers")
        if isinstance(providers, list):
            return ", ".join(str(item) for item in providers if str(item).strip())
    return ""


def _capabilities(manifest: JSONDict) -> tuple[str, ...]:
    input_summary = manifest.get("input_summary")
    found: list[str] = []
    if isinstance(input_summary, dict):
        raw_capabilities = input_summary.get("capabilities")
        if isinstance(raw_capabilities, list):
            found.extend(str(item) for item in raw_capabilities if str(item).strip())
        raw_operations = input_summary.get("operations")
        if isinstance(raw_operations, list):
            found.extend(str(item) for item in raw_operations if str(item) in CAPABILITY_NAMES)
    operation = str(manifest.get("operation") or "")
    if operation in CAPABILITY_NAMES:
        found.append(operation)
    if str(manifest.get("kind") or "") == "flow":
        from worldforge.harness.flows import flow_index

        flow = flow_index().get(operation)
        if flow is not None and flow.capability:
            found.append(flow.capability)
    if not found and str(manifest.get("kind") or "") in {"eval", "benchmark"}:
        found.append(str(manifest.get("kind")))
    return tuple(dict.fromkeys(found))


def _safe_artifact_types(manifest: JSONDict) -> tuple[str, ...]:
    raw_paths = manifest.get("artifact_paths")
    if not isinstance(raw_paths, dict):
        return ()
    found: list[str] = []
    for label, raw_path in sorted(raw_paths.items()):
        if not isinstance(raw_path, str) or not raw_path.strip():
            continue
        path = Path(raw_path)
        if path.is_absolute() or ".." in path.parts:
            continue
        suffix = path.suffix.lower().removeprefix(".")
        if suffix in _SAFE_ARTIFACT_SUFFIXES:
            found.append(str(label))
            found.append(suffix)
    return tuple(dict.fromkeys(item for item in found if item))


def _failure_summary(manifest: JSONDict) -> str:
    result_summary = manifest.get("result_summary")
    if isinstance(result_summary, dict):
        for key in (
            "failure_reason",
            "observed_failure",
            "error",
            "error_message",
            "skip_reason",
            "reason",
        ):
            value = result_summary.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        errors = result_summary.get("validation_errors")
        if isinstance(errors, list) and errors:
            return "; ".join(str(error) for error in errors if str(error).strip())
    status = str(manifest.get("status") or "unknown")
    if status == "failed":
        return "Run failed without a structured failure reason."
    if status == "cancelled":
        return "Run was cancelled before completion."
    if status == "skipped":
        return "Run was skipped without a structured reason."
    return ""


def _rerun_command(manifest: JSONDict, *, workspace_display: str) -> str:
    command = str(manifest.get("command") or "").strip() or _synthesized_command(manifest)
    tokens = _split_command(command)
    sanitized: list[str] = []
    skip_next = False
    for token in tokens:
        if skip_next:
            skip_next = False
            continue
        if _SECRET_FLAG_PATTERN.match(token) and "=" not in token:
            sanitized.extend([token, "<redacted>"])
            skip_next = True
            continue
        sanitized.append(_sanitize_token(token))
    kind = str(manifest.get("kind") or "")
    if kind in {"eval", "benchmark"} and "--run-workspace" not in sanitized:
        sanitized.extend(["--run-workspace", workspace_display])
    return shlex.join(sanitized)


def _synthesized_command(manifest: JSONDict) -> str:
    kind = str(manifest.get("kind") or "")
    provider = _provider_label(manifest) or "mock"
    operation = str(manifest.get("operation") or "")
    if kind == "eval":
        return f"worldforge eval --suite {operation or 'planning'} --provider {provider}"
    if kind == "benchmark":
        return f"worldforge benchmark --provider {provider} --operation {operation or 'predict'}"
    if kind == "flow" and operation:
        return f"worldforge harness --flow {operation}"
    return "worldforge runs list"


def _split_command(command: str) -> list[str]:
    try:
        return shlex.split(command)
    except ValueError:
        return command.split()


def _sanitize_token(token: str) -> str:
    if _UNSAFE_URL_PATTERN.search(token):
        return "<redacted-url>"
    assignment = _SECRET_ASSIGNMENT_PATTERN.match(token)
    if assignment:
        return f"{assignment.group(1)}=<redacted>"
    if _SECRET_FLAG_PATTERN.match(token):
        return token
    if Path(token).is_absolute() or token.startswith("file://"):
        return f"<host-local:{Path(token).name or 'path'}>"
    return token


def _workspace_display(workspace_dir: Path) -> str:
    if not workspace_dir.is_absolute():
        return workspace_dir.as_posix()
    if workspace_dir.name == ".worldforge":
        return ".worldforge"
    return "<workspace-dir>"


def _date_from_created_at(value: str) -> date | None:
    if not value:
        return None
    normalized = value.replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(normalized).date()
    except ValueError:
        return None


def _run_path_from_input(path: Path) -> Path:
    candidate = path.expanduser()
    if candidate.name == "run_manifest.json":
        candidate = candidate.parent
    if candidate.is_file() and candidate.parent.name == "reports":
        candidate = candidate.parent.parent
    manifest = candidate / "run_manifest.json"
    if not manifest.is_file():
        raise WorldForgeError(f"Preserved run manifest not found: {manifest}")
    return candidate.resolve()


def _load_manifest(run_path: Path) -> JSONDict:
    try:
        payload = json.loads((run_path / "run_manifest.json").read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise WorldForgeError(f"Preserved run manifest contains invalid JSON: {run_path}") from exc
    if not isinstance(payload, dict):
        raise WorldForgeError(f"Preserved run manifest must be a JSON object: {run_path}")
    payload = dict(payload)
    payload["path"] = str(run_path)
    return payload


def _report_json_path(run_path: Path, manifest: JSONDict) -> Path | None:
    artifact_paths = manifest.get("artifact_paths")
    if not isinstance(artifact_paths, dict):
        return None
    for label in ("json", "report"):
        raw = artifact_paths.get(label)
        if isinstance(raw, str):
            candidate = (run_path / raw).resolve()
            if candidate.is_file() and candidate.name.endswith(".json"):
                return candidate
    fallback = run_path / "reports" / "report.json"
    return fallback if fallback.is_file() else None


def _flow_from_record(record: RunHistoryRecord, inspector: JSONDict | None) -> HarnessFlow:
    if inspector and isinstance(inspector.get("flow"), dict):
        flow_payload = inspector["flow"]
        return HarnessFlow(
            id=str(flow_payload.get("id") or record.operation or record.run_id),
            title=str(flow_payload.get("title") or record.operation or record.run_id),
            short_title=str(flow_payload.get("short_title") or record.operation or record.kind),
            focus=str(flow_payload.get("focus") or record.kind),
            provider=str(flow_payload.get("provider") or record.provider),
            capability=str(flow_payload.get("capability") or record.capability),
            command=record.rerun_command,
            accent=str(flow_payload.get("accent") or ""),
            summary=str(flow_payload.get("summary") or record.failure_summary or record.status),
        )
    return HarnessFlow(
        id=record.operation or record.run_id,
        title=f"Preserved Run: {record.run_id}",
        short_title=record.run_id,
        focus=record.kind or "run",
        provider=record.provider,
        capability=record.capability,
        command=record.rerun_command,
        accent="",
        summary=record.failure_summary or f"{record.kind} run is {record.status}.",
    )


def _steps_from_record(
    record: RunHistoryRecord,
    inspector: JSONDict | None,
) -> tuple[HarnessStep, ...]:
    if inspector and isinstance(inspector.get("steps"), list):
        steps = [
            HarnessStep(
                title=str(item.get("title", "Step")),
                detail=str(item.get("detail", "")),
                result=str(item.get("result", "")),
                artifact=str(item.get("artifact", "")),
            )
            for item in inspector["steps"]
            if isinstance(item, dict)
        ]
        if steps:
            return tuple(steps)
    recovery = record.recovery_command or record.issue_bundle_command
    return (
        HarnessStep(
            "Load preserved run",
            "Read run_manifest.json and sanitized result summaries.",
            f"{record.kind or 'run'} status: {record.status or 'unknown'}",
            record.display_path,
        ),
        HarnessStep(
            "Prepare recovery action",
            "Use the issue-ready bundle path before attaching artifacts to a public issue.",
            recovery,
            record.issue_bundle_path,
        ),
    )


def _metrics_from_record(
    record: RunHistoryRecord,
    inspector: JSONDict | None,
) -> tuple[HarnessMetric, ...]:
    if inspector and isinstance(inspector.get("metrics"), list):
        metrics = [
            HarnessMetric(
                label=str(item.get("label", "Metric")),
                value=str(item.get("value", "")),
                detail=str(item.get("detail", "")),
            )
            for item in inspector["metrics"]
            if isinstance(item, dict)
        ]
        if metrics:
            return tuple(metrics)
    return (
        HarnessMetric("Status", record.status or "unknown", record.failure_summary),
        HarnessMetric(
            "Artifacts",
            str(record.artifact_count),
            ", ".join(record.safe_artifact_types),
        ),
        HarnessMetric("Events", str(record.event_count), record.capability or record.operation),
    )


def _provider_events_from_inspector(inspector: JSONDict | None) -> tuple[JSONDict, ...]:
    if not inspector or not isinstance(inspector.get("provider_events"), list):
        return ()
    return tuple(dict(item) for item in inspector["provider_events"] if isinstance(item, dict))


def _validation_errors_from_manifest(manifest: JSONDict) -> tuple[str, ...]:
    result_summary = manifest.get("result_summary")
    if not isinstance(result_summary, dict):
        return ()
    errors = result_summary.get("validation_errors")
    if isinstance(errors, str) and errors.strip():
        return (errors.strip(),)
    if isinstance(errors, list):
        return tuple(str(error).strip() for error in errors if str(error).strip())
    return ()


def _transcript_from_record(record: RunHistoryRecord) -> tuple[str, ...]:
    lines = [
        f"run_id: {record.run_id}",
        f"kind: {record.kind}",
        f"status: {record.status}",
        f"provider: {record.provider}",
        f"capabilities: {', '.join(record.capabilities) or '-'}",
        f"rerun: {record.rerun_command}",
        f"issue_bundle: {record.issue_bundle_command}",
    ]
    if record.comparison_command:
        lines.append(f"compare: {record.comparison_command}")
    if record.failure_summary:
        lines.append(f"failure: {record.failure_summary}")
    return tuple(lines)


def _read_json(path: Path) -> JSONDict | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def _clean_filter(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = value.strip()
    return cleaned or None


__all__ = [
    "RunHistoryFilter",
    "RunHistoryRecord",
    "list_run_history",
    "parse_history_date",
    "preserved_run_from_path",
    "run_history_markdown",
]

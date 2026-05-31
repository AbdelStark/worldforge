"""Textual-free preserved-run history helpers."""

from __future__ import annotations

import json
import re
import shlex
from dataclasses import dataclass, replace
from datetime import date, datetime
from pathlib import Path

from worldforge.harness.models import HarnessFlow, HarnessMetric, HarnessRun, HarnessStep
from worldforge.harness.run_history_models import (
    RunHistoryFilter,
    RunHistoryRecord,
    parse_history_date,
)
from worldforge.harness.run_history_rendering import run_history_markdown
from worldforge.harness.workspace import list_run_workspaces
from worldforge.models import CAPABILITY_NAMES, JSONDict, WorldForgeError, require_json_dict

_SAFE_ARTIFACT_SUFFIXES = {"json", "jsonl", "md", "csv", "txt", "html"}
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
_FAILURE_SUMMARY_KEYS: tuple[str, ...] = (
    "failure_reason",
    "observed_failure",
    "error",
    "error_message",
    "skip_reason",
    "reason",
)
_FAILURE_STATUS_DEFAULTS: dict[str, str] = {
    "failed": "Run failed without a structured failure reason.",
    "cancelled": "Run was cancelled before completion.",
    "skipped": "Run was skipped without a structured reason.",
}


@dataclass(frozen=True, slots=True)
class _RunRecordIdentity:
    run_id: str
    kind: str
    status: str
    provider: str
    operation: str
    capabilities: tuple[str, ...]
    capability: str
    created_at: str
    created_date: date | None
    command: str


@dataclass(frozen=True, slots=True)
class _RunRecordPaths:
    run_path: Path
    display_path: str
    issue_bundle_path: str


@dataclass(frozen=True, slots=True)
class _RunRecordCommands:
    rerun: str
    issue_bundle: str
    comparison: str | None
    recovery: str | None


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


def _record_from_manifest(manifest: JSONDict, *, workspace_dir: Path) -> RunHistoryRecord:
    identity = _run_record_identity(manifest)
    workspace_display = _workspace_display(workspace_dir)
    paths = _run_record_paths(
        manifest,
        workspace_dir=workspace_dir,
        workspace_display=workspace_display,
        run_id=identity.run_id,
    )
    commands = _run_record_commands(
        manifest,
        workspace_display=workspace_display,
        identity=identity,
        display_path=paths.display_path,
    )
    return RunHistoryRecord(
        run_id=identity.run_id,
        kind=identity.kind,
        status=identity.status,
        provider=identity.provider,
        operation=identity.operation,
        capability=identity.capability,
        capabilities=identity.capabilities,
        created_at=identity.created_at,
        created_date=identity.created_date,
        command=identity.command,
        rerun_command=commands.rerun,
        failure_summary=_failure_summary(manifest),
        safe_artifact_types=_safe_artifact_types(manifest),
        artifact_count=_artifact_count(manifest),
        event_count=_event_count(manifest),
        path=paths.run_path,
        display_path=paths.display_path,
        issue_bundle_command=commands.issue_bundle,
        issue_bundle_path=paths.issue_bundle_path,
        comparison_command=commands.comparison,
        recovery_command=commands.recovery,
    )


def _run_record_identity(manifest: JSONDict) -> _RunRecordIdentity:
    run_id = str(manifest.get("run_id") or Path(str(manifest.get("path", ""))).name)
    capabilities = _capabilities(manifest)
    created_at = str(manifest.get("created_at") or "")
    return _RunRecordIdentity(
        run_id=run_id,
        kind=str(manifest.get("kind") or ""),
        status=str(manifest.get("status") or ""),
        provider=_provider_label(manifest),
        operation=str(manifest.get("operation") or ""),
        capabilities=capabilities,
        capability=capabilities[0] if capabilities else "",
        created_at=created_at,
        created_date=_date_from_created_at(created_at),
        command=str(manifest.get("command") or "").strip(),
    )


def _run_record_paths(
    manifest: JSONDict,
    *,
    workspace_dir: Path,
    workspace_display: str,
    run_id: str,
) -> _RunRecordPaths:
    return _RunRecordPaths(
        run_path=Path(str(manifest.get("path") or Path(workspace_dir) / "runs" / run_id)),
        display_path=f"{workspace_display}/runs/{run_id}",
        issue_bundle_path=f"{workspace_display}/issue-bundles/{run_id}",
    )


def _run_record_commands(
    manifest: JSONDict,
    *,
    workspace_display: str,
    identity: _RunRecordIdentity,
    display_path: str,
) -> _RunRecordCommands:
    issue_bundle = (
        f"worldforge runs bundle {shlex.quote(identity.run_id)} --workspace-dir "
        f"{shlex.quote(workspace_display)}"
    )
    return _RunRecordCommands(
        rerun=_rerun_command(manifest, workspace_display=workspace_display),
        issue_bundle=issue_bundle,
        comparison=_comparison_command(identity.kind, display_path),
        recovery=_recovery_command(identity.status, issue_bundle),
    )


def _comparison_command(kind: str, display_path: str) -> str | None:
    if kind not in {"eval", "benchmark"}:
        return None
    return f"worldforge runs compare {shlex.quote(display_path)} <other-run>"


def _recovery_command(status: str, issue_bundle_command: str) -> str | None:
    if status not in {"failed", "cancelled", "skipped"}:
        return None
    return issue_bundle_command


def _artifact_count(manifest: JSONDict) -> int:
    artifact_paths = manifest.get("artifact_paths")
    if not isinstance(artifact_paths, dict):
        return 0
    return len(artifact_paths)


def _event_count(manifest: JSONDict) -> int:
    raw_count = manifest.get("event_count")
    if raw_count in (None, ""):
        return 0
    return int(raw_count)


def _matches_filter(record: RunHistoryRecord, filters: RunHistoryFilter) -> bool:
    return all(
        (
            _matches_text_contains(record.provider, filters.provider),
            _matches_collection_item(record.capabilities, filters.capability),
            _matches_text_exact(record.status, filters.status),
            _matches_created_from(record.created_date, filters.created_from),
            _matches_created_to(record.created_date, filters.created_to),
            _matches_collection_item(record.safe_artifact_types, filters.artifact_type),
        )
    )


def _matches_text_contains(value: str, expected: str | None) -> bool:
    return not expected or expected.lower() in value.lower()


def _matches_text_exact(value: str, expected: str | None) -> bool:
    return not expected or expected.lower() == value.lower()


def _matches_collection_item(values: tuple[str, ...], expected: str | None) -> bool:
    return not expected or expected.lower() in {item.lower() for item in values}


def _matches_created_from(created_date: date | None, boundary: date | None) -> bool:
    return boundary is None or (created_date is not None and created_date >= boundary)


def _matches_created_to(created_date: date | None, boundary: date | None) -> bool:
    return boundary is None or (created_date is not None and created_date <= boundary)


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
    kind = str(manifest.get("kind") or "")
    operation = str(manifest.get("operation") or "")
    found = (
        *_input_summary_capabilities(manifest.get("input_summary")),
        *_operation_capabilities(operation),
        *_flow_capabilities(kind=kind, operation=operation),
    )
    if found:
        return tuple(dict.fromkeys(found))
    return _default_run_capabilities(kind)


def _input_summary_capabilities(input_summary: object) -> tuple[str, ...]:
    if not isinstance(input_summary, dict):
        return ()
    return (
        *_string_items(input_summary.get("capabilities")),
        *_known_capability_items(input_summary.get("operations")),
    )


def _string_items(value: object) -> tuple[str, ...]:
    if not isinstance(value, list):
        return ()
    return tuple(str(item) for item in value if str(item).strip())


def _known_capability_items(value: object) -> tuple[str, ...]:
    if not isinstance(value, list):
        return ()
    return tuple(str(item) for item in value if str(item) in CAPABILITY_NAMES)


def _operation_capabilities(operation: str) -> tuple[str, ...]:
    return (operation,) if operation in CAPABILITY_NAMES else ()


def _flow_capabilities(*, kind: str, operation: str) -> tuple[str, ...]:
    if kind != "flow":
        return ()
    from worldforge.harness.flow_catalog import flow_index

    flow = flow_index().get(operation)
    if flow is None or not flow.capability:
        return ()
    return (flow.capability,)


def _default_run_capabilities(kind: str) -> tuple[str, ...]:
    return (kind,) if kind in {"eval", "benchmark"} else ()


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
    result_summary = _run_result_summary(manifest)
    return (
        _structured_failure_summary(result_summary)
        or _validation_failure_summary(result_summary)
        or _status_failure_summary(manifest)
    )


def _run_result_summary(manifest: JSONDict) -> JSONDict:
    result_summary = manifest.get("result_summary")
    if isinstance(result_summary, dict):
        return result_summary
    return {}


def _structured_failure_summary(result_summary: JSONDict) -> str:
    for key in _FAILURE_SUMMARY_KEYS:
        value = result_summary.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _validation_failure_summary(result_summary: JSONDict) -> str:
    errors = result_summary.get("validation_errors")
    if isinstance(errors, list) and errors:
        return "; ".join(str(error).strip() for error in errors if str(error).strip())
    return ""


def _status_failure_summary(manifest: JSONDict) -> str:
    status = str(manifest.get("status") or "unknown")
    return _FAILURE_STATUS_DEFAULTS.get(status, "")


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
        return "worldforge runs list --status failed"
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
    payload = require_json_dict(payload, name=f"Preserved run manifest {run_path}")
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
    flow_payload = _flow_payload_from_inspector(inspector)
    if flow_payload is not None:
        return _flow_from_inspector_payload(record, flow_payload)
    return _fallback_flow_from_record(record)


def _flow_payload_from_inspector(inspector: JSONDict | None) -> JSONDict | None:
    if inspector is None:
        return None
    flow_payload = inspector.get("flow")
    return flow_payload if isinstance(flow_payload, dict) else None


def _flow_field(flow_payload: JSONDict, key: str, fallback: str) -> str:
    return str(flow_payload.get(key) or fallback)


def _flow_from_inspector_payload(
    record: RunHistoryRecord,
    flow_payload: JSONDict,
) -> HarnessFlow:
    return HarnessFlow(
        id=_flow_field(flow_payload, "id", record.operation or record.run_id),
        title=_flow_field(flow_payload, "title", record.operation or record.run_id),
        short_title=_flow_field(flow_payload, "short_title", record.operation or record.kind),
        focus=_flow_field(flow_payload, "focus", record.kind),
        provider=_flow_field(flow_payload, "provider", record.provider),
        capability=_flow_field(flow_payload, "capability", record.capability),
        command=record.rerun_command,
        accent=_flow_field(flow_payload, "accent", ""),
        summary=_flow_field(flow_payload, "summary", record.failure_summary or record.status),
    )


def _fallback_flow_from_record(record: RunHistoryRecord) -> HarnessFlow:
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
        return require_json_dict(payload, name=f"Preserved run JSON {path}")
    except (OSError, json.JSONDecodeError, WorldForgeError):
        return None


__all__ = [
    "RunHistoryFilter",
    "RunHistoryRecord",
    "list_run_history",
    "parse_history_date",
    "preserved_run_from_path",
    "run_history_markdown",
]

"""Local run artifact index for preserved WorldForge runs.

Walks ``<workspace_dir>/runs/`` read-only and summarizes each preserved run
workspace. The index is checkout-safe:

- Stale, missing, or malformed run directories appear as :class:`RunIndexIssue`
  records, never crashes.
- Output is JSON, Markdown, or CSV, always sanitized — only manifest fields and
  safe-artifact suffix metadata are emitted, never raw artifact contents.
- Filters compose with existing :class:`worldforge.harness.run_history.RunHistoryFilter`
  semantics: provider (substring, case-insensitive), capability, status, date
  range, and safe-artifact type.

The indexer never mutates the workspace, never starts a daemon, and does not
maintain its own database — every call re-walks the filesystem. Retention and
cleanup remain owned by ``worldforge runs cleanup``.
"""

from __future__ import annotations

import csv
import io
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from worldforge.harness.run_history import (
    RunHistoryFilter,
    RunHistoryRecord,
    list_run_history,
)
from worldforge.harness.workspace import runs_dir
from worldforge.models import JSONDict, WorldForgeError, dump_json, require_json_dict

RUN_INDEX_SCHEMA_VERSION = 1

_ISSUE_REASONS: tuple[str, ...] = (
    "manifest-missing",
    "manifest-unreadable",
    "manifest-invalid-json",
    "manifest-not-object",
)


@dataclass(frozen=True, slots=True)
class RunIndexIssue:
    """One run directory that could not be summarized cleanly.

    ``reason`` is one of :data:`_ISSUE_REASONS` (e.g. ``manifest-missing``,
    ``manifest-invalid-json``); ``detail`` is a short human-readable note.
    """

    run_dir: str
    reason: str
    detail: str

    def __post_init__(self) -> None:
        if not isinstance(self.run_dir, str) or not self.run_dir.strip():
            raise WorldForgeError("RunIndexIssue run_dir must be a non-empty string.")
        if self.reason not in _ISSUE_REASONS:
            options = ", ".join(_ISSUE_REASONS)
            raise WorldForgeError(f"RunIndexIssue reason must be one of: {options}.")
        if not isinstance(self.detail, str):
            raise WorldForgeError("RunIndexIssue detail must be a string.")

    def to_dict(self) -> JSONDict:
        return {
            "run_dir": self.run_dir,
            "reason": self.reason,
            "detail": self.detail,
        }


@dataclass(frozen=True, slots=True)
class RunIndex:
    """Result of :func:`build_run_index`.

    ``entries`` are the successfully-parsed runs (already filtered if a filter
    was supplied). ``issues`` lists every run directory that could not be
    summarized. ``filter_applied`` is the filter dict (or ``None`` if no filter
    was set), included for provenance so attached output is reproducible.
    """

    schema_version: int
    workspace_dir: str
    generated_at: str
    entries: tuple[RunHistoryRecord, ...]
    issues: tuple[RunIndexIssue, ...]
    filter_applied: JSONDict | None = None

    def to_dict(self) -> JSONDict:
        return {
            "schema_version": self.schema_version,
            "workspace_dir": self.workspace_dir,
            "generated_at": self.generated_at,
            "filter_applied": self.filter_applied,
            "entry_count": len(self.entries),
            "issue_count": len(self.issues),
            "entries": [entry.to_dict() for entry in self.entries],
            "issues": [issue.to_dict() for issue in self.issues],
        }

    def to_json(self, *, indent: int = 2) -> str:
        return dump_json(self.to_dict(), indent=indent) + "\n"

    def to_markdown(self) -> str:
        lines = _run_index_markdown_header(self)
        filter_line = _run_index_filter_line(self.filter_applied)
        if filter_line is not None:
            lines.append(filter_line)
        lines.extend(_run_index_entry_section(self.entries))
        lines.extend(_run_index_issue_section(self.issues))
        return "\n".join(lines) + "\n"

    def to_csv(self) -> str:
        buffer = io.StringIO()
        writer = csv.writer(buffer, lineterminator="\n")
        writer.writerow(
            [
                "run_id",
                "kind",
                "status",
                "provider",
                "capability",
                "created_at",
                "artifact_count",
                "safe_artifact_types",
                "event_count",
                "failure_summary",
                "path",
            ]
        )
        for entry in self.entries:
            writer.writerow(
                [
                    entry.run_id,
                    entry.kind,
                    entry.status,
                    entry.provider,
                    entry.capability,
                    entry.created_at,
                    entry.artifact_count,
                    ";".join(entry.safe_artifact_types),
                    entry.event_count,
                    entry.failure_summary,
                    entry.display_path,
                ]
            )
        return buffer.getvalue()


def _run_index_markdown_header(index: RunIndex) -> list[str]:
    return [
        "# WorldForge Run Index",
        "",
        f"- workspace: `{index.workspace_dir}`",
        f"- generated_at: {index.generated_at}",
        f"- schema_version: {index.schema_version}",
        f"- entries: {len(index.entries)}",
        f"- issues: {len(index.issues)}",
    ]


def _run_index_filter_line(filter_applied: JSONDict | None) -> str | None:
    if not filter_applied:
        return None
    applied = ", ".join(
        f"{key}={value}" for key, value in sorted(filter_applied.items()) if value not in (None, "")
    )
    return f"- filter: {applied}" if applied else None


def _run_index_entry_section(entries: tuple[RunHistoryRecord, ...]) -> list[str]:
    lines = [
        "",
        "## Entries",
        "",
        "| Run | Kind | Status | Provider | Capability | Created | Artifacts | Failure |",
        "| --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    if not entries:
        lines.append("| - | - | - | - | - | - | - | - |")
        return lines
    lines.extend(_run_index_entry_row(entry) for entry in entries)
    return lines


def _run_index_entry_row(entry: RunHistoryRecord) -> str:
    failure = _run_index_table_text(entry.failure_summary)
    kind = _run_index_field_text(entry.kind)
    status = _run_index_field_text(entry.status)
    provider = _run_index_field_text(entry.provider)
    capability = _run_index_field_text(entry.capability)
    created = _run_index_field_text(entry.created_at)
    artifacts = _run_index_artifacts_text(entry.safe_artifact_types)
    return (
        f"| `{entry.run_id}` | {kind} | {status} | {provider} | {capability} | "
        f"{created} | {artifacts} | {failure} |"
    )


def _run_index_issue_section(issues: tuple[RunIndexIssue, ...]) -> list[str]:
    lines = ["", "## Issues", ""]
    if not issues:
        lines.append("- No malformed or unreadable run workspaces.")
        return lines
    lines.extend(["| Path | Reason | Detail |", "| --- | --- | --- |"])
    lines.extend(_run_index_issue_row(issue) for issue in issues)
    return lines


def _run_index_issue_row(issue: RunIndexIssue) -> str:
    detail = _run_index_table_text(issue.detail)
    return f"| `{issue.run_dir}` | {issue.reason} | {detail} |"


def _run_index_table_text(value: str) -> str:
    return value.replace("|", "\\|") if value else "-"


def _run_index_field_text(value: str) -> str:
    if value:
        return value
    return "-"


def _run_index_artifacts_text(values: tuple[str, ...]) -> str:
    artifacts = ", ".join(values)
    if artifacts:
        return artifacts
    return "-"


def build_run_index(
    workspace_dir: Path | str,
    *,
    filters: RunHistoryFilter | None = None,
) -> RunIndex:
    """Build a sanitized index of preserved runs under ``workspace_dir``.

    The function is read-only. Stale, missing, or malformed run directories
    are recorded as :class:`RunIndexIssue` records and the walk continues.
    A non-existent workspace is treated as an empty index, not an error.

    Filters use :class:`RunHistoryFilter` semantics — provider substring,
    capability/status exact match, date range, and safe-artifact type.
    """

    resolved_workspace_dir = _run_index_workspace_dir(workspace_dir)
    _validate_run_index_filters(filters)

    return RunIndex(
        schema_version=RUN_INDEX_SCHEMA_VERSION,
        workspace_dir=str(resolved_workspace_dir),
        generated_at=_utc_timestamp(),
        entries=_run_index_entries(resolved_workspace_dir, filters=filters),
        issues=tuple(_scan_for_issues(resolved_workspace_dir)),
        filter_applied=_run_index_filter_applied(filters),
    )


def _run_index_workspace_dir(workspace_dir: Path | str) -> Path:
    if isinstance(workspace_dir, str):
        if not workspace_dir.strip():
            raise WorldForgeError("workspace_dir must be a non-empty string or Path.")
        return Path(workspace_dir)
    if isinstance(workspace_dir, Path):
        return workspace_dir
    raise WorldForgeError("workspace_dir must be a Path.")


def _validate_run_index_filters(filters: object) -> None:
    if filters is not None and not _looks_like_run_history_filter(filters):
        raise WorldForgeError("filters must be a RunHistoryFilter or None.")


def _run_index_entries(
    workspace_dir: Path,
    *,
    filters: RunHistoryFilter | None,
) -> tuple[RunHistoryRecord, ...]:
    if not runs_dir(workspace_dir).exists():
        return ()
    return tuple(list_run_history(workspace_dir, filters=filters))


def _run_index_filter_applied(filters: RunHistoryFilter | None) -> JSONDict | None:
    if filters is None:
        return None
    return {
        "provider": filters.provider,
        "capability": filters.capability,
        "status": filters.status,
        "created_from": filters.created_from.isoformat() if filters.created_from else None,
        "created_to": filters.created_to.isoformat() if filters.created_to else None,
        "artifact_type": filters.artifact_type,
    }


def _utc_timestamp() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _looks_like_run_history_filter(value: object) -> bool:
    """Duck-type check for :class:`RunHistoryFilter`.

    A strict ``isinstance`` would fail when downstream tests reload
    ``worldforge.harness.run_history`` (for example, to verify it imports
    without Textual): the reloaded module exposes a fresh class object that
    is not the one we imported at module load time. Checking for the
    expected attribute set keeps the public API tolerant of that reload
    pattern without weakening misuse detection.
    """

    return all(
        hasattr(value, attr)
        for attr in (
            "provider",
            "capability",
            "status",
            "created_from",
            "created_to",
            "artifact_type",
        )
    )


def _scan_for_issues(workspace_dir: Path) -> list[RunIndexIssue]:
    """Walk ``runs/`` and record diagnostics for unreadable workspaces."""

    root = runs_dir(workspace_dir)
    if not root.is_dir():
        return []
    return [
        issue
        for run_path in _run_index_run_dirs(root)
        if (issue := _run_index_manifest_issue(run_path)) is not None
    ]


def _run_index_run_dirs(root: Path) -> tuple[Path, ...]:
    return tuple(
        run_path
        for run_path in sorted(root.iterdir(), key=lambda path: path.name, reverse=True)
        if run_path.is_dir()
    )


def _run_index_manifest_issue(run_path: Path) -> RunIndexIssue | None:
    manifest_path = run_path / "run_manifest.json"
    if not manifest_path.is_file():
        return _run_index_issue(
            run_path,
            reason="manifest-missing",
            detail="run_manifest.json not found",
        )
    payload = _read_run_manifest_payload(run_path, manifest_path)
    if isinstance(payload, RunIndexIssue):
        return payload
    if not isinstance(payload, dict):
        return _run_index_issue(
            run_path,
            reason="manifest-not-object",
            detail="manifest payload is not a JSON object",
        )
    return None


def _read_run_manifest_payload(run_path: Path, manifest_path: Path) -> object:
    try:
        text = manifest_path.read_text(encoding="utf-8")
    except OSError as exc:
        return _run_index_issue(run_path, reason="manifest-unreadable", detail=str(exc))
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        return _run_index_issue(run_path, reason="manifest-invalid-json", detail=str(exc))
    if not isinstance(payload, dict):
        return payload
    try:
        return require_json_dict(payload, name=f"Run manifest {manifest_path}")
    except WorldForgeError as exc:
        return _run_index_issue(run_path, reason="manifest-invalid-json", detail=str(exc))


def _run_index_issue(run_path: Path, *, reason: str, detail: str) -> RunIndexIssue:
    return RunIndexIssue(run_dir=str(run_path), reason=reason, detail=detail)


__all__ = [
    "RUN_INDEX_SCHEMA_VERSION",
    "RunIndex",
    "RunIndexIssue",
    "build_run_index",
]

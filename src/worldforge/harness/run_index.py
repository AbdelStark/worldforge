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
from worldforge.models import JSONDict, WorldForgeError

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
        return json.dumps(self.to_dict(), indent=indent, sort_keys=True) + "\n"

    def to_markdown(self) -> str:
        lines: list[str] = [
            "# WorldForge Run Index",
            "",
            f"- workspace: `{self.workspace_dir}`",
            f"- generated_at: {self.generated_at}",
            f"- schema_version: {self.schema_version}",
            f"- entries: {len(self.entries)}",
            f"- issues: {len(self.issues)}",
        ]
        if self.filter_applied:
            applied = ", ".join(
                f"{key}={value}"
                for key, value in sorted(self.filter_applied.items())
                if value not in (None, "")
            )
            if applied:
                lines.append(f"- filter: {applied}")
        lines.extend(
            [
                "",
                "## Entries",
                "",
                "| Run | Kind | Status | Provider | Capability | Created | Artifacts | Failure |",
                "| --- | --- | --- | --- | --- | --- | --- | --- |",
            ]
        )
        if self.entries:
            for entry in self.entries:
                artifacts = ", ".join(entry.safe_artifact_types) or "-"
                failure = (
                    entry.failure_summary.replace("|", "\\|") if entry.failure_summary else "-"
                )
                lines.append(
                    "| `{run_id}` | {kind} | {status} | {provider} | {capability} | "
                    "{created} | {artifacts} | {failure} |".format(
                        run_id=entry.run_id,
                        kind=entry.kind or "-",
                        status=entry.status or "-",
                        provider=entry.provider or "-",
                        capability=entry.capability or "-",
                        created=entry.created_at or "-",
                        artifacts=artifacts,
                        failure=failure,
                    )
                )
        else:
            lines.append("| - | - | - | - | - | - | - | - |")
        lines.extend(["", "## Issues", ""])
        if self.issues:
            lines.append("| Path | Reason | Detail |")
            lines.append("| --- | --- | --- |")
            for issue in self.issues:
                detail = issue.detail.replace("|", "\\|") or "-"
                lines.append(f"| `{issue.run_dir}` | {issue.reason} | {detail} |")
        else:
            lines.append("- No malformed or unreadable run workspaces.")
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

    if isinstance(workspace_dir, str):
        if not workspace_dir.strip():
            raise WorldForgeError("workspace_dir must be a non-empty string or Path.")
        workspace_dir = Path(workspace_dir)
    if not isinstance(workspace_dir, Path):
        raise WorldForgeError("workspace_dir must be a Path.")
    if filters is not None and not _looks_like_run_history_filter(filters):
        raise WorldForgeError("filters must be a RunHistoryFilter or None.")

    issues = _scan_for_issues(workspace_dir)
    if (workspace_dir / "runs").exists():
        entries = list_run_history(workspace_dir, filters=filters)
    else:
        entries = ()

    generated_at = datetime.now(UTC).isoformat().replace("+00:00", "Z")
    filter_applied: JSONDict | None = None
    if filters is not None:
        filter_applied = {
            "provider": filters.provider,
            "capability": filters.capability,
            "status": filters.status,
            "created_from": filters.created_from.isoformat() if filters.created_from else None,
            "created_to": filters.created_to.isoformat() if filters.created_to else None,
            "artifact_type": filters.artifact_type,
        }

    return RunIndex(
        schema_version=RUN_INDEX_SCHEMA_VERSION,
        workspace_dir=str(workspace_dir),
        generated_at=generated_at,
        entries=tuple(entries),
        issues=tuple(issues),
        filter_applied=filter_applied,
    )


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

    issues: list[RunIndexIssue] = []
    root = runs_dir(workspace_dir)
    if not root.is_dir():
        return issues
    for run_path in sorted(root.iterdir(), key=lambda p: p.name, reverse=True):
        if not run_path.is_dir():
            continue
        manifest_path = run_path / "run_manifest.json"
        if not manifest_path.is_file():
            issues.append(
                RunIndexIssue(
                    run_dir=str(run_path),
                    reason="manifest-missing",
                    detail="run_manifest.json not found",
                )
            )
            continue
        try:
            text = manifest_path.read_text(encoding="utf-8")
        except OSError as exc:
            issues.append(
                RunIndexIssue(
                    run_dir=str(run_path),
                    reason="manifest-unreadable",
                    detail=str(exc),
                )
            )
            continue
        try:
            payload = json.loads(text)
        except json.JSONDecodeError as exc:
            issues.append(
                RunIndexIssue(
                    run_dir=str(run_path),
                    reason="manifest-invalid-json",
                    detail=str(exc),
                )
            )
            continue
        if not isinstance(payload, dict):
            issues.append(
                RunIndexIssue(
                    run_dir=str(run_path),
                    reason="manifest-not-object",
                    detail="manifest payload is not a JSON object",
                )
            )
    return issues


__all__ = [
    "RUN_INDEX_SCHEMA_VERSION",
    "RunIndex",
    "RunIndexIssue",
    "build_run_index",
]

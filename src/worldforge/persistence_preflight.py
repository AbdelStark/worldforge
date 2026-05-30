"""Read-only preflight checks for local JSON state and preserved run workspaces."""

from __future__ import annotations

from pathlib import Path

from worldforge.harness.workspace import workspace_root_for_state_dir
from worldforge.models import JSONDict, WorldForgeError
from worldforge.persistence_preflight_rendering import render_state_preflight_markdown
from worldforge.persistence_preflight_reporting import (
    DEFAULT_RETENTION_KEEP,
    DEFAULT_STATE_DIR_DISPLAY,
    DEFAULT_WORKSPACE_DISPLAY,
    _artifact_recovery_command,
    _diagnostic_command,
    _display_path,
    _markdown_cell,
    _sanitize_message,
)
from worldforge.persistence_preflight_runs import (
    _check_run_workspaces,
    _unsafe_artifact_reason,
)
from worldforge.persistence_preflight_worlds import (
    _check_requested_world_ids,
    _check_world_bounding_boxes,
    _check_world_state_dir,
    _world_state_failure_check,
)

STATE_PREFLIGHT_SCHEMA_VERSION = 1

__all__ = (
    "DEFAULT_RETENTION_KEEP",
    "DEFAULT_STATE_DIR_DISPLAY",
    "DEFAULT_WORKSPACE_DISPLAY",
    "STATE_PREFLIGHT_SCHEMA_VERSION",
    "_artifact_recovery_command",
    "_check_world_bounding_boxes",
    "_diagnostic_command",
    "_display_path",
    "_markdown_cell",
    "_sanitize_message",
    "_unsafe_artifact_reason",
    "_world_state_failure_check",
    "preflight_local_state",
    "render_state_preflight_markdown",
)


def preflight_local_state(
    *,
    state_dir: Path,
    workspace_dir: Path | None = None,
    world_ids: tuple[str, ...] = (),
    retention_keep: int = DEFAULT_RETENTION_KEEP,
) -> JSONDict:
    """Inspect local state without creating, deleting, or rewriting files."""

    if retention_keep < 0:
        raise WorldForgeError("retention_keep must be greater than or equal to 0.")

    state_root = state_dir.expanduser()
    workspace_root = (workspace_dir or workspace_root_for_state_dir(state_root)).expanduser()
    issues: list[JSONDict] = []
    stats: JSONDict = {
        "world_files_checked": 0,
        "run_workspaces_checked": 0,
        "requested_world_ids_checked": len(world_ids),
    }

    _check_requested_world_ids(world_ids, issues)
    _check_world_state_dir(state_root, issues, stats)
    _check_run_workspaces(
        workspace_root,
        issues,
        stats,
        retention_keep=retention_keep,
    )

    error_count = sum(1 for issue in issues if issue["severity"] == "error")
    warning_count = sum(1 for issue in issues if issue["severity"] == "warning")
    status = "failed" if error_count else "warning" if warning_count else "passed"
    return {
        "schema_version": STATE_PREFLIGHT_SCHEMA_VERSION,
        "status": status,
        "safe_to_attach": True,
        "state_dir": "<state-dir>",
        "workspace_dir": "<workspace-dir>",
        "retention_keep": retention_keep,
        "diagnostic_command": _diagnostic_command(),
        "recovery_policy": (
            "Export this preflight report before quarantining invalid files; do not silently "
            "delete local state."
        ),
        "counts": {
            **stats,
            "issue_count": len(issues),
            "error_count": error_count,
            "warning_count": warning_count,
        },
        "issues": issues,
    }

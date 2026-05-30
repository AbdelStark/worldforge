"""Run workspace validation helpers for local state preflight."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from worldforge.harness.workspace import runs_dir
from worldforge.models import JSONDict, WorldForgeError, require_json_dict
from worldforge.persistence_preflight_reporting import (
    _SECRET_LIKE_PATTERN,
    DEFAULT_WORKSPACE_DISPLAY,
    _artifact_recovery_command,
    _diagnostic_command,
    _display_path,
    _is_valid_run_id,
    _issue,
    _quarantine_run_command,
    _sanitize_message,
)

_URL_PATTERN = re.compile(r"^[a-z][a-z0-9+.-]*://", re.IGNORECASE)
_VALID_RUN_STATUSES = {"running", "completed", "failed", "skipped", "cancelled"}


@dataclass(frozen=True)
class _RunWorkspaceContext:
    workspace_dir: Path
    run_path: Path

    @property
    def manifest_path(self) -> Path:
        return self.run_path / "run_manifest.json"

    @property
    def run_display_path(self) -> str:
        return _display_path(self.run_path, self.workspace_dir, "workspace-dir")

    @property
    def manifest_display_path(self) -> str:
        return _display_path(self.manifest_path, self.workspace_dir, "workspace-dir")

    @property
    def quarantine_command(self) -> str:
        return _quarantine_run_command(self.run_path)


def _check_run_workspaces(
    workspace_dir: Path,
    issues: list[JSONDict],
    stats: JSONDict,
    *,
    retention_keep: int,
) -> None:
    root = runs_dir(workspace_dir)
    if not _runs_root_is_checkable(root, issues):
        return

    valid_run_ids: list[str] = []
    for run_path in sorted(root.iterdir(), key=lambda item: item.name, reverse=True):
        stats["run_workspaces_checked"] += 1
        context = _RunWorkspaceContext(workspace_dir=workspace_dir, run_path=run_path)
        valid_run_id = _checked_run_workspace_id(context, issues)
        if valid_run_id is not None:
            valid_run_ids.append(valid_run_id)

    valid_run_ids.sort(reverse=True)
    _check_retention_pressure(valid_run_ids, retention_keep=retention_keep, issues=issues)


def _runs_root_is_checkable(root: Path, issues: list[JSONDict]) -> bool:
    if not root.exists():
        return False
    if root.is_dir():
        return True
    issues.append(
        _issue(
            check="runs-dir-invalid",
            severity="error",
            path="<workspace-dir>/runs",
            message="Run workspace path exists but is not a directory.",
            recovery_command=f"{_diagnostic_command()} && move the blocking file aside",
        )
    )
    return False


def _checked_run_workspace_id(
    context: _RunWorkspaceContext,
    issues: list[JSONDict],
) -> str | None:
    if not context.run_path.is_dir():
        _add_stale_run_workspace_issue(
            context,
            issues,
            message="Non-directory entry under runs/ is ignored by run history tooling.",
        )
        return None

    run_id_valid = _check_run_workspace_name(context, issues)
    if not context.manifest_path.is_file():
        _add_stale_run_workspace_issue(
            context,
            issues,
            message="Run workspace has no run_manifest.json and cannot be bundled safely.",
            details={"run_id": context.run_path.name if run_id_valid else "<invalid-run-id>"},
        )
        return None

    manifest = _load_manifest(
        context.manifest_path, workspace_dir=context.workspace_dir, issues=issues
    )
    if manifest is None:
        return None
    if not _check_run_manifest(
        manifest,
        run_path=context.run_path,
        workspace_dir=context.workspace_dir,
        issues=issues,
    ):
        return None
    return str(manifest["run_id"])


def _check_run_workspace_name(
    context: _RunWorkspaceContext,
    issues: list[JSONDict],
) -> bool:
    if _is_valid_run_id(context.run_path.name):
        return True
    _add_stale_run_workspace_issue(
        context,
        issues,
        message="Run workspace directory name is not a valid sortable run id.",
        details={"run_id": "<invalid-run-id>"},
    )
    return False


def _add_stale_run_workspace_issue(
    context: _RunWorkspaceContext,
    issues: list[JSONDict],
    *,
    message: str,
    details: JSONDict | None = None,
) -> None:
    issues.append(
        _issue(
            check="stale-run-workspace",
            severity="warning",
            path=context.run_display_path,
            message=message,
            recovery_command=context.quarantine_command,
            details=details,
        )
    )


def _check_retention_pressure(
    valid_run_ids: list[str],
    *,
    retention_keep: int,
    issues: list[JSONDict],
) -> None:
    if len(valid_run_ids) <= retention_keep:
        return
    stale_ids = valid_run_ids[retention_keep:]
    issues.append(
        _issue(
            check="retention-pressure",
            severity="warning",
            path="<workspace-dir>/runs",
            message=(
                f"{len(valid_run_ids)} valid run workspaces exceed retention_keep={retention_keep}."
            ),
            recovery_command=(
                "uv run worldforge runs cleanup --workspace-dir "
                f"{DEFAULT_WORKSPACE_DISPLAY} --keep {retention_keep} --dry-run"
            ),
            details={"candidate_run_ids": stale_ids[:10], "candidate_count": len(stale_ids)},
        )
    )


def _load_manifest(
    path: Path,
    *,
    workspace_dir: Path,
    issues: list[JSONDict],
) -> JSONDict | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        issues.append(
            _issue(
                check="invalid-run-manifest",
                severity="error",
                path=_display_path(path, workspace_dir, "workspace-dir"),
                message=f"Run manifest could not be decoded: {_sanitize_message(str(exc))}",
                recovery_command=_quarantine_run_command(path.parent),
            )
        )
        return None
    try:
        return require_json_dict(payload, name="Run manifest")
    except WorldForgeError as exc:
        issues.append(
            _issue(
                check="invalid-run-manifest",
                severity="error",
                path=_display_path(path, workspace_dir, "workspace-dir"),
                message=f"Run manifest contains invalid JSON-native values: {exc}",
                recovery_command=_quarantine_run_command(path.parent),
            )
        )
        return None


def _check_run_manifest(
    manifest: JSONDict,
    *,
    run_path: Path,
    workspace_dir: Path,
    issues: list[JSONDict],
) -> bool:
    context = _RunWorkspaceContext(workspace_dir=workspace_dir, run_path=run_path)
    raw_run_id = manifest.get("run_id")
    valid = _run_manifest_id_is_valid(raw_run_id, context, issues)
    valid = _run_manifest_schema_is_valid(manifest, raw_run_id, context, issues) and valid
    valid = _run_manifest_status_is_valid(manifest, raw_run_id, context, issues) and valid

    artifact_paths = manifest.get("artifact_paths", {})
    if not isinstance(artifact_paths, dict):
        _add_invalid_run_manifest_issue(
            context,
            issues,
            message="Run manifest artifact_paths must be an object.",
            details={"run_id": _run_id_detail(raw_run_id)},
        )
        return False

    _check_run_manifest_artifact_paths(
        artifact_paths,
        raw_run_id=raw_run_id,
        context=context,
        issues=issues,
    )
    return valid


def _run_manifest_id_is_valid(
    raw_run_id: object,
    context: _RunWorkspaceContext,
    issues: list[JSONDict],
) -> bool:
    if not isinstance(raw_run_id, str) or not _is_valid_run_id(raw_run_id):
        _add_invalid_run_manifest_issue(
            context,
            issues,
            message="Run manifest run_id is missing or invalid.",
            details={"run_id": "<invalid-run-id>"},
        )
        return False
    if raw_run_id == context.run_path.name:
        return True
    _add_invalid_run_manifest_issue(
        context,
        issues,
        message="Run manifest run_id does not match its workspace directory.",
        details={"run_id": raw_run_id},
    )
    return False


def _run_manifest_schema_is_valid(
    manifest: JSONDict,
    raw_run_id: object,
    context: _RunWorkspaceContext,
    issues: list[JSONDict],
) -> bool:
    if manifest.get("schema_version") == 1:
        return True
    _add_invalid_run_manifest_issue(
        context,
        issues,
        message="Run manifest schema_version must be 1.",
        details={"run_id": _run_id_detail(raw_run_id)},
    )
    return False


def _run_manifest_status_is_valid(
    manifest: JSONDict,
    raw_run_id: object,
    context: _RunWorkspaceContext,
    issues: list[JSONDict],
) -> bool:
    if str(manifest.get("status", "")) in _VALID_RUN_STATUSES:
        return True
    _add_invalid_run_manifest_issue(
        context,
        issues,
        message="Run manifest status is missing or unknown.",
        details={"run_id": _run_id_detail(raw_run_id)},
    )
    return False


def _check_run_manifest_artifact_paths(
    artifact_paths: JSONDict,
    *,
    raw_run_id: object,
    context: _RunWorkspaceContext,
    issues: list[JSONDict],
) -> None:
    for label, raw_path in sorted(artifact_paths.items()):
        reason = _unsafe_artifact_reason(raw_path, run_path=context.run_path)
        if reason is None:
            continue
        issues.append(
            _issue(
                check="unsafe-artifact-path",
                severity="error",
                path=context.manifest_display_path,
                message=f"Run manifest artifact path for label '{label}' is unsafe: {reason}.",
                recovery_command=_artifact_recovery_command(
                    raw_run_id if isinstance(raw_run_id, str) else None
                ),
                details={
                    "run_id": raw_run_id if isinstance(raw_run_id, str) else "<unknown>",
                    "artifact_label": str(label),
                    "artifact_path": "<redacted-unsafe-reference>",
                },
            )
        )


def _add_invalid_run_manifest_issue(
    context: _RunWorkspaceContext,
    issues: list[JSONDict],
    *,
    message: str,
    details: JSONDict,
) -> None:
    issues.append(
        _issue(
            check="invalid-run-manifest",
            severity="error",
            path=context.manifest_display_path,
            message=message,
            recovery_command=context.quarantine_command,
            details=details,
        )
    )


def _run_id_detail(raw_run_id: object) -> str:
    return raw_run_id if isinstance(raw_run_id, str) else "<unknown>"


def _unsafe_artifact_reason(raw_path: Any, *, run_path: Path) -> str | None:
    if not isinstance(raw_path, str) or not raw_path.strip():
        return "reference is not a non-empty relative path"
    value = raw_path.strip()
    if _URL_PATTERN.match(value):
        return "reference is a URL instead of a workspace-relative artifact path"
    if _SECRET_LIKE_PATTERN.search(value):
        return "reference contains secret-like or signed URL material"
    candidate = Path(value)
    if candidate.is_absolute():
        return "reference is an absolute host path"
    if ".." in candidate.parts:
        return "reference contains traversal"
    resolved = (run_path / candidate).resolve()
    run_root = run_path.resolve()
    if resolved != run_root and run_root not in resolved.parents:
        return "reference escapes the run workspace"
    return None

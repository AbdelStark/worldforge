"""Read-only preflight checks for local JSON state and preserved run workspaces."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from worldforge.framework import WorldForge, _validate_storage_id
from worldforge.harness.workspace import runs_dir, validate_run_id, workspace_root_for_state_dir
from worldforge.models import (
    BBox,
    JSONDict,
    Position,
    SceneObject,
    WorldForgeError,
    WorldStateError,
)

STATE_PREFLIGHT_SCHEMA_VERSION = 1
DEFAULT_STATE_DIR_DISPLAY = ".worldforge/worlds"
DEFAULT_WORKSPACE_DISPLAY = ".worldforge"
DEFAULT_RETENTION_KEEP = 20

_SECRET_LIKE_PATTERN = re.compile(
    r"(?:api[_-]?key|authorization|bearer|secret|signature|signed|token|x-amz)",
    re.IGNORECASE,
)
_URL_PATTERN = re.compile(r"^[a-z][a-z0-9+.-]*://", re.IGNORECASE)
_SAFE_NAME_PATTERN = re.compile(r"^[A-Za-z0-9_.-]+$")
_VALID_RUN_STATUSES = {"running", "completed", "failed", "skipped", "cancelled"}


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


def render_state_preflight_markdown(report: JSONDict) -> str:
    """Render a local state preflight report for operator runbooks."""

    counts = report.get("counts", {})
    lines = [
        "# WorldForge Local State Preflight",
        "",
        f"status: `{report.get('status', 'unknown')}`",
        f"safe_to_attach: `{str(report.get('safe_to_attach', False)).lower()}`",
        f"state_dir: `{report.get('state_dir', '<state-dir>')}`",
        f"workspace_dir: `{report.get('workspace_dir', '<workspace-dir>')}`",
        f"retention_keep: `{report.get('retention_keep', DEFAULT_RETENTION_KEEP)}`",
        "",
        f"errors: `{counts.get('error_count', 0)}`",
        f"warnings: `{counts.get('warning_count', 0)}`",
        f"world_files_checked: `{counts.get('world_files_checked', 0)}`",
        f"run_workspaces_checked: `{counts.get('run_workspaces_checked', 0)}`",
        "",
        "Diagnostic command:",
        "",
        f"```bash\n{report.get('diagnostic_command', _diagnostic_command())}\n```",
    ]
    issues = report.get("issues", [])
    if not isinstance(issues, list) or not issues:
        lines.extend(["", "No local state issues were found."])
        return "\n".join(lines)

    lines.extend(
        [
            "",
            "| Severity | Check | Path | Message | Recovery |",
            "| --- | --- | --- | --- | --- |",
        ]
    )
    for issue in issues:
        if not isinstance(issue, dict):
            continue
        lines.append(
            "| "
            f"{_markdown_cell(issue.get('severity'))} | "
            f"{_markdown_cell(issue.get('check'))} | "
            f"{_markdown_cell(issue.get('path'))} | "
            f"{_markdown_cell(issue.get('message'))} | "
            f"{_markdown_cell(issue.get('recovery_command'))} |"
        )
    return "\n".join(lines)


def _check_requested_world_ids(world_ids: tuple[str, ...], issues: list[JSONDict]) -> None:
    for raw_world_id in world_ids:
        try:
            _validate_storage_id(raw_world_id, name="world_id")
        except WorldForgeError:
            issues.append(
                _issue(
                    check="unsafe-world-id",
                    severity="error",
                    path="<input:world_id>",
                    message=(
                        "Requested world id is traversal-shaped or not file-safe; persistence "
                        "will reject it before filesystem access."
                    ),
                    recovery_command=(
                        f"{_diagnostic_command()} && use a world id matching "
                        "[A-Za-z0-9][A-Za-z0-9_.-]*"
                    ),
                    details={"world_id": "<unsafe-world-id>"},
                )
            )


def _check_world_state_dir(state_dir: Path, issues: list[JSONDict], stats: JSONDict) -> None:
    if not state_dir.exists():
        issues.append(
            _issue(
                check="state-dir-missing",
                severity="warning",
                path="<state-dir>",
                message="World state directory does not exist; no persisted worlds were checked.",
                recovery_command=(
                    "uv run worldforge world create lab --provider mock "
                    f"--state-dir {DEFAULT_STATE_DIR_DISPLAY}"
                ),
            )
        )
        return
    if not state_dir.is_dir():
        issues.append(
            _issue(
                check="state-dir-invalid",
                severity="error",
                path="<state-dir>",
                message="World state path exists but is not a directory.",
                recovery_command=(
                    f"{_diagnostic_command()} && move the blocking file aside before using "
                    f"{DEFAULT_STATE_DIR_DISPLAY}"
                ),
            )
        )
        return

    forge = WorldForge(state_dir=state_dir)
    roots = ((state_dir, "state-dir"),)
    for world_file in sorted(state_dir.glob("*.json")):
        stats["world_files_checked"] += 1
        world_id = world_file.stem
        try:
            _validate_storage_id(world_id, name="world file stem")
        except WorldForgeError:
            issues.append(
                _issue(
                    check="unsafe-world-file-id",
                    severity="error",
                    path=_display_path(world_file, state_dir, "state-dir"),
                    message="World JSON filename does not map to a file-safe world id.",
                    recovery_command=_quarantine_world_command(world_file),
                    details={"world_file": _safe_file_name(world_file.name)},
                )
            )
            continue

        payload = _load_json_object(world_file, state_dir=state_dir, issues=issues)
        if payload is None:
            continue
        payload_id = payload.get("id")
        if isinstance(payload_id, str) and payload_id != world_id:
            issues.append(
                _issue(
                    check="world-id-mismatch",
                    severity="warning",
                    path=_display_path(world_file, state_dir, "state-dir"),
                    message="World JSON filename does not match the serialized world id.",
                    recovery_command=(
                        f"{_diagnostic_command()} && export a valid copy with "
                        "`uv run worldforge world export <world-id> --output world.json` before "
                        "renaming or quarantining the mismatched file"
                    ),
                    details={"file_world_id": world_id, "payload_world_id": payload_id},
                )
            )
        try:
            forge.load_world(world_id)
        except WorldStateError as exc:
            issues.append(
                _issue(
                    check=_world_state_failure_check(str(exc)),
                    severity="error",
                    path=_display_path(world_file, state_dir, "state-dir"),
                    message=(
                        f"World state validation failed: {_sanitize_message(str(exc), roots=roots)}"
                    ),
                    recovery_command=_quarantine_world_command(world_file),
                    details={"world_id": world_id},
                )
            )
            continue
        _check_world_bounding_boxes(
            payload,
            world_file=world_file,
            state_dir=state_dir,
            issues=issues,
        )


def _load_json_object(
    path: Path,
    *,
    state_dir: Path,
    issues: list[JSONDict],
) -> JSONDict | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        issues.append(
            _issue(
                check="corrupted-world-json",
                severity="error",
                path=_display_path(path, state_dir, "state-dir"),
                message=f"World JSON could not be decoded: {_sanitize_message(str(exc))}",
                recovery_command=_quarantine_world_command(path),
                details={"world_file": _safe_file_name(path.name)},
            )
        )
        return None
    if not isinstance(payload, dict):
        issues.append(
            _issue(
                check="corrupted-world-json",
                severity="error",
                path=_display_path(path, state_dir, "state-dir"),
                message="World JSON must decode to an object.",
                recovery_command=_quarantine_world_command(path),
                details={"world_file": _safe_file_name(path.name)},
            )
        )
        return None
    return payload


def _check_world_bounding_boxes(
    state: JSONDict,
    *,
    world_file: Path,
    state_dir: Path,
    issues: list[JSONDict],
) -> None:
    seen: set[int] = set()

    def visit(payload: JSONDict, *, context: str) -> None:
        payload_id = id(payload)
        if payload_id in seen:
            return
        seen.add(payload_id)
        objects = payload.get("scene", {}).get("objects", {})
        if isinstance(objects, dict):
            for object_id, raw_object in sorted(objects.items()):
                if not isinstance(raw_object, dict):
                    continue
                object_payload = dict(raw_object)
                object_payload.setdefault("id", str(object_id))
                try:
                    scene_object = SceneObject.from_dict(object_payload)
                except WorldForgeError:
                    continue
                if not _position_inside_bbox(scene_object.position, scene_object.bbox):
                    issues.append(
                        _issue(
                            check="bbox-incoherent",
                            severity="error",
                            path=_display_path(world_file, state_dir, "state-dir"),
                            message=(
                                "Scene object position is outside its bounding box; position "
                                "patches must keep spatial bounds translated with the object pose."
                            ),
                            recovery_command=_quarantine_world_command(world_file),
                            details={
                                "world_id": str(state.get("id", world_file.stem)),
                                "object_id": scene_object.id,
                                "context": context,
                            },
                        )
                    )
        history = payload.get("history", [])
        if isinstance(history, list):
            for index, entry in enumerate(history):
                if isinstance(entry, dict) and isinstance(entry.get("state"), dict):
                    visit(entry["state"], context=f"{context}.history[{index}].state")

    visit(state, context="state")


def _check_run_workspaces(
    workspace_dir: Path,
    issues: list[JSONDict],
    stats: JSONDict,
    *,
    retention_keep: int,
) -> None:
    root = runs_dir(workspace_dir)
    if not root.exists():
        return
    if not root.is_dir():
        issues.append(
            _issue(
                check="runs-dir-invalid",
                severity="error",
                path="<workspace-dir>/runs",
                message="Run workspace path exists but is not a directory.",
                recovery_command=f"{_diagnostic_command()} && move the blocking file aside",
            )
        )
        return

    valid_run_ids: list[str] = []
    for run_path in sorted(root.iterdir(), key=lambda item: item.name, reverse=True):
        stats["run_workspaces_checked"] += 1
        if not run_path.is_dir():
            issues.append(
                _issue(
                    check="stale-run-workspace",
                    severity="warning",
                    path=_display_path(run_path, workspace_dir, "workspace-dir"),
                    message="Non-directory entry under runs/ is ignored by run history tooling.",
                    recovery_command=_quarantine_run_command(run_path),
                )
            )
            continue

        run_id_valid = _is_valid_run_id(run_path.name)
        if not run_id_valid:
            issues.append(
                _issue(
                    check="stale-run-workspace",
                    severity="warning",
                    path=_display_path(run_path, workspace_dir, "workspace-dir"),
                    message="Run workspace directory name is not a valid sortable run id.",
                    recovery_command=_quarantine_run_command(run_path),
                    details={"run_id": "<invalid-run-id>"},
                )
            )

        manifest_path = run_path / "run_manifest.json"
        if not manifest_path.is_file():
            issues.append(
                _issue(
                    check="stale-run-workspace",
                    severity="warning",
                    path=_display_path(run_path, workspace_dir, "workspace-dir"),
                    message="Run workspace has no run_manifest.json and cannot be bundled safely.",
                    recovery_command=_quarantine_run_command(run_path),
                    details={"run_id": run_path.name if run_id_valid else "<invalid-run-id>"},
                )
            )
            continue

        manifest = _load_manifest(manifest_path, workspace_dir=workspace_dir, issues=issues)
        if manifest is None:
            continue
        if _check_run_manifest(
            manifest,
            run_path=run_path,
            workspace_dir=workspace_dir,
            issues=issues,
        ):
            valid_run_ids.append(str(manifest["run_id"]))

    valid_run_ids.sort(reverse=True)
    if len(valid_run_ids) > retention_keep:
        stale_ids = valid_run_ids[retention_keep:]
        issues.append(
            _issue(
                check="retention-pressure",
                severity="warning",
                path="<workspace-dir>/runs",
                message=(
                    f"{len(valid_run_ids)} valid run workspaces exceed retention_keep="
                    f"{retention_keep}."
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
    if not isinstance(payload, dict):
        issues.append(
            _issue(
                check="invalid-run-manifest",
                severity="error",
                path=_display_path(path, workspace_dir, "workspace-dir"),
                message="Run manifest must decode to an object.",
                recovery_command=_quarantine_run_command(path.parent),
            )
        )
        return None
    return payload


def _check_run_manifest(
    manifest: JSONDict,
    *,
    run_path: Path,
    workspace_dir: Path,
    issues: list[JSONDict],
) -> bool:
    valid = True
    raw_run_id = manifest.get("run_id")
    if not isinstance(raw_run_id, str) or not _is_valid_run_id(raw_run_id):
        valid = False
        issues.append(
            _issue(
                check="invalid-run-manifest",
                severity="error",
                path=_display_path(run_path / "run_manifest.json", workspace_dir, "workspace-dir"),
                message="Run manifest run_id is missing or invalid.",
                recovery_command=_quarantine_run_command(run_path),
                details={"run_id": "<invalid-run-id>"},
            )
        )
    elif raw_run_id != run_path.name:
        valid = False
        issues.append(
            _issue(
                check="invalid-run-manifest",
                severity="error",
                path=_display_path(run_path / "run_manifest.json", workspace_dir, "workspace-dir"),
                message="Run manifest run_id does not match its workspace directory.",
                recovery_command=_quarantine_run_command(run_path),
                details={"run_id": raw_run_id},
            )
        )

    if manifest.get("schema_version") != 1:
        valid = False
        issues.append(
            _issue(
                check="invalid-run-manifest",
                severity="error",
                path=_display_path(run_path / "run_manifest.json", workspace_dir, "workspace-dir"),
                message="Run manifest schema_version must be 1.",
                recovery_command=_quarantine_run_command(run_path),
                details={"run_id": raw_run_id if isinstance(raw_run_id, str) else "<unknown>"},
            )
        )
    if str(manifest.get("status", "")) not in _VALID_RUN_STATUSES:
        valid = False
        issues.append(
            _issue(
                check="invalid-run-manifest",
                severity="error",
                path=_display_path(run_path / "run_manifest.json", workspace_dir, "workspace-dir"),
                message="Run manifest status is missing or unknown.",
                recovery_command=_quarantine_run_command(run_path),
                details={"run_id": raw_run_id if isinstance(raw_run_id, str) else "<unknown>"},
            )
        )

    artifact_paths = manifest.get("artifact_paths", {})
    if not isinstance(artifact_paths, dict):
        valid = False
        issues.append(
            _issue(
                check="invalid-run-manifest",
                severity="error",
                path=_display_path(run_path / "run_manifest.json", workspace_dir, "workspace-dir"),
                message="Run manifest artifact_paths must be an object.",
                recovery_command=_quarantine_run_command(run_path),
                details={"run_id": raw_run_id if isinstance(raw_run_id, str) else "<unknown>"},
            )
        )
        return valid

    for label, raw_path in sorted(artifact_paths.items()):
        reason = _unsafe_artifact_reason(raw_path, run_path=run_path)
        if reason is None:
            continue
        issues.append(
            _issue(
                check="unsafe-artifact-path",
                severity="error",
                path=_display_path(run_path / "run_manifest.json", workspace_dir, "workspace-dir"),
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
    return valid


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


def _position_inside_bbox(position: Position, bbox: BBox) -> bool:
    return (
        bbox.min.x <= position.x <= bbox.max.x
        and bbox.min.y <= position.y <= bbox.max.y
        and bbox.min.z <= position.z <= bbox.max.z
    )


def _world_state_failure_check(message: str) -> str:
    if "history" in message:
        return "invalid-world-history"
    if "scene object" in message or "bbox" in message:
        return "invalid-world-object"
    return "invalid-world-state"


def _is_valid_run_id(value: str) -> bool:
    try:
        validate_run_id(value)
    except ValueError:
        return False
    return True


def _issue(
    *,
    check: str,
    severity: str,
    path: str,
    message: str,
    recovery_command: str,
    details: JSONDict | None = None,
) -> JSONDict:
    return {
        "check": check,
        "severity": severity,
        "path": path,
        "message": message,
        "recovery_command": recovery_command,
        "safe_to_attach": True,
        "details": details or {},
    }


def _display_path(path: Path, root: Path, label: str) -> str:
    try:
        relative = path.relative_to(root)
    except ValueError:
        try:
            relative = path.resolve().relative_to(root.resolve())
        except ValueError:
            return f"<{label}>/{_safe_file_name(path.name)}"
    if relative == Path("."):
        return f"<{label}>"
    return f"<{label}>/{relative.as_posix()}"


def _safe_file_name(value: str) -> str:
    return value if _SAFE_NAME_PATTERN.fullmatch(value) else "<unsafe-name>"


def _diagnostic_command() -> str:
    return (
        "uv run worldforge world preflight "
        f"--state-dir {DEFAULT_STATE_DIR_DISPLAY} "
        f"--workspace-dir {DEFAULT_WORKSPACE_DISPLAY} "
        "--format json > worldforge-state-preflight.json"
    )


def _quarantine_world_command(world_file: Path) -> str:
    name = _safe_file_name(world_file.name)
    return (
        f"{_diagnostic_command()} && mkdir -p {DEFAULT_WORKSPACE_DISPLAY}/quarantine/worlds && "
        f"mv {DEFAULT_STATE_DIR_DISPLAY}/{name} "
        f"{DEFAULT_WORKSPACE_DISPLAY}/quarantine/worlds/{name}"
    )


def _quarantine_run_command(run_path: Path) -> str:
    name = _safe_file_name(run_path.name)
    return (
        f"{_diagnostic_command()} && mkdir -p {DEFAULT_WORKSPACE_DISPLAY}/quarantine/runs && "
        f"mv {DEFAULT_WORKSPACE_DISPLAY}/runs/{name} "
        f"{DEFAULT_WORKSPACE_DISPLAY}/quarantine/runs/{name}"
    )


def _artifact_recovery_command(run_id: str | None) -> str:
    if run_id and _is_valid_run_id(run_id):
        return (
            f"uv run worldforge runs bundle {run_id} "
            f"--workspace-dir {DEFAULT_WORKSPACE_DISPLAY} --format markdown "
            "> worldforge-run-issue.md && regenerate the run manifest with relative artifact "
            "paths under the run workspace"
        )
    return (
        f"{_diagnostic_command()} && regenerate the run manifest with relative artifact paths "
        "under the run workspace"
    )


def _sanitize_message(
    message: str,
    *,
    roots: tuple[tuple[Path, str], ...] = (),
) -> str:
    sanitized = message
    for root, label in roots:
        sanitized = sanitized.replace(str(root.resolve()), f"<{label}>")
        sanitized = sanitized.replace(str(root), f"<{label}>")
    if _SECRET_LIKE_PATTERN.search(sanitized):
        sanitized = _SECRET_LIKE_PATTERN.sub("<redacted>", sanitized)
    return sanitized


def _markdown_cell(value: object) -> str:
    text = str(value if value is not None else "")
    return text.replace("|", "\\|").replace("\n", " ")

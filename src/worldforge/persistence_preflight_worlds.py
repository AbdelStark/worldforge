"""World JSON validation helpers for local state preflight."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from worldforge._state import validate_storage_id as _validate_storage_id
from worldforge.framework import WorldForge
from worldforge.models import (
    BBox,
    JSONDict,
    Position,
    SceneObject,
    WorldForgeError,
    WorldStateError,
    require_json_dict,
)
from worldforge.persistence_preflight_reporting import (
    DEFAULT_STATE_DIR_DISPLAY,
    _diagnostic_command,
    _display_path,
    _issue,
    _quarantine_world_command,
    _safe_file_name,
    _sanitize_message,
)


@dataclass(frozen=True)
class _WorldFileContext:
    state_dir: Path
    world_file: Path
    world_id: str

    @property
    def display_path(self) -> str:
        return _display_path(self.world_file, self.state_dir, "state-dir")

    @property
    def quarantine_command(self) -> str:
        return _quarantine_world_command(self.world_file)


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
    if not _world_state_dir_is_checkable(state_dir, issues):
        return

    forge = WorldForge(state_dir=state_dir)
    roots = ((state_dir, "state-dir"),)
    for world_file in sorted(state_dir.glob("*.json")):
        stats["world_files_checked"] += 1
        context = _WorldFileContext(
            state_dir=state_dir,
            world_file=world_file,
            world_id=world_file.stem,
        )
        _check_world_file(context, forge=forge, roots=roots, issues=issues)


def _world_state_dir_is_checkable(state_dir: Path, issues: list[JSONDict]) -> bool:
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
        return False
    if state_dir.is_dir():
        return True
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
    return False


def _check_world_file(
    context: _WorldFileContext,
    *,
    forge: WorldForge,
    roots: tuple[tuple[Path, str], ...],
    issues: list[JSONDict],
) -> None:
    if not _world_file_id_is_valid(context, issues):
        return

    payload = _load_json_object(context.world_file, state_dir=context.state_dir, issues=issues)
    if payload is None:
        return
    _check_payload_world_id(payload, context, issues)
    if not _world_state_loads(context, forge=forge, roots=roots, issues=issues):
        return
    _check_world_bounding_boxes(
        payload,
        world_file=context.world_file,
        state_dir=context.state_dir,
        issues=issues,
    )


def _world_file_id_is_valid(
    context: _WorldFileContext,
    issues: list[JSONDict],
) -> bool:
    try:
        _validate_storage_id(context.world_id, name="world file stem")
    except WorldForgeError:
        issues.append(
            _issue(
                check="unsafe-world-file-id",
                severity="error",
                path=context.display_path,
                message="World JSON filename does not map to a file-safe world id.",
                recovery_command=context.quarantine_command,
                details={"world_file": _safe_file_name(context.world_file.name)},
            )
        )
        return False
    return True


def _check_payload_world_id(
    payload: JSONDict,
    context: _WorldFileContext,
    issues: list[JSONDict],
) -> None:
    payload_id = payload.get("id")
    if not isinstance(payload_id, str) or payload_id == context.world_id:
        return
    issues.append(
        _issue(
            check="world-id-mismatch",
            severity="warning",
            path=context.display_path,
            message="World JSON filename does not match the serialized world id.",
            recovery_command=(
                f"{_diagnostic_command()} && export a valid copy with "
                "`uv run worldforge world export <world-id> --output world.json` before "
                "renaming or quarantining the mismatched file"
            ),
            details={"file_world_id": context.world_id, "payload_world_id": payload_id},
        )
    )


def _world_state_loads(
    context: _WorldFileContext,
    *,
    forge: WorldForge,
    roots: tuple[tuple[Path, str], ...],
    issues: list[JSONDict],
) -> bool:
    try:
        forge.load_world(context.world_id)
    except WorldStateError as exc:
        issues.append(
            _issue(
                check=_world_state_failure_check(str(exc)),
                severity="error",
                path=context.display_path,
                message=(
                    f"World state validation failed: {_sanitize_message(str(exc), roots=roots)}"
                ),
                recovery_command=context.quarantine_command,
                details={"world_id": context.world_id},
            )
        )
        return False
    return True


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
    try:
        return require_json_dict(payload, name="World JSON")
    except WorldForgeError as exc:
        issues.append(
            _issue(
                check="corrupted-world-json",
                severity="error",
                path=_display_path(path, state_dir, "state-dir"),
                message=f"World JSON contains invalid JSON-native values: {exc}",
                recovery_command=_quarantine_world_command(path),
                details={"world_file": _safe_file_name(path.name)},
            )
        )
        return None


def _check_world_bounding_boxes(
    state: JSONDict,
    *,
    world_file: Path,
    state_dir: Path,
    issues: list[JSONDict],
) -> None:
    context = _WorldFileContext(
        state_dir=state_dir,
        world_file=world_file,
        world_id=str(state.get("id", world_file.stem)),
    )
    _visit_bounding_box_payload(state, context=context, location="state", seen=set(), issues=issues)


def _visit_bounding_box_payload(
    payload: JSONDict,
    *,
    context: _WorldFileContext,
    location: str,
    seen: set[int],
    issues: list[JSONDict],
) -> None:
    payload_id = id(payload)
    if payload_id in seen:
        return
    seen.add(payload_id)

    for object_id, raw_object in _scene_object_items(payload):
        scene_object = _scene_object_from_payload(object_id, raw_object)
        if scene_object is None or _position_inside_bbox(scene_object.position, scene_object.bbox):
            continue
        _record_bbox_issue(context, scene_object, location, issues)

    for index, nested_state in _history_state_entries(payload):
        _visit_bounding_box_payload(
            nested_state,
            context=context,
            location=f"{location}.history[{index}].state",
            seen=seen,
            issues=issues,
        )


def _scene_object_items(payload: JSONDict) -> list[tuple[object, object]]:
    scene = payload.get("scene", {})
    if not isinstance(scene, dict):
        return []
    objects = scene.get("objects", {})
    if not isinstance(objects, dict):
        return []
    return sorted(objects.items(), key=lambda item: str(item[0]))


def _scene_object_from_payload(object_id: object, raw_object: object) -> SceneObject | None:
    if not isinstance(raw_object, dict):
        return None
    object_payload = dict(raw_object)
    object_payload.setdefault("id", str(object_id))
    try:
        return SceneObject.from_dict(object_payload)
    except WorldForgeError:
        return None


def _history_state_entries(payload: JSONDict) -> list[tuple[int, JSONDict]]:
    history = payload.get("history", [])
    if not isinstance(history, list):
        return []
    return [
        (index, entry["state"])
        for index, entry in enumerate(history)
        if isinstance(entry, dict) and isinstance(entry.get("state"), dict)
    ]


def _record_bbox_issue(
    context: _WorldFileContext,
    scene_object: SceneObject,
    location: str,
    issues: list[JSONDict],
) -> None:
    issues.append(
        _issue(
            check="bbox-incoherent",
            severity="error",
            path=context.display_path,
            message=(
                "Scene object position is outside its bounding box; position patches must keep "
                "spatial bounds translated with the object pose."
            ),
            recovery_command=context.quarantine_command,
            details={
                "world_id": context.world_id,
                "object_id": scene_object.id,
                "context": location,
            },
        )
    )


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

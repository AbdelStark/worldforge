"""Read-only migration previews for local and exported world state JSON."""

from __future__ import annotations

import json
from copy import deepcopy
from dataclasses import dataclass, field
from pathlib import Path

from worldforge._state import (
    SCHEMA_VERSION,
)
from worldforge._state import (
    validate_storage_id as _validate_storage_id,
)
from worldforge._state import (
    validate_world_state_payload as _validate_world_state_payload,
)
from worldforge.models import (
    BBox,
    JSONDict,
    Position,
    SceneObject,
    WorldForgeError,
    WorldStateError,
    require_json_dict,
)
from worldforge.world_migration_preview_reporting import (
    _first_triage_step,
    _invalid_field,
    _path_token,
    _required_change,
    _safe_file_name,
    _safe_id_value,
    _sanitize_message,
    _unsafe_id,
    render_world_migration_preview_markdown,
)

WORLD_MIGRATION_PREVIEW_SCHEMA_VERSION = 1


@dataclass(slots=True)
class _MigrationPreviewFindings:
    required_changes: list[JSONDict] = field(default_factory=list)
    invalid_fields: list[JSONDict] = field(default_factory=list)
    unsafe_ids: list[JSONDict] = field(default_factory=list)
    bounding_box_corrections: list[JSONDict] = field(default_factory=list)


def preview_world_migration_from_world_id(world_id: str, *, state_dir: Path) -> JSONDict:
    """Preview migration requirements for a persisted world without writing local state."""

    source_label = "<state-dir>/<unsafe-world-id>.json"
    try:
        safe_id = _validate_storage_id(world_id, name="world_id")
    except WorldForgeError as exc:
        return _report(
            source={"kind": "world-id", "label": source_label},
            schema={},
            unsafe_ids=[
                _unsafe_id(
                    kind="world-id",
                    path="source.world_id",
                    message=str(exc),
                    value="<unsafe-world-id>",
                )
            ],
            invalid_fields=[],
        )

    source_label = f"<state-dir>/{safe_id}.json"
    path = state_dir.expanduser() / f"{safe_id}.json"
    try:
        payload = _load_json(path)
    except WorldStateError as exc:
        message = f"World JSON could not be read or decoded: {_sanitize_message(str(exc))}"
        return _report(
            source={"kind": "world-id", "label": source_label},
            schema={},
            invalid_fields=[
                _invalid_field(
                    path="source",
                    message=message,
                )
            ],
        )
    return preview_world_migration(
        payload,
        source={"kind": "world-id", "label": source_label},
        expected_world_id=safe_id,
    )


def preview_world_migration_from_path(path: Path) -> JSONDict:
    """Preview migration requirements for a persisted or exported world JSON file."""

    source_label = f"<input>/{_safe_file_name(path.name)}"
    try:
        payload = _load_json(path.expanduser())
    except WorldStateError as exc:
        message = f"World JSON could not be read or decoded: {_sanitize_message(str(exc))}"
        return _report(
            source={"kind": "json-file", "label": source_label},
            schema={},
            invalid_fields=[
                _invalid_field(
                    path="source",
                    message=message,
                )
            ],
        )
    return preview_world_migration(
        payload,
        source={"kind": "json-file", "label": source_label},
    )


def preview_world_migration(
    payload: object,
    *,
    source: JSONDict | None = None,
    expected_world_id: str | None = None,
) -> JSONDict:
    """Return a safe-to-attach migration preview for a world JSON payload.

    The preview is intentionally read-only. It may infer a candidate migrated shape for validation,
    but it never writes the source payload, local state directory, or exported JSON file.
    """

    findings = _MigrationPreviewFindings()
    if not isinstance(payload, dict):
        return _non_object_source_report(source)

    state, schema, source_kind = _extract_world_state(
        payload,
        findings.invalid_fields,
        findings.required_changes,
    )
    resolved_source = _resolved_preview_source(source, source_kind=source_kind)
    if state is None:
        return _migration_preview_report(source=resolved_source, schema=schema, findings=findings)

    candidate = _analyzed_migration_candidate(state, findings=findings)
    _record_expected_world_id_mismatch(
        state,
        expected_world_id=expected_world_id,
        invalid_fields=findings.invalid_fields,
    )
    _record_candidate_validation(candidate, invalid_fields=findings.invalid_fields)
    return _migration_preview_report(source=resolved_source, schema=schema, findings=findings)


def _non_object_source_report(source: JSONDict | None) -> JSONDict:
    return _report(
        source=source or {"kind": "payload", "label": "<input>"},
        schema={},
        invalid_fields=[
            _invalid_field(path="source", message="World migration source must be a JSON object.")
        ],
    )


def _resolved_preview_source(source: JSONDict | None, *, source_kind: str) -> JSONDict:
    resolved_source = dict(source or {"kind": source_kind, "label": "<input>"})
    if source and source.get("kind") == "json-file":
        resolved_source["payload_kind"] = source_kind
    return resolved_source


def _analyzed_migration_candidate(
    state: JSONDict,
    *,
    findings: _MigrationPreviewFindings,
) -> JSONDict:
    candidate = deepcopy(state)
    _analyze_state(
        state,
        candidate,
        path="state",
        required_changes=findings.required_changes,
        unsafe_ids=findings.unsafe_ids,
        bounding_box_corrections=findings.bounding_box_corrections,
    )
    return candidate


def _record_expected_world_id_mismatch(
    state: JSONDict,
    *,
    expected_world_id: str | None,
    invalid_fields: list[JSONDict],
) -> None:
    if expected_world_id is None:
        return
    payload_world_id = state.get("id")
    if not isinstance(payload_world_id, str) or payload_world_id == expected_world_id:
        return
    invalid_fields.append(
        _invalid_field(
            path="state.id",
            message=(
                "Persisted world filename does not match the serialized world id; "
                "export a valid copy before renaming."
            ),
            details={
                "file_world_id": expected_world_id,
                "payload_world_id": _safe_id_value(payload_world_id),
            },
        )
    )


def _record_candidate_validation(candidate: JSONDict, *, invalid_fields: list[JSONDict]) -> None:
    try:
        _validate_world_state_payload(candidate, context="World state")
    except WorldStateError as exc:
        invalid_fields.append(
            _invalid_field(
                path="state",
                message=f"World state validation failed: {_sanitize_message(str(exc))}",
            )
        )


def _migration_preview_report(
    *,
    source: JSONDict,
    schema: JSONDict,
    findings: _MigrationPreviewFindings,
) -> JSONDict:
    return _report(
        source=source,
        schema=schema,
        required_changes=findings.required_changes,
        invalid_fields=findings.invalid_fields,
        unsafe_ids=findings.unsafe_ids,
        bounding_box_corrections=findings.bounding_box_corrections,
    )


def _extract_world_state(
    payload: JSONDict,
    invalid_fields: list[JSONDict],
    required_changes: list[JSONDict],
) -> tuple[JSONDict | None, JSONDict, str]:
    schema: JSONDict = {
        "preview_schema_version": WORLD_MIGRATION_PREVIEW_SCHEMA_VERSION,
        "current_world_schema_version": SCHEMA_VERSION,
    }
    if "state" in payload:
        schema["export_schema_version"] = payload.get("schema_version")
        _analyze_schema_version(
            payload.get("schema_version"),
            path="schema_version",
            label="Export artifact",
            required_changes=required_changes,
            invalid_fields=invalid_fields,
        )
        raw_state = payload.get("state")
        if not isinstance(raw_state, dict):
            invalid_fields.append(
                _invalid_field(path="state", message="Exported world state must be a JSON object.")
            )
            return None, schema, "exported-json"
        schema["world_schema_version"] = raw_state.get("schema_version")
        return raw_state, schema, "exported-json"

    schema["world_schema_version"] = payload.get("schema_version")
    return payload, schema, "persisted-json"


def _analyze_state(
    state: object,
    candidate: object,
    *,
    path: str,
    required_changes: list[JSONDict],
    unsafe_ids: list[JSONDict],
    bounding_box_corrections: list[JSONDict],
) -> None:
    if not isinstance(state, dict) or not isinstance(candidate, dict):
        return

    _analyze_schema_version(
        state.get("schema_version"),
        path=f"{path}.schema_version",
        label="World state",
        required_changes=required_changes,
        invalid_fields=[],
        candidate=candidate,
    )
    _analyze_world_id(state, path=path, unsafe_ids=unsafe_ids)
    _analyze_scene_objects(
        state,
        candidate,
        path=path,
        required_changes=required_changes,
        unsafe_ids=unsafe_ids,
        bounding_box_corrections=bounding_box_corrections,
    )
    _analyze_history(
        state,
        candidate,
        path=path,
        required_changes=required_changes,
        unsafe_ids=unsafe_ids,
        bounding_box_corrections=bounding_box_corrections,
    )


def _analyze_schema_version(
    value: object,
    *,
    path: str,
    label: str,
    required_changes: list[JSONDict],
    invalid_fields: list[JSONDict],
    candidate: JSONDict | None = None,
) -> None:
    if value == SCHEMA_VERSION:
        return
    if value is None:
        required_changes.append(
            _required_change(
                kind="add-schema-version",
                path=path,
                message=f"{label} is missing schema_version; add schema_version={SCHEMA_VERSION}.",
            )
        )
        if candidate is not None:
            candidate["schema_version"] = SCHEMA_VERSION
        return
    if isinstance(value, int) and 0 < value < SCHEMA_VERSION:
        required_changes.append(
            _required_change(
                kind="upgrade-schema-version",
                path=path,
                message=f"{label} schema_version {value} must be upgraded to {SCHEMA_VERSION}.",
            )
        )
        if candidate is not None:
            candidate["schema_version"] = SCHEMA_VERSION
        return
    invalid_fields.append(
        _invalid_field(
            path=path,
            message=(
                f"{label} schema_version must be {SCHEMA_VERSION}; "
                "newer or malformed schema versions need an explicit migration."
            ),
        )
    )


def _analyze_world_id(state: JSONDict, *, path: str, unsafe_ids: list[JSONDict]) -> None:
    world_id = state.get("id")
    try:
        _validate_storage_id(world_id, name="world id")
    except WorldForgeError as exc:
        unsafe_ids.append(
            _unsafe_id(
                kind="world-id",
                path=f"{path}.id",
                message=str(exc),
                value=_safe_id_value(world_id),
            )
        )


def _analyze_scene_objects(
    state: JSONDict,
    candidate: JSONDict,
    *,
    path: str,
    required_changes: list[JSONDict],
    unsafe_ids: list[JSONDict],
    bounding_box_corrections: list[JSONDict],
) -> None:
    object_maps = _scene_object_maps(state, candidate)
    if object_maps is None:
        return
    objects, candidate_objects = object_maps

    for raw_object_id, raw_object in sorted(objects.items(), key=lambda item: str(item[0])):
        _analyze_scene_object(
            raw_object_id,
            raw_object,
            candidate_objects,
            path=path,
            required_changes=required_changes,
            unsafe_ids=unsafe_ids,
            bounding_box_corrections=bounding_box_corrections,
        )


def _scene_object_maps(
    state: JSONDict,
    candidate: JSONDict,
) -> tuple[dict[object, object], dict[object, object]] | None:
    scene = state.get("scene", {})
    candidate_scene = candidate.get("scene", {})
    if not isinstance(scene, dict) or not isinstance(candidate_scene, dict):
        return None
    objects = scene.get("objects", {})
    candidate_objects = candidate_scene.get("objects", {})
    if not isinstance(objects, dict) or not isinstance(candidate_objects, dict):
        return None
    return objects, candidate_objects


def _analyze_scene_object(
    raw_object_id: object,
    raw_object: object,
    candidate_objects: dict[object, object],
    *,
    path: str,
    required_changes: list[JSONDict],
    unsafe_ids: list[JSONDict],
    bounding_box_corrections: list[JSONDict],
) -> None:
    object_path = f"{path}.scene.objects.{_path_token(raw_object_id)}"
    _analyze_scene_object_ids(raw_object_id, raw_object, path=object_path, unsafe_ids=unsafe_ids)
    if not isinstance(raw_object, dict):
        return

    scene_object = _scene_object_from_payload(raw_object_id, raw_object)
    if scene_object is None:
        return

    _record_legacy_position_migration(
        raw_object_id,
        raw_object,
        scene_object,
        candidate_objects,
        path=object_path,
        required_changes=required_changes,
    )
    _record_bbox_correction(
        raw_object_id,
        scene_object,
        candidate_objects,
        path=object_path,
        bounding_box_corrections=bounding_box_corrections,
    )


def _analyze_scene_object_ids(
    raw_object_id: object,
    raw_object: object,
    *,
    path: str,
    unsafe_ids: list[JSONDict],
) -> None:
    _analyze_object_id(raw_object_id, path=path, unsafe_ids=unsafe_ids)
    if not isinstance(raw_object, dict):
        return
    embedded_id = raw_object.get("id")
    if embedded_id is not None:
        _analyze_object_id(embedded_id, path=f"{path}.id", unsafe_ids=unsafe_ids)


def _scene_object_from_payload(
    raw_object_id: object,
    raw_object: dict[object, object],
) -> SceneObject | None:
    object_payload = dict(raw_object)
    object_payload.setdefault("id", str(raw_object_id))
    try:
        return SceneObject.from_dict(object_payload)
    except WorldForgeError:
        return None


def _record_legacy_position_migration(
    raw_object_id: object,
    raw_object: dict[object, object],
    scene_object: SceneObject,
    candidate_objects: dict[object, object],
    *,
    path: str,
    required_changes: list[JSONDict],
) -> None:
    if "position" not in raw_object or "pose" in raw_object:
        return
    required_changes.append(
        _required_change(
            kind="promote-position-to-pose",
            path=f"{path}.position",
            message="Legacy scene object position should be promoted to pose.position.",
        )
    )
    candidate_objects[raw_object_id] = scene_object.to_dict()


def _record_bbox_correction(
    raw_object_id: object,
    scene_object: SceneObject,
    candidate_objects: dict[object, object],
    *,
    path: str,
    bounding_box_corrections: list[JSONDict],
) -> None:
    if _position_inside_bbox(scene_object.position, scene_object.bbox):
        return
    proposed_bbox = _bbox_centered_on_position(scene_object.position, scene_object.bbox)
    bounding_box_corrections.append(
        {
            "path": f"{path}.bbox",
            "object_id": _safe_id_value(scene_object.id),
            "message": (
                "Scene object position is outside its bounding box; previewed migration "
                "would translate the bounding box center onto the object pose."
            ),
            "position": scene_object.position.to_dict(),
            "current_bbox": scene_object.bbox.to_dict(),
            "proposed_bbox": proposed_bbox.to_dict(),
            "safe_to_attach": True,
        }
    )
    target = candidate_objects.get(raw_object_id)
    if isinstance(target, dict):
        target["bbox"] = proposed_bbox.to_dict()


def _analyze_history(
    state: JSONDict,
    candidate: JSONDict,
    *,
    path: str,
    required_changes: list[JSONDict],
    unsafe_ids: list[JSONDict],
    bounding_box_corrections: list[JSONDict],
) -> None:
    history = state.get("history", [])
    candidate_history = candidate.get("history", [])
    if not isinstance(history, list) or not isinstance(candidate_history, list):
        return
    for index, entry in enumerate(history):
        if not isinstance(entry, dict):
            continue
        candidate_entry = candidate_history[index] if index < len(candidate_history) else None
        if not isinstance(candidate_entry, dict):
            continue
        entry_state = entry.get("state")
        candidate_entry_state = candidate_entry.get("state")
        if isinstance(entry_state, dict) and isinstance(candidate_entry_state, dict):
            _analyze_state(
                entry_state,
                candidate_entry_state,
                path=f"{path}.history[{index}].state",
                required_changes=required_changes,
                unsafe_ids=unsafe_ids,
                bounding_box_corrections=bounding_box_corrections,
            )


def _report(
    *,
    source: JSONDict,
    schema: JSONDict,
    required_changes: list[JSONDict] | None = None,
    invalid_fields: list[JSONDict] | None = None,
    unsafe_ids: list[JSONDict] | None = None,
    bounding_box_corrections: list[JSONDict] | None = None,
) -> JSONDict:
    required_changes = required_changes or []
    invalid_fields = invalid_fields or []
    unsafe_ids = unsafe_ids or []
    bounding_box_corrections = bounding_box_corrections or []
    blocked = bool(invalid_fields or unsafe_ids)
    needs_migration = bool(required_changes or bounding_box_corrections)
    status = "blocked" if blocked else "migration-needed" if needs_migration else "passed"
    return {
        "schema_version": WORLD_MIGRATION_PREVIEW_SCHEMA_VERSION,
        "status": status,
        "safe_to_attach": True,
        "read_only": True,
        "rewrite_available": False,
        "rewrite_policy": (
            "This command is preview-only. Rewrite remains an explicit host-owned or future "
            "WorldForge step."
        ),
        "can_apply_safely": not blocked,
        "source": source,
        "schema": {
            "preview_schema_version": WORLD_MIGRATION_PREVIEW_SCHEMA_VERSION,
            "current_world_schema_version": SCHEMA_VERSION,
            **schema,
        },
        "counts": {
            "required_change_count": len(required_changes),
            "invalid_field_count": len(invalid_fields),
            "unsafe_id_count": len(unsafe_ids),
            "bounding_box_correction_count": len(bounding_box_corrections),
            "blocking_issue_count": len(invalid_fields) + len(unsafe_ids),
        },
        "required_changes": required_changes,
        "invalid_fields": invalid_fields,
        "unsafe_ids": unsafe_ids,
        "bounding_box_corrections": bounding_box_corrections,
        "first_triage_step": _first_triage_step(blocked, needs_migration),
    }


def _load_json(path: Path) -> JSONDict:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise WorldStateError(str(exc)) from exc
    except json.JSONDecodeError as exc:
        raise WorldStateError(str(exc)) from exc
    try:
        return require_json_dict(payload, name="World JSON")
    except WorldForgeError as exc:
        raise WorldStateError(str(exc)) from exc


def _analyze_object_id(value: object, *, path: str, unsafe_ids: list[JSONDict]) -> None:
    if not isinstance(value, str) or not value.strip():
        unsafe_ids.append(
            _unsafe_id(
                kind="object-id",
                path=path,
                message="Scene object id must be a non-empty string.",
                value="<unsafe-object-id>",
            )
        )
        return
    if value in {".", ".."} or "/" in value or "\\" in value:
        unsafe_ids.append(
            _unsafe_id(
                kind="object-id",
                path=path,
                message="Scene object id is traversal-shaped and must be renamed explicitly.",
                value="<unsafe-object-id>",
            )
        )


def _bbox_centered_on_position(position: Position, bbox: BBox) -> BBox:
    half_x = (bbox.max.x - bbox.min.x) / 2
    half_y = (bbox.max.y - bbox.min.y) / 2
    half_z = (bbox.max.z - bbox.min.z) / 2
    return BBox(
        min=Position(position.x - half_x, position.y - half_y, position.z - half_z),
        max=Position(position.x + half_x, position.y + half_y, position.z + half_z),
    )


def _position_inside_bbox(position: Position, bbox: BBox) -> bool:
    return (
        bbox.min.x <= position.x <= bbox.max.x
        and bbox.min.y <= position.y <= bbox.max.y
        and bbox.min.z <= position.z <= bbox.max.z
    )


__all__ = [
    "WORLD_MIGRATION_PREVIEW_SCHEMA_VERSION",
    "preview_world_migration",
    "preview_world_migration_from_path",
    "preview_world_migration_from_world_id",
    "render_world_migration_preview_markdown",
]

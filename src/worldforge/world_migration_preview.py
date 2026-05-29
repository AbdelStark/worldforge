"""Read-only migration previews for local and exported world state JSON."""

from __future__ import annotations

import json
import re
from copy import deepcopy
from pathlib import Path

from worldforge.framework import SCHEMA_VERSION, _validate_storage_id, _validate_world_state_payload
from worldforge.models import (
    BBox,
    JSONDict,
    Position,
    SceneObject,
    WorldForgeError,
    WorldStateError,
)

WORLD_MIGRATION_PREVIEW_SCHEMA_VERSION = 1

_SAFE_NAME_PATTERN = re.compile(r"^[A-Za-z0-9_.-]+$")
_SECRET_LIKE_PATTERN = re.compile(
    r"(?:api[_-]?key|authorization|bearer|secret|signature|signed|token|x-amz)",
    re.IGNORECASE,
)
_HOST_LOCAL_PATH_PATTERN = re.compile(
    r"(?P<path>(?:/Users|/private|/var/folders|/tmp)/[^\s,;:)'\"]+)"
)


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

    required_changes: list[JSONDict] = []
    invalid_fields: list[JSONDict] = []
    unsafe_ids: list[JSONDict] = []
    bounding_box_corrections: list[JSONDict] = []

    if not isinstance(payload, dict):
        return _report(
            source=source or {"kind": "payload", "label": "<input>"},
            schema={},
            invalid_fields=[
                _invalid_field(
                    path="source", message="World migration source must be a JSON object."
                )
            ],
        )

    state, schema, source_kind = _extract_world_state(payload, invalid_fields, required_changes)
    resolved_source = dict(source or {"kind": source_kind, "label": "<input>"})
    if source and source.get("kind") == "json-file":
        resolved_source["payload_kind"] = source_kind
    if state is None:
        return _report(
            source=resolved_source,
            schema=schema,
            required_changes=required_changes,
            invalid_fields=invalid_fields,
            unsafe_ids=unsafe_ids,
            bounding_box_corrections=bounding_box_corrections,
        )

    candidate = deepcopy(state)
    _analyze_state(
        state,
        candidate,
        path="state",
        required_changes=required_changes,
        unsafe_ids=unsafe_ids,
        bounding_box_corrections=bounding_box_corrections,
    )

    if expected_world_id is not None:
        payload_world_id = state.get("id")
        if isinstance(payload_world_id, str) and payload_world_id != expected_world_id:
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

    if isinstance(candidate, dict):
        try:
            _validate_world_state_payload(candidate, context="World state")
        except WorldStateError as exc:
            invalid_fields.append(
                _invalid_field(
                    path="state",
                    message=f"World state validation failed: {_sanitize_message(str(exc))}",
                )
            )

    return _report(
        source=resolved_source,
        schema=schema,
        required_changes=required_changes,
        invalid_fields=invalid_fields,
        unsafe_ids=unsafe_ids,
        bounding_box_corrections=bounding_box_corrections,
    )


def render_world_migration_preview_markdown(report: JSONDict) -> str:
    """Render a migration preview report for operator review."""

    counts = report.get("counts", {})
    schema = report.get("schema", {})
    source = report.get("source", {})
    lines = [
        "# WorldForge World Migration Preview",
        "",
        f"status: `{report.get('status', 'unknown')}`",
        f"safe_to_attach: `{str(report.get('safe_to_attach', False)).lower()}`",
        f"read_only: `{str(report.get('read_only', False)).lower()}`",
        f"can_apply_safely: `{str(report.get('can_apply_safely', False)).lower()}`",
        f"rewrite_available: `{str(report.get('rewrite_available', False)).lower()}`",
        f"source: `{source.get('label', '<input>')}`",
        f"source_kind: `{source.get('kind', 'unknown')}`",
        f"world_schema_version: `{schema.get('world_schema_version', 'missing')}`",
        (
            "current_world_schema_version: "
            f"`{schema.get('current_world_schema_version', SCHEMA_VERSION)}`"
        ),
        "",
        f"required_changes: `{counts.get('required_change_count', 0)}`",
        f"invalid_fields: `{counts.get('invalid_field_count', 0)}`",
        f"unsafe_ids: `{counts.get('unsafe_id_count', 0)}`",
        f"bounding_box_corrections: `{counts.get('bounding_box_correction_count', 0)}`",
        "",
        "First triage:",
        "",
        f"- {report.get('first_triage_step', _first_triage_step(False, False))}",
    ]

    _append_table(
        lines,
        title="Required Changes",
        rows=report.get("required_changes", []),
        columns=("kind", "path", "message"),
    )
    _append_table(
        lines,
        title="Invalid Fields",
        rows=report.get("invalid_fields", []),
        columns=("path", "message"),
    )
    _append_table(
        lines,
        title="Unsafe IDs",
        rows=report.get("unsafe_ids", []),
        columns=("kind", "path", "message"),
    )
    _append_table(
        lines,
        title="Bounding Box Corrections",
        rows=report.get("bounding_box_corrections", []),
        columns=("path", "object_id", "message"),
    )
    return "\n".join(lines) + "\n"


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
    objects = state.get("scene", {}).get("objects", {})
    candidate_objects = candidate.get("scene", {}).get("objects", {})
    if not isinstance(objects, dict) or not isinstance(candidate_objects, dict):
        return

    for raw_object_id, raw_object in sorted(objects.items(), key=lambda item: str(item[0])):
        object_path = f"{path}.scene.objects.{_path_token(raw_object_id)}"
        _analyze_object_id(raw_object_id, path=object_path, unsafe_ids=unsafe_ids)
        if not isinstance(raw_object, dict):
            continue
        embedded_id = raw_object.get("id")
        if embedded_id is not None:
            _analyze_object_id(
                embedded_id,
                path=f"{object_path}.id",
                unsafe_ids=unsafe_ids,
            )

        object_payload = dict(raw_object)
        object_payload.setdefault("id", str(raw_object_id))
        try:
            scene_object = SceneObject.from_dict(object_payload)
        except WorldForgeError:
            continue

        if "position" in raw_object and "pose" not in raw_object:
            required_changes.append(
                _required_change(
                    kind="promote-position-to-pose",
                    path=f"{object_path}.position",
                    message="Legacy scene object position should be promoted to pose.position.",
                )
            )
            candidate_objects[raw_object_id] = scene_object.to_dict()

        if not _position_inside_bbox(scene_object.position, scene_object.bbox):
            proposed_bbox = _bbox_centered_on_position(scene_object.position, scene_object.bbox)
            bounding_box_corrections.append(
                {
                    "path": f"{object_path}.bbox",
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
    if not isinstance(payload, dict):
        raise WorldStateError("World JSON must decode to an object.")
    return payload


def _required_change(*, kind: str, path: str, message: str) -> JSONDict:
    return {"kind": kind, "path": path, "message": message, "safe_to_attach": True}


def _invalid_field(*, path: str, message: str, details: JSONDict | None = None) -> JSONDict:
    return {
        "path": path,
        "message": _sanitize_message(message),
        "safe_to_attach": True,
        "details": details or {},
    }


def _unsafe_id(*, kind: str, path: str, message: str, value: object) -> JSONDict:
    return {
        "kind": kind,
        "path": path,
        "message": _sanitize_message(message),
        "value": value,
        "safe_to_attach": True,
    }


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


def _sanitize_message(message: str) -> str:
    sanitized = _HOST_LOCAL_PATH_PATTERN.sub("<host-local-path>", message)
    if _SECRET_LIKE_PATTERN.search(sanitized):
        return _SECRET_LIKE_PATTERN.sub("<redacted>", sanitized)
    return sanitized


def _safe_file_name(value: str) -> str:
    return value if _is_public_name(value) else "<unsafe-name>"


def _safe_id_value(value: object) -> str:
    if isinstance(value, str) and value.strip() and _is_public_name(value):
        return value
    return "<unsafe-id>"


def _path_token(value: object) -> str:
    if isinstance(value, str) and value.strip() and _is_public_name(value):
        return value
    return "<unsafe-id>"


def _is_public_name(value: str) -> bool:
    return (
        _SAFE_NAME_PATTERN.fullmatch(value) is not None
        and _SECRET_LIKE_PATTERN.search(value) is None
    )


def _first_triage_step(blocked: bool, needs_migration: bool) -> str:
    if blocked:
        return (
            "run `uv run worldforge world preflight --state-dir .worldforge/worlds "
            "--workspace-dir .worldforge --format json` before moving or rewriting state."
        )
    if needs_migration:
        return (
            "export the source JSON first, review this preview, then apply migration through an "
            "explicit host-owned rewrite step."
        )
    return "no migration is required for this world state."


def _append_table(
    lines: list[str],
    *,
    title: str,
    rows: object,
    columns: tuple[str, ...],
) -> None:
    lines.extend(["", f"## {title}", ""])
    if not isinstance(rows, list) or not rows:
        lines.append("- None.")
        return
    lines.append("| " + " | ".join(column.replace("_", " ").title() for column in columns) + " |")
    lines.append("| " + " | ".join("---" for _ in columns) + " |")
    for row in rows:
        if not isinstance(row, dict):
            continue
        lines.append(
            "| " + " | ".join(_markdown_cell(row.get(column)) for column in columns) + " |"
        )


def _markdown_cell(value: object) -> str:
    text = str(value if value is not None else "")
    return text.replace("|", "\\|").replace("\n", " ")


__all__ = [
    "WORLD_MIGRATION_PREVIEW_SCHEMA_VERSION",
    "preview_world_migration",
    "preview_world_migration_from_path",
    "preview_world_migration_from_world_id",
    "render_world_migration_preview_markdown",
]

"""Private local-world state validation and restoration helpers."""

from __future__ import annotations

import re
from pathlib import Path

from worldforge.models import (
    HistoryEntry,
    JSONDict,
    SceneObject,
    WorldForgeError,
    WorldStateError,
    require_json_dict,
    require_non_negative_int,
    require_positive_int,
)

SCHEMA_VERSION = 1
_STORAGE_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")
_REQUIRED_WORLD_FIELDS = ("schema_version", "id", "name", "provider")


def require_non_empty_text(value: object, *, name: str, message: str | None = None) -> str:
    if not isinstance(value, str) or not value.strip():
        raise WorldForgeError(message or f"{name} must be a non-empty string.")
    return value.strip()


def validate_storage_id(value: object, *, name: str) -> str:
    """Return a file-safe local storage identifier or raise ``WorldForgeError``."""

    identifier = require_non_empty_text(value, name=name)
    if (
        identifier in {".", ".."}
        or "/" in identifier
        or "\\" in identifier
        or _STORAGE_ID_PATTERN.fullmatch(identifier) is None
    ):
        raise WorldForgeError(
            f"{name} must be a file-safe identifier using only letters, numbers, '.', '_', or '-'."
        )
    return identifier


def world_file(state_dir: Path, world_id: str) -> Path:
    return state_dir / f"{validate_storage_id(world_id, name='world_id')}.json"


def missing_required_world_fields(state: JSONDict) -> list[str]:
    return sorted(key for key in _REQUIRED_WORLD_FIELDS if key not in state)


def require_world_fields_present(state: JSONDict, *, context: str) -> None:
    missing_keys = missing_required_world_fields(state)
    if missing_keys:
        joined = ", ".join(sorted(missing_keys))
        raise WorldStateError(f"{context} is missing required keys: {joined}.")


def validate_world_schema_version(schema_version_value: object, *, context: str) -> None:
    schema_version = require_positive_int(
        schema_version_value,
        name=f"{context} field 'schema_version'",
    )
    if schema_version != SCHEMA_VERSION:
        raise WorldForgeError(f"{context} field 'schema_version' must be {SCHEMA_VERSION}.")


def validate_world_identity_fields(state: JSONDict, *, context: str) -> None:
    validate_storage_id(state["id"], name=f"{context} field 'id'")
    require_non_empty_text(state["name"], name=f"{context} field 'name'")
    require_non_empty_text(state["provider"], name=f"{context} field 'provider'")


def validate_required_world_fields(state: JSONDict, *, context: str) -> None:
    require_world_fields_present(state, context=context)
    try:
        validate_world_schema_version(state["schema_version"], context=context)
        validate_world_identity_fields(state, context=context)
    except WorldForgeError as exc:
        raise WorldStateError(str(exc)) from exc


def world_scene_objects_payload(state: JSONDict, *, context: str) -> dict[object, object]:
    scene = state.get("scene", {})
    if not isinstance(scene, dict):
        raise WorldStateError(f"{context} field 'scene' must be a JSON object.")
    objects = scene.get("objects", {})
    if not isinstance(objects, dict):
        raise WorldStateError(f"{context} field 'scene.objects' must be a JSON object.")
    return objects


def validate_world_scene_objects(objects: dict[object, object], *, context: str) -> None:
    for object_id, object_state in objects.items():
        scene_object_id = validate_world_scene_object_id(object_id, context=context)
        scene_object_state = require_world_scene_object_state(
            object_state,
            object_id=scene_object_id,
            context=context,
        )
        validate_world_scene_object(scene_object_id, scene_object_state, context=context)


def validate_world_scene_object_id(object_id: object, *, context: str) -> str:
    if not isinstance(object_id, str) or not object_id.strip():
        raise WorldStateError(f"{context} scene object ids must be non-empty strings.")
    return object_id


def require_world_scene_object_state(
    object_state: object,
    *,
    object_id: str,
    context: str,
) -> dict[object, object]:
    if not isinstance(object_state, dict):
        raise WorldStateError(f"{context} scene object '{object_id}' must be a JSON object.")
    return object_state


def validate_world_scene_object(
    object_id: str,
    object_state: dict[object, object],
    *,
    context: str,
) -> None:
    validate_scene_object_embedded_id(object_id, object_state, context=context)
    parse_world_scene_object(
        object_id,
        scene_object_payload_with_id(object_id, object_state),
        context=context,
    )


def validate_scene_object_embedded_id(
    object_id: str,
    object_state: dict[object, object],
    *,
    context: str,
) -> None:
    embedded_id = object_state.get("id")
    if embedded_id is not None and str(embedded_id) != str(object_id):
        raise WorldStateError(
            f"{context} scene object key '{object_id}' does not match embedded id '{embedded_id}'."
        )


def scene_object_payload_with_id(
    object_id: str,
    object_state: dict[object, object],
) -> dict[object, object]:
    payload = dict(object_state)
    payload.setdefault("id", object_id)
    return payload


def parse_world_scene_object(
    object_id: str,
    object_payload: dict[object, object],
    *,
    context: str,
) -> SceneObject:
    try:
        return SceneObject.from_dict(object_payload)
    except (KeyError, TypeError, ValueError, WorldForgeError) as exc:
        raise WorldStateError(f"{context} scene object '{object_id}' is invalid: {exc}") from exc


def validate_world_metadata(state: JSONDict, *, context: str) -> None:
    metadata = state.get("metadata", {})
    try:
        require_json_dict(metadata, name=f"{context} field 'metadata'")
    except WorldForgeError as exc:
        raise WorldStateError(str(exc)) from exc


def world_state_step(state: JSONDict, *, context: str) -> int:
    try:
        return require_non_negative_int(state.get("step", 0), name=f"{context} field 'step'")
    except WorldForgeError as exc:
        raise WorldStateError(str(exc)) from exc


def validate_world_history(state: JSONDict, *, context: str, current_step: int) -> None:
    history = state.get("history", [])
    if not isinstance(history, list):
        raise WorldStateError(f"{context} field 'history' must be a JSON array.")
    for index, entry in enumerate(history):
        validate_world_history_entry(
            entry,
            index=index,
            context=context,
            current_step=current_step,
        )


def world_history_entry_context(context: str, index: int) -> str:
    return f"{context}.history[{index}]"


def world_history_entry(entry: object, *, context: str) -> HistoryEntry:
    if not isinstance(entry, dict):
        raise WorldStateError(f"{context} must be a JSON object.")
    try:
        return HistoryEntry.from_dict(entry)
    except (KeyError, TypeError, ValueError, WorldForgeError) as exc:
        raise WorldStateError(f"{context} is invalid: {exc}") from exc


def validate_world_history_step(
    history_entry: HistoryEntry,
    *,
    context: str,
    current_step: int,
) -> None:
    if history_entry.step > current_step:
        raise WorldStateError(f"{context} step must not be greater than current step.")


def validate_world_history_state(history_entry: HistoryEntry, *, context: str) -> None:
    try:
        validate_world_state_payload(
            history_entry.state,
            context=f"{context}.state",
        )
    except WorldStateError as exc:
        raise WorldStateError(f"{context} has invalid state: {exc}") from exc


def validate_world_history_entry(
    entry: object,
    *,
    index: int,
    context: str,
    current_step: int,
) -> None:
    entry_context = world_history_entry_context(context, index)
    history_entry = world_history_entry(entry, context=entry_context)
    validate_world_history_step(
        history_entry,
        context=entry_context,
        current_step=current_step,
    )
    validate_world_history_state(history_entry, context=entry_context)


def validate_world_state_payload(state: JSONDict, *, context: str) -> None:
    """Validate a serialized world before it is restored, saved, or applied."""

    if not isinstance(state, dict):
        raise WorldStateError(f"{context} must be a JSON object.")

    validate_required_world_fields(state, context=context)
    objects = world_scene_objects_payload(state, context=context)
    validate_world_scene_objects(objects, context=context)
    validate_world_metadata(state, context=context)
    step = world_state_step(state, context=context)
    validate_world_history(state, context=context, current_step=step)


def restore_scene_objects(state: JSONDict, *, context: str) -> dict[str, SceneObject]:
    objects = state.get("scene", {}).get("objects", {})
    restored: dict[str, SceneObject] = {}
    for object_id, object_state in objects.items():
        object_payload = dict(object_state)
        object_payload.setdefault("id", str(object_id))
        try:
            restored[str(object_id)] = SceneObject.from_dict(object_payload)
        except (KeyError, TypeError, ValueError, WorldForgeError) as exc:
            raise WorldStateError(
                f"{context} scene object '{object_id}' could not be restored: {exc}"
            ) from exc
    return restored


def restore_history_entries(
    state: JSONDict,
    *,
    context: str,
    fallback: HistoryEntry,
) -> list[HistoryEntry]:
    entries = state.get("history", [])
    restored = [
        restore_history_entry(entry, index=index, context=context)
        for index, entry in enumerate(entries)
    ]
    return history_entries_or_fallback(restored, fallback=fallback)


def restore_history_entry(entry: object, *, index: int, context: str) -> HistoryEntry:
    try:
        return HistoryEntry.from_dict(entry)
    except (KeyError, TypeError, ValueError, WorldForgeError) as exc:
        raise WorldStateError(f"{context} history[{index}] could not be restored: {exc}") from exc


def history_entries_or_fallback(
    entries: list[HistoryEntry],
    *,
    fallback: HistoryEntry,
) -> list[HistoryEntry]:
    return entries or [fallback]

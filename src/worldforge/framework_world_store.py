"""Local JSON world-store helpers for :class:`worldforge.framework.WorldForge`."""

from __future__ import annotations

import json
from contextlib import suppress
from typing import TYPE_CHECKING

from worldforge._state import SCHEMA_VERSION
from worldforge._state import validate_storage_id as _validate_storage_id
from worldforge._state import world_file as _world_file
from worldforge._world import World
from worldforge.models import (
    JSONDict,
    WorldForgeError,
    WorldStateError,
    dump_json,
    generate_id,
    require_json_dict,
)

if TYPE_CHECKING:
    from worldforge.framework import WorldForge


def save_world(owner: WorldForge, world: World) -> str:
    """Validate and atomically write a world to the local JSON state directory."""

    path = _world_file(owner.state_dir, world.id)
    tmp_path = path.with_name(f".{path.name}.{generate_id('tmp')}.tmp")
    try:
        state = world.to_dict()
        World.from_state(owner, state)
        tmp_path.write_text(dump_json(state), encoding="utf-8")
        tmp_path.replace(path)
    except OSError as exc:
        raise WorldStateError(f"Failed to save world '{world.id}' to {path}: {exc}") from exc
    except WorldStateError as exc:
        raise WorldStateError(f"World '{world.id}' is not valid for persistence: {exc}") from exc
    finally:
        with suppress(OSError):
            tmp_path.unlink(missing_ok=True)
    return world.id


def load_world(owner: WorldForge, world_id: str) -> World:
    """Load a world from local JSON after validating its storage identifier and payload."""

    path = _world_file(owner.state_dir, world_id)
    try:
        payload = _decode_json_object(
            json.loads(path.read_text(encoding="utf-8")),
            name="World file",
        )
        return World.from_state(owner, payload)
    except OSError as exc:
        raise WorldStateError(f"Failed to load world '{world_id}' from {path}: {exc}") from exc
    except ValueError as exc:
        raise WorldStateError(f"World file '{path}' is invalid: {exc}") from exc


def delete_world(owner: WorldForge, world_id: str) -> str:
    """Delete a persisted world file after validating its storage identifier."""

    safe_id = _validate_storage_id(world_id, name="world_id")
    path = owner.state_dir / f"{safe_id}.json"
    try:
        path.unlink(missing_ok=False)
    except FileNotFoundError as exc:
        raise WorldStateError(f"World '{safe_id}' is not present at {path}.") from exc
    except OSError as exc:
        raise WorldStateError(f"Failed to delete world '{safe_id}' at {path}: {exc}") from exc
    return safe_id


def list_worlds(owner: WorldForge) -> list[str]:
    return sorted(path.stem for path in owner.state_dir.glob("*.json"))


def export_world(owner: WorldForge, world_id: str, *, format: str = "json") -> str:
    if format != "json":
        raise WorldForgeError("Only json export is supported.")
    world = load_world(owner, world_id)
    return dump_json({"schema_version": SCHEMA_VERSION, "state": world.to_dict()})


def import_world(
    owner: WorldForge,
    payload: str,
    *,
    format: str = "json",
    new_id: bool = False,
    name: str | None = None,
) -> World:
    """Restore a world from exported JSON without saving it automatically."""

    if format != "json":
        raise WorldForgeError("Only json import is supported.")
    state = _import_state_payload(_decode_import_payload(payload))
    return World.from_state(
        owner,
        _apply_import_overrides(state, new_id=new_id, name=name),
    )


def fork_world(
    owner: WorldForge,
    world_id: str,
    *,
    history_index: int = 0,
    name: str | None = None,
) -> World:
    fork = load_world(owner, world_id).history_state(history_index)
    if name:
        fork.name = name
        fork.metadata["name"] = name
    fork.id = generate_id("world")
    fork._history = []
    fork._record_history(summary="world forked", action=None)
    return fork


def _decode_import_payload(payload: str) -> JSONDict:
    try:
        decoded = json.loads(payload)
    except json.JSONDecodeError as exc:
        raise WorldStateError(f"Import payload is not valid JSON: {exc}") from exc
    return _decode_json_object(decoded, name="Import payload")


def _decode_json_object(decoded: object, *, name: str) -> JSONDict:
    try:
        return require_json_dict(decoded, name=name)
    except WorldForgeError as exc:
        raise WorldStateError(str(exc)) from exc


def _import_state_payload(data: JSONDict) -> JSONDict:
    state = data.get("state", data)
    if not isinstance(state, dict):
        raise WorldStateError("Import payload state must be a JSON object.")
    return dict(state)


def _apply_import_overrides(
    state: JSONDict,
    *,
    new_id: bool,
    name: str | None,
) -> JSONDict:
    imported_state = dict(state)
    if new_id:
        imported_state["id"] = generate_id("world")
    if name:
        _apply_import_name(imported_state, name)
    return imported_state


def _apply_import_name(state: JSONDict, name: str) -> None:
    state["name"] = name
    metadata = state.get("metadata", {})
    if not isinstance(metadata, dict):
        raise WorldStateError("Import payload metadata must be a JSON object.")
    updated_metadata = dict(metadata)
    updated_metadata["name"] = name
    state["metadata"] = updated_metadata

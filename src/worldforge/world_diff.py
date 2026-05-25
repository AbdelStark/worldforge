"""JSON-native diff and patch artifacts for WorldForge worlds.

Two persisted or exported world snapshots can be compared into a structured
:class:`WorldDiff`, and the diff can be promoted to a :class:`WorldPatch` that
applies cleanly to a base snapshot. The artifact is schema-versioned and JSON
native; every patch operation validates the resulting world fragment through
the existing public primitives (``SceneObject``, ``Position``, ``BBox``)
before mutating state, so a malformed patch fails loudly instead of silently
corrupting the world JSON.

Out of scope: no concurrent merge logic and no automatic conflict resolution.
A patch is a single sequenced application of changes to one base snapshot.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from worldforge.models import (
    BBox,
    JSONDict,
    Position,
    SceneObject,
    WorldForgeError,
    WorldStateError,
)

if TYPE_CHECKING:
    from worldforge.framework import World

WORLD_DIFF_SCHEMA_VERSION = 1

OBJECT_CHANGE_KINDS: tuple[str, ...] = ("added", "removed", "updated")
WORLD_FIELD_NAMES: tuple[str, ...] = ("name", "provider", "description", "step", "metadata")


@dataclass(frozen=True, slots=True)
class WorldFieldChange:
    """A change to a top-level world field (``step``, ``name``, ``metadata``, ...)."""

    field: str
    before: object | None
    after: object | None

    def __post_init__(self) -> None:
        if self.field not in WORLD_FIELD_NAMES:
            options = ", ".join(WORLD_FIELD_NAMES)
            raise WorldForgeError(f"WorldFieldChange field must be one of: {options}.")

    def to_dict(self) -> JSONDict:
        return {"field": self.field, "before": self.before, "after": self.after}


@dataclass(frozen=True, slots=True)
class ObjectChange:
    """One scene-object change: ``added``, ``removed``, or ``updated``."""

    kind: str
    object_id: str
    before: JSONDict | None = None
    after: JSONDict | None = None
    field_changes: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.kind not in OBJECT_CHANGE_KINDS:
            options = ", ".join(OBJECT_CHANGE_KINDS)
            raise WorldForgeError(f"ObjectChange kind must be one of: {options}.")
        _validate_object_id(self.object_id)
        if self.kind == "added" and self.after is None:
            raise WorldForgeError("ObjectChange kind='added' requires an 'after' payload.")
        if self.kind == "removed" and self.before is None:
            raise WorldForgeError("ObjectChange kind='removed' requires a 'before' payload.")
        if self.kind == "updated" and (self.before is None or self.after is None):
            raise WorldForgeError(
                "ObjectChange kind='updated' requires both 'before' and 'after' payloads."
            )

    def to_dict(self) -> JSONDict:
        return {
            "kind": self.kind,
            "object_id": self.object_id,
            "before": self.before,
            "after": self.after,
            "field_changes": list(self.field_changes),
        }


@dataclass(frozen=True, slots=True)
class WorldDiff:
    """Schema-versioned diff between two world snapshots."""

    schema_version: int
    source_label: str
    target_label: str
    field_changes: tuple[WorldFieldChange, ...]
    object_changes: tuple[ObjectChange, ...]
    history_summary: dict[str, int]

    def to_dict(self) -> JSONDict:
        return {
            "schema_version": self.schema_version,
            "source_label": self.source_label,
            "target_label": self.target_label,
            "field_changes": [change.to_dict() for change in self.field_changes],
            "object_changes": [change.to_dict() for change in self.object_changes],
            "history_summary": dict(self.history_summary),
        }

    def to_json(self, *, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, sort_keys=True) + "\n"

    def to_markdown(self) -> str:
        lines = [
            "# WorldForge World Diff",
            "",
            f"- source: `{self.source_label}`",
            f"- target: `{self.target_label}`",
            f"- schema_version: {self.schema_version}",
            f"- field_changes: {len(self.field_changes)}",
            f"- object_changes: {len(self.object_changes)}",
            (
                f"- history: {self.history_summary.get('source', 0)} → "
                f"{self.history_summary.get('target', 0)} entries"
            ),
            "",
            "## Field Changes",
            "",
        ]
        if self.field_changes:
            lines.extend(["| Field | Before | After |", "| --- | --- | --- |"])
            lines.extend(
                f"| {change.field} | "
                f"{_format_inline(change.before)} | "
                f"{_format_inline(change.after)} |"
                for change in self.field_changes
            )
        else:
            lines.append("- No top-level field changes.")

        lines.extend(["", "## Object Changes", ""])
        if self.object_changes:
            lines.extend(["| Kind | Object ID | Field Changes |", "| --- | --- | --- |"])
            lines.extend(
                f"| {change.kind} | `{change.object_id}` | "
                f"{', '.join(change.field_changes) or '-'} |"
                for change in self.object_changes
            )
        else:
            lines.append("- No scene object changes.")
        return "\n".join(lines) + "\n"

    def is_empty(self) -> bool:
        return not self.field_changes and not self.object_changes


@dataclass(frozen=True, slots=True)
class WorldPatch:
    """A patch derived from a :class:`WorldDiff` that applies to a base snapshot.

    The patch is a sequenced list of validated operations. Applying a patch is
    deterministic — it does not attempt three-way merge or conflict resolution.
    Use :func:`apply_patch` to apply against a snapshot.
    """

    schema_version: int
    field_changes: tuple[WorldFieldChange, ...]
    object_changes: tuple[ObjectChange, ...]

    @classmethod
    def from_diff(cls, diff: WorldDiff) -> WorldPatch:
        return cls(
            schema_version=diff.schema_version,
            field_changes=diff.field_changes,
            object_changes=diff.object_changes,
        )

    def to_dict(self) -> JSONDict:
        return {
            "schema_version": self.schema_version,
            "field_changes": [change.to_dict() for change in self.field_changes],
            "object_changes": [change.to_dict() for change in self.object_changes],
        }

    def to_json(self, *, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, sort_keys=True) + "\n"


def diff_worlds(
    source: JSONDict | World,
    target: JSONDict | World,
    *,
    source_label: str = "source",
    target_label: str = "target",
) -> WorldDiff:
    """Compare two world snapshots and return a structured diff.

    Either argument may be a :class:`worldforge.framework.World` instance or a
    JSON-shaped dict (e.g. loaded from a persisted ``.json`` world file or
    from ``World.to_dict()``). The diff is read-only — neither input is
    mutated.
    """

    source_dict = _coerce_to_dict(source, name="source")
    target_dict = _coerce_to_dict(target, name="target")

    field_changes = tuple(_field_changes(source_dict, target_dict))
    object_changes = tuple(_object_changes(source_dict, target_dict))
    history_summary = {
        "source": _history_length(source_dict),
        "target": _history_length(target_dict),
    }

    return WorldDiff(
        schema_version=WORLD_DIFF_SCHEMA_VERSION,
        source_label=source_label,
        target_label=target_label,
        field_changes=field_changes,
        object_changes=object_changes,
        history_summary=history_summary,
    )


def diff_worlds_from_paths(
    source_path: Path | str,
    target_path: Path | str,
) -> WorldDiff:
    """Load two persisted or exported world JSON files and diff them."""

    source = _load_world_payload(source_path, name="source")
    target = _load_world_payload(target_path, name="target")
    return diff_worlds(
        source,
        target,
        source_label=str(source_path),
        target_label=str(target_path),
    )


def apply_patch(world_state: JSONDict, patch: WorldPatch) -> JSONDict:
    """Apply a patch to a world snapshot, validating each change before applying.

    The function never mutates ``world_state``; it returns a new dict. Each
    operation is validated through :class:`SceneObject`, :class:`Position`,
    and :class:`BBox` so patches that introduce traversal-shaped IDs,
    incoherent bboxes, or malformed scene objects raise
    :class:`WorldStateError` instead of silently corrupting persisted state.
    """

    if not isinstance(world_state, Mapping):
        raise WorldStateError("apply_patch base world_state must be a JSON object.")
    if not isinstance(patch, WorldPatch):
        raise WorldForgeError("apply_patch patch must be a WorldPatch instance.")

    # Deep enough copy to allow per-key mutation without leaking changes back.
    new_state = json.loads(json.dumps(dict(world_state)))
    if "scene" not in new_state or not isinstance(new_state["scene"], dict):
        new_state["scene"] = {"objects": {}}
    objects = new_state["scene"].setdefault("objects", {})
    if not isinstance(objects, dict):
        raise WorldStateError("World scene.objects must be a JSON object.")

    for change in patch.field_changes:
        _apply_field_change(new_state, change)

    for change in patch.object_changes:
        _apply_object_change(objects, change)

    return new_state


def _apply_field_change(state: JSONDict, change: WorldFieldChange) -> None:
    if change.field == "step":
        if not isinstance(change.after, int) or change.after < 0:
            raise WorldStateError("Patch step value must be a non-negative integer.")
        state["step"] = change.after
        return
    if change.field == "metadata":
        if change.after is not None and not isinstance(change.after, dict):
            raise WorldStateError("Patch metadata value must be a JSON object or null.")
        state["metadata"] = dict(change.after or {})
        return
    if change.after is not None and not isinstance(change.after, str):
        raise WorldStateError(f"Patch {change.field} value must be a string or null.")
    state[change.field] = change.after


def _apply_object_change(objects: dict, change: ObjectChange) -> None:
    if change.kind == "added":
        if change.object_id in objects:
            raise WorldStateError(
                f"Patch cannot add object '{change.object_id}': id already present."
            )
        validated = _validate_object_payload(change.after, name="patch added object")
        objects[change.object_id] = validated
        return
    if change.kind == "removed":
        if change.object_id not in objects:
            raise WorldStateError(
                f"Patch cannot remove object '{change.object_id}': id not present."
            )
        del objects[change.object_id]
        return
    if change.kind == "updated":
        if change.object_id not in objects:
            raise WorldStateError(
                f"Patch cannot update object '{change.object_id}': id not present."
            )
        validated = _validate_object_payload(change.after, name="patch updated object")
        objects[change.object_id] = validated


def _coerce_to_dict(value: object, *, name: str) -> JSONDict:
    if isinstance(value, Mapping):
        return dict(value)
    if hasattr(value, "to_dict") and callable(value.to_dict):
        payload = value.to_dict()
        if isinstance(payload, Mapping):
            return dict(payload)
    raise WorldForgeError(f"diff_worlds {name} must be a World instance or a JSON-shaped dict.")


def _load_world_payload(path: Path | str, *, name: str) -> JSONDict:
    target = Path(path).expanduser()
    try:
        text = target.read_text(encoding="utf-8")
    except OSError as exc:
        raise WorldForgeError(f"Failed to read {name} world file {target}: {exc}") from exc
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise WorldForgeError(f"{name.title()} world file {target} contains invalid JSON.") from exc
    if not isinstance(payload, dict):
        raise WorldForgeError(f"{name.title()} world file {target} must be a JSON object.")
    return payload


def _field_changes(
    source: JSONDict,
    target: JSONDict,
) -> Iterable[WorldFieldChange]:
    for field in WORLD_FIELD_NAMES:
        before = source.get(field)
        after = target.get(field)
        if field == "metadata":
            before = dict(before or {})
            after = dict(after or {})
        if before != after:
            yield WorldFieldChange(field=field, before=before, after=after)


def _object_changes(
    source: JSONDict,
    target: JSONDict,
) -> Iterable[ObjectChange]:
    source_objects = _scene_objects(source)
    target_objects = _scene_objects(target)
    for object_id in sorted(target_objects.keys() - source_objects.keys()):
        yield ObjectChange(
            kind="added",
            object_id=object_id,
            after=dict(target_objects[object_id]),
        )
    for object_id in sorted(source_objects.keys() - target_objects.keys()):
        yield ObjectChange(
            kind="removed",
            object_id=object_id,
            before=dict(source_objects[object_id]),
        )
    for object_id in sorted(source_objects.keys() & target_objects.keys()):
        before = source_objects[object_id]
        after = target_objects[object_id]
        if before == after:
            continue
        changed_fields = tuple(
            field
            for field in sorted(set(before) | set(after))
            if before.get(field) != after.get(field)
        )
        yield ObjectChange(
            kind="updated",
            object_id=object_id,
            before=dict(before),
            after=dict(after),
            field_changes=changed_fields,
        )


def _scene_objects(state: JSONDict) -> dict[str, JSONDict]:
    scene = state.get("scene")
    if not isinstance(scene, Mapping):
        return {}
    objects = scene.get("objects")
    if not isinstance(objects, Mapping):
        return {}
    return {
        str(object_id): dict(payload)
        for object_id, payload in objects.items()
        if isinstance(payload, Mapping)
    }


def _history_length(state: JSONDict) -> int:
    history = state.get("history")
    return len(history) if isinstance(history, list) else 0


def _validate_object_id(object_id: object) -> None:
    if not isinstance(object_id, str) or not object_id.strip():
        raise WorldForgeError("ObjectChange object_id must be a non-empty string.")
    if object_id in {".", ".."} or "/" in object_id or "\\" in object_id:
        raise WorldForgeError(
            f"ObjectChange object_id '{object_id}' is traversal-shaped and rejected."
        )


def _validate_object_payload(payload: object, *, name: str) -> JSONDict:
    """Round-trip a scene-object payload through :class:`SceneObject` validation."""

    if not isinstance(payload, Mapping):
        raise WorldStateError(f"{name} payload must be a JSON object.")
    try:
        pose = payload.get("pose") or {}
        if not isinstance(pose, Mapping):
            raise WorldStateError(f"{name} pose must be a JSON object.")
        position_payload = pose.get("position") or {}
        if not isinstance(position_payload, Mapping):
            raise WorldStateError(f"{name} pose.position must be a JSON object.")
        position = Position(
            float(position_payload.get("x", 0.0)),
            float(position_payload.get("y", 0.0)),
            float(position_payload.get("z", 0.0)),
        )
        bbox_payload = payload.get("bbox") or {}
        if not isinstance(bbox_payload, Mapping):
            raise WorldStateError(f"{name} bbox must be a JSON object.")
        bbox_min = bbox_payload.get("min") or {}
        bbox_max = bbox_payload.get("max") or {}
        if not isinstance(bbox_min, Mapping) or not isinstance(bbox_max, Mapping):
            raise WorldStateError(f"{name} bbox.min and bbox.max must be JSON objects.")
        bbox = BBox(
            Position(
                float(bbox_min.get("x", 0.0)),
                float(bbox_min.get("y", 0.0)),
                float(bbox_min.get("z", 0.0)),
            ),
            Position(
                float(bbox_max.get("x", 0.0)),
                float(bbox_max.get("y", 0.0)),
                float(bbox_max.get("z", 0.0)),
            ),
        )
        scene_object = SceneObject(
            name=str(payload.get("name", "object")),
            position=position,
            bbox=bbox,
            id=str(payload.get("id")) if payload.get("id") is not None else None,
            is_graspable=bool(payload.get("is_graspable", False)),
            metadata=dict(payload.get("metadata") or {}),
        )
    except WorldForgeError as exc:
        raise WorldStateError(f"{name} validation failed: {exc}") from exc
    return scene_object.to_dict()


def _format_inline(value: object) -> str:
    if value is None:
        return "-"
    if isinstance(value, str | int | float | bool):
        return str(value)
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


__all__ = [
    "OBJECT_CHANGE_KINDS",
    "WORLD_DIFF_SCHEMA_VERSION",
    "WORLD_FIELD_NAMES",
    "ObjectChange",
    "WorldDiff",
    "WorldFieldChange",
    "WorldPatch",
    "apply_patch",
    "diff_worlds",
    "diff_worlds_from_paths",
]

"""Scene, action, and local world-history data contracts."""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field

from worldforge._model_utils import (
    JSONDict,
    WorldForgeError,
    dump_json,
    generate_id,
    require_bool,
    require_finite_number,
    require_json_dict,
    require_non_negative_int,
)


@dataclass(slots=True, frozen=True)
class Position:
    """A 3D position in world coordinates."""

    x: float
    y: float
    z: float

    def __post_init__(self) -> None:
        object.__setattr__(self, "x", require_finite_number(self.x, name="Position.x"))
        object.__setattr__(self, "y", require_finite_number(self.y, name="Position.y"))
        object.__setattr__(self, "z", require_finite_number(self.z, name="Position.z"))

    def to_dict(self) -> JSONDict:
        return {"x": self.x, "y": self.y, "z": self.z}

    @classmethod
    def from_dict(cls, payload: JSONDict) -> Position:
        if not isinstance(payload, dict):
            raise WorldForgeError("Position payload must be a JSON object.")
        try:
            return cls(
                x=payload["x"],
                y=payload["y"],
                z=payload["z"],
            )
        except KeyError as exc:
            raise WorldForgeError(
                f"Position payload is missing coordinate '{exc.args[0]}'."
            ) from exc

    def distance_to(self, other: Position) -> float:
        """Return the Euclidean distance to ``other`` in world-coordinate units."""

        return math.dist((self.x, self.y, self.z), (other.x, other.y, other.z))


@dataclass(slots=True, frozen=True)
class Rotation:
    """A quaternion rotation."""

    w: float = 1.0
    x: float = 0.0
    y: float = 0.0
    z: float = 0.0

    def __post_init__(self) -> None:
        object.__setattr__(self, "w", require_finite_number(self.w, name="Rotation.w"))
        object.__setattr__(self, "x", require_finite_number(self.x, name="Rotation.x"))
        object.__setattr__(self, "y", require_finite_number(self.y, name="Rotation.y"))
        object.__setattr__(self, "z", require_finite_number(self.z, name="Rotation.z"))

    def to_dict(self) -> JSONDict:
        return {"w": self.w, "x": self.x, "y": self.y, "z": self.z}

    @classmethod
    def from_dict(cls, payload: JSONDict | None) -> Rotation:
        if payload is None:
            return cls()
        if not isinstance(payload, dict):
            raise WorldForgeError("Rotation payload must be a JSON object when provided.")
        return cls(
            w=payload.get("w", 1.0),
            x=payload.get("x", 0.0),
            y=payload.get("y", 0.0),
            z=payload.get("z", 0.0),
        )


@dataclass(slots=True, frozen=True)
class Pose:
    """A 6DoF pose."""

    position: Position
    rotation: Rotation = field(default_factory=Rotation)

    def __post_init__(self) -> None:
        if not isinstance(self.position, Position):
            raise WorldForgeError("Pose position must be a Position.")
        if not isinstance(self.rotation, Rotation):
            raise WorldForgeError("Pose rotation must be a Rotation.")

    def to_dict(self) -> JSONDict:
        return {"position": self.position.to_dict(), "rotation": self.rotation.to_dict()}

    @classmethod
    def from_dict(cls, payload: JSONDict) -> Pose:
        if not isinstance(payload, dict):
            raise WorldForgeError("Pose payload must be a JSON object.")
        return cls(
            position=Position.from_dict(payload["position"]),
            rotation=Rotation.from_dict(payload.get("rotation")),
        )


@dataclass(slots=True, frozen=True)
class BBox:
    """Axis-aligned bounding box."""

    min: Position
    max: Position

    def __post_init__(self) -> None:
        if not isinstance(self.min, Position) or not isinstance(self.max, Position):
            raise WorldForgeError("BBox min and max must be Position instances.")
        if self.min.x > self.max.x or self.min.y > self.max.y or self.min.z > self.max.z:
            raise WorldForgeError("BBox min coordinates must be less than or equal to max.")

    def to_dict(self) -> JSONDict:
        return {"min": self.min.to_dict(), "max": self.max.to_dict()}

    @classmethod
    def from_dict(cls, payload: JSONDict) -> BBox:
        if not isinstance(payload, dict):
            raise WorldForgeError("BBox payload must be a JSON object.")
        return cls(
            min=Position.from_dict(payload["min"]),
            max=Position.from_dict(payload["max"]),
        )


@dataclass(slots=True)
class Action:
    """A structured action applied to a world."""

    kind: str
    parameters: JSONDict = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.kind, str) or not self.kind.strip():
            raise WorldForgeError("Action kind must be a non-empty string.")
        if not isinstance(self.parameters, dict):
            raise WorldForgeError("Action parameters must be a JSON object.")
        self.kind = self.kind.strip()
        self.parameters = require_json_dict(self.parameters, name="Action parameters")

    @staticmethod
    def move_to(
        x: float,
        y: float,
        z: float,
        speed: float = 1.0,
        *,
        object_id: str | None = None,
    ) -> Action:
        target_position = Position(x, y, z)
        resolved_speed = require_finite_number(speed, name="Action.move_to speed")
        if resolved_speed <= 0.0:
            raise WorldForgeError("Action.move_to speed must be greater than 0.")
        parameters: JSONDict = {
            "target": target_position.to_dict(),
            "speed": resolved_speed,
        }
        if object_id is not None:
            if not str(object_id).strip():
                raise WorldForgeError("Action.move_to object_id must not be empty when provided.")
            parameters["object_id"] = str(object_id).strip()
        return Action(
            "move_to",
            parameters,
        )

    @staticmethod
    def spawn_object(
        name: str,
        position: Position | None = None,
        bbox: BBox | None = None,
    ) -> Action:
        if not isinstance(name, str) or not name.strip():
            raise WorldForgeError("Action.spawn_object name must be a non-empty string.")
        object_position = position or Position(0.0, 0.5, 0.0)
        object_bbox = bbox or BBox(
            Position(object_position.x - 0.05, object_position.y - 0.05, object_position.z - 0.05),
            Position(object_position.x + 0.05, object_position.y + 0.05, object_position.z + 0.05),
        )
        return Action(
            "spawn_object",
            {
                "name": name.strip(),
                "position": object_position.to_dict(),
                "bbox": object_bbox.to_dict(),
            },
        )

    @staticmethod
    def from_dict(payload: JSONDict) -> Action:
        if not isinstance(payload, dict):
            raise WorldForgeError("Action.from_dict expects a JSON object.")
        if "type" in payload:
            parameters = payload.get("parameters", {})
            if not isinstance(parameters, dict):
                raise WorldForgeError("Action.from_dict field 'parameters' must be a JSON object.")
            return Action(str(payload["type"]), parameters)
        if len(payload) != 1:
            raise WorldForgeError("Action.from_dict expects {'type': ...} or a single-key mapping.")
        kind, parameters = next(iter(payload.items()))
        if not isinstance(parameters, dict):
            raise WorldForgeError("Action.from_dict single-key parameters must be a JSON object.")
        return Action(str(kind), parameters)

    def to_dict(self) -> JSONDict:
        return {"type": self.kind, "parameters": dict(self.parameters)}

    def to_json(self) -> str:
        return dump_json(self.to_dict())


@dataclass(slots=True)
class SceneObjectPatch:
    """Partial mutation for a scene object."""

    name: str | None = None
    position: Position | None = None
    graspable: bool | None = None

    def __post_init__(self) -> None:
        if self.name is not None:
            self.set_name(self.name)
        if self.position is not None:
            self.set_position(self.position)
        if self.graspable is not None:
            self.set_graspable(self.graspable)

    def set_name(self, name: str) -> None:
        if not isinstance(name, str) or not name.strip():
            raise WorldForgeError("SceneObjectPatch name must be a non-empty string.")
        self.name = name.strip()

    def set_position(self, position: Position) -> None:
        if not isinstance(position, Position):
            raise WorldForgeError("SceneObjectPatch position must be a Position.")
        self.position = position

    def set_graspable(self, value: bool) -> None:
        self.graspable = require_bool(value, name="SceneObjectPatch graspable")


@dataclass(slots=True)
class SceneObject:
    """An object tracked in the scene graph."""

    name: str
    position: Position
    bbox: BBox
    id: str = field(default_factory=lambda: generate_id("obj"))
    is_graspable: bool = False
    metadata: JSONDict = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or not self.name.strip():
            raise WorldForgeError("SceneObject name must be a non-empty string.")
        if not isinstance(self.position, Position):
            raise WorldForgeError("SceneObject position must be a Position.")
        if not isinstance(self.bbox, BBox):
            raise WorldForgeError("SceneObject bbox must be a BBox.")
        if not isinstance(self.id, str) or not self.id.strip():
            raise WorldForgeError("SceneObject id must be a non-empty string.")
        if not isinstance(self.metadata, dict):
            raise WorldForgeError("SceneObject metadata must be a JSON object.")
        self.name = self.name.strip()
        self.id = self.id.strip()
        self.is_graspable = require_bool(
            self.is_graspable,
            name="SceneObject is_graspable",
        )
        self.metadata = require_json_dict(self.metadata, name="SceneObject metadata")

    @property
    def pose(self) -> Pose:
        return Pose(position=self.position)

    def copy(self) -> SceneObject:
        return SceneObject.from_dict(self.to_dict())

    def _bbox_translated_to(self, position: Position) -> BBox:
        dx = position.x - self.position.x
        dy = position.y - self.position.y
        dz = position.z - self.position.z
        return BBox(
            min=Position(
                self.bbox.min.x + dx,
                self.bbox.min.y + dy,
                self.bbox.min.z + dz,
            ),
            max=Position(
                self.bbox.max.x + dx,
                self.bbox.max.y + dy,
                self.bbox.max.z + dz,
            ),
        )

    def apply_patch(self, patch: SceneObjectPatch) -> None:
        if patch.name is not None:
            self.name = patch.name
        if patch.position is not None:
            self.bbox = self._bbox_translated_to(patch.position)
            self.position = patch.position
        if patch.graspable is not None:
            self.is_graspable = patch.graspable

    def to_dict(self) -> JSONDict:
        return {
            "id": self.id,
            "name": self.name,
            "pose": self.pose.to_dict(),
            "bbox": self.bbox.to_dict(),
            "is_graspable": self.is_graspable,
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, payload: JSONDict) -> SceneObject:
        if not isinstance(payload, dict):
            raise WorldForgeError("SceneObject payload must be a JSON object.")
        pose = (
            Pose.from_dict(payload["pose"])
            if "pose" in payload
            else Pose(Position.from_dict(payload["position"]))
        )
        return cls(
            id=str(payload.get("id") or generate_id("obj")),
            name=str(payload["name"]),
            position=pose.position,
            bbox=BBox.from_dict(payload["bbox"]),
            is_graspable=payload.get("is_graspable", False),
            metadata=dict(payload.get("metadata", {})),
        )


@dataclass(slots=True)
class HistoryEntry:
    """A recorded world snapshot."""

    step: int
    state: JSONDict
    summary: str
    action_json: str | None = None

    def __post_init__(self) -> None:
        self.step = require_non_negative_int(self.step, name="HistoryEntry step")
        if not isinstance(self.state, dict):
            raise WorldForgeError("HistoryEntry state must be a JSON object.")
        if not isinstance(self.summary, str) or not self.summary.strip():
            raise WorldForgeError("HistoryEntry summary must be a non-empty string.")
        if self.action_json is not None:
            if not isinstance(self.action_json, str) or not self.action_json.strip():
                raise WorldForgeError(
                    "HistoryEntry action_json must be a non-empty string when provided."
                )
            try:
                action_payload = json.loads(self.action_json)
            except json.JSONDecodeError as exc:
                raise WorldForgeError("HistoryEntry action_json must be valid JSON.") from exc
            Action.from_dict(action_payload)
        self.state = dict(self.state)
        self.summary = self.summary.strip()

    def to_dict(self) -> JSONDict:
        return {
            "step": self.step,
            "state": self.state,
            "summary": self.summary,
            "action_json": self.action_json,
        }

    @classmethod
    def from_dict(cls, payload: JSONDict) -> HistoryEntry:
        if not isinstance(payload, dict):
            raise WorldForgeError("HistoryEntry payload must be a JSON object.")
        return cls(
            step=payload["step"],
            state=payload["state"],
            summary=payload.get("summary", ""),
            action_json=payload.get("action_json"),
        )


def __getattr__(name: str) -> object:
    if name == "StructuredGoal":
        from worldforge.structured_goals import StructuredGoal

        return StructuredGoal
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

"""Core models and serialization helpers for WorldForge."""

from __future__ import annotations

import json
import math
from collections.abc import Iterable
from dataclasses import dataclass, field
from hashlib import sha256
from mimetypes import guess_type
from pathlib import Path
from typing import Any
from uuid import uuid4

JSONDict = dict[str, Any]


class WorldForgeError(ValueError):
    """Raised when a caller supplies invalid input to the framework."""


class WorldStateError(WorldForgeError):
    """Raised when persisted or provider-supplied world state is malformed."""


def generate_id(prefix: str) -> str:
    """Return an opaque identifier with a stable prefix."""

    return f"{prefix}_{uuid4().hex[:12]}"


def dump_json(payload: Any) -> str:
    """Serialize data with deterministic formatting."""

    try:
        return json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise WorldForgeError(
            "Payload must be JSON serializable and contain only finite numbers."
        ) from exc


def ensure_directory(path: Path) -> None:
    """Create a directory tree when it does not already exist."""

    path.mkdir(parents=True, exist_ok=True)


def average(values: Iterable[float]) -> float:
    """Return the arithmetic mean for a non-empty iterable."""

    numbers = list(values)
    if not numbers:
        return 0.0
    return sum(numbers) / len(numbers)


def require_positive_int(value: int, *, name: str) -> int:
    """Raise WorldForgeError unless ``value`` is a non-bool positive int."""

    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise WorldForgeError(f"{name} must be an integer greater than 0.")
    return value


def require_finite_number(value: float | int, *, name: str) -> float:
    """Raise WorldForgeError unless ``value`` is a finite real number."""

    if isinstance(value, bool) or not isinstance(value, int | float):
        raise WorldForgeError(f"{name} must be a finite number.")
    number = float(value)
    if not math.isfinite(number):
        raise WorldForgeError(f"{name} must be a finite number.")
    return number


def require_probability(value: float | int, *, name: str) -> float:
    """Raise WorldForgeError unless ``value`` is finite and within [0, 1]."""

    number = require_finite_number(value, name=name)
    if number < 0.0 or number > 1.0:
        raise WorldForgeError(f"{name} must be between 0 and 1.")
    return number


def deterministic_floats(seed: str, size: int) -> list[float]:
    """Generate deterministic floats in the range [0, 1)."""

    digest = sha256(seed.encode("utf-8")).digest()
    values: list[float] = []
    counter = 0
    while len(values) < size:
        block = sha256(digest + counter.to_bytes(4, "big")).digest()
        for index in range(0, len(block), 4):
            if len(values) >= size:
                break
            chunk = int.from_bytes(block[index : index + 4], "big")
            values.append((chunk % 10_000) / 10_000.0)
        counter += 1
    return values


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
        self.parameters = dict(self.parameters)

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


@dataclass(slots=True, frozen=True)
class StructuredGoal:
    """Typed structured planning goal with explicit validation."""

    kind: str
    object_id: str | None = None
    object_name: str | None = None
    position: Position | None = None
    reference_object_id: str | None = None
    reference_object_name: str | None = None
    offset: Position | None = None
    tolerance: float = 0.05

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "tolerance",
            require_finite_number(self.tolerance, name="StructuredGoal tolerance"),
        )
        if self.kind not in {"object_at", "spawn_object", "object_near", "swap_objects"}:
            raise WorldForgeError(
                "StructuredGoal kind must be one of: object_at, spawn_object, "
                "object_near, swap_objects."
            )
        if self.kind in {"object_at", "object_near", "swap_objects"} and self.tolerance <= 0.0:
            raise WorldForgeError(f"StructuredGoal {self.kind} tolerance must be greater than 0.")
        if self.kind == "object_at":
            if self.position is None:
                raise WorldForgeError("StructuredGoal object_at goals require a target position.")
            self._require_primary_selector("object_at")
            self._reject_reference_selector("object_at")
            self._reject_offset("object_at")
        if self.kind == "spawn_object":
            if not self.object_name:
                raise WorldForgeError("StructuredGoal spawn_object goals require object_name.")
            if self.object_id is not None:
                raise WorldForgeError("StructuredGoal spawn_object goals do not accept object_id.")
            self._reject_reference_selector("spawn_object")
            self._reject_offset("spawn_object")
        if self.kind == "object_near":
            self._require_primary_selector("object_near")
            self._require_reference_selector("object_near")
            if self.position is not None:
                raise WorldForgeError("StructuredGoal object_near goals do not accept position.")
            if self.offset is None:
                object.__setattr__(self, "offset", Position(0.1, 0.0, 0.0))
            self._require_distinct_selectors("object_near")
        if self.kind == "swap_objects":
            self._require_primary_selector("swap_objects")
            self._require_reference_selector("swap_objects")
            if self.position is not None:
                raise WorldForgeError("StructuredGoal swap_objects goals do not accept position.")
            self._reject_offset("swap_objects")
            self._require_distinct_selectors("swap_objects")

    @staticmethod
    def _has_selector(object_id: str | None, object_name: str | None) -> bool:
        return bool(object_id or object_name)

    @staticmethod
    def _selector_label(
        object_id: str | None,
        object_name: str | None,
        *,
        fallback: str = "object",
    ) -> str:
        return object_name or object_id or fallback

    @staticmethod
    def _normalize_selector_payload(
        payload: object,
        *,
        field_name: str,
    ) -> JSONDict:
        if payload is None:
            return {}
        if isinstance(payload, str):
            return {"name": payload}
        if not isinstance(payload, dict):
            raise WorldForgeError(f"StructuredGoal field '{field_name}' must be a JSON object.")
        return payload

    @classmethod
    def _selector_fields(
        cls,
        payload: object,
        *,
        field_name: str,
    ) -> tuple[str | None, str | None]:
        normalized = cls._normalize_selector_payload(payload, field_name=field_name)
        object_id = str(normalized["id"]) if normalized.get("id") is not None else None
        object_name = str(normalized["name"]) if normalized.get("name") is not None else None
        return object_id, object_name

    def _require_primary_selector(self, kind: str) -> None:
        if not self._has_selector(self.object_id, self.object_name):
            raise WorldForgeError(f"StructuredGoal {kind} goals require object_id or object_name.")

    def _require_reference_selector(self, kind: str) -> None:
        if not self._has_selector(self.reference_object_id, self.reference_object_name):
            raise WorldForgeError(
                f"StructuredGoal {kind} goals require reference_object.id or reference_object.name."
            )

    def _reject_reference_selector(self, kind: str) -> None:
        if self.reference_object_id is not None or self.reference_object_name is not None:
            raise WorldForgeError(
                f"StructuredGoal {kind} goals do not accept reference_object selectors."
            )

    def _reject_offset(self, kind: str) -> None:
        if self.offset is not None:
            raise WorldForgeError(f"StructuredGoal {kind} goals do not accept offset.")

    def _require_distinct_selectors(self, kind: str) -> None:
        same_id = (
            self.object_id is not None
            and self.reference_object_id is not None
            and self.object_id == self.reference_object_id
        )
        same_name = (
            self.object_id is None
            and self.reference_object_id is None
            and self.object_name is not None
            and self.object_name == self.reference_object_name
        )
        if same_id or same_name:
            raise WorldForgeError(
                f"StructuredGoal {kind} goals require distinct primary and reference objects."
            )

    @classmethod
    def object_at(
        cls,
        *,
        position: Position,
        object_id: str | None = None,
        object_name: str | None = None,
        tolerance: float = 0.05,
    ) -> StructuredGoal:
        return cls(
            kind="object_at",
            object_id=object_id,
            object_name=object_name,
            position=position,
            tolerance=tolerance,
        )

    @classmethod
    def object_near(
        cls,
        *,
        object_id: str | None = None,
        object_name: str | None = None,
        reference_object_id: str | None = None,
        reference_object_name: str | None = None,
        offset: Position | None = None,
        tolerance: float = 0.05,
    ) -> StructuredGoal:
        return cls(
            kind="object_near",
            object_id=object_id,
            object_name=object_name,
            reference_object_id=reference_object_id,
            reference_object_name=reference_object_name,
            offset=offset,
            tolerance=tolerance,
        )

    @classmethod
    def spawn_object(
        cls,
        object_name: str,
        *,
        position: Position | None = None,
    ) -> StructuredGoal:
        return cls(
            kind="spawn_object",
            object_name=object_name,
            position=position,
        )

    @classmethod
    def swap_objects(
        cls,
        *,
        object_id: str | None = None,
        object_name: str | None = None,
        reference_object_id: str | None = None,
        reference_object_name: str | None = None,
        tolerance: float = 0.05,
    ) -> StructuredGoal:
        return cls(
            kind="swap_objects",
            object_id=object_id,
            object_name=object_name,
            reference_object_id=reference_object_id,
            reference_object_name=reference_object_name,
            tolerance=tolerance,
        )

    @classmethod
    def from_json(cls, payload: str) -> StructuredGoal:
        try:
            decoded = json.loads(payload)
        except json.JSONDecodeError as exc:
            raise WorldForgeError(f"goal_json must be valid JSON: {exc}") from exc
        return cls.from_dict(decoded)

    @classmethod
    def from_dict(cls, payload: JSONDict) -> StructuredGoal:
        if not isinstance(payload, dict):
            raise WorldForgeError("Structured goals must decode to a JSON object.")

        if "kind" in payload:
            kind = str(payload["kind"])
            object_id, object_name = cls._selector_fields(
                payload.get("object"), field_name="object"
            )
            reference_object_id, reference_object_name = cls._selector_fields(
                payload.get("reference_object"),
                field_name="reference_object",
            )
            position_payload = payload.get("position")
            position = (
                Position.from_dict(position_payload) if isinstance(position_payload, dict) else None
            )
            offset_payload = payload.get("offset")
            offset = (
                Position.from_dict(offset_payload) if isinstance(offset_payload, dict) else None
            )
            return cls(
                kind=kind,
                object_id=object_id,
                object_name=object_name,
                position=position,
                reference_object_id=reference_object_id,
                reference_object_name=reference_object_name,
                offset=offset,
                tolerance=payload.get("tolerance", 0.05),
            )

        if payload.get("type") != "condition":
            raise WorldForgeError(
                "StructuredGoal JSON must include either 'kind' or legacy type='condition'."
            )
        condition = payload.get("condition")
        if not isinstance(condition, dict) or len(condition) != 1:
            raise WorldForgeError(
                "Legacy goal_json condition payload must contain exactly one condition."
            )

        condition_name, condition_payload = next(iter(condition.items()))
        if not isinstance(condition_payload, dict):
            raise WorldForgeError("Legacy goal_json condition payload must be a JSON object.")

        if condition_name == "ObjectAt":
            position_payload = condition_payload.get("position")
            if not isinstance(position_payload, dict):
                raise WorldForgeError("Legacy ObjectAt goals require a position object.")
            object_value = condition_payload.get("object")
            object_name = condition_payload.get("object_name")
            return cls.object_at(
                object_id=str(object_value) if object_value is not None else None,
                object_name=str(object_name) if object_name is not None else None,
                position=Position.from_dict(position_payload),
                tolerance=condition_payload.get("tolerance", 0.05),
            )

        if condition_name == "SpawnObject":
            object_payload = condition_payload.get("object", {})
            if isinstance(object_payload, str):
                object_name = object_payload
            elif isinstance(object_payload, dict):
                object_name = object_payload.get("name")
            else:
                object_name = condition_payload.get("name")
            if object_name is None:
                raise WorldForgeError("Legacy SpawnObject goals require object.name or name.")
            position_payload = condition_payload.get("position")
            return cls.spawn_object(
                str(object_name),
                position=(
                    Position.from_dict(position_payload)
                    if isinstance(position_payload, dict)
                    else None
                ),
            )

        if condition_name == "ObjectNear":
            object_id, object_name = cls._selector_fields(
                condition_payload.get("object"),
                field_name="object",
            )
            reference_object_id, reference_object_name = cls._selector_fields(
                condition_payload.get("reference_object", condition_payload.get("anchor")),
                field_name="reference_object",
            )
            offset_payload = condition_payload.get("offset")
            offset = (
                Position.from_dict(offset_payload) if isinstance(offset_payload, dict) else None
            )
            return cls.object_near(
                object_id=object_id,
                object_name=object_name,
                reference_object_id=reference_object_id,
                reference_object_name=reference_object_name,
                offset=offset,
                tolerance=condition_payload.get("tolerance", 0.05),
            )

        if condition_name == "SwapObjects":
            object_id, object_name = cls._selector_fields(
                condition_payload.get("object", condition_payload.get("first_object")),
                field_name="object",
            )
            reference_object_id, reference_object_name = cls._selector_fields(
                condition_payload.get("reference_object", condition_payload.get("second_object")),
                field_name="reference_object",
            )
            return cls.swap_objects(
                object_id=object_id,
                object_name=object_name,
                reference_object_id=reference_object_id,
                reference_object_name=reference_object_name,
                tolerance=condition_payload.get("tolerance", 0.05),
            )

        raise WorldForgeError(f"Unsupported legacy structured goal condition '{condition_name}'.")

    def to_dict(self) -> JSONDict:
        payload: JSONDict = {
            "kind": self.kind,
            "object": {},
        }
        if self.object_id is not None:
            payload["object"]["id"] = self.object_id
        if self.object_name is not None:
            payload["object"]["name"] = self.object_name
        if self.position is not None:
            payload["position"] = self.position.to_dict()
        if self.reference_object_id is not None or self.reference_object_name is not None:
            payload["reference_object"] = {}
            if self.reference_object_id is not None:
                payload["reference_object"]["id"] = self.reference_object_id
            if self.reference_object_name is not None:
                payload["reference_object"]["name"] = self.reference_object_name
        if self.offset is not None:
            payload["offset"] = self.offset.to_dict()
        if self.kind in {"object_at", "object_near", "swap_objects"}:
            payload["tolerance"] = self.tolerance
        return payload

    def to_json(self) -> str:
        return dump_json(self.to_dict())

    def summary(self) -> str:
        if self.kind == "spawn_object":
            return f"spawn {self.object_name}"
        target = self._selector_label(self.object_id, self.object_name)
        if self.kind == "object_near":
            reference = self._selector_label(
                self.reference_object_id,
                self.reference_object_name,
                fallback="reference object",
            )
            assert self.offset is not None
            return (
                f"move {target} near {reference} "
                f"with offset ({self.offset.x:.2f}, {self.offset.y:.2f}, {self.offset.z:.2f})"
            )
        if self.kind == "swap_objects":
            reference = self._selector_label(
                self.reference_object_id,
                self.reference_object_name,
                fallback="reference object",
            )
            return f"swap {target} with {reference}"
        assert self.position is not None
        return (
            f"move {target} to "
            f"({self.position.x:.2f}, {self.position.y:.2f}, {self.position.z:.2f})"
        )


@dataclass(slots=True)
class SceneObjectPatch:
    """Partial mutation for a scene object."""

    name: str | None = None
    position: Position | None = None
    graspable: bool | None = None

    def set_name(self, name: str) -> None:
        if not isinstance(name, str) or not name.strip():
            raise WorldForgeError("SceneObjectPatch name must be a non-empty string.")
        self.name = name.strip()

    def set_position(self, position: Position) -> None:
        if not isinstance(position, Position):
            raise WorldForgeError("SceneObjectPatch position must be a Position.")
        self.position = position

    def set_graspable(self, value: bool) -> None:
        self.graspable = bool(value)


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
        self.is_graspable = bool(self.is_graspable)
        self.metadata = dict(self.metadata)

    @property
    def pose(self) -> Pose:
        return Pose(position=self.position)

    def copy(self) -> SceneObject:
        return SceneObject.from_dict(self.to_dict())

    def apply_patch(self, patch: SceneObjectPatch) -> None:
        if patch.name is not None:
            self.name = patch.name
        if patch.position is not None:
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
            is_graspable=bool(payload.get("is_graspable", False)),
            metadata=dict(payload.get("metadata", {})),
        )


@dataclass(slots=True)
class ProviderCapabilities:
    """Boolean capability matrix for a provider."""

    predict: bool = True
    generate: bool = False
    reason: bool = False
    embed: bool = False
    plan: bool = False
    transfer: bool = False

    def to_dict(self) -> JSONDict:
        return {
            "predict": self.predict,
            "generate": self.generate,
            "reason": self.reason,
            "embed": self.embed,
            "plan": self.plan,
            "transfer": self.transfer,
        }

    def supports(self, capability: str) -> bool:
        return bool(getattr(self, capability, False))

    def enabled_names(self) -> list[str]:
        return [name for name, enabled in self.to_dict().items() if enabled]


@dataclass(slots=True, frozen=True)
class RetryPolicy:
    """Retry and backoff policy for one class of remote operations."""

    max_attempts: int = 1
    backoff_seconds: float = 0.0
    backoff_multiplier: float = 1.0
    retryable_status_codes: tuple[int, ...] = (408, 429, 500, 502, 503, 504)

    def __post_init__(self) -> None:
        if (
            isinstance(self.max_attempts, bool)
            or not isinstance(self.max_attempts, int)
            or self.max_attempts < 1
        ):
            raise WorldForgeError("RetryPolicy max_attempts must be greater than or equal to 1.")
        object.__setattr__(
            self,
            "backoff_seconds",
            require_finite_number(self.backoff_seconds, name="RetryPolicy backoff_seconds"),
        )
        object.__setattr__(
            self,
            "backoff_multiplier",
            require_finite_number(self.backoff_multiplier, name="RetryPolicy backoff_multiplier"),
        )
        if self.backoff_seconds < 0.0:
            raise WorldForgeError("RetryPolicy backoff_seconds must be non-negative.")
        if self.backoff_multiplier < 1.0:
            raise WorldForgeError(
                "RetryPolicy backoff_multiplier must be greater than or equal to 1."
            )
        object.__setattr__(
            self,
            "retryable_status_codes",
            tuple(self.retryable_status_codes),
        )
        for status_code in self.retryable_status_codes:
            if (
                isinstance(status_code, bool)
                or not isinstance(status_code, int)
                or status_code < 100
                or status_code > 599
            ):
                raise WorldForgeError(
                    "RetryPolicy retryable_status_codes must contain valid HTTP status codes."
                )

    def delay_for_attempt(self, attempt_number: int) -> float:
        """Return the sleep delay before the given attempt number."""

        if attempt_number <= 1 or self.backoff_seconds == 0.0:
            return 0.0
        return self.backoff_seconds * (self.backoff_multiplier ** (attempt_number - 2))

    def to_dict(self) -> JSONDict:
        return {
            "max_attempts": self.max_attempts,
            "backoff_seconds": self.backoff_seconds,
            "backoff_multiplier": self.backoff_multiplier,
            "retryable_status_codes": list(self.retryable_status_codes),
        }


@dataclass(slots=True, frozen=True)
class RequestOperationPolicy:
    """Timeout and retry policy for a single remote operation type."""

    timeout_seconds: float
    retry: RetryPolicy = field(default_factory=RetryPolicy)

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "timeout_seconds",
            require_finite_number(
                self.timeout_seconds,
                name="RequestOperationPolicy timeout_seconds",
            ),
        )
        if self.timeout_seconds <= 0.0:
            raise WorldForgeError("RequestOperationPolicy timeout_seconds must be greater than 0.")

    def to_dict(self) -> JSONDict:
        return {
            "timeout_seconds": self.timeout_seconds,
            "retry": self.retry.to_dict(),
        }


@dataclass(slots=True, frozen=True)
class ProviderRequestPolicy:
    """Typed network policy for HTTP-backed provider operations."""

    health: RequestOperationPolicy
    request: RequestOperationPolicy
    polling: RequestOperationPolicy
    download: RequestOperationPolicy

    @classmethod
    def remote_defaults(
        cls,
        *,
        request_timeout_seconds: float,
        health_timeout_seconds: float | None = None,
        polling_timeout_seconds: float | None = None,
        download_timeout_seconds: float | None = None,
        read_retry_attempts: int = 3,
        read_backoff_seconds: float = 0.25,
        read_backoff_multiplier: float = 2.0,
    ) -> ProviderRequestPolicy:
        read_retry = RetryPolicy(
            max_attempts=read_retry_attempts,
            backoff_seconds=read_backoff_seconds,
            backoff_multiplier=read_backoff_multiplier,
        )
        no_retry = RetryPolicy(max_attempts=1)
        resolved_request_timeout = require_finite_number(
            request_timeout_seconds,
            name="ProviderRequestPolicy request_timeout_seconds",
        )
        resolved_health_timeout = require_finite_number(
            health_timeout_seconds
            if health_timeout_seconds is not None
            else min(resolved_request_timeout, 10.0),
            name="ProviderRequestPolicy health_timeout_seconds",
        )
        resolved_polling_timeout = require_finite_number(
            polling_timeout_seconds
            if polling_timeout_seconds is not None
            else min(resolved_request_timeout, 30.0),
            name="ProviderRequestPolicy polling_timeout_seconds",
        )
        resolved_download_timeout = require_finite_number(
            download_timeout_seconds
            if download_timeout_seconds is not None
            else resolved_request_timeout,
            name="ProviderRequestPolicy download_timeout_seconds",
        )
        return cls(
            health=RequestOperationPolicy(
                timeout_seconds=resolved_health_timeout,
                retry=read_retry,
            ),
            request=RequestOperationPolicy(
                timeout_seconds=resolved_request_timeout,
                retry=no_retry,
            ),
            polling=RequestOperationPolicy(
                timeout_seconds=resolved_polling_timeout,
                retry=read_retry,
            ),
            download=RequestOperationPolicy(
                timeout_seconds=resolved_download_timeout,
                retry=read_retry,
            ),
        )

    def to_dict(self) -> JSONDict:
        return {
            "health": self.health.to_dict(),
            "request": self.request.to_dict(),
            "polling": self.polling.to_dict(),
            "download": self.download.to_dict(),
        }


@dataclass(slots=True)
class GenerationOptions:
    """Typed generation options for remote video and world-model providers."""

    image: str | None = None
    video: str | None = None
    model: str | None = None
    ratio: str | None = None
    size: str | None = None
    fps: float | None = None
    seed: int | None = None
    negative_prompt: str | None = None
    reference_images: list[str] = field(default_factory=list)
    extras: JSONDict = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.fps is not None:
            self.fps = require_finite_number(self.fps, name="GenerationOptions fps")
            if self.fps <= 0.0:
                raise WorldForgeError("GenerationOptions fps must be greater than 0.")
        if self.seed is not None and (
            isinstance(self.seed, bool) or not isinstance(self.seed, int)
        ):
            raise WorldForgeError("GenerationOptions seed must be an integer when provided.")
        if not isinstance(self.reference_images, list) or not all(
            isinstance(reference, str) for reference in self.reference_images
        ):
            raise WorldForgeError("GenerationOptions reference_images must be a list of strings.")
        if not isinstance(self.extras, dict):
            raise WorldForgeError("GenerationOptions extras must be a JSON object.")
        self.reference_images = list(self.reference_images)
        self.extras = dict(self.extras)

    def to_dict(self) -> JSONDict:
        return {
            "image": self.image,
            "video": self.video,
            "model": self.model,
            "ratio": self.ratio,
            "size": self.size,
            "fps": self.fps,
            "seed": self.seed,
            "negative_prompt": self.negative_prompt,
            "reference_images": list(self.reference_images),
            "extras": dict(self.extras),
        }


@dataclass(slots=True)
class ProviderInfo:
    """Public provider metadata."""

    name: str
    capabilities: ProviderCapabilities
    is_local: bool
    description: str = ""

    def to_dict(self) -> JSONDict:
        return {
            "name": self.name,
            "capabilities": self.capabilities.to_dict(),
            "is_local": self.is_local,
            "description": self.description,
        }


@dataclass(slots=True)
class ProviderProfile:
    """Richer provider metadata for routing, docs, and diagnostics."""

    name: str
    capabilities: ProviderCapabilities
    is_local: bool
    description: str = ""
    package: str = "worldforge"
    implementation_status: str = "experimental"
    deterministic: bool = False
    requires_credentials: bool = False
    credential_env_var: str | None = None
    required_env_vars: list[str] = field(default_factory=list)
    supported_modalities: list[str] = field(default_factory=list)
    artifact_types: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    default_model: str | None = None
    supported_models: list[str] = field(default_factory=list)
    request_policy: ProviderRequestPolicy | None = None

    @property
    def supported_tasks(self) -> list[str]:
        return self.capabilities.enabled_names()

    def to_dict(self) -> JSONDict:
        return {
            "name": self.name,
            "capabilities": self.capabilities.to_dict(),
            "supported_tasks": self.supported_tasks,
            "is_local": self.is_local,
            "description": self.description,
            "package": self.package,
            "implementation_status": self.implementation_status,
            "deterministic": self.deterministic,
            "requires_credentials": self.requires_credentials,
            "credential_env_var": self.credential_env_var,
            "required_env_vars": list(self.required_env_vars),
            "supported_modalities": list(self.supported_modalities),
            "artifact_types": list(self.artifact_types),
            "notes": list(self.notes),
            "default_model": self.default_model,
            "supported_models": list(self.supported_models),
            "request_policy": self.request_policy.to_dict() if self.request_policy else None,
        }


@dataclass(slots=True)
class ProviderEvent:
    """Structured provider event emitted during observable operations."""

    provider: str
    operation: str
    phase: str
    attempt: int = 1
    max_attempts: int = 1
    method: str | None = None
    target: str | None = None
    status_code: int | None = None
    duration_ms: float | None = None
    message: str = ""
    metadata: JSONDict = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.provider, str) or not self.provider.strip():
            raise WorldForgeError("ProviderEvent provider must be a non-empty string.")
        if not isinstance(self.operation, str) or not self.operation.strip():
            raise WorldForgeError("ProviderEvent operation must be a non-empty string.")
        if not isinstance(self.phase, str) or not self.phase.strip():
            raise WorldForgeError("ProviderEvent phase must be a non-empty string.")
        if isinstance(self.attempt, bool) or not isinstance(self.attempt, int) or self.attempt < 1:
            raise WorldForgeError("ProviderEvent attempt must be greater than or equal to 1.")
        if (
            isinstance(self.max_attempts, bool)
            or not isinstance(self.max_attempts, int)
            or self.max_attempts < self.attempt
        ):
            raise WorldForgeError(
                "ProviderEvent max_attempts must be greater than or equal to attempt."
            )
        if self.status_code is not None and (
            isinstance(self.status_code, bool)
            or not isinstance(self.status_code, int)
            or self.status_code < 100
            or self.status_code > 599
        ):
            raise WorldForgeError("ProviderEvent status_code must be a valid HTTP status code.")
        if self.duration_ms is not None:
            self.duration_ms = require_finite_number(
                self.duration_ms,
                name="ProviderEvent duration_ms",
            )
        if self.duration_ms is not None and self.duration_ms < 0.0:
            raise WorldForgeError("ProviderEvent duration_ms must be non-negative when set.")
        if not isinstance(self.metadata, dict):
            raise WorldForgeError("ProviderEvent metadata must be a JSON object.")
        self.provider = self.provider.strip()
        self.operation = self.operation.strip()
        self.phase = self.phase.strip()
        self.metadata = dict(self.metadata)

    def to_dict(self) -> JSONDict:
        return {
            "provider": self.provider,
            "operation": self.operation,
            "phase": self.phase,
            "attempt": self.attempt,
            "max_attempts": self.max_attempts,
            "method": self.method,
            "target": self.target,
            "status_code": self.status_code,
            "duration_ms": self.duration_ms,
            "message": self.message,
            "metadata": dict(self.metadata),
        }


@dataclass(slots=True)
class ProviderHealth:
    """Health information for a provider."""

    name: str
    healthy: bool
    latency_ms: float
    details: str = ""

    def to_dict(self) -> JSONDict:
        return {
            "name": self.name,
            "healthy": self.healthy,
            "latency_ms": self.latency_ms,
            "details": self.details,
        }


@dataclass(slots=True)
class ProviderDoctorStatus:
    """Diagnostic snapshot for a provider in the active environment."""

    registered: bool
    profile: ProviderProfile
    health: ProviderHealth

    def to_dict(self) -> JSONDict:
        return {
            "name": self.profile.name,
            "registered": self.registered,
            "profile": self.profile.to_dict(),
            "health": self.health.to_dict(),
        }


@dataclass(slots=True)
class DoctorReport:
    """Environment diagnostics for the current WorldForge install."""

    state_dir: str
    world_count: int
    providers: list[ProviderDoctorStatus]
    issues: list[str] = field(default_factory=list)

    @property
    def provider_count(self) -> int:
        return len(self.providers)

    @property
    def healthy_provider_count(self) -> int:
        return sum(1 for provider in self.providers if provider.health.healthy)

    @property
    def registered_provider_count(self) -> int:
        return sum(1 for provider in self.providers if provider.registered)

    def to_dict(self) -> JSONDict:
        return {
            "state_dir": self.state_dir,
            "world_count": self.world_count,
            "provider_count": self.provider_count,
            "healthy_provider_count": self.healthy_provider_count,
            "registered_provider_count": self.registered_provider_count,
            "providers": [provider.to_dict() for provider in self.providers],
            "issues": list(self.issues),
        }

    def to_json(self) -> str:
        return dump_json(self.to_dict())


@dataclass(slots=True)
class VideoClip:
    """Generated or transformed video content."""

    frames: list[bytes]
    fps: float
    resolution: tuple[int, int]
    duration_seconds: float
    metadata: JSONDict = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not all(isinstance(frame, bytes) for frame in self.frames):
            raise WorldForgeError("VideoClip frames must be bytes.")
        self.fps = require_finite_number(self.fps, name="VideoClip fps")
        if self.fps <= 0.0:
            raise WorldForgeError("VideoClip fps must be greater than 0.")
        try:
            width, height = self.resolution
        except (TypeError, ValueError) as exc:
            raise WorldForgeError("VideoClip resolution must contain width and height.") from exc
        if (
            isinstance(width, bool)
            or isinstance(height, bool)
            or not isinstance(width, int)
            or not isinstance(height, int)
            or width <= 0
            or height <= 0
        ):
            raise WorldForgeError("VideoClip resolution values must be greater than 0.")
        self.resolution = (width, height)
        self.duration_seconds = require_finite_number(
            self.duration_seconds,
            name="VideoClip duration_seconds",
        )
        if self.duration_seconds < 0.0:
            raise WorldForgeError("VideoClip duration_seconds must be non-negative.")
        if not isinstance(self.metadata, dict):
            raise WorldForgeError("VideoClip metadata must be a JSON object.")
        self.frames = list(self.frames)
        self.metadata = dict(self.metadata)

    @property
    def frame_count(self) -> int:
        return len(self.frames)

    def blob(self) -> bytes:
        """Return the clip as a single binary blob when possible."""

        if self.frame_count == 1:
            return self.frames[0]
        return b"".join(self.frames)

    def content_type(self) -> str:
        """Return the best-known content type for the clip."""

        return str(self.metadata.get("content_type", "application/octet-stream"))

    def save(self, path: str | Path) -> Path:
        """Persist the clip bytes to disk and return the resolved path."""

        target = Path(path).expanduser().resolve()
        ensure_directory(target.parent)
        target.write_bytes(self.blob())
        return target

    @classmethod
    def from_file(
        cls,
        path: str | Path,
        *,
        fps: float = 24.0,
        resolution: tuple[int, int] = (1280, 720),
        duration_seconds: float = 0.0,
        metadata: JSONDict | None = None,
    ) -> VideoClip:
        """Build a clip from a local file for transfer-style APIs."""

        source = Path(path).expanduser().resolve()
        if not source.exists():
            raise WorldForgeError(f"Video clip source does not exist: {source}")
        if not source.is_file():
            raise WorldForgeError(f"Video clip source is not a file: {source}")
        content_type = guess_type(source.name)[0] or "application/octet-stream"
        merged_metadata = dict(metadata or {})
        merged_metadata.setdefault("content_type", content_type)
        merged_metadata.setdefault("source_path", str(source))
        return cls(
            frames=[source.read_bytes()],
            fps=fps,
            resolution=resolution,
            duration_seconds=duration_seconds,
            metadata=merged_metadata,
        )

    def to_dict(self) -> JSONDict:
        return {
            "frame_count": self.frame_count,
            "fps": self.fps,
            "resolution": list(self.resolution),
            "duration_seconds": self.duration_seconds,
            "content_type": self.content_type(),
            "metadata": dict(self.metadata),
        }


@dataclass(slots=True)
class ReasoningResult:
    """A provider answer about a scene or prompt."""

    provider: str
    answer: str
    confidence: float
    evidence: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not isinstance(self.provider, str) or not self.provider.strip():
            raise WorldForgeError("ReasoningResult provider must be a non-empty string.")
        if not isinstance(self.answer, str):
            raise WorldForgeError("ReasoningResult answer must be a string.")
        self.confidence = require_probability(
            self.confidence,
            name="ReasoningResult confidence",
        )
        if not isinstance(self.evidence, list) or not all(
            isinstance(item, str) for item in self.evidence
        ):
            raise WorldForgeError("ReasoningResult evidence must be a list of strings.")
        self.provider = self.provider.strip()
        self.evidence = list(self.evidence)


@dataclass(slots=True)
class EmbeddingResult:
    """Embedding output from a provider."""

    provider: str
    model: str
    vector: list[float]

    def __post_init__(self) -> None:
        if not isinstance(self.provider, str) or not self.provider.strip():
            raise WorldForgeError("EmbeddingResult provider must be a non-empty string.")
        if not isinstance(self.model, str) or not self.model.strip():
            raise WorldForgeError("EmbeddingResult model must be a non-empty string.")
        if not isinstance(self.vector, list) or not self.vector:
            raise WorldForgeError("EmbeddingResult vector must be a non-empty list.")
        self.provider = self.provider.strip()
        self.model = self.model.strip()
        self.vector = [
            require_finite_number(value, name="EmbeddingResult vector value")
            for value in self.vector
        ]

    @property
    def shape(self) -> list[int]:
        return [len(self.vector)]


@dataclass(slots=True)
class HistoryEntry:
    """A recorded world snapshot."""

    step: int
    state: JSONDict
    summary: str
    action_json: str | None = None

    def to_dict(self) -> JSONDict:
        return {
            "step": self.step,
            "state": self.state,
            "summary": self.summary,
            "action_json": self.action_json,
        }

    @classmethod
    def from_dict(cls, payload: JSONDict) -> HistoryEntry:
        return cls(
            step=int(payload["step"]),
            state=dict(payload["state"]),
            summary=str(payload.get("summary", "")),
            action_json=payload.get("action_json"),
        )

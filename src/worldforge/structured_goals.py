"""Structured planning goal data contracts."""

from __future__ import annotations

import json
from dataclasses import dataclass

from worldforge._model_utils import JSONDict, WorldForgeError, dump_json, require_finite_number
from worldforge.scene_models import Position


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
        self._require_supported_kind()
        self._require_positive_tolerance()
        self._validate_by_kind()

    def _require_supported_kind(self) -> None:
        if self.kind not in {"object_at", "spawn_object", "object_near", "swap_objects"}:
            raise WorldForgeError(
                "StructuredGoal kind must be one of: object_at, spawn_object, "
                "object_near, swap_objects."
            )

    def _require_positive_tolerance(self) -> None:
        if self.kind in {"object_at", "object_near", "swap_objects"} and self.tolerance <= 0.0:
            raise WorldForgeError(f"StructuredGoal {self.kind} tolerance must be greater than 0.")

    def _validate_by_kind(self) -> None:
        validators = {
            "object_at": self._validate_object_at_goal,
            "spawn_object": self._validate_spawn_object_goal,
            "object_near": self._validate_object_near_goal,
            "swap_objects": self._validate_swap_objects_goal,
        }
        validators[self.kind]()

    def _validate_object_at_goal(self) -> None:
        if self.position is None:
            raise WorldForgeError("StructuredGoal object_at goals require a target position.")
        self._require_primary_selector("object_at")
        self._reject_reference_selector("object_at")
        self._reject_offset("object_at")

    def _validate_spawn_object_goal(self) -> None:
        if not self.object_name:
            raise WorldForgeError("StructuredGoal spawn_object goals require object_name.")
        if self.object_id is not None:
            raise WorldForgeError("StructuredGoal spawn_object goals do not accept object_id.")
        self._reject_reference_selector("spawn_object")
        self._reject_offset("spawn_object")

    def _validate_object_near_goal(self) -> None:
        self._require_primary_selector("object_near")
        self._require_reference_selector("object_near")
        if self.position is not None:
            raise WorldForgeError("StructuredGoal object_near goals do not accept position.")
        if self.offset is None:
            object.__setattr__(self, "offset", Position(0.1, 0.0, 0.0))
        self._require_distinct_selectors("object_near")

    def _validate_swap_objects_goal(self) -> None:
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
            return cls._from_kind_payload(payload)

        condition_name, condition_payload = cls._legacy_condition_payload(payload)
        return cls._from_legacy_condition(condition_name, condition_payload)

    @classmethod
    def _from_kind_payload(cls, payload: JSONDict) -> StructuredGoal:
        object_id, object_name = cls._selector_fields(payload.get("object"), field_name="object")
        reference_object_id, reference_object_name = cls._selector_fields(
            payload.get("reference_object"),
            field_name="reference_object",
        )
        return cls(
            kind=str(payload["kind"]),
            object_id=object_id,
            object_name=object_name,
            position=cls._optional_position(payload.get("position")),
            reference_object_id=reference_object_id,
            reference_object_name=reference_object_name,
            offset=cls._optional_position(payload.get("offset")),
            tolerance=payload.get("tolerance", 0.05),
        )

    @staticmethod
    def _optional_position(payload: object) -> Position | None:
        return Position.from_dict(payload) if isinstance(payload, dict) else None

    @staticmethod
    def _legacy_condition_payload(payload: JSONDict) -> tuple[str, JSONDict]:
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
        return condition_name, condition_payload

    @classmethod
    def _from_legacy_condition(
        cls,
        condition_name: str,
        condition_payload: JSONDict,
    ) -> StructuredGoal:
        if condition_name == "ObjectAt":
            return cls._from_legacy_object_at(condition_payload)
        if condition_name == "SpawnObject":
            return cls._from_legacy_spawn_object(condition_payload)
        if condition_name == "ObjectNear":
            return cls._from_legacy_object_near(condition_payload)
        if condition_name == "SwapObjects":
            return cls._from_legacy_swap_objects(condition_payload)
        raise WorldForgeError(f"Unsupported legacy structured goal condition '{condition_name}'.")

    @classmethod
    def _from_legacy_object_at(cls, payload: JSONDict) -> StructuredGoal:
        position_payload = payload.get("position")
        if not isinstance(position_payload, dict):
            raise WorldForgeError("Legacy ObjectAt goals require a position object.")
        object_value = payload.get("object")
        object_name = payload.get("object_name")
        return cls.object_at(
            object_id=str(object_value) if object_value is not None else None,
            object_name=str(object_name) if object_name is not None else None,
            position=Position.from_dict(position_payload),
            tolerance=payload.get("tolerance", 0.05),
        )

    @classmethod
    def _from_legacy_spawn_object(cls, payload: JSONDict) -> StructuredGoal:
        object_name = cls._legacy_spawn_object_name(payload)
        if object_name is None:
            raise WorldForgeError("Legacy SpawnObject goals require object.name or name.")
        return cls.spawn_object(
            str(object_name),
            position=cls._optional_position(payload.get("position")),
        )

    @staticmethod
    def _legacy_spawn_object_name(payload: JSONDict) -> object | None:
        object_payload = payload.get("object", {})
        if isinstance(object_payload, str):
            return object_payload
        if isinstance(object_payload, dict):
            return object_payload.get("name")
        return payload.get("name")

    @classmethod
    def _from_legacy_object_near(cls, payload: JSONDict) -> StructuredGoal:
        object_id, object_name = cls._selector_fields(
            payload.get("object"),
            field_name="object",
        )
        reference_object_id, reference_object_name = cls._selector_fields(
            payload.get("reference_object", payload.get("anchor")),
            field_name="reference_object",
        )
        return cls.object_near(
            object_id=object_id,
            object_name=object_name,
            reference_object_id=reference_object_id,
            reference_object_name=reference_object_name,
            offset=cls._optional_position(payload.get("offset")),
            tolerance=payload.get("tolerance", 0.05),
        )

    @classmethod
    def _from_legacy_swap_objects(cls, payload: JSONDict) -> StructuredGoal:
        object_id, object_name = cls._selector_fields(
            payload.get("object", payload.get("first_object")),
            field_name="object",
        )
        reference_object_id, reference_object_name = cls._selector_fields(
            payload.get("reference_object", payload.get("second_object")),
            field_name="reference_object",
        )
        return cls.swap_objects(
            object_id=object_id,
            object_name=object_name,
            reference_object_id=reference_object_id,
            reference_object_name=reference_object_name,
            tolerance=payload.get("tolerance", 0.05),
        )

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
            offset = self.offset
            if offset is None:
                raise WorldForgeError(
                    "StructuredGoal object_near must have a non-null offset (enforced in "
                    "__post_init__)."
                )
            return (
                f"move {target} near {reference} "
                f"with offset ({offset.x:.2f}, {offset.y:.2f}, {offset.z:.2f})"
            )
        if self.kind == "swap_objects":
            reference = self._selector_label(
                self.reference_object_id,
                self.reference_object_name,
                fallback="reference object",
            )
            return f"swap {target} with {reference}"
        position = self.position
        if position is None:
            raise WorldForgeError(
                f"StructuredGoal {self.kind!r} must have a non-null position (enforced in "
                "__post_init__)."
            )
        return f"move {target} to ({position.x:.2f}, {position.y:.2f}, {position.z:.2f})"


__all__ = ["StructuredGoal"]

"""Private validated result objects returned by framework operations."""

from __future__ import annotations

from collections.abc import Sequence
from copy import deepcopy
from dataclasses import dataclass
from typing import TYPE_CHECKING

from worldforge._state import require_non_empty_text, validate_world_state_payload
from worldforge.models import (
    Action,
    JSONDict,
    WorldForgeError,
    dump_json,
    require_finite_number,
    require_probability,
)

if TYPE_CHECKING:
    from worldforge.framework import World, WorldForge


def _clone_state(state: JSONDict) -> JSONDict:
    return deepcopy(state)


def _is_sequence_of_actions(value: object) -> bool:
    return isinstance(value, Sequence) and not isinstance(value, str | bytes)


def _plan_actions(actions: Sequence[Action]) -> list[Action]:
    if not _is_sequence_of_actions(actions) or not all(
        isinstance(action, Action) for action in actions
    ):
        raise WorldForgeError("Plan actions must be a sequence of Action instances.")
    return list(actions)


def _require_plan_predicted_states_sequence(value: object) -> Sequence[object]:
    if not isinstance(value, Sequence) or isinstance(value, str | bytes):
        raise WorldForgeError("Plan predicted_states must be a sequence of JSON objects.")
    return value


def _plan_predicted_state(state: object, *, index: int) -> JSONDict:
    if not isinstance(state, dict):
        raise WorldForgeError(f"Plan predicted_states[{index}] must be a JSON object.")
    cloned_state = _clone_state(state)
    validate_world_state_payload(cloned_state, context=f"Plan predicted_states[{index}]")
    return cloned_state


def _plan_predicted_states(predicted_states: Sequence[JSONDict]) -> list[JSONDict]:
    return [
        _plan_predicted_state(state, index=index)
        for index, state in enumerate(_require_plan_predicted_states_sequence(predicted_states))
    ]


def _optional_plan_json_object(value: JSONDict | None, *, name: str) -> JSONDict | None:
    if value is None:
        return None
    if not isinstance(value, dict):
        raise WorldForgeError(f"Plan {name} must be a JSON object when provided.")
    return _clone_state(value)


def _plan_metadata(metadata: JSONDict | None) -> JSONDict:
    if metadata is not None and not isinstance(metadata, dict):
        raise WorldForgeError("Plan metadata must be a JSON object when provided.")
    return _clone_state(metadata or {})


def _prediction_frames(frames: object) -> list[bytes]:
    if not isinstance(frames, list) or not all(isinstance(frame, bytes) for frame in frames):
        raise WorldForgeError("Prediction frames must be a list of bytes.")
    return list(frames)


def _prediction_metadata(metadata: object) -> JSONDict:
    if not isinstance(metadata, dict):
        raise WorldForgeError("Prediction metadata must be a JSON object.")
    dump_json(metadata)
    return _clone_state(metadata)


def _prediction_world_state(world_state: object) -> JSONDict:
    if not isinstance(world_state, dict):
        raise WorldForgeError("Prediction world_state must be a JSON object.")
    validate_world_state_payload(world_state, context="Prediction world_state")
    dump_json(world_state)
    return _clone_state(world_state)


def _prediction_latency_ms(latency_ms: float) -> float:
    latency = require_finite_number(latency_ms, name="Prediction latency_ms")
    if latency < 0.0:
        raise WorldForgeError("Prediction latency_ms must be non-negative.")
    return latency


@dataclass(slots=True)
class Prediction:
    """Result of a world prediction."""

    provider: str
    confidence: float
    physics_score: float
    frames: list[bytes]
    world_state: JSONDict
    metadata: JSONDict
    latency_ms: float
    _forge: WorldForge

    def __post_init__(self) -> None:
        self.provider = require_non_empty_text(self.provider, name="Prediction provider")
        self.confidence = require_probability(self.confidence, name="Prediction confidence")
        self.physics_score = require_probability(
            self.physics_score,
            name="Prediction physics_score",
        )
        self.frames = _prediction_frames(self.frames)
        self.metadata = _prediction_metadata(self.metadata)
        self.world_state = _prediction_world_state(self.world_state)
        self.latency_ms = _prediction_latency_ms(self.latency_ms)

    def output_world(self) -> World:
        """Return a fresh world hydrated from this prediction's snapshot."""

        from worldforge.framework import World

        return World.from_state(self._forge, _clone_state(self.world_state))


class Comparison:
    """Result of comparing predictions from multiple providers for the same input."""

    def __init__(self, predictions: Sequence[Prediction]) -> None:
        self.results = list(predictions)

    @property
    def prediction_count(self) -> int:
        return len(self.results)

    def best_prediction(self) -> Prediction:
        if not self.results:
            raise ValueError("Comparison has no predictions.")
        return max(self.results, key=lambda item: (item.physics_score, item.confidence))

    def to_markdown(self) -> str:
        lines = [
            "# WorldForge Comparison",
            "",
            "| provider | physics_score | confidence | latency_ms |",
            "| --- | ---: | ---: | ---: |",
        ]
        lines.extend(
            (
                f"| {result.provider} | {result.physics_score:.2f} | "
                f"{result.confidence:.2f} | {result.latency_ms:.2f} |"
            )
            for result in self.results
        )
        return "\n".join(lines)

    def to_csv(self) -> str:
        rows = ["provider,physics_score,confidence,latency_ms"]
        rows.extend(
            (
                f"{result.provider},{result.physics_score:.4f},"
                f"{result.confidence:.4f},{result.latency_ms:.4f}"
            )
            for result in self.results
        )
        return "\n".join(rows)

    def to_json(self) -> str:
        return dump_json(
            {
                "predictions": [
                    {
                        "provider": result.provider,
                        "physics_score": result.physics_score,
                        "confidence": result.confidence,
                        "latency_ms": result.latency_ms,
                        "metadata": result.metadata,
                    }
                    for result in self.results
                ]
            }
        )

    def artifacts(self) -> dict[str, str]:
        return {
            "json": self.to_json(),
            "markdown": self.to_markdown(),
            "csv": self.to_csv(),
        }


class Plan:
    """Deterministic multi-step execution plan."""

    def __init__(
        self,
        *,
        goal: str,
        planner: str,
        provider: str,
        actions: Sequence[Action],
        predicted_states: Sequence[JSONDict],
        success_probability: float,
        goal_spec: JSONDict | None = None,
        metadata: JSONDict | None = None,
    ) -> None:
        self.goal = require_non_empty_text(goal, name="Plan goal")
        self.planner = require_non_empty_text(planner, name="Plan planner")
        self.provider = require_non_empty_text(provider, name="Plan provider")
        self.actions = _plan_actions(actions)
        self.predicted_states = _plan_predicted_states(predicted_states)
        self.success_probability = require_probability(
            success_probability,
            name="Plan success_probability",
        )
        self.goal_spec = _optional_plan_json_object(goal_spec, name="goal_spec")
        self.metadata = _plan_metadata(metadata)
        dump_json(self.to_dict())

    @property
    def action_count(self) -> int:
        return len(self.actions)

    def to_dict(self) -> JSONDict:
        return {
            "goal": self.goal,
            "goal_spec": self.goal_spec,
            "planner": self.planner,
            "provider": self.provider,
            "actions": [action.to_dict() for action in self.actions],
            "action_count": self.action_count,
            "success_probability": self.success_probability,
            "predicted_states": self.predicted_states,
            "metadata": self.metadata,
        }

    def to_json(self) -> str:
        return dump_json(self.to_dict())


class PlanExecution:
    """Result of applying a :class:`Plan` against a :class:`World`."""

    def __init__(self, final_world: World, actions_applied: Sequence[Action]) -> None:
        self._final_world = final_world
        self.actions_applied = list(actions_applied)

    def final_world(self) -> World:
        return self._final_world

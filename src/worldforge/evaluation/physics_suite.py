"""Deterministic physics-style evaluation suite over the forge predict surface."""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, ClassVar

from worldforge.evaluation.metrics import position_distance as _distance
from worldforge.evaluation.results import EvaluationResult, EvaluationScenario
from worldforge.evaluation.results import clamp_score as _clamp_score
from worldforge.evaluation.suite_base import EvaluationSuite
from worldforge.models import Action, JSONDict, Position, SceneObject, WorldForgeError

if TYPE_CHECKING:
    from worldforge.framework import WorldForge

_CUBE_START = Position(0.0, 0.5, 0.0)


class PhysicsEvaluationSuite(EvaluationSuite):
    """Built-in suite for deterministic physics-style checks.

    Each scenario rolls the bound provider's ``predict`` surface forward over a plain
    ``world_state`` dict (no symbolic :class:`~worldforge.framework.World`) and asserts the
    returned payload satisfies a deterministic contract.
    """

    def __init__(self) -> None:
        super().__init__(
            "Physics Evaluation Suite",
            scenarios=[
                EvaluationScenario(
                    "object-stability",
                    "Checks that repeated predictions over the same state are deterministic.",
                    required_capabilities=("predict",),
                ),
                EvaluationScenario(
                    "action-response",
                    "Checks that a move action shifts the object toward the requested target.",
                    required_capabilities=("predict",),
                ),
            ],
            suite_id="physics",
        )

    def _seed_objects(self) -> tuple[SceneObject, ...]:
        return (self._seed_object("cube", _CUBE_START),)

    @staticmethod
    def _primary_object_id(state: JSONDict) -> str:
        objects = state.get("scene", {}).get("objects", {})
        if not objects:  # pragma: no cover - seed guard
            raise WorldForgeError("Physics evaluation seed state is missing the primary object.")
        return next(iter(objects))

    @staticmethod
    def _object_position(state: JSONDict, object_id: str) -> Position:
        scene_object = state.get("scene", {}).get("objects", {}).get(object_id)
        if not isinstance(scene_object, dict):  # pragma: no cover - prediction guard
            raise WorldForgeError("Physics evaluation lost the primary object during prediction.")
        return Position.from_dict(scene_object["pose"]["position"])

    def evaluate_scenario(
        self,
        scenario: EvaluationScenario,
        provider: str,
        *,
        forge: WorldForge,
        index: int,
    ) -> EvaluationResult:
        handler = self._SCENARIO_HANDLERS.get(scenario.name)
        if handler is None:
            return super().evaluate_scenario(
                scenario,
                provider,
                forge=forge,
                index=index,
            )
        return handler(self, scenario, provider, forge=forge, index=index)

    def _evaluate_object_stability(
        self,
        scenario: EvaluationScenario,
        provider: str,
        *,
        forge: WorldForge,
        index: int,
    ) -> EvaluationResult:
        seed = self._seed_world_state()
        object_id = self._primary_object_id(seed)
        action = Action.move_to(_CUBE_START.x, _CUBE_START.y, _CUBE_START.z, object_id=object_id)
        first = forge.predict(seed, action, steps=1, provider=provider)
        second = forge.predict(seed, action, steps=1, provider=provider)
        first_position = self._object_position(first.state, object_id)
        second_position = self._object_position(second.state, object_id)
        determinism_drift = _distance(first_position, second_position)
        deterministic = determinism_drift <= 1e-9
        passed = deterministic and first.physics_score >= 0.7
        score = _clamp_score(
            ((first.physics_score + first.confidence) / 2) - min(0.25, determinism_drift)
        )
        return EvaluationResult(
            suite_id=self.suite_id,
            suite=self.name,
            scenario=scenario.name,
            provider=provider,
            score=score,
            passed=passed,
            metrics={
                "physics_score": first.physics_score,
                "confidence": first.confidence,
                "determinism_drift": determinism_drift,
                "deterministic": deterministic,
            },
        )

    def _evaluate_action_response(
        self,
        scenario: EvaluationScenario,
        provider: str,
        *,
        forge: WorldForge,
        index: int,
    ) -> EvaluationResult:
        seed = self._seed_world_state()
        object_id = self._primary_object_id(seed)
        start = self._object_position(seed, object_id)
        target = Position(start.x + 0.35, start.y, start.z)
        prediction = forge.predict(
            seed,
            Action.move_to(target.x, target.y, target.z, object_id=object_id),
            steps=2,
            provider=provider,
        )
        final = self._object_position(prediction.state, object_id)
        target_error = _distance(target, final)
        moved_distance = _distance(start, final)
        passed = target_error <= 0.05 and moved_distance >= 0.3
        score = _clamp_score(
            ((prediction.physics_score + prediction.confidence) / 2)
            + min(0.2, moved_distance / 2)
            - min(0.3, target_error)
        )
        return EvaluationResult(
            suite_id=self.suite_id,
            suite=self.name,
            scenario=scenario.name,
            provider=provider,
            score=score,
            passed=passed,
            metrics={
                "physics_score": prediction.physics_score,
                "confidence": prediction.confidence,
                "moved_distance": moved_distance,
                "target_error": target_error,
            },
        )

    _SCENARIO_HANDLERS: ClassVar[dict[str, Callable[..., EvaluationResult]]] = {
        "object-stability": _evaluate_object_stability,
        "action-response": _evaluate_action_response,
    }


__all__ = ["PhysicsEvaluationSuite"]

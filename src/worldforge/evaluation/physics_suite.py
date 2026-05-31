"""Deterministic physics-style evaluation suite."""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, ClassVar

from worldforge.evaluation.metrics import position_distance as _distance
from worldforge.evaluation.results import EvaluationResult, EvaluationScenario
from worldforge.evaluation.results import clamp_score as _clamp_score
from worldforge.evaluation.suite_base import EvaluationSuite
from worldforge.evaluation.suite_fixtures import seed_object
from worldforge.models import Action, Position, WorldForgeError

if TYPE_CHECKING:
    from worldforge.framework import World, WorldForge


class PhysicsEvaluationSuite(EvaluationSuite):
    """Built-in suite for deterministic physics-style checks."""

    def __init__(self) -> None:
        super().__init__(
            "Physics Evaluation Suite",
            scenarios=[
                EvaluationScenario(
                    "object-stability",
                    "Checks that an object remains stable under a no-op move.",
                    required_capabilities=("predict",),
                ),
                EvaluationScenario(
                    "action-response",
                    "Checks that a move action reaches the target pose.",
                    required_capabilities=("predict",),
                ),
            ],
            suite_id="physics",
        )

    def _build_world(self, provider: str, *, forge: WorldForge) -> World:
        world = super()._build_world(provider, forge=forge)
        seed_object(world, "cube", Position(0.0, 0.5, 0.0))
        return world

    def evaluate_scenario(
        self,
        scenario: EvaluationScenario,
        provider: str,
        *,
        world: World,
        forge: WorldForge,
        index: int,
    ) -> EvaluationResult:
        handler = self._SCENARIO_HANDLERS.get(scenario.name)
        if handler is None:
            return super().evaluate_scenario(
                scenario,
                provider,
                world=world,
                forge=forge,
                index=index,
            )
        return handler(self, scenario, provider, world=world, forge=forge, index=index)

    def _evaluate_object_stability(
        self,
        scenario: EvaluationScenario,
        provider: str,
        *,
        world: World,
        forge: WorldForge,
        index: int,
    ) -> EvaluationResult:
        primary = seed_object(world, "cube", Position(0.0, 0.5, 0.0))
        start = primary.position
        prediction = world.predict(
            Action.move_to(start.x, start.y, start.z),
            steps=1,
            provider=provider,
        )
        current = world.get_object_by_id(primary.id)
        if current is None:  # pragma: no cover - world state corruption guard
            raise WorldForgeError("Evaluation lost the primary object during physics run.")
        displacement = _distance(start, current.position)
        passed = displacement <= 0.01 and prediction.physics_score >= 0.7
        score = _clamp_score(
            ((prediction.physics_score + prediction.confidence) / 2) - min(0.25, displacement)
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
                "displacement": displacement,
                "step": world.step,
            },
        )

    def _evaluate_action_response(
        self,
        scenario: EvaluationScenario,
        provider: str,
        *,
        world: World,
        forge: WorldForge,
        index: int,
    ) -> EvaluationResult:
        primary = seed_object(world, "cube", Position(0.0, 0.5, 0.0))
        start = primary.position
        target = Position(start.x + 0.35, start.y, start.z)
        prediction = world.predict(
            Action.move_to(target.x, target.y, target.z),
            steps=2,
            provider=provider,
        )
        current = world.get_object_by_id(primary.id)
        if current is None:  # pragma: no cover - world state corruption guard
            raise WorldForgeError("Evaluation lost the primary object during physics run.")
        target_error = _distance(target, current.position)
        moved_distance = _distance(start, current.position)
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
                "step": world.step,
            },
        )

    _SCENARIO_HANDLERS: ClassVar[dict[str, Callable[..., EvaluationResult]]] = {
        "object-stability": _evaluate_object_stability,
        "action-response": _evaluate_action_response,
    }


__all__ = ["PhysicsEvaluationSuite"]

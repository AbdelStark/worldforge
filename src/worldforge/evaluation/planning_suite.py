"""Deterministic planning and execution evaluation suite."""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, ClassVar

from worldforge.evaluation.metrics import position_distance as _distance
from worldforge.evaluation.results import EvaluationResult, EvaluationScenario
from worldforge.evaluation.results import clamp_score as _clamp_score
from worldforge.evaluation.suite_base import EvaluationSuite
from worldforge.evaluation.suite_fixtures import seed_object
from worldforge.models import Position, StructuredGoal, WorldForgeError, average

if TYPE_CHECKING:
    from worldforge.framework import World, WorldForge


class PlanningEvaluationSuite(EvaluationSuite):
    """Built-in suite for heuristic planning and execution checks."""

    def __init__(self) -> None:
        super().__init__(
            "Planning Evaluation Suite",
            scenarios=[
                EvaluationScenario(
                    "object-relocation",
                    "Plans and executes a relocation objective for a seeded object.",
                    required_capabilities=("predict",),
                ),
                EvaluationScenario(
                    "object-neighbor-placement",
                    "Places one object near another using a typed relational goal.",
                    required_capabilities=("predict",),
                ),
                EvaluationScenario(
                    "object-swap",
                    "Swaps the positions of two seeded objects using a typed relational goal.",
                    required_capabilities=("predict",),
                ),
                EvaluationScenario(
                    "object-spawn",
                    "Plans and executes a simple spawn goal.",
                    required_capabilities=("predict",),
                ),
            ],
            suite_id="planning",
        )

    def _build_world(self, provider: str, *, forge: WorldForge) -> World:
        world = super()._build_world(provider, forge=forge)
        seed_object(world, "cube", Position(0.0, 0.5, 0.0))
        seed_object(world, "mug", Position(0.3, 0.8, 0.0))
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

    def _evaluate_object_relocation(
        self,
        scenario: EvaluationScenario,
        provider: str,
        *,
        world: World,
        forge: WorldForge,
        index: int,
    ) -> EvaluationResult:
        primary = seed_object(world, "cube", Position(0.0, 0.5, 0.0))
        seed_object(world, "mug", Position(0.3, 0.8, 0.0))
        plan = world.plan(
            goal_spec=StructuredGoal.object_at(
                object_id=primary.id,
                object_name=primary.name,
                position=Position(
                    primary.position.x + 0.35,
                    primary.position.y,
                    primary.position.z,
                ),
                tolerance=0.05,
            ),
            max_steps=4,
            provider=provider,
        )
        execution = world.execute_plan(plan, provider)
        final_world = execution.final_world()
        final_object = final_world.get_object_by_id(primary.id)
        if final_object is None:  # pragma: no cover - world state corruption guard
            raise WorldForgeError("Evaluation lost the primary object during plan execution.")
        moved_distance = final_object.position.x - primary.position.x
        passed = plan.action_count >= 1 and moved_distance >= 0.25
        score = _clamp_score((plan.success_probability + min(1.0, moved_distance)) / 2)
        return EvaluationResult(
            suite_id=self.suite_id,
            suite=self.name,
            scenario=scenario.name,
            provider=provider,
            score=score,
            passed=passed,
            metrics={
                "action_count": plan.action_count,
                "success_probability": plan.success_probability,
                "moved_distance": moved_distance,
                "final_step": final_world.step,
            },
        )

    def _evaluate_object_neighbor_placement(
        self,
        scenario: EvaluationScenario,
        provider: str,
        *,
        world: World,
        forge: WorldForge,
        index: int,
    ) -> EvaluationResult:
        primary = seed_object(world, "cube", Position(0.0, 0.5, 0.0))
        reference = seed_object(world, "mug", Position(0.3, 0.8, 0.0))
        offset = Position(0.15, 0.0, 0.0)
        target = Position(
            reference.position.x + offset.x,
            reference.position.y + offset.y,
            reference.position.z + offset.z,
        )
        plan = world.plan(
            goal_spec=StructuredGoal.object_near(
                object_id=primary.id,
                object_name=primary.name,
                reference_object_id=reference.id,
                reference_object_name=reference.name,
                offset=offset,
                tolerance=0.05,
            ),
            max_steps=4,
            provider=provider,
        )
        execution = world.execute_plan(plan, provider)
        final_world = execution.final_world()
        final_primary = final_world.get_object_by_id(primary.id)
        final_reference = final_world.get_object_by_id(reference.id)
        if final_primary is None or final_reference is None:  # pragma: no cover
            raise WorldForgeError("Evaluation lost an object during relational plan execution.")
        target_error = _distance(target, final_primary.position)
        reference_drift = _distance(reference.position, final_reference.position)
        passed = plan.action_count >= 1 and target_error <= 0.05 and reference_drift <= 0.01
        score = average(
            [
                plan.success_probability,
                _clamp_score(1.0 - min(1.0, target_error / 0.25)),
                _clamp_score(1.0 - min(1.0, reference_drift / 0.25)),
            ]
        )
        return EvaluationResult(
            suite_id=self.suite_id,
            suite=self.name,
            scenario=scenario.name,
            provider=provider,
            score=score,
            passed=passed,
            metrics={
                "action_count": plan.action_count,
                "success_probability": plan.success_probability,
                "target_error": target_error,
                "reference_drift": reference_drift,
                "final_step": final_world.step,
            },
        )

    def _evaluate_object_swap(
        self,
        scenario: EvaluationScenario,
        provider: str,
        *,
        world: World,
        forge: WorldForge,
        index: int,
    ) -> EvaluationResult:
        primary = seed_object(world, "cube", Position(0.0, 0.5, 0.0))
        reference = seed_object(world, "mug", Position(0.3, 0.8, 0.0))
        plan = world.plan(
            goal_spec=StructuredGoal.swap_objects(
                object_id=primary.id,
                object_name=primary.name,
                reference_object_id=reference.id,
                reference_object_name=reference.name,
                tolerance=0.05,
            ),
            max_steps=4,
            provider=provider,
        )
        execution = world.execute_plan(plan, provider)
        final_world = execution.final_world()
        final_primary = final_world.get_object_by_id(primary.id)
        final_reference = final_world.get_object_by_id(reference.id)
        if final_primary is None or final_reference is None:  # pragma: no cover
            raise WorldForgeError("Evaluation lost an object during swap plan execution.")
        primary_target_error = _distance(reference.position, final_primary.position)
        reference_target_error = _distance(primary.position, final_reference.position)
        passed = (
            plan.action_count == 2
            and primary_target_error <= 0.05
            and reference_target_error <= 0.05
        )
        score = average(
            [
                plan.success_probability,
                _clamp_score(1.0 - min(1.0, primary_target_error / 0.25)),
                _clamp_score(1.0 - min(1.0, reference_target_error / 0.25)),
            ]
        )
        return EvaluationResult(
            suite_id=self.suite_id,
            suite=self.name,
            scenario=scenario.name,
            provider=provider,
            score=score,
            passed=passed,
            metrics={
                "action_count": plan.action_count,
                "success_probability": plan.success_probability,
                "primary_target_error": primary_target_error,
                "reference_target_error": reference_target_error,
                "final_step": final_world.step,
            },
        )

    def _evaluate_object_spawn(
        self,
        scenario: EvaluationScenario,
        provider: str,
        *,
        world: World,
        forge: WorldForge,
        index: int,
    ) -> EvaluationResult:
        seed_object(world, "cube", Position(0.0, 0.5, 0.0))
        seed_object(world, "mug", Position(0.3, 0.8, 0.0))
        initial_count = world.object_count
        plan = world.plan(goal="spawn cube", max_steps=3, provider=provider)
        execution = world.execute_plan(plan, provider)
        final_world = execution.final_world()
        final_count = final_world.object_count
        spawned = final_count > initial_count
        score = _clamp_score((plan.success_probability + (1.0 if spawned else 0.0)) / 2)
        return EvaluationResult(
            suite_id=self.suite_id,
            suite=self.name,
            scenario=scenario.name,
            provider=provider,
            score=score,
            passed=spawned,
            metrics={
                "action_count": plan.action_count,
                "success_probability": plan.success_probability,
                "initial_object_count": initial_count,
                "final_object_count": final_count,
            },
        )

    _SCENARIO_HANDLERS: ClassVar[dict[str, Callable[..., EvaluationResult]]] = {
        "object-relocation": _evaluate_object_relocation,
        "object-neighbor-placement": _evaluate_object_neighbor_placement,
        "object-swap": _evaluate_object_swap,
        "object-spawn": _evaluate_object_spawn,
    }


__all__ = ["PlanningEvaluationSuite"]

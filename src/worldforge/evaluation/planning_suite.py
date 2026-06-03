"""Latent-MPC planning evaluation suite over the forge score surface."""

from __future__ import annotations

from collections.abc import Callable
from itertools import pairwise
from typing import TYPE_CHECKING, ClassVar

from worldforge.control import LatentMPCController, PlannerConfig
from worldforge.evaluation.results import EvaluationResult, EvaluationScenario
from worldforge.evaluation.results import clamp_score as _clamp_score
from worldforge.evaluation.suite_base import EvaluationSuite

if TYPE_CHECKING:
    from worldforge.control import MPCStepResult
    from worldforge.framework import WorldForge

# Each scenario solves a short latent-MPC problem toward a distinct goal target. The targets sit
# inside the controller's action-parameter bounds so the deterministic mock cost oracle (squared
# distance to target) can converge.
_SCENARIO_TARGETS: dict[str, tuple[float, float, float]] = {
    "object-relocation": (0.45, 0.5, 0.0),
    "object-neighbor-placement": (0.30, 0.40, 0.0),
    "object-swap": (-0.40, 0.30, 0.0),
    "object-spawn": (0.60, -0.20, 0.10),
}

_PLANNER_BOUNDS = {
    "x": (-1.0, 1.0),
    "y": (-1.0, 1.0),
    "z": (-1.0, 1.0),
}


class PlanningEvaluationSuite(EvaluationSuite):
    """Built-in suite for latent-MPC planning checks over a ``score`` cost oracle.

    Each scenario runs a short receding-horizon CEM solve through
    :class:`~worldforge.control.LatentMPCController`, which scores candidate action plans via the
    provider's ``score_actions`` surface. A scenario passes when the controller reduced cost across
    iterations and selected at least one action. There is no symbolic
    :class:`~worldforge.framework.World` involved.
    """

    def __init__(self) -> None:
        super().__init__(
            "Planning Evaluation Suite",
            scenarios=[
                EvaluationScenario(
                    "object-relocation",
                    "Solves a latent-MPC relocation objective toward a typed target.",
                    required_capabilities=("score",),
                ),
                EvaluationScenario(
                    "object-neighbor-placement",
                    "Solves a latent-MPC placement objective near a relational target.",
                    required_capabilities=("score",),
                ),
                EvaluationScenario(
                    "object-swap",
                    "Solves a latent-MPC objective toward a swapped-position target.",
                    required_capabilities=("score",),
                ),
                EvaluationScenario(
                    "object-spawn",
                    "Solves a latent-MPC objective toward a spawn-placement target.",
                    required_capabilities=("score",),
                ),
            ],
            suite_id="planning",
        )

    def _controller(self, provider: str, *, forge: WorldForge) -> LatentMPCController:
        return LatentMPCController(
            forge=forge,
            score_provider=provider,
            config=PlannerConfig(
                horizon=1,
                num_samples=48,
                num_iterations=4,
                num_elites=8,
                action_kind="latent_action",
                action_parameter_bounds=_PLANNER_BOUNDS,
                seed=0,
            ),
        )

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

    def _solve(
        self,
        scenario: EvaluationScenario,
        provider: str,
        *,
        forge: WorldForge,
    ) -> EvaluationResult:
        target = list(_SCENARIO_TARGETS[scenario.name])
        result = self._controller(provider, forge=forge).plan_step(
            observation_info={"point": [0.0, 0.0, 0.0]},
            goal_info={"target": target},
        )
        return self._result_from_step(scenario, provider, result=result, target=target)

    def _result_from_step(
        self,
        scenario: EvaluationScenario,
        provider: str,
        *,
        result: MPCStepResult,
        target: list[float],
    ) -> EvaluationResult:
        iteration_scores = result.iteration_best_scores
        first_cost = iteration_scores[0]
        last_cost = iteration_scores[-1]
        non_increasing = all(
            later <= earlier + 1e-9 for earlier, later in pairwise(iteration_scores)
        )
        cost_reduction = max(0.0, first_cost - last_cost)
        selected = bool(result.actions)
        # A small final cost means the controller steered candidates close to the goal target.
        success_probability = _clamp_score(1.0 - min(1.0, result.best_score))
        passed = selected and non_increasing and result.best_score <= 0.1
        score = _clamp_score((success_probability + (1.0 if cost_reduction > 0.0 else 0.0)) / 2)
        return EvaluationResult(
            suite_id=self.suite_id,
            suite=self.name,
            scenario=scenario.name,
            provider=provider,
            score=score,
            passed=passed,
            metrics={
                "action_count": len(result.actions),
                "success_probability": success_probability,
                "best_score": result.best_score,
                "first_iteration_cost": first_cost,
                "final_iteration_cost": last_cost,
                "cost_reduction": cost_reduction,
                "candidate_count": result.candidate_count,
                "non_increasing": non_increasing,
                "selected": selected,
            },
        )

    def _evaluate_object_relocation(
        self,
        scenario: EvaluationScenario,
        provider: str,
        *,
        forge: WorldForge,
        index: int,
    ) -> EvaluationResult:
        return self._solve(scenario, provider, forge=forge)

    def _evaluate_object_neighbor_placement(
        self,
        scenario: EvaluationScenario,
        provider: str,
        *,
        forge: WorldForge,
        index: int,
    ) -> EvaluationResult:
        return self._solve(scenario, provider, forge=forge)

    def _evaluate_object_swap(
        self,
        scenario: EvaluationScenario,
        provider: str,
        *,
        forge: WorldForge,
        index: int,
    ) -> EvaluationResult:
        return self._solve(scenario, provider, forge=forge)

    def _evaluate_object_spawn(
        self,
        scenario: EvaluationScenario,
        provider: str,
        *,
        forge: WorldForge,
        index: int,
    ) -> EvaluationResult:
        return self._solve(scenario, provider, forge=forge)

    _SCENARIO_HANDLERS: ClassVar[dict[str, Callable[..., EvaluationResult]]] = {
        "object-relocation": _evaluate_object_relocation,
        "object-neighbor-placement": _evaluate_object_neighbor_placement,
        "object-swap": _evaluate_object_swap,
        "object-spawn": _evaluate_object_spawn,
    }


__all__ = ["PlanningEvaluationSuite"]

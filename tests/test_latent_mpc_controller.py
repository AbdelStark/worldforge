from __future__ import annotations

import pytest

from worldforge import (
    ActionPlanCandidateEncoder,
    ActionScoreResult,
    LatentMPCController,
    PlannerConfig,
    WorldForgeError,
)
from worldforge.models import JSONDict
from worldforge.providers.base import ProviderProfileSpec


def _candidate_payloads(action_candidates: object) -> list[list[JSONDict]]:
    assert isinstance(action_candidates, list)
    return action_candidates


def _first_x(candidate: list[JSONDict]) -> float:
    return float(candidate[0]["parameters"]["x"])


class _ConvexCost:
    name = "convex_cost"
    profile = ProviderProfileSpec(description="convex test score model")

    def score_actions(self, *, info: JSONDict, action_candidates: object) -> ActionScoreResult:
        candidates = _candidate_payloads(action_candidates)
        target_x = float(info["goal"]["target_x"])
        scores = [(_first_x(candidate) - target_x) ** 2 for candidate in candidates]
        best_index = min(range(len(scores)), key=scores.__getitem__)
        return ActionScoreResult(provider=self.name, scores=scores, best_index=best_index)


class _ConvexForge:
    def __init__(self, *, lower_is_better: bool = True, target_x: float = 0.75) -> None:
        self.lower_is_better = lower_is_better
        self.target_x = target_x

    def score_actions(
        self,
        provider: str,
        *,
        info: JSONDict,
        action_candidates: object,
    ) -> ActionScoreResult:
        candidates = _candidate_payloads(action_candidates)
        target_x = float(info["goal"].get("target_x", self.target_x))
        if self.lower_is_better:
            scores = [(_first_x(candidate) - target_x) ** 2 for candidate in candidates]
            best_index = min(range(len(scores)), key=scores.__getitem__)
        else:
            scores = [1.0 - abs(_first_x(candidate) - target_x) for candidate in candidates]
            best_index = max(range(len(scores)), key=scores.__getitem__)
        return ActionScoreResult(
            provider=provider,
            scores=scores,
            best_index=best_index,
            lower_is_better=self.lower_is_better,
        )


class _BadScoreForge:
    def score_actions(
        self,
        provider: str,
        *,
        info: JSONDict,
        action_candidates: object,
    ) -> ActionScoreResult:
        return ActionScoreResult(provider=provider, scores=[0.0], best_index=0)


class _FlatTieForge:
    def score_actions(
        self,
        provider: str,
        *,
        info: JSONDict,
        action_candidates: object,
    ) -> ActionScoreResult:
        candidates = _candidate_payloads(action_candidates)
        return ActionScoreResult(
            provider=provider,
            scores=[0.0 for _ in candidates],
            best_index=0,
        )


def test_latent_mpc_controller_converges_on_lower_is_better_score() -> None:
    controller = LatentMPCController(
        forge=_ConvexForge(),
        score_provider="convex",
        encoder=ActionPlanCandidateEncoder(),
        config=PlannerConfig(
            horizon=2,
            num_samples=96,
            num_iterations=5,
            num_elites=12,
            execute_k=1,
            init_std=1.25,
            seed=7,
            action_kind="velocity",
            action_parameter_bounds={"x": (-2.0, 2.0)},
        ),
    )

    result = controller.plan_step(
        observation_info={"frame": "synthetic"},
        goal_info={"target_x": 0.75},
    )

    assert result.actions[0].kind == "velocity"
    assert result.actions[0].parameters["x"] == pytest.approx(0.75, abs=0.2)
    assert result.best_score < 0.04
    assert result.lower_is_better is True
    assert result.iteration_best_scores[-1] <= result.iteration_best_scores[0]
    assert result.candidate_count == 96 * 5


def test_latent_mpc_controller_handles_higher_is_better_scores() -> None:
    controller = LatentMPCController(
        forge=_ConvexForge(lower_is_better=False, target_x=-0.4),
        score_provider="utility",
        config=PlannerConfig(
            horizon=1,
            num_samples=80,
            num_iterations=4,
            num_elites=10,
            execute_k=1,
            init_std=1.0,
            seed=11,
            action_kind="velocity",
            action_parameter_bounds={"x": (-2.0, 2.0)},
        ),
    )

    result = controller.plan_step(observation_info={}, goal_info={"target_x": -0.4})

    assert result.actions[0].parameters["x"] == pytest.approx(-0.4, abs=0.2)
    assert result.lower_is_better is False
    assert result.best_score > 0.8


def test_latent_mpc_controller_default_seed_makes_tie_cases_repeatable() -> None:
    config = PlannerConfig(
        horizon=1,
        num_samples=8,
        num_iterations=2,
        num_elites=4,
        action_kind="velocity",
        action_parameter_bounds={"x": (-1.0, 1.0)},
    )
    first = LatentMPCController(
        forge=_FlatTieForge(),
        score_provider="flat",
        config=config,
    ).plan_step(observation_info={}, goal_info={})
    second = LatentMPCController(
        forge=_FlatTieForge(),
        score_provider="flat",
        config=config,
    ).plan_step(observation_info={}, goal_info={})

    assert first.actions[0].to_dict() == second.actions[0].to_dict()
    assert first.iteration_best_scores == second.iteration_best_scores
    assert first.metadata["config"]["seed"] == 0


def test_latent_mpc_controller_rejects_score_count_mismatch() -> None:
    controller = LatentMPCController(
        forge=_BadScoreForge(),
        score_provider="bad",
        config=PlannerConfig(num_samples=4, num_iterations=1, num_elites=1, seed=3),
    )

    with pytest.raises(WorldForgeError, match=r"returned 1 score\(s\) for 4 candidate"):
        controller.plan_step(observation_info={}, goal_info={})


def test_planner_config_validates_cem_settings() -> None:
    with pytest.raises(WorldForgeError, match="num_elites"):
        PlannerConfig(num_samples=2, num_elites=3)

    with pytest.raises(WorldForgeError, match="execute_k"):
        PlannerConfig(horizon=1, execute_k=2)

    with pytest.raises(WorldForgeError, match="action_parameter_bounds"):
        PlannerConfig(action_parameter_bounds={})

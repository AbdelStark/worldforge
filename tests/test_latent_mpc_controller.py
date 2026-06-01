from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from worldforge import (
    ActionPlanCandidateEncoder,
    ActionScoreResult,
    LatentMPCController,
    PlannerConfig,
    WorldForge,
    WorldForgeError,
)
from worldforge.models import JSONDict
from worldforge.providers.base import ProviderProfileSpec


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


def test_world_plan_latent_mpc_routes_through_score_provider(tmp_path: Path) -> None:
    forge = WorldForge(state_dir=tmp_path)
    forge.register_cost(_ConvexCost())
    world = forge.create_world("latent-mpc-world", "mock")

    plan = world.plan(
        goal="choose a one-step velocity",
        planner="latent-mpc",
        score_provider="convex_cost",
        score_info={"observation_id": "synthetic-frame"},
        goal_info={"target_x": 0.5},
        planner_config=PlannerConfig(
            horizon=1,
            num_samples=96,
            num_iterations=5,
            num_elites=12,
            execute_k=1,
            init_std=1.0,
            seed=19,
            action_kind="velocity",
            action_parameter_bounds={"x": (-2.0, 2.0)},
        ),
    )

    assert plan.provider == "convex_cost"
    assert plan.planner == "latent-mpc"
    assert plan.predicted_states == []
    assert plan.actions[0].kind == "velocity"
    assert plan.metadata["planning_mode"] == "latent-mpc"
    assert plan.metadata["control_mode"] == "mpc"
    assert plan.metadata["optimizer"] == "cem"
    assert plan.metadata["score_provider"] == "convex_cost"
    assert plan.metadata["candidate_count"] == 96 * 5
    assert plan.metadata["iteration_costs"] == plan.metadata["iteration_best_scores"]
    assert plan.metadata["workflow_trace"]["metadata"]["planning_mode"] == "latent-mpc"
    assert [step["status"] for step in plan.metadata["workflow_trace"]["steps"]] == [
        "success",
        "skipped",
        "success",
    ]


def test_world_plan_rejects_latent_mpc_options_without_latent_mpc_planner(tmp_path: Path) -> None:
    forge = WorldForge(state_dir=tmp_path)
    world = forge.create_world("latent-mpc-options-world", "mock")

    with pytest.raises(WorldForgeError, match="planner='latent-mpc'"):
        world.plan(
            goal="reject misplaced config",
            planner_config=PlannerConfig(),
        )


def test_world_plan_requires_explicit_score_provider_for_latent_mpc(tmp_path: Path) -> None:
    forge = WorldForge(state_dir=tmp_path)
    world = forge.create_world("latent-mpc-explicit-score-world", "mock")

    with pytest.raises(WorldForgeError, match="explicit score_provider"):
        world.plan(
            goal="reject implicit world provider as score oracle",
            planner="latent-mpc",
            score_info={},
            goal_info={"target_x": 0.0},
            planner_config=PlannerConfig(),
        )


def test_world_plan_rejects_blank_score_provider_for_latent_mpc(tmp_path: Path) -> None:
    forge = WorldForge(state_dir=tmp_path)
    world = forge.create_world("latent-mpc-blank-score-world", "mock")

    with pytest.raises(WorldForgeError, match="non-empty explicit score_provider"):
        world.plan(
            goal="reject blank score provider",
            planner="latent-mpc",
            score_provider=" ",
            score_info={},
            goal_info={"target_x": 0.0},
            planner_config=PlannerConfig(),
        )


def test_world_plan_rejects_unsupported_latent_mpc_policy_warm_start(tmp_path: Path) -> None:
    forge = WorldForge(state_dir=tmp_path)
    forge.register_cost(_ConvexCost())
    world = forge.create_world("latent-mpc-policy-world", "mock")

    with pytest.raises(WorldForgeError, match="policy warm-start"):
        world.plan(
            goal="reject policy warm start until implemented",
            planner="latent-mpc",
            score_provider="convex_cost",
            score_info={},
            goal_info={"target_x": 0.0},
            planner_config=PlannerConfig(),
            policy_info={"mode": "unsupported"},
        )


def test_world_plan_rejects_latent_mpc_execute_k_above_max_steps(tmp_path: Path) -> None:
    forge = WorldForge(state_dir=tmp_path)
    forge.register_cost(_ConvexCost())
    world = forge.create_world("latent-mpc-max-steps-world", "mock")

    with pytest.raises(WorldForgeError, match="execute_k must be <= max_steps"):
        world.plan(
            goal="reject incoherent receding horizon",
            planner="latent-mpc",
            score_provider="convex_cost",
            score_info={},
            goal_info={"target_x": 0.0},
            max_steps=1,
            planner_config=PlannerConfig(horizon=3, execute_k=2),
        )


def _candidate_payloads(action_candidates: object) -> list[list[dict[str, Any]]]:
    assert isinstance(action_candidates, list)
    assert action_candidates
    return action_candidates  # type: ignore[return-value]


def _first_x(candidate: list[dict[str, Any]]) -> float:
    return float(candidate[0]["parameters"]["x"])

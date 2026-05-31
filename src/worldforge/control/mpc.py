"""Latent MPC control over score providers.

The controller keeps the world-model boundary explicit: candidate action horizons are sampled
locally, encoded by the caller, then scored through the existing ``score_actions`` capability.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from random import Random
from typing import Protocol

from worldforge._model_utils import (
    JSONDict,
    WorldForgeError,
    require_finite_number,
    require_json_dict,
    require_non_empty_text,
    require_positive_int,
)
from worldforge.capability_results import ActionScoreResult
from worldforge.scene_models import Action


class ScorePlanningForge(Protocol):
    """Minimal forge surface required by :class:`LatentMPCController`."""

    def score_actions(
        self,
        provider: str,
        *,
        info: JSONDict,
        action_candidates: object,
    ) -> ActionScoreResult: ...


@dataclass(slots=True, frozen=True)
class ScoreCandidateBatch:
    """Payload passed to a score provider for one MPC scoring iteration."""

    info: JSONDict
    action_candidates: object

    def __post_init__(self) -> None:
        object.__setattr__(self, "info", require_json_dict(self.info, name="score batch info"))


class ScoreCandidateEncoder(Protocol):
    """Encode sampled action horizons into provider-specific score payloads."""

    def encode(
        self,
        candidate_action_plans: Sequence[Sequence[Action]],
        *,
        observation_info: JSONDict,
        goal_info: JSONDict,
    ) -> ScoreCandidateBatch: ...


@dataclass(slots=True, frozen=True)
class ActionPlanCandidateEncoder:
    """Generic encoder that sends action dictionaries plus observation and goal info."""

    def encode(
        self,
        candidate_action_plans: Sequence[Sequence[Action]],
        *,
        observation_info: JSONDict,
        goal_info: JSONDict,
    ) -> ScoreCandidateBatch:
        return ScoreCandidateBatch(
            info={
                "observation": require_json_dict(
                    observation_info,
                    name="observation_info",
                ),
                "goal": require_json_dict(goal_info, name="goal_info"),
            },
            action_candidates=[
                [action.to_dict() for action in candidate] for candidate in candidate_action_plans
            ],
        )


@dataclass(slots=True, frozen=True)
class PlannerConfig:
    """Configuration for action-space CEM/MPC over a score provider."""

    horizon: int = 1
    num_samples: int = 64
    num_iterations: int = 4
    num_elites: int = 8
    execute_k: int = 1
    init_std: float = 1.0
    min_std: float = 1e-3
    seed: int | None = None
    action_kind: str = "latent_action"
    action_parameter_bounds: Mapping[str, tuple[float, float]] = field(
        default_factory=lambda: {"x": (-1.0, 1.0)}
    )

    def __post_init__(self) -> None:
        horizon = require_positive_int(self.horizon, name="PlannerConfig.horizon")
        num_samples = require_positive_int(
            self.num_samples,
            name="PlannerConfig.num_samples",
        )
        num_iterations = require_positive_int(
            self.num_iterations,
            name="PlannerConfig.num_iterations",
        )
        num_elites = require_positive_int(self.num_elites, name="PlannerConfig.num_elites")
        execute_k = require_positive_int(self.execute_k, name="PlannerConfig.execute_k")
        if num_elites > num_samples:
            raise WorldForgeError("PlannerConfig.num_elites must be <= num_samples.")
        if execute_k > horizon:
            raise WorldForgeError("PlannerConfig.execute_k must be <= horizon.")
        init_std = _positive_float(self.init_std, name="PlannerConfig.init_std")
        min_std = _positive_float(self.min_std, name="PlannerConfig.min_std")
        if min_std > init_std:
            raise WorldForgeError("PlannerConfig.min_std must be <= init_std.")
        if self.seed is not None and (
            isinstance(self.seed, bool) or not isinstance(self.seed, int)
        ):
            raise WorldForgeError("PlannerConfig.seed must be an integer when provided.")

        object.__setattr__(self, "horizon", horizon)
        object.__setattr__(self, "num_samples", num_samples)
        object.__setattr__(self, "num_iterations", num_iterations)
        object.__setattr__(self, "num_elites", num_elites)
        object.__setattr__(self, "execute_k", execute_k)
        object.__setattr__(self, "init_std", init_std)
        object.__setattr__(self, "min_std", min_std)
        object.__setattr__(
            self,
            "action_kind",
            require_non_empty_text(self.action_kind, name="PlannerConfig.action_kind"),
        )
        object.__setattr__(
            self,
            "action_parameter_bounds",
            _validated_bounds(self.action_parameter_bounds),
        )

    def to_dict(self) -> JSONDict:
        return {
            "horizon": self.horizon,
            "num_samples": self.num_samples,
            "num_iterations": self.num_iterations,
            "num_elites": self.num_elites,
            "execute_k": self.execute_k,
            "init_std": self.init_std,
            "min_std": self.min_std,
            "seed": self.seed,
            "action_kind": self.action_kind,
            "action_parameter_bounds": {
                name: [lower, upper]
                for name, (lower, upper) in self.action_parameter_bounds.items()
            },
        }


@dataclass(slots=True, frozen=True)
class MPCStepResult:
    """Result for one receding-horizon MPC decision."""

    actions: list[Action]
    best_score: float
    lower_is_better: bool
    candidate_count: int
    iteration_best_scores: list[float]
    metadata: JSONDict = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.actions:
            raise WorldForgeError("MPCStepResult actions must not be empty.")
        object.__setattr__(self, "actions", list(self.actions))
        object.__setattr__(
            self,
            "best_score",
            require_finite_number(self.best_score, name="MPCStepResult.best_score"),
        )
        if not isinstance(self.lower_is_better, bool):
            raise WorldForgeError("MPCStepResult lower_is_better must be a boolean.")
        object.__setattr__(
            self,
            "candidate_count",
            require_positive_int(self.candidate_count, name="MPCStepResult.candidate_count"),
        )
        scores = [
            require_finite_number(score, name="MPCStepResult iteration_best_score")
            for score in self.iteration_best_scores
        ]
        if not scores:
            raise WorldForgeError("MPCStepResult iteration_best_scores must not be empty.")
        object.__setattr__(self, "iteration_best_scores", scores)
        object.__setattr__(
            self,
            "metadata",
            require_json_dict(self.metadata, name="MPCStepResult metadata"),
        )


@dataclass(slots=True, frozen=True)
class _GaussianState:
    means: list[list[float]]
    stds: list[list[float]]
    parameter_names: tuple[str, ...]


class LatentMPCController:
    """Receding-horizon CEM/MPC controller backed by ``score_actions``."""

    def __init__(
        self,
        *,
        forge: ScorePlanningForge,
        score_provider: str,
        config: PlannerConfig | None = None,
        encoder: ScoreCandidateEncoder | None = None,
    ) -> None:
        self.forge = forge
        self.score_provider = require_non_empty_text(
            score_provider,
            name="LatentMPCController.score_provider",
        )
        self.config = config or PlannerConfig()
        if not isinstance(self.config, PlannerConfig):
            raise WorldForgeError("LatentMPCController config must be a PlannerConfig.")
        self.encoder = encoder or ActionPlanCandidateEncoder()
        self._rng = Random(self.config.seed)

    def plan_step(
        self,
        *,
        observation_info: JSONDict,
        goal_info: JSONDict,
    ) -> MPCStepResult:
        observation = require_json_dict(observation_info, name="observation_info")
        goal = require_json_dict(goal_info, name="goal_info")
        state = self._initial_gaussian_state()
        best_candidate: list[Action] | None = None
        best_score: float | None = None
        lower_is_better: bool | None = None
        iteration_best_scores: list[float] = []
        scored_candidate_count = 0

        for _ in range(self.config.num_iterations):
            candidates = self._sample_candidates(state)
            score_result = self._score_candidates(candidates, observation=observation, goal=goal)
            scored_candidate_count += len(candidates)
            lower_is_better = _consistent_score_direction(
                previous=lower_is_better,
                current=score_result.lower_is_better,
            )
            iteration_best_index = score_result.best_index
            iteration_best_score = score_result.scores[iteration_best_index]
            if best_score is None or _score_is_better(
                iteration_best_score,
                best_score,
                lower_is_better=lower_is_better,
            ):
                best_score = iteration_best_score
                best_candidate = list(candidates[iteration_best_index])
            iteration_best_scores.append(best_score)
            state = self._refit_gaussian_state(
                state,
                candidates,
                score_result,
            )

        if best_candidate is None or best_score is None or lower_is_better is None:
            raise WorldForgeError("Latent MPC did not score any candidate action plans.")
        selected_actions = best_candidate[: self.config.execute_k]
        return MPCStepResult(
            actions=selected_actions,
            best_score=best_score,
            lower_is_better=lower_is_better,
            candidate_count=scored_candidate_count,
            iteration_best_scores=iteration_best_scores,
            metadata={
                "planning_mode": "latent-mpc",
                "control_mode": "mpc",
                "optimizer": "cem",
                "score_provider": self.score_provider,
                "config": self.config.to_dict(),
                "candidate_count": scored_candidate_count,
                "iteration_best_scores": list(iteration_best_scores),
                "iteration_costs": list(iteration_best_scores) if lower_is_better else [],
            },
        )

    def _initial_gaussian_state(self) -> _GaussianState:
        names = tuple(self.config.action_parameter_bounds)
        means: list[list[float]] = []
        stds: list[list[float]] = []
        for _ in range(self.config.horizon):
            means.append(
                [
                    (lower + upper) / 2.0
                    for lower, upper in self.config.action_parameter_bounds.values()
                ]
            )
            stds.append(
                [
                    min(self.config.init_std, max(self.config.min_std, (upper - lower) / 2.0))
                    for lower, upper in self.config.action_parameter_bounds.values()
                ]
            )
        return _GaussianState(means=means, stds=stds, parameter_names=names)

    def _sample_candidates(self, state: _GaussianState) -> list[list[Action]]:
        return [self._sample_action_plan(state) for _ in range(self.config.num_samples)]

    def _sample_action_plan(self, state: _GaussianState) -> list[Action]:
        actions: list[Action] = []
        for step_index in range(self.config.horizon):
            parameters: JSONDict = {}
            for param_index, name in enumerate(state.parameter_names):
                lower, upper = self.config.action_parameter_bounds[name]
                value = self._rng.gauss(
                    state.means[step_index][param_index],
                    state.stds[step_index][param_index],
                )
                parameters[name] = min(upper, max(lower, value))
            actions.append(Action(kind=self.config.action_kind, parameters=parameters))
        return actions

    def _score_candidates(
        self,
        candidates: Sequence[Sequence[Action]],
        *,
        observation: JSONDict,
        goal: JSONDict,
    ) -> ActionScoreResult:
        batch = self.encoder.encode(candidates, observation_info=observation, goal_info=goal)
        if not isinstance(batch, ScoreCandidateBatch):
            raise WorldForgeError("ScoreCandidateEncoder.encode must return ScoreCandidateBatch.")
        result = self.forge.score_actions(
            self.score_provider,
            info=batch.info,
            action_candidates=batch.action_candidates,
        )
        _require_score_count_matches_candidates(
            provider=self.score_provider,
            score_result=result,
            candidate_count=len(candidates),
        )
        return result

    def _refit_gaussian_state(
        self,
        state: _GaussianState,
        candidates: Sequence[Sequence[Action]],
        score_result: ActionScoreResult,
    ) -> _GaussianState:
        elite_indices = _elite_indices(
            score_result.scores,
            count=self.config.num_elites,
            lower_is_better=score_result.lower_is_better,
        )
        elite_vectors = [
            _candidate_parameter_vector(
                candidates[index],
                parameter_names=state.parameter_names,
                horizon=self.config.horizon,
            )
            for index in elite_indices
        ]
        means: list[list[float]] = []
        stds: list[list[float]] = []
        for step_index in range(self.config.horizon):
            step_means: list[float] = []
            step_stds: list[float] = []
            for param_index, name in enumerate(state.parameter_names):
                values = [vector[step_index][param_index] for vector in elite_vectors]
                mean = sum(values) / len(values)
                variance = sum((value - mean) ** 2 for value in values) / len(values)
                lower, upper = self.config.action_parameter_bounds[name]
                step_means.append(min(upper, max(lower, mean)))
                step_stds.append(max(self.config.min_std, variance**0.5))
            means.append(step_means)
            stds.append(step_stds)
        return _GaussianState(
            means=means,
            stds=stds,
            parameter_names=state.parameter_names,
        )


def _positive_float(value: object, *, name: str) -> float:
    resolved = require_finite_number(value, name=name)
    if resolved <= 0.0:
        raise WorldForgeError(f"{name} must be greater than 0.")
    return resolved


def _validated_bounds(bounds: object) -> dict[str, tuple[float, float]]:
    if not isinstance(bounds, Mapping) or not bounds:
        raise WorldForgeError("PlannerConfig.action_parameter_bounds must be a non-empty mapping.")
    resolved: dict[str, tuple[float, float]] = {}
    for raw_name, raw_limits in bounds.items():
        name = require_non_empty_text(
            raw_name,
            name="PlannerConfig.action_parameter_bounds key",
        )
        if (
            not isinstance(raw_limits, Sequence)
            or isinstance(raw_limits, (str, bytes, bytearray))
            or len(raw_limits) != 2
        ):
            raise WorldForgeError(
                f"PlannerConfig.action_parameter_bounds[{name!r}] must contain two bounds."
            )
        lower = require_finite_number(
            raw_limits[0],
            name=f"PlannerConfig.action_parameter_bounds[{name!r}][0]",
        )
        upper = require_finite_number(
            raw_limits[1],
            name=f"PlannerConfig.action_parameter_bounds[{name!r}][1]",
        )
        if lower >= upper:
            raise WorldForgeError(
                f"PlannerConfig.action_parameter_bounds[{name!r}] lower bound must be < upper."
            )
        resolved[name] = (lower, upper)
    return resolved


def _require_score_count_matches_candidates(
    *,
    provider: str,
    score_result: ActionScoreResult,
    candidate_count: int,
) -> None:
    score_count = len(score_result.scores)
    if score_count != candidate_count:
        raise WorldForgeError(
            f"Provider '{provider}' returned {score_count} score(s) for "
            f"{candidate_count} candidate action plan(s)."
        )


def _consistent_score_direction(previous: bool | None, current: bool) -> bool:
    if previous is None or previous == current:
        return current
    raise WorldForgeError("Latent MPC score provider changed lower_is_better between iterations.")


def _score_is_better(candidate: float, incumbent: float, *, lower_is_better: bool) -> bool:
    return candidate < incumbent if lower_is_better else candidate > incumbent


def _elite_indices(scores: Sequence[float], *, count: int, lower_is_better: bool) -> list[int]:
    return sorted(
        range(len(scores)),
        key=lambda index: scores[index],
        reverse=not lower_is_better,
    )[:count]


def _candidate_parameter_vector(
    candidate: Sequence[Action],
    *,
    parameter_names: Sequence[str],
    horizon: int,
) -> list[list[float]]:
    if len(candidate) != horizon:
        raise WorldForgeError("Latent MPC candidate action plan length did not match horizon.")
    return [
        [
            require_finite_number(
                action.parameters[name],
                name=f"Action parameter {name}",
            )
            for name in parameter_names
        ]
        for action in candidate
    ]


__all__ = [
    "ActionPlanCandidateEncoder",
    "LatentMPCController",
    "MPCStepResult",
    "PlannerConfig",
    "ScoreCandidateBatch",
    "ScoreCandidateEncoder",
    "ScorePlanningForge",
]

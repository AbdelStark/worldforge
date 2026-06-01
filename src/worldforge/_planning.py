"""Private planning helpers for WorldForge orchestration.

This module keeps plan-mode selection support, workflow-trace construction, and provider score
bookkeeping out of ``framework.py``. It deliberately has no dependency on ``World`` or
``WorldForge`` concrete classes.
"""

from __future__ import annotations

from collections.abc import Sequence
from copy import deepcopy
from dataclasses import dataclass
from typing import Protocol

from worldforge.action_candidates import normalize_action_candidates
from worldforge.control import MPCStepResult, PlannerConfig, ScoreCandidateEncoder
from worldforge.models import (
    Action,
    ActionPolicyResult,
    ActionScoreResult,
    JSONDict,
    WorldForgeError,
    average,
)
from worldforge.providers import PredictionPayload
from worldforge.workflow_trace import WorkflowArtifactRef, WorkflowTrace, WorkflowTraceStep

POLICY_PLAN_DEFAULT_SUCCESS_PROBABILITY = 0.5
PREDICTIVE_PLAN_MIN_SUCCESS_PROBABILITY = 0.65
PREDICTIVE_PLAN_MAX_SUCCESS_PROBABILITY = 0.98
PREDICTIVE_PLAN_DEFAULT_SUCCESS_PROBABILITY = 0.7


class PredictivePlannerForge(Protocol):
    def predict(
        self,
        state: JSONDict,
        action: Action,
        steps: int = 1,
        provider: str | None = None,
    ) -> PredictionPayload: ...


@dataclass(slots=True, frozen=True)
class ResolvedPlanGoal:
    goal: str
    goal_spec: JSONDict | None
    actions: list[Action]


@dataclass(slots=True, frozen=True)
class PlanRequest:
    planner: str
    max_steps: int
    provider: str
    policy_provider: str
    score_provider: str
    uses_policy_planning: bool
    uses_score_planning: bool
    candidate_actions: Sequence[Action | Sequence[Action]] | None
    policy_info: JSONDict | None
    score_info: JSONDict | None
    score_action_candidates: object | None
    execution_provider: str | None
    uses_mpc_planning: bool = False
    planner_config: PlannerConfig | None = None
    candidate_encoder: ScoreCandidateEncoder | None = None
    goal_info: JSONDict | None = None


@dataclass(slots=True, frozen=True)
class PlanProviderSelection:
    provider: str
    policy_provider: str
    score_provider: str
    uses_policy_planning: bool
    uses_score_planning: bool


@dataclass(slots=True, frozen=True)
class ScoredPlanSelection:
    actions: list[Action]
    score_result: ActionScoreResult
    success_probability: float
    success_probability_source: str


@dataclass(slots=True, frozen=True)
class PredictivePlanSimulation:
    predicted_states: list[JSONDict]
    scores: list[float]

    @property
    def success_probability(self) -> float:
        return predictive_plan_success_probability(self.scores)


def action_plans_to_score_payload(
    candidate_action_plans: Sequence[Sequence[Action]],
) -> list[list[JSONDict]]:
    return [[action.to_dict() for action in candidate] for candidate in candidate_action_plans]


def bounded_plan_actions(actions: Sequence[Action], *, max_steps: int) -> list[Action]:
    return list(actions)[:max_steps]


def require_score_count_matches_candidates(
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


def score_plan_success_probability(score_result: ActionScoreResult) -> tuple[float, str]:
    """Return a conservative plan probability heuristic for provider-defined scores."""

    best_score = score_result.best_score
    if score_result.lower_is_better:
        best_cost = max(0.0, best_score)
        return 1.0 / (1.0 + best_cost), "inverse_best_cost_heuristic"
    if 0.0 <= best_score <= 1.0:
        return best_score, "bounded_best_utility_heuristic"
    return 0.5, "unbounded_best_utility_no_probability"


def clamped_probability(value: float) -> float:
    return max(0.0, min(1.0, value))


def require_valid_best_score_index(
    *,
    score_provider: str,
    best_index: int,
    candidate_count: int,
    policy_provider: str | None = None,
) -> None:
    if best_index < candidate_count:
        return
    raise best_score_index_error(
        score_provider=score_provider,
        best_index=best_index,
        candidate_count=candidate_count,
        policy_provider=policy_provider,
    )


def best_score_index_error(
    *,
    score_provider: str,
    best_index: int,
    candidate_count: int,
    policy_provider: str | None = None,
) -> WorldForgeError:
    if policy_provider is not None:
        return WorldForgeError(
            f"Provider '{score_provider}' selected candidate index "
            f"{best_index}, but policy provider "
            f"'{policy_provider}' returned only "
            f"{candidate_count} candidate action plan(s)."
        )
    return WorldForgeError(
        f"Provider '{score_provider}' selected candidate index "
        f"{best_index}, but only {candidate_count} "
        "candidate action plan(s) were provided."
    )


def plan_workflow_trace(
    *,
    mode: str,
    planner: str,
    provider: str,
    action_count: int,
    candidate_count: int | None = None,
    policy_provider: str | None = None,
    score_provider: str | None = None,
    predict_step_count: int = 0,
) -> JSONDict:
    steps = [plan_trace_root_step(mode=mode, provider=provider)]
    steps.extend(
        plan_trace_policy_steps(
            mode=mode,
            provider=provider,
            policy_provider=policy_provider,
        )
    )
    steps.extend(
        plan_trace_score_steps(
            mode=mode,
            provider=provider,
            score_provider=score_provider,
        )
    )
    steps.extend(
        plan_trace_predict_steps(
            mode=mode,
            provider=provider,
            predict_step_count=predict_step_count,
        )
    )
    return plan_trace_payload(
        mode=mode,
        planner=planner,
        action_count=action_count,
        candidate_count=candidate_count,
        steps=steps,
    )


def plan_trace_root_step(*, mode: str, provider: str) -> WorkflowTraceStep:
    return WorkflowTraceStep(
        step_id="plan",
        operation=f"{mode} planning",
        status="success",
        provider=provider,
        input_artifacts=(WorkflowArtifactRef(label="world-state"),),
        output_artifacts=(WorkflowArtifactRef(label="plan"),),
    )


def plan_trace_policy_steps(
    *,
    mode: str,
    provider: str,
    policy_provider: str | None,
) -> list[WorkflowTraceStep]:
    builder = POLICY_TRACE_STEP_BUILDERS.get(mode)
    if builder is None:
        return []
    return [builder(provider=provider, selected_provider=policy_provider)]


def plan_trace_score_steps(
    *,
    mode: str,
    provider: str,
    score_provider: str | None,
) -> list[WorkflowTraceStep]:
    builder = SCORE_TRACE_STEP_BUILDERS.get(mode)
    if builder is None:
        return []
    return [builder(provider=provider, selected_provider=score_provider)]


def active_policy_trace_step(
    *,
    provider: str,
    selected_provider: str | None,
) -> WorkflowTraceStep:
    return WorkflowTraceStep(
        step_id="policy",
        parent_id="plan",
        operation="select action candidates",
        status="success",
        provider=selected_provider or provider,
        capability="policy",
        output_artifacts=(WorkflowArtifactRef(label="policy-candidates"),),
    )


def skipped_policy_trace_step(
    *,
    provider: str,
    selected_provider: str | None,
) -> WorkflowTraceStep:
    return WorkflowTraceStep(
        step_id="policy",
        parent_id="plan",
        operation="select action candidates",
        status="skipped",
        capability="policy",
        error_summary="Policy provider not requested; score planning used caller candidates.",
    )


def active_score_trace_step(
    *,
    provider: str,
    selected_provider: str | None,
) -> WorkflowTraceStep:
    return WorkflowTraceStep(
        step_id="score",
        parent_id="plan",
        operation="rank action candidates",
        status="success",
        provider=selected_provider or provider,
        capability="score",
        input_artifacts=(WorkflowArtifactRef(label="action-candidates"),),
        output_artifacts=(WorkflowArtifactRef(label="score-ranking"),),
    )


def skipped_score_trace_step(
    *,
    provider: str,
    selected_provider: str | None,
) -> WorkflowTraceStep:
    return WorkflowTraceStep(
        step_id="score",
        parent_id="plan",
        operation="rank action candidates",
        status="skipped",
        capability="score",
        error_summary="Score provider not requested; policy result used directly.",
    )


POLICY_TRACE_STEP_BUILDERS = {
    "policy": active_policy_trace_step,
    "policy+score": active_policy_trace_step,
    "score": skipped_policy_trace_step,
    "latent-mpc": skipped_policy_trace_step,
}
SCORE_TRACE_STEP_BUILDERS = {
    "score": active_score_trace_step,
    "policy+score": active_score_trace_step,
    "policy": skipped_score_trace_step,
    "latent-mpc": active_score_trace_step,
}


def plan_trace_predict_steps(
    *,
    mode: str,
    provider: str,
    predict_step_count: int,
) -> list[WorkflowTraceStep]:
    if mode != "predict":
        return []
    return [
        WorkflowTraceStep(
            step_id=f"predict-{index + 1}",
            parent_id="plan",
            operation="predict next state",
            status="success",
            provider=provider,
            capability="predict",
            input_artifacts=(WorkflowArtifactRef(label="world-state"),),
            output_artifacts=(WorkflowArtifactRef(label=f"predicted-state-{index + 1}"),),
        )
        for index in range(max(0, predict_step_count))
    ]


def plan_trace_payload(
    *,
    mode: str,
    planner: str,
    action_count: int,
    candidate_count: int | None,
    steps: Sequence[WorkflowTraceStep],
) -> JSONDict:
    return WorkflowTrace(
        workflow_id=f"plan:{mode.replace('+', '-')}",
        name=f"World plan ({mode})",
        steps=steps,
        metadata={
            "planner": planner,
            "planning_mode": mode,
            "action_count": action_count,
            "candidate_count": candidate_count,
        },
    ).to_dict()


def policy_plan_metadata(
    request: PlanRequest,
    policy_result: ActionPolicyResult,
    *,
    action_count: int,
    candidate_count: int,
) -> JSONDict:
    return {
        "planning_mode": "policy",
        "policy_provider": request.policy_provider,
        "policy_result": policy_result.to_dict(),
        "candidate_count": candidate_count,
        "success_probability_source": "policy_provider_no_world_model",
        "workflow_trace": plan_workflow_trace(
            mode="policy",
            planner=request.planner,
            provider=request.policy_provider,
            action_count=action_count,
            candidate_count=candidate_count,
            policy_provider=request.policy_provider,
        ),
    }


def policy_score_plan_metadata(
    request: PlanRequest,
    policy_result: ActionPolicyResult,
    selection: ScoredPlanSelection,
    *,
    candidate_count: int,
) -> JSONDict:
    return {
        "planning_mode": "policy+score",
        "policy_provider": request.policy_provider,
        "score_provider": request.score_provider,
        "policy_result": policy_result.to_dict(),
        "score_result": selection.score_result.to_dict(),
        "candidate_count": candidate_count,
        "success_probability_source": selection.success_probability_source,
        "workflow_trace": plan_workflow_trace(
            mode="policy+score",
            planner=request.planner,
            provider=request.score_provider,
            action_count=len(selection.actions),
            candidate_count=candidate_count,
            policy_provider=request.policy_provider,
            score_provider=request.score_provider,
        ),
    }


def score_plan_metadata(
    request: PlanRequest,
    selection: ScoredPlanSelection,
    *,
    candidate_count: int,
) -> JSONDict:
    return {
        "planning_mode": "score",
        "score_result": selection.score_result.to_dict(),
        "candidate_count": candidate_count,
        "success_probability_source": selection.success_probability_source,
        "workflow_trace": plan_workflow_trace(
            mode="score",
            planner=request.planner,
            provider=request.score_provider,
            action_count=len(selection.actions),
            candidate_count=candidate_count,
            score_provider=request.score_provider,
        ),
    }


def mpc_plan_metadata(
    request: PlanRequest,
    step_result: MPCStepResult,
    *,
    success_probability_source: str,
) -> JSONDict:
    return {
        "planning_mode": "latent-mpc",
        "control_mode": "mpc",
        "optimizer": "cem",
        "score_provider": request.score_provider,
        "best_score": step_result.best_score,
        "lower_is_better": step_result.lower_is_better,
        "candidate_count": step_result.candidate_count,
        "iteration_best_scores": list(step_result.iteration_best_scores),
        "iteration_costs": (
            list(step_result.iteration_best_scores) if step_result.lower_is_better else []
        ),
        "mpc_result": dict(step_result.metadata),
        "success_probability_source": success_probability_source,
        "workflow_trace": plan_workflow_trace(
            mode="latent-mpc",
            planner=request.planner,
            provider=request.score_provider,
            action_count=len(step_result.actions),
            candidate_count=step_result.candidate_count,
            score_provider=request.score_provider,
        ),
    }


def score_only_candidate_action_plans(request: PlanRequest) -> list[list[Action]]:
    if request.candidate_actions is None or request.score_info is None:
        raise WorldForgeError(
            "Score planning (without policy planning) requires provider, "
            "candidate_actions, and score_info."
        )
    return normalize_action_candidates(request.candidate_actions)


def mpc_plan_success_probability(step_result: MPCStepResult) -> tuple[float, str]:
    best_score = step_result.best_score
    if step_result.lower_is_better:
        best_cost = max(0.0, best_score)
        return 1.0 / (1.0 + best_cost), "inverse_best_cost_heuristic"
    if 0.0 <= best_score <= 1.0:
        return best_score, "bounded_best_utility_heuristic"
    return 0.5, "unbounded_best_utility_no_probability"


def predictive_plan_success_probability(scores: Sequence[float]) -> float:
    score_average = average(scores) if scores else PREDICTIVE_PLAN_DEFAULT_SUCCESS_PROBABILITY
    return max(
        PREDICTIVE_PLAN_MIN_SUCCESS_PROBABILITY,
        min(PREDICTIVE_PLAN_MAX_SUCCESS_PROBABILITY, score_average),
    )


def simulate_predictive_plan(
    forge: PredictivePlannerForge,
    *,
    initial_state: JSONDict,
    actions: Sequence[Action],
    provider: str,
) -> PredictivePlanSimulation:
    simulated_state = deepcopy(initial_state)
    predicted_states: list[JSONDict] = []
    scores: list[float] = []
    for action in actions:
        payload = forge.predict(
            simulated_state,
            action,
            steps=1,
            provider=provider,
        )
        simulated_state = deepcopy(payload.state)
        predicted_states.append(simulated_state)
        scores.append(payload.physics_score)
    return PredictivePlanSimulation(predicted_states=predicted_states, scores=scores)


def predictive_plan_metadata(
    request: PlanRequest,
    resolved_goal: ResolvedPlanGoal,
    simulation: PredictivePlanSimulation,
) -> JSONDict:
    return {
        "planning_mode": "predict",
        "workflow_trace": plan_workflow_trace(
            mode="predict",
            planner=request.planner,
            provider=request.provider,
            action_count=len(resolved_goal.actions),
            predict_step_count=len(simulation.predicted_states),
        ),
    }

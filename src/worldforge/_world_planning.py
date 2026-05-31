"""Planning orchestration for mutable :class:`worldforge._world.World` instances.

This module owns the provider-mode routing for ``World.plan``. It stays independent from the
concrete ``World`` class so world state mutation, persistence, and evaluation do not need to carry
policy/score/predictive planning internals as private methods.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from typing import Protocol

from worldforge._planning import (
    POLICY_PLAN_DEFAULT_SUCCESS_PROBABILITY,
    PlanProviderSelection,
    PlanRequest,
    ResolvedPlanGoal,
    ScoredPlanSelection,
    action_plans_to_score_payload,
    clamped_probability,
    mpc_plan_metadata,
    mpc_plan_success_probability,
    policy_plan_metadata,
    policy_score_plan_metadata,
    predictive_plan_metadata,
    require_score_count_matches_candidates,
    require_valid_best_score_index,
    score_only_candidate_action_plans,
    score_plan_metadata,
    score_plan_success_probability,
    simulate_predictive_plan,
)
from worldforge._results import Plan
from worldforge._world_goal_resolution import resolve_plan_goal
from worldforge.control import LatentMPCController, PlannerConfig, ScoreCandidateEncoder
from worldforge.models import (
    Action,
    ActionPolicyResult,
    ActionScoreResult,
    JSONDict,
    ProviderProfile,
    SceneObject,
    StructuredGoal,
    WorldForgeError,
    require_non_empty_text,
    require_positive_int,
)
from worldforge.providers import PredictionPayload


class WorldPlanningForge(Protocol):
    def provider_profile(self, provider: str) -> ProviderProfile: ...

    def select_actions(self, provider: str, *, info: JSONDict) -> ActionPolicyResult: ...

    def score_actions(
        self,
        provider: str,
        *,
        info: JSONDict,
        action_candidates: object,
    ) -> ActionScoreResult: ...

    def predict(
        self,
        state: JSONDict,
        action: Action,
        steps: int = 1,
        provider: str | None = None,
    ) -> PredictionPayload: ...


def normalize_provider_name(provider: str | None, fallback: str) -> str:
    return provider or fallback


def plan_execution_provider(
    plan: Plan,
    *,
    args: Sequence[object],
    provider: str | None,
) -> str:
    if provider is not None:
        return provider
    legacy_provider = next((arg for arg in args if isinstance(arg, str)), None)
    if legacy_provider is not None:
        return legacy_provider
    return str(plan.metadata.get("execution_provider") or plan.provider)


def plan_world(
    *,
    forge: WorldPlanningForge,
    scene_objects: Mapping[str, SceneObject],
    snapshot: Callable[[], JSONDict],
    default_provider: str,
    goal: str | None = None,
    goal_spec: StructuredGoal | None = None,
    goal_json: str | None = None,
    planner: str = "cem",
    max_steps: int = 20,
    provider: str | None = None,
    candidate_actions: Sequence[Action | Sequence[Action]] | None = None,
    policy_provider: str | None = None,
    policy_info: JSONDict | None = None,
    score_provider: str | None = None,
    score_info: JSONDict | None = None,
    score_action_candidates: object | None = None,
    planner_config: PlannerConfig | None = None,
    candidate_encoder: ScoreCandidateEncoder | None = None,
    goal_info: JSONDict | None = None,
    execution_provider: str | None = None,
) -> Plan:
    request = build_plan_request(
        default_provider=default_provider,
        forge=forge,
        planner=planner,
        max_steps=max_steps,
        provider=provider,
        candidate_actions=candidate_actions,
        policy_provider=policy_provider,
        policy_info=policy_info,
        score_provider=score_provider,
        score_info=score_info,
        score_action_candidates=score_action_candidates,
        planner_config=planner_config,
        candidate_encoder=candidate_encoder,
        goal_info=goal_info,
        execution_provider=execution_provider,
    )
    resolved_goal = resolve_plan_goal(
        scene_objects,
        goal=goal,
        goal_spec=goal_spec,
        goal_json=goal_json,
        max_steps=request.max_steps,
    )
    return plan_for_request(
        forge=forge,
        snapshot=snapshot,
        request=request,
        resolved_goal=resolved_goal,
    )


def build_plan_request(
    *,
    default_provider: str,
    forge: WorldPlanningForge,
    planner: str = "cem",
    max_steps: int = 20,
    provider: str | None = None,
    candidate_actions: Sequence[Action | Sequence[Action]] | None = None,
    policy_provider: str | None = None,
    policy_info: JSONDict | None = None,
    score_provider: str | None = None,
    score_info: JSONDict | None = None,
    score_action_candidates: object | None = None,
    planner_config: PlannerConfig | None = None,
    candidate_encoder: ScoreCandidateEncoder | None = None,
    goal_info: JSONDict | None = None,
    execution_provider: str | None = None,
) -> PlanRequest:
    resolved_max_steps = require_positive_int(max_steps, name="max_steps")
    uses_mpc = uses_mpc_planning(
        planner=planner,
        planner_config=planner_config,
        candidate_encoder=candidate_encoder,
        goal_info=goal_info,
    )
    selection = plan_provider_selection(
        default_provider=default_provider,
        provider=provider,
        uses_mpc_planning=uses_mpc,
        policy_provider=policy_provider,
        policy_info=policy_info,
        score_provider=score_provider,
        score_info=score_info,
        candidate_actions=candidate_actions,
        score_action_candidates=score_action_candidates,
    )
    validate_mpc_plan_request(
        uses_mpc_planning=uses_mpc,
        max_steps=resolved_max_steps,
        planner_config=planner_config,
        score_provider=score_provider,
        policy_provider=policy_provider,
        policy_info=policy_info,
        candidate_actions=candidate_actions,
        score_action_candidates=score_action_candidates,
        goal_info=goal_info,
    )
    validate_plan_provider_selection(
        forge,
        selection,
        uses_mpc_planning=uses_mpc,
        policy_info=policy_info,
        candidate_actions=candidate_actions,
        score_info=score_info,
    )
    return PlanRequest(
        planner=planner,
        max_steps=resolved_max_steps,
        provider=selection.provider,
        policy_provider=selection.policy_provider,
        score_provider=selection.score_provider,
        uses_policy_planning=selection.uses_policy_planning,
        uses_score_planning=selection.uses_score_planning,
        candidate_actions=candidate_actions,
        policy_info=policy_info,
        score_info=score_info,
        score_action_candidates=score_action_candidates,
        execution_provider=execution_provider,
        uses_mpc_planning=uses_mpc,
        planner_config=planner_config,
        candidate_encoder=candidate_encoder,
        goal_info=goal_info,
    )


def plan_provider_selection(
    *,
    default_provider: str,
    provider: str | None,
    uses_mpc_planning: bool = False,
    policy_provider: str | None,
    policy_info: JSONDict | None,
    score_provider: str | None,
    score_info: JSONDict | None,
    candidate_actions: Sequence[Action | Sequence[Action]] | None,
    score_action_candidates: object | None,
) -> PlanProviderSelection:
    selected_provider = normalize_provider_name(provider, default_provider)
    return PlanProviderSelection(
        provider=selected_provider,
        policy_provider=policy_provider or selected_provider,
        score_provider=score_provider if score_provider is not None else selected_provider,
        uses_policy_planning=uses_policy_planning(
            policy_info=policy_info,
            policy_provider=policy_provider,
        ),
        uses_score_planning=uses_mpc_planning
        or uses_score_planning(
            candidate_actions=candidate_actions,
            score_provider=score_provider,
            score_info=score_info,
            score_action_candidates=score_action_candidates,
        ),
    )


def validate_plan_provider_selection(
    forge: WorldPlanningForge,
    selection: PlanProviderSelection,
    *,
    uses_mpc_planning: bool,
    policy_info: JSONDict | None,
    candidate_actions: Sequence[Action | Sequence[Action]] | None,
    score_info: JSONDict | None,
) -> None:
    validate_policy_plan_request(
        forge,
        uses_policy_planning=selection.uses_policy_planning,
        selected_policy_provider=selection.policy_provider,
        policy_info=policy_info,
        candidate_actions=candidate_actions,
    )
    validate_score_plan_request(
        forge,
        uses_score_planning=selection.uses_score_planning,
        uses_policy_planning=selection.uses_policy_planning,
        uses_mpc_planning=uses_mpc_planning,
        selected_score_provider=selection.score_provider,
        candidate_actions=candidate_actions,
        score_info=score_info,
    )


def validate_policy_plan_request(
    forge: WorldPlanningForge,
    *,
    uses_policy_planning: bool,
    selected_policy_provider: str,
    policy_info: JSONDict | None,
    candidate_actions: Sequence[Action | Sequence[Action]] | None,
) -> None:
    if not uses_policy_planning:
        return
    require_planning_provider_capability(
        forge,
        provider=selected_policy_provider,
        capability="policy",
        planning_label="policy planning",
    )
    require_policy_plan_inputs(policy_info=policy_info, candidate_actions=candidate_actions)


def validate_score_plan_request(
    forge: WorldPlanningForge,
    *,
    uses_score_planning: bool,
    uses_policy_planning: bool,
    uses_mpc_planning: bool,
    selected_score_provider: str,
    candidate_actions: Sequence[Action | Sequence[Action]] | None,
    score_info: JSONDict | None,
) -> None:
    if not uses_score_planning:
        return
    require_planning_provider_capability(
        forge,
        provider=selected_score_provider,
        capability="score",
        planning_label="score-based planning",
    )
    require_score_plan_inputs(
        uses_policy_planning=uses_policy_planning,
        uses_mpc_planning=uses_mpc_planning,
        candidate_actions=candidate_actions,
        score_info=score_info,
    )


def require_planning_provider_capability(
    forge: WorldPlanningForge,
    *,
    provider: str,
    capability: str,
    planning_label: str,
) -> None:
    if forge.provider_profile(provider).capabilities.supports(capability):
        return
    raise WorldForgeError(f"Provider '{provider}' does not support {planning_label}.")


def require_policy_plan_inputs(
    *,
    policy_info: JSONDict | None,
    candidate_actions: Sequence[Action | Sequence[Action]] | None,
) -> None:
    if policy_info is None:
        raise WorldForgeError("Policy planning requires policy_info.")
    if candidate_actions is not None:
        raise WorldForgeError(
            "Policy planning derives candidate actions from the policy provider; do not "
            "pass candidate_actions."
        )


def require_score_plan_inputs(
    *,
    uses_policy_planning: bool,
    uses_mpc_planning: bool = False,
    candidate_actions: Sequence[Action | Sequence[Action]] | None,
    score_info: JSONDict | None,
) -> None:
    if not uses_policy_planning and not uses_mpc_planning and candidate_actions is None:
        raise WorldForgeError(
            "Score-based planning requires candidate_actions unless policy planning "
            "provides candidates."
        )
    if score_info is None:
        raise WorldForgeError("Score-based planning requires score_info.")


def uses_policy_planning(
    *,
    policy_info: JSONDict | None,
    policy_provider: str | None,
) -> bool:
    return policy_info is not None or policy_provider is not None


def uses_score_planning(
    *,
    candidate_actions: Sequence[Action | Sequence[Action]] | None,
    score_provider: str | None,
    score_info: JSONDict | None,
    score_action_candidates: object | None,
) -> bool:
    return any(
        item is not None
        for item in (candidate_actions, score_provider, score_info, score_action_candidates)
    )


def uses_mpc_planning(
    *,
    planner: str,
    planner_config: PlannerConfig | None,
    candidate_encoder: ScoreCandidateEncoder | None,
    goal_info: JSONDict | None,
) -> bool:
    if planner == "latent-mpc":
        return True
    if any(item is not None for item in (planner_config, candidate_encoder, goal_info)):
        raise WorldForgeError("Latent MPC options require planner='latent-mpc'.")
    return False


def validate_mpc_plan_request(
    *,
    uses_mpc_planning: bool,
    max_steps: int,
    planner_config: PlannerConfig | None,
    score_provider: str | None,
    policy_provider: str | None,
    policy_info: JSONDict | None,
    candidate_actions: Sequence[Action | Sequence[Action]] | None,
    score_action_candidates: object | None,
    goal_info: JSONDict | None,
) -> None:
    if not uses_mpc_planning:
        return
    if planner_config is None:
        raise WorldForgeError("Latent MPC planning requires planner_config.")
    if score_provider is None:
        raise WorldForgeError("Latent MPC planning requires an explicit score_provider.")
    require_non_empty_text(
        score_provider,
        name="Latent MPC score_provider",
        message="Latent MPC planning requires a non-empty explicit score_provider.",
    )
    if planner_config.execute_k > max_steps:
        raise WorldForgeError("Latent MPC planner_config.execute_k must be <= max_steps.")
    if goal_info is None:
        raise WorldForgeError("Latent MPC planning requires goal_info.")
    if policy_provider is not None or policy_info is not None:
        raise WorldForgeError("Latent MPC policy warm-start is not implemented yet.")
    if candidate_actions is not None:
        raise WorldForgeError("Latent MPC samples candidate_actions from planner_config.")
    if score_action_candidates is not None:
        raise WorldForgeError("Latent MPC builds score_action_candidates from sampled actions.")


def plan_for_request(
    *,
    forge: WorldPlanningForge,
    snapshot: Callable[[], JSONDict],
    request: PlanRequest,
    resolved_goal: ResolvedPlanGoal,
) -> Plan:
    if request.uses_mpc_planning:
        return plan_with_mpc(forge=forge, request=request, resolved_goal=resolved_goal)
    if request.uses_policy_planning:
        return plan_with_policy(forge=forge, request=request, resolved_goal=resolved_goal)
    if request.uses_score_planning:
        return plan_with_score(forge=forge, request=request, resolved_goal=resolved_goal)
    return plan_with_predictions(
        forge=forge,
        snapshot=snapshot,
        request=request,
        resolved_goal=resolved_goal,
    )


def plan_with_mpc(
    *,
    forge: WorldPlanningForge,
    request: PlanRequest,
    resolved_goal: ResolvedPlanGoal,
) -> Plan:
    if request.score_info is None:
        raise WorldForgeError("Latent MPC planning requires score_info.")
    if request.goal_info is None:
        raise WorldForgeError("Latent MPC planning requires goal_info.")
    if request.planner_config is None:
        raise WorldForgeError("Latent MPC planning requires planner_config.")
    controller = LatentMPCController(
        forge=forge,
        score_provider=request.score_provider,
        config=request.planner_config,
        encoder=request.candidate_encoder,
    )
    step_result = controller.plan_step(
        observation_info=request.score_info,
        goal_info=request.goal_info,
    )
    success_probability, success_probability_source = mpc_plan_success_probability(step_result)
    metadata = mpc_plan_metadata(
        request,
        step_result,
        success_probability_source=success_probability_source,
    )
    return plan_from_actions(
        request,
        resolved_goal,
        provider=request.score_provider,
        actions=step_result.actions[: request.max_steps],
        predicted_states=[],
        success_probability=clamped_probability(success_probability),
        metadata=metadata,
    )


def plan_with_policy(
    *,
    forge: WorldPlanningForge,
    request: PlanRequest,
    resolved_goal: ResolvedPlanGoal,
) -> Plan:
    policy_result = select_policy_actions(forge, request)
    candidate_action_plans = policy_candidate_action_plans(request, policy_result)
    if request.uses_score_planning:
        return plan_with_policy_and_score(
            forge=forge,
            request=request,
            resolved_goal=resolved_goal,
            policy_result=policy_result,
            candidate_action_plans=candidate_action_plans,
        )
    return plan_with_policy_only(
        request=request,
        resolved_goal=resolved_goal,
        policy_result=policy_result,
        candidate_action_plans=candidate_action_plans,
    )


def select_policy_actions(
    forge: WorldPlanningForge,
    request: PlanRequest,
) -> ActionPolicyResult:
    if request.policy_info is None:
        raise WorldForgeError("Policy planning is active but policy_info is missing.")
    return forge.select_actions(request.policy_provider, info=request.policy_info)


def policy_candidate_action_plans(
    request: PlanRequest,
    policy_result: ActionPolicyResult,
) -> list[list[Action]]:
    candidate_action_plans = [
        candidate[: request.max_steps] for candidate in policy_result.action_candidates
    ]
    if not candidate_action_plans:
        raise WorldForgeError(
            f"Provider '{request.policy_provider}' returned no policy action candidates."
        )
    return candidate_action_plans


def plan_with_policy_only(
    *,
    request: PlanRequest,
    resolved_goal: ResolvedPlanGoal,
    policy_result: ActionPolicyResult,
    candidate_action_plans: Sequence[Sequence[Action]],
) -> Plan:
    selected_actions = policy_result.actions[: request.max_steps]
    metadata = policy_plan_metadata(
        request,
        policy_result,
        action_count=len(selected_actions),
        candidate_count=len(candidate_action_plans),
    )
    return plan_from_actions(
        request,
        resolved_goal,
        provider=request.policy_provider,
        actions=selected_actions,
        predicted_states=[],
        success_probability=POLICY_PLAN_DEFAULT_SUCCESS_PROBABILITY,
        metadata=metadata,
    )


def plan_with_policy_and_score(
    *,
    forge: WorldPlanningForge,
    request: PlanRequest,
    resolved_goal: ResolvedPlanGoal,
    policy_result: ActionPolicyResult,
    candidate_action_plans: Sequence[Sequence[Action]],
) -> Plan:
    selection = scored_plan_selection(
        forge,
        request,
        candidate_action_plans,
        policy_provider=request.policy_provider,
    )
    metadata = policy_score_plan_metadata(
        request,
        policy_result,
        selection,
        candidate_count=len(candidate_action_plans),
    )
    return plan_from_actions(
        request,
        resolved_goal,
        provider=request.score_provider,
        actions=selection.actions,
        predicted_states=[],
        success_probability=selection.success_probability,
        metadata=metadata,
    )


def plan_with_score(
    *,
    forge: WorldPlanningForge,
    request: PlanRequest,
    resolved_goal: ResolvedPlanGoal,
) -> Plan:
    candidate_action_plans = score_only_candidate_action_plans(request)
    selection = scored_plan_selection(
        forge,
        request,
        candidate_action_plans,
        max_steps=request.max_steps,
    )
    metadata = score_plan_metadata(
        request,
        selection,
        candidate_count=len(candidate_action_plans),
    )
    return plan_from_actions(
        request,
        resolved_goal,
        provider=request.score_provider,
        actions=selection.actions,
        predicted_states=[],
        success_probability=selection.success_probability,
        metadata=metadata,
    )


def scored_plan_selection(
    forge: WorldPlanningForge,
    request: PlanRequest,
    candidate_action_plans: Sequence[Sequence[Action]],
    *,
    policy_provider: str | None = None,
    max_steps: int | None = None,
) -> ScoredPlanSelection:
    score_result = score_candidate_action_plans(forge, request, candidate_action_plans)
    require_valid_best_score_index(
        score_provider=request.score_provider,
        best_index=score_result.best_index,
        candidate_count=len(candidate_action_plans),
        policy_provider=policy_provider,
    )
    selected_actions = list(candidate_action_plans[score_result.best_index])
    if max_steps is not None:
        selected_actions = selected_actions[:max_steps]
    success_probability, success_probability_source = score_plan_success_probability(score_result)
    return ScoredPlanSelection(
        actions=selected_actions,
        score_result=score_result,
        success_probability=clamped_probability(success_probability),
        success_probability_source=success_probability_source,
    )


def score_candidate_action_plans(
    forge: WorldPlanningForge,
    request: PlanRequest,
    candidate_action_plans: Sequence[Sequence[Action]],
) -> ActionScoreResult:
    if request.score_info is None:
        raise WorldForgeError("Score planning is active but score_info is missing.")
    score_payload = (
        request.score_action_candidates
        if request.score_action_candidates is not None
        else action_plans_to_score_payload(candidate_action_plans)
    )
    score_result = forge.score_actions(
        request.score_provider,
        info=request.score_info,
        action_candidates=score_payload,
    )
    require_score_count_matches_candidates(
        provider=request.score_provider,
        score_result=score_result,
        candidate_count=len(candidate_action_plans),
    )
    return score_result


def plan_with_predictions(
    *,
    forge: WorldPlanningForge,
    snapshot: Callable[[], JSONDict],
    request: PlanRequest,
    resolved_goal: ResolvedPlanGoal,
) -> Plan:
    simulation = simulate_predictive_plan(
        forge,
        initial_state=snapshot(),
        actions=resolved_goal.actions,
        provider=request.provider,
    )
    return plan_from_actions(
        request,
        resolved_goal,
        provider=request.provider,
        actions=resolved_goal.actions,
        predicted_states=simulation.predicted_states,
        success_probability=simulation.success_probability,
        metadata=predictive_plan_metadata(request, resolved_goal, simulation),
        include_execution_provider=False,
    )


def plan_from_actions(
    request: PlanRequest,
    resolved_goal: ResolvedPlanGoal,
    *,
    provider: str,
    actions: Sequence[Action],
    predicted_states: Sequence[JSONDict],
    success_probability: float,
    metadata: JSONDict,
    include_execution_provider: bool = True,
) -> Plan:
    if include_execution_provider and request.execution_provider is not None:
        metadata = {**metadata, "execution_provider": request.execution_provider}
    return Plan(
        goal=resolved_goal.goal,
        goal_spec=resolved_goal.goal_spec,
        planner=request.planner,
        provider=provider,
        actions=actions,
        predicted_states=predicted_states,
        success_probability=success_probability,
        metadata=metadata,
    )


__all__ = [
    "WorldPlanningForge",
    "build_plan_request",
    "normalize_provider_name",
    "plan_execution_provider",
    "plan_world",
]

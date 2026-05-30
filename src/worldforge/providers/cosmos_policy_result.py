"""Result assembly helpers for the Cosmos-Policy provider."""

from __future__ import annotations

from worldforge.models import Action, JSONDict

from .base import ProviderError
from .cosmos_policy_response import CosmosPolicyResponse, _bounded_shape


def cosmos_policy_raw_actions(parsed: CosmosPolicyResponse) -> JSONDict:
    raw_actions: JSONDict = {"actions": parsed.actions}
    if parsed.all_actions:
        raw_actions["all_actions"] = parsed.all_actions
    return raw_actions


def validate_translated_candidate_count(
    *,
    parsed: CosmosPolicyResponse,
    candidate_plans: list[list[Action]],
) -> None:
    if parsed.all_actions and len(candidate_plans) != len(parsed.all_actions):
        raise ProviderError(
            "Cosmos-Policy action translator returned "
            f"{len(candidate_plans)} candidate(s) for "
            f"{len(parsed.all_actions)} raw candidate(s)."
        )
    if not parsed.all_actions and len(candidate_plans) != 1:
        raise ProviderError(
            "Cosmos-Policy action translator must return exactly 1 candidate "
            "when the response omits 'all_actions'."
        )


def cosmos_policy_result_metadata(
    *,
    model: str | None,
    task_description: str,
    expected_action_dim: int | None,
    selected_index: int,
    candidate_count: int,
    action_horizon_override: int | None,
    parsed: CosmosPolicyResponse,
) -> JSONDict:
    return {
        "runtime": "cosmos-policy-server",
        "server_path": "/act",
        "model": model,
        "task_description": task_description,
        "expected_action_dim": expected_action_dim,
        "selected_candidate_index": selected_index,
        "candidate_count": candidate_count,
        "requested_action_horizon": action_horizon_override,
        "provider_info": parsed.provider_info,
        "raw_action_summary": {
            "actions_shape": _bounded_shape(parsed.actions),
            "all_actions_shape": _bounded_shape(parsed.all_actions) if parsed.all_actions else None,
        },
    }


_cosmos_policy_raw_actions = cosmos_policy_raw_actions
_validate_translated_candidate_count = validate_translated_candidate_count
_cosmos_policy_result_metadata = cosmos_policy_result_metadata

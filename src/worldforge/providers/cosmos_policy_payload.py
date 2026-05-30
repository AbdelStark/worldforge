"""Payload validation helpers for the Cosmos-Policy provider."""

from __future__ import annotations

from collections.abc import Sequence

from worldforge.models import (
    JSONDict,
    WorldForgeError,
    require_finite_number,
    require_positive_int,
)

OBSERVATION_FIELDS = (
    "primary_image",
    "left_wrist_image",
    "right_wrist_image",
    "proprio",
)


def optional_positive_float(value: float | int | str | None, *, name: str) -> float | None:
    if value is None:
        return None
    if isinstance(value, str):
        if not value.strip():
            return None
        try:
            parsed = float(value)
        except ValueError:
            raise WorldForgeError(f"{name} must be greater than 0.") from None
        value = parsed
    number = require_finite_number(value, name=name)
    if number <= 0.0:
        raise WorldForgeError(f"{name} must be greater than 0.")
    return number


def optional_host_patterns(
    value: Sequence[str] | str | None, *, name: str
) -> tuple[str, ...] | None:
    if value is None:
        return None
    if isinstance(value, str):
        raw_patterns = [item for item in value.split(",") if item.strip()]
        if not raw_patterns:
            return None
    else:
        raw_patterns = list(value)
    patterns: list[str] = []
    for index, item in enumerate(raw_patterns):
        if not isinstance(item, str) or not item.strip():
            raise WorldForgeError(f"{name}[{index}] must be a non-empty hostname pattern.")
        patterns.append(item.strip().lower())
    if not patterns:
        raise WorldForgeError(f"{name} must contain at least one hostname pattern when provided.")
    return tuple(patterns)


def cosmos_policy_observation(normalized_info: JSONDict) -> JSONDict:
    observation = normalized_info.get("observation")
    if not isinstance(observation, dict) or not observation:
        raise WorldForgeError(
            "Cosmos-Policy policy info.observation must be a non-empty JSON object."
        )
    for field_name in OBSERVATION_FIELDS:
        if field_name not in observation:
            raise WorldForgeError(f"Cosmos-Policy ALOHA observation must include '{field_name}'.")
    return dict(observation)


def cosmos_policy_task_description(normalized_info: JSONDict, observation: JSONDict) -> str:
    if "task_description" in normalized_info:
        task_description = normalized_info["task_description"]
    else:
        task_description = observation.get("task_description")
    if not isinstance(task_description, str) or not task_description.strip():
        raise WorldForgeError(
            "Cosmos-Policy policy info must include a non-empty task_description."
        )
    return task_description.strip()


def validate_cosmos_policy_embodiment_tag(normalized_info: JSONDict) -> None:
    embodiment_tag_value = normalized_info.get("embodiment_tag")
    if embodiment_tag_value is None:
        return
    if not isinstance(embodiment_tag_value, str) or not embodiment_tag_value.strip():
        raise WorldForgeError(
            "Cosmos-Policy policy info.embodiment_tag must be a non-empty string."
        )


def cosmos_policy_options(normalized_info: JSONDict) -> JSONDict | None:
    options = normalized_info.get("options")
    if options is None:
        return None
    if not isinstance(options, dict):
        raise WorldForgeError("Cosmos-Policy policy info.options must be a JSON object.")
    return dict(options)


def cosmos_policy_payload(
    *,
    observation: JSONDict,
    task_description: str,
    options: JSONDict | None,
) -> JSONDict:
    payload = dict(observation)
    payload["task_description"] = task_description
    if not options:
        return payload
    for key, value in options.items():
        if key in payload and key != "action_horizon" and payload[key] != value:
            raise WorldForgeError(
                f"Cosmos-Policy option '{key}' conflicts with the observation payload."
            )
        payload[key] = value
    return payload


def apply_cosmos_policy_return_all(
    *,
    payload: JSONDict,
    normalized_info: JSONDict,
    default_return_all: bool | None,
) -> None:
    if "return_all_query_results" in normalized_info:
        return_all = normalized_info["return_all_query_results"]
        if not isinstance(return_all, bool):
            raise WorldForgeError("Cosmos-Policy return_all_query_results must be a boolean.")
        payload["return_all_query_results"] = return_all
    elif default_return_all is not None:
        payload["return_all_query_results"] = default_return_all


def cosmos_policy_action_horizon(
    *,
    normalized_info: JSONDict,
    observation: JSONDict,
    options: JSONDict | None,
    payload: JSONDict,
) -> int | None:
    action_horizon = action_horizon_from_info_or_payload(
        normalized_info=normalized_info,
        options=options,
        payload=payload,
    )
    validate_observation_options_action_horizon_match(
        observation=observation,
        options=options,
    )
    return action_horizon


def action_horizon_from_info_or_payload(
    *,
    normalized_info: JSONDict,
    options: JSONDict | None,
    payload: JSONDict,
) -> int | None:
    payload_horizon_source = payload_action_horizon_source(options)
    if "action_horizon" in normalized_info:
        action_horizon = require_action_horizon(
            normalized_info["action_horizon"],
            source="info.action_horizon",
        )
        if "action_horizon" in payload:
            validate_payload_action_horizon_matches_info(
                payload=payload,
                payload_horizon_source=payload_horizon_source,
                info_action_horizon=action_horizon,
            )
        return action_horizon
    if "action_horizon" in payload:
        return require_action_horizon(
            payload["action_horizon"],
            source=payload_horizon_source,
        )
    return None


def require_action_horizon(value: object, *, source: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise WorldForgeError(f"Cosmos-Policy {source} must be an integer greater than 0.")
    return require_positive_int(value, name=f"Cosmos-Policy {source}")


def validate_payload_action_horizon_matches_info(
    *,
    payload: JSONDict,
    payload_horizon_source: str,
    info_action_horizon: int,
) -> None:
    payload_action_horizon = require_action_horizon(
        payload["action_horizon"],
        source=payload_horizon_source,
    )
    if payload_action_horizon != info_action_horizon:
        raise WorldForgeError(
            "Cosmos-Policy option 'action_horizon' conflicts with info.action_horizon."
        )


def validate_observation_options_action_horizon_match(
    *,
    observation: JSONDict,
    options: JSONDict | None,
) -> None:
    if "action_horizon" not in observation or options is None or "action_horizon" not in options:
        return
    observation_action_horizon = require_action_horizon(
        observation["action_horizon"],
        source="observation.action_horizon",
    )
    options_action_horizon = require_action_horizon(
        options["action_horizon"],
        source="options.action_horizon",
    )
    if observation_action_horizon != options_action_horizon:
        raise WorldForgeError(
            "Cosmos-Policy option 'action_horizon' conflicts with the observation payload."
        )


def payload_action_horizon_source(options: JSONDict | None) -> str:
    if options is not None and "action_horizon" in options:
        return "options.action_horizon"
    return "observation.action_horizon"


def is_malformed_json_response_error(message: str) -> bool:
    return any(
        marker in message
        for marker in (
            "returned invalid JSON",
            "returned a non-object JSON payload",
            "returned unsupported content type",
        )
    )


_OBSERVATION_FIELDS = OBSERVATION_FIELDS
_optional_positive_float = optional_positive_float
_optional_host_patterns = optional_host_patterns
_cosmos_policy_observation = cosmos_policy_observation
_cosmos_policy_task_description = cosmos_policy_task_description
_validate_cosmos_policy_embodiment_tag = validate_cosmos_policy_embodiment_tag
_cosmos_policy_options = cosmos_policy_options
_cosmos_policy_payload = cosmos_policy_payload
_apply_cosmos_policy_return_all = apply_cosmos_policy_return_all
_cosmos_policy_action_horizon = cosmos_policy_action_horizon
_action_horizon_from_info_or_payload = action_horizon_from_info_or_payload
_require_action_horizon = require_action_horizon
_validate_payload_action_horizon_matches_info = validate_payload_action_horizon_matches_info
_validate_observation_options_action_horizon_match = (
    validate_observation_options_action_horizon_match
)
_payload_action_horizon_source = payload_action_horizon_source
_is_malformed_json_response_error = is_malformed_json_response_error

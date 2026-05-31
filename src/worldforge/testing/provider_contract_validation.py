"""Validation primitives for provider contract helpers."""

from __future__ import annotations

from collections.abc import Callable, Sequence

from worldforge.models import (
    Action,
    ActionPolicyResult,
    ActionScoreResult,
    EmbeddingResult,
    ProviderEvent,
    WorldForgeError,
    dump_json,
    require_finite_number,
    require_positive_int,
    require_probability,
)
from worldforge.providers import PredictionPayload, ProviderError


def expect_provider_error[T](operation_name: str, call: Callable[[], T]) -> None:
    try:
        call()
    except ProviderError:
        return
    msg = f"Provider contract expected '{operation_name}' to raise ProviderError when unavailable."
    raise AssertionError(msg)


def contract_check(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def contract_json(value: object, message: str) -> None:
    try:
        dump_json(value)
    except WorldForgeError as exc:
        raise AssertionError(message) from exc


def invoke_contract[T](
    operation_name: str,
    result_name: str,
    call: Callable[[], T],
) -> T:
    try:
        return call()
    except ProviderError as exc:
        raise AssertionError(
            f"{operation_name} must return a valid {result_name}; provider raised ProviderError: "
            f"{exc}"
        ) from exc
    except WorldForgeError as exc:
        raise AssertionError(f"{operation_name} must return a valid {result_name}: {exc}") from exc


def validate_prediction(provider: str, payload: PredictionPayload) -> None:
    contract_check(
        isinstance(payload, PredictionPayload),
        "predict must return PredictionPayload.",
    )
    try:
        from worldforge._state import validate_world_state_payload as _validate_world_state_payload

        _validate_world_state_payload(payload.state, context="Provider contract prediction state")
    except WorldForgeError as exc:
        raise AssertionError("predict returned invalid world state.") from exc
    contract_check(isinstance(payload.metadata, dict), "predict metadata must be a JSON object.")
    contract_json(payload.metadata, "predict metadata must be JSON serializable.")
    contract_check(isinstance(payload.frames, list), "predict frames must be a list.")
    contract_check(
        all(isinstance(frame, bytes) for frame in payload.frames),
        "predict frames must contain only bytes.",
    )
    _contract_probability(
        payload.confidence,
        name="predict confidence",
        message="predict confidence must be a probability float.",
    )
    _contract_probability(
        payload.physics_score,
        name="predict physics_score",
        message="predict physics_score must be a probability float.",
    )
    latency_ms = _contract_finite_number(
        payload.latency_ms,
        name="predict latency_ms",
        message="predict latency_ms must be finite.",
    )
    contract_check(latency_ms >= 0.0, "predict latency_ms must be non-negative.")
    contract_check(
        payload.metadata.get("provider") == provider,
        "predict metadata provider must match provider name.",
    )


def validate_embedding(provider: str, result: EmbeddingResult) -> None:
    contract_check(isinstance(result, EmbeddingResult), "embed must return EmbeddingResult.")
    contract_check(result.provider == provider, "embed provider must match provider name.")
    contract_check(isinstance(result.model, str) and bool(result.model), "embed model required.")
    contract_check(isinstance(result.vector, list), "embed vector must be a list.")
    contract_check(len(result.vector) >= 1, "embed vector must not be empty.")
    _contract_finite_float_sequence(
        result.vector,
        name="embed vector value",
        message="embed vector values must be finite floats.",
    )


def validate_action_scores(provider: str, result: ActionScoreResult) -> None:
    contract_check(isinstance(result, ActionScoreResult), "score must return ActionScoreResult.")
    contract_check(result.provider == provider, "score provider must match provider name.")
    contract_check(isinstance(result.scores, list), "score scores must be a list.")
    contract_check(bool(result.scores), "score scores must not be empty.")
    _contract_finite_float_sequence(
        result.scores,
        name="score value",
        message="score values must be finite floats.",
    )
    contract_check(
        isinstance(result.best_index, int) and not isinstance(result.best_index, bool),
        "score best_index must be an integer.",
    )
    contract_check(
        0 <= result.best_index < len(result.scores),
        "score best_index must point at a score.",
    )
    contract_check(
        result.best_score == result.scores[result.best_index],
        "score best_score must match scores[best_index].",
    )
    contract_check(isinstance(result.lower_is_better, bool), "score direction flag must be bool.")
    expected_best_score = min(result.scores) if result.lower_is_better else max(result.scores)
    contract_check(
        result.best_score == expected_best_score,
        "score best_index must match lower_is_better direction.",
    )
    contract_check(isinstance(result.metadata, dict), "score metadata must be a JSON object.")
    contract_json(result.to_dict(), "score result must be JSON serializable.")


def validate_action_policy(provider: str, result: ActionPolicyResult) -> None:
    contract_check(
        isinstance(result, ActionPolicyResult),
        "policy must return ActionPolicyResult.",
    )
    contract_check(result.provider == provider, "policy provider must match provider name.")
    contract_check(isinstance(result.actions, list), "policy actions must be a list.")
    contract_check(bool(result.actions), "policy actions must not be empty.")
    contract_check(
        all(isinstance(action, Action) for action in result.actions),
        "policy actions must contain only Action objects.",
    )
    contract_check(
        isinstance(result.raw_actions, dict),
        "policy raw_actions must be a JSON object.",
    )
    if result.action_horizon is not None:
        _contract_positive_int(
            result.action_horizon,
            name="policy action_horizon",
            message="policy action_horizon must be positive when provided.",
        )
    if result.embodiment_tag is not None:
        contract_check(
            isinstance(result.embodiment_tag, str) and bool(result.embodiment_tag.strip()),
            "policy embodiment_tag must be a non-empty string when provided.",
        )
    contract_check(isinstance(result.metadata, dict), "policy metadata must be a JSON object.")
    contract_check(
        isinstance(result.action_candidates, list),
        "policy action_candidates must be a list.",
    )
    contract_check(bool(result.action_candidates), "policy action_candidates must not be empty.")
    for candidate in result.action_candidates:
        contract_check(
            isinstance(candidate, list) and bool(candidate),
            "policy action candidate plans must be non-empty lists.",
        )
        contract_check(
            all(isinstance(action, Action) for action in candidate),
            "policy action candidate plans must contain only Action objects.",
        )
    contract_json(result.to_dict(), "policy result must be JSON serializable.")


def validate_provider_events(
    events: Sequence[ProviderEvent],
    *,
    provider: str | None = None,
) -> None:
    for index, event in enumerate(events):
        contract_check(
            isinstance(event, ProviderEvent),
            f"provider event {index} must be a ProviderEvent.",
        )
        payload = event.to_dict()
        contract_json(payload, f"provider event {index} must be JSON serializable.")
        if provider is not None:
            contract_check(
                payload["provider"] == provider,
                f"provider event {index} provider must match {provider}.",
            )
        rendered = dump_json(payload).lower()
        for forbidden in ("api-secret", "api_secret", "raw-secret", "bearer-secret"):
            contract_check(
                forbidden not in rendered,
                f"provider event {index} appears to expose secret material.",
            )


def _contract_finite_number(value: object, *, name: str, message: str) -> float:
    try:
        return require_finite_number(value, name=name)
    except WorldForgeError as exc:
        raise AssertionError(message) from exc


def _contract_probability(value: object, *, name: str, message: str) -> float:
    try:
        return require_probability(value, name=name)
    except WorldForgeError as exc:
        raise AssertionError(message) from exc


def _contract_positive_int(value: object, *, name: str, message: str) -> int:
    try:
        return require_positive_int(value, name=name)  # type: ignore[arg-type]
    except WorldForgeError as exc:
        raise AssertionError(message) from exc


def _contract_finite_float_sequence(
    values: Sequence[object],
    *,
    name: str,
    message: str,
) -> None:
    for value in values:
        contract_check(isinstance(value, float), message)
        _contract_finite_number(value, name=name, message=message)


__all__ = [
    "contract_check",
    "contract_json",
    "expect_provider_error",
    "invoke_contract",
    "validate_action_policy",
    "validate_action_scores",
    "validate_embedding",
    "validate_prediction",
    "validate_provider_events",
]

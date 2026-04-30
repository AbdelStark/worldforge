"""Reusable provider contract helpers."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field

from worldforge.models import (
    Action,
    ActionPolicyResult,
    ActionScoreResult,
    BBox,
    EmbeddingResult,
    JSONDict,
    Position,
    ProviderEvent,
    ProviderHealth,
    ProviderProfile,
    ReasoningResult,
    SceneObject,
    VideoClip,
    WorldForgeError,
    dump_json,
)
from worldforge.providers import BaseProvider, PredictionPayload, ProviderError


def sample_contract_action() -> Action:
    """Return a deterministic action for provider contract checks."""

    return Action.move_to(0.25, 0.5, 0.0, speed=1.0)


def sample_contract_world_state() -> JSONDict:
    """Return a minimal world-state payload for provider contract checks."""

    cube = SceneObject(
        "contract-cube",
        Position(0.0, 0.5, 0.0),
        BBox(Position(-0.05, 0.45, -0.05), Position(0.05, 0.55, 0.05)),
        is_graspable=True,
    )
    return {
        "schema_version": 1,
        "id": "world_contract",
        "name": "contract-world",
        "provider": "contract",
        "description": "World state used for provider contract checks.",
        "step": 0,
        "scene": {"objects": {cube.id: cube.to_dict()}},
        "metadata": {"name": "contract-world"},
    }


def sample_contract_policy_info() -> JSONDict:
    """Return a minimal embodied-policy observation payload for contract checks."""

    return {
        "observation": {
            "video": {
                "front": [[[[[0, 0, 0]]]]],
            },
            "state": {
                "eef": [[[0.0, 0.5, 0.0]]],
            },
            "language": {
                "task": [["move the object"]],
            },
        },
        "action_horizon": 1,
    }


@dataclass(slots=True)
class ProviderContractReport:
    """Summary of executed provider contract checks."""

    provider: str
    configured: bool
    profile: ProviderProfile
    health: ProviderHealth
    exercised_operations: list[str] = field(default_factory=list)

    def to_dict(self) -> JSONDict:
        return {
            "provider": self.provider,
            "configured": self.configured,
            "profile": self.profile.to_dict(),
            "health": self.health.to_dict(),
            "exercised_operations": list(self.exercised_operations),
        }


def _expect_provider_error[T](operation_name: str, call: Callable[[], T]) -> None:
    try:
        call()
    except ProviderError:
        return
    msg = f"Provider contract expected '{operation_name}' to raise ProviderError when unavailable."
    raise AssertionError(msg)


def _contract_check(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def _contract_json(value: object, message: str) -> None:
    try:
        dump_json(value)
    except WorldForgeError as exc:
        raise AssertionError(message) from exc


def _validate_prediction(provider: str, payload: PredictionPayload) -> None:
    _contract_check(
        isinstance(payload, PredictionPayload),
        "predict must return PredictionPayload.",
    )
    try:
        from worldforge.framework import _validate_world_state_payload

        _validate_world_state_payload(payload.state, context="Provider contract prediction state")
    except WorldForgeError as exc:
        raise AssertionError("predict returned invalid world state.") from exc
    _contract_check(isinstance(payload.metadata, dict), "predict metadata must be a JSON object.")
    _contract_json(payload.metadata, "predict metadata must be JSON serializable.")
    _contract_check(isinstance(payload.frames, list), "predict frames must be a list.")
    _contract_check(
        all(isinstance(frame, bytes) for frame in payload.frames),
        "predict frames must contain only bytes.",
    )
    _contract_check(
        isinstance(payload.confidence, float) and 0.0 <= payload.confidence <= 1.0,
        "predict confidence must be a probability float.",
    )
    _contract_check(
        isinstance(payload.physics_score, float) and 0.0 <= payload.physics_score <= 1.0,
        "predict physics_score must be a probability float.",
    )
    _contract_check(payload.latency_ms >= 0.0, "predict latency_ms must be non-negative.")
    _contract_check(
        payload.metadata.get("provider") == provider,
        "predict metadata provider must match provider name.",
    )


def _validate_reasoning(provider: str, result: ReasoningResult) -> None:
    _contract_check(isinstance(result, ReasoningResult), "reason must return ReasoningResult.")
    _contract_check(result.provider == provider, "reason provider must match provider name.")
    _contract_check(
        isinstance(result.answer, str) and bool(result.answer),
        "reason answer required.",
    )
    _contract_check(0.0 <= result.confidence <= 1.0, "reason confidence must be a probability.")
    _contract_check(isinstance(result.evidence, list), "reason evidence must be a list.")


def _validate_embedding(provider: str, result: EmbeddingResult) -> None:
    _contract_check(isinstance(result, EmbeddingResult), "embed must return EmbeddingResult.")
    _contract_check(result.provider == provider, "embed provider must match provider name.")
    _contract_check(isinstance(result.model, str) and bool(result.model), "embed model required.")
    _contract_check(isinstance(result.vector, list), "embed vector must be a list.")
    _contract_check(len(result.vector) >= 1, "embed vector must not be empty.")
    _contract_check(
        all(isinstance(value, float) for value in result.vector),
        "embed vector values must be floats.",
    )


def _validate_clip(clip: VideoClip) -> None:
    _contract_check(isinstance(clip, VideoClip), "media operation must return VideoClip.")
    _contract_check(isinstance(clip.frames, list), "VideoClip frames must be a list.")
    _contract_check(
        all(isinstance(frame, bytes) for frame in clip.frames),
        "VideoClip frames must contain only bytes.",
    )
    _contract_check(clip.fps > 0.0, "VideoClip fps must be positive.")
    _contract_check(clip.resolution[0] > 0, "VideoClip width must be positive.")
    _contract_check(clip.resolution[1] > 0, "VideoClip height must be positive.")
    _contract_check(clip.duration_seconds >= 0.0, "VideoClip duration must be non-negative.")
    _contract_check(isinstance(clip.metadata, dict), "VideoClip metadata must be a JSON object.")
    _contract_json(clip.metadata, "VideoClip metadata must be JSON serializable.")


def _validate_action_scores(provider: str, result: ActionScoreResult) -> None:
    _contract_check(isinstance(result, ActionScoreResult), "score must return ActionScoreResult.")
    _contract_check(result.provider == provider, "score provider must match provider name.")
    _contract_check(isinstance(result.scores, list), "score scores must be a list.")
    _contract_check(bool(result.scores), "score scores must not be empty.")
    _contract_check(
        all(isinstance(score, float) for score in result.scores),
        "score values must be floats.",
    )
    _contract_check(isinstance(result.best_index, int), "score best_index must be an integer.")
    _contract_check(
        0 <= result.best_index < len(result.scores),
        "score best_index must point at a score.",
    )
    _contract_check(
        result.best_score == result.scores[result.best_index],
        "score best_score must match scores[best_index].",
    )
    _contract_check(isinstance(result.lower_is_better, bool), "score direction flag must be bool.")
    _contract_check(isinstance(result.metadata, dict), "score metadata must be a JSON object.")


def _validate_action_policy(provider: str, result: ActionPolicyResult) -> None:
    _contract_check(
        isinstance(result, ActionPolicyResult),
        "policy must return ActionPolicyResult.",
    )
    _contract_check(result.provider == provider, "policy provider must match provider name.")
    _contract_check(isinstance(result.actions, list), "policy actions must be a list.")
    _contract_check(bool(result.actions), "policy actions must not be empty.")
    _contract_check(
        all(isinstance(action, Action) for action in result.actions),
        "policy actions must contain only Action objects.",
    )
    _contract_check(
        isinstance(result.raw_actions, dict),
        "policy raw_actions must be a JSON object.",
    )
    _contract_check(
        result.action_horizon is None or result.action_horizon >= 1,
        "policy action_horizon must be positive when provided.",
    )
    _contract_check(isinstance(result.metadata, dict), "policy metadata must be a JSON object.")
    _contract_check(
        isinstance(result.action_candidates, list),
        "policy action_candidates must be a list.",
    )
    _contract_check(bool(result.action_candidates), "policy action_candidates must not be empty.")
    _contract_check(
        all(candidate for candidate in result.action_candidates),
        "policy action candidate plans must not be empty.",
    )


def assert_predict_conformance(
    provider: BaseProvider,
    *,
    world_state: JSONDict | None = None,
    action: Action | None = None,
    steps: int = 2,
) -> PredictionPayload:
    """Assert that a provider's predict capability returns a valid payload."""

    if not provider.profile().capabilities.predict:
        raise AssertionError("Provider does not declare the predict capability.")
    sample_state = world_state or sample_contract_world_state()
    sample_action = action or sample_contract_action()
    prediction = provider.predict(sample_state, sample_action, steps)
    _validate_prediction(provider.name, prediction)
    return prediction


def assert_reason_conformance(
    provider: BaseProvider,
    *,
    query: str = "How many objects are in the scene?",
    world_state: JSONDict | None = None,
) -> ReasoningResult:
    """Assert that a provider's reason capability returns a valid result."""

    if not provider.profile().capabilities.reason:
        raise AssertionError("Provider does not declare the reason capability.")
    result = provider.reason(query, world_state=world_state or sample_contract_world_state())
    _validate_reasoning(provider.name, result)
    return result


def assert_embed_conformance(
    provider: BaseProvider,
    *,
    text: str = "contract vector",
) -> EmbeddingResult:
    """Assert that a provider's embed capability returns a valid result."""

    if not provider.profile().capabilities.embed:
        raise AssertionError("Provider does not declare the embed capability.")
    result = provider.embed(text=text)
    _validate_embedding(provider.name, result)
    return result


def assert_generate_conformance(
    provider: BaseProvider,
    *,
    prompt: str = "contract prompt",
    duration_seconds: float = 1.0,
) -> VideoClip:
    """Assert that a provider's generate capability returns a valid clip."""

    if not provider.profile().capabilities.generate:
        raise AssertionError("Provider does not declare the generate capability.")
    clip = provider.generate(prompt, duration_seconds=duration_seconds)
    _validate_clip(clip)
    return clip


def assert_transfer_conformance(
    provider: BaseProvider,
    *,
    clip: VideoClip | None = None,
    width: int = 48,
    height: int = 48,
    fps: float = 12.0,
) -> VideoClip:
    """Assert that a provider's transfer capability returns a valid clip."""

    if not provider.profile().capabilities.transfer:
        raise AssertionError("Provider does not declare the transfer capability.")
    transfer_input = clip or VideoClip(
        frames=[b"contract-frame"],
        fps=8.0,
        resolution=(64, 64),
        duration_seconds=0.125,
        metadata={"provider": provider.name},
    )
    result = provider.transfer(transfer_input, width=width, height=height, fps=fps)
    _validate_clip(result)
    return result


def assert_score_conformance(
    provider: BaseProvider,
    *,
    info: JSONDict,
    action_candidates: object,
) -> ActionScoreResult:
    """Assert that a provider's score capability returns valid finite scores."""

    if not provider.profile().capabilities.score:
        raise AssertionError("Provider does not declare the score capability.")
    result = provider.score_actions(info=info, action_candidates=action_candidates)
    _validate_action_scores(provider.name, result)
    return result


def assert_policy_conformance(
    provider: BaseProvider,
    *,
    info: JSONDict | None = None,
) -> ActionPolicyResult:
    """Assert that a provider's policy capability returns executable actions."""

    if not provider.profile().capabilities.policy:
        raise AssertionError("Provider does not declare the policy capability.")
    result = provider.select_actions(info=info or sample_contract_policy_info())
    _validate_action_policy(provider.name, result)
    return result


def assert_provider_events_conform(
    events: Sequence[ProviderEvent],
    *,
    provider: str | None = None,
) -> None:
    """Assert that captured provider events are JSON-native and redaction-safe."""

    for index, event in enumerate(events):
        _contract_check(
            isinstance(event, ProviderEvent),
            f"provider event {index} must be a ProviderEvent.",
        )
        payload = event.to_dict()
        _contract_json(payload, f"provider event {index} must be JSON serializable.")
        if provider is not None:
            _contract_check(
                payload["provider"] == provider,
                f"provider event {index} provider must match {provider}.",
            )
        rendered = dump_json(payload).lower()
        for forbidden in ("api-secret", "api_secret", "raw-secret", "bearer-secret"):
            _contract_check(
                forbidden not in rendered,
                f"provider event {index} appears to expose secret material.",
            )


def assert_provider_contract(
    provider: BaseProvider,
    *,
    world_state: JSONDict | None = None,
    action: Action | None = None,
    policy_info: JSONDict | None = None,
    score_info: JSONDict | None = None,
    score_action_candidates: object | None = None,
) -> ProviderContractReport:
    """Assert that a provider obeys the WorldForge adapter contract.

    This helper is intended for provider package tests. It validates metadata,
    health reporting, and either successful execution or clear credential errors
    for every declared capability.
    """

    profile = provider.profile()
    info = provider.info()
    health = provider.health()
    configured = provider.configured()

    _contract_check(profile.name == provider.name, "profile name must match provider name.")
    _contract_check(info.name == provider.name, "provider info name must match provider name.")
    _contract_check(
        info.description == profile.description,
        "provider info description must match profile description.",
    )
    _contract_check(
        info.is_local == profile.is_local,
        "provider info locality must match profile locality.",
    )
    _contract_check(
        sorted(info.capabilities.enabled_names()) == sorted(profile.supported_tasks),
        "provider info capabilities must match profile supported_tasks.",
    )
    _contract_check(health.name == provider.name, "provider health name must match provider name.")
    if health.healthy:
        _contract_check(configured, "healthy provider must report configured=True.")
    if not configured and profile.requires_credentials:
        _contract_check(
            health.healthy is False,
            "credential-gated unconfigured provider must report unhealthy health.",
        )
    if profile.capabilities.plan:
        _contract_check(
            profile.capabilities.predict,
            "provider-level plan capability requires predict capability.",
        )

    sample_state = world_state or sample_contract_world_state()
    sample_action = action or sample_contract_action()
    report = ProviderContractReport(
        provider=provider.name,
        configured=configured,
        profile=profile,
        health=health,
    )
    can_invoke = configured

    if profile.capabilities.predict:
        if can_invoke:
            assert_predict_conformance(
                provider,
                world_state=sample_state,
                action=sample_action,
                steps=2,
            )
            report.exercised_operations.append("predict")
        else:
            _expect_provider_error(
                "predict",
                lambda: provider.predict(sample_state, sample_action, 2),
            )

    if profile.capabilities.reason:
        if can_invoke:
            assert_reason_conformance(
                provider,
                query="How many objects are in the scene?",
                world_state=sample_state,
            )
            report.exercised_operations.append("reason")
        else:
            _expect_provider_error(
                "reason",
                lambda: provider.reason(
                    "How many objects are in the scene?",
                    world_state=sample_state,
                ),
            )

    if profile.capabilities.embed:
        if can_invoke:
            assert_embed_conformance(provider, text="contract vector")
            report.exercised_operations.append("embed")
        else:
            _expect_provider_error("embed", lambda: provider.embed(text="contract vector"))

    generated_clip: VideoClip | None = None
    if profile.capabilities.generate:
        if can_invoke:
            generated_clip = assert_generate_conformance(provider)
            report.exercised_operations.append("generate")
        else:
            _expect_provider_error(
                "generate",
                lambda: provider.generate("contract prompt", duration_seconds=1.0),
            )

    if profile.capabilities.transfer:
        if can_invoke:
            assert_transfer_conformance(provider, clip=generated_clip)
            report.exercised_operations.append("transfer")
        else:
            transfer_input = generated_clip or VideoClip(
                frames=[b"contract-frame"],
                fps=8.0,
                resolution=(64, 64),
                duration_seconds=0.125,
                metadata={"provider": provider.name},
            )
            _expect_provider_error(
                "transfer",
                lambda: provider.transfer(transfer_input, width=48, height=48, fps=12.0),
            )

    if profile.capabilities.score:
        if can_invoke:
            if score_info is None or score_action_candidates is None:
                raise AssertionError(
                    "Provider contract requires score_info and score_action_candidates for "
                    "configured score providers."
                )
            assert_score_conformance(
                provider,
                info=score_info,
                action_candidates=score_action_candidates,
            )
            report.exercised_operations.append("score")
        else:
            _expect_provider_error(
                "score",
                lambda: provider.score_actions(
                    info=score_info or {},
                    action_candidates=[]
                    if score_action_candidates is None
                    else score_action_candidates,
                ),
            )

    if profile.capabilities.policy:
        if can_invoke:
            assert_policy_conformance(provider, info=policy_info or sample_contract_policy_info())
            report.exercised_operations.append("policy")
        else:
            _expect_provider_error(
                "policy",
                lambda: provider.select_actions(info=policy_info or sample_contract_policy_info()),
            )

    return report

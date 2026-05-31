"""Reusable provider contract helpers."""

from __future__ import annotations

from collections.abc import Sequence
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
    SceneObject,
)
from worldforge.providers import BaseProvider, PredictionPayload
from worldforge.testing.provider_contract_validation import (
    contract_check as _contract_check,
)
from worldforge.testing.provider_contract_validation import (
    expect_provider_error as _expect_provider_error,
)
from worldforge.testing.provider_contract_validation import (
    invoke_contract as _invoke_contract,
)
from worldforge.testing.provider_contract_validation import (
    validate_action_policy as _validate_action_policy,
)
from worldforge.testing.provider_contract_validation import (
    validate_action_scores as _validate_action_scores,
)
from worldforge.testing.provider_contract_validation import (
    validate_embedding as _validate_embedding,
)
from worldforge.testing.provider_contract_validation import (
    validate_prediction as _validate_prediction,
)
from worldforge.testing.provider_contract_validation import (
    validate_provider_events as _validate_provider_events,
)


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


@dataclass(slots=True)
class _ProviderContractInputs:
    world_state: JSONDict
    action: Action
    policy_info: JSONDict | None
    score_info: JSONDict | None
    score_action_candidates: object | None


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
    prediction = _invoke_contract(
        "predict",
        "PredictionPayload",
        lambda: provider.predict(sample_state, sample_action, steps),
    )
    _validate_prediction(provider.name, prediction)
    return prediction


def assert_embed_conformance(
    provider: BaseProvider,
    *,
    text: str = "contract vector",
) -> EmbeddingResult:
    """Assert that a provider's embed capability returns a valid result."""

    if not provider.profile().capabilities.embed:
        raise AssertionError("Provider does not declare the embed capability.")
    result = _invoke_contract("embed", "EmbeddingResult", lambda: provider.embed(text=text))
    _validate_embedding(provider.name, result)
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
    result = _invoke_contract(
        "score",
        "ActionScoreResult",
        lambda: provider.score_actions(info=info, action_candidates=action_candidates),
    )
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
    result = _invoke_contract(
        "policy",
        "ActionPolicyResult",
        lambda: provider.select_actions(info=info or sample_contract_policy_info()),
    )
    _validate_action_policy(provider.name, result)
    return result


def assert_provider_events_conform(
    events: Sequence[ProviderEvent],
    *,
    provider: str | None = None,
) -> None:
    """Assert that captured provider events are JSON-native and redaction-safe."""

    _validate_provider_events(events, provider=provider)


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

    report = assert_provider_metadata_conformance(provider)
    inputs = _provider_contract_inputs(
        world_state=world_state,
        action=action,
        policy_info=policy_info,
        score_info=score_info,
        score_action_candidates=score_action_candidates,
    )
    can_invoke = report.configured

    _check_predict_contract(provider, report, inputs, can_invoke=can_invoke)
    _check_embed_contract(provider, report, can_invoke=can_invoke)
    _check_score_contract(provider, report, inputs, can_invoke=can_invoke)
    _check_policy_contract(provider, report, inputs, can_invoke=can_invoke)

    return report


def _provider_contract_inputs(
    *,
    world_state: JSONDict | None,
    action: Action | None,
    policy_info: JSONDict | None,
    score_info: JSONDict | None,
    score_action_candidates: object | None,
) -> _ProviderContractInputs:
    return _ProviderContractInputs(
        world_state=world_state or sample_contract_world_state(),
        action=action or sample_contract_action(),
        policy_info=policy_info,
        score_info=score_info,
        score_action_candidates=score_action_candidates,
    )


def _check_predict_contract(
    provider: BaseProvider,
    report: ProviderContractReport,
    inputs: _ProviderContractInputs,
    *,
    can_invoke: bool,
) -> None:
    if not report.profile.capabilities.predict:
        return
    if can_invoke:
        assert_predict_conformance(
            provider,
            world_state=inputs.world_state,
            action=inputs.action,
            steps=2,
        )
        report.exercised_operations.append("predict")
        return
    _expect_provider_error(
        "predict",
        lambda: provider.predict(inputs.world_state, inputs.action, 2),
    )


def _check_embed_contract(
    provider: BaseProvider,
    report: ProviderContractReport,
    *,
    can_invoke: bool,
) -> None:
    if not report.profile.capabilities.embed:
        return
    if can_invoke:
        assert_embed_conformance(provider, text="contract vector")
        report.exercised_operations.append("embed")
        return
    _expect_provider_error("embed", lambda: provider.embed(text="contract vector"))


def _check_score_contract(
    provider: BaseProvider,
    report: ProviderContractReport,
    inputs: _ProviderContractInputs,
    *,
    can_invoke: bool,
) -> None:
    if not report.profile.capabilities.score:
        return
    if can_invoke:
        _require_score_contract_inputs(inputs)
        assert_score_conformance(
            provider,
            info=inputs.score_info,
            action_candidates=inputs.score_action_candidates,
        )
        report.exercised_operations.append("score")
        return
    _expect_provider_error(
        "score",
        lambda: provider.score_actions(
            info=inputs.score_info or {},
            action_candidates=_score_action_candidates_or_empty(inputs),
        ),
    )


def _require_score_contract_inputs(inputs: _ProviderContractInputs) -> None:
    if inputs.score_info is not None and inputs.score_action_candidates is not None:
        return
    raise AssertionError(
        "Provider contract requires score_info and score_action_candidates for "
        "configured score providers."
    )


def _score_action_candidates_or_empty(inputs: _ProviderContractInputs) -> object:
    if inputs.score_action_candidates is None:
        return []
    return inputs.score_action_candidates


def _check_policy_contract(
    provider: BaseProvider,
    report: ProviderContractReport,
    inputs: _ProviderContractInputs,
    *,
    can_invoke: bool,
) -> None:
    if not report.profile.capabilities.policy:
        return
    info = inputs.policy_info or sample_contract_policy_info()
    if can_invoke:
        assert_policy_conformance(provider, info=info)
        report.exercised_operations.append("policy")
        return
    _expect_provider_error("policy", lambda: provider.select_actions(info=info))


def assert_provider_metadata_conformance(provider: BaseProvider) -> ProviderContractReport:
    """Assert that provider profile, info, health, and capability metadata agree."""

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
    return ProviderContractReport(
        provider=provider.name,
        configured=configured,
        profile=profile,
        health=health,
    )

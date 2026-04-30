from __future__ import annotations

import inspect

import pytest

import worldforge.testing.providers as provider_testing
from worldforge import Action, ActionPolicyResult, ActionScoreResult, ProviderCapabilities
from worldforge.models import ProviderEvent, ProviderHealth
from worldforge.providers import (
    BaseProvider,
    CosmosProvider,
    GenieProvider,
    JepaProvider,
    MockProvider,
    PredictionPayload,
    ProviderError,
    ProviderProfileSpec,
)
from worldforge.testing import (
    assert_generate_conformance,
    assert_policy_conformance,
    assert_predict_conformance,
    assert_provider_contract,
    assert_provider_events_conform,
    assert_score_conformance,
    assert_transfer_conformance,
)


def test_mock_provider_passes_contract_checks() -> None:
    provider = MockProvider()
    report = assert_provider_contract(provider)

    assert report.configured is True
    assert set(report.exercised_operations) == {
        "predict",
        "reason",
        "embed",
        "generate",
        "transfer",
    }
    assert_predict_conformance(provider)
    generated = assert_generate_conformance(provider)
    assert_transfer_conformance(provider, clip=generated)


def test_provider_contract_uses_explicit_failure_for_invalid_prediction_state() -> None:
    class BadPredictionProvider(BaseProvider):
        def __init__(self) -> None:
            super().__init__(
                name="bad-predict",
                capabilities=ProviderCapabilities(predict=True),
                profile=ProviderProfileSpec(description="Invalid prediction provider"),
            )

        def predict(self, world_state, action, steps) -> PredictionPayload:
            return PredictionPayload(
                state={"scene": {"objects": {}}},
                confidence=0.5,
                physics_score=0.5,
                frames=[],
                metadata={"provider": self.name},
                latency_ms=0.1,
            )

    with pytest.raises(AssertionError, match="invalid world state"):
        assert_provider_contract(BadPredictionProvider())


class FakeScoreProvider(BaseProvider):
    def __init__(self) -> None:
        super().__init__(
            name="fake-score",
            capabilities=ProviderCapabilities(score=True),
            profile=ProviderProfileSpec(
                description="Contract score provider",
                is_local=True,
                deterministic=True,
                requires_credentials=False,
            ),
        )

    def health(self) -> ProviderHealth:
        return ProviderHealth(name=self.name, healthy=True, latency_ms=0.1, details="configured")

    def score_actions(self, *, info, action_candidates) -> ActionScoreResult:
        return ActionScoreResult(
            provider=self.name,
            scores=[0.4, 0.1],
            best_index=1,
            metadata={"fixture": info["fixture"], "candidates": len(action_candidates)},
        )


class FakePolicyProvider(BaseProvider):
    def __init__(self) -> None:
        super().__init__(
            name="fake-policy",
            capabilities=ProviderCapabilities(policy=True),
            profile=ProviderProfileSpec(
                description="Contract policy provider",
                is_local=True,
                deterministic=True,
                requires_credentials=False,
            ),
        )

    def health(self) -> ProviderHealth:
        return ProviderHealth(name=self.name, healthy=True, latency_ms=0.1, details="configured")

    def select_actions(self, *, info) -> ActionPolicyResult:
        action = Action.move_to(0.1, 0.2, 0.3)
        return ActionPolicyResult(
            provider=self.name,
            actions=[action],
            raw_actions={"fixture": info["fixture"]},
            action_candidates=[[action]],
            metadata={"runtime": "test"},
        )


def test_capability_specific_score_and_policy_helpers() -> None:
    score = assert_score_conformance(
        FakeScoreProvider(),
        info={"fixture": "score"},
        action_candidates=[["a"], ["b"]],
    )
    policy = assert_policy_conformance(FakePolicyProvider(), info={"fixture": "policy"})

    assert score.best_score == 0.1
    assert policy.actions == [Action.move_to(0.1, 0.2, 0.3)]


def test_provider_event_conformance_helper_rejects_secret_material() -> None:
    assert_provider_events_conform(
        [
            ProviderEvent(
                provider="runway",
                operation="download",
                phase="success",
                target="https://example.test/artifact.mp4?token=api-secret",
                metadata={"status": "ok"},
            )
        ],
        provider="runway",
    )

    with pytest.raises(AssertionError, match="secret material"):
        assert_provider_events_conform(
            [
                ProviderEvent(
                    provider="runway",
                    operation="download",
                    phase="success",
                    metadata={"safe": "raw-secret"},
                )
            ]
        )


def test_provider_conformance_helpers_do_not_use_bare_assert_statements() -> None:
    source = inspect.getsource(provider_testing)
    helper_source = source.split("def assert_predict_conformance", 1)[1]

    assert "\n    assert " not in helper_source


def test_scaffold_provider_reports_clear_unconfigured_contract(monkeypatch) -> None:
    monkeypatch.delenv("COSMOS_BASE_URL", raising=False)

    report = assert_provider_contract(CosmosProvider())

    assert report.configured is False
    assert report.health.healthy is False
    assert report.exercised_operations == []


def test_configured_scaffold_remote_providers_stay_fail_closed(monkeypatch) -> None:
    monkeypatch.setenv("JEPA_MODEL_PATH", "/tmp/jepa-model")
    monkeypatch.setenv("GENIE_API_KEY", "genie-test-key")
    monkeypatch.delenv("WORLDFORGE_ENABLE_SCAFFOLD_SURROGATES", raising=False)

    jepa_report = assert_provider_contract(JepaProvider())
    assert jepa_report.configured is True
    assert jepa_report.exercised_operations == []

    genie_report = assert_provider_contract(GenieProvider())
    assert genie_report.configured is True
    assert genie_report.exercised_operations == []


def test_scaffold_surrogate_requires_explicit_local_opt_in(monkeypatch) -> None:
    monkeypatch.setenv("JEPA_MODEL_PATH", "/tmp/jepa-model")
    monkeypatch.delenv("WORLDFORGE_ENABLE_SCAFFOLD_SURROGATES", raising=False)

    with pytest.raises(ProviderError, match="WORLDFORGE_ENABLE_SCAFFOLD_SURROGATES"):
        JepaProvider().embed(text="cube")

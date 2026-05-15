from __future__ import annotations

import importlib.util
import inspect
import json
import sys
from pathlib import Path

import pytest

import worldforge.testing.providers as provider_testing
from worldforge import Action, ActionPolicyResult, ActionScoreResult, ProviderCapabilities
from worldforge.cli import main as worldforge_main
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
    assert_embed_conformance,
    assert_generate_conformance,
    assert_policy_conformance,
    assert_predict_conformance,
    assert_provider_contract,
    assert_provider_events_conform,
    assert_reason_conformance,
    assert_score_conformance,
    assert_transfer_conformance,
    load_capability_fixture,
)

_ROOT = Path(__file__).resolve().parents[1]
_DEMO_SCRIPT = _ROOT / "scripts" / "demo_showcases.py"
_DEMO_SPEC = importlib.util.spec_from_file_location(
    "demo_showcases_for_provider_contract_tests",
    _DEMO_SCRIPT,
)
assert _DEMO_SPEC is not None
_demo_showcases = importlib.util.module_from_spec(_DEMO_SPEC)
assert _DEMO_SPEC.loader is not None
sys.modules[_DEMO_SPEC.name] = _demo_showcases
_DEMO_SPEC.loader.exec_module(_demo_showcases)


def _gallery_entry(entry_id: str) -> dict[str, object]:
    entries = {
        str(entry["id"]): entry
        for entry in _demo_showcases.build_provider_failure_gallery_entries()
    }
    return entries[entry_id]


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


class BrokenContractProvider(BaseProvider):
    def __init__(self, *, event_handler=None) -> None:
        super().__init__(
            name="broken-contract",
            capabilities=ProviderCapabilities(predict=True),
            profile=ProviderProfileSpec(
                description="Fixture provider that advertises a broken predict surface",
                is_local=True,
                deterministic=True,
            ),
            event_handler=event_handler,
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


def make_broken_contract_provider(event_handler=None) -> BrokenContractProvider:
    return BrokenContractProvider(event_handler=event_handler)


class RemoteConfiguredPredictProvider(BaseProvider):
    def __init__(self, *, event_handler=None) -> None:
        super().__init__(
            name="remote-contract",
            capabilities=ProviderCapabilities(predict=True),
            profile=ProviderProfileSpec(
                description="Configured remote fixture for host-owned skip evidence",
                is_local=False,
                deterministic=False,
                requires_credentials=False,
            ),
            event_handler=event_handler,
        )

    def predict(self, world_state, action, steps) -> PredictionPayload:
        raise AssertionError("remote predict should require --live before invocation")


def make_remote_configured_predict_provider(event_handler=None) -> RemoteConfiguredPredictProvider:
    return RemoteConfiguredPredictProvider(event_handler=event_handler)


def test_capability_specific_score_and_policy_helpers() -> None:
    score = assert_score_conformance(
        FakeScoreProvider(),
        info={"fixture": "score"},
        action_candidates=[["a"], ["b"]],
    )
    policy = assert_policy_conformance(FakePolicyProvider(), info={"fixture": "policy"})

    assert score.best_score == 0.1
    assert policy.actions == [Action.move_to(0.1, 0.2, 0.3)]


def test_corpus_valid_baselines_pass_mock_provider_conformance() -> None:
    provider = MockProvider()

    predict_fx = load_capability_fixture("predict", "valid_baseline")
    assert_predict_conformance(
        provider,
        world_state=predict_fx.payload["world_state"],
        action=Action.from_dict(predict_fx.payload["action"]),
        steps=predict_fx.payload["steps"],
    )

    reason_fx = load_capability_fixture("reason", "valid_baseline")
    assert_reason_conformance(
        provider,
        query=reason_fx.payload["query"],
        world_state=reason_fx.payload["world_state"],
    )

    embed_fx = load_capability_fixture("embed", "valid_baseline")
    assert_embed_conformance(provider, text=embed_fx.payload["text"])

    generate_fx = load_capability_fixture("generate", "valid_baseline")
    assert_generate_conformance(
        provider,
        prompt=generate_fx.payload["prompt"],
        duration_seconds=generate_fx.payload["duration_seconds"],
    )


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
    monkeypatch.setenv("GENIE_API_KEY", "genie-test-key")
    monkeypatch.delenv("WORLDFORGE_ENABLE_SCAFFOLD_SURROGATES", raising=False)

    genie_report = assert_provider_contract(GenieProvider())
    assert genie_report.configured is True
    assert genie_report.exercised_operations == []


def test_jepa_no_longer_exposes_scaffold_surrogate(monkeypatch) -> None:
    monkeypatch.setenv("JEPA_MODEL_PATH", "/tmp/jepa-model")
    monkeypatch.delenv("WORLDFORGE_ENABLE_SCAFFOLD_SURROGATES", raising=False)

    provider = JepaProvider()
    assert provider.configured() is False
    assert provider.profile().capabilities.enabled_names() == ["score"]

    with pytest.raises(ProviderError, match="does not implement embed"):
        JepaProvider().embed(text="cube")


def test_provider_failure_gallery_matches_contract_failures(monkeypatch) -> None:
    invalid_entry = _gallery_entry("mock-invalid-prediction-state")
    with pytest.raises(AssertionError) as invalid_error:
        assert_provider_contract(BrokenContractProvider())
    assert str(invalid_entry["expected_error"]) in str(invalid_error.value)

    secret_entry = _gallery_entry("provider-event-secret-material")
    with pytest.raises(AssertionError) as secret_error:
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
    assert str(secret_entry["expected_error"]) in str(secret_error.value)

    unsupported_entry = _gallery_entry("genie-scaffold-fail-closed")
    monkeypatch.setenv("GENIE_API_KEY", "genie-test-key")
    monkeypatch.delenv("WORLDFORGE_ENABLE_SCAFFOLD_SURROGATES", raising=False)
    genie_report = assert_provider_contract(GenieProvider())
    assert genie_report.configured is True
    assert genie_report.exercised_operations == []
    assert "exercised_operations=[]" in str(unsupported_entry["expected_error"])

    jepa_entry = _gallery_entry("optional-runtime-missing-dependency")
    assert str(jepa_entry["owner"]) == "prepared host owner"
    assert "do not add it to base dependencies" in str(jepa_entry["first_triage_step"])


def test_provider_contract_cli_runs_mock_provider(monkeypatch, capsys) -> None:
    monkeypatch.setattr(
        sys,
        "argv",
        ["worldforge", "provider", "contract", "mock", "--format", "json"],
    )

    assert worldforge_main() == 0

    payload = json.loads(capsys.readouterr().out)
    assert payload["schema_version"] == 1
    assert payload["status"] == "passed"
    assert payload["provider"] == "mock"
    assert payload["registered"] is True
    assert payload["safe_to_attach"] is True
    assert payload["validation_commands"][0] == (
        "uv run worldforge provider contract mock --format json"
    )
    checks = {check["name"]: check for check in payload["checks"]}
    assert checks["metadata"]["status"] == "passed"
    for capability in ("predict", "reason", "embed", "generate", "transfer"):
        assert checks[capability]["status"] == "passed"


def test_provider_contract_cli_reports_direct_factory_failure(monkeypatch, capsys) -> None:
    factory_path = f"{__name__}:make_broken_contract_provider"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "worldforge",
            "provider",
            "contract",
            "--factory",
            factory_path,
            "--format",
            "json",
        ],
    )

    assert worldforge_main() == 1

    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "failed"
    assert payload["provider"] == "broken-contract"
    assert payload["registered"] is False
    assert payload["factory_path"] == factory_path
    checks = {check["name"]: check for check in payload["checks"]}
    assert checks["metadata"]["status"] == "passed"
    assert checks["capability-contract"]["status"] == "failed"
    assert "invalid world state" in checks["capability-contract"]["detail"]
    assert f"--factory {factory_path}" in checks["capability-contract"]["next_step"]


def test_provider_contract_cli_skips_configured_remote_without_live(monkeypatch, capsys) -> None:
    factory_path = f"{__name__}:make_remote_configured_predict_provider"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "worldforge",
            "provider",
            "contract",
            "--factory",
            factory_path,
            "--format",
            "json",
        ],
    )

    assert worldforge_main() == 0

    payload = json.loads(capsys.readouterr().out)
    checks = {check["name"]: check for check in payload["checks"]}
    assert payload["status"] == "passed"
    assert payload["skipped_count"] == 1
    assert checks["predict"]["status"] == "skipped"
    assert "requires --live" in checks["predict"]["detail"]

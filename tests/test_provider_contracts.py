from __future__ import annotations

import inspect
import json
import sys
from collections.abc import Callable

import pytest

import worldforge.testing.provider_contract_validation as provider_contract_validation
import worldforge.testing.providers as provider_testing
from worldforge import (
    Action,
    ActionPolicyResult,
    ActionScoreResult,
    EmbeddingResult,
    ProviderCapabilities,
    WorldForgeError,
)
from worldforge.cli import main as worldforge_main
from worldforge.demos.provider_failure_gallery import build_provider_failure_gallery_entries
from worldforge.models import ProviderEvent, ProviderHealth
from worldforge.provider_contracts import (
    ProviderContractCheck,
    ProviderContractEvidence,
    load_json_contract_input,
)
from worldforge.providers import (
    BaseProvider,
    GenieProvider,
    JepaProvider,
    MockProvider,
    PredictionPayload,
    ProviderError,
    ProviderProfileSpec,
)
from worldforge.testing import (
    assert_embed_conformance,
    assert_policy_conformance,
    assert_predict_conformance,
    assert_provider_contract,
    assert_provider_events_conform,
    assert_score_conformance,
    load_capability_fixture,
)


def _gallery_entry(entry_id: str) -> dict[str, object]:
    entries = {str(entry["id"]): entry for entry in build_provider_failure_gallery_entries()}
    return entries[entry_id]


def test_provider_contract_facade_uses_shared_validation_module() -> None:
    assert provider_testing._validate_prediction is provider_contract_validation.validate_prediction
    assert provider_testing._validate_provider_events is (
        provider_contract_validation.validate_provider_events
    )
    assert provider_testing._expect_provider_error is (
        provider_contract_validation.expect_provider_error
    )


def test_provider_contract_json_boundaries_reject_non_finite_payloads(tmp_path) -> None:
    score_info = tmp_path / "score-info.json"
    score_info.write_text('{"temperature": NaN}\n', encoding="utf-8")

    with pytest.raises(WorldForgeError, match="finite numbers"):
        load_json_contract_input(score_info, name="score-info")

    score_candidates = tmp_path / "score-candidates.json"
    score_candidates.write_text('[["candidate-a"], ["candidate-b"]]\n', encoding="utf-8")
    assert load_json_contract_input(score_candidates, name="score-candidates") == [
        ["candidate-a"],
        ["candidate-b"],
    ]

    evidence = ProviderContractEvidence(
        provider="bad-json",
        registered=True,
        configured=True,
        profile={"quality": float("nan")},
        health={},
        checks=(
            ProviderContractCheck(
                name="metadata",
                status="passed",
                detail="metadata ok",
                next_step="keep metadata valid",
            ),
        ),
        validation_commands=("uv run worldforge provider contract bad-json --format json",),
    )
    with pytest.raises(WorldForgeError, match="finite numbers"):
        evidence.to_json()


def test_mock_provider_passes_contract_checks() -> None:
    provider = MockProvider()
    report = assert_provider_contract(provider)

    assert report.configured is True
    assert set(report.exercised_operations) == {"predict", "embed"}
    assert_predict_conformance(provider)
    assert_embed_conformance(provider)


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
    def __init__(
        self,
        *,
        scores: list[float] | None = None,
        best_index: int = 1,
        lower_is_better: bool = True,
    ) -> None:
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
        self._scores = scores or [0.4, 0.1]
        self._best_index = best_index
        self._lower_is_better = lower_is_better

    def health(self) -> ProviderHealth:
        return ProviderHealth(name=self.name, healthy=True, latency_ms=0.1, details="configured")

    def score_actions(self, *, info, action_candidates) -> ActionScoreResult:
        return ActionScoreResult(
            provider=self.name,
            scores=list(self._scores),
            best_index=self._best_index,
            lower_is_better=self._lower_is_better,
            metadata={
                "fixture": info.get("fixture", "score"),
                "candidates": len(action_candidates),
            },
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
            raw_actions={"fixture": info.get("fixture", "policy")},
            action_candidates=[[action]],
            metadata={"runtime": "test"},
        )


class InvalidPublicResultProvider(BaseProvider):
    def __init__(self) -> None:
        super().__init__(
            name="invalid-public-result",
            capabilities=ProviderCapabilities(
                predict=True,
                embed=True,
                score=True,
                policy=True,
            ),
            profile=ProviderProfileSpec(
                description="Provider that constructs invalid public result models",
                is_local=True,
                deterministic=True,
                requires_credentials=False,
            ),
        )

    def predict(self, world_state, action, steps) -> PredictionPayload:
        return PredictionPayload(
            state={"metadata": {"not_json": object()}},
            confidence=0.5,
            physics_score=0.5,
            frames=[],
            metadata={"provider": self.name},
            latency_ms=0.1,
        )

    def embed(self, *, text) -> EmbeddingResult:
        return EmbeddingResult(provider=self.name, model="fixture", vector=[])

    def score_actions(self, *, info, action_candidates) -> ActionScoreResult:
        return ActionScoreResult(
            provider=self.name,
            scores=[0.4, 0.1],
            best_index=0,
            lower_is_better=True,
        )

    def select_actions(self, *, info) -> ActionPolicyResult:
        return ActionPolicyResult(provider=self.name, actions=[])


class ProviderErrorResultProvider(BaseProvider):
    def __init__(self) -> None:
        super().__init__(
            name="provider-error-result",
            capabilities=ProviderCapabilities(score=True),
            profile=ProviderProfileSpec(
                description="Provider that raises ProviderError from a declared capability",
                is_local=True,
                deterministic=True,
                requires_credentials=False,
            ),
        )

    def score_actions(self, *, info, action_candidates) -> ActionScoreResult:
        raise ProviderError("score runtime unavailable")


class MutatedPublicResultProvider(BaseProvider):
    def __init__(self, mutation: str) -> None:
        super().__init__(
            name="mutated-public-result",
            capabilities=ProviderCapabilities(
                embed=True,
                score=True,
                policy=True,
            ),
            profile=ProviderProfileSpec(
                description="Provider that mutates public result models after construction",
                is_local=True,
                deterministic=True,
                requires_credentials=False,
            ),
        )
        self._mutation = mutation

    def embed(self, *, text) -> EmbeddingResult:
        result = EmbeddingResult(provider=self.name, model="fixture", vector=[1.0])
        if self._mutation == "embed_non_finite_vector":
            result.vector = [float("nan")]
        return result

    def score_actions(self, *, info, action_candidates) -> ActionScoreResult:
        result = ActionScoreResult(provider=self.name, scores=[0.1, 0.2], best_index=0)
        if self._mutation == "score_non_finite_score":
            result.scores = [0.1, float("nan")]
        if self._mutation == "score_non_json_metadata":
            result.metadata = {"bad": object()}
        return result

    def select_actions(self, *, info) -> ActionPolicyResult:
        action = Action.move_to(0.1, 0.2, 0.3)
        result = ActionPolicyResult(provider=self.name, actions=[action], raw_actions={})
        if self._mutation == "policy_bool_horizon":
            result.action_horizon = True  # type: ignore[assignment]
        if self._mutation == "policy_non_json_raw_actions":
            result.raw_actions = {"bad": object()}
        if self._mutation == "policy_bad_candidate_shape":
            result.action_candidates = [action]  # type: ignore[list-item]
        return result


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


@pytest.mark.parametrize(
    ("provider", "expected_best_score"),
    [
        (FakeScoreProvider(scores=[0.4, 0.1], best_index=1, lower_is_better=True), 0.1),
        (FakeScoreProvider(scores=[0.4, 0.1], best_index=0, lower_is_better=False), 0.4),
    ],
)
def test_score_conformance_accepts_best_index_that_matches_direction(
    provider: FakeScoreProvider,
    expected_best_score: float,
) -> None:
    score = assert_score_conformance(
        provider,
        info={"fixture": "score"},
        action_candidates=[["a"], ["b"]],
    )

    assert score.best_score == expected_best_score


@pytest.mark.parametrize(
    "provider",
    [
        FakeScoreProvider(scores=[0.4, 0.1], best_index=0, lower_is_better=True),
        FakeScoreProvider(scores=[0.4, 0.1], best_index=1, lower_is_better=False),
    ],
)
def test_score_conformance_rejects_best_index_that_contradicts_direction(
    provider: FakeScoreProvider,
) -> None:
    with pytest.raises(AssertionError, match="lower_is_better direction"):
        assert_score_conformance(
            provider,
            info={"fixture": "score"},
            action_candidates=[["a"], ["b"]],
        )


@pytest.mark.parametrize(
    ("helper", "expected_message"),
    [
        (
            lambda provider: assert_predict_conformance(provider),
            "predict must return a valid PredictionPayload",
        ),
        (
            lambda provider: assert_embed_conformance(provider),
            "embed must return a valid EmbeddingResult",
        ),
        (
            lambda provider: assert_score_conformance(
                provider,
                info={},
                action_candidates=[["a"], ["b"]],
            ),
            "score must return a valid ActionScoreResult",
        ),
        (
            lambda provider: assert_policy_conformance(provider),
            "policy must return a valid ActionPolicyResult",
        ),
    ],
)
def test_capability_conformance_helpers_normalize_public_model_errors(
    helper: Callable[[InvalidPublicResultProvider], object],
    expected_message: str,
) -> None:
    with pytest.raises(AssertionError, match=expected_message):
        helper(InvalidPublicResultProvider())


def test_capability_conformance_helpers_normalize_provider_errors() -> None:
    with pytest.raises(AssertionError, match="provider raised ProviderError"):
        assert_score_conformance(
            ProviderErrorResultProvider(),
            info={},
            action_candidates=[["a"], ["b"]],
        )


@pytest.mark.parametrize(
    ("provider", "helper", "expected_message"),
    [
        (
            MutatedPublicResultProvider("embed_non_finite_vector"),
            lambda provider: assert_embed_conformance(provider),
            "embed vector values must be finite floats",
        ),
        (
            MutatedPublicResultProvider("score_non_finite_score"),
            lambda provider: assert_score_conformance(
                provider,
                info={},
                action_candidates=[["a"], ["b"]],
            ),
            "score values must be finite floats",
        ),
        (
            MutatedPublicResultProvider("score_non_json_metadata"),
            lambda provider: assert_score_conformance(
                provider,
                info={},
                action_candidates=[["a"], ["b"]],
            ),
            "score result must be JSON serializable",
        ),
        (
            MutatedPublicResultProvider("policy_bool_horizon"),
            lambda provider: assert_policy_conformance(provider),
            "policy action_horizon must be positive",
        ),
        (
            MutatedPublicResultProvider("policy_non_json_raw_actions"),
            lambda provider: assert_policy_conformance(provider),
            "policy result must be JSON serializable",
        ),
        (
            MutatedPublicResultProvider("policy_bad_candidate_shape"),
            lambda provider: assert_policy_conformance(provider),
            "policy action candidate plans must be non-empty lists",
        ),
    ],
)
def test_capability_conformance_helpers_revalidate_mutable_results(
    provider: MutatedPublicResultProvider,
    helper: Callable[[MutatedPublicResultProvider], object],
    expected_message: str,
) -> None:
    with pytest.raises(AssertionError, match=expected_message):
        helper(provider)


def test_corpus_valid_baselines_pass_mock_provider_conformance() -> None:
    provider = MockProvider()

    predict_fx = load_capability_fixture("predict", "valid_baseline")
    assert_predict_conformance(
        provider,
        world_state=predict_fx.payload["world_state"],
        action=Action.from_dict(predict_fx.payload["action"]),
        steps=predict_fx.payload["steps"],
    )

    embed_fx = load_capability_fixture("embed", "valid_baseline")
    assert_embed_conformance(provider, text=embed_fx.payload["text"])

    score_fx = load_capability_fixture("score", "valid_baseline")
    assert_score_conformance(
        FakeScoreProvider(),
        info=score_fx.payload["info"],
        action_candidates=score_fx.payload["action_candidates"],
    )
    policy_fx = load_capability_fixture("policy", "valid_baseline")
    assert_policy_conformance(FakePolicyProvider(), info=policy_fx.payload["info"])


def test_provider_event_conformance_helper_rejects_secret_material() -> None:
    assert_provider_events_conform(
        [
            ProviderEvent(
                provider="fixture",
                operation="download",
                phase="success",
                target="https://example.test/artifact.mp4?token=api-secret",
                metadata={"status": "ok"},
            )
        ],
        provider="fixture",
    )

    with pytest.raises(AssertionError, match="secret material"):
        assert_provider_events_conform(
            [
                ProviderEvent(
                    provider="fixture",
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
                    provider="mock",
                    operation="predict",
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
    for capability in ("predict", "embed"):
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

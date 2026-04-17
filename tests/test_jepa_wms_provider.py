from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from worldforge import ActionScoreResult, WorldForgeError
from worldforge.providers.base import ProviderError
from worldforge.providers.jepa_wms import JEPAWMSProvider
from worldforge.testing import assert_provider_contract

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "providers"


def _fixture(name: str) -> dict[str, Any]:
    return json.loads((FIXTURE_DIR / name).read_text(encoding="utf-8"))


class FakeJEPAWMSRuntime:
    def __init__(self, response: object) -> None:
        self.response = response
        self.calls: list[dict[str, Any]] = []

    def score_actions(
        self,
        *,
        model_path: str,
        info: dict[str, Any],
        action_candidates: object,
    ) -> object:
        self.calls.append(
            {
                "model_path": model_path,
                "info": info,
                "action_candidates": action_candidates,
            }
        )
        return self.response


def test_jepa_wms_profile_starts_as_safe_scaffold() -> None:
    provider = JEPAWMSProvider()
    profile = provider.profile()

    assert profile.name == "jepa-wms"
    assert profile.implementation_status == "scaffold"
    assert profile.supported_tasks == []
    assert profile.capabilities.score is False
    assert provider.planned_capabilities == ("score",)
    assert provider.taxonomy_category == "JEPA latent predictive world model"


def test_jepa_wms_health_reports_missing_configuration(monkeypatch) -> None:
    monkeypatch.delenv("JEPA_WMS_MODEL_PATH", raising=False)

    health = JEPAWMSProvider().health()

    assert health.healthy is False
    assert "JEPA_WMS_MODEL_PATH" in health.details


def test_jepa_wms_health_stays_unhealthy_until_runtime_is_supplied(monkeypatch) -> None:
    monkeypatch.setenv("JEPA_WMS_MODEL_PATH", "/tmp/jepa-wms-checkpoint")

    provider = JEPAWMSProvider()
    health = provider.health()

    assert provider.configured() is False
    assert health.healthy is False
    assert "no runtime adapter implemented" in health.details


def test_jepa_wms_fake_runtime_scores_fixture_payload_and_contract() -> None:
    payload = _fixture("jepa_wms_success.json")
    runtime = FakeJEPAWMSRuntime(payload["runtime_response"])
    events = []
    provider = JEPAWMSProvider(
        model_path=payload["model_path"],
        runtime=runtime,
        event_handler=events.append,
    )

    report = assert_provider_contract(
        provider,
        score_info=payload["info"],
        score_action_candidates=payload["action_candidates"],
    )
    result = provider.score_actions(
        info=payload["info"],
        action_candidates=payload["action_candidates"],
    )

    assert report.exercised_operations == ["score"]
    assert provider.profile().supported_tasks == ["score"]
    assert provider.health().healthy is True
    assert isinstance(result, ActionScoreResult)
    assert result.provider == "jepa-wms"
    assert result.scores == [0.4, 0.12, 0.9]
    assert result.best_index == 1
    assert result.best_score == 0.12
    assert result.lower_is_better is True
    assert result.metadata["model_path"] == payload["model_path"]
    assert result.metadata["score_type"] == "cost"
    assert result.metadata["runtime"] == "fake-jepa-wms"
    assert runtime.calls[-1]["model_path"] == payload["model_path"]
    assert runtime.calls[-1]["info"] == payload["info"]
    assert events[-1].operation == "score"
    assert events[-1].phase == "success"


def test_jepa_wms_callable_runtime_can_return_utility_scores() -> None:
    payload = _fixture("jepa_wms_success.json")

    def runtime(**_kwargs: object) -> object:
        return {
            "scores": [0.4, 0.72, 0.2],
            "lower_is_better": False,
            "best_index": 1,
        }

    provider = JEPAWMSProvider(model_path=payload["model_path"], runtime=runtime)

    result = provider.score_actions(
        info=payload["info"],
        action_candidates=payload["action_candidates"],
    )

    assert result.best_index == 1
    assert result.best_score == 0.72
    assert result.lower_is_better is False
    assert result.metadata["score_type"] == "utility"


def test_jepa_wms_runtime_can_return_action_score_result() -> None:
    payload = _fixture("jepa_wms_success.json")
    runtime = FakeJEPAWMSRuntime(
        ActionScoreResult(
            provider="jepa-wms",
            scores=[0.4, 0.12, 0.9],
            best_index=1,
        )
    )
    provider = JEPAWMSProvider(model_path=payload["model_path"], runtime=runtime)

    result = provider.score_actions(
        info=payload["info"],
        action_candidates=payload["action_candidates"],
    )

    assert result.best_index == 1
    assert result.best_score == 0.12


def test_jepa_wms_runtime_error_response_emits_failure_event() -> None:
    payload = _fixture("jepa_wms_error.json")
    events = []
    provider = JEPAWMSProvider(
        model_path=payload["model_path"],
        runtime=FakeJEPAWMSRuntime(payload["runtime_response"]),
        event_handler=events.append,
    )

    with pytest.raises(ProviderError, match="checkpoint_expired"):
        provider.score_actions(
            info=payload["info"],
            action_candidates=payload["action_candidates"],
        )

    assert events[-1].operation == "score"
    assert events[-1].phase == "failure"
    assert "checkpoint_expired" in events[-1].message


@pytest.mark.parametrize(
    ("runtime_response", "match"),
    [
        ("not-a-json-object", "response must be a JSON object"),
        ({"error": "bad-error"}, "error response must be a JSON object"),
        ({"scores": []}, "returned no action scores"),
        (
            {"scores": [0.4, 0.12, 0.9], "lower_is_better": "yes"},
            "lower_is_better must be a boolean",
        ),
        (
            {"scores": [0.4, 0.12, 0.9], "metadata": "bad"},
            "metadata must be a JSON object",
        ),
        (
            {"scores": [0.4, 0.12, 0.9], "best_index": 3},
            "best_index is out of range",
        ),
    ],
)
def test_jepa_wms_rejects_malformed_runtime_responses(
    runtime_response: object,
    match: str,
) -> None:
    payload = _fixture("jepa_wms_success.json")
    provider = JEPAWMSProvider(
        model_path=payload["model_path"],
        runtime=FakeJEPAWMSRuntime(runtime_response),
    )

    with pytest.raises(ProviderError, match=match):
        provider.score_actions(
            info=payload["info"],
            action_candidates=payload["action_candidates"],
        )


@pytest.mark.parametrize(
    ("fixture_name", "match"),
    [
        ("jepa_wms_missing_goal.json", "missing required input fields: goal"),
        ("jepa_wms_bad_action_candidates.json", "four-dimensional"),
        ("jepa_wms_bad_scores.json", "finite numbers"),
    ],
)
def test_jepa_wms_rejects_malformed_contract_fixtures(
    fixture_name: str,
    match: str,
) -> None:
    payload = _fixture(fixture_name)
    provider = JEPAWMSProvider(
        model_path="/models/jepa-wms/checkpoint.pt",
        runtime=FakeJEPAWMSRuntime(payload["runtime_response"]),
    )

    with pytest.raises(ProviderError, match=match):
        provider.score_actions(
            info=payload["info"],
            action_candidates=payload["action_candidates"],
        )


def test_jepa_wms_rejects_score_count_mismatch() -> None:
    payload = _fixture("jepa_wms_success.json")
    provider = JEPAWMSProvider(
        model_path=payload["model_path"],
        runtime=FakeJEPAWMSRuntime({"scores": [0.2]}),
    )

    with pytest.raises(ProviderError, match="score count"):
        provider.score_actions(
            info=payload["info"],
            action_candidates=payload["action_candidates"],
        )


def test_jepa_wms_rejects_invalid_model_path() -> None:
    with pytest.raises(WorldForgeError, match="model_path"):
        JEPAWMSProvider(model_path=" ")


@pytest.mark.parametrize(
    ("bad_info", "match"),
    [
        ({"observation": [], "goal": [[1.0]]}, "empty sequences"),
        ({"observation": [[0.0], [0.1, 0.2]], "goal": [[1.0]]}, "rectangular"),
        ({"observation": "bad", "goal": [[1.0]]}, "tensor-like object"),
    ],
)
def test_jepa_wms_rejects_malformed_info_values(
    bad_info: dict[str, object],
    match: str,
) -> None:
    payload = _fixture("jepa_wms_success.json")
    provider = JEPAWMSProvider(
        model_path=payload["model_path"],
        runtime=FakeJEPAWMSRuntime(payload["runtime_response"]),
    )

    with pytest.raises(ProviderError, match=match):
        provider.score_actions(
            info=bad_info,
            action_candidates=payload["action_candidates"],
        )

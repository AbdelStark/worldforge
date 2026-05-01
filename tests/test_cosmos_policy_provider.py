from __future__ import annotations

import json

import httpx
import pytest

from worldforge import Action, ActionPolicyResult, ActionScoreResult, WorldForge
from worldforge.models import JSONDict, ProviderCapabilities, ProviderEvent, ProviderHealth
from worldforge.providers import (
    BaseProvider,
    CosmosPolicyProvider,
    ProviderError,
    ProviderProfileSpec,
)
from worldforge.testing import assert_provider_contract


def _row(seed: float) -> list[float]:
    return [seed + (index / 100.0) for index in range(14)]


def _actions(seed: float) -> list[list[float]]:
    return [_row(seed), _row(seed + 1.0)]


def _policy_info() -> JSONDict:
    return {
        "observation": {
            "primary_image": [[[[0, 0, 0]]]],
            "left_wrist_image": [[[[1, 1, 1]]]],
            "right_wrist_image": [[[[2, 2, 2]]]],
            "proprio": [0.0 for _ in range(14)],
        },
        "task_description": "put the candy in the bowl",
        "embodiment_tag": "aloha",
        "action_horizon": 2,
    }


def _translator(raw_actions: object, _info: JSONDict, _provider_info: JSONDict):
    assert isinstance(raw_actions, dict)
    matrix = raw_actions["actions"]
    return [Action.move_to(float(row[0]), float(row[1]), float(row[2])) for row in matrix]


def _candidate_translator(raw_actions: object, _info: JSONDict, _provider_info: JSONDict):
    assert isinstance(raw_actions, dict)
    candidates = raw_actions.get("all_actions") or [raw_actions["actions"]]
    return [
        [Action.move_to(float(row[0]), float(row[1]), float(row[2])) for row in candidate]
        for candidate in candidates
    ]


class FakeScoreProvider(BaseProvider):
    def __init__(self, scores: list[float]) -> None:
        self.calls: list[dict[str, object]] = []
        best_index = min(range(len(scores)), key=scores.__getitem__)
        self._result = ActionScoreResult(
            provider="fake-score",
            scores=scores,
            best_index=best_index,
            metadata={"runtime": "fake-score"},
        )
        super().__init__(
            "fake-score",
            capabilities=ProviderCapabilities(score=True),
            profile=ProviderProfileSpec(
                is_local=True,
                description="Fake score provider for Cosmos-Policy planning tests.",
                implementation_status="test",
                deterministic=True,
                requires_credentials=False,
            ),
        )

    def health(self) -> ProviderHealth:
        return ProviderHealth(name=self.name, healthy=True, latency_ms=0.1, details="configured")

    def score_actions(self, *, info: JSONDict, action_candidates: object) -> ActionScoreResult:
        self.calls.append({"info": info, "action_candidates": action_candidates})
        return self._result


def test_cosmos_policy_provider_contract() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        assert request.url.path == "/act"
        payload = json.loads(request.content.decode("utf-8"))
        assert payload["task_description"] == "put the candy in the bowl"
        return httpx.Response(
            200,
            json={
                "actions": _actions(0.1),
                "value_prediction": 0.73,
                "future_image_predictions": {"future_image": [[[0, 1, 2]]]},
            },
        )

    provider = CosmosPolicyProvider(
        base_url="http://cosmos-policy.test",
        transport=httpx.MockTransport(handler),
        action_translator=_translator,
    )

    report = assert_provider_contract(provider, policy_info=_policy_info())

    assert report.configured is True
    assert report.exercised_operations == ["policy"]
    assert set(provider.profile().capabilities.enabled_names()) == {"policy"}


def test_cosmos_policy_provider_contract_unconfigured(monkeypatch) -> None:
    monkeypatch.delenv("COSMOS_POLICY_BASE_URL", raising=False)

    report = assert_provider_contract(CosmosPolicyProvider())

    assert report.configured is False
    assert report.exercised_operations == []


def test_cosmos_policy_select_actions_preserves_values_candidates_and_events() -> None:
    events: list[ProviderEvent] = []
    candidate_a = _actions(0.1)
    candidate_b = _actions(2.0)

    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content.decode("utf-8"))
        assert request.headers["authorization"] == "Bearer test-token"
        assert payload["return_all_query_results"] is True
        return httpx.Response(
            200,
            json={
                "actions": candidate_b,
                "all_actions": [candidate_a, candidate_b],
                "value_prediction": 0.91,
                "all_value_predictions": [0.1, 0.91],
                "all_value_predictions_by_depth": [[0.1], [0.91]],
                "future_image_predictions": {
                    "future_image": [[[[0, 0, 0]]]],
                    "future_left_wrist_image": [[[[1, 1, 1]]]],
                },
            },
        )

    provider = CosmosPolicyProvider(
        base_url="http://cosmos-policy.test",
        api_token="test-token",
        transport=httpx.MockTransport(handler),
        return_all_query_results=True,
        action_translator=_candidate_translator,
        event_handler=events.append,
    )

    result = provider.select_actions(info=_policy_info())

    assert isinstance(result, ActionPolicyResult)
    assert result.provider == "cosmos-policy"
    assert result.action_horizon == 2
    assert result.embodiment_tag == "aloha"
    assert result.raw_actions == {"actions": candidate_b, "all_actions": [candidate_a, candidate_b]}
    assert len(result.action_candidates) == 2
    assert result.actions == result.action_candidates[1]
    assert result.metadata["selected_candidate_index"] == 1
    assert result.metadata["provider_info"]["value_prediction"] == 0.91
    assert result.metadata["provider_info"]["all_value_predictions"] == [0.1, 0.91]
    assert result.metadata["provider_info"]["future_prediction_summary"][
        "future_image_predictions"
    ]["future_image"] == {"shape": [1, 1, 1, 3]}
    assert events[-1].operation == "policy"
    assert events[-1].phase == "success"
    assert events[-1].method == "POST"
    assert events[-1].target == "/act"


def test_cosmos_policy_only_planning_uses_selected_actions(tmp_path) -> None:
    provider = CosmosPolicyProvider(
        base_url="http://cosmos-policy.test",
        transport=httpx.MockTransport(
            lambda _request: httpx.Response(200, json={"actions": _actions(0.3)})
        ),
        action_translator=_translator,
    )
    forge = WorldForge(state_dir=tmp_path, auto_register_remote=False)
    forge.register_provider(provider)
    world = forge.create_world("aloha-workcell", provider="mock")

    plan = world.plan(
        goal="put the candy in the bowl",
        provider="cosmos-policy",
        policy_info=_policy_info(),
        execution_provider="mock",
    )
    execution = world.execute_plan(plan)

    assert plan.provider == "cosmos-policy"
    assert plan.metadata["planning_mode"] == "policy"
    assert plan.metadata["policy_result"]["provider"] == "cosmos-policy"
    assert execution.final_world().provider == "mock"


def test_cosmos_policy_plus_score_planning_scores_translated_candidates(tmp_path) -> None:
    candidate_a = _actions(0.1)
    candidate_b = _actions(2.0)
    policy_provider = CosmosPolicyProvider(
        base_url="http://cosmos-policy.test",
        transport=httpx.MockTransport(
            lambda _request: httpx.Response(
                200,
                json={"actions": candidate_b, "all_actions": [candidate_a, candidate_b]},
            )
        ),
        action_translator=_candidate_translator,
    )
    score_provider = FakeScoreProvider([0.4, 0.2])
    forge = WorldForge(state_dir=tmp_path, auto_register_remote=False)
    forge.register_provider(policy_provider)
    forge.register_provider(score_provider)
    world = forge.create_world("aloha-score-workcell", provider="mock")

    plan = world.plan(
        goal="choose the best Cosmos-Policy candidate",
        policy_provider="cosmos-policy",
        score_provider="fake-score",
        policy_info=_policy_info(),
        score_info={"goal": "lowest cost"},
        execution_provider="mock",
    )

    assert plan.metadata["planning_mode"] == "policy+score"
    assert plan.metadata["score_result"]["best_index"] == 1
    assert plan.actions == [
        Action.move_to(float(row[0]), float(row[1]), float(row[2])) for row in candidate_b
    ]
    assert score_provider.calls


def test_cosmos_policy_requires_translator() -> None:
    provider = CosmosPolicyProvider(
        base_url="http://cosmos-policy.test",
        transport=httpx.MockTransport(
            lambda _request: httpx.Response(200, json={"actions": _actions(0.1)})
        ),
    )

    with pytest.raises(ProviderError, match="provide action_translator"):
        provider.select_actions(info=_policy_info())


def test_cosmos_policy_validates_observation_before_request() -> None:
    called = False

    def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal called
        called = True
        return httpx.Response(200, json={"actions": _actions(0.1)})

    provider = CosmosPolicyProvider(
        base_url="http://cosmos-policy.test",
        transport=httpx.MockTransport(handler),
        action_translator=_translator,
    )
    info = _policy_info()
    del info["observation"]["primary_image"]

    with pytest.raises(ProviderError, match="primary_image"):
        provider.select_actions(info=info)
    assert called is False


@pytest.mark.parametrize(
    ("payload", "match"),
    [
        ({"actions": []}, "non-empty action matrix"),
        ({"actions": [[0.0, 1.0]]}, "action_dim must be 14"),
        ({"actions": [_row(0.1), [0.0]]}, "rectangular"),
        ({"actions": [_row(0.1)], "value_prediction": float("nan")}, "finite number"),
        ({"actions": [_row(0.1)], "all_actions": []}, "all_actions"),
    ],
)
def test_cosmos_policy_rejects_malformed_responses(payload: JSONDict, match: str) -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            content=json.dumps(payload).encode("utf-8"),
            headers={"content-type": "application/json"},
        )

    provider = CosmosPolicyProvider(
        base_url="http://cosmos-policy.test",
        transport=httpx.MockTransport(handler),
        action_translator=_translator,
    )

    with pytest.raises(ProviderError, match=match):
        provider.select_actions(info=_policy_info())


def test_cosmos_policy_config_summary_is_value_free(monkeypatch) -> None:
    monkeypatch.delenv("COSMOS_POLICY_BASE_URL", raising=False)
    monkeypatch.delenv("COSMOS_POLICY_API_TOKEN", raising=False)
    provider = CosmosPolicyProvider(
        base_url="http://cosmos-policy.test",
        api_token="secret-token",
    )

    summary = provider.config_summary().to_dict()

    assert summary["provider"] == "cosmos-policy"
    assert summary["configured"] is True
    assert "secret-token" not in json.dumps(summary)
    assert summary["fields"][0]["source"] == "direct"
    assert summary["fields"][1]["secret"] is True

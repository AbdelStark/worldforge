from __future__ import annotations

import math
import sys
import types

import pytest

from worldforge import Action, ActionPolicyResult, ActionScoreResult, WorldForge, WorldForgeError
from worldforge.models import JSONDict, ProviderCapabilities, ProviderEvent, ProviderHealth
from worldforge.providers import (
    BaseProvider,
    GrootPolicyClientProvider,
    MockProvider,
    ProviderError,
)
from worldforge.testing import assert_provider_contract


def _policy_info() -> JSONDict:
    return {
        "observation": {
            "video": {
                "front": [[[[[0, 0, 0]]]]],
            },
            "state": {
                "eef": [[[0.0, 0.5, 0.0]]],
            },
            "language": {
                "task": [["push the cube"]],
            },
        },
        "embodiment_tag": "LIBERO_PANDA",
        "action_horizon": 2,
    }


class FakeGrootClient:
    def __init__(self, response: object, *, healthy: bool = True) -> None:
        self.response = response
        self.healthy = healthy
        self.ping_calls = 0
        self.get_action_calls: list[dict[str, object]] = []

    def ping(self) -> bool:
        self.ping_calls += 1
        return self.healthy

    def get_action(self, observation: object, options: object | None = None) -> object:
        self.get_action_calls.append({"observation": observation, "options": options})
        return self.response


class FakeArray:
    def __init__(self, value: object) -> None:
        self.value = value

    def tolist(self) -> object:
        return self.value


class FakeScoreProvider(BaseProvider):
    def __init__(self, scores: list[float]) -> None:
        self.calls: list[dict[str, object]] = []
        self._scores = scores
        best_index = min(range(len(scores)), key=scores.__getitem__)
        self._result = ActionScoreResult(
            provider="fake-score",
            scores=scores,
            best_index=best_index,
            metadata={"runtime": "fake-score"},
        )
        super().__init__(
            "fake-score",
            capabilities=ProviderCapabilities(predict=False, score=True),
            is_local=True,
            description="Fake score provider for policy planning tests.",
            implementation_status="test",
            deterministic=True,
            requires_credentials=False,
        )

    def health(self) -> ProviderHealth:
        return ProviderHealth(name=self.name, healthy=True, latency_ms=0.1, details="configured")

    def score_actions(self, *, info: JSONDict, action_candidates: object) -> ActionScoreResult:
        self.calls.append({"info": info, "action_candidates": action_candidates})
        return self._result


def test_gr00t_policy_client_provider_passes_contract_and_emits_events() -> None:
    raw_response = (
        {
            "arm": [[[0.1, 0.5, 0.0], [0.2, 0.5, 0.0]]],
            "gripper": [[[0.0], [1.0]]],
        },
        {"latency_ms": 7.5},
    )
    client = FakeGrootClient(raw_response)
    events: list[ProviderEvent] = []

    def translator(_raw: object, _info: JSONDict, provider_info: JSONDict):
        assert provider_info == {"latency_ms": 7.5}
        return [
            Action.move_to(0.1, 0.5, 0.0),
            Action.move_to(0.2, 0.5, 0.0),
        ]

    provider = GrootPolicyClientProvider(
        policy_client=client,
        embodiment_tag="LIBERO_PANDA",
        action_translator=translator,
        event_handler=events.append,
    )

    report = assert_provider_contract(provider, policy_info=_policy_info())
    result = provider.select_actions(info=_policy_info())

    assert report.exercised_operations == ["policy"]
    assert provider.profile().capabilities.policy is True
    assert provider.profile().capabilities.predict is False
    assert isinstance(result, ActionPolicyResult)
    assert result.provider == "gr00t"
    assert result.action_horizon == 2
    assert result.embodiment_tag == "LIBERO_PANDA"
    assert result.raw_actions["arm"] == [[[0.1, 0.5, 0.0], [0.2, 0.5, 0.0]]]
    assert result.metadata["provider_info"] == {"latency_ms": 7.5}
    assert client.get_action_calls[-1]["observation"] == _policy_info()["observation"]
    assert events[-1].operation == "policy"
    assert events[-1].phase == "success"


def test_gr00t_policy_only_planning_uses_policy_actions(tmp_path) -> None:
    client = FakeGrootClient(({"arm": [[[0.3, 0.5, 0.0]]]}, {}))
    provider = GrootPolicyClientProvider(
        policy_client=client,
        action_translator=lambda *_args: [Action.move_to(0.3, 0.5, 0.0)],
    )
    forge = WorldForge(state_dir=tmp_path, auto_register_remote=False)
    forge.register_provider(provider)
    world = forge.create_world("robot-workcell", provider="mock")

    selected = forge.select_actions("gr00t", info=_policy_info())
    plan = world.plan(
        goal="push the cube",
        provider="gr00t",
        policy_info=_policy_info(),
        execution_provider="mock",
    )
    execution = world.execute_plan(plan)

    assert selected.actions == [Action.move_to(0.3, 0.5, 0.0)]
    assert plan.provider == "gr00t"
    assert plan.actions == [Action.move_to(0.3, 0.5, 0.0)]
    assert plan.metadata["planning_mode"] == "policy"
    assert plan.metadata["policy_result"]["provider"] == "gr00t"
    assert plan.success_probability == 0.5
    assert execution.final_world().provider == "mock"


def test_gr00t_policy_plus_score_planning_selects_scored_candidate(tmp_path) -> None:
    candidate_plans = [
        [Action.move_to(0.1, 0.5, 0.0)],
        [Action.move_to(0.6, 0.5, 0.0)],
        [Action.move_to(0.9, 0.5, 0.0)],
    ]
    client = FakeGrootClient(
        (
            {
                "arm": [
                    [[0.1, 0.5, 0.0]],
                    [[0.6, 0.5, 0.0]],
                    [[0.9, 0.5, 0.0]],
                ]
            },
            {"candidate_source": "diffusion-samples"},
        )
    )
    policy_provider = GrootPolicyClientProvider(
        policy_client=client,
        action_translator=lambda *_args: candidate_plans,
    )
    score_provider = FakeScoreProvider([0.9, 0.1, 0.4])
    forge = WorldForge(state_dir=tmp_path, auto_register_remote=False)
    forge.register_provider(policy_provider)
    forge.register_provider(score_provider)
    world = forge.create_world("robot-workcell", provider="mock")

    plan = world.plan(
        goal="choose the lowest world-model cost candidate",
        provider="fake-score",
        policy_provider="gr00t",
        policy_info=_policy_info(),
        score_info={"observation": [[0.0]], "goal": [[1.0]]},
        execution_provider="mock",
    )

    assert plan.provider == "fake-score"
    assert plan.actions == candidate_plans[1]
    assert plan.metadata["planning_mode"] == "policy+score"
    assert plan.metadata["policy_provider"] == "gr00t"
    assert plan.metadata["score_provider"] == "fake-score"
    assert plan.metadata["policy_result"]["metadata"]["candidate_count"] == 3
    assert plan.metadata["score_result"]["best_index"] == 1
    assert score_provider.calls[-1]["action_candidates"] == [
        [action.to_dict() for action in candidate] for candidate in candidate_plans
    ]


def test_score_planning_defaults_to_serialized_action_candidates(tmp_path) -> None:
    candidate_plans = [
        [Action.move_to(0.1, 0.5, 0.0)],
        [Action.move_to(0.6, 0.5, 0.0)],
    ]
    score_provider = FakeScoreProvider([0.7, 0.2])
    forge = WorldForge(state_dir=tmp_path, auto_register_remote=False)
    forge.register_provider(score_provider)
    world = forge.create_world("robot-workcell", provider="mock")

    plan = world.plan(
        goal="choose the lowest-cost candidate",
        provider="fake-score",
        candidate_actions=candidate_plans,
        score_info={"observation": [[0.0]], "goal": [[1.0]]},
        execution_provider="mock",
    )

    assert plan.actions == candidate_plans[1]
    assert plan.metadata["planning_mode"] == "score"
    assert score_provider.calls[-1]["action_candidates"] == [
        [action.to_dict() for action in candidate] for candidate in candidate_plans
    ]


def test_gr00t_provider_reports_unconfigured_and_failed_health(monkeypatch) -> None:
    monkeypatch.delenv("GROOT_POLICY_HOST", raising=False)
    missing = GrootPolicyClientProvider()
    assert missing.configured() is False
    assert missing.health().healthy is False

    unhealthy = GrootPolicyClientProvider(
        policy_client=FakeGrootClient(({"arm": [[[0.0, 0.0, 0.0]]]}, {}), healthy=False),
        action_translator=lambda *_args: [Action.move_to(0.0, 0.0, 0.0)],
    )
    assert unhealthy.configured() is True
    assert unhealthy.health().healthy is False


def test_gr00t_provider_reads_env_configuration_and_reports_missing_dependency(
    monkeypatch,
) -> None:
    monkeypatch.setenv("GROOT_POLICY_HOST", "127.0.0.1")
    monkeypatch.setenv("GROOT_POLICY_PORT", "7777")
    monkeypatch.setenv("GROOT_POLICY_TIMEOUT_MS", "2000")
    monkeypatch.setenv("GROOT_POLICY_API_TOKEN", "token")
    monkeypatch.setenv("GROOT_POLICY_STRICT", "true")
    monkeypatch.setenv("GROOT_EMBODIMENT_TAG", "SO100")

    provider = GrootPolicyClientProvider()

    assert provider.configured() is True
    assert provider.host == "127.0.0.1"
    assert provider.port == 7777
    assert provider.timeout_ms == 2000
    assert provider.api_token == "token"
    assert provider.strict is True
    assert provider.embodiment_tag == "SO100"
    assert provider.health().healthy is False
    assert "gr00t.policy.server_client" in provider.health().details


def test_gr00t_provider_lazily_constructs_policy_client_from_import(monkeypatch) -> None:
    created: list[dict[str, object]] = []

    class ImportedPolicyClient(FakeGrootClient):
        def __init__(self, **kwargs: object) -> None:
            created.append(kwargs)
            super().__init__(({"arm": FakeArray([[[0.2, 0.5, 0.0]]])}, {"ok": True}))

    fake_policy_module = types.SimpleNamespace(server_client=types.SimpleNamespace())
    fake_server_client_module = types.SimpleNamespace(PolicyClient=ImportedPolicyClient)
    monkeypatch.setitem(sys.modules, "gr00t", types.SimpleNamespace(policy=fake_policy_module))
    monkeypatch.setitem(sys.modules, "gr00t.policy", fake_policy_module)
    monkeypatch.setitem(sys.modules, "gr00t.policy.server_client", fake_server_client_module)
    provider = GrootPolicyClientProvider(
        host="localhost",
        port=5556,
        timeout_ms=1234,
        api_token="secret",
        strict=True,
        action_translator=lambda *_args: [Action.move_to(0.2, 0.5, 0.0)],
    )

    assert provider.health().healthy is True
    result = provider.select_actions(info={**_policy_info(), "options": {"temperature": 0.1}})

    assert created == [
        {
            "host": "localhost",
            "port": 5556,
            "timeout_ms": 1234,
            "api_token": "secret",
            "strict": True,
        }
    ]
    assert result.raw_actions == {"arm": [[[0.2, 0.5, 0.0]]]}


@pytest.mark.parametrize(
    ("kwargs", "match"),
    [
        ({"host": " "}, "host"),
        ({"port": "bad"}, "port"),
        ({"port": 0}, "port"),
        ({"timeout_ms": 0}, "timeout_ms"),
        ({"strict": "maybe"}, "strict"),
        ({"strict": object()}, "strict"),
        ({"api_token": " "}, "api_token"),
    ],
)
def test_gr00t_provider_rejects_invalid_configuration(
    kwargs: dict[str, object],
    match: str,
) -> None:
    with pytest.raises(WorldForgeError, match=match):
        GrootPolicyClientProvider(**kwargs)


@pytest.mark.parametrize(
    ("provider", "info", "match"),
    [
        (
            GrootPolicyClientProvider(
                policy_client=FakeGrootClient(({"arm": [[[0.0, 0.0, 0.0]]]}, {}))
            ),
            _policy_info(),
            "action_translator",
        ),
        (
            GrootPolicyClientProvider(
                policy_client=FakeGrootClient(({"arm": [[[0.0, 0.0, 0.0]]]}, {})),
                action_translator=lambda *_args: [Action.move_to(0.0, 0.0, 0.0)],
            ),
            {"observation": {}},
            "at least one of video, state, or language",
        ),
    ],
)
def test_gr00t_provider_rejects_malformed_policy_inputs(
    provider: GrootPolicyClientProvider,
    info: JSONDict,
    match: str,
) -> None:
    with pytest.raises(ProviderError, match=match):
        provider.select_actions(info=info)


@pytest.mark.parametrize(
    ("response", "translator", "match"),
    [
        (({"arm": [[[0.0, 0.0, 0.0]]]}, {}, "extra"), lambda *_args: [Action("noop")], "tuple"),
        ("not-a-json-object", lambda *_args: [Action("noop")], "raw_actions"),
        (({"bad": math.nan}, {}), lambda *_args: [Action("noop")], "finite numbers"),
        (({1: "bad-key"}, {}), lambda *_args: [Action("noop")], "keys"),
        (({"arm": [[[0.0]]]}, "not-info"), lambda *_args: [Action("noop")], "provider_info"),
        (({"arm": [[[0.0]]]}, {}), lambda *_args: [], "non-empty action sequence"),
        (({"arm": [[[0.0]]]}, {}), lambda *_args: [[object()]], "Action instances"),
    ],
)
def test_gr00t_provider_rejects_malformed_policy_outputs(
    response: object,
    translator,
    match: str,
) -> None:
    provider = GrootPolicyClientProvider(
        policy_client=FakeGrootClient(response),
        action_translator=translator,
    )

    with pytest.raises(ProviderError, match=match):
        provider.select_actions(info=_policy_info())


def test_gr00t_provider_wraps_client_and_translation_failures() -> None:
    failing_client = FakeGrootClient(({"arm": [[[0.0]]]}, {}))

    def fail_get_action(_observation: object) -> object:
        raise RuntimeError("server unavailable")

    failing_client.get_action = fail_get_action  # type: ignore[method-assign]
    provider = GrootPolicyClientProvider(
        policy_client=failing_client,
        action_translator=lambda *_args: [Action("noop")],
    )
    with pytest.raises(ProviderError, match="server unavailable"):
        provider.select_actions(info=_policy_info())

    no_get_action = GrootPolicyClientProvider(
        policy_client=object(),
        action_translator=lambda *_args: [Action("noop")],
    )
    with pytest.raises(ProviderError, match="get_action"):
        no_get_action.select_actions(info=_policy_info())

    bad_translator = GrootPolicyClientProvider(
        policy_client=FakeGrootClient(({"arm": [[[0.0]]]}, {})),
        action_translator=lambda *_args: (_ for _ in ()).throw(RuntimeError("bad map")),
    )
    with pytest.raises(ProviderError, match="bad map"):
        bad_translator.select_actions(info=_policy_info())


def test_policy_planning_validation_errors(tmp_path) -> None:
    forge = WorldForge(state_dir=tmp_path, auto_register_remote=False)
    forge.register_provider(MockProvider(name="manual-mock"))
    world = forge.create_world("robot-workcell", provider="manual-mock")

    with pytest.raises(WorldForgeError, match="does not support policy planning"):
        world.plan(goal="move", provider="manual-mock", policy_info=_policy_info())

    policy_provider = GrootPolicyClientProvider(
        policy_client=FakeGrootClient(({"arm": [[[0.0, 0.0, 0.0]]]}, {})),
        action_translator=lambda *_args: [Action.move_to(0.0, 0.0, 0.0)],
    )
    forge.register_provider(policy_provider)
    with pytest.raises(WorldForgeError, match="Policy planning requires policy_info"):
        world.plan(goal="move", provider="gr00t", policy_provider="gr00t")

    forge.register_provider(FakeScoreProvider([0.2]))
    with pytest.raises(WorldForgeError, match="score_info"):
        world.plan(
            goal="move",
            provider="gr00t",
            policy_info=_policy_info(),
            score_provider="fake-score",
        )

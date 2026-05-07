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
    ProviderProfileSpec,
)
from worldforge.providers.gr00t import _GrootZmqPolicyClient
from worldforge.testing import assert_provider_contract


def _policy_info(*, action_horizon: int = 1) -> JSONDict:
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
        "action_horizon": action_horizon,
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


class FailingPingGrootClient(FakeGrootClient):
    def ping(self) -> bool:
        raise RuntimeError("server unreachable api_token=secret")


class FakeArray:
    def __init__(self, value: object) -> None:
        self.value = value

    def tolist(self) -> object:
        return self.value


class FakeZmqSocket:
    def __init__(self, responses: list[object]) -> None:
        self.responses = responses
        self.sent: list[object] = []
        self.options: list[tuple[int, object]] = []
        self.targets: list[str] = []

    def setsockopt(self, option: int, value: object) -> None:
        self.options.append((option, value))

    def connect(self, target: str) -> None:
        self.targets.append(target)

    def send(self, payload: object) -> None:
        self.sent.append(payload)

    def recv(self) -> object:
        response = self.responses.pop(0)
        if isinstance(response, BaseException):
            raise response
        return response


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
            profile=ProviderProfileSpec(
                is_local=True,
                description="Fake score provider for policy planning tests.",
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


def test_gr00t_provider_contract() -> None:
    client = FakeGrootClient(({"arm": [[[0.1, 0.5, 0.0]]]}, {}))
    provider = GrootPolicyClientProvider(
        policy_client=client,
        embodiment_tag="LIBERO_PANDA",
        action_translator=lambda *_args: [Action.move_to(0.1, 0.5, 0.0)],
    )

    report = assert_provider_contract(provider, policy_info=_policy_info())

    assert report.configured is True
    assert report.exercised_operations == ["policy"]
    assert set(provider.profile().capabilities.enabled_names()) == {"policy"}


def test_gr00t_provider_contract_unconfigured(monkeypatch) -> None:
    monkeypatch.delenv("GROOT_POLICY_HOST", raising=False)

    report = assert_provider_contract(GrootPolicyClientProvider())

    assert report.configured is False
    assert report.exercised_operations == []


def test_gr00t_policy_client_provider_passes_contract_and_emits_events() -> None:
    policy_info = _policy_info(action_horizon=2)
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

    report = assert_provider_contract(provider, policy_info=policy_info)
    result = provider.select_actions(info=policy_info)

    assert report.exercised_operations == ["policy"]
    assert provider.profile().capabilities.policy is True
    assert provider.profile().capabilities.predict is False
    assert isinstance(result, ActionPolicyResult)
    assert result.provider == "gr00t"
    assert result.action_horizon == 2
    assert result.embodiment_tag == "LIBERO_PANDA"
    assert result.raw_actions["arm"] == [[[0.1, 0.5, 0.0], [0.2, 0.5, 0.0]]]
    assert result.metadata["provider_info"] == {"latency_ms": 7.5}
    assert client.get_action_calls[-1]["observation"] == policy_info["observation"]
    assert events[-1].operation == "policy"
    assert events[-1].phase == "success"
    assert events[-1].attempt == 1
    assert events[-1].max_attempts == 1
    assert events[-1].method == "POLICYCLIENT.GET_ACTION"
    assert events[-1].target == "injected-policy-client"
    assert events[-1].metadata["timeout_ms"] == 15000
    assert events[-1].metadata["strict"] is False


@pytest.mark.parametrize(
    ("raw_actions", "expected_raw"),
    [
        ([[[0.1, 0.5, 0.0]]], {"actions": [[[0.1, 0.5, 0.0]]]}),
        (FakeArray([[[0.2, 0.5, 0.0]]]), {"actions": [[[0.2, 0.5, 0.0]]]}),
    ],
)
def test_gr00t_policy_preserves_raw_action_arrays(
    raw_actions: object,
    expected_raw: JSONDict,
) -> None:
    provider = GrootPolicyClientProvider(
        policy_client=FakeGrootClient((raw_actions, {})),
        action_translator=lambda *_args: [Action.move_to(0.1, 0.5, 0.0)],
    )

    result = provider.select_actions(info=_policy_info())

    assert result.raw_actions == expected_raw


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
    assert "fallback client packages" in provider.health().details


def test_gr00t_provider_health_reports_native_import_failures(monkeypatch) -> None:
    def fail_import(name: str) -> object:
        if name == "gr00t.policy.server_client":
            raise OSError("native loader failed")
        return __import__(name)

    monkeypatch.setattr("worldforge.providers.gr00t.importlib.import_module", fail_import)

    health = GrootPolicyClientProvider(host="127.0.0.1").health()

    assert health.healthy is False
    assert "GR00T optional dependency import failed" in health.details
    assert "native loader failed" in health.details


def test_gr00t_provider_health_reports_unreachable_policy_server() -> None:
    provider = GrootPolicyClientProvider(
        policy_client=FailingPingGrootClient(({"arm": [[[0.0]]]}, {})),
        action_translator=lambda *_args: [Action("noop")],
    )

    health = provider.health()

    assert health.healthy is False
    assert "policy server health check failed" in health.details
    assert "api_token=[redacted]" in health.details
    assert "secret" not in health.details


def test_gr00t_provider_health_reports_missing_policy_client_symbol(monkeypatch) -> None:
    monkeypatch.setitem(sys.modules, "gr00t.policy.server_client", types.SimpleNamespace())

    health = GrootPolicyClientProvider(host="127.0.0.1").health()

    assert health.healthy is False
    assert "PolicyClient is unavailable" in health.details


def test_gr00t_provider_health_reports_policy_client_creation_failures(monkeypatch) -> None:
    class FailingPolicyClient:
        def __init__(self, **_kwargs: object) -> None:
            raise RuntimeError("bad client init api_token=gr00t-secret")

    fake_server_client_module = types.SimpleNamespace(PolicyClient=FailingPolicyClient)
    monkeypatch.setitem(sys.modules, "gr00t.policy.server_client", fake_server_client_module)

    health = GrootPolicyClientProvider(host="127.0.0.1").health()

    assert health.healthy is False
    assert "Failed to create GR00T PolicyClient" in health.details
    assert "bad client init" in health.details
    assert "gr00t-secret" not in health.details
    assert "api_token=[redacted]" in health.details


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


def test_gr00t_provider_uses_zmq_fallback_when_full_client_is_unavailable(monkeypatch) -> None:
    created: list[dict[str, object]] = []

    class FallbackPolicyClient(FakeGrootClient):
        def __init__(self, **kwargs: object) -> None:
            created.append(kwargs)
            super().__init__(({"eef_9d": FakeArray([[[0.4, 0.1, 0.2]]])}, {"step": 8}))

    def fake_import(name: str) -> object:
        if name == "gr00t.policy.server_client":
            raise ImportError("full gr00t package is not installed")
        if name in {"msgpack", "numpy", "zmq"}:
            return types.SimpleNamespace()
        return __import__(name)

    monkeypatch.setattr("worldforge.providers.gr00t.importlib.import_module", fake_import)
    monkeypatch.setattr(
        "worldforge.providers.gr00t._GrootZmqPolicyClient",
        FallbackPolicyClient,
    )

    provider = GrootPolicyClientProvider(
        host="38.128.233.36",
        port=5555,
        timeout_ms=20_000,
        embodiment_tag="OXE_DROID_RELATIVE_EEF_RELATIVE_JOINT",
        action_translator=lambda *_args: [Action.move_to(0.4, 0.1, 0.2)],
    )

    assert provider.health().healthy is True
    result = provider.select_actions(info=_policy_info())

    assert created == [
        {
            "host": "38.128.233.36",
            "port": 5555,
            "timeout_ms": 20_000,
            "api_token": None,
            "strict": False,
        }
    ]
    assert result.raw_actions == {"eef_9d": [[[0.4, 0.1, 0.2]]]}
    assert result.metadata["provider_info"] == {"step": 8}


def test_gr00t_zmq_fallback_matches_official_get_action_tuple_conversion() -> None:
    client = object.__new__(_GrootZmqPolicyClient)
    calls: list[tuple[str, dict[str, object]]] = []

    def call_endpoint(endpoint: str, data: dict[str, object]) -> object:
        calls.append((endpoint, data))
        return [{"eef_9d": [[[0.1, 0.2, 0.3]]]}, {"current_step": 0}]

    client.call_endpoint = call_endpoint  # type: ignore[method-assign]

    response = client.get_action({"language": {"task": [["replay"]]}})

    assert response == (
        {"eef_9d": [[[0.1, 0.2, 0.3]]]},
        {"current_step": 0},
    )
    assert calls == [
        (
            "get_action",
            {"observation": {"language": {"task": [["replay"]]}}},
        )
    ]


def test_gr00t_zmq_fallback_calls_policy_server_endpoints(monkeypatch) -> None:
    sockets: list[FakeZmqSocket] = []

    class FakeContext:
        def socket(self, kind: int) -> FakeZmqSocket:
            assert kind == 1
            socket = FakeZmqSocket(
                [
                    {"status": "ok"},
                    [{"eef_9d": [[[0.1, 0.2, 0.3]]]}, {"current_step": 0}],
                    {"episode_index": 2},
                    {"video": {"modality_keys": ["front"]}},
                ]
            )
            sockets.append(socket)
            return socket

    class FakeZmq:
        REQ = 1
        RCVTIMEO = 2
        SNDTIMEO = 3
        MAXMSGSIZE = 4

        @staticmethod
        def Context() -> FakeContext:
            return FakeContext()

    class FakeMsgpack:
        @staticmethod
        def packb(payload: object, *, default: object) -> object:
            return payload

        @staticmethod
        def unpackb(
            payload: object,
            *,
            object_hook: object,
            raw: bool,
        ) -> object:
            assert raw is False
            if isinstance(payload, dict):
                return object_hook(payload)  # type: ignore[misc]
            return payload

    class FakeNumpy:
        class ndarray:
            pass

        @staticmethod
        def save(output: object, _obj: object, *, allow_pickle: bool) -> None:
            assert allow_pickle is False
            output.write(b"array-bytes")

        @staticmethod
        def load(_payload: object, *, allow_pickle: bool) -> list[str]:
            assert allow_pickle is False
            return ["decoded-array"]

    def fake_import(name: str) -> object:
        if name == "msgpack":
            return FakeMsgpack
        if name == "numpy":
            return FakeNumpy
        if name == "zmq":
            return FakeZmq
        return __import__(name)

    monkeypatch.setattr("worldforge.providers.gr00t.importlib.import_module", fake_import)

    client = _GrootZmqPolicyClient(
        host="gpu.example.test",
        port=5555,
        timeout_ms=321,
        api_token="client-token",
        strict=True,
    )

    assert client.ping() is True
    assert client.get_action({"language": {"task": [["replay"]]}}, options={"step": 0}) == (
        {"eef_9d": [[[0.1, 0.2, 0.3]]]},
        {"current_step": 0},
    )
    assert client.reset({"episode_index": 2}) == {"episode_index": 2}
    assert client.get_modality_config() == {"video": {"modality_keys": ["front"]}}

    socket = sockets[0]
    assert socket.options == [(2, 321), (3, 321), (4, 64 * 1024 * 1024)]
    assert socket.targets == ["tcp://gpu.example.test:5555"]
    assert socket.sent == [
        {"endpoint": "ping", "api_token": "client-token"},
        {
            "endpoint": "get_action",
            "data": {
                "observation": {"language": {"task": [["replay"]]}},
                "options": {"step": 0},
            },
            "api_token": "client-token",
        },
        {
            "endpoint": "reset",
            "data": {"options": {"episode_index": 2}},
            "api_token": "client-token",
        },
        {
            "endpoint": "get_modality_config",
            "api_token": "client-token",
        },
    ]

    encoded = client._encode_custom(FakeNumpy.ndarray())
    assert encoded == {"__ndarray_class__": True, "as_npy": b"array-bytes"}
    assert client._encode_custom({"plain": True}) == {"plain": True}
    assert client._decode_custom("plain") == "plain"
    assert client._decode_custom({"__ndarray_class__": True, "as_npy": b"array-bytes"}) == [
        "decoded-array"
    ]
    assert client._decode_custom(
        {"__ModalityConfig_class__": True, "as_json": {"delta_indices": [0]}}
    ) == {"delta_indices": [0]}


def test_gr00t_zmq_fallback_raises_protocol_server_errors() -> None:
    client = object.__new__(_GrootZmqPolicyClient)
    client.api_token = None
    client._socket = FakeZmqSocket([{"error": "bad observation api_token=server-secret"}])
    client._to_bytes = lambda payload: payload  # type: ignore[method-assign]
    client._from_bytes = lambda payload: payload  # type: ignore[method-assign]

    with pytest.raises(RuntimeError) as exc_info:
        client.call_endpoint("get_action", {"observation": {}})

    message = str(exc_info.value)
    assert "Server error: bad observation" in message
    assert "api_token=[redacted]" in message
    assert "server-secret" not in message
    assert client._socket.sent == [
        {"endpoint": "get_action", "data": {"observation": {}}},
    ]


def test_gr00t_zmq_fallback_bounds_response_and_ndarray_payloads() -> None:
    client = object.__new__(_GrootZmqPolicyClient)
    client.max_response_bytes = 4
    client.max_array_bytes = 4
    client._msgpack = None

    with pytest.raises(RuntimeError, match="response exceeds 4 bytes"):
        client._from_bytes(b"12345")

    with pytest.raises(RuntimeError, match="invalid ndarray payload"):
        client._decode_custom({"__ndarray_class__": True, "as_npy": "not-bytes"})

    with pytest.raises(RuntimeError, match="ndarray payload exceeds 4 bytes"):
        client._decode_custom({"__ndarray_class__": True, "as_npy": b"12345"})


def test_gr00t_zmq_fallback_ping_reinitializes_socket_after_failure(monkeypatch) -> None:
    sockets: list[FakeZmqSocket] = []

    class FakeContext:
        def socket(self, _kind: int) -> FakeZmqSocket:
            response = RuntimeError("timeout") if not sockets else {"status": "ok"}
            socket = FakeZmqSocket([response])
            sockets.append(socket)
            return socket

    class FakeZmq:
        REQ = 1
        RCVTIMEO = 2
        SNDTIMEO = 3

        @staticmethod
        def Context() -> FakeContext:
            return FakeContext()

    class FakeMsgpack:
        @staticmethod
        def packb(payload: object, *, default: object) -> object:
            return payload

        @staticmethod
        def unpackb(payload: object, **_kwargs: object) -> object:
            return payload

    class FakeNumpy:
        class ndarray:
            pass

    def fake_import(name: str) -> object:
        if name == "msgpack":
            return FakeMsgpack
        if name == "numpy":
            return FakeNumpy
        if name == "zmq":
            return FakeZmq
        return __import__(name)

    monkeypatch.setattr("worldforge.providers.gr00t.importlib.import_module", fake_import)

    client = _GrootZmqPolicyClient(host="gpu.example.test", port=5555, timeout_ms=321)

    assert client.ping() is False
    assert len(sockets) == 2
    assert sockets[0].sent == [{"endpoint": "ping"}]
    assert sockets[1].targets == ["tcp://gpu.example.test:5555"]


def test_gr00t_provider_reports_fallback_dependency_import_failure(monkeypatch) -> None:
    def fake_import(name: str) -> object:
        if name == "gr00t.policy.server_client":
            raise ImportError("full gr00t package missing")
        if name == "msgpack":
            raise RuntimeError("native msgpack loader failed")
        return types.SimpleNamespace()

    monkeypatch.setattr("worldforge.providers.gr00t.importlib.import_module", fake_import)

    provider = GrootPolicyClientProvider(
        host="127.0.0.1",
        action_translator=lambda *_args: [Action("noop")],
    )
    health = provider.health()

    assert health.healthy is False
    assert "fallback ZMQ client optional dependency import failed" in health.details
    assert "native msgpack loader failed" in health.details

    with pytest.raises(
        ProviderError, match="fallback ZMQ client optional dependency import failed"
    ):
        provider.select_actions(info=_policy_info())


def test_gr00t_provider_wraps_policy_client_import_runtime_failures(monkeypatch) -> None:
    def fake_import(name: str) -> object:
        if name == "gr00t.policy.server_client":
            raise RuntimeError("loader leaked api_token=secret")
        return __import__(name)

    monkeypatch.setattr("worldforge.providers.gr00t.importlib.import_module", fake_import)

    provider = GrootPolicyClientProvider(
        host="127.0.0.1",
        action_translator=lambda *_args: [Action("noop")],
    )

    with pytest.raises(ProviderError, match="Failed to import GR00T PolicyClient"):
        provider.select_actions(info=_policy_info())


def test_gr00t_policy_events_include_sanitized_remote_target_and_redacted_failures() -> None:
    events: list[ProviderEvent] = []
    client = FakeGrootClient(({"arm": [[[0.0]]]}, {}))

    def fail_get_action(_observation: object) -> object:
        raise RuntimeError("server refused bearer secret-token")

    client.get_action = fail_get_action  # type: ignore[method-assign]
    provider = GrootPolicyClientProvider(
        host="https://policy.example.test:8443/path?api_token=secret",
        port=5555,
        timeout_ms=2500,
        strict=True,
        api_token="provider-token",
        policy_client=client,
        action_translator=lambda *_args: [Action("noop")],
        event_handler=events.append,
    )

    with pytest.raises(ProviderError, match="server refused"):
        provider.select_actions(info=_policy_info())

    event = events[-1]
    payload = event.to_dict()
    assert payload["phase"] == "failure"
    assert payload["operation"] == "policy"
    assert payload["attempt"] == 1
    assert payload["max_attempts"] == 1
    assert payload["method"] == "POLICYCLIENT.GET_ACTION"
    assert payload["target"] == "https://policy.example.test:8443/path"
    assert payload["metadata"]["timeout_ms"] == 2500
    assert payload["metadata"]["strict"] is True
    assert "provider-token" not in str(payload)
    assert "secret-token" not in payload["message"]
    assert "Bearer [redacted]" in payload["message"]


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
        (
            GrootPolicyClientProvider(
                policy_client=FakeGrootClient(({"arm": [[[0.0, 0.0, 0.0]]]}, {})),
                action_translator=lambda *_args: [Action.move_to(0.0, 0.0, 0.0)],
            ),
            [],
            "JSON object",
        ),
        (
            GrootPolicyClientProvider(
                policy_client=FakeGrootClient(({"arm": [[[0.0, 0.0, 0.0]]]}, {})),
                action_translator=lambda *_args: [Action.move_to(0.0, 0.0, 0.0)],
            ),
            {"observation": "not-an-object"},
            "observation",
        ),
        (
            GrootPolicyClientProvider(
                policy_client=FakeGrootClient(({"arm": [[[0.0, 0.0, 0.0]]]}, {})),
                action_translator=lambda *_args: [Action.move_to(0.0, 0.0, 0.0)],
            ),
            {"observation": {"language": {"task": [["move"]]}}, "options": []},
            "options",
        ),
        (
            GrootPolicyClientProvider(
                policy_client=FakeGrootClient(({"arm": [[[0.0, 0.0, 0.0]]]}, {})),
                action_translator=lambda *_args: [Action.move_to(0.0, 0.0, 0.0)],
            ),
            {"observation": {"language": {"task": [["move"]]}}, "embodiment_tag": object()},
            "embodiment_tag",
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


def test_gr00t_provider_rejects_invalid_action_horizon_before_policy_call() -> None:
    client = FakeGrootClient(({"arm": [[[0.0, 0.0, 0.0]]]}, {}))
    provider = GrootPolicyClientProvider(
        policy_client=client,
        action_translator=lambda *_args: [Action.move_to(0.0, 0.0, 0.0)],
    )

    with pytest.raises(ProviderError, match="action_horizon"):
        provider.select_actions(info={**_policy_info(), "action_horizon": 0})

    assert client.get_action_calls == []


def test_gr00t_provider_rejects_invalid_embodiment_tag_before_policy_call() -> None:
    client = FakeGrootClient(({"arm": [[[0.0, 0.0, 0.0]]]}, {}))
    provider = GrootPolicyClientProvider(
        policy_client=client,
        action_translator=lambda *_args: [Action.move_to(0.0, 0.0, 0.0)],
    )

    with pytest.raises(ProviderError, match="embodiment_tag"):
        provider.select_actions(
            info={"observation": {"language": {"task": [["move"]]}}, "embodiment_tag": object()}
        )

    assert client.get_action_calls == []


def test_gr00t_provider_rejects_action_horizon_mismatch_after_translation() -> None:
    client = FakeGrootClient(({"arm": [[[0.0, 0.0, 0.0]]]}, {}))
    provider = GrootPolicyClientProvider(
        policy_client=client,
        action_translator=lambda *_args: [Action.move_to(0.0, 0.0, 0.0)],
    )

    with pytest.raises(ProviderError, match="action_horizon"):
        provider.select_actions(info={**_policy_info(), "action_horizon": 2})

    assert len(client.get_action_calls) == 1


def test_gr00t_provider_wraps_unexpected_event_sink_failure() -> None:
    events: list[str] = []

    def fail_on_success(event: ProviderEvent) -> None:
        events.append(event.phase)
        if event.phase == "success":
            raise RuntimeError("event sink down")

    provider = GrootPolicyClientProvider(
        policy_client=FakeGrootClient(({"arm": [[[0.0, 0.0, 0.0]]]}, {})),
        action_translator=lambda *_args: [Action.move_to(0.0, 0.0, 0.0)],
        event_handler=fail_on_success,
    )

    with pytest.raises(ProviderError, match="event sink down"):
        provider.select_actions(info=_policy_info())

    assert events == ["success", "failure"]


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

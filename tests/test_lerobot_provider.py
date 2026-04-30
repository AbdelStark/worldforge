from __future__ import annotations

import importlib
import math
import sys
import types

import pytest

import worldforge.providers.lerobot as lerobot_module
from worldforge import Action, ActionPolicyResult, ActionScoreResult, WorldForge, WorldForgeError
from worldforge.models import JSONDict, ProviderCapabilities, ProviderEvent, ProviderHealth
from worldforge.providers import (
    BaseProvider,
    EmbodimentActionTranslator,
    EmbodimentTranslatorContract,
    LeRobotPolicyProvider,
    MockProvider,
    ProviderError,
    ProviderProfileSpec,
)
from worldforge.testing import assert_provider_contract


def _policy_info() -> JSONDict:
    return {
        "observation": {
            "observation.state": [[0.0, 0.5, 0.0]],
            "observation.images.top": [[[[0, 0, 0]]]],
            "task": "pick up the red cube",
        },
        "embodiment_tag": "aloha",
        "action_horizon": 2,
    }


class FakeTensor:
    def __init__(self, value: object) -> None:
        self.value = value

    def tolist(self) -> object:
        return self.value


class FakeLeRobotPolicy:
    """Mimics the lerobot.policies.pretrained.PreTrainedPolicy surface."""

    def __init__(
        self,
        response: object,
        *,
        chunk_response: object | None = None,
        device: str | None = None,
    ) -> None:
        self.response = response
        self.chunk_response = chunk_response
        self.device = device
        self.reset_calls = 0
        self.select_action_calls: list[object] = []
        self.predict_action_chunk_calls: list[object] = []
        self.requires_grad_disabled = False
        self.eval_called = False

    def to(self, device: str) -> FakeLeRobotPolicy:
        self.device = device
        return self

    def eval(self) -> FakeLeRobotPolicy:
        self.eval_called = True
        return self

    def requires_grad_(self, enabled: bool) -> None:
        self.requires_grad_disabled = not enabled

    def reset(self) -> None:
        self.reset_calls += 1

    def select_action(self, observation: object) -> object:
        self.select_action_calls.append(observation)
        return self.response

    def predict_action_chunk(self, observation: object) -> object:
        self.predict_action_chunk_calls.append(observation)
        return self.chunk_response


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
                description=("Fake score provider for LeRobot policy+score planning tests."),
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


def test_lerobot_provider_contract() -> None:
    provider = LeRobotPolicyProvider(
        policy=FakeLeRobotPolicy(response=FakeTensor([[0.1, 0.5, 0.0]])),
        embodiment_tag="aloha",
        action_translator=lambda *_args: [Action.move_to(0.1, 0.5, 0.0)],
    )

    report = assert_provider_contract(provider, policy_info=_policy_info())

    assert report.configured is True
    assert report.exercised_operations == ["policy"]
    assert set(provider.profile().capabilities.enabled_names()) == {"policy"}


def test_lerobot_provider_contract_unconfigured(monkeypatch) -> None:
    monkeypatch.delenv("LEROBOT_POLICY_PATH", raising=False)
    monkeypatch.delenv("LEROBOT_POLICY", raising=False)

    report = assert_provider_contract(LeRobotPolicyProvider())

    assert report.configured is False
    assert report.exercised_operations == []


def test_lerobot_provider_rejects_missing_pretrained_module(monkeypatch) -> None:
    monkeypatch.setattr(
        lerobot_module,
        "_import_pretrained_policy_module",
        lambda: (None, None),
    )
    provider = LeRobotPolicyProvider(
        policy_path="lerobot/diffusion_pusht",
        action_translator=lambda *_args: [Action.move_to(0.0, 0.0, 0.0)],
    )

    with pytest.raises(ProviderError, match="PreTrainedPolicy module was not loaded"):
        provider.select_actions(info=_policy_info())


def test_lerobot_policy_provider_passes_contract_and_emits_events() -> None:
    response = FakeTensor([[0.1, 0.5, 0.0]])
    policy = FakeLeRobotPolicy(response)
    events: list[ProviderEvent] = []

    def translator(raw: object, _info: JSONDict, provider_info: JSONDict):
        assert provider_info == {}
        return [Action.move_to(0.1, 0.5, 0.0)]

    provider = LeRobotPolicyProvider(
        policy=policy,
        embodiment_tag="aloha",
        action_translator=translator,
        event_handler=events.append,
    )

    report = assert_provider_contract(provider, policy_info=_policy_info())
    result = provider.select_actions(info=_policy_info())

    assert report.exercised_operations == ["policy"]
    assert provider.profile().capabilities.policy is True
    assert provider.profile().capabilities.predict is False
    assert provider.profile().is_local is True
    assert isinstance(result, ActionPolicyResult)
    assert result.provider == "lerobot"
    assert result.action_horizon == 2
    assert result.embodiment_tag == "aloha"
    assert result.raw_actions == {"actions": [[0.1, 0.5, 0.0]]}
    assert result.metadata["runtime"] == "lerobot"
    assert result.metadata["mode"] == "select_action"
    assert policy.select_action_calls[-1] == _policy_info()["observation"]
    assert events[-1].operation == "policy"
    assert events[-1].phase == "success"


def test_lerobot_contract_translator_records_safe_metadata() -> None:
    contract = EmbodimentTranslatorContract(
        embodiment_tag="aloha",
        action_dim=3,
        action_horizon=2,
        metadata={"controller": "sim", "preview": {"units": "meters"}},
    )

    translator = EmbodimentActionTranslator(
        contract,
        lambda *_args: [
            Action.move_to(0.1, 0.5, 0.0),
            Action.move_to(0.2, 0.5, 0.0),
        ],
    )
    provider = LeRobotPolicyProvider(
        policy=FakeLeRobotPolicy(response=FakeTensor([[0.1, 0.5, 0.0], [0.2, 0.5, 0.0]])),
        embodiment_tag="aloha",
        action_translator=translator,
    )

    result = provider.select_actions(info=_policy_info())

    summary = result.metadata["translator_contract"]
    assert summary == {
        "embodiment_tag": "aloha",
        "action_dim": 3,
        "action_horizon": 2,
        "raw_action_shape": [2, 3],
        "metadata": {"controller": "sim", "preview": {"units": "meters"}},
    }
    assert contract.preview_summary(raw_shape=(2, 3)) == summary


def test_lerobot_contract_translator_rejects_wrong_embodiment_tag() -> None:
    translator = EmbodimentActionTranslator(
        EmbodimentTranslatorContract(embodiment_tag="aloha", action_dim=3),
        lambda *_args: [Action.move_to(0.1, 0.5, 0.0)],
    )
    provider = LeRobotPolicyProvider(
        policy=FakeLeRobotPolicy(response=FakeTensor([[0.1, 0.5, 0.0]])),
        action_translator=translator,
    )

    with pytest.raises(ProviderError, match="cannot translate actions tagged 'so100'"):
        provider.select_actions(info={**_policy_info(), "embodiment_tag": "so100"})


def test_lerobot_contract_translator_rejects_shape_and_cardinality_mismatches() -> None:
    wrong_dim = EmbodimentActionTranslator(
        EmbodimentTranslatorContract(embodiment_tag="aloha", action_dim=3),
        lambda *_args: [Action.move_to(0.1, 0.5, 0.0)],
    )
    provider = LeRobotPolicyProvider(
        policy=FakeLeRobotPolicy(response=FakeTensor([[0.1, 0.5]])),
        action_translator=wrong_dim,
    )
    with pytest.raises(ProviderError, match="action_dim=3"):
        provider.select_actions(info=_policy_info())

    wrong_count = EmbodimentActionTranslator(
        EmbodimentTranslatorContract(embodiment_tag="aloha", action_dim=3, action_horizon=2),
        lambda *_args: [Action.move_to(0.1, 0.5, 0.0)],
    )
    provider = LeRobotPolicyProvider(
        policy=FakeLeRobotPolicy(response=FakeTensor([[0.1, 0.5, 0.0], [0.2, 0.5, 0.0]])),
        action_translator=wrong_count,
    )
    with pytest.raises(ProviderError, match="expected 2"):
        provider.select_actions(info=_policy_info())


def test_lerobot_contract_translator_rejects_nonfinite_values_and_metadata() -> None:
    contract = EmbodimentTranslatorContract(embodiment_tag="aloha", action_dim=3)
    with pytest.raises(ProviderError, match="finite action values"):
        contract.validate_raw_actions(
            [[math.inf, 0.5, 0.0]],
            {"embodiment_tag": "aloha"},
            {},
        )

    with pytest.raises(ProviderError, match="translator metadata"):
        EmbodimentTranslatorContract(embodiment_tag="aloha", metadata={"bad": object()})


def test_lerobot_provider_supports_predict_action_chunk_mode() -> None:
    chunk = FakeTensor([[[0.0, 0.5, 0.0], [0.1, 0.5, 0.0]]])
    policy = FakeLeRobotPolicy(
        response=FakeTensor([[0.0, 0.0, 0.0]]),
        chunk_response=chunk,
    )
    provider = LeRobotPolicyProvider(
        policy=policy,
        action_translator=lambda *_args: [
            [Action.move_to(0.0, 0.5, 0.0), Action.move_to(0.1, 0.5, 0.0)],
        ],
    )
    info = {**_policy_info(), "mode": "predict_chunk"}

    result = provider.select_actions(info=info)

    assert result.metadata["mode"] == "predict_chunk"
    assert policy.predict_action_chunk_calls
    assert not policy.select_action_calls
    assert len(result.actions) == 2


def test_lerobot_provider_rejects_chunk_mode_when_unsupported() -> None:
    policy = FakeLeRobotPolicy(response=FakeTensor([[0.0]]))
    policy.predict_action_chunk = None  # type: ignore[method-assign]
    provider = LeRobotPolicyProvider(
        policy=policy,
        action_translator=lambda *_args: [Action.move_to(0.0, 0.0, 0.0)],
    )

    with pytest.raises(ProviderError, match="predict_action_chunk"):
        provider.select_actions(info={**_policy_info(), "mode": "predict_chunk"})


def test_lerobot_policy_only_planning_uses_policy_actions(tmp_path) -> None:
    policy = FakeLeRobotPolicy(response=FakeTensor([[0.3, 0.5, 0.0]]))
    provider = LeRobotPolicyProvider(
        policy=policy,
        action_translator=lambda *_args: [Action.move_to(0.3, 0.5, 0.0)],
    )
    forge = WorldForge(state_dir=tmp_path, auto_register_remote=False)
    forge.register_provider(provider)
    world = forge.create_world("robot-workcell", provider="mock")

    selected = forge.select_actions("lerobot", info=_policy_info())
    plan = world.plan(
        goal="push the cube",
        provider="lerobot",
        policy_info=_policy_info(),
        execution_provider="mock",
    )
    execution = world.execute_plan(plan)

    assert selected.actions == [Action.move_to(0.3, 0.5, 0.0)]
    assert plan.provider == "lerobot"
    assert plan.actions == [Action.move_to(0.3, 0.5, 0.0)]
    assert plan.metadata["planning_mode"] == "policy"
    assert plan.metadata["policy_result"]["provider"] == "lerobot"
    assert plan.success_probability == 0.5
    assert execution.final_world().provider == "mock"


def test_lerobot_policy_plus_score_planning_selects_scored_candidate(tmp_path) -> None:
    candidate_plans = [
        [Action.move_to(0.1, 0.5, 0.0)],
        [Action.move_to(0.6, 0.5, 0.0)],
        [Action.move_to(0.9, 0.5, 0.0)],
    ]
    policy = FakeLeRobotPolicy(response=FakeTensor([[0.0, 0.5, 0.0]]))
    policy_provider = LeRobotPolicyProvider(
        policy=policy,
        action_translator=lambda *_args: candidate_plans,
    )
    score_provider = FakeScoreProvider([0.7, 0.2, 0.9])
    forge = WorldForge(state_dir=tmp_path, auto_register_remote=False)
    forge.register_provider(policy_provider)
    forge.register_provider(score_provider)
    world = forge.create_world("robot-workcell", provider="mock")

    plan = world.plan(
        goal="pick lowest-cost candidate",
        provider="fake-score",
        policy_provider="lerobot",
        policy_info=_policy_info(),
        score_info={"observation": [[0.0]], "goal": [[1.0]]},
        execution_provider="mock",
    )

    assert plan.provider == "fake-score"
    assert plan.actions == candidate_plans[1]
    assert plan.metadata["planning_mode"] == "policy+score"
    assert plan.metadata["policy_provider"] == "lerobot"
    assert plan.metadata["score_provider"] == "fake-score"
    assert plan.metadata["policy_result"]["metadata"]["candidate_count"] == 3
    assert plan.metadata["score_result"]["best_index"] == 1


def test_lerobot_policy_plus_score_planning_rejects_score_count_mismatch(tmp_path) -> None:
    candidate_plans = [
        [Action.move_to(0.1, 0.5, 0.0)],
        [Action.move_to(0.6, 0.5, 0.0)],
    ]
    policy_provider = LeRobotPolicyProvider(
        policy=FakeLeRobotPolicy(response=FakeTensor([[0.0, 0.5, 0.0]])),
        action_translator=lambda *_args: candidate_plans,
    )
    score_provider = FakeScoreProvider([0.1, 0.2, 0.3])
    forge = WorldForge(state_dir=tmp_path, auto_register_remote=False)
    forge.register_provider(policy_provider)
    forge.register_provider(score_provider)
    world = forge.create_world("robot-workcell", provider="mock")

    with pytest.raises(WorldForgeError, match="returned 3 score\\(s\\) for 2 candidate"):
        world.plan(
            goal="pick lowest-cost candidate",
            provider="fake-score",
            policy_provider="lerobot",
            policy_info=_policy_info(),
            score_info={"observation": [[0.0]], "goal": [[1.0]]},
        )


def test_lerobot_provider_reports_unconfigured_and_missing_dependency(monkeypatch) -> None:
    monkeypatch.delenv("LEROBOT_POLICY_PATH", raising=False)
    monkeypatch.delenv("LEROBOT_POLICY", raising=False)
    missing = LeRobotPolicyProvider()
    assert missing.configured() is False
    assert missing.health().healthy is False
    assert "LEROBOT_POLICY_PATH" in missing.health().details

    real_import = importlib.import_module

    def no_lerobot(name: str, *args: object, **kwargs: object):
        if name == "lerobot" or name.startswith("lerobot."):
            raise ImportError("no lerobot")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(importlib, "import_module", no_lerobot)
    monkeypatch.setenv("LEROBOT_POLICY_PATH", "lerobot/act_aloha_sim_transfer_cube_human")
    unhealthy = LeRobotPolicyProvider()
    assert unhealthy.configured() is True
    assert unhealthy.health().healthy is False
    assert "lerobot" in unhealthy.health().details


def test_lerobot_provider_health_reports_optional_import_crash(monkeypatch) -> None:
    real_import = importlib.import_module

    def broken_lerobot_policy_import(name: str, *args: object, **kwargs: object):
        if name == "lerobot":
            return types.SimpleNamespace()
        if name == "lerobot.policies.pretrained":
            raise TypeError("non-default argument 'backbone_cfg' follows default argument")
        if name == "lerobot.common.policies.pretrained":
            raise ImportError("no common pretrained policy module")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(importlib, "import_module", broken_lerobot_policy_import)

    provider = LeRobotPolicyProvider(policy_path="lerobot/diffusion_pusht")
    health = provider.health()

    assert health.healthy is False
    assert "lerobot.policies.pretrained" in health.details
    assert "TypeError" in health.details
    assert "backbone_cfg" in health.details


def test_lerobot_provider_reads_env_configuration(monkeypatch) -> None:
    monkeypatch.setenv("LEROBOT_POLICY_PATH", "lerobot/diffusion_pusht")
    monkeypatch.setenv("LEROBOT_POLICY_TYPE", "diffusion")
    monkeypatch.setenv("LEROBOT_DEVICE", "cpu")
    monkeypatch.setenv("LEROBOT_CACHE_DIR", "/tmp/lerobot-cache")
    monkeypatch.setenv("LEROBOT_EMBODIMENT_TAG", "pusht")

    provider = LeRobotPolicyProvider()

    assert provider.policy_path == "lerobot/diffusion_pusht"
    assert provider.policy_type == "diffusion"
    assert provider.device == "cpu"
    assert provider.cache_dir == "/tmp/lerobot-cache"
    assert provider.embodiment_tag == "pusht"
    assert provider.profile().default_model == "lerobot/diffusion_pusht"
    assert provider.configured() is True


def test_lerobot_provider_lazily_loads_via_loader_and_applies_device() -> None:
    created: list[dict[str, object]] = []

    def loader(
        policy_path: str,
        policy_type: str | None,
        device: str | None,
        cache_dir: str | None,
    ) -> FakeLeRobotPolicy:
        created.append(
            {
                "policy_path": policy_path,
                "policy_type": policy_type,
                "device": device,
                "cache_dir": cache_dir,
            }
        )
        return FakeLeRobotPolicy(response=FakeTensor([[0.42, 0.5, 0.0]]))

    provider = LeRobotPolicyProvider(
        policy_path="lerobot/act_aloha_sim_transfer_cube_human",
        policy_type="act",
        device="cpu",
        cache_dir="/tmp/cache",
        policy_loader=loader,
        action_translator=lambda *_args: [Action.move_to(0.42, 0.5, 0.0)],
    )

    assert provider.health().healthy is True
    result = provider.select_actions(info=_policy_info())

    assert created == [
        {
            "policy_path": "lerobot/act_aloha_sim_transfer_cube_human",
            "policy_type": "act",
            "device": "cpu",
            "cache_dir": "/tmp/cache",
        }
    ]
    assert result.actions == [Action.move_to(0.42, 0.5, 0.0)]


def test_lerobot_provider_lazily_imports_pretrained_policy(monkeypatch) -> None:
    loads: list[dict[str, object]] = []

    class FakePretrainedPolicy:
        @classmethod
        def from_pretrained(cls, path: str, **kwargs: object) -> FakeLeRobotPolicy:
            loads.append({"path": path, "kwargs": kwargs})
            return FakeLeRobotPolicy(response=FakeTensor([[0.2, 0.5, 0.0]]))

    pretrained_module = types.SimpleNamespace(PreTrainedPolicy=FakePretrainedPolicy)
    policies_module = types.SimpleNamespace(pretrained=pretrained_module)
    lerobot_module = types.SimpleNamespace(policies=policies_module)
    monkeypatch.setitem(sys.modules, "lerobot", lerobot_module)
    monkeypatch.setitem(sys.modules, "lerobot.policies", policies_module)
    monkeypatch.setitem(sys.modules, "lerobot.policies.pretrained", pretrained_module)

    provider = LeRobotPolicyProvider(
        policy_path="lerobot/act_aloha_sim_transfer_cube_human",
        cache_dir="/tmp/cache",
        action_translator=lambda *_args: [Action.move_to(0.2, 0.5, 0.0)],
    )

    assert provider.health().healthy is True
    result = provider.select_actions(info=_policy_info())

    assert loads == [
        {
            "path": "lerobot/act_aloha_sim_transfer_cube_human",
            "kwargs": {"cache_dir": "/tmp/cache"},
        }
    ]
    assert result.actions == [Action.move_to(0.2, 0.5, 0.0)]


@pytest.mark.parametrize(
    ("kwargs", "match"),
    [
        ({"policy_path": " "}, "policy_path"),
        ({"policy_type": "notapolicy"}, "policy_type"),
        ({"device": " "}, "device"),
        ({"cache_dir": " "}, "cache_dir"),
        ({"embodiment_tag": " "}, "embodiment_tag"),
    ],
)
def test_lerobot_provider_rejects_invalid_configuration(
    kwargs: dict[str, object],
    match: str,
) -> None:
    with pytest.raises(WorldForgeError, match=match):
        LeRobotPolicyProvider(**kwargs)


@pytest.mark.parametrize(
    ("info", "match"),
    [
        ({}, "observation"),
        ({"observation": "not-a-dict"}, "observation"),
        ({"observation": {}}, "observation"),
        ({"observation": {"observation.state": [[0.0]]}, "options": "bad"}, "options"),
        ({"observation": {"observation.state": [[0.0]]}, "mode": "rollout"}, "mode"),
        (
            {"observation": {"observation.state": [[0.0]]}, "action_horizon": 0},
            "action_horizon",
        ),
        (
            {"observation": {"observation.state": [[0.0]]}, "action_horizon": "two"},
            "action_horizon",
        ),
    ],
)
def test_lerobot_provider_rejects_malformed_info(
    info: JSONDict,
    match: str,
) -> None:
    provider = LeRobotPolicyProvider(
        policy=FakeLeRobotPolicy(response=FakeTensor([[0.0]])),
        action_translator=lambda *_args: [Action.move_to(0.0, 0.0, 0.0)],
    )

    with pytest.raises(ProviderError, match=match):
        provider.select_actions(info=info)


@pytest.mark.parametrize(
    ("response", "translator", "match"),
    [
        (
            (FakeTensor([[0.0]]), {}, "extra"),
            lambda *_args: [Action.move_to(0.0, 0.0, 0.0)],
            "tuple",
        ),
        (
            FakeTensor([[math.nan]]),
            lambda *_args: [Action.move_to(0.0, 0.0, 0.0)],
            "finite numbers",
        ),
        (
            (FakeTensor([[0.0]]), "not-info"),
            lambda *_args: [Action.move_to(0.0, 0.0, 0.0)],
            "provider_info",
        ),
        (
            FakeTensor([[0.0]]),
            lambda *_args: [],
            "non-empty action sequence",
        ),
        (
            FakeTensor([[0.0]]),
            lambda *_args: [[object()]],
            "Action instances",
        ),
    ],
)
def test_lerobot_provider_rejects_malformed_outputs(
    response: object,
    translator,
    match: str,
) -> None:
    provider = LeRobotPolicyProvider(
        policy=FakeLeRobotPolicy(response=response),
        action_translator=translator,
    )

    with pytest.raises(ProviderError, match=match):
        provider.select_actions(info=_policy_info())


def test_lerobot_provider_wraps_policy_and_translator_failures() -> None:
    failing_policy = FakeLeRobotPolicy(response=FakeTensor([[0.0]]))

    def fail_select(_observation: object) -> object:
        raise RuntimeError("gpu unavailable")

    failing_policy.select_action = fail_select  # type: ignore[method-assign]
    provider = LeRobotPolicyProvider(
        policy=failing_policy,
        action_translator=lambda *_args: [Action("noop")],
    )
    with pytest.raises(ProviderError, match="gpu unavailable"):
        provider.select_actions(info=_policy_info())

    no_select = LeRobotPolicyProvider(
        policy=object(),
        action_translator=lambda *_args: [Action("noop")],
    )
    with pytest.raises(ProviderError, match="select_action"):
        no_select.select_actions(info=_policy_info())

    bad_translator = LeRobotPolicyProvider(
        policy=FakeLeRobotPolicy(response=FakeTensor([[0.0]])),
        action_translator=lambda *_args: (_ for _ in ()).throw(RuntimeError("bad map")),
    )
    with pytest.raises(ProviderError, match="bad map"):
        bad_translator.select_actions(info=_policy_info())


def test_lerobot_provider_missing_translator_raises() -> None:
    provider = LeRobotPolicyProvider(
        policy=FakeLeRobotPolicy(response=FakeTensor([[0.0]])),
    )
    with pytest.raises(ProviderError, match="action_translator"):
        provider.select_actions(info=_policy_info())


def test_lerobot_provider_reset_delegates_when_policy_loaded() -> None:
    policy = FakeLeRobotPolicy(response=FakeTensor([[0.0]]))
    provider = LeRobotPolicyProvider(
        policy=policy,
        action_translator=lambda *_args: [Action.move_to(0.0, 0.0, 0.0)],
    )
    provider.reset()
    assert policy.reset_calls == 1


def test_lerobot_provider_reset_is_noop_when_policy_not_loaded() -> None:
    provider = LeRobotPolicyProvider(policy_path="lerobot/act_aloha_sim_transfer_cube_human")
    provider.reset()  # should not raise


def test_lerobot_auto_registers_when_policy_path_env_set(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("LEROBOT_POLICY_PATH", "lerobot/act_aloha_sim_transfer_cube_human")
    forge = WorldForge(state_dir=tmp_path)
    assert "lerobot" in forge.providers()


def test_lerobot_not_auto_registered_without_policy_path_env(monkeypatch, tmp_path) -> None:
    monkeypatch.delenv("LEROBOT_POLICY_PATH", raising=False)
    monkeypatch.delenv("LEROBOT_POLICY", raising=False)
    forge = WorldForge(state_dir=tmp_path)
    assert "lerobot" not in forge.providers()


def test_lerobot_provider_lazily_imports_specific_policy_class(monkeypatch) -> None:
    loads: list[dict[str, object]] = []

    class FakeACTPolicy:
        @classmethod
        def from_pretrained(cls, path: str, **kwargs: object) -> FakeLeRobotPolicy:
            loads.append({"path": path, "kwargs": kwargs, "class": cls.__name__})
            return FakeLeRobotPolicy(response=FakeTensor([[0.3, 0.5, 0.0]]))

    act_module = types.SimpleNamespace(ACTPolicy=FakeACTPolicy)
    policies_module = types.SimpleNamespace(act=types.SimpleNamespace(modeling_act=act_module))
    lerobot_module = types.SimpleNamespace(policies=policies_module)
    monkeypatch.setitem(sys.modules, "lerobot", lerobot_module)
    monkeypatch.setitem(sys.modules, "lerobot.policies", policies_module)
    monkeypatch.setitem(sys.modules, "lerobot.policies.act", policies_module.act)
    monkeypatch.setitem(sys.modules, "lerobot.policies.act.modeling_act", act_module)

    provider = LeRobotPolicyProvider(
        policy_path="lerobot/act_aloha_sim_transfer_cube_human",
        policy_type="act",
        action_translator=lambda *_args: [Action.move_to(0.3, 0.5, 0.0)],
    )
    result = provider.select_actions(info=_policy_info())

    assert loads == [
        {
            "path": "lerobot/act_aloha_sim_transfer_cube_human",
            "kwargs": {},
            "class": "FakeACTPolicy",
        }
    ]
    assert result.actions == [Action.move_to(0.3, 0.5, 0.0)]


def test_lerobot_provider_falls_back_to_common_path_for_policy_class(monkeypatch) -> None:
    class FakeDiffusionPolicy:
        @classmethod
        def from_pretrained(cls, path: str, **_kwargs: object) -> FakeLeRobotPolicy:
            return FakeLeRobotPolicy(response=FakeTensor([[0.1]]))

    diffusion_modeling = types.SimpleNamespace(DiffusionPolicy=FakeDiffusionPolicy)
    monkeypatch.setitem(
        sys.modules,
        "lerobot.common.policies.diffusion.modeling_diffusion",
        diffusion_modeling,
    )

    real_import = importlib.import_module

    def selective_import(name: str, *args: object, **kwargs: object):
        if name in {
            "lerobot.policies.diffusion.modeling_diffusion",
            "lerobot.policies.diffusion",
            "lerobot.common.policies.diffusion",
        }:
            raise ImportError(f"simulated missing module {name}")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(importlib, "import_module", selective_import)

    provider = LeRobotPolicyProvider(
        policy_path="lerobot/diffusion_pusht",
        policy_type="diffusion",
        action_translator=lambda *_args: [Action.move_to(0.1, 0.0, 0.0)],
    )
    result = provider.select_actions(info=_policy_info())

    assert result.actions == [Action.move_to(0.1, 0.0, 0.0)]


def test_lerobot_provider_raises_when_no_policy_class_resolves(monkeypatch) -> None:
    real_import = importlib.import_module

    def no_policy_module(name: str, *args: object, **kwargs: object):
        if name.startswith(("lerobot.policies.vqbet", "lerobot.common.policies.vqbet")):
            raise ImportError("simulated missing vqbet module")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(importlib, "import_module", no_policy_module)

    provider = LeRobotPolicyProvider(
        policy_path="lerobot/vqbet_pusht",
        policy_type="vqbet",
        action_translator=lambda *_args: [Action.move_to(0.0, 0.0, 0.0)],
    )
    with pytest.raises(ProviderError, match="VQBeTPolicy"):
        provider.select_actions(info=_policy_info())


def test_lerobot_provider_load_errors_wrapped(monkeypatch) -> None:
    def broken_loader(*_args: object) -> FakeLeRobotPolicy:
        raise RuntimeError("checkpoint corrupt")

    provider = LeRobotPolicyProvider(
        policy_path="lerobot/act_aloha_sim_transfer_cube_human",
        policy_loader=broken_loader,
        action_translator=lambda *_args: [Action.move_to(0.0, 0.0, 0.0)],
    )
    with pytest.raises(ProviderError, match="Failed to load LeRobot policy"):
        provider.select_actions(info=_policy_info())


def test_lerobot_provider_load_without_policy_path_raises() -> None:
    provider = LeRobotPolicyProvider(
        policy_loader=lambda *_args: FakeLeRobotPolicy(response=FakeTensor([[0.0]])),
        action_translator=lambda *_args: [Action.move_to(0.0, 0.0, 0.0)],
    )
    with pytest.raises(ProviderError, match="LEROBOT_POLICY_PATH"):
        provider.select_actions(info=_policy_info())


def test_lerobot_provider_no_grad_fallback_without_torch(monkeypatch) -> None:
    real_import = importlib.import_module

    def no_torch(name: str, *args: object, **kwargs: object):
        if name == "torch":
            raise ImportError("no torch")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(importlib, "import_module", no_torch)
    policy = FakeLeRobotPolicy(response=FakeTensor([[0.2, 0.5, 0.0]]))
    provider = LeRobotPolicyProvider(
        policy=policy,
        action_translator=lambda *_args: [Action.move_to(0.2, 0.5, 0.0)],
    )
    result = provider.select_actions(info=_policy_info())

    assert result.actions == [Action.move_to(0.2, 0.5, 0.0)]


def test_policy_planning_validation_errors_for_lerobot(tmp_path) -> None:
    forge = WorldForge(state_dir=tmp_path, auto_register_remote=False)
    forge.register_provider(MockProvider(name="manual-mock"))
    world = forge.create_world("robot-workcell", provider="manual-mock")

    policy_provider = LeRobotPolicyProvider(
        policy=FakeLeRobotPolicy(response=FakeTensor([[0.0, 0.0, 0.0]])),
        action_translator=lambda *_args: [Action.move_to(0.0, 0.0, 0.0)],
    )
    forge.register_provider(policy_provider)
    with pytest.raises(WorldForgeError, match="Policy planning requires policy_info"):
        world.plan(goal="move", provider="lerobot", policy_provider="lerobot")

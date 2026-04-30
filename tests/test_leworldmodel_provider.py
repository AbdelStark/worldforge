from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from worldforge import Action, ActionScoreResult, WorldForge, WorldForgeError
from worldforge.providers import LeWorldModelProvider, ProviderError
from worldforge.testing import assert_provider_contract

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "providers"


def _fixture(name: str) -> dict[str, Any]:
    return json.loads((FIXTURE_DIR / name).read_text(encoding="utf-8"))


def _depth(value: object) -> int:
    if isinstance(value, list | tuple) and value:
        return 1 + _depth(value[0])
    return 0


def _flatten(value: object) -> list[object]:
    if isinstance(value, list | tuple):
        flattened: list[object] = []
        for item in value:
            flattened.extend(_flatten(item))
        return flattened
    return [value]


class FakeTensor:
    def __init__(self, value: object) -> None:
        self.value = value
        self.ndim = _depth(value)
        self.device: str | None = None

    def to(self, device: str) -> FakeTensor:
        self.device = device
        return self

    def detach(self) -> FakeTensor:
        return self

    def cpu(self) -> FakeTensor:
        return self

    def reshape(self, *_shape: object) -> FakeTensor:
        return FakeTensor(_flatten(self.value))

    def tolist(self) -> object:
        return self.value


class FakeNoGrad:
    def __enter__(self) -> None:
        return None

    def __exit__(self, *_args: object) -> bool:
        return False


class FakeTorch:
    Tensor = FakeTensor

    def as_tensor(self, value: object) -> FakeTensor:
        return FakeTensor(value)

    def is_tensor(self, value: object) -> bool:
        return isinstance(value, FakeTensor)

    def no_grad(self) -> FakeNoGrad:
        return FakeNoGrad()


class FakeLeWorldModel:
    def __init__(self, scores: object) -> None:
        self.scores = scores
        self.device: str | None = None
        self.eval_called = False
        self.requires_grad_disabled = False
        self.calls: list[tuple[dict[str, Any], Any]] = []

    def to(self, device: str) -> FakeLeWorldModel:
        self.device = device
        return self

    def eval(self) -> FakeLeWorldModel:
        self.eval_called = True
        return self

    def requires_grad_(self, enabled: bool) -> None:
        self.requires_grad_disabled = not enabled

    def get_cost(self, info: dict[str, Any], action_candidates: Any) -> FakeTensor:
        self.calls.append((info, action_candidates))
        return FakeTensor(self.scores)


def test_leworldmodel_provider_scores_fixture_payload_and_routes_through_forge(tmp_path) -> None:
    payload = _fixture("leworldmodel_score_request.json")
    model = FakeLeWorldModel([0.7, 0.15, 0.4])
    loaded: list[tuple[str, str | None]] = []
    events = []

    def load_model(policy: str, cache_dir: str | None) -> FakeLeWorldModel:
        loaded.append((policy, cache_dir))
        return model

    provider = LeWorldModelProvider(
        policy="pusht/lewm",
        cache_dir="/tmp/stablewm",
        device="cpu",
        model_loader=load_model,
        tensor_module=FakeTorch(),
        event_handler=events.append,
    )
    forge = WorldForge(state_dir=tmp_path, auto_register_remote=False)
    forge.register_provider(provider)

    result = forge.score_actions(
        "leworldmodel",
        info=payload["info"],
        action_candidates=payload["action_candidates"],
    )

    assert isinstance(result, ActionScoreResult)
    assert result.provider == "leworldmodel"
    assert result.scores == [0.7, 0.15, 0.4]
    assert result.best_index == 1
    assert result.best_score == 0.15
    assert result.lower_is_better is True
    assert result.metadata["score_type"] == "cost"
    assert result.metadata["score_direction"] == "lower_is_better"
    assert result.metadata["model_family"] == "LeWorldModel (LeWM)"
    assert result.metadata["official_code"] == "https://github.com/lucas-maes/le-wm"
    assert result.metadata["runtime_api"] == "stable_worldmodel.policy.AutoCostModel"
    assert result.metadata["device"] == "cpu"
    assert result.metadata["requested_device"] == "cpu"
    assert result.metadata["candidate_count"] == 3
    assert result.metadata["input_shapes"]["action_candidates"] == [1, 3, 3, 1]
    assert result.metadata["score_shape"] == [3]
    assert result.to_dict()["best_score"] == 0.15
    assert loaded == [("pusht/lewm", "/tmp/stablewm")]
    assert model.device == "cpu"
    assert model.eval_called is True
    assert model.requires_grad_disabled is True
    assert len(model.calls) == 1
    assert events[-1].operation == "score"
    assert events[-1].phase == "success"


def test_leworldmodel_provider_rejects_score_count_mismatch() -> None:
    payload = _fixture("leworldmodel_score_request.json")
    provider = LeWorldModelProvider(
        policy="pusht/lewm",
        model_loader=lambda _policy, _cache_dir: FakeLeWorldModel([0.1, 0.2]),
        tensor_module=FakeTorch(),
    )

    with pytest.raises(ProviderError, match=r"returned 2 score\(s\) for 3 candidate"):
        provider.score_actions(
            info=payload["info"],
            action_candidates=payload["action_candidates"],
        )


def test_leworldmodel_provider_rejects_ambiguous_score_tensor_shape() -> None:
    payload = _fixture("leworldmodel_score_request.json")
    provider = LeWorldModelProvider(
        policy="pusht/lewm",
        model_loader=lambda _policy, _cache_dir: FakeLeWorldModel([[0.1, 0.2], [0.3, 0.4]]),
        tensor_module=FakeTorch(),
    )

    with pytest.raises(ProviderError, match="score output shape"):
        provider.score_actions(
            info=payload["info"],
            action_candidates=[[[[0.1, 0.2]], [[0.3, 0.4]], [[0.5, 0.6]], [[0.7, 0.8]]]],
        )


def test_leworldmodel_provider_defaults_runtime_device_to_cpu() -> None:
    payload = _fixture("leworldmodel_score_request.json")
    model = FakeLeWorldModel([0.7, 0.15, 0.4])
    provider = LeWorldModelProvider(
        policy="pusht/lewm",
        model_loader=lambda _policy, _cache_dir: model,
        tensor_module=FakeTorch(),
    )

    result = provider.score_actions(
        info=payload["info"],
        action_candidates=payload["action_candidates"],
    )

    assert model.device == "cpu"
    assert result.metadata["device"] == "cpu"
    assert result.metadata["requested_device"] is None


def test_leworldmodel_score_planning_selects_best_candidate_and_execution_provider(
    tmp_path,
) -> None:
    payload = _fixture("leworldmodel_score_request.json")
    provider = LeWorldModelProvider(
        policy="pusht/lewm",
        model_loader=lambda _policy, _cache_dir: FakeLeWorldModel([0.7, 0.15, 0.4]),
        tensor_module=FakeTorch(),
    )
    forge = WorldForge(state_dir=tmp_path, auto_register_remote=False)
    forge.register_provider(provider)
    world = forge.create_world_from_prompt("room with cube", provider="mock")

    candidate_plans = [
        [Action.move_to(0.1, 0.5, 0.0)],
        [Action.move_to(0.4, 0.5, 0.0)],
        [Action.move_to(0.7, 0.5, 0.0)],
    ]
    plan = world.plan(
        goal="choose the lowest-cost LeWorldModel action",
        provider="leworldmodel",
        planner="leworldmodel-mpc",
        candidate_actions=candidate_plans,
        score_info=payload["info"],
        score_action_candidates=payload["action_candidates"],
        execution_provider="mock",
    )

    assert plan.provider == "leworldmodel"
    assert plan.actions == candidate_plans[1]
    assert plan.predicted_states == []
    assert plan.metadata["planning_mode"] == "score"
    assert plan.metadata["score_result"]["best_index"] == 1
    assert plan.metadata["execution_provider"] == "mock"

    execution = world.execute_plan(plan)
    assert execution.actions_applied == candidate_plans[1]
    assert execution.final_world().provider == "mock"

    with pytest.raises(WorldForgeError, match="requires candidate_actions"):
        world.plan(
            goal="incomplete score plan",
            provider="leworldmodel",
            score_info=payload["info"],
        )

    with pytest.raises(WorldForgeError, match="does not support score-based planning"):
        world.plan(
            goal="wrong provider",
            provider="mock",
            candidate_actions=candidate_plans,
            score_info=payload["info"],
            score_action_candidates=payload["action_candidates"],
        )

    mismatched_provider = LeWorldModelProvider(
        name="mismatched-leworldmodel",
        policy="pusht/lewm",
        model_loader=lambda _policy, _cache_dir: FakeLeWorldModel([0.1, 0.2]),
        tensor_module=FakeTorch(),
    )
    forge.register_provider(mismatched_provider)
    with pytest.raises(ProviderError, match=r"returned 2 score\(s\) for 3 candidate"):
        world.plan(
            goal="mismatched score count",
            provider="mismatched-leworldmodel",
            candidate_actions=candidate_plans,
            score_info=payload["info"],
            score_action_candidates=payload["action_candidates"],
        )


def test_leworldmodel_provider_reports_profile_health_and_auto_registration(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.setenv("LEWORLDMODEL_POLICY", "cube/lewm")
    monkeypatch.delenv("LEWM_POLICY", raising=False)

    provider = LeWorldModelProvider(model_loader=lambda _policy, _cache_dir: FakeLeWorldModel([]))
    profile = provider.profile()

    assert provider.configured() is True
    assert profile.capabilities.score is True
    assert profile.capabilities.predict is False
    assert profile.implementation_status == "stable"
    assert profile.requires_credentials is False
    assert profile.default_model == "cube/lewm"
    assert "LEWORLDMODEL_POLICY" in profile.required_env_vars

    forge = WorldForge(state_dir=tmp_path)
    assert "leworldmodel" in forge.providers()
    assert forge.provider_profile("leworldmodel").capabilities.score is True


def test_leworldmodel_provider_health_reports_missing_configuration_and_dependency(
    monkeypatch,
) -> None:
    monkeypatch.delenv("LEWORLDMODEL_POLICY", raising=False)
    monkeypatch.delenv("LEWM_POLICY", raising=False)
    unconfigured = LeWorldModelProvider(tensor_module=FakeTorch())

    assert unconfigured.health().healthy is False
    assert "LEWORLDMODEL_POLICY" in unconfigured.health().details
    with pytest.raises(ProviderError, match="set LEWORLDMODEL_POLICY"):
        unconfigured.score_actions(info={}, action_candidates=[])

    configured = LeWorldModelProvider(policy="pusht/lewm", tensor_module=FakeTorch())

    def fail_import(name: str) -> object:
        if name == "stable_worldmodel":
            raise ImportError("stable_worldmodel unavailable")
        return __import__(name)

    monkeypatch.setattr(
        "worldforge.providers.leworldmodel.importlib.import_module",
        fail_import,
    )

    health = configured.health()
    assert health.healthy is False
    assert "stable_worldmodel" in health.details


def test_leworldmodel_provider_health_reports_transitive_stable_worldmodel_imports(
    monkeypatch,
) -> None:
    provider = LeWorldModelProvider(policy="pusht/lewm", tensor_module=FakeTorch())

    def fail_import(name: str) -> object:
        if name == "stable_worldmodel":
            raise ModuleNotFoundError("No module named 'cv2'", name="cv2")
        return __import__(name)

    monkeypatch.setattr(
        "worldforge.providers.leworldmodel.importlib.import_module",
        fail_import,
    )

    health = provider.health()

    assert health.healthy is False
    assert "stable_worldmodel import failed" in health.details
    assert "cv2" in health.details


def test_leworldmodel_doctor_reports_dependency_issue_after_configuration(
    tmp_path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("LEWORLDMODEL_POLICY", "pusht/lewm")
    monkeypatch.delenv("LEWM_POLICY", raising=False)

    def fail_import(name: str) -> object:
        if name == "torch":
            raise ImportError("torch unavailable")
        return __import__(name)

    monkeypatch.setattr(
        "worldforge.providers.leworldmodel.importlib.import_module",
        fail_import,
    )

    report = WorldForge(state_dir=tmp_path).doctor()

    assert any("missing optional dependency torch" in issue for issue in report.issues)


def test_leworldmodel_provider_health_reports_native_import_failures(monkeypatch) -> None:
    provider = LeWorldModelProvider(policy="pusht/lewm")

    def fail_import(name: str) -> object:
        if name == "torch":
            raise OSError("native torch loader failed")
        return __import__(name)

    monkeypatch.setattr(
        "worldforge.providers.leworldmodel.importlib.import_module",
        fail_import,
    )

    health = provider.health()

    assert health.healthy is False
    assert "LeWorldModel optional dependency torch import failed" in health.details
    assert "native torch loader failed" in health.details


@pytest.mark.parametrize(
    ("fixture_name", "match"),
    [
        ("leworldmodel_missing_goal.json", "missing required input fields: goal"),
        ("leworldmodel_bad_action_candidates.json", "four-dimensional"),
    ],
)
def test_leworldmodel_provider_rejects_malformed_payload_fixtures(
    fixture_name: str,
    match: str,
) -> None:
    payload = _fixture(fixture_name)
    provider = LeWorldModelProvider(
        policy="pusht/lewm",
        model_loader=lambda _policy, _cache_dir: FakeLeWorldModel([0.5]),
        tensor_module=FakeTorch(),
    )

    with pytest.raises(ProviderError, match=match):
        provider.score_actions(
            info=payload["info"],
            action_candidates=payload["action_candidates"],
        )


def test_leworldmodel_provider_contract() -> None:
    payload = _fixture("leworldmodel_score_request.json")
    provider = LeWorldModelProvider(
        policy="pusht/lewm",
        model_loader=lambda _policy, _cache_dir: FakeLeWorldModel([0.7, 0.15, 0.4]),
        tensor_module=FakeTorch(),
    )

    report = assert_provider_contract(
        provider,
        score_info=payload["info"],
        score_action_candidates=payload["action_candidates"],
    )

    assert report.configured is True
    assert report.exercised_operations == ["score"]
    assert set(provider.profile().capabilities.enabled_names()) == {"score"}


def test_leworldmodel_provider_contract_unconfigured(monkeypatch) -> None:
    monkeypatch.delenv("LEWORLDMODEL_POLICY", raising=False)
    monkeypatch.delenv("LEWM_POLICY", raising=False)

    report = assert_provider_contract(LeWorldModelProvider(tensor_module=FakeTorch()))

    assert report.configured is False
    assert report.exercised_operations == []


def test_leworldmodel_provider_rejects_malformed_score_output_fixture() -> None:
    payload = _fixture("leworldmodel_score_request.json")
    score_fixture = _fixture("leworldmodel_bad_scores.json")
    provider = LeWorldModelProvider(
        policy="pusht/lewm",
        model_loader=lambda _policy, _cache_dir: FakeLeWorldModel(score_fixture["scores"]),
        tensor_module=FakeTorch(),
    )

    with pytest.raises(ProviderError, match="finite score values"):
        provider.score_actions(
            info=payload["info"],
            action_candidates=payload["action_candidates"],
        )

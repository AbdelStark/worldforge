from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import pytest

from worldforge import Action, ActionScoreResult, WorldForge, WorldForgeError
from worldforge.providers.base import ProviderError
from worldforge.providers.jepa_wms import JEPAWMSProvider, TorchHubJEPAWMSRuntime
from worldforge.smoke import jepa_wms
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


class FakeHubScoringModel:
    def __init__(self, response: object) -> None:
        self.response = response
        self.device: str | None = None
        self.eval_called = False
        self.calls: list[dict[str, Any]] = []

    def to(self, device: str) -> FakeHubScoringModel:
        self.device = device
        return self

    def eval(self) -> FakeHubScoringModel:
        self.eval_called = True
        return self

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


class FakeHub:
    def __init__(self, response: object) -> None:
        self.response = response
        self.calls: list[dict[str, Any]] = []

    def load(self, hub_repo: str, model_name: str, **kwargs: object) -> object:
        self.calls.append(
            {
                "hub_repo": hub_repo,
                "model_name": model_name,
                "kwargs": kwargs,
            }
        )
        return self.response


def _shape(value: object) -> tuple[int, ...]:
    if isinstance(value, list) and value:
        return (len(value), *_shape(value[0]))
    if isinstance(value, list):
        return (0,)
    return ()


def _transpose_3d_102(value: list) -> list:
    first, second, third = _shape(value)
    return [[[value[j][i][k] for k in range(third)] for j in range(first)] for i in range(second)]


def _map_nested(value: object, fn) -> object:
    if isinstance(value, list):
        return [_map_nested(item, fn) for item in value]
    return fn(value)


def _subtract_nested(left: object, right: object) -> object:
    if isinstance(left, list) and isinstance(right, list):
        if left and not isinstance(left[0], list) and right and not isinstance(right[0], list):
            return [l_value - r_value for l_value, r_value in zip(left, right, strict=True)]
        if left and isinstance(left[0], list) and right and not isinstance(right[0], list):
            return [_subtract_nested(row, right) for row in left]
        return [
            _subtract_nested(l_value, r_value) for l_value, r_value in zip(left, right, strict=True)
        ]
    return left - right


class FakeTensor:
    def __init__(self, value: object) -> None:
        self.value = value
        self.shape = _shape(value)
        self.ndim = len(self.shape)
        self.device: str | None = None

    def to(self, device: str) -> FakeTensor:
        self.device = device
        return self

    def __getitem__(self, index: int) -> FakeTensor:
        return FakeTensor(self.value[index])  # type: ignore[index]

    def permute(self, *order: int) -> FakeTensor:
        if order == (1, 0, 2):
            return FakeTensor(_transpose_3d_102(self.value))  # type: ignore[arg-type]
        raise AssertionError(f"unexpected permute order {order}")

    def __sub__(self, other: object) -> FakeTensor:
        other_value = other.value if isinstance(other, FakeTensor) else other
        return FakeTensor(_subtract_nested(self.value, other_value))

    def __mul__(self, other: object) -> FakeTensor:
        other_value = other.value if isinstance(other, FakeTensor) else other
        if isinstance(other_value, int | float):
            return FakeTensor(_map_nested(self.value, lambda item: item * other_value))
        raise AssertionError("fake tensor only multiplies by scalars")

    def pow(self, exponent: int) -> FakeTensor:
        return FakeTensor(_map_nested(self.value, lambda item: item**exponent))

    def mean(self, *, dim: tuple[int, ...]) -> FakeTensor:
        if dim != (1,):
            raise AssertionError(f"unexpected mean dims {dim}")
        return FakeTensor([sum(row) / len(row) for row in self.value])  # type: ignore[arg-type]

    def tolist(self) -> object:
        return self.value


class FakeTorch:
    __version__ = "2.9.0-test"

    def __init__(self, hub_response: object | None = None) -> None:
        self.hub = FakeHub(hub_response) if hub_response is not None else None
        self.seed: int | None = None

    def as_tensor(self, value: object) -> FakeTensor:
        return value if isinstance(value, FakeTensor) else FakeTensor(value)

    def manual_seed(self, seed: int) -> None:
        self.seed = seed

    def rand(self, *shape: int) -> FakeTensor:
        return FakeTensor(_zeros(shape))

    def abs(self, value: FakeTensor) -> FakeTensor:
        return FakeTensor(_map_nested(value.value, abs))

    def no_grad(self):
        class NoGrad:
            def __enter__(self) -> None:
                return None

            def __exit__(self, *_args: object) -> bool:
                return False

        return NoGrad()


def _zeros(shape: tuple[int, ...]) -> object:
    if not shape:
        return 0.0
    return [_zeros(shape[1:]) for _ in range(shape[0])]


class FakePreprocessor:
    def __init__(self) -> None:
        self.normalized_actions: object | None = None

    def normalize_actions(self, actions: object) -> object:
        self.normalized_actions = actions
        return actions


class FakeHubEncodeUnrollModel:
    def __init__(self) -> None:
        self.device: str | None = None
        self.eval_called = False
        self.encoded_act_values: list[bool] = []
        self.unroll_actions: object | None = None

    def to(self, device: str) -> FakeHubEncodeUnrollModel:
        self.device = device
        return self

    def eval(self) -> FakeHubEncodeUnrollModel:
        self.eval_called = True
        return self

    def encode(self, _value: object, *, act: bool) -> FakeTensor:
        self.encoded_act_values.append(act)
        if act:
            return FakeTensor([[0.0, 0.0]])
        return FakeTensor([[3.0, 5.0]])

    def unroll(self, _z_init: object, *, act_suffix: object) -> FakeTensor:
        self.unroll_actions = act_suffix
        return FakeTensor([[[1.0, 1.0], [3.0, 5.0], [7.0, 9.0]]])


class FakeHubEncodeWithoutActModel:
    def __init__(self) -> None:
        self.encode_calls = 0

    def encode(self, _value: object) -> FakeTensor:
        self.encode_calls += 1
        if self.encode_calls == 1:
            return FakeTensor([[0.0, 0.0]])
        return FakeTensor([[1.0, 2.0]])

    def unroll(self, _z_init: object, *, act_suffix: object) -> FakeTensor:
        return FakeTensor([[[0.0, 2.0], [3.0, 2.0], [1.0, 0.0]]])


class BrokenActionTensor:
    shape = (1, 3, 1, 3)
    ndim = 4

    def to(self, _device: str) -> BrokenActionTensor:
        return self

    def __getitem__(self, _index: int) -> object:
        return object()


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


def test_jepa_wms_torchhub_runtime_scores_and_plans_through_world(tmp_path) -> None:
    payload = _fixture("jepa_wms_success.json")
    model = FakeHubScoringModel(payload["runtime_response"])
    loader_calls: list[dict[str, Any]] = []

    def load_from_hub(hub_repo: str, model_name: str, **kwargs: object) -> object:
        loader_calls.append(
            {
                "hub_repo": hub_repo,
                "model_name": model_name,
                "kwargs": kwargs,
            }
        )
        return model, object()

    provider = JEPAWMSProvider.from_torch_hub(
        model_name="jepa_wm_pusht",
        device="cpu",
        hub_loader=load_from_hub,
        torch_module=object(),
    )
    forge = WorldForge(state_dir=tmp_path, auto_register_remote=False)
    forge.register_provider(provider)
    world = forge.create_world_from_prompt("tabletop Push-T scene", provider="mock")
    candidate_plans = [
        [Action.move_to(0.1, 0.5, 0.0)],
        [Action.move_to(0.4, 0.5, 0.0)],
        [Action.move_to(0.7, 0.5, 0.0)],
    ]

    plan = world.plan(
        goal="choose the lowest JEPA-WMS latent cost",
        provider="jepa-wms",
        planner="jepa-wms-mpc",
        candidate_actions=candidate_plans,
        score_info=payload["info"],
        score_action_candidates=payload["action_candidates"],
        execution_provider="mock",
    )

    assert plan.provider == "jepa-wms"
    assert plan.actions == candidate_plans[1]
    assert plan.metadata["planning_mode"] == "score"
    assert plan.metadata["score_result"]["best_index"] == 1
    assert plan.metadata["score_result"]["metadata"]["runtime"] == "fake-jepa-wms"
    assert plan.metadata["execution_provider"] == "mock"
    assert loader_calls == [
        {
            "hub_repo": "facebookresearch/jepa-wms",
            "model_name": "jepa_wm_pusht",
            "kwargs": {"pretrained": True, "device": "cpu"},
        }
    ]
    assert model.device == "cpu"
    assert model.eval_called is True
    assert model.calls[-1]["model_path"] == "jepa_wm_pusht"
    assert model.calls[-1]["info"] == payload["info"]

    execution = world.execute_plan(plan)
    assert execution.actions_applied == candidate_plans[1]
    assert execution.final_world().provider == "mock"


def test_jepa_wms_torchhub_runtime_falls_back_to_encode_unroll_distance() -> None:
    payload = _fixture("jepa_wms_success.json")
    model = FakeHubEncodeUnrollModel()
    preprocessor = FakePreprocessor()

    def load_from_hub(_hub_repo: str, _model_name: str, **_kwargs: object) -> object:
        return model, preprocessor

    provider = JEPAWMSProvider.from_torch_hub(
        model_name="jepa_wm_pusht",
        device="cpu",
        hub_loader=load_from_hub,
        torch_module=FakeTorch(),
    )
    score_info = {
        **payload["info"],
        "actions_are_normalized": False,
        "objective": "l2",
    }

    result = provider.score_actions(
        info=score_info,
        action_candidates=payload["action_candidates"],
    )

    assert result.scores == [10.0, 0.0, 16.0]
    assert result.best_index == 1
    assert result.metadata["runtime"] == "torchhub"
    assert result.metadata["model_name"] == "jepa_wm_pusht"
    assert result.metadata["objective"] == "l2"
    assert result.metadata["actions_are_normalized"] is False
    assert model.device == "cpu"
    assert model.eval_called is True
    assert model.encoded_act_values == [True, False]
    assert isinstance(model.unroll_actions, FakeTensor)
    assert preprocessor.normalized_actions is not None


def test_jepa_wms_torchhub_runtime_loads_from_torch_module_and_caches_model() -> None:
    payload = _fixture("jepa_wms_success.json")
    model = FakeHubScoringModel(payload["runtime_response"])
    torch = FakeTorch(model)

    provider = JEPAWMSProvider.from_torch_hub(
        model_name="jepa_wm_droid",
        device="cuda:0",
        pretrained=False,
        trust_repo=True,
        torch_module=torch,
    )

    first = provider.score_actions(
        info=payload["info"],
        action_candidates=payload["action_candidates"],
    )
    second = provider.score_actions(
        info=payload["info"],
        action_candidates=payload["action_candidates"],
    )

    assert first.best_index == 1
    assert second.best_index == 1
    assert torch.hub is not None
    assert torch.hub.calls == [
        {
            "hub_repo": "facebookresearch/jepa-wms",
            "model_name": "jepa_wm_droid",
            "kwargs": {
                "pretrained": False,
                "device": "cuda:0",
                "trust_repo": True,
            },
        }
    ]
    assert model.device == "cuda:0"
    assert model.eval_called is True


def test_jepa_wms_torchhub_runtime_scores_l1_with_encode_signature_fallback() -> None:
    payload = _fixture("jepa_wms_success.json")
    model = FakeHubEncodeWithoutActModel()

    provider = JEPAWMSProvider.from_torch_hub(
        model_name="jepa_wm_pusht",
        hub_loader=lambda *_args, **_kwargs: (model, object()),
        torch_module=FakeTorch(),
    )

    result = provider.score_actions(
        info={**payload["info"], "objective": "l1"},
        action_candidates=payload["action_candidates"],
    )

    assert result.scores == [0.5, 1.0, 1.0]
    assert result.best_index == 0
    assert result.metadata["objective"] == "l1"


def test_jepa_wms_torchhub_runtime_reports_loader_failures() -> None:
    payload = _fixture("jepa_wms_success.json")

    def fail_loader(_hub_repo: str, _model_name: str, **_kwargs: object) -> object:
        raise RuntimeError("checkpoint unavailable")

    provider = JEPAWMSProvider.from_torch_hub(
        model_name="jepa_wm_pusht",
        hub_loader=fail_loader,
        torch_module=FakeTorch(),
    )

    with pytest.raises(ProviderError, match="checkpoint unavailable"):
        provider.score_actions(
            info=payload["info"],
            action_candidates=payload["action_candidates"],
        )


def test_jepa_wms_torchhub_runtime_requires_hub_loader() -> None:
    payload = _fixture("jepa_wms_success.json")
    provider = JEPAWMSProvider.from_torch_hub(
        model_name="jepa_wm_pusht",
        torch_module=FakeTorch(),
    )

    with pytest.raises(ProviderError, match=r"torch\.hub\.load"):
        provider.score_actions(
            info=payload["info"],
            action_candidates=payload["action_candidates"],
        )


def test_jepa_wms_torchhub_runtime_rejects_empty_loader_tuple() -> None:
    payload = _fixture("jepa_wms_success.json")
    provider = JEPAWMSProvider.from_torch_hub(
        model_name="jepa_wm_pusht",
        hub_loader=lambda *_args, **_kwargs: (),
        torch_module=FakeTorch(),
    )

    with pytest.raises(ProviderError, match="empty tuple"):
        provider.score_actions(
            info=payload["info"],
            action_candidates=payload["action_candidates"],
        )


def test_jepa_wms_torchhub_runtime_requires_preprocessor_for_raw_actions() -> None:
    payload = _fixture("jepa_wms_success.json")
    provider = JEPAWMSProvider.from_torch_hub(
        model_name="jepa_wm_pusht",
        hub_loader=lambda *_args, **_kwargs: (FakeHubEncodeUnrollModel(), None),
        torch_module=FakeTorch(),
    )

    with pytest.raises(ProviderError, match="normalize_actions"):
        provider.score_actions(
            info={**payload["info"], "actions_are_normalized": False},
            action_candidates=payload["action_candidates"],
        )


def test_jepa_wms_torchhub_runtime_rejects_string_boolean_options() -> None:
    payload = _fixture("jepa_wms_success.json")
    provider = JEPAWMSProvider.from_torch_hub(
        model_name="jepa_wm_pusht",
        hub_loader=lambda *_args, **_kwargs: (FakeHubEncodeUnrollModel(), FakePreprocessor()),
        torch_module=FakeTorch(),
    )

    with pytest.raises(ProviderError, match="actions_are_normalized"):
        provider.score_actions(
            info={**payload["info"], "actions_are_normalized": "false"},
            action_candidates=payload["action_candidates"],
        )


def test_jepa_wms_torchhub_runtime_rejects_unknown_objective() -> None:
    payload = _fixture("jepa_wms_success.json")
    provider = JEPAWMSProvider.from_torch_hub(
        model_name="jepa_wm_pusht",
        hub_loader=lambda *_args, **_kwargs: (FakeHubEncodeUnrollModel(), object()),
        torch_module=FakeTorch(),
    )

    with pytest.raises(ProviderError, match="objective must be 'l1' or 'l2'"):
        provider.score_actions(
            info={**payload["info"], "objective": "cosine"},
            action_candidates=payload["action_candidates"],
        )


def test_jepa_wms_torchhub_runtime_reports_action_preparation_failures() -> None:
    payload = _fixture("jepa_wms_success.json")
    provider = JEPAWMSProvider.from_torch_hub(
        model_name="jepa_wm_pusht",
        hub_loader=lambda *_args, **_kwargs: (FakeHubEncodeUnrollModel(), object()),
        torch_module=FakeTorch(),
    )

    with pytest.raises(ProviderError, match="action tensor preparation failed"):
        provider.score_actions(
            info=payload["info"],
            action_candidates=BrokenActionTensor(),
        )


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
        ({"lower_is_better": True}, "missing required scores"),
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
        (
            ActionScoreResult(provider="other", scores=[0.4, 0.12, 0.9], best_index=1),
            "result provider",
        ),
        (
            ActionScoreResult(provider="jepa-wms", scores=[0.4], best_index=0),
            "score count",
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


def test_jepa_wms_torchhub_runtime_requires_model_name() -> None:
    with pytest.raises(WorldForgeError, match="model_name"):
        JEPAWMSProvider.from_torch_hub(model_name=" ", torch_module=object())


@pytest.mark.parametrize(
    ("kwargs", "match"),
    [
        ({"hub_repo": " "}, "hub_repo"),
        ({"pretrained": "yes"}, "pretrained"),
        ({"trust_repo": "yes"}, "trust_repo"),
    ],
)
def test_jepa_wms_torchhub_runtime_rejects_invalid_configuration(
    kwargs: dict[str, object],
    match: str,
) -> None:
    with pytest.raises(WorldForgeError, match=match):
        TorchHubJEPAWMSRuntime(model_name="jepa_wm_pusht", **kwargs)


@pytest.mark.parametrize(
    ("bad_info", "match"),
    [
        ("bad", "info must be a JSON object"),
        ({"observation": [], "goal": [[1.0]]}, "empty sequences"),
        ({"observation": [[0.0], [0.1, 0.2]], "goal": [[1.0]]}, "rectangular"),
        ({"observation": "bad", "goal": [[1.0]]}, "tensor-like object"),
        ({1: [[0.0]], "observation": [[0.0]], "goal": [[1.0]]}, "field names"),
    ],
)
def test_jepa_wms_rejects_malformed_info_values(
    bad_info: object,
    match: str,
) -> None:
    payload = _fixture("jepa_wms_success.json")
    provider = JEPAWMSProvider(
        model_path=payload["model_path"],
        runtime=FakeJEPAWMSRuntime(payload["runtime_response"]),
    )

    with pytest.raises(ProviderError, match=match):
        provider.score_actions(
            info=bad_info,  # type: ignore[arg-type]
            action_candidates=payload["action_candidates"],
        )


def test_jepa_wms_rejects_zero_candidate_tensor() -> None:
    payload = _fixture("jepa_wms_success.json")
    provider = JEPAWMSProvider(
        model_path=payload["model_path"],
        runtime=FakeJEPAWMSRuntime(payload["runtime_response"]),
    )

    with pytest.raises(ProviderError, match="at least one sample"):
        provider.score_actions(
            info=payload["info"],
            action_candidates=type("UnknownCandidates", (), {"shape": (1, -1, 1, 1)})(),
        )


def test_jepa_wms_rejects_multi_batch_action_candidates() -> None:
    payload = _fixture("jepa_wms_success.json")
    provider = JEPAWMSProvider(
        model_path=payload["model_path"],
        runtime=FakeJEPAWMSRuntime(payload["runtime_response"]),
    )

    with pytest.raises(ProviderError, match="one batch"):
        provider.score_actions(
            info=payload["info"],
            action_candidates=[payload["action_candidates"][0], payload["action_candidates"][0]],
        )


def test_jepa_wms_rejects_unconfigured_score_calls(monkeypatch) -> None:
    payload = _fixture("jepa_wms_success.json")
    monkeypatch.delenv("JEPA_WMS_MODEL_PATH", raising=False)
    provider = JEPAWMSProvider(runtime=FakeJEPAWMSRuntime(payload["runtime_response"]))

    with pytest.raises(ProviderError, match="missing JEPA_WMS_MODEL_PATH"):
        provider.score_actions(
            info=payload["info"],
            action_candidates=payload["action_candidates"],
        )


def test_jepa_wms_rejects_missing_runtime_score_calls() -> None:
    payload = _fixture("jepa_wms_success.json")
    provider = JEPAWMSProvider(model_path=payload["model_path"])

    with pytest.raises(ProviderError, match="no runtime adapter"):
        provider.score_actions(
            info=payload["info"],
            action_candidates=payload["action_candidates"],
        )


def test_jepa_wms_rejects_runtime_without_score_contract() -> None:
    payload = _fixture("jepa_wms_success.json")

    with pytest.raises(WorldForgeError, match="runtime must be callable"):
        JEPAWMSProvider(model_path=payload["model_path"], runtime=object())


def test_jepa_wms_wraps_unexpected_runtime_failures() -> None:
    payload = _fixture("jepa_wms_success.json")

    def runtime(**_kwargs: object) -> object:
        raise RuntimeError("native runtime exploded")

    provider = JEPAWMSProvider(model_path=payload["model_path"], runtime=runtime)

    with pytest.raises(ProviderError, match="native runtime exploded"):
        provider.score_actions(
            info=payload["info"],
            action_candidates=payload["action_candidates"],
        )


def test_jepa_wms_prepared_host_smoke_writes_runtime_manifest(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    fake_torch = FakeTorch(FakeHubScoringModel({"scores": [0.5, 0.1, 0.3]}))
    monkeypatch.setitem(sys.modules, "torch", fake_torch)
    summary_path = tmp_path / "results" / "summary.json"
    manifest_path = tmp_path / "run_manifest.json"

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "worldforge-smoke-jepa-wms",
            "--model-name",
            "jepa_wm_pusht",
            "--device",
            "cpu",
            "--json-output",
            str(summary_path),
            "--run-manifest",
            str(manifest_path),
        ],
    )

    assert jepa_wms.main() == 0
    captured = capsys.readouterr()
    assert "prepared-host smoke passed" in captured.out

    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert summary["runtime_version"]["torch"] == "2.9.0-test"
    assert summary["runtime_version"]["model_class"] == "FakeHubScoringModel"
    assert summary["score_summary"]["candidate_count"] == 3
    assert summary["score_summary"]["best_index"] == 1
    assert manifest["provider_profile"] == "jepa-wms"
    assert manifest["capability"] == "score"
    assert manifest["status"] == "passed"
    assert manifest["event_count"] == 1
    assert manifest["input_summary"]["runtime_version"]["torch"] == "2.9.0-test"
    assert manifest["input_summary"]["score_summary"]["best_score"] == 0.1
    assert manifest["artifact_paths"]["summary_json"] == str(summary_path)


def test_jepa_wms_prepared_host_smoke_records_failed_manifest(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.delitem(sys.modules, "torch", raising=False)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "worldforge-smoke-jepa-wms",
            "--model-name",
            "jepa_wm_pusht",
            "--run-manifest",
            str(tmp_path / "run_manifest.json"),
        ],
    )
    monkeypatch.setattr(
        jepa_wms.importlib,
        "import_module",
        lambda name: (_ for _ in ()).throw(ImportError("missing torch")),
    )

    assert jepa_wms.main() == 1
    captured = capsys.readouterr()
    assert "missing torch" in captured.err
    manifest = json.loads((tmp_path / "run_manifest.json").read_text(encoding="utf-8"))
    assert manifest["status"] == "failed"
    assert manifest["event_count"] == 0

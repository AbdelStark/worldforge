from __future__ import annotations

import argparse
import json
import sys
from contextlib import nullcontext
from pathlib import Path
from typing import Any

import pytest

from worldforge.providers import LeRobotPolicyProvider, LeWorldModelProvider
from worldforge.smoke import lerobot_leworldmodel
from worldforge.smoke.leworldmodel_bridges import get_bridge


class FakeTensor:
    def __init__(self, value: object) -> None:
        self.value = value
        self.shape = lerobot_leworldmodel._nested_shape(value)
        self.ndim = len(self.shape)

    def tolist(self) -> object:
        return self.value

    def detach(self) -> FakeTensor:
        return self

    def cpu(self) -> FakeTensor:
        return self

    def reshape(self, _shape: int) -> FakeTensor:
        flattened: list[float] = []

        def visit(value: object) -> None:
            if isinstance(value, list):
                for child in value:
                    visit(child)
                return
            flattened.append(float(value))  # type: ignore[arg-type]

        visit(self.value)
        return FakeTensor(flattened)


class FakeTorch:
    Tensor = FakeTensor

    @staticmethod
    def is_tensor(value: object) -> bool:
        return isinstance(value, FakeTensor)

    @staticmethod
    def as_tensor(value: object) -> FakeTensor:
        return FakeTensor(value)

    @staticmethod
    def no_grad() -> object:
        return nullcontext()


class FakeLeRobotPolicy:
    def __init__(self) -> None:
        self.eval_called = False
        self.reset_calls = 0

    def eval(self) -> FakeLeRobotPolicy:
        self.eval_called = True
        return self

    def requires_grad_(self, _enabled: bool) -> None:
        return None

    def reset(self) -> None:
        self.reset_calls += 1

    def predict_action_chunk(self, _observation: object) -> FakeTensor:
        return FakeTensor(
            [
                [[0.10, 0.50], [0.20, 0.50]],
                [[0.70, 0.50], [0.55, 0.50]],
            ]
        )

    def select_action(self, _observation: object) -> FakeTensor:
        return self.predict_action_chunk(_observation)


class FakeLeWorldModel:
    def get_cost(self, _info: dict[str, object], action_candidates: FakeTensor) -> FakeTensor:
        assert action_candidates.shape == (1, 2, 2, 2)
        return FakeTensor([3.0, 1.0])


def _patch_fake_providers(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_policy_provider(**kwargs: Any) -> LeRobotPolicyProvider:
        return LeRobotPolicyProvider(
            policy_path=kwargs["policy_path"],
            policy=FakeLeRobotPolicy(),
            policy_type=kwargs["policy_type"],
            device=kwargs["device"],
            cache_dir=kwargs["cache_dir"],
            embodiment_tag=kwargs["embodiment_tag"],
            action_translator=kwargs["action_translator"],
            event_handler=kwargs["event_handler"],
        )

    def fake_score_provider(**kwargs: Any) -> LeWorldModelProvider:
        return LeWorldModelProvider(
            policy=kwargs["policy"],
            cache_dir=kwargs["cache_dir"],
            device=kwargs["device"],
            model_loader=lambda _policy, _cache_dir: FakeLeWorldModel(),
            tensor_module=FakeTorch(),
            event_handler=kwargs["event_handler"],
        )

    monkeypatch.setattr(lerobot_leworldmodel, "LeRobotPolicyProvider", fake_policy_provider)
    monkeypatch.setattr(lerobot_leworldmodel, "LeWorldModelProvider", fake_score_provider)


def _write_common_inputs(tmp_path: Path) -> tuple[Path, Path, Path]:
    checkpoint = tmp_path / "stablewm/pusht/lewm_object.ckpt"
    checkpoint.parent.mkdir(parents=True)
    checkpoint.write_text("checkpoint")
    observation_path = tmp_path / "observation.json"
    observation_path.write_text(json.dumps({"observation.state": [[0.0, 0.5]]}))
    score_info_path = tmp_path / "score-info.json"
    score_info_path.write_text(
        json.dumps(
            {
                "pixels": [[[0.0]]],
                "goal": [[[1.0]]],
                "action": [[[0.0, 0.0]]],
            }
        )
    )
    return checkpoint, observation_path, score_info_path


def _write_candidate_builder(tmp_path: Path) -> Path:
    bridge_path = tmp_path / "bridge.py"
    bridge_path.write_text(
        "from worldforge.smoke.lerobot_leworldmodel import "
        "build_pusht_lewm_action_candidates\n"
        "def build(raw_actions, info, provider_info):\n"
        "    return build_pusht_lewm_action_candidates(raw_actions, info, provider_info)\n"
    )
    return bridge_path


def _args(**overrides: object) -> argparse.Namespace:
    defaults: dict[str, object] = {
        "policy_info_json": None,
        "observation_json": None,
        "observation_module": None,
        "options_json": None,
        "embodiment_tag": "pusht",
        "action_horizon": None,
        "mode": "select_action",
        "expected_action_dim": None,
        "expected_horizon": None,
    }
    defaults.update(overrides)
    return argparse.Namespace(**defaults)


def test_policy_info_loader_adds_bridge_expectations(tmp_path: Path) -> None:
    observation_path = tmp_path / "observation.json"
    observation_path.write_text(json.dumps({"observation.state": [[0.0, 0.5]]}))

    info = lerobot_leworldmodel._load_policy_info(
        _args(
            observation_json=observation_path,
            expected_action_dim=2,
            expected_horizon=4,
        )
    )

    assert info["observation"] == {"observation.state": [[0.0, 0.5]]}
    assert info["embodiment_tag"] == "pusht"
    assert info["mode"] == "select_action"
    assert info["score_bridge"]["expected_action_dim"] == 2
    assert info["score_bridge"]["expected_horizon"] == 4


def test_builtin_pusht_candidate_builder_normalizes_and_rejects_mismatch() -> None:
    raw = [[[0.1, 0.2], [0.3, 0.4]], [[0.5, 0.6], [0.7, 0.8]]]

    candidates = lerobot_leworldmodel.build_pusht_lewm_action_candidates(
        raw,
        {"score_bridge": {"expected_action_dim": 2, "expected_horizon": 2}},
        {},
    )

    assert lerobot_leworldmodel._nested_shape(candidates) == (1, 2, 2, 2)

    with pytest.raises(ValueError, match="does not match expected LeWorldModel action dim"):
        lerobot_leworldmodel.build_pusht_lewm_action_candidates(
            raw,
            {"score_bridge": {"expected_action_dim": 10}},
            {},
        )
    with pytest.raises(ValueError, match="supports one world batch"):
        lerobot_leworldmodel.build_pusht_lewm_action_candidates(
            [[[[0.1, 0.2]]], [[[0.3, 0.4]]]],
            {},
            {},
        )


def test_builtin_pusht_translator_returns_worldforge_actions() -> None:
    actions = lerobot_leworldmodel.translate_pusht_xy_actions(
        [[[0.1, 0.2], [0.3, 0.4]]],
        {"score_bridge": {"object_id": "block-1"}},
        {},
    )

    assert len(actions) == 1
    assert [action.kind for action in actions[0]] == ["move_to", "move_to"]
    assert actions[0][0].parameters["object_id"] == "block-1"
    assert actions[0][1].parameters["target"] == {"x": 0.3, "y": 0.4, "z": 0.0}

    with pytest.raises(ValueError, match="supports one world batch"):
        lerobot_leworldmodel.translate_pusht_xy_actions(
            [[[[0.1, 0.2]]], [[[0.3, 0.4]]]],
            {},
            {},
        )


def test_leworldmodel_bridge_registry_exposes_checkout_safe_pusht_metadata() -> None:
    bridge = get_bridge("pusht")

    assert bridge.observation_module == "worldforge.smoke.pusht_showcase_inputs:build_observation"
    assert bridge.score_info_module == "worldforge.smoke.pusht_showcase_inputs:build_score_info"
    assert bridge.expected_action_dim == 10
    assert bridge.expected_horizon == 4
    assert bridge.shape_summary["action_candidates"] == [1, 3, 4, 10]

    with pytest.raises(ValueError, match="Unknown LeWorldModel task bridge"):
        get_bridge("unknown")


def test_bridge_defaults_fill_smoke_inputs_without_optional_imports() -> None:
    args = _args(
        bridge="pusht",
        score_info_json=None,
        score_info_npz=None,
        score_info_module=None,
        action_candidates_json=None,
        action_candidates_npz=None,
        candidate_builder=None,
        translator=lerobot_leworldmodel.DEFAULT_TRANSLATOR,
        task=lerobot_leworldmodel.DEFAULT_TASK,
    )

    summary = lerobot_leworldmodel._apply_bridge_defaults(args)

    assert summary is not None
    assert summary["name"] == "pusht"
    assert args.observation_module == "worldforge.smoke.pusht_showcase_inputs:build_observation"
    assert args.score_info_module == "worldforge.smoke.pusht_showcase_inputs:build_score_info"
    assert (
        args.candidate_builder == "worldforge.smoke.pusht_showcase_inputs:build_action_candidates"
    )
    assert args.translator == "worldforge.smoke.pusht_showcase_inputs:translate_candidates_contract"
    assert args.expected_action_dim == 10
    assert args.expected_horizon == 4


def test_helper_loaders_and_error_paths(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("WF_TEST_VALUE", "  configured  ")
    assert lerobot_leworldmodel._env_value("WF_TEST_VALUE") == "configured"
    monkeypatch.setenv("WF_TEST_VALUE", " ")
    assert lerobot_leworldmodel._env_value("WF_TEST_VALUE") is None

    module_path = tmp_path / "factory.py"
    module_path.write_text(
        "def build_observation():\n"
        "    return {'observation.state': [[0.0, 0.5]]}\n"
        "def score_info():\n"
        "    return {'pixels': [[[0.0]]], 'goal': [[[1.0]]], 'action': [[[0.0, 0.0]]]}\n"
    )
    policy_info = lerobot_leworldmodel._load_policy_info(
        _args(observation_module=f"{module_path}:build_observation")
    )
    assert policy_info["observation"] == {"observation.state": [[0.0, 0.5]]}

    score_info = lerobot_leworldmodel._load_score_info(
        argparse.Namespace(
            score_info_json=None,
            score_info_npz=None,
            score_info_module=f"{module_path}:score_info",
        )
    )
    assert sorted(score_info) == ["action", "goal", "pixels"]

    candidate_path = tmp_path / "candidates.json"
    candidate_path.write_text(json.dumps({"action_candidates": [[[[0.1, 0.2]]]]}))
    static_candidates = lerobot_leworldmodel._load_static_action_candidates(
        argparse.Namespace(
            action_candidates_json=candidate_path,
            action_candidates_npz=None,
            action_candidates_key="action_candidates",
        )
    )
    assert lerobot_leworldmodel._nested_shape(static_candidates) == (1, 1, 1, 2)

    assert lerobot_leworldmodel._materialize_candidate_payload(
        {"score_action_candidates": (FakeTensor([1.0]), FakeTensor([2.0]))}
    ) == [[1.0], [2.0]]
    assert lerobot_leworldmodel._array_to_runtime_value(FakeTensor([3.0])) == [3.0]
    assert lerobot_leworldmodel._shape_text(FakeTensor([[1.0, 2.0]])) == "1 x 2"
    assert lerobot_leworldmodel._shape_text(object()) == "unknown"
    assert lerobot_leworldmodel._event_latency([], "lerobot", "policy") == "n/a"
    assert (
        lerobot_leworldmodel._event_latency(
            [{"provider": "lerobot", "operation": "policy", "duration_ms": 1.25}],
            "lerobot",
            "policy",
        )
        == "1.25"
    )
    assert lerobot_leworldmodel._normalize_action_candidate_tensor([0.1, 0.2]) == [[[[0.1, 0.2]]]]
    assert lerobot_leworldmodel._normalize_action_candidate_tensor([[0.1, 0.2]]) == [[[[0.1, 0.2]]]]
    assert lerobot_leworldmodel._normalize_action_candidate_tensor([[[[0.1, 0.2]]]]) == [
        [[[0.1, 0.2]]]
    ]
    assert lerobot_leworldmodel._coerce_action({"type": "noop", "parameters": {}}).kind == "noop"
    flat_actions = lerobot_leworldmodel._coerce_action_candidates(
        [{"type": "noop", "parameters": {}}]
    )
    assert flat_actions[0][0].kind == "noop"

    class BadShape:
        shape = ("bad",)

    assert lerobot_leworldmodel._shape_tuple(BadShape()) is None

    with pytest.raises(SystemExit, match="module_or_file:function"):
        lerobot_leworldmodel._load_callable("missing-colon", name="translator")
    with pytest.raises(SystemExit, match="module_or_file:function"):
        lerobot_leworldmodel._load_callable("module:", name="translator")
    with pytest.raises(SystemExit, match="Could not import"):
        lerobot_leworldmodel._load_callable("missing_module_for_test:function", name="translator")
    with pytest.raises(SystemExit, match="does not exist"):
        lerobot_leworldmodel._module_from_path(tmp_path / "missing.py")
    with pytest.raises(SystemExit, match="was not found"):
        lerobot_leworldmodel._load_callable(f"{module_path}:missing", name="translator")
    noncallable_path = tmp_path / "noncallable.py"
    noncallable_path.write_text("value = 1\n")
    with pytest.raises(SystemExit, match="not callable"):
        lerobot_leworldmodel._load_callable(f"{noncallable_path}:value", name="translator")
    list_path = tmp_path / "list.json"
    list_path.write_text(json.dumps([1, 2, 3]))
    with pytest.raises(SystemExit, match="must decode to a JSON object"):
        lerobot_leworldmodel._json_object_from_file(list_path, name="object")
    bad_json_path = tmp_path / "bad.json"
    bad_json_path.write_text("{")
    with pytest.raises(SystemExit, match="not valid JSON"):
        lerobot_leworldmodel._load_json_file(bad_json_path, name="bad")
    with pytest.raises(SystemExit, match="does not exist"):
        lerobot_leworldmodel._load_json_file(tmp_path / "missing.json", name="missing")
    with pytest.raises(SystemExit, match="requires --score-info-json"):
        lerobot_leworldmodel._load_score_info(
            argparse.Namespace(score_info_json=None, score_info_npz=None, score_info_module=None)
        )
    policy_path = tmp_path / "policy-info.json"
    options_path = tmp_path / "options.json"
    policy_path.write_text(json.dumps({"observation": {"observation.state": [[0.0]]}}))
    options_path.write_text(json.dumps({"temperature": 0.0}))
    policy_info_from_file = lerobot_leworldmodel._load_policy_info(
        _args(policy_info_json=policy_path, options_json=options_path, action_horizon=2)
    )
    assert policy_info_from_file["options"] == {"temperature": 0.0}
    assert policy_info_from_file["action_horizon"] == 2
    failing_factory_path = tmp_path / "failing_factory.py"
    failing_factory_path.write_text(
        "def fail_observation():\n"
        "    raise RuntimeError('boom')\n"
        "def bad_observation():\n"
        "    return 1\n"
        "def fail_score():\n"
        "    raise RuntimeError('boom')\n"
        "def bad_score():\n"
        "    return 1\n"
    )
    with pytest.raises(SystemExit, match="Observation factory failed"):
        lerobot_leworldmodel._load_policy_info(
            _args(observation_module=f"{failing_factory_path}:fail_observation")
        )
    with pytest.raises(SystemExit, match="Observation factory must return"):
        lerobot_leworldmodel._load_policy_info(
            _args(observation_module=f"{failing_factory_path}:bad_observation")
        )
    with pytest.raises(SystemExit, match="requires --policy-info-json"):
        lerobot_leworldmodel._load_policy_info(_args())
    with pytest.raises(SystemExit, match="Score-info factory failed"):
        lerobot_leworldmodel._load_score_info(
            argparse.Namespace(
                score_info_json=None,
                score_info_npz=None,
                score_info_module=f"{failing_factory_path}:fail_score",
            )
        )
    with pytest.raises(SystemExit, match="Score-info factory must return"):
        lerobot_leworldmodel._load_score_info(
            argparse.Namespace(
                score_info_json=None,
                score_info_npz=None,
                score_info_module=f"{failing_factory_path}:bad_score",
            )
        )
    with pytest.raises(ValueError, match="must not contain empty"):
        lerobot_leworldmodel._nested_shape([])
    with pytest.raises(ValueError, match="rectangular"):
        lerobot_leworldmodel._nested_shape([[1.0], [1.0, 2.0]])
    with pytest.raises(ValueError, match="must be numeric"):
        lerobot_leworldmodel._numeric_leaf("bad", name="value")
    with pytest.raises(ValueError, match="must be finite"):
        lerobot_leworldmodel._numeric_leaf(float("inf"), name="value")
    with pytest.raises(ValueError, match="materialize"):
        lerobot_leworldmodel._ensure_nested_list(object())
    with pytest.raises(ValueError, match="raw policy actions"):
        lerobot_leworldmodel._normalize_action_candidate_tensor([[[[[0.0]]]]])
    with pytest.raises(ValueError, match="expected LeWorldModel horizon"):
        lerobot_leworldmodel.build_pusht_lewm_action_candidates(
            [[[0.1, 0.2]]],
            {"score_bridge": {"expected_horizon": 2}},
            {},
        )
    with pytest.raises(ValueError, match="Action objects"):
        lerobot_leworldmodel._coerce_action(object())
    with pytest.raises(ValueError, match="non-empty"):
        lerobot_leworldmodel._coerce_action_candidates([])
    with pytest.raises(ValueError, match="non-empty action sequence"):
        lerobot_leworldmodel._coerce_action_candidates([[]])
    with pytest.raises(ValueError, match="at least x and y"):
        lerobot_leworldmodel.translate_pusht_xy_actions([[[0.1]]], {}, {})


def test_print_provider_events_handles_empty_log(capsys: pytest.CaptureFixture[str]) -> None:
    lerobot_leworldmodel._print_provider_events([])

    assert "no provider events emitted" in capsys.readouterr().out


def test_resolve_checkpoint_can_report_missing_path_without_requiring_it(tmp_path: Path) -> None:
    object_path, cache_dir = lerobot_leworldmodel._resolve_checkpoint(
        policy="pusht/lewm",
        stablewm_home=tmp_path / "stablewm",
        cache_dir=None,
        checkpoint=None,
        require_exists=False,
    )

    assert object_path == tmp_path / "stablewm/pusht/lewm_object.ckpt"
    assert cache_dir == tmp_path / "stablewm"
    assert not object_path.exists()


def test_main_runs_policy_score_plan_with_fake_real_runtimes(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    checkpoint, observation_path, score_info_path = _write_common_inputs(tmp_path)
    bridge_path = _write_candidate_builder(tmp_path)
    run_manifest = tmp_path / "run_manifest.json"
    _patch_fake_providers(monkeypatch)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "lewm-lerobot-real",
            "--policy-path",
            "lerobot/diffusion_pusht",
            "--checkpoint",
            str(checkpoint),
            "--observation-json",
            str(observation_path),
            "--score-info-json",
            str(score_info_path),
            "--candidate-builder",
            f"{bridge_path}:build",
            "--expected-action-dim",
            "2",
            "--expected-horizon",
            "2",
            "--json-only",
            "--run-manifest",
            str(run_manifest),
        ],
    )

    assert lerobot_leworldmodel.main() == 0

    payload = json.loads(capsys.readouterr().out)
    assert payload["mode"] == "real_lerobot_policy_plus_real_leworldmodel_score"
    assert payload["score_result"]["best_index"] == 1
    assert payload["plan"]["metadata"]["planning_mode"] == "policy+score"
    assert payload["plan"]["metadata"]["policy_provider"] == "lerobot"
    assert payload["plan"]["metadata"]["score_provider"] == "leworldmodel"
    assert payload["inputs"]["score_action_candidates_shape"] == [1, 2, 2, 2]
    assert payload["execution"]["actions_applied"] == 2
    assert payload["visualization"]["selected_candidate"] == 1
    assert payload["visualization"]["candidate_targets"][1]["index"] == 1
    manifest = json.loads(run_manifest.read_text())
    assert manifest["provider_profile"] == "lerobot-leworldmodel"
    assert manifest["capability"] == "policy+score"
    assert manifest["status"] == "passed"
    assert manifest["event_count"] == len(payload["provider_events"])
    assert manifest["input_fixture_digest"].startswith("sha256:")
    assert manifest["input_summary"]["score_shapes"]["action_candidates"] == [1, 2, 2, 2]
    assert set(manifest["artifact_paths"]) == {"worldforge_state"}


def test_main_json_flow_can_write_rerun_recording(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    pytest.importorskip("rerun")
    checkpoint, observation_path, score_info_path = _write_common_inputs(tmp_path)
    bridge_path = _write_candidate_builder(tmp_path)
    rerun_output = tmp_path / "robotics.rrd"
    _patch_fake_providers(monkeypatch)
    monkeypatch.setenv("RERUN", "on")
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "lewm-lerobot-real",
            "--policy-path",
            "lerobot/diffusion_pusht",
            "--checkpoint",
            str(checkpoint),
            "--observation-json",
            str(observation_path),
            "--score-info-json",
            str(score_info_path),
            "--candidate-builder",
            f"{bridge_path}:build",
            "--expected-action-dim",
            "2",
            "--expected-horizon",
            "2",
            "--rerun-output",
            str(rerun_output),
            "--json-only",
        ],
    )

    assert lerobot_leworldmodel.main() == 0

    payload = json.loads(capsys.readouterr().out)
    assert payload["rerun"]["recording_written"] is True
    assert payload["rerun"]["recording_size_bytes"] > 0
    assert rerun_output.is_file()


def test_main_visual_static_candidate_path_skips_execution(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    checkpoint, observation_path, score_info_path = _write_common_inputs(tmp_path)
    candidates_path = tmp_path / "candidates.json"
    candidates_path.write_text(
        json.dumps(
            {
                "action_candidates": [
                    [
                        [[0.10, 0.50], [0.20, 0.50]],
                        [[0.70, 0.50], [0.55, 0.50]],
                    ]
                ]
            }
        )
    )
    json_output = tmp_path / "summary.json"
    run_manifest = tmp_path / "run_manifest.json"
    _patch_fake_providers(monkeypatch)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "lewm-lerobot-real",
            "--policy-path",
            "lerobot/diffusion_pusht",
            "--checkpoint",
            str(checkpoint),
            "--observation-json",
            str(observation_path),
            "--score-info-json",
            str(score_info_path),
            "--action-candidates-json",
            str(candidates_path),
            "--expected-action-dim",
            "2",
            "--expected-horizon",
            "2",
            "--json-output",
            str(json_output),
            "--run-manifest",
            str(run_manifest),
            "--no-execute",
            "--no-color",
        ],
    )

    assert lerobot_leworldmodel.main() == 0

    output = capsys.readouterr().out
    assert "WorldForge real robotics policy+world-model inference" in output
    assert "Pipeline map" in output
    assert "Runtime profile" in output
    assert "Score summary" in output
    assert "Candidate cost landscape" in output
    assert "Candidate targets" in output
    assert "Tabletop replay" in output
    assert "Skip local mock execution" in output
    payload = json.loads(json_output.read_text())
    assert payload["execution"] is None
    assert payload["visualization"]["candidate_targets"][0]["index"] == 0
    manifest = json.loads(run_manifest.read_text())
    assert manifest["artifact_paths"] == {
        "policy_summary": str(json_output),
        "score_summary": str(json_output),
        "report_summary": str(json_output),
        "worldforge_state": payload["state_dir"],
    }


def test_main_preflight_failure_prints_runtime_command(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    checkpoint, _observation_path, _score_info_path = _write_common_inputs(tmp_path)

    class UnhealthyProvider:
        def __init__(self, **_kwargs: object) -> None:
            return None

        @staticmethod
        def health() -> object:
            return type(
                "Health",
                (),
                {
                    "to_dict": lambda self: {
                        "name": "provider",
                        "healthy": False,
                        "details": "missing runtime",
                    }
                },
            )()

    monkeypatch.setattr(lerobot_leworldmodel, "LeRobotPolicyProvider", UnhealthyProvider)
    monkeypatch.setattr(lerobot_leworldmodel, "LeWorldModelProvider", UnhealthyProvider)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "lewm-lerobot-real",
            "--policy-path",
            "lerobot/diffusion_pusht",
            "--checkpoint",
            str(checkpoint),
            "--health-only",
            "--no-color",
        ],
    )

    assert lerobot_leworldmodel.main() == 1

    output = capsys.readouterr().out
    assert "Runtime preflight failed" in output
    assert "scripts/lewm-lerobot-real" in output


def test_main_health_only_json_output_with_fake_real_runtimes(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    checkpoint, _observation_path, _score_info_path = _write_common_inputs(tmp_path)
    json_output = tmp_path / "health.json"
    _patch_fake_providers(monkeypatch)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "lewm-lerobot-real",
            "--policy-path",
            "lerobot/diffusion_pusht",
            "--checkpoint",
            str(checkpoint),
            "--health-only",
            "--json-only",
            "--json-output",
            str(json_output),
        ],
    )

    assert lerobot_leworldmodel.main() == 0

    stdout_payload = json.loads(capsys.readouterr().out)
    file_payload = json.loads(json_output.read_text())
    assert stdout_payload["checkpoint_exists"] is True
    assert stdout_payload["health"]["lerobot"]["healthy"] is True
    assert file_payload["health"]["leworldmodel"]["healthy"] is True


def test_main_health_only_reports_missing_checkpoint_without_loading_inputs(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _patch_fake_providers(monkeypatch)
    missing_home = tmp_path / "stablewm"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "lewm-lerobot-real",
            "--policy-path",
            "lerobot/diffusion_pusht",
            "--stablewm-home",
            str(missing_home),
            "--health-only",
            "--json-only",
        ],
    )

    assert lerobot_leworldmodel.main() == 1

    payload = json.loads(capsys.readouterr().out)
    assert payload["checkpoint"] == str(missing_home / "pusht/lewm_object.ckpt")
    assert payload["checkpoint_exists"] is False
    assert payload["health"]["leworldmodel"]["healthy"] is False
    assert "object checkpoint not found" in payload["health"]["leworldmodel"]["details"]

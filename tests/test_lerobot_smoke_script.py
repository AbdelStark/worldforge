from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType

import pytest


def _load_script() -> ModuleType:
    script_path = Path(__file__).resolve().parents[1] / "scripts" / "smoke_lerobot_policy.py"
    spec = importlib.util.spec_from_file_location("smoke_lerobot_policy", script_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _args(**overrides: object) -> argparse.Namespace:
    defaults: dict[str, object] = {
        "policy_info_json": None,
        "observation_json": None,
        "observation_module": None,
        "options_json": None,
        "embodiment_tag": None,
        "action_horizon": None,
        "mode": "select_action",
        "policy_path": "lerobot/act_aloha_sim_transfer_cube_human",
        "policy_type": None,
        "device": "cpu",
        "cache_dir": None,
        "translator": None,
        "health_only": False,
        "run_manifest": None,
    }
    defaults.update(overrides)
    return argparse.Namespace(**defaults)


def test_smoke_script_loads_file_callables(tmp_path: Path) -> None:
    module_path = tmp_path / "translator.py"
    module_path.write_text(
        "def translate(raw_actions, info, provider_info):\n"
        "    return (raw_actions, info, provider_info)\n"
    )
    script = _load_script()

    loaded = script._load_callable(f"{module_path}:translate", name="translator")

    assert loaded({"actions": []}, {"observation": {}}, {}) == (
        {"actions": []},
        {"observation": {}},
        {},
    )


def test_smoke_script_health_only_main_writes_skipped_manifest(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    script = _load_script()
    run_manifest = tmp_path / "run" / "run_manifest.json"
    provider_kwargs: dict[str, object] = {}

    class FakeHealth:
        healthy = True
        details = "configured"

        def to_dict(self) -> dict[str, object]:
            return {"name": "lerobot", "healthy": True, "details": self.details}

    class FakeProvider:
        def __init__(self, **kwargs: object) -> None:
            provider_kwargs.update(kwargs)

        def health(self) -> FakeHealth:
            return FakeHealth()

        def select_actions(self, *, info: dict[str, object]) -> object:
            raise AssertionError("health-only smoke must not run policy inference")

    monkeypatch.setattr(script, "LeRobotPolicyProvider", FakeProvider)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "smoke_lerobot_policy.py",
            "--policy-path",
            "lerobot/act_aloha_sim_transfer_cube_human",
            "--health-only",
            "--run-manifest",
            str(run_manifest),
        ],
    )

    assert script.main() == 0

    payload = json.loads(capsys.readouterr().out)
    assert payload["health"]["healthy"] is True
    assert provider_kwargs["action_translator"] is None
    manifest = json.loads(run_manifest.read_text())
    assert manifest["provider_profile"] == "lerobot"
    assert manifest["capability"] == "policy"
    assert manifest["status"] == "skipped"
    assert manifest["event_count"] == 0


def test_smoke_script_builds_policy_info_from_json_files(tmp_path: Path) -> None:
    policy_path = tmp_path / "policy.json"
    options_path = tmp_path / "options.json"
    policy_path.write_text(
        json.dumps(
            {
                "observation": {
                    "observation.state": [[0.0, 0.5, 0.0]],
                    "task": "pick up the cube",
                }
            }
        )
    )
    options_path.write_text(json.dumps({"temperature": 0.1}))
    script = _load_script()

    info = script._load_policy_info(
        _args(
            policy_info_json=policy_path,
            options_json=options_path,
            embodiment_tag="aloha",
            action_horizon=8,
            mode="predict_chunk",
        )
    )

    assert info == {
        "observation": {
            "observation.state": [[0.0, 0.5, 0.0]],
            "task": "pick up the cube",
        },
        "options": {"temperature": 0.1},
        "embodiment_tag": "aloha",
        "action_horizon": 8,
        "mode": "predict_chunk",
    }


def test_smoke_script_builds_policy_info_from_observation_factory(tmp_path: Path) -> None:
    module_path = tmp_path / "observation.py"
    module_path.write_text(
        "def build():\n"
        "    return {\n"
        "        'observation.state': [[0.0, 0.5, 0.0]],\n"
        "        'task': 'open the drawer',\n"
        "    }\n"
    )
    script = _load_script()

    info = script._load_policy_info(_args(observation_module=f"{module_path}:build"))

    assert info == {
        "observation": {
            "observation.state": [[0.0, 0.5, 0.0]],
            "task": "open the drawer",
        },
        "mode": "select_action",
    }


def test_smoke_script_rejects_missing_policy_info(tmp_path: Path) -> None:
    script = _load_script()

    with pytest.raises(SystemExit, match="Live policy smoke requires"):
        script._load_policy_info(_args())


def test_smoke_script_rejects_non_json_object_policy_info(tmp_path: Path) -> None:
    policy_path = tmp_path / "policy.json"
    policy_path.write_text(json.dumps([1, 2, 3]))
    script = _load_script()

    with pytest.raises(SystemExit, match="must decode to a JSON object"):
        script._load_policy_info(_args(policy_info_json=policy_path))


def test_smoke_script_rejects_nonexistent_module_file(tmp_path: Path) -> None:
    script = _load_script()

    with pytest.raises(SystemExit, match="does not exist"):
        script._load_callable(f"{tmp_path}/does_not_exist.py:translate", name="translator")


def test_smoke_script_rejects_invalid_callable_spec() -> None:
    script = _load_script()

    with pytest.raises(SystemExit, match="module_or_file:function"):
        script._load_callable("no-colon-here", name="translator")

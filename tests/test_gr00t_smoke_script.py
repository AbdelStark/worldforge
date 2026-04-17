from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path
from types import ModuleType

import pytest


def _load_script() -> ModuleType:
    script_path = Path(__file__).resolve().parents[1] / "scripts" / "smoke_gr00t_policy.py"
    spec = importlib.util.spec_from_file_location("smoke_gr00t_policy", script_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _args(**overrides: object) -> argparse.Namespace:
    defaults = {
        "policy_info_json": None,
        "observation_json": None,
        "observation_module": None,
        "options_json": None,
        "embodiment_tag": None,
        "action_horizon": None,
        "gr00t_root": None,
        "model_path": None,
        "dataset_path": None,
        "host": "127.0.0.1",
        "port": 5555,
        "device": "cuda:0",
        "server_host": "127.0.0.1",
        "server_arg": [],
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

    assert loaded({"arm": []}, {"observation": {}}, {}) == (
        {"arm": []},
        {"observation": {}},
        {},
    )


def test_smoke_script_builds_policy_info_from_json_files(tmp_path: Path) -> None:
    policy_path = tmp_path / "policy.json"
    options_path = tmp_path / "options.json"
    policy_path.write_text(
        json.dumps(
            {
                "observation": {
                    "language": {"task": [["pick up the cube"]]},
                }
            }
        )
    )
    options_path.write_text(json.dumps({"episode_index": 2}))
    script = _load_script()

    info = script._load_policy_info(
        _args(
            policy_info_json=policy_path,
            options_json=options_path,
            embodiment_tag="GR1",
            action_horizon=8,
        )
    )

    assert info == {
        "observation": {"language": {"task": [["pick up the cube"]]}},
        "options": {"episode_index": 2},
        "embodiment_tag": "GR1",
        "action_horizon": 8,
    }


def test_smoke_script_builds_policy_info_from_observation_factory(tmp_path: Path) -> None:
    module_path = tmp_path / "observation.py"
    module_path.write_text(
        "def build():\n    return {'language': {'task': [['open the drawer']]}}\n"
    )
    script = _load_script()

    info = script._load_policy_info(_args(observation_module=f"{module_path}:build"))

    assert info == {
        "observation": {
            "language": {"task": [["open the drawer"]]},
        }
    }


def test_smoke_script_rejects_missing_server_checkout(tmp_path: Path) -> None:
    script = _load_script()

    with pytest.raises(SystemExit, match="Isaac-GR00T checkout"):
        script._server_command(_args(gr00t_root=tmp_path))

from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path
from types import ModuleType

import pytest

from worldforge import Action
from worldforge.models import ProviderHealth


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
        "allow_observation_code": False,
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

    loaded = script._load_callable(
        f"{module_path}:translate",
        name="translator",
        allow_code=True,
    )

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

    info = script._load_policy_info(
        _args(observation_module=f"{module_path}:build", allow_observation_code=True)
    )

    assert info == {
        "observation": {
            "language": {"task": [["open the drawer"]]},
        }
    }


def test_smoke_script_rejects_missing_server_checkout(tmp_path: Path) -> None:
    script = _load_script()

    with pytest.raises(SystemExit, match="Isaac-GR00T checkout"):
        script._server_command(_args(gr00t_root=tmp_path))


def test_smoke_script_requires_translator_code_opt_in(tmp_path: Path) -> None:
    policy_path = tmp_path / "policy_info.json"
    policy_path.write_text(
        json.dumps({"observation": {"language": {"task": [["fold the cloth"]]}}}),
        encoding="utf-8",
    )
    translator_path = tmp_path / "translator.py"
    translator_path.write_text(
        "def translate(raw_actions, info, provider_info):\n    return []\n",
        encoding="utf-8",
    )
    script = _load_script()

    with pytest.raises(SystemExit, match="allow-translator-code"):
        script.main(
            [
                "--host",
                "127.0.0.1",
                "--policy-info-json",
                str(policy_path),
                "--translator",
                f"{translator_path}:translate",
            ]
        )


def test_smoke_script_requires_observation_code_opt_in(tmp_path: Path) -> None:
    module_path = tmp_path / "observation.py"
    module_path.write_text("def build():\n    return {'observation': {'language': {}}}\n")
    script = _load_script()

    with pytest.raises(SystemExit, match="allow-observation-code"):
        script._load_policy_info(_args(observation_module=f"{module_path}:build"))


def test_smoke_script_writes_health_only_manifest(tmp_path: Path, monkeypatch) -> None:
    manifest_path = tmp_path / "runs" / "gr00t-health" / "run_manifest.json"
    script = _load_script()

    class StubGrootProvider:
        def __init__(self, *args, **kwargs) -> None:
            pass

        def health(self) -> ProviderHealth:
            return ProviderHealth(
                name="gr00t",
                healthy=True,
                latency_ms=0.1,
                details="reachable",
            )

    monkeypatch.setattr(script, "GrootPolicyClientProvider", StubGrootProvider)

    assert (
        script.main(
            [
                "--host",
                "127.0.0.1",
                "--health-only",
                "--run-manifest",
                str(manifest_path),
            ]
        )
        == 0
    )

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["provider_profile"] == "gr00t"
    assert manifest["capability"] == "policy"
    assert manifest["status"] == "skipped"
    assert manifest["event_count"] == 0


def test_smoke_script_writes_failed_manifest_on_translator_error(
    tmp_path: Path,
    monkeypatch,
) -> None:
    policy_path = tmp_path / "policy_info.json"
    policy_path.write_text(
        json.dumps({"observation": {"language": {"task": [["fold the cloth"]]}}}),
        encoding="utf-8",
    )
    translator_path = tmp_path / "translator.py"
    translator_path.write_text(
        "def translate(raw_actions, info, provider_info):\n"
        "    raise RuntimeError('token=gr00t-secret')\n",
        encoding="utf-8",
    )
    manifest_path = tmp_path / "runs" / "gr00t-failed" / "run_manifest.json"
    script = _load_script()

    class StubGrootProvider:
        def __init__(self, *args, **kwargs) -> None:
            self.action_translator = kwargs["action_translator"]

        def health(self) -> ProviderHealth:
            return ProviderHealth(
                name="gr00t",
                healthy=True,
                latency_ms=0.1,
                details="reachable",
            )

        def select_actions(self, *, info: dict[str, object]):
            try:
                self.action_translator({"actions": [[[0.1, 0.2, 0.3]]]}, info, {})
            except RuntimeError as exc:
                raise RuntimeError(f"translator failed: {exc}") from exc
            return Action.move_to(0.1, 0.2, 0.3)

    monkeypatch.setattr(script, "GrootPolicyClientProvider", StubGrootProvider)

    with pytest.raises(SystemExit) as exc_info:
        script.main(
            [
                "--host",
                "127.0.0.1",
                "--policy-info-json",
                str(policy_path),
                "--translator",
                f"{translator_path}:translate",
                "--allow-translator-code",
                "--run-manifest",
                str(manifest_path),
            ]
        )

    assert "gr00t-secret" not in str(exc_info.value)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    exported = json.dumps(manifest, sort_keys=True)
    assert manifest["provider_profile"] == "gr00t"
    assert manifest["status"] == "failed"
    assert "gr00t-secret" not in exported

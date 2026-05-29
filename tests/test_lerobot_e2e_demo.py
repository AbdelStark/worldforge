from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType

import pytest

from worldforge.demos import lerobot_e2e


def _load_demo() -> ModuleType:
    script_path = Path(__file__).resolve().parents[1] / "examples" / "lerobot_e2e_demo.py"
    spec = importlib.util.spec_from_file_location("lerobot_e2e_demo", script_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_lerobot_e2e_demo_runs_full_policy_plus_score_flow(tmp_path: Path) -> None:
    demo = _load_demo()

    summary = demo.run_demo(state_dir=tmp_path, emit=False)

    assert summary["demo_kind"] == "lerobot_provider_surface"
    assert summary["runtime_mode"] == "injected_deterministic_policy"
    assert summary["uses_real_upstream_checkpoint"] is False
    assert summary["uses_lerobot_provider"] is True
    assert summary["uses_worldforge_policy_plus_score_planning"] is True
    assert summary["providers"] == ["demo-distance-score", "lerobot", "mock"]
    assert summary["lerobot_health"]["healthy"] is True
    assert summary["policy_candidate_count"] == 3
    assert summary["candidate_costs"] == [0.2, 0.0, 0.4]
    assert summary["selected_candidate_index"] == 1
    assert summary["plan"]["metadata"]["planning_mode"] == "policy+score"
    assert summary["plan"]["metadata"]["policy_provider"] == "lerobot"
    assert summary["plan"]["metadata"]["score_provider"] == "demo-distance-score"
    assert summary["plan"]["metadata"]["policy_result"]["provider"] == "lerobot"
    assert summary["final_cube_position"] == {"x": 0.55, "y": 0.5, "z": 0.0}
    assert summary["saved_world_id"] in summary["saved_worlds"]
    assert summary["event_phases"] == ["success", "success"]
    assert summary["policy_eval_called"] is True
    assert summary["policy_requires_grad_disabled"] is True
    assert summary["policy_reset_calls"] == 1
    assert summary["policy_select_calls"] == 2


def test_lerobot_e2e_demo_main_json_only(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "worldforge-demo-lerobot",
            "--state-dir",
            str(tmp_path),
            "--json-only",
        ],
    )

    assert lerobot_e2e.main() == 0

    summary = json.loads(capsys.readouterr().out)
    assert summary["demo_kind"] == "lerobot_provider_surface"
    assert summary["uses_real_upstream_checkpoint"] is False

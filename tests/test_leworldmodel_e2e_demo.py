from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType

import pytest

from worldforge.demos import leworldmodel_e2e


def _load_demo() -> ModuleType:
    script_path = Path(__file__).resolve().parents[1] / "examples" / "leworldmodel_e2e_demo.py"
    spec = importlib.util.spec_from_file_location("leworldmodel_e2e_demo", script_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_leworldmodel_e2e_demo_runs_full_score_plan_execute_persist_flow(tmp_path: Path) -> None:
    demo = _load_demo()

    summary = demo.run_demo(state_dir=tmp_path, emit=False)

    assert summary["demo_kind"] == "leworldmodel_provider_surface"
    assert summary["runtime_mode"] == "injected_deterministic_cost_model"
    assert summary["uses_real_upstream_checkpoint"] is False
    assert summary["uses_leworldmodel_provider"] is True
    assert summary["uses_worldforge_score_planning"] is True
    assert summary["providers"] == ["leworldmodel", "mock"]
    assert summary["leworldmodel_health"]["healthy"] is True
    assert summary["candidate_costs"] == [0.2175, 0.0275, 0.4475]
    assert summary["selected_candidate_index"] == 1
    assert summary["plan"]["metadata"]["planning_mode"] == "score"
    assert summary["plan"]["metadata"]["score_result"]["best_index"] == 1
    assert summary["final_cube_position"] == {"x": 0.55, "y": 0.5, "z": 0.0}
    assert summary["saved_world_id"] in summary["saved_worlds"]
    assert summary["event_phases"] == ["success", "success"]
    assert summary["runtime_eval_called"] is True
    assert summary["runtime_grad_disabled"] is True


def test_leworldmodel_e2e_demo_prints_human_summary(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    summary = leworldmodel_e2e.run_demo(state_dir=tmp_path, emit=True)

    output = capsys.readouterr().out

    assert summary["selected_candidate_index"] == 1
    assert "WorldForge LeWorldModel provider demo" in output
    assert "Checkpoint inference: not used" in output
    assert "candidate 1: 0.0275 <- selected" in output


def test_leworldmodel_e2e_demo_main_json_only(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "worldforge-demo-leworldmodel",
            "--state-dir",
            str(tmp_path),
            "--json-only",
        ],
    )

    assert leworldmodel_e2e.main() == 0

    summary = json.loads(capsys.readouterr().out)
    assert summary["demo_kind"] == "leworldmodel_provider_surface"
    assert summary["uses_real_upstream_checkpoint"] is False


def test_leworldmodel_e2e_demo_rejects_non_vector_goal() -> None:
    with pytest.raises(ValueError, match="nested numeric vector"):
        leworldmodel_e2e._first_vector(1.0)

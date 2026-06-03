from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType

import pytest

from worldforge.cli import main as cli_main
from worldforge.demos import so101_replay_trace
from worldforge.models import WorldForgeError


def _load_demo() -> ModuleType:
    script_path = Path(__file__).resolve().parents[1] / "examples" / "so101_replay_trace_demo.py"
    spec = importlib.util.spec_from_file_location("so101_replay_trace_demo", script_path)
    if spec is None:
        raise AssertionError("so101 replay trace demo module spec could not be created.")
    if spec.loader is None:
        raise AssertionError("so101 replay trace demo module spec has no loader.")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_so101_replay_trace_demo_selects_and_explains_best_candidate() -> None:
    demo = _load_demo()

    summary = demo.run_demo(emit=False)

    assert summary["demo_kind"] == "so101_replay_decision_trace"
    assert summary["runtime_mode"] == "deterministic_replay_fixture"
    assert summary["uses_real_robot_hardware"] is False
    assert summary["uses_lerobot_runtime"] is False
    assert summary["uses_dimos_runtime"] is False
    assert summary["planning_mode"] == "score"
    assert summary["providers"] == ["mock", "so101-replay-score"]
    assert summary["score_provider_health"]["healthy"] is True
    assert summary["score_result"]["provider"] == "so101-replay-score"
    assert summary["score_result"]["best_index"] == summary["selected_candidate_index"]
    assert summary["dataset_reference"]["repo_id"] == "lerobot/svla_so101_pickplace"
    assert summary["dataset_reference"]["total_episodes"] == 50
    assert summary["dataset_reference"]["total_frames"] == 11939

    trace = summary["trace"]
    assert trace["schema_version"] == "worldforge.robot_decision_trace.v0"
    assert trace["embodiment"] == "so101_manipulation"
    assert len(trace["candidate_actions"]) == 4
    assert len(trace["candidate_scores"]) == 4
    assert trace["selected_action"]["candidate_id"] == "lift-place-stable"
    assert trace["selected_action"]["score"] == min(summary["candidate_costs"])
    assert trace["selected_action"]["score_margin_to_runner_up"] > 0
    assert "Lowest weighted replay cost" in trace["selected_action"]["why_selected"]
    assert summary["counterfactual_count"] == 3
    assert {item["candidate_id"] for item in trace["counterfactuals"]} == {
        "direct-side-push",
        "overreach-place",
        "stop-relocalize",
    }
    assert all(item["score_delta_vs_selected"] > 0 for item in trace["counterfactuals"])
    assert trace["outcome"]["success"] is True
    assert trace["outcome"]["success_label"] == "placed_at_target"
    assert trace["outcome"]["hardware_executed"] is False
    assert all(
        "total_cost_raw" in item["components"] and "total_cost_display" in item["components"]
        for item in trace["candidate_scores"]
    )
    assert summary["final_object_position"] == {"x": 0.52, "y": 0.08, "z": 0.03}
    json.dumps(summary)


def test_so101_replay_trace_default_json_summary_is_deterministic() -> None:
    first = so101_replay_trace.run_demo(emit=False)
    second = so101_replay_trace.run_demo(emit=False)

    assert first == second


def test_so101_replay_trace_demo_main_json_only(
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "worldforge-demo-so101-replay-trace",
            "--json-only",
        ],
    )

    assert so101_replay_trace.main() == 0

    summary = json.loads(capsys.readouterr().out)
    assert summary["selected_candidate_id"] == "lift-place-stable"
    assert summary["outcome"]["success"] is True


def test_so101_replay_trace_score_provider_rejects_empty_candidates() -> None:
    provider = so101_replay_trace.SO101ReplayScoreProvider()

    with pytest.raises(WorldForgeError, match="non-empty candidate list"):
        provider.score_actions(
            info={"target_pose": {"x": 0.52, "y": 0.08, "z": 0.03}},
            action_candidates=[],
        )


def test_examples_index_lists_so101_replay_trace(
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(sys, "argv", ["worldforge", "examples", "--format", "json"])

    assert cli_main() == 0

    examples = json.loads(capsys.readouterr().out)
    so101 = next(item for item in examples if item["name"] == "so101-replay-trace")
    assert so101["command"] == "uv run worldforge-demo-so101-replay-trace"
    assert "counterfactuals" in so101["surface"]

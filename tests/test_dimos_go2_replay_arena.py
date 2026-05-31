from __future__ import annotations

import json
from pathlib import Path

import pytest

from worldforge.demos.dimos_go2_replay_arena import (
    DEFAULT_FIXTURE_PATH,
    Go2ReplayScoreProvider,
    load_go2_replay_fixture,
    render_go2_replay_report,
    run_dimos_go2_replay_arena,
    run_dimos_go2_replay_arena_workflow,
)
from worldforge.models import WorldForgeError


def test_go2_replay_fixture_loads_checkout_safe_schema() -> None:
    fixture = load_go2_replay_fixture(DEFAULT_FIXTURE_PATH)

    assert fixture["schema_version"] == 1
    assert fixture["source"]["hardware_required"] is False
    assert fixture["source"]["mode"] == "replay-fixture"
    assert [candidate["id"] for candidate in fixture["candidate_actions"]] == [
        "baseline_forward",
        "arc_left_clear",
        "arc_right_glass",
        "slow_probe_left",
        "stop_relocalize",
    ]


def test_go2_replay_arena_selects_safer_counterfactual(tmp_path: Path) -> None:
    result = run_dimos_go2_replay_arena(DEFAULT_FIXTURE_PATH, tmp_path)
    trace = result.trace

    assert result.decision_trace_path.is_file()
    assert result.report_path.is_file()
    assert trace["artifact_kind"] == "worldforge.dimos_go2_replay_decision_trace"
    assert trace["candidate_count"] == 5
    assert trace["selected_action"]["id"] == "stop_relocalize"
    assert trace["baseline_action_id"] == "baseline_forward"
    assert trace["baseline_regret"] > 0.0
    assert trace["score_margin"] > 0.0
    assert "counterfactual" in trace["worldforge_value"]
    assert trace["plan_metadata"]["planning_mode"] == "score"
    assert trace["plan_metadata"]["score_provider"] == Go2ReplayScoreProvider.name
    assert trace["scored_candidates"][0]["action_id"] == "stop_relocalize"


def test_go2_replay_arena_report_explains_selected_action(tmp_path: Path) -> None:
    result = run_dimos_go2_replay_arena(DEFAULT_FIXTURE_PATH, tmp_path)
    report = render_go2_replay_report(result.trace)

    assert "DimOS Go2 Replay Arena" in report
    assert "`stop_relocalize` had the lowest transparent cost" in report
    assert "Top Counterfactuals" in report
    assert "no DimOS import" in report
    assert result.report_path.read_text(encoding="utf-8") == report


def test_go2_replay_arena_workflow_summary_points_to_artifacts(tmp_path: Path) -> None:
    summary = run_dimos_go2_replay_arena_workflow(DEFAULT_FIXTURE_PATH, tmp_path)

    assert summary["selected_action_id"] == "stop_relocalize"
    assert summary["score_margin"] > 0.0
    assert summary["baseline_regret"] > 0.0
    assert Path(summary["decision_trace_path"]).is_file()
    assert Path(summary["report_path"]).is_file()


def test_go2_replay_arena_rejects_malformed_fixture(tmp_path: Path) -> None:
    malformed = tmp_path / "bad.json"
    malformed.write_text(json.dumps({"schema_version": 1}), encoding="utf-8")

    with pytest.raises(WorldForgeError, match="missing 'scenario_id'"):
        load_go2_replay_fixture(malformed)

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


def test_go2_replay_arena_report_handles_single_candidate(tmp_path: Path) -> None:
    result = run_dimos_go2_replay_arena(DEFAULT_FIXTURE_PATH, tmp_path)
    trace = {**result.trace, "scored_candidates": result.trace["scored_candidates"][:1]}

    report = render_go2_replay_report(trace)

    assert "No rejected counterfactuals available" in report


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


def test_go2_replay_score_provider_rejects_missing_score_info() -> None:
    with pytest.raises(WorldForgeError, match="score info is missing 'observation'"):
        Go2ReplayScoreProvider().score_actions(
            info={"goal": {}},
            action_candidates=[[{"type": "go2_base_command", "parameters": {}}]],
        )


def test_go2_replay_score_provider_rejects_non_mapping_candidate() -> None:
    fixture = load_go2_replay_fixture(DEFAULT_FIXTURE_PATH)

    with pytest.raises(WorldForgeError, match="candidate 0 action must be a JSON object"):
        Go2ReplayScoreProvider().score_actions(
            info={"observation": fixture["observation"], "goal": fixture["goal"]},
            action_candidates=[["not-an-action"]],
        )


def test_go2_replay_arena_rejects_missing_nested_observation(tmp_path: Path) -> None:
    malformed = tmp_path / "bad.json"
    malformed.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "scenario_id": "bad",
                "observation": {
                    "frame_id": "bad-frame",
                    "timestamp_s": 0.0,
                    "localization_confidence": 1.0,
                    "map": {},
                },
                "goal": {"description": "bad", "x": 0.0, "y": 0.0},
                "candidate_actions": [
                    {"id": "candidate", "type": "go2_base_command", "parameters": {}}
                ],
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(WorldForgeError, match="observation is missing 'pose'"):
        load_go2_replay_fixture(malformed)


def test_go2_replay_fixture_raises_for_missing_file(tmp_path: Path) -> None:
    with pytest.raises(WorldForgeError, match="fixture not found"):
        load_go2_replay_fixture(tmp_path / "missing.json")


def test_go2_replay_fixture_raises_for_invalid_json(tmp_path: Path) -> None:
    malformed = tmp_path / "bad.json"
    malformed.write_text("{not valid json", encoding="utf-8")

    with pytest.raises(WorldForgeError, match="invalid JSON"):
        load_go2_replay_fixture(malformed)

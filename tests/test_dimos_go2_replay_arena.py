from __future__ import annotations

import json
from pathlib import Path

import pytest

from worldforge.demos.dimos_go2_replay_arena import (
    DEFAULT_FIXTURE_PATH,
    Go2ReplayScoreProvider,
    _decision_trace,
    load_go2_replay_fixture,
    render_go2_replay_report,
    run_dimos_go2_replay_arena,
    run_dimos_go2_replay_arena_workflow,
)
from worldforge.models import WorldForgeError

CLEAR_PATH_FIXTURE_PATH = DEFAULT_FIXTURE_PATH.with_name("go2_clear_hallway_replay_frame.json")


class _FakePlan:
    provider = Go2ReplayScoreProvider.name
    success_probability = 0.5

    def __init__(self, score_result: dict[str, object]) -> None:
        self.metadata = {
            "planning_mode": "score",
            "score_result": score_result,
            "workflow_trace": {},
        }


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


def test_go2_replay_arena_preserves_baseline_when_it_is_best(tmp_path: Path) -> None:
    result = run_dimos_go2_replay_arena(CLEAR_PATH_FIXTURE_PATH, tmp_path)
    trace = result.trace

    assert trace["scenario_id"] == "go2-clear-hallway-replay-frame-001"
    assert trace["candidate_count"] == 5
    assert trace["selected_action"]["id"] == "baseline_forward"
    assert trace["baseline_action_id"] == "baseline_forward"
    assert trace["baseline_regret"] == 0.0
    assert trace["score_margin"] > 0.0
    assert trace["worldforge_value"] == "ranked alternatives with a positive counterfactual margin"
    assert trace["scored_candidates"][0]["action_id"] == "baseline_forward"
    assert trace["scored_candidates"][1]["action_id"] != "baseline_forward"


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


def test_go2_replay_score_provider_rejects_malformed_action_payload() -> None:
    fixture = load_go2_replay_fixture(DEFAULT_FIXTURE_PATH)

    with pytest.raises(WorldForgeError, match="candidate 0 action is missing 'type'"):
        Go2ReplayScoreProvider().score_actions(
            info={"observation": fixture["observation"], "goal": fixture["goal"]},
            action_candidates=[[{"parameters": {}}]],
        )

    with pytest.raises(WorldForgeError, match="candidate 0 action parameters must be"):
        Go2ReplayScoreProvider().score_actions(
            info={"observation": fixture["observation"], "goal": fixture["goal"]},
            action_candidates=[[{"type": "go2_base_command", "parameters": []}]],
        )


def test_go2_replay_trace_preserves_score_result_best_index_on_ties() -> None:
    fixture = load_go2_replay_fixture(DEFAULT_FIXTURE_PATH)
    score_result = {
        "best_index": 0,
        "metadata": {
            "scored_candidates": [
                {
                    "action_id": "z_selected",
                    "action": {"type": "go2_safety_action", "parameters": {}},
                    "endpoint": {"x": 0.0, "y": 0.0, "yaw_rad": 0.0},
                    "total_cost": 1.0,
                    "components": {
                        "distance_cost": 1.0,
                        "obstacle_risk": 0.0,
                        "map_cost": 0.0,
                        "uncertainty_cost": 0.0,
                        "relocalization_cost": 0.0,
                    },
                },
                {
                    "action_id": "a_tied_rejected",
                    "action": {"type": "go2_safety_action", "parameters": {}},
                    "endpoint": {"x": 0.0, "y": 0.0, "yaw_rad": 0.0},
                    "total_cost": 1.0,
                    "components": {
                        "distance_cost": 1.0,
                        "obstacle_risk": 0.0,
                        "map_cost": 0.0,
                        "uncertainty_cost": 0.0,
                        "relocalization_cost": 0.0,
                    },
                },
            ]
        },
    }

    trace = _decision_trace(fixture, _FakePlan(score_result))

    assert trace["selected_action"]["id"] == "z_selected"
    assert trace["scored_candidates"][0]["action_id"] == "z_selected"


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


def test_go2_replay_fixture_rejects_out_of_range_localization_confidence(
    tmp_path: Path,
) -> None:
    payload = load_go2_replay_fixture(DEFAULT_FIXTURE_PATH)
    payload["observation"]["localization_confidence"] = 2.0
    malformed = tmp_path / "bad-confidence.json"
    malformed.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(WorldForgeError, match="localization_confidence must be between 0 and 1"):
        load_go2_replay_fixture(malformed)


def test_go2_replay_fixture_rejects_ambiguous_candidate_id(tmp_path: Path) -> None:
    payload = load_go2_replay_fixture(DEFAULT_FIXTURE_PATH)
    payload["candidate_actions"][1]["id"] = payload["candidate_actions"][0]["id"]
    malformed = tmp_path / "duplicate-candidate.json"
    malformed.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(WorldForgeError, match="candidate id 'baseline_forward' is duplicated"):
        load_go2_replay_fixture(malformed)


def test_go2_replay_fixture_rejects_unknown_baseline(tmp_path: Path) -> None:
    payload = load_go2_replay_fixture(DEFAULT_FIXTURE_PATH)
    payload["baseline_action_id"] = "missing-baseline"
    malformed = tmp_path / "missing-baseline.json"
    malformed.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(WorldForgeError, match="baseline_action_id 'missing-baseline'"):
        load_go2_replay_fixture(malformed)


def test_go2_replay_score_provider_rejects_zero_radius_zone() -> None:
    fixture = load_go2_replay_fixture(DEFAULT_FIXTURE_PATH)
    fixture["observation"]["map"]["cost_zones"] = [{"x": 0.0, "y": 0.0, "radius_m": 0.0}]

    with pytest.raises(WorldForgeError, match=r"zone\.radius_m must be greater than 0"):
        Go2ReplayScoreProvider().score_actions(
            info={"observation": fixture["observation"], "goal": fixture["goal"]},
            action_candidates=[[{"type": "go2_safety_action", "parameters": {}}]],
        )


def test_go2_replay_fixture_raises_for_missing_file(tmp_path: Path) -> None:
    with pytest.raises(WorldForgeError, match="fixture not found"):
        load_go2_replay_fixture(tmp_path / "missing.json")


def test_go2_replay_fixture_raises_for_invalid_json(tmp_path: Path) -> None:
    malformed = tmp_path / "bad.json"
    malformed.write_text("{not valid json", encoding="utf-8")

    with pytest.raises(WorldForgeError, match="invalid JSON"):
        load_go2_replay_fixture(malformed)

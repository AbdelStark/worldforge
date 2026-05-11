from __future__ import annotations

import base64
import importlib
import json
import math
import struct
import sys
from pathlib import Path

import pytest

from worldforge import WorldForge, WorldForgeError, WorldStateError
from worldforge.evaluation import EvaluationSuite
from worldforge.harness import available_flows, flow_index, run_flow
from worldforge.harness.flows import (
    benchmark_run_artifacts,
    eval_run_artifacts,
    flow_to_dicts,
    recent_report_paths,
    report_run_from_path,
    write_report,
)
from worldforge.harness.run_history import (
    RunHistoryFilter,
    list_run_history,
    parse_history_date,
    preserved_run_from_path,
    run_history_markdown,
)
from worldforge.harness.workspace import create_run_workspace, write_run_manifest

ROOT = Path(__file__).resolve().parents[1]


def _copy_json_payload(value: object) -> object:
    return json.loads(json.dumps(value))


def _write_cosmos_replay_payload(tmp_path: Path, name: str, payload: object) -> Path:
    path = tmp_path / name
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _write_gr00t_replay_payload(tmp_path: Path, name: str, payload: object) -> Path:
    path = tmp_path / name
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _cosmos_replay_request_payload(tmp_path: Path) -> tuple[dict, dict]:
    from worldforge.harness import flows

    replay_path = tmp_path / "cosmos-policy-replay.json"
    replay_path.write_text(
        json.dumps(flows._cosmos_policy_saved_replay_payload()),
        encoding="utf-8",
    )
    replay = flows._load_cosmos_policy_replay_artifact(replay_path)
    saved_request = replay["request"]
    policy_info = flows._cosmos_policy_policy_info_from_replay(replay)
    outbound_payload = dict(policy_info["observation"])
    outbound_payload["task_description"] = saved_request["task_description"]
    outbound_payload["action_horizon"] = saved_request["action_horizon"]
    return outbound_payload, saved_request


def test_harness_flow_metadata_is_available_without_textual() -> None:
    flows = available_flows()
    assert [flow.id for flow in flows] == [
        "leworldmodel",
        "lerobot",
        "cosmos-policy",
        "gr00t",
        "diagnostics",
        "workbench",
    ]
    assert flow_index()["leworldmodel"].provider == "LeWorldModelProvider"

    payload = flow_to_dicts()
    assert payload[0]["command"] == "uv run worldforge-demo-leworldmodel"
    assert payload[1]["focus"] == "policy plus score planning"
    assert payload[2]["command"] == "uv run --extra harness worldforge-harness --flow cosmos-policy"
    assert payload[3]["command"] == "uv run --extra harness worldforge-harness --flow gr00t"
    assert payload[4]["command"] == "uv run worldforge harness --flow diagnostics"
    assert payload[5]["command"] == "uv run worldforge provider workbench mock"


def test_harness_runs_leworldmodel_flow(tmp_path) -> None:
    run = run_flow("leworldmodel", state_dir=tmp_path)

    assert run.flow.id == "leworldmodel"
    assert len(run.steps) == 6
    assert len(run.metrics) == 6
    assert run.summary["selected_candidate_index"] == 1
    assert run.summary["saved_worlds"] == [run.summary["saved_world_id"]]
    assert run.summary["event_phases"] == ["success", "success"]
    assert [event["phase"] for event in run.provider_events] == ["success", "success"]
    assert "final_position: (0.55, 0.50, 0.00)" in run.transcript
    assert run.workspace_path is not None
    event_log = run.workspace_path / "logs" / "provider-events.jsonl"
    events = [json.loads(line) for line in event_log.read_text(encoding="utf-8").splitlines()]
    assert [event["phase"] for event in events] == ["success", "success"]
    inspector = json.loads((run.workspace_path / "results" / "inspector.json").read_text())
    assert inspector["provider_events"] == events


def test_harness_runs_lerobot_flow(tmp_path) -> None:
    run = run_flow("lerobot", state_dir=tmp_path)

    assert run.flow.id == "lerobot"
    assert len(run.steps) == 6
    assert run.summary["policy_candidate_count"] == 3
    assert run.summary["selected_candidate_index"] == 1
    assert run.summary["policy_select_calls"] == 2
    assert "policy_select_calls: 2" in run.transcript


def test_harness_runs_cosmos_policy_flow(tmp_path) -> None:
    run = run_flow("cosmos-policy", state_dir=tmp_path)

    assert run.flow.id == "cosmos-policy"
    assert len(run.steps) == 6
    assert len(run.metrics) == 6
    assert run.summary["model"] == "nvidia/Cosmos-Policy-ALOHA-Predict2-2B"
    assert run.summary["server_path"] == "/act"
    assert run.summary["raw_action_shape"] == [50, 14]
    assert run.summary["translated_action_count"] == 50
    assert run.summary["action_horizon"] == 50
    assert run.summary["value_prediction"] == 0.190714
    assert run.summary["selected_candidate_index"] == 0
    assert run.summary["selected_action_preview"][0]["type"] == "move_to"
    assert [event["phase"] for event in run.provider_events] == ["success"]
    assert "raw_action_shape: [50, 14]" in run.transcript
    assert "saved_replay_artifact: artifacts/cosmos-policy-replay.json" in run.transcript
    assert run.workspace_path is not None
    manifest = json.loads((run.workspace_path / "run_manifest.json").read_text())
    assert manifest["artifact_paths"]["cosmos_policy_replay"] == (
        "artifacts/cosmos-policy-replay.json"
    )
    replay = json.loads((run.workspace_path / "artifacts/cosmos-policy-replay.json").read_text())
    assert replay["manifest"]["flow_id"] == "cosmos-policy"
    assert replay["manifest"]["server_path"] == "/act"
    assert len(replay["policy_output"]["actions"]) == 50
    assert len(replay["translated_actions"]) == 50
    assert replay["provider_events"][0]["phase"] == "success"
    assert "policy_info" not in replay["request"]
    assert replay["request"]["observation_summary"]["primary_image"]["redacted"] is True
    assert replay["request"]["observation_summary"]["left_wrist_image"]["redacted"] is True
    assert replay["request"]["observation_summary"]["right_wrist_image"]["redacted"] is True
    assert replay["request"]["observation_summary"]["proprio"]["redacted"] is True
    assert replay["response"]["json_numpy_rows"] is True
    assert replay["response"]["raw_action_shape"] == [50, 14]
    assert replay["request"]["observation_fields"] == [
        "left_wrist_image",
        "primary_image",
        "proprio",
        "right_wrist_image",
    ]


def test_harness_cosmos_policy_flow_can_emit_transcript(tmp_path, capsys) -> None:
    from worldforge.harness import flows

    summary = flows._run_cosmos_policy_demo(state_dir=tmp_path, emit=True)

    output = capsys.readouterr().out
    assert summary["raw_action_shape"] == [50, 14]
    assert "flow: cosmos-policy" in output
    assert "translated_actions: 50" in output


def test_harness_runs_gr00t_flow(tmp_path) -> None:
    run = run_flow("gr00t", state_dir=tmp_path)

    assert run.flow.id == "gr00t"
    assert len(run.steps) == 6
    assert len(run.metrics) == 6
    assert run.summary["model"] == "nvidia/GR00T-N1.7-3B"
    assert run.summary["embodiment_tag"] == "GR1"
    assert run.summary["raw_tensor_shapes"] == {
        "eef_9d": [1, 4, 9],
        "gripper_position": [1, 4, 1],
        "joint_position": [1, 4, 7],
    }
    assert run.summary["validated_tensors"] == [
        "eef_9d",
        "gripper_position",
        "joint_position",
    ]
    assert run.summary["translated_action_count"] == 4
    assert run.summary["action_horizon"] == 4
    assert [event["phase"] for event in run.provider_events] == ["success"]
    assert "validated_tensors: eef_9d, gripper_position, joint_position" in run.transcript
    assert "saved_replay_artifact: artifacts/gr00t-policy-replay.json" in run.transcript
    assert run.workspace_path is not None

    manifest = json.loads((run.workspace_path / "run_manifest.json").read_text())
    assert manifest["artifact_paths"]["gr00t_policy_replay"] == (
        "artifacts/gr00t-policy-replay.json"
    )
    replay = json.loads((run.workspace_path / "artifacts/gr00t-policy-replay.json").read_text())
    assert replay["manifest"]["flow_id"] == "gr00t"
    assert replay["manifest"]["model"] == "nvidia/GR00T-N1.7-3B"
    assert set(replay["policy_output"]["raw_actions"]) == {
        "eef_9d",
        "gripper_position",
        "joint_position",
    }
    assert len(replay["translated_actions"]) == 4
    assert replay["provider_events"][0]["phase"] == "success"
    assert "observation" not in replay["request"]
    assert all(
        field["redacted"] is True for field in replay["request"]["observation_summary"].values()
    )
    exported = json.dumps(replay).lower()
    assert "checkpoint" not in exported
    assert "private endpoint" not in exported


def test_harness_gr00t_flow_can_emit_transcript(tmp_path, capsys) -> None:
    from worldforge.harness import flows

    summary = flows._run_gr00t_demo(state_dir=tmp_path, emit=True)

    output = capsys.readouterr().out
    assert summary["raw_tensor_shapes"]["eef_9d"] == [1, 4, 9]
    assert "flow: gr00t" in output
    assert "translated_actions: 4" in output


def test_harness_cosmos_policy_flow_ignores_live_cosmos_env(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("COSMOS_POLICY_ALLOWED_HOSTS", "live-cosmos.example")
    monkeypatch.setenv("COSMOS_POLICY_RETURN_ALL_QUERY_RESULTS", "true")

    run = run_flow("cosmos-policy", state_dir=tmp_path)

    assert run.summary["raw_action_shape"] == [50, 14]
    assert run.summary["translated_action_count"] == 50


def test_harness_loads_cosmos_policy_replay_artifact(tmp_path) -> None:
    from worldforge.harness import flows

    path = tmp_path / "cosmos-policy-replay.json"
    payload = flows._cosmos_policy_saved_replay_payload()
    path.write_text(json.dumps(payload), encoding="utf-8")

    loaded = flows._load_cosmos_policy_replay_artifact(path)

    assert loaded["manifest"]["model"] == "nvidia/Cosmos-Policy-ALOHA-Predict2-2B"
    assert loaded["request"]["task_description"] == "fold shirt"
    assert loaded["request"]["observation_summary"]["primary_image"]["redacted"] is True
    assert loaded["request"]["observation_summary"]["proprio"]["redacted"] is True
    assert "policy_info" not in loaded["request"]
    assert len(loaded["policy_output"]["actions"]) == 50


def test_harness_loads_gr00t_replay_artifact(tmp_path) -> None:
    from worldforge.harness import flows

    fixture_loaded = flows._load_gr00t_replay_artifact(
        ROOT / "tests" / "fixtures" / "providers" / "gr00t_policy_replay.json"
    )
    path = tmp_path / "gr00t-policy-replay.json"
    payload = flows._gr00t_saved_replay_payload()
    path.write_text(json.dumps(payload), encoding="utf-8")

    loaded = flows._load_gr00t_replay_artifact(path)

    assert fixture_loaded["policy_output"] == loaded["policy_output"]
    assert loaded["manifest"]["model"] == "nvidia/GR00T-N1.7-3B"
    assert loaded["request"]["task_instruction"]
    assert loaded["request"]["observation_summary"]["video.front"]["redacted"] is True
    assert "observation" not in loaded["request"]
    assert set(loaded["policy_output"]["raw_actions"]) == {
        "eef_9d",
        "gripper_position",
        "joint_position",
    }


def test_harness_rejects_cosmos_policy_replay_schema_drift(tmp_path) -> None:
    from worldforge.harness import flows

    payload = flows._cosmos_policy_saved_replay_payload()
    invalid_schema = _copy_json_payload(payload)
    invalid_schema["schema_version"] = 99

    with pytest.raises(WorldStateError, match="schema_version"):
        flows._load_cosmos_policy_replay_artifact(
            _write_cosmos_replay_payload(tmp_path, "bad-schema.json", invalid_schema)
        )


def test_harness_rejects_gr00t_replay_schema_drift(tmp_path) -> None:
    from worldforge.harness import flows

    payload = flows._gr00t_saved_replay_payload()
    invalid_schema = _copy_json_payload(payload)
    invalid_schema["schema_version"] = 99

    with pytest.raises(WorldStateError, match="schema_version"):
        flows._load_gr00t_replay_artifact(
            _write_gr00t_replay_payload(tmp_path, "bad-gr00t-schema.json", invalid_schema)
        )


def test_harness_rejects_gr00t_replay_missing_named_tensor(tmp_path) -> None:
    from worldforge.harness import flows

    payload = flows._gr00t_saved_replay_payload()
    missing_tensor = _copy_json_payload(payload)
    del missing_tensor["policy_output"]["raw_actions"]["eef_9d"]

    with pytest.raises(WorldStateError, match="eef_9d"):
        flows._load_gr00t_replay_artifact(
            _write_gr00t_replay_payload(tmp_path, "missing-gr00t-tensor.json", missing_tensor)
        )


def test_harness_rejects_gr00t_replay_bad_tensor_shape(tmp_path) -> None:
    from worldforge.harness import flows

    payload = flows._gr00t_saved_replay_payload()
    bad_shape = _copy_json_payload(payload)
    bad_shape["policy_output"]["raw_actions"]["joint_position"][0][0] = [0.0]

    with pytest.raises(WorldStateError, match="joint_position"):
        flows._load_gr00t_replay_artifact(
            _write_gr00t_replay_payload(tmp_path, "bad-gr00t-shape.json", bad_shape)
        )


def test_harness_rejects_unredacted_gr00t_replay_observation(tmp_path) -> None:
    from worldforge.harness import flows

    payload = flows._gr00t_saved_replay_payload()
    unredacted = _copy_json_payload(payload)
    unredacted["request"]["observation_summary"]["video.front"]["redacted"] = False

    with pytest.raises(WorldStateError, match="must be redacted"):
        flows._load_gr00t_replay_artifact(
            _write_gr00t_replay_payload(tmp_path, "unredacted-gr00t.json", unredacted)
        )


def test_harness_rejects_cosmos_policy_replay_missing_observation(tmp_path) -> None:
    from worldforge.harness import flows

    payload = flows._cosmos_policy_saved_replay_payload()
    missing_observation = _copy_json_payload(payload)
    missing_observation["request"]["observation_fields"] = ["primary_image"]

    with pytest.raises(WorldStateError, match="missing fields"):
        flows._load_cosmos_policy_replay_artifact(
            _write_cosmos_replay_payload(
                tmp_path,
                "missing-observation.json",
                missing_observation,
            )
        )


def test_harness_rejects_unredacted_cosmos_policy_replay_image(tmp_path) -> None:
    from worldforge.harness import flows

    payload = flows._cosmos_policy_saved_replay_payload()
    unredacted_image = _copy_json_payload(payload)
    unredacted_image["request"]["observation_summary"]["primary_image"]["redacted"] = False

    with pytest.raises(WorldStateError, match="must be redacted"):
        flows._load_cosmos_policy_replay_artifact(
            _write_cosmos_replay_payload(tmp_path, "unredacted-image.json", unredacted_image)
        )


def test_harness_rejects_unredacted_cosmos_policy_replay_proprio(tmp_path) -> None:
    from worldforge.harness import flows

    payload = flows._cosmos_policy_saved_replay_payload()
    unredacted_proprio = _copy_json_payload(payload)
    unredacted_proprio["request"]["observation_summary"]["proprio"]["redacted"] = False

    with pytest.raises(WorldStateError, match="must be redacted"):
        flows._load_cosmos_policy_replay_artifact(
            _write_cosmos_replay_payload(tmp_path, "unredacted-proprio.json", unredacted_proprio)
        )


def test_harness_rejects_raw_cosmos_policy_replay_observation(tmp_path) -> None:
    from worldforge.harness import flows

    payload = flows._cosmos_policy_saved_replay_payload()
    raw_observation = _copy_json_payload(payload)
    raw_observation["request"]["observation"] = {"primary_image": [[[[0, 0, 0]]]]}

    with pytest.raises(WorldStateError, match="unsupported fields"):
        flows._load_cosmos_policy_replay_artifact(
            _write_cosmos_replay_payload(tmp_path, "raw-observation.json", raw_observation)
        )


def test_harness_rejects_cosmos_policy_replay_observation_summary_extra_keys(
    tmp_path,
) -> None:
    from worldforge.harness import flows

    payload = flows._cosmos_policy_saved_replay_payload()
    extra_summary_key = _copy_json_payload(payload)
    extra_summary_key["request"]["observation_summary"]["primary_image"]["raw_tensor"] = [
        0,
        1,
        2,
    ]

    with pytest.raises(WorldStateError, match="unsupported fields"):
        flows._load_cosmos_policy_replay_artifact(
            _write_cosmos_replay_payload(
                tmp_path,
                "extra-summary-key.json",
                extra_summary_key,
            )
        )


def test_harness_rejects_cosmos_policy_replay_bad_action_shape(tmp_path) -> None:
    from worldforge.harness import flows

    payload = flows._cosmos_policy_saved_replay_payload()
    bad_action_shape = _copy_json_payload(payload)
    bad_action_shape["policy_output"]["actions"][0]["shape"] = [15]

    with pytest.raises(WorldStateError, match="shape"):
        flows._load_cosmos_policy_replay_artifact(
            _write_cosmos_replay_payload(tmp_path, "bad-action-shape.json", bad_action_shape)
        )


def test_harness_rejects_cosmos_policy_replay_large_base64_before_decode(tmp_path) -> None:
    from worldforge.harness import flows

    payload = flows._cosmos_policy_saved_replay_payload()
    large_row = _copy_json_payload(payload)
    large_row["policy_output"]["actions"][0]["__numpy__"] = "A" * 512

    with pytest.raises(WorldStateError, match="base64 payload is too large"):
        flows._load_cosmos_policy_replay_artifact(
            _write_cosmos_replay_payload(tmp_path, "large-row.json", large_row)
        )


def test_harness_accepts_cosmos_policy_replay_float64_dtype(tmp_path) -> None:
    from worldforge.harness import flows

    payload = flows._cosmos_policy_saved_replay_payload()
    float64_row = _copy_json_payload(payload)
    raw = struct.pack("<14d", *[float(index) / 100.0 for index in range(14)])
    float64_row["policy_output"]["actions"][0] = {
        "__numpy__": base64.b64encode(raw).decode("ascii"),
        "dtype": "float64",
        "shape": [14],
    }

    loaded = flows._load_cosmos_policy_replay_artifact(
        _write_cosmos_replay_payload(tmp_path, "float64-row.json", float64_row)
    )

    assert loaded["policy_output"]["actions"][0]["dtype"] == "float64"


def test_harness_validates_cosmos_policy_replay_request_contract(tmp_path) -> None:
    from worldforge.harness import flows

    outbound_payload, saved_request = _cosmos_replay_request_payload(tmp_path)

    flows._validate_cosmos_policy_replay_request(outbound_payload, saved_request)

    return_all_payload = {**outbound_payload, "return_all_query_results": False}
    flows._validate_cosmos_policy_replay_request(return_all_payload, saved_request)

    drifted_payload = {**outbound_payload, "task_description": "pick cube"}
    with pytest.raises(WorldStateError, match="task_description drifted"):
        flows._validate_cosmos_policy_replay_request(drifted_payload, saved_request)

    missing_field_payload = dict(outbound_payload)
    del missing_field_payload["left_wrist_image"]
    with pytest.raises(WorldStateError, match="request keys drifted"):
        flows._validate_cosmos_policy_replay_request(missing_field_payload, saved_request)

    bad_return_all_payload = {**outbound_payload, "return_all_query_results": "false"}
    with pytest.raises(WorldStateError, match="return_all_query_results"):
        flows._validate_cosmos_policy_replay_request(bad_return_all_payload, saved_request)


def test_harness_rejects_cosmos_policy_replay_request_non_json_values(tmp_path) -> None:
    from worldforge.harness import flows

    outbound_payload, saved_request = _cosmos_replay_request_payload(tmp_path)

    tuple_payload = {**outbound_payload, "primary_image": tuple(outbound_payload["primary_image"])}
    with pytest.raises(WorldStateError, match="JSON-native"):
        flows._validate_cosmos_policy_replay_request(tuple_payload, saved_request)

    bytes_payload = {**outbound_payload, "left_wrist_image": b"not-json"}
    with pytest.raises(WorldStateError, match="JSON-native"):
        flows._validate_cosmos_policy_replay_request(bytes_payload, saved_request)

    nan_payload = {**outbound_payload, "proprio": [0.0] * 13 + [math.nan]}
    with pytest.raises(WorldStateError, match="JSON-native"):
        flows._validate_cosmos_policy_replay_request(nan_payload, saved_request)


def test_harness_cosmos_policy_optional_value_prediction_renders(tmp_path) -> None:
    from worldforge.harness import flows

    summary = run_flow("cosmos-policy", state_dir=tmp_path).summary
    summary = {**summary, "value_prediction": None}

    assert flows._steps_for("cosmos-policy", summary)[4].artifact == "value_prediction=n/a"
    assert flows._metrics_for("cosmos-policy", summary)[3].value == "n/a"
    assert "value_prediction: n/a" in flows._transcript_for("cosmos-policy", summary)


def test_harness_cosmos_policy_failure_preserves_replay_artifact(tmp_path, monkeypatch) -> None:
    from worldforge.harness import flows

    original_response_payload = flows._cosmos_policy_response_payload

    def malformed_response(replay_artifact):
        response = json.loads(json.dumps(original_response_payload(replay_artifact)))
        response["actions"][0]["shape"] = [15]
        return response

    monkeypatch.setattr(flows, "_cosmos_policy_response_payload", malformed_response)

    run = run_flow("cosmos-policy", state_dir=tmp_path)

    assert run.validation_errors
    assert run.workspace_path is not None
    manifest = json.loads((run.workspace_path / "run_manifest.json").read_text())
    assert manifest["status"] == "failed"
    replay_path = run.workspace_path / "artifacts" / "cosmos-policy-replay.json"
    replay = json.loads(replay_path.read_text())
    assert replay["manifest"]["status"] == "failed"
    assert "failure" in [event["phase"] for event in replay["provider_events"]]
    assert replay["translated_actions"] == []


def test_harness_rejects_unknown_flow(tmp_path) -> None:
    with pytest.raises(WorldForgeError, match="unknown harness flow 'unknown'"):
        run_flow("unknown", state_dir=tmp_path)


def test_harness_flow_artifact_descriptors_are_validated(tmp_path) -> None:
    from worldforge.harness import flows

    workspace = create_run_workspace(
        tmp_path,
        kind="flow",
        command="worldforge harness --flow demo",
        provider="demo",
        operation="demo",
    )

    assert flows._write_flow_artifacts(workspace, {"harness_artifacts": {}}) == {}

    with pytest.raises(ValueError, match="artifact names"):
        flows._write_flow_artifacts(
            workspace,
            {"harness_artifacts": {"": {"path": "artifacts/demo.json"}}},
        )
    with pytest.raises(ValueError, match="descriptor"):
        flows._write_flow_artifacts(workspace, {"harness_artifacts": {"demo": "bad"}})
    with pytest.raises(ValueError, match="under artifacts"):
        flows._write_flow_artifacts(
            workspace,
            {"harness_artifacts": {"demo": {"path": "results/demo.json"}}},
        )
    with pytest.raises(ValueError, match="reserved"):
        flows._write_flow_artifacts(
            workspace,
            {"harness_artifacts": {"summary": {"path": "artifacts/summary.json"}}},
        )


def test_harness_private_helpers_cover_invalid_and_emit_paths(tmp_path, capsys) -> None:
    from worldforge.harness import flows

    assert flows._preview_action_rows("not rows") == []
    assert flows._preview_action_rows([[1, 2], "bad", [3]]) == [[1.0, 2.0], [3.0]]

    with pytest.raises(ValueError, match="unknown harness flow"):
        flows._steps_for("unknown", {})

    forge = WorldForge(state_dir=tmp_path)
    with pytest.raises(ValueError, match="must include a json entry"):
        write_report(forge, "missing-json", {})

    unsupported_path = tmp_path / "unsupported-report.json"
    unsupported_path.write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError, match="unsupported harness report payload"):
        report_run_from_path(unsupported_path, state_dir=tmp_path)

    def broken_glob(_self: Path, _pattern: str):
        raise OSError("cannot scan")

    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(Path, "glob", broken_glob)
    try:
        assert recent_report_paths(tmp_path) == ()
    finally:
        monkeypatch.undo()

    assert flows._provider_events_for("diagnostics", {}) == ()
    assert [
        event["phase"]
        for event in flows._provider_events_for(
            "diagnostics",
            {"event_phases": ["success"]},
        )
    ] == ["success"]
    events = flows._provider_events_for(
        "diagnostics",
        {
            "benchmark_results": [
                "bad",
                {"operation_metrics": "bad"},
                {
                    "provider": "mock",
                    "operation": "predict",
                    "operation_metrics": {
                        "events": [
                            "bad",
                            {"request_count": 1, "retry_count": 1, "error_count": 0},
                        ],
                    },
                },
            ],
        },
    )
    assert [event["phase"] for event in events] == ["retry"]

    flows._run_diagnostics_demo(state_dir=tmp_path / "diagnostics", emit=True)
    flows._run_workbench_demo(state_dir=tmp_path / "workbench", emit=True)
    output = capsys.readouterr().out
    assert "Benchmark Report" in output
    assert "Provider Workbench" in output


def test_harness_failed_flow_preserves_manifest_and_inspector(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from worldforge.harness import flows

    def broken_runner(**_kwargs) -> dict[str, object]:
        raise RuntimeError("api_key=secret-value failed")

    monkeypatch.setitem(flows._RUNNERS, "leworldmodel", broken_runner)

    run = flows.run_flow("leworldmodel", state_dir=tmp_path)

    assert run.validation_errors == ("api_key=[redacted] failed",)
    assert run.provider_events[0]["phase"] == "failure"
    assert run.provider_events[0]["message"] == "api_key=[redacted] failed"
    assert run.workspace_path is not None
    manifest = json.loads((run.workspace_path / "run_manifest.json").read_text())
    assert manifest["status"] == "failed"
    assert manifest["event_count"] == 1
    assert manifest["artifact_paths"]["inspector"] == "results/inspector.json"
    inspector = json.loads((run.workspace_path / "results" / "inspector.json").read_text())
    assert inspector["status"] == "failed"
    assert inspector["validation_errors"] == ["api_key=[redacted] failed"]


def test_harness_runs_diagnostics_flow(tmp_path) -> None:
    run = run_flow("diagnostics", state_dir=tmp_path)

    assert run.flow.id == "diagnostics"
    assert len(run.steps) == 6
    assert len(run.metrics) == 6
    assert run.summary["registered_providers"] == ["mock"]
    assert run.summary["benchmark_operation_count"] == 5
    assert run.summary["mock_supported_operations"] == [
        "predict",
        "reason",
        "generate",
        "transfer",
        "embed",
    ]
    assert run.summary["benchmark_event_count"] >= 10
    assert "benchmark_operations: predict, reason, generate, transfer, embed" in run.transcript


def test_harness_runs_workbench_flow(tmp_path) -> None:
    run = run_flow("workbench", state_dir=tmp_path)

    assert run.flow.id == "workbench"
    assert len(run.steps) == 5
    assert len(run.metrics) == 5
    assert run.summary["providers"] == ["mock", "jepa-wms"]
    assert run.summary["passed_count"] == 2
    assert run.summary["missing_evidence_by_provider"]["jepa-wms"]["experimental"] == []
    assert run.summary["missing_evidence_by_provider"]["jepa-wms"]["stable"] == [
        "prepared_host_smoke_artifact",
        "release_evidence",
    ]
    assert "jepa-wms_missing_stable: prepared_host_smoke_artifact, release_evidence" in (
        run.transcript
    )
    assert run.workspace_path is not None
    inspector = json.loads((run.workspace_path / "results" / "inspector.json").read_text())
    assert inspector["steps"][0]["title"] == "Select authoring targets"


def test_eval_run_artifacts_match_canonical_renderer(tmp_path) -> None:
    forge = WorldForge(state_dir=tmp_path)
    artifacts, report = eval_run_artifacts(forge, "planning", "mock")

    direct = EvaluationSuite.from_builtin("planning").run_report("mock", forge=forge)
    artifact_payload = json.loads(artifacts["json"])
    direct_payload = json.loads(direct.to_json())
    assert artifact_payload["provenance"]["created_at"]
    assert direct_payload["provenance"]["created_at"]
    artifact_payload["provenance"]["created_at"] = "<created-at>"
    direct_payload["provenance"]["created_at"] = "<created-at>"
    assert artifact_payload == direct_payload
    assert artifacts["markdown"] == report.to_markdown()
    assert artifact_payload["suite_id"] == "planning"


def test_benchmark_run_artifacts_invokes_sample_callback(tmp_path) -> None:
    forge = WorldForge(state_dir=tmp_path)
    samples = []
    artifacts, report = benchmark_run_artifacts(
        forge,
        "mock",
        operations=("predict",),
        iterations=3,
        on_sample=samples.append,
    )

    assert len(samples) == 3
    assert report.results[0].operation == "predict"
    assert json.loads(artifacts["json"])["results"][0]["iterations"] == 3


def test_write_report_and_recent_report_round_trip(tmp_path) -> None:
    forge = WorldForge(state_dir=tmp_path)
    artifacts, _report = eval_run_artifacts(forge, "planning", "mock")

    path = write_report(forge, "eval-planning", artifacts)

    assert path.exists()
    assert path.parent == (forge.state_dir / "reports").resolve()
    assert recent_report_paths(forge.state_dir) == (path,)
    run = report_run_from_path(path, state_dir=forge.state_dir)
    assert run.kind == "eval"
    assert run.report_path == path
    assert run.artifacts == artifacts


def test_write_benchmark_report_round_trips_canonical_artifacts(tmp_path) -> None:
    forge = WorldForge(state_dir=tmp_path)
    artifacts, _report = benchmark_run_artifacts(
        forge,
        "mock",
        operations=("predict",),
        iterations=1,
    )

    path = write_report(forge, "benchmark", artifacts)
    run = report_run_from_path(path, state_dir=forge.state_dir)

    assert run.kind == "benchmark"
    assert run.report_path == path
    assert run.artifacts == artifacts
    assert "Claim boundary:" in run.artifacts["markdown"]
    assert "operation_metrics_json" in run.artifacts["csv"]


def test_run_history_filters_and_generates_safe_recovery_actions(tmp_path: Path) -> None:
    _preserved_run_history_eval(tmp_path)
    failed = _preserved_run_history_benchmark(tmp_path)

    records = list_run_history(
        tmp_path,
        filters=RunHistoryFilter.from_strings(
            provider="mock",
            capability="predict",
            status="failed",
            created_from="2026-01-02",
            artifact_type="json",
        ),
    )

    assert [record.run_id for record in records] == ["20260102T000000Z-00000002"]
    record = records[0]
    assert record.recovery_command == record.issue_bundle_command
    assert record.issue_bundle_path.endswith("/issue-bundles/20260102T000000Z-00000002")
    assert record.comparison_command is not None
    assert "worldforge runs compare" in record.comparison_command
    assert "super-secret-value" not in record.rerun_command
    assert "/tmp/private-worldforge" not in record.rerun_command
    assert "<redacted>" in record.rerun_command
    assert "<host-local:private-worldforge>" in record.rerun_command
    assert record.safe_artifact_types == ("json",)

    opened = preserved_run_from_path(failed.path, state_dir=tmp_path)
    assert opened.kind == "benchmark"
    assert opened.workspace_path == failed.path.resolve()
    assert opened.flow.capability == "benchmark"


def test_run_history_markdown_and_filter_boundaries(tmp_path: Path) -> None:
    _preserved_run_history_eval(tmp_path)
    _preserved_run_history_benchmark(tmp_path)

    assert parse_history_date(None) is None
    with pytest.raises(WorldForgeError, match="YYYY-MM-DD"):
        parse_history_date("2026/01/01")

    all_records = list_run_history(tmp_path, limit=1)
    assert len(all_records) == 1
    markdown = run_history_markdown(all_records)
    assert "# TheWorldHarness Run History" in markdown
    assert "Rerun Commands" in markdown
    assert run_history_markdown(()) == (
        "# TheWorldHarness Run History\n\n"
        "| Run | Kind | Status | Provider | Capability | Artifacts | Recovery |\n"
        "| --- | --- | --- | --- | --- | --- | --- |\n"
        "| - | - | - | - | - | - | - |\n\n"
        "## Rerun Commands\n\n"
        "- No preserved runs matched the filter.\n"
    )

    assert not list_run_history(tmp_path, filters=RunHistoryFilter(provider="runway"))
    assert not list_run_history(tmp_path, filters=RunHistoryFilter(capability="generate"))
    assert not list_run_history(tmp_path, filters=RunHistoryFilter(status="cancelled"))
    assert not list_run_history(
        tmp_path,
        filters=RunHistoryFilter.from_strings(created_to="2025-12-31"),
    )
    assert not list_run_history(tmp_path, filters=RunHistoryFilter(artifact_type="png"))


def test_preserved_flow_run_opens_from_inspector_without_optional_runtime(tmp_path: Path) -> None:
    run = run_flow("diagnostics", state_dir=tmp_path)
    assert run.workspace_path is not None

    opened = preserved_run_from_path(run.workspace_path / "run_manifest.json", state_dir=tmp_path)

    assert opened.flow.id == "diagnostics"
    assert opened.workspace_path == run.workspace_path.resolve()
    assert opened.steps[0].title == "Create isolated forge"
    assert opened.metrics[0].label == "Known profiles"
    assert opened.provider_events


def test_preserved_generic_failed_run_uses_recovery_fallbacks(tmp_path: Path) -> None:
    workspace = create_run_workspace(
        tmp_path,
        kind="flow",
        command="",
        provider=None,
        operation="custom-flow",
        run_id="20260103T000000Z-00000003",
        input_summary={},
    )
    write_run_manifest(
        workspace,
        kind="flow",
        command="",
        status="failed",
        operation="custom-flow",
        result_summary={"validation_errors": ["custom failure"]},
        artifact_paths={
            "summary": "results/summary.json",
            "absolute": "/tmp/private.json",
            "escape": "../secret.txt",
        },
    )

    records = list_run_history(tmp_path)
    record = records[0]
    assert record.provider == ""
    assert record.rerun_command == "worldforge harness --flow custom-flow"
    assert record.failure_summary == "custom failure"
    assert record.safe_artifact_types == ("summary", "json")
    assert record.recovery_command is not None

    opened = preserved_run_from_path(workspace.path, state_dir=tmp_path)
    assert opened.flow.id == "custom-flow"
    assert opened.steps[0].title == "Load preserved run"
    assert opened.metrics[0].value == "failed"
    assert opened.validation_errors == ("custom failure",)
    assert "issue_bundle:" in opened.transcript[6]


def test_run_history_rejects_missing_or_invalid_manifests(tmp_path: Path) -> None:
    with pytest.raises(WorldForgeError, match="manifest not found"):
        preserved_run_from_path(tmp_path / "missing", state_dir=tmp_path)

    bad = tmp_path / "bad" / "run_manifest.json"
    bad.parent.mkdir()
    bad.write_text("not-json", encoding="utf-8")
    with pytest.raises(WorldForgeError, match="invalid JSON"):
        preserved_run_from_path(bad.parent, state_dir=tmp_path)

    non_object = tmp_path / "non-object" / "run_manifest.json"
    non_object.parent.mkdir()
    non_object.write_text("[]", encoding="utf-8")
    with pytest.raises(WorldForgeError, match="must be a JSON object"):
        preserved_run_from_path(non_object.parent, state_dir=tmp_path)


def test_run_history_sanitizes_assignments_urls_and_synthesizes_commands(tmp_path: Path) -> None:
    workspace = create_run_workspace(
        tmp_path,
        kind="benchmark",
        command=(
            "TOKEN=super-secret worldforge benchmark --provider mock --operation predict "
            "https://example.test/result.json?token=secret"
        ),
        provider="",
        operation="predict",
        run_id="20260104T000000Z-00000004",
        input_summary={"providers": ["mock"], "operations": ["predict"]},
    )
    write_run_manifest(
        workspace,
        kind="benchmark",
        command=(
            "TOKEN=super-secret worldforge benchmark --provider mock --operation predict "
            "https://example.test/result.json?token=secret"
        ),
        status="cancelled",
        operation="predict",
        input_summary={"providers": ["mock"], "operations": ["predict"]},
        result_summary={},
        artifact_paths={},
    )

    record = list_run_history(tmp_path)[0]
    assert "super-secret" not in record.rerun_command
    assert "<redacted-url>" in record.rerun_command
    assert "TOKEN=<redacted>" in record.rerun_command
    assert record.failure_summary == "Run was cancelled before completion."
    assert record.safe_artifact_types == ()


def test_run_history_module_imports_without_textual(monkeypatch: pytest.MonkeyPatch) -> None:
    saved_textual = sys.modules.pop("textual", None)
    monkeypatch.setitem(sys.modules, "textual", None)
    try:
        module = importlib.reload(importlib.import_module("worldforge.harness.run_history"))
        assert hasattr(module, "list_run_history")
    finally:
        if saved_textual is not None:
            sys.modules["textual"] = saved_textual
        else:
            sys.modules.pop("textual", None)


def test_eval_capability_mismatch_propagates(tmp_path) -> None:
    forge = WorldForge(state_dir=tmp_path)
    with pytest.raises(WorldForgeError, match="missing required capabilities"):
        eval_run_artifacts(forge, "generation", "leworldmodel")


def _preserved_run_history_eval(workspace_dir: Path):
    workspace = create_run_workspace(
        workspace_dir,
        kind="eval",
        command="worldforge eval --suite planning --provider mock",
        provider="mock",
        operation="planning",
        run_id="20260101T000000Z-00000001",
        input_summary={"suite_id": "planning", "providers": ["mock"], "capabilities": ["plan"]},
    )
    workspace.write_json(
        "reports/report.json",
        {
            "suite_id": "planning",
            "suite": "Planning Evaluation",
            "provider_summaries": [],
            "results": [],
        },
    )
    write_run_manifest(
        workspace,
        kind="eval",
        command="worldforge eval --suite planning --provider mock",
        provider="mock",
        operation="planning",
        status="completed",
        input_summary={"suite_id": "planning", "providers": ["mock"], "capabilities": ["plan"]},
        result_summary={"result_count": 0, "passed_count": 0},
        artifact_paths={"json": "reports/report.json"},
    )
    return workspace


def _preserved_run_history_benchmark(workspace_dir: Path):
    workspace = create_run_workspace(
        workspace_dir,
        kind="benchmark",
        command=(
            "worldforge benchmark --provider mock --operation predict "
            "--api-key super-secret-value --state-dir /tmp/private-worldforge"
        ),
        provider="mock",
        operation="predict",
        run_id="20260102T000000Z-00000002",
        input_summary={
            "providers": ["mock"],
            "operations": ["predict"],
            "capabilities": ["predict"],
        },
    )
    workspace.write_json(
        "reports/report.json",
        {
            "claim_boundary": "test",
            "run_metadata": {},
            "results": [
                {
                    "provider": "mock",
                    "operation": "predict",
                    "iterations": 1,
                    "concurrency": 1,
                    "success_count": 0,
                    "error_count": 1,
                    "retry_count": 0,
                    "total_time_ms": 1.0,
                    "average_latency_ms": 1.0,
                    "min_latency_ms": 1.0,
                    "max_latency_ms": 1.0,
                    "p50_latency_ms": 1.0,
                    "p95_latency_ms": 1.0,
                    "throughput_per_second": 1.0,
                    "operation_metrics": {"events": [{"request_count": 1}]},
                    "errors": ["budget failed"],
                }
            ],
        },
    )
    write_run_manifest(
        workspace,
        kind="benchmark",
        command=(
            "worldforge benchmark --provider mock --operation predict "
            "--api-key super-secret-value --state-dir /tmp/private-worldforge"
        ),
        provider="mock",
        operation="predict",
        status="failed",
        input_summary={
            "providers": ["mock"],
            "operations": ["predict"],
            "capabilities": ["predict"],
        },
        result_summary={"result_count": 1, "error_count": 1, "failure_reason": "budget failed"},
        artifact_paths={"json": "reports/report.json"},
        event_count=1,
    )
    return workspace

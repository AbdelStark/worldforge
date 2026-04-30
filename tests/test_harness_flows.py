from __future__ import annotations

import json

import pytest

from worldforge import WorldForge, WorldForgeError
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


def test_harness_flow_metadata_is_available_without_textual() -> None:
    flows = available_flows()
    assert [flow.id for flow in flows] == ["leworldmodel", "lerobot", "diagnostics"]
    assert flow_index()["leworldmodel"].provider == "LeWorldModelProvider"

    payload = flow_to_dicts()
    assert payload[0]["command"] == "uv run worldforge-demo-leworldmodel"
    assert payload[1]["focus"] == "policy plus score planning"
    assert payload[2]["command"] == "uv run worldforge harness --flow diagnostics"


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


def test_eval_run_artifacts_match_canonical_renderer(tmp_path) -> None:
    forge = WorldForge(state_dir=tmp_path)
    artifacts, report = eval_run_artifacts(forge, "planning", "mock")

    direct = EvaluationSuite.from_builtin("planning").run_report("mock", forge=forge)
    assert artifacts["json"] == direct.to_json()
    assert artifacts["markdown"] == report.to_markdown()
    assert json.loads(artifacts["json"])["suite_id"] == "planning"


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


def test_eval_capability_mismatch_propagates(tmp_path) -> None:
    forge = WorldForge(state_dir=tmp_path)
    with pytest.raises(WorldForgeError, match="missing required capabilities"):
        eval_run_artifacts(forge, "generation", "leworldmodel")

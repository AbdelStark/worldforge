from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path

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
from worldforge.harness.run_history import (
    RunHistoryFilter,
    list_run_history,
    parse_history_date,
    preserved_run_from_path,
    run_history_markdown,
)
from worldforge.harness.workspace import create_run_workspace, write_run_manifest


def test_harness_flow_metadata_is_available_without_textual() -> None:
    flows = available_flows()
    assert [flow.id for flow in flows] == ["leworldmodel", "lerobot", "diagnostics", "workbench"]
    assert flow_index()["leworldmodel"].provider == "LeWorldModelProvider"

    payload = flow_to_dicts()
    assert payload[0]["command"] == "uv run worldforge-demo-leworldmodel"
    assert payload[1]["focus"] == "policy plus score planning"
    assert payload[2]["command"] == "uv run worldforge harness --flow diagnostics"
    assert payload[3]["command"] == "uv run worldforge provider workbench mock"


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

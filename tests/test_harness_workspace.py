from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from worldforge.cli import main
from worldforge.harness import run_flow
from worldforge.harness.workspace import (
    cleanup_run_workspaces,
    create_run_workspace,
    list_run_workspaces,
    validate_run_id,
    workspace_root_for_state_dir,
    write_run_manifest,
)


def test_run_flow_preserves_shared_workspace_layout(tmp_path) -> None:
    run = run_flow("diagnostics", state_dir=tmp_path)

    assert run.workspace_path is not None
    assert run.workspace_path.parent == tmp_path / "runs"
    manifest = json.loads((run.workspace_path / "run_manifest.json").read_text())

    assert manifest["kind"] == "flow"
    assert manifest["status"] == "completed"
    assert manifest["operation"] == "diagnostics"
    assert manifest["artifact_paths"]["summary"] == "results/summary.json"
    assert (run.workspace_path / "results" / "summary.json").exists()
    assert (run.workspace_path / "results" / "steps.json").exists()
    assert (run.workspace_path / "results" / "metrics.json").exists()
    assert (run.workspace_path / "logs" / "transcript.txt").exists()


def test_eval_cli_preserves_run_workspace(tmp_path, monkeypatch, capsys) -> None:
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "worldforge",
            "eval",
            "--suite",
            "planning",
            "--provider",
            "mock",
            "--run-workspace",
            str(tmp_path),
            "--format",
            "json",
        ],
    )

    assert main() == 0
    assert json.loads(capsys.readouterr().out)["suite_id"] == "planning"
    runs = list_run_workspaces(tmp_path)

    assert len(runs) == 1
    assert runs[0]["kind"] == "eval"
    assert runs[0]["operation"] == "planning"
    run_path = Path(str(runs[0]["path"]))
    assert json.loads((run_path / "reports" / "report.json").read_text())["suite_id"] == "planning"
    assert (run_path / "reports" / "report.md").exists()
    assert (run_path / "reports" / "report.csv").exists()


def test_benchmark_cli_preserves_failed_budget_workspace(tmp_path, monkeypatch, capsys) -> None:
    budget_file = tmp_path / "budget.json"
    budget_file.write_text(
        json.dumps(
            {
                "budgets": [
                    {
                        "provider": "mock",
                        "operation": "predict",
                        "max_error_count": 0,
                        "max_average_latency_ms": 0.0,
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "worldforge",
            "benchmark",
            "--provider",
            "mock",
            "--operation",
            "predict",
            "--iterations",
            "1",
            "--budget-file",
            str(budget_file),
            "--run-workspace",
            str(tmp_path),
            "--format",
            "json",
        ],
    )

    assert main() == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload["gate"]["passed"] is False
    run = list_run_workspaces(tmp_path)[0]

    assert run["kind"] == "benchmark"
    assert run["status"] == "failed"
    assert run["result_summary"]["budget_passed"] is False
    assert Path(str(run["path"]), "reports", "report.json").exists()


def test_runs_cleanup_keeps_newest_run_workspaces(tmp_path, monkeypatch, capsys) -> None:
    create_run_workspace(
        tmp_path,
        kind="eval",
        command="worldforge eval",
        run_id="20260101T000000Z-00000001",
    )
    create_run_workspace(
        tmp_path,
        kind="eval",
        command="worldforge eval",
        run_id="20260102T000000Z-00000002",
    )

    selected = cleanup_run_workspaces(tmp_path, keep=1, dry_run=True)
    assert [path.name for path in selected] == ["20260101T000000Z-00000001"]

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "worldforge",
            "runs",
            "cleanup",
            "--workspace-dir",
            str(tmp_path),
            "--keep",
            "1",
        ],
    )

    assert main() == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["removed_count"] == 1
    assert [run["run_id"] for run in list_run_workspaces(tmp_path)] == ["20260102T000000Z-00000002"]


def test_runs_cli_markdown_and_dry_run_cleanup(tmp_path, monkeypatch, capsys) -> None:
    create_run_workspace(
        tmp_path,
        kind="eval",
        command="worldforge eval",
        provider="mock",
        run_id="20260101T000000Z-00000001",
    )
    create_run_workspace(
        tmp_path,
        kind="benchmark",
        command="worldforge benchmark",
        provider="mock",
        run_id="20260102T000000Z-00000002",
    )

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "worldforge",
            "runs",
            "list",
            "--workspace-dir",
            str(tmp_path),
            "--format",
            "markdown",
        ],
    )
    assert main() == 0
    list_output = capsys.readouterr().out
    assert "# WorldForge Runs" in list_output
    assert "20260102T000000Z-00000002" in list_output

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "worldforge",
            "runs",
            "cleanup",
            "--workspace-dir",
            str(tmp_path),
            "--keep",
            "1",
            "--dry-run",
            "--format",
            "markdown",
        ],
    )
    assert main() == 0
    cleanup_output = capsys.readouterr().out
    assert "# WorldForge Run Cleanup Preview" in cleanup_output
    assert "selected_count: 1" in cleanup_output
    assert len(list_run_workspaces(tmp_path)) == 2


def test_runs_compare_exports_benchmark_artifacts(tmp_path, monkeypatch, capsys) -> None:
    first = _preserved_benchmark_run(
        tmp_path,
        run_id="20260101T000000Z-00000001",
        average_latency_ms=10.0,
        throughput_per_second=5.0,
    )
    second = _preserved_benchmark_run(
        tmp_path,
        run_id="20260102T000000Z-00000002",
        average_latency_ms=15.0,
        throughput_per_second=4.0,
    )
    csv_path = tmp_path / "comparison.csv"

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "worldforge",
            "runs",
            "compare",
            str(first.path),
            str(second.manifest_path),
            "--format",
            "json",
        ],
    )
    assert main() == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["kind"] == "benchmark"
    assert payload["baseline_run_id"] == "20260101T000000Z-00000001"
    assert payload["rows"][1]["delta_average_latency_ms"] == 5.0
    assert "budget_file:/tmp/budget.json#abc123" in payload["runs"][0]["provenance_refs"]
    assert str(first.path / "reports" / "report.json") in payload["runs"][0]["artifact_refs"]

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "worldforge",
            "runs",
            "compare",
            str(first.path),
            str(second.path),
            "--format",
            "csv",
            "--output",
            str(csv_path),
        ],
    )
    assert main() == 0
    assert "delta_average_latency_ms" in csv_path.read_text(encoding="utf-8")
    assert capsys.readouterr().out == ""

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "worldforge",
            "runs",
            "compare",
            str(first.path),
            str(second.path),
            "--format",
            "markdown",
        ],
    )
    assert main() == 0
    markdown = capsys.readouterr().out
    assert "# WorldForge Run Comparison" in markdown
    assert "## Benchmark Rows" in markdown


def test_runs_compare_exports_eval_summary(tmp_path, monkeypatch, capsys) -> None:
    first = _preserved_eval_run(
        tmp_path,
        run_id="20260101T000000Z-00000001",
        average_score=0.75,
    )
    second = _preserved_eval_run(
        tmp_path,
        run_id="20260102T000000Z-00000002",
        average_score=0.5,
    )

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "worldforge",
            "runs",
            "compare",
            str(first.path / "reports" / "report.json"),
            str(second.path),
            "--format",
            "json",
        ],
    )

    assert main() == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["kind"] == "eval"
    assert payload["rows"][1]["delta_average_score"] == -0.25
    assert 'suite_id:"planning"' in payload["runs"][0]["provenance_refs"]


def test_runs_compare_refuses_incompatible_report_types(tmp_path, monkeypatch, capsys) -> None:
    benchmark = _preserved_benchmark_run(
        tmp_path,
        run_id="20260101T000000Z-00000001",
        average_latency_ms=10.0,
        throughput_per_second=5.0,
    )
    evaluation = _preserved_eval_run(
        tmp_path,
        run_id="20260102T000000Z-00000002",
        average_score=0.5,
    )

    monkeypatch.setattr(
        sys,
        "argv",
        ["worldforge", "runs", "compare", str(benchmark.path), str(evaluation.path)],
    )

    with pytest.raises(SystemExit) as exc:
        main()
    assert exc.value.code == 2
    assert "Cannot compare incompatible report types" in capsys.readouterr().err


def test_run_id_validation_rejects_non_sortable_names() -> None:
    with pytest.raises(ValueError, match="run_id must match"):
        validate_run_id("not safe")


def test_workspace_helpers_reject_escape_and_invalid_cleanup(tmp_path) -> None:
    workspace = create_run_workspace(
        tmp_path,
        kind="eval",
        command="worldforge eval",
        run_id="20260101T000000Z-00000001",
    )

    assert workspace_root_for_state_dir(Path(".worldforge/worlds")) == Path(".worldforge")
    assert list_run_workspaces(tmp_path / "missing") == ()
    with pytest.raises(ValueError, match="escapes workspace"):
        workspace.write_json("../escape.json", {})
    with pytest.raises(ValueError, match="keep must be"):
        cleanup_run_workspaces(tmp_path, keep=-1)

    bad_manifest = tmp_path / "runs" / "bad" / "run_manifest.json"
    bad_manifest.parent.mkdir(parents=True)
    bad_manifest.write_text("not-json", encoding="utf-8")
    assert [run["run_id"] for run in list_run_workspaces(tmp_path)] == ["20260101T000000Z-00000001"]


def _preserved_benchmark_run(
    workspace_dir: Path,
    *,
    run_id: str,
    average_latency_ms: float,
    throughput_per_second: float,
):
    workspace = create_run_workspace(
        workspace_dir,
        kind="benchmark",
        command="worldforge benchmark --provider mock --operation predict",
        provider="mock",
        operation="predict",
        run_id=run_id,
        input_summary={"providers": ["mock"], "operations": ["predict"]},
    )
    report = {
        "claim_boundary": "test",
        "metric_semantics": "test",
        "run_metadata": {
            "budget_file": {
                "path": "/tmp/budget.json",
                "sha256": "abc123",
                "metadata": {"profile": "ci"},
            }
        },
        "results": [
            {
                "provider": "mock",
                "operation": "predict",
                "iterations": 2,
                "concurrency": 1,
                "success_count": 2,
                "error_count": 0,
                "retry_count": 1,
                "total_time_ms": average_latency_ms * 2,
                "average_latency_ms": average_latency_ms,
                "min_latency_ms": average_latency_ms,
                "max_latency_ms": average_latency_ms,
                "p50_latency_ms": average_latency_ms,
                "p95_latency_ms": average_latency_ms,
                "throughput_per_second": throughput_per_second,
                "operation_metrics": {"events": [{"request_count": 2}]},
                "errors": [],
            }
        ],
    }
    workspace.write_json("reports/report.json", report)
    workspace.write_text("reports/report.md", "# Benchmark Report")
    workspace.write_text("reports/report.csv", "provider,operation\nmock,predict\n")
    write_run_manifest(
        workspace,
        kind="benchmark",
        command="worldforge benchmark --provider mock --operation predict",
        provider="mock",
        operation="predict",
        status="completed",
        input_summary={"providers": ["mock"], "operations": ["predict"]},
        result_summary={"result_count": 1, "error_count": 0, "retry_count": 1},
        artifact_paths={
            "json": "reports/report.json",
            "markdown": "reports/report.md",
            "csv": "reports/report.csv",
        },
        event_count=2,
    )
    return workspace


def _preserved_eval_run(workspace_dir: Path, *, run_id: str, average_score: float):
    workspace = create_run_workspace(
        workspace_dir,
        kind="eval",
        command="worldforge eval --suite planning --provider mock",
        provider="mock",
        operation="planning",
        run_id=run_id,
        input_summary={"suite_id": "planning", "providers": ["mock"]},
    )
    report = {
        "suite_id": "planning",
        "suite": "Planning Evaluation",
        "claim_boundary": "test",
        "metric_semantics": "test",
        "provider_summaries": [
            {
                "provider": "mock",
                "average_score": average_score,
                "scenario_count": 2,
                "passed_scenario_count": 1,
                "failed_scenario_count": 1,
                "pass_rate": 0.5,
            }
        ],
        "results": [],
    }
    workspace.write_json("reports/report.json", report)
    workspace.write_text("reports/report.md", "# Evaluation Report")
    workspace.write_text("reports/report.csv", "provider,scenario\nmock,plan\n")
    write_run_manifest(
        workspace,
        kind="eval",
        command="worldforge eval --suite planning --provider mock",
        provider="mock",
        operation="planning",
        status="completed",
        input_summary={"suite_id": "planning", "providers": ["mock"]},
        result_summary={"suite_id": "planning", "result_count": 2, "passed_count": 1},
        artifact_paths={
            "json": "reports/report.json",
            "markdown": "reports/report.md",
            "csv": "reports/report.csv",
        },
    )
    return workspace

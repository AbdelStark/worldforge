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

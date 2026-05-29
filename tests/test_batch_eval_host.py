from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BATCH_APP = ROOT / "examples" / "hosts" / "batch-eval" / "app.py"


def _load_batch_app():
    import importlib.util

    spec = importlib.util.spec_from_file_location("worldforge_batch_eval_host_example", BATCH_APP)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_batch_eval_host_runs_mock_eval_job(tmp_path) -> None:
    app = _load_batch_app()
    result = app.run_eval_job(
        suite="planning",
        providers=["mock"],
        workspace_dir=tmp_path / "workspace",
        state_dir=tmp_path / "worlds",
    )

    assert result["status"] == "passed"
    assert result["exit_code"] == 0
    run_workspace = Path(result["run_workspace"])
    manifest = json.loads(Path(result["run_manifest"]).read_text(encoding="utf-8"))

    assert manifest["kind"] == "eval"
    assert manifest["operation"] == "planning"
    assert manifest["status"] == "completed"
    assert manifest["artifact_paths"]["json"] == "reports/report.json"
    assert (run_workspace / "reports" / "report.json").exists()
    assert (run_workspace / "reports" / "report.md").exists()
    assert (run_workspace / "reports" / "report.csv").exists()


def test_batch_eval_host_runs_mock_benchmark_with_inputs_and_budget(tmp_path) -> None:
    app = _load_batch_app()
    result = app.run_benchmark_job(
        providers=["mock"],
        operations=["generate"],
        iterations=1,
        concurrency=1,
        workspace_dir=tmp_path / "workspace",
        state_dir=tmp_path / "worlds",
        input_file=ROOT / "examples" / "benchmark-inputs.json",
        budget_file=ROOT / "examples" / "benchmark-budget.json",
    )

    assert result["status"] == "passed"
    assert result["exit_code"] == 0
    assert result["budget"]["passed"] is True
    run_workspace = Path(result["run_workspace"])
    manifest = json.loads(Path(result["run_manifest"]).read_text(encoding="utf-8"))

    assert manifest["kind"] == "benchmark"
    assert manifest["status"] == "completed"
    assert manifest["artifact_paths"]["input_file"] == "inputs/benchmark-inputs.json"
    assert manifest["artifact_paths"]["budget_file"] == "inputs/benchmark-budget.json"
    assert (run_workspace / "inputs" / "benchmark-inputs.json").exists()
    assert (run_workspace / "inputs" / "benchmark-budget.json").exists()
    assert (run_workspace / "reports" / "report.json").exists()
    assert "sha256" in result["input_file"]
    assert "sha256" in result["budget_file"]


def test_batch_eval_host_exits_nonzero_on_budget_violation(tmp_path, capsys) -> None:
    app = _load_batch_app()
    budget_file = tmp_path / "budget.json"
    budget_file.write_text(
        json.dumps(
            {
                "budgets": [
                    {
                        "provider": "mock",
                        "operation": "predict",
                        "max_average_latency_ms": 0.0,
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    exit_code = app.main(
        [
            "--workspace",
            str(tmp_path / "workspace"),
            "--state-dir",
            str(tmp_path / "worlds"),
            "benchmark",
            "--provider",
            "mock",
            "--operation",
            "predict",
            "--iterations",
            "1",
            "--budget-file",
            str(budget_file),
        ]
    )
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 1
    assert payload["status"] == "failed"
    assert payload["budget"]["passed"] is False
    manifest = json.loads(Path(payload["run_manifest"]).read_text(encoding="utf-8"))
    assert manifest["status"] == "failed"
    assert manifest["result_summary"]["budget_passed"] is False

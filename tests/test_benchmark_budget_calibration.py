from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest

from worldforge import ProviderBenchmarkHarness, WorldForge
from worldforge.benchmark import BenchmarkReport, load_benchmark_budgets
from worldforge.benchmark_calibration import calibrate_benchmark_budgets
from worldforge.models import WorldForgeError

ROOT = Path(__file__).resolve().parents[1]


def _write_benchmark_report(path: Path, *, state_dir: Path) -> BenchmarkReport:
    report = ProviderBenchmarkHarness(forge=WorldForge(state_dir=state_dir)).run(
        "mock",
        operations=["generate"],
        iterations=2,
    )
    assert report.provenance is not None
    report.provenance = report.provenance.with_overrides(
        command=("worldforge", "benchmark", "--provider", "mock", "--operation", "generate"),
    )
    path.write_text(report.to_json() + "\n", encoding="utf-8")
    return report


def _write_current_budget(path: Path, *, max_average_latency_ms: float = 10_000.0) -> str:
    payload = {
        "metadata": {"purpose": "current release budget"},
        "budgets": [
            {
                "provider": "mock",
                "operation": "generate",
                "min_success_rate": 1.0,
                "max_error_count": 0,
                "max_retry_count": 0,
                "max_average_latency_ms": max_average_latency_ms,
                "max_p95_latency_ms": 10_000.0,
                "min_throughput_per_second": 0.0,
            }
        ],
    }
    text = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    path.write_text(text, encoding="utf-8")
    return text


def test_budget_calibration_writes_reviewable_candidate_artifacts(tmp_path: Path) -> None:
    report_path = tmp_path / "benchmark-report.json"
    report = _write_benchmark_report(report_path, state_dir=tmp_path / "worlds")
    current_budget_path = tmp_path / "current-budget.json"
    _write_current_budget(current_budget_path)

    result = calibrate_benchmark_budgets(
        (report_path,),
        current_budget_path=current_budget_path,
        output_dir=tmp_path / "calibration",
        headroom_ratio=0.10,
        machine_class="ci-macos-arm64",
        rationale="hardware cohort review",
    )

    assert result.calibration_path is not None
    assert result.calibration_path.exists()
    assert result.candidate_budget_path is not None
    assert result.candidate_budget_path.exists()
    assert result.markdown_path is not None
    assert result.markdown_path.exists()

    payload = result.payload
    source = payload["source_reports"][0]
    expected_digest = f"sha256:{hashlib.sha256(report_path.read_bytes()).hexdigest()}"
    assert source["sha256"] == expected_digest
    assert source["command"] == "worldforge benchmark --provider mock --operation generate"

    baseline = payload["baseline_context"][0]
    assert baseline["provider"] == "mock"
    assert baseline["operation"] == "generate"
    assert baseline["sample_count"] == 2
    assert baseline["machine_class"] == "ci-macos-arm64"
    assert baseline["python_version"]
    assert baseline["input_fixture_digest"] == report.provenance.input_digest

    candidate_payload = json.loads(result.candidate_budget_path.read_text(encoding="utf-8"))
    candidate_budget = load_benchmark_budgets(candidate_payload)[0]
    assert candidate_budget.provider == "mock"
    assert candidate_budget.operation == "generate"
    assert candidate_budget.min_success_rate == 1.0
    assert candidate_budget.max_error_count == 0
    assert candidate_budget.max_retry_count == 0
    assert candidate_budget.max_average_latency_ms is not None
    assert candidate_budget.max_average_latency_ms >= report.results[0].average_latency_ms

    average_latency_diff = next(
        diff for diff in payload["diffs"] if diff["metric"] == "max_average_latency_ms"
    )
    assert average_latency_diff["old_threshold"] == 10_000.0
    assert average_latency_diff["candidate_threshold"] == candidate_budget.max_average_latency_ms
    assert average_latency_diff["observed_baseline"] == report.results[0].average_latency_ms
    assert average_latency_diff["rationale"] == "hardware cohort review"
    assert average_latency_diff["review_required"] is True

    markdown = result.markdown_path.read_text(encoding="utf-8")
    assert "## Human Review Required" in markdown
    assert "ci-macos-arm64" in markdown
    assert "hardware cohort review" in markdown


def test_budget_calibration_preserves_current_budget_and_existing_failure_behavior(
    tmp_path: Path,
) -> None:
    report_path = tmp_path / "benchmark-report.json"
    report = _write_benchmark_report(report_path, state_dir=tmp_path / "worlds")
    current_budget_path = tmp_path / "current-budget.json"
    original_budget_text = _write_current_budget(current_budget_path, max_average_latency_ms=0.0)

    gate = report.evaluate_budgets(
        load_benchmark_budgets(json.loads(current_budget_path.read_text(encoding="utf-8")))
    )

    assert gate.passed is False
    assert any(violation.metric == "average_latency_ms" for violation in gate.violations)

    calibrate_benchmark_budgets(
        (report_path,),
        current_budget_path=current_budget_path,
        output_dir=tmp_path / "calibration",
    )

    assert current_budget_path.read_text(encoding="utf-8") == original_budget_text


def test_budget_calibration_can_return_payload_without_writing_artifacts(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("WORLDFORGE_MACHINE_CLASS", "env-ci-runner")
    report_path = tmp_path / "benchmark-report.json"
    _write_benchmark_report(report_path, state_dir=tmp_path / "worlds")

    result = calibrate_benchmark_budgets((report_path,))

    assert result.output_dir is None
    assert result.calibration_path is None
    assert result.candidate_budget_path is None
    assert result.markdown_path is None
    assert result.payload["current_budget_digest"] is None
    assert result.payload["baseline_context"][0]["machine_class"] == "env-ci-runner"
    assert {diff["old_threshold"] for diff in result.payload["diffs"]} == {None}


@pytest.mark.parametrize(
    ("contents", "match"),
    (
        ("[]", "JSON object"),
        ('{"results": []}', "non-empty results"),
        ('{"results": [true]}', "results must contain JSON objects"),
        (
            json.dumps(
                {
                    "results": [
                        {
                            "provider": "mock",
                            "operation": "generate",
                            "iterations": 2,
                            "success_count": 1,
                            "error_count": 0,
                            "retry_count": 0,
                        }
                    ]
                }
            ),
            "must sum to iterations",
        ),
    ),
)
def test_budget_calibration_rejects_malformed_reports(
    tmp_path: Path,
    contents: str,
    match: str,
) -> None:
    report_path = tmp_path / "bad-report.json"
    report_path.write_text(contents, encoding="utf-8")

    with pytest.raises(WorldForgeError, match=match):
        calibrate_benchmark_budgets((report_path,))


def test_budget_calibration_rejects_invalid_review_inputs(tmp_path: Path) -> None:
    report_path = tmp_path / "benchmark-report.json"
    _write_benchmark_report(report_path, state_dir=tmp_path / "worlds")
    bad_budget_path = tmp_path / "bad-budget.json"
    bad_budget_path.write_text("{", encoding="utf-8")

    with pytest.raises(WorldForgeError, match="At least one benchmark report path"):
        calibrate_benchmark_budgets(())
    with pytest.raises(WorldForgeError, match="headroom_ratio must be between"):
        calibrate_benchmark_budgets((report_path,), headroom_ratio=-0.1)
    with pytest.raises(WorldForgeError, match="rationale must be a non-empty string"):
        calibrate_benchmark_budgets((report_path,), rationale="")
    with pytest.raises(WorldForgeError, match="Current budget file contains invalid JSON"):
        calibrate_benchmark_budgets((report_path,), current_budget_path=bad_budget_path)


def test_calibration_script_generates_candidate_budget_files(tmp_path: Path) -> None:
    report_path = tmp_path / "benchmark-report.json"
    _write_benchmark_report(report_path, state_dir=tmp_path / "worlds")
    current_budget_path = tmp_path / "current-budget.json"
    _write_current_budget(current_budget_path)
    output = tmp_path / "script-calibration"

    completed = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts/calibrate_benchmark_budgets.py"),
            "--report",
            str(report_path),
            "--current-budget",
            str(current_budget_path),
            "--output",
            str(output),
            "--headroom-ratio",
            "0.2",
            "--machine-class",
            "developer-laptop",
            "--rationale",
            "manual review",
        ],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )

    assert "review required before replacing any release budget file" in completed.stdout
    assert (output / "budget-calibration.json").exists()
    assert (output / "budget-calibration.md").exists()
    candidate_payload = json.loads((output / "candidate-budgets.json").read_text(encoding="utf-8"))
    candidate_budget = load_benchmark_budgets(candidate_payload)[0]
    assert candidate_budget.provider == "mock"

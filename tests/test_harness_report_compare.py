from __future__ import annotations

from pathlib import Path

import pytest

from worldforge.harness.report_compare import (
    compare_preserved_run_regression,
    compare_preserved_run_reports,
    comparison_artifact,
    comparison_to_csv,
    comparison_to_markdown,
)
from worldforge.harness.workspace import create_run_workspace, write_run_manifest
from worldforge.models import WorldForgeError

FIXTURE_DIGEST = "sha256:" + "a" * 64
BUDGET_DIGEST = "sha256:" + "b" * 64


def test_cross_provider_benchmark_comparison_exports_context_and_budget_status(
    tmp_path: Path,
) -> None:
    baseline = _benchmark_run(
        tmp_path,
        run_id="20260101T000000Z-00000001",
        provider="mock",
        average_latency_ms=10.0,
        budget_passed=True,
    )
    candidate = _benchmark_run(
        tmp_path,
        run_id="20260102T000000Z-00000002",
        provider="manual-mock",
        average_latency_ms=12.0,
        budget_passed=False,
    )

    payload = compare_preserved_run_reports([baseline.path, candidate.path])

    assert payload["schema_version"] == 2
    assert payload["comparison_context"]["providers"] == ["manual-mock", "mock"]
    assert payload["comparison_context"]["capabilities"] == ["predict"]
    assert payload["comparison_context"]["operations"] == ["predict"]
    assert payload["comparison_context"]["fixture_digest"] == FIXTURE_DIGEST
    assert payload["comparison_context"]["budget_refs"] == [
        f"/fixtures/budget.json#{BUDGET_DIGEST}"
    ]
    assert payload["rows"][1]["provider"] == "manual-mock"
    assert payload["rows"][1]["delta_average_latency_ms"] == 2.0
    assert payload["rows"][1]["budget_passed"] is False
    assert payload["rows"][1]["event_count"] == 3

    markdown = comparison_to_markdown(payload)
    assert "Claim boundary: benchmark claim boundary" in markdown
    assert "## Comparison Context" in markdown
    assert FIXTURE_DIGEST in markdown
    assert "failed `/fixtures/budget.json#" in markdown

    csv_output = comparison_to_csv(payload)
    assert "budget_passed" in csv_output
    assert "manual-mock" in csv_output


@pytest.mark.parametrize(
    ("field", "kwargs", "message"),
    [
        (
            "fixture",
            {"fixture_digest": "sha256:" + "c" * 64},
            "fixture digest mismatch",
        ),
        ("capability", {"capability": "generate"}, "capability mismatch"),
        ("operation", {"operation": "generate"}, "operation mismatch"),
        (
            "budget",
            {"budget_digest": "sha256:" + "d" * 64},
            "budget mismatch",
        ),
        ("suite_version", {"suite_version": "benchmark:2"}, "suite version mismatch"),
    ],
)
def test_benchmark_comparison_refuses_incompatible_run_context(
    tmp_path: Path,
    field: str,
    kwargs: dict[str, str],
    message: str,
) -> None:
    del field
    baseline = _benchmark_run(
        tmp_path,
        run_id="20260101T000000Z-00000001",
        provider="mock",
        average_latency_ms=10.0,
    )
    candidate = _benchmark_run(
        tmp_path,
        run_id="20260102T000000Z-00000002",
        provider="manual-mock",
        average_latency_ms=12.0,
        **kwargs,
    )

    with pytest.raises(WorldForgeError, match=message):
        compare_preserved_run_reports([baseline.path, candidate.path])


def test_cross_provider_evaluation_comparison_uses_suite_context(tmp_path: Path) -> None:
    baseline = _evaluation_run(
        tmp_path,
        run_id="20260101T000000Z-00000001",
        provider="mock",
        average_score=0.75,
    )
    candidate = _evaluation_run(
        tmp_path,
        run_id="20260102T000000Z-00000002",
        provider="manual-mock",
        average_score=0.50,
    )

    payload = compare_preserved_run_reports([baseline.path, candidate.path])

    assert payload["kind"] == "eval"
    assert payload["comparison_context"]["providers"] == ["manual-mock", "mock"]
    assert payload["comparison_context"]["operations"] == ["planning"]
    assert payload["comparison_context"]["capabilities"] == ["predict"]
    assert payload["comparison_context"]["suite_version"] == "evaluation:1"
    assert payload["rows"][1]["suite_id"] == "planning"
    assert payload["rows"][1]["delta_average_score"] == -0.25
    assert payload["rows"][1]["event_count"] == 2


def test_comparison_surfaces_missing_evidence_and_skip_reasons(tmp_path: Path) -> None:
    first = _minimal_skipped_benchmark_run(
        tmp_path,
        run_id="20260101T000000Z-00000001",
        provider="mock",
    )
    second = _minimal_skipped_benchmark_run(
        tmp_path,
        run_id="20260102T000000Z-00000002",
        provider="manual-mock",
    )

    payload = compare_preserved_run_reports([first.path, second.path])

    assert payload["comparison_context"]["missing_evidence"] == [
        "budget_status",
        "fixture_digest",
        "suite_version",
    ]
    assert payload["runs"][0]["skip_reason"] == "optional runtime unavailable"
    assert payload["runs"][0]["missing_evidence"] == [
        "fixture_digest",
        "suite_version",
        "budget_status",
    ]
    markdown = comparison_to_markdown(payload)
    assert "`fixture_digest`" in markdown
    assert "optional runtime unavailable" in markdown


def test_regression_comparison_reports_improved_candidate(tmp_path: Path) -> None:
    baseline = _benchmark_run(
        tmp_path,
        run_id="20260101T000000Z-00000001",
        provider="mock",
        average_latency_ms=12.0,
        budget_passed=False,
    )
    candidate = _benchmark_run(
        tmp_path,
        run_id="20260102T000000Z-00000002",
        provider="manual-mock",
        average_latency_ms=8.0,
        budget_passed=True,
    )

    payload = compare_preserved_run_reports(
        [baseline.path, candidate.path],
        mode="regression",
    )

    assert payload["mode"] == "regression"
    assert payload["kind"] == "benchmark"
    assert payload["regression_summary"]["status"] == "improved"
    average_latency = _metric(payload, "average_latency_ms")
    assert average_latency["delta"] == -4.0
    assert average_latency["status"] == "improved"
    assert payload["budget_status_changes"]["status"] == "improved"
    assert payload["artifact_changes"]["status"] == "changed"

    markdown = comparison_artifact(payload, output_format="markdown")
    assert "# WorldForge Regression Comparison" in markdown
    assert "Budget Status" in markdown
    html = comparison_artifact(payload, output_format="html")
    assert "WorldForge Regression Comparison" in html
    assert "Regression Summary" in html
    csv_output = comparison_artifact(payload, output_format="csv")
    assert "metric,average_latency_ms,improved" in csv_output


def test_regression_comparison_reports_regression_and_excludes_unsafe_artifacts(
    tmp_path: Path,
) -> None:
    baseline = _benchmark_run(
        tmp_path,
        run_id="20260101T000000Z-00000001",
        provider="mock",
        average_latency_ms=10.0,
        budget_passed=True,
    )
    candidate = _benchmark_run(
        tmp_path,
        run_id="20260102T000000Z-00000002",
        provider="manual-mock",
        average_latency_ms=15.0,
        budget_passed=False,
        errors=[{"message": "timeout"}],
        unsafe_artifact=True,
    )

    payload = compare_preserved_run_regression([baseline.path, candidate.path])

    assert payload["regression_summary"]["status"] == "regressed"
    assert _metric(payload, "average_latency_ms")["status"] == "regressed"
    assert payload["budget_status_changes"]["status"] == "budget-violation"
    assert payload["failure_changes"]["new_failures"] == ["benchmark:predict:timeout"]
    assert payload["artifact_changes"]["excluded_unsafe_count"] == 1
    rendered = comparison_artifact(payload, output_format="markdown")
    assert "/private/checkpoint.bin" not in rendered
    assert "Unsafe artifacts excluded from rendered reports: `1`" in rendered


def test_regression_comparison_supports_demo_showcase_runs(tmp_path: Path) -> None:
    baseline = _demo_showcase_run(
        tmp_path,
        run_id="20260101T000000Z-00000001",
        workflow="first-run",
        status="passed",
        safe_to_attach=True,
        summary="baseline completed",
    )
    candidate = _demo_showcase_run(
        tmp_path,
        run_id="20260102T000000Z-00000002",
        workflow="first-run",
        status="failed",
        safe_to_attach=False,
        summary="candidate failed",
    )

    payload = compare_preserved_run_reports(
        [baseline.path, candidate.path],
        mode="regression",
    )

    assert payload["kind"] == "demo_showcase"
    assert payload["regression_summary"]["status"] == "regressed"
    assert _metric(payload, "safe_to_attach")["status"] == "regressed"
    assert payload["failure_changes"]["new_failures"] == ["run:failed:failed"]


def test_regression_comparison_reports_missing_baseline(tmp_path: Path) -> None:
    candidate = _benchmark_run(
        tmp_path,
        run_id="20260102T000000Z-00000002",
        provider="mock",
        average_latency_ms=8.0,
    )

    with pytest.raises(WorldForgeError, match="Baseline run does not exist"):
        compare_preserved_run_reports(
            [tmp_path / "missing-baseline", candidate.path],
            mode="regression",
        )


def test_regression_comparison_rejects_incompatible_run_schema(tmp_path: Path) -> None:
    baseline = _benchmark_run(
        tmp_path,
        run_id="20260101T000000Z-00000001",
        provider="mock",
        average_latency_ms=10.0,
    )
    candidate = _benchmark_run(
        tmp_path,
        run_id="20260102T000000Z-00000002",
        provider="manual-mock",
        average_latency_ms=8.0,
    )
    manifest = baseline.manifest_path.read_text(encoding="utf-8")
    baseline.manifest_path.write_text(
        manifest.replace('"schema_version": 1', '"schema_version": 99'),
        encoding="utf-8",
    )

    with pytest.raises(WorldForgeError, match="unsupported run workspace schema_version"):
        compare_preserved_run_regression([baseline.path, candidate.path])


def _benchmark_run(
    workspace_dir: Path,
    *,
    run_id: str,
    provider: str,
    average_latency_ms: float,
    operation: str = "predict",
    capability: str = "predict",
    fixture_digest: str = FIXTURE_DIGEST,
    budget_digest: str = BUDGET_DIGEST,
    suite_version: str = "benchmark:1",
    budget_passed: bool | None = True,
    errors: list[object] | None = None,
    unsafe_artifact: bool = False,
):
    workspace = create_run_workspace(
        workspace_dir,
        kind="benchmark",
        command=f"worldforge benchmark --provider {provider} --operation {operation}",
        provider=provider,
        operation=operation,
        run_id=run_id,
        input_summary={
            "providers": [provider],
            "operations": [operation],
            "capabilities": [capability],
        },
    )
    resolved_errors = list(errors or [])
    report = {
        "claim_boundary": "benchmark claim boundary",
        "run_metadata": {
            "input_file": {
                "path": "/fixtures/benchmark-inputs.json",
                "sha256": fixture_digest,
            },
            "budget_file": {
                "path": "/fixtures/budget.json",
                "sha256": budget_digest,
            },
        },
        "provenance": {
            "kind": "benchmark",
            "suite_id": "benchmark",
            "suite_version": suite_version,
            "providers": [provider],
            "capabilities": [capability],
            "input_digest": "sha256:" + "f" * 64,
            "budget_file": {
                "path": "/fixtures/budget.json",
                "sha256": budget_digest,
            },
            "event_count": 3,
            "claim_boundary": "benchmark claim boundary",
        },
        "results": [
            {
                "provider": provider,
                "operation": operation,
                "iterations": 2,
                "success_count": 2 if not resolved_errors else 1,
                "error_count": len(resolved_errors),
                "retry_count": 1,
                "average_latency_ms": average_latency_ms,
                "p95_latency_ms": average_latency_ms,
                "throughput_per_second": 4.0,
                "operation_metrics": {"events": [{"request_count": 3}]},
                "errors": resolved_errors,
            }
        ],
    }
    workspace.write_json("reports/report.json", report)
    result_summary = {"result_count": 1, "error_count": len(resolved_errors), "retry_count": 1}
    if budget_passed is not None:
        result_summary["budget_passed"] = budget_passed
    artifact_paths = {"json": "reports/report.json"}
    if unsafe_artifact:
        artifact_paths["checkpoint"] = "/private/checkpoint.bin"
    write_run_manifest(
        workspace,
        kind="benchmark",
        command=f"worldforge benchmark --provider {provider} --operation {operation}",
        provider=provider,
        operation=operation,
        status="completed",
        input_summary={
            "providers": [provider],
            "operations": [operation],
            "capabilities": [capability],
        },
        result_summary=result_summary,
        artifact_paths=artifact_paths,
        event_count=3,
    )
    return workspace


def _evaluation_run(
    workspace_dir: Path,
    *,
    run_id: str,
    provider: str,
    average_score: float,
):
    workspace = create_run_workspace(
        workspace_dir,
        kind="eval",
        command=f"worldforge eval --suite planning --provider {provider}",
        provider=provider,
        operation="planning",
        run_id=run_id,
        input_summary={"suite_id": "planning", "providers": [provider]},
    )
    report = {
        "suite_id": "planning",
        "suite": "Planning Evaluation",
        "claim_boundary": "evaluation claim boundary",
        "run_metadata": {
            "input_file": {
                "path": "/fixtures/planning-eval.json",
                "sha256": FIXTURE_DIGEST,
            }
        },
        "provenance": {
            "kind": "evaluation",
            "suite_id": "planning",
            "suite_version": "evaluation:1",
            "providers": [provider],
            "capabilities": ["predict"],
            "input_digest": "sha256:" + "e" * 64,
            "event_count": 2,
            "claim_boundary": "evaluation claim boundary",
        },
        "provider_summaries": [
            {
                "provider": provider,
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
    write_run_manifest(
        workspace,
        kind="eval",
        command=f"worldforge eval --suite planning --provider {provider}",
        provider=provider,
        operation="planning",
        status="completed",
        input_summary={"suite_id": "planning", "providers": [provider]},
        result_summary={"scenario_count": 2, "failed_scenario_count": 1},
        artifact_paths={"json": "reports/report.json"},
        event_count=2,
    )
    return workspace


def _minimal_skipped_benchmark_run(
    workspace_dir: Path,
    *,
    run_id: str,
    provider: str,
):
    workspace = create_run_workspace(
        workspace_dir,
        kind="benchmark",
        command=f"worldforge benchmark --provider {provider} --operation predict",
        provider=provider,
        operation="predict",
        run_id=run_id,
        input_summary={"providers": [provider], "operations": ["predict"]},
    )
    workspace.write_json(
        "reports/report.json",
        {
            "results": [
                {
                    "provider": provider,
                    "operation": "predict",
                    "iterations": 0,
                    "success_count": 0,
                    "error_count": 0,
                    "retry_count": 0,
                    "average_latency_ms": None,
                    "p95_latency_ms": None,
                    "throughput_per_second": None,
                    "operation_metrics": {"events": []},
                }
            ]
        },
    )
    write_run_manifest(
        workspace,
        kind="benchmark",
        command=f"worldforge benchmark --provider {provider} --operation predict",
        provider=provider,
        operation="predict",
        status="skipped",
        input_summary={"providers": [provider], "operations": ["predict"]},
        result_summary={"skip_reason": "optional runtime unavailable"},
        artifact_paths={"json": "reports/report.json"},
        event_count=0,
    )
    return workspace


def _demo_showcase_run(
    workspace_dir: Path,
    *,
    run_id: str,
    workflow: str,
    status: str,
    safe_to_attach: bool,
    summary: str,
):
    workspace = create_run_workspace(
        workspace_dir,
        kind="demo_showcase",
        command=f"uv run python scripts/demo_showcases.py run {workflow}",
        provider="fixture",
        operation=workflow,
        run_id=run_id,
        input_summary={"workflow": workflow, "issue": 189},
    )
    workspace.write_json(
        "results/summary.json",
        {
            "status": status,
            "safe_to_attach": safe_to_attach,
            "summary": summary,
            "first_triage_step": "inspect summary",
        },
    )
    workspace.write_text("reports/summary.md", f"# {workflow}\n\n{summary}\n")
    write_run_manifest(
        workspace,
        kind="demo_showcase",
        command=f"uv run python scripts/demo_showcases.py run {workflow}",
        provider="fixture",
        operation=workflow,
        status=status,
        input_summary={"workflow": workflow, "issue": 189},
        result_summary={
            "summary": summary,
            "safe_to_attach": safe_to_attach,
            "failure_reason": "failed" if status == "failed" else "",
        },
        artifact_paths={
            "summary_json": "results/summary.json",
            "summary_markdown": "reports/summary.md",
        },
    )
    return workspace


def _metric(payload: dict[str, object], name: str) -> dict[str, object]:
    for metric in payload["metric_deltas"]:  # type: ignore[index]
        if isinstance(metric, dict) and metric["metric"] == name:
            return metric
    raise AssertionError(f"metric not found: {name}")

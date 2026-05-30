import json
from pathlib import Path

from worldforge.demos.fixture_drift_review import (
    fixture_drift_changed_paths,
    fixture_drift_paths,
    fixture_drift_summary_report,
    run_fixture_drift_review,
    run_fixture_drift_review_workflow,
)


def test_fixture_drift_paths_are_workspace_scoped(tmp_path: Path) -> None:
    paths = fixture_drift_paths(tmp_path)

    assert paths.lab_root == tmp_path / "fixture-drift-lab"
    assert paths.review_markdown == tmp_path / "fixture-drift-review.md"
    assert fixture_drift_changed_paths(paths) == {
        "examples/demo-benchmark-inputs.json",
        "examples/scenarios/demo-scenario.json",
    }
    for path in (
        paths.provider_fixture,
        paths.benchmark_fixture,
        paths.scenario_fixture,
        paths.baseline_manifest,
        paths.review_manifest,
        paths.review_json,
        paths.review_markdown,
        paths.intended_json,
        paths.refreshed_manifest,
        paths.summary,
    ):
        assert path.relative_to(tmp_path)


def test_fixture_drift_run_covers_review_statuses(tmp_path: Path) -> None:
    run = run_fixture_drift_review(tmp_path)
    report = fixture_drift_summary_report(run)

    assert report["baseline_passed"] is True
    assert report["review_passed"] is False
    assert report["intended_update_passed"] is True
    assert {"missing", "changed", "unsafe"} <= set(report["review_statuses"])
    assert set(report["managed_fixture_kinds"]) == {
        "benchmark-fixture",
        "provider-payload-fixture",
        "scenario-fixture",
    }
    assert "allow-intended-updates" in " ".join(report["approved_update_path"])
    assert run.paths.review_markdown.read_text(encoding="utf-8").startswith(
        "# Fixture Snapshot Review"
    )


def test_fixture_drift_workflow_writes_summary_and_artifacts(tmp_path: Path) -> None:
    summary = run_fixture_drift_review_workflow(tmp_path)
    report = summary["report"]

    assert summary["status"] == "passed"
    assert summary["safe_to_attach"] is True
    assert summary["claim_boundary"] == report["claim_boundary"]

    summary_path = Path(str(summary["artifact_paths"]["summary"]))
    review_path = Path(str(summary["artifact_paths"]["review_json"]))
    intended_path = Path(str(summary["artifact_paths"]["intended_update_json"]))
    assert json.loads(summary_path.read_text(encoding="utf-8")) == report
    assert json.loads(review_path.read_text(encoding="utf-8"))["passed"] is False
    assert json.loads(intended_path.read_text(encoding="utf-8"))["passed"] is True

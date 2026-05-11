from __future__ import annotations

import json

import pytest

from worldforge import WorldForge, WorldForgeError
from worldforge.evaluation import (
    EvaluationContext,
    EvaluationScenario,
    EvaluationScenarioOutcome,
    EvaluationSuite,
)


def test_builtin_evaluation_suite_names_are_stable() -> None:
    assert EvaluationSuite.builtin_names() == [
        "generation",
        "physics",
        "planning",
        "reasoning",
        "transfer",
    ]


def test_builtin_evaluation_reports_export_failure_gallery_artifacts(tmp_path) -> None:
    report = EvaluationSuite.from_builtin("physics").run_report(
        ["mock"],
        forge=WorldForge(state_dir=tmp_path),
    )
    artifacts = report.artifacts()

    assert {"json", "markdown", "csv", "failure_gallery.json", "failure_gallery.md"} <= set(
        artifacts
    )
    assert json.loads(artifacts["failure_gallery.json"])["case_count"] == 0
    assert "No failed evaluation cases." in artifacts["failure_gallery.md"]


def test_custom_evaluation_suite_runs_with_provenance_and_artifacts(tmp_path) -> None:
    def evaluate_object_count(context: EvaluationContext) -> EvaluationScenarioOutcome:
        return context.outcome(
            score=1.0,
            passed=True,
            metrics={
                "object_count": context.world.object_count,
                "scenario_index": context.index,
            },
        )

    suite = EvaluationSuite.custom(
        suite_id="custom-object-count",
        name="Custom Object Count",
        suite_version="custom-object-count:1",
        claim_boundary=(
            "This custom suite is a deterministic checkout example, not a model-quality claim."
        ),
        scenarios=[
            EvaluationScenario.from_callable(
                name="empty-world-count",
                description="Checks that a checkout-created world is readable.",
                evaluator=evaluate_object_count,
            )
        ],
    )
    EvaluationSuite.register("custom-object-count", lambda: suite, replace=True)
    try:
        report = EvaluationSuite.from_registered("custom-object-count").run_report(
            ["mock"],
            forge=WorldForge(state_dir=tmp_path),
        )
    finally:
        EvaluationSuite.unregister("custom-object-count")

    assert report.results[0].passed is True
    assert report.results[0].metrics["object_count"] == 0
    assert report.provenance is not None
    assert report.provenance.suite_version == "custom-object-count:1"
    assert report.to_dict()["claim_boundary"].startswith("This custom suite")
    assert json.loads(report.artifacts()["failure_gallery.json"])["suite_version"] == (
        "custom-object-count:1"
    )
    assert "Custom Object Count" in report.artifacts()["markdown"]


def test_custom_evaluation_suite_failure_gallery_uses_custom_claim_boundary(tmp_path) -> None:
    def fail(context: EvaluationContext) -> dict[str, object]:
        return {
            "score": 0.25,
            "passed": False,
            "metrics": {
                "local_path": "/Users/example/private/run.json",
                "tensor_values": [[1, 2, 3], [4, 5, 6]],
                "scenario": context.scenario.name,
            },
        }

    suite = EvaluationSuite.custom(
        suite_id="custom-failure",
        name="Custom Failure Suite",
        suite_version="custom-failure:1",
        claim_boundary="Custom failure gallery is issue-triage evidence only.",
        scenarios=[
            EvaluationScenario.from_callable(
                name="failing-scenario",
                description="Produces one representative failure.",
                evaluator=fail,
            )
        ],
    )

    report = suite.run_report("mock", forge=WorldForge(state_dir=tmp_path))
    gallery = report.failure_gallery()
    payload = gallery.to_dict()

    assert payload["case_count"] == 1
    assert payload["claim_boundary"] == "Custom failure gallery is issue-triage evidence only."
    assert payload["cases"][0]["metrics_preview"]["local_path"] == "[host-local-path]"
    assert payload["cases"][0]["metrics_preview"]["tensor_values"]["type"] == "array"


def test_custom_evaluation_suite_rejects_invalid_metric_payload(tmp_path) -> None:
    def invalid_metrics(context: EvaluationContext) -> EvaluationScenarioOutcome:
        return context.outcome(
            score=1.0,
            passed=True,
            metrics={"bad": object()},
        )

    suite = EvaluationSuite.custom(
        suite_id="custom-invalid-metrics",
        name="Custom Invalid Metrics",
        suite_version="custom-invalid-metrics:1",
        claim_boundary="Invalid metric fixture.",
        scenarios=[
            EvaluationScenario.from_callable(
                name="invalid-metrics",
                description="Returns a non-JSON metric payload.",
                evaluator=invalid_metrics,
            )
        ],
    )

    with pytest.raises(WorldForgeError, match=r"EvaluationScenarioOutcome metrics\.bad"):
        suite.run_report("mock", forge=WorldForge(state_dir=tmp_path))

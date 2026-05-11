"""Custom evaluation suite walkthrough built through WorldForge's public authoring API."""

from __future__ import annotations

import json
from pathlib import Path

from worldforge import WorldForge
from worldforge.evaluation import (
    EvaluationContext,
    EvaluationScenario,
    EvaluationScenarioOutcome,
    EvaluationSuite,
)
from worldforge.models import JSONDict


def evaluate_empty_world(context: EvaluationContext) -> EvaluationScenarioOutcome:
    """Score whether the checkout-created world is readable and deterministic."""

    object_count = context.world.object_count
    return context.outcome(
        score=1.0,
        passed=object_count == 0,
        metrics={"object_count": object_count, "scenario": context.scenario.name},
    )


def evaluate_expected_failure(context: EvaluationContext) -> EvaluationScenarioOutcome:
    """Produce one controlled failed case for failure-gallery documentation."""

    return context.outcome(
        score=0.25,
        passed=False,
        metrics={
            "scenario": context.scenario.name,
            "expected_signal": "controlled failure for walkthrough",
            "local_path": "/Users/example/private/custom-eval.json",
            "tensor_values": [[1.0, 2.0], [3.0, 4.0]],
        },
    )


def build_suite() -> EvaluationSuite:
    return EvaluationSuite.custom(
        suite_id="custom-empty-world",
        name="Custom Empty World Evaluation",
        suite_version="custom-empty-world:1",
        claim_boundary=(
            "This custom suite is a deterministic checkout example. It is not a physical "
            "fidelity, model quality, safety, or leaderboard claim."
        ),
        scenarios=[
            EvaluationScenario.from_callable(
                name="empty-world-readable",
                description="Checks that a newly created world can be inspected.",
                evaluator=evaluate_empty_world,
            ),
            EvaluationScenario.from_callable(
                name="controlled-failure-gallery",
                description="Creates one deterministic failed case for report review.",
                evaluator=evaluate_expected_failure,
            ),
        ],
    )


def run_walkthrough(*, output_dir: Path, state_dir: Path) -> JSONDict:
    """Run the custom suite and preserve every report artifact."""

    output_dir.mkdir(parents=True, exist_ok=True)
    forge = WorldForge(state_dir=state_dir)
    report = build_suite().run_report("mock", forge=forge)
    artifacts = report.artifacts()
    artifact_paths: dict[str, str] = {}
    for artifact_name, artifact_text in artifacts.items():
        path = output_dir / artifact_name
        path.write_text(artifact_text, encoding="utf-8")
        artifact_paths[artifact_name] = str(path)
    artifact_paths["walkthrough-summary.json"] = str(output_dir / "walkthrough-summary.json")
    summary: JSONDict = {
        "schema_version": 1,
        "suite_id": report.suite_id,
        "provider": "mock",
        "result_count": len(report.results),
        "passed_count": sum(1 for result in report.results if result.passed),
        "failed_count": sum(1 for result in report.results if not result.passed),
        "provenance_present": report.provenance is not None,
        "failure_gallery_cases": report.failure_gallery().case_count,
        "artifact_paths": artifact_paths,
        "claim_boundary": report.claim_boundary,
        "safe_to_attach": True,
    }
    (output_dir / "walkthrough-summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return summary


def main() -> None:
    summary = run_walkthrough(
        output_dir=Path(".worldforge") / "custom-eval-artifacts",
        state_dir=Path(".worldforge") / "custom-eval-worlds",
    )
    print(Path(summary["artifact_paths"]["markdown"]).read_text(encoding="utf-8"))


if __name__ == "__main__":
    main()

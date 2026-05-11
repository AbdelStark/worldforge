"""Small custom evaluation suite built through WorldForge's public authoring API."""

from __future__ import annotations

from pathlib import Path

from worldforge import WorldForge
from worldforge.evaluation import EvaluationContext, EvaluationScenario, EvaluationSuite


def evaluate_empty_world(context: EvaluationContext):
    """Score whether the checkout-created world is readable and deterministic."""

    object_count = context.world.object_count
    return context.outcome(
        score=1.0,
        passed=object_count == 0,
        metrics={"object_count": object_count, "scenario": context.scenario.name},
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
            )
        ],
    )


def main() -> None:
    forge = WorldForge(state_dir=Path(".worldforge") / "custom-eval-worlds")
    report = build_suite().run_report("mock", forge=forge)
    print(report.to_markdown())


if __name__ == "__main__":
    main()

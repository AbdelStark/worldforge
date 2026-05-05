from __future__ import annotations

import json

from worldforge import WorldForge
from worldforge.evaluation import EvaluationSuite


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

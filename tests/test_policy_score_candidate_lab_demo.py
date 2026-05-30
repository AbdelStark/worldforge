import json
from pathlib import Path

from worldforge.demos.policy_score_candidate_lab import (
    CandidateLabConfig,
    candidate_lab_candidates,
    candidate_lab_expected_failures,
    candidate_lab_report,
    render_candidate_lab_markdown,
    run_policy_score_candidate_lab,
    run_policy_score_candidate_lab_workflow,
)


def test_candidate_lab_config_drives_candidates_and_failures() -> None:
    config = CandidateLabConfig(x_bounds=(0.2, 0.8), x_steps=4)

    candidates = candidate_lab_candidates(config)
    failures = candidate_lab_expected_failures(config)

    assert len(candidates) == 4
    assert candidates[0][0].parameters["target"]["x"] == 0.2
    assert candidates[-1][0].parameters["target"]["x"] == 0.8
    assert "lower bound" in failures["invalid_candidate_bounds"]
    assert "action_translator" in failures["missing_translator"]


def test_policy_score_candidate_lab_workflow_writes_attachable_artifacts(tmp_path: Path) -> None:
    summary = run_policy_score_candidate_lab_workflow(tmp_path)
    report = summary["report"]

    assert summary["status"] == "passed"
    assert summary["safe_to_attach"] is True
    assert report["planning_mode"] == "policy+score"
    assert report["selected_candidate_index"] == 1
    assert report["candidate_table"][1]["selected"] is True
    assert report["raw_policy_actions"]["raw_policy_action_preserved"] is True

    report_path = Path(str(summary["artifact_paths"]["lab_report"]))
    markdown_path = Path(str(summary["artifact_paths"]["lab_markdown"]))
    assert json.loads(report_path.read_text(encoding="utf-8")) == report
    markdown = markdown_path.read_text(encoding="utf-8")
    assert "| 1 | 0.18 | yes | 0.40 |" in markdown
    assert "Expected Failures" in markdown


def test_candidate_lab_score_config_changes_selected_action(tmp_path: Path) -> None:
    config = CandidateLabConfig(
        world_id="candidate-lab-custom-scores",
        scores=(0.2, 0.5, 0.1),
    )

    run = run_policy_score_candidate_lab(tmp_path, config=config)
    report = candidate_lab_report(run, candidate_lab_expected_failures(config))
    markdown = render_candidate_lab_markdown(report)

    assert report["selected_candidate_index"] == 2
    assert report["candidate_table"][2]["selected"] is True
    assert report["selected_action"]["parameters"]["target"]["x"] == 0.7
    assert "| 2 | 0.10 | yes | 0.70 |" in markdown

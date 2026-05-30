import json
from pathlib import Path

from worldforge.demos.capability_negotiation_preflight import (
    CAPABILITY_NEGOTIATION_WORKFLOWS,
    capability_negotiation_paths,
    capability_negotiation_report,
    capability_negotiation_reports,
    capability_readiness_values,
    run_capability_negotiation_preflight_workflow,
)


def test_capability_negotiation_paths_are_workspace_scoped(tmp_path: Path) -> None:
    paths = capability_negotiation_paths(tmp_path)

    assert paths.reports_dir == tmp_path / "capability-negotiation"
    assert paths.summary == tmp_path / "capability-negotiation-preflight.json"
    assert paths.preflight_markdown == tmp_path / "capability-negotiation/preflight-report.md"
    for path in (
        paths.summary,
        paths.preflight_json,
        paths.preflight_markdown,
        paths.not_registered_json,
    ):
        assert path.relative_to(tmp_path)


def test_capability_negotiation_reports_preserve_blocker_classes(tmp_path: Path) -> None:
    reports = capability_negotiation_reports(tmp_path)
    readiness_values = set(capability_readiness_values(reports))
    report = capability_negotiation_report(reports)

    assert {"ready", "missing-config", "missing-dependency", "not-registered"} <= readiness_values
    assert report["workflow_shapes"] == list(CAPABILITY_NEGOTIATION_WORKFLOWS)
    assert report["unsupported_example"]["readiness"] == "unsupported"
    assert report["recommended_actions"]


def test_capability_negotiation_workflow_writes_attachable_artifacts(tmp_path: Path) -> None:
    summary = run_capability_negotiation_preflight_workflow(tmp_path)
    report = summary["report"]

    assert summary["status"] == "passed"
    assert summary["safe_to_attach"] is True
    assert summary["claim_boundary"] == report["claim_boundary"]

    summary_path = Path(str(summary["artifact_paths"]["summary"]))
    preflight_json = Path(str(summary["artifact_paths"]["preflight_json"]))
    preflight_markdown = Path(str(summary["artifact_paths"]["preflight_markdown"]))
    not_registered_json = Path(str(summary["artifact_paths"]["not_registered_json"]))

    assert json.loads(summary_path.read_text(encoding="utf-8")) == report
    assert json.loads(preflight_json.read_text(encoding="utf-8"))["workflows"]
    assert json.loads(not_registered_json.read_text(encoding="utf-8"))["workflows"]
    markdown = preflight_markdown.read_text(encoding="utf-8")
    assert "# Capability Negotiation Report" in markdown
    assert "Recommended actions" in markdown

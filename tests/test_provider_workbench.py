from __future__ import annotations

import json
import sys

from worldforge.cli import main as worldforge_main
from worldforge.harness.workbench import provider_workbench_markdown, provider_workbench_report


def test_provider_workbench_runs_mock_in_clean_checkout() -> None:
    report = provider_workbench_report("mock")

    assert report["status"] == "passed"
    assert report["live"] is False
    assert report["required_tests"] == [
        "assert_predict_conformance",
        "assert_generate_conformance",
        "assert_transfer_conformance",
        "assert_reason_conformance",
        "assert_embed_conformance",
    ]
    checks = {check["name"]: check for check in report["checks"]}
    assert checks["health"]["status"] == "passed"
    assert checks["health"]["configured"] is True
    assert checks["conformance"]["status"] == "passed"
    assert "exercised predict" in checks["conformance"]["detail"]
    assert checks["events"]["status"] == "passed"
    assert report["docs"]["authoring_guide"] == "docs/src/provider-authoring-guide.md"
    assert (
        report["docs"]["catalog_check"] == "uv run python scripts/generate_provider_docs.py --check"
    )


def test_provider_workbench_skips_live_runway_but_validates_fixtures() -> None:
    report = provider_workbench_report("runway")

    assert report["status"] == "passed"
    assert report["required_tests"] == [
        "assert_generate_conformance",
        "assert_transfer_conformance",
    ]
    checks = {check["name"]: check for check in report["checks"]}
    assert checks["health"]["status"] == "passed"
    assert checks["health"]["configured"] is False
    assert checks["conformance"]["status"] == "skipped"
    assert "--live" in checks["conformance"]["detail"]
    assert checks["fixtures"]["status"] == "passed"
    assert checks["fixtures"]["paths"]


def test_provider_workbench_runs_scaffold_and_names_promotion_gaps() -> None:
    report = provider_workbench_report("genie")

    assert report["status"] == "passed"
    assert report["target_source"] == "provider_catalog"
    assert report["profile"]["implementation_status"] == "scaffold"
    checks = {check["name"]: check for check in report["checks"]}
    assert checks["runtime_manifest"]["status"] == "skipped"
    assert checks["fixtures"]["status"] == "skipped"
    assert report["promotion"]["missing_evidence_by_status"]["experimental"] == [
        "conformance_helpers",
        "fixture_coverage",
        "runtime_manifest",
    ]

    markdown = provider_workbench_markdown(report)
    assert "missing for `experimental`" in markdown
    assert "`runtime_manifest`" in markdown
    assert "## Validation Commands" in markdown
    assert "uv run mkdocs build --strict" in markdown


def test_provider_workbench_runs_direct_candidate_in_clean_checkout() -> None:
    report = provider_workbench_report("jepa-wms")

    assert report["status"] == "passed"
    assert report["target_source"] == "direct_construction_candidate"
    assert report["catalog_registered"] is False
    assert report["planned_capabilities"] == ["score"]
    checks = {check["name"]: check for check in report["checks"]}
    assert checks["runtime_manifest"]["status"] == "passed"
    assert checks["fixtures"]["status"] == "passed"
    assert "tests/fixtures/providers/jepa_wms_success.json" in checks["fixtures"]["paths"]
    assert report["promotion"]["missing_evidence_by_status"]["experimental"] == []
    assert report["promotion"]["missing_evidence_by_status"]["stable"] == [
        "prepared_host_smoke_artifact",
        "release_evidence",
    ]


def test_provider_workbench_markdown_is_issue_ready() -> None:
    markdown = provider_workbench_markdown(provider_workbench_report("mock"))

    assert markdown.startswith("# Provider Workbench: `mock`")
    assert "`passed` `conformance`" in markdown
    assert "generated catalog check" in markdown
    assert "Safe Artifacts" in markdown
    assert "Validation Commands" in markdown
    assert "Issue Summary" in markdown


def test_provider_workbench_cli_outputs_json(monkeypatch, capsys) -> None:
    monkeypatch.setattr(
        sys,
        "argv",
        ["worldforge", "provider", "workbench", "mock", "--format", "json"],
    )

    assert worldforge_main() == 0
    payload = json.loads(capsys.readouterr().out)

    assert payload["provider"] == "mock"
    assert payload["status"] == "passed"
    assert payload["validation_commands"]


def test_provider_workbench_cli_outputs_candidate_json(monkeypatch, capsys) -> None:
    monkeypatch.setattr(
        sys,
        "argv",
        ["worldforge", "provider", "workbench", "jepa-wms", "--format", "json"],
    )

    assert worldforge_main() == 0
    payload = json.loads(capsys.readouterr().out)

    assert payload["provider"] == "jepa-wms"
    assert payload["target_source"] == "direct_construction_candidate"
    assert payload["promotion"]["missing_evidence_by_status"]["experimental"] == []

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from worldforge.cli import main
from worldforge.operator_drills import (
    DRILL_IDS,
    list_operator_drills,
    render_operator_drills_markdown,
    run_all_operator_drills,
    run_operator_drill,
)

ROOT = Path(__file__).resolve().parents[1]


def test_operator_drill_catalog_documents_failure_and_recovery_commands() -> None:
    drills = list_operator_drills()

    assert tuple(drill["id"] for drill in drills) == DRILL_IDS
    assert len(drills) == 7
    for drill in drills:
        assert drill["checkout_safe"] is True
        assert drill["prepared_host"] is False
        assert drill["expected_failure"]
        assert drill["recovery_command"]
        assert drill["command"].endswith(
            f"worldforge drills run {drill['id']} --workspace-dir .worldforge/drills"
        )

    markdown = render_operator_drills_markdown(drills)
    assert "Operator Failure Drills" in markdown
    assert "missing-credentials" in markdown
    assert "unsafe-event-metadata" in markdown


@pytest.mark.parametrize("drill_id", DRILL_IDS)
def test_operator_drills_preserve_expected_failures_under_workspace(
    tmp_path: Path,
    drill_id: str,
) -> None:
    result = run_operator_drill(drill_id, workspace_dir=tmp_path)

    assert result["status"] == "passed"
    assert result["expected_failure_observed"] is True
    assert result["recovery_command"]
    assert tmp_path.resolve() in Path(result["run_workspace"]).resolve().parents

    manifest = json.loads(Path(result["run_manifest"]).read_text(encoding="utf-8"))
    assert manifest["kind"] == "operator_drill"
    assert manifest["status"] == "failed"
    assert manifest["operation"] == result["drill"]["failure_mode"]
    assert manifest["result_summary"]["drill_passed"] is True
    assert manifest["result_summary"]["expected_failure_observed"] is True
    assert manifest["artifact_paths"]["drill_json"] == "results/drill.json"
    assert (Path(result["run_workspace"]) / "results" / "drill.json").exists()
    assert (Path(result["run_workspace"]) / "reports" / "drill.md").exists()

    serialized = json.dumps(result, sort_keys=True)
    assert "drill-secret" not in serialized


def test_operator_drill_issue_bundle_exports_safe_manifest(tmp_path: Path) -> None:
    result = run_operator_drill("budget-violation", workspace_dir=tmp_path, bundle=True)

    bundle = result["issue_bundle"]
    assert bundle["safe_to_attach"] is True
    manifest = json.loads(Path(bundle["manifest_path"]).read_text(encoding="utf-8"))
    issue = Path(bundle["issue_template_path"]).read_text(encoding="utf-8")

    assert manifest["bundle_kind"] == "issue-run"
    assert manifest["safe_to_attach"] is True
    assert manifest["runs"][0]["status"] == "failed"
    assert manifest["runs"][0]["operation"] == "budget_violation"
    assert "benchmark budget violation" in manifest["runs"][0]["observed_failure"]
    assert "budget-violation" in issue
    assert "drill-secret" not in json.dumps(manifest, sort_keys=True)


def test_unsafe_event_metadata_drill_bundle_fails_closed(tmp_path: Path) -> None:
    result = run_operator_drill("unsafe-event-metadata", workspace_dir=tmp_path, bundle=True)

    bundle = result["issue_bundle"]
    manifest = json.loads(Path(bundle["manifest_path"]).read_text(encoding="utf-8"))

    assert bundle["safe_to_attach"] is False
    assert manifest["safe_to_attach"] is False
    assert manifest["excluded_count"] > 0
    assert any(file["reason"] == "secret-like material detected" for file in manifest["files"])
    assert "drill-secret" not in json.dumps(manifest, sort_keys=True)
    assert result["details"]["secret_leaked"] is False


def test_operator_drills_all_runs_every_checkout_safe_drill(tmp_path: Path) -> None:
    result = run_all_operator_drills(workspace_dir=tmp_path)

    assert result["status"] == "passed"
    assert result["run_count"] == len(DRILL_IDS)
    assert {run["drill"]["id"] for run in result["runs"]} == set(DRILL_IDS)
    assert len(list((tmp_path / "runs").glob("*/run_manifest.json"))) == len(DRILL_IDS)


def test_operator_drill_docs_cover_issue_152_contract() -> None:
    playbooks = (ROOT / "docs/src/playbooks.md").read_text(encoding="utf-8")
    operations = (ROOT / "docs/src/operations.md").read_text(encoding="utf-8")
    cli_docs = (ROOT / "docs/src/cli.md").read_text(encoding="utf-8")
    continuation = (ROOT / "docs/src/roadmap-continuation.md").read_text(encoding="utf-8")
    changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")

    for drill_id in DRILL_IDS:
        assert drill_id in playbooks
    for signal in (
        "worldforge drills list",
        "worldforge drills run unsafe-event-metadata",
        "expected failure",
        "recovery command",
        "temporary or documented workspace",
        "issue bundle",
    ):
        assert signal in playbooks or signal in operations or signal in cli_docs
    assert "operator failure drills" in changelog
    assert "- [x] Drill commands run in a clean checkout" in continuation
    assert "- [x] Unsafe metadata drills prove redaction gates fail closed" in continuation


def test_worldforge_drills_cli_lists_and_runs(tmp_path: Path, monkeypatch, capsys) -> None:
    monkeypatch.setattr(sys, "argv", ["worldforge", "drills", "list", "--format", "json"])
    assert main() == 0
    drills = json.loads(capsys.readouterr().out)
    assert [drill["id"] for drill in drills] == list(DRILL_IDS)

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "worldforge",
            "drills",
            "run",
            "missing-credentials",
            "--workspace-dir",
            str(tmp_path),
            "--format",
            "json",
        ],
    )
    assert main() == 0
    result = json.loads(capsys.readouterr().out)
    assert result["drill"]["id"] == "missing-credentials"
    assert Path(result["run_manifest"]).exists()

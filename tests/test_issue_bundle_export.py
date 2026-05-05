from __future__ import annotations

import json
import sys
from pathlib import Path

from worldforge.cli import main
from worldforge.evidence_bundle import generate_issue_bundle
from worldforge.harness.workspace import create_run_workspace, write_run_manifest


def _mock_run(workspace_dir: Path, *, run_id: str, status: str) -> None:
    workspace = create_run_workspace(
        workspace_dir,
        kind="eval",
        command=f"worldforge eval --suite planning --provider mock --status {status}",
        provider="mock",
        operation="planning",
        run_id=run_id,
        input_summary={"suite_id": "planning", "providers": ["mock"]},
    )
    workspace.write_json(
        "reports/report.json",
        {
            "suite_id": "planning",
            "provider_summaries": [{"provider": "mock", "status": status}],
            "run_metadata": {},
        },
    )
    workspace.write_json("results/result-summary.json", {"status": status, "provider": "mock"})
    workspace.write_text(
        "logs/provider-events.jsonl",
        '{"provider":"mock","operation":"planning","phase":"success","metadata":{}}',
    )
    result_summary = {
        "expected_signal": "planning evaluation writes a preserved report and run manifest",
    }
    if status == "failed":
        result_summary["validation_errors"] = ["score was below threshold"]
    if status == "skipped":
        result_summary["skip_reason"] = "fixture requested skip"
    if status == "cancelled":
        result_summary["failure_reason"] = "operator cancelled run"
    write_run_manifest(
        workspace,
        kind="eval",
        command=f"worldforge eval --suite planning --provider mock --status {status}",
        provider="mock",
        operation="planning",
        status=status,
        input_summary={"suite_id": "planning", "providers": ["mock"]},
        result_summary=result_summary,
        artifact_paths={
            "report": "reports/report.json",
            "result": "results/result-summary.json",
            "events": "logs/provider-events.jsonl",
        },
        event_count=1,
    )


def test_issue_bundle_exports_mock_run_statuses(tmp_path: Path) -> None:
    run_ids = {
        "passed": "20260101T000000Z-00000001",
        "failed": "20260102T000000Z-00000002",
        "skipped": "20260103T000000Z-00000003",
        "cancelled": "20260104T000000Z-00000004",
    }
    for status, run_id in run_ids.items():
        _mock_run(tmp_path, run_id=run_id, status=status)

    for status, run_id in run_ids.items():
        result = generate_issue_bundle(
            workspace_dir=tmp_path,
            run_id=run_id,
            output_dir=tmp_path / "issue-bundles" / status,
        )

        manifest = result.manifest
        assert manifest["bundle_kind"] == "issue-run"
        assert manifest["run_count"] == 1
        assert manifest["runs"][0]["run_id"] == run_id
        assert manifest["runs"][0]["status"] == status
        assert manifest["runs"][0]["expected_signal"].startswith("planning evaluation")
        assert manifest["safe_to_attach"] is True
        assert all(item["sha256"].startswith("sha256:") for item in manifest["files"])
        assert result.issue_template_path is not None
        issue = result.issue_template_path.read_text(encoding="utf-8")
        assert "### Command" in issue
        assert "### Expected Signal" in issue
        assert "### Observed Failure" in issue
        assert "### Safe-To-Attach Notes" in issue
        assert "### First Triage Step" in issue
        assert "safe_to_attach: `true`" in issue

    failed = json.loads(
        (tmp_path / "issue-bundles" / "failed" / "evidence_manifest.json").read_text(
            encoding="utf-8"
        )
    )
    assert failed["runs"][0]["validation_errors"] == ["score was below threshold"]
    assert "score was below threshold" in (
        tmp_path / "issue-bundles" / "failed" / "issue.md"
    ).read_text(encoding="utf-8")


def test_issue_bundle_marks_unsafe_metadata_local_only(tmp_path: Path) -> None:
    workspace = create_run_workspace(
        tmp_path,
        kind="eval",
        command="worldforge eval --suite planning --provider mock",
        provider="mock",
        operation="planning",
        run_id="20260105T000000Z-00000005",
        input_summary={"suite_id": "planning", "providers": ["mock"]},
    )
    workspace.write_text(
        "logs/provider-events.jsonl",
        '{"target":"https://example.test/artifact.json?token=secret"}',
    )
    local_path = tmp_path / "local-result.json"
    local_path.write_text("{}", encoding="utf-8")
    write_run_manifest(
        workspace,
        kind="eval",
        command="worldforge eval --suite planning --provider mock",
        provider="mock",
        operation="planning",
        status="failed",
        input_summary={"suite_id": "planning", "providers": ["mock"]},
        result_summary={"failure_reason": "provider event was unsafe"},
        artifact_paths={
            "events": "logs/provider-events.jsonl",
            "local": str(local_path),
            "linux_tmp": "/tmp/worldforge-local-result.json",
        },
    )

    result = generate_issue_bundle(
        workspace_dir=tmp_path,
        run_id="20260105T000000Z-00000005",
        output_dir=tmp_path / "issue-bundles" / "unsafe",
    )

    manifest = result.manifest
    assert manifest["safe_to_attach"] is False
    excluded = {item["path"]: item for item in manifest["files"] if not item["included"]}
    assert excluded["runs/20260105T000000Z-00000005/logs/provider-events.jsonl"]["reason"] in {
        "secret-like material detected",
        "signed or credentialed URL detected",
    }
    assert excluded["runs/20260105T000000Z-00000005/artifacts/local"]["local_only"] is True
    assert excluded["runs/20260105T000000Z-00000005/artifacts/linux_tmp"]["local_only"] is True
    assert str(tmp_path) not in json.dumps(manifest)
    assert "/tmp/worldforge-local-result.json" not in json.dumps(manifest)
    assert result.issue_template_path is not None
    assert (
        "Review `evidence_manifest.json` before attaching"
        in result.issue_template_path.read_text(encoding="utf-8")
    )


def test_runs_bundle_cli_prints_issue_template_and_json(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    run_id = "20260106T000000Z-00000006"
    _mock_run(tmp_path, run_id=run_id, status="failed")

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "worldforge",
            "runs",
            "bundle",
            run_id,
            "--workspace-dir",
            str(tmp_path),
            "--output",
            str(tmp_path / "bundle-md"),
        ],
    )
    assert main() == 0
    markdown = capsys.readouterr().out
    assert "## WorldForge Run Issue" in markdown
    assert "score was below threshold" in markdown
    assert (tmp_path / "bundle-md" / "issue.md").exists()

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "worldforge",
            "runs",
            "bundle",
            run_id,
            "--workspace-dir",
            str(tmp_path),
            "--output",
            str(tmp_path / "bundle-json"),
            "--format",
            "json",
        ],
    )
    assert main() == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["run_id"] == run_id
    assert payload["safe_to_attach"] is True
    assert payload["issue_template_path"].endswith("issue.md")

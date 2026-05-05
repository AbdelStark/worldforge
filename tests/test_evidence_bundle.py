from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

from worldforge.cli import main
from worldforge.evidence_bundle import generate_evidence_bundle
from worldforge.harness.workspace import create_run_workspace, write_run_manifest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "generate_release_evidence.py"
SPEC = importlib.util.spec_from_file_location("generate_release_evidence_for_bundle", SCRIPT)
assert SPEC is not None
generate_release_evidence = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules["generate_release_evidence_for_bundle"] = generate_release_evidence
SPEC.loader.exec_module(generate_release_evidence)
render_release_evidence = generate_release_evidence.render_release_evidence


def test_evidence_bundle_collects_mock_eval_and_benchmark_runs(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    workspace = tmp_path / "workspace"
    state_dir = tmp_path / "worlds"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "worldforge",
            "eval",
            "--suite",
            "planning",
            "--provider",
            "mock",
            "--state-dir",
            str(state_dir),
            "--run-workspace",
            str(workspace),
            "--format",
            "json",
        ],
    )
    assert main() == 0
    capsys.readouterr()

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "worldforge",
            "benchmark",
            "--preset",
            "mock-smoke",
            "--state-dir",
            str(state_dir),
            "--run-workspace",
            str(workspace),
            "--format",
            "json",
        ],
    )
    assert main() == 0
    capsys.readouterr()

    result = generate_evidence_bundle(
        workspace_dir=workspace,
        output_dir=tmp_path / "bundle",
    )

    manifest = result.manifest
    assert manifest["schema_version"] == 1
    assert manifest["run_count"] == 2
    assert manifest["safe_to_attach"] is True
    paths = {item["path"] for item in manifest["files"]}
    assert sum(path.endswith("run_manifest.json") for path in paths) == 2
    assert sum(path.endswith("reports/report.json") for path in paths) == 2
    assert "inputs/src/worldforge/benchmark_presets/_data/inputs-mock.json" in paths
    assert "budgets/src/worldforge/benchmark_presets/_data/budget-mock-smoke.json" in paths
    assert all(item["sha256"].startswith("sha256:") for item in manifest["files"])
    assert any(
        item["path"] == "src/worldforge/testing/fixtures/predict/valid_baseline.json"
        for item in manifest["fixture_digests"]
    )

    summary = result.summary_path.read_text(encoding="utf-8")
    assert "# WorldForge Evidence Bundle" in summary
    assert "Safe to attach: `true`" in summary
    assert "worldforge benchmark --preset mock-smoke" in summary


def test_evidence_bundle_marks_unsafe_and_local_only_artifacts(tmp_path: Path) -> None:
    workspace = create_run_workspace(
        tmp_path,
        kind="eval",
        command="worldforge eval --suite planning --provider mock",
        provider="mock",
        operation="planning",
        run_id="20260101T000000Z-00000001",
        input_summary={"suite_id": "planning", "providers": ["mock"]},
    )
    workspace.write_text(
        "logs/provider-events.jsonl",
        '{"target":"https://example.test/artifact.json?token=secret"}',
    )
    workspace.write_text("artifacts/video.mp4", "not really video")
    local_path = tmp_path / "local-only.json"
    local_path.write_text("{}", encoding="utf-8")
    write_run_manifest(
        workspace,
        kind="eval",
        command="worldforge eval --suite planning --provider mock",
        provider="mock",
        operation="planning",
        status="skipped",
        input_summary={"suite_id": "planning", "providers": ["mock"]},
        result_summary={"skip_reason": "fixture drill"},
        artifact_paths={
            "events": "logs/provider-events.jsonl",
            "video": "artifacts/video.mp4",
            "local": str(local_path),
            "escape": "../outside.json",
        },
    )

    result = generate_evidence_bundle(
        workspace_dir=tmp_path,
        output_dir=tmp_path / "bundle",
    )

    manifest = result.manifest
    assert manifest["safe_to_attach"] is False
    assert manifest["excluded_count"] >= 3
    excluded = {item["path"]: item for item in manifest["files"] if not item["included"]}
    assert excluded["runs/20260101T000000Z-00000001/logs/provider-events.jsonl"]["reason"] in {
        "secret-like material detected",
        "signed or credentialed URL detected",
    }
    assert (
        excluded["runs/20260101T000000Z-00000001/artifacts/video.mp4"]["reason"]
        == "unsupported artifact suffix '.mp4'"
    )
    assert excluded["runs/20260101T000000Z-00000001/artifacts/local"]["local_only"] is True
    assert excluded["runs/20260101T000000Z-00000001/artifacts/escape"]["local_only"] is True
    assert not (
        result.output_dir / "runs" / "20260101T000000Z-00000001" / "logs" / "provider-events.jsonl"
    ).exists()
    assert manifest["runs"][0]["skip_reason"] == "fixture drill"


def test_release_evidence_can_link_generated_bundle(tmp_path: Path) -> None:
    manifest_path = tmp_path / "bundle" / "evidence_manifest.json"
    manifest_path.parent.mkdir()
    manifest_path.write_text(
        json.dumps({"schema_version": 1, "safe_to_attach": True}) + "\n",
        encoding="utf-8",
    )

    report = render_release_evidence(
        output=tmp_path / "release-evidence.md",
        manifests=(),
        benchmark_artifacts=(),
        artifacts=(manifest_path,),
    )

    assert "evidence_manifest.json" in report
    assert "Preserved Release Artifacts" in report

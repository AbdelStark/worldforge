from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import worldforge.evidence_bundle as evidence_bundle
from worldforge.cli import main
from worldforge.evidence_bundle import (
    evidence_bundle_artifact,
    generate_evidence_bundle,
    generate_issue_bundle,
    issue_bundle_artifact,
)
from worldforge.harness.workspace import create_run_workspace, write_run_manifest
from worldforge.testing import DeterministicIdFactory, stable_json_dumps, stable_snapshot

ROOT = Path(__file__).resolve().parents[1]
DATASET_MANIFEST = ROOT / "examples/dataset-manifests/mock-evaluation-fixtures.json"
SCRIPT = ROOT / "scripts" / "generate_release_evidence.py"
SPEC = importlib.util.spec_from_file_location("generate_release_evidence_for_bundle", SCRIPT)
assert SPEC is not None
generate_release_evidence = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules["generate_release_evidence_for_bundle"] = generate_release_evidence
SPEC.loader.exec_module(generate_release_evidence)
render_release_evidence = generate_release_evidence.render_release_evidence
DEMO_SCRIPT = ROOT / "scripts" / "demo_showcases.py"
DEMO_SPEC = importlib.util.spec_from_file_location(
    "demo_showcases_for_evidence_review", DEMO_SCRIPT
)
assert DEMO_SPEC is not None
demo_showcases = importlib.util.module_from_spec(DEMO_SPEC)
assert DEMO_SPEC.loader is not None
sys.modules["demo_showcases_for_evidence_review"] = demo_showcases
DEMO_SPEC.loader.exec_module(demo_showcases)


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
            "--dataset-manifest",
            str(DATASET_MANIFEST.relative_to(ROOT)),
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
    assert "dataset-manifests/examples/dataset-manifests/mock-evaluation-fixtures.json" in paths
    assert all(item["sha256"].startswith("sha256:") for item in manifest["files"])
    assert any(
        item["path"] == "src/worldforge/testing/fixtures/predict/valid_baseline.json"
        for item in manifest["fixture_digests"]
    )

    summary = result.summary_path.read_text(encoding="utf-8")
    assert "# WorldForge Evidence Bundle" in summary
    assert "Safe to attach: `true`" in summary
    assert "worldforge benchmark --preset mock-smoke" in summary
    rendered = evidence_bundle_artifact(manifest, "html")
    assert rendered.media_type == "text/html"
    assert rendered.safe_to_attach is True
    assert rendered.content.startswith("<!DOCTYPE html>")


def test_evidence_bundle_resolves_checkout_references_from_installed_package_root(
    tmp_path: Path,
    monkeypatch,
) -> None:
    checkout_root = tmp_path / "checkout"
    package_root = tmp_path / "installed-package"
    fixture = checkout_root / "examples" / "dataset-manifests" / "mock.json"
    fixture.parent.mkdir(parents=True)
    package_root.mkdir()
    fixture.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(evidence_bundle, "_ROOT", package_root)
    monkeypatch.chdir(checkout_root)

    assert evidence_bundle._known_roots() == (package_root.resolve(), checkout_root.resolve())
    assert evidence_bundle._resolve_report_reference(fixture.as_posix()) == fixture
    assert (
        evidence_bundle._resolve_report_reference("examples/dataset-manifests/mock.json") == fixture
    )
    assert evidence_bundle._repo_relative(fixture) == Path("examples/dataset-manifests/mock.json")
    assert evidence_bundle._display_path(fixture) == "examples/dataset-manifests/mock.json"


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


def test_evidence_bundle_reports_missing_manifest_artifact_reference(tmp_path: Path) -> None:
    workspace = create_run_workspace(
        tmp_path,
        kind="eval",
        command="worldforge eval --suite planning --provider mock",
        provider="mock",
        operation="planning",
        run_id="20260101T000000Z-00000001",
        input_summary={"suite_id": "planning", "providers": ["mock"]},
    )
    write_run_manifest(
        workspace,
        kind="eval",
        command="worldforge eval --suite planning --provider mock",
        provider="mock",
        operation="planning",
        status="failed",
        input_summary={"suite_id": "planning", "providers": ["mock"]},
        result_summary={"failed_count": 1},
        artifact_paths={"missing": "artifacts/missing.json"},
    )

    result = generate_evidence_bundle(
        workspace_dir=tmp_path,
        output_dir=tmp_path / "bundle",
    )

    manifest = result.manifest
    excluded = {item["path"]: item for item in manifest["files"] if not item["included"]}
    missing = excluded["runs/20260101T000000Z-00000001/artifacts/missing"]
    assert missing["reason"] == "artifact reference does not exist"
    assert missing["local_only"] is True
    assert manifest["safe_to_attach"] is False


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


def test_non_developer_evidence_review_demo_escapes_and_marks_local_only(
    tmp_path: Path,
) -> None:
    results = demo_showcases.run_workflows(
        "non-developer-evidence-review",
        workspace_dir=tmp_path,
        overwrite=True,
    )
    summary = json.loads(Path(results[0]["artifact_paths"]["summary_json"]).read_text())
    report = summary["report"]
    html = Path(summary["artifact_paths"]["review_html"]).read_text(encoding="utf-8")

    assert summary["safe_to_attach"] is True
    assert report["safe_to_attach"] is True
    assert report["local_only_count"] >= 1
    assert any(item["share_policy"] == "local-only" for item in report["artifacts"])
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in html
    assert "<script" not in html
    assert '<a href="evaluation-report.json">' in html
    assert '<a href="&lt;host-local:provider-events.jsonl&gt;">' not in html
    assert "Unsupported claims: model quality" in html


def test_issue_bundle_uses_deterministic_controls_for_exact_snapshot(tmp_path: Path) -> None:
    ids = DeterministicIdFactory()
    run_id = ids.run_id()
    workspace = create_run_workspace(
        tmp_path,
        kind="eval",
        command="worldforge eval --suite planning --provider mock",
        provider="mock",
        operation="planning",
        run_id=run_id,
        input_summary={"suite_id": "planning", "providers": ["mock"]},
    )
    workspace.write_json(
        "reports/report.json",
        {"suite_id": "planning", "results": [], "claim_boundary": "fixture-only"},
    )
    write_run_manifest(
        workspace,
        kind="eval",
        command="worldforge eval --suite planning --provider mock",
        provider="mock",
        operation="planning",
        status="failed",
        input_summary={"suite_id": "planning", "providers": ["mock"]},
        result_summary={"result_count": 0, "failed_count": 1},
        artifact_paths={"json": "reports/report.json"},
    )

    result = generate_issue_bundle(
        workspace_dir=tmp_path,
        run_id=run_id,
        output_dir=tmp_path / "issue-bundle",
        generated_at="2026-01-01T00:00:00+00:00",
    )
    snapshot = stable_snapshot(result.manifest, path_roots={tmp_path: "<tmp>"})
    digest_fields = {
        item["path"]: item["sha256"] for item in snapshot["files"] if item.get("sha256")
    }

    assert str(tmp_path) not in stable_json_dumps(snapshot)
    assert snapshot["generated_at"] == "2026-01-01T00:00:00+00:00"
    assert snapshot["bundle_kind"] == "issue-run"
    assert snapshot["runs"][0]["run_id"] == "20260101T000000Z-00000001"
    assert snapshot["runs"][0]["source_path"] == "<host-local:20260101T000000Z-00000001>"
    assert snapshot["safe_to_attach"] is True
    issue_rendered = issue_bundle_artifact(result.manifest, "markdown")
    assert issue_rendered.safe_to_attach is True
    assert "WorldForge Run Issue" in issue_rendered.content
    assert set(digest_fields) == {
        "runs/20260101T000000Z-00000001/reports/report.json",
        "runs/20260101T000000Z-00000001/run_manifest.json",
    }

from __future__ import annotations

import importlib.util
import json
import math
import sys
from pathlib import Path

import pytest

import worldforge.evidence_bundle as evidence_bundle
from worldforge import WorldForgeError
from worldforge.cli import main
from worldforge.demos.evidence_review import run_non_developer_evidence_review_workflow
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


def test_evidence_bundle_file_helpers_preserve_facade_imports() -> None:
    from worldforge import evidence_bundle_files

    assert evidence_bundle.MAX_SAFE_ARTIFACT_BYTES == (
        evidence_bundle_files.MAX_SAFE_ARTIFACT_BYTES
    )
    assert evidence_bundle._BundleContext is evidence_bundle_files._BundleContext
    assert evidence_bundle._copy_report_references is (
        evidence_bundle_files._copy_report_references
    )
    assert evidence_bundle._load_run_manifest is evidence_bundle_files._load_run_manifest


def test_evidence_bundle_manifest_writer_rejects_non_finite_before_touching_disk(
    tmp_path: Path,
) -> None:
    output_dir = tmp_path / "bundle"
    manifest = {
        "schema_version": 1,
        "generated_at": "2026-01-01T00:00:00+00:00",
        "source_workspace": "workspace",
        "run_count": 0,
        "runs": [],
        "files": [],
        "fixture_digests": [],
        "included_count": 0,
        "excluded_count": 0,
        "safe_to_attach": True,
        "bad_metric": math.nan,
    }

    with pytest.raises(WorldForgeError, match="finite numbers"):
        evidence_bundle._write_evidence_bundle_outputs(output_dir, manifest)

    assert not output_dir.exists()


def test_evidence_bundle_rejects_non_finite_run_manifest(tmp_path: Path) -> None:
    runs = tmp_path / "runs"
    runs.mkdir()
    run_dir = runs / "20260101T000000Z-00000001"
    run_dir.mkdir()
    (run_dir / "run_manifest.json").write_text(
        '{"schema_version": 1, "run_id": "20260101T000000Z-00000001", '
        '"kind": "eval", "status": "failed", "latency_ms": NaN}\n',
        encoding="utf-8",
    )

    with pytest.raises(WorldForgeError, match="finite number"):
        generate_evidence_bundle(
            workspace_dir=tmp_path,
            output_dir=tmp_path / "bundle",
        )

    assert not (tmp_path / "bundle" / "evidence_manifest.json").exists()


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


def test_evidence_bundle_rejects_absolute_report_reference_outside_known_roots(
    tmp_path: Path,
    monkeypatch,
) -> None:
    checkout_root = tmp_path / "checkout"
    package_root = tmp_path / "installed-package"
    outside = tmp_path / "outside" / "host-only.json"
    checkout_root.mkdir()
    package_root.mkdir()
    outside.parent.mkdir()
    outside.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(evidence_bundle, "_ROOT", package_root)
    monkeypatch.chdir(checkout_root)

    assert evidence_bundle._resolve_report_reference(outside.as_posix()) is None


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


def test_observed_failure_uses_structured_reason_precedence() -> None:
    manifest = {
        "status": "failed",
        "result_summary": {
            "message": "structured failure",
            "validation_errors": ["secondary validation failure"],
        },
    }

    assert evidence_bundle._observed_failure(manifest) == "structured failure"


def test_observed_failure_falls_back_to_validation_and_status_defaults() -> None:
    assert (
        evidence_bundle._observed_failure(
            {
                "status": "failed",
                "result_summary": {"validation_errors": ["bad score", "bad artifact"]},
            }
        )
        == "bad score; bad artifact"
    )
    assert (
        evidence_bundle._observed_failure(
            {
                "status": "skipped",
                "input_summary": {"reason": "host runtime unavailable"},
            }
        )
        == "host runtime unavailable"
    )
    assert (
        evidence_bundle._observed_failure({"status": "passed", "result_summary": []})
        == "No failure recorded; bundle captures a successful preserved run."
    )
    assert (
        evidence_bundle._observed_failure({"status": "unknown-new"}) == "Run status is unknown-new."
    )


def test_evidence_bundle_rejects_traversal_run_id(tmp_path: Path) -> None:
    (tmp_path / "runs").mkdir()
    escaped = tmp_path / "escape"
    escaped.mkdir()
    (escaped / "run_manifest.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "run_id": "20260101T000000Z-00000001",
                "kind": "eval",
                "command": "worldforge eval",
                "status": "passed",
                "artifact_paths": {},
            }
        )
        + "\n",
        encoding="utf-8",
    )

    with pytest.raises(WorldForgeError, match="run_id"):
        generate_evidence_bundle(
            workspace_dir=tmp_path,
            output_dir=tmp_path / "bundle",
            run_ids=("../escape",),
        )


def test_evidence_bundle_excludes_run_workspace_symlink_escape(tmp_path: Path) -> None:
    workspace = create_run_workspace(
        tmp_path,
        kind="eval",
        command="worldforge eval --suite planning --provider mock",
        provider="mock",
        operation="planning",
        run_id="20260101T000000Z-00000001",
        input_summary={"suite_id": "planning", "providers": ["mock"]},
    )
    external = tmp_path / "outside.json"
    external.write_text('{"safe": true}\n', encoding="utf-8")
    symlink_path = workspace.path / "reports" / "external.json"
    symlink_path.symlink_to(external)
    write_run_manifest(
        workspace,
        kind="eval",
        command="worldforge eval --suite planning --provider mock",
        provider="mock",
        operation="planning",
        status="failed",
        input_summary={"suite_id": "planning", "providers": ["mock"]},
        result_summary={"failed_count": 1},
        artifact_paths={"json": "reports/external.json"},
    )

    result = generate_evidence_bundle(
        workspace_dir=tmp_path,
        output_dir=tmp_path / "bundle",
    )

    manifest = result.manifest
    excluded = {item["path"]: item for item in manifest["files"] if not item["included"]}
    escaped = excluded["runs/20260101T000000Z-00000001/reports/external.json"]
    assert escaped["reason"] == "run artifact resolves outside the run workspace"
    assert escaped["local_only"] is True
    assert manifest["safe_to_attach"] is False
    assert not (
        result.output_dir / "runs" / "20260101T000000Z-00000001" / "reports" / "external.json"
    ).exists()


def test_evidence_bundle_detects_signed_url_sig_query(tmp_path: Path) -> None:
    workspace = create_run_workspace(
        tmp_path,
        kind="eval",
        command="worldforge eval --suite planning --provider mock",
        provider="mock",
        operation="planning",
        run_id="20260101T000000Z-00000001",
        input_summary={"suite_id": "planning", "providers": ["mock"]},
    )
    workspace.write_json(
        "reports/report.json",
        {"artifact": "https://assets.example.test/output.json?sig=credential"},
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
        artifact_paths={"json": "reports/report.json"},
    )

    result = generate_evidence_bundle(
        workspace_dir=tmp_path,
        output_dir=tmp_path / "bundle",
    )

    manifest = result.manifest
    excluded = {item["path"]: item for item in manifest["files"] if not item["included"]}
    report = excluded["runs/20260101T000000Z-00000001/reports/report.json"]
    assert report["reason"] == "signed or credentialed URL detected"
    assert manifest["safe_to_attach"] is False


def test_evidence_bundle_excludes_non_finite_json_artifact(tmp_path: Path) -> None:
    workspace = create_run_workspace(
        tmp_path,
        kind="eval",
        command="worldforge eval --suite planning --provider mock",
        provider="mock",
        operation="planning",
        run_id="20260101T000000Z-00000001",
        input_summary={"suite_id": "planning", "providers": ["mock"]},
    )
    report_path = workspace.path / "reports" / "report.json"
    report_path.write_text('{"suite_id": "planning", "score": NaN}\n', encoding="utf-8")
    write_run_manifest(
        workspace,
        kind="eval",
        command="worldforge eval --suite planning --provider mock",
        provider="mock",
        operation="planning",
        status="failed",
        input_summary={"suite_id": "planning", "providers": ["mock"]},
        result_summary={"failed_count": 1},
        artifact_paths={"json": "reports/report.json"},
    )

    result = generate_evidence_bundle(
        workspace_dir=tmp_path,
        output_dir=tmp_path / "bundle",
    )

    excluded = {item["path"]: item for item in result.manifest["files"] if not item["included"]}
    report = excluded["runs/20260101T000000Z-00000001/reports/report.json"]
    assert report["reason"] == "JSON artifact must contain only finite JSON values"
    assert result.manifest["safe_to_attach"] is False
    assert not (
        result.output_dir / "runs" / "20260101T000000Z-00000001" / "reports" / "report.json"
    ).exists()


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
    summary = run_non_developer_evidence_review_workflow(tmp_path)
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


def test_issue_bundle_rejects_non_finite_manifest_before_overwriting_base_bundle(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run_id = DeterministicIdFactory().run_id()
    workspace = create_run_workspace(
        tmp_path,
        kind="eval",
        command="worldforge eval --suite planning --provider mock",
        provider="mock",
        operation="planning",
        run_id=run_id,
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
        artifact_paths={},
    )
    output_dir = tmp_path / "issue-bundle"
    monkeypatch.setattr(evidence_bundle, "_first_triage_step", lambda _manifest: math.nan)

    with pytest.raises(WorldForgeError, match="finite numbers"):
        generate_issue_bundle(
            workspace_dir=tmp_path,
            run_id=run_id,
            output_dir=output_dir,
            generated_at="2026-01-01T00:00:00+00:00",
        )

    manifest_path = output_dir / "evidence_manifest.json"
    assert "bundle_kind" not in json.loads(manifest_path.read_text(encoding="utf-8"))
    assert not (output_dir / "issue.md").exists()

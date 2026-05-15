from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from worldforge import BBox, Position, SceneObject, World, WorldForge
from worldforge.cli import main
from worldforge.harness.workspace import create_run_workspace, write_run_manifest
from worldforge.models import WorldForgeError
from worldforge.persistence_preflight import (
    _artifact_recovery_command,
    _check_world_bounding_boxes,
    _display_path,
    _sanitize_message,
    _unsafe_artifact_reason,
    _world_state_failure_check,
    preflight_local_state,
    render_state_preflight_markdown,
)


def test_local_state_preflight_passes_for_valid_world_and_run_workspace(tmp_path) -> None:
    state_dir = tmp_path / "worlds"
    workspace_dir = tmp_path / "workspace"
    forge = WorldForge(state_dir=state_dir)
    world = forge.create_world("preflight-ok", provider="mock")
    world.add_object(
        SceneObject(
            "cube",
            Position(0.0, 0.5, 0.0),
            BBox(Position(-0.05, 0.45, -0.05), Position(0.05, 0.55, 0.05)),
            id="cube-1",
        )
    )
    forge.save_world(world)
    run = create_run_workspace(
        workspace_dir,
        kind="eval",
        command="worldforge eval",
        run_id="20260102T000000Z-00000002",
    )
    run.write_json("reports/report.json", {"status": "ok"})
    write_run_manifest(
        run,
        kind="eval",
        command="worldforge eval",
        status="completed",
        provider="mock",
        operation="planning",
        artifact_paths={"json": "reports/report.json"},
    )

    report = preflight_local_state(state_dir=state_dir, workspace_dir=workspace_dir)

    assert report["status"] == "passed"
    assert report["safe_to_attach"] is True
    assert report["counts"]["world_files_checked"] == 1
    assert report["counts"]["run_workspaces_checked"] == 1
    assert report["issues"] == []
    assert str(tmp_path) not in json.dumps(report)


def test_local_state_preflight_reports_corrupt_history_and_bbox_issues(tmp_path) -> None:
    state_dir = tmp_path / "worlds"
    workspace_dir = tmp_path / "workspace"
    forge = WorldForge(state_dir=state_dir)

    valid = World("bbox", provider="mock", forge=forge, world_id="bbox-world")
    valid.add_object(
        SceneObject(
            "cube",
            Position(0.0, 0.5, 0.0),
            BBox(Position(-0.05, 0.45, -0.05), Position(0.05, 0.55, 0.05)),
            id="cube-1",
        )
    )
    forge.save_world(valid)
    bbox_payload = json.loads((state_dir / "bbox-world.json").read_text(encoding="utf-8"))
    bbox_payload["scene"]["objects"]["cube-1"]["bbox"] = {
        "min": {"x": 10.0, "y": 10.0, "z": 10.0},
        "max": {"x": 11.0, "y": 11.0, "z": 11.0},
    }
    (state_dir / "bbox-world.json").write_text(json.dumps(bbox_payload), encoding="utf-8")

    bad_history = World("bad-history", provider="mock", forge=forge, world_id="bad-history")
    forge.save_world(bad_history)
    history_payload = json.loads((state_dir / "bad-history.json").read_text(encoding="utf-8"))
    history_payload["history"][0]["summary"] = ""
    (state_dir / "bad-history.json").write_text(json.dumps(history_payload), encoding="utf-8")
    (state_dir / "broken.json").write_text("{not valid json", encoding="utf-8")

    report = preflight_local_state(state_dir=state_dir, workspace_dir=workspace_dir)

    checks = {issue["check"] for issue in report["issues"]}
    assert report["status"] == "failed"
    assert {"bbox-incoherent", "invalid-world-history", "corrupted-world-json"} <= checks
    assert all(issue["safe_to_attach"] is True for issue in report["issues"])
    assert all("rm " not in issue["recovery_command"] for issue in report["issues"])
    assert any("preflight" in issue["recovery_command"] for issue in report["issues"])
    assert str(tmp_path) not in json.dumps(report)


def test_local_state_preflight_reports_requested_traversal_world_id(tmp_path) -> None:
    report = preflight_local_state(
        state_dir=tmp_path / "worlds",
        workspace_dir=tmp_path / "workspace",
        world_ids=("../outside",),
    )

    assert report["status"] == "failed"
    issue = report["issues"][0]
    assert issue["check"] == "unsafe-world-id"
    assert "traversal-shaped" in issue["message"]
    assert "../outside" not in json.dumps(report)


def test_local_state_preflight_reports_invalid_storage_and_manifest_shapes(tmp_path) -> None:
    blocking_state_dir = tmp_path / "blocking-worlds"
    blocking_state_dir.write_text("not a directory", encoding="utf-8")
    blocking_workspace = tmp_path / "blocking-workspace"
    blocking_workspace.mkdir()
    (blocking_workspace / "runs").write_text("not a directory", encoding="utf-8")

    blocking_report = preflight_local_state(
        state_dir=blocking_state_dir,
        workspace_dir=blocking_workspace,
    )

    blocking_checks = {issue["check"] for issue in blocking_report["issues"]}
    assert {"state-dir-invalid", "runs-dir-invalid"} <= blocking_checks

    state_dir = tmp_path / "worlds"
    workspace_dir = tmp_path / "workspace"
    state_dir.mkdir()
    forge = WorldForge(state_dir=state_dir)
    mismatched = World("mismatch", provider="mock", forge=forge, world_id="payload-id")
    forge.save_world(mismatched)
    (state_dir / "payload-id.json").rename(state_dir / "file-id.json")
    (state_dir / "array.json").write_text("[]", encoding="utf-8")
    (state_dir / "bad?name.json").write_text("{}", encoding="utf-8")

    runs_root = workspace_dir / "runs"
    runs_root.mkdir(parents=True)
    (runs_root / "loose-entry").write_text("ignored", encoding="utf-8")
    invalid_name = runs_root / "not-a-run-id"
    invalid_name.mkdir()
    (invalid_name / "run_manifest.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "run_id": "not-a-run-id",
                "status": "completed",
                "artifact_paths": {},
            }
        ),
        encoding="utf-8",
    )
    bad_json = runs_root / "20260104T000000Z-00000004"
    bad_json.mkdir()
    (bad_json / "run_manifest.json").write_text("{bad", encoding="utf-8")
    non_object = runs_root / "20260105T000000Z-00000005"
    non_object.mkdir()
    (non_object / "run_manifest.json").write_text("[]", encoding="utf-8")
    mismatched_manifest = runs_root / "20260106T000000Z-00000006"
    mismatched_manifest.mkdir()
    (mismatched_manifest / "run_manifest.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "run_id": "20260107T000000Z-00000007",
                "status": "completed",
                "artifact_paths": {},
            }
        ),
        encoding="utf-8",
    )
    bad_fields = runs_root / "20260108T000000Z-00000008"
    bad_fields.mkdir()
    (bad_fields / "run_manifest.json").write_text(
        json.dumps(
            {
                "schema_version": 2,
                "run_id": "20260108T000000Z-00000008",
                "status": "unknown",
                "artifact_paths": [],
            }
        ),
        encoding="utf-8",
    )

    report = preflight_local_state(state_dir=state_dir, workspace_dir=workspace_dir)

    checks = [issue["check"] for issue in report["issues"]]
    assert report["status"] == "failed"
    assert "world-id-mismatch" in checks
    assert "unsafe-world-file-id" in checks
    assert "corrupted-world-json" in checks
    assert "stale-run-workspace" in checks
    assert checks.count("invalid-run-manifest") >= 6
    assert str(tmp_path) not in json.dumps(report)


def test_local_state_preflight_helper_boundaries_are_sanitized(tmp_path) -> None:
    with pytest.raises(WorldForgeError, match="retention_keep"):
        preflight_local_state(
            state_dir=tmp_path / "worlds",
            workspace_dir=tmp_path / "workspace",
            retention_keep=-1,
        )

    run_path = tmp_path / "workspace" / "runs" / "20260109T000000Z-00000009"
    run_path.mkdir(parents=True)
    outside = tmp_path / "outside.json"
    assert _unsafe_artifact_reason("", run_path=run_path) == (
        "reference is not a non-empty relative path"
    )
    assert _unsafe_artifact_reason("artifact.json?token=secret", run_path=run_path) == (
        "reference contains secret-like or signed URL material"
    )
    assert _unsafe_artifact_reason(str(outside), run_path=run_path) == (
        "reference is an absolute host path"
    )
    assert _unsafe_artifact_reason("../outside.json", run_path=run_path) == (
        "reference contains traversal"
    )
    outside.write_text("{}", encoding="utf-8")
    (run_path / "linked-outside.json").symlink_to(outside)
    assert _unsafe_artifact_reason("linked-outside.json", run_path=run_path) == (
        "reference escapes the run workspace"
    )
    assert _unsafe_artifact_reason("reports/report.json", run_path=run_path) is None

    assert _world_state_failure_check("scene object bbox mismatch") == "invalid-world-object"
    assert _world_state_failure_check("unstructured failure") == "invalid-world-state"
    assert "regenerate the run manifest" in _artifact_recovery_command(None)
    sanitized = _sanitize_message(
        f"{tmp_path}/worlds.json contains token=secret",
        roots=((tmp_path, "tmp"),),
    )
    assert "<tmp>" in sanitized
    assert "token" not in sanitized
    assert _display_path(Path("/tmp/outside.json"), tmp_path / "workspace", "workspace-dir") == (
        "<workspace-dir>/outside.json"
    )
    assert _display_path(tmp_path / "workspace", tmp_path / "workspace", "workspace-dir") == (
        "<workspace-dir>"
    )
    cyclic_state = {
        "id": "cyclic",
        "scene": {
            "objects": {
                "raw": "not an object",
                "invalid": {
                    "id": "invalid",
                    "name": "invalid",
                    "position": [],
                    "bbox": {"min": {"x": 0, "y": 0, "z": 0}, "max": {"x": 1, "y": 1, "z": 1}},
                },
            }
        },
        "history": [],
    }
    cyclic_state["history"].append({"state": cyclic_state})
    issues = []
    _check_world_bounding_boxes(
        cyclic_state,
        world_file=tmp_path / "worlds" / "cyclic.json",
        state_dir=tmp_path / "worlds",
        issues=issues,
    )
    assert issues == []

    markdown = render_state_preflight_markdown(
        {
            "status": "warning",
            "safe_to_attach": True,
            "counts": {
                "error_count": 0,
                "warning_count": 1,
                "world_files_checked": 0,
                "run_workspaces_checked": 0,
            },
            "issues": [
                "ignored",
                {
                    "severity": "warning",
                    "check": "pipe",
                    "path": "a|b",
                    "message": "line\nbreak",
                    "recovery_command": "cmd|safe",
                },
            ],
        }
    )
    assert "a\\|b" in markdown
    assert "line break" in markdown


def test_local_state_preflight_reports_stale_runs_unsafe_artifacts_and_retention(tmp_path) -> None:
    state_dir = tmp_path / "worlds"
    workspace_dir = tmp_path / "workspace"
    state_dir.mkdir()
    stale_run = workspace_dir / "runs" / "20260101T000000Z-00000001"
    stale_run.mkdir(parents=True)

    unsafe_run = create_run_workspace(
        workspace_dir,
        kind="benchmark",
        command="worldforge benchmark",
        run_id="20260102T000000Z-00000002",
    )
    write_run_manifest(
        unsafe_run,
        kind="benchmark",
        command="worldforge benchmark",
        status="failed",
        provider="mock",
        operation="predict",
        artifact_paths={"signed_url": "https://example.test/video.mp4?X-Amz-Signature=secret"},
    )
    valid_run = create_run_workspace(
        workspace_dir,
        kind="eval",
        command="worldforge eval",
        run_id="20260103T000000Z-00000003",
    )
    write_run_manifest(
        valid_run,
        kind="eval",
        command="worldforge eval",
        status="completed",
        provider="mock",
        operation="planning",
        artifact_paths={"json": "reports/report.json"},
    )

    report = preflight_local_state(
        state_dir=state_dir,
        workspace_dir=workspace_dir,
        retention_keep=1,
    )

    checks = [issue["check"] for issue in report["issues"]]
    assert report["status"] == "failed"
    assert "stale-run-workspace" in checks
    assert "unsafe-artifact-path" in checks
    assert "retention-pressure" in checks
    assert "X-Amz-Signature" not in json.dumps(report)
    retention = next(issue for issue in report["issues"] if issue["check"] == "retention-pressure")
    assert "--dry-run" in retention["recovery_command"]
    unsafe = next(issue for issue in report["issues"] if issue["check"] == "unsafe-artifact-path")
    assert "worldforge runs bundle 20260102T000000Z-00000002" in unsafe["recovery_command"]


def test_world_preflight_cli_does_not_create_missing_state_dir(
    tmp_path,
    monkeypatch,
    capsys,
) -> None:
    state_dir = tmp_path / "missing" / "worlds"
    workspace_dir = tmp_path / "workspace"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "worldforge",
            "world",
            "preflight",
            "--state-dir",
            str(state_dir),
            "--workspace-dir",
            str(workspace_dir),
            "--format",
            "json",
        ],
    )

    assert main() == 0
    report = json.loads(capsys.readouterr().out)
    assert report["status"] == "warning"
    assert report["issues"][0]["check"] == "state-dir-missing"
    assert not state_dir.exists()


def test_world_preflight_cli_reports_failure_and_markdown(tmp_path, monkeypatch, capsys) -> None:
    state_dir = tmp_path / "worlds"
    workspace_dir = tmp_path / "workspace"
    state_dir.mkdir()
    (state_dir / "broken.json").write_text("{bad", encoding="utf-8")
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "worldforge",
            "world",
            "preflight",
            "--state-dir",
            str(state_dir),
            "--workspace-dir",
            str(workspace_dir),
            "--world-id",
            "../outside",
            "--format",
            "markdown",
        ],
    )

    assert main() == 1
    output = capsys.readouterr().out
    assert "# WorldForge Local State Preflight" in output
    assert "unsafe-world-id" in output
    assert "corrupted-world-json" in output
    assert str(tmp_path) not in output


def test_state_preflight_markdown_includes_recovery_table() -> None:
    report = {
        "status": "passed",
        "safe_to_attach": True,
        "counts": {
            "error_count": 0,
            "warning_count": 0,
            "world_files_checked": 0,
            "run_workspaces_checked": 0,
        },
        "issues": [],
    }

    rendered = render_state_preflight_markdown(report)

    assert rendered.startswith("# WorldForge Local State Preflight")
    assert "Diagnostic command:" in rendered

from __future__ import annotations

import json
import sys

from worldforge import BBox, Position, SceneObject, World, WorldForge
from worldforge.cli import main
from worldforge.harness.workspace import create_run_workspace, write_run_manifest
from worldforge.persistence_preflight import preflight_local_state, render_state_preflight_markdown


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

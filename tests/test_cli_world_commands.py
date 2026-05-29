from __future__ import annotations

import json
import sys

import pytest

from worldforge.cli import main


def _run_world_cli(tmp_path, monkeypatch, capsys, *args: str) -> str:
    monkeypatch.setattr(
        sys,
        "argv",
        ["worldforge", "world", *args, "--state-dir", str(tmp_path)],
    )
    assert main() == 0
    return capsys.readouterr().out


def test_world_cli_edits_persisted_scene_objects(tmp_path, monkeypatch, capsys) -> None:
    created = json.loads(_run_world_cli(tmp_path, monkeypatch, capsys, "create", "lab"))
    world_id = created["id"]

    added = json.loads(
        _run_world_cli(
            tmp_path,
            monkeypatch,
            capsys,
            "add-object",
            world_id,
            "red_mug",
            "--x",
            "0.0",
            "--y",
            "0.8",
            "--z",
            "0.0",
            "--object-id",
            "mug-1",
            "--size",
            "0.2",
            "--graspable",
            "--metadata",
            '{"material": "ceramic"}',
        )
    )
    assert added["object"]["id"] == "mug-1"
    assert added["object"]["is_graspable"] is True
    assert added["object"]["metadata"] == {"material": "ceramic"}
    assert added["object"]["bbox"]["min"]["x"] == pytest.approx(-0.1)
    assert added["object"]["bbox"]["min"]["y"] == pytest.approx(0.7)
    assert added["object"]["bbox"]["min"]["z"] == pytest.approx(-0.1)
    assert added["world"]["object_count"] == 1

    objects = json.loads(_run_world_cli(tmp_path, monkeypatch, capsys, "objects", world_id))
    assert [obj["id"] for obj in objects["objects"]] == ["mug-1"]

    updated = json.loads(
        _run_world_cli(
            tmp_path,
            monkeypatch,
            capsys,
            "update-object",
            world_id,
            "mug-1",
            "--name",
            "coffee_mug",
            "--x",
            "0.25",
            "--y",
            "0.8",
            "--z",
            "0.05",
            "--graspable",
            "false",
        )
    )
    assert updated["object"]["name"] == "coffee_mug"
    assert updated["object"]["position"] == {"x": 0.25, "y": 0.8, "z": 0.05}
    assert updated["object"]["is_graspable"] is False
    assert updated["object"]["bbox"]["min"]["x"] == pytest.approx(0.15)
    assert updated["object"]["bbox"]["max"]["x"] == pytest.approx(0.35)
    assert updated["object"]["bbox"]["min"]["z"] == pytest.approx(-0.05)
    assert updated["object"]["bbox"]["max"]["z"] == pytest.approx(0.15)

    removed = json.loads(
        _run_world_cli(tmp_path, monkeypatch, capsys, "remove-object", world_id, "mug-1")
    )
    assert removed["removed_object"]["id"] == "mug-1"
    assert removed["world"]["object_count"] == 0

    history = json.loads(_run_world_cli(tmp_path, monkeypatch, capsys, "history", world_id))
    assert [entry["summary"] for entry in history["history"]] == [
        "world initialized",
        "added object mug-1",
        "updated object mug-1",
        "removed object mug-1",
    ]
    assert history["history"][1]["action"]["type"] == "add_object"
    assert history["history"][2]["action"]["type"] == "update_object"
    assert history["history"][2]["object_count"] == 1
    assert history["history"][3]["action"]["type"] == "remove_object"
    assert history["history"][3]["object_count"] == 0


def test_world_cli_deletes_persisted_world(tmp_path, monkeypatch, capsys) -> None:
    created = json.loads(_run_world_cli(tmp_path, monkeypatch, capsys, "create", "lab"))
    world_id = created["id"]

    deleted = json.loads(_run_world_cli(tmp_path, monkeypatch, capsys, "delete", world_id))
    assert deleted["world_id"] == world_id
    assert deleted["deleted"] is True
    assert deleted["state_dir"] == str(tmp_path)

    worlds = json.loads(_run_world_cli(tmp_path, monkeypatch, capsys, "list"))
    assert worlds == []

    monkeypatch.setattr(
        sys,
        "argv",
        ["worldforge", "world", "delete", world_id, "--state-dir", str(tmp_path)],
    )
    with pytest.raises(SystemExit) as excinfo:
        main()
    assert excinfo.value.code == 2
    error = capsys.readouterr().err
    assert f"World '{world_id}' is not present" in error
    assert "WorldForge CLI error [world delete]" in error
    assert "First triage:" in error
    assert "worldforge world list --state-dir <state-dir>" in error
    assert str(tmp_path) not in error


def test_world_cli_prediction_saves_or_dry_runs_persisted_world(
    tmp_path,
    monkeypatch,
    capsys,
) -> None:
    created = json.loads(_run_world_cli(tmp_path, monkeypatch, capsys, "create", "lab"))
    world_id = created["id"]
    json.loads(
        _run_world_cli(
            tmp_path,
            monkeypatch,
            capsys,
            "add-object",
            world_id,
            "cube",
            "--object-id",
            "cube-1",
            "--x",
            "0.0",
            "--y",
            "0.5",
            "--z",
            "0.0",
        )
    )

    prediction = json.loads(
        _run_world_cli(
            tmp_path,
            monkeypatch,
            capsys,
            "predict",
            world_id,
            "--object-id",
            "cube-1",
            "--x",
            "0.4",
            "--y",
            "0.5",
            "--z",
            "0.0",
            "--steps",
            "2",
        )
    )
    assert prediction["saved"] is True
    assert prediction["world"]["step"] == 2
    assert prediction["world"]["history_length"] == 3

    saved_objects = json.loads(_run_world_cli(tmp_path, monkeypatch, capsys, "objects", world_id))
    assert saved_objects["objects"][0]["position"] == {"x": 0.4, "y": 0.5, "z": 0.0}

    dry_run = json.loads(
        _run_world_cli(
            tmp_path,
            monkeypatch,
            capsys,
            "predict",
            world_id,
            "--object-id",
            "cube-1",
            "--x",
            "0.9",
            "--y",
            "0.5",
            "--z",
            "0.0",
            "--dry-run",
        )
    )
    assert dry_run["saved"] is False
    assert dry_run["world_state"]["scene"]["objects"]["cube-1"]["pose"]["position"] == {
        "x": 0.9,
        "y": 0.5,
        "z": 0.0,
    }

    persisted_after_dry_run = json.loads(
        _run_world_cli(tmp_path, monkeypatch, capsys, "objects", world_id)
    )
    assert persisted_after_dry_run["objects"][0]["position"] == {"x": 0.4, "y": 0.5, "z": 0.0}


def test_world_cli_rejects_incomplete_object_updates(tmp_path, monkeypatch, capsys) -> None:
    created = json.loads(_run_world_cli(tmp_path, monkeypatch, capsys, "create", "lab"))
    world_id = created["id"]

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "worldforge",
            "world",
            "update-object",
            world_id,
            "missing",
            "--x",
            "1.0",
            "--state-dir",
            str(tmp_path),
        ],
    )

    with pytest.raises(SystemExit) as excinfo:
        main()

    assert excinfo.value.code == 2
    assert "Position updates require --x, --y, and --z together." in capsys.readouterr().err


def test_world_cli_public_error_contract_for_malformed_state(
    tmp_path,
    monkeypatch,
    capsys,
) -> None:
    (tmp_path / "broken.json").write_text("{not-json", encoding="utf-8")
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "worldforge",
            "world",
            "show",
            "broken",
            "--state-dir",
            str(tmp_path),
        ],
    )

    with pytest.raises(SystemExit) as excinfo:
        main()

    error = capsys.readouterr().err
    assert excinfo.value.code == 2
    assert "WorldForge CLI error [world show]" in error
    assert "World file '<host-local-path>' is invalid" in error
    assert "First triage:" in error
    assert "Traceback" not in error
    assert str(tmp_path) not in error


def test_world_cli_migration_preview_is_read_only_and_attachable(
    tmp_path,
    monkeypatch,
    capsys,
) -> None:
    created = json.loads(_run_world_cli(tmp_path, monkeypatch, capsys, "create", "lab"))
    world_id = created["id"]
    world_path = tmp_path / f"{world_id}.json"
    before = world_path.read_text(encoding="utf-8")

    preview = json.loads(
        _run_world_cli(
            tmp_path,
            monkeypatch,
            capsys,
            "migration-preview",
            world_id,
        )
    )

    assert preview["status"] == "passed"
    assert preview["read_only"] is True
    assert preview["safe_to_attach"] is True
    assert world_path.read_text(encoding="utf-8") == before

    exported_path = tmp_path / "exported.json"
    exported_path.write_text(
        json.dumps({"schema_version": 1, "state": json.loads(before)}),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "worldforge",
            "world",
            "migration-preview",
            str(exported_path),
            "--source-path",
            "--format",
            "markdown",
        ],
    )

    assert main() == 0
    output = capsys.readouterr().out
    assert "# WorldForge World Migration Preview" in output
    assert "can_apply_safely: `true`" in output
    assert str(tmp_path) not in output


def test_world_cli_migration_preview_returns_nonzero_for_blocked_state(
    tmp_path,
    monkeypatch,
    capsys,
) -> None:
    (tmp_path / "broken.json").write_text("{bad", encoding="utf-8")
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "worldforge",
            "world",
            "migration-preview",
            "broken",
            "--state-dir",
            str(tmp_path),
            "--format",
            "json",
        ],
    )

    assert main() == 1
    report = json.loads(capsys.readouterr().out)
    assert report["status"] == "blocked"
    assert report["can_apply_safely"] is False
    assert report["invalid_fields"][0]["path"] == "source"
    assert str(tmp_path) not in json.dumps(report)

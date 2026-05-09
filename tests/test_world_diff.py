"""Tests for world state diff and patch artifacts (WF-FEAT-008)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from worldforge import (
    BBox,
    Position,
    SceneObject,
    SceneObjectPatch,
    WorldForge,
    WorldForgeError,
    WorldStateError,
)
from worldforge.cli import main as worldforge_main
from worldforge.world_diff import (
    OBJECT_CHANGE_KINDS,
    WORLD_DIFF_SCHEMA_VERSION,
    WORLD_FIELD_NAMES,
    ObjectChange,
    WorldFieldChange,
    WorldPatch,
    apply_patch,
    diff_worlds,
    diff_worlds_from_paths,
)


def _seed_world(forge: WorldForge, name: str, *, with_mug: bool = False):
    world = forge.create_world(name, "mock")
    world.add_object(
        SceneObject(
            "cube",
            Position(0.0, 0.5, 0.0),
            BBox(Position(-0.05, 0.45, -0.05), Position(0.05, 0.55, 0.05)),
        )
    )
    if with_mug:
        world.add_object(
            SceneObject(
                "mug",
                Position(0.25, 0.8, 0.0),
                BBox(Position(0.2, 0.75, -0.05), Position(0.3, 0.85, 0.05)),
            )
        )
    return world


def test_diff_identical_worlds_is_empty(tmp_path: Path) -> None:
    forge = WorldForge(state_dir=tmp_path)
    world = _seed_world(forge, "a")

    diff = diff_worlds(world.to_dict(), world.to_dict())

    assert diff.is_empty()
    assert diff.field_changes == ()
    assert diff.object_changes == ()
    assert diff.schema_version == WORLD_DIFF_SCHEMA_VERSION


def test_diff_detects_added_and_removed_objects(tmp_path: Path) -> None:
    forge = WorldForge(state_dir=tmp_path)
    source = _seed_world(forge, "src")
    target = _seed_world(forge, "tgt", with_mug=True)
    target.remove_object_by_id(next(iter(target.scene_objects)))

    diff = diff_worlds(source.to_dict(), target.to_dict())

    kinds = [(c.kind, c.object_id) for c in diff.object_changes]
    assert any(kind == "added" for kind, _ in kinds)
    assert any(kind == "removed" for kind, _ in kinds)


def test_diff_detects_field_changes_and_metadata(tmp_path: Path) -> None:
    forge = WorldForge(state_dir=tmp_path)
    world_a = _seed_world(forge, "alpha")
    world_b = _seed_world(forge, "beta")

    diff = diff_worlds(world_a.to_dict(), world_b.to_dict())

    fields = {change.field for change in diff.field_changes}
    assert "name" in fields
    assert "metadata" in fields  # framework writes the world name into metadata


def test_diff_detects_step_changes(tmp_path: Path) -> None:
    state_a = {"name": "w", "provider": "mock", "step": 0, "scene": {"objects": {}}}
    state_b = {"name": "w", "provider": "mock", "step": 7, "scene": {"objects": {}}}

    diff = diff_worlds(state_a, state_b)

    assert diff.field_changes == (WorldFieldChange(field="step", before=0, after=7),)


def test_diff_detects_updated_objects_with_field_changes(tmp_path: Path) -> None:
    forge = WorldForge(state_dir=tmp_path)
    world = _seed_world(forge, "w")
    object_id = next(iter(world.scene_objects))

    state_a = world.to_dict()
    world.update_object_patch(
        object_id,
        SceneObjectPatch(position=Position(0.5, 0.5, 0.0)),
    )
    state_b = world.to_dict()

    diff = diff_worlds(state_a, state_b)

    updated = [c for c in diff.object_changes if c.kind == "updated"]
    assert len(updated) == 1
    assert updated[0].object_id == object_id
    assert "pose" in updated[0].field_changes


def test_diff_to_dict_round_trips(tmp_path: Path) -> None:
    forge = WorldForge(state_dir=tmp_path)
    world_a = _seed_world(forge, "a")
    world_b = _seed_world(forge, "b", with_mug=True)

    payload = diff_worlds(world_a.to_dict(), world_b.to_dict()).to_dict()

    assert payload["schema_version"] == WORLD_DIFF_SCHEMA_VERSION
    assert "field_changes" in payload
    assert "object_changes" in payload
    assert payload["history_summary"]["source"] >= 1


def test_diff_to_markdown_includes_summary(tmp_path: Path) -> None:
    forge = WorldForge(state_dir=tmp_path)
    world_a = _seed_world(forge, "a")
    world_b = _seed_world(forge, "b", with_mug=True)

    rendered = diff_worlds(world_a.to_dict(), world_b.to_dict()).to_markdown()

    assert rendered.startswith("# WorldForge World Diff")
    assert "Field Changes" in rendered
    assert "Object Changes" in rendered


def test_diff_worlds_from_paths_round_trip(tmp_path: Path) -> None:
    forge = WorldForge(state_dir=tmp_path)
    world_a = _seed_world(forge, "a")
    world_b = _seed_world(forge, "b", with_mug=True)

    path_a = tmp_path / "a.json"
    path_b = tmp_path / "b.json"
    path_a.write_text(json.dumps(world_a.to_dict()), encoding="utf-8")
    path_b.write_text(json.dumps(world_b.to_dict()), encoding="utf-8")

    diff = diff_worlds_from_paths(path_a, path_b)
    assert diff.source_label == str(path_a)
    assert not diff.is_empty()


def test_diff_worlds_from_paths_rejects_invalid_json(tmp_path: Path) -> None:
    bad = tmp_path / "bad.json"
    bad.write_text("{not-json", encoding="utf-8")
    good = tmp_path / "good.json"
    good.write_text("{}", encoding="utf-8")

    with pytest.raises(WorldForgeError, match="invalid JSON"):
        diff_worlds_from_paths(bad, good)


def test_diff_worlds_rejects_invalid_inputs() -> None:
    with pytest.raises(WorldForgeError, match="World instance"):
        diff_worlds("not-a-world", {})  # type: ignore[arg-type]
    with pytest.raises(WorldForgeError, match="World instance"):
        diff_worlds({}, 42)  # type: ignore[arg-type]


def test_apply_patch_round_trips_through_diff(tmp_path: Path) -> None:
    forge = WorldForge(state_dir=tmp_path)
    world_a = _seed_world(forge, "a")
    world_b = _seed_world(forge, "b", with_mug=True)

    state_a = world_a.to_dict()
    state_b = world_b.to_dict()
    diff = diff_worlds(state_a, state_b)
    patch = WorldPatch.from_diff(diff)

    applied = apply_patch(state_a, patch)

    # Object IDs and core fields match the target snapshot.
    assert set(applied["scene"]["objects"]) == set(state_b["scene"]["objects"])
    assert applied["name"] == state_b["name"]
    assert applied["metadata"] == state_b["metadata"]


def test_apply_patch_does_not_mutate_input(tmp_path: Path) -> None:
    forge = WorldForge(state_dir=tmp_path)
    world = _seed_world(forge, "w")
    state = world.to_dict()
    snapshot = json.dumps(state, sort_keys=True)

    patch = WorldPatch(
        schema_version=WORLD_DIFF_SCHEMA_VERSION,
        field_changes=(WorldFieldChange(field="step", before=0, after=3),),
        object_changes=(),
    )
    apply_patch(state, patch)

    assert json.dumps(state, sort_keys=True) == snapshot


def test_apply_patch_rejects_traversal_object_id() -> None:
    payload = {
        "id": "x",
        "name": "x",
        "pose": {"position": {}},
        "bbox": {"min": {}, "max": {}},
    }
    with pytest.raises(WorldForgeError, match="traversal-shaped"):
        ObjectChange(kind="added", object_id="../escape", after=payload)


def test_apply_patch_rejects_incoherent_bbox(tmp_path: Path) -> None:
    forge = WorldForge(state_dir=tmp_path)
    world = _seed_world(forge, "w")
    state = world.to_dict()

    bad = {
        "id": "obj_bad",
        "name": "bad",
        "pose": {"position": {"x": 0.0, "y": 0.0, "z": 0.0}},
        "bbox": {
            "min": {"x": 1.0, "y": 1.0, "z": 1.0},
            "max": {"x": 0.0, "y": 0.0, "z": 0.0},
        },
        "is_graspable": False,
        "metadata": {},
    }
    patch = WorldPatch(
        schema_version=WORLD_DIFF_SCHEMA_VERSION,
        field_changes=(),
        object_changes=(ObjectChange(kind="added", object_id="obj_bad", after=bad),),
    )

    with pytest.raises(WorldStateError, match=r"BBox|validation failed"):
        apply_patch(state, patch)


def test_apply_patch_rejects_remove_of_missing_object(tmp_path: Path) -> None:
    forge = WorldForge(state_dir=tmp_path)
    state = _seed_world(forge, "w").to_dict()
    patch = WorldPatch(
        schema_version=WORLD_DIFF_SCHEMA_VERSION,
        field_changes=(),
        object_changes=(
            ObjectChange(
                kind="removed",
                object_id="ghost",
                before={"id": "ghost", "name": "ghost"},
            ),
        ),
    )
    with pytest.raises(WorldStateError, match="not present"):
        apply_patch(state, patch)


def test_apply_patch_rejects_add_of_existing_object(tmp_path: Path) -> None:
    forge = WorldForge(state_dir=tmp_path)
    world = _seed_world(forge, "w")
    state = world.to_dict()
    existing_id = next(iter(world.scene_objects))

    patch = WorldPatch(
        schema_version=WORLD_DIFF_SCHEMA_VERSION,
        field_changes=(),
        object_changes=(
            ObjectChange(
                kind="added",
                object_id=existing_id,
                after=state["scene"]["objects"][existing_id],
            ),
        ),
    )
    with pytest.raises(WorldStateError, match="already present"):
        apply_patch(state, patch)


def test_apply_patch_rejects_update_of_missing_object() -> None:
    state = {
        "name": "w",
        "provider": "mock",
        "step": 0,
        "scene": {"objects": {}},
        "metadata": {},
    }
    payload = {
        "id": "ghost",
        "name": "ghost",
        "pose": {"position": {"x": 0.0, "y": 0.0, "z": 0.0}},
        "bbox": {
            "min": {"x": -1, "y": -1, "z": -1},
            "max": {"x": 1, "y": 1, "z": 1},
        },
        "is_graspable": False,
        "metadata": {},
    }
    patch = WorldPatch(
        schema_version=WORLD_DIFF_SCHEMA_VERSION,
        field_changes=(),
        object_changes=(
            ObjectChange(kind="updated", object_id="ghost", before=payload, after=payload),
        ),
    )
    with pytest.raises(WorldStateError, match="not present"):
        apply_patch(state, patch)


def test_apply_patch_validates_step_value() -> None:
    state = {"name": "w", "provider": "mock", "step": 0, "scene": {"objects": {}}}
    patch = WorldPatch(
        schema_version=WORLD_DIFF_SCHEMA_VERSION,
        field_changes=(WorldFieldChange(field="step", before=0, after=-1),),
        object_changes=(),
    )
    with pytest.raises(WorldStateError, match="step value"):
        apply_patch(state, patch)


def test_world_field_change_rejects_unknown_field() -> None:
    with pytest.raises(WorldForgeError, match="must be one of"):
        WorldFieldChange(field="schema_version", before=1, after=2)


def test_object_change_kind_validation() -> None:
    assert "added" in OBJECT_CHANGE_KINDS
    assert "name" in WORLD_FIELD_NAMES
    with pytest.raises(WorldForgeError, match="kind must be one of"):
        ObjectChange(kind="weird", object_id="obj_x", after={})
    with pytest.raises(WorldForgeError, match="requires an 'after'"):
        ObjectChange(kind="added", object_id="obj_x")
    with pytest.raises(WorldForgeError, match="requires a 'before'"):
        ObjectChange(kind="removed", object_id="obj_x")
    with pytest.raises(WorldForgeError, match="requires both"):
        ObjectChange(kind="updated", object_id="obj_x")


def test_world_diff_cli_persisted_worlds(tmp_path: Path, monkeypatch, capsys) -> None:
    state_dir = tmp_path / "worlds"
    forge = WorldForge(state_dir=state_dir)
    a = _seed_world(forge, "alpha")
    b = _seed_world(forge, "beta", with_mug=True)
    forge.save_world(a)
    forge.save_world(b)

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "worldforge",
            "world",
            "diff",
            a.id,
            b.id,
            "--state-dir",
            str(state_dir),
            "--format",
            "json",
        ],
    )
    assert worldforge_main() == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["schema_version"] == WORLD_DIFF_SCHEMA_VERSION
    assert payload["source_label"] == a.id
    assert payload["target_label"] == b.id


def test_world_diff_cli_exported_paths(tmp_path: Path, monkeypatch, capsys) -> None:
    forge = WorldForge(state_dir=tmp_path / "ws")
    state_a = _seed_world(forge, "a").to_dict()
    state_b = _seed_world(forge, "b", with_mug=True).to_dict()

    path_a = tmp_path / "a.json"
    path_b = tmp_path / "b.json"
    path_a.write_text(json.dumps(state_a), encoding="utf-8")
    path_b.write_text(json.dumps(state_b), encoding="utf-8")

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "worldforge",
            "world",
            "diff",
            str(path_a),
            str(path_b),
            "--source-path",
            "--target-path",
            "--format",
            "markdown",
        ],
    )
    assert worldforge_main() == 0
    output = capsys.readouterr().out
    assert output.startswith("# WorldForge World Diff")


def test_world_diff_cli_requires_both_path_flags(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "worldforge",
            "world",
            "diff",
            "/tmp/a.json",
            "/tmp/b.json",
            "--source-path",
        ],
    )
    with pytest.raises(SystemExit):
        worldforge_main()

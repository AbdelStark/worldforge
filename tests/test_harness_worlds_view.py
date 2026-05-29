from __future__ import annotations

import importlib
import sys

import pytest

from worldforge import BBox, Position, SceneObject, WorldForge
from worldforge.harness.worlds_view import (
    SceneObjectSpec,
    WorldSpec,
    filter_world_ids,
    format_detail_summary,
    format_world_row,
    is_dirty,
    validate_id_or_reason,
)


def test_worlds_view_imports_without_textual() -> None:
    """Guard the Textual import boundary — the helpers must load on base install."""

    # Poison ``textual`` in ``sys.modules`` and reload the helper module. If
    # anything in the module imports Textual, the reload raises ModuleNotFoundError.
    import worldforge.harness.worlds_view as module

    saved_textual = sys.modules.pop("textual", None)
    sys.modules["textual"] = None  # type: ignore[assignment]
    try:
        reloaded = importlib.reload(module)
        assert callable(reloaded.format_world_row)
        assert callable(reloaded.validate_id_or_reason)
    finally:
        if saved_textual is not None:
            sys.modules["textual"] = saved_textual
        else:
            sys.modules.pop("textual", None)
        importlib.reload(module)


def test_validate_id_or_reason_accepts_valid_ids() -> None:
    assert validate_id_or_reason("lab") is None
    assert validate_id_or_reason("lab-01") is None
    assert validate_id_or_reason("lab_01.snap") is None


@pytest.mark.parametrize(
    "candidate",
    ["", "   ", ".", "..", "../escape", "a/b", "a\\b", "bad name", "with space"],
)
def test_validate_id_or_reason_rejects_unsafe_ids(candidate: str) -> None:
    reason = validate_id_or_reason(candidate)
    assert isinstance(reason, str)
    assert reason


def test_validate_id_or_reason_rejects_non_strings() -> None:
    assert validate_id_or_reason(None) is not None  # type: ignore[arg-type]
    assert validate_id_or_reason(42) is not None  # type: ignore[arg-type]


def test_validate_id_matches_framework(tmp_path) -> None:
    """The helper's verdict must agree with ``WorldForge.save_world`` at the boundary."""

    forge = WorldForge(state_dir=tmp_path)
    # Accept.
    assert validate_id_or_reason("lab-ok") is None
    # Reject at the boundary too.
    world = forge.create_world("shape", provider="mock")
    world.id = "../escape"  # bypass normal construction to exercise save-time
    from worldforge import WorldForgeError

    with pytest.raises(WorldForgeError):
        forge.save_world(world)


def test_format_world_row_shape(tmp_path) -> None:
    forge = WorldForge(state_dir=tmp_path)
    world = forge.create_world("lab", provider="mock")
    row = format_world_row(world, state_dir=None)
    assert row == (world.id, "lab", "mock", 0, "")


def test_format_world_row_includes_last_touched_when_saved(tmp_path) -> None:
    forge = WorldForge(state_dir=tmp_path)
    world = forge.create_world("lab", provider="mock")
    world_id = forge.save_world(world)
    row = format_world_row(world, state_dir=tmp_path)
    assert row[0] == world_id
    assert row[4]  # ISO timestamp populated


def test_format_detail_summary_lists_core_fields(tmp_path) -> None:
    forge = WorldForge(state_dir=tmp_path)
    world = forge.create_world("lab", provider="mock")
    world.add_object(
        SceneObject(
            "cube",
            Position(0.0, 0.5, 0.0),
            BBox(Position(-0.05, 0.45, -0.05), Position(0.05, 0.55, 0.05)),
        )
    )
    summary = format_detail_summary(world, state_dir=tmp_path)
    assert f"ID: {world.id}" in summary
    assert "Name: lab" in summary
    assert "Provider: mock" in summary
    assert "Scene objects: 1" in summary
    assert str(tmp_path) in summary


def test_is_dirty_flags_new_worlds_as_dirty(tmp_path) -> None:
    forge = WorldForge(state_dir=tmp_path)
    world = forge.create_world("lab", provider="mock")
    assert is_dirty(None, world) is True
    assert is_dirty(world, None) is False


def test_is_dirty_detects_name_change(tmp_path) -> None:
    forge = WorldForge(state_dir=tmp_path)
    original = forge.create_world("lab", provider="mock")
    edited = forge.create_world("lab", provider="mock")
    edited.id = original.id
    assert is_dirty(original, edited) is False
    edited.name = "kitchen"
    assert is_dirty(original, edited) is True


def test_filter_world_ids_substring_match() -> None:
    ids = ["kitchen-a", "kitchen-b", "lab-1"]
    names = {"kitchen-a": "Kitchen A", "kitchen-b": "Kitchen B", "lab-1": "Workbench"}
    assert filter_world_ids(ids, "", names) == ids
    assert filter_world_ids(ids, "kit", names) == ["kitchen-a", "kitchen-b"]
    assert filter_world_ids(ids, "WORK", names) == ["lab-1"]
    assert filter_world_ids(ids, "nope", names) == []


def test_world_spec_dataclass_defaults() -> None:
    spec = WorldSpec(name="lab", provider="mock")
    assert spec.description == ""


def test_scene_object_spec_defaults() -> None:
    spec = SceneObjectSpec(name="cube", x=0.0, y=0.5, z=0.0)
    assert spec.is_graspable is False
    assert spec.metadata == {}

from __future__ import annotations

import importlib
import sys

import pytest

from worldforge import BBox, Position, SceneObject, WorldForge
from worldforge.harness.worlds_view import (
    CONFIRM_DELETE_BINDING_SPECS,
    CONFIRM_DIALOG_SPEC,
    EDIT_OBJECT_BINDING_SPECS,
    EDIT_OBJECT_MODAL_SPEC,
    EDIT_PREVIEW_SAVED_CAPTION,
    FORM_FIELD_LABEL_CLASS,
    FORM_HIDDEN_CLASS,
    NEW_WORLD_BINDING_SPECS,
    NEW_WORLD_MODAL_SPEC,
    WORLD_EDIT_BINDING_SPECS,
    WORLD_EDIT_NAME_ID,
    WORLD_EDIT_OBJECTS_SELECTOR,
    WORLD_EDIT_PREVIEW_BODY_SELECTOR,
    WORLD_EDIT_PREVIEW_CAPTION_SELECTOR,
    WORLD_EDIT_PREVIEW_SELECTOR,
    WORLD_EDIT_PROVIDER_ID,
    WORLD_EDIT_SCREEN_SPEC,
    WORLD_EDIT_TITLE_SELECTOR,
    WORLDS_BINDING_SPECS,
    WORLDS_DETAIL_SELECTOR,
    WORLDS_EMPTY_SELECTOR,
    WORLDS_FILTER_ID,
    WORLDS_FILTER_SELECTOR,
    WORLDS_SCREEN_SPEC,
    WORLDS_TABLE_SELECTOR,
    SceneObjectSpec,
    WorldSpec,
    add_scene_object_from_spec,
    apply_world_name_edit,
    apply_world_provider_edit,
    bbox_for_position,
    clone_world,
    default_scene_object_spec,
    edit_preview_caption,
    filter_world_ids,
    format_detail_summary,
    format_scene_object_option,
    format_world_row,
    is_dirty,
    remove_scene_object_by_id,
    scene_object_from_spec,
    scene_object_options,
    scene_object_spec_from_form,
    spawn_action_from_spec,
    validate_id_or_reason,
    world_edit_title,
    world_spec_from_form,
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
        assert callable(reloaded.world_spec_from_form)
        assert callable(reloaded.scene_object_spec_from_form)
        assert callable(reloaded.world_edit_title)
        assert callable(reloaded.add_scene_object_from_spec)
        assert reloaded.CONFIRM_DELETE_BINDING_SPECS[0].action == "deny"
        assert reloaded.WORLDS_BINDING_SPECS[0].key == "n"
        assert reloaded.WORLD_EDIT_BINDING_SPECS[0].action == "save_world"
        assert reloaded.NEW_WORLD_MODAL_SPEC.name.widget_id == "new-world-name"
        assert reloaded.WORLDS_SCREEN_SPEC.table.columns == (
            "id",
            "name",
            "provider",
            "step",
            "last touched",
        )
        assert reloaded.WORLDS_TABLE_SELECTOR == "#worlds-table"
        assert reloaded.WORLD_EDIT_SCREEN_SPEC.name.widget_id == "edit-name"
        assert reloaded.WORLD_EDIT_OBJECTS_SELECTOR == "#edit-objects"
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
    ["", "   ", ".", "..", ".hidden", "../escape", "a/b", "a\\b", "bad name", "with space"],
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


def test_world_spec_from_form_trims_values() -> None:
    result = world_spec_from_form(
        name="  kitchen lab  ",
        provider_value="mock",
        description="  prep scene  ",
    )

    assert result.error is None
    assert result.spec is not None
    assert result.spec.name == "kitchen lab"
    assert result.spec.provider == "mock"
    assert result.spec.description == "prep scene"


def test_world_spec_from_form_defaults_non_string_provider() -> None:
    result = world_spec_from_form(name="lab", provider_value=object(), description=None)

    assert result.error is None
    assert result.spec is not None
    assert result.spec.name == "lab"
    assert result.spec.provider == "mock"
    assert result.spec.description == ""


@pytest.mark.parametrize(
    ("name", "message"),
    [
        ("", "Name must be a non-empty string."),
        ("   ", "Name must be a non-empty string."),
        ("../escape", "World ID must not contain path separators."),
        ("a\\b", "World ID must not contain path separators."),
        (".", "World ID must not be '.' or '..'."),
        ("..", "World ID must not be '.' or '..'."),
    ],
)
def test_world_spec_from_form_reports_user_facing_errors(name: str, message: str) -> None:
    result = world_spec_from_form(name=name, provider_value="mock", description="")

    assert result.spec is None
    assert result.error == message


def test_scene_object_spec_defaults() -> None:
    spec = SceneObjectSpec(name="cube", x=0.0, y=0.5, z=0.0)
    assert spec.is_graspable is False
    assert spec.metadata == {}


def test_world_modal_specs_are_stable() -> None:
    assert FORM_FIELD_LABEL_CLASS == "field-label"
    assert FORM_HIDDEN_CLASS == "hidden"
    assert CONFIRM_DIALOG_SPEC.confirm.widget_id == "confirm-accept"
    assert CONFIRM_DIALOG_SPEC.cancel.label == "Cancel"
    assert [
        (spec.key, spec.action, spec.description, spec.show)
        for spec in CONFIRM_DELETE_BINDING_SPECS
    ] == [("escape", "deny", "Cancel", True)]
    assert NEW_WORLD_MODAL_SPEC.default_providers == ("mock",)
    assert NEW_WORLD_MODAL_SPEC.submit.label == "Create"
    assert NEW_WORLD_MODAL_SPEC.description.placeholder == "A short scene description."
    assert [
        (spec.key, spec.action, spec.description, spec.show) for spec in NEW_WORLD_BINDING_SPECS
    ] == [("escape", "cancel", "Cancel", True)]
    assert EDIT_OBJECT_MODAL_SPEC.name.placeholder == "cube"
    assert EDIT_OBJECT_MODAL_SPEC.position_label == "Position x / y / z"
    assert EDIT_OBJECT_MODAL_SPEC.submit.widget_id == "edit-object-save"
    assert [
        (spec.key, spec.action, spec.description, spec.show) for spec in EDIT_OBJECT_BINDING_SPECS
    ] == [("escape", "cancel", "Cancel", True)]
    assert WORLDS_SCREEN_SPEC.root_id == "worlds-root"
    assert WORLDS_SCREEN_SPEC.filter_label.text == "Filter:"
    assert WORLDS_SCREEN_SPEC.filter_input.placeholder == "id or name substring"
    assert WORLDS_SCREEN_SPEC.empty.text == "No worlds yet — press [b]n[/] to create one."
    assert WORLDS_SCREEN_SPEC.detail.text == "Select a world to see its summary."
    assert [
        (spec.key, spec.action, spec.description, spec.show) for spec in WORLDS_BINDING_SPECS
    ] == [
        ("n", "new_world", "New", True),
        ("enter", "open_selected", "Open", True),
        ("e", "open_selected", "Edit", False),
        ("d", "delete_selected", "Delete", True),
        ("f", "fork_selected", "Fork", True),
        ("slash", "focus_filter", "Filter", True),
        ("r", "refresh_worlds", "Refresh", True),
        ("escape", "clear_filter", "Clear filter", False),
    ]
    assert WORLDS_TABLE_SELECTOR == "#worlds-table"
    assert WORLDS_EMPTY_SELECTOR == "#worlds-empty"
    assert WORLDS_DETAIL_SELECTOR == "#worlds-detail"
    assert WORLDS_FILTER_ID == "worlds-filter"
    assert WORLDS_FILTER_SELECTOR == "#worlds-filter"
    assert WORLD_EDIT_SCREEN_SPEC.root_id == "edit-root"
    assert WORLD_EDIT_SCREEN_SPEC.name_label.text == "Name"
    assert WORLD_EDIT_SCREEN_SPEC.provider_label.text == "Provider"
    assert WORLD_EDIT_SCREEN_SPEC.objects_header.text == "Scene objects"
    assert WORLD_EDIT_SCREEN_SPEC.preview_caption.text == EDIT_PREVIEW_SAVED_CAPTION
    assert [
        (spec.key, spec.action, spec.description, spec.show) for spec in WORLD_EDIT_BINDING_SPECS
    ] == [
        ("ctrl+s", "save_world", "Save", True),
        ("a", "add_object", "Add object", True),
        ("delete", "remove_object", "Remove", True),
        ("ctrl+p,predict", "predict_preview", "Preview", False),
        ("escape", "close", "Back", True),
    ]
    assert WORLD_EDIT_NAME_ID == "edit-name"
    assert WORLD_EDIT_PROVIDER_ID == "edit-provider"
    assert WORLD_EDIT_OBJECTS_SELECTOR == "#edit-objects"
    assert WORLD_EDIT_PREVIEW_SELECTOR == "#edit-preview"
    assert WORLD_EDIT_PREVIEW_CAPTION_SELECTOR == "#edit-preview-caption"
    assert WORLD_EDIT_PREVIEW_BODY_SELECTOR == "#edit-preview-body"
    assert WORLD_EDIT_TITLE_SELECTOR == "#edit-title"


def test_scene_object_spec_from_form_parses_position_defaults() -> None:
    result = scene_object_spec_from_form(name=" block ", x="1.25", y="0.5", z="")

    assert result.error is None
    assert result.spec is not None
    assert result.spec.name == "block"
    assert result.spec.x == 1.25
    assert result.spec.y == 0.5
    assert result.spec.z == 0.0


def test_scene_object_spec_from_form_rejects_blank_name() -> None:
    result = scene_object_spec_from_form(name=" ", x="0", y="0", z="0")

    assert result.spec is None
    assert result.error == "Name must be a non-empty string."


def test_scene_object_spec_from_form_rejects_non_numeric_position() -> None:
    result = scene_object_spec_from_form(name="block", x="oops", y="0", z="0")

    assert result.spec is None
    assert result.error == "Position coordinates must be numeric."


def test_default_scene_object_spec_is_centralized() -> None:
    spec = default_scene_object_spec()

    assert spec.name == "cube"
    assert spec.x == 0.0
    assert spec.y == 0.5
    assert spec.z == 0.0
    assert spec.is_graspable is False
    assert spec.metadata == {}


def test_bbox_for_position_uses_default_half_extent() -> None:
    bbox = bbox_for_position(Position(1.0, 2.0, 3.0))

    assert bbox.min == Position(0.95, 1.95, 2.95)
    assert bbox.max == Position(1.05, 2.05, 3.05)


def test_scene_object_from_spec_preserves_metadata_without_aliasing() -> None:
    metadata = {"material": "foam"}
    spec = SceneObjectSpec(
        name="block",
        x=0.25,
        y=0.5,
        z=0.0,
        is_graspable=True,
        metadata=metadata,
    )

    scene_object = scene_object_from_spec(spec)
    metadata["material"] = "steel"

    assert scene_object.name == "block"
    assert scene_object.position == Position(0.25, 0.5, 0.0)
    assert scene_object.is_graspable is True
    assert scene_object.metadata == {"material": "foam"}
    assert scene_object.bbox.min == Position(0.2, 0.45, -0.05)
    assert scene_object.bbox.max == Position(0.3, 0.55, 0.05)


def test_spawn_action_from_spec_matches_object_position() -> None:
    spec = SceneObjectSpec(name="block", x=0.25, y=0.5, z=0.0)

    action = spawn_action_from_spec(spec)

    assert action.kind == "spawn_object"
    assert action.parameters == {
        "name": "block",
        "position": {"x": 0.25, "y": 0.5, "z": 0.0},
        "bbox": {
            "min": {"x": 0.2, "y": 0.45, "z": -0.05},
            "max": {"x": 0.3, "y": 0.55, "z": 0.05},
        },
    }


def test_add_scene_object_from_spec_returns_preview_action(tmp_path) -> None:
    forge = WorldForge(state_dir=tmp_path)
    world = forge.create_world("lab", provider="mock")
    spec = SceneObjectSpec(name="block", x=0.25, y=0.5, z=0.0)

    action = add_scene_object_from_spec(world, spec)

    assert len(world.scene_objects) == 1
    scene_object = next(iter(world.scene_objects.values()))
    assert scene_object.name == "block"
    assert action.kind == "spawn_object"
    assert action.parameters["name"] == "block"


def test_remove_scene_object_by_id_reports_change(tmp_path) -> None:
    forge = WorldForge(state_dir=tmp_path)
    world = forge.create_world("lab", provider="mock")
    action = add_scene_object_from_spec(world, SceneObjectSpec(name="block", x=0.0, y=0.5, z=0.0))
    assert action.kind == "spawn_object"
    object_id = next(iter(world.scene_objects))

    assert remove_scene_object_by_id(world, None) is False
    assert remove_scene_object_by_id(world, "missing") is False
    assert remove_scene_object_by_id(world, object_id) is True
    assert world.scene_objects == {}


def test_format_scene_object_option_is_stable() -> None:
    scene_object = SceneObject(
        "block",
        Position(0.25, 0.5, 0.0),
        BBox(Position(0.2, 0.45, -0.05), Position(0.3, 0.55, 0.05)),
        id="block-1",
    )

    assert format_scene_object_option(scene_object) == ("block @ (0.25, 0.50, 0.00)", "block-1")


def test_scene_object_options_preserve_world_order(tmp_path) -> None:
    forge = WorldForge(state_dir=tmp_path)
    world = forge.create_world("lab", provider="mock")
    first = SceneObject(
        "alpha",
        Position(0.0, 0.5, 0.0),
        BBox(Position(-0.05, 0.45, -0.05), Position(0.05, 0.55, 0.05)),
        id="alpha-1",
    )
    second = SceneObject(
        "beta",
        Position(1.0, 0.5, 0.0),
        BBox(Position(0.95, 0.45, -0.05), Position(1.05, 0.55, 0.05)),
        id="beta-1",
    )
    world.add_object(first)
    world.add_object(second)

    assert scene_object_options(world) == [
        ("alpha @ (0.00, 0.50, 0.00)", "alpha-1"),
        ("beta @ (1.00, 0.50, 0.00)", "beta-1"),
    ]


def test_world_editor_title_and_preview_caption(tmp_path) -> None:
    forge = WorldForge(state_dir=tmp_path)
    world = forge.create_world("lab", provider="mock")

    assert world_edit_title(world, dirty=False, is_new=False) == f"Edit: lab ({world.id})"
    assert world_edit_title(world, dirty=True, is_new=False) == f"Edit: lab ({world.id}) *"
    assert world_edit_title(world, dirty=False, is_new=True) == f"Edit: lab ({world.id}) *"
    assert edit_preview_caption(staged=False) == "Preview (saved state)"
    assert edit_preview_caption(staged=True) == "Preview (predicted next state)"


def test_apply_world_name_edit_strips_and_updates_metadata(tmp_path) -> None:
    forge = WorldForge(state_dir=tmp_path)
    world = forge.create_world("lab", provider="mock")

    assert apply_world_name_edit(world, "  kitchen  ") is True
    assert world.name == "kitchen"
    assert world.metadata["name"] == "kitchen"
    assert apply_world_name_edit(world, "   ") is False
    assert world.name == "kitchen"


def test_apply_world_provider_edit_accepts_only_changed_strings(tmp_path) -> None:
    forge = WorldForge(state_dir=tmp_path)
    world = forge.create_world("lab", provider="mock")

    assert apply_world_provider_edit(world, "mock") is None
    assert apply_world_provider_edit(world, object()) is None
    assert apply_world_provider_edit(world, "mock-lab") == "mock-lab"
    assert world.provider == "mock-lab"


def test_clone_world_is_detached_for_dirty_detection(tmp_path) -> None:
    forge = WorldForge(state_dir=tmp_path)
    world = forge.create_world("lab", provider="mock")
    original = clone_world(world)

    world.name = "edited"

    assert original.name == "lab"
    assert is_dirty(original, world) is True

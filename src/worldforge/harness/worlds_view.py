"""Textual-free presentation helpers for TheWorldHarness Worlds screens.

This module is imported by :mod:`worldforge.harness.tui` to format table rows,
detail-pane summaries, dirty markers, and pre-validated world identifiers. It is
deliberately free of any ``textual`` import so ``from worldforge.harness.worlds_view
import format_world_row`` works on the base install (the ``harness`` extra only
exists for the Textual TUI itself).

The helpers intentionally mirror — but do not bypass — the validation in
:mod:`worldforge._state`. The TUI still round-trips every persistence call
through the public ``WorldForge`` API; the helpers here only let the UI render an
inline error *before* submitting invalid input, so the modal can stay open and
surface the rejection reason without a worker round trip.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

from worldforge.models import Action, BBox, Position, SceneObject

if TYPE_CHECKING:  # pragma: no cover - typing only
    from worldforge.framework import World


# Mirror of ``worldforge._state._STORAGE_ID_PATTERN`` so this module stays
# Textual-free and import-free of the framework at module load. The regex is
# kept narrow on purpose: any drift is caught by
# ``tests/test_harness_worlds_view.py::test_validate_id_matches_framework``.
_STORAGE_ID_PATTERN: re.Pattern[str] = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]*")
DEFAULT_SCENE_OBJECT_NAME = "cube"
DEFAULT_SCENE_OBJECT_X = 0.0
DEFAULT_SCENE_OBJECT_Y = 0.5
DEFAULT_SCENE_OBJECT_Z = 0.0
DEFAULT_SCENE_OBJECT_BBOX_HALF_EXTENT = 0.05
EDIT_PREVIEW_SAVED_CAPTION = "Preview (saved state)"
EDIT_PREVIEW_STAGED_CAPTION = "Preview (predicted next state)"
FORM_FIELD_LABEL_CLASS = "field-label"
FORM_HIDDEN_CLASS = "hidden"


@dataclass(slots=True, frozen=True)
class ModalButtonSpec:
    widget_id: str
    label: str
    variant: str


@dataclass(slots=True, frozen=True)
class ModalInputSpec:
    widget_id: str
    label: str
    placeholder: str = ""


@dataclass(slots=True, frozen=True)
class ConfirmDialogSpec:
    card_id: str
    title_id: str
    prompt_id: str
    actions_id: str
    title: str
    prompt: str
    cancel: ModalButtonSpec
    confirm: ModalButtonSpec


@dataclass(slots=True, frozen=True)
class NewWorldModalSpec:
    card_id: str
    title_id: str
    title: str
    name: ModalInputSpec
    provider: ModalInputSpec
    description: ModalInputSpec
    error_id: str
    actions_id: str
    cancel: ModalButtonSpec
    submit: ModalButtonSpec
    default_providers: tuple[str, ...] = ("mock",)


@dataclass(slots=True, frozen=True)
class EditObjectModalSpec:
    card_id: str
    title_id: str
    title: str
    name: ModalInputSpec
    position_label: str
    x_id: str
    y_id: str
    z_id: str
    error_id: str
    actions_id: str
    cancel: ModalButtonSpec
    submit: ModalButtonSpec


@dataclass(slots=True, frozen=True)
class ScreenInputSpec:
    widget_id: str
    placeholder: str

    @property
    def selector(self) -> str:
        return f"#{self.widget_id}"


@dataclass(slots=True, frozen=True)
class ScreenSelectSpec:
    widget_id: str

    @property
    def selector(self) -> str:
        return f"#{self.widget_id}"


@dataclass(slots=True, frozen=True)
class ScreenWidgetSpec:
    widget_id: str

    @property
    def selector(self) -> str:
        return f"#{self.widget_id}"


@dataclass(slots=True, frozen=True)
class ScreenLabelSpec:
    text: str


@dataclass(slots=True, frozen=True)
class ScreenTextSpec:
    widget_id: str
    text: str

    @property
    def selector(self) -> str:
        return f"#{self.widget_id}"


@dataclass(slots=True, frozen=True)
class ScreenTableSpec:
    widget_id: str
    columns: tuple[str, ...]

    @property
    def selector(self) -> str:
        return f"#{self.widget_id}"


@dataclass(slots=True, frozen=True)
class WorldsScreenSpec:
    root_id: str
    filter_row_id: str
    filter_label: ScreenTextSpec
    filter_input: ScreenInputSpec
    body_id: str
    table_wrap_id: str
    table: ScreenTableSpec
    empty: ScreenTextSpec
    detail: ScreenTextSpec


@dataclass(slots=True, frozen=True)
class WorldEditScreenSpec:
    root_id: str
    title: ScreenTextSpec
    body_id: str
    form_id: str
    name_label: ScreenLabelSpec
    name: ScreenInputSpec
    provider_label: ScreenLabelSpec
    provider: ScreenSelectSpec
    objects_header: ScreenTextSpec
    objects: ScreenWidgetSpec
    preview: ScreenWidgetSpec
    preview_caption: ScreenTextSpec
    preview_body: ScreenTextSpec


@dataclass(slots=True, frozen=True)
class WorldBindingSpec:
    key: str
    action: str
    description: str
    show: bool = True


CONFIRM_DIALOG_SPEC = ConfirmDialogSpec(
    card_id="confirm-card",
    title_id="confirm-title",
    prompt_id="confirm-prompt",
    actions_id="confirm-actions",
    title="Delete?",
    prompt="This action cannot be undone.",
    cancel=ModalButtonSpec("confirm-cancel", "Cancel", "default"),
    confirm=ModalButtonSpec("confirm-accept", "Delete", "error"),
)
NEW_WORLD_MODAL_SPEC = NewWorldModalSpec(
    card_id="new-world-card",
    title_id="new-world-title",
    title="Create world",
    name=ModalInputSpec("new-world-name", "Name", "e.g. kitchen-counter"),
    provider=ModalInputSpec("new-world-provider", "Provider"),
    description=ModalInputSpec(
        "new-world-description",
        "Description (optional)",
        "A short scene description.",
    ),
    error_id="new-world-error",
    actions_id="new-world-actions",
    cancel=ModalButtonSpec("new-world-cancel", "Cancel", "default"),
    submit=ModalButtonSpec("new-world-create", "Create", "primary"),
)
EDIT_OBJECT_MODAL_SPEC = EditObjectModalSpec(
    card_id="edit-object-card",
    title_id="edit-object-title",
    title="Scene object",
    name=ModalInputSpec("edit-object-name", "Name", "cube"),
    position_label="Position x / y / z",
    x_id="edit-object-x",
    y_id="edit-object-y",
    z_id="edit-object-z",
    error_id="edit-object-error",
    actions_id="edit-object-actions",
    cancel=ModalButtonSpec("edit-object-cancel", "Cancel", "default"),
    submit=ModalButtonSpec("edit-object-save", "Save", "primary"),
)
WORLDS_SCREEN_SPEC = WorldsScreenSpec(
    root_id="worlds-root",
    filter_row_id="worlds-filter-row",
    filter_label=ScreenTextSpec("worlds-filter-label", "Filter:"),
    filter_input=ScreenInputSpec("worlds-filter", "id or name substring"),
    body_id="worlds-body",
    table_wrap_id="worlds-table-wrap",
    table=ScreenTableSpec("worlds-table", ("id", "name", "provider", "step", "last touched")),
    empty=ScreenTextSpec("worlds-empty", "No worlds yet — press [b]n[/] to create one."),
    detail=ScreenTextSpec("worlds-detail", "Select a world to see its summary."),
)
CONFIRM_DELETE_BINDING_SPECS: tuple[WorldBindingSpec, ...] = (
    WorldBindingSpec("escape", "deny", "Cancel"),
)
NEW_WORLD_BINDING_SPECS: tuple[WorldBindingSpec, ...] = (
    WorldBindingSpec("escape", "cancel", "Cancel"),
)
EDIT_OBJECT_BINDING_SPECS: tuple[WorldBindingSpec, ...] = (
    WorldBindingSpec("escape", "cancel", "Cancel"),
)
WORLDS_BINDING_SPECS: tuple[WorldBindingSpec, ...] = (
    WorldBindingSpec("n", "new_world", "New"),
    WorldBindingSpec("enter", "open_selected", "Open"),
    WorldBindingSpec("e", "open_selected", "Edit", show=False),
    WorldBindingSpec("d", "delete_selected", "Delete"),
    WorldBindingSpec("f", "fork_selected", "Fork"),
    WorldBindingSpec("slash", "focus_filter", "Filter"),
    WorldBindingSpec("r", "refresh_worlds", "Refresh"),
    WorldBindingSpec("escape", "clear_filter", "Clear filter", show=False),
)
WORLDS_TABLE_SELECTOR = WORLDS_SCREEN_SPEC.table.selector
WORLDS_EMPTY_SELECTOR = WORLDS_SCREEN_SPEC.empty.selector
WORLDS_DETAIL_SELECTOR = WORLDS_SCREEN_SPEC.detail.selector
WORLDS_FILTER_ID = WORLDS_SCREEN_SPEC.filter_input.widget_id
WORLDS_FILTER_SELECTOR = WORLDS_SCREEN_SPEC.filter_input.selector
WORLD_EDIT_SCREEN_SPEC = WorldEditScreenSpec(
    root_id="edit-root",
    title=ScreenTextSpec("edit-title", ""),
    body_id="edit-body",
    form_id="edit-form",
    name_label=ScreenLabelSpec("Name"),
    name=ScreenInputSpec("edit-name", ""),
    provider_label=ScreenLabelSpec("Provider"),
    provider=ScreenSelectSpec("edit-provider"),
    objects_header=ScreenTextSpec("edit-objects-header", "Scene objects"),
    objects=ScreenWidgetSpec("edit-objects"),
    preview=ScreenWidgetSpec("edit-preview"),
    preview_caption=ScreenTextSpec("edit-preview-caption", EDIT_PREVIEW_SAVED_CAPTION),
    preview_body=ScreenTextSpec("edit-preview-body", ""),
)
WORLD_EDIT_BINDING_SPECS: tuple[WorldBindingSpec, ...] = (
    WorldBindingSpec("ctrl+s", "save_world", "Save"),
    WorldBindingSpec("a", "add_object", "Add object"),
    WorldBindingSpec("delete", "remove_object", "Remove"),
    WorldBindingSpec("ctrl+p,predict", "predict_preview", "Preview", show=False),
    WorldBindingSpec("escape", "close", "Back"),
)
WORLD_EDIT_NAME_ID = WORLD_EDIT_SCREEN_SPEC.name.widget_id
WORLD_EDIT_PROVIDER_ID = WORLD_EDIT_SCREEN_SPEC.provider.widget_id
WORLD_EDIT_OBJECTS_SELECTOR = WORLD_EDIT_SCREEN_SPEC.objects.selector
WORLD_EDIT_PREVIEW_SELECTOR = WORLD_EDIT_SCREEN_SPEC.preview.selector
WORLD_EDIT_PREVIEW_CAPTION_SELECTOR = WORLD_EDIT_SCREEN_SPEC.preview_caption.selector
WORLD_EDIT_PREVIEW_BODY_SELECTOR = WORLD_EDIT_SCREEN_SPEC.preview_body.selector
WORLD_EDIT_TITLE_SELECTOR = WORLD_EDIT_SCREEN_SPEC.title.selector


@dataclass(slots=True, frozen=True)
class WorldSpec:
    """User-submitted description of a new world, returned by ``NewWorldScreen``.

    Only the ``name`` and ``provider`` are required; ``description`` is optional.
    Validation of each field matches the contract documented on
    ``WorldForge.create_world``: non-empty ``name``, non-empty registered
    ``provider``, arbitrary ``description``.
    """

    name: str
    provider: str
    description: str = ""


@dataclass(slots=True)
class SceneObjectSpec:
    """User-submitted description of a scene object, returned by ``EditObjectScreen``.

    Independent from :class:`worldforge.models.SceneObject` so modal state can be
    held in the TUI without a ``SceneObject`` round trip (which itself would need
    a :class:`worldforge.models.BBox`). ``metadata`` defaults to an empty dict.
    """

    name: str
    x: float
    y: float
    z: float
    is_graspable: bool = False
    metadata: dict[str, object] = field(default_factory=dict)


@dataclass(slots=True, frozen=True)
class WorldSpecValidation:
    """Validation outcome for a new-world modal submission."""

    spec: WorldSpec | None = None
    error: str | None = None


@dataclass(slots=True, frozen=True)
class SceneObjectSpecValidation:
    """Validation outcome for a scene-object modal submission."""

    spec: SceneObjectSpec | None = None
    error: str | None = None


def default_scene_object_spec() -> SceneObjectSpec:
    """Return the modal default for creating a local scene object."""

    return SceneObjectSpec(
        name=DEFAULT_SCENE_OBJECT_NAME,
        x=DEFAULT_SCENE_OBJECT_X,
        y=DEFAULT_SCENE_OBJECT_Y,
        z=DEFAULT_SCENE_OBJECT_Z,
    )


def validate_id_or_reason(world_id: str) -> str | None:
    """Return ``None`` if ``world_id`` is a valid storage identifier, else a reason.

    The reason string is user-facing and matches the wording the persistence
    layer would raise when ``WorldForge.save_world`` is called. Modal callers
    can display it under the offending field without a worker round trip.
    """

    if not isinstance(world_id, str) or not world_id.strip():
        return "World ID must be a non-empty string."
    trimmed = world_id.strip()
    if trimmed in {".", ".."}:
        return "World ID must not be '.' or '..'."
    if "/" in trimmed or "\\" in trimmed:
        return "World ID must not contain path separators."
    if _STORAGE_ID_PATTERN.fullmatch(trimmed) is None:
        return "World ID must use only letters, numbers, '.', '_', or '-'."
    return None


def world_spec_from_form(
    *,
    name: str | None,
    provider_value: object,
    description: str | None,
) -> WorldSpecValidation:
    """Return a validated ``WorldSpec`` or a user-facing form error."""

    trimmed_name = (name or "").strip()
    if not trimmed_name:
        return WorldSpecValidation(error="Name must be a non-empty string.")

    # Most users type a human name; pre-validate only when the value actively
    # looks path-like. The persistence boundary remains the final authority.
    if " " not in trimmed_name and (
        "/" in trimmed_name or "\\" in trimmed_name or trimmed_name in {".", ".."}
    ):
        reason = validate_id_or_reason(trimmed_name)
        if reason:
            return WorldSpecValidation(error=reason)

    provider = provider_value if isinstance(provider_value, str) else "mock"
    spec = WorldSpec(
        name=trimmed_name,
        provider=provider,
        description=(description or "").strip(),
    )
    return WorldSpecValidation(spec=spec)


def scene_object_spec_from_form(
    *,
    name: str | None,
    x: str | None,
    y: str | None,
    z: str | None,
) -> SceneObjectSpecValidation:
    """Return a validated ``SceneObjectSpec`` or a user-facing form error."""

    trimmed_name = (name or "").strip()
    if not trimmed_name:
        return SceneObjectSpecValidation(error="Name must be a non-empty string.")

    try:
        spec = SceneObjectSpec(
            name=trimmed_name,
            x=float(x or 0.0),
            y=float(y or 0.0),
            z=float(z or 0.0),
        )
    except ValueError:
        return SceneObjectSpecValidation(error="Position coordinates must be numeric.")
    return SceneObjectSpecValidation(spec=spec)


def format_world_row(
    world: World,
    *,
    state_dir: Path | None = None,
) -> tuple[str, str, str, int, str]:
    """Return the ``(id, name, provider, step, last_touched)`` tuple for the table.

    ``last_touched`` is the ISO8601 timestamp of the backing JSON file's mtime
    when ``state_dir`` is provided and the file exists; otherwise the string is
    empty. This keeps the helper pure — no ``Path.stat`` side effects when the
    caller does not own a state directory.
    """

    last_touched = ""
    if state_dir is not None:
        path = state_dir / f"{world.id}.json"
        try:
            mtime = path.stat().st_mtime
        except OSError:
            mtime = 0.0
        if mtime > 0.0:
            last_touched = datetime.fromtimestamp(mtime, tz=UTC).replace(microsecond=0).isoformat()
    return (world.id, world.name, world.provider, int(world.step), last_touched)


def format_detail_summary(world: World, *, state_dir: Path | None = None) -> str:
    """Return a multi-line summary rendered in the right-side detail pane."""

    lines = [
        f"ID: {world.id}",
        f"Name: {world.name}",
        f"Provider: {world.provider}",
        f"Step: {int(world.step)}",
        f"Scene objects: {len(world.scene_objects)}",
        f"History entries: {world.history_length}",
    ]
    if world.description:
        lines.append(f"Description: {world.description}")
    if state_dir is not None:
        lines.append(f"State dir: {state_dir}")
    return "\n".join(lines)


def format_scene_object_option(scene_object: SceneObject) -> tuple[str, str]:
    """Return the ``OptionList`` label and id for a scene object."""

    return (
        f"{scene_object.name} @ "
        f"({scene_object.position.x:.2f},"
        f" {scene_object.position.y:.2f},"
        f" {scene_object.position.z:.2f})",
        scene_object.id,
    )


def scene_object_options(world: World) -> list[tuple[str, str]]:
    """Return stable scene-object option rows for the world editor."""

    return [
        format_scene_object_option(scene_object) for scene_object in world.scene_objects.values()
    ]


def bbox_for_position(
    position: Position,
    *,
    half_extent: float = DEFAULT_SCENE_OBJECT_BBOX_HALF_EXTENT,
) -> BBox:
    """Build a conservative axis-aligned box around ``position``."""

    return BBox(
        Position(position.x - half_extent, position.y - half_extent, position.z - half_extent),
        Position(position.x + half_extent, position.y + half_extent, position.z + half_extent),
    )


def scene_object_from_spec(spec: SceneObjectSpec) -> SceneObject:
    position = Position(spec.x, spec.y, spec.z)
    return SceneObject(
        name=spec.name,
        position=position,
        bbox=bbox_for_position(position),
        is_graspable=spec.is_graspable,
        metadata=dict(spec.metadata),
    )


def spawn_action_from_spec(spec: SceneObjectSpec) -> Action:
    position = Position(spec.x, spec.y, spec.z)
    return Action.spawn_object(
        spec.name,
        position=position,
        bbox=bbox_for_position(position),
    )


def add_scene_object_from_spec(world: World, spec: SceneObjectSpec) -> Action:
    """Add ``spec`` to ``world`` and return the staged preview action."""

    world.add_object(scene_object_from_spec(spec))
    return spawn_action_from_spec(spec)


def remove_scene_object_by_id(world: World, object_id: str | None) -> bool:
    """Remove a scene object by id and report whether anything changed."""

    if object_id is None:
        return False
    return world.remove_object_by_id(object_id) is not None


def apply_world_name_edit(world: World, value: str | None) -> bool:
    """Apply a non-empty name edit to ``world`` and report whether it was accepted."""

    name = (value or "").strip()
    if not name:
        return False
    world.name = name
    world.metadata["name"] = name
    return True


def apply_world_provider_edit(world: World, value: object) -> str | None:
    """Apply a provider edit and return the new provider when it changed."""

    if not isinstance(value, str) or value == world.provider:
        return None
    world.provider = value
    return value


def world_edit_title(world: World, *, dirty: bool, is_new: bool) -> str:
    """Return the world-editor title with the dirty marker applied."""

    marker = " *" if dirty or is_new else ""
    return f"Edit: {world.name} ({world.id}){marker}"


def edit_preview_caption(*, staged: bool) -> str:
    """Return the preview caption for saved versus staged editor state."""

    return EDIT_PREVIEW_STAGED_CAPTION if staged else EDIT_PREVIEW_SAVED_CAPTION


def clone_world(world: World) -> World:
    """Return a detached snapshot for dirty detection."""

    return type(world).from_state(world._forge, world.to_dict())


def is_dirty(original: World | None, edited: World | None) -> bool:
    """Return whether ``edited`` differs from ``original`` in persisted fields.

    A newly-created world (no ``original``) is considered dirty as soon as an
    ``edited`` World exists — the user must press ``Ctrl+S`` to persist it.
    Comparison uses ``World.to_dict()`` minus the ``history`` block because
    history is recorded as a side effect of ``record_history`` and would flap
    even during pure display refreshes.
    """

    if edited is None:
        return False
    if original is None:
        return True

    def _shape(world: World) -> dict[str, object]:
        snapshot = dict(world.to_dict())
        snapshot.pop("history", None)
        return snapshot

    return _shape(original) != _shape(edited)


def filter_world_ids(world_ids: list[str], query: str, name_map: dict[str, str]) -> list[str]:
    """Substring-filter ``world_ids`` by id or name.

    ``name_map`` maps world id → name. The filter is case-insensitive. Matching
    preserves the input order so the table does not shuffle on filter toggles.
    """

    if not query.strip():
        return list(world_ids)
    needle = query.strip().lower()
    result = []
    for world_id in world_ids:
        name = name_map.get(world_id, "")
        if needle in world_id.lower() or needle in name.lower():
            result.append(world_id)
    return result

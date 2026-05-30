"""Textual TUI for TheWorldHarness."""

from __future__ import annotations

import asyncio
import queue
from collections.abc import Callable, Iterable, Mapping
from contextlib import suppress
from pathlib import Path
from typing import Any, ClassVar

from rich.console import RenderableType
from rich.text import Text
from textual import events, on, work
from textual.app import App, ComposeResult, SystemCommand
from textual.binding import Binding
from textual.command import DiscoveryHit, Hit
from textual.command import Provider as CommandProvider
from textual.containers import Container, Horizontal, Vertical, VerticalScroll
from textual.css.query import NoMatches
from textual.message import Message
from textual.reactive import reactive
from textual.screen import ModalScreen, Screen
from textual.theme import Theme
from textual.widgets import (
    Button,
    DataTable,
    Footer,
    Header,
    Input,
    OptionList,
    ProgressBar,
    RichLog,
    Select,
    Static,
)
from textual.widgets.option_list import Option
from textual.worker import get_current_worker

from worldforge import (
    Action,
    World,
    WorldForge,
    WorldForgeError,
    WorldStateError,
    list_eval_suites,
)
from worldforge.benchmark import BENCHMARKABLE_OPERATIONS
from worldforge.harness import robotics_launch as _robotics_launch
from worldforge.harness import robotics_view as _robotics_view
from worldforge.harness import tui_styles as _tui_styles
from worldforge.harness.connectors import (
    ProviderConnectorSummary,
    provider_connector_detail_text,
    provider_connector_summaries,
)
from worldforge.harness.flow_catalog import available_flows
from worldforge.harness.flows import (
    benchmark_report_harness_run,
    benchmark_run_artifacts,
    eval_report_harness_run,
    eval_run_artifacts,
    recent_report_paths,
    report_run_from_path,
    run_flow,
    write_report,
)
from worldforge.harness.models import HarnessFlow, HarnessRun, HarnessStep
from worldforge.harness.robotics_tui_rendering import (
    ROBOTICS_ARM_FRAMES,
    robotics_arm_panel,
    robotics_arm_target_line,
    robotics_candidate_panel,
    robotics_event_panel,
    robotics_help_section_renderable,
    robotics_hero_panel,
    robotics_metrics_panel,
    robotics_pipeline_panel,
    robotics_progress_panel,
    robotics_report_guide_panel,
    robotics_rerun_panel,
    robotics_tabletop_panel,
    robotics_tensorboard_panel,
)
from worldforge.harness.run_history import (
    RunHistoryFilter,
    RunHistoryRecord,
    list_run_history,
    preserved_run_from_path,
)
from worldforge.harness.run_history_view import (
    RUN_ARTIFACT_FILTER_ID,
    RUN_CAPABILITY_FILTER_ID,
    RUN_CREATED_FROM_FILTER_ID,
    RUN_FILTER_INPUT_SELECTORS,
    RUN_HISTORY_BINDING_SPECS,
    RUN_HISTORY_DETAIL_SELECTOR,
    RUN_HISTORY_EMPTY_SELECTOR,
    RUN_HISTORY_SCREEN_SPEC,
    RUN_HISTORY_TABLE_SELECTOR,
    RUN_PROVIDER_FILTER_ID,
    RUN_STATUS_FILTER_ID,
    RUNS_DETAIL_EMPTY_MESSAGE,
    RunHistoryFilterForm,
    first_visible_run_id,
    run_history_filter_from_form,
    selected_run_provider_label,
    selected_run_record,
)
from worldforge.harness.run_history_view import (
    run_history_detail_text as _run_history_detail_text,
)
from worldforge.harness.run_history_view import (
    run_history_table_row as _run_history_table_row,
)
from worldforge.harness.theme import (
    THEME_NAME_DARK,
    THEME_SPECS,
    next_theme_name,
)
from worldforge.harness.tui_app_view import (
    APP_BINDING_SPECS,
    SYSTEM_COMMAND_SPECS,
    AppScreenName,
    PaletteItemSpec,
    SystemCommandSpec,
    app_screen_name,
    flow_system_command_help,
    flow_system_command_title,
    initial_screen_name,
    palette_item_specs,
    screen_needs_run_inspector_refresh,
)
from worldforge.harness.tui_benchmark_view import (
    BENCHMARK_BINDING_SPECS,
    BENCHMARK_LOG_SELECTOR,
    BENCHMARK_RUN_BUTTON_ID,
    BENCHMARK_SCREEN_SPEC,
    DEFAULT_BENCHMARK_ITERATIONS,
    benchmark_request_from_form,
    benchmark_sample_progress,
)
from worldforge.harness.tui_chrome_view import (
    BREADCRUMB_ID,
    BREADCRUMB_SELECTOR,
    CHROME_CONTAINER_ID,
    PROVIDER_PILL_ID,
    PROVIDER_PILL_SELECTOR,
    ScreenChrome,
    flow_provider_label,
    provider_capability_label,
    run_inspector_fixed_chrome,
    run_inspector_flow_chrome,
    screen_chrome,
)
from worldforge.harness.tui_eval_view import (
    EVAL_BINDING_SPECS,
    EVAL_LOG_SELECTOR,
    EVAL_RUN_BUTTON_ID,
    EVAL_SCREEN_SPEC,
    eval_request_from_form,
    eval_running_log_line,
)
from worldforge.harness.tui_help_view import (
    HELP_BINDING_SPECS,
    HELP_MODAL_SPEC,
    HELP_TABLE_SELECTOR,
    PLACEHOLDER_BINDING_SPECS,
    PLACEHOLDER_MODAL_SPEC,
    help_binding_rows,
    placeholder_title,
)
from worldforge.harness.tui_home_view import (
    HOME_INITIAL_FOCUS_WIDGET_ID,
    HOME_JUMP_CARD_BINDING_SPECS,
    HOME_JUMP_SPECS,
    HOME_RECENT_SELECTOR,
    HOME_SCREEN_BINDING_SPECS,
    HOME_SCREEN_SPEC,
    home_jump_target_screen,
    home_recent_text,
    recent_world_ids,
)
from worldforge.harness.tui_provider_events import (
    format_provider_event as _format_provider_event,
)
from worldforge.harness.tui_provider_events import (
    provider_event_failure as _provider_event_failure,
)
from worldforge.harness.tui_provider_events import (
    provider_event_summary as _event_summary,
)
from worldforge.harness.tui_provider_view import (
    PROVIDER_ACTION_SPECS,
    PROVIDER_BINDING_SPECS,
    PROVIDER_CANCEL_BUTTON_ID,
    PROVIDER_DETAIL_SELECTOR,
    PROVIDER_EMPTY_SELECTOR,
    PROVIDER_FIELD_LABEL_CLASS,
    PROVIDER_LOG_SELECTOR,
    PROVIDER_REGISTER_BUTTON_ID,
    PROVIDER_RUN_BUTTON_ID,
    PROVIDER_SCREEN_SPEC,
    PROVIDER_TABLE_SELECTOR,
    REGISTER_PROVIDER_BINDING_SPECS,
    REGISTER_PROVIDER_MODAL_SPEC,
    provider_cancel_target,
    provider_predict_target,
    provider_registration_from_form,
    provider_success_summary,
    provider_table_row,
)
from worldforge.harness.tui_rendering import (
    TuiRenderColors,
    empty_inspector_panel,
    empty_transcript_panel,
    export_preview_panel,
    flow_card_panel,
    hero_panel,
    run_inspector_panel,
    run_transcript_panel,
    timeline_panel,
)
from worldforge.harness.tui_report_view import ReportCompletionSpec, ReportRunControlSpec
from worldforge.harness.tui_run_inspector_view import (
    RUN_INSPECTOR_BINDING_SPECS,
    RUN_INSPECTOR_DEFAULT_FLOW_ID,
    RUN_INSPECTOR_DEFAULT_STEP_DELAY_SECONDS,
    RUN_INSPECTOR_EXPORT_PREVIEW_ID,
    RUN_INSPECTOR_FLOW_SELECT_ID,
    RUN_INSPECTOR_INSPECTOR_ID,
    RUN_INSPECTOR_READY_STEPS,
    RUN_INSPECTOR_RUN_BUTTON_ID,
    RUN_INSPECTOR_SCREEN_SPEC,
    RUN_INSPECTOR_TIMELINE_ID,
    RUN_INSPECTOR_TRANSCRIPT_ID,
    resolve_run_inspector_flow_id,
    run_inspector_flow_bindings,
    run_inspector_flow_card_id,
    run_inspector_flow_options,
)
from worldforge.harness.workspace import workspace_root_for_state_dir
from worldforge.harness.worlds_view import (
    CONFIRM_DELETE_BINDING_SPECS,
    CONFIRM_DIALOG_SPEC,
    EDIT_OBJECT_BINDING_SPECS,
    EDIT_OBJECT_MODAL_SPEC,
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
    clone_world,
    default_scene_object_spec,
    edit_preview_caption,
    filter_world_ids,
    format_detail_summary,
    is_dirty,
    remove_scene_object_by_id,
    scene_object_options,
    scene_object_spec_from_form,
    world_edit_title,
    world_spec_from_form,
)
from worldforge.models import JSONDict, ProviderEvent
from worldforge.providers.base import ProviderError
from worldforge.providers.mock import MockProvider

InitialScreen = AppScreenName
_RUNS_DETAIL_EMPTY_MESSAGE = RUNS_DETAIL_EMPTY_MESSAGE


def _build_theme(name: str, palette: Mapping[str, str], *, dark: bool) -> Theme:
    """Construct a Textual ``Theme`` from a palette mapping.

    Keeping this builder local lets ``tui.py`` stay free of literal hex strings;
    every color token lives in ``harness/theme.py`` instead.
    """
    return Theme(
        name=name,
        primary=palette["primary"],
        secondary=palette["secondary"],
        accent=palette["accent"],
        warning=palette["warning"],
        error=palette["error"],
        success=palette["success"],
        foreground=palette["foreground"],
        background=palette["background"],
        surface=palette["surface"],
        panel=palette["panel"],
        boost=palette["boost"],
        dark=dark,
        variables={"muted": palette["muted"]},
    )


def _register_worldforge_themes(app: App[Any]) -> None:
    for spec in THEME_SPECS:
        app.register_theme(_build_theme(spec.name, spec.palette, dark=spec.dark))


def _apply_chrome(node: Any, chrome: ScreenChrome) -> None:
    breadcrumb = _maybe_query(node, BREADCRUMB_SELECTOR, Breadcrumb)
    if breadcrumb is not None:
        breadcrumb.path = chrome.path
    pill = _maybe_query(node, PROVIDER_PILL_SELECTOR, ProviderStatusPill)
    if pill is not None:
        pill.label = chrome.provider_label


def _compose_chrome() -> ComposeResult:
    with Horizontal(id=CHROME_CONTAINER_ID):
        yield Breadcrumb(id=BREADCRUMB_ID)
        yield ProviderStatusPill(id=PROVIDER_PILL_ID)


class _ThemedRenderer:
    """Mixin that resolves semantic-token names against the active theme.

    Rich renderables (``Panel``, ``Text``) accept inline ``style="..."`` and
    ``border_style="..."`` strings. We resolve a token name (``"accent"``,
    ``"success"``, ``"muted"``, ``"panel"``, ``"surface"``) into the concrete
    color the active Textual theme declares, so the rendered output always
    matches whichever theme the user toggled to.
    """

    app: App[None]

    def _color(self, token: str) -> str:
        variables = self.app.get_css_variables()
        return variables.get(token, variables.get("foreground", ""))

    def _render_colors(self) -> TuiRenderColors:
        return TuiRenderColors(
            foreground=self._color("foreground"),
            accent=self._color("accent"),
            success=self._color("success"),
            warning=self._color("warning"),
            error=self._color("error"),
            muted=self._color("muted"),
            panel=self._color("panel"),
        )


def _set_form_error(node, selector: str, message: str | None) -> None:
    """Update or hide an inline form-error ``Static`` identified by ``selector``."""

    error = _maybe_query(node, selector, Static)
    if error is None:
        return
    if message:
        error.update(message)
        error.remove_class("hidden")
    else:
        error.update("")
        error.add_class("hidden")


def _maybe_query(node, selector: str, expected_type):
    """Return a widget from ``node`` if composed, else ``None``.

    Reactives can fire before all widgets in ``compose()`` are mounted (and
    chrome updates can fire on a screen that hasn't mounted yet). Treat a
    missing target as a no-op rather than crashing.
    """
    try:
        return node.query_one(selector, expected_type)
    except NoMatches:
        return None


def _input_value(input_widget: Input | None) -> str | None:
    if input_widget is None:
        return None
    value = input_widget.value.strip()
    return value or None


def _select_value(select_widget: Select | None) -> str | None:
    if select_widget is None or select_widget.value is Select.BLANK:
        return None
    value = str(select_widget.value).strip()
    return value or None


class Breadcrumb(Static):
    """Header breadcrumb showing ``worldforge > <screen> [> <flow>]``.

    Path segments live in a reactive tuple; later milestones can deepen the
    trail (worlds, runs) without changing the rendering surface.
    """

    DEFAULT_CSS = _tui_styles.BREADCRUMB_DEFAULT_CSS

    path: reactive[tuple[str, ...]] = reactive((), layout=True)

    def watch_path(self, _old: tuple[str, ...], new: tuple[str, ...]) -> None:
        if not new:
            self.update("")
            return
        separator = Text(" > ", style="dim")
        rendered = Text()
        for index, segment in enumerate(new):
            if index:
                rendered.append_text(separator)
            style = "bold" if index == len(new) - 1 else "dim"
            rendered.append(segment, style=style)
        self.update(rendered)


class ProviderStatusPill(Static):
    """Header right-side pill showing ``<provider> . <capability>``.

    The label is sourced from the App-level ``current_provider`` reactive so a
    flow change updates the pill before the next user interaction.
    """

    DEFAULT_CSS = _tui_styles.PROVIDER_STATUS_PILL_DEFAULT_CSS

    label: reactive[str] = reactive("")

    def watch_label(self, _old: str, new: str) -> None:
        self.update(new)


class HeroPane(Static, _ThemedRenderer):
    """Top-level harness identity panel."""

    def compose_panel(self, flow: HarnessFlow | None, running: bool) -> RenderableType:
        return hero_panel(flow, running=running, colors=self._render_colors())


class FlowCard(Static, _ThemedRenderer):
    """Flow selection card."""

    def render_flow(self, flow: HarnessFlow, selected: bool) -> None:
        self.update(flow_card_panel(flow, selected=selected, colors=self._render_colors()))


class TimelinePane(Static, _ThemedRenderer):
    """Visual execution timeline."""

    def render_steps(
        self,
        flow: HarnessFlow,
        steps: tuple[HarnessStep, ...],
        active_index: int,
        complete_count: int,
    ) -> None:
        self.update(
            timeline_panel(
                flow,
                steps,
                active_index=active_index,
                complete_count=complete_count,
                colors=self._render_colors(),
            )
        )


class InspectorPane(Static, _ThemedRenderer):
    """Run metrics and state summary."""

    def render_empty(self) -> None:
        self.update(empty_inspector_panel(self._render_colors()))

    def render_run(self, run: HarnessRun) -> None:
        self.update(run_inspector_panel(run, colors=self._render_colors()))


class TranscriptPane(Static, _ThemedRenderer):
    """Structured transcript from the completed flow."""

    def render_empty(self) -> None:
        self.update(empty_transcript_panel())

    def render_run(self, run: HarnessRun) -> None:
        self.update(run_transcript_panel(run, colors=self._render_colors()))


class ExportPane(Static, _ThemedRenderer):  # pragma: no cover - exercised by Pilot tests.
    """Preview report artifacts without re-running the underlying workflow."""

    report_format: reactive[str] = reactive("markdown", init=False)

    def __init__(self, *, artifacts: dict[str, str] | None = None, widget_id: str | None = None):
        super().__init__(id=widget_id)
        self._artifacts = dict(artifacts or {})

    def set_artifacts(self, artifacts: dict[str, str]) -> None:
        self._artifacts = dict(artifacts)
        self._refresh()

    def watch_report_format(self, _old: str, _new: str) -> None:
        self._refresh()

    def _refresh(self) -> None:
        self.update(
            export_preview_panel(
                self._artifacts,
                report_format=self.report_format,
                colors=self._render_colors(),
            )
        )


class ProviderEventReceived(Message):
    """Provider event forwarded from a worker thread."""

    def __init__(self, event: ProviderEvent) -> None:
        super().__init__()
        self.event = event


class RunCompleted(Message):
    """A live provider run completed."""

    def __init__(self, *, provider: str, latency_ms: float) -> None:
        super().__init__()
        self.provider = provider
        self.latency_ms = latency_ms


class RunCancelled(Message):
    """A worker cancellation became visible to the UI."""

    def __init__(self, *, provider: str) -> None:
        super().__init__()
        self.provider = provider


class ReportExported(Message):
    """A preserved eval or benchmark report was written to disk."""

    def __init__(self, *, path: Path, kind: str) -> None:
        super().__init__()
        self.path = path
        self.kind = kind


class CapabilityMismatch(Message):
    """Evaluation or benchmark capability mismatch surfaced from a worker."""

    def __init__(self, error: WorldForgeError) -> None:
        super().__init__()
        self.error = error


# ---------------------------------------------------------------------------
# Jump cards & messages (Home screen)
# ---------------------------------------------------------------------------


class JumpRequested(Message):
    """Posted by a ``JumpCard`` when the user activates it."""

    def __init__(self, target: str) -> None:
        super().__init__()
        self.target = target


class JumpCard(Static, _ThemedRenderer):
    """Focusable Home-screen jump target.

    Activates on ``enter``, click, or its bound letter key (handled by
    the parent screen). Posts a :class:`JumpRequested` so the parent
    screen owns the routing decision per the skill's "messages over
    reach-across" rule.
    """

    DEFAULT_CSS = _tui_styles.JUMP_CARD_DEFAULT_CSS

    BINDINGS: ClassVar[list[Binding]] = [
        Binding(spec.key, spec.action, spec.description, show=spec.show)
        for spec in HOME_JUMP_CARD_BINDING_SPECS
    ]

    can_focus = True

    def __init__(
        self,
        *,
        target: str,
        title: str,
        binding: str,
        description: str,
        widget_id: str | None = None,
    ) -> None:
        super().__init__(id=widget_id)
        self._target = target
        self._title = title
        self._binding = binding
        self._description = description

    def on_mount(self) -> None:
        accent = self._color("accent")
        body = Text()
        body.append(self._title, style=f"bold {accent}")
        body.append(f"   [{self._binding}]\n", style="dim")
        body.append(self._description, style="dim")
        self.update(body)

    def action_activate(self) -> None:
        self.post_message(JumpRequested(self._target))

    def on_click(self, event: events.Click) -> None:  # pragma: no cover - thin wrapper
        event.stop()
        self.focus()
        self.post_message(JumpRequested(self._target))


# ---------------------------------------------------------------------------
# Screens
# ---------------------------------------------------------------------------


class HomeScreen(Screen):
    """Landing screen with a 30-second intro and three jump cards."""

    BINDINGS: ClassVar[list[Binding]] = [
        Binding(spec.key, spec.action, spec.description, show=spec.show)
        for spec in HOME_SCREEN_BINDING_SPECS
    ]

    DEFAULT_CSS = _tui_styles.HOME_SCREEN_DEFAULT_CSS

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        yield from _compose_chrome()
        with Container(id=HOME_SCREEN_SPEC.root_id):
            yield Static(
                Text.from_markup(HOME_SCREEN_SPEC.intro.text),
                id=HOME_SCREEN_SPEC.intro.widget_id,
            )
            with Vertical(id=HOME_SCREEN_SPEC.cards_id):
                for spec in HOME_JUMP_SPECS:
                    yield JumpCard(
                        target=spec.target,
                        title=spec.title,
                        binding=spec.binding,
                        description=spec.description,
                        widget_id=spec.widget_id,
                    )
            yield Static(
                HOME_SCREEN_SPEC.recent.text,
                id=HOME_SCREEN_SPEC.recent.widget_id,
            )
        yield Footer()

    def on_mount(self) -> None:
        self._update_chrome()
        self._refresh_recent()
        first_card = _maybe_query(self, f"#{HOME_INITIAL_FOCUS_WIDGET_ID}", JumpCard)
        if first_card is not None:
            first_card.focus()

    def on_screen_resume(self) -> None:
        self._update_chrome()
        self._refresh_recent()

    def _update_chrome(self) -> None:
        _apply_chrome(self, screen_chrome("home"))

    def action_jump(self, target: str) -> None:
        self.post_message(JumpRequested(target))

    def on_jump_requested(self, event: JumpRequested) -> None:
        event.stop()
        screen_name = home_jump_target_screen(event.target)
        if screen_name is not None:
            self.app.action_switch_screen(screen_name)
            return
        self.app.push_screen(
            PlaceholderScreen(target_milestone="?", next_action="Target not yet routed.")
        )

    def _refresh_recent(self) -> None:
        target = _maybe_query(self, HOME_RECENT_SELECTOR, Static)
        if target is None or not hasattr(self.app, "_get_forge"):
            return
        forge = self.app._get_forge()  # type: ignore[attr-defined]
        target.update(
            home_recent_text(
                world_ids=recent_world_ids(forge.list_worlds(), state_dir=forge.state_dir),
                report_paths=recent_report_paths(forge.state_dir, limit=5),
                run_records=list_run_history(
                    workspace_root_for_state_dir(forge.state_dir), limit=5
                ),
            )
        )


class RunsScreen(Screen):
    """Filter and open preserved run workspaces."""

    BINDINGS: ClassVar[list[Binding]] = [
        Binding(spec.key, spec.action, spec.description, show=spec.show)
        for spec in RUN_HISTORY_BINDING_SPECS
    ]

    DEFAULT_CSS = _tui_styles.RUNS_SCREEN_DEFAULT_CSS

    selected_run_id: reactive[str | None] = reactive(None, init=False)

    def __init__(self, *, state_dir: Path) -> None:
        super().__init__()
        self._state_dir = state_dir
        self._records: dict[str, RunHistoryRecord] = {}
        self._ordered_ids: list[str] = []

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        yield from _compose_chrome()
        with Container(id=RUN_HISTORY_SCREEN_SPEC.root_id):
            with Horizontal(id=RUN_HISTORY_SCREEN_SPEC.filter_row_id):
                yield Input(
                    placeholder=RUN_HISTORY_SCREEN_SPEC.provider_filter.placeholder,
                    id=RUN_HISTORY_SCREEN_SPEC.provider_filter.widget_id,
                )
                yield Input(
                    placeholder=RUN_HISTORY_SCREEN_SPEC.capability_filter.placeholder,
                    id=RUN_HISTORY_SCREEN_SPEC.capability_filter.widget_id,
                )
                yield Select(
                    list(RUN_HISTORY_SCREEN_SPEC.status_filter.options),
                    value=RUN_HISTORY_SCREEN_SPEC.status_filter.default,
                    allow_blank=False,
                    id=RUN_HISTORY_SCREEN_SPEC.status_filter.widget_id,
                )
                yield Input(
                    placeholder=RUN_HISTORY_SCREEN_SPEC.created_from_filter.placeholder,
                    id=RUN_HISTORY_SCREEN_SPEC.created_from_filter.widget_id,
                )
                yield Input(
                    placeholder=RUN_HISTORY_SCREEN_SPEC.artifact_filter.placeholder,
                    id=RUN_HISTORY_SCREEN_SPEC.artifact_filter.widget_id,
                )
            with Horizontal(id=RUN_HISTORY_SCREEN_SPEC.body_id):
                with Container(id=RUN_HISTORY_SCREEN_SPEC.table_wrap_id):
                    yield DataTable(
                        zebra_stripes=True,
                        cursor_type="row",
                        id=RUN_HISTORY_SCREEN_SPEC.table_id,
                    )
                    yield Static(
                        RUN_HISTORY_SCREEN_SPEC.empty.empty_message,
                        id=RUN_HISTORY_SCREEN_SPEC.empty.widget_id,
                    )
                yield Static(
                    RUN_HISTORY_SCREEN_SPEC.detail.empty_message,
                    id=RUN_HISTORY_SCREEN_SPEC.detail.widget_id,
                )
        yield Footer()

    def on_mount(self) -> None:
        table = self.query_one(RUN_HISTORY_TABLE_SELECTOR, DataTable)
        table.add_columns(*RUN_HISTORY_SCREEN_SPEC.table_columns)
        table.focus()
        self._update_chrome()
        self.refresh_runs()

    def on_screen_resume(self) -> None:
        self._update_chrome()
        table = _maybe_query(self, RUN_HISTORY_TABLE_SELECTOR, DataTable)
        if table is not None:
            table.focus()

    def watch_selected_run_id(self, _old: str | None, _new: str | None) -> None:
        self._refresh_detail()
        self._update_chrome()

    def _update_chrome(self) -> None:
        record = selected_run_record(self._records, self.selected_run_id)
        _apply_chrome(
            self,
            screen_chrome("runs", provider_label=selected_run_provider_label(record)),
        )

    def refresh_runs(self) -> None:
        filters = self._filters()
        records = list_run_history(
            workspace_root_for_state_dir(self._state_dir),
            filters=filters,
        )
        self._records = {record.run_id: record for record in records}
        self._ordered_ids = [record.run_id for record in records]
        self._rebuild_table_rows()

    def _filters(self) -> RunHistoryFilter:
        status = _select_value(
            _maybe_query(self, RUN_HISTORY_SCREEN_SPEC.status_filter.selector, Select)
        )
        result = run_history_filter_from_form(
            RunHistoryFilterForm(
                provider=_input_value(
                    _maybe_query(self, RUN_HISTORY_SCREEN_SPEC.provider_filter.selector, Input)
                ),
                capability=_input_value(
                    _maybe_query(self, RUN_HISTORY_SCREEN_SPEC.capability_filter.selector, Input)
                ),
                status=status,
                created_from=_input_value(
                    _maybe_query(self, RUN_HISTORY_SCREEN_SPEC.created_from_filter.selector, Input)
                ),
                artifact_type=_input_value(
                    _maybe_query(self, RUN_HISTORY_SCREEN_SPEC.artifact_filter.selector, Input)
                ),
            )
        )
        if result.error is not None:
            self.notify(result.error, severity="error", title="Run filter")
        return result.filters

    def _rebuild_table_rows(self) -> None:
        table = _maybe_query(self, RUN_HISTORY_TABLE_SELECTOR, DataTable)
        empty = _maybe_query(self, RUN_HISTORY_EMPTY_SELECTOR, Static)
        if table is None:
            return
        table.clear()
        for run_id in self._ordered_ids:
            table.add_row(*_run_history_table_row(self._records[run_id]), key=run_id)
        self._sync_empty_state(table, empty)

    def _sync_empty_state(self, table: DataTable, empty: Static | None) -> None:
        if self._ordered_ids:
            if empty is not None:
                empty.add_class("hidden")
            table.remove_class("hidden")
            self.selected_run_id = first_visible_run_id(self._ordered_ids)
            return
        if empty is not None:
            empty.remove_class("hidden")
        table.add_class("hidden")
        self.selected_run_id = None

    def _refresh_detail(self) -> None:
        detail = _maybe_query(self, RUN_HISTORY_DETAIL_SELECTOR, Static)
        if detail is None:
            return
        record = selected_run_record(self._records, self.selected_run_id)
        detail.update(_run_history_detail_text(record))

    @on(DataTable.RowHighlighted, RUN_HISTORY_TABLE_SELECTOR)
    def _on_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        key = event.row_key.value if event.row_key else None
        if isinstance(key, str):
            self.selected_run_id = key

    @on(DataTable.RowSelected, RUN_HISTORY_TABLE_SELECTOR)
    def _on_row_selected(self, event: DataTable.RowSelected) -> None:
        key = event.row_key.value if event.row_key else None
        if isinstance(key, str):
            self.selected_run_id = key
            self.action_open_selected()

    @on(Input.Changed, f"#{RUN_PROVIDER_FILTER_ID}")
    @on(Input.Changed, f"#{RUN_CAPABILITY_FILTER_ID}")
    @on(Input.Changed, f"#{RUN_CREATED_FROM_FILTER_ID}")
    @on(Input.Changed, f"#{RUN_ARTIFACT_FILTER_ID}")
    def _on_filter_changed(self, event: Input.Changed) -> None:
        del event
        self.refresh_runs()

    @on(Select.Changed, f"#{RUN_STATUS_FILTER_ID}")
    def _on_status_changed(self) -> None:
        self.refresh_runs()

    def action_focus_provider_filter(self) -> None:
        provider_filter = _maybe_query(
            self,
            RUN_HISTORY_SCREEN_SPEC.provider_filter.selector,
            Input,
        )
        if provider_filter is not None:
            provider_filter.focus()

    def action_clear_filters(self) -> None:
        for selector in RUN_FILTER_INPUT_SELECTORS:
            field = _maybe_query(self, selector, Input)
            if field is not None:
                field.value = ""
        status = _maybe_query(self, RUN_HISTORY_SCREEN_SPEC.status_filter.selector, Select)
        if status is not None:
            status.value = RUN_HISTORY_SCREEN_SPEC.status_filter.default
        self.refresh_runs()
        table = _maybe_query(self, RUN_HISTORY_TABLE_SELECTOR, DataTable)
        if table is not None:
            table.focus()

    def action_open_selected(self) -> None:
        record = selected_run_record(self._records, self.selected_run_id)
        if record is None:
            return
        if hasattr(self.app, "_open_run_workspace"):
            self.app._open_run_workspace(record.path)  # type: ignore[attr-defined]


class RunInspectorScreen(Screen):
    """Hosts the existing flow visualisation (hero, rail, timeline, inspector, transcript)."""

    BINDINGS: ClassVar[list[Binding]] = [
        *(
            Binding(spec.key, spec.action, spec.description, show=spec.show)
            for spec in RUN_INSPECTOR_BINDING_SPECS
        ),
        *(
            Binding(spec.key, spec.action, spec.description, show=spec.show)
            for spec in run_inspector_flow_bindings(available_flows())
        ),
    ]

    DEFAULT_CSS = _tui_styles.RUN_INSPECTOR_SCREEN_DEFAULT_CSS

    selected_flow_id: reactive[str] = reactive(RUN_INSPECTOR_DEFAULT_FLOW_ID, init=False)
    current_provider: reactive[str] = reactive("", init=False)
    running: reactive[bool] = reactive(False, init=False)
    last_run: reactive[HarnessRun | None] = reactive(None, init=False)

    def __init__(
        self,
        *,
        initial_flow_id: str = RUN_INSPECTOR_DEFAULT_FLOW_ID,
        state_dir: Path | None = None,
        step_delay: float = RUN_INSPECTOR_DEFAULT_STEP_DELAY_SECONDS,
        run: HarnessRun | None = None,
    ) -> None:
        super().__init__()
        self._fixed_run = run
        self.flows = {flow.id: flow for flow in available_flows()}
        resolved_id = resolve_run_inspector_flow_id(initial_flow_id, self.flows)
        self.set_reactive(RunInspectorScreen.selected_flow_id, resolved_id)
        self.set_reactive(
            RunInspectorScreen.current_provider,
            flow_provider_label(self.flows[resolved_id]),
        )
        self.state_dir = state_dir
        self.step_delay = step_delay
        if run is not None:
            self.set_reactive(RunInspectorScreen.last_run, run)

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        yield from _compose_chrome()
        if self._fixed_run is not None and self._fixed_run.kind != "flow":
            with (
                Container(id=RUN_INSPECTOR_SCREEN_SPEC.root_id),
                Horizontal(id=RUN_INSPECTOR_SCREEN_SPEC.body_id),
            ):
                with Vertical(id=RUN_INSPECTOR_SCREEN_SPEC.report_column_id):
                    yield InspectorPane(id=RUN_INSPECTOR_SCREEN_SPEC.inspector_id)
                    yield TranscriptPane(id=RUN_INSPECTOR_SCREEN_SPEC.transcript_id)
                yield ExportPane(
                    artifacts=self._fixed_run.artifacts or {},
                    widget_id=RUN_INSPECTOR_SCREEN_SPEC.export_preview_id,
                )
            yield Footer()
            return
        with Container(id=RUN_INSPECTOR_SCREEN_SPEC.root_id):
            yield HeroPane(id=RUN_INSPECTOR_SCREEN_SPEC.hero_id)
            with Horizontal(id=RUN_INSPECTOR_SCREEN_SPEC.body_id):
                with Vertical(id=RUN_INSPECTOR_SCREEN_SPEC.rail_id):
                    yield Select(
                        list(run_inspector_flow_options(tuple(self.flows.values()))),
                        value=self.selected_flow_id,
                        allow_blank=False,
                        id=RUN_INSPECTOR_SCREEN_SPEC.flow_select_id,
                    )
                    yield Button(
                        RUN_INSPECTOR_SCREEN_SPEC.run.label,
                        id=RUN_INSPECTOR_SCREEN_SPEC.run.widget_id,
                        variant=RUN_INSPECTOR_SCREEN_SPEC.run.variant,
                    )
                    for flow in self.flows.values():
                        yield FlowCard(id=run_inspector_flow_card_id(flow))
                yield TimelinePane(id=RUN_INSPECTOR_SCREEN_SPEC.flow_timeline_id)
                with Vertical(id=RUN_INSPECTOR_SCREEN_SPEC.inspector_column_id):
                    yield InspectorPane(id=RUN_INSPECTOR_SCREEN_SPEC.inspector_id)
                    yield TranscriptPane(id=RUN_INSPECTOR_SCREEN_SPEC.transcript_id)
        yield Footer()

    def on_mount(self) -> None:
        self._update_chrome()
        self._refresh_static()

    def on_screen_resume(self) -> None:
        self._update_chrome()
        self._refresh_static()

    @on(Select.Changed, f"#{RUN_INSPECTOR_FLOW_SELECT_ID}")
    def _on_flow_changed(self, event: Select.Changed) -> None:
        if isinstance(event.value, str):
            self.selected_flow_id = event.value

    @on(Button.Pressed, f"#{RUN_INSPECTOR_RUN_BUTTON_ID}")
    async def _on_run_pressed(self) -> None:
        await self.action_run_selected()

    def action_select_flow(self, flow_id: str) -> None:
        if flow_id in self.flows:
            self.selected_flow_id = flow_id
            select = _maybe_query(self, f"#{RUN_INSPECTOR_FLOW_SELECT_ID}", Select)
            if select is not None and select.value != flow_id:
                select.value = flow_id

    @property
    def can_run_flows(self) -> bool:
        """Return whether this screen has the interactive flow controls mounted."""

        return self._fixed_run is None or self._fixed_run.kind == "flow"

    def watch_selected_flow_id(self, _old: str, new: str) -> None:
        if new not in self.flows:
            return
        self.current_provider = flow_provider_label(self.flows[new])
        self._update_chrome()
        self._refresh_static()

    def watch_current_provider(self, _old: str, new: str) -> None:
        del new
        self._update_chrome()

    async def action_run_selected(self) -> None:
        if self.running:
            return
        await self._run_flow(self.selected_flow_id)

    async def _run_flow(self, flow_id: str) -> None:
        self.running = True
        flow = self.flows[flow_id]
        self.query_one(f"#{RUN_INSPECTOR_RUN_BUTTON_ID}", Button).disabled = True
        self._refresh_static()
        run = run_flow(flow_id, state_dir=self.state_dir)
        self.last_run = run
        timeline = self.query_one(f"#{RUN_INSPECTOR_TIMELINE_ID}", TimelinePane)
        for index, _step in enumerate(run.steps):
            timeline.render_steps(flow, run.steps, active_index=index, complete_count=index)
            await asyncio.sleep(self.step_delay)
            timeline.render_steps(flow, run.steps, active_index=index, complete_count=index + 1)
        self.query_one(f"#{RUN_INSPECTOR_INSPECTOR_ID}", InspectorPane).render_run(run)
        self.query_one(f"#{RUN_INSPECTOR_TRANSCRIPT_ID}", TranscriptPane).render_run(run)
        self.running = False
        self.query_one(f"#{RUN_INSPECTOR_RUN_BUTTON_ID}", Button).disabled = False
        self._refresh_static()

    def _update_chrome(self) -> None:
        if self._fixed_run is not None and self._fixed_run.kind != "flow":
            _apply_chrome(self, run_inspector_fixed_chrome(self._fixed_run))
            return
        flow = self.flows[self.selected_flow_id]
        _apply_chrome(self, run_inspector_flow_chrome(flow, self.current_provider))

    def _refresh_static(self) -> None:
        if self._fixed_run is not None and self._fixed_run.kind != "flow":
            inspector = _maybe_query(self, f"#{RUN_INSPECTOR_INSPECTOR_ID}", InspectorPane)
            transcript = _maybe_query(self, f"#{RUN_INSPECTOR_TRANSCRIPT_ID}", TranscriptPane)
            export = _maybe_query(self, f"#{RUN_INSPECTOR_EXPORT_PREVIEW_ID}", ExportPane)
            if inspector is not None:
                inspector.render_run(self._fixed_run)
            if transcript is not None:
                transcript.render_run(self._fixed_run)
            if export is not None:
                export.set_artifacts(self._fixed_run.artifacts or {})
            return
        selected = self.flows[self.selected_flow_id]
        hero = _maybe_query(self, f"#{RUN_INSPECTOR_SCREEN_SPEC.hero_id}", HeroPane)
        if hero is None:
            return
        hero.update(hero.compose_panel(selected, self.running))
        for flow in self.flows.values():
            self.query_one(f"#{run_inspector_flow_card_id(flow)}", FlowCard).render_flow(
                flow,
                selected=flow.id == self.selected_flow_id,
            )
        if self.last_run is None:
            self.query_one(f"#{RUN_INSPECTOR_TIMELINE_ID}", TimelinePane).render_steps(
                selected,
                RUN_INSPECTOR_READY_STEPS,
                active_index=0,
                complete_count=0,
            )
            self.query_one(f"#{RUN_INSPECTOR_INSPECTOR_ID}", InspectorPane).render_empty()
            self.query_one(f"#{RUN_INSPECTOR_TRANSCRIPT_ID}", TranscriptPane).render_empty()


def _complete_report_run(
    screen: Screen,
    *,
    forge: WorldForge,
    completion: ReportCompletionSpec,
    run: HarnessRun,
    artifacts: dict[str, str],
    path: Path,
) -> None:
    export = _maybe_query(screen, completion.export_selector, ExportPane)
    if export is not None:
        export.set_artifacts(artifacts)
    status = _maybe_query(screen, completion.status_selector, Static)
    if status is not None:
        status.update(completion.saved_message(path))
    screen.post_message(ReportExported(path=path, kind=completion.kind))
    screen.app.push_screen(RunInspectorScreen(state_dir=forge.state_dir, run=run))


def _cancel_report_or_back(
    screen: Screen,
    *,
    running: bool,
    run_control: ReportRunControlSpec,
) -> bool:
    if not running:
        screen.app.action_switch_screen("home")
        return False
    screen.workers.cancel_group(screen, run_control.worker_group)
    screen.app.notify(
        run_control.cancel_message,
        severity="warning",
        title=run_control.notify_title,
    )
    return True


def _handle_capability_mismatch(
    screen: Screen,
    event: CapabilityMismatch,
    *,
    run_control: ReportRunControlSpec,
    log_selector: str,
) -> None:
    event.stop()
    message = str(event.error)
    screen.app.notify(message, severity="error", title=run_control.mismatch_title)
    log = _maybe_query(screen, log_selector, RichLog)
    if log is not None:
        log.write(Text(message, style=run_control.mismatch_log_style))


class HelpScreen(ModalScreen[None]):
    """Modal overlay that lists the bindings of the screen below it."""

    BINDINGS: ClassVar[list[Binding]] = [
        Binding(spec.key, spec.action, spec.description, show=spec.show)
        for spec in HELP_BINDING_SPECS
    ]

    DEFAULT_CSS = _tui_styles.HELP_SCREEN_DEFAULT_CSS

    def __init__(self, source_screen: Screen | None = None) -> None:
        super().__init__()
        self._source_screen = source_screen

    def compose(self) -> ComposeResult:
        with Container(id=HELP_MODAL_SPEC.card_id):
            yield Static(
                HELP_MODAL_SPEC.title.text,
                id=HELP_MODAL_SPEC.title.widget_id,
            )
            yield DataTable(
                id=HELP_MODAL_SPEC.table.widget_id,
                cursor_type="row",
                zebra_stripes=True,
            )
            yield Static(
                HELP_MODAL_SPEC.footnote.text,
                id=HELP_MODAL_SPEC.footnote.widget_id,
            )

    def on_mount(self) -> None:
        # Update breadcrumb (sits on the screen below this modal) and
        # populate the table from that same source screen.
        breadcrumb = _maybe_query(self.app, BREADCRUMB_SELECTOR, Breadcrumb)
        if breadcrumb is not None:
            breadcrumb.path = ("worldforge", "help")
        table = self.query_one(HELP_TABLE_SELECTOR, DataTable)
        table.add_columns(*HELP_MODAL_SPEC.table.columns)
        source = self._source_screen or self._previous_screen()
        for row in help_binding_rows(source):
            table.add_row(row.key, row.description, row.action)

    def _previous_screen(self) -> Screen | None:
        """Return the screen below this modal on the stack, if any."""
        stack = list(self.app.screen_stack)
        if self in stack:
            stack.remove(self)
        return stack[-1] if stack else None


class PlaceholderScreen(ModalScreen[None]):
    """Modal explaining a jump target that lands in a later milestone."""

    BINDINGS: ClassVar[list[Binding]] = [
        Binding(spec.key, spec.action, spec.description, show=spec.show)
        for spec in PLACEHOLDER_BINDING_SPECS
    ]

    DEFAULT_CSS = _tui_styles.PLACEHOLDER_SCREEN_DEFAULT_CSS

    def __init__(self, *, target_milestone: str, next_action: str) -> None:
        super().__init__()
        self._target_milestone = target_milestone
        self._next_action = next_action

    def compose(self) -> ComposeResult:
        with Container(id=PLACEHOLDER_MODAL_SPEC.card_id):
            yield Static(
                placeholder_title(self._target_milestone),
                id=PLACEHOLDER_MODAL_SPEC.title_id,
            )
            yield Static(self._next_action, id=PLACEHOLDER_MODAL_SPEC.body_id)
            yield Static(
                PLACEHOLDER_MODAL_SPEC.footnote.text,
                id=PLACEHOLDER_MODAL_SPEC.footnote.widget_id,
            )

    def on_mount(self) -> None:
        breadcrumb = _maybe_query(self.app, BREADCRUMB_SELECTOR, Breadcrumb)
        if breadcrumb is not None:
            breadcrumb.path = ("worldforge", "placeholder")


# ---------------------------------------------------------------------------
# Worlds CRUD: messages
# ---------------------------------------------------------------------------


class WorldSaved(Message):
    """Posted after a successful ``WorldForge.save_world`` worker."""

    def __init__(self, world_id: str) -> None:
        super().__init__()
        self.world_id = world_id


class WorldDeleted(Message):
    """Posted after a world file is removed from the state directory."""

    def __init__(self, world_id: str) -> None:
        super().__init__()
        self.world_id = world_id


class WorldForked(Message):
    """Posted after ``WorldForge.fork_world`` returns successfully."""

    def __init__(self, source_id: str, fork: World) -> None:
        super().__init__()
        self.source_id = source_id
        self.fork = fork


# ---------------------------------------------------------------------------
# Worlds CRUD: modals
# ---------------------------------------------------------------------------


class ConfirmDeleteScreen(ModalScreen[bool]):
    """Yes/no overlay for destructive actions. Returns ``True`` only on confirm."""

    BINDINGS: ClassVar[list[Binding]] = [
        Binding(spec.key, spec.action, spec.description, show=spec.show)
        for spec in CONFIRM_DELETE_BINDING_SPECS
    ]

    DEFAULT_CSS = _tui_styles.CONFIRM_DELETE_SCREEN_DEFAULT_CSS

    def __init__(
        self,
        *,
        prompt: str = CONFIRM_DIALOG_SPEC.prompt,
        title: str = CONFIRM_DIALOG_SPEC.title,
        confirm_label: str = CONFIRM_DIALOG_SPEC.confirm.label,
        cancel_label: str = CONFIRM_DIALOG_SPEC.cancel.label,
    ) -> None:
        super().__init__()
        self._prompt = prompt
        self._title = title
        self._confirm_label = confirm_label
        self._cancel_label = cancel_label

    def compose(self) -> ComposeResult:
        with Container(id=CONFIRM_DIALOG_SPEC.card_id):
            yield Static(self._title, id=CONFIRM_DIALOG_SPEC.title_id)
            yield Static(self._prompt, id=CONFIRM_DIALOG_SPEC.prompt_id)
            with Horizontal(id=CONFIRM_DIALOG_SPEC.actions_id):
                yield Button(
                    self._cancel_label,
                    id=CONFIRM_DIALOG_SPEC.cancel.widget_id,
                    variant=CONFIRM_DIALOG_SPEC.cancel.variant,
                )
                yield Button(
                    self._confirm_label,
                    id=CONFIRM_DIALOG_SPEC.confirm.widget_id,
                    variant=CONFIRM_DIALOG_SPEC.confirm.variant,
                )

    def on_mount(self) -> None:
        accept = _maybe_query(self, f"#{CONFIRM_DIALOG_SPEC.confirm.widget_id}", Button)
        if accept is not None:
            accept.focus()

    @on(Button.Pressed, f"#{CONFIRM_DIALOG_SPEC.confirm.widget_id}")
    def _on_accept(self) -> None:
        self.dismiss(True)

    @on(Button.Pressed, f"#{CONFIRM_DIALOG_SPEC.cancel.widget_id}")
    def _on_cancel(self) -> None:
        self.dismiss(False)

    def action_deny(self) -> None:
        self.dismiss(False)


class NewWorldScreen(ModalScreen[WorldSpec | None]):
    """Collect name + provider + description for a brand-new world."""

    BINDINGS: ClassVar[list[Binding]] = [
        Binding(spec.key, spec.action, spec.description, show=spec.show)
        for spec in NEW_WORLD_BINDING_SPECS
    ]

    DEFAULT_CSS = _tui_styles.NEW_WORLD_SCREEN_DEFAULT_CSS

    def __init__(self, *, providers: tuple[str, ...]) -> None:
        super().__init__()
        self._providers = providers or NEW_WORLD_MODAL_SPEC.default_providers

    def compose(self) -> ComposeResult:
        with Container(id=NEW_WORLD_MODAL_SPEC.card_id):
            yield Static(NEW_WORLD_MODAL_SPEC.title, id=NEW_WORLD_MODAL_SPEC.title_id)
            yield Static(NEW_WORLD_MODAL_SPEC.name.label, classes=FORM_FIELD_LABEL_CLASS)
            yield Input(
                placeholder=NEW_WORLD_MODAL_SPEC.name.placeholder,
                id=NEW_WORLD_MODAL_SPEC.name.widget_id,
            )
            yield Static(NEW_WORLD_MODAL_SPEC.provider.label, classes=FORM_FIELD_LABEL_CLASS)
            yield Select(
                [(provider, provider) for provider in self._providers],
                value=self._providers[0],
                allow_blank=False,
                id=NEW_WORLD_MODAL_SPEC.provider.widget_id,
            )
            yield Static(NEW_WORLD_MODAL_SPEC.description.label, classes=FORM_FIELD_LABEL_CLASS)
            yield Input(
                placeholder=NEW_WORLD_MODAL_SPEC.description.placeholder,
                id=NEW_WORLD_MODAL_SPEC.description.widget_id,
            )
            yield Static("", id=NEW_WORLD_MODAL_SPEC.error_id, classes=FORM_HIDDEN_CLASS)
            with Horizontal(id=NEW_WORLD_MODAL_SPEC.actions_id):
                yield Button(
                    NEW_WORLD_MODAL_SPEC.cancel.label,
                    id=NEW_WORLD_MODAL_SPEC.cancel.widget_id,
                    variant=NEW_WORLD_MODAL_SPEC.cancel.variant,
                )
                yield Button(
                    NEW_WORLD_MODAL_SPEC.submit.label,
                    id=NEW_WORLD_MODAL_SPEC.submit.widget_id,
                    variant=NEW_WORLD_MODAL_SPEC.submit.variant,
                )

    def on_mount(self) -> None:
        name_input = _maybe_query(self, f"#{NEW_WORLD_MODAL_SPEC.name.widget_id}", Input)
        if name_input is not None:
            name_input.focus()

    def _set_error(self, message: str | None) -> None:
        _set_form_error(self, f"#{NEW_WORLD_MODAL_SPEC.error_id}", message)

    @on(Button.Pressed, f"#{NEW_WORLD_MODAL_SPEC.submit.widget_id}")
    @on(Input.Submitted, f"#{NEW_WORLD_MODAL_SPEC.name.widget_id}")
    @on(Input.Submitted, f"#{NEW_WORLD_MODAL_SPEC.description.widget_id}")
    def _on_create(self) -> None:
        result = world_spec_from_form(
            name=self.query_one(f"#{NEW_WORLD_MODAL_SPEC.name.widget_id}", Input).value,
            provider_value=self.query_one(
                f"#{NEW_WORLD_MODAL_SPEC.provider.widget_id}", Select
            ).value,
            description=self.query_one(
                f"#{NEW_WORLD_MODAL_SPEC.description.widget_id}", Input
            ).value,
        )
        if result.error:
            self._set_error(result.error)
            return
        if result.spec is not None:
            self.dismiss(result.spec)

    @on(Button.Pressed, f"#{NEW_WORLD_MODAL_SPEC.cancel.widget_id}")
    def _on_cancel_button(self) -> None:
        self.dismiss(None)

    def action_cancel(self) -> None:
        self.dismiss(None)


class EditObjectScreen(ModalScreen[SceneObjectSpec | None]):
    """Collect name + position for a single scene object."""

    BINDINGS: ClassVar[list[Binding]] = [
        Binding(spec.key, spec.action, spec.description, show=spec.show)
        for spec in EDIT_OBJECT_BINDING_SPECS
    ]

    DEFAULT_CSS = _tui_styles.EDIT_OBJECT_SCREEN_DEFAULT_CSS

    def __init__(self, *, existing: SceneObjectSpec | None = None) -> None:
        super().__init__()
        self._existing = existing

    def compose(self) -> ComposeResult:
        default = self._existing or default_scene_object_spec()
        with Container(id=EDIT_OBJECT_MODAL_SPEC.card_id):
            yield Static(EDIT_OBJECT_MODAL_SPEC.title, id=EDIT_OBJECT_MODAL_SPEC.title_id)
            yield Static(EDIT_OBJECT_MODAL_SPEC.name.label, classes=FORM_FIELD_LABEL_CLASS)
            yield Input(
                value=default.name,
                placeholder=EDIT_OBJECT_MODAL_SPEC.name.placeholder,
                id=EDIT_OBJECT_MODAL_SPEC.name.widget_id,
            )
            yield Static(EDIT_OBJECT_MODAL_SPEC.position_label, classes=FORM_FIELD_LABEL_CLASS)
            yield Input(value=str(default.x), id=EDIT_OBJECT_MODAL_SPEC.x_id)
            yield Input(value=str(default.y), id=EDIT_OBJECT_MODAL_SPEC.y_id)
            yield Input(value=str(default.z), id=EDIT_OBJECT_MODAL_SPEC.z_id)
            yield Static("", id=EDIT_OBJECT_MODAL_SPEC.error_id, classes=FORM_HIDDEN_CLASS)
            with Horizontal(id=EDIT_OBJECT_MODAL_SPEC.actions_id):
                yield Button(
                    EDIT_OBJECT_MODAL_SPEC.cancel.label,
                    id=EDIT_OBJECT_MODAL_SPEC.cancel.widget_id,
                    variant=EDIT_OBJECT_MODAL_SPEC.cancel.variant,
                )
                yield Button(
                    EDIT_OBJECT_MODAL_SPEC.submit.label,
                    id=EDIT_OBJECT_MODAL_SPEC.submit.widget_id,
                    variant=EDIT_OBJECT_MODAL_SPEC.submit.variant,
                )

    def on_mount(self) -> None:
        name_input = _maybe_query(self, f"#{EDIT_OBJECT_MODAL_SPEC.name.widget_id}", Input)
        if name_input is not None:
            name_input.focus()

    def _set_error(self, message: str | None) -> None:
        _set_form_error(self, f"#{EDIT_OBJECT_MODAL_SPEC.error_id}", message)

    @on(Button.Pressed, f"#{EDIT_OBJECT_MODAL_SPEC.submit.widget_id}")
    def _on_save(self) -> None:
        result = scene_object_spec_from_form(
            name=self.query_one(f"#{EDIT_OBJECT_MODAL_SPEC.name.widget_id}", Input).value,
            x=self.query_one(f"#{EDIT_OBJECT_MODAL_SPEC.x_id}", Input).value,
            y=self.query_one(f"#{EDIT_OBJECT_MODAL_SPEC.y_id}", Input).value,
            z=self.query_one(f"#{EDIT_OBJECT_MODAL_SPEC.z_id}", Input).value,
        )
        if result.error:
            self._set_error(result.error)
            return
        if result.spec is not None:
            self.dismiss(result.spec)

    @on(Button.Pressed, f"#{EDIT_OBJECT_MODAL_SPEC.cancel.widget_id}")
    def _on_cancel_button(self) -> None:
        self.dismiss(None)

    def action_cancel(self) -> None:
        self.dismiss(None)


class WorldsScreen(Screen):
    """Table of persisted worlds plus a detail pane.

    Hosts the main Worlds CRUD loop: list → create / edit / fork / delete.
    Every disk-touching operation runs inside a ``persistence``-group worker so
    the UI thread never blocks on filesystem I/O.
    """

    BINDINGS: ClassVar[list[Binding]] = [
        Binding(spec.key, spec.action, spec.description, show=spec.show)
        for spec in WORLDS_BINDING_SPECS
    ]

    DEFAULT_CSS = _tui_styles.WORLDS_SCREEN_DEFAULT_CSS

    selected_world: reactive[str | None] = reactive(None, init=False)
    filter_query: reactive[str] = reactive("", init=False)

    def __init__(self, *, forge: WorldForge) -> None:
        super().__init__()
        self._forge = forge
        self._worlds: dict[str, World] = {}
        self._ordered_ids: list[str] = []

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        yield from _compose_chrome()
        with Container(id=WORLDS_SCREEN_SPEC.root_id):
            with Horizontal(id=WORLDS_SCREEN_SPEC.filter_row_id):
                yield Static(
                    WORLDS_SCREEN_SPEC.filter_label.text,
                    id=WORLDS_SCREEN_SPEC.filter_label.widget_id,
                )
                yield Input(
                    placeholder=WORLDS_SCREEN_SPEC.filter_input.placeholder,
                    id=WORLDS_SCREEN_SPEC.filter_input.widget_id,
                )
            with Horizontal(id=WORLDS_SCREEN_SPEC.body_id):
                with Container(id=WORLDS_SCREEN_SPEC.table_wrap_id):
                    yield DataTable(
                        zebra_stripes=True,
                        cursor_type="row",
                        id=WORLDS_SCREEN_SPEC.table.widget_id,
                    )
                    yield Static(
                        WORLDS_SCREEN_SPEC.empty.text,
                        id=WORLDS_SCREEN_SPEC.empty.widget_id,
                    )
                yield Static(
                    WORLDS_SCREEN_SPEC.detail.text,
                    id=WORLDS_SCREEN_SPEC.detail.widget_id,
                )
        yield Footer()

    def on_mount(self) -> None:
        table = self.query_one(WORLDS_TABLE_SELECTOR, DataTable)
        table.add_columns(*WORLDS_SCREEN_SPEC.table.columns)
        # Focus the table so the screen bindings (``n``, ``d``, ``f``, ``/``)
        # win over the filter ``Input`` at the top of the screen. The filter
        # focuses explicitly via ``/`` → ``action_focus_filter``.
        table.focus()
        self._update_chrome()
        self.refresh_worlds()

    def on_screen_resume(self) -> None:
        self._update_chrome()
        table = _maybe_query(self, WORLDS_TABLE_SELECTOR, DataTable)
        if table is not None:
            table.focus()
        # We intentionally avoid calling ``refresh_worlds`` here: screen
        # resume fires when a modal dismisses, and an exclusive persistence
        # worker started there would cancel an in-flight save/delete/fork
        # worker that just started from the modal's own callback. State
        # changes inside the app flow back via ``WorldSaved`` / ``WorldDeleted``
        # / ``WorldForked`` messages instead.

    def _update_chrome(self) -> None:
        selected = self.selected_world
        world = self._worlds.get(selected) if selected else None
        _apply_chrome(
            self,
            screen_chrome("worlds", provider_label=world.provider if world else ""),
        )

    # ------------------------------------------------------------------
    # Reactives
    # ------------------------------------------------------------------

    def watch_selected_world(self, _old: str | None, new: str | None) -> None:
        self._refresh_detail()
        self._update_chrome()

    def watch_filter_query(self, _old: str, _new: str) -> None:
        self._rebuild_table_rows()

    # ------------------------------------------------------------------
    # Persistence workers (group="persistence")
    # ------------------------------------------------------------------

    @work(thread=True, group="persistence", exclusive=True, name="list_worlds")
    def refresh_worlds(self) -> None:
        try:
            ids = self._forge.list_worlds()
            loaded = {world_id: self._forge.load_world(world_id) for world_id in ids}
        except (WorldForgeError, WorldStateError) as exc:
            self.app.call_from_thread(
                self._notify_error,
                f"Could not list worlds: {exc}",
            )
            return
        self.app.call_from_thread(self._apply_worlds, loaded, ids)

    def _apply_worlds(self, worlds: dict[str, World], ordered_ids: list[str]) -> None:
        self._worlds = worlds
        self._ordered_ids = list(ordered_ids)
        self._rebuild_table_rows()

    def _rebuild_table_rows(self) -> None:
        table = _maybe_query(self, WORLDS_TABLE_SELECTOR, DataTable)
        empty = _maybe_query(self, WORLDS_EMPTY_SELECTOR, Static)
        if table is None:
            return
        table.clear()
        name_map = {world_id: world.name for world_id, world in self._worlds.items()}
        filtered = filter_world_ids(self._ordered_ids, self.filter_query, name_map)
        for world_id in filtered:
            world = self._worlds[world_id]
            table.add_row(
                world.id,
                world.name,
                world.provider,
                str(world.step),
                "",
                key=world.id,
            )
        if not self._ordered_ids:
            if empty is not None:
                empty.remove_class("hidden")
            table.add_class("hidden")
        else:
            if empty is not None:
                empty.add_class("hidden")
            table.remove_class("hidden")
        if filtered:
            # Keep the cursor on the first visible row; drives the detail pane.
            self.selected_world = filtered[0]
        else:
            self.selected_world = None

    def _refresh_detail(self) -> None:
        detail = _maybe_query(self, WORLDS_DETAIL_SELECTOR, Static)
        if detail is None:
            return
        selected = self.selected_world
        world = self._worlds.get(selected) if selected else None
        if world is None:
            detail.update(WORLDS_SCREEN_SPEC.detail.text)
            return
        detail.update(format_detail_summary(world, state_dir=self._forge.state_dir))

    # ------------------------------------------------------------------
    # Events / actions
    # ------------------------------------------------------------------

    @on(DataTable.RowHighlighted, WORLDS_TABLE_SELECTOR)
    def _on_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        key = event.row_key.value if event.row_key else None
        if isinstance(key, str):
            self.selected_world = key

    @on(DataTable.RowSelected, WORLDS_TABLE_SELECTOR)
    def _on_row_selected(self, event: DataTable.RowSelected) -> None:
        key = event.row_key.value if event.row_key else None
        if isinstance(key, str):
            self.selected_world = key
            self.action_open_selected()

    @on(Input.Changed, f"#{WORLDS_FILTER_ID}")
    def _on_filter_changed(self, event: Input.Changed) -> None:
        self.filter_query = event.value

    @on(Input.Submitted, f"#{WORLDS_FILTER_ID}")
    def _on_filter_submitted(self) -> None:
        table = _maybe_query(self, WORLDS_TABLE_SELECTOR, DataTable)
        if table is not None:
            table.focus()

    def action_focus_filter(self) -> None:
        filt = _maybe_query(self, WORLDS_FILTER_SELECTOR, Input)
        if filt is not None:
            filt.focus()

    def action_clear_filter(self) -> None:
        filt = _maybe_query(self, WORLDS_FILTER_SELECTOR, Input)
        if filt is not None:
            filt.value = ""
        self.filter_query = ""
        table = _maybe_query(self, WORLDS_TABLE_SELECTOR, DataTable)
        if table is not None:
            table.focus()

    def action_refresh_worlds(self) -> None:
        self.refresh_worlds()

    def action_new_world(self) -> None:
        providers = tuple(self._forge.providers())
        self.app.push_screen(
            NewWorldScreen(providers=providers),
            self._handle_new_world_result,
        )

    def _handle_new_world_result(self, spec: WorldSpec | None) -> None:
        if spec is None:
            return
        try:
            world = self._forge.create_world(
                spec.name,
                provider=spec.provider,
                description=spec.description,
            )
        except WorldForgeError as exc:
            self._notify_error(str(exc))
            return
        self.app.push_screen(WorldEditScreen(forge=self._forge, world=world, is_new=True))

    def action_open_selected(self) -> None:
        if not self.selected_world:
            return
        world = self._worlds.get(self.selected_world)
        if world is None:
            return
        self.app.push_screen(WorldEditScreen(forge=self._forge, world=world, is_new=False))

    def action_delete_selected(self) -> None:
        if not self.selected_world:
            return
        world_id = self.selected_world
        self.app.push_screen(
            ConfirmDeleteScreen(
                title="Delete world?",
                prompt=(
                    f"The world '{world_id}' will be permanently removed from "
                    f"{self._forge.state_dir}."
                ),
            ),
            self._on_confirm_delete(world_id),
        )

    def _on_confirm_delete(self, world_id: str):
        def _callback(confirmed: bool | None) -> None:
            if not confirmed:
                return
            self._run_delete(world_id)

        return _callback

    @work(thread=True, group="persistence", exclusive=True, name="delete_world")
    def _run_delete(self, world_id: str) -> None:
        try:
            deleted_id = self._forge.delete_world(world_id)
        except (WorldForgeError, WorldStateError) as exc:
            self.app.call_from_thread(self._notify_error, f"Delete failed: {exc}")
            return
        self.app.call_from_thread(self.post_message, WorldDeleted(deleted_id))

    def on_world_deleted(self, event: WorldDeleted) -> None:
        event.stop()
        self._notify_success(f"Deleted world '{event.world_id}'.")
        self.refresh_worlds()

    def action_fork_selected(self) -> None:
        if not self.selected_world:
            return
        self._run_fork(self.selected_world)

    @work(thread=True, group="persistence", exclusive=True, name="fork_world")
    def _run_fork(self, source_id: str) -> None:
        try:
            fork = self._forge.fork_world(source_id, history_index=0)
        except (WorldForgeError, WorldStateError) as exc:
            self.app.call_from_thread(self._notify_error, f"Fork failed: {exc}")
            return
        self.app.call_from_thread(self.post_message, WorldForked(source_id, fork))

    def on_world_forked(self, event: WorldForked) -> None:
        event.stop()
        self._notify_success(f"Forked '{event.source_id}' → '{event.fork.id}'.")
        self.app.push_screen(WorldEditScreen(forge=self._forge, world=event.fork, is_new=True))

    def on_world_saved(self, event: WorldSaved) -> None:
        event.stop()
        self._notify_success(f"Saved world '{event.world_id}'.")
        self.refresh_worlds()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _notify_error(self, message: str) -> None:
        self.app.notify(message, severity="error", title="Worlds")

    def _notify_success(self, message: str) -> None:
        self.app.notify(message, severity="information", title="Worlds")


class WorldEditScreen(Screen):
    """Form editor for a single in-memory ``World`` + single-shot preview pane."""

    BINDINGS: ClassVar[list[Binding]] = [
        Binding(spec.key, spec.action, spec.description, show=spec.show)
        for spec in WORLD_EDIT_BINDING_SPECS
    ]

    DEFAULT_CSS = _tui_styles.WORLD_EDIT_SCREEN_DEFAULT_CSS

    dirty: reactive[bool] = reactive(False, init=False)
    staged_action: reactive[Action | None] = reactive(None, init=False)

    def __init__(self, *, forge: WorldForge, world: World, is_new: bool) -> None:
        super().__init__()
        self._forge = forge
        self._world = world
        self._is_new = is_new
        # Keep an original-snapshot clone (unless new) for dirty detection.
        self._original = None if is_new else clone_world(world)

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        yield from _compose_chrome()
        with Container(id=WORLD_EDIT_SCREEN_SPEC.root_id):
            yield Static(
                self._render_title(),
                id=WORLD_EDIT_SCREEN_SPEC.title.widget_id,
            )
            with Horizontal(id=WORLD_EDIT_SCREEN_SPEC.body_id):
                with Container(id=WORLD_EDIT_SCREEN_SPEC.form_id):
                    yield Static(
                        WORLD_EDIT_SCREEN_SPEC.name_label.text,
                        classes=FORM_FIELD_LABEL_CLASS,
                    )
                    yield Input(
                        value=self._world.name,
                        id=WORLD_EDIT_SCREEN_SPEC.name.widget_id,
                    )
                    yield Static(
                        WORLD_EDIT_SCREEN_SPEC.provider_label.text,
                        classes=FORM_FIELD_LABEL_CLASS,
                    )
                    yield Select(
                        [(name, name) for name in self._forge.providers()],
                        value=self._world.provider,
                        allow_blank=False,
                        id=WORLD_EDIT_SCREEN_SPEC.provider.widget_id,
                    )
                    yield Static(
                        WORLD_EDIT_SCREEN_SPEC.objects_header.text,
                        id=WORLD_EDIT_SCREEN_SPEC.objects_header.widget_id,
                    )
                    yield OptionList(id=WORLD_EDIT_SCREEN_SPEC.objects.widget_id)
                with Container(id=WORLD_EDIT_SCREEN_SPEC.preview.widget_id):
                    yield Static(
                        WORLD_EDIT_SCREEN_SPEC.preview_caption.text,
                        id=WORLD_EDIT_SCREEN_SPEC.preview_caption.widget_id,
                    )
                    yield Static(
                        WORLD_EDIT_SCREEN_SPEC.preview_body.text,
                        id=WORLD_EDIT_SCREEN_SPEC.preview_body.widget_id,
                    )
        yield Footer()

    def _render_title(self) -> str:
        return world_edit_title(self._world, dirty=self.dirty, is_new=self._is_new)

    def on_mount(self) -> None:
        self._update_chrome()
        self._populate_objects()
        self._refresh_preview_static()
        self.dirty = self._is_new or is_dirty(self._original, self._world)
        # Focus the object list so the screen-level ``a``/``delete`` bindings
        # fire before the name ``Input`` swallows them. The user can press
        # ``Tab`` (or click) to move to the name field when renaming.
        options = _maybe_query(self, WORLD_EDIT_OBJECTS_SELECTOR, OptionList)
        if options is not None:
            options.focus()

    def on_screen_resume(self) -> None:
        self._update_chrome()

    def _update_chrome(self) -> None:
        _apply_chrome(
            self,
            screen_chrome("worlds", "edit", self._world.name, provider_label=self._world.provider),
        )

    def _populate_objects(self) -> None:
        options = _maybe_query(self, WORLD_EDIT_OBJECTS_SELECTOR, OptionList)
        if options is None:
            return
        options.clear_options()
        for label, option_id in scene_object_options(self._world):
            options.add_option(Option(label, id=option_id))

    def _refresh_preview_static(self) -> None:
        caption = _maybe_query(self, WORLD_EDIT_PREVIEW_CAPTION_SELECTOR, Static)
        body = _maybe_query(self, WORLD_EDIT_PREVIEW_BODY_SELECTOR, Static)
        preview = _maybe_query(self, WORLD_EDIT_PREVIEW_SELECTOR, Container)
        if body is None or caption is None or preview is None:
            return
        staged = self.staged_action is not None
        caption.update(edit_preview_caption(staged=staged))
        if staged:
            caption.remove_class("hidden")
            preview.add_class("-staged")
        else:
            caption.remove_class("hidden")
            preview.remove_class("-staged")
        body.update(format_detail_summary(self._world, state_dir=self._forge.state_dir))

    # ------------------------------------------------------------------
    # Reactives
    # ------------------------------------------------------------------

    def watch_dirty(self, _old: bool, _new: bool) -> None:
        title = _maybe_query(self, WORLD_EDIT_TITLE_SELECTOR, Static)
        if title is not None:
            title.update(self._render_title())

    def watch_staged_action(self, _old: Action | None, _new: Action | None) -> None:
        self._refresh_preview_static()

    # ------------------------------------------------------------------
    # Input events
    # ------------------------------------------------------------------

    @on(Input.Changed, f"#{WORLD_EDIT_NAME_ID}")
    def _on_name_changed(self, event: Input.Changed) -> None:
        if not apply_world_name_edit(self._world, event.value):
            return
        self.dirty = True
        title = _maybe_query(self, WORLD_EDIT_TITLE_SELECTOR, Static)
        if title is not None:
            title.update(self._render_title())

    @on(Select.Changed, f"#{WORLD_EDIT_PROVIDER_ID}")
    def _on_provider_changed(self, event: Select.Changed) -> None:
        provider = apply_world_provider_edit(self._world, event.value)
        if provider is None:
            return
        self.dirty = True
        self._update_chrome()

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    def action_add_object(self) -> None:
        self.app.push_screen(EditObjectScreen(), self._handle_object_result)

    def _handle_object_result(self, spec: SceneObjectSpec | None) -> None:
        if spec is None:
            return
        try:
            staged_action = add_scene_object_from_spec(self._world, spec)
        except WorldForgeError as exc:
            self.app.notify(str(exc), severity="error", title="Scene object")
            return
        self.dirty = True
        self._populate_objects()
        # Stage a spawn action so the preview pane reflects the addition.
        self.staged_action = staged_action
        self._run_preview()

    def action_remove_object(self) -> None:
        options = _maybe_query(self, WORLD_EDIT_OBJECTS_SELECTOR, OptionList)
        if options is None:
            return
        highlighted = options.highlighted
        if highlighted is None:
            return
        option = options.get_option_at_index(highlighted)
        if remove_scene_object_by_id(self._world, option.id):
            self.dirty = True
            self._populate_objects()
            self._refresh_preview_static()

    def action_predict_preview(self) -> None:
        self._run_preview()

    @work(thread=True, group="provider", exclusive=True, name="predict_preview")
    def _run_preview(self) -> None:
        action = self.staged_action
        if action is None:
            return
        try:
            # Single-shot preview: we only render the detail summary; the
            # mutation has already been applied in-memory by ``add_object``.
            provider = self._forge._require_provider(self._world.provider)
            with suppress(Exception):  # pragma: no cover - optional providers
                provider.predict(self._world._snapshot(), action, 1)
        finally:
            self.app.call_from_thread(self._refresh_preview_static)

    # ------------------------------------------------------------------
    # Save + close
    # ------------------------------------------------------------------

    def action_save_world(self) -> None:
        self._run_save()

    @work(thread=True, group="persistence", exclusive=True, name="save_world")
    def _run_save(self) -> None:
        try:
            world_id = self._forge.save_world(self._world)
        except (WorldForgeError, WorldStateError) as exc:
            self.app.call_from_thread(
                self.app.notify,
                str(exc),
                severity="error",
                title="Save failed",
            )
            return
        self.app.call_from_thread(self._handle_save_success, world_id)

    def _handle_save_success(self, world_id: str) -> None:
        self._is_new = False
        self._original = clone_world(self._world)
        self.dirty = False
        self.app.notify(f"Saved world '{world_id}'.", severity="information", title="Save")
        self.post_message(WorldSaved(world_id))

    def action_close(self) -> None:
        if self.dirty:
            self.app.push_screen(
                ConfirmDeleteScreen(
                    title="Discard changes?",
                    prompt="Unsaved changes will be lost.",
                    confirm_label="Discard",
                ),
                self._on_confirm_close,
            )
            return
        self._pop_to_worlds()

    def _on_confirm_close(self, confirmed: bool | None) -> None:
        if confirmed:
            self._pop_to_worlds()

    def _pop_to_worlds(self) -> None:
        self.workers.cancel_group(self, "persistence")
        self.workers.cancel_group(self, "provider")
        self.app.pop_screen()


# ---------------------------------------------------------------------------
# Providers, eval, and benchmark screens
# ---------------------------------------------------------------------------


class RegisterProviderModal(  # pragma: no cover - exercised by Pilot tests.
    ModalScreen[MockProvider | None]
):
    """Register a deterministic mock provider variant for local testing."""

    BINDINGS: ClassVar[list[Binding]] = [
        Binding(spec.key, spec.action, spec.description, show=spec.show)
        for spec in REGISTER_PROVIDER_BINDING_SPECS
    ]

    DEFAULT_CSS = _tui_styles.REGISTER_PROVIDER_MODAL_DEFAULT_CSS

    def compose(self) -> ComposeResult:
        with Container(id=REGISTER_PROVIDER_MODAL_SPEC.card_id):
            yield Static(
                REGISTER_PROVIDER_MODAL_SPEC.title,
                id=REGISTER_PROVIDER_MODAL_SPEC.title_id,
            )
            yield Static(
                REGISTER_PROVIDER_MODAL_SPEC.name.label,
                classes=PROVIDER_FIELD_LABEL_CLASS,
            )
            yield Input(
                placeholder=REGISTER_PROVIDER_MODAL_SPEC.name.placeholder,
                id=REGISTER_PROVIDER_MODAL_SPEC.name.widget_id,
            )
            yield Static(
                REGISTER_PROVIDER_MODAL_SPEC.note,
                id=REGISTER_PROVIDER_MODAL_SPEC.note_id,
            )
            with Horizontal(id=REGISTER_PROVIDER_MODAL_SPEC.actions_id):
                yield Button(
                    REGISTER_PROVIDER_MODAL_SPEC.cancel.label,
                    id=REGISTER_PROVIDER_MODAL_SPEC.cancel.widget_id,
                    variant=REGISTER_PROVIDER_MODAL_SPEC.cancel.variant,
                )
                yield Button(
                    REGISTER_PROVIDER_MODAL_SPEC.submit.label,
                    id=REGISTER_PROVIDER_MODAL_SPEC.submit.widget_id,
                    variant=REGISTER_PROVIDER_MODAL_SPEC.submit.variant,
                )

    def on_mount(self) -> None:
        name = _maybe_query(self, f"#{REGISTER_PROVIDER_MODAL_SPEC.name.widget_id}", Input)
        if name is not None:
            name.focus()

    @on(Button.Pressed, f"#{REGISTER_PROVIDER_MODAL_SPEC.submit.widget_id}")
    @on(Input.Submitted, f"#{REGISTER_PROVIDER_MODAL_SPEC.name.widget_id}")
    def _submit(self) -> None:
        result = provider_registration_from_form(
            self.query_one(f"#{REGISTER_PROVIDER_MODAL_SPEC.name.widget_id}", Input).value
        )
        if result.error:
            self.app.notify(result.error, severity="error", title="Provider")
            return
        if result.provider_name is not None:
            self.dismiss(MockProvider(name=result.provider_name))

    @on(Button.Pressed, f"#{REGISTER_PROVIDER_MODAL_SPEC.cancel.widget_id}")
    def _cancel_button(self) -> None:
        self.dismiss(None)

    def action_cancel(self) -> None:
        self.dismiss(None)


class ProvidersScreen(Screen):  # pragma: no cover - exercised by Pilot tests.
    """Capability matrix and live ``mock.predict`` execution surface."""

    BINDINGS: ClassVar[list[Binding]] = [
        Binding(spec.key, spec.action, spec.description, show=spec.show)
        for spec in PROVIDER_BINDING_SPECS
    ]

    DEFAULT_CSS = _tui_styles.PROVIDERS_SCREEN_DEFAULT_CSS

    current_row_provider: reactive[str | None] = reactive(None, init=False)
    running_operation: reactive[str] = reactive("idle", init=False)

    def __init__(self, *, forge: WorldForge) -> None:
        super().__init__()
        self._forge = forge
        self._provider_names: list[str] = []
        self._provider_rows: dict[str, ProviderConnectorSummary] = {}
        self._last_call_summary: dict[str, dict[str, Any]] = {}

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        yield from _compose_chrome()
        with Container(id=PROVIDER_SCREEN_SPEC.root_id):
            with Horizontal(id=PROVIDER_SCREEN_SPEC.body_id):
                with Container(id=PROVIDER_SCREEN_SPEC.table_wrap_id):
                    yield DataTable(
                        zebra_stripes=True,
                        cursor_type="row",
                        id=PROVIDER_SCREEN_SPEC.table.widget_id,
                    )
                    yield Static(
                        PROVIDER_SCREEN_SPEC.empty.message,
                        id=PROVIDER_SCREEN_SPEC.empty.widget_id,
                        classes="hidden",
                    )
                yield Static(
                    PROVIDER_SCREEN_SPEC.detail.message,
                    id=PROVIDER_SCREEN_SPEC.detail.widget_id,
                )
            yield RichLog(
                highlight=True,
                markup=True,
                max_lines=PROVIDER_SCREEN_SPEC.log.max_lines,
                id=PROVIDER_SCREEN_SPEC.log.widget_id,
            )
            with Horizontal(id=PROVIDER_SCREEN_SPEC.actions_id):
                for spec in PROVIDER_ACTION_SPECS:
                    yield Button(spec.label, id=spec.widget_id, variant=spec.variant)
        yield Footer()

    def on_mount(self) -> None:
        self._update_chrome()
        self._build_table()

    def on_screen_resume(self) -> None:
        self._update_chrome()

    def _update_chrome(self) -> None:
        provider = getattr(self.app, "current_provider", "mock")
        _apply_chrome(
            self,
            screen_chrome(
                "providers",
                provider_label=provider_capability_label(provider, "predict"),
            ),
        )

    def _build_table(self) -> None:
        table = _maybe_query(self, PROVIDER_TABLE_SELECTOR, DataTable)
        empty = _maybe_query(self, PROVIDER_EMPTY_SELECTOR, Static)
        if table is None:
            return
        table.clear(columns=True)
        table.add_columns(*PROVIDER_SCREEN_SPEC.table.columns)
        rows = provider_connector_summaries(self._forge)
        self._provider_rows = {row.name: row for row in rows}
        self._provider_names = [row.name for row in rows]
        for row in rows:
            table.add_row(*provider_table_row(row), key=row.name)
        if rows:
            table.remove_class("hidden")
            if empty is not None:
                empty.add_class("hidden")
            table.focus()
            self.current_row_provider = rows[0].name
        else:
            table.add_class("hidden")
            if empty is not None:
                empty.remove_class("hidden")
            self.current_row_provider = None
        self._refresh_detail()

    @on(DataTable.RowHighlighted, PROVIDER_TABLE_SELECTOR)
    def _on_provider_highlighted(self, event: DataTable.RowHighlighted) -> None:
        key = event.row_key.value if event.row_key else None
        if isinstance(key, str):
            self.current_row_provider = key

    def watch_current_row_provider(self, _old: str | None, _new: str | None) -> None:
        self._refresh_detail()

    def _refresh_detail(self) -> None:
        detail = _maybe_query(self, PROVIDER_DETAIL_SELECTOR, Static)
        if detail is None:
            return
        provider = self.current_row_provider
        row = self._provider_rows.get(provider) if provider is not None else None
        detail.update(
            provider_connector_detail_text(
                row,
                last_call_summary=self._last_call_summary.get(provider or ""),
            )
        )

    def action_select_provider(self) -> None:
        if self.current_row_provider is None:
            return
        self.app.current_provider = self.current_row_provider  # type: ignore[attr-defined]
        self._update_chrome()
        self.app.notify(
            f"Current provider: {self.current_row_provider}",
            severity="information",
            title="Provider",
        )

    def action_run_predict(self) -> None:
        provider = provider_predict_target(
            current_provider=getattr(self.app, "current_provider", "mock"),
            current_row_provider=self.current_row_provider,
            provider_names=self._provider_names,
        )
        self._run_predict(provider)

    @on(Button.Pressed, f"#{PROVIDER_RUN_BUTTON_ID}")
    def _run_button(self) -> None:
        self.action_run_predict()

    @on(Button.Pressed, f"#{PROVIDER_CANCEL_BUTTON_ID}")
    def _cancel_button(self) -> None:
        self.action_cancel_or_back()

    @on(Button.Pressed, f"#{PROVIDER_REGISTER_BUTTON_ID}")
    def _register_button(self) -> None:
        self.action_register_provider()

    def action_cancel_or_back(self) -> None:
        if self.running_operation == "running":
            self.workers.cancel_group(self, "provider")
            self.running_operation = "cancelled"
            provider = provider_cancel_target(
                current_provider=getattr(self.app, "current_provider", "mock"),
                current_row_provider=self.current_row_provider,
            )
            self.post_message(RunCancelled(provider=provider))
            return
        self.app.action_switch_screen("home")

    def action_register_provider(self) -> None:
        self.app.push_screen(RegisterProviderModal(), self._handle_registered_provider)

    def _handle_registered_provider(self, provider: MockProvider | None) -> None:
        if provider is None:
            return
        self._forge.register_provider(provider)
        self.app.current_provider = provider.name  # type: ignore[attr-defined]
        self._build_table()
        self.app.notify(f"Registered provider '{provider.name}'.", title="Provider")

    @work(thread=True, group="provider", exclusive=True, name="provider.predict")
    def _run_predict(self, provider_name: str) -> None:
        worker = get_current_worker()
        self.app.call_from_thread(setattr, self, "running_operation", "running")
        self.app.call_from_thread(self._clear_provider_events)
        try:
            world = self._forge.create_world("scratch", provider=provider_name)
            prediction = world.predict(Action("noop"), steps=1, provider=provider_name)
        except (ProviderError, WorldForgeError) as exc:
            self.app.call_from_thread(
                self.post_message,
                ProviderEventReceived(_provider_event_failure(provider_name, "predict", exc)),
            )
            self.app.call_from_thread(setattr, self, "running_operation", "error")
            return
        if worker.is_cancelled:
            self.app.call_from_thread(self.post_message, RunCancelled(provider=provider_name))
            return
        self.app.call_from_thread(self._drain_provider_events)
        self.app.call_from_thread(
            self.post_message,
            RunCompleted(provider=provider_name, latency_ms=prediction.latency_ms),
        )

    def _clear_provider_events(self) -> None:
        if hasattr(self.app, "drain_provider_events"):
            self.app.drain_provider_events()  # type: ignore[attr-defined]

    def _drain_provider_events(self) -> None:
        events = (
            self.app.drain_provider_events()  # type: ignore[attr-defined]
            if hasattr(self.app, "drain_provider_events")
            else ()
        )
        for event in events:
            self.post_message(ProviderEventReceived(event))

    def on_provider_event_received(self, event: ProviderEventReceived) -> None:
        event.stop()
        log = _maybe_query(self, PROVIDER_LOG_SELECTOR, RichLog)
        if log is not None:
            log.write(_format_provider_event(event.event))
        self._last_call_summary[event.event.provider] = _event_summary(event.event)
        self._refresh_detail()

    def on_run_completed(self, event: RunCompleted) -> None:
        event.stop()
        self.running_operation = "done"
        self._last_call_summary[event.provider] = provider_success_summary(event.latency_ms)
        self._refresh_detail()
        self.app.notify(
            f"{event.provider}.predict completed in {event.latency_ms:.2f} ms.",
            title="Provider",
        )

    def on_run_cancelled(self, event: RunCancelled) -> None:
        event.stop()
        self.running_operation = "cancelled"
        log = _maybe_query(self, PROVIDER_LOG_SELECTOR, RichLog)
        if log is not None:
            log.write(Text("cancelled provider run", style="bold yellow"))
        self.app.notify("Cancelled provider run.", severity="warning", title="Provider")


class EvalScreen(Screen):  # pragma: no cover - exercised by Pilot tests.
    """Run built-in deterministic evaluation suites from the TUI."""

    BINDINGS: ClassVar[list[Binding]] = [
        Binding(spec.key, spec.action, spec.description, show=spec.show)
        for spec in EVAL_BINDING_SPECS
    ]

    DEFAULT_CSS = _tui_styles.EVAL_SCREEN_DEFAULT_CSS

    running: reactive[bool] = reactive(False, init=False)

    def __init__(self, *, forge: WorldForge) -> None:
        super().__init__()
        self._forge = forge

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        yield from _compose_chrome()
        with Horizontal(id=EVAL_SCREEN_SPEC.root_id):
            with Vertical(id=EVAL_SCREEN_SPEC.form_id):
                yield Static(EVAL_SCREEN_SPEC.suite.label)
                yield Select(
                    [(suite, suite) for suite in list_eval_suites()],
                    value=EVAL_SCREEN_SPEC.suite.default,
                    allow_blank=False,
                    id=EVAL_SCREEN_SPEC.suite.widget_id,
                )
                yield Static(EVAL_SCREEN_SPEC.provider.label)
                yield Select(
                    [(provider, provider) for provider in self._forge.providers()],
                    value=getattr(self.app, "current_provider", "mock"),
                    allow_blank=False,
                    id=EVAL_SCREEN_SPEC.provider.widget_id,
                )
                yield Button(
                    EVAL_SCREEN_SPEC.run.label,
                    id=EVAL_SCREEN_SPEC.run.widget_id,
                    variant=EVAL_SCREEN_SPEC.run.variant,
                )
            with Vertical(id=EVAL_SCREEN_SPEC.output_id):
                yield Static(
                    EVAL_SCREEN_SPEC.verdict.empty_message,
                    id=EVAL_SCREEN_SPEC.verdict.widget_id,
                )
                yield RichLog(
                    highlight=True,
                    markup=True,
                    max_lines=EVAL_SCREEN_SPEC.log.max_lines,
                    id=EVAL_SCREEN_SPEC.log.widget_id,
                )
                yield ExportPane(widget_id=EVAL_SCREEN_SPEC.completion.export_widget_id)
        yield Footer()

    def on_mount(self) -> None:
        self._update_chrome()

    def _update_chrome(self) -> None:
        provider = getattr(self.app, "current_provider", "mock")
        _apply_chrome(
            self,
            screen_chrome("eval", provider_label=provider_capability_label(provider, "eval")),
        )

    @on(Button.Pressed, f"#{EVAL_RUN_BUTTON_ID}")
    def _run_button(self) -> None:
        self.action_run_eval()

    def action_run_eval(self) -> None:
        request = eval_request_from_form(
            suite_value=self.query_one(f"#{EVAL_SCREEN_SPEC.suite.widget_id}", Select).value,
            provider_value=self.query_one(f"#{EVAL_SCREEN_SPEC.provider.widget_id}", Select).value,
        )
        if request is not None:
            self._run_eval(request.suite_id, request.provider)

    def action_cancel_or_back(self) -> None:
        if _cancel_report_or_back(
            self,
            running=self.running,
            run_control=EVAL_SCREEN_SPEC.run_control,
        ):
            self.running = False
            return

    @work(
        thread=True,
        group=EVAL_SCREEN_SPEC.run_control.worker_group,
        exclusive=True,
        name=EVAL_SCREEN_SPEC.run_control.worker_name,
    )
    def _run_eval(self, suite_id: str, provider: str) -> None:
        self.app.call_from_thread(setattr, self, "running", True)
        self.app.call_from_thread(self._write_eval_log, eval_running_log_line(suite_id, provider))
        try:
            artifacts, report = eval_run_artifacts(self._forge, suite_id, provider)
            path = write_report(self._forge, f"eval-{suite_id}", artifacts)
        except WorldForgeError as exc:
            self.app.call_from_thread(self.post_message, CapabilityMismatch(exc))
            self.app.call_from_thread(setattr, self, "running", False)
            return
        if get_current_worker().is_cancelled:
            self.app.call_from_thread(setattr, self, "running", False)
            return
        run = eval_report_harness_run(
            suite_id,
            artifacts,
            report.to_dict(),
            path=path,
            state_dir=self._forge.state_dir,
        )
        self.app.call_from_thread(self._complete_report_run, run, artifacts, path)

    def _write_eval_log(self, line: str | Text) -> None:
        log = _maybe_query(self, EVAL_LOG_SELECTOR, RichLog)
        if log is not None:
            log.write(line)

    def _complete_report_run(
        self,
        run: HarnessRun,
        artifacts: dict[str, str],
        path: Path,
    ) -> None:
        self.running = False
        _complete_report_run(
            self,
            forge=self._forge,
            completion=EVAL_SCREEN_SPEC.completion,
            run=run,
            artifacts=artifacts,
            path=path,
        )

    def on_capability_mismatch(self, event: CapabilityMismatch) -> None:
        _handle_capability_mismatch(
            self,
            event,
            run_control=EVAL_SCREEN_SPEC.run_control,
            log_selector=EVAL_LOG_SELECTOR,
        )


class BenchmarkScreen(Screen):  # pragma: no cover - exercised by Pilot tests.
    """Run capability-aware provider benchmarks from the TUI."""

    BINDINGS: ClassVar[list[Binding]] = [
        Binding(spec.key, spec.action, spec.description, show=spec.show)
        for spec in BENCHMARK_BINDING_SPECS
    ]

    DEFAULT_CSS = _tui_styles.BENCHMARK_SCREEN_DEFAULT_CSS

    running: reactive[bool] = reactive(False, init=False)

    def __init__(self, *, forge: WorldForge) -> None:
        super().__init__()
        self._forge = forge
        self._samples: list[float] = []

    def compose(self) -> ComposeResult:
        provider = getattr(self.app, "current_provider", "mock")
        yield Header(show_clock=True)
        yield from _compose_chrome()
        with Horizontal(id=BENCHMARK_SCREEN_SPEC.root_id):
            with Vertical(id=BENCHMARK_SCREEN_SPEC.form_id):
                yield Static(BENCHMARK_SCREEN_SPEC.provider.label)
                yield Select(
                    [(name, name) for name in self._forge.providers()],
                    value=provider,
                    allow_blank=False,
                    id=BENCHMARK_SCREEN_SPEC.provider.widget_id,
                )
                yield Static(BENCHMARK_SCREEN_SPEC.operation.label)
                yield Select(
                    [(operation, operation) for operation in BENCHMARKABLE_OPERATIONS],
                    value=BENCHMARK_SCREEN_SPEC.operation.default,
                    allow_blank=False,
                    id=BENCHMARK_SCREEN_SPEC.operation.widget_id,
                )
                yield Static(BENCHMARK_SCREEN_SPEC.iterations.label)
                yield Input(
                    value=BENCHMARK_SCREEN_SPEC.iterations.default,
                    id=BENCHMARK_SCREEN_SPEC.iterations.widget_id,
                )
                yield Button(
                    BENCHMARK_SCREEN_SPEC.run.label,
                    id=BENCHMARK_SCREEN_SPEC.run.widget_id,
                    variant=BENCHMARK_SCREEN_SPEC.run.variant,
                )
            with Vertical(id=BENCHMARK_SCREEN_SPEC.output_id):
                yield Static(
                    BENCHMARK_SCREEN_SPEC.stats.empty_message,
                    id=BENCHMARK_SCREEN_SPEC.stats.widget_id,
                )
                yield ProgressBar(
                    total=DEFAULT_BENCHMARK_ITERATIONS,
                    id=BENCHMARK_SCREEN_SPEC.progress_id,
                )
                yield RichLog(
                    highlight=True,
                    markup=True,
                    max_lines=BENCHMARK_SCREEN_SPEC.log.max_lines,
                    id=BENCHMARK_SCREEN_SPEC.log.widget_id,
                )
                yield ExportPane(widget_id=BENCHMARK_SCREEN_SPEC.completion.export_widget_id)
        yield Footer()

    def on_mount(self) -> None:
        self._update_chrome()

    def _update_chrome(self) -> None:
        provider = getattr(self.app, "current_provider", "mock")
        _apply_chrome(
            self,
            screen_chrome(
                "benchmark",
                provider_label=provider_capability_label(provider, "benchmark"),
            ),
        )

    @on(Button.Pressed, f"#{BENCHMARK_RUN_BUTTON_ID}")
    def _run_button(self) -> None:
        self.action_run_benchmark()

    def action_run_benchmark(self) -> None:
        result = benchmark_request_from_form(
            provider_value=self.query_one(
                f"#{BENCHMARK_SCREEN_SPEC.provider.widget_id}", Select
            ).value,
            operation_value=self.query_one(
                f"#{BENCHMARK_SCREEN_SPEC.operation.widget_id}", Select
            ).value,
            iterations_value=self.query_one(
                f"#{BENCHMARK_SCREEN_SPEC.iterations.widget_id}", Input
            ).value,
        )
        if result.error:
            self.app.notify(result.error, severity="error", title="Benchmark")
            return
        if result.request is None:
            return
        progress = _maybe_query(self, f"#{BENCHMARK_SCREEN_SPEC.progress_id}", ProgressBar)
        if progress is not None:
            progress.total = result.request.iterations
            progress.progress = 0
        self._samples = []
        self._run_benchmark(
            result.request.provider,
            result.request.operation,
            result.request.iterations,
        )

    def action_cancel_or_back(self) -> None:
        if _cancel_report_or_back(
            self,
            running=self.running,
            run_control=BENCHMARK_SCREEN_SPEC.run_control,
        ):
            self.running = False
            return

    @work(
        thread=True,
        group=BENCHMARK_SCREEN_SPEC.run_control.worker_group,
        exclusive=True,
        name=BENCHMARK_SCREEN_SPEC.run_control.worker_name,
    )
    def _run_benchmark(self, provider: str, operation: str, iterations: int) -> None:
        self.app.call_from_thread(setattr, self, "running", True)

        def on_sample(sample: JSONDict) -> None:
            self.app.call_from_thread(self._record_benchmark_sample, sample, iterations)

        try:
            artifacts, report = benchmark_run_artifacts(
                self._forge,
                provider,
                operations=(operation,),
                iterations=iterations,
                concurrency=1,
                on_sample=on_sample,
            )
            path = write_report(self._forge, "benchmark", artifacts)
        except WorldForgeError as exc:
            self.app.call_from_thread(self.post_message, CapabilityMismatch(exc))
            self.app.call_from_thread(setattr, self, "running", False)
            return
        if get_current_worker().is_cancelled:
            self.app.call_from_thread(setattr, self, "running", False)
            return
        run = benchmark_report_harness_run(
            artifacts,
            report.to_dict(),
            path=path,
            state_dir=self._forge.state_dir,
        )
        self.app.call_from_thread(self._complete_report_run, run, artifacts, path)

    def _record_benchmark_sample(self, sample: JSONDict, total: int) -> None:
        view = benchmark_sample_progress(sample, self._samples, total=total)
        self._samples = list(view.samples)
        progress = _maybe_query(self, f"#{BENCHMARK_SCREEN_SPEC.progress_id}", ProgressBar)
        if progress is not None:
            progress.progress = view.progress_count
        log = _maybe_query(self, BENCHMARK_LOG_SELECTOR, RichLog)
        if log is not None:
            log.write(view.log_line)
        stats = _maybe_query(self, f"#{BENCHMARK_SCREEN_SPEC.stats.widget_id}", Static)
        if stats is not None:
            stats.update(view.stats_line)

    def _complete_report_run(
        self,
        run: HarnessRun,
        artifacts: dict[str, str],
        path: Path,
    ) -> None:
        self.running = False
        _complete_report_run(
            self,
            forge=self._forge,
            completion=BENCHMARK_SCREEN_SPEC.completion,
            run=run,
            artifacts=artifacts,
            path=path,
        )

    def on_capability_mismatch(self, event: CapabilityMismatch) -> None:
        _handle_capability_mismatch(
            self,
            event,
            run_control=BENCHMARK_SCREEN_SPEC.run_control,
            log_selector=BENCHMARK_LOG_SELECTOR,
        )


# ---------------------------------------------------------------------------
# Robotics Replay Showcase Report
# ---------------------------------------------------------------------------

# Compatibility names kept on ``worldforge.harness.tui`` for existing tests
# and callers; implementation lives in a Textual-free helper module.
ROBOTICS_REPORT_GUIDE_ROWS = _robotics_view.ROBOTICS_REPORT_GUIDE_ROWS
ROBOTICS_TABLETOP_DIAGRAM = _robotics_view.ROBOTICS_TABLETOP_DIAGRAM
ROBOTICS_TABLETOP_GOAL = _robotics_view.ROBOTICS_TABLETOP_GOAL
ROBOTICS_TABLETOP_HEIGHT = _robotics_view.ROBOTICS_TABLETOP_HEIGHT
ROBOTICS_TABLETOP_HELP_BINDING_SPECS = _robotics_view.ROBOTICS_TABLETOP_HELP_BINDING_SPECS
ROBOTICS_TABLETOP_HELP_SCREEN_SPEC = _robotics_view.ROBOTICS_TABLETOP_HELP_SCREEN_SPEC
ROBOTICS_TABLETOP_HELP_TEXT = _robotics_view.ROBOTICS_TABLETOP_HELP_TEXT
ROBOTICS_TABLETOP_START = _robotics_view.ROBOTICS_TABLETOP_START
ROBOTICS_TABLETOP_WIDTH = _robotics_view.ROBOTICS_TABLETOP_WIDTH
ROBOTICS_SHOWCASE_APP_SPEC = _robotics_view.ROBOTICS_SHOWCASE_APP_SPEC
ROBOTICS_SHOWCASE_BODY_SELECTOR = _robotics_view.ROBOTICS_SHOWCASE_BODY_SELECTOR
ROBOTICS_TENSORBOARD_DEFAULT_PORT = _robotics_view.ROBOTICS_TENSORBOARD_DEFAULT_PORT
ROBOTICS_TENSORBOARD_POLL_INTERVAL_S = _robotics_view.ROBOTICS_TENSORBOARD_POLL_INTERVAL_S
ROBOTICS_TENSORBOARD_READY_TIMEOUT_S = _robotics_view.ROBOTICS_TENSORBOARD_READY_TIMEOUT_S
ROBOTICS_TENSORBOARD_STDERR_LOG = _robotics_view.ROBOTICS_TENSORBOARD_STDERR_LOG
ROBOTICS_TENSORBOARD_STDOUT_LOG = _robotics_view.ROBOTICS_TENSORBOARD_STDOUT_LOG
_robotics_candidate_targets = _robotics_view.robotics_candidate_targets
_robotics_event_duration = _robotics_view.robotics_event_duration
_robotics_final_position = _robotics_view.robotics_final_position
_robotics_nested = _robotics_view.robotics_nested
_robotics_number = _robotics_view.robotics_number
_robotics_rerun_recording_path = _robotics_view.robotics_rerun_recording_path
_robotics_scores = _robotics_view.robotics_scores
_robotics_selected_index = _robotics_view.robotics_selected_index
_robotics_tabletop_map_lines = _robotics_view.robotics_tabletop_map_lines
_robotics_tensorboard_log_dir = _robotics_view.robotics_tensorboard_log_dir
_tensorboard_port_open = _robotics_view.tensorboard_port_open
subprocess = _robotics_launch.subprocess
webbrowser = _robotics_launch.webbrowser


class RoboticsHeroPane(Static, _ThemedRenderer):
    """Top-level real robotics showcase identity and run contract."""

    def __init__(self, summary: dict[str, object], summary_path: Path | None) -> None:
        super().__init__()
        self.summary = summary
        self.summary_path = summary_path

    def on_mount(self) -> None:
        self.update(robotics_hero_panel(self.summary, summary_path=self.summary_path))


class _RoboticsSummaryPane(Static, _ThemedRenderer):
    """Base for summary-backed robotics panes with pure renderable builders."""

    _render_summary: ClassVar[Callable[[dict[str, object]], RenderableType]]

    def __init__(self, summary: dict[str, object]) -> None:
        super().__init__()
        self.summary = summary

    def on_mount(self) -> None:
        self.update(type(self)._render_summary(self.summary))


class _RoboticsStaticPane(Static, _ThemedRenderer):
    """Base for robotics panes rendered from static pure builders."""

    _render_static: ClassVar[Callable[[], RenderableType]]

    def on_mount(self) -> None:
        self.update(type(self)._render_static())


class RoboticsPipelinePane(_RoboticsStaticPane):
    """Visual pipeline graph for the real policy+score run."""

    _render_static: ClassVar[Callable[[], RenderableType]] = staticmethod(robotics_pipeline_panel)


class RoboticsReportGuidePane(_RoboticsStaticPane):
    """Compact guide for interpreting the report panes."""

    _render_static: ClassVar[Callable[[], RenderableType]] = staticmethod(
        robotics_report_guide_panel
    )


class RoboticsRerunPane(_RoboticsSummaryPane):
    """Rerun artifact location and viewer command."""

    _render_summary: ClassVar[Callable[[dict[str, object]], RenderableType]] = staticmethod(
        robotics_rerun_panel
    )


class RoboticsTensorBoardPane(_RoboticsSummaryPane):
    """TensorBoard log directory and viewer command."""

    _render_summary: ClassVar[Callable[[dict[str, object]], RenderableType]] = staticmethod(
        robotics_tensorboard_panel
    )


class RoboticsMetricsPane(_RoboticsSummaryPane):
    """Runtime bars and tensor contract summary."""

    _render_summary: ClassVar[Callable[[dict[str, object]], RenderableType]] = staticmethod(
        robotics_metrics_panel
    )


class RoboticsCandidatePane(_RoboticsSummaryPane):
    """Candidate scores, targets, and selection status."""

    _render_summary: ClassVar[Callable[[dict[str, object]], RenderableType]] = staticmethod(
        robotics_candidate_panel
    )


class RoboticsTabletopPane(_RoboticsSummaryPane):
    """Compact tabletop map with stable marker semantics."""

    _render_summary: ClassVar[Callable[[dict[str, object]], RenderableType]] = staticmethod(
        robotics_tabletop_panel
    )

    def _map_lines(self) -> list[str]:
        return _robotics_tabletop_map_lines(self.summary)


class RoboticsArmPane(Static, _ThemedRenderer):
    """Illustrative animated robot-arm replay for the selected candidate."""

    _FRAMES: ClassVar[tuple[tuple[str, ...], ...]] = ROBOTICS_ARM_FRAMES

    def __init__(self, summary: dict[str, object], *, animate: bool = True) -> None:
        super().__init__()
        self.summary = summary
        self.animate = animate
        self._frame_index = 0
        self._timer: Any | None = None
        self._target_line_cached = ""

    def on_mount(self) -> None:
        self._target_line_cached = robotics_arm_target_line(self.summary)
        self._render_frame()
        if self.animate:
            self._timer = self.set_interval(
                ROBOTICS_SHOWCASE_APP_SPEC.arm_frame_interval_s,
                self._advance,
            )

    def on_unmount(self) -> None:
        # Textual timers keep firing on dismounted widgets unless stopped,
        # so cancel the one `on_mount` started before this pane goes away.
        if self._timer is not None:
            self._timer.stop()
            self._timer = None

    def _advance(self) -> None:
        self._frame_index = (self._frame_index + 1) % len(self._FRAMES)
        self._render_frame()

    def _render_frame(self) -> None:
        self.update(
            robotics_arm_panel(
                self.summary,
                frame_lines=self._FRAMES[self._frame_index],
                target_line=self._target_line_cached,
            )
        )


class RoboticsEventPane(_RoboticsSummaryPane):
    """Provider events emitted by the completed real run."""

    _render_summary: ClassVar[Callable[[dict[str, object]], RenderableType]] = staticmethod(
        robotics_event_panel
    )


class RoboticsTabletopHelpScreen(ModalScreen[None]):
    """Modal explainer for the standalone robotics tabletop replay."""

    BINDINGS: ClassVar[list[Binding]] = [
        Binding(spec.key, spec.action, spec.description, show=spec.show)
        for spec in ROBOTICS_TABLETOP_HELP_BINDING_SPECS
    ]

    CSS = _tui_styles.ROBOTICS_TABLETOP_HELP_SCREEN_CSS

    def compose(self) -> ComposeResult:
        spec = ROBOTICS_TABLETOP_HELP_SCREEN_SPEC
        with VerticalScroll(id=spec.card_id):
            yield Static(spec.title, id=spec.title_id)
            for section in spec.sections:
                yield Static(
                    robotics_help_section_renderable(section),
                    classes=section.classes,
                )


class RoboticsProgressPane(Static, _ThemedRenderer):
    """Staged reveal status for the standalone showcase report."""

    def on_mount(self) -> None:
        self.set_message(ROBOTICS_SHOWCASE_APP_SPEC.initial_progress_message)

    def set_message(self, message: str) -> None:
        self.update(robotics_progress_panel(message))


class RoboticsShowcaseApp(App[None]):
    """Standalone Textual report for the real robotics showcase."""

    TITLE = ROBOTICS_SHOWCASE_APP_SPEC.title
    SUB_TITLE = ROBOTICS_SHOWCASE_APP_SPEC.subtitle
    BINDINGS: ClassVar[list[Binding]] = [
        Binding(spec.key, spec.action, spec.description, show=spec.show)
        for spec in ROBOTICS_SHOWCASE_APP_SPEC.bindings
    ]
    CSS = _tui_styles.ROBOTICS_SHOWCASE_APP_CSS

    def __init__(
        self,
        *,
        summary: dict[str, object],
        summary_path: Path | None = None,
        stage_delay: float = ROBOTICS_SHOWCASE_APP_SPEC.default_stage_delay_s,
        animate_arm: bool = True,
    ) -> None:
        super().__init__()
        self.summary = summary
        self.summary_path = summary_path
        self.stage_delay = max(0.0, stage_delay)
        self.animate_arm = animate_arm
        self.rerun_recording_path = _robotics_rerun_recording_path(summary)
        self.tensorboard_log_dir = _robotics_tensorboard_log_dir(summary)
        _register_worldforge_themes(self)
        self.theme = THEME_NAME_DARK

    def compose(self) -> ComposeResult:
        yield Header()
        with VerticalScroll(id=ROBOTICS_SHOWCASE_APP_SPEC.body_id):
            if self.stage_delay <= 0:
                for stage in ROBOTICS_SHOWCASE_APP_SPEC.stages:
                    widget = self._stage_widget(stage)
                    if widget is not None:
                        yield widget
            else:
                yield RoboticsProgressPane()
        yield Footer()

    async def on_mount(self) -> None:
        if self.stage_delay > 0:
            self.run_worker(self._reveal_report(), name="robotics.reveal", group="robotics")

    async def _reveal_report(self) -> None:
        body = self.query_one(ROBOTICS_SHOWCASE_BODY_SELECTOR, VerticalScroll)
        progress = self.query_one(RoboticsProgressPane)
        await asyncio.sleep(self.stage_delay)
        for stage in ROBOTICS_SHOWCASE_APP_SPEC.stages:
            widget = self._stage_widget(stage)
            if widget is None:
                continue
            progress.set_message(stage.message)
            await body.mount(widget)
            await asyncio.sleep(self.stage_delay)
        await progress.remove()

    def _stage_widget(self, stage: _robotics_view.RoboticsShowcaseStageSpec) -> Static | None:
        if not _robotics_view.robotics_showcase_stage_enabled(
            stage,
            has_rerun_recording=self.rerun_recording_path is not None,
            has_tensorboard_logs=self.tensorboard_log_dir is not None,
        ):
            return None
        return self._make_stage_widget(stage.stage_id)

    def _make_stage_widget(self, stage_id: str) -> Static | None:
        if stage_id == "hero":
            return RoboticsHeroPane(self.summary, self.summary_path)
        if stage_id == "pipeline":
            return RoboticsPipelinePane()
        if stage_id == "guide":
            return RoboticsReportGuidePane()
        if stage_id == "rerun":
            return RoboticsRerunPane(self.summary)
        if stage_id == "tensorboard":
            return RoboticsTensorBoardPane(self.summary)
        if stage_id == "metrics":
            return RoboticsMetricsPane(self.summary)
        if stage_id == "arm":
            return RoboticsArmPane(self.summary, animate=self.animate_arm)
        if stage_id == "candidates":
            return RoboticsCandidatePane(self.summary)
        if stage_id == "tabletop":
            return RoboticsTabletopPane(self.summary)
        if stage_id == "events":
            return RoboticsEventPane(self.summary)
        return None

    def action_toggle_theme(self) -> None:
        self.theme = next_theme_name(self.theme)

    def action_show_tabletop_help(self) -> None:
        self.push_screen(RoboticsTabletopHelpScreen())

    def action_open_rerun(self) -> None:
        path = self.rerun_recording_path
        issue = _robotics_launch.rerun_recording_preflight(path)
        if issue is not None:
            self.notify(issue.message, severity=issue.severity, title=issue.title)
            return
        assert path is not None
        try:
            command_text = _robotics_launch.launch_rerun_viewer(path)
        except OSError as exc:
            self.notify(str(exc), severity="error", title="Rerun")
            return
        self.notify(
            command_text,
            severity="information",
            title="Opening Rerun",
        )

    def action_open_tensorboard(self) -> None:
        path = self.tensorboard_log_dir
        issue = _robotics_launch.tensorboard_log_dir_preflight(path)
        if issue is not None:
            self.notify(issue.message, severity=issue.severity, title=issue.title)
            return
        assert path is not None
        try:
            launch = _robotics_launch.launch_tensorboard_viewer(path)
        except OSError as exc:
            self.notify(str(exc), severity="error", title="TensorBoard")
            return
        self.notify(
            f"Waiting for TensorBoard to start at {launch.url}\nlogs: {launch.stderr_log}",
            severity="information",
            title="TensorBoard",
        )
        self.run_worker(
            self._open_tensorboard_browser_when_ready(launch.url, launch.stderr_log),
            name="tensorboard.open",
            group="tensorboard",
            exclusive=True,
        )

    async def _open_tensorboard_browser_when_ready(self, url: str, stderr_log: Path) -> None:
        ready = await _robotics_launch.wait_for_tensorboard_ready(
            host="localhost",
            port=ROBOTICS_TENSORBOARD_DEFAULT_PORT,
            timeout_s=ROBOTICS_TENSORBOARD_READY_TIMEOUT_S,
            interval_s=ROBOTICS_TENSORBOARD_POLL_INTERVAL_S,
            port_open=_tensorboard_port_open,
        )
        if not ready:
            self.notify(
                f"TensorBoard did not come up at {url} within "
                f"{ROBOTICS_TENSORBOARD_READY_TIMEOUT_S:.0f}s. "
                f"See {stderr_log} for the launcher output.",
                severity="error",
                title="TensorBoard",
            )
            return
        browser = await _robotics_launch.open_browser_url(url)
        if browser.error is not None:
            self.notify(browser.error, severity="warning", title="TensorBoard")
            return
        if not browser.opened:
            self.notify(
                f"Could not auto-open a browser. Visit {url} manually.",
                severity="warning",
                title="TensorBoard",
            )
            return
        self.notify(
            f"Opening {url}",
            severity="information",
            title="TensorBoard",
        )


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------


class WorldForgeCommandProvider(  # pragma: no cover - exercised by Pilot/provider tests.
    CommandProvider
):
    """Dynamic command palette entries for worlds, providers, and saved runs."""

    async def discover(self):
        for title, help_text, callback in self._items():
            yield DiscoveryHit(title, callback, help=help_text)

    async def search(self, query: str):
        matcher = self.matcher(query)
        for title, help_text, callback in self._items():
            score = matcher.match(title)
            if score > 0:
                yield Hit(score, matcher.highlight(title), callback, text=title, help=help_text)

    def _items(self) -> list[tuple[str, str, Any]]:
        app = self.app
        if not hasattr(app, "_get_forge"):
            return []
        forge = app._get_forge()  # type: ignore[attr-defined]
        specs = palette_item_specs(
            world_ids=forge.list_worlds(),
            providers=forge.providers(),
            report_paths=recent_report_paths(forge.state_dir, limit=50),
            run_records=list_run_history(workspace_root_for_state_dir(forge.state_dir), limit=50),
        )
        return [
            (spec.title, spec.help_text, self._callback_for_palette_item(app, spec))
            for spec in specs
        ]

    @staticmethod
    def _callback_for_palette_item(app: App, spec: PaletteItemSpec) -> Any:
        if spec.kind == "world":
            return lambda value=str(spec.value): app._open_world_from_palette(value)  # type: ignore[attr-defined]
        if spec.kind == "provider":
            return lambda value=str(spec.value): app._open_provider_from_palette(value)  # type: ignore[attr-defined]
        if spec.kind == "report":
            return lambda value=Path(spec.value): app._open_report_path(value)  # type: ignore[attr-defined]
        return lambda value=Path(spec.value): app._open_run_workspace(value)  # type: ignore[attr-defined]


class TheWorldHarnessApp(App[None]):
    """Visual TUI harness for WorldForge E2E demos."""

    TITLE = "TheWorldHarness"
    SUB_TITLE = "WorldForge visual integration harness"
    COMMANDS = App.COMMANDS | {WorldForgeCommandProvider}
    BINDINGS: ClassVar[list[Binding]] = [
        Binding(spec.key, spec.action, spec.description, show=spec.show)
        for spec in APP_BINDING_SPECS
    ]
    SCREENS: ClassVar[dict[AppScreenName, type[Screen[Any]]]] = {
        "home": HomeScreen,
        "run-inspector": RunInspectorScreen,
        "worlds": WorldsScreen,
        "providers": ProvidersScreen,
        "eval": EvalScreen,
        "benchmark": BenchmarkScreen,
        "runs": RunsScreen,
    }
    CSS = _tui_styles.THE_WORLD_HARNESS_APP_CSS

    current_provider: reactive[str] = reactive("mock", init=False)

    def __init__(
        self,
        *,
        initial_flow_id: str = RUN_INSPECTOR_DEFAULT_FLOW_ID,
        initial_screen: InitialScreen = "home",
        state_dir: Path | None = None,
        step_delay: float = RUN_INSPECTOR_DEFAULT_STEP_DELAY_SECONDS,
    ) -> None:
        super().__init__()
        self._initial_flow_id = initial_flow_id
        self._initial_screen: InitialScreen = initial_screen
        self._state_dir = state_dir
        self._step_delay = step_delay
        # Lazy ``WorldForge`` — only constructed once we know the resolved
        # ``state_dir`` (the CLI may leave it as ``None`` so the framework
        # picks a temp path). Sharing one forge across screens preserves the
        # single-writer contract documented in ``CLAUDE.md``.
        self._forge: WorldForge | None = None
        self._provider_event_queue: queue.Queue[ProviderEvent] = queue.Queue()

    # The harness keeps its own screen factories so we can pass per-instance
    # construction args (state_dir, step_delay, initial flow) into screens
    # without resorting to module-level globals.
    def _make_run_inspector(self) -> RunInspectorScreen:
        return RunInspectorScreen(
            initial_flow_id=self._initial_flow_id,
            state_dir=self._state_dir,
            step_delay=self._step_delay,
        )

    def _make_home(self) -> HomeScreen:
        return HomeScreen()

    def _get_forge(self) -> WorldForge:
        if self._forge is None:
            self._forge = WorldForge(
                state_dir=self._state_dir,
                event_handler=self._record_provider_event,
            )
        return self._forge

    def _make_worlds(self) -> WorldsScreen:
        return WorldsScreen(forge=self._get_forge())

    def _make_providers(self) -> ProvidersScreen:
        return ProvidersScreen(forge=self._get_forge())

    def _make_eval(self) -> EvalScreen:
        return EvalScreen(forge=self._get_forge())

    def _make_benchmark(self) -> BenchmarkScreen:
        return BenchmarkScreen(forge=self._get_forge())

    def _make_runs(self) -> RunsScreen:
        return RunsScreen(state_dir=self._get_forge().state_dir)

    def _record_provider_event(self, event: ProviderEvent) -> None:
        self._provider_event_queue.put(event)

    def drain_provider_events(self) -> tuple[ProviderEvent, ...]:
        events: list[ProviderEvent] = []
        while True:
            try:
                events.append(self._provider_event_queue.get_nowait())
            except queue.Empty:
                return tuple(events)

    async def on_mount(self) -> None:
        _register_worldforge_themes(self)
        self.theme = THEME_NAME_DARK
        # Awaiting the push keeps the active screen consistent before any
        # test/Pilot interaction runs.
        await self.push_screen(
            self._make_screen_for_name(initial_screen_name(self._initial_screen))
        )

    def action_show_help(self) -> None:
        self.push_screen(HelpScreen(source_screen=self.screen))

    def action_toggle_theme(self) -> None:
        """Cycle between the registered worldforge themes."""
        self.theme = next_theme_name(self.theme)

    def action_switch_screen(self, screen_name: str) -> None:
        """Switch to ``screen_name`` if not already the active screen.

        Replaces (rather than stacks on top of) the active non-modal screen
        so chord navigation does not grow the stack indefinitely. Modal
        overlays are popped first so the user does not get stuck behind
        them.
        """
        while isinstance(self.screen, ModalScreen):
            self.pop_screen()
        resolved_screen_name = app_screen_name(screen_name)
        if resolved_screen_name is None:
            return
        target_cls = self.SCREENS[resolved_screen_name]
        if isinstance(self.screen, target_cls):
            if self._active_run_inspector_needs_refresh(resolved_screen_name):
                self.switch_screen(self._make_screen_for_name(resolved_screen_name))
            return
        self.switch_screen(self._make_screen_for_name(resolved_screen_name))

    def _active_run_inspector_needs_refresh(self, screen_name: AppScreenName) -> bool:
        return screen_needs_run_inspector_refresh(
            screen_name,
            is_run_inspector=isinstance(self.screen, RunInspectorScreen),
            can_run_flows=getattr(self.screen, "can_run_flows", True),
        )

    def _make_screen_for_name(  # pragma: no cover - exercised through Textual callbacks.
        self, screen_name: AppScreenName
    ) -> Screen:
        match screen_name:
            case "home":
                return self._make_home()
            case "run-inspector":
                return self._make_run_inspector()
            case "worlds":
                return self._make_worlds()
            case "providers":
                return self._make_providers()
            case "eval":
                return self._make_eval()
            case "benchmark":
                return self._make_benchmark()
            case "runs":
                return self._make_runs()
        raise AssertionError(f"Unhandled harness screen route: {screen_name!r}")

    async def _switch_screen_and_wait(  # pragma: no cover - exercised through command callbacks.
        self, screen_name: AppScreenName
    ) -> Screen:
        while isinstance(self.screen, ModalScreen):
            await self.pop_screen()
        target_cls = self.SCREENS[screen_name]
        if isinstance(self.screen, target_cls):
            if self._active_run_inspector_needs_refresh(screen_name):
                await self.switch_screen(self._make_run_inspector())
            return self.screen
        await self.switch_screen(self._make_screen_for_name(screen_name))
        return self.screen

    def get_system_commands(self, screen: Screen) -> Iterable[SystemCommand]:
        # Yield the stock Textual commands first (theme, quit) so they stay
        # discoverable, then layer the harness-specific entries.
        yield from super().get_system_commands(screen)
        theme_command: SystemCommandSpec | None = None
        for spec in SYSTEM_COMMAND_SPECS:
            if spec.action == "theme":
                theme_command = spec
                continue
            yield SystemCommand(
                spec.title,
                spec.help_text,
                self._callback_for_system_command(spec),
            )
        for flow in available_flows():
            yield SystemCommand(
                flow_system_command_title(flow.title),
                flow_system_command_help(flow.short_title),
                self._make_run_flow_command(flow.id),
            )
        if theme_command is not None:
            yield SystemCommand(
                theme_command.title,
                theme_command.help_text,
                self._callback_for_system_command(theme_command),
            )

    def _callback_for_system_command(self, spec: SystemCommandSpec) -> Any:
        screen_name = app_screen_name(spec.action)
        if screen_name is not None:
            return lambda screen_name=screen_name: self.action_switch_screen(screen_name)
        if spec.action == "new-world":
            return self._command_new_world
        if spec.action == "help":
            return self.action_show_help
        return self.action_toggle_theme

    def _make_run_flow_command(self, flow_id: str):
        async def _run() -> None:
            screen = await self._switch_screen_and_wait("run-inspector")
            if isinstance(screen, RunInspectorScreen):
                screen.action_select_flow(flow_id)
                await screen.action_run_selected()

        return _run

    def _command_new_world(self) -> None:
        self.action_switch_screen("worlds")
        screen = self.screen
        if isinstance(screen, WorldsScreen):
            screen.action_new_world()

    def _open_world_from_palette(self, world_id: str) -> None:
        self.action_switch_screen("worlds")
        screen = self.screen
        if isinstance(screen, WorldsScreen):
            screen.selected_world = world_id

    def _open_provider_from_palette(self, provider: str) -> None:
        self.current_provider = provider
        self.action_switch_screen("providers")
        screen = self.screen
        if isinstance(screen, ProvidersScreen):
            screen.current_row_provider = provider

    def _open_report_path(self, path: Path) -> None:
        run = report_run_from_path(path, state_dir=self._get_forge().state_dir)
        while isinstance(self.screen, ModalScreen):
            self.pop_screen()
        self.switch_screen(RunInspectorScreen(state_dir=self._get_forge().state_dir, run=run))

    def _open_run_workspace(self, path: Path) -> None:
        run = preserved_run_from_path(path, state_dir=self._get_forge().state_dir)
        while isinstance(self.screen, ModalScreen):
            self.pop_screen()
        self.switch_screen(RunInspectorScreen(state_dir=self._get_forge().state_dir, run=run))

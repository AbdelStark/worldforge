"""Textual TUI for TheWorldHarness."""

from __future__ import annotations

import asyncio
import queue
import shlex
import statistics
import subprocess
import time
from collections.abc import Iterable
from contextlib import suppress
from pathlib import Path
from typing import Any, ClassVar, Literal

from rich import box
from rich.align import Align
from rich.console import Group, RenderableType
from rich.panel import Panel
from rich.table import Table
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
    BBox,
    Position,
    SceneObject,
    World,
    WorldForge,
    WorldForgeError,
    WorldStateError,
    list_eval_suites,
)
from worldforge.benchmark import BENCHMARKABLE_OPERATIONS
from worldforge.harness.connectors import (
    ProviderConnectorSummary,
    provider_connector_summaries,
)
from worldforge.harness.flows import (
    available_flows,
    benchmark_run_artifacts,
    eval_run_artifacts,
    recent_report_paths,
    report_run_from_path,
    run_flow,
    write_report,
)
from worldforge.harness.models import HarnessFlow, HarnessMetric, HarnessRun, HarnessStep
from worldforge.harness.theme import (
    FLOW_CAPABILITY_FALLBACKS,
    THEME_NAME_DARK,
    THEME_NAME_HIGH_CONTRAST,
    THEME_NAME_LIGHT,
    WORLDFORGE_DARK_PALETTE,
    WORLDFORGE_HIGH_CONTRAST_PALETTE,
    WORLDFORGE_LIGHT_PALETTE,
)
from worldforge.harness.worlds_view import (
    SceneObjectSpec,
    WorldSpec,
    filter_world_ids,
    format_detail_summary,
    is_dirty,
    validate_id_or_reason,
)
from worldforge.models import CAPABILITY_NAMES, JSONDict, ProviderEvent
from worldforge.providers.base import ProviderError
from worldforge.providers.mock import MockProvider

InitialScreen = Literal["home", "run-inspector", "worlds", "providers", "eval", "benchmark"]


def _build_theme(name: str, palette: dict[str, str], *, dark: bool) -> Theme:
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


class Breadcrumb(Static):
    """Header breadcrumb showing ``worldforge > <screen> [> <flow>]``.

    Path segments live in a reactive tuple; later milestones can deepen the
    trail (worlds, runs) without changing the rendering surface.
    """

    DEFAULT_CSS = """
    Breadcrumb {
        height: 1;
        padding: 0 2;
        background: $boost;
        color: $foreground;
    }
    """

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

    DEFAULT_CSS = """
    ProviderStatusPill {
        height: 1;
        padding: 0 2;
        background: $boost;
        color: $foreground;
        text-style: bold;
    }
    """

    label: reactive[str] = reactive("")

    def watch_label(self, _old: str, new: str) -> None:
        self.update(new)


class HeroPane(Static, _ThemedRenderer):
    """Top-level harness identity panel."""

    def compose_panel(self, flow: HarnessFlow | None, running: bool) -> RenderableType:
        title = Text("TheWorldHarness", style="bold")
        title.append("  /  visual WorldForge integration reference", style="dim")
        command = flow.command if flow else "select a flow"
        status = "RUNNING" if running else "READY"
        accent = self._color("accent")
        success = self._color("success")
        status_style = f"black on {accent}" if running else f"black on {success}"
        border = accent if running else success
        return Panel(
            Group(
                title,
                Text(""),
                Text(
                    flow.summary if flow else "Run an E2E flow and inspect every boundary.",
                    style="dim",
                ),
                Text(""),
                Text(f"Command: {command}", style=f"bold {accent}"),
                Text(f"Status: {status}", style=status_style),
            ),
            title="WORLD FORGE / HARNESS",
            border_style=border,
        )


class FlowCard(Static, _ThemedRenderer):
    """Flow selection card."""

    def render_flow(self, flow: HarnessFlow, selected: bool) -> None:
        marker = ">>" if selected else "  "
        accent = self._color("accent")
        body = self._color("foreground")
        success = self._color("success")
        panel = self._color("panel")
        style = f"bold {accent}" if selected else body
        self.update(
            Panel(
                Group(
                    Text(f"{marker} {flow.short_title}", style=style),
                    Text(flow.focus, style="dim"),
                    Text(flow.provider, style=success),
                ),
                border_style=accent if selected else panel,
            )
        )


class TimelinePane(Static, _ThemedRenderer):
    """Visual execution timeline."""

    def render_steps(
        self,
        flow: HarnessFlow,
        steps: tuple[HarnessStep, ...],
        active_index: int,
        complete_count: int,
    ) -> None:
        rows: list[RenderableType] = []
        accent = self._color("accent")
        success = self._color("success")
        muted = self._color("muted")
        body = self._color("foreground")
        for index, step in enumerate(steps):
            if index < complete_count:
                symbol = "OK"
                color = success
            elif index == active_index:
                symbol = ">>"
                color = accent
            else:
                symbol = "--"
                color = muted
            rows.append(Text(f"{symbol} {index + 1:02d}. {step.title}", style=f"bold {color}"))
            rows.append(Text(f"    {step.detail}", style="dim"))
            if index < complete_count:
                rows.append(Text(f"    {step.result}", style=body))
                if step.artifact:
                    rows.append(Text(f"    {step.artifact}", style=success))
            rows.append(Text(""))
        self.update(
            Panel(
                Group(*rows),
                title=f"{flow.title} / execution trace",
                border_style=accent,
            )
        )


class InspectorPane(Static, _ThemedRenderer):
    """Run metrics and state summary."""

    def render_empty(self) -> None:
        self.update(
            Panel(
                Align.center(
                    Text(
                        "Run a flow to populate metrics, state, and provider events.", style="dim"
                    ),
                    vertical="middle",
                ),
                title="Inspector",
                border_style=self._color("panel"),
            )
        )

    def render_run(self, run: HarnessRun) -> None:
        accent = self._color("accent")
        success = self._color("success")
        table = Table.grid(expand=True)
        table.add_column(justify="left", ratio=1)
        table.add_column(justify="right", ratio=1)
        for metric in run.metrics:
            table.add_row(
                Text(metric.label, style="dim"), Text(metric.value, style=f"bold {accent}")
            )
            if metric.detail:
                table.add_row("", Text(metric.detail, style=success))
        self.update(Panel(table, title="Inspector", border_style=accent))


class TranscriptPane(Static, _ThemedRenderer):
    """Structured transcript from the completed flow."""

    def render_empty(self) -> None:
        self.update(Panel(Text("Awaiting run output.", style="dim"), title="Run Transcript"))

    def render_run(self, run: HarnessRun) -> None:
        body = self._color("foreground")
        accent = self._color("accent")
        lines = [Text(line, style=body) for line in run.transcript]
        self.update(Panel(Group(*lines), title="Run Transcript", border_style=accent))


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
        panel = self._color("panel")
        accent = self._color("accent")
        if not self._artifacts:
            self.update(
                Panel(
                    Align.center(Text("No report captured yet.", style="dim"), vertical="middle"),
                    title="Export Preview",
                    border_style=panel,
                )
            )
            return
        text = self._artifacts.get(self.report_format) or self._artifacts.get("markdown", "")
        if len(text) > 5000:
            text = f"{text[:5000]}\n... truncated preview ..."
        self.update(
            Panel(
                Text(text),
                title=f"Export Preview / {self.report_format}",
                border_style=accent,
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


def _format_provider_event(event: ProviderEvent) -> Text:
    phase_styles = {
        "success": "bold green",
        "failure": "bold red",
        "retry": "bold yellow",
        "cancelled": "bold yellow",
    }
    duration = f"{event.duration_ms:.1f} ms" if event.duration_ms is not None else "n/a"
    timestamp = time.strftime("%H:%M:%S")
    text = Text()
    text.append(f"{timestamp} ", style="dim")
    text.append(f"{event.phase:<9}", style=phase_styles.get(event.phase, "bold"))
    text.append(f" {event.provider}.{event.operation} ")
    text.append(f"({duration})", style="dim")
    return text


def _provider_event_failure(provider: str, operation: str, exc: Exception) -> ProviderEvent:
    return ProviderEvent(
        provider=provider,
        operation=operation,
        phase="failure",
        message=str(exc),
    )


def _event_summary(event: ProviderEvent) -> dict[str, Any]:
    return {
        "phase": event.phase,
        "latency_ms": event.duration_ms,
        "retries": max(0, event.attempt - 1),
    }


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

    DEFAULT_CSS = """
    JumpCard {
        height: 7;
        padding: 1 2;
        margin-bottom: 1;
        border: round $panel;
        background: $surface;
        color: $foreground;
    }
    JumpCard:focus, JumpCard:focus-within {
        border: round $accent;
        background: $boost;
    }
    """

    BINDINGS: ClassVar[list[Binding]] = [
        Binding("enter", "activate", "Activate", show=False),
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
        Binding("n", "jump('worlds')", "Create a world", show=True),
        Binding("p", "jump('providers')", "Run a provider", show=True),
        Binding("e", "jump('eval')", "Run an eval", show=True),
    ]

    DEFAULT_CSS = """
    HomeScreen {
        background: $background;
        color: $foreground;
    }

    #home-root {
        padding: 1 2;
        height: 1fr;
    }

    #home-intro {
        height: auto;
        padding: 1 2;
        margin-bottom: 1;
        border: round $panel;
        background: $surface;
    }

    #home-cards {
        height: auto;
    }

    #home-recent {
        height: auto;
        margin-top: 1;
        padding: 1 2;
        border: round $panel;
        background: $surface;
        color: $text-muted;
    }
    """

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Horizontal(id="chrome"):
            yield Breadcrumb(id="breadcrumb")
            yield ProviderStatusPill(id="provider-pill")
        with Container(id="home-root"):
            yield Static(
                Text.from_markup(
                    "[bold]TheWorldHarness[/] is the visual integration reference for "
                    "WorldForge.\n"
                    "It runs the same provider, planning, evaluation, and persistence APIs "
                    "you would use in a script — wired into a keyboard-first workspace so "
                    "you can see every boundary as it executes.\n\n"
                    "Pick a jump target below, press [bold]Ctrl+P[/] to search every action, "
                    "or [bold]?[/] to see this screen's bindings."
                ),
                id="home-intro",
            )
            with Vertical(id="home-cards"):
                yield JumpCard(
                    target="worlds",
                    title="Create a world",
                    binding="n",
                    description="Open the Worlds screen — create, edit, save, fork.",
                    widget_id="jump-create-world",
                )
                yield JumpCard(
                    target="providers",
                    title="Run a provider",
                    binding="p",
                    description="Stream live provider events with cancellable workers.",
                    widget_id="jump-run-provider",
                )
                yield JumpCard(
                    target="eval",
                    title="Run an eval",
                    binding="e",
                    description="Execute a deterministic evaluation suite against a provider.",
                    widget_id="jump-run-eval",
                )
            yield Static(
                "No recent items yet — jump targets will appear here once you open them.",
                id="home-recent",
            )
        yield Footer()

    def on_mount(self) -> None:
        self._update_chrome()
        self._refresh_recent()
        first_card = _maybe_query(self, "#jump-create-world", JumpCard)
        if first_card is not None:
            first_card.focus()

    def on_screen_resume(self) -> None:
        self._update_chrome()
        self._refresh_recent()

    def _update_chrome(self) -> None:
        breadcrumb = _maybe_query(self, "#breadcrumb", Breadcrumb)
        if breadcrumb is not None:
            breadcrumb.path = ("worldforge", "home")
        pill = _maybe_query(self, "#provider-pill", ProviderStatusPill)
        if pill is not None:
            pill.label = ""

    def action_jump(self, target: str) -> None:
        self.post_message(JumpRequested(target))

    def on_jump_requested(self, event: JumpRequested) -> None:
        event.stop()
        if event.target == "worlds":
            self.app.action_switch_screen("worlds")
            return
        if event.target == "providers":
            self.app.action_switch_screen("providers")
            return
        if event.target == "eval":
            self.app.action_switch_screen("eval")
            return
        self.app.push_screen(
            PlaceholderScreen(target_milestone="?", next_action="Target not yet routed.")
        )

    def _refresh_recent(self) -> None:
        target = _maybe_query(self, "#home-recent", Static)
        if target is None or not hasattr(self.app, "_get_forge"):
            return
        forge = self.app._get_forge()  # type: ignore[attr-defined]
        world_ids = forge.list_worlds()
        world_ids = sorted(
            world_ids,
            key=lambda world_id: (
                (forge.state_dir / f"{world_id}.json").stat().st_mtime
                if (forge.state_dir / f"{world_id}.json").exists()
                else 0
            ),
            reverse=True,
        )[:5]
        reports = recent_report_paths(forge.state_dir, limit=5)
        if not world_ids and not reports:
            target.update(
                "No recent worlds or runs — press [b]n[/] to create a world "
                "or [b]e[/] to run an eval."
            )
            return
        lines = ["Recent"]
        if world_ids:
            lines.append("Worlds: " + ", ".join(world_ids))
        else:
            lines.append("Worlds: none yet")
        if reports:
            lines.append("Runs: " + ", ".join(path.name for path in reports))
        else:
            lines.append("Runs: none yet")
        target.update("\n".join(lines))


class RunInspectorScreen(Screen):
    """Hosts the existing flow visualisation (hero, rail, timeline, inspector, transcript)."""

    BINDINGS: ClassVar[list[Binding]] = [
        Binding("r", "run_selected", "Run", show=True),
        Binding("1", "select_flow('leworldmodel')", "LeWorldModel", show=True),
        Binding("2", "select_flow('lerobot')", "LeRobot", show=True),
        Binding("3", "select_flow('diagnostics')", "Diagnostics", show=True),
    ]

    DEFAULT_CSS = """
    RunInspectorScreen {
        background: $background;
        color: $foreground;
    }

    #root {
        height: 1fr;
        padding: 1 2;
    }

    #hero {
        height: 10;
        margin-bottom: 1;
    }

    #body {
        height: 1fr;
    }

    #rail {
        width: 30;
        margin-right: 1;
    }

    #timeline {
        width: 1fr;
        margin-right: 1;
    }

    #inspector-column {
        width: 42;
    }

    FlowCard {
        height: 6;
        margin-bottom: 1;
    }

    Select {
        margin-bottom: 1;
    }

    Button {
        margin-bottom: 1;
    }

    #transcript {
        height: 14;
        margin-top: 1;
    }
    """

    selected_flow_id: reactive[str] = reactive("leworldmodel", init=False)
    current_provider: reactive[str] = reactive("", init=False)
    running: reactive[bool] = reactive(False, init=False)
    last_run: reactive[HarnessRun | None] = reactive(None, init=False)

    def __init__(
        self,
        *,
        initial_flow_id: str = "leworldmodel",
        state_dir: Path | None = None,
        step_delay: float = 0.18,
        run: HarnessRun | None = None,
    ) -> None:
        super().__init__()
        self._fixed_run = run
        self.flows = {flow.id: flow for flow in available_flows()}
        resolved_id = initial_flow_id if initial_flow_id in self.flows else "leworldmodel"
        self.set_reactive(RunInspectorScreen.selected_flow_id, resolved_id)
        self.set_reactive(
            RunInspectorScreen.current_provider,
            self._provider_label(self.flows[resolved_id]),
        )
        self.state_dir = state_dir
        self.step_delay = step_delay
        if run is not None:
            self.set_reactive(RunInspectorScreen.last_run, run)

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Horizontal(id="chrome"):
            yield Breadcrumb(id="breadcrumb")
            yield ProviderStatusPill(id="provider-pill")
        if self._fixed_run is not None and self._fixed_run.kind != "flow":
            with Container(id="root"), Horizontal(id="body"):
                with Vertical(id="timeline"):
                    yield InspectorPane(id="inspector")
                    yield TranscriptPane(id="transcript")
                yield ExportPane(
                    artifacts=self._fixed_run.artifacts or {},
                    widget_id="export-preview",
                )
            yield Footer()
            return
        with Container(id="root"):
            yield HeroPane(id="hero")
            with Horizontal(id="body"):
                with Vertical(id="rail"):
                    yield Select(
                        [(flow.title, flow.id) for flow in self.flows.values()],
                        value=self.selected_flow_id,
                        allow_blank=False,
                        id="flow-select",
                    )
                    yield Button("Run selected flow", id="run-button", variant="warning")
                    for flow in self.flows.values():
                        yield FlowCard(id=f"flow-card-{flow.id}")
                yield TimelinePane(id="timeline")
                with Vertical(id="inspector-column"):
                    yield InspectorPane(id="inspector")
                    yield TranscriptPane(id="transcript")
        yield Footer()

    def on_mount(self) -> None:
        self._update_chrome()
        self._refresh_static()

    def on_screen_resume(self) -> None:
        self._update_chrome()
        self._refresh_static()

    @on(Select.Changed, "#flow-select")
    def _on_flow_changed(self, event: Select.Changed) -> None:
        if isinstance(event.value, str):
            self.selected_flow_id = event.value

    @on(Button.Pressed, "#run-button")
    async def _on_run_pressed(self) -> None:
        await self.action_run_selected()

    def action_select_flow(self, flow_id: str) -> None:
        if flow_id in self.flows:
            self.selected_flow_id = flow_id
            select = _maybe_query(self, "#flow-select", Select)
            if select is not None and select.value != flow_id:
                select.value = flow_id

    @property
    def can_run_flows(self) -> bool:
        """Return whether this screen has the interactive flow controls mounted."""

        return self._fixed_run is None or self._fixed_run.kind == "flow"

    def watch_selected_flow_id(self, _old: str, new: str) -> None:
        if new not in self.flows:
            return
        self.current_provider = self._provider_label(self.flows[new])
        self._update_chrome()
        self._refresh_static()

    def watch_current_provider(self, _old: str, new: str) -> None:
        pill = _maybe_query(self, "#provider-pill", ProviderStatusPill)
        if pill is not None:
            pill.label = new

    async def action_run_selected(self) -> None:
        if self.running:
            return
        await self._run_flow(self.selected_flow_id)

    async def _run_flow(self, flow_id: str) -> None:
        self.running = True
        flow = self.flows[flow_id]
        self.query_one("#run-button", Button).disabled = True
        self._refresh_static()
        run = run_flow(flow_id, state_dir=self.state_dir)
        self.last_run = run
        timeline = self.query_one("#timeline", TimelinePane)
        for index, _step in enumerate(run.steps):
            timeline.render_steps(flow, run.steps, active_index=index, complete_count=index)
            await asyncio.sleep(self.step_delay)
            timeline.render_steps(flow, run.steps, active_index=index, complete_count=index + 1)
        self.query_one("#inspector", InspectorPane).render_run(run)
        self.query_one("#transcript", TranscriptPane).render_run(run)
        self.running = False
        self.query_one("#run-button", Button).disabled = False
        self._refresh_static()

    def _update_chrome(self) -> None:
        if self._fixed_run is not None and self._fixed_run.kind != "flow":
            breadcrumb = _maybe_query(self, "#breadcrumb", Breadcrumb)
            if breadcrumb is not None:
                breadcrumb.path = ("worldforge", "run-inspector", self._fixed_run.flow.short_title)
            pill = _maybe_query(self, "#provider-pill", ProviderStatusPill)
            if pill is not None:
                pill.label = self._fixed_run.flow.capability
            return
        flow = self.flows[self.selected_flow_id]
        breadcrumb = _maybe_query(self, "#breadcrumb", Breadcrumb)
        if breadcrumb is not None:
            breadcrumb.path = ("worldforge", "run-inspector", flow.short_title)
        pill = _maybe_query(self, "#provider-pill", ProviderStatusPill)
        if pill is not None:
            pill.label = self.current_provider

    def _provider_label(self, flow: HarnessFlow) -> str:
        capability = flow.capability or FLOW_CAPABILITY_FALLBACKS.get(flow.id, "")
        suffix = f" · {capability}" if capability else ""
        return f"{flow.provider}{suffix}"

    def _refresh_static(self) -> None:
        if self._fixed_run is not None and self._fixed_run.kind != "flow":
            inspector = _maybe_query(self, "#inspector", InspectorPane)
            transcript = _maybe_query(self, "#transcript", TranscriptPane)
            export = _maybe_query(self, "#export-preview", ExportPane)
            if inspector is not None:
                inspector.render_run(self._fixed_run)
            if transcript is not None:
                transcript.render_run(self._fixed_run)
            if export is not None:
                export.set_artifacts(self._fixed_run.artifacts or {})
            return
        selected = self.flows[self.selected_flow_id]
        hero = _maybe_query(self, "#hero", HeroPane)
        if hero is None:
            return
        hero.update(hero.compose_panel(selected, self.running))
        for flow in self.flows.values():
            self.query_one(f"#flow-card-{flow.id}", FlowCard).render_flow(
                flow,
                selected=flow.id == self.selected_flow_id,
            )
        if self.last_run is None:
            self.query_one("#timeline", TimelinePane).render_steps(
                selected,
                (
                    HarnessStep(
                        "Ready",
                        "Select a flow and press Run to visualize the integration path.",
                        "Waiting for execution.",
                    ),
                ),
                active_index=0,
                complete_count=0,
            )
            self.query_one("#inspector", InspectorPane).render_empty()
            self.query_one("#transcript", TranscriptPane).render_empty()


class HelpScreen(ModalScreen[None]):
    """Modal overlay that lists the bindings of the screen below it."""

    BINDINGS: ClassVar[list[Binding]] = [
        Binding("escape", "dismiss", "Close", show=True),
        Binding("q", "dismiss", "Close", show=False),
    ]

    DEFAULT_CSS = """
    HelpScreen {
        align: center middle;
    }

    HelpScreen > #help-card {
        width: 70%;
        max-width: 90;
        height: auto;
        max-height: 80%;
        padding: 1 2;
        border: round $accent;
        background: $surface;
    }

    HelpScreen #help-title {
        height: auto;
        padding: 0 0 1 0;
        text-style: bold;
        color: $accent;
    }

    HelpScreen DataTable {
        height: auto;
        max-height: 30;
        background: $surface;
    }

    HelpScreen #help-footnote {
        height: auto;
        padding: 1 0 0 0;
        color: $text-muted;
    }
    """

    def __init__(self, source_screen: Screen | None = None) -> None:
        super().__init__()
        self._source_screen = source_screen

    def compose(self) -> ComposeResult:
        with Container(id="help-card"):
            yield Static("Bindings on this screen", id="help-title")
            yield DataTable(id="help-table", cursor_type="row", zebra_stripes=True)
            yield Static(
                "Press [bold]Esc[/] or [bold]q[/] to close. "
                "[bold]Ctrl+P[/] opens the command palette.",
                id="help-footnote",
            )

    def on_mount(self) -> None:
        # Update breadcrumb (sits on the screen below this modal) and
        # populate the table from that same source screen.
        breadcrumb = _maybe_query(self.app, "#breadcrumb", Breadcrumb)
        if breadcrumb is not None:
            breadcrumb.path = ("worldforge", "help")
        table = self.query_one("#help-table", DataTable)
        table.add_columns("Key", "Description", "Action")
        source = self._source_screen or self._previous_screen()
        for binding in self._iter_bindings(source):
            table.add_row(
                binding.key,
                binding.description or "",
                binding.action,
            )

    def _previous_screen(self) -> Screen | None:
        """Return the screen below this modal on the stack, if any."""
        stack = list(self.app.screen_stack)
        if self in stack:
            stack.remove(self)
        return stack[-1] if stack else None

    @staticmethod
    def _iter_bindings(screen: Screen | None) -> Iterable[Binding]:
        if screen is None:
            return ()
        # Surface every binding declared on the source screen — discovery is
        # the whole point of this overlay, so ``show=False`` entries are
        # included alongside footer-visible ones. We also fold in App-level
        # bindings so the user can see "Help / Quit / Ctrl+P" alongside the
        # screen-local ones.
        seen: set[tuple[str, str]] = set()
        bindings: list[Binding] = []
        sources = (screen, screen.app)
        for source in sources:
            try:
                items = source._bindings.key_to_bindings.items()  # type: ignore[attr-defined]
            except AttributeError:  # pragma: no cover - defensive
                continue
            for _key, binding_list in items:
                for binding in binding_list:
                    fingerprint = (binding.key, binding.action)
                    if fingerprint in seen:
                        continue
                    seen.add(fingerprint)
                    bindings.append(binding)
        return bindings


class PlaceholderScreen(ModalScreen[None]):
    """Modal explaining a jump target that lands in a later milestone."""

    BINDINGS: ClassVar[list[Binding]] = [
        Binding("escape", "dismiss", "Close", show=True),
        Binding("q", "dismiss", "Close", show=False),
        Binding("enter", "dismiss", "Close", show=False),
    ]

    DEFAULT_CSS = """
    PlaceholderScreen {
        align: center middle;
    }

    PlaceholderScreen > #placeholder-card {
        width: 60%;
        max-width: 80;
        height: auto;
        padding: 1 2;
        border: round $warning;
        background: $surface;
    }

    PlaceholderScreen #placeholder-title {
        height: auto;
        padding: 0 0 1 0;
        text-style: bold;
        color: $warning;
    }

    PlaceholderScreen #placeholder-body {
        height: auto;
        color: $foreground;
    }

    PlaceholderScreen #placeholder-footnote {
        height: auto;
        padding: 1 0 0 0;
        color: $text-muted;
    }
    """

    def __init__(self, *, target_milestone: str, next_action: str) -> None:
        super().__init__()
        self._target_milestone = target_milestone
        self._next_action = next_action

    def compose(self) -> ComposeResult:
        with Container(id="placeholder-card"):
            yield Static(
                f"Coming in milestone {self._target_milestone}",
                id="placeholder-title",
            )
            yield Static(self._next_action, id="placeholder-body")
            yield Static(
                "Press [bold]Esc[/], [bold]q[/], or [bold]Enter[/] to close.",
                id="placeholder-footnote",
            )

    def on_mount(self) -> None:
        breadcrumb = _maybe_query(self.app, "#breadcrumb", Breadcrumb)
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
        Binding("escape", "deny", "Cancel", show=True),
    ]

    DEFAULT_CSS = """
    ConfirmDeleteScreen {
        align: center middle;
    }

    ConfirmDeleteScreen > #confirm-card {
        width: 60%;
        max-width: 72;
        height: auto;
        padding: 1 2;
        border: round $error;
        background: $surface;
    }

    ConfirmDeleteScreen #confirm-title {
        height: auto;
        padding: 0 0 1 0;
        text-style: bold;
        color: $error;
    }

    ConfirmDeleteScreen #confirm-prompt {
        height: auto;
        color: $foreground;
    }

    ConfirmDeleteScreen #confirm-actions {
        height: auto;
        padding-top: 1;
        align: right middle;
    }

    ConfirmDeleteScreen Button {
        margin-left: 1;
    }
    """

    def __init__(
        self,
        *,
        prompt: str = "This action cannot be undone.",
        title: str = "Delete?",
        confirm_label: str = "Delete",
        cancel_label: str = "Cancel",
    ) -> None:
        super().__init__()
        self._prompt = prompt
        self._title = title
        self._confirm_label = confirm_label
        self._cancel_label = cancel_label

    def compose(self) -> ComposeResult:
        with Container(id="confirm-card"):
            yield Static(self._title, id="confirm-title")
            yield Static(self._prompt, id="confirm-prompt")
            with Horizontal(id="confirm-actions"):
                yield Button(self._cancel_label, id="confirm-cancel", variant="default")
                yield Button(self._confirm_label, id="confirm-accept", variant="error")

    def on_mount(self) -> None:
        accept = _maybe_query(self, "#confirm-accept", Button)
        if accept is not None:
            accept.focus()

    @on(Button.Pressed, "#confirm-accept")
    def _on_accept(self) -> None:
        self.dismiss(True)

    @on(Button.Pressed, "#confirm-cancel")
    def _on_cancel(self) -> None:
        self.dismiss(False)

    def action_deny(self) -> None:
        self.dismiss(False)


class NewWorldScreen(ModalScreen[WorldSpec | None]):
    """Collect name + provider + description for a brand-new world."""

    BINDINGS: ClassVar[list[Binding]] = [
        Binding("escape", "cancel", "Cancel", show=True),
    ]

    DEFAULT_CSS = """
    NewWorldScreen {
        align: center middle;
    }

    NewWorldScreen > #new-world-card {
        width: 70%;
        max-width: 84;
        height: auto;
        padding: 1 2;
        border: round $accent;
        background: $surface;
    }

    NewWorldScreen #new-world-title {
        height: auto;
        padding: 0 0 1 0;
        text-style: bold;
        color: $accent;
    }

    NewWorldScreen #new-world-error {
        height: auto;
        color: $error;
        padding: 1 0 0 0;
    }

    NewWorldScreen #new-world-error.hidden {
        display: none;
    }

    NewWorldScreen .field-label {
        color: $text-muted;
        height: 1;
    }

    NewWorldScreen Input, NewWorldScreen Select {
        margin-bottom: 1;
    }

    NewWorldScreen #new-world-actions {
        height: auto;
        padding-top: 1;
        align: right middle;
    }

    NewWorldScreen Button {
        margin-left: 1;
    }
    """

    def __init__(self, *, providers: tuple[str, ...]) -> None:
        super().__init__()
        self._providers = providers or ("mock",)

    def compose(self) -> ComposeResult:
        with Container(id="new-world-card"):
            yield Static("Create world", id="new-world-title")
            yield Static("Name", classes="field-label")
            yield Input(placeholder="e.g. kitchen-counter", id="new-world-name")
            yield Static("Provider", classes="field-label")
            yield Select(
                [(provider, provider) for provider in self._providers],
                value=self._providers[0],
                allow_blank=False,
                id="new-world-provider",
            )
            yield Static("Description (optional)", classes="field-label")
            yield Input(placeholder="A short scene description.", id="new-world-description")
            yield Static("", id="new-world-error", classes="hidden")
            with Horizontal(id="new-world-actions"):
                yield Button("Cancel", id="new-world-cancel", variant="default")
                yield Button("Create", id="new-world-create", variant="primary")

    def on_mount(self) -> None:
        name_input = _maybe_query(self, "#new-world-name", Input)
        if name_input is not None:
            name_input.focus()

    def _set_error(self, message: str | None) -> None:
        _set_form_error(self, "#new-world-error", message)

    @on(Button.Pressed, "#new-world-create")
    @on(Input.Submitted, "#new-world-name")
    @on(Input.Submitted, "#new-world-description")
    def _on_create(self) -> None:
        name_input = self.query_one("#new-world-name", Input)
        description_input = self.query_one("#new-world-description", Input)
        provider_select = self.query_one("#new-world-provider", Select)
        name = (name_input.value or "").strip()
        if not name:
            self._set_error("Name must be a non-empty string.")
            return
        # Most users type a human name — we *only* pre-validate when the user
        # typed something that actively looks like an id (no spaces, looks
        # path-ish). Otherwise the save worker's WorldForgeError is the true
        # boundary and raises a toast.
        if " " not in name and ("/" in name or "\\" in name or name in {".", ".."}):
            reason = validate_id_or_reason(name)
            if reason:
                self._set_error(reason)
                return
        provider = provider_select.value if isinstance(provider_select.value, str) else "mock"
        description = (description_input.value or "").strip()
        self.dismiss(WorldSpec(name=name, provider=provider, description=description))

    @on(Button.Pressed, "#new-world-cancel")
    def _on_cancel_button(self) -> None:
        self.dismiss(None)

    def action_cancel(self) -> None:
        self.dismiss(None)


class EditObjectScreen(ModalScreen[SceneObjectSpec | None]):
    """Collect name + position for a single scene object."""

    BINDINGS: ClassVar[list[Binding]] = [
        Binding("escape", "cancel", "Cancel", show=True),
    ]

    DEFAULT_CSS = """
    EditObjectScreen {
        align: center middle;
    }

    EditObjectScreen > #edit-object-card {
        width: 60%;
        max-width: 72;
        height: auto;
        padding: 1 2;
        border: round $accent;
        background: $surface;
    }

    EditObjectScreen #edit-object-title {
        height: auto;
        padding: 0 0 1 0;
        text-style: bold;
        color: $accent;
    }

    EditObjectScreen .field-label {
        color: $text-muted;
        height: 1;
    }

    EditObjectScreen Input {
        margin-bottom: 1;
    }

    EditObjectScreen #edit-object-error {
        color: $error;
        height: auto;
    }

    EditObjectScreen #edit-object-error.hidden {
        display: none;
    }

    EditObjectScreen #edit-object-actions {
        height: auto;
        padding-top: 1;
        align: right middle;
    }

    EditObjectScreen Button {
        margin-left: 1;
    }
    """

    def __init__(self, *, existing: SceneObjectSpec | None = None) -> None:
        super().__init__()
        self._existing = existing

    def compose(self) -> ComposeResult:
        default = self._existing or SceneObjectSpec(name="cube", x=0.0, y=0.5, z=0.0)
        with Container(id="edit-object-card"):
            yield Static("Scene object", id="edit-object-title")
            yield Static("Name", classes="field-label")
            yield Input(value=default.name, placeholder="cube", id="edit-object-name")
            yield Static("Position x / y / z", classes="field-label")
            yield Input(value=str(default.x), id="edit-object-x")
            yield Input(value=str(default.y), id="edit-object-y")
            yield Input(value=str(default.z), id="edit-object-z")
            yield Static("", id="edit-object-error", classes="hidden")
            with Horizontal(id="edit-object-actions"):
                yield Button("Cancel", id="edit-object-cancel", variant="default")
                yield Button("Save", id="edit-object-save", variant="primary")

    def on_mount(self) -> None:
        name_input = _maybe_query(self, "#edit-object-name", Input)
        if name_input is not None:
            name_input.focus()

    def _set_error(self, message: str | None) -> None:
        _set_form_error(self, "#edit-object-error", message)

    @on(Button.Pressed, "#edit-object-save")
    def _on_save(self) -> None:
        try:
            name = (self.query_one("#edit-object-name", Input).value or "").strip()
            if not name:
                self._set_error("Name must be a non-empty string.")
                return
            x = float(self.query_one("#edit-object-x", Input).value or 0.0)
            y = float(self.query_one("#edit-object-y", Input).value or 0.0)
            z = float(self.query_one("#edit-object-z", Input).value or 0.0)
        except ValueError:
            self._set_error("Position coordinates must be numeric.")
            return
        self.dismiss(SceneObjectSpec(name=name, x=x, y=y, z=z))

    @on(Button.Pressed, "#edit-object-cancel")
    def _on_cancel_button(self) -> None:
        self.dismiss(None)

    def action_cancel(self) -> None:
        self.dismiss(None)


# ---------------------------------------------------------------------------
# Worlds CRUD: screens
# ---------------------------------------------------------------------------


def _default_bbox_for_position(position: Position) -> BBox:
    """Build a conservative unit-sized bounding box around ``position``."""

    return BBox(
        Position(position.x - 0.05, position.y - 0.05, position.z - 0.05),
        Position(position.x + 0.05, position.y + 0.05, position.z + 0.05),
    )


def _scene_object_from_spec(spec: SceneObjectSpec) -> SceneObject:
    position = Position(spec.x, spec.y, spec.z)
    return SceneObject(
        name=spec.name,
        position=position,
        bbox=_default_bbox_for_position(position),
        is_graspable=spec.is_graspable,
        metadata=dict(spec.metadata),
    )


class WorldsScreen(Screen):
    """Table of persisted worlds plus a detail pane.

    Hosts the main Worlds CRUD loop: list → create / edit / fork / delete.
    Every disk-touching operation runs inside a ``persistence``-group worker so
    the UI thread never blocks on filesystem I/O.
    """

    BINDINGS: ClassVar[list[Binding]] = [
        Binding("n", "new_world", "New", show=True),
        Binding("enter", "open_selected", "Open", show=True),
        Binding("e", "open_selected", "Edit", show=False),
        Binding("d", "delete_selected", "Delete", show=True),
        Binding("f", "fork_selected", "Fork", show=True),
        Binding("slash", "focus_filter", "Filter", show=True),
        Binding("r", "refresh_worlds", "Refresh", show=True),
        Binding("escape", "clear_filter", "Clear filter", show=False),
    ]

    DEFAULT_CSS = """
    WorldsScreen {
        background: $background;
        color: $foreground;
    }

    #worlds-root {
        height: 1fr;
        padding: 1 2;
    }

    #worlds-filter-row {
        height: 3;
        margin-bottom: 1;
    }

    #worlds-filter-label {
        width: auto;
        padding: 1 1 0 0;
        color: $text-muted;
    }

    #worlds-filter {
        width: 1fr;
    }

    #worlds-body {
        height: 1fr;
    }

    #worlds-table-wrap {
        width: 2fr;
        margin-right: 1;
        border: round $panel;
        background: $surface;
    }

    #worlds-detail {
        width: 1fr;
        padding: 1 2;
        border: round $panel;
        background: $surface;
        color: $foreground;
    }

    #worlds-detail.-focused {
        border: round $accent;
    }

    #worlds-empty {
        padding: 1 2;
        color: $text-muted;
    }

    #worlds-empty.hidden {
        display: none;
    }

    #worlds-table.hidden {
        display: none;
    }
    """

    selected_world: reactive[str | None] = reactive(None, init=False)
    filter_query: reactive[str] = reactive("", init=False)

    def __init__(self, *, forge: WorldForge) -> None:
        super().__init__()
        self._forge = forge
        self._worlds: dict[str, World] = {}
        self._ordered_ids: list[str] = []

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Horizontal(id="chrome"):
            yield Breadcrumb(id="breadcrumb")
            yield ProviderStatusPill(id="provider-pill")
        with Container(id="worlds-root"):
            with Horizontal(id="worlds-filter-row"):
                yield Static("Filter:", id="worlds-filter-label")
                yield Input(placeholder="id or name substring", id="worlds-filter")
            with Horizontal(id="worlds-body"):
                with Container(id="worlds-table-wrap"):
                    yield DataTable(
                        zebra_stripes=True,
                        cursor_type="row",
                        id="worlds-table",
                    )
                    yield Static(
                        "No worlds yet — press [b]n[/] to create one.",
                        id="worlds-empty",
                    )
                yield Static(
                    "Select a world to see its summary.",
                    id="worlds-detail",
                )
        yield Footer()

    def on_mount(self) -> None:
        table = self.query_one("#worlds-table", DataTable)
        table.add_columns("id", "name", "provider", "step", "last touched")
        # Focus the table so the screen bindings (``n``, ``d``, ``f``, ``/``)
        # win over the filter ``Input`` at the top of the screen. The filter
        # focuses explicitly via ``/`` → ``action_focus_filter``.
        table.focus()
        self._update_chrome()
        self.refresh_worlds()

    def on_screen_resume(self) -> None:
        self._update_chrome()
        table = _maybe_query(self, "#worlds-table", DataTable)
        if table is not None:
            table.focus()
        # We intentionally avoid calling ``refresh_worlds`` here: screen
        # resume fires when a modal dismisses, and an exclusive persistence
        # worker started there would cancel an in-flight save/delete/fork
        # worker that just started from the modal's own callback. State
        # changes inside the app flow back via ``WorldSaved`` / ``WorldDeleted``
        # / ``WorldForked`` messages instead.

    def _update_chrome(self) -> None:
        breadcrumb = _maybe_query(self, "#breadcrumb", Breadcrumb)
        if breadcrumb is not None:
            breadcrumb.path = ("worldforge", "worlds")
        pill = _maybe_query(self, "#provider-pill", ProviderStatusPill)
        if pill is not None:
            selected = self.selected_world
            world = self._worlds.get(selected) if selected else None
            pill.label = world.provider if world else ""

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
        table = _maybe_query(self, "#worlds-table", DataTable)
        empty = _maybe_query(self, "#worlds-empty", Static)
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
        detail = _maybe_query(self, "#worlds-detail", Static)
        if detail is None:
            return
        selected = self.selected_world
        world = self._worlds.get(selected) if selected else None
        if world is None:
            detail.update("Select a world to see its summary.")
            return
        detail.update(format_detail_summary(world, state_dir=self._forge.state_dir))

    # ------------------------------------------------------------------
    # Events / actions
    # ------------------------------------------------------------------

    @on(DataTable.RowHighlighted, "#worlds-table")
    def _on_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        key = event.row_key.value if event.row_key else None
        if isinstance(key, str):
            self.selected_world = key

    @on(DataTable.RowSelected, "#worlds-table")
    def _on_row_selected(self, event: DataTable.RowSelected) -> None:
        key = event.row_key.value if event.row_key else None
        if isinstance(key, str):
            self.selected_world = key
            self.action_open_selected()

    @on(Input.Changed, "#worlds-filter")
    def _on_filter_changed(self, event: Input.Changed) -> None:
        self.filter_query = event.value

    @on(Input.Submitted, "#worlds-filter")
    def _on_filter_submitted(self) -> None:
        table = _maybe_query(self, "#worlds-table", DataTable)
        if table is not None:
            table.focus()

    def action_focus_filter(self) -> None:
        filt = _maybe_query(self, "#worlds-filter", Input)
        if filt is not None:
            filt.focus()

    def action_clear_filter(self) -> None:
        filt = _maybe_query(self, "#worlds-filter", Input)
        if filt is not None:
            filt.value = ""
        self.filter_query = ""
        table = _maybe_query(self, "#worlds-table", DataTable)
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
        Binding("ctrl+s", "save_world", "Save", show=True),
        Binding("a", "add_object", "Add object", show=True),
        Binding("delete", "remove_object", "Remove", show=True),
        Binding("ctrl+p,predict", "predict_preview", "Preview", show=False),
        Binding("escape", "close", "Back", show=True),
    ]

    DEFAULT_CSS = """
    WorldEditScreen {
        background: $background;
        color: $foreground;
    }

    #edit-root {
        height: 1fr;
        padding: 1 2;
    }

    #edit-title {
        height: 1;
        text-style: bold;
        color: $accent;
    }

    #edit-body {
        height: 1fr;
    }

    #edit-form {
        width: 2fr;
        margin-right: 1;
        border: round $panel;
        background: $surface;
        padding: 1 2;
    }

    #edit-preview {
        width: 1fr;
        border: round $panel;
        background: $surface;
        padding: 1 2;
        color: $foreground;
    }

    #edit-preview.-staged {
        border: round $warning;
    }

    #edit-objects {
        height: 10;
        margin-top: 1;
        background: $surface;
    }

    #edit-objects-header {
        height: 1;
        color: $text-muted;
    }

    .field-label {
        height: 1;
        color: $text-muted;
    }

    Input, Select {
        margin-bottom: 1;
    }

    #edit-preview-caption {
        height: 1;
        color: $warning;
    }

    #edit-preview-caption.hidden {
        display: none;
    }
    """

    dirty: reactive[bool] = reactive(False, init=False)
    staged_action: reactive[Action | None] = reactive(None, init=False)

    def __init__(self, *, forge: WorldForge, world: World, is_new: bool) -> None:
        super().__init__()
        self._forge = forge
        self._world = world
        self._is_new = is_new
        # Keep an original-snapshot clone (unless new) for dirty detection.
        self._original = None if is_new else self._clone_world(world)

    @staticmethod
    def _clone_world(world: World) -> World:
        # Round-trip through ``World.from_state`` so ``_original`` is a
        # detached snapshot that does not share mutable members with ``world``.
        return World.from_state(world._forge, world.to_dict())

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Horizontal(id="chrome"):
            yield Breadcrumb(id="breadcrumb")
            yield ProviderStatusPill(id="provider-pill")
        with Container(id="edit-root"):
            yield Static(self._render_title(), id="edit-title")
            with Horizontal(id="edit-body"):
                with Container(id="edit-form"):
                    yield Static("Name", classes="field-label")
                    yield Input(value=self._world.name, id="edit-name")
                    yield Static("Provider", classes="field-label")
                    yield Select(
                        [(name, name) for name in self._forge.providers()],
                        value=self._world.provider,
                        allow_blank=False,
                        id="edit-provider",
                    )
                    yield Static("Scene objects", id="edit-objects-header")
                    yield OptionList(id="edit-objects")
                with Container(id="edit-preview"):
                    yield Static("Preview (saved state)", id="edit-preview-caption")
                    yield Static("", id="edit-preview-body")
        yield Footer()

    def _render_title(self) -> str:
        marker = " *" if self.dirty or self._is_new else ""
        return f"Edit: {self._world.name} ({self._world.id}){marker}"

    def on_mount(self) -> None:
        self._update_chrome()
        self._populate_objects()
        self._refresh_preview_static()
        self.dirty = self._is_new or is_dirty(self._original, self._world)
        # Focus the object list so the screen-level ``a``/``delete`` bindings
        # fire before the name ``Input`` swallows them. The user can press
        # ``Tab`` (or click) to move to the name field when renaming.
        options = _maybe_query(self, "#edit-objects", OptionList)
        if options is not None:
            options.focus()

    def on_screen_resume(self) -> None:
        self._update_chrome()

    def _update_chrome(self) -> None:
        breadcrumb = _maybe_query(self, "#breadcrumb", Breadcrumb)
        if breadcrumb is not None:
            breadcrumb.path = ("worldforge", "worlds", "edit", self._world.name)
        pill = _maybe_query(self, "#provider-pill", ProviderStatusPill)
        if pill is not None:
            pill.label = self._world.provider

    def _populate_objects(self) -> None:
        options = _maybe_query(self, "#edit-objects", OptionList)
        if options is None:
            return
        options.clear_options()
        for scene_object in self._world.scene_objects.values():
            options.add_option(
                Option(
                    f"{scene_object.name} @ "
                    f"({scene_object.position.x:.2f},"
                    f" {scene_object.position.y:.2f},"
                    f" {scene_object.position.z:.2f})",
                    id=scene_object.id,
                )
            )

    def _refresh_preview_static(self) -> None:
        caption = _maybe_query(self, "#edit-preview-caption", Static)
        body = _maybe_query(self, "#edit-preview-body", Static)
        preview = _maybe_query(self, "#edit-preview", Container)
        if body is None or caption is None or preview is None:
            return
        if self.staged_action is not None:
            caption.update("Preview (predicted next state)")
            caption.remove_class("hidden")
            preview.add_class("-staged")
        else:
            caption.update("Preview (saved state)")
            caption.remove_class("hidden")
            preview.remove_class("-staged")
        body.update(format_detail_summary(self._world, state_dir=self._forge.state_dir))

    # ------------------------------------------------------------------
    # Reactives
    # ------------------------------------------------------------------

    def watch_dirty(self, _old: bool, _new: bool) -> None:
        title = _maybe_query(self, "#edit-title", Static)
        if title is not None:
            title.update(self._render_title())

    def watch_staged_action(self, _old: Action | None, _new: Action | None) -> None:
        self._refresh_preview_static()

    # ------------------------------------------------------------------
    # Input events
    # ------------------------------------------------------------------

    @on(Input.Changed, "#edit-name")
    def _on_name_changed(self, event: Input.Changed) -> None:
        new_name = event.value.strip()
        if not new_name:
            return
        self._world.name = new_name
        self._world.metadata["name"] = new_name
        self.dirty = True
        title = _maybe_query(self, "#edit-title", Static)
        if title is not None:
            title.update(self._render_title())

    @on(Select.Changed, "#edit-provider")
    def _on_provider_changed(self, event: Select.Changed) -> None:
        if isinstance(event.value, str) and event.value != self._world.provider:
            self._world.provider = event.value
            self.dirty = True
            pill = _maybe_query(self, "#provider-pill", ProviderStatusPill)
            if pill is not None:
                pill.label = event.value

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    def action_add_object(self) -> None:
        self.app.push_screen(EditObjectScreen(), self._handle_object_result)

    def _handle_object_result(self, spec: SceneObjectSpec | None) -> None:
        if spec is None:
            return
        try:
            scene_object = _scene_object_from_spec(spec)
            self._world.add_object(scene_object)
        except WorldForgeError as exc:
            self.app.notify(str(exc), severity="error", title="Scene object")
            return
        self.dirty = True
        self._populate_objects()
        # Stage a spawn action so the preview pane reflects the addition.
        self.staged_action = Action.spawn_object(
            spec.name,
            position=Position(spec.x, spec.y, spec.z),
        )
        self._run_preview()

    def action_remove_object(self) -> None:
        options = _maybe_query(self, "#edit-objects", OptionList)
        if options is None:
            return
        highlighted = options.highlighted
        if highlighted is None:
            return
        option = options.get_option_at_index(highlighted)
        if option.id is None:
            return
        removed = self._world.remove_object_by_id(option.id)
        if removed is not None:
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
        self._original = self._clone_world(self._world)
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

    BINDINGS: ClassVar[list[Binding]] = [Binding("escape", "cancel", "Cancel", show=True)]

    DEFAULT_CSS = """
    RegisterProviderModal {
        align: center middle;
    }

    RegisterProviderModal > #register-provider-card {
        width: 64;
        height: auto;
        padding: 1 2;
        border: round $accent;
        background: $surface;
    }

    RegisterProviderModal .field-label {
        color: $text-muted;
        height: 1;
    }

    RegisterProviderModal Input {
        margin-bottom: 1;
    }

    RegisterProviderModal #register-provider-actions {
        height: auto;
        align: right middle;
        padding-top: 1;
    }

    RegisterProviderModal Button {
        margin-left: 1;
    }
    """

    def compose(self) -> ComposeResult:
        with Container(id="register-provider-card"):
            yield Static("Register deterministic provider", id="register-provider-title")
            yield Static("Provider id", classes="field-label")
            yield Input(placeholder="mock-lab", id="register-provider-name")
            yield Static(
                "Registers a MockProvider variant. Live optional runtimes remain host-owned.",
                id="register-provider-note",
            )
            with Horizontal(id="register-provider-actions"):
                yield Button("Cancel", id="register-provider-cancel", variant="default")
                yield Button("Register", id="register-provider-submit", variant="primary")

    def on_mount(self) -> None:
        name = _maybe_query(self, "#register-provider-name", Input)
        if name is not None:
            name.focus()

    @on(Button.Pressed, "#register-provider-submit")
    @on(Input.Submitted, "#register-provider-name")
    def _submit(self) -> None:
        value = self.query_one("#register-provider-name", Input).value.strip()
        if not value:
            self.app.notify("Provider id must be non-empty.", severity="error", title="Provider")
            return
        self.dismiss(MockProvider(name=value))

    @on(Button.Pressed, "#register-provider-cancel")
    def _cancel_button(self) -> None:
        self.dismiss(None)

    def action_cancel(self) -> None:
        self.dismiss(None)


class ProvidersScreen(Screen):  # pragma: no cover - exercised by Pilot tests.
    """Capability matrix and live ``mock.predict`` execution surface."""

    BINDINGS: ClassVar[list[Binding]] = [
        Binding("enter", "select_provider", "Use", show=True),
        Binding("p", "run_predict", "Predict", show=True),
        Binding("r", "register_provider", "Register", show=True),
        Binding("escape", "cancel_or_back", "Cancel/Back", show=True),
    ]

    DEFAULT_CSS = """
    ProvidersScreen {
        background: $background;
        color: $foreground;
    }

    #providers-root {
        height: 1fr;
        padding: 1 2;
    }

    #providers-body {
        height: 1fr;
    }

    #providers-table-wrap {
        width: 2fr;
        margin-right: 1;
        border: round $panel;
        background: $surface;
    }

    #providers-table {
        height: 1fr;
        background: $surface;
    }

    #providers-empty {
        padding: 1 2;
        color: $text-muted;
    }

    #providers-empty.hidden {
        display: none;
    }

    #providers-detail {
        width: 1fr;
        padding: 1 2;
        border: round $panel;
        background: $surface;
    }

    #providers-log {
        height: 10;
        margin-top: 1;
        border: round $panel;
        background: $surface;
    }

    #providers-actions {
        height: 3;
        margin-top: 1;
        align: right middle;
    }

    #providers-actions Button {
        margin-left: 1;
    }
    """

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
        with Horizontal(id="chrome"):
            yield Breadcrumb(id="breadcrumb")
            yield ProviderStatusPill(id="provider-pill")
        with Container(id="providers-root"):
            with Horizontal(id="providers-body"):
                with Container(id="providers-table-wrap"):
                    yield DataTable(zebra_stripes=True, cursor_type="row", id="providers-table")
                    yield Static(
                        "No providers registered — set env vars or run with provider mock.",
                        id="providers-empty",
                        classes="hidden",
                    )
                yield Static("Select a provider.", id="providers-detail")
            yield RichLog(highlight=True, markup=True, max_lines=5000, id="providers-log")
            with Horizontal(id="providers-actions"):
                yield Button("Run predict", id="provider-run", variant="primary")
                yield Button("Cancel", id="provider-cancel", variant="warning")
                yield Button("Register", id="provider-register", variant="default")
        yield Footer()

    def on_mount(self) -> None:
        self._update_chrome()
        self._build_table()

    def on_screen_resume(self) -> None:
        self._update_chrome()

    def _update_chrome(self) -> None:
        breadcrumb = _maybe_query(self, "#breadcrumb", Breadcrumb)
        if breadcrumb is not None:
            breadcrumb.path = ("worldforge", "providers")
        pill = _maybe_query(self, "#provider-pill", ProviderStatusPill)
        if pill is not None:
            provider = getattr(self.app, "current_provider", "mock")
            pill.label = f"{provider} · predict"

    def _build_table(self) -> None:
        table = _maybe_query(self, "#providers-table", DataTable)
        empty = _maybe_query(self, "#providers-empty", Static)
        if table is None:
            return
        table.clear(columns=True)
        table.add_columns("provider", "status", "credentials", "runtime", *CAPABILITY_NAMES)
        rows = provider_connector_summaries(self._forge)
        self._provider_rows = {row.name: row for row in rows}
        self._provider_names = [row.name for row in rows]
        for row in rows:
            cells = [
                self._capability_cell(name in row.capabilities, row.implementation_status)
                for name in CAPABILITY_NAMES
            ]
            credentials = "missing" if row.missing_env_vars else "ok"
            runtime = "deps" if row.status == "missing_dependency" else "ok"
            if row.status == "scaffold":
                credentials = "n/a"
                runtime = "scaffold"
            table.add_row(row.name, row.status, credentials, runtime, *cells, key=row.name)
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

    @staticmethod
    def _capability_cell(enabled: bool, implementation_status: str) -> str:
        if not enabled:
            return ""
        return "○" if implementation_status == "scaffold" else "●"

    @on(DataTable.RowHighlighted, "#providers-table")
    def _on_provider_highlighted(self, event: DataTable.RowHighlighted) -> None:
        key = event.row_key.value if event.row_key else None
        if isinstance(key, str):
            self.current_row_provider = key

    def watch_current_row_provider(self, _old: str | None, _new: str | None) -> None:
        self._refresh_detail()

    def _refresh_detail(self) -> None:
        detail = _maybe_query(self, "#providers-detail", Static)
        if detail is None:
            return
        provider = self.current_row_provider
        if provider is None:
            detail.update("No provider selected.")
            return
        row = self._provider_rows.get(provider)
        if row is None:
            detail.update("No provider selected.")
            return
        summary = self._last_call_summary.get(provider, {})
        env_vars = ", ".join(row.required_env_vars) if row.required_env_vars else "none"
        missing = ", ".join(row.missing_env_vars) if row.missing_env_vars else "none"
        dependencies = ", ".join(row.optional_dependencies) if row.optional_dependencies else "none"
        last = (
            f"{summary.get('phase')} "
            f"{float(summary.get('latency_ms') or 0.0):.2f} ms "
            f"retries={summary.get('retries', 0)}"
            if summary
            else "No run captured — press p to run mock.predict."
        )
        detail.update(
            "\n".join(
                [
                    f"Provider: {provider}",
                    f"Status: {row.status} ({row.implementation_status})",
                    f"Capabilities: {', '.join(row.capabilities) or 'none'}",
                    f"Health: {row.health}",
                    f"Required env vars: {env_vars}",
                    f"Missing env vars: {missing}",
                    f"Optional deps: {dependencies}",
                    f"Next command: {row.smoke_command}",
                    "Triage: " + " | ".join(row.triage_steps),
                    f"Last call: {last}",
                ]
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
        provider = getattr(self.app, "current_provider", "mock")
        if provider not in self._provider_names:
            provider = self.current_row_provider or "mock"
        self._run_predict(str(provider))

    @on(Button.Pressed, "#provider-run")
    def _run_button(self) -> None:
        self.action_run_predict()

    @on(Button.Pressed, "#provider-cancel")
    def _cancel_button(self) -> None:
        self.action_cancel_or_back()

    @on(Button.Pressed, "#provider-register")
    def _register_button(self) -> None:
        self.action_register_provider()

    def action_cancel_or_back(self) -> None:
        if self.running_operation == "running":
            self.workers.cancel_group(self, "provider")
            self.running_operation = "cancelled"
            provider = getattr(self.app, "current_provider", self.current_row_provider or "mock")
            self.post_message(RunCancelled(provider=str(provider)))
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
        log = _maybe_query(self, "#providers-log", RichLog)
        if log is not None:
            log.write(_format_provider_event(event.event))
        self._last_call_summary[event.event.provider] = _event_summary(event.event)
        self._refresh_detail()

    def on_run_completed(self, event: RunCompleted) -> None:
        event.stop()
        self.running_operation = "done"
        self._last_call_summary[event.provider] = {
            "phase": "success",
            "latency_ms": event.latency_ms,
            "retries": 0,
        }
        self._refresh_detail()
        self.app.notify(
            f"{event.provider}.predict completed in {event.latency_ms:.2f} ms.",
            title="Provider",
        )

    def on_run_cancelled(self, event: RunCancelled) -> None:
        event.stop()
        self.running_operation = "cancelled"
        log = _maybe_query(self, "#providers-log", RichLog)
        if log is not None:
            log.write(Text("cancelled provider run", style="bold yellow"))
        self.app.notify("Cancelled provider run.", severity="warning", title="Provider")


class EvalScreen(Screen):  # pragma: no cover - exercised by Pilot tests.
    """Run built-in deterministic evaluation suites from the TUI."""

    BINDINGS: ClassVar[list[Binding]] = [
        Binding("r", "run_eval", "Run", show=True),
        Binding("escape", "cancel_or_back", "Cancel/Back", show=True),
    ]

    DEFAULT_CSS = """
    EvalScreen {
        background: $background;
        color: $foreground;
    }

    #eval-root {
        height: 1fr;
        padding: 1 2;
    }

    #eval-form {
        width: 34;
        margin-right: 1;
        padding: 1 2;
        border: round $panel;
        background: $surface;
    }

    #eval-output {
        width: 1fr;
    }

    #eval-log {
        height: 10;
        border: round $panel;
        background: $surface;
    }

    #eval-verdict {
        height: auto;
        padding: 1 2;
        margin-bottom: 1;
        border: round $panel;
        background: $surface;
    }

    EvalScreen Select, EvalScreen Button {
        margin-bottom: 1;
    }
    """

    running: reactive[bool] = reactive(False, init=False)

    def __init__(self, *, forge: WorldForge) -> None:
        super().__init__()
        self._forge = forge

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Horizontal(id="chrome"):
            yield Breadcrumb(id="breadcrumb")
            yield ProviderStatusPill(id="provider-pill")
        with Horizontal(id="eval-root"):
            with Vertical(id="eval-form"):
                yield Static("Suite")
                yield Select(
                    [(suite, suite) for suite in list_eval_suites()],
                    value="planning",
                    allow_blank=False,
                    id="eval-suite",
                )
                yield Static("Provider")
                yield Select(
                    [(provider, provider) for provider in self._forge.providers()],
                    value=getattr(self.app, "current_provider", "mock"),
                    allow_blank=False,
                    id="eval-provider",
                )
                yield Button("Run eval", id="eval-run", variant="primary")
            with Vertical(id="eval-output"):
                yield Static("No suite run yet — press r to execute.", id="eval-verdict")
                yield RichLog(highlight=True, markup=True, max_lines=5000, id="eval-log")
                yield ExportPane(widget_id="eval-export")
        yield Footer()

    def on_mount(self) -> None:
        self._update_chrome()

    def _update_chrome(self) -> None:
        breadcrumb = _maybe_query(self, "#breadcrumb", Breadcrumb)
        if breadcrumb is not None:
            breadcrumb.path = ("worldforge", "eval")
        pill = _maybe_query(self, "#provider-pill", ProviderStatusPill)
        if pill is not None:
            pill.label = f"{getattr(self.app, 'current_provider', 'mock')} · eval"

    @on(Button.Pressed, "#eval-run")
    def _run_button(self) -> None:
        self.action_run_eval()

    def action_run_eval(self) -> None:
        suite = self.query_one("#eval-suite", Select).value
        provider = self.query_one("#eval-provider", Select).value
        if isinstance(suite, str) and isinstance(provider, str):
            self._run_eval(suite, provider)

    def action_cancel_or_back(self) -> None:
        if self.running:
            self.workers.cancel_group(self, "eval")
            self.running = False
            self.app.notify("Cancelled eval run.", severity="warning", title="Eval")
            return
        self.app.action_switch_screen("home")

    @work(thread=True, group="eval", exclusive=True, name="eval.run")
    def _run_eval(self, suite_id: str, provider: str) -> None:
        self.app.call_from_thread(setattr, self, "running", True)
        self.app.call_from_thread(self._write_eval_log, f"running {suite_id} x {provider}")
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
        run = self._run_from_eval_report(suite_id, artifacts, report.to_dict(), path)
        self.app.call_from_thread(self._complete_report_run, run, artifacts, path, "eval")

    def _write_eval_log(self, line: str | Text) -> None:
        log = _maybe_query(self, "#eval-log", RichLog)
        if log is not None:
            log.write(line)

    def _run_from_eval_report(
        self,
        suite_id: str,
        artifacts: dict[str, str],
        payload: dict[str, Any],
        path: Path,
    ) -> HarnessRun:
        passed = sum(1 for result in payload.get("results", []) if result.get("passed"))
        total = len(payload.get("results", []))
        flow = HarnessFlow(
            id=f"eval-{suite_id}",
            title=f"Evaluation: {payload.get('suite', suite_id)}",
            short_title=f"Eval {suite_id}",
            focus="evaluation",
            provider=", ".join(
                summary.get("provider", "provider")
                for summary in payload.get("provider_summaries", [])
            )
            or "provider",
            capability="eval",
            command=f"worldforge eval --suite {suite_id}",
            accent="",
            summary=f"{passed}/{total} scenarios passed.",
        )
        return HarnessRun(
            flow=flow,
            state_dir=self._forge.state_dir,
            summary=payload,
            steps=(
                HarnessStep(
                    "Run evaluation", "Execute built-in suite.", f"{passed}/{total} passed."
                ),
            ),
            metrics=tuple(
                HarnessMetric(
                    summary.get("provider", "provider"),
                    f"{summary.get('passed_scenario_count', 0)}/{summary.get('scenario_count', 0)}",
                    f"average_score={float(summary.get('average_score', 0.0)):.2f}",
                )
                for summary in payload.get("provider_summaries", [])
            ),
            transcript=("kind: eval", f"suite: {suite_id}", f"report_path: {path}"),
            kind="eval",
            report_path=path,
            artifacts=artifacts,
        )

    def _complete_report_run(
        self,
        run: HarnessRun,
        artifacts: dict[str, str],
        path: Path,
        kind: str,
    ) -> None:
        self.running = False
        export = _maybe_query(self, "#eval-export", ExportPane) or _maybe_query(
            self, "#benchmark-export", ExportPane
        )
        if export is not None:
            export.set_artifacts(artifacts)
        verdict = _maybe_query(self, "#eval-verdict", Static)
        if verdict is not None:
            verdict.update(f"Report saved: {path}")
        self.post_message(ReportExported(path=path, kind=kind))
        self.app.push_screen(RunInspectorScreen(state_dir=self._forge.state_dir, run=run))

    def on_capability_mismatch(self, event: CapabilityMismatch) -> None:
        event.stop()
        self.app.notify(str(event.error), severity="error", title="Capability mismatch")
        log = _maybe_query(self, "#eval-log", RichLog)
        if log is not None:
            log.write(Text(str(event.error), style="bold red"))


class BenchmarkScreen(Screen):  # pragma: no cover - exercised by Pilot tests.
    """Run capability-aware provider benchmarks from the TUI."""

    BINDINGS: ClassVar[list[Binding]] = [
        Binding("r", "run_benchmark", "Run", show=True),
        Binding("escape", "cancel_or_back", "Cancel/Back", show=True),
    ]

    DEFAULT_CSS = """
    BenchmarkScreen {
        background: $background;
        color: $foreground;
    }

    #benchmark-root {
        height: 1fr;
        padding: 1 2;
    }

    #benchmark-form {
        width: 34;
        margin-right: 1;
        padding: 1 2;
        border: round $panel;
        background: $surface;
    }

    #benchmark-output {
        width: 1fr;
    }

    #benchmark-log {
        height: 10;
        border: round $panel;
        background: $surface;
    }

    #benchmark-stats {
        height: auto;
        padding: 1 2;
        margin-bottom: 1;
        border: round $panel;
        background: $surface;
    }

    BenchmarkScreen Select, BenchmarkScreen Input, BenchmarkScreen Button {
        margin-bottom: 1;
    }
    """

    running: reactive[bool] = reactive(False, init=False)

    def __init__(self, *, forge: WorldForge) -> None:
        super().__init__()
        self._forge = forge
        self._samples: list[float] = []

    def compose(self) -> ComposeResult:
        provider = getattr(self.app, "current_provider", "mock")
        yield Header(show_clock=True)
        with Horizontal(id="chrome"):
            yield Breadcrumb(id="breadcrumb")
            yield ProviderStatusPill(id="provider-pill")
        with Horizontal(id="benchmark-root"):
            with Vertical(id="benchmark-form"):
                yield Static("Provider")
                yield Select(
                    [(name, name) for name in self._forge.providers()],
                    value=provider,
                    allow_blank=False,
                    id="benchmark-provider",
                )
                yield Static("Operation")
                yield Select(
                    [(operation, operation) for operation in BENCHMARKABLE_OPERATIONS],
                    value="predict",
                    allow_blank=False,
                    id="benchmark-operation",
                )
                yield Static("Iterations")
                yield Input(value="5", id="benchmark-iterations")
                yield Button("Run benchmark", id="benchmark-run", variant="primary")
            with Vertical(id="benchmark-output"):
                yield Static("No benchmark run yet — press r to execute.", id="benchmark-stats")
                yield ProgressBar(total=5, id="benchmark-progress")
                yield RichLog(highlight=True, markup=True, max_lines=5000, id="benchmark-log")
                yield ExportPane(widget_id="benchmark-export")
        yield Footer()

    def on_mount(self) -> None:
        self._update_chrome()

    def _update_chrome(self) -> None:
        breadcrumb = _maybe_query(self, "#breadcrumb", Breadcrumb)
        if breadcrumb is not None:
            breadcrumb.path = ("worldforge", "benchmark")
        pill = _maybe_query(self, "#provider-pill", ProviderStatusPill)
        if pill is not None:
            pill.label = f"{getattr(self.app, 'current_provider', 'mock')} · benchmark"

    @on(Button.Pressed, "#benchmark-run")
    def _run_button(self) -> None:
        self.action_run_benchmark()

    def action_run_benchmark(self) -> None:
        provider = self.query_one("#benchmark-provider", Select).value
        operation = self.query_one("#benchmark-operation", Select).value
        try:
            iterations = int(self.query_one("#benchmark-iterations", Input).value or "5")
        except ValueError:
            self.app.notify("Iterations must be an integer.", severity="error", title="Benchmark")
            return
        if isinstance(provider, str) and isinstance(operation, str):
            progress = _maybe_query(self, "#benchmark-progress", ProgressBar)
            if progress is not None:
                progress.total = iterations
                progress.progress = 0
            self._samples = []
            self._run_benchmark(provider, operation, iterations)

    def action_cancel_or_back(self) -> None:
        if self.running:
            self.workers.cancel_group(self, "benchmark")
            self.running = False
            self.app.notify("Cancelled benchmark run.", severity="warning", title="Benchmark")
            return
        self.app.action_switch_screen("home")

    @work(thread=True, group="benchmark", exclusive=True, name="benchmark.run")
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
        run = self._run_from_benchmark_report(artifacts, report.to_dict(), path)
        self.app.call_from_thread(self._complete_report_run, run, artifacts, path)

    def _record_benchmark_sample(self, sample: JSONDict, total: int) -> None:
        latency = float(sample.get("latency_ms") or 0.0)
        self._samples.append(latency)
        progress = _maybe_query(self, "#benchmark-progress", ProgressBar)
        if progress is not None:
            progress.progress = min(len(self._samples), total)
        log = _maybe_query(self, "#benchmark-log", RichLog)
        if log is not None:
            log.write(
                f"{sample.get('provider')}.{sample.get('operation')} "
                f"#{sample.get('iteration')} {latency:.2f} ms"
            )
        median = statistics.median(self._samples)
        p95 = sorted(self._samples)[max(0, int((len(self._samples) - 1) * 0.95))]
        stats = _maybe_query(self, "#benchmark-stats", Static)
        if stats is not None:
            stats.update(
                f"Samples: {len(self._samples)}/{total}  median={median:.2f} ms  p95={p95:.2f} ms"
            )

    def _run_from_benchmark_report(
        self,
        artifacts: dict[str, str],
        payload: dict[str, Any],
        path: Path,
    ) -> HarnessRun:
        results = payload.get("results", [])
        flow = HarnessFlow(
            id="benchmark",
            title="Benchmark Report",
            short_title="Benchmark",
            focus="latency / retry / throughput",
            provider=", ".join(sorted({result.get("provider", "provider") for result in results}))
            or "provider",
            capability="benchmark",
            command="worldforge benchmark",
            accent="",
            summary=f"{len(results)} benchmark rows.",
        )
        return HarnessRun(
            flow=flow,
            state_dir=self._forge.state_dir,
            summary=payload,
            steps=(
                HarnessStep(
                    "Run benchmark", "Execute provider operations.", f"{len(results)} rows."
                ),
            ),
            metrics=tuple(
                HarnessMetric(
                    f"{result.get('provider')}.{result.get('operation')}",
                    f"{float(result.get('average_latency_ms') or 0.0):.2f} ms",
                    f"ok={result.get('success_count')}/{result.get('iterations')}",
                )
                for result in results
            ),
            transcript=("kind: benchmark", f"report_path: {path}", f"rows: {len(results)}"),
            kind="benchmark",
            report_path=path,
            artifacts=artifacts,
        )

    def _complete_report_run(
        self,
        run: HarnessRun,
        artifacts: dict[str, str],
        path: Path,
    ) -> None:
        self.running = False
        export = _maybe_query(self, "#benchmark-export", ExportPane)
        if export is not None:
            export.set_artifacts(artifacts)
        stats = _maybe_query(self, "#benchmark-stats", Static)
        if stats is not None:
            stats.update(f"Report saved: {path}")
        self.post_message(ReportExported(path=path, kind="benchmark"))
        self.app.push_screen(RunInspectorScreen(state_dir=self._forge.state_dir, run=run))

    def on_capability_mismatch(self, event: CapabilityMismatch) -> None:
        event.stop()
        self.app.notify(str(event.error), severity="error", title="Benchmark")
        log = _maybe_query(self, "#benchmark-log", RichLog)
        if log is not None:
            log.write(Text(str(event.error), style="bold red"))


# ---------------------------------------------------------------------------
# Robotics Replay Showcase Report
# ---------------------------------------------------------------------------


def _robotics_number(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    number = float(value)
    if number != number or number in (float("inf"), float("-inf")):
        return None
    return number


def _robotics_nested(payload: dict[str, object], *keys: str) -> object:
    current: object = payload
    for key in keys:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


def _robotics_candidate_targets(payload: dict[str, object]) -> list[dict[str, object]]:
    value = _robotics_nested(payload, "visualization", "candidate_targets")
    return [dict(item) for item in value] if isinstance(value, list) else []


def _robotics_scores(payload: dict[str, object]) -> list[float]:
    value = _robotics_nested(payload, "score_result", "scores")
    if not isinstance(value, list):
        return []
    scores: list[float] = []
    for item in value:
        number = _robotics_number(item)
        if number is not None:
            scores.append(number)
    return scores


def _robotics_selected_index(payload: dict[str, object]) -> int | None:
    value = _robotics_nested(payload, "score_result", "best_index")
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value


def _robotics_event_duration(
    payload: dict[str, object],
    *,
    provider: str,
    operation: str,
) -> float | None:
    events = payload.get("provider_events")
    if not isinstance(events, list):
        return None
    for event in reversed(events):
        if not isinstance(event, dict):
            continue
        if event.get("provider") == provider and event.get("operation") == operation:
            return _robotics_number(event.get("duration_ms"))
    return None


def _robotics_final_position(payload: dict[str, object]) -> dict[str, float] | None:
    position = _robotics_nested(payload, "execution", "final_block_position")
    if not isinstance(position, dict):
        return None
    x = _robotics_number(position.get("x"))
    y = _robotics_number(position.get("y"))
    z = _robotics_number(position.get("z"))
    if x is None or y is None or z is None:
        return None
    return {"x": x, "y": y, "z": z}


def _robotics_rerun_recording_path(payload: dict[str, object]) -> Path | None:
    rerun = payload.get("rerun")
    if not isinstance(rerun, dict):
        return None
    save_path = rerun.get("save_path")
    if not isinstance(save_path, str) or not save_path.strip():
        return None
    path = Path(save_path).expanduser()
    return path if path.is_absolute() else path.resolve()


def _robotics_rerun_viewer_command(path: Path) -> list[str]:
    return [
        "uvx",
        "--from",
        "rerun-sdk>=0.24,<0.32",
        "rerun",
        str(path),
    ]


def _robotics_rerun_viewer_command_text(path: Path) -> str:
    return " ".join(shlex.quote(part) for part in _robotics_rerun_viewer_command(path))


def _robotics_color(token: str) -> str:
    return {
        "accent": "cyan",
        "success": "green",
        "warning": "yellow",
        "muted": "bright_black",
        "panel": "blue",
    }.get(token, "white")


ROBOTICS_REPORT_GUIDE_ROWS: tuple[tuple[str, str, str], ...] = (
    (
        "Runtime bars",
        "policy, score, plan, and total are wall-clock milliseconds for the completed run.",
        "Policy is the LeRobot checkpoint call; score is the LeWorldModel cost call.",
    ),
    (
        "Tensor contract",
        "tensor MB and elements describe the preprocessed score tensors sent to LeWorldModel.",
        "They explain runtime size and shape, not physical skill or task success by themselves.",
    ),
    (
        "Candidate ranking",
        "lower cost wins; SELECTED is the action chunk WorldForge mock-replays.",
        "The selected row should agree with the tabletop target/final marker and best_index.",
    ),
)

ROBOTICS_TABLETOP_DIAGRAM = """Tabletop replay
---------------
legend: S=start, G=goal, T=selected target, F=mock final, X=selected+final
selected candidate: #2
+------------------------------------------+
|                                          |
|                                          |
|                                          |
|                               0          |
|                          1               |
|                                          |
|S                   G                     |
|                                          |
|               X                          |
|                                          |
|                                          |
|                                          |
|                                          |
+------------------------------------------+
x=0.00             x=0.50             x=1.00"""

ROBOTICS_TABLETOP_HELP_TEXT = (
    "Read the tabletop replay as a top-down map of the PushT workspace. "
    "S is the start, G is the goal, numbered marks are non-selected policy "
    "candidates, T is the selected target, F is the mock final position, and "
    "X means the selected target and mock final state overlap on the same rendered cell. "
    "Mentally: LeRobot proposes possible pushes, LeWorldModel assigns costs, "
    "WorldForge picks the lowest-cost candidate, then the local mock world replays that action. "
    "This is a planning visualization, not a hardware camera feed or robot-control trace."
)


class RoboticsHeroPane(Static, _ThemedRenderer):
    """Top-level real robotics showcase identity and run contract."""

    def __init__(self, summary: dict[str, object], summary_path: Path | None) -> None:
        super().__init__()
        self.summary = summary
        self.summary_path = summary_path

    def on_mount(self) -> None:
        policy_path = _robotics_nested(self.summary, "inputs", "policy_path") or "unknown"
        checkpoint = self.summary.get("checkpoint_display") or self.summary.get("checkpoint")
        selected = _robotics_selected_index(self.summary)
        best_score = _robotics_nested(self.summary, "score_result", "best_score")
        score_text = (
            f"{float(best_score):.6f}" if _robotics_number(best_score) is not None else "n/a"
        )
        artifact = str(self.summary_path or self.summary.get("checkpoint_display") or "summary")
        title = Text("WorldForge Robotics Showcase", style=f"bold {_robotics_color('accent')}")
        subtitle = Text("real LeRobot policy + real LeWorldModel checkpoint scoring", style="dim")
        contract = Text()
        contract.append("REAL policy", style=f"bold {_robotics_color('success')}")
        contract.append("  +  ")
        contract.append("REAL score", style=f"bold {_robotics_color('success')}")
        contract.append("  +  ")
        contract.append("LOCAL mock replay", style=f"bold {_robotics_color('warning')}")
        body = Table.grid(expand=True)
        body.add_column(ratio=1)
        body.add_column(justify="right", ratio=1)
        body.add_row(Text("policy", style="dim"), Text(str(policy_path), style="bold"))
        body.add_row(Text("checkpoint", style="dim"), Text(str(checkpoint), style="bold"))
        body.add_row(
            Text("selected candidate", style="dim"),
            Text(f"#{selected} / score {score_text}", style=f"bold {_robotics_color('success')}"),
        )
        body.add_row(Text("artifact", style="dim"), Text(artifact, style=_robotics_color("muted")))
        self.update(
            Panel(
                Group(title, subtitle, Text(""), contract, Text(""), body),
                title="REAL ROBOTICS POLICY + WORLD MODEL",
                border_style=_robotics_color("accent"),
            )
        )


class RoboticsPipelinePane(Static, _ThemedRenderer):
    """Visual pipeline graph for the real policy+score run."""

    def __init__(self, summary: dict[str, object]) -> None:
        super().__init__()
        self.summary = summary

    def on_mount(self) -> None:
        accent = _robotics_color("accent")
        success = _robotics_color("success")
        warning = _robotics_color("warning")
        rows = [
            ("1", "PushT observation", "packaged host-preprocessed task state", success),
            ("2", "LeRobot policy", "select_action from lerobot/diffusion_pusht", accent),
            ("3", "Candidate bridge", "3 checkpoint-native action tensors", accent),
            ("4", "LeWorldModel cost", "lower cost wins", success),
            ("5", "WorldForge planner", "policy+score candidate selection", accent),
            ("6", "Mock replay", "local execution only, no hardware control", warning),
        ]
        table = Table.grid(expand=True, padding=(0, 2))
        table.add_column(justify="right", no_wrap=True)
        table.add_column(no_wrap=True)
        table.add_column(ratio=2)
        for index, label, detail, color in rows:
            table.add_row(
                Text(f"{index}.", style=f"bold {color}"), Text(label, style="bold"), detail
            )
            if index != rows[-1][0]:
                table.add_row("", Text("|", style=color), Text("v", style=color))
        self.update(Panel(table, title="Pipeline Flow", border_style=accent))


class RoboticsReportGuidePane(Static, _ThemedRenderer):
    """Compact guide for interpreting the report panes."""

    def on_mount(self) -> None:
        table = Table(
            expand=True,
            show_header=True,
            header_style=f"bold {_robotics_color('accent')}",
            box=box.SIMPLE,
        )
        table.add_column("pane", no_wrap=True)
        table.add_column("read it as", ratio=2)
        table.add_column("watch for", ratio=2)
        for pane, meaning, watch_for in ROBOTICS_REPORT_GUIDE_ROWS:
            table.add_row(
                Text(pane, style=f"bold {_robotics_color('success')}"),
                meaning,
                Text(watch_for, style=_robotics_color("muted")),
            )
        footer = Text(
            "Press ? for the tabletop replay legend and mental model.",
            style=f"bold {_robotics_color('warning')}",
        )
        self.update(
            Panel(
                Group(table, Text(""), footer),
                title="Reading The Report",
                border_style=_robotics_color("panel"),
            )
        )


class RoboticsRerunPane(Static, _ThemedRenderer):
    """Rerun artifact location and viewer command."""

    def __init__(self, summary: dict[str, object]) -> None:
        super().__init__()
        self.summary = summary

    def on_mount(self) -> None:
        path = _robotics_rerun_recording_path(self.summary)
        if path is None:
            self.update(
                Panel(
                    Text("Rerun recording was not enabled for this run.", style="dim"),
                    title="Rerun Recording",
                    border_style=_robotics_color("panel"),
                )
            )
            return
        rerun = self.summary.get("rerun")
        size = None
        written = None
        if isinstance(rerun, dict):
            size = rerun.get("recording_size_bytes")
            written = rerun.get("recording_written")
        status = "written" if written else "configured"
        if isinstance(size, int) and size > 0:
            status = f"{status}, {size} bytes"
        command = _robotics_rerun_viewer_command_text(path)
        table = Table.grid(expand=True)
        table.add_column(no_wrap=True)
        table.add_column(ratio=1)
        table.add_row(Text("path", style="dim"), Text(str(path), style="bold"))
        table.add_row(Text("status", style="dim"), Text(status, style="bold"))
        table.add_row(Text("open", style="dim"), Text(command, style=_robotics_color("accent")))
        table.add_row(Text("shortcut", style="dim"), Text("press o", style="bold"))
        self.update(Panel(table, title="Rerun Recording", border_style=_robotics_color("success")))


class RoboticsMetricsPane(Static, _ThemedRenderer):
    """Runtime bars and tensor contract summary."""

    def __init__(self, summary: dict[str, object]) -> None:
        super().__init__()
        self.summary = summary

    @staticmethod
    def _bar(value: float, maximum: float, *, width: int = 34) -> str:
        fill = 0 if maximum <= 0 else max(1, min(width, round((value / maximum) * width)))
        return f"{'#' * fill:<{width}}"

    def on_mount(self) -> None:
        policy_ms = _robotics_event_duration(self.summary, provider="lerobot", operation="policy")
        score_ms = _robotics_event_duration(
            self.summary, provider="leworldmodel", operation="score"
        )
        plan_ms = _robotics_number(_robotics_nested(self.summary, "metrics", "plan_latency_ms"))
        total_ms = _robotics_number(_robotics_nested(self.summary, "metrics", "total_latency_ms"))
        rows = [
            ("policy", policy_ms, _robotics_color("accent")),
            ("score", score_ms, _robotics_color("success")),
            ("plan", plan_ms, _robotics_color("accent")),
            ("total", total_ms, _robotics_color("warning")),
        ]
        maximum = max((value or 0.0) for _label, value, _color in rows)
        table = Table.grid(expand=True, padding=(0, 2))
        table.add_column(no_wrap=True)
        table.add_column(justify="right", no_wrap=True)
        table.add_column(ratio=1)
        for label, value, color in rows:
            if value is None:
                table.add_row(label, "n/a", "")
                continue
            table.add_row(
                Text(label, style="dim"),
                Text(f"{value:.2f} ms", style=f"bold {color}"),
                Text(self._bar(value, maximum), style=color),
            )
        tensor_mb = _robotics_nested(self.summary, "inputs", "approx_float32_mb")
        total_elements = _robotics_nested(self.summary, "inputs", "total_tensor_elements")
        table.add_row("", "", "")
        table.add_row(Text("tensor MB", style="dim"), Text(str(tensor_mb), style="bold"), "")
        table.add_row(Text("elements", style="dim"), Text(str(total_elements), style="bold"), "")
        self.update(
            Panel(table, title="Runtime + Tensor Contract", border_style=_robotics_color("accent"))
        )


class RoboticsCandidatePane(Static, _ThemedRenderer):
    """Candidate scores, targets, and selection status."""

    def __init__(self, summary: dict[str, object]) -> None:
        super().__init__()
        self.summary = summary

    def on_mount(self) -> None:
        targets = _robotics_candidate_targets(self.summary)
        scores = _robotics_scores(self.summary)
        selected = _robotics_selected_index(self.summary)
        table = Table(
            expand=True,
            show_header=True,
            header_style=f"bold {_robotics_color('accent')}",
            box=box.SIMPLE_HEAVY,
        )
        table.add_column("candidate", justify="right", no_wrap=True)
        table.add_column("target", no_wrap=True)
        table.add_column("cost", justify="right", no_wrap=True)
        table.add_column("status", no_wrap=True)
        for target in targets:
            index = int(target.get("index", -1))
            score = scores[index] if 0 <= index < len(scores) else None
            x = _robotics_number(target.get("x")) or 0.0
            y = _robotics_number(target.get("y")) or 0.0
            z = _robotics_number(target.get("z")) or 0.0
            status = "SELECTED" if index == selected else ""
            style = f"bold {_robotics_color('success')}" if index == selected else ""
            table.add_row(
                f"#{index}",
                f"x={x:.3f} y={y:.3f} z={z:.3f}",
                "n/a" if score is None else f"{score:.6f}",
                Text(status, style=style),
                style=style,
            )
        self.update(
            Panel(table, title="Candidate Ranking", border_style=_robotics_color("success"))
        )


class RoboticsTabletopPane(Static, _ThemedRenderer):
    """Compact tabletop map with stable marker semantics."""

    def __init__(self, summary: dict[str, object]) -> None:
        super().__init__()
        self.summary = summary

    def _map_lines(self) -> list[str]:
        targets = _robotics_candidate_targets(self.summary)
        selected = _robotics_selected_index(self.summary)
        final_position = _robotics_final_position(self.summary)
        width = 62
        height = 12
        cells: dict[tuple[int, int], set[str]] = {}

        def place(x: float, y: float, marker: str) -> None:
            column = max(0, min(width - 1, round(x * (width - 1))))
            row = max(0, min(height - 1, round((1.0 - y) * (height - 1))))
            cells.setdefault((row, column), set()).add(marker)

        place(0.0, 0.5, "S")
        place(0.5, 0.5, "G")
        for target in targets:
            index = int(target.get("index", -1))
            x = _robotics_number(target.get("x"))
            y = _robotics_number(target.get("y"))
            if x is None or y is None:
                continue
            marker = "T" if index == selected else str(index % 10)
            place(x, y, marker)
        if final_position is not None:
            place(final_position["x"], final_position["y"], "F")

        lines = ["+" + "-" * width + "+"]
        for row in range(height):
            characters: list[str] = []
            for column in range(width):
                markers = cells.get((row, column), set())
                if not markers:
                    characters.append(" ")
                elif "F" in markers and "T" in markers:
                    characters.append("X")
                elif "F" in markers:
                    characters.append("F")
                elif "T" in markers:
                    characters.append("T")
                elif len(markers) > 1:
                    characters.append("*")
                else:
                    characters.append(next(iter(markers)))
            lines.append("|" + "".join(characters) + "|")
        lines.append("+" + "-" * width + "+")
        lines.append("x=0.00                         x=0.50                         x=1.00")
        return lines

    def on_mount(self) -> None:
        legend = Text("S start  G goal  T selected target  F final  X selected+final", style="dim")
        selected = _robotics_selected_index(self.summary)
        map_text = Text("\n".join(self._map_lines()), style=f"bold {_robotics_color('success')}")
        subtitle = Text(
            f"selected candidate: #{selected}", style=f"bold {_robotics_color('success')}"
        )
        self.update(
            Panel(
                Group(subtitle, legend, map_text),
                title="Tabletop Replay",
                border_style=_robotics_color("warning"),
            )
        )


class RoboticsArmPane(Static, _ThemedRenderer):
    """Illustrative animated robot-arm replay for the selected candidate."""

    _FRAMES: ClassVar[list[list[str]]] = [
        [
            "                                    target",
            "                                      T",
            "                                      |",
            "base [###]o====o----[]",
            "        shoulder elbow gripper",
            "        replay frame 1/4",
        ],
        [
            "                                    target",
            "                                      T",
            "                                     /",
            "base [###]o======o-----[]",
            "        shoulder  elbow gripper",
            "        replay frame 2/4",
        ],
        [
            "                                    target",
            "                                      T",
            "                                    /",
            "base [###]o========o------[]",
            "        shoulder   elbow gripper",
            "        replay frame 3/4",
        ],
        [
            "                                    target",
            "                                      T",
            "                                      |",
            "base [###]o==========o========[]",
            "        shoulder    elbow     gripper",
            "        replay frame 4/4",
        ],
    ]

    def __init__(self, summary: dict[str, object], *, animate: bool = True) -> None:
        super().__init__()
        self.summary = summary
        self.animate = animate
        self._frame_index = 0
        self._timer: Any | None = None
        self._target_line_cached = ""

    def on_mount(self) -> None:
        self._target_line_cached = self._target_line()
        self._render_frame()
        if self.animate:
            self._timer = self.set_interval(0.32, self._advance)

    def on_unmount(self) -> None:
        # Textual timers keep firing on dismounted widgets unless stopped,
        # so cancel the one `on_mount` started before this pane goes away.
        if self._timer is not None:
            self._timer.stop()
            self._timer = None

    def _advance(self) -> None:
        self._frame_index = (self._frame_index + 1) % len(self._FRAMES)
        self._render_frame()

    def _selected_target(self) -> dict[str, object] | None:
        selected = _robotics_selected_index(self.summary)
        for target in _robotics_candidate_targets(self.summary):
            if target.get("index") == selected:
                return target
        return None

    def _target_line(self) -> str:
        selected = _robotics_selected_index(self.summary)
        target = self._selected_target()
        if target is None:
            return f"selected candidate #{selected}"
        x = _robotics_number(target.get("x")) or 0.0
        y = _robotics_number(target.get("y")) or 0.0
        z = _robotics_number(target.get("z")) or 0.0
        return f"selected candidate #{selected}: target x={x:.3f} y={y:.3f} z={z:.3f}"

    def _render_frame(self) -> None:
        title = Text("Illustrative Arm Replay", style=f"bold {_robotics_color('accent')}")
        subtitle = Text("simulation/replay only; no hardware command is emitted", style="dim")
        target = Text(self._target_line_cached, style=f"bold {_robotics_color('success')}")
        frame = Text("\n".join(self._FRAMES[self._frame_index]), style=_robotics_color("accent"))
        final_position = _robotics_final_position(self.summary)
        final = "mock final unavailable"
        if final_position is not None:
            final = (
                "mock final "
                f"x={final_position['x']:.3f} "
                f"y={final_position['y']:.3f} "
                f"z={final_position['z']:.3f}"
            )
        details = Table.grid(expand=True)
        details.add_column(no_wrap=True)
        details.add_column()
        details.add_row(Text("action chunk", style="dim"), Text("1 selected WorldForge action"))
        details.add_row(Text("replay target", style="dim"), target)
        details.add_row(Text("result", style="dim"), Text(final, style="bold"))
        details.add_row(Text("boundary", style="dim"), Text("local mock execution only"))
        body = Table.grid(expand=True, padding=(0, 3))
        body.add_column(ratio=1)
        body.add_column(ratio=1)
        body.add_row(frame, details)
        self.update(
            Panel(
                Group(title, subtitle, Text(""), body),
                title="Robot Arm Visualization",
                border_style=_robotics_color("accent"),
            )
        )


class RoboticsEventPane(Static, _ThemedRenderer):
    """Provider events emitted by the completed real run."""

    def __init__(self, summary: dict[str, object]) -> None:
        super().__init__()
        self.summary = summary

    def on_mount(self) -> None:
        events = self.summary.get("provider_events")
        table = Table(
            expand=True, show_header=True, header_style=f"bold {_robotics_color('accent')}"
        )
        table.add_column("provider", no_wrap=True)
        table.add_column("operation", no_wrap=True)
        table.add_column("phase", no_wrap=True)
        table.add_column("duration", justify="right", no_wrap=True)
        if isinstance(events, list):
            for event in events:
                if not isinstance(event, dict):
                    continue
                duration = _robotics_number(event.get("duration_ms"))
                table.add_row(
                    str(event.get("provider")),
                    str(event.get("operation")),
                    str(event.get("phase")),
                    "n/a" if duration is None else f"{duration:.2f} ms",
                )
        self.update(Panel(table, title="Provider Event Log", border_style=_robotics_color("panel")))


class RoboticsTabletopHelpScreen(ModalScreen[None]):
    """Modal explainer for the standalone robotics tabletop replay."""

    BINDINGS: ClassVar[list[Binding]] = [
        Binding("escape", "dismiss", "Close", show=True),
        Binding("q", "dismiss", "Close", show=False),
    ]

    CSS = """
    RoboticsTabletopHelpScreen {
        align: center middle;
    }

    RoboticsTabletopHelpScreen > #robotics-help-card {
        width: 104;
        height: 38;
        background: $surface;
        border: tall $accent;
        padding: 1 2;
    }

    RoboticsTabletopHelpScreen #robotics-help-title {
        height: 1;
        text-style: bold;
        color: $accent;
        margin-bottom: 1;
    }

    RoboticsTabletopHelpScreen .robotics-help-section {
        margin-bottom: 1;
    }
    """

    def compose(self) -> ComposeResult:
        with VerticalScroll(id="robotics-help-card"):
            yield Static("Reading the tabletop replay", id="robotics-help-title")
            yield Static(ROBOTICS_TABLETOP_HELP_TEXT, classes="robotics-help-section")
            yield Static(
                Text(ROBOTICS_TABLETOP_DIAGRAM, style=f"bold {_robotics_color('success')}"),
                classes="robotics-help-section",
            )
            yield Static(
                "ELI5: the policy suggests a few pushes, the world model scores them, "
                "WorldForge chooses the cheapest one, and the mock world shows where that "
                "choice ended. If T and F overlap, the map prints X.",
                classes="robotics-help-section",
            )
            yield Static(
                "Boundary: this visualizes simulation/replay planning only. It is not a "
                "hardware command stream, safety check, or physical success proof.",
                classes="robotics-help-section",
            )


class RoboticsProgressPane(Static, _ThemedRenderer):
    """Staged reveal status for the standalone showcase report."""

    def on_mount(self) -> None:
        self.set_message("Preparing visual replay from completed real inference summary...")

    def set_message(self, message: str) -> None:
        self.update(
            Panel(
                Text(message, style=f"bold {_robotics_color('accent')}"),
                title="Replay Sequencer",
                border_style=_robotics_color("accent"),
            )
        )


class RoboticsShowcaseApp(App[None]):
    """Standalone Textual report for the real robotics showcase."""

    TITLE = "WorldForge Robotics Showcase"
    SUB_TITLE = "LeRobot policy + LeWorldModel checkpoint scoring replay"
    BINDINGS: ClassVar[list[Binding]] = [
        Binding("?", "show_tabletop_help", "Help", show=True),
        Binding("o", "open_rerun", "Open Rerun", show=True),
        Binding("q", "quit", "Quit", show=True),
        Binding("ctrl+t", "toggle_theme", "Theme", show=True),
    ]
    CSS = """
    Header {
        background: $surface;
        color: $foreground;
    }

    Footer {
        background: $surface;
        color: $foreground;
    }

    #robotics-body {
        height: 1fr;
        padding: 1 2;
        background: $surface;
    }

    RoboticsHeroPane {
        height: 10;
        margin-bottom: 1;
    }

    RoboticsProgressPane {
        height: 5;
        margin-bottom: 1;
    }

    RoboticsPipelinePane {
        height: 13;
        margin-bottom: 1;
    }

    RoboticsReportGuidePane {
        height: 11;
        margin-bottom: 1;
    }

    RoboticsRerunPane {
        height: 9;
        margin-bottom: 1;
    }

    RoboticsMetricsPane {
        height: 12;
        margin-bottom: 1;
    }

    RoboticsArmPane {
        height: 15;
        margin-bottom: 1;
    }

    RoboticsCandidatePane {
        height: 10;
        margin-bottom: 1;
    }

    RoboticsTabletopPane {
        height: 17;
        margin-bottom: 1;
    }

    RoboticsEventPane {
        height: 10;
        margin-bottom: 1;
    }
    """

    def __init__(
        self,
        *,
        summary: dict[str, object],
        summary_path: Path | None = None,
        stage_delay: float = 0.35,
        animate_arm: bool = True,
    ) -> None:
        super().__init__()
        self.summary = summary
        self.summary_path = summary_path
        self.stage_delay = max(0.0, stage_delay)
        self.animate_arm = animate_arm
        self.rerun_recording_path = _robotics_rerun_recording_path(summary)
        self.register_theme(_build_theme(THEME_NAME_DARK, WORLDFORGE_DARK_PALETTE, dark=True))
        self.register_theme(_build_theme(THEME_NAME_LIGHT, WORLDFORGE_LIGHT_PALETTE, dark=False))
        self.register_theme(
            _build_theme(
                THEME_NAME_HIGH_CONTRAST,
                WORLDFORGE_HIGH_CONTRAST_PALETTE,
                dark=True,
            )
        )
        self.theme = THEME_NAME_DARK

    def compose(self) -> ComposeResult:
        yield Header()
        with VerticalScroll(id="robotics-body"):
            if self.stage_delay <= 0:
                yield RoboticsHeroPane(self.summary, self.summary_path)
                yield RoboticsPipelinePane(self.summary)
                yield RoboticsReportGuidePane()
                if self.rerun_recording_path is not None:
                    yield RoboticsRerunPane(self.summary)
                yield RoboticsMetricsPane(self.summary)
                yield RoboticsArmPane(self.summary, animate=self.animate_arm)
                yield RoboticsCandidatePane(self.summary)
                yield RoboticsTabletopPane(self.summary)
                yield RoboticsEventPane(self.summary)
            else:
                yield RoboticsProgressPane()
        yield Footer()

    async def on_mount(self) -> None:
        if self.stage_delay > 0:
            self.run_worker(self._reveal_report(), name="robotics.reveal", group="robotics")

    async def _reveal_report(self) -> None:
        body = self.query_one("#robotics-body", VerticalScroll)
        progress = self.query_one(RoboticsProgressPane)
        stages: list[tuple[str, Static]] = [
            (
                "Loaded real policy + score summary.",
                RoboticsHeroPane(self.summary, self.summary_path),
            ),
            ("Tracing the policy-to-world-model pipeline.", RoboticsPipelinePane(self.summary)),
            (
                "Explaining how to read the runtime, tensor, and candidate panes.",
                RoboticsReportGuidePane(),
            ),
        ]
        if self.rerun_recording_path is not None:
            stages.append(
                (
                    "Attaching Rerun artifact location and viewer command.",
                    RoboticsRerunPane(self.summary),
                )
            )
        stages.extend(
            [
                (
                    "Rendering latency and tensor contract metrics.",
                    RoboticsMetricsPane(self.summary),
                ),
                (
                    "Animating the selected action chunk as an illustrative arm replay.",
                    RoboticsArmPane(self.summary, animate=self.animate_arm),
                ),
                (
                    "Ranking LeRobot action candidates by LeWorldModel cost.",
                    RoboticsCandidatePane(self.summary),
                ),
                (
                    "Drawing the tabletop replay with stable markers.",
                    RoboticsTabletopPane(self.summary),
                ),
                ("Attaching provider event log.", RoboticsEventPane(self.summary)),
            ]
        )
        await asyncio.sleep(self.stage_delay)
        for message, widget in stages:
            progress.set_message(message)
            await body.mount(widget)
            await asyncio.sleep(self.stage_delay)
        await progress.remove()

    def action_toggle_theme(self) -> None:
        order = (THEME_NAME_DARK, THEME_NAME_LIGHT, THEME_NAME_HIGH_CONTRAST)
        try:
            index = order.index(self.theme)
        except ValueError:
            index = 0
        self.theme = order[(index + 1) % len(order)]

    def action_show_tabletop_help(self) -> None:
        self.push_screen(RoboticsTabletopHelpScreen())

    def action_open_rerun(self) -> None:
        path = self.rerun_recording_path
        if path is None:
            self.notify(
                "This run does not include a persisted Rerun recording.",
                severity="warning",
                title="Rerun",
            )
            return
        if not path.is_file():
            self.notify(
                f"Rerun recording not found: {path}",
                severity="error",
                title="Rerun",
            )
            return
        command = _robotics_rerun_viewer_command(path)
        try:
            subprocess.Popen(
                command,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
        except OSError as exc:
            self.notify(str(exc), severity="error", title="Rerun")
            return
        self.notify(
            _robotics_rerun_viewer_command_text(path),
            severity="information",
            title="Opening Rerun",
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
        items: list[tuple[str, str, Any]] = [
            (
                f"World: {world_id}",
                "Open the Worlds screen",
                lambda world_id=world_id: app._open_world_from_palette(world_id),  # type: ignore[attr-defined]
            )
            for world_id in forge.list_worlds()
        ]
        items.extend(
            (
                f"Provider: {provider}",
                "Open the Providers screen",
                lambda provider=provider: app._open_provider_from_palette(provider),  # type: ignore[attr-defined]
            )
            for provider in forge.providers()
        )
        items.extend(
            (
                f"Run: {path.name}",
                "Open the preserved report",
                lambda path=path: app._open_report_path(path),  # type: ignore[attr-defined]
            )
            for path in recent_report_paths(forge.state_dir, limit=50)
        )
        return items


class TheWorldHarnessApp(App[None]):
    """Visual TUI harness for WorldForge E2E demos."""

    TITLE = "TheWorldHarness"
    SUB_TITLE = "WorldForge visual integration harness"
    COMMANDS = App.COMMANDS | {WorldForgeCommandProvider}
    BINDINGS: ClassVar[list[Binding]] = [
        Binding("?", "show_help", "Help", show=True),
        Binding("q", "quit", "Quit", show=True),
        Binding("ctrl+t", "toggle_theme", "Theme", show=False),
        Binding("g,h", "switch_screen('home')", "Jump: Home", show=False),
        Binding("g,r", "switch_screen('run-inspector')", "Jump: Run Inspector", show=False),
        Binding("g,w", "switch_screen('worlds')", "Jump: Worlds", show=False),
        Binding("g,p", "switch_screen('providers')", "Jump: Providers", show=False),
        Binding("g,e", "switch_screen('eval')", "Jump: Eval", show=False),
        Binding("g,b", "switch_screen('benchmark')", "Jump: Benchmark", show=False),
    ]
    SCREENS: ClassVar[dict[str, type[Screen[Any]]]] = {
        "home": HomeScreen,
        "run-inspector": RunInspectorScreen,
        "worlds": WorldsScreen,
        "providers": ProvidersScreen,
        "eval": EvalScreen,
        "benchmark": BenchmarkScreen,
    }
    CSS = """
    Header {
        background: $surface;
        color: $foreground;
    }

    Footer {
        background: $surface;
        color: $foreground;
    }

    #chrome {
        height: 1;
        background: $boost;
    }

    #breadcrumb {
        width: 1fr;
    }

    #provider-pill {
        width: auto;
    }
    """

    current_provider: reactive[str] = reactive("mock", init=False)

    def __init__(
        self,
        *,
        initial_flow_id: str = "leworldmodel",
        initial_screen: InitialScreen = "home",
        state_dir: Path | None = None,
        step_delay: float = 0.18,
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
        self.register_theme(_build_theme(THEME_NAME_DARK, WORLDFORGE_DARK_PALETTE, dark=True))
        self.register_theme(_build_theme(THEME_NAME_LIGHT, WORLDFORGE_LIGHT_PALETTE, dark=False))
        self.register_theme(
            _build_theme(
                THEME_NAME_HIGH_CONTRAST,
                WORLDFORGE_HIGH_CONTRAST_PALETTE,
                dark=True,
            )
        )
        self.theme = THEME_NAME_DARK
        # Replace the stock default screen with the harness landing screen
        # (Home unless the CLI passed --flow or --initial-screen). Awaiting
        # the push keeps the active screen consistent before any test/Pilot
        # interaction runs.
        if self._initial_screen == "run-inspector":
            await self.push_screen(self._make_run_inspector())
        elif self._initial_screen == "worlds":
            await self.push_screen(self._make_worlds())
        elif self._initial_screen == "providers":
            await self.push_screen(self._make_providers())
        elif self._initial_screen == "eval":
            await self.push_screen(self._make_eval())
        elif self._initial_screen == "benchmark":
            await self.push_screen(self._make_benchmark())
        else:
            await self.push_screen(self._make_home())

    def action_show_help(self) -> None:
        self.push_screen(HelpScreen(source_screen=self.screen))

    def action_toggle_theme(self) -> None:
        """Cycle between the registered worldforge themes."""
        order = (THEME_NAME_DARK, THEME_NAME_LIGHT, THEME_NAME_HIGH_CONTRAST)
        try:
            index = order.index(self.theme)
        except ValueError:
            index = 0
        self.theme = order[(index + 1) % len(order)]

    def action_switch_screen(self, screen_name: str) -> None:
        """Switch to ``screen_name`` if not already the active screen.

        Replaces (rather than stacks on top of) the active non-modal screen
        so chord navigation does not grow the stack indefinitely. Modal
        overlays are popped first so the user does not get stuck behind
        them.
        """
        while isinstance(self.screen, ModalScreen):
            self.pop_screen()
        target_cls = self.SCREENS.get(screen_name)
        if target_cls is None or isinstance(self.screen, target_cls):
            if (
                screen_name == "run-inspector"
                and isinstance(self.screen, RunInspectorScreen)
                and not self.screen.can_run_flows
            ):
                self.switch_screen(self._make_run_inspector())
            return
        if screen_name == "run-inspector":
            self.switch_screen(self._make_run_inspector())
        elif screen_name == "home":
            self.switch_screen(self._make_home())
        elif screen_name == "worlds":
            self.switch_screen(self._make_worlds())
        elif screen_name == "providers":
            self.switch_screen(self._make_providers())
        elif screen_name == "eval":
            self.switch_screen(self._make_eval())
        elif screen_name == "benchmark":
            self.switch_screen(self._make_benchmark())
        else:  # pragma: no cover - defensive
            self.switch_screen(screen_name)

    def _make_screen_for_name(  # pragma: no cover - exercised through Textual callbacks.
        self, screen_name: str
    ) -> Screen | str:
        if screen_name == "run-inspector":
            return self._make_run_inspector()
        if screen_name == "home":
            return self._make_home()
        if screen_name == "worlds":
            return self._make_worlds()
        if screen_name == "providers":
            return self._make_providers()
        if screen_name == "eval":
            return self._make_eval()
        if screen_name == "benchmark":
            return self._make_benchmark()
        return screen_name

    async def _switch_screen_and_wait(  # pragma: no cover - exercised through command callbacks.
        self, screen_name: str
    ) -> Screen:
        while isinstance(self.screen, ModalScreen):
            await self.pop_screen()
        target_cls = self.SCREENS.get(screen_name)
        if target_cls is not None and isinstance(self.screen, target_cls):
            if (
                screen_name == "run-inspector"
                and isinstance(self.screen, RunInspectorScreen)
                and not self.screen.can_run_flows
            ):
                await self.switch_screen(self._make_run_inspector())
            return self.screen
        await self.switch_screen(self._make_screen_for_name(screen_name))
        return self.screen

    def get_system_commands(self, screen: Screen) -> Iterable[SystemCommand]:
        # Yield the stock Textual commands first (theme, quit) so they stay
        # discoverable, then layer the harness-specific entries.
        yield from super().get_system_commands(screen)
        yield SystemCommand(
            "Jump: Home",
            "Open the Home screen",
            lambda: self.action_switch_screen("home"),
        )
        yield SystemCommand(
            "Jump: Run Inspector",
            "Open the Run Inspector screen",
            lambda: self.action_switch_screen("run-inspector"),
        )
        yield SystemCommand(
            "Jump: Worlds",
            "Open the Worlds screen",
            lambda: self.action_switch_screen("worlds"),
        )
        yield SystemCommand(
            "Jump: Providers",
            "Open the Providers screen",
            lambda: self.action_switch_screen("providers"),
        )
        yield SystemCommand(
            "Run eval suite",
            "Open the Eval screen",
            lambda: self.action_switch_screen("eval"),
        )
        yield SystemCommand(
            "Run benchmark",
            "Open the Benchmark screen",
            lambda: self.action_switch_screen("benchmark"),
        )
        yield SystemCommand(
            "New world",
            "Open the Worlds screen and start a new world",
            self._command_new_world,
        )
        yield SystemCommand(
            "Open Help",
            "Show the bindings on the active screen",
            self.action_show_help,
        )
        for flow in available_flows():
            yield SystemCommand(
                f"Run flow: {flow.title}",
                f"Switch the Run Inspector to {flow.short_title} and run it",
                self._make_run_flow_command(flow.id),
            )
        yield SystemCommand(
            "Switch theme",
            "Cycle worldforge-dark, worldforge-light, and worldforge-high-contrast",
            self.action_toggle_theme,
        )

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

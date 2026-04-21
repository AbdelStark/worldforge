"""Textual TUI for TheWorldHarness."""

from __future__ import annotations

import asyncio
from collections.abc import Iterable
from pathlib import Path
from typing import Literal

from rich.align import Align
from rich.console import Group, RenderableType
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from textual import events, on
from textual.app import App, ComposeResult, SystemCommand
from textual.binding import Binding
from textual.containers import Container, Horizontal, Vertical
from textual.css.query import NoMatches
from textual.message import Message
from textual.reactive import reactive
from textual.screen import ModalScreen, Screen
from textual.theme import Theme
from textual.widgets import Button, DataTable, Footer, Header, Select, Static

from worldforge.harness.flows import available_flows, run_flow
from worldforge.harness.models import HarnessFlow, HarnessRun, HarnessStep
from worldforge.harness.theme import (
    FLOW_CAPABILITY_FALLBACKS,
    THEME_NAME_DARK,
    THEME_NAME_LIGHT,
    WORLDFORGE_DARK_PALETTE,
    WORLDFORGE_LIGHT_PALETTE,
)

InitialScreen = Literal["home", "run-inspector"]


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
    """Header breadcrumb showing ``worldforge › <screen> [› <flow>]``.

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
        separator = Text(" › ", style="dim")
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

    BINDINGS = [
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

    BINDINGS = [
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
        first_card = _maybe_query(self, "#jump-create-world", JumpCard)
        if first_card is not None:
            first_card.focus()

    def on_screen_resume(self) -> None:
        self._update_chrome()

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
        routing = {
            "worlds": ("M2", "Worlds CRUD lands in M2 — see roadmap §8."),
            "providers": ("M3", "Live provider streaming lands in M3 — see roadmap §8."),
            "eval": ("M4", "Eval and benchmark land in M4 — see roadmap §8."),
        }
        milestone, message = routing.get(event.target, ("?", "Target not yet routed."))
        self.app.push_screen(PlaceholderScreen(target_milestone=milestone, next_action=message))


class RunInspectorScreen(Screen):
    """Hosts the existing flow visualisation (hero, rail, timeline, inspector, transcript)."""

    BINDINGS = [
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
    ) -> None:
        super().__init__()
        self.flows = {flow.id: flow for flow in available_flows()}
        resolved_id = initial_flow_id if initial_flow_id in self.flows else "leworldmodel"
        self.set_reactive(RunInspectorScreen.selected_flow_id, resolved_id)
        self.set_reactive(
            RunInspectorScreen.current_provider,
            self._provider_label(self.flows[resolved_id]),
        )
        self.state_dir = state_dir
        self.step_delay = step_delay

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Horizontal(id="chrome"):
            yield Breadcrumb(id="breadcrumb")
            yield ProviderStatusPill(id="provider-pill")
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

    BINDINGS = [
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

    BINDINGS = [
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
# App
# ---------------------------------------------------------------------------


class TheWorldHarnessApp(App[None]):
    """Visual TUI harness for WorldForge E2E demos."""

    TITLE = "TheWorldHarness"
    SUB_TITLE = "WorldForge visual integration harness"
    BINDINGS = [
        Binding("?", "show_help", "Help", show=True),
        Binding("q", "quit", "Quit", show=True),
        Binding("ctrl+t", "toggle_theme", "Theme", show=False),
        Binding("g,h", "switch_screen('home')", "Jump: Home", show=False),
        Binding("g,r", "switch_screen('run-inspector')", "Jump: Run Inspector", show=False),
    ]
    SCREENS = {"home": HomeScreen, "run-inspector": RunInspectorScreen}
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

    async def on_mount(self) -> None:
        self.register_theme(_build_theme(THEME_NAME_DARK, WORLDFORGE_DARK_PALETTE, dark=True))
        self.register_theme(_build_theme(THEME_NAME_LIGHT, WORLDFORGE_LIGHT_PALETTE, dark=False))
        self.theme = THEME_NAME_DARK
        # Replace the stock default screen with the harness landing screen
        # (Home unless the CLI passed --flow). Awaiting the push keeps the
        # active screen consistent before any test/Pilot interaction runs.
        if self._initial_screen == "run-inspector":
            await self.push_screen(self._make_run_inspector())
        else:
            await self.push_screen(self._make_home())

    def action_show_help(self) -> None:
        self.push_screen(HelpScreen(source_screen=self.screen))

    def action_toggle_theme(self) -> None:
        """Cycle between the two registered worldforge themes."""
        self.theme = THEME_NAME_LIGHT if self.theme == THEME_NAME_DARK else THEME_NAME_DARK

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
            return
        if screen_name == "run-inspector":
            self.switch_screen(self._make_run_inspector())
        elif screen_name == "home":
            self.switch_screen(self._make_home())
        else:  # pragma: no cover - defensive
            self.switch_screen(screen_name)

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
            "Toggle between worldforge-dark and worldforge-light",
            self.action_toggle_theme,
        )

    def _make_run_flow_command(self, flow_id: str):
        async def _run() -> None:
            self.action_switch_screen("run-inspector")
            screen = self.screen
            if isinstance(screen, RunInspectorScreen):
                screen.action_select_flow(flow_id)
                await screen.action_run_selected()

        return _run

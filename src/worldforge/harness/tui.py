"""Textual TUI for TheWorldHarness."""

from __future__ import annotations

import asyncio
from collections.abc import Iterable
from contextlib import suppress
from pathlib import Path
from typing import Literal

from rich.align import Align
from rich.console import Group, RenderableType
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from textual import events, on, work
from textual.app import App, ComposeResult, SystemCommand
from textual.binding import Binding
from textual.containers import Container, Horizontal, Vertical
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
    Select,
    Static,
)
from textual.widgets.option_list import Option

from worldforge import (
    Action,
    BBox,
    Position,
    SceneObject,
    World,
    WorldForge,
    WorldForgeError,
    WorldStateError,
)
from worldforge.framework import _validate_storage_id
from worldforge.harness.flows import available_flows, run_flow
from worldforge.harness.models import HarnessFlow, HarnessRun, HarnessStep
from worldforge.harness.theme import (
    FLOW_CAPABILITY_FALLBACKS,
    THEME_NAME_DARK,
    THEME_NAME_LIGHT,
    WORLDFORGE_DARK_PALETTE,
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

InitialScreen = Literal["home", "run-inspector", "worlds"]


def _delete_world_file(state_dir: Path, world_id: str) -> None:
    """Remove a persisted world file after re-validating its storage id.

    Fallback for the gated public ``WorldForge.delete_world`` method that M2 did
    *not* introduce (see ``specs/theworldharness-M2-worlds-crud/`` T2). The id is
    re-validated through the public ``_validate_storage_id`` helper so any path
    traversal, separator, or empty value raises ``WorldForgeError`` before
    ``Path.unlink`` is called. A missing file raises ``WorldStateError`` so the
    UI can surface it as a toast (identical to the shape the future public API
    would use).
    """

    safe_id = _validate_storage_id(world_id, name="world_id")
    path = state_dir / f"{safe_id}.json"
    try:
        path.unlink(missing_ok=False)
    except FileNotFoundError as exc:
        raise WorldStateError(f"World '{safe_id}' is not present at {path}.") from exc
    except OSError as exc:
        raise WorldStateError(f"Failed to delete world '{safe_id}' at {path}: {exc}") from exc


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
        if event.target == "worlds":
            self.app.action_switch_screen("worlds")
            return
        routing = {
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
# M2 — Worlds CRUD: messages
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
# M2 — Worlds CRUD: modals
# ---------------------------------------------------------------------------


class ConfirmDeleteScreen(ModalScreen[bool]):
    """Yes/no overlay for destructive actions. Returns ``True`` only on confirm."""

    BINDINGS = [
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

    BINDINGS = [
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
        error = _maybe_query(self, "#new-world-error", Static)
        if error is None:
            return
        if message:
            error.update(message)
            error.remove_class("hidden")
        else:
            error.update("")
            error.add_class("hidden")

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

    BINDINGS = [
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
        error = _maybe_query(self, "#edit-object-error", Static)
        if error is None:
            return
        if message:
            error.update(message)
            error.remove_class("hidden")
        else:
            error.update("")
            error.add_class("hidden")

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
# M2 — Worlds CRUD: screens
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

    BINDINGS = [
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
            _delete_world_file(self._forge.state_dir, world_id)
        except (WorldForgeError, WorldStateError) as exc:
            self.app.call_from_thread(self._notify_error, f"Delete failed: {exc}")
            return
        self.app.call_from_thread(self.post_message, WorldDeleted(world_id))

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

    BINDINGS = [
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
        Binding("g,w", "switch_screen('worlds')", "Jump: Worlds", show=False),
    ]
    SCREENS = {
        "home": HomeScreen,
        "run-inspector": RunInspectorScreen,
        "worlds": WorldsScreen,
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
            self._forge = WorldForge(state_dir=self._state_dir)
        return self._forge

    def _make_worlds(self) -> WorldsScreen:
        return WorldsScreen(forge=self._get_forge())

    async def on_mount(self) -> None:
        self.register_theme(_build_theme(THEME_NAME_DARK, WORLDFORGE_DARK_PALETTE, dark=True))
        self.register_theme(_build_theme(THEME_NAME_LIGHT, WORLDFORGE_LIGHT_PALETTE, dark=False))
        self.theme = THEME_NAME_DARK
        # Replace the stock default screen with the harness landing screen
        # (Home unless the CLI passed --flow or --initial-screen). Awaiting
        # the push keeps the active screen consistent before any test/Pilot
        # interaction runs.
        if self._initial_screen == "run-inspector":
            await self.push_screen(self._make_run_inspector())
        elif self._initial_screen == "worlds":
            await self.push_screen(self._make_worlds())
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
        elif screen_name == "worlds":
            self.switch_screen(self._make_worlds())
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
            "Jump: Worlds",
            "Open the Worlds screen",
            lambda: self.action_switch_screen("worlds"),
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

    def _command_new_world(self) -> None:
        self.action_switch_screen("worlds")
        screen = self.screen
        if isinstance(screen, WorldsScreen):
            screen.action_new_world()

"""Textual TUI for TheWorldHarness."""

from __future__ import annotations

import asyncio
from pathlib import Path

from rich.align import Align
from rich.console import Group, RenderableType
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from textual import on
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal, Vertical
from textual.css.query import NoMatches
from textual.reactive import reactive
from textual.theme import Theme
from textual.widgets import Button, Footer, Header, Select, Static

from worldforge.harness.flows import available_flows, run_flow
from worldforge.harness.models import HarnessFlow, HarnessRun, HarnessStep
from worldforge.harness.theme import (
    FLOW_CAPABILITY_FALLBACKS,
    THEME_NAME_DARK,
    THEME_NAME_LIGHT,
    WORLDFORGE_DARK_PALETTE,
    WORLDFORGE_LIGHT_PALETTE,
)


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


class Breadcrumb(Static):
    """Header breadcrumb showing ``worldforge › <flow short_title>``.

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


class TheWorldHarnessApp(App[None]):
    """Visual TUI harness for WorldForge E2E demos."""

    TITLE = "TheWorldHarness"
    SUB_TITLE = "WorldForge visual integration harness"
    BINDINGS = [
        ("r", "run_selected", "Run"),
        ("1", "select_flow('leworldmodel')", "LeWorldModel"),
        ("2", "select_flow('lerobot')", "LeRobot"),
        ("3", "select_flow('diagnostics')", "Diagnostics"),
        ("q", "quit", "Quit"),
        Binding("ctrl+t", "toggle_theme", "Theme", show=False),
    ]
    CSS = """
    Screen {
        background: $background;
        color: $foreground;
    }

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
        self.set_reactive(TheWorldHarnessApp.selected_flow_id, resolved_id)
        self.set_reactive(
            TheWorldHarnessApp.current_provider,
            self._provider_label(self.flows[resolved_id]),
        )
        self.state_dir = state_dir
        self.step_delay = step_delay
        self.running = False
        self.last_run: HarnessRun | None = None

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
        self.register_theme(_build_theme(THEME_NAME_DARK, WORLDFORGE_DARK_PALETTE, dark=True))
        self.register_theme(_build_theme(THEME_NAME_LIGHT, WORLDFORGE_LIGHT_PALETTE, dark=False))
        self.theme = THEME_NAME_DARK
        self._sync_chrome()
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
            select = self.query_one("#flow-select", Select)
            if select.value != flow_id:
                select.value = flow_id

    def action_toggle_theme(self) -> None:
        """Cycle between the two registered worldforge themes."""
        self.theme = THEME_NAME_LIGHT if self.theme == THEME_NAME_DARK else THEME_NAME_DARK

    def watch_selected_flow_id(self, _old: str, new: str) -> None:
        if new not in self.flows:
            return
        self.current_provider = self._provider_label(self.flows[new])
        self._sync_chrome()
        self._refresh_static()

    def watch_current_provider(self, _old: str, new: str) -> None:
        pill = self._maybe_query("#provider-pill", ProviderStatusPill)
        if pill is not None:
            pill.label = new

    def _maybe_query(self, selector: str, expected_type):
        """Return a widget if it has been composed, else ``None``.

        Reactives can fire before all widgets in ``compose()`` are mounted
        (e.g. when the App is being torn down between Pilot tests). We treat
        a missing target as a no-op rather than crashing.
        """
        try:
            return self.query_one(selector, expected_type)
        except NoMatches:
            return None

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

    def _sync_chrome(self) -> None:
        flow = self.flows[self.selected_flow_id]
        breadcrumb = self._maybe_query("#breadcrumb", Breadcrumb)
        if breadcrumb is not None:
            breadcrumb.path = ("worldforge", flow.short_title)
        # Pill mirrors current_provider via watch_current_provider; setting it
        # here as well keeps on_mount idempotent in case the watcher fires
        # before the widget exists.
        pill = self._maybe_query("#provider-pill", ProviderStatusPill)
        if pill is not None:
            pill.label = self.current_provider

    def _provider_label(self, flow: HarnessFlow) -> str:
        capability = flow.capability or FLOW_CAPABILITY_FALLBACKS.get(flow.id, "")
        suffix = f" · {capability}" if capability else ""
        return f"{flow.provider}{suffix}"

    def _refresh_static(self) -> None:
        selected = self.flows[self.selected_flow_id]
        hero = self._maybe_query("#hero", HeroPane)
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

"""Textual report UI for the robotics showcase."""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any, ClassVar

from rich.console import RenderableType
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import VerticalScroll
from textual.screen import ModalScreen
from textual.theme import Theme
from textual.widgets import Footer, Header, Static

from worldforge.harness import robotics_launch as _robotics_launch
from worldforge.harness import robotics_view as _robotics_view
from worldforge.harness import tui_styles as _tui_styles
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
from worldforge.harness.theme import (
    THEME_NAME_DARK,
    THEME_SPECS,
    next_theme_name,
)


def _build_theme(name: str, palette: Mapping[str, str], *, dark: bool) -> Theme:
    """Construct a Textual ``Theme`` from the shared harness palette."""

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


class _ThemedRenderer:
    """Marker mixin retained for robotics pane compatibility."""


# Compatibility names kept on ``worldforge.harness.tui`` for robotics tests and
# callers; implementation lives in the Textual-free robotics view modules.
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
    """Visual pipeline graph for the real policy-plus-score run."""

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
        self.notify(command_text, severity="information", title="Opening Rerun")

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
        self.notify(f"Opening {url}", severity="information", title="TensorBoard")

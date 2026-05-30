"""Rich renderable builders for TheWorldHarness TUI widgets.

The functions here deliberately avoid Textual imports. ``harness.tui`` owns widgets, actions,
workers, and event handling; this module owns pure renderable construction.
"""

from __future__ import annotations

from dataclasses import dataclass

from rich.align import Align
from rich.console import Group, RenderableType
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from worldforge.harness.models import HarnessFlow, HarnessRun, HarnessStep

EXPORT_PREVIEW_MAX_CHARS = 5000
EXPORT_PREVIEW_TRUNCATED_MESSAGE = "... truncated preview ..."


@dataclass(frozen=True, slots=True)
class TuiRenderColors:
    foreground: str
    accent: str
    success: str
    warning: str
    error: str
    muted: str
    panel: str


def hero_panel(
    flow: HarnessFlow | None,
    *,
    running: bool,
    colors: TuiRenderColors,
) -> RenderableType:
    title = Text("TheWorldHarness", style="bold")
    title.append("  /  visual WorldForge integration reference", style="dim")
    command = flow.command if flow else "select a flow"
    status = "RUNNING" if running else "READY"
    status_color = colors.accent if running else colors.success
    return Panel(
        Group(
            title,
            Text(""),
            Text(
                flow.summary if flow else "Run an E2E flow and inspect every boundary.",
                style="dim",
            ),
            Text(""),
            Text(f"Command: {command}", style=f"bold {colors.accent}"),
            Text(f"Status: {status}", style=f"black on {status_color}"),
        ),
        title="WORLD FORGE / HARNESS",
        border_style=status_color,
    )


def flow_card_panel(
    flow: HarnessFlow,
    *,
    selected: bool,
    colors: TuiRenderColors,
) -> RenderableType:
    marker = ">>" if selected else "  "
    style = f"bold {colors.accent}" if selected else colors.foreground
    return Panel(
        Group(
            Text(f"{marker} {flow.short_title}", style=style),
            Text(flow.focus, style="dim"),
            Text(flow.provider, style=colors.success),
        ),
        border_style=colors.accent if selected else colors.panel,
    )


def timeline_panel(
    flow: HarnessFlow,
    steps: tuple[HarnessStep, ...],
    *,
    active_index: int,
    complete_count: int,
    colors: TuiRenderColors,
) -> RenderableType:
    rows: list[RenderableType] = []
    for index, step in enumerate(steps):
        symbol, color = _timeline_marker(
            index,
            active_index=active_index,
            complete_count=complete_count,
            colors=colors,
        )
        rows.append(Text(f"{symbol} {index + 1:02d}. {step.title}", style=f"bold {color}"))
        rows.append(Text(f"    {step.detail}", style="dim"))
        if index < complete_count:
            rows.append(Text(f"    {step.result}", style=colors.foreground))
            if step.artifact:
                rows.append(Text(f"    {step.artifact}", style=colors.success))
        rows.append(Text(""))
    return Panel(
        Group(*rows),
        title=f"{flow.title} / execution trace",
        border_style=colors.accent,
    )


def _timeline_marker(
    index: int,
    *,
    active_index: int,
    complete_count: int,
    colors: TuiRenderColors,
) -> tuple[str, str]:
    if index < complete_count:
        return "OK", colors.success
    if index == active_index:
        return ">>", colors.accent
    return "--", colors.muted


def empty_inspector_panel(colors: TuiRenderColors) -> RenderableType:
    return Panel(
        Align.center(
            Text("Run a flow to populate metrics, state, and provider events.", style="dim"),
            vertical="middle",
        ),
        title="Inspector",
        border_style=colors.panel,
    )


def run_inspector_panel(run: HarnessRun, *, colors: TuiRenderColors) -> RenderableType:
    table = Table.grid(expand=True)
    table.add_column(justify="left", ratio=1)
    table.add_column(justify="right", ratio=1)
    for metric in run.metrics:
        table.add_row(
            Text(metric.label, style="dim"),
            Text(metric.value, style=f"bold {colors.accent}"),
        )
        if metric.detail:
            table.add_row("", Text(metric.detail, style=colors.success))
    _add_provider_events(table, run, colors=colors)
    _add_validation_errors(table, run, colors=colors)
    return Panel(table, title="Inspector", border_style=colors.accent)


def _add_provider_events(
    table: Table,
    run: HarnessRun,
    *,
    colors: TuiRenderColors,
) -> None:
    if not run.provider_events:
        return
    table.add_row(Text(""), Text(""))
    table.add_row(Text("Provider events", style="dim"), Text(str(len(run.provider_events))))
    for provider_event in run.provider_events[:6]:
        phase = str(provider_event.get("phase", "event"))
        phase_style = {
            "success": colors.success,
            "retry": colors.warning,
            "failure": colors.error,
            "cancelled": colors.warning,
            "budget_exceeded": colors.error,
        }.get(phase, colors.accent)
        provider = str(provider_event.get("provider", "provider"))
        operation = str(provider_event.get("operation", "operation"))
        suffix = _provider_event_suffix(provider_event)
        table.add_row(
            Text(phase, style=f"bold {phase_style}"),
            Text(f"{provider}.{operation} {' '.join(suffix)}".strip()),
        )


def _provider_event_suffix(provider_event: dict[str, object]) -> list[str]:
    suffix: list[str] = []
    attempt = provider_event.get("attempt")
    duration = provider_event.get("duration_ms")
    if attempt is not None:
        suffix.append(f"attempt={attempt}")
    if duration is not None:
        suffix.append(f"{float(duration):.1f} ms")
    return suffix


def _add_validation_errors(
    table: Table,
    run: HarnessRun,
    *,
    colors: TuiRenderColors,
) -> None:
    if not run.validation_errors:
        return
    table.add_row(Text(""), Text(""))
    table.add_row(Text("Validation errors", style=f"bold {colors.error}"), Text(""))
    for validation_error in run.validation_errors[:3]:
        table.add_row("", Text(validation_error, style=colors.error))


def empty_transcript_panel() -> RenderableType:
    return Panel(Text("Awaiting run output.", style="dim"), title="Run Transcript")


def run_transcript_panel(run: HarnessRun, *, colors: TuiRenderColors) -> RenderableType:
    lines = [Text(line, style=colors.foreground) for line in run.transcript]
    return Panel(Group(*lines), title="Run Transcript", border_style=colors.accent)


def export_preview_panel(
    artifacts: dict[str, str],
    *,
    report_format: str,
    colors: TuiRenderColors,
) -> RenderableType:
    if not artifacts:
        return Panel(
            Align.center(Text("No report captured yet.", style="dim"), vertical="middle"),
            title="Export Preview",
            border_style=colors.panel,
        )
    text = artifacts.get(report_format) or artifacts.get("markdown", "")
    if len(text) > EXPORT_PREVIEW_MAX_CHARS:
        text = f"{text[:EXPORT_PREVIEW_MAX_CHARS]}\n{EXPORT_PREVIEW_TRUNCATED_MESSAGE}"
    return Panel(
        Text(text),
        title=f"Export Preview / {report_format}",
        border_style=colors.accent,
    )

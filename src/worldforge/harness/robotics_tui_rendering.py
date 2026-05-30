"""Rich renderable builders for the robotics showcase TUI.

This module is intentionally Textual-free. ``harness.tui`` owns widget lifecycle,
animation timers, key bindings, and subprocess handling; these helpers own pure
renderable construction for completed robotics run summaries.
"""

from __future__ import annotations

from pathlib import Path

from rich import box
from rich.console import Group, RenderableType
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from worldforge.harness import robotics_view as _robotics_view

ROBOTICS_ARM_FRAMES: tuple[tuple[str, ...], ...] = (
    (
        "                                    target",
        "                                      T",
        "                                      |",
        "base [###]o====o----[]",
        "        shoulder elbow gripper",
        "        replay frame 1/4",
    ),
    (
        "                                    target",
        "                                      T",
        "                                     /",
        "base [###]o======o-----[]",
        "        shoulder  elbow gripper",
        "        replay frame 2/4",
    ),
    (
        "                                    target",
        "                                      T",
        "                                    /",
        "base [###]o========o------[]",
        "        shoulder   elbow gripper",
        "        replay frame 3/4",
    ),
    (
        "                                    target",
        "                                      T",
        "                                      |",
        "base [###]o==========o========[]",
        "        shoulder    elbow     gripper",
        "        replay frame 4/4",
    ),
)


def robotics_hero_panel(
    summary: dict[str, object],
    *,
    summary_path: Path | None,
) -> RenderableType:
    policy_path = _robotics_view.robotics_nested(summary, "inputs", "policy_path") or "unknown"
    checkpoint = summary.get("checkpoint_display") or summary.get("checkpoint")
    selected = _robotics_view.robotics_selected_index(summary)
    best_score = _robotics_view.robotics_nested(summary, "score_result", "best_score")
    score_text = (
        f"{float(best_score):.6f}"
        if _robotics_view.robotics_number(best_score) is not None
        else "n/a"
    )
    artifact = str(summary_path or summary.get("checkpoint_display") or "summary")
    title = Text(
        "WorldForge Robotics Showcase",
        style=f"bold {_robotics_view.robotics_color('accent')}",
    )
    subtitle = Text("real LeRobot policy + real LeWorldModel checkpoint scoring", style="dim")
    contract = Text()
    contract.append("REAL policy", style=f"bold {_robotics_view.robotics_color('success')}")
    contract.append("  +  ")
    contract.append("REAL score", style=f"bold {_robotics_view.robotics_color('success')}")
    contract.append("  +  ")
    contract.append("LOCAL mock replay", style=f"bold {_robotics_view.robotics_color('warning')}")
    body = Table.grid(expand=True)
    body.add_column(ratio=1)
    body.add_column(justify="right", ratio=1)
    body.add_row(Text("policy", style="dim"), Text(str(policy_path), style="bold"))
    body.add_row(Text("checkpoint", style="dim"), Text(str(checkpoint), style="bold"))
    body.add_row(
        Text("selected candidate", style="dim"),
        Text(
            f"#{selected} / score {score_text}",
            style=f"bold {_robotics_view.robotics_color('success')}",
        ),
    )
    body.add_row(
        Text("artifact", style="dim"),
        Text(artifact, style=_robotics_view.robotics_color("muted")),
    )
    return Panel(
        Group(title, subtitle, Text(""), contract, Text(""), body),
        title="REAL ROBOTICS POLICY + WORLD MODEL",
        border_style=_robotics_view.robotics_color("accent"),
    )


def robotics_pipeline_panel() -> RenderableType:
    accent = _robotics_view.robotics_color("accent")
    success = _robotics_view.robotics_color("success")
    warning = _robotics_view.robotics_color("warning")
    rows = (
        ("1", "PushT observation", "packaged host-preprocessed task state", success),
        ("2", "LeRobot policy", "select_action from lerobot/diffusion_pusht", accent),
        ("3", "Candidate bridge", "3 checkpoint-native action tensors", accent),
        ("4", "LeWorldModel cost", "lower cost wins", success),
        ("5", "WorldForge planner", "policy+score candidate selection", accent),
        ("6", "Mock replay", "local execution only, no hardware control", warning),
    )
    table = Table.grid(expand=True, padding=(0, 2))
    table.add_column(justify="right", no_wrap=True)
    table.add_column(no_wrap=True)
    table.add_column(ratio=2)
    for index, label, detail, color in rows:
        table.add_row(Text(f"{index}.", style=f"bold {color}"), Text(label, style="bold"), detail)
        if index != rows[-1][0]:
            table.add_row("", Text("|", style=color), Text("v", style=color))
    return Panel(table, title="Pipeline Flow", border_style=accent)


def robotics_report_guide_panel() -> RenderableType:
    table = Table(
        expand=True,
        show_header=True,
        header_style=f"bold {_robotics_view.robotics_color('accent')}",
        box=box.SIMPLE,
    )
    table.add_column("pane", no_wrap=True)
    table.add_column("read it as", ratio=2)
    table.add_column("watch for", ratio=2)
    for pane, meaning, watch_for in _robotics_view.ROBOTICS_REPORT_GUIDE_ROWS:
        table.add_row(
            Text(pane, style=f"bold {_robotics_view.robotics_color('success')}"),
            meaning,
            Text(watch_for, style=_robotics_view.robotics_color("muted")),
        )
    footer = Text(
        "Press ? for the tabletop replay legend and mental model.",
        style=f"bold {_robotics_view.robotics_color('warning')}",
    )
    return Panel(
        Group(table, Text(""), footer),
        title="Reading The Report",
        border_style=_robotics_view.robotics_color("panel"),
    )


def robotics_help_section_renderable(
    section: _robotics_view.RoboticsHelpSectionSpec,
) -> str | Text:
    if not section.style_token:
        return section.text
    return Text(section.text, style=f"bold {_robotics_view.robotics_color(section.style_token)}")


def robotics_rerun_panel(summary: dict[str, object]) -> RenderableType:
    path = _robotics_view.robotics_rerun_recording_path(summary)
    if path is None:
        return Panel(
            Text("Rerun recording was not enabled for this run.", style="dim"),
            title="Rerun Recording",
            border_style=_robotics_view.robotics_color("panel"),
        )
    rerun = summary.get("rerun")
    size = None
    written = None
    if isinstance(rerun, dict):
        size = rerun.get("recording_size_bytes")
        written = rerun.get("recording_written")
    status = "written" if written else "configured"
    if isinstance(size, int) and size > 0:
        status = f"{status}, {size} bytes"
    command = _robotics_view.robotics_rerun_viewer_command_text(path)
    table = Table.grid(expand=True)
    table.add_column(no_wrap=True)
    table.add_column(ratio=1)
    table.add_row(Text("path", style="dim"), Text(str(path), style="bold"))
    table.add_row(Text("status", style="dim"), Text(status, style="bold"))
    table.add_row(
        Text("open", style="dim"),
        Text(command, style=_robotics_view.robotics_color("accent")),
    )
    table.add_row(Text("shortcut", style="dim"), Text("press o", style="bold"))
    return Panel(
        table, title="Rerun Recording", border_style=_robotics_view.robotics_color("success")
    )


def robotics_tensorboard_panel(summary: dict[str, object]) -> RenderableType:
    path = _robotics_view.robotics_tensorboard_log_dir(summary)
    if path is None:
        return Panel(
            Text("TensorBoard recording was not enabled for this run.", style="dim"),
            title="TensorBoard Logs",
            border_style=_robotics_view.robotics_color("panel"),
        )
    tensorboard = summary.get("tensorboard")
    events_written = None
    run_name = None
    if isinstance(tensorboard, dict):
        events_written = tensorboard.get("events_written")
        run_name = tensorboard.get("run_name")
    status = "events written" if events_written else "configured"
    command = _robotics_view.robotics_tensorboard_viewer_command_text(path)
    url = _robotics_view.robotics_tensorboard_url()
    table = Table.grid(expand=True)
    table.add_column(no_wrap=True)
    table.add_column(ratio=1)
    table.add_row(Text("path", style="dim"), Text(str(path), style="bold"))
    if isinstance(run_name, str) and run_name.strip():
        table.add_row(Text("run", style="dim"), Text(run_name, style="bold"))
    table.add_row(Text("status", style="dim"), Text(status, style="bold"))
    table.add_row(
        Text("url", style="dim"), Text(url, style=_robotics_view.robotics_color("accent"))
    )
    table.add_row(
        Text("open", style="dim"),
        Text(command, style=_robotics_view.robotics_color("accent")),
    )
    table.add_row(Text("shortcut", style="dim"), Text("press t", style="bold"))
    return Panel(
        table, title="TensorBoard Logs", border_style=_robotics_view.robotics_color("success")
    )


def robotics_metrics_panel(summary: dict[str, object]) -> RenderableType:
    policy_ms = _robotics_view.robotics_event_duration(
        summary, provider="lerobot", operation="policy"
    )
    score_ms = _robotics_view.robotics_event_duration(
        summary,
        provider="leworldmodel",
        operation="score",
    )
    plan_ms = _robotics_view.robotics_number(
        _robotics_view.robotics_nested(summary, "metrics", "plan_latency_ms")
    )
    total_ms = _robotics_view.robotics_number(
        _robotics_view.robotics_nested(summary, "metrics", "total_latency_ms")
    )
    rows = (
        ("policy", policy_ms, _robotics_view.robotics_color("accent")),
        ("score", score_ms, _robotics_view.robotics_color("success")),
        ("plan", plan_ms, _robotics_view.robotics_color("accent")),
        ("total", total_ms, _robotics_view.robotics_color("warning")),
    )
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
            Text(robotics_latency_bar(value, maximum), style=color),
        )
    tensor_mb = _robotics_view.robotics_nested(summary, "inputs", "approx_float32_mb")
    total_elements = _robotics_view.robotics_nested(summary, "inputs", "total_tensor_elements")
    table.add_row("", "", "")
    table.add_row(Text("tensor MB", style="dim"), Text(str(tensor_mb), style="bold"), "")
    table.add_row(Text("elements", style="dim"), Text(str(total_elements), style="bold"), "")
    return Panel(
        table,
        title="Runtime + Tensor Contract",
        border_style=_robotics_view.robotics_color("accent"),
    )


def robotics_latency_bar(value: float, maximum: float, *, width: int = 34) -> str:
    fill = 0 if maximum <= 0 else max(1, min(width, round((value / maximum) * width)))
    return f"{'#' * fill:<{width}}"


def robotics_candidate_panel(summary: dict[str, object]) -> RenderableType:
    targets = _robotics_view.robotics_candidate_targets(summary)
    scores = _robotics_view.robotics_scores(summary)
    selected = _robotics_view.robotics_selected_index(summary)
    table = Table(
        expand=True,
        show_header=True,
        header_style=f"bold {_robotics_view.robotics_color('accent')}",
        box=box.SIMPLE_HEAVY,
    )
    table.add_column("candidate", justify="right", no_wrap=True)
    table.add_column("target", no_wrap=True)
    table.add_column("cost", justify="right", no_wrap=True)
    table.add_column("status", no_wrap=True)
    for target in targets:
        index = _robotics_candidate_index(target)
        score = scores[index] if 0 <= index < len(scores) else None
        x = _robotics_view.robotics_number(target.get("x")) or 0.0
        y = _robotics_view.robotics_number(target.get("y")) or 0.0
        z = _robotics_view.robotics_number(target.get("z")) or 0.0
        status = "SELECTED" if index == selected else ""
        style = f"bold {_robotics_view.robotics_color('success')}" if index == selected else ""
        table.add_row(
            f"#{index}",
            f"x={x:.3f} y={y:.3f} z={z:.3f}",
            "n/a" if score is None else f"{score:.6f}",
            Text(status, style=style),
            style=style,
        )
    return Panel(
        table, title="Candidate Ranking", border_style=_robotics_view.robotics_color("success")
    )


def _robotics_candidate_index(target: dict[str, object]) -> int:
    value = target.get("index", -1)
    if isinstance(value, bool):
        return -1
    if isinstance(value, int):
        return value
    return -1


def robotics_tabletop_panel(summary: dict[str, object]) -> RenderableType:
    legend = Text("S start  G goal  T selected target  F final  X selected+final", style="dim")
    selected = _robotics_view.robotics_selected_index(summary)
    map_text = Text(
        "\n".join(_robotics_view.robotics_tabletop_map_lines(summary)),
        style=f"bold {_robotics_view.robotics_color('success')}",
    )
    subtitle = Text(
        f"selected candidate: #{selected}",
        style=f"bold {_robotics_view.robotics_color('success')}",
    )
    return Panel(
        Group(subtitle, legend, map_text),
        title="Tabletop Replay",
        border_style=_robotics_view.robotics_color("warning"),
    )


def robotics_arm_target_line(summary: dict[str, object]) -> str:
    selected = _robotics_view.robotics_selected_index(summary)
    target = _robotics_selected_target(summary)
    if target is None:
        return f"selected candidate #{selected}"
    x = _robotics_view.robotics_number(target.get("x")) or 0.0
    y = _robotics_view.robotics_number(target.get("y")) or 0.0
    z = _robotics_view.robotics_number(target.get("z")) or 0.0
    return f"selected candidate #{selected}: target x={x:.3f} y={y:.3f} z={z:.3f}"


def _robotics_selected_target(summary: dict[str, object]) -> dict[str, object] | None:
    selected = _robotics_view.robotics_selected_index(summary)
    for target in _robotics_view.robotics_candidate_targets(summary):
        if target.get("index") == selected:
            return target
    return None


def robotics_arm_panel(
    summary: dict[str, object],
    *,
    frame_lines: tuple[str, ...],
    target_line: str,
) -> RenderableType:
    title = Text("Illustrative Arm Replay", style=f"bold {_robotics_view.robotics_color('accent')}")
    subtitle = Text("simulation/replay only; no hardware command is emitted", style="dim")
    target = Text(target_line, style=f"bold {_robotics_view.robotics_color('success')}")
    frame = Text("\n".join(frame_lines), style=_robotics_view.robotics_color("accent"))
    details = Table.grid(expand=True)
    details.add_column(no_wrap=True)
    details.add_column()
    details.add_row(Text("action chunk", style="dim"), Text("1 selected WorldForge action"))
    details.add_row(Text("replay target", style="dim"), target)
    details.add_row(Text("result", style="dim"), Text(_robotics_final_text(summary), style="bold"))
    details.add_row(Text("boundary", style="dim"), Text("local mock execution only"))
    body = Table.grid(expand=True, padding=(0, 3))
    body.add_column(ratio=1)
    body.add_column(ratio=1)
    body.add_row(frame, details)
    return Panel(
        Group(title, subtitle, Text(""), body),
        title="Robot Arm Visualization",
        border_style=_robotics_view.robotics_color("accent"),
    )


def _robotics_final_text(summary: dict[str, object]) -> str:
    final_position = _robotics_view.robotics_final_position(summary)
    if final_position is None:
        return "mock final unavailable"
    return (
        "mock final "
        f"x={final_position['x']:.3f} "
        f"y={final_position['y']:.3f} "
        f"z={final_position['z']:.3f}"
    )


def robotics_event_panel(summary: dict[str, object]) -> RenderableType:
    events = summary.get("provider_events")
    table = Table(
        expand=True,
        show_header=True,
        header_style=f"bold {_robotics_view.robotics_color('accent')}",
    )
    table.add_column("provider", no_wrap=True)
    table.add_column("operation", no_wrap=True)
    table.add_column("phase", no_wrap=True)
    table.add_column("duration", justify="right", no_wrap=True)
    if isinstance(events, list):
        for event in events:
            if not isinstance(event, dict):
                continue
            duration = _robotics_view.robotics_number(event.get("duration_ms"))
            table.add_row(
                str(event.get("provider")),
                str(event.get("operation")),
                str(event.get("phase")),
                "n/a" if duration is None else f"{duration:.2f} ms",
            )
    return Panel(
        table, title="Provider Event Log", border_style=_robotics_view.robotics_color("panel")
    )


def robotics_progress_panel(message: str) -> RenderableType:
    return Panel(
        Text(message, style=f"bold {_robotics_view.robotics_color('accent')}"),
        title="Replay Sequencer",
        border_style=_robotics_view.robotics_color("accent"),
    )

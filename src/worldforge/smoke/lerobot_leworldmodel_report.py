"""Terminal report helpers for the LeRobot plus LeWorldModel smoke runner."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .leworldmodel_output import _display_path, _paint
from .leworldmodel_tensors import _score_chart

_TABLETOP_REPLAY_WIDTH = 42
_TABLETOP_REPLAY_HEIGHT = 13
_TABLETOP_START = (0.0, 0.5)
_TABLETOP_GOAL = (0.5, 0.5)


def _print_header(*, color: bool) -> None:
    title = "WorldForge real robotics policy+world-model inference"
    print(_paint(title, "cyan", enabled=color, bold=True))
    print("=" * len(title))
    print("Mode: real LeRobot policy inference plus real LeWorldModel checkpoint scoring.")
    print(
        "Run contract: "
        f"{_paint('REAL', 'green', enabled=color, bold=True)} policy + "
        f"{_paint('REAL', 'green', enabled=color, bold=True)} score + "
        f"{_paint('LOCAL', 'yellow', enabled=color, bold=True)} mock replay"
    )
    print("\nWhat this demonstrates")
    print("----------------------")
    print("  - loads a host-owned LeRobot policy checkpoint")
    print("  - loads a host-owned LeWorldModel object checkpoint")
    print("  - asks LeRobot for action candidates from a task observation")
    print("  - bridges policy actions into LeWorldModel action-candidate tensors")
    print("  - ranks those candidates through WorldForge policy+score planning")
    print("  - executes the selected WorldForge action chunk in the local mock world")
    print(
        "Boundary: this is simulation/replay planning. Hardware control, safety checks, "
        "and task-specific preprocessing remain host-owned."
    )
    print("\nPipeline")
    print("--------")
    print(
        "  observation -> LeRobot policy -> action candidates -> tensor bridge -> "
        "LeWorldModel costs -> WorldForge plan -> mock execution"
    )
    print("\nPipeline map")
    print("------------")
    print("  +-------------------+      +-------------------+      +----------------------+")
    print("  | PushT observation | ---> | LeRobot policy    | ---> | action candidates    |")
    print("  +-------------------+      +-------------------+      +----------+-----------+")
    print("             |                                                    |")
    print("             v                                                    v")
    print("  +-------------------+      +-------------------+      +----------------------+")
    print("  | LeWM score tensors| ---> | LeWorldModel cost | ---> | WorldForge planner   |")
    print("  +-------------------+      +-------------------+      +----------+-----------+")
    print("                                                                  |")
    print("                                                                  v")
    print("                                                        +----------------------+")
    print("                                                        | local mock replay    |")
    print("                                                        +----------------------+")


def _log_step(
    index: int,
    total: int,
    title: str,
    rows: list[tuple[str, object]] | None = None,
    *,
    color: bool,
) -> None:
    print(f"\n{_paint(f'[{index}/{total}] {title}', 'cyan', enabled=color, bold=True)}")
    for label, value in rows or []:
        print(f"  {label:<22} {value}")


def _print_provider_events(events: list[dict[str, Any]]) -> None:
    print("\nProvider event log")
    print("------------------")
    if not events:
        print("  no provider events emitted")
        return
    for event in events:
        duration = event.get("duration_ms")
        duration_text = f"{float(duration):.2f} ms" if duration is not None else "n/a"
        metadata = event.get("metadata") if isinstance(event.get("metadata"), dict) else {}
        metadata_text = " ".join(
            f"{key}={value}" for key, value in sorted(metadata.items()) if value is not None
        )
        print(
            f"  {event.get('provider')}.{event.get('operation')} "
            f"{event.get('phase')} duration={duration_text} {metadata_text}".rstrip()
        )


def _section(title: str) -> None:
    print(f"\n{title}")
    print("-" * len(title))


def _float_or_none(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    number = float(value)
    if number != number or number in (float("inf"), float("-inf")):
        return None
    return number


def _provider_latency_ms(
    events: list[dict[str, Any]],
    provider: str,
    operation: str,
) -> float | None:
    for event in reversed(events):
        if event.get("provider") == provider and event.get("operation") == operation:
            return _float_or_none(event.get("duration_ms"))
    return None


def _bar(value: float, maximum: float, *, width: int = 30) -> str:
    if maximum <= 0.0 or value <= 0.0:
        fill = 0
    else:
        fill = max(1, min(width, round((value / maximum) * width)))
    return f"|{'#' * fill:<{width}}|"


def _print_runtime_profile(
    *,
    events: list[dict[str, Any]],
    plan_latency_ms: float,
    total_latency_ms: float,
    color: bool,
) -> None:
    rows = [
        ("LeRobot policy", _provider_latency_ms(events, "lerobot", "policy")),
        ("LeWorldModel score", _provider_latency_ms(events, "leworldmodel", "score")),
        ("WorldForge plan", plan_latency_ms),
        ("End-to-end run", total_latency_ms),
    ]
    maximum = max((value or 0.0) for _label, value in rows)
    _section("Runtime profile")
    for label, value in rows:
        if value is None:
            print(f"  {label:<20} {'n/a':>10}  {_bar(0.0, maximum)}")
            continue
        bar_color = "green" if label == "LeWorldModel score" else "cyan"
        bar = _paint(_bar(value, maximum), bar_color, enabled=color)
        print(f"  {label:<20} {value:>9.2f} ms  {bar}")


def _print_score_summary(stats: dict[str, Any]) -> None:
    if not stats:
        return
    _section("Score summary")
    rows = [
        ("min", stats.get("score_min")),
        ("median", stats.get("score_median")),
        ("mean", stats.get("score_mean")),
        ("max", stats.get("score_max")),
        ("range", stats.get("score_range")),
        ("gap to runner-up", stats.get("gap_to_runner_up")),
    ]
    for label, value in rows:
        number = _float_or_none(value)
        text = "n/a" if number is None else f"{number:.6f}"
        print(f"  {label:<18} {text}")


def _action_target(action: object) -> dict[str, float] | None:
    if not isinstance(action, dict):
        return None
    parameters = action.get("parameters")
    if not isinstance(parameters, dict):
        return None
    target = parameters.get("target")
    if not isinstance(target, dict):
        return None
    x = _float_or_none(target.get("x"))
    y = _float_or_none(target.get("y"))
    z = _float_or_none(target.get("z"))
    if x is None or y is None or z is None:
        return None
    return {"x": x, "y": y, "z": z}


def _candidate_targets(policy_result: dict[str, Any]) -> list[dict[str, Any]]:
    candidates = policy_result.get("action_candidates")
    if not isinstance(candidates, list):
        return []
    targets: list[dict[str, Any]] = []
    for index, candidate in enumerate(candidates):
        if not isinstance(candidate, list) or not candidate:
            continue
        target = _action_target(candidate[0])
        if target is None:
            continue
        targets.append({"index": index, **target})
    return targets


def _score_by_index(score_result: dict[str, Any]) -> dict[int, float]:
    scores = score_result.get("scores")
    if not isinstance(scores, list):
        return {}
    score_map: dict[int, float] = {}
    for index, score in enumerate(scores):
        number = _float_or_none(score)
        if number is not None:
            score_map[index] = number
    return score_map


def _print_candidate_targets(
    *,
    policy_result: dict[str, Any],
    score_result: dict[str, Any],
    color: bool,
) -> list[dict[str, Any]]:
    targets = _candidate_targets(policy_result)
    if not targets:
        return []
    scores = _score_by_index(score_result)
    best_index = score_result.get("best_index")
    _section("Candidate targets")
    print(f"  {'candidate':<10} {'x':>8} {'y':>8} {'z':>8} {'score':>12}  status")
    for target in targets:
        index = int(target["index"])
        score = scores.get(index)
        marker = "SELECTED" if index == best_index else ""
        status = _paint(marker, "green", enabled=color, bold=True) if marker else ""
        score_text = "n/a" if score is None else f"{score:.6f}"
        print(
            f"  #{index:<9} {target['x']:>8.3f} {target['y']:>8.3f} "
            f"{target['z']:>8.3f} {score_text:>12}  {status}"
        )
    return targets


def _position_from_summary(summary: dict[str, Any] | None) -> dict[str, float] | None:
    if not isinstance(summary, dict):
        return None
    position = summary.get("final_block_position")
    if not isinstance(position, dict):
        return None
    x = _float_or_none(position.get("x"))
    y = _float_or_none(position.get("y"))
    z = _float_or_none(position.get("z"))
    if x is None or y is None or z is None:
        return None
    return {"x": x, "y": y, "z": z}


def _print_tabletop_replay(
    *,
    targets: list[dict[str, Any]],
    score_result: dict[str, Any],
    execution_summary: dict[str, Any] | None,
) -> None:
    lines = _tabletop_replay_lines(
        targets=targets,
        score_result=score_result,
        execution_summary=execution_summary,
    )
    if not lines:
        return
    _section("Tabletop replay")
    for line in lines:
        print(line)


def _tabletop_replay_lines(
    *,
    targets: list[dict[str, Any]],
    score_result: dict[str, Any],
    execution_summary: dict[str, Any] | None,
) -> list[str]:
    if not targets:
        return []
    best_index = score_result.get("best_index")
    cells = _tabletop_replay_cells(
        targets=targets,
        best_index=best_index,
        execution_summary=execution_summary,
    )
    lines = [
        "  legend: S=start, G=goal, T=selected target, F=mock final, X=selected+final",
    ]
    if isinstance(best_index, int):
        lines.append(f"  selected candidate: #{best_index}")
    lines.append("  +" + "-" * _TABLETOP_REPLAY_WIDTH + "+")
    lines.extend(_tabletop_replay_row(cells, row) for row in range(_TABLETOP_REPLAY_HEIGHT))
    lines.append("  +" + "-" * _TABLETOP_REPLAY_WIDTH + "+")
    lines.append("  x=0.00             x=0.50             x=1.00")
    return lines


def _tabletop_replay_cells(
    *,
    targets: list[dict[str, Any]],
    best_index: object,
    execution_summary: dict[str, Any] | None,
) -> dict[tuple[int, int], set[str]]:
    cells: dict[tuple[int, int], set[str]] = {}
    _place_tabletop_marker(cells, *_TABLETOP_START, marker="S")
    _place_tabletop_marker(cells, *_TABLETOP_GOAL, marker="G")
    for target in targets:
        index = int(target["index"])
        marker = "T" if index == best_index else str(index % 10)
        _place_tabletop_marker(cells, float(target["x"]), float(target["y"]), marker=marker)
    final_position = _position_from_summary(execution_summary)
    if final_position is not None:
        _place_tabletop_marker(cells, final_position["x"], final_position["y"], marker="F")
    return cells


def _place_tabletop_marker(
    cells: dict[tuple[int, int], set[str]],
    x: float,
    y: float,
    *,
    marker: str,
) -> None:
    column = max(0, min(_TABLETOP_REPLAY_WIDTH - 1, round(x * (_TABLETOP_REPLAY_WIDTH - 1))))
    row = max(0, min(_TABLETOP_REPLAY_HEIGHT - 1, round((1.0 - y) * (_TABLETOP_REPLAY_HEIGHT - 1))))
    cells.setdefault((row, column), set()).add(marker)


def _tabletop_replay_row(cells: dict[tuple[int, int], set[str]], row: int) -> str:
    chars = [
        _tabletop_cell_marker(cells.get((row, column), set()))
        for column in range(_TABLETOP_REPLAY_WIDTH)
    ]
    return f"  |{''.join(chars)}|"


def _tabletop_cell_marker(markers: set[str]) -> str:
    if not markers:
        return " "
    if "F" in markers and "T" in markers:
        return "X"
    if "F" in markers:
        return "F"
    if "T" in markers:
        return "T"
    if len(markers) > 1:
        return "*"
    return next(iter(markers))


def _runtime_command(*, checkpoint: Path, policy_path: str, device: str) -> str:
    checkpoint_text = _display_path(checkpoint)
    return (
        "scripts/lewm-lerobot-real \\\n"
        f"  --policy-path {policy_path} \\\n"
        "  --policy-type diffusion \\\n"
        f"  --checkpoint {checkpoint_text} \\\n"
        f"  --device {device} \\\n"
        "  --mode select_action \\\n"
        "  --bridge pusht"
    )


def _event_latency(events: list[dict[str, Any]], provider: str, operation: str) -> str:
    for event in reversed(events):
        if event.get("provider") == provider and event.get("operation") == operation:
            duration = event.get("duration_ms")
            if duration is not None:
                return f"{float(duration):.2f}"
    return "n/a"


def _print_success_report(
    _args: object,
    *,
    summary: Any,
    plan_run: Any,
    total_latency_ms: float,
    json_output_path: Path | None,
    run_manifest_path: Path | None,
    color: bool,
) -> None:
    _print_score_tensor_shapes(summary)
    _print_runtime_profile(
        events=summary.event_payload,
        plan_latency_ms=plan_run.plan_latency_ms,
        total_latency_ms=total_latency_ms,
        color=color,
    )
    _print_score_summary(plan_run.score_stats)
    _print_candidate_cost_landscape(plan_run.score_result, color=color)
    printed_targets = _print_candidate_targets(
        policy_result=plan_run.policy_result,
        score_result=plan_run.score_result,
        color=color,
    )
    _print_tabletop_replay(
        targets=printed_targets,
        score_result=plan_run.score_result,
        execution_summary=plan_run.execution_summary,
    )
    _print_selected_plan(plan_run)
    _print_provider_events(summary.event_payload)
    _print_artifact_summary(
        payload=summary.payload,
        json_output_path=json_output_path,
        run_manifest_path=run_manifest_path,
    )
    print("\nCompleted real LeRobot + LeWorldModel policy+score inference.")
    print("Use --json-only for the machine-readable summary.")


def _print_score_tensor_shapes(summary: Any) -> None:
    print("\nScore tensor shapes")
    print("-------------------")
    for label, shape in summary.score_shapes.items():
        print(f"  {label:<22} {shape}")
    print(f"  {'tensor elements':<22} {summary.input_stats['total_tensor_elements']}")
    print(f"  {'approx float32 MB':<22} {summary.input_stats['approx_float32_mb']}")


def _print_candidate_cost_landscape(score_result: dict[str, Any], *, color: bool) -> None:
    print("\nCandidate cost landscape")
    print("------------------------")
    for line in _score_chart(score_result, color=color):
        print(line)


def _print_selected_plan(plan_run: Any) -> None:
    print("\nSelected plan")
    print("-------------")
    print(f"  selected candidate     #{plan_run.score_result.get('best_index')}")
    print(f"  selected actions       {len(plan_run.plan.actions)}")
    print(f"  success heuristic      {plan_run.plan.success_probability:.6f}")
    if plan_run.execution_summary is not None:
        print(f"  mock final step        {plan_run.execution_summary['final_step']}")
        print(f"  mock final block       {plan_run.execution_summary['final_block_position']}")


def _print_artifact_summary(
    *,
    payload: dict[str, Any],
    json_output_path: Path | None,
    run_manifest_path: Path | None,
) -> None:
    rerun_artifact = payload.get("rerun")
    tensorboard_artifact = payload.get("tensorboard")
    if not (
        json_output_path is not None
        or run_manifest_path is not None
        or isinstance(rerun_artifact, dict)
        or isinstance(tensorboard_artifact, dict)
    ):
        return
    print("\nArtifacts")
    print("---------")
    if json_output_path is not None:
        print(f"  json summary           {_display_path(json_output_path)}")
    if run_manifest_path is not None:
        print(f"  run manifest           {_display_path(run_manifest_path)}")
    if isinstance(rerun_artifact, dict):
        _print_rerun_artifact_summary(rerun_artifact)
    if isinstance(tensorboard_artifact, dict):
        _print_tensorboard_artifact_summary(tensorboard_artifact)


def _print_rerun_artifact_summary(rerun_artifact: dict[str, Any]) -> None:
    save_path = rerun_artifact.get("save_path")
    server_uri = rerun_artifact.get("server_uri")
    if save_path:
        suffix = ""
        if rerun_artifact.get("recording_written"):
            suffix = f" ({rerun_artifact.get('recording_size_bytes')} bytes written)"
        print(f"  rerun recording        {_display_path(Path(str(save_path)))}{suffix}")
    elif server_uri:
        print(f"  rerun stream           {server_uri}")
    else:
        print("  rerun recording        viewer")


def _print_tensorboard_artifact_summary(tensorboard_artifact: dict[str, Any]) -> None:
    log_dir = tensorboard_artifact.get("log_dir")
    if log_dir:
        suffix = " (events written)" if tensorboard_artifact.get("events_written") else ""
        print(f"  tensorboard logdir     {_display_path(Path(str(log_dir)))}{suffix}")

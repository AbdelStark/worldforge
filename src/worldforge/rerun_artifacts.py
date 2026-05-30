"""Pure artifact visualization helpers for optional Rerun logging."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from worldforge.models import JSONDict, WorldForgeError
from worldforge.rerun_paths import entity_path, entity_segment

_BENCHMARK_SCALAR_METRICS = (
    "error_count",
    "retry_count",
    "average_latency_ms",
    "p50_latency_ms",
    "p95_latency_ms",
    "throughput_per_second",
)
_ROBOTICS_RUNTIME_METRICS = ("plan_latency_ms", "total_latency_ms")

_LogJson = Callable[[object, str, JSONDict], None]
_LogScalar = Callable[[object, str, float], None]


@dataclass(frozen=True, slots=True)
class _BenchmarkResultView:
    index: int
    payload: JSONDict


@dataclass(frozen=True, slots=True)
class _RuntimeLatencyRow:
    label: str
    value_ms: float


@dataclass(frozen=True, slots=True)
class _ActionTargetView:
    position: list[float]
    label: str


@dataclass(frozen=True, slots=True)
class _WorldObjectVisualization:
    object_id: str
    name: str
    position: list[float]
    color: list[int]
    is_graspable: bool
    box_center: list[float] | None
    box_size: list[float] | None


@dataclass(frozen=True, slots=True)
class _RoboticsTarget:
    index: int
    point: list[float]


@dataclass(frozen=True, slots=True)
class _RoboticsTabletopScene:
    start: list[float]
    goal: list[float]
    targets: list[_RoboticsTarget]
    selected_candidate: object
    selected_target: list[float] | None
    final_position: list[float] | None
    scores: list[float]


def finite_float(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    number = float(value)
    if number != number or number in (float("inf"), float("-inf")):
        return None
    return number


def _position_xyz(value: object) -> list[float] | None:
    if not isinstance(value, dict):
        return None
    x = finite_float(value.get("x"))
    y = finite_float(value.get("y"))
    z = finite_float(value.get("z"))
    if x is None or y is None or z is None:
        return None
    return [x, y, z]


def _bbox_geometry(value: object) -> tuple[list[float], list[float]] | None:
    if not isinstance(value, dict):
        return None
    bbox_min = _position_xyz(value.get("min"))
    bbox_max = _position_xyz(value.get("max"))
    if bbox_min is None or bbox_max is None:
        return None
    center = [(bbox_min[index] + bbox_max[index]) / 2.0 for index in range(3)]
    size = [max(0.0, bbox_max[index] - bbox_min[index]) for index in range(3)]
    return center, size


def _score_values(value: object) -> list[float]:
    if not isinstance(value, list):
        return []
    scores: list[float] = []
    for item in value:
        number = finite_float(item)
        if number is not None:
            scores.append(number)
    return scores


def _int_metric(value: object) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value


def _benchmark_success_rate(result: JSONDict) -> float | None:
    iterations = _int_metric(result.get("iterations"))
    success_count = _int_metric(result.get("success_count"))
    if iterations is None or success_count is None or iterations <= 0:
        return None
    if success_count < 0 or success_count > iterations:
        return None
    return success_count / iterations


def _benchmark_scalar_values(result: JSONDict) -> list[tuple[str, float]]:
    values: list[tuple[str, float]] = []
    success_rate = _benchmark_success_rate(result)
    if success_rate is not None:
        values.append(("success_rate", success_rate))
    values.extend(
        (metric, value)
        for metric in _BENCHMARK_SCALAR_METRICS
        for value in (finite_float(result.get(metric)),)
        if value is not None
    )
    return values


def _benchmark_result_views(payload: JSONDict) -> list[_BenchmarkResultView]:
    results = payload.get("results", [])
    if not isinstance(results, list):
        raise WorldForgeError("benchmark_report.results must be a list.")
    views: list[_BenchmarkResultView] = []
    for index, result in enumerate(results):
        if not isinstance(result, dict):
            raise WorldForgeError("benchmark_report.results entries must be JSON objects.")
        views.append(_BenchmarkResultView(index=index, payload=result))
    return views


def log_benchmark_results(
    rr: object,
    path_prefix: str,
    timeline: str,
    payload: JSONDict,
    *,
    log_json: _LogJson,
    log_scalar: _LogScalar,
) -> None:
    for view in _benchmark_result_views(payload):
        rr.set_time(timeline, sequence=view.index)
        base_path = entity_path(
            path_prefix,
            "benchmarks",
            view.payload.get("provider", "provider"),
            view.payload.get("operation", "operation"),
        )
        log_json(rr, f"{base_path}/result", view.payload)
        for metric, value in _benchmark_scalar_values(view.payload):
            log_scalar(rr, f"{base_path}/{metric}", value)


def world_step(state: JSONDict) -> int:
    step = state.get("step", 0)
    if isinstance(step, bool) or not isinstance(step, int) or step < 0:
        raise WorldForgeError("world.step must be a non-negative integer.")
    return step


def world_scene_objects(state: JSONDict) -> dict[str, object]:
    scene = state.get("scene", {})
    if not isinstance(scene, dict):
        raise WorldForgeError("world.scene must be a JSON object.")
    objects = scene.get("objects", {})
    if not isinstance(objects, dict):
        raise WorldForgeError("world.scene.objects must be a JSON object.")
    return objects


def _world_object_position(item: dict[str, object]) -> list[float] | None:
    pose = item.get("pose", {})
    position = pose.get("position", {}) if isinstance(pose, dict) else {}
    if not isinstance(position, dict):
        return None
    try:
        return [float(position["x"]), float(position["y"]), float(position["z"])]
    except (KeyError, TypeError, ValueError):
        return None


def _world_object_visualization(
    object_id: str,
    item: dict[str, object],
) -> _WorldObjectVisualization | None:
    position = _world_object_position(item)
    if position is None:
        return None
    name = str(item.get("name") or object_id)
    is_graspable = bool(item.get("is_graspable", False))
    bbox_geometry = _bbox_geometry(item.get("bbox"))
    box_center = None
    box_size = None
    if bbox_geometry is not None:
        box_center, box_size = bbox_geometry
    return _WorldObjectVisualization(
        object_id=object_id,
        name=name,
        position=position,
        color=[52, 111, 235] if is_graspable else [42, 170, 120],
        is_graspable=is_graspable,
        box_center=box_center,
        box_size=box_size,
    )


def _world_object_visualizations(objects: dict[str, object]) -> list[_WorldObjectVisualization]:
    visualizations: list[_WorldObjectVisualization] = []
    for object_id, item in objects.items():
        if not isinstance(item, dict):
            raise WorldForgeError("world.scene.objects entries must be JSON objects.")
        visualization = _world_object_visualization(str(object_id), item)
        if visualization is not None:
            visualizations.append(visualization)
    return visualizations


def log_rerun_any_values(rr: object, path: str, **values: object) -> None:
    any_values = getattr(rr, "AnyValues", None)
    if any_values is not None:
        rr.log(path, any_values(**values))


def log_world_visual_layers(rr: object, world_path: str, objects: dict[str, object]) -> None:
    visualizations = _world_object_visualizations(objects)
    _log_world_object_values(rr, world_path, visualizations)
    _log_world_object_points(rr, world_path, visualizations)
    _log_world_object_boxes(rr, world_path, visualizations)


def _log_world_object_values(
    rr: object,
    world_path: str,
    visualizations: list[_WorldObjectVisualization],
) -> None:
    for item in visualizations:
        log_rerun_any_values(
            rr,
            f"{world_path}/objects/{entity_segment(item.object_id)}",
            object_id=item.object_id,
            name=item.name,
            x=item.position[0],
            y=item.position[1],
            z=item.position[2],
            is_graspable=item.is_graspable,
        )


def _log_world_object_points(
    rr: object,
    world_path: str,
    visualizations: list[_WorldObjectVisualization],
) -> None:
    points = getattr(rr, "Points3D", None)
    if points is None or not visualizations:
        return
    positions = [item.position for item in visualizations]
    rr.log(
        f"{world_path}/objects",
        points(
            positions,
            labels=[item.name for item in visualizations],
            colors=[item.color for item in visualizations],
            radii=[0.04] * len(positions),
        ),
    )


def _log_world_object_boxes(
    rr: object,
    world_path: str,
    visualizations: list[_WorldObjectVisualization],
) -> None:
    boxes = getattr(rr, "Boxes3D", None)
    box_items = [
        item for item in visualizations if item.box_center is not None and item.box_size is not None
    ]
    if boxes is None or not box_items:
        return
    rr.log(
        f"{world_path}/object_boxes",
        boxes(
            centers=[item.box_center for item in box_items],
            sizes=[item.box_size for item in box_items],
            labels=[item.name for item in box_items],
            colors=[item.color for item in box_items],
            radii=[0.002] * len(box_items),
        ),
    )


def _robotics_tabletop_scene(payload: JSONDict) -> _RoboticsTabletopScene | None:
    visualization = payload.get("visualization")
    if not isinstance(visualization, dict):
        return None
    targets_payload = visualization.get("candidate_targets")
    if not isinstance(targets_payload, list):
        return None

    score_result = payload.get("score_result")
    score_result = score_result if isinstance(score_result, dict) else {}
    selected_candidate = score_result.get("best_index", visualization.get("selected_candidate"))
    targets = _robotics_targets(targets_payload)
    if not targets:
        return None

    execution = payload.get("execution")
    final_position = None
    if isinstance(execution, dict):
        final_position = _position_xyz(execution.get("final_block_position"))
    selected_target = next(
        (target.point for target in targets if target.index == selected_candidate),
        None,
    )
    return _RoboticsTabletopScene(
        start=[0.0, 0.5, 0.0],
        goal=[0.5, 0.5, 0.0],
        targets=targets,
        selected_candidate=selected_candidate,
        selected_target=selected_target,
        final_position=final_position,
        scores=_score_values(score_result.get("scores")),
    )


def _robotics_targets(targets_payload: list[object]) -> list[_RoboticsTarget]:
    targets: list[_RoboticsTarget] = []
    for target in targets_payload:
        if not isinstance(target, dict):
            continue
        index = target.get("index")
        if isinstance(index, bool) or not isinstance(index, int):
            continue
        point = _position_xyz(target)
        if point is not None:
            targets.append(_RoboticsTarget(index=index, point=point))
    return targets


def _candidate_score_text(index: int, scores: list[float]) -> str:
    if index >= len(scores):
        return ""
    return f" cost={scores[index]:.3f}"


def _robotics_point_layers(
    scene: _RoboticsTabletopScene,
) -> tuple[list[list[float]], list[str], list[list[int]]]:
    points = [scene.start, scene.goal, *(target.point for target in scene.targets)]
    labels = ["start", "goal"]
    colors = [[90, 90, 90], [42, 170, 120]]
    for target in scene.targets:
        score_text = _candidate_score_text(target.index, scene.scores)
        labels.append(f"candidate {target.index}{score_text}")
        colors.append(
            [42, 170, 120] if target.index == scene.selected_candidate else [235, 147, 52]
        )
    if scene.final_position is not None:
        points.append(scene.final_position)
        labels.append("mock final")
        colors.append([52, 111, 235])
    return points, labels, colors


def log_robotics_tabletop(rr: object, base_path: str, payload: JSONDict) -> None:
    scene = _robotics_tabletop_scene(payload)
    if scene is None:
        return
    _log_robotics_points(rr, base_path, scene)
    _log_robotics_candidate_paths(rr, base_path, scene)
    _log_robotics_selected_vector(rr, base_path, scene)
    _log_robotics_block_boxes(rr, base_path, scene)


def _log_robotics_points(rr: object, base_path: str, scene: _RoboticsTabletopScene) -> None:
    points3d = getattr(rr, "Points3D", None)
    if points3d is None:
        return
    points, labels, colors = _robotics_point_layers(scene)
    rr.log(
        f"{base_path}/tabletop/points",
        points3d(points, labels=labels, colors=colors, radii=[0.035] * len(points)),
    )


def _log_robotics_candidate_paths(
    rr: object,
    base_path: str,
    scene: _RoboticsTabletopScene,
) -> None:
    line_strips = getattr(rr, "LineStrips3D", None)
    if line_strips is None:
        return
    strips = [[scene.start, target.point] for target in scene.targets]
    strip_colors = [
        [42, 170, 120] if target.index == scene.selected_candidate else [235, 147, 52]
        for target in scene.targets
    ]
    radii = [
        0.01 if target.index == scene.selected_candidate else 0.004 for target in scene.targets
    ]
    rr.log(
        f"{base_path}/tabletop/candidate_paths",
        line_strips(
            strips,
            labels=[f"candidate {target.index}" for target in scene.targets],
            colors=strip_colors,
            radii=radii,
        ),
    )
    if scene.final_position is not None:
        _log_selected_replay(rr, base_path, scene, line_strips)


def _log_selected_replay(
    rr: object,
    base_path: str,
    scene: _RoboticsTabletopScene,
    line_strips: object,
) -> None:
    if scene.final_position is None:
        return
    replay_strip = [scene.start]
    if scene.selected_target is not None:
        replay_strip.append(scene.selected_target)
    replay_strip.append(scene.final_position)
    rr.log(
        f"{base_path}/tabletop/selected_replay",
        line_strips(
            [replay_strip],
            labels=["selected candidate replay"],
            colors=[[52, 111, 235]],
            radii=[0.012],
        ),
    )


def _log_robotics_selected_vector(
    rr: object,
    base_path: str,
    scene: _RoboticsTabletopScene,
) -> None:
    arrows = getattr(rr, "Arrows3D", None)
    if arrows is None or scene.selected_target is None:
        return
    vector = [scene.selected_target[index] - scene.start[index] for index in range(3)]
    rr.log(
        f"{base_path}/tabletop/selected_vector",
        arrows(
            origins=[scene.start],
            vectors=[vector],
            labels=["selected action"],
            colors=[[42, 170, 120]],
            radii=[0.012],
        ),
    )


def _log_robotics_block_boxes(rr: object, base_path: str, scene: _RoboticsTabletopScene) -> None:
    boxes = getattr(rr, "Boxes3D", None)
    if boxes is None:
        return
    centers = [scene.start]
    sizes = [[0.1, 0.1, 0.05]]
    box_labels = ["start block"]
    box_colors = [[90, 90, 90]]
    if scene.final_position is not None:
        centers.append(scene.final_position)
        sizes.append([0.1, 0.1, 0.05])
        box_labels.append("mock final block")
        box_colors.append([52, 111, 235])
    rr.log(
        f"{base_path}/tabletop/block_boxes",
        boxes(
            centers=centers,
            sizes=sizes,
            labels=box_labels,
            colors=box_colors,
            radii=[0.002] * len(centers),
        ),
    )


def log_robotics_score_landscape(
    rr: object,
    base_path: str,
    payload: JSONDict,
    *,
    log_scalar: _LogScalar,
) -> None:
    score_result = payload.get("score_result")
    if not isinstance(score_result, dict):
        return
    scores = _score_values(score_result.get("scores"))
    if not scores:
        return
    bar_chart = getattr(rr, "BarChart", None)
    if bar_chart is not None:
        rr.log(f"{base_path}/scores/cost_bars", bar_chart(scores, color=[235, 147, 52]))
    for index, score in enumerate(scores):
        rr.set_time("worldforge_candidate", sequence=index)
        log_scalar(rr, f"{base_path}/scores/candidate_cost", score)
    best_score = finite_float(score_result.get("best_score"))
    if best_score is not None:
        log_scalar(rr, f"{base_path}/scores/best_cost", best_score)


def _provider_event_latency_rows(events: object) -> list[_RuntimeLatencyRow]:
    if not isinstance(events, list):
        return []
    rows: list[_RuntimeLatencyRow] = []
    for event in events:
        if not isinstance(event, dict):
            continue
        provider = event.get("provider")
        operation = event.get("operation")
        duration = finite_float(event.get("duration_ms"))
        if isinstance(provider, str) and isinstance(operation, str) and duration is not None:
            rows.append(_RuntimeLatencyRow(label=f"{provider}.{operation}", value_ms=duration))
    return rows


def _runtime_metric_latency_rows(metrics: object) -> list[_RuntimeLatencyRow]:
    if not isinstance(metrics, dict):
        return []
    return [
        _RuntimeLatencyRow(label=metric, value_ms=value)
        for metric in _ROBOTICS_RUNTIME_METRICS
        for value in (finite_float(metrics.get(metric)),)
        if value is not None
    ]


def _runtime_latency_rows(payload: JSONDict) -> list[_RuntimeLatencyRow]:
    return [
        *_provider_event_latency_rows(payload.get("provider_events")),
        *_runtime_metric_latency_rows(payload.get("metrics")),
    ]


def log_robotics_runtime_profile(rr: object, base_path: str, payload: JSONDict) -> None:
    rows = _runtime_latency_rows(payload)
    if not rows:
        return
    _log_runtime_latency_bars(rr, base_path, rows)
    _log_runtime_latency_labels(rr, base_path, rows)


def _log_runtime_latency_bars(
    rr: object,
    base_path: str,
    rows: list[_RuntimeLatencyRow],
) -> None:
    bar_chart = getattr(rr, "BarChart", None)
    if bar_chart is not None:
        rr.log(
            f"{base_path}/runtime/latency_bars",
            bar_chart([row.value_ms for row in rows], color=[52, 111, 235]),
        )


def _log_runtime_latency_labels(
    rr: object,
    base_path: str,
    rows: list[_RuntimeLatencyRow],
) -> None:
    log_rerun_any_values(
        rr,
        f"{base_path}/runtime/latency_labels",
        labels=[row.label for row in rows],
        values_ms=[row.value_ms for row in rows],
    )


def _action_target_view(index: int, action: object) -> _ActionTargetView | None:
    if not isinstance(action, dict):
        return None
    parameters = action.get("parameters", {})
    if not isinstance(parameters, dict):
        return None
    position = _position_xyz(parameters.get("target"))
    if position is None:
        return None
    return _ActionTargetView(position=position, label=f"{index}:{action.get('type', 'action')}")


def _action_target_views(actions: object) -> list[_ActionTargetView]:
    if not isinstance(actions, list):
        return []
    return [
        target
        for index, action in enumerate(actions)
        for target in (_action_target_view(index, action),)
        if target is not None
    ]


def log_action_targets(rr: object, plan_path: str, actions: object) -> None:
    targets = _action_target_views(actions)
    points = getattr(rr, "Points3D", None)
    if points is not None and targets:
        rr.log(
            f"{plan_path}/action_targets",
            points(
                [target.position for target in targets],
                labels=[target.label for target in targets],
                colors=[[235, 147, 52]] * len(targets),
                radii=[0.035] * len(targets),
            ),
        )

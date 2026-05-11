"""Optional Rerun integration for WorldForge observability and run artifacts."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from importlib import import_module
from pathlib import Path
from threading import Lock
from typing import Any

from worldforge.models import JSONDict, ProviderEvent, WorldForgeError, dump_json, require_json_dict

_ENTITY_SEGMENT_PATTERN = re.compile(r"[^A-Za-z0-9_.-]+")
_DEFAULT_EVENT_PREFIX = "worldforge/events"
_DEFAULT_ARTIFACT_PREFIX = "worldforge"


def _require_text(value: object, *, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise WorldForgeError(f"{name} must be a non-empty string.")
    return value.strip()


def _require_optional_text(value: object, *, name: str) -> str | None:
    if value is None:
        return None
    return _require_text(value, name=name)


def _require_bool(value: object, *, name: str) -> bool:
    if not isinstance(value, bool):
        raise WorldForgeError(f"{name} must be a boolean.")
    return value


def _require_optional_bool(value: object, *, name: str) -> bool | None:
    if value is None:
        return None
    return _require_bool(value, name=name)


def _require_port(value: object, *, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1 or value > 65535:
        raise WorldForgeError(f"{name} must be an integer TCP port in [1, 65535].")
    return value


def _entity_segment(value: object, *, fallback: str = "item") -> str:
    text = str(value).strip().strip("/")
    if not text:
        return fallback
    segment = _ENTITY_SEGMENT_PATTERN.sub("_", text).strip("._-")
    if not segment or segment.startswith("__"):
        return fallback
    return segment


def _entity_path(prefix: str, *segments: object) -> str:
    clean_prefix = _validate_path_prefix(prefix, name="path_prefix")
    clean_segments: list[str] = []
    for segment in segments:
        raw_segment = str(segment).strip("/")
        if not raw_segment:
            clean_segments.append(_entity_segment(segment))
            continue
        clean_segments.extend(_entity_segment(part) for part in raw_segment.split("/") if part)
    return "/".join([clean_prefix, *clean_segments])


def _validate_path_prefix(value: object, *, name: str) -> str:
    prefix = _require_text(value, name=name).strip("/")
    if not prefix:
        raise WorldForgeError(f"{name} must contain at least one path segment.")
    if any(not part or part.startswith("__") for part in prefix.split("/")):
        raise WorldForgeError(f"{name} must not contain empty or Rerun-reserved path segments.")
    return prefix


def _as_json_payload(value: object, *, name: str) -> JSONDict:
    if hasattr(value, "to_dict"):
        value = value.to_dict()  # type: ignore[assignment, attr-defined]
    return require_json_dict(value, name=name)


def _pretty_json(payload: JSONDict) -> str:
    try:
        return json.dumps(payload, sort_keys=True, indent=2, allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise WorldForgeError(
            "Rerun payloads must be JSON serializable and contain only finite numbers."
        ) from exc


def _finite_float(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    number = float(value)
    if number != number or number in (float("inf"), float("-inf")):
        return None
    return number


def _position_xyz(value: object) -> list[float] | None:
    if not isinstance(value, dict):
        return None
    x = _finite_float(value.get("x"))
    y = _finite_float(value.get("y"))
    z = _finite_float(value.get("z"))
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
        number = _finite_float(item)
        if number is not None:
            scores.append(number)
    return scores


def _load_rerun_sdk(sdk: object | None) -> Any:
    if sdk is not None:
        return sdk
    try:
        return import_module("rerun")
    except ModuleNotFoundError as exc:
        raise WorldForgeError(
            "Rerun integration requires the optional 'rerun' extra. Install with "
            "`pip install 'worldforge-ai[rerun]'` or install `rerun-sdk` in the host "
            "environment."
        ) from exc


def _call_if_present(target: object, name: str, *args: object, **kwargs: object) -> object | None:
    method = getattr(target, name, None)
    if method is None:
        return None
    return method(*args, **kwargs)


def _text_log_level(rr: object, phase: str) -> object | None:
    levels = getattr(rr, "TextLogLevel", None)
    if levels is None:
        return None
    if phase == "failure":
        return getattr(levels, "ERROR", "ERROR")
    if phase == "retry":
        return getattr(levels, "WARN", "WARN")
    return getattr(levels, "INFO", "INFO")


@dataclass(slots=True)
class RerunRecordingConfig:
    """Configuration for the WorldForge Rerun recording.

    The integration keeps Rerun optional and host-owned. A config can stream to one Rerun sink:
    a local ``.rrd`` file, a spawned viewer, a remote gRPC viewer, or an in-process gRPC server.
    If no sink is selected, the SDK uses its normal buffered recording behavior.
    """

    application_id: str = "worldforge"
    recording_id: str | None = None
    recording_name: str | None = "WorldForge run"
    save_path: str | Path | None = None
    spawn_viewer: bool = False
    connect_url: str | None = None
    serve_grpc_port: int | None = None
    spawn_port: int = 9876
    viewer_memory_limit: str = "75%"
    server_memory_limit: str = "1GiB"
    hide_welcome_screen: bool = True
    detach_process: bool = True
    strict: bool | None = None
    default_enabled: bool = True
    init_logging: bool = True
    send_properties: bool = True

    def __post_init__(self) -> None:
        self.application_id = _require_text(self.application_id, name="application_id")
        if self.application_id.startswith("rerun_example_") or self.application_id.startswith("__"):
            raise WorldForgeError(
                "application_id must not use Rerun's example or reserved prefixes."
            )
        self.recording_id = _require_optional_text(self.recording_id, name="recording_id")
        self.recording_name = _require_optional_text(
            self.recording_name,
            name="recording_name",
        )
        if self.save_path is not None:
            self.save_path = Path(self.save_path)
        self.spawn_viewer = _require_bool(self.spawn_viewer, name="spawn_viewer")
        self.connect_url = _require_optional_text(self.connect_url, name="connect_url")
        if self.serve_grpc_port is not None:
            self.serve_grpc_port = _require_port(
                self.serve_grpc_port,
                name="serve_grpc_port",
            )
        self.spawn_port = _require_port(self.spawn_port, name="spawn_port")
        self.viewer_memory_limit = _require_text(
            self.viewer_memory_limit,
            name="viewer_memory_limit",
        )
        self.server_memory_limit = _require_text(
            self.server_memory_limit,
            name="server_memory_limit",
        )
        self.hide_welcome_screen = _require_bool(
            self.hide_welcome_screen,
            name="hide_welcome_screen",
        )
        self.detach_process = _require_bool(self.detach_process, name="detach_process")
        self.strict = _require_optional_bool(self.strict, name="strict")
        self.default_enabled = _require_bool(self.default_enabled, name="default_enabled")
        self.init_logging = _require_bool(self.init_logging, name="init_logging")
        self.send_properties = _require_bool(self.send_properties, name="send_properties")

        sink_count = sum(
            (
                self.save_path is not None,
                self.spawn_viewer,
                self.connect_url is not None,
                self.serve_grpc_port is not None,
            )
        )
        if sink_count > 1:
            raise WorldForgeError(
                "RerunRecordingConfig accepts at most one sink among save_path, spawn_viewer, "
                "connect_url, and serve_grpc_port."
            )


@dataclass(slots=True)
class RerunSession:
    """Lazy Rerun SDK session used by event sinks and artifact loggers."""

    config: RerunRecordingConfig = field(default_factory=RerunRecordingConfig)
    sdk: object | None = None
    _rr: object | None = field(default=None, init=False, repr=False)
    _started: bool = field(default=False, init=False, repr=False)
    _server_uri: str | None = field(default=None, init=False, repr=False)
    _lock: Lock = field(default_factory=Lock, init=False, repr=False)

    @property
    def server_uri(self) -> str | None:
        """Return the Rerun gRPC URI when ``serve_grpc_port`` is active."""

        return self._server_uri

    def start(self) -> RerunSession:
        """Initialize the SDK and attach the configured sink if needed."""

        with self._lock:
            if self._started:
                return self
            rr = _load_rerun_sdk(self.sdk)
            init_kwargs: dict[str, object] = {
                "spawn": False,
                "init_logging": self.config.init_logging,
                "default_enabled": self.config.default_enabled,
                "strict": self.config.strict,
                "send_properties": self.config.send_properties,
            }
            if self.config.recording_id is not None:
                init_kwargs["recording_id"] = self.config.recording_id
            rr.init(self.config.application_id, **init_kwargs)

            if self.config.save_path is not None:
                path = Path(self.config.save_path).expanduser()
                path.parent.mkdir(parents=True, exist_ok=True)
                rr.save(path)
            elif self.config.spawn_viewer:
                rr.spawn(
                    port=self.config.spawn_port,
                    connect=True,
                    memory_limit=self.config.viewer_memory_limit,
                    server_memory_limit=self.config.server_memory_limit,
                    hide_welcome_screen=self.config.hide_welcome_screen,
                    detach_process=self.config.detach_process,
                )
            elif self.config.connect_url is not None:
                rr.connect_grpc(self.config.connect_url)
            elif self.config.serve_grpc_port is not None:
                self._server_uri = rr.serve_grpc(
                    grpc_port=self.config.serve_grpc_port,
                    server_memory_limit=self.config.server_memory_limit,
                )

            if self.config.recording_name is not None:
                _call_if_present(rr, "send_recording_name", self.config.recording_name)
            self._rr = rr
            self._started = True
        return self

    @property
    def rr(self) -> Any:
        """Return the initialized Rerun SDK module."""

        return self.start()._rr

    def close(self) -> None:
        """Close Rerun sinks opened by this session."""

        with self._lock:
            if not self._started or self._rr is None:
                return
            _call_if_present(self._rr, "disconnect")
            self._started = False
            self._server_uri = None


@dataclass(slots=True)
class RerunEventSink:
    """ProviderEvent handler that logs WorldForge provider activity into Rerun."""

    session: RerunSession = field(default_factory=RerunSession)
    path_prefix: str = _DEFAULT_EVENT_PREFIX
    timeline: str = "worldforge_event"
    extra_fields: JSONDict = field(default_factory=dict)
    _sequence: int = field(default=0, init=False, repr=False)
    _lock: Lock = field(default_factory=Lock, init=False, repr=False)

    def __post_init__(self) -> None:
        self.path_prefix = _validate_path_prefix(self.path_prefix, name="path_prefix")
        self.timeline = _require_text(self.timeline, name="timeline")
        self.extra_fields = require_json_dict(self.extra_fields, name="extra_fields")

    def __call__(self, event: ProviderEvent) -> None:
        if not isinstance(event, ProviderEvent):
            raise WorldForgeError("RerunEventSink accepts only ProviderEvent instances.")
        with self._lock:
            sequence = self._sequence
            self._sequence += 1
        rr = self.session.rr
        rr.set_time(self.timeline, sequence=sequence)
        payload: JSONDict = {"event_type": "provider_event", **self.extra_fields, **event.to_dict()}
        event_path = _entity_path(
            self.path_prefix,
            event.provider,
            event.operation,
            event.phase,
        )
        message = event.message or f"{event.provider}.{event.operation} {event.phase}"
        self._log_text(rr, f"{event_path}/log", message, level=_text_log_level(rr, event.phase))
        self._log_json(rr, f"{event_path}/payload", payload)
        self._log_scalar(rr, f"{event_path}/attempt", float(event.attempt))
        self._log_scalar(rr, f"{event_path}/max_attempts", float(event.max_attempts))
        if event.duration_ms is not None:
            self._log_scalar(rr, f"{event_path}/duration_ms", event.duration_ms)
        if event.status_code is not None:
            self._log_scalar(rr, f"{event_path}/status_code", float(event.status_code))
        self._log_scalar(rr, f"{event_path}/failure", 1.0 if event.phase == "failure" else 0.0)
        self._log_scalar(rr, f"{event_path}/retry", 1.0 if event.phase == "retry" else 0.0)

    @staticmethod
    def _log_text(rr: object, entity_path: str, text: str, *, level: object | None) -> None:
        text_log = getattr(rr, "TextLog", None)
        if text_log is not None:
            if level is None:
                rr.log(entity_path, text_log(text))
            else:
                rr.log(entity_path, text_log(text, level=level))
            return
        text_document = getattr(rr, "TextDocument", None)
        if text_document is not None:
            rr.log(entity_path, text_document(text, media_type="text/plain"))

    @staticmethod
    def _log_json(rr: object, entity_path: str, payload: JSONDict) -> None:
        text_document = getattr(rr, "TextDocument", None)
        if text_document is not None:
            rr.log(entity_path, text_document(_pretty_json(payload), media_type="application/json"))
            return
        any_values = getattr(rr, "AnyValues", None)
        if any_values is not None:
            rr.log(entity_path, any_values(payload=dump_json(payload)))

    @staticmethod
    def _log_scalar(rr: object, entity_path: str, value: float) -> None:
        scalars = getattr(rr, "Scalars", None)
        if scalars is not None:
            rr.log(entity_path, scalars([value]))
            return
        scalar = getattr(rr, "Scalar", None)
        if scalar is not None:
            rr.log(entity_path, scalar(value))


@dataclass(slots=True)
class RerunArtifactLogger:
    """Log worlds, plans, benchmark reports, and JSON artifacts into Rerun."""

    session: RerunSession = field(default_factory=RerunSession)
    path_prefix: str = _DEFAULT_ARTIFACT_PREFIX
    world_timeline: str = "worldforge_step"
    plan_timeline: str = "worldforge_plan"
    benchmark_timeline: str = "worldforge_benchmark_result"
    robotics_timeline: str = "worldforge_robotics_showcase"
    workflow_timeline: str = "worldforge_workflow_trace"
    _plan_sequence: int = field(default=0, init=False, repr=False)
    _workflow_sequence: int = field(default=0, init=False, repr=False)
    _lock: Lock = field(default_factory=Lock, init=False, repr=False)

    def __post_init__(self) -> None:
        self.path_prefix = _validate_path_prefix(self.path_prefix, name="path_prefix")
        self.world_timeline = _require_text(self.world_timeline, name="world_timeline")
        self.plan_timeline = _require_text(self.plan_timeline, name="plan_timeline")
        self.benchmark_timeline = _require_text(
            self.benchmark_timeline,
            name="benchmark_timeline",
        )
        self.robotics_timeline = _require_text(
            self.robotics_timeline,
            name="robotics_timeline",
        )
        self.workflow_timeline = _require_text(
            self.workflow_timeline,
            name="workflow_timeline",
        )

    def log_world(self, world: object, *, label: str | None = None) -> None:
        """Log a WorldForge world snapshot as JSON plus 3D object markers."""

        state = _as_json_payload(world, name="world")
        world_id = _require_text(state.get("id"), name="world.id")
        world_step = state.get("step", 0)
        if isinstance(world_step, bool) or not isinstance(world_step, int) or world_step < 0:
            raise WorldForgeError("world.step must be a non-negative integer.")
        rr = self.session.rr
        rr.set_time(self.world_timeline, sequence=world_step)
        world_path = _entity_path(self.path_prefix, "worlds", world_id)
        self._log_json(rr, f"{world_path}/state", state)
        if label is not None:
            self._log_text(rr, f"{world_path}/label", label)

        objects = state.get("scene", {}).get("objects", {})
        if not isinstance(objects, dict):
            raise WorldForgeError("world.scene.objects must be a JSON object.")
        self._log_scalar(rr, f"{world_path}/object_count", float(len(objects)))
        positions: list[list[float]] = []
        labels: list[str] = []
        colors: list[list[int]] = []
        box_centers: list[list[float]] = []
        box_sizes: list[list[float]] = []
        box_labels: list[str] = []
        box_colors: list[list[int]] = []
        for object_id, item in objects.items():
            if not isinstance(item, dict):
                raise WorldForgeError("world.scene.objects entries must be JSON objects.")
            pose = item.get("pose", {})
            position = pose.get("position", {}) if isinstance(pose, dict) else {}
            if not isinstance(position, dict):
                continue
            try:
                x = float(position["x"])
                y = float(position["y"])
                z = float(position["z"])
            except (KeyError, TypeError, ValueError):
                continue
            positions.append([x, y, z])
            labels.append(str(item.get("name") or object_id))
            color = [52, 111, 235] if item.get("is_graspable") else [42, 170, 120]
            colors.append(color)
            bbox_geometry = _bbox_geometry(item.get("bbox"))
            if bbox_geometry is not None:
                center, size = bbox_geometry
                box_centers.append(center)
                box_sizes.append(size)
                box_labels.append(str(item.get("name") or object_id))
                box_colors.append(color)
            self._log_any_values(
                rr,
                f"{world_path}/objects/{_entity_segment(object_id)}",
                object_id=str(object_id),
                name=str(item.get("name") or object_id),
                x=x,
                y=y,
                z=z,
                is_graspable=bool(item.get("is_graspable", False)),
            )
        points = getattr(rr, "Points3D", None)
        if points is not None and positions:
            rr.log(
                f"{world_path}/objects",
                points(positions, labels=labels, colors=colors, radii=[0.04] * len(positions)),
            )
        boxes = getattr(rr, "Boxes3D", None)
        if boxes is not None and box_centers:
            rr.log(
                f"{world_path}/object_boxes",
                boxes(
                    centers=box_centers,
                    sizes=box_sizes,
                    labels=box_labels,
                    colors=box_colors,
                    radii=[0.002] * len(box_centers),
                ),
            )

    def log_plan(self, plan: object, *, label: str | None = None) -> None:
        """Log a WorldForge plan as JSON, metrics, and target waypoints."""

        payload = _as_json_payload(plan, name="plan")
        with self._lock:
            sequence = self._plan_sequence
            self._plan_sequence += 1
        rr = self.session.rr
        rr.set_time(self.plan_timeline, sequence=sequence)
        provider = payload.get("provider", "unknown")
        planner = payload.get("planner", "plan")
        plan_path = _entity_path(self.path_prefix, "plans", provider, planner, sequence)
        self._log_json(rr, f"{plan_path}/payload", payload)
        if label is not None:
            self._log_text(rr, f"{plan_path}/label", label)
        action_count = payload.get("action_count", len(payload.get("actions", [])))
        if isinstance(action_count, int) and not isinstance(action_count, bool):
            self._log_scalar(rr, f"{plan_path}/action_count", float(action_count))
        success_probability = payload.get("success_probability")
        if isinstance(success_probability, int | float) and not isinstance(
            success_probability,
            bool,
        ):
            self._log_scalar(rr, f"{plan_path}/success_probability", float(success_probability))
        self._log_action_targets(rr, plan_path, payload.get("actions", []))

    def log_benchmark_report(self, report: object) -> None:
        """Log a benchmark report as JSON plus per-result timeseries metrics."""

        payload = _as_json_payload(report, name="benchmark_report")
        rr = self.session.rr
        report_path = _entity_path(self.path_prefix, "benchmarks")
        self._log_json(rr, f"{report_path}/report", payload)
        results = payload.get("results", [])
        if not isinstance(results, list):
            raise WorldForgeError("benchmark_report.results must be a list.")
        for index, result in enumerate(results):
            if not isinstance(result, dict):
                raise WorldForgeError("benchmark_report.results entries must be JSON objects.")
            rr.set_time(self.benchmark_timeline, sequence=index)
            provider = result.get("provider", "provider")
            operation = result.get("operation", "operation")
            base_path = _entity_path(self.path_prefix, "benchmarks", provider, operation)
            self._log_json(rr, f"{base_path}/result", result)
            iterations = result.get("iterations")
            success_count = result.get("success_count")
            if (
                isinstance(iterations, int)
                and not isinstance(iterations, bool)
                and iterations > 0
                and isinstance(success_count, int)
                and not isinstance(success_count, bool)
            ):
                self._log_scalar(rr, f"{base_path}/success_rate", success_count / iterations)
            for metric in (
                "error_count",
                "retry_count",
                "average_latency_ms",
                "p50_latency_ms",
                "p95_latency_ms",
                "throughput_per_second",
            ):
                value = result.get(metric)
                if isinstance(value, int | float) and not isinstance(value, bool):
                    self._log_scalar(rr, f"{base_path}/{metric}", float(value))

    def log_json(self, entity_path: str, payload: JSONDict) -> None:
        """Log a validated JSON payload under ``path_prefix/entity_path``."""

        payload = require_json_dict(payload, name="payload")
        rr = self.session.rr
        self._log_json(rr, _entity_path(self.path_prefix, entity_path), payload)

    def log_workflow_trace(self, trace: object, *, label: str | None = None) -> None:
        """Log a workflow trace artifact as JSON plus per-step status markers."""

        payload = _as_json_payload(trace, name="workflow_trace")
        if payload.get("schema_version") != 1:
            raise WorldForgeError("workflow_trace schema_version must be 1.")
        workflow_id = _require_text(payload.get("workflow_id"), name="workflow_trace.workflow_id")
        steps = payload.get("steps", [])
        if not isinstance(steps, list):
            raise WorldForgeError("workflow_trace.steps must be a list.")
        with self._lock:
            sequence = self._workflow_sequence
            self._workflow_sequence += 1
        rr = self.session.rr
        rr.set_time(self.workflow_timeline, sequence=sequence)
        trace_path = _entity_path(self.path_prefix, "workflow_traces", workflow_id)
        self._log_json(rr, f"{trace_path}/payload", payload)
        if label is not None:
            self._log_text(rr, f"{trace_path}/label", label)
        self._log_scalar(rr, f"{trace_path}/step_count", float(len(steps)))
        for index, step in enumerate(steps):
            if not isinstance(step, dict):
                continue
            rr.set_time(self.workflow_timeline, sequence=index)
            step_path = _entity_path(trace_path, "steps", step.get("step_id", index))
            self._log_json(rr, f"{step_path}/payload", step)
            self._log_any_values(
                rr,
                f"{step_path}/summary",
                operation=step.get("operation", ""),
                provider=step.get("provider", ""),
                capability=step.get("capability", ""),
                status=step.get("status", ""),
                parent_id=step.get("parent_id", ""),
            )

    def log_robotics_showcase_summary(self, summary: JSONDict) -> None:
        """Log a robotics showcase summary as a visual Rerun inspection scene."""

        payload = require_json_dict(summary, name="robotics_showcase_summary")
        rr = self.session.rr
        rr.set_time(self.robotics_timeline, sequence=0)
        base_path = _entity_path(self.path_prefix, "robotics_showcase")
        self._log_json(rr, f"{base_path}/summary", payload)
        task = payload.get("task")
        if isinstance(task, str) and task.strip():
            self._log_text(rr, f"{base_path}/task", task)
        self._log_robotics_tabletop(rr, base_path, payload)
        self._log_robotics_score_landscape(rr, base_path, payload)
        rr.set_time(self.robotics_timeline, sequence=0)
        self._log_robotics_runtime_profile(rr, base_path, payload)

    @staticmethod
    def _log_json(rr: object, entity_path: str, payload: JSONDict) -> None:
        RerunEventSink._log_json(rr, entity_path, payload)

    @staticmethod
    def _log_scalar(rr: object, entity_path: str, value: float) -> None:
        RerunEventSink._log_scalar(rr, entity_path, value)

    @staticmethod
    def _log_text(rr: object, entity_path: str, text: str) -> None:
        RerunEventSink._log_text(rr, entity_path, text, level=None)

    @staticmethod
    def _log_any_values(rr: object, entity_path: str, **values: object) -> None:
        any_values = getattr(rr, "AnyValues", None)
        if any_values is not None:
            rr.log(entity_path, any_values(**values))

    @staticmethod
    def _log_robotics_tabletop(rr: object, base_path: str, payload: JSONDict) -> None:
        visualization = payload.get("visualization")
        if not isinstance(visualization, dict):
            return
        targets_payload = visualization.get("candidate_targets")
        if not isinstance(targets_payload, list):
            return
        score_result = payload.get("score_result")
        score_result = score_result if isinstance(score_result, dict) else {}
        selected_candidate = score_result.get("best_index", visualization.get("selected_candidate"))
        scores = _score_values(score_result.get("scores"))
        targets: list[tuple[int, list[float]]] = []
        for target in targets_payload:
            if not isinstance(target, dict):
                continue
            index = target.get("index")
            if isinstance(index, bool) or not isinstance(index, int):
                continue
            point = _position_xyz(target)
            if point is not None:
                targets.append((index, point))
        if not targets:
            return

        start = [0.0, 0.5, 0.0]
        goal = [0.5, 0.5, 0.0]
        selected_target = next(
            (point for index, point in targets if index == selected_candidate),
            None,
        )
        points = [start, goal, *(point for _index, point in targets)]
        labels = ["start", "goal"]
        colors = [[90, 90, 90], [42, 170, 120]]
        for index, _point in targets:
            score_text = f" cost={scores[index]:.3f}" if index < len(scores) else ""
            labels.append(f"candidate {index}{score_text}")
            colors.append([42, 170, 120] if index == selected_candidate else [235, 147, 52])

        execution = payload.get("execution")
        final_position = None
        if isinstance(execution, dict):
            final_position = _position_xyz(execution.get("final_block_position"))
        if final_position is not None:
            points.append(final_position)
            labels.append("mock final")
            colors.append([52, 111, 235])

        points3d = getattr(rr, "Points3D", None)
        if points3d is not None:
            rr.log(
                f"{base_path}/tabletop/points",
                points3d(points, labels=labels, colors=colors, radii=[0.035] * len(points)),
            )

        line_strips = getattr(rr, "LineStrips3D", None)
        if line_strips is not None:
            strips = [[start, point] for _index, point in targets]
            strip_colors = [
                [42, 170, 120] if index == selected_candidate else [235, 147, 52]
                for index, _point in targets
            ]
            radii = [0.01 if index == selected_candidate else 0.004 for index, _point in targets]
            rr.log(
                f"{base_path}/tabletop/candidate_paths",
                line_strips(
                    strips,
                    labels=[f"candidate {index}" for index, _point in targets],
                    colors=strip_colors,
                    radii=radii,
                ),
            )
            if final_position is not None:
                replay_strip = [start]
                if selected_target is not None:
                    replay_strip.append(selected_target)
                replay_strip.append(final_position)
                rr.log(
                    f"{base_path}/tabletop/selected_replay",
                    line_strips(
                        [replay_strip],
                        labels=["selected candidate replay"],
                        colors=[[52, 111, 235]],
                        radii=[0.012],
                    ),
                )

        arrows = getattr(rr, "Arrows3D", None)
        if arrows is not None and selected_target is not None:
            vector = [selected_target[index] - start[index] for index in range(3)]
            rr.log(
                f"{base_path}/tabletop/selected_vector",
                arrows(
                    origins=[start],
                    vectors=[vector],
                    labels=["selected action"],
                    colors=[[42, 170, 120]],
                    radii=[0.012],
                ),
            )

        boxes = getattr(rr, "Boxes3D", None)
        if boxes is not None:
            centers = [start]
            sizes = [[0.1, 0.1, 0.05]]
            box_labels = ["start block"]
            box_colors = [[90, 90, 90]]
            if final_position is not None:
                centers.append(final_position)
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

    @staticmethod
    def _log_robotics_score_landscape(rr: object, base_path: str, payload: JSONDict) -> None:
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
            RerunEventSink._log_scalar(rr, f"{base_path}/scores/candidate_cost", score)
        best_score = _finite_float(score_result.get("best_score"))
        if best_score is not None:
            RerunEventSink._log_scalar(rr, f"{base_path}/scores/best_cost", best_score)

    @staticmethod
    def _log_robotics_runtime_profile(rr: object, base_path: str, payload: JSONDict) -> None:
        rows: list[tuple[str, float]] = []
        events = payload.get("provider_events")
        if isinstance(events, list):
            for event in events:
                if not isinstance(event, dict):
                    continue
                provider = event.get("provider")
                operation = event.get("operation")
                duration = _finite_float(event.get("duration_ms"))
                if (
                    isinstance(provider, str)
                    and isinstance(operation, str)
                    and duration is not None
                ):
                    rows.append((f"{provider}.{operation}", duration))
        metrics = payload.get("metrics")
        if isinstance(metrics, dict):
            for key in ("plan_latency_ms", "total_latency_ms"):
                value = _finite_float(metrics.get(key))
                if value is not None:
                    rows.append((key, value))
        if not rows:
            return
        values = [value for _label, value in rows]
        bar_chart = getattr(rr, "BarChart", None)
        if bar_chart is not None:
            rr.log(f"{base_path}/runtime/latency_bars", bar_chart(values, color=[52, 111, 235]))
        RerunArtifactLogger._log_any_values(
            rr,
            f"{base_path}/runtime/latency_labels",
            labels=[label for label, _value in rows],
            values_ms=values,
        )

    @staticmethod
    def _log_action_targets(rr: object, plan_path: str, actions: object) -> None:
        if not isinstance(actions, list):
            return
        positions: list[list[float]] = []
        labels: list[str] = []
        for index, action in enumerate(actions):
            if not isinstance(action, dict):
                continue
            parameters = action.get("parameters", {})
            if not isinstance(parameters, dict):
                continue
            target = parameters.get("target")
            if not isinstance(target, dict):
                continue
            try:
                positions.append([float(target["x"]), float(target["y"]), float(target["z"])])
            except (KeyError, TypeError, ValueError):
                continue
            labels.append(f"{index}:{action.get('type', 'action')}")
        points = getattr(rr, "Points3D", None)
        if points is not None and positions:
            rr.log(
                f"{plan_path}/action_targets",
                points(
                    positions,
                    labels=labels,
                    colors=[[235, 147, 52]] * len(positions),
                    radii=[0.035] * len(positions),
                ),
            )


def create_rerun_event_handler(
    *,
    config: RerunRecordingConfig | None = None,
    session: RerunSession | None = None,
    path_prefix: str = _DEFAULT_EVENT_PREFIX,
    extra_fields: JSONDict | None = None,
) -> RerunEventSink:
    """Create a Rerun-backed ``ProviderEvent`` handler."""

    if config is not None and session is not None:
        raise WorldForgeError("Pass either config or session, not both.")
    resolved_session = session or RerunSession(config or RerunRecordingConfig())
    return RerunEventSink(
        session=resolved_session,
        path_prefix=path_prefix,
        extra_fields=dict(extra_fields or {}),
    )


__all__ = [
    "RerunArtifactLogger",
    "RerunEventSink",
    "RerunRecordingConfig",
    "RerunSession",
    "create_rerun_event_handler",
]

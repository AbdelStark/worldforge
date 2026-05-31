"""Optional Rerun integration for WorldForge observability and run artifacts."""

from __future__ import annotations

from dataclasses import dataclass, field
from importlib import import_module
from pathlib import Path
from threading import Lock
from typing import Any

from worldforge.models import JSONDict, ProviderEvent, WorldForgeError, dump_json, require_json_dict
from worldforge.rerun_artifacts import (
    log_action_targets as _log_action_targets,
)
from worldforge.rerun_artifacts import (
    log_benchmark_results as _log_benchmark_results,
)
from worldforge.rerun_artifacts import (
    log_rerun_any_values as _log_rerun_any_values,
)
from worldforge.rerun_artifacts import (
    log_robotics_runtime_profile as _log_robotics_runtime_profile,
)
from worldforge.rerun_artifacts import (
    log_robotics_score_landscape as _log_robotics_score_landscape,
)
from worldforge.rerun_artifacts import (
    log_robotics_tabletop as _log_robotics_tabletop,
)
from worldforge.rerun_artifacts import (
    log_world_visual_layers as _log_world_visual_layers,
)
from worldforge.rerun_artifacts import (
    world_scene_objects as _world_scene_objects,
)
from worldforge.rerun_artifacts import (
    world_step as _world_step,
)
from worldforge.rerun_paths import (
    entity_path as _entity_path,
)
from worldforge.rerun_paths import (
    validate_path_prefix as _validate_path_prefix,
)

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


def _as_json_payload(value: object, *, name: str) -> JSONDict:
    if hasattr(value, "to_dict"):
        value = value.to_dict()  # type: ignore[assignment, attr-defined]
    return require_json_dict(value, name=name)


def _pretty_json(payload: JSONDict) -> str:
    try:
        return dump_json(payload, indent=2)
    except WorldForgeError as exc:
        raise WorldForgeError(
            "Rerun payloads must be JSON serializable and contain only finite numbers."
        ) from exc


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
        world_step = _world_step(state)
        rr = self.session.rr
        rr.set_time(self.world_timeline, sequence=world_step)
        world_path = _entity_path(self.path_prefix, "worlds", world_id)
        self._log_json(rr, f"{world_path}/state", state)
        if label is not None:
            self._log_text(rr, f"{world_path}/label", label)

        objects = _world_scene_objects(state)
        self._log_scalar(rr, f"{world_path}/object_count", float(len(objects)))
        _log_world_visual_layers(rr, world_path, objects)

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
        _log_action_targets(rr, plan_path, payload.get("actions", []))

    def log_benchmark_report(self, report: object) -> None:
        """Log a benchmark report as JSON plus per-result timeseries metrics."""

        payload = _as_json_payload(report, name="benchmark_report")
        rr = self.session.rr
        report_path = _entity_path(self.path_prefix, "benchmarks")
        self._log_json(rr, f"{report_path}/report", payload)
        _log_benchmark_results(
            rr,
            self.path_prefix,
            self.benchmark_timeline,
            payload,
            log_json=self._log_json,
            log_scalar=self._log_scalar,
        )

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
            _log_rerun_any_values(
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
        _log_robotics_tabletop(rr, base_path, payload)
        _log_robotics_score_landscape(rr, base_path, payload, log_scalar=self._log_scalar)
        rr.set_time(self.robotics_timeline, sequence=0)
        _log_robotics_runtime_profile(rr, base_path, payload)

    @staticmethod
    def _log_json(rr: object, entity_path: str, payload: JSONDict) -> None:
        RerunEventSink._log_json(rr, entity_path, payload)

    @staticmethod
    def _log_scalar(rr: object, entity_path: str, value: float) -> None:
        RerunEventSink._log_scalar(rr, entity_path, value)

    @staticmethod
    def _log_text(rr: object, entity_path: str, text: str) -> None:
        RerunEventSink._log_text(rr, entity_path, text, level=None)


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

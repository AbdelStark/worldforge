from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

import worldforge.rerun as rerun_module
from worldforge import (
    Action,
    BBox,
    BenchmarkReport,
    BenchmarkResult,
    Position,
    ProviderEvent,
    SceneObject,
    StructuredGoal,
    WorldForge,
    WorldForgeError,
)
from worldforge.demos.rerun_showcase import run_demo
from worldforge.rerun import (
    RerunArtifactLogger,
    RerunEventSink,
    RerunRecordingConfig,
    RerunSession,
    create_rerun_event_handler,
)
from worldforge.workflow_trace import WorkflowTrace, WorkflowTraceStep


class _FakeRerun:
    TextLogLevel = SimpleNamespace(ERROR="ERROR", WARN="WARN", INFO="INFO")

    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple[Any, ...], dict[str, Any]]] = []
        self.logs: list[tuple[str, dict[str, Any]]] = []
        self.times: list[tuple[str, int]] = []

    def init(self, *args: Any, **kwargs: Any) -> None:
        self.calls.append(("init", args, kwargs))

    def save(self, *args: Any, **kwargs: Any) -> None:
        self.calls.append(("save", args, kwargs))

    def spawn(self, *args: Any, **kwargs: Any) -> None:
        self.calls.append(("spawn", args, kwargs))

    def connect_grpc(self, *args: Any, **kwargs: Any) -> None:
        self.calls.append(("connect_grpc", args, kwargs))

    def serve_grpc(self, *args: Any, **kwargs: Any) -> str:
        self.calls.append(("serve_grpc", args, kwargs))
        port = kwargs.get("grpc_port", 9876)
        return f"rerun+http://localhost:{port}/proxy"

    def send_recording_name(self, *args: Any, **kwargs: Any) -> None:
        self.calls.append(("send_recording_name", args, kwargs))

    def disconnect(self) -> None:
        self.calls.append(("disconnect", (), {}))

    def set_time(self, timeline: str, *, sequence: int) -> None:
        self.times.append((timeline, sequence))

    def log(self, entity_path: str, entity: dict[str, Any]) -> None:
        self.logs.append((entity_path, entity))

    def TextLog(self, text: str, *, level: object | None = None) -> dict[str, Any]:
        return {"kind": "TextLog", "text": text, "level": level}

    def TextDocument(
        self,
        text: str,
        *,
        media_type: str | None = None,
    ) -> dict[str, Any]:
        return {"kind": "TextDocument", "text": text, "media_type": media_type}

    def Scalar(self, scalar: float) -> dict[str, Any]:
        return {"kind": "Scalar", "scalar": scalar}

    def Scalars(self, scalars: object) -> dict[str, Any]:
        return {"kind": "Scalars", "scalars": scalars}

    def Points3D(self, positions: object, **kwargs: Any) -> dict[str, Any]:
        return {"kind": "Points3D", "positions": positions, **kwargs}

    def Boxes3D(self, **kwargs: Any) -> dict[str, Any]:
        return {"kind": "Boxes3D", **kwargs}

    def LineStrips3D(self, strips: object, **kwargs: Any) -> dict[str, Any]:
        return {"kind": "LineStrips3D", "strips": strips, **kwargs}

    def Arrows3D(self, **kwargs: Any) -> dict[str, Any]:
        return {"kind": "Arrows3D", **kwargs}

    def BarChart(self, values: object, **kwargs: Any) -> dict[str, Any]:
        return {"kind": "BarChart", "values": values, **kwargs}

    def AnyValues(self, **kwargs: Any) -> dict[str, Any]:
        return {"kind": "AnyValues", **kwargs}


def _fake_session(
    fake: _FakeRerun,
    *,
    save_path: Path | None = None,
) -> RerunSession:
    return RerunSession(
        config=RerunRecordingConfig(save_path=save_path, recording_name="test run"),
        sdk=fake,
    )


def test_rerun_recording_config_validates_sink_and_reserved_names(tmp_path: Path) -> None:
    with pytest.raises(WorldForgeError, match="at most one sink"):
        RerunRecordingConfig(save_path=tmp_path / "run.rrd", spawn_viewer=True)

    with pytest.raises(WorldForgeError, match="reserved"):
        RerunRecordingConfig(application_id="__worldforge")

    with pytest.raises(WorldForgeError, match="TCP port"):
        RerunRecordingConfig(spawn_viewer=True, spawn_port=70_000)


def test_rerun_session_supports_live_sink_modes_and_close_is_idempotent() -> None:
    cases = [
        (RerunRecordingConfig(spawn_viewer=True), "spawn"),
        (
            RerunRecordingConfig(connect_url="rerun+http://127.0.0.1:9876/proxy"),
            "connect_grpc",
        ),
        (RerunRecordingConfig(serve_grpc_port=9876), "serve_grpc"),
    ]

    for config, expected_call in cases:
        fake = _FakeRerun()
        session = RerunSession(config=config, sdk=fake)
        assert session.server_uri is None

        session.start()
        session.start()
        session.close()
        session.close()

        call_names = [call[0] for call in fake.calls]
        assert call_names.count("init") == 1
        assert expected_call in call_names
        assert call_names[-1] == "disconnect"


def test_rerun_session_initializes_enabled_recording_by_default(tmp_path: Path) -> None:
    fake = _FakeRerun()
    session = RerunSession(
        config=RerunRecordingConfig(save_path=tmp_path / "events.rrd"),
        sdk=fake,
    )

    session.start()

    assert fake.calls[0][0] == "init"
    assert fake.calls[0][2]["init_logging"] is True
    assert fake.calls[1][0] == "save"


def test_rerun_session_reports_missing_optional_sdk(monkeypatch: pytest.MonkeyPatch) -> None:
    def missing_import(_name: str) -> object:
        raise ModuleNotFoundError("rerun")

    monkeypatch.setattr(rerun_module, "import_module", missing_import)
    session = RerunSession(config=RerunRecordingConfig())

    with pytest.raises(WorldForgeError, match="optional 'rerun' extra"):
        session.start()


def test_rerun_event_sink_logs_sanitized_provider_event(tmp_path: Path) -> None:
    fake = _FakeRerun()
    session = _fake_session(fake, save_path=tmp_path / "events.rrd")
    sink = RerunEventSink(session=session, extra_fields={"run_id": "demo"})

    sink(
        ProviderEvent(
            provider="runway",
            operation="artifact download",
            phase="failure",
            duration_ms=12.5,
            target="https://downloads.example.com/out.mp4?token=secret",
            message="failed with api_key=secret",
            metadata={"signed_url": "https://downloads.example.com/out.mp4?signature=secret"},
        )
    )

    assert fake.calls[0][0] == "init"
    assert fake.calls[1][0] == "save"
    assert fake.times == [("worldforge_event", 0)]
    paths = [path for path, _entity in fake.logs]
    assert "worldforge/events/runway/artifact_download/failure/log" in paths
    assert "worldforge/events/runway/artifact_download/failure/duration_ms" in paths
    payload_text = next(
        entity["text"]
        for path, entity in fake.logs
        if path == "worldforge/events/runway/artifact_download/failure/payload"
    )
    assert "secret" not in payload_text
    assert "[redacted]" in payload_text
    assert '"run_id": "demo"' in payload_text


def test_rerun_event_sink_falls_back_to_any_values_when_text_documents_are_absent() -> None:
    fake = _FakeRerun()
    fake.TextLogLevel = None
    fake.TextLog = None
    fake.TextDocument = None
    sink = RerunEventSink(session=RerunSession(sdk=fake))

    sink(ProviderEvent(provider="mock", operation="predict", phase="success"))

    assert any(entity["kind"] == "AnyValues" for _path, entity in fake.logs)
    assert not any(path.endswith("/log") for path, _entity in fake.logs)


def test_rerun_artifact_logger_logs_world_plan_and_benchmark(tmp_path: Path) -> None:
    fake = _FakeRerun()
    session = _fake_session(fake)
    logger = RerunArtifactLogger(session=session)
    forge = WorldForge(state_dir=tmp_path, auto_register_remote=False)
    world = forge.create_world("rerun-test-world", provider="mock")
    cube = world.add_object(
        SceneObject(
            "blue_cube",
            Position(0.0, 0.5, 0.0),
            BBox(Position(-0.05, 0.45, -0.05), Position(0.05, 0.55, 0.05)),
        )
    )
    goal = StructuredGoal.object_at(
        object_id=cube.id,
        object_name=cube.name,
        position=Position(0.55, 0.5, 0.0),
    )
    plan = world.plan(goal_spec=goal, provider="mock")
    report = BenchmarkReport(
        [
            BenchmarkResult(
                provider="mock",
                operation="predict",
                iterations=2,
                concurrency=1,
                success_count=2,
                error_count=0,
                retry_count=0,
                total_time_ms=4.0,
                average_latency_ms=2.0,
                min_latency_ms=1.0,
                max_latency_ms=3.0,
                p50_latency_ms=2.0,
                p95_latency_ms=2.9,
                throughput_per_second=500.0,
            )
        ]
    )

    logger.log_world(world, label="initial")
    logger.log_plan(plan)
    logger.log_benchmark_report(report)

    assert any(entity["kind"] == "Points3D" for _path, entity in fake.logs)
    assert any(entity["kind"] == "Boxes3D" for _path, entity in fake.logs)
    assert any(path.endswith("/object_count") for path, _entity in fake.logs)
    assert any(path.endswith("/action_targets") for path, _entity in fake.logs)
    assert any(path.endswith("/success_rate") for path, _entity in fake.logs)
    assert ("worldforge_step", 0) in fake.times
    assert ("worldforge_plan", 0) in fake.times
    assert ("worldforge_benchmark_result", 0) in fake.times


def test_rerun_artifact_logger_logs_workflow_trace() -> None:
    fake = _FakeRerun()
    logger = RerunArtifactLogger(session=RerunSession(sdk=fake))
    trace = WorkflowTrace(
        workflow_id="demo-trace",
        name="Demo trace",
        steps=[
            WorkflowTraceStep(step_id="root", operation="demo workflow", status="success"),
            WorkflowTraceStep(
                step_id="score",
                parent_id="root",
                operation="score candidates",
                provider="leworldmodel",
                capability="score",
                status="success",
                duration_ms=12.0,
            ),
        ],
    )

    logger.log_workflow_trace(trace, label="demo")

    paths = [path for path, _entity in fake.logs]
    assert "worldforge/workflow_traces/demo-trace/payload" in paths
    assert "worldforge/workflow_traces/demo-trace/step_count" in paths
    assert "worldforge/workflow_traces/demo-trace/steps/score/payload" in paths
    assert any(entity["kind"] == "AnyValues" for _path, entity in fake.logs)
    assert ("worldforge_workflow_trace", 0) in fake.times


def test_rerun_artifact_logger_validates_payload_shapes() -> None:
    logger = RerunArtifactLogger(session=RerunSession(sdk=_FakeRerun()))

    with pytest.raises(WorldForgeError, match=r"world\.step"):
        logger.log_world({"id": "bad", "step": -1, "scene": {"objects": {}}})

    with pytest.raises(WorldForgeError, match=r"scene\.objects"):
        logger.log_world({"id": "bad", "step": 0, "scene": {"objects": []}})

    with pytest.raises(WorldForgeError, match=r"benchmark_report\.results"):
        logger.log_benchmark_report({"results": {}})


def test_rerun_artifact_logger_logs_arbitrary_json_payload() -> None:
    fake = _FakeRerun()
    logger = RerunArtifactLogger(session=RerunSession(sdk=fake))

    logger.log_json("diagnostics/doctor", {"healthy": True})

    assert any(path == "worldforge/diagnostics/doctor" for path, _entity in fake.logs)


def test_rerun_artifact_logger_logs_robotics_showcase_visual_layers() -> None:
    fake = _FakeRerun()
    logger = RerunArtifactLogger(session=RerunSession(sdk=fake))

    logger.log_robotics_showcase_summary(
        {
            "task": "PushT policy plus score planning",
            "score_result": {
                "best_index": 1,
                "best_score": 1.0,
                "scores": [3.0, 1.0],
            },
            "execution": {
                "final_block_position": {"x": 0.55, "y": 0.5, "z": 0.0},
            },
            "provider_events": [
                {
                    "provider": "lerobot",
                    "operation": "policy",
                    "phase": "success",
                    "duration_ms": 10.0,
                },
                {
                    "provider": "leworldmodel",
                    "operation": "score",
                    "phase": "success",
                    "duration_ms": 2.0,
                },
            ],
            "visualization": {
                "selected_candidate": 1,
                "candidate_targets": [
                    {"index": 0, "x": 0.2, "y": 0.5, "z": 0.0},
                    {"index": 1, "x": 0.55, "y": 0.5, "z": 0.0},
                ],
            },
            "metrics": {"plan_latency_ms": 12.0, "total_latency_ms": 20.0},
        }
    )

    logs_by_path = dict(fake.logs)
    assert "worldforge/robotics_showcase/tabletop/points" in logs_by_path
    assert "worldforge/robotics_showcase/tabletop/candidate_paths" in logs_by_path
    assert "worldforge/robotics_showcase/tabletop/selected_vector" in logs_by_path
    assert "worldforge/robotics_showcase/tabletop/block_boxes" in logs_by_path
    assert "worldforge/robotics_showcase/scores/cost_bars" in logs_by_path
    assert "worldforge/robotics_showcase/runtime/latency_bars" in logs_by_path
    assert logs_by_path["worldforge/robotics_showcase/scores/cost_bars"]["values"] == [
        3.0,
        1.0,
    ]
    assert ("worldforge_robotics_showcase", 0) in fake.times
    assert ("worldforge_candidate", 1) in fake.times


def test_rerun_path_prefix_rejects_reserved_segments() -> None:
    with pytest.raises(WorldForgeError, match="reserved"):
        RerunEventSink(session=RerunSession(sdk=_FakeRerun()), path_prefix="worldforge/__events")


def test_create_rerun_event_handler_rejects_ambiguous_session_and_config() -> None:
    with pytest.raises(WorldForgeError, match="either config or session"):
        create_rerun_event_handler(
            config=RerunRecordingConfig(),
            session=RerunSession(sdk=_FakeRerun()),
        )


def test_create_rerun_event_handler_builds_session_from_config(tmp_path: Path) -> None:
    handler = create_rerun_event_handler(
        config=RerunRecordingConfig(save_path=tmp_path / "events.rrd")
    )

    assert isinstance(handler, RerunEventSink)


def test_rerun_showcase_demo_logs_events_and_artifacts(tmp_path: Path) -> None:
    fake = _FakeRerun()

    summary = run_demo(
        state_dir=tmp_path,
        save_path=tmp_path / "showcase.rrd",
        iterations=1,
        rerun_module=fake,
    )

    assert summary["demo_kind"] == "rerun_observability_showcase"
    assert summary["rerun"]["save_path"].endswith("showcase.rrd")
    assert summary["rerun"]["recording_written"] is False
    assert summary["rerun"]["recording_size_bytes"] is None
    assert summary["plan"]["action_count"] == 1
    assert summary["benchmark"]["results"][0]["operation"] == "predict"
    assert any(path.startswith("worldforge/events/mock/predict") for path, _entity in fake.logs)
    assert any(path.startswith("worldforge/worlds/") for path, _entity in fake.logs)
    assert fake.calls[-1][0] == "disconnect"


def test_rerun_showcase_demo_uses_default_ignored_recording_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = _FakeRerun()
    monkeypatch.chdir(tmp_path)

    summary = run_demo(state_dir=tmp_path / "state", iterations=1, rerun_module=fake)

    assert summary["rerun"]["save_path"] == ".worldforge/rerun/worldforge-rerun-showcase.rrd"
    assert summary["rerun"]["recording_written"] is False
    assert any(call[0] == "save" for call in fake.calls)


def test_rerun_session_writes_real_rrd_file_when_sdk_available(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pytest.importorskip("rerun")
    monkeypatch.setenv("RERUN", "on")
    recording = tmp_path / "actual.rrd"
    session = RerunSession(
        config=RerunRecordingConfig(
            application_id="worldforge_test_rerun_recording",
            save_path=recording,
        )
    )
    logger = RerunArtifactLogger(session=session)

    logger.log_json("probe", {"ok": True})
    session.close()

    assert recording.is_file()
    assert recording.stat().st_size > 0


def test_rerun_event_sink_requires_provider_events() -> None:
    sink = RerunEventSink(session=RerunSession(sdk=_FakeRerun()))

    with pytest.raises(WorldForgeError, match="ProviderEvent"):
        sink(Action("noop"))  # type: ignore[arg-type]

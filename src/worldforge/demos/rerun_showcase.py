"""Rerun-backed WorldForge observability and artifact showcase."""

from __future__ import annotations

import argparse
import json
import tempfile
from pathlib import Path

from worldforge import Action, BenchmarkInputs, ProviderBenchmarkHarness, WorldForge
from worldforge.models import JSONDict, WorldForgeError
from worldforge.observability import ProviderMetricsSink, compose_event_handlers
from worldforge.rerun import (
    RerunArtifactLogger,
    RerunEventSink,
    RerunRecordingConfig,
    RerunSession,
)

from . import BLUE_CUBE_GOAL, blue_cube_goal, make_blue_cube


def _default_save_path() -> Path:
    return Path(".worldforge/rerun/worldforge-rerun-showcase.rrd")


def _make_config(
    *,
    save_path: Path | None,
    spawn: bool,
    connect_url: str | None,
    serve_grpc_port: int | None,
) -> RerunRecordingConfig:
    has_explicit_sink = any(
        (
            save_path is not None,
            spawn,
            connect_url is not None,
            serve_grpc_port is not None,
        )
    )
    return RerunRecordingConfig(
        recording_name="WorldForge Rerun showcase",
        save_path=save_path if has_explicit_sink else _default_save_path(),
        spawn_viewer=spawn,
        connect_url=connect_url,
        serve_grpc_port=serve_grpc_port,
    )


def _recording_file_status(path: str | Path | None) -> tuple[bool | None, int | None]:
    if path is None:
        return None, None
    resolved = Path(path).expanduser()
    if not resolved.is_file():
        return False, None
    return True, resolved.stat().st_size


def run_demo(
    *,
    state_dir: Path | None = None,
    save_path: Path | None = None,
    spawn: bool = False,
    connect_url: str | None = None,
    serve_grpc_port: int | None = None,
    iterations: int = 3,
    rerun_module: object | None = None,
) -> JSONDict:
    """Run a deterministic workflow and log it to Rerun."""

    resolved_state_dir = state_dir or Path(tempfile.mkdtemp(prefix="worldforge-rerun-demo-"))
    config = _make_config(
        save_path=save_path,
        spawn=spawn,
        connect_url=connect_url,
        serve_grpc_port=serve_grpc_port,
    )
    session = RerunSession(config=config, sdk=rerun_module)
    rerun_events = RerunEventSink(session=session)
    artifacts = RerunArtifactLogger(session=session)
    metrics = ProviderMetricsSink()
    forge = WorldForge(
        state_dir=resolved_state_dir,
        auto_register_remote=False,
        event_handler=compose_event_handlers(rerun_events, metrics),
    )

    world = forge.create_world("rerun-observability-showcase", provider="mock")
    cube = make_blue_cube(world)
    artifacts.log_world(world, label="initial tabletop scene")

    goal = blue_cube_goal(cube)
    plan = world.plan(goal_spec=goal, provider="mock")
    artifacts.log_plan(plan, label="predictive plan to the blue cube goal")
    execution = world.execute_plan(plan, provider="mock")
    final_world = execution.final_world()
    artifacts.log_world(final_world, label="executed plan result")

    benchmark_inputs = BenchmarkInputs(
        prediction_action=Action.move_to(
            BLUE_CUBE_GOAL.x,
            BLUE_CUBE_GOAL.y,
            BLUE_CUBE_GOAL.z,
        ),
        prediction_steps=1,
    )
    benchmark = ProviderBenchmarkHarness(forge=forge).run(
        "mock",
        operations=["predict"],
        iterations=iterations,
        inputs=benchmark_inputs,
    )
    artifacts.log_benchmark_report(benchmark)

    saved_world_id = forge.save_world(final_world)
    server_uri = session.server_uri
    session.close()
    recording_written, recording_size_bytes = _recording_file_status(config.save_path)
    if config.save_path is not None and rerun_module is None and not recording_written:
        raise WorldForgeError(
            "Rerun save_path was configured, but no .rrd recording was written. "
            "Check that the optional rerun-sdk runtime is enabled and that RERUN is not set to off."
        )
    summary: JSONDict = {
        "demo_kind": "rerun_observability_showcase",
        "state_dir": str(resolved_state_dir),
        "rerun": {
            "application_id": config.application_id,
            "recording_name": config.recording_name,
            "save_path": str(config.save_path) if config.save_path is not None else None,
            "spawn_viewer": config.spawn_viewer,
            "connect_url": config.connect_url,
            "serve_grpc_port": config.serve_grpc_port,
            "server_uri": server_uri,
            "recording_written": recording_written,
            "recording_size_bytes": recording_size_bytes,
        },
        "world_id": final_world.id,
        "saved_world_id": saved_world_id,
        "final_cube_position": final_world.get_object_by_id(cube.id).position.to_dict()
        if final_world.get_object_by_id(cube.id)
        else None,
        "plan": {
            "provider": plan.provider,
            "planner": plan.planner,
            "action_count": plan.action_count,
            "success_probability": plan.success_probability,
        },
        "provider_metrics": metrics.to_dict(),
        "benchmark": benchmark.to_dict(),
    }
    return summary


def _render_markdown(summary: JSONDict) -> str:
    rerun = summary["rerun"]
    plan = summary["plan"]
    recording = rerun.get("save_path") or rerun.get("server_uri") or "viewer"
    if rerun.get("save_path") is not None:
        if rerun.get("recording_written"):
            recording = f"{recording} ({rerun.get('recording_size_bytes')} bytes written)"
        else:
            recording = f"{recording} (not written)"
    return "\n".join(
        [
            "# WorldForge Rerun Showcase",
            "",
            f"- recording: {recording}",
            f"- state_dir: {summary['state_dir']}",
            f"- world_id: {summary['world_id']}",
            f"- plan: {plan['planner']} via {plan['provider']} ({plan['action_count']} action)",
            f"- success_probability: {plan['success_probability']:.3f}",
        ]
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run a deterministic WorldForge workflow and log it to Rerun.",
    )
    parser.add_argument(
        "--state-dir",
        type=Path,
        default=None,
        help="Directory for persisted demo worlds. Defaults to a temporary directory.",
    )
    parser.add_argument(
        "--save-path",
        type=Path,
        default=None,
        help=(
            "Write a Rerun .rrd recording. Defaults to "
            ".worldforge/rerun/worldforge-rerun-showcase.rrd when no live sink is selected."
        ),
    )
    parser.add_argument("--spawn", action="store_true", help="Spawn a local Rerun Viewer.")
    parser.add_argument("--connect-url", default=None, help="Connect to a remote Rerun Viewer.")
    parser.add_argument(
        "--serve-grpc-port",
        type=int,
        default=None,
        help="Serve an in-process Rerun gRPC stream on this port.",
    )
    parser.add_argument("--iterations", type=int, default=3, help="Benchmark iterations.")
    parser.add_argument(
        "--format",
        choices=("json", "markdown"),
        default="markdown",
        help="Summary output format.",
    )
    args = parser.parse_args()
    summary = run_demo(
        state_dir=args.state_dir,
        save_path=args.save_path,
        spawn=args.spawn,
        connect_url=args.connect_url,
        serve_grpc_port=args.serve_grpc_port,
        iterations=args.iterations,
    )
    if args.format == "json":
        print(json.dumps(summary, sort_keys=True, indent=2))
    else:
        print(_render_markdown(summary))


if __name__ == "__main__":
    main()

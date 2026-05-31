"""Observability helpers for the LeRobot plus LeWorldModel smoke runner."""

from __future__ import annotations

import argparse
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from worldforge.models import ProviderEvent


def event_dicts(events: Iterable[ProviderEvent]) -> list[dict[str, Any]]:
    """Serialize provider events into JSON-native payload rows."""

    return [event.to_dict() for event in events]


def has_rerun_sink(args: argparse.Namespace) -> bool:
    return any(
        (
            args.rerun_output is not None,
            args.rerun_spawn,
            args.rerun_connect_url is not None,
            args.rerun_serve_grpc_port is not None,
        )
    )


def recording_file_status(path: Path | None) -> tuple[bool | None, int | None]:
    if path is None:
        return None, None
    resolved = path.expanduser()
    if not resolved.is_file():
        return False, None
    return True, resolved.stat().st_size


def is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.expanduser().resolve().relative_to(root.expanduser().resolve())
    except ValueError:
        return False
    return True


def create_rerun_loggers(args: argparse.Namespace) -> tuple[object, object, object] | None:
    if not has_rerun_sink(args):
        return None
    from worldforge.rerun import (
        RerunArtifactLogger,
        RerunEventSink,
        RerunRecordingConfig,
        RerunSession,
    )

    session = RerunSession(
        RerunRecordingConfig(
            recording_name="WorldForge robotics showcase",
            save_path=args.rerun_output,
            spawn_viewer=args.rerun_spawn,
            connect_url=args.rerun_connect_url,
            serve_grpc_port=args.rerun_serve_grpc_port,
        )
    )
    return session, RerunEventSink(session=session), RerunArtifactLogger(session=session)


def rerun_payload(args: argparse.Namespace, session: object | None) -> dict[str, Any] | None:
    if not has_rerun_sink(args):
        return None
    return {
        "save_path": str(args.rerun_output) if args.rerun_output is not None else None,
        "spawn_viewer": args.rerun_spawn,
        "connect_url": args.rerun_connect_url,
        "serve_grpc_port": args.rerun_serve_grpc_port,
        "server_uri": getattr(session, "server_uri", None),
        "recording_written": None,
        "recording_size_bytes": None,
    }


def create_tensorboard_inspector(args: argparse.Namespace) -> object | None:
    if getattr(args, "tensorboard_logdir", None) is None:
        return None
    from worldforge.tensorboard import (
        TensorBoardCheckpointInspector,
        TensorBoardLogConfig,
        TensorBoardSession,
        default_run_name,
    )

    run_name = args.tensorboard_run_name or default_run_name("robotics-showcase")
    config = TensorBoardLogConfig(
        log_dir=args.tensorboard_logdir,
        run_name=run_name,
        flush_secs=args.tensorboard_flush_secs,
    )
    session = TensorBoardSession(config=config)
    return TensorBoardCheckpointInspector(session=session)


def tensorboard_payload(
    args: argparse.Namespace,
    inspector: object | None,
) -> dict[str, Any] | None:
    if getattr(args, "tensorboard_logdir", None) is None or inspector is None:
        return None
    log_dir = getattr(inspector, "log_dir", None)
    return {
        "log_dir": str(log_dir) if log_dir is not None else str(args.tensorboard_logdir),
        "run_name": args.tensorboard_run_name,
        "flush_secs": args.tensorboard_flush_secs,
        "events_written": None,
    }


def finish_tensorboard_recording(
    payload: dict[str, Any],
    inspector: object | None,
) -> None:
    if inspector is None:
        return
    log_dir = getattr(inspector, "log_dir", None)
    try:
        inspector.flush()  # type: ignore[attr-defined]
        inspector.close()  # type: ignore[attr-defined]
    except Exception:
        return
    tb_payload = payload.get("tensorboard")
    if not isinstance(tb_payload, dict):
        return
    if log_dir is None:
        return
    log_path = Path(str(log_dir))
    tb_payload.update(
        {
            "log_dir": str(log_path),
            "events_written": _tensorboard_events_written(log_path),
        }
    )


def _tensorboard_events_written(log_path: Path) -> bool:
    if not log_path.exists():
        return False
    return any(
        entry.is_file() and entry.stat().st_size > 0
        for entry in log_path.rglob("events.out.tfevents.*")
    )


def finish_rerun_recording(
    payload: dict[str, Any],
    args: argparse.Namespace,
    session: object,
) -> None:
    server_uri = getattr(session, "server_uri", None)
    session.close()  # type: ignore[attr-defined]
    rerun = payload.get("rerun")
    if not isinstance(rerun, dict):
        return
    recording_written, recording_size = recording_file_status(args.rerun_output)
    rerun.update(
        {
            "server_uri": server_uri,
            "recording_written": recording_written,
            "recording_size_bytes": recording_size,
        }
    )

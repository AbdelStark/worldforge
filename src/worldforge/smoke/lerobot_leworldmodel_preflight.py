"""Preflight reporting for the LeRobot plus LeWorldModel smoke runner."""

from __future__ import annotations

import argparse
import contextlib
import json
from time import perf_counter
from typing import Any

from worldforge.smoke.lerobot_leworldmodel_cli import RUNTIME_ENV_VARS
from worldforge.smoke.lerobot_leworldmodel_models import ProviderRuntime, RuntimeSettings
from worldforge.smoke.lerobot_leworldmodel_observability import (
    finish_rerun_recording,
    finish_tensorboard_recording,
    rerun_payload,
    tensorboard_payload,
)
from worldforge.smoke.lerobot_leworldmodel_report import _runtime_command
from worldforge.smoke.lerobot_leworldmodel_runtime import preflight_ok
from worldforge.smoke.run_manifest import build_run_manifest, write_run_manifest

from .leworldmodel_output import _display_path, _write_json_output


def build_preflight_payload(
    args: argparse.Namespace,
    *,
    bridge_summary: dict[str, Any] | None,
    settings: RuntimeSettings,
    runtime: ProviderRuntime,
    total_started: float,
    rerun_session: object | None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "mode": "real_lerobot_policy_plus_real_leworldmodel_score",
        "bridge": bridge_summary,
        "checkpoint": str(settings.object_path),
        "checkpoint_display": _display_path(settings.object_path),
        "checkpoint_exists": settings.checkpoint_exists,
        "health": {"lerobot": runtime.policy_health, "leworldmodel": runtime.score_health},
        "runtime_assets": settings.runtime_asset_refs,
        "metrics": {"total_latency_ms": (perf_counter() - total_started) * 1000},
    }
    rerun = rerun_payload(args, rerun_session)
    if rerun is not None:
        payload["rerun"] = rerun
    return payload


def write_preflight_artifacts(
    args: argparse.Namespace,
    payload: dict[str, Any],
    *,
    bridge_summary: dict[str, Any] | None,
    settings: RuntimeSettings,
    runtime: ProviderRuntime,
) -> None:
    if args.json_output is not None:
        _write_json_output(args.json_output, payload)
    if args.run_manifest is None:
        return
    json_artifacts = {"report_summary": args.json_output} if args.json_output is not None else {}
    write_run_manifest(
        args.run_manifest,
        build_run_manifest(
            run_id=args.run_manifest.parent.name,
            provider_profile="lerobot-leworldmodel",
            capability="policy+score",
            status="skipped" if args.health_only and preflight_ok(runtime, settings) else "failed",
            env_vars=RUNTIME_ENV_VARS,
            event_count=len(runtime.provider_events),
            input_summary={"bridge": bridge_summary} if bridge_summary is not None else {},
            result=payload,
            runtime_assets=settings.runtime_assets,
            artifact_paths=json_artifacts,
            artifact_root=args.run_manifest.parent,
        ),
    )


def finish_preflight_observability(
    args: argparse.Namespace,
    payload: dict[str, Any],
    *,
    rerun_session: object | None,
    rerun_artifacts: object | None,
    tensorboard_inspector: object | None,
) -> None:
    if rerun_artifacts is not None:
        rerun_artifacts.log_json("robotics_showcase/preflight", payload)  # type: ignore[attr-defined]
    if rerun_session is not None:
        finish_rerun_recording(payload, args, rerun_session)
    tensorboard = tensorboard_payload(args, tensorboard_inspector)
    if tensorboard is not None:
        payload["tensorboard"] = tensorboard
    if tensorboard_inspector is not None:
        with contextlib.suppress(Exception):
            tensorboard_inspector.log_json(  # type: ignore[attr-defined]
                "robotics_showcase/preflight", payload
            )
        finish_tensorboard_recording(payload, tensorboard_inspector)


def handle_preflight_exit(
    args: argparse.Namespace,
    *,
    bridge_summary: dict[str, Any] | None,
    settings: RuntimeSettings,
    runtime: ProviderRuntime,
    total_started: float,
    preflight_ok: bool,
    rerun_session: object | None,
    rerun_artifacts: object | None,
    tensorboard_inspector: object | None,
) -> int:
    payload = build_preflight_payload(
        args,
        bridge_summary=bridge_summary,
        settings=settings,
        runtime=runtime,
        total_started=total_started,
        rerun_session=rerun_session,
    )
    finish_preflight_observability(
        args,
        payload,
        rerun_session=rerun_session,
        rerun_artifacts=rerun_artifacts,
        tensorboard_inspector=tensorboard_inspector,
    )
    write_preflight_artifacts(
        args,
        payload,
        bridge_summary=bridge_summary,
        settings=settings,
        runtime=runtime,
    )
    if args.json_only:
        print(json.dumps(payload, indent=2, sort_keys=True))
    elif not preflight_ok:
        print("\nRuntime preflight failed. Run the complete uv-backed task with host inputs:")
        print(
            _runtime_command(
                checkpoint=settings.object_path,
                policy_path=args.policy_path,
                device=args.device,
            )
        )
    return 0 if preflight_ok else 1


_build_preflight_payload = build_preflight_payload
_write_preflight_artifacts = write_preflight_artifacts
_finish_preflight_observability = finish_preflight_observability
_handle_preflight_exit = handle_preflight_exit

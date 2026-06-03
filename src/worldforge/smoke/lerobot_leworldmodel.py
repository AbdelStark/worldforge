"""Run a real LeRobot policy plus real LeWorldModel scoring flow.

This is a host-owned robotics-builder smoke/showcase. It composes a real
LeRobot policy checkpoint with a real LeWorldModel object checkpoint through the
WorldForge capability surface: ``forge.select_actions`` proposes policy action
chunks, ``forge.score_actions`` ranks them as a cost oracle, and the lowest-cost
chunk is rolled forward with ``forge.predict`` (policy+score planning).

The runner deliberately does not own task preprocessing. For a meaningful run,
the LeRobot policy, observation, LeWorldModel score tensors, and candidate
action tensor bridge must all describe the same robotics task.
"""

from __future__ import annotations

import argparse
import contextlib
import json
import tempfile
from collections.abc import Callable, Sequence
from pathlib import Path
from time import perf_counter
from typing import Any

from worldforge import BBox, Position, SceneObject, WorldForge
from worldforge.demos import execute_plan_over_state, object_position, seed_world_state
from worldforge.providers import LeRobotPolicyProvider, LeWorldModelProvider
from worldforge.smoke import lerobot_leworldmodel_bridge as _bridge
from worldforge.smoke import lerobot_leworldmodel_cli as _cli
from worldforge.smoke import lerobot_leworldmodel_inputs as _inputs
from worldforge.smoke import lerobot_leworldmodel_observability as _observability
from worldforge.smoke import lerobot_leworldmodel_preflight as _preflight
from worldforge.smoke import lerobot_leworldmodel_report as _report
from worldforge.smoke import lerobot_leworldmodel_runtime as _runtime
from worldforge.smoke.lerobot_leworldmodel_models import (
    _ObservabilityHandles,
    _PlanningSurface,
    _PlanRun,
    _ProviderRuntime,
    _RuntimeSettings,
    _SmokePlan,
    _SmokePlanningResult,
    _SmokeRuntime,
    _SmokeSession,
    _SuccessPayload,
)
from worldforge.smoke.run_manifest import build_run_manifest, write_run_manifest

from .leworldmodel import (
    _resolve_checkpoint as _lewm_resolve_checkpoint,
)
from .leworldmodel_output import (
    _display_path,
    _use_color,
    _write_json_output,
)
from .leworldmodel_output import (
    _status_text as _lewm_status_text,
)
from .leworldmodel_tensors import _input_stats, _score_stats

# Compatibility aliases keep existing task hooks and private tests stable while
# the implementation lives in focused modules.
_resolve_checkpoint = _lewm_resolve_checkpoint
_status_text = _lewm_status_text
_DynamicCandidateBridge = _bridge._DynamicCandidateBridge
_coerce_action = _bridge._coerce_action
_coerce_action_candidates = _bridge._coerce_action_candidates
_ensure_nested_list = _bridge._ensure_nested_list
_input_shape_summary = _bridge._input_shape_summary
_input_shapes = _bridge._input_shapes
_materialize_candidate_payload = _bridge._materialize_candidate_payload
_nested_shape = _bridge._nested_shape
_normalize_action_candidate_tensor = _bridge._normalize_action_candidate_tensor
_numeric_leaf = _bridge._numeric_leaf
_score_bridge_config = _bridge._score_bridge_config
_shape_text = _bridge._shape_text
_shape_tuple = _bridge._shape_tuple
build_pusht_lewm_action_candidates = _bridge.build_pusht_lewm_action_candidates
translate_pusht_xy_actions = _bridge.translate_pusht_xy_actions

_array_to_runtime_value = _inputs._array_to_runtime_value
_json_object_from_file = _inputs._json_object_from_file
_load_callable = _inputs._load_callable
_load_json_file = _inputs._load_json_file
_load_policy_info = _inputs._load_policy_info
_load_score_info = _inputs._load_score_info
_load_static_action_candidates = _inputs._load_static_action_candidates
_module_from_path = _inputs._module_from_path

DEFAULT_DEVICE = _cli.DEFAULT_DEVICE
DEFAULT_LEROBOT_POLICY = _cli.DEFAULT_LEROBOT_POLICY
DEFAULT_LEWORLDMODEL_POLICY = _cli.DEFAULT_LEWORLDMODEL_POLICY
DEFAULT_MODE = _cli.DEFAULT_MODE
DEFAULT_TASK = _cli.DEFAULT_TASK
DEFAULT_TRANSLATOR = _cli.DEFAULT_TRANSLATOR
_RUNTIME_ENV_VARS = _cli.RUNTIME_ENV_VARS
_add_artifact_args = _cli.add_artifact_args
_add_candidate_bridge_args = _cli.add_candidate_bridge_args
_add_device_runtime_args = _cli.add_device_runtime_args
_add_lerobot_runtime_args = _cli.add_lerobot_runtime_args
_add_leworldmodel_runtime_args = _cli.add_leworldmodel_runtime_args
_add_output_control_args = _cli.add_output_control_args
_add_policy_input_args = _cli.add_policy_input_args
_add_rerun_args = _cli.add_rerun_args
_add_score_input_args = _cli.add_score_input_args
_add_task_args = _cli.add_task_args
_add_tensorboard_args = _cli.add_tensorboard_args
_apply_bridge_defaults = _cli.apply_bridge_defaults
_apply_bridge_input_defaults = _cli.apply_bridge_input_defaults
_apply_bridge_runtime_defaults = _cli.apply_bridge_runtime_defaults
_default_checkpoint = _cli.default_checkpoint
_default_lewm_policy = _cli.default_lewm_policy
_default_policy_path = _cli.default_policy_path
_default_stablewm_home = _cli.default_stablewm_home
_env_value = _cli._env_value
_missing_action_candidate_input = _cli.missing_action_candidate_input
_missing_score_info_input = _cli.missing_score_info_input
_require_bridge = _cli.require_bridge
_should_use_bridge_candidate_builder = _cli.should_use_bridge_candidate_builder
_should_use_bridge_observation = _cli.should_use_bridge_observation
_should_use_bridge_score_info = _cli.should_use_bridge_score_info
_validate_main_args = _cli.validate_main_args
_validate_planning_inputs_present = _cli.validate_planning_inputs_present
_validate_policy_path = _cli.validate_policy_path
_validate_positive_integer_options = _cli.validate_positive_integer_options


def _parser() -> argparse.ArgumentParser:
    return _cli.parser(description=__doc__)


_create_rerun_loggers = _observability.create_rerun_loggers
_create_tensorboard_inspector = _observability.create_tensorboard_inspector
_event_dicts = _observability.event_dicts
_finish_rerun_recording = _observability.finish_rerun_recording
_finish_tensorboard_recording = _observability.finish_tensorboard_recording
_has_rerun_sink = _observability.has_rerun_sink
_is_relative_to = _observability.is_relative_to
_recording_file_status = _observability.recording_file_status
_rerun_payload = _observability.rerun_payload
_tensorboard_payload = _observability.tensorboard_payload

_TABLETOP_GOAL = _report._TABLETOP_GOAL
_TABLETOP_REPLAY_HEIGHT = _report._TABLETOP_REPLAY_HEIGHT
_TABLETOP_REPLAY_WIDTH = _report._TABLETOP_REPLAY_WIDTH
_TABLETOP_START = _report._TABLETOP_START
_bar = _report._bar
_candidate_targets = _report._candidate_targets
_event_latency = _report._event_latency
_float_or_none = _report._float_or_none
_log_step = _report._log_step
_place_tabletop_marker = _report._place_tabletop_marker
_position_from_summary = _report._position_from_summary
_print_candidate_targets = _report._print_candidate_targets
_print_header = _report._print_header
_print_provider_events = _report._print_provider_events
_print_runtime_profile = _report._print_runtime_profile
_print_score_summary = _report._print_score_summary
_print_success_report = _report._print_success_report
_print_tabletop_replay = _report._print_tabletop_replay
_provider_latency_ms = _report._provider_latency_ms
_runtime_command = _report._runtime_command
_score_by_index = _report._score_by_index
_section = _report._section
_tabletop_cell_marker = _report._tabletop_cell_marker
_tabletop_replay_cells = _report._tabletop_replay_cells
_tabletop_replay_lines = _report._tabletop_replay_lines
_tabletop_replay_row = _report._tabletop_replay_row


_resolve_runtime_settings = _runtime.resolve_runtime_settings
_log_runtime_settings = _runtime.log_runtime_settings
_build_action_bridge = _runtime.build_action_bridge
_score_health_with_checkpoint_status = _runtime.score_health_with_checkpoint_status
_log_preflight_health = _runtime.log_preflight_health
_preflight_ok = _runtime.preflight_ok


def _create_provider_runtime(
    args: argparse.Namespace,
    settings: _RuntimeSettings,
    action_translator: Callable[..., Any],
    *,
    rerun_events: object | None,
    tensorboard_inspector: object | None,
) -> _ProviderRuntime:
    return _runtime.create_provider_runtime(
        args,
        settings=settings,
        action_translator=action_translator,
        rerun_events=rerun_events,
        tensorboard_inspector=tensorboard_inspector,
        policy_provider_factory=LeRobotPolicyProvider,
        score_provider_factory=LeWorldModelProvider,
    )


_build_preflight_payload = _preflight.build_preflight_payload
_write_preflight_artifacts = _preflight.write_preflight_artifacts
_finish_preflight_observability = _preflight.finish_preflight_observability
_handle_preflight_exit = _preflight.handle_preflight_exit


def _load_planning_inputs(
    args: argparse.Namespace,
    score_action_candidates: object | None,
    *,
    color: bool,
) -> tuple[dict[str, Any], dict[str, object], object]:
    if not args.json_only:
        _log_step(
            3,
            7,
            "Load task observation, score tensors, and bridge hooks",
            [
                (
                    "observation source",
                    args.policy_info_json or args.observation_json or args.observation_module,
                ),
                (
                    "score source",
                    args.score_info_json or args.score_info_npz or args.score_info_module,
                ),
                ("translator", args.translator),
                (
                    "candidate bridge",
                    args.candidate_builder
                    or args.action_candidates_json
                    or args.action_candidates_npz,
                ),
            ],
            color=color,
        )
    policy_info = _load_policy_info(args)
    score_info = _load_score_info(args)
    if score_action_candidates is None:
        raise SystemExit("internal error: missing score_action_candidates")
    return policy_info, score_info, score_action_candidates


def _create_planning_surface(
    args: argparse.Namespace,
    runtime: _ProviderRuntime,
    policy_info: dict[str, Any],
    *,
    rerun_artifacts: object | None,
) -> _PlanningSurface:
    state_dir = args.state_dir or Path(tempfile.mkdtemp(prefix="worldforge-real-robotics-"))
    forge = WorldForge(state_dir=state_dir, auto_register_remote=False)
    forge.register_provider(runtime.policy_provider)
    forge.register_provider(runtime.score_provider)
    block = SceneObject(
        "pusht-block",
        Position(0.0, 0.5, 0.0),
        BBox(Position(-0.05, 0.45, -0.05), Position(0.05, 0.55, 0.05)),
    )
    world_state = seed_world_state([block])
    policy_info.setdefault("score_bridge", {})
    if isinstance(policy_info["score_bridge"], dict):
        policy_info["score_bridge"].setdefault("object_id", block.id)
    if rerun_artifacts is not None:
        rerun_artifacts.log_json(  # type: ignore[attr-defined]
            "robotics_showcase/initial_world_state",
            world_state,
        )
    return _PlanningSurface(forge=forge, world_state=world_state, block=block)


def _log_planning_surface(*, color: bool, no_execute: bool) -> None:
    _log_step(
        4,
        7,
        "Create WorldForge robotics planning surface",
        [
            ("policy provider", "lerobot"),
            ("score provider", "leworldmodel"),
            ("planning mode", "policy+score"),
            ("execution provider", "mock" if not no_execute else "skipped"),
        ],
        color=color,
    )


def _run_policy_score_plan(
    args: argparse.Namespace,
    *,
    surface: _PlanningSurface,
    policy_info: dict[str, Any],
    score_info: dict[str, object],
    score_action_candidates: object,
    color: bool,
    rerun_artifacts: object | None,
) -> _PlanRun:
    if not args.json_only:
        _log_step(
            5,
            7,
            "Run LeRobot policy and LeWorldModel score planning",
            [
                (
                    "operation",
                    "forge.select_actions('lerobot') + forge.score_actions('leworldmodel')",
                ),
                ("goal", args.goal),
                ("dynamic bridge", bool(args.candidate_builder)),
            ],
            color=color,
        )
    plan_started = perf_counter()
    plan = _policy_score_plan(
        surface.forge,
        goal=args.goal,
        policy_info=policy_info,
        score_info=score_info,
        score_action_candidates=score_action_candidates,
    )
    plan_latency_ms = (perf_counter() - plan_started) * 1000
    score_result = plan.metadata["score_result"]
    policy_result = plan.metadata["policy_result"]
    if rerun_artifacts is not None:
        rerun_artifacts.log_plan(plan, label="LeRobot policy candidates ranked by LeWorldModel")  # type: ignore[attr-defined]
    execution_summary = _execute_or_skip_plan(
        args,
        surface=surface,
        plan=plan,
        color=color,
        rerun_artifacts=rerun_artifacts,
    )
    return _PlanRun(
        plan=plan,
        policy_result=policy_result,
        score_result=score_result,
        score_stats=_score_stats(score_result),
        execution_summary=execution_summary,
        plan_latency_ms=plan_latency_ms,
    )


def _policy_score_plan(
    forge: WorldForge,
    *,
    goal: str,
    policy_info: dict[str, Any],
    score_info: dict[str, object],
    score_action_candidates: object,
) -> _SmokePlan:
    """Select a policy action chunk and rank candidates with the score cost oracle.

    This is the capability-surface equivalent of the deleted ``World.plan(planning_mode=
    'policy+score')`` path: the LeRobot policy proposes candidate chunks, the LeWorldModel
    score provider ranks them as costs, and the lowest-cost chunk is selected.
    """

    policy_result = forge.select_actions("lerobot", info=policy_info)
    candidate_plans = policy_result.action_candidates
    if not candidate_plans:
        raise SystemExit("policy provider 'lerobot' returned no action candidates")
    score_result = forge.score_actions(
        "leworldmodel",
        info=score_info,
        action_candidates=score_action_candidates,
    )
    best_index = score_result.best_index
    if not 0 <= best_index < len(candidate_plans):
        raise SystemExit(
            f"score provider 'leworldmodel' best_index {best_index} is out of range "
            f"for {len(candidate_plans)} policy candidates"
        )
    selected_actions = list(candidate_plans[best_index])
    return _SmokePlan(
        provider="leworldmodel",
        actions=selected_actions,
        success_probability=1.0 - min(max(float(score_result.best_score), 0.0), 1.0),
        metadata={
            "planning_mode": "policy+score",
            "planner": "lerobot-leworldmodel-mpc",
            "policy_provider": "lerobot",
            "score_provider": "leworldmodel",
            "execution_provider": "mock",
            "goal": goal,
            "candidate_count": len(candidate_plans),
            "policy_result": policy_result.to_dict(),
            "score_result": score_result.to_dict(),
        },
    )


def _execute_or_skip_plan(
    args: argparse.Namespace,
    *,
    surface: _PlanningSurface,
    plan: Any,
    color: bool,
    rerun_artifacts: object | None,
) -> dict[str, Any] | None:
    if args.no_execute:
        if not args.json_only:
            _log_step(
                6,
                7,
                "Skip local mock execution",
                [("selected actions", len(plan.actions))],
                color=color,
            )
        return None
    if not args.json_only:
        _log_step(
            6,
            7,
            "Execute selected action chunk in local mock world state",
            [("selected actions", len(plan.actions)), ("execution provider", "mock")],
            color=color,
        )
    final_state = execute_plan_over_state(
        surface.forge,
        surface.world_state,
        list(plan.actions),
        provider="mock",
    )
    final_block_position = object_position(final_state, surface.block.id)
    execution_summary = {
        "actions_applied": len(plan.actions),
        "final_step": final_state.get("step"),
        "final_block_position": final_block_position,
    }
    if rerun_artifacts is not None:
        rerun_artifacts.log_json(  # type: ignore[attr-defined]
            "robotics_showcase/final_world_state",
            final_state,
        )
    return execution_summary


def _log_planning_metrics(
    *,
    plan_run: _PlanRun,
    runtime: _ProviderRuntime,
    total_latency_ms: float,
    color: bool,
) -> None:
    _log_step(
        7,
        7,
        "Rank action candidates and collect metrics",
        [
            ("candidate count", plan_run.plan.metadata.get("candidate_count")),
            ("best index", plan_run.score_result.get("best_index")),
            ("best score", plan_run.score_result.get("best_score")),
            (
                "policy latency ms",
                _event_latency(_event_dicts(runtime.provider_events), "lerobot", "policy"),
            ),
            ("plan latency ms", f"{plan_run.plan_latency_ms:.2f}"),
            ("total latency ms", f"{total_latency_ms:.2f}"),
        ],
        color=color,
    )


def _build_success_payload(
    args: argparse.Namespace,
    *,
    bridge_summary: dict[str, Any] | None,
    settings: _RuntimeSettings,
    runtime: _ProviderRuntime,
    surface: _PlanningSurface,
    plan_run: _PlanRun,
    score_info: dict[str, object],
    score_action_candidates: object,
    total_latency_ms: float,
) -> _SuccessPayload:
    score_shapes = _input_shape_summary(score_info, score_action_candidates)
    score_shape_values = _input_shapes(score_info, score_action_candidates)
    score_shape_payload = {
        label: list(shape) if shape is not None else None
        for label, shape in score_shape_values.items()
    }
    input_stats = _input_stats(score_shape_values)
    event_payload = _event_dicts(runtime.provider_events)
    payload = {
        "mode": "real_lerobot_policy_plus_real_leworldmodel_score",
        "task": args.task,
        "bridge": bridge_summary,
        "checkpoint": str(settings.object_path),
        "checkpoint_display": _display_path(settings.object_path),
        "state_dir": str(surface.forge.state_dir),
        "health": {"lerobot": runtime.policy_health, "leworldmodel": runtime.score_health},
        "runtime_assets": settings.runtime_asset_refs,
        "inputs": {
            "policy_path": args.policy_path,
            "policy_type": args.policy_type,
            "lerobot_device": settings.lerobot_device,
            "leworldmodel_policy": args.lewm_policy,
            "leworldmodel_device": settings.lewm_device,
            "score_shapes": score_shape_payload,
            **input_stats,
            "score_action_candidates_shape": list(_shape_tuple(score_action_candidates) or []),
        },
        "plan": plan_run.plan.to_dict(),
        "policy_result": plan_run.policy_result,
        "score_result": plan_run.score_result,
        "score_stats": plan_run.score_stats,
        "execution": plan_run.execution_summary,
        "provider_events": event_payload,
        "visualization": {
            "candidate_targets": _candidate_targets(plan_run.policy_result),
            "selected_candidate": plan_run.score_result.get("best_index"),
        },
        "metrics": {
            "plan_latency_ms": plan_run.plan_latency_ms,
            "total_latency_ms": total_latency_ms,
        },
    }
    return _SuccessPayload(
        payload=payload,
        score_shapes=score_shapes,
        input_stats=input_stats,
        event_payload=event_payload,
    )


def _finish_success_observability(
    args: argparse.Namespace,
    summary: _SuccessPayload,
    *,
    settings: _RuntimeSettings,
    rerun_session: object | None,
    rerun_artifacts: object | None,
    tensorboard_inspector: object | None,
) -> None:
    rerun_payload = _rerun_payload(args, rerun_session)
    if rerun_payload is not None:
        summary.payload["rerun"] = rerun_payload
    if rerun_artifacts is not None:
        rerun_artifacts.log_robotics_showcase_summary(summary.payload)  # type: ignore[attr-defined]
    if rerun_session is not None:
        _finish_rerun_recording(summary.payload, args, rerun_session)
    tensorboard_payload = _tensorboard_payload(args, tensorboard_inspector)
    if tensorboard_payload is not None:
        summary.payload["tensorboard"] = tensorboard_payload
    if tensorboard_inspector is None:
        return
    with contextlib.suppress(Exception):
        tensorboard_inspector.log_checkpoint_summary(  # type: ignore[attr-defined]
            {
                "checkpoint": str(settings.object_path),
                "output": str(settings.object_path),
                "policy": args.lewm_policy,
                "created": settings.checkpoint_exists,
            }
        )
        tensorboard_inspector.log_robotics_showcase_summary(summary.payload)  # type: ignore[attr-defined]
    _finish_tensorboard_recording(summary.payload, tensorboard_inspector)


def _write_success_artifacts(
    args: argparse.Namespace,
    summary: _SuccessPayload,
    *,
    bridge_summary: dict[str, Any] | None,
    settings: _RuntimeSettings,
    surface: _PlanningSurface,
    score_action_candidates: object,
    execution_summary: dict[str, Any] | None,
) -> tuple[Path | None, Path | None]:
    json_output_path = (
        _write_json_output(args.json_output, summary.payload) if args.json_output else None
    )
    run_manifest_path = None
    if args.run_manifest is None:
        return json_output_path, run_manifest_path

    artifact_paths: dict[str, Path | str] = {}
    if _is_relative_to(surface.forge.state_dir, args.run_manifest.parent):
        artifact_paths["worldforge_state"] = surface.forge.state_dir
    if json_output_path is not None:
        artifact_paths.update(
            {
                "policy_summary": json_output_path,
                "score_summary": json_output_path,
                "report_summary": json_output_path,
            }
        )
        if execution_summary is not None:
            artifact_paths["replay_summary"] = json_output_path
    input_fixture = args.policy_info_json or args.observation_json
    score_shapes = summary.payload["inputs"]["score_shapes"]
    runtime_assets = settings.runtime_assets
    run_manifest_path = write_run_manifest(
        args.run_manifest,
        build_run_manifest(
            run_id=args.run_manifest.parent.name,
            provider_profile="lerobot-leworldmodel",
            capability="policy+score",
            status="passed",
            env_vars=_RUNTIME_ENV_VARS,
            event_count=len(summary.event_payload),
            input_summary={
                "bridge": bridge_summary,
                "score_shapes": score_shapes,
                "score_action_candidates_shape": list(_shape_tuple(score_action_candidates) or []),
            },
            input_fixture=input_fixture,
            result=summary.payload,
            runtime_assets=runtime_assets,
            artifact_paths=artifact_paths,
            artifact_root=args.run_manifest.parent,
        ),
    )
    return json_output_path, run_manifest_path


def _start_smoke_session(argv: Sequence[str] | None) -> _SmokeSession:
    parser = _parser()
    args = parser.parse_args(argv)
    bridge_summary = _apply_bridge_defaults(args)
    _validate_main_args(parser, args)

    color_enabled = _use_color(args.color) and not args.json_only
    total_started = perf_counter()
    if not args.json_only:
        _print_header(color=color_enabled)
    return _SmokeSession(
        args=args,
        bridge_summary=bridge_summary,
        color_enabled=color_enabled,
        total_started=total_started,
        observability=_create_observability_handles(args),
    )


def _create_observability_handles(args: argparse.Namespace) -> _ObservabilityHandles:
    rerun_session: object | None = None
    rerun_events: object | None = None
    rerun_artifacts: object | None = None
    rerun_logging = _create_rerun_loggers(args)
    if rerun_logging is not None:
        rerun_session, rerun_events, rerun_artifacts = rerun_logging
    return _ObservabilityHandles(
        rerun_session=rerun_session,
        rerun_events=rerun_events,
        rerun_artifacts=rerun_artifacts,
        tensorboard_inspector=_create_tensorboard_inspector(args),
    )


def _prepare_smoke_runtime(session: _SmokeSession) -> _SmokeRuntime:
    args = session.args
    runtime_settings = _resolve_runtime_settings(args)
    if not args.json_only:
        _log_runtime_settings(args, runtime_settings, color=session.color_enabled)

    bridge, score_action_candidates = _build_action_bridge(args)
    provider_runtime = _create_provider_runtime(
        args,
        runtime_settings,
        bridge.translate,
        rerun_events=session.observability.rerun_events,
        tensorboard_inspector=session.observability.tensorboard_inspector,
    )
    if not args.json_only:
        _log_preflight_health(
            provider_runtime,
            runtime_settings,
            color=session.color_enabled,
        )
    return _SmokeRuntime(
        settings=runtime_settings,
        provider_runtime=provider_runtime,
        score_action_candidates=score_action_candidates,
        preflight_ok=_preflight_ok(provider_runtime, runtime_settings),
    )


def _handle_smoke_preflight_exit(session: _SmokeSession, runtime: _SmokeRuntime) -> int:
    return _handle_preflight_exit(
        session.args,
        bridge_summary=session.bridge_summary,
        settings=runtime.settings,
        runtime=runtime.provider_runtime,
        total_started=session.total_started,
        preflight_ok=runtime.preflight_ok,
        rerun_session=session.observability.rerun_session,
        rerun_artifacts=session.observability.rerun_artifacts,
        tensorboard_inspector=session.observability.tensorboard_inspector,
    )


def _run_smoke_planning(session: _SmokeSession, runtime: _SmokeRuntime) -> _SmokePlanningResult:
    args = session.args
    policy_info, score_info, score_action_candidates = _load_planning_inputs(
        args,
        runtime.score_action_candidates,
        color=session.color_enabled,
    )
    if not args.json_only:
        _log_planning_surface(color=session.color_enabled, no_execute=args.no_execute)
    surface = _create_planning_surface(
        args,
        runtime.provider_runtime,
        policy_info,
        rerun_artifacts=session.observability.rerun_artifacts,
    )
    plan_run = _run_policy_score_plan(
        args,
        surface=surface,
        policy_info=policy_info,
        score_info=score_info,
        score_action_candidates=score_action_candidates,
        color=session.color_enabled,
        rerun_artifacts=session.observability.rerun_artifacts,
    )

    total_latency_ms = (perf_counter() - session.total_started) * 1000
    if not args.json_only:
        _log_planning_metrics(
            plan_run=plan_run,
            runtime=runtime.provider_runtime,
            total_latency_ms=total_latency_ms,
            color=session.color_enabled,
        )
    return _SmokePlanningResult(
        surface=surface,
        plan_run=plan_run,
        score_info=score_info,
        score_action_candidates=score_action_candidates,
        total_latency_ms=total_latency_ms,
    )


def _finish_successful_smoke(
    session: _SmokeSession,
    runtime: _SmokeRuntime,
    planning: _SmokePlanningResult,
) -> int:
    args = session.args
    summary = _build_success_payload(
        args,
        bridge_summary=session.bridge_summary,
        settings=runtime.settings,
        runtime=runtime.provider_runtime,
        surface=planning.surface,
        plan_run=planning.plan_run,
        score_info=planning.score_info,
        score_action_candidates=planning.score_action_candidates,
        total_latency_ms=planning.total_latency_ms,
    )
    _finish_success_observability(
        args,
        summary,
        settings=runtime.settings,
        rerun_session=session.observability.rerun_session,
        rerun_artifacts=session.observability.rerun_artifacts,
        tensorboard_inspector=session.observability.tensorboard_inspector,
    )
    json_output_path, run_manifest_path = _write_success_artifacts(
        args,
        summary,
        bridge_summary=session.bridge_summary,
        settings=runtime.settings,
        surface=planning.surface,
        score_action_candidates=planning.score_action_candidates,
        execution_summary=planning.plan_run.execution_summary,
    )
    if args.json_only:
        print(json.dumps(summary.payload, indent=2, sort_keys=True))
        return 0

    _print_success_report(
        args,
        summary=summary,
        plan_run=planning.plan_run,
        total_latency_ms=planning.total_latency_ms,
        json_output_path=json_output_path,
        run_manifest_path=run_manifest_path,
        color=session.color_enabled,
    )
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    session = _start_smoke_session(argv)
    runtime = _prepare_smoke_runtime(session)
    if session.args.health_only or not runtime.preflight_ok:
        return _handle_smoke_preflight_exit(session, runtime)
    planning = _run_smoke_planning(session, runtime)
    return _finish_successful_smoke(session, runtime, planning)


if __name__ == "__main__":
    raise SystemExit(main())

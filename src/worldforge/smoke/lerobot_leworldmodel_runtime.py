"""Runtime setup for the LeRobot plus LeWorldModel smoke runner."""

from __future__ import annotations

import argparse
import contextlib
from collections.abc import Callable
from typing import Any

from worldforge.models import ProviderEvent
from worldforge.providers import LeRobotPolicyProvider, LeWorldModelProvider
from worldforge.smoke.lerobot_leworldmodel_bridge import _DynamicCandidateBridge
from worldforge.smoke.lerobot_leworldmodel_inputs import (
    _load_callable,
    _load_static_action_candidates,
)
from worldforge.smoke.lerobot_leworldmodel_models import ProviderRuntime, RuntimeSettings
from worldforge.smoke.lerobot_leworldmodel_report import _log_step
from worldforge.smoke.runtime_assets import lerobot_policy_asset, leworldmodel_checkpoint_asset

from .leworldmodel import _resolve_checkpoint
from .leworldmodel_output import _display_path, _status_text

ProviderFactory = Callable[..., Any]


def resolve_runtime_settings(args: argparse.Namespace) -> RuntimeSettings:
    object_path, lewm_cache_dir = _resolve_checkpoint(
        policy=args.lewm_policy,
        stablewm_home=args.stablewm_home,
        cache_dir=args.lewm_cache_dir,
        checkpoint=args.checkpoint,
        require_exists=not args.health_only,
    )
    checkpoint_exists = object_path.exists()
    runtime_assets = (
        lerobot_policy_asset(
            policy_path=args.policy_path,
            cache_root=args.lerobot_cache_dir,
        ),
        leworldmodel_checkpoint_asset(
            policy=args.lewm_policy,
            checkpoint=object_path,
            cache_root=lewm_cache_dir,
            exists=checkpoint_exists,
        ),
    )
    return RuntimeSettings(
        object_path=object_path,
        lewm_cache_dir=lewm_cache_dir,
        checkpoint_exists=checkpoint_exists,
        runtime_assets=runtime_assets,
        runtime_asset_refs=[asset.to_reference() for asset in runtime_assets],
        lerobot_device=args.lerobot_device or args.device,
        lewm_device=args.lewm_device or args.device,
    )


def log_runtime_settings(
    args: argparse.Namespace,
    settings: RuntimeSettings,
    *,
    color: bool,
) -> None:
    _log_step(
        1,
        7,
        "Resolve checkpoints and runtime settings",
        [
            ("task", "PushT policy+world-model planning"),
            ("LeRobot policy", args.policy_path),
            ("LeRobot device", settings.lerobot_device),
            ("LeWorldModel policy", args.lewm_policy),
            ("LeWorldModel checkpoint", _display_path(settings.object_path)),
            ("LeWorldModel cache", _display_path(settings.lewm_cache_dir)),
            ("LeWorldModel device", settings.lewm_device),
        ],
        color=color,
    )


def build_action_bridge(args: argparse.Namespace) -> tuple[_DynamicCandidateBridge, object | None]:
    translator = _load_callable(args.translator, name="translator")
    candidate_builder = (
        None
        if args.candidate_builder is None
        else _load_callable(args.candidate_builder, name="candidate builder")
    )
    score_action_candidates = (
        [] if candidate_builder is not None else _load_static_action_candidates(args)
    )
    bridge = _DynamicCandidateBridge(
        translator=translator,
        candidate_builder=candidate_builder,
        holder=score_action_candidates if isinstance(score_action_candidates, list) else [],
    )
    return bridge, score_action_candidates


def create_provider_runtime(
    args: argparse.Namespace,
    settings: RuntimeSettings,
    action_translator: Callable[..., Any],
    *,
    rerun_events: object | None,
    tensorboard_inspector: object | None,
    policy_provider_factory: ProviderFactory = LeRobotPolicyProvider,
    score_provider_factory: ProviderFactory = LeWorldModelProvider,
) -> ProviderRuntime:
    provider_events: list[ProviderEvent] = []

    def record_provider_event(event: ProviderEvent) -> None:
        provider_events.append(event)
        if rerun_events is not None:
            rerun_events(event)  # type: ignore[operator]
        if tensorboard_inspector is not None:
            with contextlib.suppress(Exception):
                tensorboard_inspector.log_provider_event(event)  # type: ignore[attr-defined]

    policy_provider = policy_provider_factory(
        policy_path=args.policy_path,
        policy_type=args.policy_type,
        device=settings.lerobot_device,
        cache_dir=args.lerobot_cache_dir,
        embodiment_tag=args.embodiment_tag,
        action_translator=action_translator,
        event_handler=record_provider_event,
    )
    score_provider = score_provider_factory(
        policy=args.lewm_policy,
        cache_dir=str(settings.lewm_cache_dir),
        device=settings.lewm_device,
        event_handler=record_provider_event,
    )
    policy_health = policy_provider.health().to_dict()
    score_health = score_health_with_checkpoint_status(
        score_provider.health().to_dict(),
        settings,
    )
    return ProviderRuntime(
        policy_provider=policy_provider,
        score_provider=score_provider,
        policy_health=policy_health,
        score_health=score_health,
        provider_events=provider_events,
    )


def score_health_with_checkpoint_status(
    score_health: dict[str, Any],
    settings: RuntimeSettings,
) -> dict[str, Any]:
    if settings.checkpoint_exists:
        return score_health
    updated = dict(score_health)
    checkpoint_details = (
        f"LeWorldModel object checkpoint not found: {_display_path(settings.object_path)}"
    )
    existing_details = updated.get("details")
    updated["healthy"] = False
    updated["details"] = (
        f"{existing_details}; {checkpoint_details}" if existing_details else checkpoint_details
    )
    return updated


def log_preflight_health(
    runtime: ProviderRuntime,
    settings: RuntimeSettings,
    *,
    color: bool,
) -> None:
    _log_step(
        2,
        7,
        "Preflight optional runtime dependencies",
        [
            (
                "LeRobot healthy",
                _status_text(runtime.policy_health.get("healthy"), color=color),
            ),
            ("LeRobot details", runtime.policy_health.get("details")),
            (
                "LeWorldModel healthy",
                _status_text(runtime.score_health.get("healthy"), color=color),
            ),
            ("LeWorldModel details", runtime.score_health.get("details")),
            (
                "LeWorldModel checkpoint",
                _status_text(settings.checkpoint_exists, color=color),
            ),
        ],
        color=color,
    )


def preflight_ok(runtime: ProviderRuntime, settings: RuntimeSettings) -> bool:
    return (
        bool(runtime.policy_health.get("healthy"))
        and bool(runtime.score_health.get("healthy"))
        and settings.checkpoint_exists
    )


_resolve_runtime_settings = resolve_runtime_settings
_log_runtime_settings = log_runtime_settings
_build_action_bridge = build_action_bridge
_create_provider_runtime = create_provider_runtime
_score_health_with_checkpoint_status = score_health_with_checkpoint_status
_log_preflight_health = log_preflight_health
_preflight_ok = preflight_ok

"""Typed run-state models for the LeRobot plus LeWorldModel smoke runner."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from worldforge import SceneObject, WorldForge
from worldforge.models import ProviderEvent
from worldforge.providers import LeRobotPolicyProvider, LeWorldModelProvider


@dataclass(slots=True, frozen=True)
class RuntimeSettings:
    object_path: Path
    lewm_cache_dir: Path
    checkpoint_exists: bool
    runtime_assets: tuple[object, ...]
    runtime_asset_refs: list[dict[str, Any]]
    lerobot_device: str
    lewm_device: str


@dataclass(slots=True)
class ProviderRuntime:
    policy_provider: LeRobotPolicyProvider
    score_provider: LeWorldModelProvider
    policy_health: dict[str, Any]
    score_health: dict[str, Any]
    provider_events: list[ProviderEvent]


@dataclass(slots=True)
class PlanningSurface:
    forge: WorldForge
    world_state: dict[str, Any]
    block: SceneObject


@dataclass(slots=True)
class SmokePlan:
    """Plain policy+score plan record built from the capability surface.

    Replaces the deleted symbolic ``Plan``: the smoke runner selects a candidate action chunk
    with ``forge.select_actions`` + ``forge.score_actions`` and records the result here so the
    report, metrics, and JSON payload have a stable serializable shape.
    """

    provider: str
    actions: list[Any]
    success_probability: float
    metadata: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "actions": [action.to_dict() for action in self.actions],
            "action_count": len(self.actions),
            "success_probability": self.success_probability,
            "metadata": dict(self.metadata),
        }


@dataclass(slots=True)
class PlanRun:
    plan: SmokePlan
    policy_result: dict[str, Any]
    score_result: dict[str, Any]
    score_stats: dict[str, Any]
    execution_summary: dict[str, Any] | None
    plan_latency_ms: float


@dataclass(slots=True)
class SuccessPayload:
    payload: dict[str, Any]
    score_shapes: dict[str, str]
    input_stats: dict[str, Any]
    event_payload: list[dict[str, Any]]


@dataclass(slots=True)
class ObservabilityHandles:
    rerun_session: object | None
    rerun_events: object | None
    rerun_artifacts: object | None
    tensorboard_inspector: object | None


@dataclass(slots=True)
class SmokeSession:
    args: argparse.Namespace
    bridge_summary: dict[str, Any] | None
    color_enabled: bool
    total_started: float
    observability: ObservabilityHandles


@dataclass(slots=True)
class SmokeRuntime:
    settings: RuntimeSettings
    provider_runtime: ProviderRuntime
    score_action_candidates: object
    preflight_ok: bool


@dataclass(slots=True)
class SmokePlanningResult:
    surface: PlanningSurface
    plan_run: PlanRun
    score_info: dict[str, object]
    score_action_candidates: object
    total_latency_ms: float


# Compatibility aliases for the original private names used by existing tests.
_RuntimeSettings = RuntimeSettings
_ProviderRuntime = ProviderRuntime
_PlanningSurface = PlanningSurface
_SmokePlan = SmokePlan
_PlanRun = PlanRun
_SuccessPayload = SuccessPayload
_ObservabilityHandles = ObservabilityHandles
_SmokeSession = SmokeSession
_SmokeRuntime = SmokeRuntime
_SmokePlanningResult = SmokePlanningResult

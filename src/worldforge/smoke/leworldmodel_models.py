"""Typed run-state models for the LeWorldModel smoke runner."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from worldforge.providers.runtime_manifest import RuntimeAssetManifest


@dataclass(frozen=True, slots=True)
class SmokeSettings:
    policy: str
    stablewm_home: Path
    cache_dir: Path | None
    checkpoint: Path | None
    device: str
    batch: int
    samples: int
    history: int
    horizon: int
    action_dim: int
    image_size: int
    seed: int | None
    json_output: Path | None
    run_manifest: Path | None
    json_only: bool
    color_enabled: bool


@dataclass(frozen=True, slots=True)
class ResolvedCheckpoint:
    object_path: Path
    cache_dir: Path
    runtime_assets: tuple[RuntimeAssetManifest, ...]
    runtime_asset_refs: list[dict[str, Any]]
    resolve_latency_ms: float


@dataclass(frozen=True, slots=True)
class TensorBatch:
    info: dict[str, object]
    action_candidates: object
    input_shapes: dict[str, str]
    input_shape_values: dict[str, tuple[int, ...] | None]
    input_stats: dict[str, Any]
    tensor_build_latency_ms: float


@dataclass(frozen=True, slots=True)
class ScoreRun:
    result_payload: dict[str, Any]
    score_stats: dict[str, Any]
    score_payload_summary: dict[str, Any]
    score_latency_ms: float
    total_latency_ms: float
    metrics: dict[str, Any]
    payload: dict[str, Any]


_SmokeSettings = SmokeSettings
_ResolvedCheckpoint = ResolvedCheckpoint
_TensorBatch = TensorBatch
_ScoreRun = ScoreRun

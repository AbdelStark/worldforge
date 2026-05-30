"""Run a LeWorldModel provider smoke test with a real checkpoint.

Invoke this command through uv, for example:

    uv run --python 3.13 --with "<git stable-worldmodel>" --with "datasets>=2.21"
      --with "opencv-python" --with "imageio"
      lewm-real --checkpoint ~/.stable-wm/pusht/lewm_object.ckpt

This smoke requires the upstream LeWorldModel runtime dependencies and an
extracted ``<policy>_object.ckpt`` under ``--stablewm-home`` or ``--cache-dir``.
Use the exact dependency command from the README. It is not part of
WorldForge's base dependency set.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from time import perf_counter
from typing import Any

from worldforge.providers import LeWorldModelProvider
from worldforge.smoke import leworldmodel_tensors as _tensors
from worldforge.smoke.leworldmodel_models import (
    _ResolvedCheckpoint,
    _ScoreRun,
    _SmokeSettings,
    _TensorBatch,
)
from worldforge.smoke.leworldmodel_output import (
    _display_path,
    _print_header,
    _print_preflight,
    _print_provider_setup,
    _print_resolved_runtime,
    _print_score_plan,
    _print_success_report,
    _print_tensor_plan,
    _print_tensor_summary,
    _runtime_command,
    _use_color,
    _write_json_output,
)
from worldforge.smoke.leworldmodel_output import (
    _paint as _paint,
)
from worldforge.smoke.leworldmodel_output import (
    _status_text as _status_text,
)
from worldforge.smoke.run_manifest import build_run_manifest, write_run_manifest
from worldforge.smoke.runtime_assets import leworldmodel_checkpoint_asset

DEFAULT_STABLEWM_HOME = "~/.stable-wm"


_shape_tuple = _tensors.shape_tuple
_input_shapes = _tensors.input_shapes
_input_shape_summary = _tensors.input_shape_summary
_input_stats = _tensors.input_stats
_score_stats = _tensors.score_stats
_score_payload_summary = _tensors.score_payload_summary
_score_chart = _tensors.score_chart


def _build_inputs(
    *,
    batch: int,
    samples: int,
    history: int,
    horizon: int,
    action_dim: int,
    image_size: int,
    seed: int | None = 7,
):
    if horizon <= history:
        raise SystemExit("horizon must be greater than history for LeWorldModel rollout.")
    import torch

    return _tensors.build_inputs(
        torch=torch,
        batch=batch,
        samples=samples,
        history=history,
        horizon=horizon,
        action_dim=action_dim,
        image_size=image_size,
        seed=seed,
    )


def _checkpoint_path(cache_dir: Path, policy: str) -> Path:
    return cache_dir / f"{policy}_object.ckpt"


def _infer_cache_dir_from_checkpoint(checkpoint: Path, policy: str) -> Path:
    suffix = Path(f"{policy}_object.ckpt")
    suffix_parts = suffix.parts
    checkpoint_parts = checkpoint.parts
    if (
        len(checkpoint_parts) <= len(suffix_parts)
        or tuple(checkpoint_parts[-len(suffix_parts) :]) != suffix_parts
    ):
        raise SystemExit(
            f"Checkpoint path {checkpoint} does not match policy '{policy}'. "
            f"Expected a path ending with {suffix}. Pass --cache-dir/--stablewm-home "
            "with a matching --policy, or adjust --policy to match the checkpoint layout."
        )
    return Path(*checkpoint_parts[: -len(suffix_parts)])


def _require_object_checkpoint(*, policy: str, cache_dir: Path) -> Path:
    object_path = _checkpoint_path(cache_dir, policy)
    if object_path.exists():
        return object_path

    raise SystemExit(
        f"LeWorldModel object checkpoint not found: {object_path}. "
        "Download the checkpoint archive from the upstream LeWorldModel README and extract it "
        "under STABLEWM_HOME so the policy resolves to <policy>_object.ckpt, or pass "
        "--cache-dir to the directory that contains the policy subdirectory."
    )


def _resolve_checkpoint(
    *,
    policy: str,
    stablewm_home: Path,
    cache_dir: Path | None,
    checkpoint: Path | None,
    require_exists: bool = True,
) -> tuple[Path, Path]:
    if checkpoint is None:
        resolved_cache_dir = (cache_dir or stablewm_home).expanduser()
        object_path = _checkpoint_path(resolved_cache_dir, policy)
        if require_exists and not object_path.exists():
            return _require_object_checkpoint(
                policy=policy, cache_dir=resolved_cache_dir
            ), resolved_cache_dir
        return object_path, resolved_cache_dir

    object_path = checkpoint.expanduser()
    if require_exists and not object_path.exists():
        raise SystemExit(f"LeWorldModel object checkpoint not found: {object_path}")

    inferred_cache_dir = _infer_cache_dir_from_checkpoint(object_path, policy)
    resolved_cache_dir = cache_dir.expanduser() if cache_dir is not None else inferred_cache_dir
    expected_path = _checkpoint_path(resolved_cache_dir, policy)
    if expected_path != object_path:
        raise SystemExit(
            f"Checkpoint path {object_path} does not match cache root {resolved_cache_dir} for "
            f"policy '{policy}'. Expected {expected_path}."
        )
    return object_path, resolved_cache_dir


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--policy", default=os.environ.get("LEWORLDMODEL_POLICY", "pusht/lewm"))
    parser.add_argument(
        "--stablewm-home",
        type=Path,
        default=Path(os.environ.get("STABLEWM_HOME", DEFAULT_STABLEWM_HOME)).expanduser(),
    )
    parser.add_argument(
        "--cache-dir",
        type=Path,
        default=None,
        help=("Checkpoint root passed to LeWorldModelProvider. Defaults to STABLEWM_HOME."),
    )
    parser.add_argument(
        "--checkpoint",
        type=Path,
        default=(
            Path(os.environ["LEWORLDMODEL_CHECKPOINT"]).expanduser()
            if os.environ.get("LEWORLDMODEL_CHECKPOINT")
            else None
        ),
        help=(
            "Exact <policy>_object.ckpt path. When provided, the cache root is inferred from "
            "the policy-shaped suffix unless --cache-dir is also supplied."
        ),
    )
    parser.add_argument("--device", default=os.environ.get("LEWORLDMODEL_DEVICE", "cpu"))
    parser.add_argument("--batch", type=int, default=1)
    parser.add_argument("--samples", type=int, default=3)
    parser.add_argument("--history", type=int, default=3)
    parser.add_argument("--horizon", type=int, default=4)
    parser.add_argument("--action-dim", type=int, default=10)
    parser.add_argument("--image-size", type=int, default=224)
    parser.add_argument(
        "--seed",
        type=int,
        default=7,
        help="Seed used for deterministic synthetic tensor construction. Use -1 to disable.",
    )
    parser.add_argument(
        "--json-output",
        type=Path,
        default=None,
        help="Write the full inference summary JSON to this path while keeping visual output.",
    )
    parser.add_argument(
        "--run-manifest",
        type=Path,
        default=None,
        help="Write a sanitized run_manifest.json evidence file for this live smoke.",
    )
    parser.add_argument(
        "--color",
        choices=("auto", "always", "never"),
        default="auto",
        help="Control ANSI colors in the human-readable output.",
    )
    parser.add_argument(
        "--no-color",
        action="store_const",
        const="never",
        dest="color",
        help="Disable ANSI colors in the human-readable output.",
    )
    parser.add_argument(
        "--json-only",
        action="store_true",
        help="Print only the machine-readable JSON summary.",
    )
    return parser


def _settings_from_args(
    parser: argparse.ArgumentParser,
    args: argparse.Namespace,
) -> _SmokeSettings:
    if args.seed < -1:
        parser.error("--seed must be -1 or a non-negative integer.")
    json_only = bool(args.json_only)
    return _SmokeSettings(
        policy=args.policy,
        stablewm_home=args.stablewm_home,
        cache_dir=args.cache_dir,
        checkpoint=args.checkpoint,
        device=args.device,
        batch=args.batch,
        samples=args.samples,
        history=args.history,
        horizon=args.horizon,
        action_dim=args.action_dim,
        image_size=args.image_size,
        seed=None if args.seed == -1 else args.seed,
        json_output=args.json_output,
        run_manifest=args.run_manifest,
        json_only=json_only,
        color_enabled=_use_color(args.color) and not json_only,
    )


def _resolve_runtime(settings: _SmokeSettings) -> _ResolvedCheckpoint:
    resolve_started = perf_counter()
    object_path, cache_dir = _resolve_checkpoint(
        policy=settings.policy,
        stablewm_home=settings.stablewm_home,
        cache_dir=settings.cache_dir,
        checkpoint=settings.checkpoint,
    )
    runtime_assets = (
        leworldmodel_checkpoint_asset(
            policy=settings.policy,
            checkpoint=object_path,
            cache_root=cache_dir,
            exists=object_path.exists(),
        ),
    )
    return _ResolvedCheckpoint(
        object_path=object_path,
        cache_dir=cache_dir,
        runtime_assets=runtime_assets,
        runtime_asset_refs=[asset.to_reference() for asset in runtime_assets],
        resolve_latency_ms=(perf_counter() - resolve_started) * 1000,
    )


def _record_provider_event(provider_events: list[dict[str, Any]]):
    def record(event: object) -> None:
        to_dict = getattr(event, "to_dict", None)
        if callable(to_dict):
            provider_events.append(to_dict())

    return record


def _create_provider(
    settings: _SmokeSettings,
    runtime: _ResolvedCheckpoint,
    provider_events: list[dict[str, Any]],
) -> LeWorldModelProvider:
    return LeWorldModelProvider(
        policy=settings.policy,
        cache_dir=str(runtime.cache_dir),
        device=settings.device,
        event_handler=_record_provider_event(provider_events),
    )


def _preflight_failure_payload(
    *,
    settings: _SmokeSettings,
    runtime: _ResolvedCheckpoint,
    health: dict[str, Any],
    total_started: float,
) -> dict[str, Any]:
    return {
        "checkpoint": str(runtime.object_path),
        "checkpoint_display": _display_path(runtime.object_path),
        "error": "runtime preflight failed",
        "health": health,
        "runtime_assets": runtime.runtime_asset_refs,
        "metrics": {
            "resolve_latency_ms": runtime.resolve_latency_ms,
            "preflight_latency_ms": health.get("latency_ms"),
            "total_latency_ms": (perf_counter() - total_started) * 1000,
        },
    }


def _write_smoke_outputs(
    *,
    settings: _SmokeSettings,
    runtime: _ResolvedCheckpoint,
    status: str,
    payload: dict[str, Any],
    provider_events: list[dict[str, Any]],
) -> tuple[Path | None, Path | None]:
    json_output_path = (
        _write_json_output(settings.json_output, payload)
        if settings.json_output is not None
        else None
    )
    if settings.run_manifest is None:
        return json_output_path, None
    run_manifest_path = write_run_manifest(
        settings.run_manifest,
        build_run_manifest(
            run_id=settings.run_manifest.parent.name,
            provider_profile="leworldmodel",
            capability="score",
            status=status,
            env_vars=("LEWORLDMODEL_CHECKPOINT", "LEWORLDMODEL_POLICY", "STABLEWM_HOME"),
            event_count=len(provider_events),
            result=payload,
            runtime_assets=runtime.runtime_assets,
            artifact_paths=(
                {"summary_json": json_output_path} if json_output_path is not None else {}
            ),
            artifact_root=settings.run_manifest.parent,
        ),
    )
    return json_output_path, run_manifest_path


def _handle_preflight_failure(
    *,
    settings: _SmokeSettings,
    runtime: _ResolvedCheckpoint,
    health: dict[str, Any],
    provider_events: list[dict[str, Any]],
    total_started: float,
) -> int:
    payload = _preflight_failure_payload(
        settings=settings,
        runtime=runtime,
        health=health,
        total_started=total_started,
    )
    _write_smoke_outputs(
        settings=settings,
        runtime=runtime,
        status="failed",
        payload=payload,
        provider_events=provider_events,
    )
    if settings.json_only:
        print(json.dumps(payload, indent=2, sort_keys=True))
        return 1
    print(
        "\nLeWorldModel runtime preflight failed: "
        f"{health.get('details')}\n\n"
        "Run the complete uv-backed task instead:\n"
        f"{_runtime_command(checkpoint=runtime.object_path, device=settings.device)}",
        flush=True,
    )
    return 1


def _build_tensor_batch(settings: _SmokeSettings) -> _TensorBatch:
    tensor_started = perf_counter()
    info, action_candidates = _build_inputs(
        batch=settings.batch,
        samples=settings.samples,
        history=settings.history,
        horizon=settings.horizon,
        action_dim=settings.action_dim,
        image_size=settings.image_size,
        seed=settings.seed,
    )
    input_shape_values = _input_shapes(info, action_candidates)
    return _TensorBatch(
        info=info,
        action_candidates=action_candidates,
        input_shapes=_input_shape_summary(info, action_candidates),
        input_shape_values=input_shape_values,
        input_stats=_input_stats(input_shape_values),
        tensor_build_latency_ms=(perf_counter() - tensor_started) * 1000,
    )


def _run_score_actions(
    *,
    settings: _SmokeSettings,
    runtime: _ResolvedCheckpoint,
    provider: LeWorldModelProvider,
    health: dict[str, Any],
    tensor_batch: _TensorBatch,
    provider_events: list[dict[str, Any]],
    total_started: float,
) -> _ScoreRun:
    started = perf_counter()
    result = provider.score_actions(
        info=tensor_batch.info,
        action_candidates=tensor_batch.action_candidates,
    )
    score_latency_ms = (perf_counter() - started) * 1000
    result_payload = result.to_dict()
    score_stats = _score_stats(result_payload)
    total_latency_ms = (perf_counter() - total_started) * 1000
    metrics = {
        "resolve_latency_ms": runtime.resolve_latency_ms,
        "preflight_latency_ms": health.get("latency_ms"),
        "tensor_build_latency_ms": tensor_batch.tensor_build_latency_ms,
        "score_latency_ms": score_latency_ms,
        "total_latency_ms": total_latency_ms,
        **score_stats,
    }
    payload = _success_payload(
        settings=settings,
        runtime=runtime,
        health=health,
        tensor_batch=tensor_batch,
        provider_events=provider_events,
        metrics=metrics,
        result_payload=result_payload,
    )
    return _ScoreRun(
        result_payload=result_payload,
        score_stats=score_stats,
        score_payload_summary=payload["score_payload_summary"],
        score_latency_ms=score_latency_ms,
        total_latency_ms=total_latency_ms,
        metrics=metrics,
        payload=payload,
    )


def _success_payload(
    *,
    settings: _SmokeSettings,
    runtime: _ResolvedCheckpoint,
    health: dict[str, Any],
    tensor_batch: _TensorBatch,
    provider_events: list[dict[str, Any]],
    metrics: dict[str, Any],
    result_payload: dict[str, Any],
) -> dict[str, Any]:
    return {
        "checkpoint": str(runtime.object_path),
        "checkpoint_display": _display_path(runtime.object_path),
        "health": health,
        "runtime_assets": runtime.runtime_asset_refs,
        "inputs": {
            "batch": settings.batch,
            "samples": settings.samples,
            "history": settings.history,
            "horizon": settings.horizon,
            "action_dim": settings.action_dim,
            "image_size": settings.image_size,
            "seed": settings.seed,
            "shapes": tensor_batch.input_shape_values,
            **tensor_batch.input_stats,
        },
        "metrics": metrics,
        "provider_events": provider_events,
        "result": result_payload,
        "score_payload_summary": _score_payload_summary(result_payload),
    }


def main() -> int:
    parser = _parser()
    settings = _settings_from_args(parser, parser.parse_args())
    total_started = perf_counter()
    if not settings.json_only:
        _print_header(color=settings.color_enabled)

    runtime = _resolve_runtime(settings)
    _print_resolved_runtime(settings, runtime)
    _print_provider_setup(settings)

    provider_events: list[dict[str, Any]] = []
    provider = _create_provider(settings, runtime, provider_events)
    health = provider.health().to_dict()
    _print_preflight(settings, health)
    if not health.get("healthy"):
        return _handle_preflight_failure(
            settings=settings,
            runtime=runtime,
            health=health,
            provider_events=provider_events,
            total_started=total_started,
        )

    _print_tensor_plan(settings)
    tensor_batch = _build_tensor_batch(settings)
    _print_tensor_summary(settings, tensor_batch)

    _print_score_plan(settings)
    score_run = _run_score_actions(
        settings=settings,
        runtime=runtime,
        provider=provider,
        health=health,
        tensor_batch=tensor_batch,
        provider_events=provider_events,
        total_started=total_started,
    )
    json_output_path, run_manifest_path = _write_smoke_outputs(
        settings=settings,
        runtime=runtime,
        status="passed",
        payload=score_run.payload,
        provider_events=provider_events,
    )
    if settings.json_only:
        print(json.dumps(score_run.payload, indent=2, sort_keys=True))
        return 0
    _print_success_report(
        settings=settings,
        score_run=score_run,
        provider_events=provider_events,
        json_output_path=json_output_path,
        run_manifest_path=run_manifest_path,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

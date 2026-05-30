"""Run a JEPA-WMS direct-construction provider smoke on a prepared host."""

from __future__ import annotations

import argparse
import importlib
import json
import sys
from collections.abc import Callable
from dataclasses import dataclass
from math import prod
from pathlib import Path
from statistics import mean, median
from time import perf_counter
from typing import Any

from worldforge.artifact_io import write_json_artifact
from worldforge.providers.jepa_wms import (
    DEFAULT_JEPA_WMS_HUB_REPO,
    JEPA_WMS_DEVICE_ENV_VAR,
    JEPA_WMS_ENV_VAR,
    JEPA_WMS_MODEL_NAME_ENV_VAR,
    JEPAWMSProvider,
)
from worldforge.smoke.run_manifest import build_run_manifest, write_run_manifest


@dataclass(frozen=True, slots=True)
class _SmokeSettings:
    model_name: str | None
    model_path: str | None
    hub_repo: str
    device: str | None
    batch: int
    samples: int
    history: int
    horizon: int
    action_dim: int
    image_size: int
    objective: str
    actions_are_normalized: bool
    seed: int | None
    json_output: Path | None
    run_manifest: Path | None
    json_only: bool


@dataclass(frozen=True, slots=True)
class _TensorBatch:
    info: dict[str, object]
    action_candidates: object
    input_shapes: dict[str, Any]
    input_stats: dict[str, Any]


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Score synthetic JEPA-WMS action candidates through an explicit host-owned "
            "torch-hub runtime."
        )
    )
    parser.add_argument(
        "--model-name",
        default=None,
        help=f"torch-hub model name. Defaults to {JEPA_WMS_MODEL_NAME_ENV_VAR}.",
    )
    parser.add_argument(
        "--model-path",
        default=None,
        help=f"WorldForge model path label. Defaults to --model-name or {JEPA_WMS_ENV_VAR}.",
    )
    parser.add_argument("--hub-repo", default=DEFAULT_JEPA_WMS_HUB_REPO)
    parser.add_argument(
        "--device",
        default=None,
        help=f"Runtime device. Defaults to {JEPA_WMS_DEVICE_ENV_VAR}, then upstream default.",
    )
    parser.add_argument("--batch", type=int, default=1)
    parser.add_argument("--samples", type=int, default=3)
    parser.add_argument("--history", type=int, default=3)
    parser.add_argument("--horizon", type=int, default=4)
    parser.add_argument("--action-dim", type=int, default=10)
    parser.add_argument("--image-size", type=int, default=64)
    parser.add_argument(
        "--objective",
        choices=("l1", "l2"),
        default="l2",
        help="Fallback latent distance objective when the model has no native scoring method.",
    )
    parser.add_argument(
        "--unnormalized-actions",
        action="store_false",
        dest="actions_are_normalized",
        help="Ask the loaded preprocessor to normalize action candidates before scoring.",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=7,
        help="Seed used for synthetic tensor construction. Use -1 to disable.",
    )
    parser.add_argument(
        "--json-output",
        type=Path,
        default=None,
        help="Write the full smoke summary JSON to this path.",
    )
    parser.add_argument(
        "--run-manifest",
        type=Path,
        default=None,
        help="Write a sanitized run_manifest.json evidence file for this prepared-host smoke.",
    )
    parser.add_argument(
        "--json-only",
        action="store_true",
        help="Print only the machine-readable JSON summary.",
    )
    return parser


def _require_positive_int(value: int, *, name: str) -> None:
    if value <= 0:
        raise SystemExit(f"{name} must be greater than zero.")


def _shape_tuple(value: object) -> tuple[int, ...] | None:
    shape = getattr(value, "shape", None)
    if shape is None:
        return None
    try:
        return tuple(int(part) for part in tuple(shape))
    except (TypeError, ValueError):
        return None


def _input_shapes(info: dict[str, object], action_candidates: object) -> dict[str, Any]:
    return {
        "observation": _shape_tuple(info["observation"]),
        "goal": _shape_tuple(info["goal"]),
        "action_history": _shape_tuple(info["action_history"]),
        "action_candidates": _shape_tuple(action_candidates),
    }


def _input_stats(shapes: dict[str, Any]) -> dict[str, Any]:
    tensor_elements = {
        label: prod(shape) for label, shape in shapes.items() if isinstance(shape, tuple) and shape
    }
    total_elements = sum(tensor_elements.values())
    return {
        "tensor_elements": tensor_elements,
        "total_tensor_elements": total_elements,
        "approx_float32_mb": round((total_elements * 4) / (1024 * 1024), 3),
    }


def _build_inputs(
    *,
    torch: Any,
    batch: int,
    samples: int,
    history: int,
    horizon: int,
    action_dim: int,
    image_size: int,
    seed: int | None,
) -> tuple[dict[str, object], object]:
    if seed is not None and hasattr(torch, "manual_seed"):
        torch.manual_seed(seed)
    info = {
        "observation": torch.rand(batch, history, 3, image_size, image_size),
        "goal": torch.rand(batch, history, 3, image_size, image_size),
        "action_history": torch.rand(batch, history, action_dim),
        "objective": "l2",
        "actions_are_normalized": True,
    }
    action_candidates = torch.rand(batch, samples, horizon, action_dim)
    return info, action_candidates


def _runtime_version(torch: Any, provider: JEPAWMSProvider) -> dict[str, Any]:
    runtime = getattr(provider, "_runtime", None)
    loaded_model = getattr(runtime, "_model", None)
    return {
        "torch": str(getattr(torch, "__version__", "unknown")),
        "hub_repo": getattr(runtime, "hub_repo", None),
        "model_name": getattr(runtime, "model_name", None),
        "device": getattr(runtime, "device", None),
        "model_class": type(loaded_model).__name__ if loaded_model is not None else None,
        "model_module": getattr(type(loaded_model), "__module__", None)
        if loaded_model is not None
        else None,
    }


def _score_stats(result: dict[str, Any]) -> dict[str, Any]:
    scores = [float(score) for score in result.get("scores", [])]
    if not scores:
        return {}
    lower_is_better = bool(result.get("lower_is_better", True))
    best_index = int(result.get("best_index", 0))
    ranked = sorted(enumerate(scores), key=lambda item: item[1], reverse=not lower_is_better)
    runner_up = ranked[1] if len(ranked) > 1 else None
    best_score = scores[best_index]
    return {
        "candidate_count": len(scores),
        "best_index": best_index,
        "best_score": best_score,
        "lower_is_better": lower_is_better,
        "score_min": min(scores),
        "score_max": max(scores),
        "score_mean": mean(scores),
        "score_median": median(scores),
        "score_range": max(scores) - min(scores),
        "runner_up_index": runner_up[0] if runner_up is not None else None,
        "runner_up_score": runner_up[1] if runner_up is not None else None,
    }


def _write_json(path: Path, payload: dict[str, Any]) -> Path:
    return write_json_artifact(path.expanduser(), payload)


def _print_summary(payload: dict[str, Any]) -> None:
    score = payload.get("score_summary", {})
    runtime = payload.get("runtime_version", {})
    print("JEPA-WMS prepared-host smoke passed.")
    print(f"  model              {runtime.get('model_name')}")
    print(f"  torch              {runtime.get('torch')}")
    print(f"  candidate count    {score.get('candidate_count')}")
    print(f"  best index         {score.get('best_index')}")
    print(f"  best score         {score.get('best_score')}")


def _settings_from_args(args: argparse.Namespace) -> _SmokeSettings:
    for field_name in ("batch", "samples", "history", "horizon", "action_dim", "image_size"):
        _require_positive_int(getattr(args, field_name), name=f"--{field_name.replace('_', '-')}")
    if args.seed < -1:
        raise SystemExit("--seed must be -1 or a non-negative integer.")
    return _SmokeSettings(
        model_name=args.model_name,
        model_path=args.model_path,
        hub_repo=args.hub_repo,
        device=args.device,
        batch=args.batch,
        samples=args.samples,
        history=args.history,
        horizon=args.horizon,
        action_dim=args.action_dim,
        image_size=args.image_size,
        objective=args.objective,
        actions_are_normalized=args.actions_are_normalized,
        seed=None if args.seed == -1 else args.seed,
        json_output=args.json_output,
        run_manifest=args.run_manifest,
        json_only=args.json_only,
    )


def _record_provider_event(provider_events: list[dict[str, Any]]) -> Callable[[object], None]:
    def record(event: object) -> None:
        to_dict = getattr(event, "to_dict", None)
        if callable(to_dict):
            provider_events.append(to_dict())

    return record


def _build_tensor_batch(settings: _SmokeSettings, *, torch: Any) -> _TensorBatch:
    info, action_candidates = _build_inputs(
        torch=torch,
        batch=settings.batch,
        samples=settings.samples,
        history=settings.history,
        horizon=settings.horizon,
        action_dim=settings.action_dim,
        image_size=settings.image_size,
        seed=settings.seed,
    )
    info["objective"] = settings.objective
    info["actions_are_normalized"] = settings.actions_are_normalized
    input_shapes = _input_shapes(info, action_candidates)
    return _TensorBatch(
        info=info,
        action_candidates=action_candidates,
        input_shapes=input_shapes,
        input_stats=_input_stats(input_shapes),
    )


def _create_provider(
    settings: _SmokeSettings,
    *,
    torch: Any,
    provider_events: list[dict[str, Any]],
) -> JEPAWMSProvider:
    return JEPAWMSProvider.from_torch_hub(
        model_name=settings.model_name,
        model_path=settings.model_path,
        hub_repo=settings.hub_repo,
        device=settings.device,
        torch_module=torch,
        event_handler=_record_provider_event(provider_events),
    )


def _success_payload(
    *,
    settings: _SmokeSettings,
    torch: Any,
    provider: JEPAWMSProvider,
    health: dict[str, Any],
    tensor_batch: _TensorBatch,
    provider_events: list[dict[str, Any]],
    result_payload: dict[str, Any],
    score_latency_ms: float,
    total_started: float,
) -> dict[str, Any]:
    return {
        "provider": "jepa-wms",
        "capability": "score",
        "health": health,
        "inputs": {
            "batch": settings.batch,
            "samples": settings.samples,
            "history": settings.history,
            "horizon": settings.horizon,
            "action_dim": settings.action_dim,
            "image_size": settings.image_size,
            "seed": settings.seed,
            "objective": settings.objective,
            "actions_are_normalized": settings.actions_are_normalized,
            "shapes": tensor_batch.input_shapes,
            **tensor_batch.input_stats,
        },
        "metrics": {
            "score_latency_ms": score_latency_ms,
            "total_latency_ms": (perf_counter() - total_started) * 1000,
        },
        "provider_events": provider_events,
        "result": result_payload,
        "runtime_version": _runtime_version(torch, provider),
        "score_summary": _score_stats(result_payload),
    }


def _run_smoke(
    *,
    settings: _SmokeSettings,
    provider_events: list[dict[str, Any]],
    total_started: float,
) -> dict[str, Any]:
    torch = importlib.import_module("torch")
    tensor_batch = _build_tensor_batch(settings, torch=torch)
    provider = _create_provider(settings, torch=torch, provider_events=provider_events)
    health = provider.health().to_dict()
    score_started = perf_counter()
    result = provider.score_actions(
        info=tensor_batch.info,
        action_candidates=tensor_batch.action_candidates,
    )
    score_latency_ms = (perf_counter() - score_started) * 1000
    result_payload = result.to_dict()
    return _success_payload(
        settings=settings,
        torch=torch,
        provider=provider,
        health=health,
        tensor_batch=tensor_batch,
        provider_events=provider_events,
        result_payload=result_payload,
        score_latency_ms=score_latency_ms,
        total_started=total_started,
    )


def _failure_payload(
    *,
    exc: Exception,
    provider_events: list[dict[str, Any]],
    total_started: float,
) -> dict[str, Any]:
    return {
        "provider": "jepa-wms",
        "capability": "score",
        "error": str(exc),
        "metrics": {"total_latency_ms": (perf_counter() - total_started) * 1000},
        "provider_events": provider_events,
    }


def _manifest_input_summary(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "inputs": payload.get("inputs", {}),
        "runtime_version": payload.get("runtime_version", {}),
        "score_summary": payload.get("score_summary", {}),
    }


def _write_smoke_outputs(
    *,
    settings: _SmokeSettings,
    status: str,
    payload: dict[str, Any],
    provider_events: list[dict[str, Any]],
) -> None:
    json_output_path = (
        _write_json(settings.json_output, payload) if settings.json_output is not None else None
    )
    if settings.run_manifest is not None:
        write_run_manifest(
            settings.run_manifest,
            build_run_manifest(
                run_id=settings.run_manifest.parent.name,
                provider_profile="jepa-wms",
                capability="score",
                status=status,
                env_vars=(JEPA_WMS_ENV_VAR, JEPA_WMS_MODEL_NAME_ENV_VAR, JEPA_WMS_DEVICE_ENV_VAR),
                event_count=len(provider_events),
                input_summary=_manifest_input_summary(payload),
                result=payload,
                artifact_paths=(
                    {"summary_json": json_output_path} if json_output_path is not None else {}
                ),
                artifact_root=settings.run_manifest.parent,
            ),
        )


def _print_result(*, settings: _SmokeSettings, status: str, payload: dict[str, Any]) -> None:
    if settings.json_only:
        print(json.dumps(payload, indent=2, sort_keys=True))
    elif status == "passed":
        _print_summary(payload)
    else:
        print(f"JEPA-WMS prepared-host smoke failed: {payload['error']}", file=sys.stderr)


def main() -> int:
    settings = _settings_from_args(_parser().parse_args())
    provider_events: list[dict[str, Any]] = []
    started = perf_counter()
    status = "passed"
    try:
        payload = _run_smoke(
            settings=settings,
            provider_events=provider_events,
            total_started=started,
        )
    except Exception as exc:
        status = "failed"
        payload = _failure_payload(
            exc=exc,
            provider_events=provider_events,
            total_started=started,
        )

    _write_smoke_outputs(
        settings=settings,
        status=status,
        payload=payload,
        provider_events=provider_events,
    )
    _print_result(settings=settings, status=status, payload=payload)
    return 0 if status == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())

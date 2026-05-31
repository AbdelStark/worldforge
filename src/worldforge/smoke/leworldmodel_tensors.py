"""Tensor construction and score summaries for LeWorldModel smoke runs."""

from __future__ import annotations

from math import prod
from statistics import mean, median
from typing import Any

ANSI_CODES = {
    "reset": "\033[0m",
    "bold": "\033[1m",
    "green": "\033[32m",
}


def build_inputs(
    *,
    torch: Any,
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

    if seed is not None and hasattr(torch, "manual_seed"):
        torch.manual_seed(seed)
    info = {
        "pixels": torch.rand(batch, 1, history, 3, image_size, image_size),
        "goal": torch.rand(batch, 1, history, 3, image_size, image_size),
        "action": torch.rand(batch, 1, history, action_dim),
    }
    action_candidates = torch.rand(batch, samples, horizon, action_dim)
    return info, action_candidates


def shape_tuple(value: object) -> tuple[int, ...] | None:
    shape = getattr(value, "shape", None)
    if shape is None and isinstance(value, dict):
        shape = value.get("shape")
    if shape is None:
        return None
    try:
        return tuple(int(part) for part in tuple(shape))
    except (TypeError, ValueError):
        return None


def input_shapes(
    info: dict[str, object],
    action_candidates: object,
) -> dict[str, tuple[int, ...] | None]:
    return {
        "pixels": shape_tuple(info["pixels"]),
        "goal": shape_tuple(info["goal"]),
        "action_history": shape_tuple(info["action"]),
        "action_candidates": shape_tuple(action_candidates),
    }


def input_shape_summary(info: dict[str, object], action_candidates: object) -> dict[str, str]:
    shapes = input_shapes(info, action_candidates)
    return {
        label: " x ".join(str(part) for part in shape) if shape is not None else "unknown"
        for label, shape in shapes.items()
    }


def input_stats(shapes: dict[str, tuple[int, ...] | None]) -> dict[str, Any]:
    tensor_elements = {label: prod(shape) for label, shape in shapes.items() if shape is not None}
    total_elements = sum(tensor_elements.values())
    return {
        "tensor_elements": tensor_elements,
        "total_tensor_elements": total_elements,
        "approx_float32_mb": round((total_elements * 4) / (1024 * 1024), 3),
    }


def score_stats(result: dict[str, Any]) -> dict[str, Any]:
    scores = [float(score) for score in result.get("scores", [])]
    if not scores:
        return {}
    lower_is_better = bool(result.get("lower_is_better", True))
    best_index = int(result.get("best_index", 0))
    ranked = sorted(enumerate(scores), key=lambda item: item[1], reverse=not lower_is_better)
    runner_up_index = ranked[1][0] if len(ranked) > 1 else None
    runner_up_score = ranked[1][1] if len(ranked) > 1 else None
    best_score = scores[best_index]
    gap = abs(float(runner_up_score) - best_score) if runner_up_score is not None else 0.0
    return {
        "score_min": min(scores),
        "score_max": max(scores),
        "score_mean": mean(scores),
        "score_median": median(scores),
        "score_range": max(scores) - min(scores),
        "runner_up_index": runner_up_index,
        "runner_up_score": runner_up_score,
        "gap_to_runner_up": gap,
    }


def score_payload_summary(result: dict[str, Any]) -> dict[str, Any]:
    metadata = result.get("metadata") if isinstance(result.get("metadata"), dict) else {}
    scores = result.get("scores") if isinstance(result.get("scores"), list) else []
    return {
        "candidate_count": metadata.get("candidate_count", len(scores)),
        "best_index": result.get("best_index"),
        "best_score": result.get("best_score"),
        "lower_is_better": result.get("lower_is_better"),
        "score_direction": metadata.get("score_direction", "lower_is_better"),
        "score_shape": metadata.get("score_shape"),
        "input_shapes": metadata.get("input_shapes"),
        "runtime_api": metadata.get("runtime_api"),
    }


def score_chart(result: dict[str, Any], *, color: bool = False) -> list[str]:
    scores = [float(score) for score in result.get("scores", [])]
    if not scores:
        return ["  no scores returned"]
    lower_is_better = bool(result.get("lower_is_better", True))
    best_index = int(result.get("best_index", 0))
    best_score = scores[best_index]
    ranked = sorted(enumerate(scores), key=lambda item: item[1], reverse=not lower_is_better)
    deltas = [
        (score - best_score) if lower_is_better else (best_score - score)
        for _index, score in ranked
    ]
    span = max(deltas) if deltas else 0.0
    width = 24
    delta_label = "extra cost" if lower_is_better else "below best"
    lines = [f"  {'rank':<4} {'candidate':<9} {'score':>12} {delta_label:>12}  landscape"]
    for rank, (index, score) in enumerate(ranked, start=1):
        delta = (score - best_score) if lower_is_better else (best_score - score)
        fill = 0 if span == 0 else round((delta / span) * width)
        bar = "#" * fill
        marker = "BEST" if index == best_index else ""
        marker = _paint(marker, "green", enabled=color, bold=True) if marker else ""
        lines.append(
            f"  {rank:<4} #{index:<8} {score:>12.6f} {delta:>+12.6f}  |{bar:<{width}}| {marker}"
        )
    return lines


def _paint(text: str, color: str, *, enabled: bool, bold: bool = False) -> str:
    if not enabled:
        return text
    codes = []
    if bold:
        codes.append(ANSI_CODES["bold"])
    codes.append(ANSI_CODES[color])
    return f"{''.join(codes)}{text}{ANSI_CODES['reset']}"


_build_inputs = build_inputs
_shape_tuple = shape_tuple
_input_shapes = input_shapes
_input_shape_summary = input_shape_summary
_input_stats = input_stats
_score_stats = score_stats
_score_payload_summary = score_payload_summary
_score_chart = score_chart

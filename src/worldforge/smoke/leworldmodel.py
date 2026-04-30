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
import sys
from math import prod
from pathlib import Path
from statistics import mean, median
from time import perf_counter
from typing import Any

from worldforge.providers import LeWorldModelProvider
from worldforge.smoke.run_manifest import build_run_manifest, write_run_manifest

DEFAULT_STABLEWM_HOME = "~/.stable-wm"
ANSI_CODES = {
    "reset": "\033[0m",
    "bold": "\033[1m",
    "red": "\033[31m",
    "green": "\033[32m",
    "yellow": "\033[33m",
    "blue": "\033[34m",
    "magenta": "\033[35m",
    "cyan": "\033[36m",
}


def _checkpoint_path(cache_dir: Path, policy: str) -> Path:
    return cache_dir / f"{policy}_object.ckpt"


def _display_path(path: Path) -> str:
    expanded = path.expanduser()
    try:
        relative = expanded.relative_to(Path.home())
    except ValueError:
        return str(expanded)
    if str(relative) == ".":
        return "~"
    return f"~/{relative.as_posix()}"


def _use_color(mode: str) -> bool:
    if mode == "always":
        return True
    if mode == "never" or os.environ.get("NO_COLOR"):
        return False
    return bool(sys.stdout.isatty()) and os.environ.get("TERM") != "dumb"


def _paint(text: str, color: str, *, enabled: bool, bold: bool = False) -> str:
    if not enabled:
        return text
    codes = []
    if bold:
        codes.append(ANSI_CODES["bold"])
    codes.append(ANSI_CODES[color])
    return f"{''.join(codes)}{text}{ANSI_CODES['reset']}"


def _status_text(value: object, *, color: bool) -> str:
    if value is True:
        return _paint("OK", "green", enabled=color, bold=True)
    if value is False:
        return _paint("FAIL", "red", enabled=color, bold=True)
    return str(value)


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

    if seed is not None and hasattr(torch, "manual_seed"):
        torch.manual_seed(seed)
    info = {
        "pixels": torch.rand(batch, 1, history, 3, image_size, image_size),
        "goal": torch.rand(batch, 1, history, 3, image_size, image_size),
        "action": torch.rand(batch, 1, history, action_dim),
    }
    action_candidates = torch.rand(batch, samples, horizon, action_dim)
    return info, action_candidates


def _shape_tuple(value: object) -> tuple[int, ...] | None:
    shape = getattr(value, "shape", None)
    if shape is None and isinstance(value, dict):
        shape = value.get("shape")
    if shape is None:
        return None
    try:
        return tuple(int(part) for part in tuple(shape))
    except (TypeError, ValueError):
        return None


def _input_shapes(
    info: dict[str, object], action_candidates: object
) -> dict[str, tuple[int, ...] | None]:
    return {
        "pixels": _shape_tuple(info["pixels"]),
        "goal": _shape_tuple(info["goal"]),
        "action_history": _shape_tuple(info["action"]),
        "action_candidates": _shape_tuple(action_candidates),
    }


def _input_shape_summary(info: dict[str, object], action_candidates: object) -> dict[str, str]:
    shapes = _input_shapes(info, action_candidates)
    return {
        label: " x ".join(str(part) for part in shape) if shape is not None else "unknown"
        for label, shape in shapes.items()
    }


def _input_stats(shapes: dict[str, tuple[int, ...] | None]) -> dict[str, Any]:
    tensor_elements = {label: prod(shape) for label, shape in shapes.items() if shape is not None}
    total_elements = sum(tensor_elements.values())
    return {
        "tensor_elements": tensor_elements,
        "total_tensor_elements": total_elements,
        "approx_float32_mb": round((total_elements * 4) / (1024 * 1024), 3),
    }


def _score_stats(result: dict[str, Any]) -> dict[str, Any]:
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


def _score_payload_summary(result: dict[str, Any]) -> dict[str, Any]:
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


def _score_chart(result: dict[str, Any], *, color: bool = False) -> list[str]:
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


def _log_step(
    index: int,
    total: int,
    title: str,
    rows: list[tuple[str, object]] | None = None,
    *,
    color: bool = False,
) -> None:
    print(f"\n{_paint(f'[{index}/{total}] {title}', 'cyan', enabled=color, bold=True)}", flush=True)
    for label, value in rows or []:
        print(f"  {label:<18} {value}", flush=True)


def _print_header(*, color: bool = False) -> None:
    print(
        _paint(
            "WorldForge LeWorldModel real checkpoint inference", "cyan", enabled=color, bold=True
        ),
        flush=True,
    )
    print("=" * 48, flush=True)
    print(
        "Mode: real upstream checkpoint inference, not the injected checkout-safe demo.", flush=True
    )
    print("\nWhat this demonstrates", flush=True)
    print("----------------------", flush=True)
    print("  - loads a host-owned LeWorldModel object checkpoint", flush=True)
    print("  - validates the WorldForge LeWorldModelProvider health boundary", flush=True)
    print("  - builds deterministic PushT-shaped tensor inputs", flush=True)
    print("  - runs score_actions through the real upstream cost model", flush=True)
    print("  - ranks action candidates using lower-is-better model costs", flush=True)
    print(
        "Boundary: inputs are synthetic tensors for the provider contract; this is not robot "
        "execution or task-specific image preprocessing.",
        flush=True,
    )
    print("\nPipeline", flush=True)
    print("--------", flush=True)
    print(
        "  checkpoint -> provider -> preflight -> tensors -> real score_actions -> ranking",
        flush=True,
    )


def _runtime_command(*, checkpoint: Path, device: str) -> str:
    checkpoint_text = _display_path(checkpoint)
    return (
        f"scripts/lewm-real --checkpoint {checkpoint_text} --device {device}\n"
        "\n"
        "or, without the wrapper:\n"
        'uv run --python 3.13 --with "stable-worldmodel @ '
        'git+https://github.com/galilai-group/stable-worldmodel.git" '
        '--with "datasets>=2.21" --with "opencv-python" --with "imageio" '
        f"lewm-real --checkpoint {checkpoint_text} --device {device}"
    )


def _write_json_output(path: Path, payload: dict[str, Any]) -> Path:
    output_path = path.expanduser()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return output_path


def _print_score_stats(stats: dict[str, Any]) -> None:
    if not stats:
        return
    print("\nInference metrics", flush=True)
    print("-----------------", flush=True)
    rows = [
        ("score min", f"{float(stats['score_min']):.6f}"),
        ("score median", f"{float(stats['score_median']):.6f}"),
        ("score mean", f"{float(stats['score_mean']):.6f}"),
        ("score max", f"{float(stats['score_max']):.6f}"),
        ("score range", f"{float(stats['score_range']):.6f}"),
        ("gap to runner-up", f"{float(stats['gap_to_runner_up']):.6f}"),
    ]
    for label, value in rows:
        print(f"  {label:<18} {value}", flush=True)


def _print_provider_events(events: list[dict[str, Any]]) -> None:
    print("\nProvider event log", flush=True)
    print("------------------", flush=True)
    if not events:
        print("  no provider events emitted", flush=True)
        return
    for event in events:
        duration = event.get("duration_ms")
        duration_text = f"{float(duration):.2f} ms" if duration is not None else "n/a"
        metadata = event.get("metadata") if isinstance(event.get("metadata"), dict) else {}
        metadata_text = " ".join(
            f"{key}={value}" for key, value in sorted(metadata.items()) if value is not None
        )
        print(
            f"  {event.get('provider')}.{event.get('operation')} "
            f"{event.get('phase')} duration={duration_text} {metadata_text}".rstrip(),
            flush=True,
        )


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


def main() -> int:
    parser = _parser()
    args = parser.parse_args()
    if args.seed < -1:
        parser.error("--seed must be -1 or a non-negative integer.")
    seed = None if args.seed == -1 else args.seed
    color_enabled = _use_color(args.color) and not args.json_only
    total_started = perf_counter()
    if not args.json_only:
        _print_header(color=color_enabled)

    resolve_started = perf_counter()
    object_path, cache_dir = _resolve_checkpoint(
        policy=args.policy,
        stablewm_home=args.stablewm_home,
        cache_dir=args.cache_dir,
        checkpoint=args.checkpoint,
    )
    resolve_latency_ms = (perf_counter() - resolve_started) * 1000
    if not args.json_only:
        _log_step(
            1,
            6,
            "Resolve checkpoint and runtime settings",
            [
                ("policy", args.policy),
                ("checkpoint", _display_path(object_path)),
                ("cache root", _display_path(cache_dir)),
                ("device", args.device),
            ],
            color=color_enabled,
        )

    if not args.json_only:
        _log_step(
            2,
            6,
            "Create LeWorldModelProvider",
            [
                ("provider", "leworldmodel"),
                ("capability", "score"),
                (
                    "runtime",
                    "stable_worldmodel.policy.AutoCostModel (official LeWM loading API)",
                ),
            ],
            color=color_enabled,
        )
    provider_events = []

    def _record_event(event: object) -> None:
        to_dict = getattr(event, "to_dict", None)
        if callable(to_dict):
            provider_events.append(to_dict())

    provider = LeWorldModelProvider(
        policy=args.policy,
        cache_dir=str(cache_dir),
        device=args.device,
        event_handler=_record_event,
    )
    health = provider.health().to_dict()
    if not args.json_only:
        _log_step(
            3,
            6,
            "Preflight optional runtime dependencies",
            [
                ("healthy", _status_text(health.get("healthy"), color=color_enabled)),
                ("details", health.get("details")),
                ("latency ms", f"{float(health.get('latency_ms') or 0.0):.2f}"),
            ],
            color=color_enabled,
        )
    if not health.get("healthy"):
        payload = {
            "checkpoint": str(object_path),
            "checkpoint_display": _display_path(object_path),
            "error": "runtime preflight failed",
            "health": health,
            "metrics": {
                "resolve_latency_ms": resolve_latency_ms,
                "preflight_latency_ms": health.get("latency_ms"),
                "total_latency_ms": (perf_counter() - total_started) * 1000,
            },
        }
        if args.json_output is not None:
            _write_json_output(args.json_output, payload)
        if args.run_manifest is not None:
            write_run_manifest(
                args.run_manifest,
                build_run_manifest(
                    run_id=args.run_manifest.parent.name,
                    provider_profile="leworldmodel",
                    capability="score",
                    status="failed",
                    env_vars=("LEWORLDMODEL_CHECKPOINT", "LEWORLDMODEL_POLICY", "STABLEWM_HOME"),
                    event_count=len(provider_events),
                    result=payload,
                    artifact_paths=(
                        {"summary_json": args.json_output} if args.json_output is not None else {}
                    ),
                ),
            )
        if args.json_only:
            print(json.dumps(payload, indent=2, sort_keys=True))
            return 1
        print(
            "\nLeWorldModel runtime preflight failed: "
            f"{health.get('details')}\n\n"
            "Run the complete uv-backed task instead:\n"
            f"{_runtime_command(checkpoint=object_path, device=args.device)}",
            flush=True,
        )
        return 1

    if not args.json_only:
        _log_step(
            4,
            6,
            "Build synthetic LeWorldModel tensors",
            [
                ("batch", args.batch),
                ("samples", args.samples),
                ("history", args.history),
                ("horizon", args.horizon),
                ("action dim", args.action_dim),
                ("image size", args.image_size),
                ("seed", seed if seed is not None else "disabled"),
                ("data", "synthetic PushT-shaped tensors"),
            ],
            color=color_enabled,
        )
    tensor_started = perf_counter()
    info, action_candidates = _build_inputs(
        batch=args.batch,
        samples=args.samples,
        history=args.history,
        horizon=args.horizon,
        action_dim=args.action_dim,
        image_size=args.image_size,
        seed=seed,
    )
    tensor_build_latency_ms = (perf_counter() - tensor_started) * 1000
    input_shapes = _input_shape_summary(info, action_candidates)
    input_shape_values = _input_shapes(info, action_candidates)
    input_stats = _input_stats(input_shape_values)
    if not args.json_only:
        for label, shape in input_shapes.items():
            print(f"  {label:<18} {shape}", flush=True)
        print(
            f"  {'tensor elements':<18} {input_stats['total_tensor_elements']}",
            flush=True,
        )
        print(
            f"  {'approx float32 MB':<18} {input_stats['approx_float32_mb']}",
            flush=True,
        )
        print(f"  {'build latency ms':<18} {tensor_build_latency_ms:.2f}", flush=True)

    if not args.json_only:
        _log_step(
            5,
            6,
            "Run score_actions through the real checkpoint",
            [
                ("operation", "leworldmodel.score_actions"),
                ("candidate count", args.samples),
                ("contract", "observations + goal + candidate action sequences -> costs"),
            ],
            color=color_enabled,
        )
    started = perf_counter()
    result = provider.score_actions(info=info, action_candidates=action_candidates)
    score_latency_ms = (perf_counter() - started) * 1000
    result_payload = result.to_dict()
    score_stats = _score_stats(result_payload)
    score_payload_summary = _score_payload_summary(result_payload)
    total_latency_ms = (perf_counter() - total_started) * 1000
    metrics = {
        "resolve_latency_ms": resolve_latency_ms,
        "preflight_latency_ms": health.get("latency_ms"),
        "tensor_build_latency_ms": tensor_build_latency_ms,
        "score_latency_ms": score_latency_ms,
        "total_latency_ms": total_latency_ms,
        **score_stats,
    }
    payload = {
        "checkpoint": str(object_path),
        "checkpoint_display": _display_path(object_path),
        "health": health,
        "inputs": {
            "batch": args.batch,
            "samples": args.samples,
            "history": args.history,
            "horizon": args.horizon,
            "action_dim": args.action_dim,
            "image_size": args.image_size,
            "seed": seed,
            "shapes": input_shape_values,
            **input_stats,
        },
        "metrics": metrics,
        "provider_events": provider_events,
        "result": result_payload,
        "score_payload_summary": score_payload_summary,
    }
    if args.json_output is not None:
        json_output_path = _write_json_output(args.json_output, payload)
    else:
        json_output_path = None
    run_manifest_path = None
    if args.run_manifest is not None:
        run_manifest_path = write_run_manifest(
            args.run_manifest,
            build_run_manifest(
                run_id=args.run_manifest.parent.name,
                provider_profile="leworldmodel",
                capability="score",
                status="passed",
                env_vars=("LEWORLDMODEL_CHECKPOINT", "LEWORLDMODEL_POLICY", "STABLEWM_HOME"),
                event_count=len(provider_events),
                result=payload,
                artifact_paths=(
                    {"summary_json": json_output_path} if json_output_path is not None else {}
                ),
            ),
        )
    if args.json_only:
        print(json.dumps(payload, indent=2, sort_keys=True))
        return 0

    metadata = result_payload.get("metadata", {})
    _log_step(
        6,
        6,
        "Rank action candidates",
        [
            ("lower is better", result_payload.get("lower_is_better")),
            ("best index", result_payload.get("best_index")),
            ("best score", result_payload.get("best_score")),
            ("score latency ms", f"{score_latency_ms:.2f}"),
            ("total latency ms", f"{total_latency_ms:.2f}"),
            ("score type", metadata.get("score_type", "cost")),
            ("gap to runner-up", f"{float(score_stats.get('gap_to_runner_up', 0.0)):.6f}"),
        ],
        color=color_enabled,
    )
    print("\nCandidate cost landscape", flush=True)
    print("------------------------", flush=True)
    for line in _score_chart(result_payload, color=color_enabled):
        print(line, flush=True)
    _print_score_stats(score_stats)
    _print_provider_events(provider_events)
    if json_output_path is not None:
        print("\nArtifacts", flush=True)
        print("---------", flush=True)
        print(f"  json summary       {_display_path(json_output_path)}", flush=True)
        if run_manifest_path is not None:
            print(f"  run manifest       {_display_path(run_manifest_path)}", flush=True)
    print("\nCompleted real LeWorldModel checkpoint inference.", flush=True)
    print("Use --json-only for the machine-readable summary.", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

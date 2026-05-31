"""Human-readable and JSON output helpers for LeWorldModel smoke runs."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

from worldforge.artifact_io import write_json_artifact
from worldforge.smoke.leworldmodel_models import (
    _ResolvedCheckpoint,
    _ScoreRun,
    _SmokeSettings,
    _TensorBatch,
)
from worldforge.smoke.leworldmodel_tensors import _score_chart

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
    return write_json_artifact(path.expanduser(), payload)


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


def _print_resolved_runtime(settings: _SmokeSettings, runtime: _ResolvedCheckpoint) -> None:
    if settings.json_only:
        return
    _log_step(
        1,
        6,
        "Resolve checkpoint and runtime settings",
        [
            ("policy", settings.policy),
            ("checkpoint", _display_path(runtime.object_path)),
            ("cache root", _display_path(runtime.cache_dir)),
            ("device", settings.device),
        ],
        color=settings.color_enabled,
    )


def _print_provider_setup(settings: _SmokeSettings) -> None:
    if settings.json_only:
        return
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
        color=settings.color_enabled,
    )


def _print_preflight(settings: _SmokeSettings, health: dict[str, Any]) -> None:
    if settings.json_only:
        return
    _log_step(
        3,
        6,
        "Preflight optional runtime dependencies",
        [
            ("healthy", _status_text(health.get("healthy"), color=settings.color_enabled)),
            ("details", health.get("details")),
            ("latency ms", f"{float(health.get('latency_ms') or 0.0):.2f}"),
        ],
        color=settings.color_enabled,
    )


def _print_tensor_plan(settings: _SmokeSettings) -> None:
    if settings.json_only:
        return
    _log_step(
        4,
        6,
        "Build synthetic LeWorldModel tensors",
        [
            ("batch", settings.batch),
            ("samples", settings.samples),
            ("history", settings.history),
            ("horizon", settings.horizon),
            ("action dim", settings.action_dim),
            ("image size", settings.image_size),
            ("seed", settings.seed if settings.seed is not None else "disabled"),
            ("data", "synthetic PushT-shaped tensors"),
        ],
        color=settings.color_enabled,
    )


def _print_tensor_summary(settings: _SmokeSettings, tensor_batch: _TensorBatch) -> None:
    if settings.json_only:
        return
    for label, shape in tensor_batch.input_shapes.items():
        print(f"  {label:<18} {shape}", flush=True)
    print(
        f"  {'tensor elements':<18} {tensor_batch.input_stats['total_tensor_elements']}",
        flush=True,
    )
    print(
        f"  {'approx float32 MB':<18} {tensor_batch.input_stats['approx_float32_mb']}",
        flush=True,
    )
    print(
        f"  {'build latency ms':<18} {tensor_batch.tensor_build_latency_ms:.2f}",
        flush=True,
    )


def _print_score_plan(settings: _SmokeSettings) -> None:
    if settings.json_only:
        return
    _log_step(
        5,
        6,
        "Run score_actions through the real checkpoint",
        [
            ("operation", "leworldmodel.score_actions"),
            ("candidate count", settings.samples),
            ("contract", "observations + goal + candidate action sequences -> costs"),
        ],
        color=settings.color_enabled,
    )


def _print_success_report(
    *,
    settings: _SmokeSettings,
    score_run: _ScoreRun,
    provider_events: list[dict[str, Any]],
    json_output_path: Path | None,
    run_manifest_path: Path | None,
) -> None:
    metadata = score_run.result_payload.get("metadata", {})
    _log_step(
        6,
        6,
        "Rank action candidates",
        [
            ("lower is better", score_run.result_payload.get("lower_is_better")),
            ("best index", score_run.result_payload.get("best_index")),
            ("best score", score_run.result_payload.get("best_score")),
            ("score latency ms", f"{score_run.score_latency_ms:.2f}"),
            ("total latency ms", f"{score_run.total_latency_ms:.2f}"),
            ("score type", metadata.get("score_type", "cost")),
            (
                "gap to runner-up",
                f"{float(score_run.score_stats.get('gap_to_runner_up', 0.0)):.6f}",
            ),
        ],
        color=settings.color_enabled,
    )
    print("\nCandidate cost landscape", flush=True)
    print("------------------------", flush=True)
    for line in _score_chart(score_run.result_payload, color=settings.color_enabled):
        print(line, flush=True)
    _print_score_stats(score_run.score_stats)
    _print_provider_events(provider_events)
    _print_artifacts(json_output_path=json_output_path, run_manifest_path=run_manifest_path)
    print("\nCompleted real LeWorldModel checkpoint inference.", flush=True)
    print("Use --json-only for the machine-readable summary.", flush=True)


def _print_artifacts(*, json_output_path: Path | None, run_manifest_path: Path | None) -> None:
    if json_output_path is None:
        return
    print("\nArtifacts", flush=True)
    print("---------", flush=True)
    print(f"  json summary       {_display_path(json_output_path)}", flush=True)
    if run_manifest_path is not None:
        print(f"  run manifest       {_display_path(run_manifest_path)}", flush=True)

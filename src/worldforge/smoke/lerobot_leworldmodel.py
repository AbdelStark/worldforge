"""Run a real LeRobot policy plus real LeWorldModel scoring flow.

This is a host-owned robotics-builder smoke/showcase. It composes a real
LeRobot policy checkpoint with a real LeWorldModel object checkpoint through
``World.plan(..., planning_mode="policy+score")``.

The runner deliberately does not own task preprocessing. For a meaningful run,
the LeRobot policy, observation, LeWorldModel score tensors, and candidate
action tensor bridge must all describe the same robotics task.
"""

from __future__ import annotations

import argparse
import importlib
import importlib.util
import json
import os
import tempfile
from collections.abc import Callable, Sequence
from pathlib import Path
from time import perf_counter
from types import ModuleType
from typing import Any

from worldforge import Action, BBox, Position, SceneObject, StructuredGoal, WorldForge
from worldforge.models import ProviderEvent
from worldforge.providers import LeRobotPolicyProvider, LeWorldModelProvider
from worldforge.providers._config import env_value as _env_value
from worldforge.smoke.run_manifest import build_run_manifest, write_run_manifest

from .leworldmodel import (
    DEFAULT_STABLEWM_HOME,
    _display_path,
    _input_stats,
    _paint,
    _resolve_checkpoint,
    _score_chart,
    _score_stats,
    _status_text,
    _use_color,
    _write_json_output,
)

DEFAULT_LEROBOT_POLICY = "lerobot/diffusion_pusht"
DEFAULT_LEWORLDMODEL_POLICY = "pusht/lewm"
DEFAULT_DEVICE = "cpu"
DEFAULT_MODE = "select_action"
DEFAULT_TASK = (
    "PushT tabletop manipulation: use a LeRobot policy to propose an action chunk, "
    "then rank policy-compatible candidates with a LeWorldModel cost checkpoint."
)


def _load_json_file(path: Path, *, name: str) -> object:
    try:
        return json.loads(path.expanduser().read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise SystemExit(f"{name} file does not exist: {path}") from exc
    except json.JSONDecodeError as exc:
        raise SystemExit(f"{name} file is not valid JSON: {path}: {exc}") from exc


def _json_object_from_file(path: Path, *, name: str) -> dict[str, Any]:
    payload = _load_json_file(path, name=name)
    if not isinstance(payload, dict):
        raise SystemExit(f"{name} must decode to a JSON object.")
    return dict(payload)


def _module_from_path(path: Path) -> ModuleType:
    resolved = path.expanduser().resolve()
    if not resolved.exists():
        raise SystemExit(f"Python module file does not exist: {path}")
    module_spec = importlib.util.spec_from_file_location(resolved.stem, resolved)
    if module_spec is None or module_spec.loader is None:
        raise SystemExit(f"Could not load Python module from: {path}")
    module = importlib.util.module_from_spec(module_spec)
    module_spec.loader.exec_module(module)
    return module


def _load_callable(spec: str, *, name: str) -> Callable[..., Any]:
    if ":" not in spec:
        raise SystemExit(f"{name} must be formatted as module_or_file:function.")
    module_ref, function_name = spec.rsplit(":", 1)
    if not module_ref.strip() or not function_name.strip():
        raise SystemExit(f"{name} must be formatted as module_or_file:function.")

    candidate_path = Path(module_ref)
    if candidate_path.exists() or module_ref.endswith(".py") or "/" in module_ref:
        module = _module_from_path(candidate_path)
    else:
        try:
            module = importlib.import_module(module_ref)
        except ImportError as exc:
            raise SystemExit(f"Could not import {name} module '{module_ref}': {exc}") from exc

    try:
        loaded = getattr(module, function_name)
    except AttributeError as exc:
        raise SystemExit(f"{name} function '{function_name}' was not found.") from exc
    if not callable(loaded):
        raise SystemExit(f"{name} target '{function_name}' is not callable.")
    return loaded


def _load_policy_info(args: argparse.Namespace) -> dict[str, Any]:
    if args.policy_info_json is not None:
        info = _json_object_from_file(args.policy_info_json, name="policy-info")
    elif args.observation_json is not None:
        info = {"observation": _json_object_from_file(args.observation_json, name="observation")}
    elif args.observation_module is not None:
        factory = _load_callable(args.observation_module, name="observation factory")
        try:
            produced = factory()
        except Exception as exc:
            raise SystemExit(f"Observation factory failed: {exc}") from exc
        if not isinstance(produced, dict):
            raise SystemExit("Observation factory must return a dictionary.")
        info = dict(produced) if "observation" in produced else {"observation": dict(produced)}
    else:
        raise SystemExit(
            "Real LeRobot+LeWorldModel flow requires --policy-info-json, "
            "--observation-json, or --observation-module."
        )

    if args.options_json is not None:
        info["options"] = _json_object_from_file(args.options_json, name="options")
    if args.embodiment_tag is not None:
        info.setdefault("embodiment_tag", args.embodiment_tag)
    if args.action_horizon is not None:
        info["action_horizon"] = args.action_horizon
    if args.mode is not None:
        info["mode"] = args.mode
    info.setdefault("score_bridge", {})
    if isinstance(info["score_bridge"], dict):
        info["score_bridge"].setdefault("task", "pusht")
        if args.expected_action_dim is not None:
            info["score_bridge"]["expected_action_dim"] = args.expected_action_dim
        if args.expected_horizon is not None:
            info["score_bridge"]["expected_horizon"] = args.expected_horizon
    return info


def _array_to_runtime_value(value: object) -> object:
    try:
        import torch
    except ImportError:
        tolist = getattr(value, "tolist", None)
        return tolist() if callable(tolist) else value
    as_tensor = getattr(torch, "as_tensor", None)
    if callable(as_tensor):
        return as_tensor(value)
    tolist = getattr(value, "tolist", None)
    return tolist() if callable(tolist) else value


def _load_npz_map(path: Path, *, keys: Sequence[str], name: str) -> dict[str, object]:
    try:
        import numpy as np
    except ImportError as exc:
        raise SystemExit(f"{name} loading requires optional dependency numpy.") from exc
    expanded = path.expanduser()
    if not expanded.exists():
        raise SystemExit(f"{name} file does not exist: {path}")
    try:
        with np.load(expanded, allow_pickle=False) as data:
            missing = [key for key in keys if key not in data]
            if missing:
                raise SystemExit(f"{name} NPZ is missing required arrays: {', '.join(missing)}.")
            return {key: _array_to_runtime_value(data[key]) for key in keys}
    except SystemExit:
        raise
    except Exception as exc:
        raise SystemExit(f"{name} NPZ could not be loaded: {path}: {exc}") from exc


def _load_score_info(args: argparse.Namespace) -> dict[str, object]:
    if args.score_info_json is not None:
        score_info = _json_object_from_file(args.score_info_json, name="score-info")
    elif args.score_info_npz is not None:
        score_info = _load_npz_map(
            args.score_info_npz,
            keys=("pixels", "goal", "action"),
            name="score-info",
        )
    elif args.score_info_module is not None:
        factory = _load_callable(args.score_info_module, name="score-info factory")
        try:
            produced = factory()
        except Exception as exc:
            raise SystemExit(f"Score-info factory failed: {exc}") from exc
        if not isinstance(produced, dict):
            raise SystemExit("Score-info factory must return a dictionary.")
        score_info = dict(produced)
    else:
        raise SystemExit(
            "Real LeRobot+LeWorldModel flow requires --score-info-json, --score-info-npz, "
            "or --score-info-module."
        )
    return score_info


def _materialize_candidate_payload(value: object) -> object:
    if isinstance(value, dict):
        for key in ("action_candidates", "score_action_candidates"):
            if key in value:
                return _materialize_candidate_payload(value[key])
    current = value
    for method_name in ("detach", "cpu"):
        method = getattr(current, method_name, None)
        if callable(method):
            current = method()
    tolist = getattr(current, "tolist", None)
    if callable(tolist):
        current = tolist()
    if isinstance(current, tuple):
        return [_materialize_candidate_payload(item) for item in current]
    return current


def _load_static_action_candidates(args: argparse.Namespace) -> object | None:
    if args.action_candidates_json is not None:
        payload = _load_json_file(args.action_candidates_json, name="action-candidates")
        return _materialize_candidate_payload(payload)
    if args.action_candidates_npz is not None:
        key = args.action_candidates_key
        loaded = _load_npz_map(args.action_candidates_npz, keys=(key,), name="action-candidates")
        return loaded[key]
    return None


def _numeric_leaf(value: object, *, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise ValueError(f"{name} must be numeric.")
    number = float(value)
    if number != number or number in (float("inf"), float("-inf")):
        raise ValueError(f"{name} must be finite.")
    return number


def _nested_shape(value: object) -> tuple[int, ...]:
    if isinstance(value, Sequence) and not isinstance(value, str | bytes | bytearray):
        if not value:
            raise ValueError("nested action payload must not contain empty lists.")
        child_shapes = [_nested_shape(child) for child in value]
        first = child_shapes[0]
        if any(shape != first for shape in child_shapes):
            raise ValueError("nested action payload must be rectangular.")
        return (len(value), *first)
    _numeric_leaf(value, name="action payload value")
    return ()


def _ensure_nested_list(value: object) -> list[Any]:
    materialized = _materialize_candidate_payload(value)
    if not isinstance(materialized, list):
        raise ValueError("action candidate payload must materialize to a nested list.")
    _nested_shape(materialized)
    return materialized


def _normalize_action_candidate_tensor(value: object) -> list[Any]:
    """Normalize raw policy actions to (batch, samples, horizon, action_dim)."""

    nested = _ensure_nested_list(value)
    shape = _nested_shape(nested)
    if len(shape) == 1:
        return [[[nested]]]
    if len(shape) == 2:
        return [[nested]]
    if len(shape) == 3:
        return [nested]
    if len(shape) == 4:
        return nested
    raise ValueError(
        "raw policy actions must be shaped as action_dim, horizon x action_dim, "
        "samples x horizon x action_dim, or batch x samples x horizon x action_dim."
    )


def _score_bridge_config(info: dict[str, Any]) -> dict[str, Any]:
    config = info.get("score_bridge")
    return dict(config) if isinstance(config, dict) else {}


def build_pusht_lewm_action_candidates(
    raw_actions: object,
    info: dict[str, Any],
    _provider_info: dict[str, Any],
) -> list[Any]:
    """Build LeWorldModel action candidates from already-compatible PushT actions.

    This helper only reshapes the LeRobot raw action chunk. It does not pad,
    project, or otherwise reinterpret action dimensions. Set
    ``info["score_bridge"]["expected_action_dim"]`` or pass
    ``--expected-action-dim`` to make the check explicit.
    """

    candidates = _normalize_action_candidate_tensor(raw_actions)
    shape = _nested_shape(candidates)
    if shape[0] != 1:
        raise ValueError(
            "The built-in PushT LeRobot-to-LeWorldModel bridge supports one world batch. "
            "Provide a task-specific candidate builder for batched policy output."
        )
    config = _score_bridge_config(info)
    expected_dim = config.get("expected_action_dim")
    if expected_dim is not None and shape[-1] != int(expected_dim):
        raise ValueError(
            f"LeRobot action dim {shape[-1]} does not match expected LeWorldModel action dim "
            f"{int(expected_dim)}. Provide a task-specific candidate builder instead of "
            "silently padding or projecting actions."
        )
    expected_horizon = config.get("expected_horizon")
    if expected_horizon is not None and shape[-2] != int(expected_horizon):
        raise ValueError(
            f"LeRobot action horizon {shape[-2]} does not match expected LeWorldModel horizon "
            f"{int(expected_horizon)}."
        )
    return candidates


def _coerce_action(value: object) -> Action:
    if isinstance(value, Action):
        return value
    if isinstance(value, dict):
        return Action.from_dict(value)
    raise ValueError("translator must return Action objects or Action dictionaries.")


def _coerce_action_candidates(value: object) -> list[list[Action]]:
    if not isinstance(value, Sequence) or isinstance(value, str | bytes | bytearray) or not value:
        raise ValueError("translator must return a non-empty action sequence.")
    if all(isinstance(item, Action | dict) for item in value):
        return [[_coerce_action(item) for item in value]]
    candidates: list[list[Action]] = []
    for index, candidate in enumerate(value):
        if (
            not isinstance(candidate, Sequence)
            or isinstance(candidate, str | bytes | bytearray)
            or not candidate
        ):
            raise ValueError(f"translator candidate {index} must be a non-empty action sequence.")
        candidates.append([_coerce_action(item) for item in candidate])
    return candidates


def translate_pusht_xy_actions(
    raw_actions: object,
    info: dict[str, Any],
    _provider_info: dict[str, Any],
) -> list[list[Action]]:
    """Translate PushT-like action vectors to visual WorldForge ``move_to`` actions.

    The first two action dimensions are interpreted as a tabletop ``x, y`` target
    for reporting and mock execution. The full raw action vector is still
    preserved for LeWorldModel scoring by a candidate builder.
    """

    candidates = _normalize_action_candidate_tensor(raw_actions)
    shape = _nested_shape(candidates)
    if shape[0] != 1:
        raise ValueError(
            "The built-in PushT translator supports one world batch. Provide a task-specific "
            "translator for batched policy output."
        )
    object_id = str(_score_bridge_config(info).get("object_id") or "pusht-block")
    translated: list[list[Action]] = []
    for sample in candidates[0]:
        plan: list[Action] = []
        for step in sample:
            if not isinstance(step, Sequence) or len(step) < 2:
                raise ValueError("PushT action vectors must contain at least x and y values.")
            x = _numeric_leaf(step[0], name="PushT action x")
            y = _numeric_leaf(step[1], name="PushT action y")
            z = _numeric_leaf(step[2], name="PushT action z") if len(step) >= 3 else 0.0
            plan.append(Action.move_to(x, y, z, object_id=object_id))
        translated.append(plan)
    return translated


class _DynamicCandidateBridge:
    def __init__(
        self,
        *,
        translator: Callable[..., Any],
        candidate_builder: Callable[..., Any] | None,
        holder: list[Any],
    ) -> None:
        self._translator = translator
        self._candidate_builder = candidate_builder
        self._holder = holder
        self.used_dynamic_builder = False

    def translate(
        self,
        raw_actions: object,
        info: dict[str, Any],
        provider_info: dict[str, Any],
    ) -> list[list[Action]]:
        translated = _coerce_action_candidates(self._translator(raw_actions, info, provider_info))
        if self._candidate_builder is not None:
            built = self._candidate_builder(raw_actions, info, provider_info)
            materialized = _ensure_nested_list(built)
            self._holder.clear()
            self._holder.extend(materialized)
            self.used_dynamic_builder = True
        return translated


def _shape_tuple(value: object) -> tuple[int, ...] | None:
    shape = getattr(value, "shape", None)
    if shape is None:
        try:
            shape = _nested_shape(value)
        except Exception:
            return None
    try:
        return tuple(int(part) for part in tuple(shape))
    except (TypeError, ValueError):
        return None


def _shape_text(value: object) -> str:
    shape = _shape_tuple(value)
    if shape is None:
        return "unknown"
    return " x ".join(str(part) for part in shape)


def _input_shapes(
    info: dict[str, object],
    action_candidates: object,
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


def _event_dicts(events: list[ProviderEvent]) -> list[dict[str, Any]]:
    return [event.to_dict() for event in events]


def _print_header(*, color: bool) -> None:
    title = "WorldForge real robotics policy+world-model inference"
    print(_paint(title, "cyan", enabled=color, bold=True))
    print("=" * len(title))
    print("Mode: real LeRobot policy inference plus real LeWorldModel checkpoint scoring.")
    print(
        "Run contract: "
        f"{_paint('REAL', 'green', enabled=color, bold=True)} policy + "
        f"{_paint('REAL', 'green', enabled=color, bold=True)} score + "
        f"{_paint('LOCAL', 'yellow', enabled=color, bold=True)} mock replay"
    )
    print("\nWhat this demonstrates")
    print("----------------------")
    print("  - loads a host-owned LeRobot policy checkpoint")
    print("  - loads a host-owned LeWorldModel object checkpoint")
    print("  - asks LeRobot for action candidates from a task observation")
    print("  - bridges policy actions into LeWorldModel action-candidate tensors")
    print("  - ranks those candidates through WorldForge policy+score planning")
    print("  - executes the selected WorldForge action chunk in the local mock world")
    print(
        "Boundary: this is simulation/replay planning. Hardware control, safety checks, "
        "and task-specific preprocessing remain host-owned."
    )
    print("\nPipeline")
    print("--------")
    print(
        "  observation -> LeRobot policy -> action candidates -> tensor bridge -> "
        "LeWorldModel costs -> WorldForge plan -> mock execution"
    )
    print("\nPipeline map")
    print("------------")
    print("  +-------------------+      +-------------------+      +----------------------+")
    print("  | PushT observation | ---> | LeRobot policy    | ---> | action candidates    |")
    print("  +-------------------+      +-------------------+      +----------+-----------+")
    print("             |                                                    |")
    print("             v                                                    v")
    print("  +-------------------+      +-------------------+      +----------------------+")
    print("  | LeWM score tensors| ---> | LeWorldModel cost | ---> | WorldForge planner   |")
    print("  +-------------------+      +-------------------+      +----------+-----------+")
    print("                                                                  |")
    print("                                                                  v")
    print("                                                        +----------------------+")
    print("                                                        | local mock replay    |")
    print("                                                        +----------------------+")


def _log_step(
    index: int,
    total: int,
    title: str,
    rows: list[tuple[str, object]] | None = None,
    *,
    color: bool,
) -> None:
    print(f"\n{_paint(f'[{index}/{total}] {title}', 'cyan', enabled=color, bold=True)}")
    for label, value in rows or []:
        print(f"  {label:<22} {value}")


def _print_provider_events(events: list[dict[str, Any]]) -> None:
    print("\nProvider event log")
    print("------------------")
    if not events:
        print("  no provider events emitted")
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
            f"{event.get('phase')} duration={duration_text} {metadata_text}".rstrip()
        )


def _section(title: str) -> None:
    print(f"\n{title}")
    print("-" * len(title))


def _float_or_none(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    number = float(value)
    if number != number or number in (float("inf"), float("-inf")):
        return None
    return number


def _provider_latency_ms(
    events: list[dict[str, Any]],
    provider: str,
    operation: str,
) -> float | None:
    for event in reversed(events):
        if event.get("provider") == provider and event.get("operation") == operation:
            return _float_or_none(event.get("duration_ms"))
    return None


def _bar(value: float, maximum: float, *, width: int = 30) -> str:
    if maximum <= 0.0 or value <= 0.0:
        fill = 0
    else:
        fill = max(1, min(width, round((value / maximum) * width)))
    return f"|{'#' * fill:<{width}}|"


def _print_runtime_profile(
    *,
    events: list[dict[str, Any]],
    plan_latency_ms: float,
    total_latency_ms: float,
    color: bool,
) -> None:
    rows = [
        ("LeRobot policy", _provider_latency_ms(events, "lerobot", "policy")),
        ("LeWorldModel score", _provider_latency_ms(events, "leworldmodel", "score")),
        ("WorldForge plan", plan_latency_ms),
        ("End-to-end run", total_latency_ms),
    ]
    maximum = max((value or 0.0) for _label, value in rows)
    _section("Runtime profile")
    for label, value in rows:
        if value is None:
            print(f"  {label:<20} {'n/a':>10}  {_bar(0.0, maximum)}")
            continue
        bar_color = "green" if label == "LeWorldModel score" else "cyan"
        bar = _paint(_bar(value, maximum), bar_color, enabled=color)
        print(f"  {label:<20} {value:>9.2f} ms  {bar}")


def _print_score_summary(stats: dict[str, Any]) -> None:
    if not stats:
        return
    _section("Score summary")
    rows = [
        ("min", stats.get("score_min")),
        ("median", stats.get("score_median")),
        ("mean", stats.get("score_mean")),
        ("max", stats.get("score_max")),
        ("range", stats.get("score_range")),
        ("gap to runner-up", stats.get("gap_to_runner_up")),
    ]
    for label, value in rows:
        number = _float_or_none(value)
        text = "n/a" if number is None else f"{number:.6f}"
        print(f"  {label:<18} {text}")


def _action_target(action: object) -> dict[str, float] | None:
    if not isinstance(action, dict):
        return None
    parameters = action.get("parameters")
    if not isinstance(parameters, dict):
        return None
    target = parameters.get("target")
    if not isinstance(target, dict):
        return None
    x = _float_or_none(target.get("x"))
    y = _float_or_none(target.get("y"))
    z = _float_or_none(target.get("z"))
    if x is None or y is None or z is None:
        return None
    return {"x": x, "y": y, "z": z}


def _candidate_targets(policy_result: dict[str, Any]) -> list[dict[str, Any]]:
    candidates = policy_result.get("action_candidates")
    if not isinstance(candidates, list):
        return []
    targets: list[dict[str, Any]] = []
    for index, candidate in enumerate(candidates):
        if not isinstance(candidate, list) or not candidate:
            continue
        target = _action_target(candidate[0])
        if target is None:
            continue
        targets.append({"index": index, **target})
    return targets


def _score_by_index(score_result: dict[str, Any]) -> dict[int, float]:
    scores = score_result.get("scores")
    if not isinstance(scores, list):
        return {}
    score_map: dict[int, float] = {}
    for index, score in enumerate(scores):
        number = _float_or_none(score)
        if number is not None:
            score_map[index] = number
    return score_map


def _print_candidate_targets(
    *,
    policy_result: dict[str, Any],
    score_result: dict[str, Any],
    color: bool,
) -> list[dict[str, Any]]:
    targets = _candidate_targets(policy_result)
    if not targets:
        return []
    scores = _score_by_index(score_result)
    best_index = score_result.get("best_index")
    _section("Candidate targets")
    print(f"  {'candidate':<10} {'x':>8} {'y':>8} {'z':>8} {'score':>12}  status")
    for target in targets:
        index = int(target["index"])
        score = scores.get(index)
        marker = "SELECTED" if index == best_index else ""
        status = _paint(marker, "green", enabled=color, bold=True) if marker else ""
        score_text = "n/a" if score is None else f"{score:.6f}"
        print(
            f"  #{index:<9} {target['x']:>8.3f} {target['y']:>8.3f} "
            f"{target['z']:>8.3f} {score_text:>12}  {status}"
        )
    return targets


def _position_from_summary(summary: dict[str, Any] | None) -> dict[str, float] | None:
    if not isinstance(summary, dict):
        return None
    position = summary.get("final_block_position")
    if not isinstance(position, dict):
        return None
    x = _float_or_none(position.get("x"))
    y = _float_or_none(position.get("y"))
    z = _float_or_none(position.get("z"))
    if x is None or y is None or z is None:
        return None
    return {"x": x, "y": y, "z": z}


def _print_tabletop_replay(
    *,
    targets: list[dict[str, Any]],
    score_result: dict[str, Any],
    execution_summary: dict[str, Any] | None,
) -> None:
    if not targets:
        return
    width = 42
    height = 13
    cells: dict[tuple[int, int], set[str]] = {}

    def place(x: float, y: float, marker: str) -> None:
        column = max(0, min(width - 1, round(x * (width - 1))))
        row = max(0, min(height - 1, round((1.0 - y) * (height - 1))))
        cells.setdefault((row, column), set()).add(marker)

    place(0.0, 0.5, "S")
    place(0.5, 0.5, "G")
    best_index = score_result.get("best_index")
    for target in targets:
        index = int(target["index"])
        marker = "T" if index == best_index else str(index % 10)
        place(float(target["x"]), float(target["y"]), marker)
    final_position = _position_from_summary(execution_summary)
    if final_position is not None:
        place(final_position["x"], final_position["y"], "F")

    _section("Tabletop replay")
    print("  legend: S=start, G=goal, T=selected target, F=mock final, X=selected+final")
    if isinstance(best_index, int):
        print(f"  selected candidate: #{best_index}")
    print("  +" + "-" * width + "+")
    for row in range(height):
        chars: list[str] = []
        for column in range(width):
            markers = cells.get((row, column), set())
            if not markers:
                chars.append(" ")
            elif "F" in markers and "T" in markers:
                chars.append("X")
            elif "F" in markers:
                chars.append("F")
            elif "T" in markers:
                chars.append("T")
            elif len(markers) > 1:
                chars.append("*")
            else:
                chars.append(next(iter(markers)))
        print(f"  |{''.join(chars)}|")
    print("  +" + "-" * width + "+")
    print("  x=0.00             x=0.50             x=1.00")


def _runtime_command(*, checkpoint: Path, policy_path: str, device: str) -> str:
    checkpoint_text = _display_path(checkpoint)
    return (
        "scripts/lewm-lerobot-real \\\n"
        f"  --policy-path {policy_path} \\\n"
        "  --policy-type diffusion \\\n"
        f"  --checkpoint {checkpoint_text} \\\n"
        f"  --device {device} \\\n"
        "  --mode select_action \\\n"
        "  --observation-module /path/to/pusht_obs.py:build_observation \\\n"
        "  --score-info-npz /path/to/lewm_score_tensors.npz \\\n"
        "  --translator worldforge.smoke.lerobot_leworldmodel:translate_pusht_xy_actions \\\n"
        "  --candidate-builder /path/to/pusht_lewm_bridge.py:build_action_candidates"
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--policy-path",
        default=_env_value("LEROBOT_POLICY_PATH") or _env_value("LEROBOT_POLICY"),
        help=(
            "Hugging Face repo id or local directory of a LeRobot checkpoint. "
            f"Example PushT policy: {DEFAULT_LEROBOT_POLICY}."
        ),
    )
    parser.add_argument(
        "--policy-type",
        default=_env_value("LEROBOT_POLICY_TYPE"),
        help="Optional LeRobot policy type such as diffusion, act, vqbet, pi0, or smolvla.",
    )
    parser.add_argument(
        "--lewm-policy",
        default=(
            _env_value("LEWORLDMODEL_POLICY")
            or _env_value("LEWM_POLICY")
            or DEFAULT_LEWORLDMODEL_POLICY
        ),
        help="LeWorldModel policy/checkpoint run name relative to STABLEWM_HOME.",
    )
    parser.add_argument(
        "--stablewm-home",
        type=Path,
        default=Path(os.environ.get("STABLEWM_HOME", DEFAULT_STABLEWM_HOME)).expanduser(),
    )
    parser.add_argument(
        "--lewm-cache-dir",
        type=Path,
        default=None,
        help="Checkpoint root passed to LeWorldModelProvider. Defaults to STABLEWM_HOME.",
    )
    parser.add_argument(
        "--checkpoint",
        type=Path,
        default=(
            Path(os.environ["LEWORLDMODEL_CHECKPOINT"]).expanduser()
            if os.environ.get("LEWORLDMODEL_CHECKPOINT")
            else None
        ),
        help="Exact LeWorldModel <policy>_object.ckpt path.",
    )
    parser.add_argument(
        "--device",
        default=DEFAULT_DEVICE,
        help=(
            "Default device for both LeRobot and LeWorldModel unless provider-specific "
            "flags are set."
        ),
    )
    parser.add_argument("--lerobot-device", default=_env_value("LEROBOT_DEVICE"))
    parser.add_argument("--lewm-device", default=_env_value("LEWORLDMODEL_DEVICE"))
    parser.add_argument("--lerobot-cache-dir", default=_env_value("LEROBOT_CACHE_DIR"))
    parser.add_argument("--embodiment-tag", default=_env_value("LEROBOT_EMBODIMENT_TAG") or "pusht")
    parser.add_argument("--mode", choices=("select_action", "predict_chunk"), default=DEFAULT_MODE)
    parser.add_argument("--action-horizon", type=int, default=None)
    parser.add_argument("--expected-action-dim", type=int, default=None)
    parser.add_argument("--expected-horizon", type=int, default=None)
    parser.add_argument("--task", default=DEFAULT_TASK)
    parser.add_argument(
        "--goal",
        default="choose the lowest-cost PushT policy action chunk",
        help="WorldForge planning goal text.",
    )
    parser.add_argument(
        "--state-dir",
        type=Path,
        default=None,
        help="Optional WorldForge state directory. Defaults to a temporary run directory.",
    )
    parser.add_argument(
        "--json-output",
        type=Path,
        default=None,
        help="Write the full run summary JSON while keeping visual terminal output.",
    )
    parser.add_argument(
        "--run-manifest",
        type=Path,
        default=None,
        help="Write a sanitized run_manifest.json evidence file for this live robotics smoke.",
    )
    parser.add_argument("--json-only", action="store_true")
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
        "--no-execute",
        action="store_true",
        help="Skip local mock execution after selecting the policy+score plan.",
    )
    parser.add_argument("--health-only", action="store_true")

    input_group = parser.add_mutually_exclusive_group()
    input_group.add_argument("--policy-info-json", type=Path)
    input_group.add_argument("--observation-json", type=Path)
    input_group.add_argument("--observation-module")
    parser.add_argument("--options-json", type=Path)

    score_group = parser.add_mutually_exclusive_group()
    score_group.add_argument("--score-info-json", type=Path)
    score_group.add_argument("--score-info-npz", type=Path)
    score_group.add_argument("--score-info-module")

    candidates_group = parser.add_mutually_exclusive_group()
    candidates_group.add_argument("--action-candidates-json", type=Path)
    candidates_group.add_argument("--action-candidates-npz", type=Path)
    candidates_group.add_argument(
        "--candidate-builder",
        help=(
            "Callable module_or_file:function receiving (raw_actions, info, provider_info) "
            "and returning the LeWorldModel action_candidates tensor/list."
        ),
    )
    parser.add_argument("--action-candidates-key", default="action_candidates")
    parser.add_argument(
        "--translator",
        default="worldforge.smoke.lerobot_leworldmodel:translate_pusht_xy_actions",
        help=(
            "Callable module_or_file:function receiving (raw_actions, info, provider_info) "
            "and returning WorldForge Action candidates."
        ),
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    if not args.policy_path:
        parser.error(
            "real LeRobot+LeWorldModel flow requires --policy-path or LEROBOT_POLICY_PATH."
        )
    if args.action_horizon is not None and args.action_horizon <= 0:
        parser.error("--action-horizon must be greater than 0.")
    if args.expected_action_dim is not None and args.expected_action_dim <= 0:
        parser.error("--expected-action-dim must be greater than 0.")
    if args.expected_horizon is not None and args.expected_horizon <= 0:
        parser.error("--expected-horizon must be greater than 0.")
    missing_score_info = (
        args.score_info_json is None
        and args.score_info_npz is None
        and args.score_info_module is None
    )
    missing_candidates = (
        args.action_candidates_json is None
        and args.action_candidates_npz is None
        and args.candidate_builder is None
    )
    if not args.health_only and missing_score_info:
        parser.error(
            "planning requires --score-info-json, --score-info-npz, or --score-info-module."
        )
    if not args.health_only and missing_candidates:
        parser.error(
            "planning requires --candidate-builder or prebuilt --action-candidates-* input."
        )

    color_enabled = _use_color(args.color) and not args.json_only
    total_started = perf_counter()
    if not args.json_only:
        _print_header(color=color_enabled)

    object_path, lewm_cache_dir = _resolve_checkpoint(
        policy=args.lewm_policy,
        stablewm_home=args.stablewm_home,
        cache_dir=args.lewm_cache_dir,
        checkpoint=args.checkpoint,
        require_exists=not args.health_only,
    )
    checkpoint_exists = object_path.exists()
    lerobot_device = args.lerobot_device or args.device
    lewm_device = args.lewm_device or args.device
    if not args.json_only:
        _log_step(
            1,
            7,
            "Resolve checkpoints and runtime settings",
            [
                ("task", "PushT policy+world-model planning"),
                ("LeRobot policy", args.policy_path),
                ("LeRobot device", lerobot_device),
                ("LeWorldModel policy", args.lewm_policy),
                ("LeWorldModel checkpoint", _display_path(object_path)),
                ("LeWorldModel cache", _display_path(lewm_cache_dir)),
                ("LeWorldModel device", lewm_device),
            ],
            color=color_enabled,
        )

    provider_events: list[ProviderEvent] = []
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
    action_translator = bridge.translate

    policy_provider = LeRobotPolicyProvider(
        policy_path=args.policy_path,
        policy_type=args.policy_type,
        device=lerobot_device,
        cache_dir=args.lerobot_cache_dir,
        embodiment_tag=args.embodiment_tag,
        action_translator=action_translator,
        event_handler=provider_events.append,
    )
    score_provider = LeWorldModelProvider(
        policy=args.lewm_policy,
        cache_dir=str(lewm_cache_dir),
        device=lewm_device,
        event_handler=provider_events.append,
    )
    policy_health = policy_provider.health().to_dict()
    score_health = score_provider.health().to_dict()
    if not checkpoint_exists:
        score_health = dict(score_health)
        checkpoint_details = (
            f"LeWorldModel object checkpoint not found: {_display_path(object_path)}"
        )
        existing_details = score_health.get("details")
        score_health["healthy"] = False
        score_health["details"] = (
            f"{existing_details}; {checkpoint_details}" if existing_details else checkpoint_details
        )
    if not args.json_only:
        _log_step(
            2,
            7,
            "Preflight optional runtime dependencies",
            [
                (
                    "LeRobot healthy",
                    _status_text(policy_health.get("healthy"), color=color_enabled),
                ),
                ("LeRobot details", policy_health.get("details")),
                (
                    "LeWorldModel healthy",
                    _status_text(score_health.get("healthy"), color=color_enabled),
                ),
                ("LeWorldModel details", score_health.get("details")),
                (
                    "LeWorldModel checkpoint",
                    _status_text(checkpoint_exists, color=color_enabled),
                ),
            ],
            color=color_enabled,
        )

    preflight_ok = (
        bool(policy_health.get("healthy"))
        and bool(score_health.get("healthy"))
        and checkpoint_exists
    )
    if args.health_only or not preflight_ok:
        payload = {
            "mode": "real_lerobot_policy_plus_real_leworldmodel_score",
            "checkpoint": str(object_path),
            "checkpoint_display": _display_path(object_path),
            "checkpoint_exists": checkpoint_exists,
            "health": {"lerobot": policy_health, "leworldmodel": score_health},
            "metrics": {"total_latency_ms": (perf_counter() - total_started) * 1000},
        }
        if args.json_output is not None:
            _write_json_output(args.json_output, payload)
        if args.run_manifest is not None:
            json_artifacts = (
                {"report_summary": args.json_output} if args.json_output is not None else {}
            )
            write_run_manifest(
                args.run_manifest,
                build_run_manifest(
                    run_id=args.run_manifest.parent.name,
                    provider_profile="lerobot-leworldmodel",
                    capability="policy+score",
                    status="skipped" if args.health_only and preflight_ok else "failed",
                    env_vars=(
                        "LEROBOT_POLICY_PATH",
                        "LEROBOT_POLICY",
                        "LEROBOT_POLICY_TYPE",
                        "LEROBOT_DEVICE",
                        "LEROBOT_CACHE_DIR",
                        "LEWORLDMODEL_CHECKPOINT",
                        "LEWORLDMODEL_POLICY",
                        "LEWM_POLICY",
                        "LEWORLDMODEL_DEVICE",
                        "STABLEWM_HOME",
                    ),
                    event_count=len(provider_events),
                    result=payload,
                    artifact_paths=json_artifacts,
                ),
            )
        if args.json_only:
            print(json.dumps(payload, indent=2, sort_keys=True))
        elif not preflight_ok:
            print("\nRuntime preflight failed. Run the complete uv-backed task with host inputs:")
            print(
                _runtime_command(
                    checkpoint=object_path,
                    policy_path=args.policy_path,
                    device=args.device,
                )
            )
        return 0 if preflight_ok else 1

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
            color=color_enabled,
        )
    policy_info = _load_policy_info(args)
    score_info = _load_score_info(args)
    if score_action_candidates is None:
        raise SystemExit("internal error: missing score_action_candidates")

    if not args.json_only:
        _log_step(
            4,
            7,
            "Create WorldForge robotics planning surface",
            [
                ("policy provider", "lerobot"),
                ("score provider", "leworldmodel"),
                ("planning mode", "policy+score"),
                ("execution provider", "mock" if not args.no_execute else "skipped"),
            ],
            color=color_enabled,
        )
    state_dir = args.state_dir or Path(tempfile.mkdtemp(prefix="worldforge-real-robotics-"))
    forge = WorldForge(state_dir=state_dir, auto_register_remote=False)
    forge.register_provider(policy_provider)
    forge.register_provider(score_provider)
    world = forge.create_world("real-robotics-policy-world-model", provider="mock")
    block = world.add_object(
        SceneObject(
            "pusht-block",
            Position(0.0, 0.5, 0.0),
            BBox(Position(-0.05, 0.45, -0.05), Position(0.05, 0.55, 0.05)),
        )
    )
    policy_info.setdefault("score_bridge", {})
    if isinstance(policy_info["score_bridge"], dict):
        policy_info["score_bridge"].setdefault("object_id", block.id)

    if not args.json_only:
        _log_step(
            5,
            7,
            "Run LeRobot policy and LeWorldModel score planning",
            [
                (
                    "operation",
                    "World.plan(policy_provider='lerobot', score_provider='leworldmodel')",
                ),
                ("goal", args.goal),
                ("dynamic bridge", bool(candidate_builder)),
            ],
            color=color_enabled,
        )
    plan_started = perf_counter()
    goal_spec = StructuredGoal.object_at(
        object_id=block.id,
        object_name=block.name,
        position=Position(0.5, 0.5, 0.0),
        tolerance=0.05,
    )
    plan = world.plan(
        goal=args.goal,
        goal_spec=goal_spec,
        planner="lerobot-leworldmodel-mpc",
        policy_provider="lerobot",
        policy_info=policy_info,  # type: ignore[arg-type]
        score_provider="leworldmodel",
        score_info=score_info,  # type: ignore[arg-type]
        score_action_candidates=score_action_candidates,
        execution_provider="mock",
    )
    plan_latency_ms = (perf_counter() - plan_started) * 1000
    score_result = plan.metadata["score_result"]
    policy_result = plan.metadata["policy_result"]
    score_stats = _score_stats(score_result)

    execution_summary: dict[str, Any] | None = None
    if not args.no_execute:
        if not args.json_only:
            _log_step(
                6,
                7,
                "Execute selected action chunk in local mock world",
                [("selected actions", len(plan.actions)), ("execution provider", "mock")],
                color=color_enabled,
            )
        execution = world.execute_plan(plan, provider="mock")
        final_world = execution.final_world()
        final_block = final_world.get_object_by_id(block.id)
        execution_summary = {
            "actions_applied": len(execution.actions_applied),
            "final_step": final_world.step,
            "final_block_position": (
                final_block.position.to_dict() if final_block is not None else None
            ),
        }
    elif not args.json_only:
        _log_step(
            6,
            7,
            "Skip local mock execution",
            [("selected actions", len(plan.actions))],
            color=color_enabled,
        )

    total_latency_ms = (perf_counter() - total_started) * 1000
    if not args.json_only:
        _log_step(
            7,
            7,
            "Rank action candidates and collect metrics",
            [
                ("candidate count", plan.metadata.get("candidate_count")),
                ("best index", score_result.get("best_index")),
                ("best score", score_result.get("best_score")),
                (
                    "policy latency ms",
                    _event_latency(_event_dicts(provider_events), "lerobot", "policy"),
                ),
                ("plan latency ms", f"{plan_latency_ms:.2f}"),
                ("total latency ms", f"{total_latency_ms:.2f}"),
            ],
            color=color_enabled,
        )

    score_shapes = _input_shape_summary(score_info, score_action_candidates)
    score_shape_values = _input_shapes(score_info, score_action_candidates)
    input_stats = _input_stats(score_shape_values)
    event_payload = _event_dicts(provider_events)
    candidate_targets = _candidate_targets(policy_result)
    payload = {
        "mode": "real_lerobot_policy_plus_real_leworldmodel_score",
        "task": args.task,
        "checkpoint": str(object_path),
        "checkpoint_display": _display_path(object_path),
        "state_dir": str(state_dir),
        "health": {"lerobot": policy_health, "leworldmodel": score_health},
        "inputs": {
            "policy_path": args.policy_path,
            "policy_type": args.policy_type,
            "lerobot_device": lerobot_device,
            "leworldmodel_policy": args.lewm_policy,
            "leworldmodel_device": lewm_device,
            "score_shapes": score_shape_values,
            **input_stats,
            "score_action_candidates_shape": _shape_tuple(score_action_candidates),
        },
        "plan": plan.to_dict(),
        "policy_result": policy_result,
        "score_result": score_result,
        "score_stats": score_stats,
        "execution": execution_summary,
        "provider_events": event_payload,
        "visualization": {
            "candidate_targets": candidate_targets,
            "selected_candidate": score_result.get("best_index"),
        },
        "metrics": {
            "plan_latency_ms": plan_latency_ms,
            "total_latency_ms": total_latency_ms,
        },
    }
    json_output_path = _write_json_output(args.json_output, payload) if args.json_output else None
    run_manifest_path = None
    if args.run_manifest is not None:
        artifact_paths: dict[str, Path | str] = {"worldforge_state": state_dir}
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
        run_manifest_path = write_run_manifest(
            args.run_manifest,
            build_run_manifest(
                run_id=args.run_manifest.parent.name,
                provider_profile="lerobot-leworldmodel",
                capability="policy+score",
                status="passed",
                env_vars=(
                    "LEROBOT_POLICY_PATH",
                    "LEROBOT_POLICY",
                    "LEROBOT_POLICY_TYPE",
                    "LEROBOT_DEVICE",
                    "LEROBOT_CACHE_DIR",
                    "LEWORLDMODEL_CHECKPOINT",
                    "LEWORLDMODEL_POLICY",
                    "LEWM_POLICY",
                    "LEWORLDMODEL_DEVICE",
                    "STABLEWM_HOME",
                ),
                event_count=len(event_payload),
                input_fixture=input_fixture,
                result=payload,
                artifact_paths=artifact_paths,
            ),
        )
    if args.json_only:
        print(json.dumps(payload, indent=2, sort_keys=True))
        return 0

    print("\nScore tensor shapes")
    print("-------------------")
    for label, shape in score_shapes.items():
        print(f"  {label:<22} {shape}")
    print(f"  {'tensor elements':<22} {input_stats['total_tensor_elements']}")
    print(f"  {'approx float32 MB':<22} {input_stats['approx_float32_mb']}")
    _print_runtime_profile(
        events=event_payload,
        plan_latency_ms=plan_latency_ms,
        total_latency_ms=total_latency_ms,
        color=color_enabled,
    )
    _print_score_summary(score_stats)
    print("\nCandidate cost landscape")
    print("------------------------")
    for line in _score_chart(score_result, color=color_enabled):
        print(line)
    printed_targets = _print_candidate_targets(
        policy_result=policy_result,
        score_result=score_result,
        color=color_enabled,
    )
    _print_tabletop_replay(
        targets=printed_targets,
        score_result=score_result,
        execution_summary=execution_summary,
    )
    print("\nSelected plan")
    print("-------------")
    print(f"  selected candidate     #{score_result.get('best_index')}")
    print(f"  selected actions       {len(plan.actions)}")
    print(f"  success heuristic      {plan.success_probability:.6f}")
    if execution_summary is not None:
        print(f"  mock final step        {execution_summary['final_step']}")
        print(f"  mock final block       {execution_summary['final_block_position']}")
    _print_provider_events(event_payload)
    if json_output_path is not None:
        print("\nArtifacts")
        print("---------")
        print(f"  json summary           {_display_path(json_output_path)}")
        if run_manifest_path is not None:
            print(f"  run manifest           {_display_path(run_manifest_path)}")
    print("\nCompleted real LeRobot + LeWorldModel policy+score inference.")
    print("Use --json-only for the machine-readable summary.")
    return 0


def _event_latency(events: list[dict[str, Any]], provider: str, operation: str) -> str:
    for event in reversed(events):
        if event.get("provider") == provider and event.get("operation") == operation:
            duration = event.get("duration_ms")
            if duration is not None:
                return f"{float(duration):.2f}"
    return "n/a"


if __name__ == "__main__":
    raise SystemExit(main())

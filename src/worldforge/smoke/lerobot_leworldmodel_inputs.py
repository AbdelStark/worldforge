"""Input loading helpers for the LeRobot plus LeWorldModel smoke runner."""

from __future__ import annotations

import argparse
import importlib
import importlib.util
import json
from collections.abc import Callable, Sequence
from pathlib import Path
from types import ModuleType
from typing import Any

from worldforge.smoke.lerobot_leworldmodel_bridge import _materialize_candidate_payload


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
    module_ref, function_name = _callable_spec_parts(spec, name=name)
    module = _module_from_ref(module_ref, name=name)
    loaded = _module_attribute(module, function_name=function_name, name=name)
    if not callable(loaded):
        raise SystemExit(f"{name} target '{function_name}' is not callable.")
    return loaded


def _callable_spec_parts(spec: str, *, name: str) -> tuple[str, str]:
    if ":" not in spec:
        raise SystemExit(f"{name} must be formatted as module_or_file:function.")
    module_ref, function_name = spec.rsplit(":", 1)
    if not module_ref.strip() or not function_name.strip():
        raise SystemExit(f"{name} must be formatted as module_or_file:function.")
    return module_ref, function_name


def _module_from_ref(module_ref: str, *, name: str) -> ModuleType:
    candidate_path = Path(module_ref)
    if _looks_like_module_path(module_ref, candidate_path):
        return _module_from_path(candidate_path)
    try:
        return importlib.import_module(module_ref)
    except ImportError as exc:
        raise SystemExit(f"Could not import {name} module '{module_ref}': {exc}") from exc


def _looks_like_module_path(module_ref: str, candidate_path: Path) -> bool:
    return candidate_path.exists() or module_ref.endswith(".py") or "/" in module_ref


def _module_attribute(module: ModuleType, *, function_name: str, name: str) -> object:
    try:
        return getattr(module, function_name)
    except AttributeError as exc:
        raise SystemExit(f"{name} function '{function_name}' was not found.") from exc


def _load_policy_info(args: argparse.Namespace) -> dict[str, Any]:
    info = _base_policy_info(args)
    _apply_policy_info_overrides(info, args)
    _apply_policy_info_score_bridge_defaults(info, args)
    return info


def _base_policy_info(args: argparse.Namespace) -> dict[str, Any]:
    if args.policy_info_json is not None:
        return _json_object_from_file(args.policy_info_json, name="policy-info")
    if args.observation_json is not None:
        return {"observation": _json_object_from_file(args.observation_json, name="observation")}
    if args.observation_module is not None:
        return _policy_info_from_observation_module(args.observation_module)
    raise SystemExit(
        "Real LeRobot+LeWorldModel flow requires --policy-info-json, "
        "--observation-json, or --observation-module."
    )


def _policy_info_from_observation_module(module_spec: str) -> dict[str, Any]:
    factory = _load_callable(module_spec, name="observation factory")
    try:
        produced = factory()
    except Exception as exc:
        raise SystemExit(f"Observation factory failed: {exc}") from exc
    if not isinstance(produced, dict):
        raise SystemExit("Observation factory must return a dictionary.")
    return _policy_info_from_observation_payload(produced)


def _policy_info_from_observation_payload(payload: dict[str, Any]) -> dict[str, Any]:
    if "observation" in payload:
        return dict(payload)
    return {"observation": dict(payload)}


def _apply_policy_info_overrides(info: dict[str, Any], args: argparse.Namespace) -> None:
    if args.options_json is not None:
        info["options"] = _json_object_from_file(args.options_json, name="options")
    if args.embodiment_tag is not None:
        info.setdefault("embodiment_tag", args.embodiment_tag)
    if args.action_horizon is not None:
        info["action_horizon"] = args.action_horizon
    if args.mode is not None:
        info["mode"] = args.mode


def _apply_policy_info_score_bridge_defaults(
    info: dict[str, Any],
    args: argparse.Namespace,
) -> None:
    info.setdefault("score_bridge", {})
    if isinstance(info["score_bridge"], dict):
        info["score_bridge"].setdefault("task", "pusht")
        if args.expected_action_dim is not None:
            info["score_bridge"]["expected_action_dim"] = args.expected_action_dim
        if args.expected_horizon is not None:
            info["score_bridge"]["expected_horizon"] = args.expected_horizon


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


def _load_static_action_candidates(args: argparse.Namespace) -> object | None:
    if args.action_candidates_json is not None:
        payload = _load_json_file(args.action_candidates_json, name="action-candidates")
        return _materialize_candidate_payload(payload)
    if args.action_candidates_npz is not None:
        key = args.action_candidates_key
        loaded = _load_npz_map(args.action_candidates_npz, keys=(key,), name="action-candidates")
        return loaded[key]
    return None

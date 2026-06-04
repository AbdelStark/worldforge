"""Input loading helpers for the LeRobot plus LeWorldModel smoke runner."""

from __future__ import annotations

import argparse
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

from worldforge.smoke.lerobot_leworldmodel_bridge import _materialize_candidate_payload
from worldforge.smoke.trusted_inputs import (
    load_callable as _trusted_load_callable,
)
from worldforge.smoke.trusted_inputs import (
    load_json_file as _trusted_load_json_file,
)
from worldforge.smoke.trusted_inputs import (
    load_json_object as _trusted_load_json_object,
)
from worldforge.smoke.trusted_inputs import (
    module_from_path as _trusted_module_from_path,
)


def _load_json_file(path: Path, *, name: str) -> object:
    return _trusted_load_json_file(path, name=name)


def _json_object_from_file(path: Path, *, name: str) -> dict[str, Any]:
    return _trusted_load_json_object(path, name=name)


def _module_from_path(path: Path):
    return _trusted_module_from_path(path)


def _load_callable(spec: str, *, name: str) -> Callable[..., Any]:
    return _trusted_load_callable(spec, name=name)


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

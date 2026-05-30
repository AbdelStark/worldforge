"""Action bridge helpers for the LeRobot plus LeWorldModel smoke runner."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Any

from worldforge import Action


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

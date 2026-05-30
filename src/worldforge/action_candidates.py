"""Provider-agnostic helpers for building score and policy+score action candidates."""

from __future__ import annotations

from collections.abc import Sequence
from typing import cast

from worldforge.models import (
    Action,
    JSONDict,
    Position,
    WorldForgeError,
    require_finite_number,
    require_positive_int,
)

ActionCandidatePlan = list[Action]
ActionCandidatePlans = list[ActionCandidatePlan]


def normalize_action_candidates(
    candidate_actions: Sequence[Action | Sequence[Action]],
) -> ActionCandidatePlans:
    """Return candidate actions as validated action-plan lists."""

    if not _is_sequence(candidate_actions) or not candidate_actions:
        raise WorldForgeError("candidate_actions must be a non-empty sequence.")
    return [
        _normalize_action_candidate(candidate, index=index)
        for index, candidate in enumerate(candidate_actions)
    ]


def action_candidates_to_score_payload(
    candidate_actions: Sequence[Action | Sequence[Action]],
) -> list[list[JSONDict]]:
    """Serialize validated action candidates for provider-agnostic score calls."""

    return [
        [action.to_dict() for action in plan]
        for plan in normalize_action_candidates(candidate_actions)
    ]


def cartesian_offset_candidates(
    origin: Position,
    offsets: Sequence[Position | Sequence[Position]],
    *,
    object_id: str | None = None,
    speed: float = 1.0,
) -> ActionCandidatePlans:
    """Build move candidates by applying Cartesian offsets to an origin position.

    Each offset can be a single :class:`Position` delta or a non-empty sequence of deltas for a
    multi-step candidate plan.
    """

    _require_position(origin, name="origin")
    resolved_speed = _validate_speed(speed)
    plans: ActionCandidatePlans = []
    for candidate_index, offset_plan in enumerate(_normalize_offset_plans(offsets)):
        plan: ActionCandidatePlan = []
        for offset_index, offset in enumerate(offset_plan):
            _require_position(
                offset,
                name=f"offsets[{candidate_index}][{offset_index}]",
            )
            plan.append(
                Action.move_to(
                    origin.x + offset.x,
                    origin.y + offset.y,
                    origin.z + offset.z,
                    speed=resolved_speed,
                    object_id=object_id,
                )
            )
        plans.append(plan)
    return plans


def object_near_candidates(
    reference_position: Position,
    offsets: Sequence[Position | Sequence[Position]],
    *,
    object_id: str | None = None,
    speed: float = 1.0,
) -> ActionCandidatePlans:
    """Build move candidates that place an object near a reference position."""

    return cartesian_offset_candidates(
        reference_position,
        offsets,
        object_id=object_id,
        speed=speed,
    )


def swap_action_candidates(
    *,
    first_object_id: str,
    first_position: Position,
    second_object_id: str,
    second_position: Position,
    speed: float = 1.0,
) -> ActionCandidatePlans:
    """Return direct two-action swap candidates in both execution orders."""

    first_id = _required_text(first_object_id, name="first_object_id")
    second_id = _required_text(second_object_id, name="second_object_id")
    if first_id == second_id:
        raise WorldForgeError("swap_action_candidates object ids must be distinct.")
    _require_position(first_position, name="first_position")
    _require_position(second_position, name="second_position")
    resolved_speed = _validate_speed(speed)
    first_to_second = Action.move_to(
        second_position.x,
        second_position.y,
        second_position.z,
        speed=resolved_speed,
        object_id=first_id,
    )
    second_to_first = Action.move_to(
        first_position.x,
        first_position.y,
        first_position.z,
        speed=resolved_speed,
        object_id=second_id,
    )
    return [[first_to_second, second_to_first], [second_to_first, first_to_second]]


def bounded_move_grid_candidates(
    *,
    x_bounds: Sequence[float],
    y_bounds: Sequence[float],
    z_bounds: Sequence[float],
    x_steps: int,
    y_steps: int,
    z_steps: int,
    object_id: str | None = None,
    speed: float = 1.0,
) -> ActionCandidatePlans:
    """Build one-step move candidates over an inclusive bounded Cartesian grid."""

    x_values = _linspace(_bounds(x_bounds, name="x_bounds"), x_steps, name="x_steps")
    y_values = _linspace(_bounds(y_bounds, name="y_bounds"), y_steps, name="y_steps")
    z_values = _linspace(_bounds(z_bounds, name="z_bounds"), z_steps, name="z_steps")
    resolved_speed = _validate_speed(speed)
    return [
        [
            Action.move_to(
                x,
                y,
                z,
                speed=resolved_speed,
                object_id=object_id,
            )
        ]
        for x in x_values
        for y in y_values
        for z in z_values
    ]


def _normalize_offset_plans(
    offsets: Sequence[Position | Sequence[Position]],
) -> list[list[Position]]:
    if not _is_sequence(offsets) or not offsets:
        raise WorldForgeError("offsets must be a non-empty sequence.")
    return [_normalize_offset_plan(item, index=index) for index, item in enumerate(offsets)]


def _normalize_action_candidate(
    candidate: Action | Sequence[Action],
    *,
    index: int,
) -> ActionCandidatePlan:
    return _normalize_single_or_plan(
        candidate,
        item_type=Action,
        collection_name="candidate_actions",
        item_name="Action",
        index=index,
    )


def _normalize_offset_plan(
    item: Position | Sequence[Position],
    *,
    index: int,
) -> list[Position]:
    return _normalize_single_or_plan(
        item,
        item_type=Position,
        collection_name="offsets",
        item_name="Position",
        index=index,
    )


def _normalize_single_or_plan[T](
    value: T | Sequence[T],
    *,
    item_type: type[T],
    collection_name: str,
    item_name: str,
    index: int,
) -> list[T]:
    single_item = _single_typed_item(value, item_type)
    if single_item is not None:
        return single_item
    items = _require_non_empty_sequence(
        value,
        message=(
            f"{collection_name}[{index}] must be a {item_name} "
            f"or non-empty sequence of {item_name}s."
        ),
    )
    return _require_typed_items(
        items,
        item_type=item_type,
        message=f"{collection_name}[{index}] must contain only {item_name} instances.",
    )


def _single_typed_item[T](value: object, item_type: type[T]) -> list[T] | None:
    if isinstance(value, item_type):
        return [value]
    return None


def _require_non_empty_sequence(value: object, *, message: str) -> Sequence[object]:
    if not _is_sequence(value) or not value:
        raise WorldForgeError(message)
    return cast(Sequence[object], value)


def _require_typed_items[T](
    values: Sequence[object],
    *,
    item_type: type[T],
    message: str,
) -> list[T]:
    items = list(values)
    if not all(isinstance(item, item_type) for item in items):
        raise WorldForgeError(message)
    return cast(list[T], items)


def _bounds(value: Sequence[float], *, name: str) -> tuple[float, float]:
    lower_value, upper_value = _bounds_pair(value, name=name)
    return _ordered_bounds(
        require_finite_number(lower_value, name=f"{name}[0]"),
        require_finite_number(upper_value, name=f"{name}[1]"),
        name=name,
    )


def _bounds_pair(value: object, *, name: str) -> tuple[object, object]:
    if not _is_sequence(value) or len(value) != 2:
        raise WorldForgeError(f"{name} must contain exactly two finite numbers.")
    return value[0], value[1]


def _ordered_bounds(lower: float, upper: float, *, name: str) -> tuple[float, float]:
    if lower > upper:
        raise WorldForgeError(f"{name} lower bound must be less than or equal to upper bound.")
    return lower, upper


def _linspace(bounds: tuple[float, float], steps: int, *, name: str) -> list[float]:
    count = require_positive_int(steps, name=name)
    lower, upper = bounds
    if count == 1:
        return [(lower + upper) / 2]
    stride = (upper - lower) / (count - 1)
    return [lower + stride * index for index in range(count)]


def _validate_speed(speed: float) -> float:
    resolved_speed = require_finite_number(speed, name="candidate speed")
    if resolved_speed <= 0.0:
        raise WorldForgeError("candidate speed must be greater than 0.")
    return resolved_speed


def _required_text(value: str, *, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise WorldForgeError(f"{name} must be a non-empty string.")
    return value.strip()


def _require_position(value: Position, *, name: str) -> Position:
    if not isinstance(value, Position):
        raise WorldForgeError(f"{name} must be a Position.")
    return value


def _is_sequence(value: object) -> bool:
    return isinstance(value, Sequence) and not isinstance(value, str | bytes)

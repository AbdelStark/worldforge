"""Goal-to-action resolution helpers for ``World.plan``.

This module is intentionally provider-free: it translates public text and structured goals into
bounded action lists against a scene snapshot. Provider selection, scoring, and prediction stay in
``_world.py`` and ``_planning.py``.
"""

from __future__ import annotations

from collections.abc import Mapping

from worldforge._planning import ResolvedPlanGoal, bounded_plan_actions
from worldforge.models import Action, Position, SceneObject, StructuredGoal, WorldForgeError

_TEXT_GOAL_DEFAULT_OBJECT = "cube"
_TEXT_GOAL_OBJECT_NAMES = ("cube", "ball", "block", "mug")
_TEXT_GOAL_RIGHT_OFFSET = Position(1.0, 0.0, 0.0)
_TEXT_GOAL_DISHWASHER_OFFSET = Position(0.8, 0.0, -0.4)
_TEXT_GOAL_DEFAULT_MOVE_OFFSET = Position(0.3, 0.0, 0.0)


def resolve_plan_goal(
    scene_objects: Mapping[str, SceneObject],
    *,
    goal: str | None,
    goal_spec: StructuredGoal | None,
    goal_json: str | None,
    max_steps: int,
) -> ResolvedPlanGoal:
    validate_plan_goal_inputs(goal=goal, goal_spec=goal_spec, goal_json=goal_json)
    resolved_goal_spec = plan_goal_spec(goal_spec=goal_spec, goal_json=goal_json)
    if resolved_goal_spec is not None:
        return resolve_structured_plan_goal(
            scene_objects,
            resolved_goal_spec,
            max_steps=max_steps,
        )
    if goal is None:
        raise WorldForgeError("plan() requires goal, goal_json, or goal_spec.")
    return resolve_text_plan_goal(scene_objects, goal, max_steps=max_steps)


def validate_plan_goal_inputs(
    *,
    goal: str | None,
    goal_spec: StructuredGoal | None,
    goal_json: str | None,
) -> None:
    for message in (
        _optional_input_type_error("goal", goal, str, "a string"),
        _blank_goal_error(goal),
        _optional_input_type_error(
            "goal_spec",
            goal_spec,
            StructuredGoal,
            "a StructuredGoal",
        ),
        _optional_input_type_error("goal_json", goal_json, str, "a string"),
        _structured_goal_conflict_error(goal_spec=goal_spec, goal_json=goal_json),
    ):
        if message is not None:
            raise WorldForgeError(message)


def plan_goal_spec(
    *,
    goal_spec: StructuredGoal | None,
    goal_json: str | None,
) -> StructuredGoal | None:
    if goal_json is None:
        return goal_spec
    return StructuredGoal.from_json(goal_json)


def resolve_structured_plan_goal(
    scene_objects: Mapping[str, SceneObject],
    goal_spec: StructuredGoal,
    *,
    max_steps: int,
) -> ResolvedPlanGoal:
    actions = actions_for_goal_spec(scene_objects, goal_spec)
    return ResolvedPlanGoal(
        goal=goal_spec.summary(),
        goal_spec=goal_spec.to_dict(),
        actions=bounded_plan_actions(actions, max_steps=max_steps),
    )


def resolve_text_plan_goal(
    scene_objects: Mapping[str, SceneObject],
    goal: str,
    *,
    max_steps: int,
) -> ResolvedPlanGoal:
    actions = goal_actions(scene_objects, goal)
    return ResolvedPlanGoal(
        goal=goal,
        goal_spec=None,
        actions=bounded_plan_actions(actions, max_steps=max_steps),
    )


def actions_for_goal_spec(
    scene_objects: Mapping[str, SceneObject],
    goal_spec: StructuredGoal,
) -> list[Action]:
    if goal_spec.kind == "object_at":
        return _object_at_actions_for_goal(scene_objects, goal_spec)
    if goal_spec.kind == "spawn_object":
        return _spawn_actions_for_goal(goal_spec)
    if goal_spec.kind == "object_near":
        return _object_near_actions_for_goal(scene_objects, goal_spec)
    if goal_spec.kind == "swap_objects":
        return _swap_actions_for_goal(scene_objects, goal_spec)
    raise WorldForgeError(f"Unsupported structured goal kind '{goal_spec.kind}'.")


def goal_actions(scene_objects: Mapping[str, SceneObject], goal: str) -> list[Action]:
    lowered = goal.lower()
    if "spawn" in lowered:
        return [Action.spawn_object(_text_goal_spawn_object_name(lowered))]
    if not scene_objects:
        return [Action.spawn_object(_TEXT_GOAL_DEFAULT_OBJECT)]
    primary = next(iter(scene_objects.values()))
    return [_text_goal_move_action(primary.position, lowered)]


def _object_at_actions_for_goal(
    scene_objects: Mapping[str, SceneObject],
    goal_spec: StructuredGoal,
) -> list[Action]:
    target_object = _resolve_goal_object(
        scene_objects,
        object_id=goal_spec.object_id,
        object_name=goal_spec.object_name,
        label="object",
    )
    return [_move_action_for_object(target_object, _require_goal_position(goal_spec))]


def _spawn_actions_for_goal(goal_spec: StructuredGoal) -> list[Action]:
    return [
        Action.spawn_object(
            _require_spawn_object_name(goal_spec),
            position=goal_spec.position,
        )
    ]


def _object_near_actions_for_goal(
    scene_objects: Mapping[str, SceneObject],
    goal_spec: StructuredGoal,
) -> list[Action]:
    target_object, reference_object = _resolve_goal_object_pair(scene_objects, goal_spec)
    target_position = _offset_position(reference_object.position, _require_goal_offset(goal_spec))
    return [_move_action_for_object(target_object, target_position)]


def _swap_actions_for_goal(
    scene_objects: Mapping[str, SceneObject],
    goal_spec: StructuredGoal,
) -> list[Action]:
    target_object, reference_object = _resolve_goal_object_pair(scene_objects, goal_spec)
    return [
        _move_action_for_object(target_object, reference_object.position),
        _move_action_for_object(reference_object, target_object.position),
    ]


def _resolve_goal_object(
    scene_objects: Mapping[str, SceneObject],
    *,
    object_id: str | None,
    object_name: str | None,
    label: str,
) -> SceneObject:
    if object_id:
        return _resolve_goal_object_by_id(
            scene_objects,
            object_id=object_id,
            object_name=object_name,
            label=label,
        )
    return _resolve_goal_object_by_name(scene_objects, object_name=object_name, label=label)


def _resolve_goal_object_by_id(
    scene_objects: Mapping[str, SceneObject],
    *,
    object_id: str,
    object_name: str | None,
    label: str,
) -> SceneObject:
    scene_object = _goal_scene_object_by_id(scene_objects, object_id=object_id, label=label)
    _require_goal_object_name_match(
        scene_object,
        object_name=object_name,
        label=label,
    )
    return scene_object.copy()


def _goal_scene_object_by_id(
    scene_objects: Mapping[str, SceneObject],
    *,
    object_id: str,
    label: str,
) -> SceneObject:
    scene_object = scene_objects.get(object_id)
    if scene_object is None:
        raise WorldForgeError(f"Structured goal references missing {label} id '{object_id}'.")
    return scene_object


def _require_goal_object_name_match(
    scene_object: SceneObject,
    *,
    object_name: str | None,
    label: str,
) -> None:
    if object_name and scene_object.name != object_name:
        raise WorldForgeError(
            f"Structured goal {label} id/name selectors do not match the same object."
        )


def _resolve_goal_object_by_name(
    scene_objects: Mapping[str, SceneObject],
    *,
    object_name: str | None,
    label: str,
) -> SceneObject:
    matches = [
        scene_object.copy()
        for scene_object in scene_objects.values()
        if scene_object.name == object_name
    ]
    if not matches:
        raise WorldForgeError(f"Structured goal references unknown {label} name '{object_name}'.")
    if len(matches) > 1:
        raise WorldForgeError(
            f"Structured goal {label} name '{object_name}' is ambiguous; use object_id instead."
        )
    return matches[0]


def _resolve_goal_object_pair(
    scene_objects: Mapping[str, SceneObject],
    goal_spec: StructuredGoal,
) -> tuple[SceneObject, SceneObject]:
    target_object = _resolve_goal_object(
        scene_objects,
        object_id=goal_spec.object_id,
        object_name=goal_spec.object_name,
        label="object",
    )
    reference_object = _resolve_goal_object(
        scene_objects,
        object_id=goal_spec.reference_object_id,
        object_name=goal_spec.reference_object_name,
        label="reference object",
    )
    _require_distinct_goal_objects(
        goal_kind=goal_spec.kind,
        target_object=target_object,
        reference_object=reference_object,
    )
    return target_object, reference_object


def _optional_input_type_error(
    name: str,
    value: object,
    expected_type: type[object],
    expected_label: str,
) -> str | None:
    if value is None or isinstance(value, expected_type):
        return None
    return f"{name} must be {expected_label} when provided."


def _blank_goal_error(goal: object) -> str | None:
    if isinstance(goal, str) and not goal.strip():
        return "goal must not be empty when provided."
    return None


def _structured_goal_conflict_error(
    *,
    goal_spec: object,
    goal_json: object,
) -> str | None:
    if goal_json is not None and goal_spec is not None:
        return "plan() accepts at most one of goal_json or goal_spec."
    return None


def _require_goal_position(goal_spec: StructuredGoal) -> Position:
    position = goal_spec.position
    if position is None:
        raise WorldForgeError(f"Structured goal {goal_spec.kind!r} must carry a non-null position.")
    return position


def _require_goal_offset(goal_spec: StructuredGoal) -> Position:
    offset = goal_spec.offset
    if offset is None:
        raise WorldForgeError(f"Structured goal {goal_spec.kind} must carry a non-null offset.")
    return offset


def _require_spawn_object_name(goal_spec: StructuredGoal) -> str:
    object_name = goal_spec.object_name
    if not object_name:
        raise WorldForgeError("Structured goal spawn_object must carry a non-empty object_name.")
    return object_name


def _move_action_for_object(scene_object: SceneObject, position: Position) -> Action:
    return Action.move_to(
        position.x,
        position.y,
        position.z,
        object_id=scene_object.id,
    )


def _require_distinct_goal_objects(
    *,
    goal_kind: str,
    target_object: SceneObject,
    reference_object: SceneObject,
) -> None:
    if reference_object.id == target_object.id:
        raise WorldForgeError(
            f"Structured goal {goal_kind} requires distinct primary and reference objects."
        )


def _offset_position(base: Position, offset: Position) -> Position:
    return Position(base.x + offset.x, base.y + offset.y, base.z + offset.z)


def _text_goal_spawn_object_name(lowered_goal: str) -> str:
    return next(
        (candidate for candidate in _TEXT_GOAL_OBJECT_NAMES if candidate in lowered_goal),
        _TEXT_GOAL_DEFAULT_OBJECT,
    )


def _text_goal_move_offset(lowered_goal: str) -> Position:
    if "right" in lowered_goal:
        return _TEXT_GOAL_RIGHT_OFFSET
    if "dishwasher" in lowered_goal:
        return _TEXT_GOAL_DISHWASHER_OFFSET
    return _TEXT_GOAL_DEFAULT_MOVE_OFFSET


def _text_goal_move_action(origin: Position, lowered_goal: str) -> Action:
    target = _offset_position(origin, _text_goal_move_offset(lowered_goal))
    return Action.move_to(target.x, target.y, target.z)

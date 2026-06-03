"""Packaged demo entry points for WorldForge.

The demos share a single deterministic tabletop scenario — a ``blue_cube`` placed at
``(0, 0.5, 0)`` with a goal at ``(0.55, 0.5, 0)`` and three two-step candidate action
chunks. The helpers below keep that scenario in one place so the LeWorldModel and
LeRobot demos stay in sync.

The demos drive the WorldForge capability surface directly — ``forge.predict``,
``forge.score_actions``, ``forge.select_actions`` — instead of the symbolic ``World``
runtime. ``make_blue_cube`` returns a standalone :class:`SceneObject` with a stable id
so candidate plans and seeded world-state dicts can reference it deterministically.
"""

from __future__ import annotations

from worldforge import Action, BBox, Position, SceneObject, WorldForge
from worldforge.action_candidates import cartesian_offset_candidates
from worldforge.models import JSONDict

BLUE_CUBE_ID = "blue_cube"
_BLUE_CUBE_START = Position(0.0, 0.5, 0.0)
_BLUE_CUBE_BBOX = BBox(Position(-0.05, 0.45, -0.05), Position(0.05, 0.55, 0.05))
BLUE_CUBE_GOAL = Position(0.55, 0.50, 0.00)
BLUE_CUBE_TOLERANCE = 0.05


def make_blue_cube() -> SceneObject:
    """Return the shared ``blue_cube`` scene object with a stable id.

    The object is standalone — it is not bound to a :class:`World`. Demos use its id when
    building candidate plans and when seeding a plain world-state dict for ``forge.predict``.
    """

    return SceneObject(BLUE_CUBE_ID, _BLUE_CUBE_START, _BLUE_CUBE_BBOX, id=BLUE_CUBE_ID)


def blue_cube_goal(cube: SceneObject) -> JSONDict:
    """Return the shared ``object_at`` goal dict for the blue cube.

    The goal is a plain JSON-serializable descriptor (there is no symbolic ``World`` runtime or
    structured-goal model): demos and host examples cite it in their planning summaries.
    """

    return {
        "kind": "object_at",
        "object": {"id": cube.id, "name": cube.name},
        "position": BLUE_CUBE_GOAL.to_dict(),
        "tolerance": BLUE_CUBE_TOLERANCE,
    }


def make_candidate_plans(cube_id: str) -> list[list[Action]]:
    """Return the three two-step PushT candidate plans used by the demos."""

    return cartesian_offset_candidates(
        _BLUE_CUBE_START,
        [
            [Position(0.20, 0.00, 0.00), Position(0.35, 0.00, 0.00)],
            [Position(0.30, 0.00, 0.00), Position(0.55, 0.00, 0.00)],
            [Position(0.70, 0.00, 0.00), Position(0.95, 0.00, 0.00)],
        ],
        object_id=cube_id,
    )


def seed_world_state(objects: list[SceneObject]) -> JSONDict:
    """Return a plain world-state dict seeded with ``objects`` for ``forge.predict``.

    Mirrors the shape the mock provider mutates: ``{"step", "scene": {"objects": {...}}}``.
    """

    return {
        "step": 0,
        "scene": {"objects": {scene_object.id: scene_object.to_dict() for scene_object in objects}},
    }


def execute_plan_over_state(
    forge: WorldForge,
    world_state: JSONDict,
    actions: list[Action],
    *,
    provider: str = "mock",
) -> JSONDict:
    """Roll ``actions`` through ``forge.predict`` and return the final world-state dict.

    This is the capability-surface equivalent of executing a plan: each action is predicted
    in turn against a plain world-state dict, with the mock provider mutating object poses.
    """

    state = world_state
    for action in actions:
        state = forge.predict(state, action, 1, provider=provider).state
    return state


def object_position(world_state: JSONDict, object_id: str) -> JSONDict | None:
    """Return the position dict of ``object_id`` in ``world_state`` if present."""

    objects = world_state.get("scene", {}).get("objects", {})
    scene_object = objects.get(object_id)
    if not isinstance(scene_object, dict):
        return None
    position = scene_object.get("pose", {}).get("position")
    return dict(position) if isinstance(position, dict) else None

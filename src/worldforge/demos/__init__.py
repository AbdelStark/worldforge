"""Packaged demo entry points for WorldForge.

The demos share a single deterministic tabletop scenario — a ``blue_cube`` placed at
``(0, 0.5, 0)`` with a goal at ``(0.55, 0.5, 0)`` and three two-step candidate action
chunks. The helpers below keep that scenario in one place so the LeWorldModel and
LeRobot demos stay in sync.
"""

from __future__ import annotations

from worldforge import Action, BBox, Position, SceneObject, StructuredGoal
from worldforge.action_candidates import cartesian_offset_candidates

_BLUE_CUBE_START = Position(0.0, 0.5, 0.0)
_BLUE_CUBE_BBOX = BBox(Position(-0.05, 0.45, -0.05), Position(0.05, 0.55, 0.05))
BLUE_CUBE_GOAL = Position(0.55, 0.50, 0.00)
BLUE_CUBE_TOLERANCE = 0.05


def make_blue_cube(world: object) -> SceneObject:
    """Add the shared ``blue_cube`` scene object to ``world`` and return it."""

    return world.add_object(  # type: ignore[attr-defined]
        SceneObject("blue_cube", _BLUE_CUBE_START, _BLUE_CUBE_BBOX)
    )


def blue_cube_goal(cube: SceneObject) -> StructuredGoal:
    """Return the shared ``object_at`` goal for the blue cube."""

    return StructuredGoal.object_at(
        object_id=cube.id,
        object_name=cube.name,
        position=BLUE_CUBE_GOAL,
        tolerance=BLUE_CUBE_TOLERANCE,
    )


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

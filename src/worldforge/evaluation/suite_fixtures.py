"""Shared deterministic fixtures for built-in evaluation suites."""

from __future__ import annotations

from typing import TYPE_CHECKING

from worldforge.models import BBox, Position, SceneObject

if TYPE_CHECKING:
    from worldforge.framework import World


def seed_object(world: World, name: str, position: Position) -> SceneObject:
    existing = next((obj for obj in world.objects() if obj.name == name), None)
    if existing is not None:
        return existing
    obj = SceneObject(
        name,
        position,
        BBox(
            Position(position.x - 0.05, position.y - 0.05, position.z - 0.05),
            Position(position.x + 0.05, position.y + 0.05, position.z + 0.05),
        ),
        is_graspable=True,
    )
    world.add_object(obj)
    return obj


_seed_object = seed_object

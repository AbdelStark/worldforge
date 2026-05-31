"""Shared deterministic fixtures for built-in evaluation suites."""

from __future__ import annotations

from typing import TYPE_CHECKING

from worldforge.models import BBox, Position, SceneObject, VideoClip

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


SAMPLE_IMAGE_DATA_URI = (
    "data:image/png;base64,"
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jq5kAAAAASUVORK5CYII="
)


def sample_transfer_clip() -> VideoClip:
    return VideoClip(
        frames=[b"worldforge-transfer-seed"],
        fps=8.0,
        resolution=(160, 90),
        duration_seconds=1.0,
        metadata={
            "provider": "worldforge",
            "content_type": "video/mp4",
            "mode": "evaluation-seed",
        },
    )


_seed_object = seed_object
_SAMPLE_IMAGE_DATA_URI = SAMPLE_IMAGE_DATA_URI
_sample_transfer_clip = sample_transfer_clip

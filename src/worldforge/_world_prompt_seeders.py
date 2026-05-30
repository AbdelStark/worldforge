"""Prompt-derived local seed scenes for ``WorldForge.create_world_from_prompt``."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import TYPE_CHECKING

from worldforge.models import BBox, Position, SceneObject

if TYPE_CHECKING:
    from worldforge._world import World

PromptMatcher = Callable[[str], bool]
PromptSeeder = Callable[["World"], None]


def _seed_kitchen(world: World) -> None:
    world.add_object(
        SceneObject(
            "countertop",
            Position(0.0, 0.9, 0.0),
            BBox(Position(-1.0, 0.85, -0.5), Position(1.0, 0.95, 0.5)),
        )
    )


def _seed_mug(world: World) -> None:
    world.add_object(
        SceneObject(
            "mug",
            Position(0.0, 0.8, 0.0),
            BBox(Position(-0.05, 0.75, -0.05), Position(0.05, 0.85, 0.05)),
            is_graspable=True,
        )
    )


def _seed_default_cube(world: World) -> None:
    world.add_object(
        SceneObject(
            "cube",
            Position(0.0, 0.5, 0.0),
            BBox(Position(-0.05, 0.45, -0.05), Position(0.05, 0.55, 0.05)),
        )
    )


def _prompt_mentions_kitchen(prompt: str) -> bool:
    return "kitchen" in prompt


def _prompt_mentions_mug(prompt: str) -> bool:
    return "mug" in prompt


_PROMPT_SEED_TEMPLATES: tuple[tuple[PromptMatcher, PromptSeeder], ...] = (
    (_prompt_mentions_kitchen, _seed_kitchen),
    (_prompt_mentions_mug, _seed_mug),
)
_DEFAULT_PROMPT_SEED: PromptSeeder = _seed_default_cube


def _prompt_world_name(name: str | None) -> str:
    return name or "prompt-world"


def _prompt_seeders(prompt: str) -> list[PromptSeeder]:
    prompt_lower = prompt.lower()
    return [seed for matches, seed in _PROMPT_SEED_TEMPLATES if matches(prompt_lower)]


def _apply_prompt_seeders(world: World, seeders: Sequence[PromptSeeder]) -> None:
    for seed in seeders:
        seed(world)


def _ensure_prompt_world_seeded(world: World) -> None:
    if not world.scene_objects:
        _DEFAULT_PROMPT_SEED(world)


def _reset_prompt_world_history(world: World) -> None:
    world._history = []
    world._record_history(summary="world seeded from prompt", action=None)


def _seed_prompt_world(world: World, prompt: str) -> None:
    _apply_prompt_seeders(world, _prompt_seeders(prompt))
    _ensure_prompt_world_seeded(world)
    _reset_prompt_world_history(world)

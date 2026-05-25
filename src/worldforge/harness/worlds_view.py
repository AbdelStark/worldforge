"""Textual-free presentation helpers for TheWorldHarness Worlds screens.

This module is imported by :mod:`worldforge.harness.tui` to format table rows,
detail-pane summaries, dirty markers, and pre-validated world identifiers. It is
deliberately free of any ``textual`` import so ``from worldforge.harness.worlds_view
import format_world_row`` works on the base install (the ``harness`` extra only
exists for the Textual TUI itself).

The helpers intentionally mirror — but do not bypass — the validation in
:mod:`worldforge.framework`. The TUI still round-trips every persistence call
through the public ``WorldForge`` API; the helpers here only let the UI render an
inline error *before* submitting invalid input, so the modal can stay open and
surface the rejection reason without a worker round trip.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover - typing only
    from worldforge.models import World


# Mirror of ``worldforge.framework._STORAGE_ID_PATTERN`` so this module stays
# Textual-free *and* import-free of the framework at module load. The regex is
# kept narrow on purpose: any drift is caught by
# ``tests/test_harness_worlds_view.py::test_validate_id_matches_framework``.
_STORAGE_ID_PATTERN: re.Pattern[str] = re.compile(r"[A-Za-z0-9._-]+")


@dataclass(slots=True, frozen=True)
class WorldSpec:
    """User-submitted description of a new world, returned by ``NewWorldScreen``.

    Only the ``name`` and ``provider`` are required; ``description`` is optional.
    Validation of each field matches the contract documented on
    ``WorldForge.create_world``: non-empty ``name``, non-empty registered
    ``provider``, arbitrary ``description``.
    """

    name: str
    provider: str
    description: str = ""


@dataclass(slots=True)
class SceneObjectSpec:
    """User-submitted description of a scene object, returned by ``EditObjectScreen``.

    Independent from :class:`worldforge.models.SceneObject` so modal state can be
    held in the TUI without a ``SceneObject`` round trip (which itself would need
    a :class:`worldforge.models.BBox`). ``metadata`` defaults to an empty dict.
    """

    name: str
    x: float
    y: float
    z: float
    is_graspable: bool = False
    metadata: dict[str, object] = field(default_factory=dict)


def validate_id_or_reason(world_id: str) -> str | None:
    """Return ``None`` if ``world_id`` is a valid storage identifier, else a reason.

    The reason string is user-facing and matches the wording the persistence
    layer would raise when ``WorldForge.save_world`` is called. Modal callers
    can display it under the offending field without a worker round trip.
    """

    if not isinstance(world_id, str) or not world_id.strip():
        return "World ID must be a non-empty string."
    trimmed = world_id.strip()
    if trimmed in {".", ".."}:
        return "World ID must not be '.' or '..'."
    if "/" in trimmed or "\\" in trimmed:
        return "World ID must not contain path separators."
    if _STORAGE_ID_PATTERN.fullmatch(trimmed) is None:
        return "World ID must use only letters, numbers, '.', '_', or '-'."
    return None


def format_world_row(
    world: World,
    *,
    state_dir: Path | None = None,
) -> tuple[str, str, str, int, str]:
    """Return the ``(id, name, provider, step, last_touched)`` tuple for the table.

    ``last_touched`` is the ISO8601 timestamp of the backing JSON file's mtime
    when ``state_dir`` is provided and the file exists; otherwise the string is
    empty. This keeps the helper pure — no ``Path.stat`` side effects when the
    caller does not own a state directory.
    """

    last_touched = ""
    if state_dir is not None:
        path = state_dir / f"{world.id}.json"
        try:
            mtime = path.stat().st_mtime
        except OSError:
            mtime = 0.0
        if mtime > 0.0:
            last_touched = datetime.fromtimestamp(mtime, tz=UTC).replace(microsecond=0).isoformat()
    return (world.id, world.name, world.provider, int(world.step), last_touched)


def format_detail_summary(world: World, *, state_dir: Path | None = None) -> str:
    """Return a multi-line summary rendered in the right-side detail pane."""

    lines = [
        f"ID: {world.id}",
        f"Name: {world.name}",
        f"Provider: {world.provider}",
        f"Step: {int(world.step)}",
        f"Scene objects: {len(world.scene_objects)}",
        f"History entries: {world.history_length}",
    ]
    if world.description:
        lines.append(f"Description: {world.description}")
    if state_dir is not None:
        lines.append(f"State dir: {state_dir}")
    return "\n".join(lines)


def is_dirty(original: World | None, edited: World | None) -> bool:
    """Return whether ``edited`` differs from ``original`` in persisted fields.

    A newly-created world (no ``original``) is considered dirty as soon as an
    ``edited`` World exists — the user must press ``Ctrl+S`` to persist it.
    Comparison uses ``World.to_dict()`` minus the ``history`` block because
    history is recorded as a side effect of ``record_history`` and would flap
    even during pure display refreshes.
    """

    if edited is None:
        return False
    if original is None:
        return True

    def _shape(world: World) -> dict[str, object]:
        snapshot = dict(world.to_dict())
        snapshot.pop("history", None)
        return snapshot

    return _shape(original) != _shape(edited)


def filter_world_ids(world_ids: list[str], query: str, name_map: dict[str, str]) -> list[str]:
    """Substring-filter ``world_ids`` by id or name.

    ``name_map`` maps world id → name. The filter is case-insensitive. Matching
    preserves the input order so the table does not shuffle on filter toggles.
    """

    if not query.strip():
        return list(world_ids)
    needle = query.strip().lower()
    result = []
    for world_id in world_ids:
        name = name_map.get(world_id, "")
        if needle in world_id.lower() or needle in name.lower():
            result.append(world_id)
    return result

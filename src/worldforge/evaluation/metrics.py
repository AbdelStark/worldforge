"""Deterministic scoring helpers for built-in WorldForge evaluation suites."""

from __future__ import annotations

from worldforge.models import Position


def position_distance(a: Position, b: Position) -> float:
    return ((a.x - b.x) ** 2 + (a.y - b.y) ** 2 + (a.z - b.z) ** 2) ** 0.5

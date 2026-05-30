"""Shared artifact-writing helpers."""

from __future__ import annotations

from pathlib import Path

from worldforge.models import dump_json


def write_json_artifact(path: Path, payload: object) -> Path:
    """Write a deterministic, finite JSON artifact and return its path."""

    json_text = dump_json(payload, indent=2) + "\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json_text, encoding="utf-8")
    return path


__all__ = ["write_json_artifact"]

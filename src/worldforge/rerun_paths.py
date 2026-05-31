"""Path normalization helpers for optional Rerun integrations."""

from __future__ import annotations

import re

from worldforge.models import WorldForgeError

_ENTITY_SEGMENT_PATTERN = re.compile(r"[^A-Za-z0-9_.-]+")


def _require_text(value: object, *, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise WorldForgeError(f"{name} must be a non-empty string.")
    return value.strip()


def entity_segment(value: object, *, fallback: str = "item") -> str:
    text = str(value).strip().strip("/")
    if not text:
        return fallback
    segment = _ENTITY_SEGMENT_PATTERN.sub("_", text).strip("._-")
    if not segment or segment.startswith("__"):
        return fallback
    return segment


def validate_path_prefix(value: object, *, name: str) -> str:
    prefix = _require_text(value, name=name).strip("/")
    if not prefix:
        raise WorldForgeError(f"{name} must contain at least one path segment.")
    if any(not part or part.startswith("__") for part in prefix.split("/")):
        raise WorldForgeError(f"{name} must not contain empty or Rerun-reserved path segments.")
    return prefix


def entity_path(prefix: str, *segments: object) -> str:
    clean_prefix = validate_path_prefix(prefix, name="path_prefix")
    clean_segments: list[str] = []
    for segment in segments:
        raw_segment = str(segment).strip("/")
        if not raw_segment:
            clean_segments.append(entity_segment(segment))
            continue
        clean_segments.extend(entity_segment(part) for part in raw_segment.split("/") if part)
    return "/".join([clean_prefix, *clean_segments])

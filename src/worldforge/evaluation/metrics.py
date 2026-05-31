"""Deterministic scoring helpers for built-in WorldForge evaluation suites."""

from __future__ import annotations

from worldforge.evaluation.results import clamp_score
from worldforge.models import Position, VideoClip


def position_distance(a: Position, b: Position) -> float:
    return ((a.x - b.x) ** 2 + (a.y - b.y) ** 2 + (a.z - b.z) ** 2) ** 0.5


def duration_score(*, actual_seconds: float, expected_seconds: float) -> float:
    if expected_seconds <= 0.0:
        return 1.0 if actual_seconds >= 0.0 else 0.0
    return clamp_score(
        1.0 - min(1.0, abs(actual_seconds - expected_seconds) / max(expected_seconds, 0.001))
    )


def resolution_score(clip: VideoClip, *, expected: tuple[int, int] | None = None) -> float:
    width, height = clip.resolution
    if width <= 0 or height <= 0:
        return 0.0
    if expected is None:
        return 1.0
    expected_width, expected_height = expected
    deviation = (
        abs(width - expected_width) / max(expected_width, 1)
        + abs(height - expected_height) / max(expected_height, 1)
    ) / 2
    return clamp_score(1.0 - min(1.0, deviation))


def fps_score(clip: VideoClip, *, expected_fps: float) -> float:
    return clamp_score(1.0 - min(1.0, abs(clip.fps - expected_fps) / max(expected_fps, 0.001)))


def blob_score(clip: VideoClip) -> float:
    return 1.0 if clip.frame_count >= 1 and bool(clip.blob()) else 0.0


def content_type_score(clip: VideoClip) -> float:
    content_type = clip.content_type()
    return (
        1.0
        if content_type.startswith("video/") or content_type == "application/octet-stream"
        else 0.0
    )


def prompt_score(clip: VideoClip, *, expected_prompt: str) -> float:
    return 1.0 if clip.metadata.get("prompt") == expected_prompt else 0.0


def is_image_conditioned(clip: VideoClip) -> bool:
    options = clip.metadata.get("options", {})
    mode = str(clip.metadata.get("mode", "")).lower()
    return (isinstance(options, dict) and bool(options.get("image"))) or "image" in mode


def is_transfer_clip(clip: VideoClip) -> bool:
    return bool(clip.metadata.get("transfer")) or (
        str(clip.metadata.get("mode", "")).lower() == "video_to_video"
    )


def reference_count(clip: VideoClip) -> int:
    value = clip.metadata.get("reference_count")
    if value is not None:
        try:
            return int(value)
        except (TypeError, ValueError):
            return 0
    options = clip.metadata.get("options", {})
    if isinstance(options, dict):
        references = options.get("reference_images", [])
        if isinstance(references, list):
            return len(references)
    return 0

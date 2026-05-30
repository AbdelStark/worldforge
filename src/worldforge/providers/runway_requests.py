"""Runway request validation and body construction helpers."""

from __future__ import annotations

from dataclasses import dataclass

from worldforge.models import GenerationOptions, VideoClip

from .base import ProviderError, validate_generation_request
from .http_utils import asset_to_uri, clip_to_data_uri

_RUNWAY_DEFAULT_DURATION = 5


@dataclass(slots=True, frozen=True)
class RunwayGenerationRequest:
    body: dict[str, object]
    duration: int
    fps: float
    resolution: tuple[int, int]
    model: str
    mode: str


@dataclass(slots=True, frozen=True)
class RunwayTransferRequest:
    body: dict[str, object]
    model: str
    reference_count: int


def validate_runway_generation_request(
    prompt: str,
    duration_seconds: float,
    *,
    options: GenerationOptions | None,
) -> tuple[str, float, GenerationOptions | None]:
    prompt, duration_seconds, options = validate_generation_request(
        prompt,
        duration_seconds,
        options=options,
    )
    if options and options.video:
        raise ProviderError(
            "Runway image_to_video does not accept `options.video`; "
            "use transfer() for video inputs."
        )
    return prompt, duration_seconds, options


def build_runway_generation_request(
    *,
    prompt: str,
    duration_seconds: float,
    ratio: str,
    options: GenerationOptions | None,
    default_model: str,
) -> RunwayGenerationRequest:
    duration = _runway_duration(duration_seconds)
    prompt_image = asset_to_uri(
        options.image if options else None,
        default_content_type="image/png",
    )
    model = _runway_option_model(options, default_model=default_model)
    return RunwayGenerationRequest(
        body=_runway_generation_body(
            prompt=prompt,
            duration=duration,
            ratio=ratio,
            model=model,
            prompt_image=prompt_image,
            options=options,
        ),
        duration=duration,
        fps=_runway_fps(options),
        resolution=_parse_ratio(ratio),
        model=model,
        mode="image_to_video" if prompt_image else "text_to_video",
    )


def build_runway_transfer_request(
    *,
    clip: VideoClip,
    prompt: str,
    options: GenerationOptions | None,
) -> RunwayTransferRequest:
    model = _runway_option_model(options, default_model="gen4_aleph")
    references = _runway_reference_payloads(options)
    return RunwayTransferRequest(
        body=_runway_transfer_body(
            clip=clip,
            prompt=prompt,
            model=model,
            references=references,
            options=options,
        ),
        model=model,
        reference_count=len(references),
    )


def _parse_ratio(ratio: str) -> tuple[int, int]:
    try:
        width_text, height_text = ratio.split(":", maxsplit=1)
        width = int(width_text)
        height = int(height_text)
    except ValueError as exc:
        raise ProviderError(f"Invalid Runway ratio '{ratio}'. Expected WIDTH:HEIGHT.") from exc
    if width <= 0 or height <= 0:
        raise ProviderError("Runway ratio width and height must be greater than 0.")
    return width, height


def _runway_duration(duration_seconds: float) -> int:
    return max(2, min(10, round(duration_seconds or _RUNWAY_DEFAULT_DURATION)))


def _runway_option_model(
    options: GenerationOptions | None,
    *,
    default_model: str,
) -> str:
    return options.model if options and options.model else default_model


def _runway_fps(options: GenerationOptions | None) -> float:
    return options.fps if options and options.fps is not None else 24.0


def _runway_generation_body(
    *,
    prompt: str,
    duration: int,
    ratio: str,
    model: str,
    prompt_image: str | None,
    options: GenerationOptions | None,
) -> dict[str, object]:
    body: dict[str, object] = {
        "model": model,
        "promptText": prompt,
        "ratio": ratio,
        "duration": duration,
    }
    if prompt_image:
        body["promptImage"] = prompt_image
    _apply_runway_options(body, options)
    return body


def _runway_reference_payloads(options: GenerationOptions | None) -> list[dict[str, object]]:
    if options is None:
        return []
    return [
        {"uri": asset_to_uri(reference, default_content_type="image/png") or reference}
        for reference in options.reference_images
    ]


def _runway_transfer_body(
    *,
    clip: VideoClip,
    prompt: str,
    model: str,
    references: list[dict[str, object]],
    options: GenerationOptions | None,
) -> dict[str, object]:
    body: dict[str, object] = {
        "model": model,
        "promptText": prompt or "Re-render the input video while preserving the scene motion.",
        "videoUri": asset_to_uri(
            options.video if options and options.video else clip_to_data_uri(clip),
            default_content_type=clip.content_type(),
        ),
    }
    if references:
        body["references"] = references
    _apply_runway_options(body, options)
    return body


def _apply_runway_options(
    body: dict[str, object],
    options: GenerationOptions | None,
) -> None:
    if options is None:
        return
    if options.seed is not None:
        body["seed"] = options.seed
    if options.extras:
        body.update(options.extras)

"""NVIDIA Cosmos provider integration."""

from __future__ import annotations

import base64
from collections.abc import Callable
from dataclasses import dataclass
from time import perf_counter
from typing import NoReturn

import httpx

from worldforge.models import (
    GenerationOptions,
    ProviderCapabilities,
    ProviderEvent,
    ProviderHealth,
    ProviderRequestPolicy,
    VideoClip,
)

from ._config import ProviderConfigSummary, config_source, env_value
from .base import (
    ProviderError,
    ProviderProfileSpec,
    RemoteProvider,
    _field_summary,
    validate_generation_request,
)
from .http_utils import asset_to_uri, parse_size, request_json_with_policy

_COSMOS_FAILED_STATUSES = frozenset({"failed", "failure", "error", "rejected"})
_COSMOS_ERROR_FIELDS = ("error", "message", "detail", "reason")
_COSMOS_ARTIFACT_REFERENCE_FIELDS = ("artifact_url", "artifact_uri", "output_url", "video_url")


@dataclass(slots=True, frozen=True)
class CosmosHealthResponse:
    """Validated response from Cosmos health endpoints."""

    status: str

    @classmethod
    def from_payload(
        cls,
        payload: dict[str, object],
        *,
        provider_name: str,
    ) -> CosmosHealthResponse:
        status = payload.get("status")
        if not isinstance(status, str) or not status.strip():
            raise ProviderError(
                f"Provider '{provider_name}' healthcheck response field 'status' "
                "must be a non-empty string."
            )
        return cls(status=status.strip())


@dataclass(slots=True, frozen=True)
class CosmosGenerationResponse:
    """Validated response from the Cosmos generation endpoint."""

    b64_video: str
    seed: int | None = None
    upsampled_prompt: str | None = None

    @classmethod
    def from_payload(
        cls,
        payload: dict[str, object],
        *,
        provider_name: str,
    ) -> CosmosGenerationResponse:
        _validate_cosmos_generation_status(payload, provider_name=provider_name)
        return cls(
            b64_video=_cosmos_required_b64_video(payload, provider_name=provider_name),
            seed=_cosmos_optional_seed(payload, provider_name=provider_name),
            upsampled_prompt=_cosmos_optional_upsampled_prompt(
                payload,
                provider_name=provider_name,
            ),
        )

    def decode_video(self, *, provider_name: str) -> bytes:
        try:
            return base64.b64decode(self.b64_video, validate=True)
        except (ValueError, TypeError) as exc:
            raise ProviderError(
                f"Provider '{provider_name}' returned an invalid base64 video payload."
            ) from exc


def _validate_cosmos_generation_status(
    payload: dict[str, object],
    *,
    provider_name: str,
) -> None:
    status = payload.get("status")
    if not _cosmos_status_is_failed(status):
        return
    reason = _cosmos_error_detail(payload)
    raise ProviderError(f"Provider '{provider_name}' generation task failed: {reason}")


def _cosmos_status_is_failed(status: object) -> bool:
    return isinstance(status, str) and status.strip().lower() in _COSMOS_FAILED_STATUSES


def _cosmos_required_b64_video(
    payload: dict[str, object],
    *,
    provider_name: str,
) -> str:
    b64_video = payload.get("b64_video")
    if isinstance(b64_video, str) and b64_video.strip():
        return b64_video.strip()
    return _raise_missing_cosmos_inline_video(payload, provider_name=provider_name)


def _raise_missing_cosmos_inline_video(
    payload: dict[str, object],
    *,
    provider_name: str,
) -> NoReturn:
    if _contains_artifact_reference(payload):
        raise ProviderError(
            f"Provider '{provider_name}' generation response returned artifact "
            "references instead of inline b64_video. This adapter only accepts "
            "inline base64 video payloads; the host must use a compatible Cosmos "
            "deployment or add an explicit artifact downloader."
        )
    raise ProviderError(
        f"Provider '{provider_name}' generation response field 'b64_video' "
        "must be a non-empty base64 string."
    )


def _cosmos_optional_seed(
    payload: dict[str, object],
    *,
    provider_name: str,
) -> int | None:
    seed = payload.get("seed")
    if seed is None:
        return None
    if isinstance(seed, bool) or not isinstance(seed, int):
        raise ProviderError(
            f"Provider '{provider_name}' generation response field 'seed' "
            "must be an integer when present."
        )
    return seed


def _cosmos_optional_upsampled_prompt(
    payload: dict[str, object],
    *,
    provider_name: str,
) -> str | None:
    upsampled_prompt = payload.get("upsampled_prompt")
    if upsampled_prompt is None or isinstance(upsampled_prompt, str):
        return upsampled_prompt
    raise ProviderError(
        f"Provider '{provider_name}' generation response field "
        "'upsampled_prompt' must be a string when present."
    )


def _cosmos_error_detail(payload: dict[str, object]) -> str:
    for value in _cosmos_error_values(payload):
        detail = _cosmos_error_text(value)
        if detail:
            return detail
    return "upstream returned failed status"


def _cosmos_error_values(payload: dict[str, object]) -> tuple[object, ...]:
    return tuple(payload.get(key) for key in _COSMOS_ERROR_FIELDS)


def _cosmos_error_text(value: object) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip()
    if isinstance(value, dict):
        return _cosmos_error_text(_first_cosmos_error_value(value))
    return None


def _first_cosmos_error_value(payload: dict[str, object]) -> object:
    return next((payload.get(key) for key in _COSMOS_ERROR_FIELDS if payload.get(key)), None)


def _contains_artifact_reference(payload: dict[str, object]) -> bool:
    return any(
        _is_non_empty_cosmos_string(payload.get(key)) for key in _COSMOS_ARTIFACT_REFERENCE_FIELDS
    ) or any(_contains_artifact_item_sequence(payload.get(key)) for key in ("artifacts", "outputs"))


def _is_non_empty_cosmos_string(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _contains_artifact_item_sequence(value: object) -> bool:
    if not isinstance(value, list):
        return False
    return any(isinstance(item, str | dict) for item in value)


class CosmosProvider(RemoteProvider):
    """HTTP adapter for self-hosted or managed NVIDIA Cosmos NIM deployments."""

    env_var = "COSMOS_BASE_URL"

    def __init__(
        self,
        name: str = "cosmos",
        *,
        base_url: str | None = None,
        timeout_seconds: float = 300.0,
        request_policy: ProviderRequestPolicy | None = None,
        event_handler: Callable[[ProviderEvent], None] | None = None,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        resolved_request_policy = request_policy or ProviderRequestPolicy.remote_defaults(
            request_timeout_seconds=timeout_seconds
        )
        super().__init__(
            name=name,
            capabilities=ProviderCapabilities(
                predict=False,
                generate=True,
                reason=False,
                embed=False,
                plan=False,
                transfer=False,
            ),
            profile=ProviderProfileSpec(
                description="NVIDIA Cosmos NIM adapter for text/image/video-to-world generation.",
                implementation_status="beta",
                supported_modalities=("text", "image", "video"),
                artifact_types=("video",),
                notes=(
                    "Targets the documented Cosmos NIM `/v1/infer` API.",
                    "Requires a reachable Cosmos deployment via `COSMOS_BASE_URL`.",
                    "If `NVIDIA_API_KEY` is set, it is sent as a bearer token.",
                ),
                default_model="Cosmos-Predict1-7B-Text2World",
                supported_models=(
                    "Cosmos-Predict1-7B-Text2World",
                    "Cosmos-Predict1-7B-Video2World",
                ),
                required_env_vars=("COSMOS_BASE_URL",),
                requires_credentials=False,
            ),
            request_policy=resolved_request_policy,
            event_handler=event_handler,
        )
        self._base_url = base_url
        self._transport = transport

    def configured(self) -> bool:
        return bool(self._resolved_base_url())

    def config_summary(self) -> ProviderConfigSummary:
        api_key_from_env = env_value("NVIDIA_API_KEY") is not None
        return ProviderConfigSummary(
            provider=self.name,
            configured=self.configured(),
            fields=(
                _field_summary(
                    "COSMOS_BASE_URL",
                    required=True,
                    source=config_source("COSMOS_BASE_URL", direct=self._base_url is not None),
                    present=self._resolved_base_url() is not None,
                ),
                _field_summary(
                    "NVIDIA_API_KEY",
                    required=False,
                    secret=True,
                    source="env:NVIDIA_API_KEY" if api_key_from_env else "unset",
                    present=api_key_from_env,
                ),
            ),
        )

    def _resolved_base_url(self) -> str | None:
        return self._base_url or env_value("COSMOS_BASE_URL")

    def _headers(self) -> dict[str, str]:
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
        }
        api_key = env_value("NVIDIA_API_KEY")
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        return headers

    def _client(self) -> httpx.Client:
        base_url = self._resolved_base_url()
        if not base_url:
            raise ProviderError(f"Provider '{self.name}' is unavailable: missing COSMOS_BASE_URL.")
        return httpx.Client(
            base_url=base_url.rstrip("/"),
            headers=self._headers(),
            transport=self._transport,
        )

    def health(self) -> ProviderHealth:
        started = perf_counter()
        base_url = self._resolved_base_url()
        if not base_url:
            return self._health(started, "missing COSMOS_BASE_URL", healthy=False)
        try:
            request_policy = self._require_request_policy()
            with self._client() as client:
                payload = request_json_with_policy(
                    client,
                    method="GET",
                    url="/v1/health/ready",
                    provider_name=self.name,
                    operation_name="healthcheck",
                    policy=request_policy.health,
                    emit_event=self._emit_event,
                )
            health_response = CosmosHealthResponse.from_payload(
                payload,
                provider_name=self.name,
            )
            healthy = health_response.status.lower() == "ready"
            details = health_response.status
        except ProviderError as exc:
            healthy = False
            details = str(exc)
        return self._health(started, details, healthy=healthy)

    def generate(
        self,
        prompt: str,
        duration_seconds: float,
        *,
        options: GenerationOptions | None = None,
    ) -> VideoClip:
        prompt, duration_seconds, options = validate_generation_request(
            prompt,
            duration_seconds,
            options=options,
        )
        self._require_credentials()
        width, height = _cosmos_output_size(options)
        fps = _cosmos_fps(options)
        body = _cosmos_generation_body(
            prompt=prompt,
            duration_seconds=duration_seconds,
            options=options,
            width=width,
            height=height,
            fps=fps,
        )
        parsed_response = self._request_generation(body)
        clip_bytes = parsed_response.decode_video(provider_name=self.name)
        return VideoClip(
            frames=[clip_bytes],
            fps=fps,
            resolution=(width, height),
            duration_seconds=duration_seconds,
            metadata=self._generation_metadata(
                prompt=prompt,
                options=options,
                response=parsed_response,
            ),
        )

    def _request_generation(self, body: dict[str, object]) -> CosmosGenerationResponse:
        request_policy = self._require_request_policy()
        with self._client() as client:
            payload = request_json_with_policy(
                client,
                method="POST",
                url="/v1/infer",
                provider_name=self.name,
                operation_name="generation request",
                policy=request_policy.request,
                emit_event=self._emit_event,
                json=body,
            )
        return CosmosGenerationResponse.from_payload(payload, provider_name=self.name)

    def _generation_metadata(
        self,
        *,
        prompt: str,
        options: GenerationOptions | None,
        response: CosmosGenerationResponse,
    ) -> dict[str, object]:
        return {
            "provider": self.name,
            "prompt": prompt,
            "mode": _cosmos_generation_mode(options),
            "seed": response.seed,
            "upsampled_prompt": response.upsampled_prompt,
            "content_type": "video/mp4",
            "model": options.model if options and options.model else self.default_model,
            "base_url": self._resolved_base_url(),
        }


def _cosmos_output_size(options: GenerationOptions | None) -> tuple[int, int]:
    width, height = parse_size(options, fallback=(1280, 720))
    if width % 8 or height % 8:
        raise ProviderError("Cosmos output size must use width and height that are multiples of 8.")
    return width, height


def _cosmos_fps(options: GenerationOptions | None) -> float:
    fps = options.fps if options and options.fps is not None else 24.0
    if fps <= 0.0:
        raise ProviderError("Cosmos fps must be greater than 0.")
    return fps


def _cosmos_generation_body(
    *,
    prompt: str,
    duration_seconds: float,
    options: GenerationOptions | None,
    width: int,
    height: int,
    fps: float,
) -> dict[str, object]:
    body: dict[str, object] = {
        "prompt": prompt,
        "seed": options.seed if options and options.seed is not None else 4,
        "video_params": {
            "height": height,
            "width": width,
            "frames_count": _cosmos_frame_count(duration_seconds=duration_seconds, fps=fps),
            "frames_per_sec": round(fps),
        },
    }
    _add_cosmos_optional_prompt_inputs(body, options)
    if options:
        body.update(options.extras)
    return body


def _cosmos_frame_count(*, duration_seconds: float, fps: float) -> int:
    return max(1, round(duration_seconds * fps))


def _add_cosmos_optional_prompt_inputs(
    body: dict[str, object],
    options: GenerationOptions | None,
) -> None:
    if options is None:
        return
    if options.negative_prompt:
        body["negative_prompt"] = options.negative_prompt
    if options.image:
        body["image"] = asset_to_uri(options.image, default_content_type="image/png")
    if options.video:
        body["video"] = asset_to_uri(options.video, default_content_type="video/mp4")


def _cosmos_generation_mode(options: GenerationOptions | None) -> str:
    if options and options.video:
        return "video2world"
    if options and options.image:
        return "image2world"
    return "text2world"

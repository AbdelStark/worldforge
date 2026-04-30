"""NVIDIA Cosmos provider integration."""

from __future__ import annotations

import base64
from collections.abc import Callable
from dataclasses import dataclass
from time import perf_counter

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
        status = payload.get("status")
        if isinstance(status, str) and status.strip().lower() in {
            "failed",
            "failure",
            "error",
            "rejected",
        }:
            reason = _cosmos_error_detail(payload)
            raise ProviderError(f"Provider '{provider_name}' generation task failed: {reason}")

        b64_video = payload.get("b64_video")
        if not isinstance(b64_video, str) or not b64_video.strip():
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

        seed = payload.get("seed")
        if seed is not None and (isinstance(seed, bool) or not isinstance(seed, int)):
            raise ProviderError(
                f"Provider '{provider_name}' generation response field 'seed' "
                "must be an integer when present."
            )

        upsampled_prompt = payload.get("upsampled_prompt")
        if upsampled_prompt is not None and not isinstance(upsampled_prompt, str):
            raise ProviderError(
                f"Provider '{provider_name}' generation response field "
                "'upsampled_prompt' must be a string when present."
            )

        return cls(
            b64_video=b64_video.strip(),
            seed=seed,
            upsampled_prompt=upsampled_prompt,
        )

    def decode_video(self, *, provider_name: str) -> bytes:
        try:
            return base64.b64decode(self.b64_video, validate=True)
        except (ValueError, TypeError) as exc:
            raise ProviderError(
                f"Provider '{provider_name}' returned an invalid base64 video payload."
            ) from exc


def _cosmos_error_detail(payload: dict[str, object]) -> str:
    for key in ("error", "message", "detail", "reason"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
        if isinstance(value, dict):
            nested_message = value.get("message") or value.get("detail") or value.get("reason")
            if isinstance(nested_message, str) and nested_message.strip():
                return nested_message.strip()
    return "upstream returned failed status"


def _contains_artifact_reference(payload: dict[str, object]) -> bool:
    for key in ("artifact_url", "artifact_uri", "output_url", "video_url"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return True
    artifacts = payload.get("artifacts") or payload.get("outputs")
    if isinstance(artifacts, list):
        return any(isinstance(item, str | dict) for item in artifacts)
    return False


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

        width, height = parse_size(options, fallback=(1280, 720))
        if width % 8 or height % 8:
            raise ProviderError(
                "Cosmos output size must use width and height that are multiples of 8."
            )

        fps = options.fps if options and options.fps is not None else 24.0
        if fps <= 0.0:
            raise ProviderError("Cosmos fps must be greater than 0.")
        frame_count = max(1, round(duration_seconds * fps))
        body: dict[str, object] = {
            "prompt": prompt,
            "seed": options.seed if options and options.seed is not None else 4,
            "video_params": {
                "height": height,
                "width": width,
                "frames_count": frame_count,
                "frames_per_sec": round(fps),
            },
        }

        if options and options.negative_prompt:
            body["negative_prompt"] = options.negative_prompt

        if options and options.image:
            body["image"] = asset_to_uri(options.image, default_content_type="image/png")
        if options and options.video:
            body["video"] = asset_to_uri(options.video, default_content_type="video/mp4")
        if options:
            body.update(options.extras)

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

        parsed_response = CosmosGenerationResponse.from_payload(payload, provider_name=self.name)
        clip_bytes = parsed_response.decode_video(provider_name=self.name)
        mode = "text2world"
        if options and options.image:
            mode = "image2world"
        if options and options.video:
            mode = "video2world"
        return VideoClip(
            frames=[clip_bytes],
            fps=fps,
            resolution=(width, height),
            duration_seconds=duration_seconds,
            metadata={
                "provider": self.name,
                "prompt": prompt,
                "mode": mode,
                "seed": parsed_response.seed,
                "upsampled_prompt": parsed_response.upsampled_prompt,
                "content_type": "video/mp4",
                "model": options.model if options and options.model else self.default_model,
                "base_url": self._resolved_base_url(),
            },
        )

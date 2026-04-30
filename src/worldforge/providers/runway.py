"""Runway video provider integration."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from time import perf_counter, sleep

import httpx

from worldforge.models import (
    GenerationOptions,
    ProviderCapabilities,
    ProviderEvent,
    ProviderHealth,
    ProviderRequestPolicy,
    VideoClip,
    _sanitize_observable_target,
    require_finite_number,
    require_positive_int,
)

from ._config import ProviderConfigSummary, config_source, env_value, first_env_value
from .base import (
    ProviderError,
    ProviderProfileSpec,
    RemoteProvider,
    _field_summary,
    validate_generation_request,
    validate_transfer_request,
)
from .http_utils import (
    asset_to_uri,
    clip_to_data_uri,
    request_bytes_with_policy,
    request_json_with_policy,
)

_RUNWAY_API_VERSION = "2024-11-06"
_RUNWAY_DEFAULT_RATIO = "1280:720"
_RUNWAY_DEFAULT_DURATION = 5


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


def _payload_message(payload: dict[str, object]) -> str:
    for key in ("failure", "error", "message"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
        if isinstance(value, dict):
            nested_message = value.get("message")
            if isinstance(nested_message, str) and nested_message.strip():
                return nested_message.strip()
    return "no failure detail returned"


def _artifact_url_summary(url: str) -> str:
    sanitized = _sanitize_observable_target(url)
    if sanitized is None:
        raise ProviderError("Runway task output URL must be a non-empty string.")
    return sanitized


@dataclass(slots=True, frozen=True)
class RunwayOrganizationResponse:
    """Validated response from Runway organization health checks."""

    organization_id: str | None = None
    name: str | None = None

    @classmethod
    def from_payload(
        cls,
        payload: dict[str, object],
        *,
        provider_name: str,
    ) -> RunwayOrganizationResponse:
        organization_id = payload.get("id")
        name = payload.get("name")
        if organization_id is not None and (
            not isinstance(organization_id, str) or not organization_id.strip()
        ):
            raise ProviderError(
                f"Provider '{provider_name}' organization response field 'id' "
                "must be a non-empty string when present."
            )
        if name is not None and (not isinstance(name, str) or not name.strip()):
            raise ProviderError(
                f"Provider '{provider_name}' organization response field 'name' "
                "must be a non-empty string when present."
            )
        if organization_id is None and name is None:
            raise ProviderError(
                f"Provider '{provider_name}' organization response must include 'id' or 'name'."
            )
        return cls(
            organization_id=organization_id.strip() if isinstance(organization_id, str) else None,
            name=name.strip() if isinstance(name, str) else None,
        )

    def details(self) -> str:
        return self.name or self.organization_id or "organization ok"


@dataclass(slots=True, frozen=True)
class RunwayTaskCreationResponse:
    """Validated response returned when creating a Runway task."""

    task_id: str

    @classmethod
    def from_payload(
        cls,
        payload: dict[str, object],
        *,
        provider_name: str,
        operation_name: str,
    ) -> RunwayTaskCreationResponse:
        task_id = payload.get("id")
        if not isinstance(task_id, str) or not task_id.strip():
            raise ProviderError(
                f"Provider '{provider_name}' {operation_name} response field 'id' "
                "must be a non-empty task id."
            )
        return cls(task_id=task_id.strip())


@dataclass(slots=True, frozen=True)
class RunwayTaskStatusResponse:
    """Validated response returned when polling a Runway task."""

    task_id: str
    status: str
    outputs: tuple[str, ...] = ()
    message: str = ""

    @classmethod
    def from_payload(
        cls,
        payload: dict[str, object],
        *,
        provider_name: str,
        expected_task_id: str,
    ) -> RunwayTaskStatusResponse:
        task_id = payload.get("id")
        if task_id is not None:
            if not isinstance(task_id, str) or not task_id.strip():
                raise ProviderError(
                    f"Provider '{provider_name}' task response field 'id' "
                    "must be a non-empty string when present."
                )
            if task_id.strip() != expected_task_id:
                raise ProviderError(
                    f"Provider '{provider_name}' task response id '{task_id}' "
                    f"does not match requested task '{expected_task_id}'."
                )

        status = payload.get("status")
        if not isinstance(status, str) or not status.strip():
            raise ProviderError(
                f"Provider '{provider_name}' task {expected_task_id} response field "
                "'status' must be a non-empty string."
            )

        outputs_payload = payload.get("output", [])
        if outputs_payload is None:
            outputs_payload = []
        if not isinstance(outputs_payload, list):
            raise ProviderError(
                f"Provider '{provider_name}' task {expected_task_id} response field "
                "'output' must be a list when present."
            )

        outputs: list[str] = []
        invalid_indexes: list[int] = []
        for index, item in enumerate(outputs_payload):
            if isinstance(item, str) and item.strip():
                outputs.append(item.strip())
            else:
                invalid_indexes.append(index)
        if invalid_indexes:
            joined = ", ".join(str(index) for index in invalid_indexes)
            raise ProviderError(
                f"Provider '{provider_name}' task {expected_task_id} response field "
                f"'output' contains invalid entries at index(es): {joined}."
            )

        return cls(
            task_id=expected_task_id,
            status=status.strip().upper(),
            outputs=tuple(outputs),
            message=_payload_message(payload),
        )

    def require_outputs(self, *, provider_name: str) -> tuple[str, ...]:
        if not self.outputs:
            raise ProviderError(
                f"Provider '{provider_name}' task {self.task_id} completed without outputs."
            )
        return self.outputs


class RunwayProvider(RemoteProvider):
    """HTTP adapter for Runway's image-to-video and video-to-video APIs."""

    env_var = "RUNWAYML_API_SECRET"

    def __init__(
        self,
        name: str = "runway",
        *,
        base_url: str | None = None,
        timeout_seconds: float = 120.0,
        poll_interval_seconds: float = 6.0,
        max_polls: int = 60,
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
                transfer=True,
            ),
            profile=ProviderProfileSpec(
                description=(
                    "Runway adapter for text/image-to-video and video-to-video generation."
                ),
                implementation_status="beta",
                supported_modalities=("text", "image", "video"),
                artifact_types=("video",),
                notes=(
                    "Targets Runway's documented `image_to_video`, `video_to_video`, and `tasks` "
                    "APIs.",
                    "Supports `RUNWAYML_API_SECRET` and the legacy alias `RUNWAY_API_SECRET`.",
                    "Downloaded task outputs should be persisted by the caller because URLs "
                    "expire.",
                ),
                default_model="gen4.5",
                supported_models=("gen4.5", "gen4_turbo", "veo3.1", "veo3.1_fast", "gen4_aleph"),
                required_env_vars=("RUNWAYML_API_SECRET", "RUNWAY_API_SECRET"),
            ),
            request_policy=resolved_request_policy,
            event_handler=event_handler,
        )
        self._base_url = (
            base_url or env_value("RUNWAYML_BASE_URL") or "https://api.dev.runwayml.com"
        )
        self._poll_interval_seconds = require_finite_number(
            poll_interval_seconds,
            name="Runway poll_interval_seconds",
        )
        if self._poll_interval_seconds < 0.0:
            raise ProviderError("Runway poll_interval_seconds must be non-negative.")
        self._max_polls = require_positive_int(max_polls, name="Runway max_polls")
        self._transport = transport

    def configured(self) -> bool:
        return bool(self._api_key())

    def config_summary(self) -> ProviderConfigSummary:
        api_source = next(
            (
                env_name
                for env_name in ("RUNWAYML_API_SECRET", "RUNWAY_API_SECRET")
                if env_value(env_name) is not None
            ),
            None,
        )
        base_url_from_env = env_value("RUNWAYML_BASE_URL") is not None
        return ProviderConfigSummary(
            provider=self.name,
            configured=self.configured(),
            fields=(
                _field_summary(
                    "RUNWAYML_API_SECRET",
                    aliases=("RUNWAY_API_SECRET",),
                    required=True,
                    secret=True,
                    source=f"env:{api_source}" if api_source else "unset",
                    present=api_source is not None,
                ),
                _field_summary(
                    "RUNWAYML_BASE_URL",
                    required=False,
                    source=config_source("RUNWAYML_BASE_URL", default=True),
                    present=base_url_from_env,
                ),
            ),
        )

    def _api_key(self) -> str | None:
        return first_env_value(("RUNWAYML_API_SECRET", "RUNWAY_API_SECRET"))

    def _headers(self) -> dict[str, str]:
        api_key = self._api_key()
        if not api_key:
            raise ProviderError(f"Provider '{self.name}' is unavailable: missing {self.env_var}.")
        return {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "X-Runway-Version": _RUNWAY_API_VERSION,
        }

    def _client(self) -> httpx.Client:
        return httpx.Client(
            base_url=self._base_url.rstrip("/"),
            headers=self._headers(),
            transport=self._transport,
        )

    def health(self) -> ProviderHealth:
        started = perf_counter()
        if not self.configured():
            return self._health(started, f"missing {self.env_var}", healthy=False)
        try:
            request_policy = self._require_request_policy()
            with self._client() as client:
                payload = request_json_with_policy(
                    client,
                    method="GET",
                    url="/v1/organization",
                    provider_name=self.name,
                    operation_name="healthcheck",
                    policy=request_policy.health,
                    emit_event=self._emit_event,
                )
            organization = RunwayOrganizationResponse.from_payload(
                payload,
                provider_name=self.name,
            )
            details = organization.details()
            healthy = True
        except ProviderError as exc:
            healthy = False
            details = str(exc)
        return self._health(started, details, healthy=healthy)

    def _ratio(
        self,
        width: int | None = None,
        height: int | None = None,
        options: GenerationOptions | None = None,
    ) -> str:
        if options and options.ratio:
            return options.ratio
        if width is not None and height is not None:
            return f"{width}:{height}"
        return _RUNWAY_DEFAULT_RATIO

    def _poll_task(self, client: httpx.Client, task_id: str) -> RunwayTaskStatusResponse:
        request_policy = self._require_request_policy()
        for _ in range(self._max_polls):
            payload = request_json_with_policy(
                client,
                method="GET",
                url=f"/v1/tasks/{task_id}",
                provider_name=self.name,
                operation_name="task poll",
                policy=request_policy.polling,
                emit_event=self._emit_event,
            )
            task = RunwayTaskStatusResponse.from_payload(
                payload,
                provider_name=self.name,
                expected_task_id=task_id,
            )
            if task.status == "SUCCEEDED":
                task.require_outputs(provider_name=self.name)
                return task
            if task.status in {"FAILED", "CANCELLED"}:
                raise ProviderError(
                    f"Provider '{self.name}' task {task_id} failed with "
                    f"status {task.status}: {task.message}"
                )
            if self._poll_interval_seconds > 0.0:
                sleep(self._poll_interval_seconds)
        raise ProviderError(f"Provider '{self.name}' task did not complete before timeout.")

    def _download_output(self, output_url: str) -> bytes:
        request_policy = self._require_request_policy()
        with httpx.Client(transport=self._transport) as client:
            try:
                data = request_bytes_with_policy(
                    client,
                    method="GET",
                    url=output_url,
                    provider_name=self.name,
                    operation_name="artifact download",
                    policy=request_policy.download,
                    emit_event=self._emit_event,
                    accepted_content_types=("video/", "application/octet-stream"),
                )
            except ProviderError as exc:
                message = str(exc)
                if "status 403" in message or "status 404" in message:
                    raise ProviderError(
                        f"Provider '{self.name}' artifact URL is expired or unavailable: {message}"
                    ) from exc
                raise
        if not data:
            raise ProviderError(f"Provider '{self.name}' artifact download returned no bytes.")
        return data

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
        if options and options.video:
            raise ProviderError(
                "Runway image_to_video does not accept `options.video`; "
                "use transfer() for video inputs."
            )

        duration = max(2, min(10, round(duration_seconds or _RUNWAY_DEFAULT_DURATION)))
        ratio = self._ratio(options=options)
        resolution = _parse_ratio(ratio)
        model = options.model if options and options.model else self.default_model
        body: dict[str, object] = {
            "model": model,
            "promptText": prompt,
            "ratio": ratio,
            "duration": duration,
        }
        prompt_image = asset_to_uri(
            options.image if options else None,
            default_content_type="image/png",
        )
        if prompt_image:
            body["promptImage"] = prompt_image
        if options and options.seed is not None:
            body["seed"] = options.seed
        if options and options.extras:
            body.update(options.extras)

        request_policy = self._require_request_policy()
        with self._client() as client:
            payload = request_json_with_policy(
                client,
                method="POST",
                url="/v1/image_to_video",
                provider_name=self.name,
                operation_name="generation request",
                policy=request_policy.request,
                emit_event=self._emit_event,
                json=body,
            )
            task_id = RunwayTaskCreationResponse.from_payload(
                payload,
                provider_name=self.name,
                operation_name="generation request",
            ).task_id
            task = self._poll_task(client, task_id)

        output_url = task.outputs[0]
        clip_bytes = self._download_output(output_url)
        artifact_url = _artifact_url_summary(output_url)
        return VideoClip(
            frames=[clip_bytes],
            fps=options.fps if options and options.fps is not None else 24.0,
            resolution=resolution,
            duration_seconds=float(duration),
            metadata={
                "provider": self.name,
                "prompt": prompt,
                "task_id": task_id,
                "artifact_url": artifact_url,
                "content_type": "video/mp4",
                "model": model,
                "mode": "image_to_video" if prompt_image else "text_to_video",
            },
        )

    def transfer(
        self,
        clip: VideoClip,
        *,
        width: int,
        height: int,
        fps: float,
        prompt: str = "",
        options: GenerationOptions | None = None,
    ) -> VideoClip:
        clip, width, height, fps, prompt, options = validate_transfer_request(
            clip,
            width=width,
            height=height,
            fps=fps,
            prompt=prompt,
            options=options,
        )
        self._require_credentials()
        model = options.model if options and options.model else "gen4_aleph"
        references: list[dict[str, str]] = []
        if options:
            references.extend(
                {"uri": asset_to_uri(reference, default_content_type="image/png") or reference}
                for reference in options.reference_images
            )

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
        if options and options.seed is not None:
            body["seed"] = options.seed
        if options and options.extras:
            body.update(options.extras)

        request_policy = self._require_request_policy()
        with self._client() as client:
            payload = request_json_with_policy(
                client,
                method="POST",
                url="/v1/video_to_video",
                provider_name=self.name,
                operation_name="transfer request",
                policy=request_policy.request,
                emit_event=self._emit_event,
                json=body,
            )
            task_id = RunwayTaskCreationResponse.from_payload(
                payload,
                provider_name=self.name,
                operation_name="transfer request",
            ).task_id
            task = self._poll_task(client, task_id)

        output_url = task.outputs[0]
        clip_bytes = self._download_output(output_url)
        artifact_url = _artifact_url_summary(output_url)
        return VideoClip(
            frames=[clip_bytes],
            fps=fps,
            resolution=(width, height),
            duration_seconds=clip.duration_seconds,
            metadata={
                "provider": self.name,
                "prompt": prompt,
                "task_id": task_id,
                "artifact_url": artifact_url,
                "content_type": "video/mp4",
                "model": model,
                "mode": "video_to_video",
                "reference_count": len(references),
            },
        )

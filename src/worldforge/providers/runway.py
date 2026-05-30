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
    require_finite_number,
    require_positive_int,
)

from ._config import (
    ProviderConfigSummary,
    config_source,
    env_value,
    first_env_value,
    optional_bool,
)
from .base import (
    ProviderError,
    ProviderProfileSpec,
    RemoteProvider,
    _field_summary,
    validate_transfer_request,
)
from .http_utils import (
    request_bytes_with_policy,
    request_json_with_policy,
    validate_remote_url,
)
from .runway_requests import (
    build_runway_generation_request,
    build_runway_transfer_request,
    validate_runway_generation_request,
)
from .runway_responses import (
    RunwayOrganizationResponse,
    RunwayTaskCreationResponse,
    RunwayTaskStatusResponse,
)
from .runway_responses import (
    artifact_url_summary as _artifact_url_summary,
)

_RUNWAY_API_VERSION = "2024-11-06"
_RUNWAY_DEFAULT_RATIO = "1280:720"
_RUNWAY_MAX_ARTIFACT_BYTES = 1024 * 1024 * 1024
_RUNWAY_ALLOW_LOCAL_ARTIFACT_URLS_ENV_VAR = "RUNWAYML_ALLOW_LOCAL_ARTIFACT_URLS"
_RUNWAY_RESOLVE_ARTIFACT_DNS_ENV_VAR = "RUNWAYML_RESOLVE_ARTIFACT_DNS"


@dataclass(slots=True, frozen=True)
class _RunwayDownloadedOutput:
    clip_bytes: bytes
    artifact_url: str


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
        allow_local_artifact_urls: bool | str | None = None,
        resolve_artifact_dns: bool | str | None = None,
        max_artifact_bytes: int = _RUNWAY_MAX_ARTIFACT_BYTES,
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
        self._allow_local_artifact_urls_direct = allow_local_artifact_urls is not None
        parsed_allow_local_artifacts = optional_bool(
            allow_local_artifact_urls
            if allow_local_artifact_urls is not None
            else env_value(_RUNWAY_ALLOW_LOCAL_ARTIFACT_URLS_ENV_VAR),
            name="Runway allow_local_artifact_urls",
        )
        self._allow_local_artifact_urls = bool(parsed_allow_local_artifacts)
        self._resolve_artifact_dns_direct = resolve_artifact_dns is not None
        self._resolve_artifact_dns = optional_bool(
            resolve_artifact_dns
            if resolve_artifact_dns is not None
            else env_value(_RUNWAY_RESOLVE_ARTIFACT_DNS_ENV_VAR),
            name="Runway resolve_artifact_dns",
        )
        self._max_artifact_bytes = require_positive_int(
            max_artifact_bytes,
            name="Runway max_artifact_bytes",
        )

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
                _field_summary(
                    _RUNWAY_ALLOW_LOCAL_ARTIFACT_URLS_ENV_VAR,
                    required=False,
                    source=config_source(
                        _RUNWAY_ALLOW_LOCAL_ARTIFACT_URLS_ENV_VAR,
                        direct=self._allow_local_artifact_urls_direct,
                    ),
                    present=self._allow_local_artifact_urls_direct
                    or env_value(_RUNWAY_ALLOW_LOCAL_ARTIFACT_URLS_ENV_VAR) is not None,
                ),
                _field_summary(
                    _RUNWAY_RESOLVE_ARTIFACT_DNS_ENV_VAR,
                    required=False,
                    source=config_source(
                        _RUNWAY_RESOLVE_ARTIFACT_DNS_ENV_VAR,
                        direct=self._resolve_artifact_dns_direct,
                        default=True,
                    ),
                    present=self._resolve_artifact_dns_direct
                    or env_value(_RUNWAY_RESOLVE_ARTIFACT_DNS_ENV_VAR) is not None,
                    detail=self._artifact_dns_config_detail(),
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
        validated_output_url = validate_remote_url(
            output_url,
            provider_name=self.name,
            url_name="artifact URL",
            allow_local_network=self._allow_local_artifact_urls,
            resolve_dns=self._should_resolve_artifact_dns(),
        )
        with httpx.Client(transport=self._transport) as client:
            try:
                data = request_bytes_with_policy(
                    client,
                    method="GET",
                    url=validated_output_url,
                    provider_name=self.name,
                    operation_name="artifact download",
                    policy=request_policy.download,
                    emit_event=self._emit_event,
                    accepted_content_types=("video/", "application/octet-stream"),
                    max_bytes=self._max_artifact_bytes,
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

    def _should_resolve_artifact_dns(self) -> bool:
        if self._resolve_artifact_dns is not None:
            return self._resolve_artifact_dns
        return self._transport is None or isinstance(self._transport, httpx.HTTPTransport)

    def _artifact_dns_config_detail(self) -> str:
        effective = str(self._should_resolve_artifact_dns()).lower()
        if self._resolve_artifact_dns is None:
            return f"auto; effective resolve_dns={effective}"
        return f"effective resolve_dns={effective}"

    def _submit_runway_task(
        self,
        *,
        url: str,
        operation_name: str,
        body: dict[str, object],
    ) -> tuple[str, RunwayTaskStatusResponse]:
        request_policy = self._require_request_policy()
        with self._client() as client:
            payload = request_json_with_policy(
                client,
                method="POST",
                url=url,
                provider_name=self.name,
                operation_name=operation_name,
                policy=request_policy.request,
                emit_event=self._emit_event,
                json=body,
            )
            task_id = RunwayTaskCreationResponse.from_payload(
                payload,
                provider_name=self.name,
                operation_name=operation_name,
            ).task_id
            task = self._poll_task(client, task_id)
        return task_id, task

    def _download_task_output(self, task: RunwayTaskStatusResponse) -> _RunwayDownloadedOutput:
        output_url = task.outputs[0]
        return _RunwayDownloadedOutput(
            clip_bytes=self._download_output(output_url),
            artifact_url=_artifact_url_summary(output_url),
        )

    def generate(
        self,
        prompt: str,
        duration_seconds: float,
        *,
        options: GenerationOptions | None = None,
    ) -> VideoClip:
        prompt, duration_seconds, options = validate_runway_generation_request(
            prompt,
            duration_seconds,
            options=options,
        )
        self._require_credentials()
        request = build_runway_generation_request(
            prompt=prompt,
            duration_seconds=duration_seconds,
            ratio=self._ratio(options=options),
            options=options,
            default_model=self.default_model,
        )
        task_id, task = self._submit_runway_task(
            url="/v1/image_to_video",
            operation_name="generation request",
            body=request.body,
        )
        output = self._download_task_output(task)
        return VideoClip(
            frames=[output.clip_bytes],
            fps=request.fps,
            resolution=request.resolution,
            duration_seconds=float(request.duration),
            metadata={
                "provider": self.name,
                "prompt": prompt,
                "task_id": task_id,
                "artifact_url": output.artifact_url,
                "content_type": "video/mp4",
                "model": request.model,
                "mode": request.mode,
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
        request = build_runway_transfer_request(clip=clip, prompt=prompt, options=options)
        task_id, task = self._submit_runway_task(
            url="/v1/video_to_video",
            operation_name="transfer request",
            body=request.body,
        )
        output = self._download_task_output(task)
        return VideoClip(
            frames=[output.clip_bytes],
            fps=fps,
            resolution=(width, height),
            duration_seconds=clip.duration_seconds,
            metadata={
                "provider": self.name,
                "prompt": prompt,
                "task_id": task_id,
                "artifact_url": output.artifact_url,
                "content_type": "video/mp4",
                "model": request.model,
                "mode": "video_to_video",
                "reference_count": request.reference_count,
            },
        )

"""Shared helpers for HTTP-backed provider adapters."""

from __future__ import annotations

import base64
import mimetypes
from collections.abc import Callable
from pathlib import Path
from time import perf_counter, sleep
from typing import Any

import httpx

from worldforge.models import (
    GenerationOptions,
    ProviderEvent,
    RequestOperationPolicy,
    VideoClip,
)

from .base import ProviderError

_RETRYABLE_EXCEPTIONS = (httpx.TransportError,)


def asset_to_uri(value: str | None, *, default_content_type: str) -> str | None:
    """Return a URL or data URI suitable for provider APIs."""

    if value is None:
        return None
    if value.startswith(("http://", "https://", "data:")):
        return value

    path = Path(value).expanduser().resolve()
    try:
        data = path.read_bytes()
    except FileNotFoundError as exc:
        raise ProviderError(f"Local asset path does not exist: {path}") from exc
    except IsADirectoryError as exc:
        raise ProviderError(f"Local asset path is not a file: {path}") from exc
    except OSError as exc:
        raise ProviderError(f"Could not read local asset {path}: {exc}") from exc

    content_type = mimetypes.guess_type(path.name)[0] or default_content_type
    payload = base64.b64encode(data).decode("ascii")
    return f"data:{content_type};base64,{payload}"


def clip_to_data_uri(clip: VideoClip) -> str:
    """Encode a clip as a data URI for video-to-video style APIs."""

    payload = base64.b64encode(clip.blob()).decode("ascii")
    return f"data:{clip.content_type()};base64,{payload}"


def parse_size(options: GenerationOptions | None, *, fallback: tuple[int, int]) -> tuple[int, int]:
    """Resolve output size from typed options."""

    def _validate_dimensions(width: int, height: int) -> tuple[int, int]:
        if width <= 0 or height <= 0:
            raise ProviderError("Output size values must be greater than 0.")
        return width, height

    if options is None:
        return _validate_dimensions(*fallback)
    if options.size:
        try:
            width_text, height_text = options.size.lower().split("x", maxsplit=1)
            return _validate_dimensions(int(width_text), int(height_text))
        except ValueError as exc:
            raise ProviderError(
                f"Invalid size '{options.size}'. Expected format WIDTHxHEIGHT."
            ) from exc
    if options.ratio:
        try:
            width_text, height_text = options.ratio.split(":", maxsplit=1)
            return _validate_dimensions(int(width_text), int(height_text))
        except ValueError as exc:
            raise ProviderError(
                f"Invalid ratio '{options.ratio}'. Expected format WIDTH:HEIGHT."
            ) from exc

    return _validate_dimensions(*fallback)


def _response_summary(response: httpx.Response) -> str:
    text = response.text.strip()
    if not text:
        return "empty response body"
    if len(text) > 200:
        return f"{text[:197]}..."
    return text


def _raise_status_error(
    *,
    provider_name: str,
    operation_name: str,
    response: httpx.Response,
) -> None:
    raise ProviderError(
        f"Provider '{provider_name}' {operation_name} failed with "
        f"status {response.status_code}: {_response_summary(response)}"
    )


def _content_type_is_allowed(content_type: str, accepted_content_types: tuple[str, ...]) -> bool:
    normalized = content_type.split(";", maxsplit=1)[0].strip().lower()
    for accepted in accepted_content_types:
        expected = accepted.lower()
        if expected.endswith("/") and normalized.startswith(expected):
            return True
        if normalized == expected:
            return True
    return False


def request_with_policy(
    client: httpx.Client,
    *,
    method: str,
    url: str,
    provider_name: str,
    operation_name: str,
    policy: RequestOperationPolicy,
    emit_event: Callable[[ProviderEvent], None] | None = None,
    **kwargs: Any,
) -> httpx.Response:
    """Send an HTTP request using the configured timeout and retry policy."""

    for attempt_number in range(1, policy.retry.max_attempts + 1):
        started = perf_counter()
        try:
            response = client.request(
                method,
                url,
                timeout=policy.timeout_seconds,
                **kwargs,
            )
        except _RETRYABLE_EXCEPTIONS as exc:
            duration_ms = max(0.0, (perf_counter() - started) * 1000)
            if attempt_number >= policy.retry.max_attempts:
                if emit_event is not None:
                    emit_event(
                        ProviderEvent(
                            provider=provider_name,
                            operation=operation_name,
                            phase="failure",
                            attempt=attempt_number,
                            max_attempts=policy.retry.max_attempts,
                            method=method,
                            target=url,
                            duration_ms=duration_ms,
                            message=str(exc),
                        )
                    )
                raise ProviderError(
                    f"Provider '{provider_name}' {operation_name} failed after "
                    f"{attempt_number} attempt(s): {exc}"
                ) from exc
            delay = policy.retry.delay_for_attempt(attempt_number + 1)
            if emit_event is not None:
                emit_event(
                    ProviderEvent(
                        provider=provider_name,
                        operation=operation_name,
                        phase="retry",
                        attempt=attempt_number,
                        max_attempts=policy.retry.max_attempts,
                        method=method,
                        target=url,
                        duration_ms=duration_ms,
                        message=str(exc),
                        metadata={"next_delay_seconds": delay},
                    )
                )
            if delay > 0.0:
                sleep(delay)
            continue
        except httpx.HTTPError as exc:
            duration_ms = max(0.0, (perf_counter() - started) * 1000)
            if emit_event is not None:
                emit_event(
                    ProviderEvent(
                        provider=provider_name,
                        operation=operation_name,
                        phase="failure",
                        attempt=attempt_number,
                        max_attempts=policy.retry.max_attempts,
                        method=method,
                        target=url,
                        duration_ms=duration_ms,
                        message=str(exc),
                    )
                )
            raise ProviderError(
                f"Provider '{provider_name}' {operation_name} failed: {exc}"
            ) from exc

        duration_ms = max(0.0, (perf_counter() - started) * 1000)
        if response.status_code in policy.retry.retryable_status_codes:
            if attempt_number >= policy.retry.max_attempts:
                if emit_event is not None:
                    emit_event(
                        ProviderEvent(
                            provider=provider_name,
                            operation=operation_name,
                            phase="failure",
                            attempt=attempt_number,
                            max_attempts=policy.retry.max_attempts,
                            method=method,
                            target=url,
                            status_code=response.status_code,
                            duration_ms=duration_ms,
                            message=_response_summary(response),
                        )
                    )
                _raise_status_error(
                    provider_name=provider_name,
                    operation_name=operation_name,
                    response=response,
                )
            delay = policy.retry.delay_for_attempt(attempt_number + 1)
            if emit_event is not None:
                emit_event(
                    ProviderEvent(
                        provider=provider_name,
                        operation=operation_name,
                        phase="retry",
                        attempt=attempt_number,
                        max_attempts=policy.retry.max_attempts,
                        method=method,
                        target=url,
                        status_code=response.status_code,
                        duration_ms=duration_ms,
                        message=_response_summary(response),
                        metadata={"next_delay_seconds": delay},
                    )
                )
            response.close()
            if delay > 0.0:
                sleep(delay)
            continue

        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            if emit_event is not None:
                emit_event(
                    ProviderEvent(
                        provider=provider_name,
                        operation=operation_name,
                        phase="failure",
                        attempt=attempt_number,
                        max_attempts=policy.retry.max_attempts,
                        method=method,
                        target=url,
                        status_code=response.status_code,
                        duration_ms=duration_ms,
                        message=_response_summary(response),
                    )
                )
            raise ProviderError(
                f"Provider '{provider_name}' {operation_name} failed with "
                f"status {response.status_code}: {_response_summary(response)}"
            ) from exc
        if emit_event is not None:
            emit_event(
                ProviderEvent(
                    provider=provider_name,
                    operation=operation_name,
                    phase="success",
                    attempt=attempt_number,
                    max_attempts=policy.retry.max_attempts,
                    method=method,
                    target=url,
                    status_code=response.status_code,
                    duration_ms=duration_ms,
                )
            )
        return response

    raise AssertionError("request_with_policy exhausted retries without returning or raising")


def request_json_with_policy(
    client: httpx.Client,
    *,
    method: str,
    url: str,
    provider_name: str,
    operation_name: str,
    policy: RequestOperationPolicy,
    emit_event: Callable[[ProviderEvent], None] | None = None,
    **kwargs: Any,
) -> dict[str, object]:
    """Send an HTTP request and decode a JSON object response."""

    response = request_with_policy(
        client,
        method=method,
        url=url,
        provider_name=provider_name,
        operation_name=operation_name,
        policy=policy,
        emit_event=emit_event,
        **kwargs,
    )
    try:
        payload = response.json()
    except ValueError as exc:
        raise ProviderError(
            f"Provider '{provider_name}' {operation_name} returned invalid JSON."
        ) from exc
    if not isinstance(payload, dict):
        raise ProviderError(
            f"Provider '{provider_name}' {operation_name} returned a non-object JSON payload."
        )
    return dict(payload)


def request_bytes_with_policy(
    client: httpx.Client,
    *,
    method: str,
    url: str,
    provider_name: str,
    operation_name: str,
    policy: RequestOperationPolicy,
    emit_event: Callable[[ProviderEvent], None] | None = None,
    accepted_content_types: tuple[str, ...] | None = None,
    **kwargs: Any,
) -> bytes:
    """Send an HTTP request and return the raw response bytes."""

    response = request_with_policy(
        client,
        method=method,
        url=url,
        provider_name=provider_name,
        operation_name=operation_name,
        policy=policy,
        emit_event=emit_event,
        **kwargs,
    )
    content_type = response.headers.get("content-type")
    if (
        content_type
        and accepted_content_types
        and not _content_type_is_allowed(
            content_type,
            accepted_content_types,
        )
    ):
        raise ProviderError(
            f"Provider '{provider_name}' {operation_name} returned unsupported "
            f"content type '{content_type}'."
        )
    return response.content


def poll_json_task(
    client: httpx.Client,
    *,
    path: str,
    status_key: str = "status",
    success_values: set[str],
    failure_values: set[str],
    poll_interval_seconds: float,
    max_polls: int,
    provider_name: str,
    operation_policy: RequestOperationPolicy,
    emit_event: Callable[[ProviderEvent], None] | None = None,
) -> dict[str, object]:
    """Poll an HTTP task endpoint until it completes or fails."""

    for _ in range(max_polls):
        payload = request_json_with_policy(
            client,
            method="GET",
            url=path,
            provider_name=provider_name,
            operation_name="task poll",
            policy=operation_policy,
            emit_event=emit_event,
        )
        status = str(payload.get(status_key, "")).upper()
        if status in success_values:
            return dict(payload)
        if status in failure_values:
            raise ProviderError(f"Provider '{provider_name}' task failed with status {status}.")
        sleep(poll_interval_seconds)
    raise ProviderError(f"Provider '{provider_name}' task did not complete before timeout.")

"""Streamed download helpers for HTTP-backed provider adapters."""

from __future__ import annotations

from collections.abc import Callable
from time import perf_counter
from typing import Any

import httpx

from worldforge.models import ProviderEvent, RequestOperationPolicy, _redact_observable_text

from . import http_request_policy as _request_policy
from .base import ProviderError
from .http_response_validation import _content_type_is_allowed

_ERROR_SUMMARY_BYTES = 512


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
    max_bytes: int | None = None,
    **kwargs: Any,
) -> bytes:
    """Send an HTTP request and stream raw response bytes with an optional hard cap."""

    _validate_download_size_limit(
        max_bytes,
        provider_name=provider_name,
        operation_name=operation_name,
    )
    context = _request_policy._HttpRequestContext(
        provider_name=provider_name,
        operation_name=operation_name,
        method=method,
        url=url,
        policy=policy,
        emit_event=emit_event,
    )
    return _request_bytes_with_context(
        client,
        context=context,
        accepted_content_types=accepted_content_types,
        max_bytes=max_bytes,
        request_kwargs=kwargs,
    )


def _request_bytes_with_context(
    client: httpx.Client,
    *,
    context: _request_policy._HttpRequestContext,
    accepted_content_types: tuple[str, ...] | None,
    max_bytes: int | None,
    request_kwargs: dict[str, Any],
) -> bytes:
    operation_started = perf_counter()
    for attempt_number in range(1, context.max_attempts + 1):
        remaining_seconds = _request_policy._remaining_attempt_budget_seconds(
            context,
            operation_started=operation_started,
            attempt=attempt_number,
        )
        started = perf_counter()
        try:
            data = _request_bytes_attempt(
                client,
                context=context,
                timeout=_request_policy._request_timeout_seconds(context.policy, remaining_seconds),
                attempt=attempt_number,
                operation_started=operation_started,
                attempt_started=started,
                accepted_content_types=accepted_content_types,
                max_bytes=max_bytes,
                request_kwargs=request_kwargs,
            )
        except _request_policy._RETRYABLE_EXCEPTIONS as exc:
            _request_policy._handle_retryable_transport_error(
                context,
                attempt=attempt_number,
                operation_started=operation_started,
                attempt_started=started,
                error=exc,
            )
            continue
        except httpx.HTTPError as exc:
            _request_policy._raise_nonretryable_http_error(
                context,
                attempt=attempt_number,
                attempt_started=started,
                error=exc,
            )
        if data is None:
            continue
        return data

    raise AssertionError("request_bytes_with_policy exhausted retries without returning or raising")


def _validate_download_size_limit(
    max_bytes: int | None,
    *,
    provider_name: str,
    operation_name: str,
) -> None:
    if max_bytes is None or max_bytes > 0:
        return
    raise ProviderError(
        f"Provider '{provider_name}' {operation_name} max_bytes must be greater than 0."
    )


def _request_bytes_attempt(
    client: httpx.Client,
    *,
    context: _request_policy._HttpRequestContext,
    timeout: float | None,
    attempt: int,
    operation_started: float,
    attempt_started: float,
    accepted_content_types: tuple[str, ...] | None,
    max_bytes: int | None,
    request_kwargs: dict[str, Any],
) -> bytes | None:
    with client.stream(context.method, context.url, timeout=timeout, **request_kwargs) as response:
        duration_ms = _request_policy._duration_ms_since(attempt_started)
        if response.status_code in context.policy.retry.retryable_status_codes:
            _retry_stream_response(
                context,
                response=response,
                attempt=attempt,
                operation_started=operation_started,
                attempt_started=attempt_started,
            )
            return None

        _raise_for_stream_status(
            context, response=response, attempt=attempt, duration_ms=duration_ms
        )
        _reject_stream_content_type(
            context,
            response=response,
            attempt=attempt,
            duration_ms=duration_ms,
            accepted_content_types=accepted_content_types,
        )
        _reject_oversized_content_length(
            response,
            provider_name=context.provider_name,
            operation_name=context.operation_name,
            max_bytes=max_bytes,
        )
        data = _read_response_bytes(
            response,
            provider_name=context.provider_name,
            operation_name=context.operation_name,
            max_bytes=max_bytes,
        )
        _emit_stream_success(
            context,
            response=response,
            attempt=attempt,
            duration_ms=_request_policy._duration_ms_since(attempt_started),
            byte_count=len(data),
        )
        return data


def _retry_stream_response(
    context: _request_policy._HttpRequestContext,
    *,
    response: httpx.Response,
    attempt: int,
    operation_started: float,
    attempt_started: float,
) -> None:
    summary = _stream_response_summary(response)
    delay = _request_policy._retry_response_or_raise_status(
        context,
        response=response,
        summary=summary,
        attempt=attempt,
        operation_started=operation_started,
        attempt_started=attempt_started,
    )
    response.close()
    _request_policy._sleep_retry_delay(delay)


def _raise_for_stream_status(
    context: _request_policy._HttpRequestContext,
    *,
    response: httpx.Response,
    attempt: int,
    duration_ms: float,
) -> None:
    if response.status_code < 400:
        return
    summary = _stream_response_summary(response)
    context.emit(
        "failure",
        attempt=attempt,
        duration_ms=duration_ms,
        status_code=response.status_code,
        message=summary,
    )
    _request_policy._raise_status_summary_error(
        context,
        status_code=response.status_code,
        summary=summary,
    )


def _reject_stream_content_type(
    context: _request_policy._HttpRequestContext,
    *,
    response: httpx.Response,
    attempt: int,
    duration_ms: float,
    accepted_content_types: tuple[str, ...] | None,
) -> None:
    content_type = response.headers.get("content-type")
    if (
        not content_type
        or not accepted_content_types
        or _content_type_is_allowed(content_type, accepted_content_types)
    ):
        return
    message = (
        f"Provider '{context.provider_name}' {context.operation_name} returned unsupported "
        f"content type '{content_type}'."
    )
    context.emit(
        "failure",
        attempt=attempt,
        duration_ms=duration_ms,
        status_code=response.status_code,
        message=message,
    )
    raise ProviderError(message)


def _emit_stream_success(
    context: _request_policy._HttpRequestContext,
    *,
    response: httpx.Response,
    attempt: int,
    duration_ms: float,
    byte_count: int,
) -> None:
    context.emit(
        "success",
        attempt=attempt,
        duration_ms=duration_ms,
        status_code=response.status_code,
        metadata={"bytes": byte_count},
    )


def _stream_response_summary(response: httpx.Response) -> str:
    data = bytearray()
    try:
        for chunk in response.iter_bytes():
            remaining = _ERROR_SUMMARY_BYTES - len(data)
            if remaining <= 0:
                break
            data.extend(chunk[:remaining])
            if len(data) >= _ERROR_SUMMARY_BYTES:
                break
    except httpx.HTTPError:
        return "unreadable response body"
    if not data:
        return "empty response body"
    text = bytes(data).decode("utf-8", errors="replace").strip()
    if not text:
        return "empty response body"
    if len(text) > 200:
        text = f"{text[:197]}..."
    return _redact_observable_text(text)


def _reject_oversized_content_length(
    response: httpx.Response,
    *,
    provider_name: str,
    operation_name: str,
    max_bytes: int | None,
) -> None:
    if max_bytes is None:
        return
    content_length = response.headers.get("content-length")
    if content_length is None:
        return
    try:
        size = int(content_length)
    except ValueError as exc:
        raise ProviderError(
            f"Provider '{provider_name}' {operation_name} returned invalid Content-Length."
        ) from exc
    if size < 0:
        raise ProviderError(
            f"Provider '{provider_name}' {operation_name} returned invalid Content-Length."
        )
    if size > max_bytes:
        raise ProviderError(
            f"Provider '{provider_name}' {operation_name} exceeded download size limit "
            f"of {max_bytes} bytes from Content-Length {size}."
        )


def _read_response_bytes(
    response: httpx.Response,
    *,
    provider_name: str,
    operation_name: str,
    max_bytes: int | None,
) -> bytes:
    data = bytearray()
    for chunk in response.iter_bytes():
        data.extend(chunk)
        if max_bytes is not None and len(data) > max_bytes:
            raise ProviderError(
                f"Provider '{provider_name}' {operation_name} exceeded download size limit "
                f"of {max_bytes} bytes."
            )
    return bytes(data)

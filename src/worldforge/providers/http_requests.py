"""Non-streaming HTTP request helpers for provider adapters."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import httpx

from worldforge.models import ProviderEvent, RequestOperationPolicy

from . import http_request_policy as _request_policy
from . import http_response_validation as _response_validation
from .base import ProviderError


def request_with_policy(
    client: httpx.Client,
    *,
    method: str,
    url: str,
    provider_name: str,
    operation_name: str,
    policy: RequestOperationPolicy,
    emit_event: Callable[[ProviderEvent], None] | None = None,
    emit_success_event: bool = True,
    **kwargs: Any,
) -> httpx.Response:
    """Send an HTTP request using the configured timeout and retry policy."""

    context = _request_policy._HttpRequestContext(
        provider_name=provider_name,
        operation_name=operation_name,
        method=method,
        url=url,
        policy=policy,
        emit_event=emit_event,
    )
    return _request_with_context(
        client,
        context=context,
        emit_success_event=emit_success_event,
        request_kwargs=kwargs,
    )


def _request_with_context(
    client: httpx.Client,
    *,
    context: _request_policy._HttpRequestContext,
    emit_success_event: bool,
    request_kwargs: dict[str, Any],
) -> httpx.Response:
    operation_started = _request_policy.perf_counter()
    for attempt_number in range(1, context.max_attempts + 1):
        remaining_seconds = _request_policy._remaining_attempt_budget_seconds(
            context,
            operation_started=operation_started,
            attempt=attempt_number,
        )
        started = _request_policy.perf_counter()
        response = _request_attempt_or_retry(
            client,
            context=context,
            timeout=_request_policy._request_timeout_seconds(context.policy, remaining_seconds),
            attempt=attempt_number,
            operation_started=operation_started,
            attempt_started=started,
            request_kwargs=request_kwargs,
        )
        if response is None:
            continue
        finalized = _finalize_response_attempt(
            context,
            response=response,
            attempt=attempt_number,
            operation_started=operation_started,
            attempt_started=started,
            emit_success_event=emit_success_event,
        )
        if finalized is None:
            continue
        return finalized

    raise AssertionError("request_with_policy exhausted retries without returning or raising")


def _request_attempt_or_retry(
    client: httpx.Client,
    *,
    context: _request_policy._HttpRequestContext,
    timeout: float | None,
    attempt: int,
    operation_started: float,
    attempt_started: float,
    request_kwargs: dict[str, Any],
) -> httpx.Response | None:
    try:
        return client.request(
            context.method,
            context.url,
            timeout=timeout,
            **request_kwargs,
        )
    except _request_policy._RETRYABLE_EXCEPTIONS as exc:
        _request_policy._handle_retryable_transport_error(
            context,
            attempt=attempt,
            operation_started=operation_started,
            attempt_started=attempt_started,
            error=exc,
        )
        return None
    except httpx.HTTPError as exc:
        _request_policy._raise_nonretryable_http_error(
            context,
            attempt=attempt,
            attempt_started=attempt_started,
            error=exc,
        )


def _finalize_response_attempt(
    context: _request_policy._HttpRequestContext,
    *,
    response: httpx.Response,
    attempt: int,
    operation_started: float,
    attempt_started: float,
    emit_success_event: bool,
) -> httpx.Response | None:
    duration_ms = _request_policy._duration_ms_since(attempt_started)
    if response.status_code in context.policy.retry.retryable_status_codes:
        delay = _request_policy._retry_response_or_raise_status(
            context,
            response=response,
            summary=_response_validation._response_summary(response),
            attempt=attempt,
            operation_started=operation_started,
            attempt_started=attempt_started,
        )
        response.close()
        _request_policy._sleep_retry_delay(delay)
        return None

    _raise_for_response_status(context, response=response, attempt=attempt, duration_ms=duration_ms)
    _record_response_extensions(
        response,
        attempt=attempt,
        max_attempts=context.max_attempts,
        duration_ms=duration_ms,
    )
    if emit_success_event:
        context.emit(
            "success",
            attempt=attempt,
            duration_ms=duration_ms,
            status_code=response.status_code,
        )
    return response


def _raise_for_response_status(
    context: _request_policy._HttpRequestContext,
    *,
    response: httpx.Response,
    attempt: int,
    duration_ms: float,
) -> None:
    try:
        response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        summary = _response_validation._response_summary(response)
        context.emit(
            "failure",
            attempt=attempt,
            duration_ms=duration_ms,
            status_code=response.status_code,
            message=summary,
        )
        raise ProviderError(
            f"Provider '{context.provider_name}' {context.operation_name} failed with "
            f"status {response.status_code}: {summary}"
        ) from exc


def _record_response_extensions(
    response: httpx.Response,
    *,
    attempt: int,
    max_attempts: int,
    duration_ms: float,
) -> None:
    response.extensions["worldforge_attempt_number"] = attempt
    response.extensions["worldforge_max_attempts"] = max_attempts
    response.extensions["worldforge_duration_ms"] = duration_ms


def request_json_with_policy(
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
        emit_success_event=False,
        **kwargs,
    )
    _response_validation._reject_json_content_type(
        response,
        emit_event=emit_event,
        provider_name=provider_name,
        operation_name=operation_name,
        method=method,
        target=url,
        policy=policy,
        accepted_content_types=accepted_content_types,
    )
    payload = _response_validation._decode_json_object_response(
        response,
        emit_event=emit_event,
        provider_name=provider_name,
        operation_name=operation_name,
        method=method,
        target=url,
        policy=policy,
    )
    _response_validation._emit_response_validation_event(
        emit_event,
        response=response,
        provider_name=provider_name,
        operation_name=operation_name,
        phase="success",
        method=method,
        target=url,
        policy=policy,
    )
    return payload

"""Response validation helpers for HTTP-backed provider adapters."""

from __future__ import annotations

from collections.abc import Callable
from typing import Literal, NoReturn

import httpx

from worldforge.models import ProviderEvent, RequestOperationPolicy, _redact_observable_text

from .base import ProviderError


def _response_summary(response: httpx.Response) -> str:
    text = response.text.strip()
    if not text:
        return "empty response body"
    if len(text) > 200:
        text = f"{text[:197]}..."
    return _redact_observable_text(text)


def _content_type_is_allowed(content_type: str, accepted_content_types: tuple[str, ...]) -> bool:
    normalized = content_type.split(";", maxsplit=1)[0].strip().lower()
    for accepted in accepted_content_types:
        expected = accepted.lower()
        if expected.endswith("/") and normalized.startswith(expected):
            return True
        if normalized == expected:
            return True
    return False


def _emit_response_validation_event(
    emit_event: Callable[[ProviderEvent], None] | None,
    *,
    response: httpx.Response,
    provider_name: str,
    operation_name: str,
    phase: Literal["success", "failure"],
    method: str,
    target: str,
    policy: RequestOperationPolicy,
    message: str | None = None,
) -> None:
    if phase not in {"success", "failure"}:
        raise AssertionError("response validation event phase must be success or failure")
    if emit_event is None:
        return
    attempt = response.extensions.get("worldforge_attempt_number")
    max_attempts = response.extensions.get("worldforge_max_attempts")
    duration = response.extensions.get("worldforge_duration_ms")
    emit_event(
        ProviderEvent(
            provider=provider_name,
            operation=operation_name,
            phase=phase,
            attempt=attempt if isinstance(attempt, int) and not isinstance(attempt, bool) else 1,
            max_attempts=max_attempts
            if isinstance(max_attempts, int) and not isinstance(max_attempts, bool)
            else policy.retry.max_attempts,
            method=method,
            target=target,
            status_code=response.status_code,
            duration_ms=duration
            if isinstance(duration, int | float) and not isinstance(duration, bool)
            else None,
            message=message or "",
        )
    )


def _reject_json_content_type(
    response: httpx.Response,
    *,
    emit_event: Callable[[ProviderEvent], None] | None,
    provider_name: str,
    operation_name: str,
    method: str,
    target: str,
    policy: RequestOperationPolicy,
    accepted_content_types: tuple[str, ...] | None,
) -> None:
    content_type = response.headers.get("content-type")
    if (
        not content_type
        or not accepted_content_types
        or _content_type_is_allowed(content_type, accepted_content_types)
    ):
        return
    _raise_response_validation_error(
        emit_event,
        response=response,
        provider_name=provider_name,
        operation_name=operation_name,
        method=method,
        target=target,
        policy=policy,
        message=f"returned unsupported content type '{content_type}'.",
    )


def _decode_json_object_response(
    response: httpx.Response,
    *,
    emit_event: Callable[[ProviderEvent], None] | None,
    provider_name: str,
    operation_name: str,
    method: str,
    target: str,
    policy: RequestOperationPolicy,
) -> dict[str, object]:
    try:
        payload = response.json()
    except ValueError as exc:
        _raise_response_validation_error(
            emit_event,
            response=response,
            provider_name=provider_name,
            operation_name=operation_name,
            method=method,
            target=target,
            policy=policy,
            message="returned invalid JSON.",
            cause=exc,
        )
    if not isinstance(payload, dict):
        _raise_response_validation_error(
            emit_event,
            response=response,
            provider_name=provider_name,
            operation_name=operation_name,
            method=method,
            target=target,
            policy=policy,
            message="returned a non-object JSON payload.",
        )
    return dict(payload)


def _raise_response_validation_error(
    emit_event: Callable[[ProviderEvent], None] | None,
    *,
    response: httpx.Response,
    provider_name: str,
    operation_name: str,
    method: str,
    target: str,
    policy: RequestOperationPolicy,
    message: str,
    cause: Exception | None = None,
) -> NoReturn:
    _emit_response_validation_event(
        emit_event,
        response=response,
        provider_name=provider_name,
        operation_name=operation_name,
        phase="failure",
        method=method,
        target=target,
        policy=policy,
        message=message,
    )
    error = ProviderError(f"Provider '{provider_name}' {operation_name} {message}")
    if cause is not None:
        raise error from cause
    raise error

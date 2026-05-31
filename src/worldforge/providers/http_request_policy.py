"""Timing, retry, and budget helpers for HTTP-backed provider requests."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from time import perf_counter, sleep
from typing import Literal, NoReturn

import httpx

from worldforge.models import ProviderEvent, RequestOperationPolicy

from .base import ProviderBudgetExceededError, ProviderError

_RETRYABLE_EXCEPTIONS = (httpx.TransportError,)


@dataclass(frozen=True, slots=True)
class _HttpRequestContext:
    provider_name: str
    operation_name: str
    method: str
    url: str
    policy: RequestOperationPolicy
    emit_event: Callable[[ProviderEvent], None] | None

    @property
    def max_attempts(self) -> int:
        return self.policy.retry.max_attempts

    def emit(
        self,
        phase: Literal["failure", "retry", "success"],
        *,
        attempt: int,
        duration_ms: float | None,
        status_code: int | None = None,
        message: str = "",
        metadata: dict[str, object] | None = None,
    ) -> None:
        if self.emit_event is None:
            return
        self.emit_event(
            ProviderEvent(
                provider=self.provider_name,
                operation=self.operation_name,
                phase=phase,
                attempt=attempt,
                max_attempts=self.max_attempts,
                method=self.method,
                target=self.url,
                status_code=status_code,
                duration_ms=duration_ms,
                message=message,
                metadata=metadata or {},
            )
        )


def _elapsed_seconds(started: float) -> float:
    return max(0.0, perf_counter() - started)


def _duration_ms_since(started: float) -> float:
    return _elapsed_seconds(started) * 1000


def _request_timeout_seconds(
    policy: RequestOperationPolicy,
    remaining_seconds: float | None,
) -> float:
    if remaining_seconds is None:
        return policy.timeout_seconds
    return min(policy.timeout_seconds, max(remaining_seconds, 0.001))


def _budget_exceeded_message(
    *,
    provider_name: str,
    operation_name: str,
    elapsed_seconds: float,
    max_elapsed_seconds: float,
) -> str:
    return (
        f"Provider '{provider_name}' {operation_name} exceeded budget "
        f"{max_elapsed_seconds:.3f}s after {elapsed_seconds:.3f}s."
    )


def _emit_budget_exceeded(
    *,
    provider_name: str,
    operation_name: str,
    method: str,
    url: str,
    attempt: int,
    max_attempts: int,
    elapsed_seconds: float,
    max_elapsed_seconds: float,
    emit_event: Callable[[ProviderEvent], None] | None,
    status_code: int | None = None,
) -> None:
    if emit_event is None:
        return
    emit_event(
        ProviderEvent(
            provider=provider_name,
            operation=operation_name,
            phase="budget_exceeded",
            attempt=attempt,
            max_attempts=max_attempts,
            method=method,
            target=url,
            status_code=status_code,
            duration_ms=elapsed_seconds * 1000,
            message=_budget_exceeded_message(
                provider_name=provider_name,
                operation_name=operation_name,
                elapsed_seconds=elapsed_seconds,
                max_elapsed_seconds=max_elapsed_seconds,
            ),
            metadata={"max_elapsed_seconds": max_elapsed_seconds},
        )
    )


def _raise_budget_exceeded(
    *,
    provider_name: str,
    operation_name: str,
    elapsed_seconds: float,
    max_elapsed_seconds: float,
) -> NoReturn:
    raise ProviderBudgetExceededError(
        _budget_exceeded_message(
            provider_name=provider_name,
            operation_name=operation_name,
            elapsed_seconds=elapsed_seconds,
            max_elapsed_seconds=max_elapsed_seconds,
        )
    )


def _remaining_budget_seconds(policy: RequestOperationPolicy, *, started: float) -> float | None:
    if policy.max_elapsed_seconds is None:
        return None
    return policy.max_elapsed_seconds - _elapsed_seconds(started)


def _remaining_attempt_budget_seconds(
    context: _HttpRequestContext,
    *,
    operation_started: float,
    attempt: int,
    status_code: int | None = None,
) -> float | None:
    remaining_seconds = _remaining_budget_seconds(context.policy, started=operation_started)
    max_elapsed_seconds = context.policy.max_elapsed_seconds
    if remaining_seconds is None or remaining_seconds > 0.0 or max_elapsed_seconds is None:
        return remaining_seconds
    elapsed_seconds = _elapsed_seconds(operation_started)
    _emit_budget_exceeded(
        provider_name=context.provider_name,
        operation_name=context.operation_name,
        method=context.method,
        url=context.url,
        attempt=attempt,
        max_attempts=context.max_attempts,
        elapsed_seconds=elapsed_seconds,
        max_elapsed_seconds=max_elapsed_seconds,
        emit_event=context.emit_event,
        status_code=status_code,
    )
    _raise_budget_exceeded(
        provider_name=context.provider_name,
        operation_name=context.operation_name,
        elapsed_seconds=elapsed_seconds,
        max_elapsed_seconds=max_elapsed_seconds,
    )


def _retry_delay_or_raise_budget_exceeded(
    context: _HttpRequestContext,
    *,
    operation_started: float,
    attempt: int,
    status_code: int | None = None,
    on_budget_exceeded: Callable[[], None] | None = None,
) -> float:
    delay = context.policy.retry.delay_for_attempt(attempt + 1)
    max_elapsed_seconds = context.policy.max_elapsed_seconds
    if (
        max_elapsed_seconds is not None
        and _elapsed_seconds(operation_started) + delay > max_elapsed_seconds
    ):
        elapsed_seconds = _elapsed_seconds(operation_started)
        _emit_budget_exceeded(
            provider_name=context.provider_name,
            operation_name=context.operation_name,
            method=context.method,
            url=context.url,
            attempt=attempt,
            max_attempts=context.max_attempts,
            elapsed_seconds=elapsed_seconds,
            max_elapsed_seconds=max_elapsed_seconds,
            emit_event=context.emit_event,
            status_code=status_code,
        )
        if on_budget_exceeded is not None:
            on_budget_exceeded()
        _raise_budget_exceeded(
            provider_name=context.provider_name,
            operation_name=context.operation_name,
            elapsed_seconds=elapsed_seconds,
            max_elapsed_seconds=max_elapsed_seconds,
        )
    return delay


def _sleep_retry_delay(delay: float) -> None:
    if delay > 0.0:
        sleep(delay)


def _raise_status_summary_error(
    context: _HttpRequestContext,
    *,
    status_code: int,
    summary: str,
) -> NoReturn:
    raise ProviderError(
        f"Provider '{context.provider_name}' {context.operation_name} failed with "
        f"status {status_code}: {summary}"
    )


def _handle_retryable_transport_error(
    context: _HttpRequestContext,
    *,
    attempt: int,
    operation_started: float,
    attempt_started: float,
    error: httpx.TransportError,
) -> None:
    duration_ms = _duration_ms_since(attempt_started)
    if attempt >= context.max_attempts:
        context.emit(
            "failure",
            attempt=attempt,
            duration_ms=duration_ms,
            message=str(error),
        )
        raise ProviderError(
            f"Provider '{context.provider_name}' {context.operation_name} failed after "
            f"{attempt} attempt(s): {error}"
        ) from error
    delay = _retry_delay_or_raise_budget_exceeded(
        context,
        operation_started=operation_started,
        attempt=attempt,
    )
    context.emit(
        "retry",
        attempt=attempt,
        duration_ms=duration_ms,
        message=str(error),
        metadata={"next_delay_seconds": delay},
    )
    _sleep_retry_delay(delay)


def _raise_nonretryable_http_error(
    context: _HttpRequestContext,
    *,
    attempt: int,
    attempt_started: float,
    error: httpx.HTTPError,
) -> NoReturn:
    context.emit(
        "failure",
        attempt=attempt,
        duration_ms=_duration_ms_since(attempt_started),
        message=str(error),
    )
    raise ProviderError(
        f"Provider '{context.provider_name}' {context.operation_name} failed: {error}"
    ) from error


def _retry_response_or_raise_status(
    context: _HttpRequestContext,
    *,
    response: httpx.Response,
    summary: str,
    attempt: int,
    operation_started: float,
    attempt_started: float,
) -> float:
    duration_ms = _duration_ms_since(attempt_started)
    if attempt >= context.max_attempts:
        context.emit(
            "failure",
            attempt=attempt,
            duration_ms=duration_ms,
            status_code=response.status_code,
            message=summary,
        )
        response.close()
        _raise_status_summary_error(
            context,
            status_code=response.status_code,
            summary=summary,
        )
    delay = _retry_delay_or_raise_budget_exceeded(
        context,
        operation_started=operation_started,
        attempt=attempt,
        status_code=response.status_code,
        on_budget_exceeded=response.close,
    )
    context.emit(
        "retry",
        attempt=attempt,
        duration_ms=duration_ms,
        status_code=response.status_code,
        message=summary,
        metadata={"next_delay_seconds": delay},
    )
    return delay

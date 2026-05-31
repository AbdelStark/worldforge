"""Polling helpers for HTTP-backed provider task APIs."""

from __future__ import annotations

from collections.abc import Callable

import httpx

from worldforge.models import ProviderEvent, RequestOperationPolicy

from . import http_request_policy as _request_policy
from .base import ProviderError
from .http_requests import request_json_with_policy


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

    operation_started = _request_policy.perf_counter()
    for poll_number in range(1, max_polls + 1):
        remaining_seconds = _request_policy._remaining_budget_seconds(
            operation_policy, started=operation_started
        )
        if remaining_seconds is not None and remaining_seconds <= 0.0:
            _raise_poll_budget_exceeded(
                provider_name=provider_name,
                path=path,
                poll_number=poll_number,
                operation_policy=operation_policy,
                operation_started=operation_started,
                emit_event=emit_event,
            )
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
        if _delay_exceeds_poll_budget(
            operation_policy,
            operation_started=operation_started,
            poll_interval_seconds=poll_interval_seconds,
        ):
            _raise_poll_budget_exceeded(
                provider_name=provider_name,
                path=path,
                poll_number=operation_policy.retry.max_attempts,
                operation_policy=operation_policy,
                operation_started=operation_started,
                emit_event=emit_event,
            )
        _request_policy.sleep(poll_interval_seconds)
    raise ProviderError(f"Provider '{provider_name}' task did not complete before timeout.")


def _delay_exceeds_poll_budget(
    operation_policy: RequestOperationPolicy,
    *,
    operation_started: float,
    poll_interval_seconds: float,
) -> bool:
    if operation_policy.max_elapsed_seconds is None:
        return False
    elapsed_after_delay = (
        _request_policy._elapsed_seconds(operation_started) + poll_interval_seconds
    )
    return elapsed_after_delay > operation_policy.max_elapsed_seconds


def _raise_poll_budget_exceeded(
    *,
    provider_name: str,
    path: str,
    poll_number: int,
    operation_policy: RequestOperationPolicy,
    operation_started: float,
    emit_event: Callable[[ProviderEvent], None] | None,
) -> None:
    elapsed_seconds = _request_policy._elapsed_seconds(operation_started)
    max_elapsed_seconds = operation_policy.max_elapsed_seconds
    if max_elapsed_seconds is None:
        raise AssertionError("poll budget exceeded helper requires max_elapsed_seconds")
    _request_policy._emit_budget_exceeded(
        provider_name=provider_name,
        operation_name="task poll",
        method="GET",
        url=path,
        attempt=min(poll_number, operation_policy.retry.max_attempts),
        max_attempts=operation_policy.retry.max_attempts,
        elapsed_seconds=elapsed_seconds,
        max_elapsed_seconds=max_elapsed_seconds,
        emit_event=emit_event,
    )
    _request_policy._raise_budget_exceeded(
        provider_name=provider_name,
        operation_name="task poll",
        elapsed_seconds=elapsed_seconds,
        max_elapsed_seconds=max_elapsed_seconds,
    )

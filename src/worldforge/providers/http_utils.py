"""Shared helpers for HTTP-backed provider adapters."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from time import perf_counter, sleep
from typing import Any

import httpx

from worldforge.models import ProviderEvent, RequestOperationPolicy

from . import http_assets as _http_assets
from . import http_downloads as _http_downloads
from . import http_polling as _http_polling
from . import http_request_policy as _request_policy
from . import http_requests as _http_requests
from . import http_response_validation as _response_validation
from . import http_url_validation as _url_validation

_RETRYABLE_EXCEPTIONS = _request_policy._RETRYABLE_EXCEPTIONS
_DNS_RESOLUTION_TIMEOUT_SECONDS = _url_validation._DNS_RESOLUTION_TIMEOUT_SECONDS
_DNS_RESULT_QUEUE_TIMEOUT_SECONDS = _url_validation._DNS_RESULT_QUEUE_TIMEOUT_SECONDS
_DNS_RESOLUTION_CACHE_SECONDS = _url_validation._DNS_RESOLUTION_CACHE_SECONDS
_DNS_RESOLUTION_CACHE_MAX_ENTRIES = _url_validation._DNS_RESOLUTION_CACHE_MAX_ENTRIES
_DNS_RESOLUTION_CACHE = _url_validation._DNS_RESOLUTION_CACHE
_ParsedRemoteURL = _url_validation._ParsedRemoteURL
multiprocessing = _url_validation.multiprocessing
_ERROR_SUMMARY_BYTES = _http_downloads._ERROR_SUMMARY_BYTES

asset_to_uri = _http_assets.asset_to_uri
_content_type_is_allowed = _response_validation._content_type_is_allowed
_decode_json_object_response = _response_validation._decode_json_object_response
_emit_response_validation_event = _response_validation._emit_response_validation_event
_raise_response_validation_error = _response_validation._raise_response_validation_error
_reject_json_content_type = _response_validation._reject_json_content_type
_response_summary = _response_validation._response_summary
_HttpRequestContext = _request_policy._HttpRequestContext
_budget_exceeded_message = _request_policy._budget_exceeded_message
_duration_ms_since = _request_policy._duration_ms_since
_elapsed_seconds = _request_policy._elapsed_seconds
_emit_budget_exceeded = _request_policy._emit_budget_exceeded
_handle_retryable_transport_error = _request_policy._handle_retryable_transport_error
_raise_budget_exceeded = _request_policy._raise_budget_exceeded
_raise_nonretryable_http_error = _request_policy._raise_nonretryable_http_error
_raise_status_summary_error = _request_policy._raise_status_summary_error
_remaining_attempt_budget_seconds = _request_policy._remaining_attempt_budget_seconds
_remaining_budget_seconds = _request_policy._remaining_budget_seconds
_request_timeout_seconds = _request_policy._request_timeout_seconds
_retry_delay_or_raise_budget_exceeded = _request_policy._retry_delay_or_raise_budget_exceeded
_retry_response_or_raise_status = _request_policy._retry_response_or_raise_status
_sleep_retry_delay = _request_policy._sleep_retry_delay
_emit_stream_success = _http_downloads._emit_stream_success
_raise_for_stream_status = _http_downloads._raise_for_stream_status
_read_response_bytes = _http_downloads._read_response_bytes
_reject_oversized_content_length = _http_downloads._reject_oversized_content_length
_reject_stream_content_type = _http_downloads._reject_stream_content_type
_request_bytes_attempt = _http_downloads._request_bytes_attempt
_request_bytes_with_context = _http_downloads._request_bytes_with_context
_retry_stream_response = _http_downloads._retry_stream_response
_stream_response_summary = _http_downloads._stream_response_summary
_validate_download_size_limit = _http_downloads._validate_download_size_limit
_finalize_response_attempt = _http_requests._finalize_response_attempt
_raise_for_response_status = _http_requests._raise_for_response_status
_record_response_extensions = _http_requests._record_response_extensions
_request_attempt_or_retry = _http_requests._request_attempt_or_retry
_request_with_context = _http_requests._request_with_context


def _sync_request_policy_runtime() -> None:
    _request_policy.perf_counter = perf_counter
    _request_policy.sleep = sleep


def _sync_download_runtime() -> None:
    _sync_request_policy_runtime()
    _http_downloads.perf_counter = perf_counter


def _sync_url_validation_config() -> None:
    _sync_request_policy_runtime()
    _url_validation.perf_counter = perf_counter
    _url_validation._DNS_RESULT_QUEUE_TIMEOUT_SECONDS = _DNS_RESULT_QUEUE_TIMEOUT_SECONDS
    _url_validation._DNS_RESOLUTION_CACHE_SECONDS = _DNS_RESOLUTION_CACHE_SECONDS
    _url_validation._DNS_RESOLUTION_CACHE_MAX_ENTRIES = _DNS_RESOLUTION_CACHE_MAX_ENTRIES


def validate_remote_url(
    url: str,
    *,
    provider_name: str,
    url_name: str,
    allow_local_network: bool = False,
    resolve_dns: bool = True,
    dns_resolution_timeout_seconds: float = _DNS_RESOLUTION_TIMEOUT_SECONDS,
) -> str:
    """Return a stripped HTTP URL after blocking local/private destinations."""

    return _url_validation.validate_remote_url(
        url,
        provider_name=provider_name,
        url_name=url_name,
        allow_local_network=allow_local_network,
        resolve_dns=resolve_dns,
        dns_resolution_timeout_seconds=dns_resolution_timeout_seconds,
        dns_resolver=_getaddrinfo_with_timeout,
    )


def validate_remote_base_url(
    base_url: str,
    *,
    provider_name: str,
    env_var: str,
    allow_local_network: bool = False,
    resolve_dns: bool = True,
    allowed_hosts: Sequence[str] | None = None,
    dns_resolution_timeout_seconds: float = _DNS_RESOLUTION_TIMEOUT_SECONDS,
) -> str:
    """Return a normalized HTTP base URL after preflight destination checks."""

    return _url_validation.validate_remote_base_url(
        base_url,
        provider_name=provider_name,
        env_var=env_var,
        allow_local_network=allow_local_network,
        resolve_dns=resolve_dns,
        allowed_hosts=allowed_hosts,
        dns_resolution_timeout_seconds=dns_resolution_timeout_seconds,
        dns_resolver=_getaddrinfo_with_timeout,
    )


def _resolve_getaddrinfo_worker(
    host: str,
    port: int,
    result_queue: Any,
) -> None:
    _url_validation._resolve_getaddrinfo_worker(host, port, result_queue)


def _getaddrinfo_with_timeout(
    host: str,
    port: int,
    *,
    timeout_seconds: float,
) -> list[str]:
    _sync_url_validation_config()
    return _url_validation._getaddrinfo_with_timeout(
        host,
        port,
        timeout_seconds=timeout_seconds,
    )


def _cached_dns_resolution(
    cache_key: tuple[str, int],
    *,
    now: float,
) -> tuple[str, ...] | None:
    _sync_url_validation_config()
    return _url_validation._cached_dns_resolution(cache_key, now=now)


def _join_dns_resolver(resolver: Any, *, timeout_seconds: float) -> None:
    _url_validation._join_dns_resolver(resolver, timeout_seconds=timeout_seconds)


def _read_dns_resolution_result(
    result_queue: Any,
    *,
    started: float,
    timeout_seconds: float,
) -> tuple[str, object]:
    _sync_url_validation_config()
    return _url_validation._read_dns_resolution_result(
        result_queue,
        started=started,
        timeout_seconds=timeout_seconds,
    )


def _dns_addresses_from_result(status: str, value: object) -> tuple[str, ...]:
    return _url_validation._dns_addresses_from_result(status, value)


def _cleanup_dns_resolver(
    resolver: Any,
    result_queue: Any,
    *,
    resolver_started: bool,
) -> None:
    _url_validation._cleanup_dns_resolver(
        resolver,
        result_queue,
        resolver_started=resolver_started,
    )


def _cache_dns_resolution(cache_key: tuple[str, int], addresses: tuple[str, ...]) -> None:
    _sync_url_validation_config()
    _url_validation._cache_dns_resolution(cache_key, addresses)


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

    _sync_request_policy_runtime()
    return _http_requests.request_with_policy(
        client,
        method=method,
        url=url,
        provider_name=provider_name,
        operation_name=operation_name,
        policy=policy,
        emit_event=emit_event,
        emit_success_event=emit_success_event,
        **kwargs,
    )


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

    _sync_request_policy_runtime()
    return _http_requests.request_json_with_policy(
        client,
        method=method,
        url=url,
        provider_name=provider_name,
        operation_name=operation_name,
        policy=policy,
        emit_event=emit_event,
        accepted_content_types=accepted_content_types,
        **kwargs,
    )


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

    _sync_download_runtime()
    return _http_downloads.request_bytes_with_policy(
        client,
        method=method,
        url=url,
        provider_name=provider_name,
        operation_name=operation_name,
        policy=policy,
        emit_event=emit_event,
        accepted_content_types=accepted_content_types,
        max_bytes=max_bytes,
        **kwargs,
    )


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

    _sync_request_policy_runtime()
    return _http_polling.poll_json_task(
        client,
        path=path,
        status_key=status_key,
        success_values=success_values,
        failure_values=failure_values,
        poll_interval_seconds=poll_interval_seconds,
        max_polls=max_polls,
        provider_name=provider_name,
        operation_policy=operation_policy,
        emit_event=emit_event,
    )

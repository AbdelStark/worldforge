"""Shared helpers for HTTP-backed provider adapters."""

from __future__ import annotations

import base64
import fnmatch
import ipaddress
import mimetypes
import multiprocessing
import queue
import socket
from collections import OrderedDict
from collections.abc import Callable, Sequence
from pathlib import Path
from time import perf_counter, sleep
from typing import Any
from urllib.parse import urlparse

import httpx

from worldforge.models import (
    GenerationOptions,
    ProviderEvent,
    RequestOperationPolicy,
    VideoClip,
    _redact_observable_text,
)

from .base import ProviderBudgetExceededError, ProviderError

_RETRYABLE_EXCEPTIONS = (httpx.TransportError,)
_LOCAL_HOST_NAMES = frozenset({"localhost", "localhost.localdomain"})
_DNS_RESOLUTION_TIMEOUT_SECONDS = 2.0
_DNS_RESULT_QUEUE_TIMEOUT_SECONDS = 1.0
_DNS_RESOLUTION_CACHE_SECONDS = 5.0
_DNS_RESOLUTION_CACHE_MAX_ENTRIES = 256
_DNS_RESOLUTION_CACHE: OrderedDict[tuple[str, int], tuple[float, tuple[str, ...]]] = OrderedDict()
_ERROR_SUMMARY_BYTES = 512


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

    if not isinstance(url, str) or not url.strip():
        raise ProviderError(f"Provider '{provider_name}' {url_name} must be a non-empty URL.")
    normalized_url = url.strip()
    parsed = urlparse(normalized_url)
    if parsed.scheme.lower() not in {"http", "https"}:
        raise ProviderError(f"Provider '{provider_name}' {url_name} must use an http or https URL.")
    if not parsed.hostname:
        raise ProviderError(f"Provider '{provider_name}' {url_name} must include a hostname.")
    if parsed.username or parsed.password:
        raise ProviderError(
            f"Provider '{provider_name}' {url_name} must not include embedded credentials."
        )

    host = parsed.hostname.strip().lower()
    if not allow_local_network:
        _reject_local_hostname(host, provider_name=provider_name, env_var=url_name)
        is_ip_literal = _reject_local_ip_literal(
            host,
            provider_name=provider_name,
            env_var=url_name,
        )
        if resolve_dns and not is_ip_literal:
            _reject_local_resolved_addresses(
                host,
                port=parsed.port or (443 if parsed.scheme.lower() == "https" else 80),
                provider_name=provider_name,
                env_var=url_name,
                timeout_seconds=dns_resolution_timeout_seconds,
            )
    return normalized_url


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

    parsed = urlparse(base_url)
    if parsed.scheme.lower() not in {"http", "https"}:
        raise ProviderError(f"Provider '{provider_name}' {env_var} must use an http or https URL.")
    if not parsed.hostname:
        raise ProviderError(f"Provider '{provider_name}' {env_var} must include a hostname.")
    if parsed.username or parsed.password:
        raise ProviderError(
            f"Provider '{provider_name}' {env_var} must not include embedded credentials."
        )
    if parsed.query or parsed.fragment:
        raise ProviderError(
            f"Provider '{provider_name}' {env_var} must not include query parameters or fragments."
        )

    host = parsed.hostname.strip().lower()
    _reject_unlisted_host(
        host,
        allowed_hosts=allowed_hosts,
        provider_name=provider_name,
        env_var=env_var,
    )
    if not allow_local_network:
        _reject_local_hostname(host, provider_name=provider_name, env_var=env_var)
        is_ip_literal = _reject_local_ip_literal(
            host,
            provider_name=provider_name,
            env_var=env_var,
        )
        if resolve_dns and not is_ip_literal:
            _reject_local_resolved_addresses(
                host,
                port=parsed.port or (443 if parsed.scheme.lower() == "https" else 80),
                provider_name=provider_name,
                env_var=env_var,
                timeout_seconds=dns_resolution_timeout_seconds,
            )
    return base_url.rstrip("/")


def _reject_unlisted_host(
    host: str,
    *,
    allowed_hosts: Sequence[str] | None,
    provider_name: str,
    env_var: str,
) -> None:
    if allowed_hosts is None:
        return
    normalized_patterns = tuple(
        pattern.strip().lower() for pattern in allowed_hosts if pattern.strip()
    )
    if not normalized_patterns:
        raise ProviderError(
            f"Provider '{provider_name}' {env_var} allowed hosts must not be empty."
        )
    if any(fnmatch.fnmatchcase(host, pattern) for pattern in normalized_patterns):
        return
    raise ProviderError(
        f"Provider '{provider_name}' {env_var} host '{host}' is not in the allowed host list."
    )


def _reject_local_hostname(host: str, *, provider_name: str, env_var: str) -> None:
    if host in _LOCAL_HOST_NAMES or host.endswith(".localhost"):
        raise ProviderError(
            f"Provider '{provider_name}' {env_var} resolves to a local/private destination. "
            "Set the provider's explicit local-network opt-in only for trusted local servers."
        )


def _reject_local_ip_literal(host: str, *, provider_name: str, env_var: str) -> bool:
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        return False
    _reject_local_address(address, provider_name=provider_name, env_var=env_var)
    return True


def _reject_local_resolved_addresses(
    host: str,
    *,
    port: int,
    provider_name: str,
    env_var: str,
    timeout_seconds: float,
) -> None:
    try:
        addresses = [
            ipaddress.ip_address(address)
            for address in _getaddrinfo_with_timeout(
                host,
                port,
                timeout_seconds=timeout_seconds,
            )
        ]
    except TimeoutError as exc:
        raise ProviderError(
            f"Provider '{provider_name}' {env_var} host resolution timed out: {host}."
        ) from exc
    except socket.gaierror as exc:
        raise ProviderError(
            f"Provider '{provider_name}' {env_var} host could not be resolved: {host}."
        ) from exc
    except (OSError, RuntimeError, ValueError) as exc:
        raise ProviderError(
            f"Provider '{provider_name}' {env_var} host resolution failed: {host}."
        ) from exc
    for address in addresses:
        _reject_local_address(
            address,
            provider_name=provider_name,
            env_var=env_var,
        )


def _resolve_getaddrinfo_worker(
    host: str,
    port: int,
    result_queue: multiprocessing.Queue,
) -> None:
    try:
        addresses = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        result_queue.put(("gaierror", (exc.errno, exc.strerror)))
        return
    result_queue.put(("ok", [address[4][0] for address in addresses]))


def _getaddrinfo_with_timeout(
    host: str,
    port: int,
    *,
    timeout_seconds: float,
) -> list[str]:
    if timeout_seconds <= 0:
        raise TimeoutError("DNS resolution timeout must be greater than 0.")

    cache_key = (host, port)
    cached = _DNS_RESOLUTION_CACHE.get(cache_key)
    now = perf_counter()
    if cached is not None:
        cached_at, cached_addresses = cached
        if now - cached_at <= _DNS_RESOLUTION_CACHE_SECONDS:
            _DNS_RESOLUTION_CACHE.move_to_end(cache_key)
            return list(cached_addresses)
        del _DNS_RESOLUTION_CACHE[cache_key]

    context = multiprocessing.get_context("spawn")
    result_queue = context.Queue(maxsize=1)
    resolver = context.Process(
        target=_resolve_getaddrinfo_worker,
        args=(host, port, result_queue),
        name=f"worldforge-dns-resolver-{host}",
    )
    resolver_started = False
    started = perf_counter()
    try:
        resolver.start()
        resolver_started = True
        resolver.join(timeout_seconds)
        if resolver.is_alive():
            resolver.terminate()
            resolver.join()
            raise TimeoutError(f"DNS resolution exceeded {timeout_seconds:.1f}s.")

        if resolver.exitcode not in (0, None):
            raise socket.gaierror(
                socket.EAI_FAIL,
                f"DNS resolver process exited with code {resolver.exitcode}",
            )
        elapsed_seconds = perf_counter() - started
        remaining_seconds = timeout_seconds - elapsed_seconds
        try:
            if remaining_seconds <= 0:
                status, value = result_queue.get_nowait()
            else:
                status, value = result_queue.get(
                    timeout=min(_DNS_RESULT_QUEUE_TIMEOUT_SECONDS, remaining_seconds)
                )
        except queue.Empty as exc:
            if perf_counter() - started >= timeout_seconds:
                raise TimeoutError(f"DNS resolution exceeded {timeout_seconds:.1f}s.") from exc
            raise socket.gaierror(socket.EAI_FAIL, "DNS resolver returned no result") from exc
        if status == "gaierror":
            error_number, error_text = value
            raise socket.gaierror(error_number, error_text)
        if status != "ok":
            raise socket.gaierror(socket.EAI_FAIL, "DNS resolver returned an invalid result")
        addresses = tuple(value)
        _cache_dns_resolution(cache_key, addresses)
        return list(addresses)
    finally:
        if resolver_started and resolver.is_alive():
            resolver.terminate()
            resolver.join()
        result_queue.close()
        result_queue.join_thread()


def _cache_dns_resolution(cache_key: tuple[str, int], addresses: tuple[str, ...]) -> None:
    _DNS_RESOLUTION_CACHE[cache_key] = (perf_counter(), addresses)
    _DNS_RESOLUTION_CACHE.move_to_end(cache_key)
    while len(_DNS_RESOLUTION_CACHE) > _DNS_RESOLUTION_CACHE_MAX_ENTRIES:
        _DNS_RESOLUTION_CACHE.popitem(last=False)


def _reject_local_address(
    address: ipaddress.IPv4Address | ipaddress.IPv6Address,
    *,
    provider_name: str,
    env_var: str,
) -> None:
    if (
        address.is_loopback
        or address.is_private
        or address.is_link_local
        or address.is_unspecified
        or address.is_reserved
        or address.is_multicast
    ):
        raise ProviderError(
            f"Provider '{provider_name}' {env_var} resolves to a local/private destination. "
            "Set the provider's explicit local-network opt-in only for trusted local servers."
        )


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
        text = f"{text[:197]}..."
    return _redact_observable_text(text)


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


def _elapsed_seconds(started: float) -> float:
    return max(0.0, perf_counter() - started)


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
) -> None:
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
    emit_success_event: bool = True,
    **kwargs: Any,
) -> httpx.Response:
    """Send an HTTP request using the configured timeout and retry policy."""

    operation_started = perf_counter()
    for attempt_number in range(1, policy.retry.max_attempts + 1):
        remaining_seconds = _remaining_budget_seconds(policy, started=operation_started)
        if remaining_seconds is not None and remaining_seconds <= 0.0:
            elapsed_seconds = _elapsed_seconds(operation_started)
            _emit_budget_exceeded(
                provider_name=provider_name,
                operation_name=operation_name,
                method=method,
                url=url,
                attempt=attempt_number,
                max_attempts=policy.retry.max_attempts,
                elapsed_seconds=elapsed_seconds,
                max_elapsed_seconds=policy.max_elapsed_seconds,
                emit_event=emit_event,
            )
            _raise_budget_exceeded(
                provider_name=provider_name,
                operation_name=operation_name,
                elapsed_seconds=elapsed_seconds,
                max_elapsed_seconds=policy.max_elapsed_seconds,
            )
        started = perf_counter()
        try:
            response = client.request(
                method,
                url,
                timeout=(
                    policy.timeout_seconds
                    if remaining_seconds is None
                    else min(policy.timeout_seconds, max(remaining_seconds, 0.001))
                ),
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
            elapsed_after_delay = _elapsed_seconds(operation_started) + delay
            if (
                policy.max_elapsed_seconds is not None
                and elapsed_after_delay > policy.max_elapsed_seconds
            ):
                elapsed_seconds = _elapsed_seconds(operation_started)
                _emit_budget_exceeded(
                    provider_name=provider_name,
                    operation_name=operation_name,
                    method=method,
                    url=url,
                    attempt=attempt_number,
                    max_attempts=policy.retry.max_attempts,
                    elapsed_seconds=elapsed_seconds,
                    max_elapsed_seconds=policy.max_elapsed_seconds,
                    emit_event=emit_event,
                )
                _raise_budget_exceeded(
                    provider_name=provider_name,
                    operation_name=operation_name,
                    elapsed_seconds=elapsed_seconds,
                    max_elapsed_seconds=policy.max_elapsed_seconds,
                )
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
            elapsed_after_delay = _elapsed_seconds(operation_started) + delay
            if (
                policy.max_elapsed_seconds is not None
                and elapsed_after_delay > policy.max_elapsed_seconds
            ):
                elapsed_seconds = _elapsed_seconds(operation_started)
                _emit_budget_exceeded(
                    provider_name=provider_name,
                    operation_name=operation_name,
                    method=method,
                    url=url,
                    attempt=attempt_number,
                    max_attempts=policy.retry.max_attempts,
                    elapsed_seconds=elapsed_seconds,
                    max_elapsed_seconds=policy.max_elapsed_seconds,
                    emit_event=emit_event,
                    status_code=response.status_code,
                )
                response.close()
                _raise_budget_exceeded(
                    provider_name=provider_name,
                    operation_name=operation_name,
                    elapsed_seconds=elapsed_seconds,
                    max_elapsed_seconds=policy.max_elapsed_seconds,
                )
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
        response.extensions["worldforge_attempt_number"] = attempt_number
        response.extensions["worldforge_max_attempts"] = policy.retry.max_attempts
        response.extensions["worldforge_duration_ms"] = duration_ms
        if emit_success_event and emit_event is not None:
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


def _emit_response_validation_event(
    emit_event: Callable[[ProviderEvent], None] | None,
    *,
    response: httpx.Response,
    provider_name: str,
    operation_name: str,
    phase: str,
    method: str,
    target: str,
    policy: RequestOperationPolicy,
    message: str | None = None,
) -> None:
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
    content_type = response.headers.get("content-type")
    if (
        content_type
        and accepted_content_types
        and not _content_type_is_allowed(
            content_type,
            accepted_content_types,
        )
    ):
        message = f"returned unsupported content type '{content_type}'."
        _emit_response_validation_event(
            emit_event,
            response=response,
            provider_name=provider_name,
            operation_name=operation_name,
            phase="failure",
            method=method,
            target=url,
            policy=policy,
            message=message,
        )
        raise ProviderError(f"Provider '{provider_name}' {operation_name} {message}")
    try:
        payload = response.json()
    except ValueError as exc:
        message = "returned invalid JSON."
        _emit_response_validation_event(
            emit_event,
            response=response,
            provider_name=provider_name,
            operation_name=operation_name,
            phase="failure",
            method=method,
            target=url,
            policy=policy,
            message=message,
        )
        raise ProviderError(f"Provider '{provider_name}' {operation_name} {message}") from exc
    if not isinstance(payload, dict):
        message = "returned a non-object JSON payload."
        _emit_response_validation_event(
            emit_event,
            response=response,
            provider_name=provider_name,
            operation_name=operation_name,
            phase="failure",
            method=method,
            target=url,
            policy=policy,
            message=message,
        )
        raise ProviderError(f"Provider '{provider_name}' {operation_name} {message}")
    _emit_response_validation_event(
        emit_event,
        response=response,
        provider_name=provider_name,
        operation_name=operation_name,
        phase="success",
        method=method,
        target=url,
        policy=policy,
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
    max_bytes: int | None = None,
    **kwargs: Any,
) -> bytes:
    """Send an HTTP request and stream raw response bytes with an optional hard cap."""

    if max_bytes is not None and max_bytes <= 0:
        raise ProviderError(
            f"Provider '{provider_name}' {operation_name} max_bytes must be greater than 0."
        )

    operation_started = perf_counter()
    for attempt_number in range(1, policy.retry.max_attempts + 1):
        remaining_seconds = _remaining_budget_seconds(policy, started=operation_started)
        if remaining_seconds is not None and remaining_seconds <= 0.0:
            elapsed_seconds = _elapsed_seconds(operation_started)
            _emit_budget_exceeded(
                provider_name=provider_name,
                operation_name=operation_name,
                method=method,
                url=url,
                attempt=attempt_number,
                max_attempts=policy.retry.max_attempts,
                elapsed_seconds=elapsed_seconds,
                max_elapsed_seconds=policy.max_elapsed_seconds,
                emit_event=emit_event,
            )
            _raise_budget_exceeded(
                provider_name=provider_name,
                operation_name=operation_name,
                elapsed_seconds=elapsed_seconds,
                max_elapsed_seconds=policy.max_elapsed_seconds,
            )
        started = perf_counter()
        try:
            with client.stream(
                method,
                url,
                timeout=(
                    policy.timeout_seconds
                    if remaining_seconds is None
                    else min(policy.timeout_seconds, max(remaining_seconds, 0.001))
                ),
                **kwargs,
            ) as response:
                duration_ms = max(0.0, (perf_counter() - started) * 1000)
                if response.status_code in policy.retry.retryable_status_codes:
                    if attempt_number >= policy.retry.max_attempts:
                        summary = _stream_response_summary(response)
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
                                    message=summary,
                                )
                            )
                        raise ProviderError(
                            f"Provider '{provider_name}' {operation_name} failed with "
                            f"status {response.status_code}: {summary}"
                        )
                    delay = policy.retry.delay_for_attempt(attempt_number + 1)
                    elapsed_after_delay = _elapsed_seconds(operation_started) + delay
                    if (
                        policy.max_elapsed_seconds is not None
                        and elapsed_after_delay > policy.max_elapsed_seconds
                    ):
                        elapsed_seconds = _elapsed_seconds(operation_started)
                        _emit_budget_exceeded(
                            provider_name=provider_name,
                            operation_name=operation_name,
                            method=method,
                            url=url,
                            attempt=attempt_number,
                            max_attempts=policy.retry.max_attempts,
                            elapsed_seconds=elapsed_seconds,
                            max_elapsed_seconds=policy.max_elapsed_seconds,
                            emit_event=emit_event,
                            status_code=response.status_code,
                        )
                        _raise_budget_exceeded(
                            provider_name=provider_name,
                            operation_name=operation_name,
                            elapsed_seconds=elapsed_seconds,
                            max_elapsed_seconds=policy.max_elapsed_seconds,
                        )
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
                                message=_stream_response_summary(response),
                                metadata={"next_delay_seconds": delay},
                            )
                        )
                    if delay > 0.0:
                        response.close()
                        sleep(delay)
                    continue

                if response.status_code >= 400:
                    summary = _stream_response_summary(response)
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
                                message=summary,
                            )
                        )
                    raise ProviderError(
                        f"Provider '{provider_name}' {operation_name} failed with "
                        f"status {response.status_code}: {summary}"
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
                    message = (
                        f"Provider '{provider_name}' {operation_name} returned unsupported "
                        f"content type '{content_type}'."
                    )
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
                                message=message,
                            )
                        )
                    raise ProviderError(message)

                _reject_oversized_content_length(
                    response,
                    provider_name=provider_name,
                    operation_name=operation_name,
                    max_bytes=max_bytes,
                )
                data = _read_response_bytes(
                    response,
                    provider_name=provider_name,
                    operation_name=operation_name,
                    max_bytes=max_bytes,
                )
                duration_ms = max(0.0, (perf_counter() - started) * 1000)
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
                            metadata={"bytes": len(data)},
                        )
                    )
                return data
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
            elapsed_after_delay = _elapsed_seconds(operation_started) + delay
            if (
                policy.max_elapsed_seconds is not None
                and elapsed_after_delay > policy.max_elapsed_seconds
            ):
                elapsed_seconds = _elapsed_seconds(operation_started)
                _emit_budget_exceeded(
                    provider_name=provider_name,
                    operation_name=operation_name,
                    method=method,
                    url=url,
                    attempt=attempt_number,
                    max_attempts=policy.retry.max_attempts,
                    elapsed_seconds=elapsed_seconds,
                    max_elapsed_seconds=policy.max_elapsed_seconds,
                    emit_event=emit_event,
                )
                _raise_budget_exceeded(
                    provider_name=provider_name,
                    operation_name=operation_name,
                    elapsed_seconds=elapsed_seconds,
                    max_elapsed_seconds=policy.max_elapsed_seconds,
                )
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

    raise AssertionError("request_bytes_with_policy exhausted retries without returning or raising")


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

    operation_started = perf_counter()
    for poll_number in range(1, max_polls + 1):
        remaining_seconds = _remaining_budget_seconds(operation_policy, started=operation_started)
        if remaining_seconds is not None and remaining_seconds <= 0.0:
            elapsed_seconds = _elapsed_seconds(operation_started)
            _emit_budget_exceeded(
                provider_name=provider_name,
                operation_name="task poll",
                method="GET",
                url=path,
                attempt=min(poll_number, operation_policy.retry.max_attempts),
                max_attempts=operation_policy.retry.max_attempts,
                elapsed_seconds=elapsed_seconds,
                max_elapsed_seconds=operation_policy.max_elapsed_seconds,
                emit_event=emit_event,
            )
            _raise_budget_exceeded(
                provider_name=provider_name,
                operation_name="task poll",
                elapsed_seconds=elapsed_seconds,
                max_elapsed_seconds=operation_policy.max_elapsed_seconds,
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
        elapsed_after_delay = _elapsed_seconds(operation_started) + poll_interval_seconds
        if (
            operation_policy.max_elapsed_seconds is not None
            and elapsed_after_delay > operation_policy.max_elapsed_seconds
        ):
            elapsed_seconds = _elapsed_seconds(operation_started)
            _emit_budget_exceeded(
                provider_name=provider_name,
                operation_name="task poll",
                method="GET",
                url=path,
                attempt=operation_policy.retry.max_attempts,
                max_attempts=operation_policy.retry.max_attempts,
                elapsed_seconds=elapsed_seconds,
                max_elapsed_seconds=operation_policy.max_elapsed_seconds,
                emit_event=emit_event,
            )
            _raise_budget_exceeded(
                provider_name=provider_name,
                operation_name="task poll",
                elapsed_seconds=elapsed_seconds,
                max_elapsed_seconds=operation_policy.max_elapsed_seconds,
            )
        sleep(poll_interval_seconds)
    raise ProviderError(f"Provider '{provider_name}' task did not complete before timeout.")

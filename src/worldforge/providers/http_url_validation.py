"""Remote URL and DNS safety checks for HTTP-backed providers."""

from __future__ import annotations

import fnmatch
import ipaddress
import multiprocessing
import queue
import socket
from collections import OrderedDict
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from time import perf_counter
from typing import Any
from urllib.parse import ParseResult, urlparse

from .base import ProviderError

_LOCAL_HOST_NAMES = frozenset({"localhost", "localhost.localdomain"})
_DNS_RESOLUTION_TIMEOUT_SECONDS = 2.0
_DNS_RESULT_QUEUE_TIMEOUT_SECONDS = 1.0
_DNS_RESOLUTION_CACHE_SECONDS = 5.0
_DNS_RESOLUTION_CACHE_MAX_ENTRIES = 256
_DNS_RESOLUTION_CACHE: OrderedDict[tuple[str, int], tuple[float, tuple[str, ...]]] = OrderedDict()

_DNSResolver = Callable[[str, int], list[str]]


@dataclass(frozen=True, slots=True)
class _ParsedRemoteURL:
    text: str
    parsed: ParseResult
    host: str
    provider_name: str
    field_name: str

    @property
    def default_port(self) -> int:
        if self.parsed.scheme.lower() == "https":
            return 443
        return 80

    @property
    def port(self) -> int:
        return self.parsed.port or self.default_port


def validate_remote_url(
    url: str,
    *,
    provider_name: str,
    url_name: str,
    allow_local_network: bool = False,
    resolve_dns: bool = True,
    dns_resolution_timeout_seconds: float = _DNS_RESOLUTION_TIMEOUT_SECONDS,
    dns_resolver: Callable[..., list[str]] | None = None,
) -> str:
    """Return a stripped HTTP URL after blocking local/private destinations."""

    remote_url = _parse_remote_url(
        _required_remote_url_text(url, provider_name=provider_name, field_name=url_name),
        provider_name=provider_name,
        field_name=url_name,
    )
    _reject_untrusted_remote_destination(
        remote_url,
        allow_local_network=allow_local_network,
        resolve_dns=resolve_dns,
        dns_resolution_timeout_seconds=dns_resolution_timeout_seconds,
        dns_resolver=dns_resolver,
    )
    return remote_url.text


def validate_remote_base_url(
    base_url: str,
    *,
    provider_name: str,
    env_var: str,
    allow_local_network: bool = False,
    resolve_dns: bool = True,
    allowed_hosts: Sequence[str] | None = None,
    dns_resolution_timeout_seconds: float = _DNS_RESOLUTION_TIMEOUT_SECONDS,
    dns_resolver: Callable[..., list[str]] | None = None,
) -> str:
    """Return a normalized HTTP base URL after preflight destination checks."""

    remote_url = _parse_remote_url(base_url, provider_name=provider_name, field_name=env_var)
    _reject_remote_url_query_or_fragment(remote_url)
    _reject_unlisted_host(
        remote_url.host,
        allowed_hosts=allowed_hosts,
        provider_name=provider_name,
        env_var=env_var,
    )
    _reject_untrusted_remote_destination(
        remote_url,
        allow_local_network=allow_local_network,
        resolve_dns=resolve_dns,
        dns_resolution_timeout_seconds=dns_resolution_timeout_seconds,
        dns_resolver=dns_resolver,
    )
    return base_url.rstrip("/")


def _required_remote_url_text(url: object, *, provider_name: str, field_name: str) -> str:
    if not isinstance(url, str) or not url.strip():
        raise ProviderError(f"Provider '{provider_name}' {field_name} must be a non-empty URL.")
    return url.strip()


def _parse_remote_url(value: str, *, provider_name: str, field_name: str) -> _ParsedRemoteURL:
    parsed = urlparse(value)
    if parsed.scheme.lower() not in {"http", "https"}:
        raise ProviderError(
            f"Provider '{provider_name}' {field_name} must use an http or https URL."
        )
    if not parsed.hostname:
        raise ProviderError(f"Provider '{provider_name}' {field_name} must include a hostname.")
    if parsed.username or parsed.password:
        raise ProviderError(
            f"Provider '{provider_name}' {field_name} must not include embedded credentials."
        )
    return _ParsedRemoteURL(
        text=value,
        parsed=parsed,
        host=parsed.hostname.strip().lower(),
        provider_name=provider_name,
        field_name=field_name,
    )


def _reject_remote_url_query_or_fragment(remote_url: _ParsedRemoteURL) -> None:
    if remote_url.parsed.query or remote_url.parsed.fragment:
        raise ProviderError(
            f"Provider '{remote_url.provider_name}' {remote_url.field_name} "
            "must not include query parameters or fragments."
        )


def _reject_untrusted_remote_destination(
    remote_url: _ParsedRemoteURL,
    *,
    allow_local_network: bool,
    resolve_dns: bool,
    dns_resolution_timeout_seconds: float,
    dns_resolver: Callable[..., list[str]] | None = None,
) -> None:
    if allow_local_network:
        return
    _reject_local_hostname(
        remote_url.host,
        provider_name=remote_url.provider_name,
        env_var=remote_url.field_name,
    )
    is_ip_literal = _reject_local_ip_literal(
        remote_url.host,
        provider_name=remote_url.provider_name,
        env_var=remote_url.field_name,
    )
    if not resolve_dns or is_ip_literal:
        return
    _reject_local_resolved_addresses(
        remote_url.host,
        port=remote_url.port,
        provider_name=remote_url.provider_name,
        env_var=remote_url.field_name,
        timeout_seconds=dns_resolution_timeout_seconds,
        dns_resolver=dns_resolver or _getaddrinfo_with_timeout,
    )


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
    dns_resolver: Callable[..., list[str]] | None = None,
) -> None:
    active_resolver = dns_resolver or _getaddrinfo_with_timeout
    try:
        addresses = [
            ipaddress.ip_address(address)
            for address in active_resolver(
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
    cached_addresses = _cached_dns_resolution(cache_key, now=perf_counter())
    if cached_addresses is not None:
        return list(cached_addresses)

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
        _join_dns_resolver(resolver, timeout_seconds=timeout_seconds)
        status, value = _read_dns_resolution_result(
            result_queue,
            started=started,
            timeout_seconds=timeout_seconds,
        )
        addresses = _dns_addresses_from_result(status, value)
        _cache_dns_resolution(cache_key, addresses)
        return list(addresses)
    finally:
        _cleanup_dns_resolver(
            resolver,
            result_queue,
            resolver_started=resolver_started,
        )


def _cached_dns_resolution(
    cache_key: tuple[str, int],
    *,
    now: float,
) -> tuple[str, ...] | None:
    cached = _DNS_RESOLUTION_CACHE.get(cache_key)
    if cached is None:
        return None

    cached_at, cached_addresses = cached
    if now - cached_at <= _DNS_RESOLUTION_CACHE_SECONDS:
        _DNS_RESOLUTION_CACHE.move_to_end(cache_key)
        return cached_addresses

    del _DNS_RESOLUTION_CACHE[cache_key]
    return None


def _join_dns_resolver(resolver: Any, *, timeout_seconds: float) -> None:
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


def _read_dns_resolution_result(
    result_queue: Any,
    *,
    started: float,
    timeout_seconds: float,
) -> tuple[str, object]:
    elapsed_seconds = perf_counter() - started
    remaining_seconds = timeout_seconds - elapsed_seconds
    try:
        if remaining_seconds <= 0:
            return result_queue.get_nowait()
        return result_queue.get(timeout=min(_DNS_RESULT_QUEUE_TIMEOUT_SECONDS, remaining_seconds))
    except queue.Empty as exc:
        if perf_counter() - started >= timeout_seconds:
            raise TimeoutError(f"DNS resolution exceeded {timeout_seconds:.1f}s.") from exc
        raise socket.gaierror(socket.EAI_FAIL, "DNS resolver returned no result") from exc


def _dns_addresses_from_result(status: str, value: object) -> tuple[str, ...]:
    if status == "gaierror":
        error_number, error_text = value
        raise socket.gaierror(error_number, error_text)
    if status != "ok":
        raise socket.gaierror(socket.EAI_FAIL, "DNS resolver returned an invalid result")
    return tuple(value)


def _cleanup_dns_resolver(
    resolver: Any,
    result_queue: Any,
    *,
    resolver_started: bool,
) -> None:
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

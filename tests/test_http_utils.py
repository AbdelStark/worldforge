from __future__ import annotations

import multiprocessing

import pytest

from worldforge.providers import ProviderError, http_utils
from worldforge.providers.http_utils import _getaddrinfo_with_timeout, validate_remote_base_url


class _FakeQueue:
    def __init__(self, *, empty: bool = True) -> None:
        self._empty = empty
        self.closed = False
        self.joined = False

    def empty(self) -> bool:
        return self._empty

    def get(self) -> tuple[str, object]:
        raise AssertionError("empty queue should not be read")

    def close(self) -> None:
        self.closed = True

    def join_thread(self) -> None:
        self.joined = True


class _HangingProcess:
    terminated = False
    joined_after_terminate = False

    def __init__(self, *_args: object, **_kwargs: object) -> None:
        self.exitcode = None
        self._started = False

    def start(self) -> None:
        self._started = True

    def join(self, _timeout: float | None = None) -> None:
        if self.terminated:
            self.joined_after_terminate = True

    def is_alive(self) -> bool:
        return self._started and not self.terminated

    def terminate(self) -> None:
        self.terminated = True


class _HangingContext:
    def __init__(self) -> None:
        self.process: _HangingProcess | None = None
        self.queue: _FakeQueue | None = None

    def Queue(self, *args: object, **kwargs: object) -> _FakeQueue:
        self.queue = _FakeQueue()
        return self.queue

    def Process(self, *args: object, **kwargs: object) -> _HangingProcess:
        self.process = _HangingProcess(*args, **kwargs)
        return self.process


def test_validate_remote_base_url_rejects_credentials_query_and_fragments() -> None:
    for url, match in (
        ("https://user:secret@93.184.216.34", "embedded credentials"),
        ("https://93.184.216.34?token=secret", "query parameters"),
        ("https://93.184.216.34/#token", "fragments"),
    ):
        with pytest.raises(ProviderError, match=match):
            validate_remote_base_url(
                url,
                provider_name="cosmos-policy",
                env_var="COSMOS_POLICY_BASE_URL",
            )


def test_validate_remote_base_url_enforces_allowed_hosts() -> None:
    assert (
        validate_remote_base_url(
            "https://policy.example.com",
            provider_name="cosmos-policy",
            env_var="COSMOS_POLICY_BASE_URL",
            allowed_hosts=("*.example.com",),
            resolve_dns=False,
        )
        == "https://policy.example.com"
    )
    with pytest.raises(ProviderError, match="allowed host"):
        validate_remote_base_url(
            "https://unexpected.example.net",
            provider_name="cosmos-policy",
            env_var="COSMOS_POLICY_BASE_URL",
            allowed_hosts=("*.example.com",),
            resolve_dns=False,
        )


def test_validate_remote_base_url_wraps_dns_worker_failures(monkeypatch) -> None:
    def fail_resolution(*_args: object, **_kwargs: object) -> list[str]:
        raise RuntimeError("resolver worker failed")

    monkeypatch.setattr(http_utils, "_getaddrinfo_with_timeout", fail_resolution)

    with pytest.raises(ProviderError, match="host resolution failed"):
        validate_remote_base_url(
            "https://policy.example.com",
            provider_name="cosmos-policy",
            env_var="COSMOS_POLICY_BASE_URL",
        )


def test_dns_resolution_cache_evicts_oldest_entry(monkeypatch) -> None:
    http_utils._DNS_RESOLUTION_CACHE.clear()
    monkeypatch.setattr(http_utils, "_DNS_RESOLUTION_CACHE_MAX_ENTRIES", 2)
    try:
        http_utils._cache_dns_resolution(("alpha.example", 443), ("93.184.216.34",))
        http_utils._cache_dns_resolution(("beta.example", 443), ("93.184.216.35",))
        http_utils._cache_dns_resolution(("gamma.example", 443), ("93.184.216.36",))

        assert list(http_utils._DNS_RESOLUTION_CACHE) == [
            ("beta.example", 443),
            ("gamma.example", 443),
        ]
    finally:
        http_utils._DNS_RESOLUTION_CACHE.clear()


def test_getaddrinfo_timeout_terminates_resolver_process(monkeypatch) -> None:
    context = _HangingContext()

    def fake_get_context(_method: str) -> _HangingContext:
        return context

    monkeypatch.setattr(multiprocessing, "get_context", fake_get_context)

    with pytest.raises(TimeoutError, match="DNS resolution exceeded"):
        _getaddrinfo_with_timeout("cosmos-policy.example", 443, timeout_seconds=0.01)
    assert context.process is not None
    assert context.process.terminated is True
    assert context.process.joined_after_terminate is True
    assert context.queue is not None
    assert context.queue.closed is True
    assert context.queue.joined is True


def test_getaddrinfo_uses_bounded_result_queue_timeout(monkeypatch) -> None:
    class CompletedProcess:
        exitcode = 0

        def start(self) -> None:
            pass

        def join(self, _timeout: float | None = None) -> None:
            pass

        def is_alive(self) -> bool:
            return False

        def terminate(self) -> None:
            raise AssertionError("completed process should not be terminated")

    class ResultQueue:
        timeout_seen: float | None = None

        def get(self, *, timeout: float) -> tuple[str, list[str]]:
            self.timeout_seen = timeout
            return ("ok", ["93.184.216.34"])

        def close(self) -> None:
            pass

        def join_thread(self) -> None:
            pass

    class CompletedContext:
        def __init__(self) -> None:
            self.queue = ResultQueue()

        def Queue(self, *args: object, **kwargs: object) -> ResultQueue:
            del args, kwargs
            return self.queue

        def Process(self, *args: object, **kwargs: object) -> CompletedProcess:
            del args, kwargs
            return CompletedProcess()

    context = CompletedContext()

    def fake_get_context(_method: str) -> CompletedContext:
        return context

    monkeypatch.setattr(multiprocessing, "get_context", fake_get_context)

    assert _getaddrinfo_with_timeout(
        "cosmos-policy.example",
        443,
        timeout_seconds=2.0,
    ) == ["93.184.216.34"]
    assert context.queue.timeout_seen is not None
    assert context.queue.timeout_seen >= 1.0

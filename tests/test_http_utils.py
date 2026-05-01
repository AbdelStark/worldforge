from __future__ import annotations

import multiprocessing

import pytest

from worldforge.providers import ProviderError
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


def test_validate_remote_base_url_rejects_credentials_and_query() -> None:
    for url, match in (
        ("https://user:secret@93.184.216.34", "embedded credentials"),
        ("https://93.184.216.34?token=secret", "query parameters"),
        ("https://93.184.216.34/#token", "query parameters"),
    ):
        with pytest.raises(ProviderError, match=match):
            validate_remote_base_url(
                url,
                provider_name="cosmos-policy",
                env_var="COSMOS_POLICY_BASE_URL",
            )


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

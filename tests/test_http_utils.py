from __future__ import annotations

import socket
import threading

import pytest

from worldforge.providers import ProviderError
from worldforge.providers.http_utils import validate_remote_base_url


def test_validate_remote_base_url_times_out_dns_resolution(monkeypatch) -> None:
    resolver_can_exit = threading.Event()

    def slow_getaddrinfo(*_args: object, **_kwargs: object) -> list[tuple[object, ...]]:
        resolver_can_exit.wait(5)
        return []

    monkeypatch.setattr(socket, "getaddrinfo", slow_getaddrinfo)

    try:
        with pytest.raises(ProviderError, match="host resolution timed out"):
            validate_remote_base_url(
                "https://cosmos-policy.example",
                provider_name="cosmos-policy",
                env_var="COSMOS_POLICY_BASE_URL",
                dns_resolution_timeout_seconds=0.01,
            )
    finally:
        resolver_can_exit.set()

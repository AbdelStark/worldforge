from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

from worldforge.models import EmbeddingResult, ProviderEvent
from worldforge.providers.base import ProviderError
from worldforge.providers.voyage import VoyageProvider

ROOT = Path(__file__).resolve().parents[1]


def _fixture(name: str) -> dict[str, object]:
    return json.loads((ROOT / "tests" / "fixtures" / "providers" / name).read_text())


def test_voyage_provider_profile() -> None:
    provider = VoyageProvider()
    profile = provider.profile()

    assert profile.name == "voyage"
    assert profile.implementation_status == "scaffold"
    assert profile.capabilities.embed is True
    assert profile.capabilities.predict is False
    assert profile.capabilities.generate is False
    assert profile.capabilities.reason is False
    assert profile.capabilities.plan is False
    assert profile.capabilities.transfer is False
    assert profile.supported_tasks == ["embed"]
    assert profile.required_env_vars == ["VOYAGE_API_KEY"]


def test_voyage_health_reports_missing_configuration(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("VOYAGE_API_KEY", raising=False)
    health = VoyageProvider().health()
    assert health.healthy is False
    assert "VOYAGE_API_KEY" in health.details


def test_voyage_health_errors_on_auth_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("VOYAGE_API_KEY", "voyage-invalid-key")

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/embeddings"
        return httpx.Response(401, json=_fixture("voyage_error.json"))

    provider = VoyageProvider(transport=httpx.MockTransport(handler))
    health = provider.health()
    assert health.healthy is False


def test_voyage_embed_success(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("VOYAGE_API_KEY", "voyage-test-key")

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/embeddings"
        body = json.loads(request.read())
        assert body["input"] == "test text"
        assert body["model"] == "voyage-3-lite"
        return httpx.Response(200, json=_fixture("voyage_success.json"))

    provider = VoyageProvider(transport=httpx.MockTransport(handler))
    result = provider.embed(text="test text")

    assert isinstance(result, EmbeddingResult)
    assert result.provider == "voyage"
    assert result.model == "voyage-3-lite"
    assert len(result.vector) == 10
    assert all(isinstance(v, float) for v in result.vector)


def test_voyage_embed_rejects_empty_text() -> None:
    provider = VoyageProvider()
    with pytest.raises(ProviderError, match="non-empty string"):
        provider.embed(text="")
    with pytest.raises(ProviderError, match="non-empty string"):
        provider.embed(text="   ")


def test_voyage_embed_rejects_missing_embedding(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("VOYAGE_API_KEY", "voyage-test-key")

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_fixture("voyage_missing_embedding.json"))

    provider = VoyageProvider(transport=httpx.MockTransport(handler))
    with pytest.raises(ProviderError, match="must be a non-empty list"):
        provider.embed(text="test")


def test_voyage_embed_emits_event(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("VOYAGE_API_KEY", "voyage-test-key")
    events: list[ProviderEvent] = []

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_fixture("voyage_success.json"))

    provider = VoyageProvider(
        transport=httpx.MockTransport(handler),
        event_handler=events.append,
    )
    provider.embed(text="test text")

    embed_events = [e for e in events if e.operation == "embed"]
    assert len(embed_events) == 1
    event = embed_events[0]
    assert event.phase == "success"
    assert event.provider == "voyage"
    assert event.metadata.get("dimensions") == 10


def test_voyage_embed_missing_credentials() -> None:
    provider = VoyageProvider()
    with pytest.raises(ProviderError, match="missing VOYAGE_API_KEY"):
        provider.embed(text="test")


def test_voyage_config_summary(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("VOYAGE_API_KEY", "voyage-test-key")
    summary = VoyageProvider().config_summary()
    assert summary.provider == "voyage"
    assert summary.configured is True
    assert any(field.name == "VOYAGE_API_KEY" for field in summary.fields)


def test_voyage_config_summary_unconfigured(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("VOYAGE_API_KEY", raising=False)
    summary = VoyageProvider().config_summary()
    assert summary.configured is False

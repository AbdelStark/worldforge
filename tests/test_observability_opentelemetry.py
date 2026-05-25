from __future__ import annotations

import sys
from contextlib import AbstractContextManager
from dataclasses import dataclass, field
from typing import Any

import pytest

import worldforge
from worldforge import ProviderEvent, WorldForgeError
from worldforge.observability import (
    OpenTelemetryProviderEventSink,
    compose_event_handlers,
    provider_event_span_attributes,
)


@dataclass
class _FakeSpan:
    name: str
    attributes: dict[str, Any] = field(default_factory=dict)

    def set_attribute(self, key: str, value: object) -> None:
        self.attributes[key] = value


@dataclass
class _SpanContext(AbstractContextManager[_FakeSpan]):
    span: _FakeSpan

    def __enter__(self) -> _FakeSpan:
        return self.span

    def __exit__(self, *exc_info: object) -> None:
        return None


@dataclass
class _FakeTracer:
    spans: list[_FakeSpan] = field(default_factory=list)

    def start_as_current_span(
        self,
        name: str,
        *,
        attributes: dict[str, object] | None = None,
    ) -> _SpanContext:
        span = _FakeSpan(name=name, attributes=dict(attributes or {}))
        self.spans.append(span)
        return _SpanContext(span)


def test_importing_worldforge_does_not_import_opentelemetry() -> None:
    assert worldforge.__version__
    assert not any(module == "opentelemetry" for module in sys.modules)


def test_provider_event_span_attributes_are_bounded_and_sanitized() -> None:
    event = ProviderEvent(
        provider="runway",
        operation="task create",
        phase="SUCCESS",
        method="post",
        target="https://user:secret@api.runwayml.com/v1/tasks?token=secret#fragment",
        status_code=201,
        duration_ms=42.5,
        attempt=2,
        max_attempts=3,
        message="Bearer secret-token failed for token=secret",
        metadata={
            "capability": "generate",
            "api_key": "secret",
            "artifact_url": "https://files.example.test/video.mp4?signature=secret",
        },
        run_id="run-123",
        request_id="req-456",
        trace_id="trace-789",
        span_id="span-abc",
        artifact_id="artifact-def",
        input_digest="sha256:123",
    )

    attributes = provider_event_span_attributes(event)

    assert attributes["worldforge.provider"] == "runway"
    assert attributes["worldforge.operation"] == "task create"
    assert attributes["worldforge.phase"] == "success"
    assert attributes["worldforge.status_class"] == "2xx"
    assert attributes["worldforge.capability"] == "generate"
    assert attributes["http.request.method"] == "POST"
    assert attributes["http.response.status_code"] == 201
    assert attributes["url.full"] == "https://api.runwayml.com/v1/tasks"
    assert attributes["worldforge.trace_id"] == "trace-789"
    rendered = str(attributes)
    assert "secret-token" not in rendered
    assert "token=secret" not in rendered
    assert "signature=secret" not in rendered
    assert '"api_key":"[redacted]"' in attributes["worldforge.metadata_json"]


def test_open_telemetry_sink_uses_injected_tracer_without_optional_dependency() -> None:
    tracer = _FakeTracer()
    sink = OpenTelemetryProviderEventSink(
        tracer=tracer,
        extra_attributes={"service": "batch-host", "api_token": "secret"},
    )

    sink(
        ProviderEvent(
            provider="mock",
            operation="predict",
            phase="failure",
            status_code=503,
            metadata={"capability": "predict"},
        )
    )

    assert len(tracer.spans) == 1
    span = tracer.spans[0]
    assert span.name == "worldforge.provider.mock.predict.failure"
    assert span.attributes["worldforge.provider"] == "mock"
    assert span.attributes["worldforge.status_class"] == "5xx"
    assert span.attributes["worldforge.host.service"] == "batch-host"
    assert span.attributes["worldforge.host.api_token"] == "[redacted]"


def test_open_telemetry_sink_composes_with_provider_handlers() -> None:
    tracer = _FakeTracer()
    events: list[ProviderEvent] = []
    handler = compose_event_handlers(events.append, OpenTelemetryProviderEventSink(tracer=tracer))

    assert handler is not None
    handler(ProviderEvent(provider="mock", operation="generate", phase="retry", attempt=1))

    assert [event.phase for event in events] == ["retry"]
    assert tracer.spans[0].attributes["worldforge.phase"] == "retry"


def test_open_telemetry_sink_requires_tracer_or_optional_dependency(monkeypatch) -> None:
    monkeypatch.setitem(sys.modules, "opentelemetry", None)

    with pytest.raises(WorldForgeError, match="opentelemetry-api"):
        OpenTelemetryProviderEventSink()

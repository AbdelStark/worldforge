"""Optional OpenTelemetry bridge for provider events.

The module intentionally has no import-time dependency on OpenTelemetry. Hosts that already own
OpenTelemetry wiring can inject a tracer directly; otherwise the sink imports ``opentelemetry``
lazily when it is constructed.
"""

from __future__ import annotations

from collections.abc import Mapping
from contextlib import AbstractContextManager
from dataclasses import dataclass, field
from typing import Protocol

from worldforge.models import (
    JSONDict,
    ProviderEvent,
    WorldForgeError,
    _redact_observable_value,
    dump_json,
    require_json_dict,
)

AttributeValue = (
    str
    | bool
    | int
    | float
    | tuple[str, ...]
    | tuple[bool, ...]
    | tuple[int, ...]
    | tuple[float, ...]
)
SpanAttributes = dict[str, AttributeValue]


class _Span(Protocol):
    def set_attribute(self, key: str, value: AttributeValue) -> None: ...


class _Tracer(Protocol):
    def start_as_current_span(
        self,
        name: str,
        *,
        attributes: Mapping[str, AttributeValue] | None = None,
    ) -> AbstractContextManager[_Span]: ...


def _status_class(status_code: int | None) -> str | None:
    if status_code is None:
        return None
    return f"{status_code // 100}xx"


def _optional_attribute(attributes: SpanAttributes, key: str, value: object | None) -> None:
    if value is None:
        return
    if isinstance(value, str | bool | int | float):
        attributes[key] = value


def provider_event_span_attributes(event: ProviderEvent) -> SpanAttributes:
    """Return bounded, redacted OpenTelemetry attributes for a provider event."""

    attributes: SpanAttributes = {
        "worldforge.provider": event.provider,
        "worldforge.operation": event.operation,
        "worldforge.phase": event.phase,
        "worldforge.attempt": event.attempt,
        "worldforge.max_attempts": event.max_attempts,
    }
    _optional_attribute(attributes, "worldforge.duration_ms", event.duration_ms)
    _optional_attribute(attributes, "worldforge.run_id", event.run_id)
    _optional_attribute(attributes, "worldforge.request_id", event.request_id)
    _optional_attribute(attributes, "worldforge.trace_id", event.trace_id)
    _optional_attribute(attributes, "worldforge.span_id", event.span_id)
    _optional_attribute(attributes, "worldforge.artifact_id", event.artifact_id)
    _optional_attribute(attributes, "worldforge.input_digest", event.input_digest)
    _optional_attribute(attributes, "http.request.method", event.method)
    _optional_attribute(attributes, "http.response.status_code", event.status_code)
    _optional_attribute(attributes, "url.full", event.target)

    status_class = _status_class(event.status_code)
    _optional_attribute(attributes, "worldforge.status_class", status_class)
    capability = event.metadata.get("capability")
    _optional_attribute(attributes, "worldforge.capability", capability)
    if event.message:
        attributes["worldforge.message"] = event.message
    if event.metadata:
        attributes["worldforge.metadata_json"] = dump_json(event.metadata)
    return attributes


def _load_default_tracer() -> _Tracer:
    try:
        from opentelemetry import trace
    except ModuleNotFoundError as exc:
        raise WorldForgeError(
            "OpenTelemetry export requires the host to install opentelemetry-api or pass an "
            "injected tracer."
        ) from exc
    return trace.get_tracer("worldforge")


@dataclass(slots=True)
class OpenTelemetryProviderEventSink:
    """Create one OpenTelemetry span for each provider event."""

    tracer: _Tracer | None = None
    span_name_prefix: str = "worldforge.provider"
    extra_attributes: JSONDict = field(default_factory=dict)
    _tracer: _Tracer = field(init=False, repr=False)

    def __post_init__(self) -> None:
        if not isinstance(self.span_name_prefix, str) or not self.span_name_prefix.strip():
            raise WorldForgeError(
                "OpenTelemetryProviderEventSink span_name_prefix must be a non-empty string."
            )
        self.span_name_prefix = self.span_name_prefix.strip()
        self._tracer = self.tracer if self.tracer is not None else _load_default_tracer()
        self.extra_attributes = require_json_dict(
            _redact_observable_value(dict(self.extra_attributes)),
            name="OpenTelemetryProviderEventSink extra_attributes",
        )

    def __call__(self, event: ProviderEvent) -> None:
        attributes = provider_event_span_attributes(event)
        for key, value in self.extra_attributes.items():
            if isinstance(value, str | bool | int | float):
                attributes[f"worldforge.host.{key}"] = value
            else:
                attributes[f"worldforge.host.{key}"] = dump_json(value)
        span_name = f"{self.span_name_prefix}.{event.provider}.{event.operation}.{event.phase}"
        with self._tracer.start_as_current_span(span_name, attributes=attributes) as span:
            # Some lightweight test tracers store attributes from construction only; real OTel spans
            # accept set_attribute calls and this keeps behavior consistent for injected tracers.
            for key, value in attributes.items():
                span.set_attribute(key, value)


__all__ = [
    "OpenTelemetryProviderEventSink",
    "provider_event_span_attributes",
]

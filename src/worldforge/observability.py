"""Ready-to-use provider telemetry sinks built on ProviderEvent."""

from __future__ import annotations

import logging
from collections.abc import Callable
from copy import deepcopy
from dataclasses import dataclass, field
from threading import Lock

from worldforge.models import JSONDict, ProviderEvent, WorldForgeError, dump_json

ProviderEventHandler = Callable[[ProviderEvent], None]


def _copy_event(event: ProviderEvent) -> ProviderEvent:
    return ProviderEvent(
        provider=event.provider,
        operation=event.operation,
        phase=event.phase,
        attempt=event.attempt,
        max_attempts=event.max_attempts,
        method=event.method,
        target=event.target,
        status_code=event.status_code,
        duration_ms=event.duration_ms,
        message=event.message,
        metadata=deepcopy(event.metadata),
    )


@dataclass(slots=True)
class _EventHandlerFanout:
    handlers: tuple[ProviderEventHandler, ...]

    def __post_init__(self) -> None:
        if not self.handlers:
            raise WorldForgeError("Event handler fanout requires at least one handler.")

    def __call__(self, event: ProviderEvent) -> None:
        for handler in self.handlers:
            handler(_copy_event(event))


def compose_event_handlers(*handlers: ProviderEventHandler | None) -> ProviderEventHandler | None:
    """Return a single provider event handler composed from zero or more handlers."""

    resolved_handlers: list[ProviderEventHandler] = []
    for handler in handlers:
        if handler is None:
            continue
        if isinstance(handler, _EventHandlerFanout):
            resolved_handlers.extend(handler.handlers)
            continue
        resolved_handlers.append(handler)
    if not resolved_handlers:
        return None
    if len(resolved_handlers) == 1:
        return resolved_handlers[0]
    return _EventHandlerFanout(tuple(resolved_handlers))


@dataclass(slots=True)
class JsonLoggerSink:
    """Log provider events as a single structured JSON record."""

    logger: logging.Logger = field(
        default_factory=lambda: logging.getLogger("worldforge.providers")
    )
    level: int = logging.INFO
    extra_fields: JSONDict = field(default_factory=dict)

    def __call__(self, event: ProviderEvent) -> None:
        payload = {"event_type": "provider_event", **deepcopy(self.extra_fields), **event.to_dict()}
        self.logger.log(self.level, dump_json(payload))


@dataclass(slots=True)
class InMemoryRecorderSink:
    """Record provider events in memory for tests and local debugging."""

    _events: list[ProviderEvent] = field(default_factory=list, init=False, repr=False)
    _lock: Lock = field(default_factory=Lock, init=False, repr=False)

    def __call__(self, event: ProviderEvent) -> None:
        with self._lock:
            self._events.append(_copy_event(event))

    @property
    def events(self) -> list[ProviderEvent]:
        return self.snapshot()

    def clear(self) -> None:
        with self._lock:
            self._events.clear()

    def snapshot(self) -> list[ProviderEvent]:
        with self._lock:
            return [_copy_event(event) for event in self._events]


@dataclass(slots=True, frozen=True)
class LatencySummary:
    """Aggregate latency measurements for a provider operation."""

    sample_count: int = 0
    total_ms: float = 0.0
    average_ms: float | None = None
    min_ms: float | None = None
    max_ms: float | None = None

    def to_dict(self) -> JSONDict:
        return {
            "sample_count": self.sample_count,
            "total_ms": self.total_ms,
            "average_ms": self.average_ms,
            "min_ms": self.min_ms,
            "max_ms": self.max_ms,
        }


@dataclass(slots=True, frozen=True)
class ProviderOperationMetrics:
    """Aggregated provider telemetry for a single provider/operation pair."""

    provider: str
    operation: str
    request_count: int = 0
    error_count: int = 0
    retry_count: int = 0
    latency: LatencySummary = field(default_factory=LatencySummary)

    def to_dict(self) -> JSONDict:
        return {
            "provider": self.provider,
            "operation": self.operation,
            "request_count": self.request_count,
            "error_count": self.error_count,
            "retry_count": self.retry_count,
            "latency": self.latency.to_dict(),
        }


@dataclass(slots=True)
class _ProviderOperationAccumulator:
    request_count: int = 0
    error_count: int = 0
    retry_count: int = 0
    latency_sample_count: int = 0
    total_latency_ms: float = 0.0
    min_latency_ms: float | None = None
    max_latency_ms: float | None = None

    def record(self, event: ProviderEvent) -> None:
        self.request_count += 1
        if event.phase == "failure":
            self.error_count += 1
        if event.phase == "retry":
            self.retry_count += 1
        if event.duration_ms is None:
            return
        self.latency_sample_count += 1
        self.total_latency_ms += event.duration_ms
        if self.min_latency_ms is None or event.duration_ms < self.min_latency_ms:
            self.min_latency_ms = event.duration_ms
        if self.max_latency_ms is None or event.duration_ms > self.max_latency_ms:
            self.max_latency_ms = event.duration_ms

    def snapshot(self, *, provider: str, operation: str) -> ProviderOperationMetrics:
        average_ms: float | None = None
        if self.latency_sample_count:
            average_ms = self.total_latency_ms / self.latency_sample_count
        return ProviderOperationMetrics(
            provider=provider,
            operation=operation,
            request_count=self.request_count,
            error_count=self.error_count,
            retry_count=self.retry_count,
            latency=LatencySummary(
                sample_count=self.latency_sample_count,
                total_ms=self.total_latency_ms,
                average_ms=average_ms,
                min_ms=self.min_latency_ms,
                max_ms=self.max_latency_ms,
            ),
        )


@dataclass(slots=True)
class ProviderMetricsSink:
    """Aggregate provider request attempts, errors, retries, and latency."""

    _metrics: dict[tuple[str, str], _ProviderOperationAccumulator] = field(
        default_factory=dict,
        init=False,
        repr=False,
    )
    _lock: Lock = field(default_factory=Lock, init=False, repr=False)

    def __call__(self, event: ProviderEvent) -> None:
        key = (event.provider, event.operation)
        with self._lock:
            accumulator = self._metrics.setdefault(key, _ProviderOperationAccumulator())
            accumulator.record(event)

    def clear(self) -> None:
        with self._lock:
            self._metrics.clear()

    def get(self, provider: str, operation: str) -> ProviderOperationMetrics:
        with self._lock:
            accumulator = self._metrics.get((provider, operation), _ProviderOperationAccumulator())
            return accumulator.snapshot(provider=provider, operation=operation)

    def snapshot(self) -> list[ProviderOperationMetrics]:
        with self._lock:
            items = [
                accumulator.snapshot(provider=provider, operation=operation)
                for (provider, operation), accumulator in self._metrics.items()
            ]
        return sorted(items, key=lambda item: (item.provider, item.operation))

    def to_dict(self) -> JSONDict:
        payload: JSONDict = {}
        for metric in self.snapshot():
            provider_metrics = payload.setdefault(metric.provider, {})
            provider_metrics[metric.operation] = metric.to_dict()
        return payload


__all__ = [
    "InMemoryRecorderSink",
    "JsonLoggerSink",
    "LatencySummary",
    "ProviderEventHandler",
    "ProviderMetricsSink",
    "ProviderOperationMetrics",
    "compose_event_handlers",
]

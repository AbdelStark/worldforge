"""ProviderEvent sinks for logging, recording, and aggregate metrics."""

from __future__ import annotations

import logging
from collections.abc import Callable, Mapping
from copy import deepcopy
from dataclasses import dataclass, field
from pathlib import Path
from threading import Lock
from typing import Protocol

from worldforge.models import (
    CAPABILITY_NAMES,
    JSONDict,
    ProviderEvent,
    WorldForgeError,
    _redact_observable_value,
    dump_json,
    require_json_dict,
)
from worldforge.observability_opentelemetry import (
    OpenTelemetryProviderEventSink,
    provider_event_span_attributes,
)

ProviderEventHandler = Callable[[ProviderEvent], None]
MetricLabels = dict[str, str]


class ProviderMetricsExporter(Protocol):
    """Host-owned metrics backend used by :class:`ProviderMetricsExporterSink`."""

    def increment_counter(
        self,
        name: str,
        *,
        value: float = 1.0,
        labels: Mapping[str, str],
    ) -> None: ...

    def observe_histogram(
        self,
        name: str,
        value: float,
        *,
        labels: Mapping[str, str],
    ) -> None: ...


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
        run_id=event.run_id,
        request_id=event.request_id,
        trace_id=event.trace_id,
        span_id=event.span_id,
        artifact_id=event.artifact_id,
        input_digest=event.input_digest,
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


def _redacted_extra_fields(extra_fields: JSONDict, *, name: str) -> JSONDict:
    return require_json_dict(
        _redact_observable_value(deepcopy(extra_fields)),
        name=name,
    )


@dataclass(slots=True)
class JsonLoggerSink:
    """Log provider events as a single structured JSON record."""

    logger: logging.Logger = field(
        default_factory=lambda: logging.getLogger("worldforge.providers")
    )
    level: int = logging.INFO
    extra_fields: JSONDict = field(default_factory=dict)

    def __post_init__(self) -> None:
        # Deep-copy once; isolating callers from later extra-field mutation only
        # matters at construction time, so don't pay the cost per event.
        self.extra_fields = _redacted_extra_fields(
            self.extra_fields,
            name="JsonLoggerSink extra_fields",
        )

    def __call__(self, event: ProviderEvent) -> None:
        payload = {"event_type": "provider_event", **self.extra_fields, **event.to_dict()}
        self.logger.log(self.level, dump_json(payload))


@dataclass(slots=True)
class RunJsonLogSink:
    """Append provider events to a run-scoped JSONL file."""

    path: Path | str
    run_id: str
    extra_fields: JSONDict = field(default_factory=dict)
    _path: Path = field(init=False, repr=False)
    _lock: Lock = field(default_factory=Lock, init=False, repr=False)

    def __post_init__(self) -> None:
        if not isinstance(self.run_id, str) or not self.run_id.strip():
            raise WorldForgeError("RunJsonLogSink run_id must be a non-empty string.")
        self.run_id = self.run_id.strip()
        self._path = Path(self.path)
        self.extra_fields = _redacted_extra_fields(
            self.extra_fields,
            name="RunJsonLogSink extra_fields",
        )
        self._path.parent.mkdir(parents=True, exist_ok=True)

    @property
    def log_path(self) -> Path:
        """Return the concrete JSONL file path used by this sink."""

        return self._path

    def __call__(self, event: ProviderEvent) -> None:
        payload = {
            "event_type": "provider_event",
            **self.extra_fields,
            **event.to_dict(),
            "run_id": self.run_id,
        }
        line = f"{dump_json(payload)}\n"
        with self._lock, self._path.open("a", encoding="utf-8") as handle:
            handle.write(line)


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


def _status_class(status_code: int | None) -> str:
    if status_code is None:
        return "none"
    return f"{status_code // 100}xx"


def _capability_label(event: ProviderEvent) -> str:
    capability = event.metadata.get("capability")
    if isinstance(capability, str) and capability in CAPABILITY_NAMES:
        return capability
    return "unknown"


def provider_event_metric_labels(event: ProviderEvent) -> MetricLabels:
    """Return bounded metric labels for a provider event."""

    return {
        "provider": event.provider,
        "operation": event.operation,
        "phase": event.phase,
        "status_class": _status_class(event.status_code),
        "capability": _capability_label(event),
    }


@dataclass(slots=True, frozen=True)
class MetricSample:
    """One exported metric observation captured by the in-memory exporter."""

    name: str
    labels: MetricLabels
    value: float

    def to_dict(self) -> JSONDict:
        return {"name": self.name, "labels": dict(self.labels), "value": self.value}


@dataclass(slots=True)
class InMemoryMetricsExporter:
    """Dependency-free metrics exporter useful for tests and local host wiring."""

    _counters: dict[tuple[str, tuple[tuple[str, str], ...]], float] = field(
        default_factory=dict,
        init=False,
        repr=False,
    )
    _histograms: list[MetricSample] = field(default_factory=list, init=False, repr=False)
    _lock: Lock = field(default_factory=Lock, init=False, repr=False)

    def increment_counter(
        self,
        name: str,
        *,
        value: float = 1.0,
        labels: Mapping[str, str],
    ) -> None:
        label_tuple = tuple(sorted(dict(labels).items()))
        with self._lock:
            counter_key = (name, label_tuple)
            self._counters[counter_key] = self._counters.get(counter_key, 0.0) + value

    def observe_histogram(
        self,
        name: str,
        value: float,
        *,
        labels: Mapping[str, str],
    ) -> None:
        with self._lock:
            self._histograms.append(MetricSample(name=name, labels=dict(labels), value=value))

    def clear(self) -> None:
        with self._lock:
            self._counters.clear()
            self._histograms.clear()

    def counter_value(self, name: str, *, labels: Mapping[str, str]) -> float:
        label_tuple = tuple(sorted(dict(labels).items()))
        with self._lock:
            return self._counters.get((name, label_tuple), 0.0)

    def counter_samples(self) -> list[MetricSample]:
        with self._lock:
            return [
                MetricSample(
                    name=name,
                    labels=dict(label_tuple),
                    value=value,
                )
                for (name, label_tuple), value in sorted(self._counters.items())
            ]

    def histogram_samples(self) -> list[MetricSample]:
        with self._lock:
            return [
                MetricSample(name=sample.name, labels=dict(sample.labels), value=sample.value)
                for sample in self._histograms
            ]


@dataclass(slots=True)
class ProviderMetricsExporterSink:
    """Export provider event counters and latency histograms to a host metrics backend."""

    exporter: ProviderMetricsExporter
    metric_prefix: str = "worldforge_provider"

    def __post_init__(self) -> None:
        if not isinstance(self.metric_prefix, str) or not self.metric_prefix.strip():
            raise WorldForgeError(
                "ProviderMetricsExporterSink metric_prefix must be a non-empty string."
            )
        self.metric_prefix = self.metric_prefix.strip()

    def __call__(self, event: ProviderEvent) -> None:
        labels = provider_event_metric_labels(event)
        self.exporter.increment_counter(
            f"{self.metric_prefix}_events_total",
            labels=labels,
        )
        if event.phase == "retry":
            self.exporter.increment_counter(
                f"{self.metric_prefix}_retries_total",
                labels=labels,
            )
        else:
            self.exporter.increment_counter(
                f"{self.metric_prefix}_operations_total",
                labels=labels,
            )
        if event.phase in {"failure", "budget_exceeded"}:
            self.exporter.increment_counter(
                f"{self.metric_prefix}_errors_total",
                labels=labels,
            )
        if event.duration_ms is not None:
            self.exporter.observe_histogram(
                f"{self.metric_prefix}_latency_ms",
                event.duration_ms,
                labels=labels,
            )


__all__ = [
    "InMemoryMetricsExporter",
    "InMemoryRecorderSink",
    "JsonLoggerSink",
    "LatencySummary",
    "MetricLabels",
    "MetricSample",
    "OpenTelemetryProviderEventSink",
    "ProviderEventHandler",
    "ProviderMetricsExporter",
    "ProviderMetricsExporterSink",
    "ProviderMetricsSink",
    "ProviderOperationMetrics",
    "RunJsonLogSink",
    "compose_event_handlers",
    "provider_event_metric_labels",
    "provider_event_span_attributes",
]

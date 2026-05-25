from __future__ import annotations

import pytest

from worldforge import ProviderEvent, WorldForgeError
from worldforge.observability import (
    InMemoryMetricsExporter,
    ProviderMetricsExporterSink,
    compose_event_handlers,
    provider_event_metric_labels,
)


def _labels(
    phase: str,
    *,
    status_class: str = "none",
    capability: str = "unknown",
) -> dict[str, str]:
    return {
        "capability": capability,
        "operation": "task poll",
        "phase": phase,
        "provider": "runway",
        "status_class": status_class,
    }


def test_provider_metrics_exporter_sink_exports_bounded_counters_and_latency() -> None:
    exporter = InMemoryMetricsExporter()
    sink = ProviderMetricsExporterSink(exporter)

    sink(
        ProviderEvent(
            provider="runway",
            operation="task poll",
            phase="retry",
            status_code=429,
            duration_ms=25.0,
            metadata={
                "capability": "generate",
                "prompt": "do not export as a label",
                "world_id": "world-123",
                "metadata_key": "unsafe-cardinality",
            },
        )
    )
    sink(
        ProviderEvent(
            provider="runway",
            operation="task poll",
            phase="success",
            status_code=200,
            duration_ms=40.0,
            metadata={"capability": "generate"},
        )
    )

    retry_labels = _labels("retry", status_class="4xx", capability="generate")
    success_labels = _labels("success", status_class="2xx", capability="generate")
    assert exporter.counter_value("worldforge_provider_events_total", labels=retry_labels) == 1.0
    assert exporter.counter_value("worldforge_provider_retries_total", labels=retry_labels) == 1.0
    assert (
        exporter.counter_value("worldforge_provider_operations_total", labels=retry_labels) == 0.0
    )
    assert exporter.counter_value("worldforge_provider_events_total", labels=success_labels) == 1.0
    assert (
        exporter.counter_value("worldforge_provider_operations_total", labels=success_labels) == 1.0
    )
    assert exporter.counter_value("worldforge_provider_retries_total", labels=success_labels) == 0.0

    histogram_samples = exporter.histogram_samples()
    assert [sample.value for sample in histogram_samples] == [25.0, 40.0]
    assert {sample.name for sample in histogram_samples} == {"worldforge_provider_latency_ms"}
    for sample in exporter.counter_samples() + histogram_samples:
        assert set(sample.labels) == {
            "provider",
            "operation",
            "phase",
            "status_class",
            "capability",
        }
        assert "do not export" not in str(sample.to_dict())
        assert "world-123" not in str(sample.to_dict())


def test_provider_metrics_exporter_sink_counts_errors_without_retries() -> None:
    exporter = InMemoryMetricsExporter()
    sink = ProviderMetricsExporterSink(exporter, metric_prefix="wf")

    sink(
        ProviderEvent(
            provider="runway",
            operation="task poll",
            phase="failure",
            status_code=503,
        )
    )
    sink(
        ProviderEvent(
            provider="runway",
            operation="task poll",
            phase="budget_exceeded",
        )
    )

    failure_labels = _labels("failure", status_class="5xx")
    budget_labels = _labels("budget_exceeded")
    assert exporter.counter_value("wf_errors_total", labels=failure_labels) == 1.0
    assert exporter.counter_value("wf_operations_total", labels=failure_labels) == 1.0
    assert exporter.counter_value("wf_errors_total", labels=budget_labels) == 1.0
    assert exporter.counter_value("wf_operations_total", labels=budget_labels) == 1.0
    assert exporter.counter_value("wf_retries_total", labels=failure_labels) == 0.0


def test_provider_event_metric_labels_ignore_unknown_capability_values() -> None:
    labels = provider_event_metric_labels(
        ProviderEvent(
            provider="mock",
            operation="predict",
            phase="success",
            metadata={"capability": "per-world-user-label"},
        )
    )

    assert labels == {
        "capability": "unknown",
        "operation": "predict",
        "phase": "success",
        "provider": "mock",
        "status_class": "none",
    }


def test_provider_metrics_exporter_sink_composes_with_other_handlers() -> None:
    exporter = InMemoryMetricsExporter()
    events: list[ProviderEvent] = []
    handler = compose_event_handlers(events.append, ProviderMetricsExporterSink(exporter))
    assert handler is not None

    handler(ProviderEvent(provider="mock", operation="predict", phase="success"))

    assert len(events) == 1
    assert exporter.counter_samples()[0].name == "worldforge_provider_events_total"


def test_provider_metrics_exporter_sink_validates_metric_prefix() -> None:
    with pytest.raises(WorldForgeError, match="metric_prefix"):
        ProviderMetricsExporterSink(InMemoryMetricsExporter(), metric_prefix=" ")

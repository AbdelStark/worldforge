from __future__ import annotations

import json
import logging

import pytest

from worldforge import Action, ProviderEvent, WorldForge
from worldforge.observability import (
    InMemoryRecorderSink,
    JsonLoggerSink,
    ProviderMetricsSink,
    compose_event_handlers,
)
from worldforge.providers import MockProvider


def test_json_logger_sink_emits_structured_json(caplog) -> None:
    logger = logging.getLogger("worldforge.tests.observability")
    sink = JsonLoggerSink(logger=logger, extra_fields={"service": "api"})

    with caplog.at_level(logging.INFO, logger=logger.name):
        sink(
            ProviderEvent(
                provider="mock",
                operation="predict",
                phase="success",
                duration_ms=12.5,
                metadata={"steps": 2},
            )
        )

    records = [record for record in caplog.records if record.name == logger.name]
    assert len(records) == 1
    payload = json.loads(records[0].message)
    assert payload == {
        "attempt": 1,
        "duration_ms": 12.5,
        "event_type": "provider_event",
        "max_attempts": 1,
        "message": "",
        "metadata": {"steps": 2},
        "method": None,
        "operation": "predict",
        "phase": "success",
        "provider": "mock",
        "service": "api",
        "status_code": None,
        "target": None,
    }


def test_in_memory_recorder_sink_records_isolated_event_snapshots() -> None:
    sink = InMemoryRecorderSink()
    event = ProviderEvent(
        provider="mock",
        operation="predict",
        phase="success",
        duration_ms=8.0,
        metadata={"nested": {"steps": [1]}},
    )

    sink(event)
    event.metadata["nested"]["steps"].append(2)

    assert sink.events[0].metadata == {"nested": {"steps": [1]}}
    sink.clear()
    assert sink.events == []


def test_compose_event_handlers_fans_out_and_isolates_sink_mutation() -> None:
    first = InMemoryRecorderSink()
    second = InMemoryRecorderSink()

    def mutating_sink(event: ProviderEvent) -> None:
        event.metadata["mutated"] = True

    handler = compose_event_handlers(first, compose_event_handlers(mutating_sink), None, second)
    assert handler is not None

    handler(
        ProviderEvent(
            provider="mock",
            operation="predict",
            phase="success",
            duration_ms=5.0,
            metadata={"steps": 2},
        )
    )

    assert first.snapshot()[0].metadata == {"steps": 2}
    assert second.snapshot()[0].metadata == {"steps": 2}


def test_provider_metrics_sink_aggregates_counts_and_latency_by_operation() -> None:
    sink = ProviderMetricsSink()

    sink(
        ProviderEvent(
            provider="runway",
            operation="task poll",
            phase="retry",
            duration_ms=10.0,
        )
    )
    sink(
        ProviderEvent(
            provider="runway",
            operation="task poll",
            phase="success",
            duration_ms=20.0,
        )
    )
    sink(
        ProviderEvent(
            provider="runway",
            operation="task poll",
            phase="failure",
            duration_ms=30.0,
        )
    )
    sink(
        ProviderEvent(
            provider="mock",
            operation="predict",
            phase="success",
        )
    )

    task_poll = sink.get("runway", "task poll")
    assert task_poll.request_count == 3
    assert task_poll.error_count == 1
    assert task_poll.retry_count == 1
    assert task_poll.latency.sample_count == 3
    assert task_poll.latency.total_ms == pytest.approx(60.0)
    assert task_poll.latency.average_ms == pytest.approx(20.0)
    assert task_poll.latency.min_ms == pytest.approx(10.0)
    assert task_poll.latency.max_ms == pytest.approx(30.0)

    predict = sink.get("mock", "predict")
    assert predict.request_count == 1
    assert predict.error_count == 0
    assert predict.retry_count == 0
    assert predict.latency.sample_count == 0
    assert predict.latency.average_ms is None
    assert predict.latency.min_ms is None
    assert predict.latency.max_ms is None

    assert [(metric.provider, metric.operation) for metric in sink.snapshot()] == [
        ("mock", "predict"),
        ("runway", "task poll"),
    ]
    assert sink.to_dict()["runway"]["task poll"]["latency"]["sample_count"] == 3


def test_worldforge_composed_event_handlers_support_builtin_and_manual_providers(tmp_path) -> None:
    recorder = InMemoryRecorderSink()
    metrics = ProviderMetricsSink()
    forge = WorldForge(
        state_dir=tmp_path,
        auto_register_remote=False,
        event_handler=compose_event_handlers(recorder, metrics),
    )
    world = forge.create_world_from_prompt("empty room", provider="mock")

    world.predict(Action.move_to(0.2, 0.5, 0.0), steps=2)
    manual_provider = MockProvider(name="manual")
    forge.register_provider(manual_provider)
    forge.reason("manual", "where is the cube?", world=world)

    assert manual_provider.event_handler is not None
    assert [(event.provider, event.operation, event.phase) for event in recorder.snapshot()] == [
        ("mock", "predict", "success"),
        ("manual", "reason", "success"),
    ]
    assert metrics.get("mock", "predict").request_count == 1
    assert metrics.get("manual", "reason").request_count == 1

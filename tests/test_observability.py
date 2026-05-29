from __future__ import annotations

import json
import logging

import pytest

from worldforge import Action, ProviderEvent, WorldForge, WorldForgeError
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


def test_provider_event_redacts_observable_secret_fields() -> None:
    event = ProviderEvent(
        provider="runway",
        operation="artifact download",
        phase="failure",
        method="get",
        target=(
            "https://user:pass@downloads.example.com/generated.mp4"
            "?X-Amz-Signature=query-secret&token=query-token#fragment"
        ),
        message=(
            "download failed for https://downloads.example.com/generated.mp4?token=query-token "
            "with Authorization=raw-secret and Bearer bearer-secret"
        ),
        metadata={
            "api_token": "metadata-secret",
            "nested": {
                "signed_url": "https://downloads.example.com/generated.mp4?signature=secret",
                "safe_url": "https://downloads.example.com/generated.mp4?signature=secret",
            },
            "json_text": '{"api_key":"json-secret","token":"json-token"}',
            "colon_text": "Authorization: colon-secret",
            "safe": "token=inline-secret",
        },
    )

    payload = event.to_dict()

    assert payload["method"] == "GET"
    assert payload["target"] == "https://downloads.example.com/generated.mp4"
    assert "query-secret" not in json.dumps(payload)
    assert "query-token" not in json.dumps(payload)
    assert "raw-secret" not in json.dumps(payload)
    assert "bearer-secret" not in json.dumps(payload)
    assert "json-secret" not in json.dumps(payload)
    assert "json-token" not in json.dumps(payload)
    assert "colon-secret" not in json.dumps(payload)
    assert payload["metadata"]["api_token"] == "[redacted]"
    assert payload["metadata"]["nested"]["signed_url"] == "[redacted]"
    assert (
        payload["metadata"]["nested"]["safe_url"] == "https://downloads.example.com/generated.mp4"
    )
    assert payload["metadata"]["safe"] == "token=[redacted]"


def test_provider_event_validates_and_normalizes_observable_fields() -> None:
    blank_target = ProviderEvent(
        provider="runway",
        operation="artifact download",
        phase=" Success ",
        target="   ",
    )
    assert blank_target.phase == "success"
    assert blank_target.target is None

    invalid_url = ProviderEvent(
        provider="runway",
        operation="artifact download",
        phase="failure",
        target="http://[invalid?token=secret",
    )
    assert invalid_url.target == "http://[invalid"

    with pytest.raises(WorldForgeError, match="target"):
        ProviderEvent(
            provider="runway",
            operation="artifact download",
            phase="failure",
            target=object(),  # type: ignore[arg-type]
        )

    with pytest.raises(WorldForgeError, match="method"):
        ProviderEvent(
            provider="runway",
            operation="artifact download",
            phase="failure",
            method=object(),  # type: ignore[arg-type]
        )

    with pytest.raises(WorldForgeError, match="message"):
        ProviderEvent(
            provider="runway",
            operation="artifact download",
            phase="failure",
            message=object(),  # type: ignore[arg-type]
        )

    with pytest.raises(WorldForgeError, match="metadata"):
        ProviderEvent(
            provider="runway",
            operation="artifact download",
            phase="failure",
            metadata={"shape": (1, 2, 3)},
        )


def test_provider_event_correlation_fields_are_optional_sanitized_and_json_native() -> None:
    event = ProviderEvent(
        provider=" runway ",
        operation=" task create ",
        phase=" Success ",
        run_id=" run-123 ",
        request_id=" req-456 ",
        trace_id=" trace-abc ",
        span_id=" span-def ",
        artifact_id=" artifact-789 ",
        input_digest="sha256:abc123",
        metadata={"status": "submitted"},
    )

    assert event.to_dict() == {
        "artifact_id": "artifact-789",
        "attempt": 1,
        "duration_ms": None,
        "input_digest": "sha256:abc123",
        "max_attempts": 1,
        "message": "",
        "metadata": {"status": "submitted"},
        "method": None,
        "operation": "task create",
        "phase": "success",
        "provider": "runway",
        "request_id": "req-456",
        "run_id": "run-123",
        "span_id": "span-def",
        "status_code": None,
        "target": None,
        "trace_id": "trace-abc",
    }

    redacted = ProviderEvent(
        provider="runway",
        operation="artifact download",
        phase="success",
        request_id="token=secret-request",
        artifact_id="https://example.test/video.mp4?X-Amz-Signature=artifact-secret",
        input_digest=" ",
    ).to_dict()

    assert redacted["request_id"] == "token=[redacted]"
    assert redacted["artifact_id"] == "https://example.test/video.mp4"
    assert "input_digest" not in redacted

    with pytest.raises(WorldForgeError, match="request_id"):
        ProviderEvent(
            provider="runway",
            operation="artifact download",
            phase="success",
            request_id=object(),  # type: ignore[arg-type]
        )


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

from __future__ import annotations

import json

import pytest

from worldforge import Action, ProviderEvent, WorldForge, WorldForgeError
from worldforge.observability import JsonLoggerSink, RunJsonLogSink, compose_event_handlers


def _read_jsonl(path) -> list[dict[str, object]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def test_run_json_log_sink_writes_run_scoped_jsonl(tmp_path) -> None:
    log_path = tmp_path / "runs" / "run-123" / "provider-events.jsonl"
    sink = RunJsonLogSink(
        log_path,
        run_id="run-123",
        extra_fields={"host": "batch-eval", "request_id": "req-456", "run_id": "wrong"},
    )

    sink(
        ProviderEvent(
            provider="mock",
            operation="predict",
            phase="success",
            duration_ms=12.5,
            request_id="event-req",
            trace_id="trace-abc",
            metadata={"steps": 2},
        )
    )

    assert sink.log_path == log_path
    records = _read_jsonl(log_path)
    assert records == [
        {
            "attempt": 1,
            "duration_ms": 12.5,
            "event_type": "provider_event",
            "host": "batch-eval",
            "max_attempts": 1,
            "message": "",
            "metadata": {"steps": 2},
            "method": None,
            "operation": "predict",
            "phase": "success",
            "provider": "mock",
            "request_id": "event-req",
            "run_id": "run-123",
            "status_code": None,
            "target": None,
            "trace_id": "trace-abc",
        }
    ]


def test_run_json_log_sink_redacts_exported_secrets(tmp_path) -> None:
    log_path = tmp_path / "provider-events.jsonl"
    sink = RunJsonLogSink(
        log_path,
        run_id="run-123",
        extra_fields={
            "authorization": "Bearer extra-secret",
            "artifact_url": "https://example.test/video.mp4?X-Amz-Signature=query-secret",
        },
    )

    sink(
        ProviderEvent(
            provider="runway",
            operation="artifact download",
            phase="failure",
            method="get",
            target="https://user:pass@example.test/video.mp4?token=target-secret",
            message="failed with api_key=message-secret and Bearer bearer-secret",
            metadata={
                "api_token": "metadata-secret",
                "signed_url": "https://example.test/video.mp4?signature=metadata-secret",
            },
        )
    )

    exported = log_path.read_text(encoding="utf-8")
    assert "extra-secret" not in exported
    assert "query-secret" not in exported
    assert "target-secret" not in exported
    assert "message-secret" not in exported
    assert "bearer-secret" not in exported
    assert "metadata-secret" not in exported

    record = _read_jsonl(log_path)[0]
    assert record["authorization"] == "[redacted]"
    assert record["artifact_url"] == "https://example.test/video.mp4"
    assert record["target"] == "https://example.test/video.mp4"
    assert record["metadata"] == {"api_token": "[redacted]", "signed_url": "[redacted]"}


def test_run_json_log_sink_validates_inputs(tmp_path) -> None:
    with pytest.raises(WorldForgeError, match="run_id"):
        RunJsonLogSink(tmp_path / "events.jsonl", run_id=" ")

    with pytest.raises(WorldForgeError, match="extra_fields"):
        RunJsonLogSink(
            tmp_path / "events.jsonl",
            run_id="run-123",
            extra_fields={"not_json": object()},  # type: ignore[dict-item]
        )


def test_run_json_log_sink_integrates_with_worldforge_event_handler(tmp_path) -> None:
    run_sink = RunJsonLogSink(tmp_path / "events.jsonl", run_id="run-123")
    forge = WorldForge(
        state_dir=tmp_path / "worlds",
        auto_register_remote=False,
        event_handler=compose_event_handlers(run_sink),
    )

    world = forge.create_world_from_prompt("empty room", provider="mock")
    world.predict(Action.move_to(0.2, 0.5, 0.0))

    records = _read_jsonl(run_sink.log_path)
    assert [(record["run_id"], record["provider"], record["operation"]) for record in records] == [
        ("run-123", "mock", "predict")
    ]


def test_json_logger_sink_redacts_extra_fields(caplog) -> None:
    import logging

    logger = logging.getLogger("worldforge.tests.run_logs")
    sink = JsonLoggerSink(
        logger=logger,
        extra_fields={"authorization": "Bearer extra-secret", "safe": "visible"},
    )

    with caplog.at_level(logging.INFO, logger=logger.name):
        sink(ProviderEvent(provider="mock", operation="predict", phase="success"))

    record = json.loads(caplog.records[0].message)
    assert record["authorization"] == "[redacted]"
    assert record["safe"] == "visible"
    assert "extra-secret" not in caplog.records[0].message

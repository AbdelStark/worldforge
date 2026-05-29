from __future__ import annotations

import json
import logging
from contextlib import AbstractContextManager
from dataclasses import dataclass, field
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from worldforge import ProviderEvent
from worldforge.evidence_bundle import generate_issue_bundle
from worldforge.harness.workspace import create_run_workspace, write_run_manifest
from worldforge.observability import (
    JsonLoggerSink,
    OpenTelemetryProviderEventSink,
    RunJsonLogSink,
    provider_event_metric_labels,
    provider_event_span_attributes,
)
from worldforge.rerun import RerunEventSink, RerunRecordingConfig, RerunSession
from worldforge.smoke.run_manifest import build_run_manifest, validate_run_manifest

ROOT = Path(__file__).resolve().parents[1]
CORPUS = ROOT / "tests/fixtures/redaction/provider_event_corpus.json"


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


class _FakeRerun:
    TextLogLevel = SimpleNamespace(ERROR="ERROR", WARN="WARN", INFO="INFO")

    def __init__(self) -> None:
        self.logs: list[tuple[str, dict[str, Any]]] = []

    def init(self, *args: Any, **kwargs: Any) -> None:
        return None

    def set_time(self, timeline: str, *, sequence: int) -> None:
        return None

    def log(self, entity_path: str, entity: dict[str, Any]) -> None:
        self.logs.append((entity_path, entity))

    def TextLog(self, text: str, *, level: object | None = None) -> dict[str, Any]:
        return {"kind": "TextLog", "text": text, "level": level}

    def TextDocument(self, text: str, *, media_type: str | None = None) -> dict[str, Any]:
        return {"kind": "TextDocument", "text": text, "media_type": media_type}

    def Scalar(self, scalar: float) -> dict[str, Any]:
        return {"kind": "Scalar", "scalar": scalar}

    def AnyValues(self, **kwargs: Any) -> dict[str, Any]:
        return {"kind": "AnyValues", **kwargs}


def _corpus_cases() -> list[dict[str, Any]]:
    payload = json.loads(CORPUS.read_text(encoding="utf-8"))
    assert payload["schema_version"] == 1
    return list(payload["cases"])


def _assert_forbidden_absent(rendered: str, forbidden: list[str]) -> None:
    for value in forbidden:
        assert value not in rendered


def test_provider_event_redaction_corpus_covers_event_sinks_and_manifests(
    caplog,
    tmp_path: Path,
) -> None:
    logger = logging.getLogger("worldforge.tests.redaction-corpus")

    for index, case in enumerate(_corpus_cases(), start=1):
        event = ProviderEvent(**case["event"])
        forbidden = list(case["forbidden"])

        event_payload = json.dumps(event.to_dict(), sort_keys=True)
        _assert_forbidden_absent(event_payload, forbidden)
        assert "[redacted]" in event_payload

        caplog.clear()
        with caplog.at_level(logging.INFO, logger=logger.name):
            JsonLoggerSink(logger=logger, extra_fields={"api_key": "wf-extra-secret"})(event)
        json_logger_payload = "\n".join(record.message for record in caplog.records)
        _assert_forbidden_absent(json_logger_payload, [*forbidden, "wf-extra-secret"])

        run_log = tmp_path / f"{case['id']}.jsonl"
        RunJsonLogSink(run_log, run_id="run-token=wf-run-secret")(event)
        run_log_payload = run_log.read_text(encoding="utf-8")
        _assert_forbidden_absent(run_log_payload, [*forbidden, "wf-run-secret"])

        metric_payload = json.dumps(provider_event_metric_labels(event), sort_keys=True)
        _assert_forbidden_absent(metric_payload, forbidden)

        otel_payload = json.dumps(provider_event_span_attributes(event), sort_keys=True)
        _assert_forbidden_absent(otel_payload, forbidden)

        tracer = _FakeTracer()
        OpenTelemetryProviderEventSink(tracer=tracer)(event)
        _assert_forbidden_absent(json.dumps(tracer.spans[0].attributes), forbidden)

        fake_rerun = _FakeRerun()
        rerun_sink = RerunEventSink(
            session=RerunSession(
                config=RerunRecordingConfig(recording_name="redaction corpus"),
                sdk=fake_rerun,
            )
        )
        rerun_sink(event)
        _assert_forbidden_absent(json.dumps(fake_rerun.logs, sort_keys=True), forbidden)

        manifest = build_run_manifest(
            run_id=f"{case['id']}-run",
            provider_profile=event.provider,
            capability=str(event.metadata["capability"]),
            status="failed",
            env_vars=("RUNWAYML_API_SECRET",),
            command_argv=("worldforge-smoke", "--provider", event.provider),
            result=event.to_dict(),
            artifact_paths={"artifact": str(case["event"]["target"])},
        ).to_dict()
        validated_manifest = validate_run_manifest(manifest)
        _assert_forbidden_absent(json.dumps(validated_manifest, sort_keys=True), forbidden)

        issue_run_id = f"20260101T00000{index}Z-0000000{index}"
        workspace = create_run_workspace(
            tmp_path,
            kind="provider-diagnostic",
            command=f"worldforge provider workbench {event.provider}",
            provider=event.provider,
            operation=event.operation,
            run_id=issue_run_id,
            input_summary={"case": case["id"]},
        )
        workspace.write_text("logs/provider-events.jsonl", event_payload)
        write_run_manifest(
            workspace,
            kind="provider-diagnostic",
            command=f"worldforge provider workbench {event.provider}",
            provider=event.provider,
            operation=event.operation,
            status="failed",
            input_summary={"case": case["id"]},
            result_summary={"event": event.to_dict()},
            event_count=1,
        )
        issue_bundle = generate_issue_bundle(
            workspace_dir=tmp_path,
            run_id=issue_run_id,
            output_dir=tmp_path / f"{case['id']}-bundle",
            overwrite=True,
        )
        _assert_forbidden_absent(json.dumps(issue_bundle.manifest, sort_keys=True), forbidden)
        _assert_forbidden_absent(
            issue_bundle.issue_template_path.read_text(encoding="utf-8"),
            forbidden,
        )

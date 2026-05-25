from __future__ import annotations

from worldforge import Action, ProviderEvent, VideoClip, WorldForge
from worldforge.providers import GenieProvider, MockProvider
from worldforge.workflow_trace import (
    WorkflowArtifactRef,
    WorkflowTrace,
    WorkflowTraceStep,
    workflow_trace_from_provider_events,
)


def test_worldforge_event_handler_propagates_to_builtin_and_manual_providers(tmp_path) -> None:
    events: list[ProviderEvent] = []
    forge = WorldForge(
        state_dir=tmp_path,
        auto_register_remote=False,
        event_handler=events.append,
    )
    world = forge.create_world_from_prompt("empty room", provider="mock")

    world.predict(Action.move_to(0.2, 0.5, 0.0), steps=2)
    forge.generate("orbiting cube", "mock", duration_seconds=1.0)

    manual_provider = MockProvider(name="manual")
    forge.register_provider(manual_provider)
    forge.reason("manual", "where is the cube?", world=world)

    assert manual_provider.event_handler is not None
    assert [(event.provider, event.operation, event.phase) for event in events] == [
        ("mock", "predict", "success"),
        ("mock", "generate", "success"),
        ("manual", "reason", "success"),
    ]
    assert events[0].metadata["steps"] == 2


def test_stub_remote_provider_forwards_mock_events(monkeypatch) -> None:
    monkeypatch.setenv("GENIE_API_KEY", "genie-test-key")
    monkeypatch.setenv("WORLDFORGE_ENABLE_SCAFFOLD_SURROGATES", "1")
    events: list[ProviderEvent] = []
    provider = GenieProvider(event_handler=events.append)

    payload = provider.predict(
        {
            "id": "world-test",
            "name": "test",
            "provider": "genie",
            "step": 0,
            "scene": {"objects": {}},
            "metadata": {},
        },
        Action.spawn_object("cube"),
        1,
    )

    assert payload.metadata["mode"] == "stub-remote-adapter"
    assert [(event.provider, event.operation, event.phase) for event in events] == [
        ("genie", "predict", "success")
    ]


def test_scaffold_surrogate_opt_in_exercises_non_predict_operations(monkeypatch) -> None:
    monkeypatch.setenv("GENIE_API_KEY", "genie-test-key")
    monkeypatch.setenv("WORLDFORGE_ENABLE_SCAFFOLD_SURROGATES", "true")
    provider = GenieProvider()

    generated = provider.generate("cube replay", 1.0)
    transferred = provider.transfer(
        VideoClip(
            frames=[b"seed"],
            fps=8.0,
            resolution=(160, 90),
            duration_seconds=1.0,
        ),
        width=320,
        height=180,
        fps=12.0,
    )
    reasoning = provider.reason("how many objects?", world_state={"scene": {"objects": {}}})
    embedding = provider.embed(text="cube")

    assert generated.metadata["mode"] == "stub-remote-adapter"
    assert transferred.metadata["credential_env"] == "GENIE_API_KEY"
    assert "GENIE_API_KEY" in reasoning.evidence[-1]
    assert embedding.provider == "genie"


def test_workflow_trace_from_provider_events_sanitizes_failures_and_artifacts() -> None:
    events = [
        ProviderEvent(
            provider="mock",
            operation="predict",
            phase="success",
            duration_ms=2.5,
            artifact_id="prediction-json",
        ),
        ProviderEvent(
            provider="runway",
            operation="generate",
            phase="failure",
            message="provider failed with token=secret at /tmp/private/run.json",
            target="https://example.test/result.mp4?signature=secret",
        ),
    ]

    trace = workflow_trace_from_provider_events(
        events,
        workflow_id="demo-trace",
        name="Demo trace",
    )
    payload = trace.to_dict()

    assert payload["schema_version"] == 1
    assert payload["status"] == "failed"
    assert payload["status_counts"]["success"] == 1
    assert payload["status_counts"]["failed"] == 1
    assert payload["steps"][0]["output_artifacts"][0]["label"] == "prediction-json"
    error_summary = payload["steps"][1]["error_summary"]
    assert "secret" not in error_summary
    assert "/tmp/private" not in error_summary
    assert "[redacted]" in error_summary
    assert "<host-local-path>" in error_summary
    assert "runway" in trace.to_markdown()


def test_workflow_trace_validates_skipped_failed_and_nested_steps() -> None:
    trace = WorkflowTrace(
        workflow_id="nested-trace",
        name="Nested trace",
        steps=[
            WorkflowTraceStep(
                step_id="root",
                operation="batch evaluation",
                status="failed",
                output_artifacts=(WorkflowArtifactRef(label="report", path="reports/report.json"),),
            ),
            WorkflowTraceStep(
                step_id="provider",
                parent_id="root",
                operation="provider run",
                provider="mock",
                capability="predict",
                status="success",
            ),
            WorkflowTraceStep(
                step_id="optional-rerun",
                parent_id="root",
                operation="rerun layer",
                status="skipped",
                error_summary="rerun extra not installed",
            ),
            WorkflowTraceStep(
                step_id="failed-scenario",
                parent_id="provider",
                operation="scenario matrix case",
                provider="mock",
                status="failed",
                error_summary="ProviderError: score mismatch",
            ),
        ],
    )

    payload = trace.to_dict()

    assert payload["safe_to_attach"] is True
    assert payload["status"] == "failed"
    assert payload["status_counts"]["skipped"] == 1
    assert payload["steps"][3]["parent_id"] == "provider"


def test_workflow_trace_marks_local_only_artifacts_not_safe_to_attach() -> None:
    trace = WorkflowTrace(
        workflow_id="local-artifact-trace",
        name="Local artifact trace",
        steps=[
            WorkflowTraceStep(
                step_id="checkpoint",
                operation="prepared-host checkpoint",
                status="success",
                output_artifacts=(
                    WorkflowArtifactRef(
                        label="checkpoint",
                        path="/Users/example/.cache/model.ckpt",
                        safe_to_attach=False,
                    ),
                ),
            )
        ],
    )

    payload = trace.to_dict()

    assert payload["safe_to_attach"] is False
    assert payload["steps"][0]["output_artifacts"][0]["safe_to_attach"] is False

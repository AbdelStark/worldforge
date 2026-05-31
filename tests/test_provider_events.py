from __future__ import annotations

import pytest

from worldforge import Action, ProviderEvent, WorldForge
from worldforge.models import WorldForgeError
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

    manual_provider = MockProvider(name="manual")
    forge.register_provider(manual_provider)
    forge.embed("manual", text="cube state")

    assert manual_provider.event_handler is not None
    assert [(event.provider, event.operation, event.phase) for event in events] == [
        ("mock", "predict", "success"),
        ("manual", "embed", "success"),
    ]
    assert events[0].metadata["steps"] == 2


def test_direct_provider_target_inherits_worldforge_event_handler(tmp_path) -> None:
    events: list[ProviderEvent] = []
    forge = WorldForge(
        state_dir=tmp_path,
        auto_register_remote=False,
        event_handler=events.append,
    )
    provider = MockProvider(name="direct")

    forge.embed(provider, text="cube state")

    assert provider.event_handler is not None
    assert [(event.provider, event.operation, event.phase) for event in events] == [
        ("direct", "embed", "success")
    ]


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


def test_scaffold_surrogate_opt_in_exercises_embed_operation(monkeypatch) -> None:
    monkeypatch.setenv("GENIE_API_KEY", "genie-test-key")
    monkeypatch.setenv("WORLDFORGE_ENABLE_SCAFFOLD_SURROGATES", "true")
    provider = GenieProvider()

    embedding = provider.embed(text="cube")

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
            provider="leworldmodel",
            operation="score",
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
    assert "leworldmodel" in trace.to_markdown()


def test_workflow_trace_from_provider_events_handles_running_and_empty_streams() -> None:
    running_trace = workflow_trace_from_provider_events(
        [
            {
                "provider": "mock",
                "operation": "predict",
                "phase": "retry",
                "message": "transient retry",
            }
        ],
        workflow_id="running-trace",
        name="Running trace",
    )
    empty_trace = workflow_trace_from_provider_events(
        [],
        workflow_id="empty-trace",
        name="Empty trace",
    )

    running_payload = running_trace.to_dict()
    empty_payload = empty_trace.to_dict()

    assert running_payload["status"] == "running"
    assert running_payload["steps"][0]["status"] == "running"
    assert "error_summary" not in running_payload["steps"][0]
    assert empty_payload["status"] == "skipped"
    assert empty_payload["steps"][0]["step_id"] == "no-provider-events"
    assert empty_payload["steps"][0]["error_summary"] == "No provider events were emitted."


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


def test_workflow_trace_rejects_status_that_contradicts_steps() -> None:
    with pytest.raises(WorldForgeError, match="status must match"):
        WorkflowTrace(
            workflow_id="contradictory-trace",
            name="Contradictory trace",
            status="success",
            steps=[
                WorkflowTraceStep(
                    step_id="provider",
                    operation="provider run",
                    status="failed",
                    error_summary="Provider failed.",
                )
            ],
        )


def test_workflow_trace_step_rejects_invalid_boundary_values() -> None:
    with pytest.raises(WorldForgeError, match="status must be one of"):
        WorkflowTraceStep(
            step_id="invalid-status",
            operation="provider run",
            status="unknown",
        )

    with pytest.raises(WorldForgeError, match="parent_id must not equal step_id"):
        WorkflowTraceStep(
            step_id="self-parent",
            parent_id="self-parent",
            operation="provider run",
            status="success",
        )

    with pytest.raises(WorldForgeError, match="duration_ms must be non-negative"):
        WorkflowTraceStep(
            step_id="negative-duration",
            operation="provider run",
            status="success",
            duration_ms=-0.1,
        )


def test_workflow_trace_rejects_invalid_parent_graphs() -> None:
    duplicate = [
        WorkflowTraceStep(step_id="root", operation="root", status="success"),
        WorkflowTraceStep(step_id="root", operation="duplicate", status="success"),
    ]
    unknown_parent = [
        WorkflowTraceStep(step_id="child", parent_id="missing", operation="child", status="success")
    ]
    cycle = [
        WorkflowTraceStep(step_id="root", parent_id="child", operation="root", status="success"),
        WorkflowTraceStep(step_id="child", parent_id="root", operation="child", status="success"),
    ]

    with pytest.raises(WorldForgeError, match="duplicated"):
        WorkflowTrace(workflow_id="duplicate-trace", name="Duplicate trace", steps=duplicate)

    with pytest.raises(WorldForgeError, match="unknown parent_id"):
        WorkflowTrace(
            workflow_id="unknown-parent-trace",
            name="Unknown parent trace",
            steps=unknown_parent,
        )

    with pytest.raises(WorldForgeError, match="must not contain cycles"):
        WorkflowTrace(workflow_id="cycle-trace", name="Cycle trace", steps=cycle)


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

"""Persist completed harness flow runs into checkout-safe run workspaces."""

from __future__ import annotations

from dataclasses import dataclass

from worldforge.harness.models import HarnessRun
from worldforge.harness.workspace import RunWorkspace, write_run_manifest
from worldforge.models import JSONDict, WorldForgeError, dump_json

FLOW_ARTIFACT_RESERVED_NAMES = frozenset({"summary", "steps", "metrics", "transcript", "inspector"})
FLOW_ARTIFACT_DESCRIPTOR_KEYS = frozenset({"path", "payload"})


@dataclass(frozen=True, slots=True)
class FlowArtifactDescriptor:
    relative_path: str
    payload: object


def write_flow_workspace(workspace: RunWorkspace, run: HarnessRun) -> None:
    summary_path = workspace.write_json("results/summary.json", run.summary)
    steps_path = workspace.write_json("results/steps.json", [step.to_dict() for step in run.steps])
    metrics_path = workspace.write_json(
        "results/metrics.json",
        [metric.to_dict() for metric in run.metrics],
    )
    transcript_path = workspace.write_text("logs/transcript.txt", "\n".join(run.transcript))
    inspector_path = workspace.write_json(
        "results/inspector.json",
        inspector_payload(run),
    )
    provider_events = run.provider_events
    event_count = len(provider_events)
    if provider_events:
        workspace.write_text(
            "logs/provider-events.jsonl",
            "\n".join(dump_json(event) for event in provider_events),
        )
    artifact_paths = {
        "summary": str(summary_path.relative_to(workspace.path)),
        "steps": str(steps_path.relative_to(workspace.path)),
        "metrics": str(metrics_path.relative_to(workspace.path)),
        "transcript": str(transcript_path.relative_to(workspace.path)),
        "inspector": str(inspector_path.relative_to(workspace.path)),
    }
    artifact_paths.update(write_flow_artifacts(workspace, run.summary))
    write_run_manifest(
        workspace,
        kind="flow",
        command=run.flow.command,
        provider=run.flow.provider,
        operation=run.flow.id,
        status="failed" if run.validation_errors else "completed",
        input_summary={"flow_id": run.flow.id, "state_dir": str(run.state_dir)},
        result_summary={
            "step_count": len(run.steps),
            "metric_count": len(run.metrics),
            "summary_keys": sorted(run.summary),
            "validation_error_count": len(run.validation_errors),
        },
        artifact_paths=artifact_paths,
        event_count=event_count,
    )


def inspector_payload(run: HarnessRun) -> JSONDict:
    return {
        "flow": run.flow.to_dict(),
        "status": "failed" if run.validation_errors else "completed",
        "metrics": [metric.to_dict() for metric in run.metrics],
        "steps": [step.to_dict() for step in run.steps],
        "provider_events": [dict(event) for event in run.provider_events],
        "validation_errors": list(run.validation_errors),
        "workspace_path": str(run.workspace_path) if run.workspace_path is not None else None,
    }


def write_flow_artifacts(workspace: RunWorkspace, summary: JSONDict) -> JSONDict:
    descriptors = summary.get("harness_artifacts")
    if not isinstance(descriptors, dict):
        return {}
    paths: JSONDict = {}
    for name, descriptor in descriptors.items():
        artifact_name = validate_flow_artifact_name(name)
        parsed_descriptor = flow_artifact_descriptor(artifact_name, descriptor)
        validate_flow_artifact_path(workspace, artifact_name, parsed_descriptor.relative_path)
        validate_flow_artifact_payload(artifact_name, parsed_descriptor.payload)
        path = workspace.write_json(parsed_descriptor.relative_path, parsed_descriptor.payload)
        paths[artifact_name] = str(path.relative_to(workspace.path))
    return paths


def validate_flow_artifact_name(name: object) -> str:
    if not isinstance(name, str) or not name.strip():
        raise ValueError("harness artifact names must be non-empty strings")
    if name in FLOW_ARTIFACT_RESERVED_NAMES:
        raise ValueError(f"harness artifact '{name}' uses a reserved manifest key")
    return name


def flow_artifact_descriptor(name: str, descriptor: object) -> FlowArtifactDescriptor:
    if not isinstance(descriptor, dict):
        raise ValueError(f"harness artifact '{name}' descriptor must be a JSON object")
    extra_keys = sorted(set(descriptor) - FLOW_ARTIFACT_DESCRIPTOR_KEYS)
    if extra_keys:
        raise ValueError(f"harness artifact '{name}' descriptor has unsupported keys: {extra_keys}")
    relative_path = descriptor.get("path")
    if not isinstance(relative_path, str) or not relative_path.startswith("artifacts/"):
        raise ValueError(f"harness artifact '{name}' path must be under artifacts/")
    return FlowArtifactDescriptor(relative_path=relative_path, payload=descriptor.get("payload"))


def validate_flow_artifact_path(
    workspace: RunWorkspace,
    name: str,
    relative_path: str,
) -> None:
    artifacts_root = workspace.artifacts_dir.resolve()
    target = (workspace.path / relative_path).resolve()
    if artifacts_root != target and artifacts_root not in target.parents:
        raise ValueError(f"harness artifact '{name}' path must be under artifacts/")


def validate_flow_artifact_payload(name: str, payload: object) -> None:
    try:
        dump_json(payload)
    except WorldForgeError as exc:
        raise ValueError(f"harness artifact '{name}' payload must be JSON-native") from exc

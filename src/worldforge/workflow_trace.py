"""Schema-versioned trace artifacts for composed WorldForge workflows."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from worldforge.models import (
    JSONDict,
    ProviderEvent,
    WorldForgeError,
    _redact_observable_text,
    _sanitize_observable_target,
    dump_json,
    require_bool,
    require_finite_number,
    require_json_dict,
)

WORKFLOW_TRACE_SCHEMA_VERSION = 1
WORKFLOW_TRACE_STEP_STATUSES: tuple[str, ...] = (
    "pending",
    "running",
    "success",
    "skipped",
    "failed",
)

_SAFE_ID_PATTERN = re.compile(r"^[A-Za-z0-9_.:-]+$")
_SECRET_LIKE_PATTERN = re.compile(
    r"(?:api[_-]?key|authorization|bearer|secret|signature|signed|token|x-amz)",
    re.IGNORECASE,
)
_HOST_LOCAL_PATH_PATTERN = re.compile(
    r"(?P<path>(?:/Users|/private|/var/folders|/tmp|~)/[^\s,;:)'\"]+)"
)


@dataclass(frozen=True, slots=True)
class WorkflowArtifactRef:
    """Safe reference to an input or output artifact used by a trace step."""

    label: str
    path: str | None = None
    digest: str | None = None
    media_type: str | None = None
    safe_to_attach: bool = True

    def __post_init__(self) -> None:
        object.__setattr__(self, "label", _require_trace_text(self.label, name="Artifact label"))
        if self.path is not None:
            object.__setattr__(
                self,
                "path",
                _safe_artifact_path(
                    self.path,
                    safe_to_attach=self.safe_to_attach,
                    name=f"Artifact '{self.label}' path",
                ),
            )
        if self.digest is not None:
            object.__setattr__(
                self, "digest", _require_trace_text(self.digest, name="Artifact digest")
            )
        if self.media_type is not None:
            object.__setattr__(
                self,
                "media_type",
                _require_trace_text(self.media_type, name="Artifact media_type"),
            )
        object.__setattr__(
            self,
            "safe_to_attach",
            require_bool(self.safe_to_attach, name="Artifact safe_to_attach"),
        )
        if self.safe_to_attach and _SECRET_LIKE_PATTERN.search(self.label):
            raise WorldForgeError("Artifact label must not contain secret-like material.")

    @classmethod
    def from_value(cls, value: WorkflowArtifactRef | Mapping[str, Any]) -> WorkflowArtifactRef:
        if isinstance(value, WorkflowArtifactRef):
            return value
        if not isinstance(value, Mapping):
            raise WorldForgeError("Workflow artifact reference must be a JSON object.")
        return cls(
            label=value.get("label", ""),
            path=value.get("path"),
            digest=value.get("digest"),
            media_type=value.get("media_type"),
            safe_to_attach=value.get("safe_to_attach", True),
        )

    def to_dict(self) -> JSONDict:
        payload: JSONDict = {
            "label": self.label,
            "safe_to_attach": self.safe_to_attach,
        }
        if self.path is not None:
            payload["path"] = self.path
        if self.digest is not None:
            payload["digest"] = self.digest
        if self.media_type is not None:
            payload["media_type"] = self.media_type
        return payload


@dataclass(frozen=True, slots=True)
class WorkflowTraceStep:
    """One step in a composed workflow trace."""

    step_id: str
    operation: str
    status: str
    provider: str | None = None
    capability: str | None = None
    parent_id: str | None = None
    input_artifacts: Sequence[WorkflowArtifactRef | Mapping[str, Any]] = ()
    output_artifacts: Sequence[WorkflowArtifactRef | Mapping[str, Any]] = ()
    duration_ms: float | None = None
    error_summary: str | None = None

    def __post_init__(self) -> None:
        step_id = _require_trace_id(self.step_id, name="step_id")
        object.__setattr__(self, "step_id", step_id)
        object.__setattr__(self, "operation", _normalize_step_operation(self.operation))
        object.__setattr__(self, "status", _normalize_step_status(self.status))
        object.__setattr__(self, "provider", _optional_trace_text(self.provider, name="provider"))
        object.__setattr__(
            self,
            "capability",
            _optional_trace_text(self.capability, name="capability"),
        )
        object.__setattr__(self, "parent_id", _normalize_step_parent(self.parent_id, step_id))
        object.__setattr__(self, "input_artifacts", _artifact_refs(self.input_artifacts))
        object.__setattr__(self, "output_artifacts", _artifact_refs(self.output_artifacts))
        object.__setattr__(self, "duration_ms", _step_duration_ms(self.duration_ms))
        object.__setattr__(self, "error_summary", _optional_error_summary(self.error_summary))

    @classmethod
    def from_value(cls, value: WorkflowTraceStep | Mapping[str, Any]) -> WorkflowTraceStep:
        if isinstance(value, WorkflowTraceStep):
            return value
        if not isinstance(value, Mapping):
            raise WorldForgeError("Workflow trace step must be a JSON object.")
        return cls(
            step_id=value.get("step_id", ""),
            operation=value.get("operation", ""),
            status=value.get("status", ""),
            provider=value.get("provider"),
            capability=value.get("capability"),
            parent_id=value.get("parent_id"),
            input_artifacts=tuple(value.get("input_artifacts") or ()),
            output_artifacts=tuple(value.get("output_artifacts") or ()),
            duration_ms=value.get("duration_ms"),
            error_summary=value.get("error_summary"),
        )

    def to_dict(self) -> JSONDict:
        payload: JSONDict = {
            "step_id": self.step_id,
            "operation": self.operation,
            "status": self.status,
            "input_artifacts": [artifact.to_dict() for artifact in self.input_artifacts],
            "output_artifacts": [artifact.to_dict() for artifact in self.output_artifacts],
        }
        if self.provider is not None:
            payload["provider"] = self.provider
        if self.capability is not None:
            payload["capability"] = self.capability
        if self.parent_id is not None:
            payload["parent_id"] = self.parent_id
        if self.duration_ms is not None:
            payload["duration_ms"] = self.duration_ms
        if self.error_summary is not None:
            payload["error_summary"] = self.error_summary
        return payload


@dataclass(frozen=True, slots=True)
class WorkflowTrace:
    """JSON-native trace artifact for one composed workflow."""

    workflow_id: str
    name: str
    steps: Sequence[WorkflowTraceStep | Mapping[str, Any]]
    status: str | None = None
    schema_version: int = WORKFLOW_TRACE_SCHEMA_VERSION
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.schema_version != WORKFLOW_TRACE_SCHEMA_VERSION:
            raise WorldForgeError(
                f"WorkflowTrace schema_version must be {WORKFLOW_TRACE_SCHEMA_VERSION}."
            )
        object.__setattr__(
            self,
            "workflow_id",
            _require_trace_id(self.workflow_id, name="workflow_id"),
        )
        object.__setattr__(self, "name", _require_trace_text(self.name, name="Workflow name"))
        normalized_steps = tuple(WorkflowTraceStep.from_value(step) for step in self.steps)
        if not normalized_steps:
            raise WorldForgeError("WorkflowTrace steps must contain at least one step.")
        _validate_step_graph(normalized_steps)
        object.__setattr__(self, "steps", normalized_steps)
        derived_status = _derive_trace_status(normalized_steps)
        resolved_status = self.status or derived_status
        resolved_status = _require_trace_text(resolved_status, name="WorkflowTrace status").lower()
        if resolved_status not in WORKFLOW_TRACE_STEP_STATUSES:
            options = ", ".join(WORKFLOW_TRACE_STEP_STATUSES)
            raise WorldForgeError(f"WorkflowTrace status must be one of: {options}.")
        if resolved_status != derived_status:
            raise WorldForgeError(
                "WorkflowTrace status must match the status derived from its steps."
            )
        object.__setattr__(self, "status", resolved_status)
        metadata = require_json_dict(dict(self.metadata), name="WorkflowTrace metadata")
        object.__setattr__(self, "metadata", _sanitize_trace_metadata(metadata))
        dump_json(self.to_dict())

    @classmethod
    def from_value(cls, value: WorkflowTrace | Mapping[str, Any]) -> WorkflowTrace:
        """Reconstruct a workflow trace from an existing instance or JSON object."""

        if isinstance(value, WorkflowTrace):
            return value
        if not isinstance(value, Mapping):
            raise WorldForgeError("Workflow trace must be a JSON object.")
        return cls.from_dict(value)

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> WorkflowTrace:
        """Reconstruct a workflow trace from its serialized dictionary shape."""

        if not isinstance(payload, Mapping):
            raise WorldForgeError("Workflow trace payload must be a JSON object.")
        return cls(
            workflow_id=payload.get("workflow_id", ""),
            name=payload.get("name", ""),
            status=payload.get("status"),
            schema_version=payload.get("schema_version", WORKFLOW_TRACE_SCHEMA_VERSION),
            steps=payload.get("steps") or (),
            metadata=payload.get("metadata") or {},
        )

    def to_dict(self) -> JSONDict:
        status_counts = {
            status: sum(1 for step in self.steps if step.status == status)
            for status in WORKFLOW_TRACE_STEP_STATUSES
        }
        safe_to_attach = all(
            artifact.safe_to_attach
            for step in self.steps
            for artifact in (*step.input_artifacts, *step.output_artifacts)
        )
        return {
            "schema_version": self.schema_version,
            "workflow_id": self.workflow_id,
            "name": self.name,
            "status": self.status,
            "safe_to_attach": safe_to_attach,
            "step_count": len(self.steps),
            "status_counts": status_counts,
            "metadata": dict(self.metadata),
            "steps": [step.to_dict() for step in self.steps],
        }

    def to_json(self, *, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, sort_keys=True) + "\n"

    def to_markdown(self) -> str:
        lines = [
            "# WorldForge Workflow Trace",
            "",
            f"- workflow_id: `{self.workflow_id}`",
            f"- name: {self.name}",
            f"- status: `{self.status}`",
            f"- schema_version: {self.schema_version}",
            f"- steps: {len(self.steps)}",
            "",
            "| Step | Parent | Operation | Provider | Capability | Status | Duration | Error |",
            "| --- | --- | --- | --- | --- | --- | ---: | --- |",
        ]
        lines.extend(
            "| "
            f"`{step.step_id}` | "
            f"{_markdown_cell(step.parent_id or '-')} | "
            f"{_markdown_cell(step.operation)} | "
            f"{_markdown_cell(step.provider or '-')} | "
            f"{_markdown_cell(step.capability or '-')} | "
            f"`{step.status}` | "
            f"{'-' if step.duration_ms is None else f'{step.duration_ms:.2f}'} | "
            f"{_markdown_cell(step.error_summary or '-')} |"
            for step in self.steps
        )
        return "\n".join(lines) + "\n"


def workflow_trace_from_provider_events(
    events: Sequence[ProviderEvent | Mapping[str, Any]],
    *,
    workflow_id: str,
    name: str,
    metadata: Mapping[str, Any] | None = None,
) -> WorkflowTrace:
    """Build a workflow trace from already-sanitized provider events."""

    steps = _provider_event_trace_steps(events)
    return WorkflowTrace(
        workflow_id=workflow_id,
        name=name,
        steps=steps,
        metadata=metadata or {},
    )


def _provider_event_trace_steps(
    events: Sequence[ProviderEvent | Mapping[str, Any]],
) -> tuple[WorkflowTraceStep, ...]:
    steps = tuple(
        _provider_event_trace_step(index, _provider_event_payload(event))
        for index, event in enumerate(events, start=1)
    )
    if steps:
        return steps
    return (_no_provider_events_step(),)


def _provider_event_payload(event: ProviderEvent | Mapping[str, Any]) -> dict[str, Any]:
    if isinstance(event, ProviderEvent):
        return event.to_dict()
    return dict(event)


def _provider_event_trace_step(index: int, payload: Mapping[str, Any]) -> WorkflowTraceStep:
    status = _provider_event_status(payload)
    return WorkflowTraceStep(
        step_id=f"event-{index}",
        operation=str(payload.get("operation", "provider-operation")),
        status=status,
        provider=str(payload.get("provider", "provider")),
        capability=str(payload.get("operation", "capability")),
        duration_ms=payload.get("duration_ms"),
        error_summary=_provider_event_error_summary(payload, status=status),
        output_artifacts=_provider_event_output_artifacts(payload),
    )


def _provider_event_status(payload: Mapping[str, Any]) -> str:
    phase = str(payload.get("phase", "")).lower()
    if phase == "success":
        return "success"
    if phase == "failure":
        return "failed"
    return "running"


def _provider_event_error_summary(
    payload: Mapping[str, Any],
    *,
    status: str,
) -> str | None:
    if status != "failed":
        return None
    message = payload.get("message")
    if message is None:
        return None
    return str(message)


def _provider_event_output_artifacts(
    payload: Mapping[str, Any],
) -> tuple[WorkflowArtifactRef, ...]:
    artifact_id = payload.get("artifact_id")
    if not artifact_id:
        return ()
    return (WorkflowArtifactRef(label=str(artifact_id)),)


def _no_provider_events_step() -> WorkflowTraceStep:
    return WorkflowTraceStep(
        step_id="no-provider-events",
        operation="provider-events",
        status="skipped",
        error_summary="No provider events were emitted.",
    )


def _normalize_step_operation(value: object) -> str:
    return _require_trace_text(value, name="Workflow step operation")


def _normalize_step_status(value: object) -> str:
    status = _require_trace_text(value, name="Workflow step status").lower()
    if status not in WORKFLOW_TRACE_STEP_STATUSES:
        options = ", ".join(WORKFLOW_TRACE_STEP_STATUSES)
        raise WorldForgeError(f"Workflow step status must be one of: {options}.")
    return status


def _optional_trace_text(value: object | None, *, name: str) -> str | None:
    if value is None:
        return None
    return _require_trace_text(value, name=f"Workflow step {name}")


def _normalize_step_parent(value: object | None, step_id: str) -> str | None:
    if value is None:
        return None
    parent_id = _require_trace_id(value, name="parent_id")
    if parent_id == step_id:
        raise WorldForgeError("Workflow step parent_id must not equal step_id.")
    return parent_id


def _artifact_refs(
    values: Sequence[WorkflowArtifactRef | Mapping[str, Any]],
) -> tuple[WorkflowArtifactRef, ...]:
    return tuple(WorkflowArtifactRef.from_value(item) for item in values)


def _step_duration_ms(value: object | None) -> float | None:
    if value is None:
        return None
    duration = require_finite_number(value, name="Workflow step duration_ms")
    if duration < 0.0:
        raise WorldForgeError("Workflow step duration_ms must be non-negative.")
    return duration


def _optional_error_summary(value: str | None) -> str | None:
    if value is None:
        return None
    return _safe_error_summary(value) or None


def _validate_step_graph(steps: Sequence[WorkflowTraceStep]) -> None:
    step_ids = _validated_step_ids(steps)
    _validate_parent_references(steps, step_ids)
    _validate_parent_graph_acyclic(steps)


def _validated_step_ids(steps: Sequence[WorkflowTraceStep]) -> set[str]:
    seen: set[str] = set()
    for step in steps:
        if step.step_id in seen:
            raise WorldForgeError(f"WorkflowTrace step_id '{step.step_id}' is duplicated.")
        seen.add(step.step_id)
    return seen


def _validate_parent_references(
    steps: Sequence[WorkflowTraceStep],
    step_ids: set[str],
) -> None:
    for step in steps:
        if step.parent_id is not None and step.parent_id not in step_ids:
            raise WorldForgeError(
                f"WorkflowTrace step '{step.step_id}' references unknown parent_id "
                f"'{step.parent_id}'."
            )


def _validate_parent_graph_acyclic(steps: Sequence[WorkflowTraceStep]) -> None:
    parent_map = {step.step_id: step.parent_id for step in steps}
    for step in steps:
        _validate_parent_chain_acyclic(step, parent_map)


def _validate_parent_chain_acyclic(
    step: WorkflowTraceStep,
    parent_map: Mapping[str, str | None],
) -> None:
    visited = {step.step_id}
    parent = step.parent_id
    while parent is not None:
        if parent in visited:
            raise WorldForgeError("WorkflowTrace parent graph must not contain cycles.")
        visited.add(parent)
        parent = parent_map.get(parent)


def _derive_trace_status(steps: Sequence[WorkflowTraceStep]) -> str:
    statuses = {step.status for step in steps}
    if "failed" in statuses:
        return "failed"
    if "running" in statuses:
        return "running"
    if statuses == {"skipped"}:
        return "skipped"
    if "pending" in statuses:
        return "pending"
    return "success"


def _require_trace_text(value: object, *, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise WorldForgeError(f"{name} must be a non-empty string.")
    sanitized = _safe_error_summary(value.strip())
    if not sanitized:
        raise WorldForgeError(f"{name} must not be empty after sanitization.")
    return sanitized


def _require_trace_id(value: object, *, name: str) -> str:
    text = _require_trace_text(value, name=name)
    if _SECRET_LIKE_PATTERN.search(text) or _SAFE_ID_PATTERN.fullmatch(text) is None:
        raise WorldForgeError(
            f"{name} must use only letters, numbers, '.', '_', ':', or '-' and no secret-like text."
        )
    return text


def _safe_artifact_path(value: object, *, safe_to_attach: bool, name: str) -> str:
    text = _require_trace_text(value, name=name)
    sanitized_target = _sanitize_observable_target(text)
    if safe_to_attach and sanitized_target != text:
        raise WorldForgeError(f"{name} must not contain signed URLs, query strings, or fragments.")
    path = Path(text)
    if safe_to_attach and (path.is_absolute() or ".." in path.parts):
        raise WorldForgeError(f"{name} must be a safe relative path.")
    return text


def _safe_error_summary(value: str) -> str:
    redacted = _redact_observable_text(value)
    redacted = _HOST_LOCAL_PATH_PATTERN.sub("<host-local-path>", redacted)
    return redacted.strip()


def _sanitize_trace_metadata(value: JSONDict) -> JSONDict:
    return require_json_dict(_sanitize_value(value), name="WorkflowTrace metadata")


def _sanitize_value(value: object) -> object:
    if isinstance(value, str):
        return _safe_error_summary(value)
    if isinstance(value, list):
        return [_sanitize_value(item) for item in value]
    if isinstance(value, dict):
        sanitized: JSONDict = {}
        for key, item in value.items():
            key_text = str(key)
            if _SECRET_LIKE_PATTERN.search(key_text):
                raise WorldForgeError("WorkflowTrace metadata keys must not be secret-like.")
            sanitized[key_text] = _sanitize_value(item)
        return sanitized
    return value


def _markdown_cell(value: object) -> str:
    text = str(value if value is not None else "")
    return text.replace("|", "\\|").replace("\n", " ")


__all__ = [
    "WORKFLOW_TRACE_SCHEMA_VERSION",
    "WORKFLOW_TRACE_STEP_STATUSES",
    "WorkflowArtifactRef",
    "WorkflowTrace",
    "WorkflowTraceStep",
    "workflow_trace_from_provider_events",
]

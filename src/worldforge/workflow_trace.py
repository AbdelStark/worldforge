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
        object.__setattr__(self, "step_id", _require_trace_id(self.step_id, name="step_id"))
        object.__setattr__(
            self,
            "operation",
            _require_trace_text(self.operation, name="Workflow step operation"),
        )
        normalized_status = _require_trace_text(self.status, name="Workflow step status").lower()
        if normalized_status not in WORKFLOW_TRACE_STEP_STATUSES:
            options = ", ".join(WORKFLOW_TRACE_STEP_STATUSES)
            raise WorldForgeError(f"Workflow step status must be one of: {options}.")
        object.__setattr__(self, "status", normalized_status)
        if self.provider is not None:
            object.__setattr__(
                self,
                "provider",
                _require_trace_text(self.provider, name="Workflow step provider"),
            )
        if self.capability is not None:
            object.__setattr__(
                self,
                "capability",
                _require_trace_text(self.capability, name="Workflow step capability"),
            )
        if self.parent_id is not None:
            object.__setattr__(
                self,
                "parent_id",
                _require_trace_id(self.parent_id, name="parent_id"),
            )
            if self.parent_id == self.step_id:
                raise WorldForgeError("Workflow step parent_id must not equal step_id.")
        object.__setattr__(
            self,
            "input_artifacts",
            tuple(WorkflowArtifactRef.from_value(item) for item in self.input_artifacts),
        )
        object.__setattr__(
            self,
            "output_artifacts",
            tuple(WorkflowArtifactRef.from_value(item) for item in self.output_artifacts),
        )
        if self.duration_ms is not None:
            duration = require_finite_number(
                self.duration_ms,
                name="Workflow step duration_ms",
            )
            if duration < 0.0:
                raise WorldForgeError("Workflow step duration_ms must be non-negative.")
            object.__setattr__(self, "duration_ms", duration)
        if self.error_summary is not None:
            sanitized = _safe_error_summary(self.error_summary)
            object.__setattr__(self, "error_summary", sanitized or None)

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
        resolved_status = self.status or _derive_trace_status(normalized_steps)
        resolved_status = _require_trace_text(resolved_status, name="WorkflowTrace status").lower()
        if resolved_status not in WORKFLOW_TRACE_STEP_STATUSES:
            options = ", ".join(WORKFLOW_TRACE_STEP_STATUSES)
            raise WorldForgeError(f"WorkflowTrace status must be one of: {options}.")
        object.__setattr__(self, "status", resolved_status)
        metadata = require_json_dict(dict(self.metadata), name="WorkflowTrace metadata")
        object.__setattr__(self, "metadata", _sanitize_trace_metadata(metadata))
        dump_json(self.to_dict())

    def to_dict(self) -> JSONDict:
        status_counts = {
            status: sum(1 for step in self.steps if step.status == status)
            for status in WORKFLOW_TRACE_STEP_STATUSES
        }
        return {
            "schema_version": self.schema_version,
            "workflow_id": self.workflow_id,
            "name": self.name,
            "status": self.status,
            "safe_to_attach": True,
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

    steps: list[WorkflowTraceStep] = []
    for index, event in enumerate(events, start=1):
        payload = event.to_dict() if isinstance(event, ProviderEvent) else dict(event)
        phase = str(payload.get("phase", "")).lower()
        status = "success" if phase == "success" else "failed" if phase == "failure" else "running"
        steps.append(
            WorkflowTraceStep(
                step_id=f"event-{index}",
                operation=str(payload.get("operation", "provider-operation")),
                status=status,
                provider=str(payload.get("provider", "provider")),
                capability=str(payload.get("operation", "capability")),
                duration_ms=payload.get("duration_ms"),
                error_summary=payload.get("message") if status == "failed" else None,
                output_artifacts=(
                    (WorkflowArtifactRef(label=str(payload["artifact_id"])),)
                    if payload.get("artifact_id")
                    else ()
                ),
            )
        )
    if not steps:
        steps.append(
            WorkflowTraceStep(
                step_id="no-provider-events",
                operation="provider-events",
                status="skipped",
                error_summary="No provider events were emitted.",
            )
        )
    return WorkflowTrace(
        workflow_id=workflow_id,
        name=name,
        steps=steps,
        metadata=metadata or {},
    )


def _validate_step_graph(steps: Sequence[WorkflowTraceStep]) -> None:
    seen: set[str] = set()
    for step in steps:
        if step.step_id in seen:
            raise WorldForgeError(f"WorkflowTrace step_id '{step.step_id}' is duplicated.")
        seen.add(step.step_id)
    for step in steps:
        if step.parent_id is not None and step.parent_id not in seen:
            raise WorldForgeError(
                f"WorkflowTrace step '{step.step_id}' references unknown parent_id "
                f"'{step.parent_id}'."
            )
    parent_map = {step.step_id: step.parent_id for step in steps}
    for step in steps:
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

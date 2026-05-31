"""Structured provider event contracts."""

from __future__ import annotations

from dataclasses import dataclass, field

from worldforge._model_utils import (
    JSONDict,
    WorldForgeError,
    require_finite_number,
    require_json_dict,
)
from worldforge.provider_redaction import (
    _redact_observable_text,
    _redact_observable_value,
    _sanitize_observable_id,
    _sanitize_observable_target,
)


def _require_provider_event_name(value: object, *, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise WorldForgeError(f"{name} must be a non-empty string.")
    return value.strip()


def _require_provider_event_attempts(
    attempt: object,
    max_attempts: object,
) -> tuple[int, int]:
    if isinstance(attempt, bool) or not isinstance(attempt, int) or attempt < 1:
        raise WorldForgeError("ProviderEvent attempt must be greater than or equal to 1.")
    if (
        isinstance(max_attempts, bool)
        or not isinstance(max_attempts, int)
        or max_attempts < attempt
    ):
        raise WorldForgeError(
            "ProviderEvent max_attempts must be greater than or equal to attempt."
        )
    return attempt, max_attempts


def _normalize_provider_event_status_code(value: object | None) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value < 100 or value > 599:
        raise WorldForgeError("ProviderEvent status_code must be a valid HTTP status code.")
    return value


def _normalize_provider_event_duration(value: object | None) -> float | None:
    if value is None:
        return None
    duration_ms = require_finite_number(value, name="ProviderEvent duration_ms")
    if duration_ms < 0.0:
        raise WorldForgeError("ProviderEvent duration_ms must be non-negative when set.")
    return duration_ms


def _normalize_provider_event_method(value: object | None) -> str | None:
    if value is not None and not isinstance(value, str):
        raise WorldForgeError("ProviderEvent method must be a string when provided.")
    return value.strip().upper() if value else None


def _normalize_provider_event_message(value: object) -> str:
    if not isinstance(value, str):
        raise WorldForgeError("ProviderEvent message must be a string.")
    return _redact_observable_text(value)


def _normalize_provider_event_metadata(value: object) -> JSONDict:
    if not isinstance(value, dict):
        raise WorldForgeError("ProviderEvent metadata must be a JSON object.")
    return require_json_dict(
        _redact_observable_value(dict(value)),
        name="ProviderEvent metadata",
    )


@dataclass(slots=True)
class ProviderEvent:
    """Structured provider event emitted during observable operations."""

    provider: str
    operation: str
    phase: str
    attempt: int = 1
    max_attempts: int = 1
    method: str | None = None
    target: str | None = None
    status_code: int | None = None
    duration_ms: float | None = None
    message: str = ""
    metadata: JSONDict = field(default_factory=dict)
    run_id: str | None = None
    request_id: str | None = None
    trace_id: str | None = None
    span_id: str | None = None
    artifact_id: str | None = None
    input_digest: str | None = None

    def __post_init__(self) -> None:
        self.provider = _require_provider_event_name(
            self.provider,
            name="ProviderEvent provider",
        )
        self.operation = _require_provider_event_name(
            self.operation,
            name="ProviderEvent operation",
        )
        self.phase = _require_provider_event_name(
            self.phase,
            name="ProviderEvent phase",
        ).lower()
        self.attempt, self.max_attempts = _require_provider_event_attempts(
            self.attempt,
            self.max_attempts,
        )
        self.status_code = _normalize_provider_event_status_code(self.status_code)
        self.duration_ms = _normalize_provider_event_duration(self.duration_ms)
        self.method = _normalize_provider_event_method(self.method)
        self.target = _sanitize_observable_target(self.target)
        self.message = _normalize_provider_event_message(self.message)
        self.metadata = _normalize_provider_event_metadata(self.metadata)
        self.run_id = _sanitize_observable_id(self.run_id, name="ProviderEvent run_id")
        self.request_id = _sanitize_observable_id(
            self.request_id,
            name="ProviderEvent request_id",
        )
        self.trace_id = _sanitize_observable_id(self.trace_id, name="ProviderEvent trace_id")
        self.span_id = _sanitize_observable_id(self.span_id, name="ProviderEvent span_id")
        self.artifact_id = _sanitize_observable_id(
            self.artifact_id,
            name="ProviderEvent artifact_id",
        )
        self.input_digest = _sanitize_observable_id(
            self.input_digest,
            name="ProviderEvent input_digest",
        )

    def to_dict(self) -> JSONDict:
        payload: JSONDict = {
            "provider": self.provider,
            "operation": self.operation,
            "phase": self.phase,
            "attempt": self.attempt,
            "max_attempts": self.max_attempts,
            "method": self.method,
            "target": self.target,
            "status_code": self.status_code,
            "duration_ms": self.duration_ms,
            "message": self.message,
            "metadata": dict(self.metadata),
        }
        optional_fields = {
            "run_id": self.run_id,
            "request_id": self.request_id,
            "trace_id": self.trace_id,
            "span_id": self.span_id,
            "artifact_id": self.artifact_id,
            "input_digest": self.input_digest,
        }
        payload.update(
            {
                field_name: value
                for field_name, value in optional_fields.items()
                if value is not None
            }
        )
        return payload

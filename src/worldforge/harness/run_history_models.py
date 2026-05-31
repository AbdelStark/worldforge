"""Public run-history records and filters."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path

from worldforge.models import JSONDict, WorldForgeError


@dataclass(frozen=True, slots=True)
class RunHistoryFilter:
    """Filter values for preserved harness run history."""

    provider: str | None = None
    capability: str | None = None
    status: str | None = None
    created_from: date | None = None
    created_to: date | None = None
    artifact_type: str | None = None

    @classmethod
    def from_strings(
        cls,
        *,
        provider: str | None = None,
        capability: str | None = None,
        status: str | None = None,
        created_from: str | None = None,
        created_to: str | None = None,
        artifact_type: str | None = None,
    ) -> RunHistoryFilter:
        """Build a filter from CLI/TUI string fields."""

        return cls(
            provider=clean_history_filter(provider),
            capability=clean_history_filter(capability),
            status=clean_history_filter(status),
            created_from=parse_history_date(created_from),
            created_to=parse_history_date(created_to),
            artifact_type=clean_history_filter(artifact_type),
        )


@dataclass(frozen=True, slots=True)
class RunHistoryRecord:
    """A checkout-safe preserved-run summary for CLI and TUI views."""

    run_id: str
    kind: str
    status: str
    provider: str
    operation: str
    capability: str
    capabilities: tuple[str, ...]
    created_at: str
    created_date: date | None
    command: str
    rerun_command: str
    failure_summary: str
    safe_artifact_types: tuple[str, ...]
    artifact_count: int
    event_count: int
    path: Path
    display_path: str
    issue_bundle_command: str
    issue_bundle_path: str
    comparison_command: str | None
    recovery_command: str | None

    def to_dict(self) -> JSONDict:
        return {
            "run_id": self.run_id,
            "kind": self.kind,
            "status": self.status,
            "provider": self.provider,
            "operation": self.operation,
            "capability": self.capability,
            "capabilities": list(self.capabilities),
            "created_at": self.created_at,
            "command": self.command,
            "rerun_command": self.rerun_command,
            "failure_summary": self.failure_summary,
            "safe_artifact_types": list(self.safe_artifact_types),
            "artifact_count": self.artifact_count,
            "event_count": self.event_count,
            "path": self.display_path,
            "issue_bundle_command": self.issue_bundle_command,
            "issue_bundle_path": self.issue_bundle_path,
            "comparison_command": self.comparison_command,
            "recovery_command": self.recovery_command,
        }


def parse_history_date(value: str | None) -> date | None:
    """Parse an ISO date value used by run-history filters."""

    if value is None or not value.strip():
        return None
    try:
        return date.fromisoformat(value.strip())
    except ValueError as exc:
        raise WorldForgeError(f"run history date must use YYYY-MM-DD: {value}") from exc


def clean_history_filter(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = value.strip()
    return cleaned or None

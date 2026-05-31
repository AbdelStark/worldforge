"""Validation and rendering helpers for live-smoke evidence registries."""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

from worldforge.models import (
    JSONDict,
    WorldForgeError,
    _redact_observable_value,
    _sanitize_observable_target,
    require_json_dict,
)

LIVE_SMOKE_EVIDENCE_SCHEMA_VERSION = 1
LIVE_SMOKE_EVIDENCE_STATUSES = frozenset(
    {
        "passed",
        "failed",
        "not_run",
        "skipped_missing_runtime",
        "skipped_missing_credentials",
        "skipped_not_configured",
    }
)

_DATE_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_SKIP_STATUSES = frozenset(
    {"not_run", "skipped_missing_runtime", "skipped_missing_credentials", "skipped_not_configured"}
)
_TERMINAL_STATUSES = frozenset({"passed", "failed"})


def validate_live_smoke_registry(payload: Mapping[str, Any]) -> JSONDict:
    """Validate a publishable live-smoke evidence registry."""

    registry = require_json_dict(dict(payload), name="Live smoke evidence registry")
    if registry.get("schema_version") != LIVE_SMOKE_EVIDENCE_SCHEMA_VERSION:
        raise WorldForgeError(
            "Live smoke evidence registry schema_version must be "
            f"{LIVE_SMOKE_EVIDENCE_SCHEMA_VERSION}."
        )
    entries = registry.get("entries")
    if not isinstance(entries, list):
        raise WorldForgeError("Live smoke evidence registry entries must be a list.")
    seen: set[tuple[str, str]] = set()
    for index, entry in enumerate(entries):
        validated = validate_live_smoke_entry(entry, name=f"Live smoke evidence entry[{index}]")
        identity = (str(validated["provider"]), str(validated["capability"]))
        if identity in seen:
            raise WorldForgeError(
                "Live smoke evidence registry entries must be unique by provider and capability."
            )
        seen.add(identity)
        entries[index] = validated
    return registry


def validate_live_smoke_entry(
    payload: object,
    *,
    name: str = "Live smoke evidence entry",
) -> JSONDict:
    """Validate one registry entry and return a JSON-native copy."""

    entry = require_json_dict(payload, name=name, allow_empty=False)
    provider, status, artifact_path = _validate_live_smoke_entry_fields(entry, name=name)
    _validate_evidence_state(
        status=status,
        artifact_path=artifact_path,
        skip_reason=entry.get("skip_reason"),
        name=name,
    )
    _validate_known_limitations(entry.get("known_limitations"), name=name)
    _reject_unsafe_values(entry, name=f"{name} ({provider})")
    return entry


def _validate_live_smoke_entry_fields(
    entry: Mapping[str, Any],
    *,
    name: str,
) -> tuple[str, str, object]:
    provider = _require_non_empty_string(entry.get("provider"), name=f"{name}.provider")
    _require_non_empty_string(entry.get("capability"), name=f"{name}.capability")
    _require_non_empty_string(entry.get("command"), name=f"{name}.command")
    runtime_manifest = entry.get("runtime_manifest")
    if runtime_manifest is not None:
        _require_non_empty_string(runtime_manifest, name=f"{name}.runtime_manifest")
    date = _require_non_empty_string(entry.get("date"), name=f"{name}.date")
    if not _DATE_PATTERN.match(date):
        raise WorldForgeError(f"{name}.date must use YYYY-MM-DD.")
    _require_non_empty_string(entry.get("version"), name=f"{name}.version")
    status = _require_choice(
        entry.get("status"),
        LIVE_SMOKE_EVIDENCE_STATUSES,
        name=f"{name}.status",
    )
    artifact_path = entry.get("artifact_path")
    if artifact_path is not None:
        _require_safe_string(artifact_path, name=f"{name}.artifact_path")
    return provider, status, artifact_path


def _validate_evidence_state(
    *,
    status: str,
    artifact_path: object,
    skip_reason: object,
    name: str,
) -> None:
    if status in _TERMINAL_STATUSES and artifact_path is None:
        raise WorldForgeError(f"{name}.artifact_path is required for {status} evidence.")
    if status in _TERMINAL_STATUSES and skip_reason is not None:
        raise WorldForgeError(f"{name}.skip_reason must be null for {status} evidence.")
    if status in _SKIP_STATUSES and artifact_path is not None:
        raise WorldForgeError(f"{name}.artifact_path must be null for skipped evidence.")
    if status in _SKIP_STATUSES:
        _require_non_empty_string(skip_reason, name=f"{name}.skip_reason")


def _validate_known_limitations(limitations: object, *, name: str) -> None:
    if not isinstance(limitations, list):
        raise WorldForgeError(f"{name}.known_limitations must be a list.")
    for index, limitation in enumerate(limitations):
        _require_non_empty_string(limitation, name=f"{name}.known_limitations[{index}]")


def render_live_smoke_registry_table(payload: Mapping[str, Any]) -> list[str]:
    """Render a validated registry as Markdown table rows."""

    registry = validate_live_smoke_registry(payload)
    lines = [
        "| Provider | Capability | Status | Evidence |",
        "| --- | --- | --- | --- |",
    ]
    for entry in registry["entries"]:
        evidence = entry.get("artifact_path") or entry.get("skip_reason") or "not recorded"
        lines.append(
            f"| `{entry['provider']}` | `{entry['capability']}` | {entry['status']} | {evidence} |"
        )
    return lines


def _reject_unsafe_values(value: object, *, name: str) -> None:
    if isinstance(value, str):
        _reject_unsafe_string(value, name=name)
        return
    if isinstance(value, list):
        _reject_unsafe_sequence(value, name=name)
        return
    if isinstance(value, dict):
        _reject_unsafe_mapping(value, name=name)


def _reject_unsafe_string(value: str, *, name: str) -> None:
    if _redact_observable_value(value) != value:
        raise WorldForgeError(f"{name} contains secret-like material.")
    if _sanitize_observable_target(value) != value:
        raise WorldForgeError(f"{name} contains an unsafe URL.")


def _reject_unsafe_sequence(values: list[object], *, name: str) -> None:
    for index, item in enumerate(values):
        _reject_unsafe_values(item, name=f"{name}[{index}]")


def _reject_unsafe_mapping(values: dict[object, object], *, name: str) -> None:
    for key, item in values.items():
        _reject_unsafe_key(key, name=name)
        _reject_unsafe_values(item, name=f"{name}.{key}")


def _reject_unsafe_key(key: object, *, name: str) -> None:
    if _redact_observable_value("", key=str(key)) != "":
        raise WorldForgeError(f"{name}.{key} is a secret-like field.")


def _require_safe_string(value: object, *, name: str) -> str:
    text = _require_non_empty_string(value, name=name)
    if _sanitize_observable_target(text) != text:
        raise WorldForgeError(f"{name} must not contain signed URL query strings or fragments.")
    return text


def _require_non_empty_string(value: object, *, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise WorldForgeError(f"{name} must be a non-empty string.")
    return value


def _require_choice(value: object, choices: frozenset[str], *, name: str) -> str:
    if not isinstance(value, str) or value not in choices:
        formatted = ", ".join(sorted(choices))
        raise WorldForgeError(f"{name} must be one of: {formatted}.")
    return value


__all__ = [
    "LIVE_SMOKE_EVIDENCE_SCHEMA_VERSION",
    "LIVE_SMOKE_EVIDENCE_STATUSES",
    "render_live_smoke_registry_table",
    "validate_live_smoke_entry",
    "validate_live_smoke_registry",
]

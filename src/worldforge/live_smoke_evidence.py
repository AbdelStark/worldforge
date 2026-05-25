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
    if status in {"passed", "failed"} and artifact_path is None:
        raise WorldForgeError(f"{name}.artifact_path is required for {status} evidence.")
    skip_reason = entry.get("skip_reason")
    if status in _SKIP_STATUSES or skip_reason is not None:
        _require_non_empty_string(skip_reason, name=f"{name}.skip_reason")
    limitations = entry.get("known_limitations")
    if not isinstance(limitations, list):
        raise WorldForgeError(f"{name}.known_limitations must be a list.")
    for index, limitation in enumerate(limitations):
        _require_non_empty_string(limitation, name=f"{name}.known_limitations[{index}]")
    _reject_unsafe_values(entry, name=f"{name} ({provider})")
    return entry


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
        if _redact_observable_value(value) != value:
            raise WorldForgeError(f"{name} contains secret-like material.")
        sanitized = _sanitize_observable_target(value)
        if sanitized != value:
            raise WorldForgeError(f"{name} contains an unsafe URL.")
    elif isinstance(value, list):
        for index, item in enumerate(value):
            _reject_unsafe_values(item, name=f"{name}[{index}]")
    elif isinstance(value, dict):
        for key, item in value.items():
            if _redact_observable_value("", key=str(key)) != "":
                raise WorldForgeError(f"{name}.{key} is a secret-like field.")
            _reject_unsafe_values(item, name=f"{name}.{key}")


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

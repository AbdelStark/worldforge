"""Reporting and sanitization helpers for world migration previews."""

from __future__ import annotations

import re

from worldforge._state import SCHEMA_VERSION
from worldforge.models import JSONDict

_SAFE_NAME_PATTERN = re.compile(r"^[A-Za-z0-9_.-]+$")
_SECRET_LIKE_PATTERN = re.compile(
    r"(?:api[_-]?key|authorization|bearer|secret|signature|signed|token|x-amz)",
    re.IGNORECASE,
)
_HOST_LOCAL_PATH_PATTERN = re.compile(
    r"(?P<path>(?:/Users|/private|/var/folders|/tmp)/[^\s,;:)'\"]+)"
)
_QUOTED_UNSAFE_NAME_PATTERN = re.compile(r"(['\"])([^'\"]*[\\/][^'\"]*|\.{1,2})\1")


def render_world_migration_preview_markdown(report: JSONDict) -> str:
    """Render a migration preview report for operator review."""

    counts = report.get("counts", {})
    schema = report.get("schema", {})
    source = report.get("source", {})
    lines = [
        "# WorldForge World Migration Preview",
        "",
        f"status: `{report.get('status', 'unknown')}`",
        f"safe_to_attach: `{str(report.get('safe_to_attach', False)).lower()}`",
        f"read_only: `{str(report.get('read_only', False)).lower()}`",
        f"can_apply_safely: `{str(report.get('can_apply_safely', False)).lower()}`",
        f"rewrite_available: `{str(report.get('rewrite_available', False)).lower()}`",
        f"source: `{source.get('label', '<input>')}`",
        f"source_kind: `{source.get('kind', 'unknown')}`",
        f"world_schema_version: `{schema.get('world_schema_version', 'missing')}`",
        (
            "current_world_schema_version: "
            f"`{schema.get('current_world_schema_version', SCHEMA_VERSION)}`"
        ),
        "",
        f"required_changes: `{counts.get('required_change_count', 0)}`",
        f"invalid_fields: `{counts.get('invalid_field_count', 0)}`",
        f"unsafe_ids: `{counts.get('unsafe_id_count', 0)}`",
        f"bounding_box_corrections: `{counts.get('bounding_box_correction_count', 0)}`",
        "",
        "First triage:",
        "",
        f"- {report.get('first_triage_step', _first_triage_step(False, False))}",
    ]

    _append_table(
        lines,
        title="Required Changes",
        rows=report.get("required_changes", []),
        columns=("kind", "path", "message"),
    )
    _append_table(
        lines,
        title="Invalid Fields",
        rows=report.get("invalid_fields", []),
        columns=("path", "message"),
    )
    _append_table(
        lines,
        title="Unsafe IDs",
        rows=report.get("unsafe_ids", []),
        columns=("kind", "path", "message"),
    )
    _append_table(
        lines,
        title="Bounding Box Corrections",
        rows=report.get("bounding_box_corrections", []),
        columns=("path", "object_id", "message"),
    )
    return "\n".join(lines) + "\n"


def _required_change(*, kind: str, path: str, message: str) -> JSONDict:
    return {"kind": kind, "path": path, "message": message, "safe_to_attach": True}


def _invalid_field(*, path: str, message: str, details: JSONDict | None = None) -> JSONDict:
    return {
        "path": path,
        "message": _sanitize_message(message),
        "safe_to_attach": True,
        "details": details or {},
    }


def _unsafe_id(*, kind: str, path: str, message: str, value: object) -> JSONDict:
    return {
        "kind": kind,
        "path": path,
        "message": _sanitize_message(message),
        "value": value,
        "safe_to_attach": True,
    }


def _sanitize_message(message: str) -> str:
    sanitized = _HOST_LOCAL_PATH_PATTERN.sub("<host-local-path>", message)
    sanitized = _QUOTED_UNSAFE_NAME_PATTERN.sub(r"\1<unsafe-id>\1", sanitized)
    if _SECRET_LIKE_PATTERN.search(sanitized):
        return _SECRET_LIKE_PATTERN.sub("<redacted>", sanitized)
    return sanitized


def _safe_file_name(value: str) -> str:
    return value if _is_public_name(value) else "<unsafe-name>"


def _safe_id_value(value: object) -> str:
    if isinstance(value, str) and value.strip() and _is_public_name(value):
        return value
    return "<unsafe-id>"


def _path_token(value: object) -> str:
    if isinstance(value, str) and value.strip() and _is_public_name(value):
        return value
    return "<unsafe-id>"


def _is_public_name(value: str) -> bool:
    return (
        _SAFE_NAME_PATTERN.fullmatch(value) is not None
        and _SECRET_LIKE_PATTERN.search(value) is None
    )


def _first_triage_step(blocked: bool, needs_migration: bool) -> str:
    if blocked:
        return (
            "run `uv run worldforge world preflight --state-dir .worldforge/worlds "
            "--workspace-dir .worldforge --format json` before moving or rewriting state."
        )
    if needs_migration:
        return (
            "export the source JSON first, review this preview, then apply migration through an "
            "explicit host-owned rewrite step."
        )
    return "no migration is required for this world state."


def _append_table(
    lines: list[str],
    *,
    title: str,
    rows: object,
    columns: tuple[str, ...],
) -> None:
    lines.extend(["", f"## {title}", ""])
    if not isinstance(rows, list) or not rows:
        lines.append("- None.")
        return
    lines.append("| " + " | ".join(column.replace("_", " ").title() for column in columns) + " |")
    lines.append("| " + " | ".join("---" for _ in columns) + " |")
    for row in rows:
        if not isinstance(row, dict):
            continue
        lines.append(
            "| " + " | ".join(_markdown_cell(row.get(column)) for column in columns) + " |"
        )


def _markdown_cell(value: object) -> str:
    text = str(value if value is not None else "")
    return text.replace("|", "\\|").replace("\n", " ")

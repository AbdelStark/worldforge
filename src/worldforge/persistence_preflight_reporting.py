"""Sanitized reporting helpers for local state preflight checks."""

from __future__ import annotations

import re
from pathlib import Path

from worldforge.harness.workspace import validate_run_id
from worldforge.models import JSONDict

DEFAULT_STATE_DIR_DISPLAY = ".worldforge/worlds"
DEFAULT_WORKSPACE_DISPLAY = ".worldforge"
DEFAULT_RETENTION_KEEP = 20

_SECRET_LIKE_PATTERN = re.compile(
    r"(?:api[_-]?key|authorization|bearer|secret|signature|signed|token|x-amz)",
    re.IGNORECASE,
)
_SAFE_NAME_PATTERN = re.compile(r"^[A-Za-z0-9_.-]+$")


def _issue(
    *,
    check: str,
    severity: str,
    path: str,
    message: str,
    recovery_command: str,
    details: JSONDict | None = None,
) -> JSONDict:
    return {
        "check": check,
        "severity": severity,
        "path": path,
        "message": message,
        "recovery_command": recovery_command,
        "safe_to_attach": True,
        "details": details or {},
    }


def _display_path(path: Path, root: Path, label: str) -> str:
    try:
        relative = path.relative_to(root)
    except ValueError:
        try:
            relative = path.resolve().relative_to(root.resolve())
        except ValueError:
            return f"<{label}>/{_safe_file_name(path.name)}"
    if relative == Path("."):
        return f"<{label}>"
    return f"<{label}>/{relative.as_posix()}"


def _safe_file_name(value: str) -> str:
    return value if _SAFE_NAME_PATTERN.fullmatch(value) else "<unsafe-name>"


def _diagnostic_command() -> str:
    return (
        "uv run worldforge world preflight "
        f"--state-dir {DEFAULT_STATE_DIR_DISPLAY} "
        f"--workspace-dir {DEFAULT_WORKSPACE_DISPLAY} "
        "--format json > worldforge-state-preflight.json"
    )


def _quarantine_world_command(world_file: Path) -> str:
    name = _safe_file_name(world_file.name)
    return (
        f"{_diagnostic_command()} && mkdir -p {DEFAULT_WORKSPACE_DISPLAY}/quarantine/worlds && "
        f"mv {DEFAULT_STATE_DIR_DISPLAY}/{name} "
        f"{DEFAULT_WORKSPACE_DISPLAY}/quarantine/worlds/{name}"
    )


def _quarantine_run_command(run_path: Path) -> str:
    name = _safe_file_name(run_path.name)
    return (
        f"{_diagnostic_command()} && mkdir -p {DEFAULT_WORKSPACE_DISPLAY}/quarantine/runs && "
        f"mv {DEFAULT_WORKSPACE_DISPLAY}/runs/{name} "
        f"{DEFAULT_WORKSPACE_DISPLAY}/quarantine/runs/{name}"
    )


def _artifact_recovery_command(run_id: str | None) -> str:
    if run_id and _is_valid_run_id(run_id):
        return (
            f"uv run worldforge runs bundle {run_id} "
            f"--workspace-dir {DEFAULT_WORKSPACE_DISPLAY} --format markdown "
            "> worldforge-run-issue.md && regenerate the run manifest with relative artifact "
            "paths under the run workspace"
        )
    return (
        f"{_diagnostic_command()} && regenerate the run manifest with relative artifact paths "
        "under the run workspace"
    )


def _sanitize_message(
    message: str,
    *,
    roots: tuple[tuple[Path, str], ...] = (),
) -> str:
    sanitized = message
    for root, label in roots:
        sanitized = sanitized.replace(str(root.resolve()), f"<{label}>")
        sanitized = sanitized.replace(str(root), f"<{label}>")
    if _SECRET_LIKE_PATTERN.search(sanitized):
        sanitized = _SECRET_LIKE_PATTERN.sub("<redacted>", sanitized)
    return sanitized


def _markdown_cell(value: object) -> str:
    text = str(value if value is not None else "")
    return text.replace("|", "\\|").replace("\n", " ")


def _is_valid_run_id(value: str) -> bool:
    try:
        validate_run_id(value)
    except ValueError:
        return False
    return True

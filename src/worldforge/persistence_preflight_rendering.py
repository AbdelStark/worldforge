"""Markdown rendering for local state preflight reports."""

from __future__ import annotations

from worldforge.models import JSONDict
from worldforge.persistence_preflight_reporting import (
    DEFAULT_RETENTION_KEEP,
    _diagnostic_command,
    _markdown_cell,
)


def render_state_preflight_markdown(report: JSONDict) -> str:
    """Render a local state preflight report for operator runbooks."""

    counts = report.get("counts", {})
    lines = [
        "# WorldForge Local State Preflight",
        "",
        f"status: `{report.get('status', 'unknown')}`",
        f"safe_to_attach: `{str(report.get('safe_to_attach', False)).lower()}`",
        f"state_dir: `{report.get('state_dir', '<state-dir>')}`",
        f"workspace_dir: `{report.get('workspace_dir', '<workspace-dir>')}`",
        f"retention_keep: `{report.get('retention_keep', DEFAULT_RETENTION_KEEP)}`",
        "",
        f"errors: `{counts.get('error_count', 0)}`",
        f"warnings: `{counts.get('warning_count', 0)}`",
        f"world_files_checked: `{counts.get('world_files_checked', 0)}`",
        f"run_workspaces_checked: `{counts.get('run_workspaces_checked', 0)}`",
        "",
        "Diagnostic command:",
        "",
        f"```bash\n{report.get('diagnostic_command', _diagnostic_command())}\n```",
    ]
    issues = report.get("issues", [])
    if not isinstance(issues, list) or not issues:
        lines.extend(["", "No local state issues were found."])
        return "\n".join(lines)

    lines.extend(
        [
            "",
            "| Severity | Check | Path | Message | Recovery |",
            "| --- | --- | --- | --- | --- |",
        ]
    )
    for issue in issues:
        if not isinstance(issue, dict):
            continue
        lines.append(
            "| "
            f"{_markdown_cell(issue.get('severity'))} | "
            f"{_markdown_cell(issue.get('check'))} | "
            f"{_markdown_cell(issue.get('path'))} | "
            f"{_markdown_cell(issue.get('message'))} | "
            f"{_markdown_cell(issue.get('recovery_command'))} |"
        )
    return "\n".join(lines)

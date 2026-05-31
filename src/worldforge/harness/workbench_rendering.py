"""Markdown rendering for provider workbench reports."""

from __future__ import annotations

from worldforge.models import JSONDict


def provider_workbench_markdown(report: JSONDict) -> str:
    """Render a provider workbench report as pasteable Markdown."""

    lines = _workbench_markdown_header(report)
    _append_required_tests_markdown(lines, report)
    _append_planned_capabilities_markdown(lines, report)
    _append_checks_markdown(lines, report)
    _append_promotion_markdown(lines, report)
    _append_safe_artifacts_markdown(lines, report)
    _append_validation_commands_markdown(lines, report)
    _append_author_links_markdown(lines, report)
    return "\n".join(lines)


def _workbench_markdown_header(report: JSONDict) -> list[str]:
    return [
        f"# Provider Workbench: `{report['provider']}`",
        "",
        f"- status: `{report['status']}`",
        f"- target source: `{report['target_source']}`",
        f"- catalog registered: `{str(report['catalog_registered']).lower()}`",
        f"- live calls: `{str(report['live']).lower()}`",
        f"- duration_ms: `{report['duration_ms']}`",
        "",
    ]


def _append_markdown_section(lines: list[str], title: str) -> None:
    lines.extend([f"## {title}", ""])


def _markdown_code_list(values: object, *, empty: str) -> list[str]:
    if isinstance(values, list) and values:
        return [f"- `{value}`" for value in values]
    return [empty]


def _append_required_tests_markdown(lines: list[str], report: JSONDict) -> None:
    _append_markdown_section(lines, "Required Capability Tests")
    lines.extend(_markdown_code_list(report["required_tests"], empty="- none advertised"))


def _append_planned_capabilities_markdown(lines: list[str], report: JSONDict) -> None:
    lines.append("")
    _append_markdown_section(lines, "Planned Capability Surface")
    lines.extend(
        _markdown_code_list(
            report.get("planned_capabilities", []),
            empty="- none declared",
        )
    )


def _append_checks_markdown(lines: list[str], report: JSONDict) -> None:
    lines.extend(["", "## Checks", ""])
    lines.extend(
        f"- `{check['status']}` `{check['name']}`: {check['detail']}" for check in report["checks"]
    )


def _append_promotion_markdown(lines: list[str], report: JSONDict) -> None:
    promotion = report["promotion"]
    lines.extend(
        [
            "",
            "## Promotion Evidence",
            "",
            f"- current status: `{promotion['current_status']}`",
        ]
    )
    missing_by_status = promotion["missing_evidence_by_status"]
    if not isinstance(missing_by_status, dict) or not missing_by_status:
        lines.append("- no promotion gaps for the current status")
        return
    lines.extend(
        f"- missing for `{status}`: {', '.join(f'`{item}`' for item in missing) or 'none'}"
        for status, missing in missing_by_status.items()
    )


def _append_safe_artifacts_markdown(lines: list[str], report: JSONDict) -> None:
    lines.extend(["", "## Safe Artifacts", ""])
    safe_artifacts = report.get("safe_artifacts", [])
    if not isinstance(safe_artifacts, list) or not safe_artifacts:
        lines.append("- no local artifacts were referenced")
        return
    lines.extend(
        f"- `{artifact['path']}`: {artifact['note']}"
        for artifact in safe_artifacts
        if isinstance(artifact, dict)
    )


def _append_validation_commands_markdown(lines: list[str], report: JSONDict) -> None:
    lines.extend(["", "## Validation Commands", ""])
    validation_commands = report.get("validation_commands", [])
    if isinstance(validation_commands, list):
        lines.extend(f"- `{command}`" for command in validation_commands)


def _append_author_links_markdown(lines: list[str], report: JSONDict) -> None:
    docs = report["docs"]
    lines.extend(
        [
            "",
            "## Author Links",
            "",
            f"- authoring guide: `{docs['authoring_guide']}`",
            f"- generated catalog check: `{docs['catalog_check']}`",
            f"- fixture pattern: `{docs['fixture_pattern']}`",
            "",
            "## Issue Summary",
            "",
            str(report["issue_summary"]),
        ]
    )

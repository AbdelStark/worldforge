"""Markdown rendering helpers for preserved runs."""

from __future__ import annotations

from worldforge.harness.run_history_models import RunHistoryRecord


def run_history_markdown(records: tuple[RunHistoryRecord, ...]) -> str:
    """Render preserved run history as Markdown."""

    lines = [
        "# WorldForge Run History",
        "",
        *_run_history_table_lines(records),
        "",
        "## Rerun Commands",
        "",
        *_run_history_rerun_command_lines(records),
    ]
    return "\n".join(lines) + "\n"


def _run_history_table_lines(records: tuple[RunHistoryRecord, ...]) -> list[str]:
    return [
        "| Run | Kind | Status | Provider | Capability | Artifacts | Recovery |",
        "| --- | --- | --- | --- | --- | --- | --- |",
        *_run_history_table_rows(records),
    ]


def _run_history_table_rows(records: tuple[RunHistoryRecord, ...]) -> list[str]:
    if not records:
        return ["| - | - | - | - | - | - | - |"]
    return [_run_history_table_row(record) for record in records]


def _run_history_table_row(record: RunHistoryRecord) -> str:
    return (
        "| `{run_id}` | {kind} | {status} | {provider} | {capability} | {artifacts} | {recovery} |"
    ).format(
        run_id=record.run_id,
        kind=_markdown_table_value(record.kind),
        status=_markdown_table_value(record.status),
        provider=_markdown_table_value(record.provider),
        capability=_markdown_table_value(record.capability),
        artifacts=_markdown_table_value(", ".join(record.safe_artifact_types)),
        recovery=_markdown_command_or_dash(record.recovery_command),
    )


def _run_history_rerun_command_lines(records: tuple[RunHistoryRecord, ...]) -> list[str]:
    if not records:
        return ["- No preserved runs matched the filter."]
    return [f"- `{record.run_id}`: `{record.rerun_command}`" for record in records]


def _markdown_table_value(value: str) -> str:
    return value or "-"


def _markdown_command_or_dash(value: str | None) -> str:
    if not value:
        return "-"
    return f"`{value}`"

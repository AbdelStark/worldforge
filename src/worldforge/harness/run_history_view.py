"""Textual-free run-history view formatting helpers."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from worldforge.harness.run_history_models import RunHistoryFilter, RunHistoryRecord
from worldforge.models import WorldForgeError

RUNS_DETAIL_EMPTY_MESSAGE = "Select a run to see recovery commands."
RUN_STATUS_FILTER_OPTIONS: tuple[tuple[str, str], ...] = (
    ("any status", ""),
    ("completed", "completed"),
    ("failed", "failed"),
    ("skipped", "skipped"),
    ("cancelled", "cancelled"),
)


@dataclass(frozen=True, slots=True)
class RunHistoryInputSpec:
    widget_id: str
    placeholder: str

    @property
    def selector(self) -> str:
        return f"#{self.widget_id}"


@dataclass(frozen=True, slots=True)
class RunHistorySelectSpec:
    widget_id: str
    options: tuple[tuple[str, str], ...]
    default: str

    @property
    def selector(self) -> str:
        return f"#{self.widget_id}"


@dataclass(frozen=True, slots=True)
class RunHistoryOutputSpec:
    widget_id: str
    empty_message: str

    @property
    def selector(self) -> str:
        return f"#{self.widget_id}"


@dataclass(frozen=True, slots=True)
class RunHistoryScreenSpec:
    root_id: str
    filter_row_id: str
    body_id: str
    table_wrap_id: str
    table_id: str
    table_columns: tuple[str, ...]
    empty: RunHistoryOutputSpec
    detail: RunHistoryOutputSpec
    provider_filter: RunHistoryInputSpec
    capability_filter: RunHistoryInputSpec
    status_filter: RunHistorySelectSpec
    created_from_filter: RunHistoryInputSpec
    artifact_filter: RunHistoryInputSpec


@dataclass(frozen=True, slots=True)
class RunHistoryBindingSpec:
    key: str
    action: str
    description: str
    show: bool = True


RUN_HISTORY_SCREEN_SPEC = RunHistoryScreenSpec(
    root_id="runs-root",
    filter_row_id="runs-filter-row",
    body_id="runs-body",
    table_wrap_id="runs-table-wrap",
    table_id="runs-table",
    table_columns=("run", "status", "provider", "capability", "artifacts"),
    empty=RunHistoryOutputSpec(
        "runs-empty",
        "No preserved runs match the active filters.",
    ),
    detail=RunHistoryOutputSpec("runs-detail", RUNS_DETAIL_EMPTY_MESSAGE),
    provider_filter=RunHistoryInputSpec("runs-provider-filter", "provider"),
    capability_filter=RunHistoryInputSpec("runs-capability-filter", "capability"),
    status_filter=RunHistorySelectSpec("runs-status-filter", RUN_STATUS_FILTER_OPTIONS, ""),
    created_from_filter=RunHistoryInputSpec("runs-created-from-filter", "from YYYY-MM-DD"),
    artifact_filter=RunHistoryInputSpec("runs-artifact-filter", "artifact type"),
)
RUN_HISTORY_BINDING_SPECS: tuple[RunHistoryBindingSpec, ...] = (
    RunHistoryBindingSpec("enter", "open_selected", "Open"),
    RunHistoryBindingSpec("f", "focus_provider_filter", "Filter"),
    RunHistoryBindingSpec("escape", "clear_filters", "Clear"),
)
RUN_HISTORY_TABLE_ID = RUN_HISTORY_SCREEN_SPEC.table_id
RUN_HISTORY_TABLE_SELECTOR = f"#{RUN_HISTORY_TABLE_ID}"
RUN_HISTORY_EMPTY_SELECTOR = RUN_HISTORY_SCREEN_SPEC.empty.selector
RUN_HISTORY_DETAIL_SELECTOR = RUN_HISTORY_SCREEN_SPEC.detail.selector
RUN_PROVIDER_FILTER_ID = RUN_HISTORY_SCREEN_SPEC.provider_filter.widget_id
RUN_CAPABILITY_FILTER_ID = RUN_HISTORY_SCREEN_SPEC.capability_filter.widget_id
RUN_CREATED_FROM_FILTER_ID = RUN_HISTORY_SCREEN_SPEC.created_from_filter.widget_id
RUN_ARTIFACT_FILTER_ID = RUN_HISTORY_SCREEN_SPEC.artifact_filter.widget_id
RUN_STATUS_FILTER_ID = RUN_HISTORY_SCREEN_SPEC.status_filter.widget_id
RUN_FILTER_INPUT_SELECTORS: tuple[str, ...] = (
    RUN_HISTORY_SCREEN_SPEC.provider_filter.selector,
    RUN_HISTORY_SCREEN_SPEC.capability_filter.selector,
    RUN_HISTORY_SCREEN_SPEC.created_from_filter.selector,
    RUN_HISTORY_SCREEN_SPEC.artifact_filter.selector,
)


@dataclass(frozen=True, slots=True)
class RunHistoryFilterForm:
    provider: str | None = None
    capability: str | None = None
    status: str | None = None
    created_from: str | None = None
    artifact_type: str | None = None


@dataclass(frozen=True, slots=True)
class RunHistoryFilterResult:
    filters: RunHistoryFilter
    error: str | None = None


def run_history_filter_from_form(form: RunHistoryFilterForm) -> RunHistoryFilterResult:
    try:
        filters = RunHistoryFilter.from_strings(
            provider=form.provider,
            capability=form.capability,
            status=form.status,
            created_from=form.created_from,
            artifact_type=form.artifact_type,
        )
    except WorldForgeError as exc:
        return RunHistoryFilterResult(RunHistoryFilter(), str(exc))
    return RunHistoryFilterResult(filters)


def selected_run_record(
    records: Mapping[str, RunHistoryRecord],
    selected_run_id: str | None,
) -> RunHistoryRecord | None:
    return records.get(selected_run_id or "")


def selected_run_provider_label(record: RunHistoryRecord | None) -> str:
    return record.provider if record is not None else ""


def first_visible_run_id(ordered_ids: tuple[str, ...] | list[str]) -> str | None:
    return ordered_ids[0] if ordered_ids else None


def run_history_detail_text(record: RunHistoryRecord | None) -> str:
    """Render one preserved-run detail panel body."""

    if record is None:
        return RUNS_DETAIL_EMPTY_MESSAGE
    return "\n".join(_run_history_detail_lines(record))


def run_history_table_row(record: RunHistoryRecord) -> tuple[str, str, str, str, str]:
    """Return the stable table row used by the TUI run-history screen."""

    return (
        record.run_id,
        _run_history_value(record.status),
        _run_history_value(record.provider),
        _run_history_value(record.capability),
        _run_history_artifacts_label(record),
    )


def _run_history_value(value: str | None) -> str:
    if value:
        return value
    return "-"


def _run_history_detail_line(label: str, value: str | None) -> str:
    return f"{label}: {_run_history_value(value)}"


def _run_history_styled_line(label: str, value: str, *, style: str) -> str:
    return f"{label}: [{style}]{value}[/]"


def _run_history_optional_line(
    label: str,
    value: str | None,
    *,
    style: str | None = None,
) -> str | None:
    if not value:
        return None
    if style is None:
        return f"{label}: {value}"
    return _run_history_styled_line(label, value, style=style)


def _run_history_detail_lines(record: RunHistoryRecord) -> list[str]:
    lines = [
        f"[bold]{record.run_id}[/]",
        _run_history_detail_line("status", record.status),
        _run_history_detail_line("kind", record.kind),
        _run_history_detail_line("provider", record.provider),
        _run_history_detail_line("capability", record.capability),
        _run_history_styled_line("rerun", record.rerun_command, style="dim"),
        _run_history_styled_line("issue bundle", record.issue_bundle_command, style="dim"),
    ]
    lines.extend(
        line
        for line in (
            _run_history_optional_line("compare", record.comparison_command, style="dim"),
            _run_history_optional_line("recovery", record.recovery_command, style="bold"),
            _run_history_optional_line("failure", record.failure_summary),
        )
        if line is not None
    )
    return lines


def _run_history_artifacts_label(record: RunHistoryRecord) -> str:
    artifacts = ", ".join(record.safe_artifact_types)
    if artifacts:
        return artifacts
    return "-"

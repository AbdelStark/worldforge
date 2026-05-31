"""Row builders for preserved run comparison reports."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from worldforge.harness.report_compare_regression import (
    result_event_count as _result_event_count,
)
from worldforge.models import JSONDict

if TYPE_CHECKING:
    from worldforge.harness.report_compare import PreservedRunReport


@dataclass(slots=True)
class _BenchmarkBaseline:
    by_key: dict[tuple[str, str], float | None]
    by_operation: dict[str, float | None]

    def record_first_run(
        self,
        *,
        report_index: int,
        key: tuple[str, str],
        average_latency_ms: float | None,
    ) -> None:
        if report_index != 0:
            return
        self.by_key[key] = average_latency_ms
        self.by_operation.setdefault(key[1], average_latency_ms)

    def average_for(self, key: tuple[str, str]) -> float | None:
        return self.by_key.get(key, self.by_operation.get(key[1]))


@dataclass(slots=True)
class _EvaluationBaseline:
    by_provider: dict[str, float | None]
    average: float | None = None

    def record_first_run(
        self,
        *,
        report_index: int,
        provider: str,
        average_score: float | None,
    ) -> None:
        if report_index != 0:
            return
        self.by_provider[provider] = average_score
        if self.average is None:
            self.average = average_score

    def average_for(self, provider: str) -> float | None:
        return self.by_provider.get(provider, self.average)


def comparison_rows(
    kind: str,
    reports: list[PreservedRunReport],
    contexts: list[JSONDict],
) -> list[JSONDict]:
    """Build stable comparison rows for compatible preserved reports."""

    if kind == "benchmark":
        return _benchmark_rows(reports, contexts)
    if kind == "eval":
        return _evaluation_rows(reports, contexts)
    return _demo_showcase_rows(reports, contexts)


def _benchmark_rows(reports: list[PreservedRunReport], contexts: list[JSONDict]) -> list[JSONDict]:
    baseline = _BenchmarkBaseline(by_key={}, by_operation={})
    return [
        row
        for report_index, (report, context) in enumerate(zip(reports, contexts, strict=True))
        for row in _benchmark_report_rows(
            report,
            context,
            report_index=report_index,
            baseline=baseline,
        )
    ]


def _benchmark_report_rows(
    report: PreservedRunReport,
    context: JSONDict,
    *,
    report_index: int,
    baseline: _BenchmarkBaseline,
) -> list[JSONDict]:
    return [
        _benchmark_result_row(
            report,
            context,
            result,
            report_index=report_index,
            baseline=baseline,
        )
        for result in report.report.get("results", [])
        if isinstance(result, dict)
    ]


def _benchmark_result_row(
    report: PreservedRunReport,
    context: JSONDict,
    result: JSONDict,
    *,
    report_index: int,
    baseline: _BenchmarkBaseline,
) -> JSONDict:
    key = _benchmark_result_key(result)
    average_latency_ms = _optional_float(result.get("average_latency_ms"))
    baseline.record_first_run(
        report_index=report_index,
        key=key,
        average_latency_ms=average_latency_ms,
    )
    event_count = _result_event_count(result)
    return {
        "run_id": report.run_id,
        "provider": key[0],
        "capability": _row_capability(context, fallback=key[1]),
        "operation": key[1],
        "fixture_digest": context["fixture_digest"],
        "suite_version": context["suite_version"],
        "budget_ref": context["budget_ref"],
        "budget_passed": context["budget_passed"],
        "iterations": _int_field(result, "iterations"),
        "success_count": _int_field(result, "success_count"),
        "error_count": _int_field(result, "error_count"),
        "retry_count": _int_field(result, "retry_count"),
        "average_latency_ms": average_latency_ms,
        "delta_average_latency_ms": _numeric_delta(
            average_latency_ms,
            baseline.average_for(key),
        ),
        "p95_latency_ms": _optional_float(result.get("p95_latency_ms")),
        "throughput_per_second": _optional_float(result.get("throughput_per_second")),
        "event_count": _row_event_count(event_count, context),
    }


def _benchmark_result_key(result: JSONDict) -> tuple[str, str]:
    return str(result.get("provider", "")), str(result.get("operation", ""))


def _evaluation_rows(
    reports: list[PreservedRunReport],
    contexts: list[JSONDict],
) -> list[JSONDict]:
    baseline = _EvaluationBaseline(by_provider={})
    return [
        row
        for report_index, (report, context) in enumerate(zip(reports, contexts, strict=True))
        for row in _evaluation_report_rows(
            report,
            context,
            report_index=report_index,
            baseline=baseline,
        )
    ]


def _evaluation_report_rows(
    report: PreservedRunReport,
    context: JSONDict,
    *,
    report_index: int,
    baseline: _EvaluationBaseline,
) -> list[JSONDict]:
    return [
        _evaluation_summary_row(
            report,
            context,
            summary,
            report_index=report_index,
            baseline=baseline,
        )
        for summary in report.report.get("provider_summaries", [])
        if isinstance(summary, dict)
    ]


def _evaluation_summary_row(
    report: PreservedRunReport,
    context: JSONDict,
    summary: JSONDict,
    *,
    report_index: int,
    baseline: _EvaluationBaseline,
) -> JSONDict:
    provider = str(summary.get("provider", ""))
    average_score = _optional_float(summary.get("average_score"))
    baseline.record_first_run(
        report_index=report_index,
        provider=provider,
        average_score=average_score,
    )
    return {
        "run_id": report.run_id,
        "provider": provider,
        "capability": _row_capability(context, fallback=""),
        "suite_id": _evaluation_suite_id(report, context),
        "fixture_digest": context["fixture_digest"],
        "suite_version": context["suite_version"],
        "average_score": average_score,
        "delta_average_score": _numeric_delta(average_score, baseline.average_for(provider)),
        "scenario_count": _int_field(summary, "scenario_count"),
        "passed_scenario_count": _int_field(summary, "passed_scenario_count"),
        "failed_scenario_count": _int_field(summary, "failed_scenario_count"),
        "event_count": int(context["event_count"]),
    }


def _demo_showcase_rows(
    reports: list[PreservedRunReport],
    contexts: list[JSONDict],
) -> list[JSONDict]:
    rows: list[JSONDict] = []
    for report, context in zip(reports, contexts, strict=True):
        rows.append(
            {
                "run_id": report.run_id,
                "provider": str(report.manifest.get("provider", "")),
                "workflow": _demo_workflow(report, context),
                "status": str(report.report.get("status", report.manifest.get("status", ""))),
                "safe_to_attach": bool(
                    report.report.get(
                        "safe_to_attach",
                        _json_object(report.manifest.get("result_summary")).get(
                            "safe_to_attach",
                            False,
                        ),
                    )
                ),
                "summary": str(report.report.get("summary", "")),
                "event_count": int(context["event_count"]),
            }
        )
    return rows


def _numeric_delta(value: float | None, baseline: float | None) -> float | None:
    if value is None or baseline is None:
        return None
    return value - baseline


def _int_field(payload: JSONDict, key: str) -> int:
    return int(payload.get(key, 0) or 0)


def _row_event_count(result_event_count: int, context: JSONDict) -> int:
    if result_event_count:
        return result_event_count
    return int(context["event_count"])


def _row_capability(context: JSONDict, *, fallback: str) -> str:
    capabilities = context.get("capabilities")
    if isinstance(capabilities, list) and capabilities:
        return ",".join(str(capability) for capability in capabilities)
    return fallback


def _evaluation_suite_id(report: PreservedRunReport, context: JSONDict) -> str:
    suite_id = _optional_text(report.report.get("suite_id"))
    if suite_id is not None:
        return suite_id
    operations = context.get("operations")
    if isinstance(operations, list) and operations:
        return str(operations[0])
    return ""


def _demo_workflow(report: PreservedRunReport, context: JSONDict) -> str:
    input_summary = _json_object(report.manifest.get("input_summary"))
    for value in (input_summary.get("workflow"), report.manifest.get("operation")):
        text = _optional_text(value)
        if text:
            return text
    operations = context.get("operations")
    if isinstance(operations, list) and operations:
        return str(operations[0])
    return ""


def _optional_float(value: object) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _optional_text(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    stripped = value.strip()
    return stripped or None


def _json_object(value: object) -> JSONDict:
    return dict(value) if isinstance(value, dict) else {}

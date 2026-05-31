"""Benchmark result and report rendering contracts."""

from __future__ import annotations

import csv
import io
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field

from worldforge.benchmark_budgets import (
    BenchmarkBudget,
    BenchmarkGateReport,
    BenchmarkGateViolation,
)
from worldforge.benchmark_contracts import (
    BENCHMARK_CLAIM_BOUNDARY,
    BENCHMARK_METRIC_SEMANTICS,
    BENCHMARKABLE_OPERATIONS,
    _comma_join_or_dash,
    _format_optional_number,
    _non_negative_number,
    _optional_non_negative_number,
    _required_text,
)
from worldforge.models import (
    JSONDict,
    WorldForgeError,
    dump_json,
    require_json_dict,
    require_non_negative_int,
    require_positive_int,
)
from worldforge.provenance import ProvenanceEnvelope


def _benchmark_provenance_markdown_lines(provenance: ProvenanceEnvelope | None) -> list[str]:
    """Render the report-level provenance section for Markdown artifacts."""

    if provenance is None:
        return []
    return [
        "## Provenance",
        "",
        *_benchmark_provenance_core_lines(provenance),
        *_benchmark_provenance_optional_lines(provenance),
        "",
    ]


def _benchmark_provenance_core_lines(provenance: ProvenanceEnvelope) -> list[str]:
    return [
        f"- WorldForge version: {provenance.worldforge_version}",
        f"- Suite version: {provenance.suite_version}",
        f"- Created at: {provenance.created_at}",
        f"- Providers: {_comma_join_or_dash(provenance.providers)}",
        f"- Capabilities: {_comma_join_or_dash(provenance.capabilities)}",
        f"- Event count: {provenance.event_count}",
        f"- Input digest: {provenance.input_digest or '-'}",
        f"- Result digest: {provenance.result_digest or '-'}",
    ]


def _benchmark_provenance_optional_lines(provenance: ProvenanceEnvelope) -> list[str]:
    return [
        line
        for line in (
            _runtime_manifests_markdown_line(provenance.runtime_manifests),
            _budget_file_markdown_line(provenance.budget_file),
            _command_markdown_line(provenance.command),
            _notes_markdown_line(provenance.notes),
        )
        if line is not None
    ]


def _runtime_manifests_markdown_line(runtime_manifests: Mapping[str, str]) -> str | None:
    if not runtime_manifests:
        return None
    manifests = ", ".join(
        f"{provider}={manifest_id}" for provider, manifest_id in sorted(runtime_manifests.items())
    )
    return f"- Runtime manifests: {manifests}"


def _budget_file_markdown_line(budget_file: JSONDict | None) -> str | None:
    if budget_file is None:
        return None
    return f"- Budget file: {budget_file['path']}"


def _command_markdown_line(command: Sequence[str]) -> str | None:
    if not command:
        return None
    return f"- Command: `{' '.join(command)}`"


def _notes_markdown_line(notes: str | None) -> str | None:
    if not notes:
        return None
    return f"- Notes: {notes}"


@dataclass(slots=True)
class BenchmarkResult:
    """Aggregate result for one provider/operation benchmark case."""

    provider: str
    operation: str
    iterations: int
    concurrency: int
    success_count: int
    error_count: int
    retry_count: int
    total_time_ms: float
    average_latency_ms: float | None
    min_latency_ms: float | None
    max_latency_ms: float | None
    p50_latency_ms: float | None
    p95_latency_ms: float | None
    throughput_per_second: float
    operation_metrics: JSONDict = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.provider = _required_text(self.provider, name="BenchmarkResult provider")
        self.operation = _required_text(self.operation, name="BenchmarkResult operation")
        if self.operation not in BENCHMARKABLE_OPERATIONS:
            known = ", ".join(BENCHMARKABLE_OPERATIONS)
            raise WorldForgeError(f"BenchmarkResult operation must be one of: {known}.")
        self.iterations = require_positive_int(self.iterations, name="BenchmarkResult iterations")
        self.concurrency = require_positive_int(
            self.concurrency,
            name="BenchmarkResult concurrency",
        )
        self.success_count = require_non_negative_int(
            self.success_count,
            name="BenchmarkResult success_count",
        )
        self.error_count = require_non_negative_int(
            self.error_count,
            name="BenchmarkResult error_count",
        )
        if self.success_count + self.error_count != self.iterations:
            raise WorldForgeError(
                "BenchmarkResult success_count and error_count must sum to iterations."
            )
        self.retry_count = require_non_negative_int(
            self.retry_count,
            name="BenchmarkResult retry_count",
        )
        self.total_time_ms = _non_negative_number(
            self.total_time_ms,
            name="BenchmarkResult total_time_ms",
        )
        self.average_latency_ms = _optional_non_negative_number(
            self.average_latency_ms,
            name="BenchmarkResult average_latency_ms",
        )
        self.min_latency_ms = _optional_non_negative_number(
            self.min_latency_ms,
            name="BenchmarkResult min_latency_ms",
        )
        self.max_latency_ms = _optional_non_negative_number(
            self.max_latency_ms,
            name="BenchmarkResult max_latency_ms",
        )
        self.p50_latency_ms = _optional_non_negative_number(
            self.p50_latency_ms,
            name="BenchmarkResult p50_latency_ms",
        )
        self.p95_latency_ms = _optional_non_negative_number(
            self.p95_latency_ms,
            name="BenchmarkResult p95_latency_ms",
        )
        self.throughput_per_second = _non_negative_number(
            self.throughput_per_second,
            name="BenchmarkResult throughput_per_second",
        )
        self.operation_metrics = require_json_dict(
            self.operation_metrics,
            name="BenchmarkResult operation_metrics",
        )
        if not isinstance(self.errors, list) or not all(
            isinstance(error, str) and error for error in self.errors
        ):
            raise WorldForgeError("BenchmarkResult errors must be a list of non-empty strings.")
        if len(self.errors) != self.error_count:
            raise WorldForgeError("BenchmarkResult errors length must match error_count.")
        self.errors = list(self.errors)

    def to_dict(self) -> JSONDict:
        return {
            "provider": self.provider,
            "operation": self.operation,
            "iterations": self.iterations,
            "concurrency": self.concurrency,
            "success_count": self.success_count,
            "error_count": self.error_count,
            "retry_count": self.retry_count,
            "total_time_ms": self.total_time_ms,
            "average_latency_ms": self.average_latency_ms,
            "min_latency_ms": self.min_latency_ms,
            "max_latency_ms": self.max_latency_ms,
            "p50_latency_ms": self.p50_latency_ms,
            "p95_latency_ms": self.p95_latency_ms,
            "throughput_per_second": self.throughput_per_second,
            "operation_metrics": dict(self.operation_metrics),
            "errors": list(self.errors),
        }


def _add_max_violation(
    violations: list[BenchmarkGateViolation],
    *,
    budget: BenchmarkBudget,
    result: BenchmarkResult,
    metric: str,
    observed: float | int | None,
    threshold: float | int | None,
) -> None:
    if threshold is None:
        return
    if observed is None or observed > threshold:
        violations.append(
            BenchmarkGateViolation(
                provider=result.provider,
                operation=result.operation,
                metric=metric,
                observed=observed,
                threshold=threshold,
                condition=f"<= {_format_optional_number(threshold)}",
                budget_selector=budget.selector_label(),
            )
        )


def _add_min_violation(
    violations: list[BenchmarkGateViolation],
    *,
    budget: BenchmarkBudget,
    result: BenchmarkResult,
    metric: str,
    observed: float | int | None,
    threshold: float | int | None,
) -> None:
    if threshold is None:
        return
    if observed is None or observed < threshold:
        violations.append(
            BenchmarkGateViolation(
                provider=result.provider,
                operation=result.operation,
                metric=metric,
                observed=observed,
                threshold=threshold,
                condition=f">= {_format_optional_number(threshold)}",
                budget_selector=budget.selector_label(),
            )
        )


def _evaluate_budget_for_result(
    budget: BenchmarkBudget,
    result: BenchmarkResult,
) -> list[BenchmarkGateViolation]:
    violations: list[BenchmarkGateViolation] = []
    success_rate = result.success_count / result.iterations if result.iterations else None
    _add_min_violation(
        violations,
        budget=budget,
        result=result,
        metric="success_rate",
        observed=success_rate,
        threshold=budget.min_success_rate,
    )
    _add_max_violation(
        violations,
        budget=budget,
        result=result,
        metric="error_count",
        observed=result.error_count,
        threshold=budget.max_error_count,
    )
    _add_max_violation(
        violations,
        budget=budget,
        result=result,
        metric="retry_count",
        observed=result.retry_count,
        threshold=budget.max_retry_count,
    )
    _add_max_violation(
        violations,
        budget=budget,
        result=result,
        metric="average_latency_ms",
        observed=result.average_latency_ms,
        threshold=budget.max_average_latency_ms,
    )
    _add_max_violation(
        violations,
        budget=budget,
        result=result,
        metric="p95_latency_ms",
        observed=result.p95_latency_ms,
        threshold=budget.max_p95_latency_ms,
    )
    _add_min_violation(
        violations,
        budget=budget,
        result=result,
        metric="throughput_per_second",
        observed=result.throughput_per_second,
        threshold=budget.min_throughput_per_second,
    )
    return violations


@dataclass(slots=True)
class BenchmarkReport:
    """Materialized benchmark report with export helpers."""

    results: list[BenchmarkResult]
    run_metadata: JSONDict = field(default_factory=dict)
    provenance: ProvenanceEnvelope | None = None

    def __post_init__(self) -> None:
        self.run_metadata = require_json_dict(
            self.run_metadata,
            name="BenchmarkReport run_metadata",
        )
        if not isinstance(self.results, list) or not all(
            isinstance(result, BenchmarkResult) for result in self.results
        ):
            raise WorldForgeError("BenchmarkReport results must contain only BenchmarkResult.")
        if self.provenance is not None:
            if not isinstance(self.provenance, ProvenanceEnvelope):
                raise WorldForgeError(
                    "BenchmarkReport provenance must be a ProvenanceEnvelope or None."
                )
            if self.provenance.kind != "benchmark":
                raise WorldForgeError("BenchmarkReport provenance must have kind='benchmark'.")

    def to_dict(self) -> JSONDict:
        payload: JSONDict = {
            "claim_boundary": BENCHMARK_CLAIM_BOUNDARY,
            "metric_semantics": BENCHMARK_METRIC_SEMANTICS,
            "run_metadata": dict(self.run_metadata),
            "results": [result.to_dict() for result in self.results],
        }
        if self.provenance is not None:
            payload["provenance"] = self.provenance.to_dict()
        return payload

    def to_json(self) -> str:
        return dump_json(self.to_dict())

    def to_markdown(self) -> str:
        lines = [
            "# Benchmark Report",
            "",
            f"Claim boundary: {BENCHMARK_CLAIM_BOUNDARY}",
            f"Metric semantics: {BENCHMARK_METRIC_SEMANTICS}",
            "",
        ]
        lines.extend(_benchmark_provenance_markdown_lines(self.provenance))
        lines.extend(
            [
                "| provider | operation | ok | retries | avg_ms | p95_ms | throughput/s |",
                "| --- | --- | ---: | ---: | ---: | ---: | ---: |",
            ]
        )
        lines.extend(
            (
                f"| {result.provider} | {result.operation} | "
                f"{result.success_count}/{result.iterations} | {result.retry_count} | "
                f"{(result.average_latency_ms or 0.0):.2f} | "
                f"{(result.p95_latency_ms or 0.0):.2f} | "
                f"{result.throughput_per_second:.2f} |"
            )
            for result in self.results
        )
        return "\n".join(lines)

    def to_csv(self) -> str:
        buffer = io.StringIO()
        writer = csv.DictWriter(
            buffer,
            fieldnames=[
                "provider",
                "operation",
                "iterations",
                "concurrency",
                "success_count",
                "error_count",
                "retry_count",
                "total_time_ms",
                "average_latency_ms",
                "min_latency_ms",
                "max_latency_ms",
                "p50_latency_ms",
                "p95_latency_ms",
                "throughput_per_second",
                "operation_metrics_json",
                "errors_json",
            ],
        )
        writer.writeheader()
        for result in self.results:
            writer.writerow(
                {
                    "provider": result.provider,
                    "operation": result.operation,
                    "iterations": result.iterations,
                    "concurrency": result.concurrency,
                    "success_count": result.success_count,
                    "error_count": result.error_count,
                    "retry_count": result.retry_count,
                    "total_time_ms": f"{result.total_time_ms:.4f}",
                    "average_latency_ms": (
                        f"{result.average_latency_ms:.4f}"
                        if result.average_latency_ms is not None
                        else ""
                    ),
                    "min_latency_ms": (
                        f"{result.min_latency_ms:.4f}" if result.min_latency_ms is not None else ""
                    ),
                    "max_latency_ms": (
                        f"{result.max_latency_ms:.4f}" if result.max_latency_ms is not None else ""
                    ),
                    "p50_latency_ms": (
                        f"{result.p50_latency_ms:.4f}" if result.p50_latency_ms is not None else ""
                    ),
                    "p95_latency_ms": (
                        f"{result.p95_latency_ms:.4f}" if result.p95_latency_ms is not None else ""
                    ),
                    "throughput_per_second": f"{result.throughput_per_second:.4f}",
                    "operation_metrics_json": dump_json(result.operation_metrics),
                    "errors_json": dump_json(result.errors),
                }
            )
        return buffer.getvalue().strip()

    def to_html(self) -> str:
        from worldforge.html_report import render_benchmark_html

        return render_benchmark_html(self)

    def artifacts(self) -> dict[str, str]:
        return {
            "json": self.to_json(),
            "markdown": self.to_markdown(),
            "csv": self.to_csv(),
            "html": self.to_html(),
        }

    def evaluate_budgets(
        self,
        budgets: Sequence[BenchmarkBudget],
    ) -> BenchmarkGateReport:
        """Evaluate release or claim budgets against materialized benchmark results."""

        if not budgets:
            raise WorldForgeError("evaluate_budgets() requires at least one BenchmarkBudget.")

        violations: list[BenchmarkGateViolation] = []
        checked_result_count = 0
        for budget in budgets:
            if not isinstance(budget, BenchmarkBudget):
                raise WorldForgeError("evaluate_budgets() accepts only BenchmarkBudget entries.")
            matched_results = [result for result in self.results if budget.matches(result)]
            if not matched_results:
                violations.append(
                    BenchmarkGateViolation(
                        provider=budget.provider or "*",
                        operation=budget.operation or "*",
                        metric="matching_results",
                        observed=0,
                        threshold=1,
                        condition=">= 1 matching result",
                        budget_selector=budget.selector_label(),
                    )
                )
                continue

            checked_result_count += len(matched_results)
            for result in matched_results:
                violations.extend(_evaluate_budget_for_result(budget, result))

        return BenchmarkGateReport(
            budgets=list(budgets),
            checked_result_count=checked_result_count,
            violations=violations,
        )

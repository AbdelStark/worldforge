"""Benchmark budget gate contracts."""

from __future__ import annotations

import csv
import io
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from worldforge.benchmark_contracts import (
    BENCHMARKABLE_OPERATIONS,
    _format_optional_number,
    _non_empty_optional_text,
    _optional_non_negative_int,
    _optional_non_negative_number,
    _reject_unknown_keys,
)
from worldforge.models import JSONDict, WorldForgeError, dump_json, require_probability

if TYPE_CHECKING:
    from worldforge.benchmark_reports import BenchmarkResult


_BENCHMARK_BUDGET_KEYS = {
    "provider",
    "operation",
    "min_success_rate",
    "max_error_count",
    "max_retry_count",
    "max_average_latency_ms",
    "max_p95_latency_ms",
    "min_throughput_per_second",
}
_BENCHMARK_BUDGET_WRAPPER_KEYS = {"budgets", "metadata"}
_BENCHMARK_BUDGET_THRESHOLD_FIELDS = (
    "min_success_rate",
    "max_error_count",
    "max_retry_count",
    "max_average_latency_ms",
    "max_p95_latency_ms",
    "min_throughput_per_second",
)


def _optional_probability(value: object, *, name: str) -> float | None:
    if value is None:
        return None
    return require_probability(value, name=name)


def _benchmark_budget_operation(value: object) -> str | None:
    operation = _non_empty_optional_text(value, name="BenchmarkBudget operation")
    if operation is not None and operation not in BENCHMARKABLE_OPERATIONS:
        known = ", ".join(BENCHMARKABLE_OPERATIONS)
        raise WorldForgeError(f"BenchmarkBudget operation must be one of: {known}.")
    return operation


def _benchmark_budget_threshold_validators() -> tuple[tuple[str, Callable[[object], object]], ...]:
    return (
        (
            "min_success_rate",
            lambda value: _optional_probability(value, name="BenchmarkBudget min_success_rate"),
        ),
        (
            "max_error_count",
            lambda value: _optional_non_negative_int(
                value,
                name="BenchmarkBudget max_error_count",
            ),
        ),
        (
            "max_retry_count",
            lambda value: _optional_non_negative_int(
                value,
                name="BenchmarkBudget max_retry_count",
            ),
        ),
        (
            "max_average_latency_ms",
            lambda value: _optional_non_negative_number(
                value,
                name="BenchmarkBudget max_average_latency_ms",
            ),
        ),
        (
            "max_p95_latency_ms",
            lambda value: _optional_non_negative_number(
                value,
                name="BenchmarkBudget max_p95_latency_ms",
            ),
        ),
        (
            "min_throughput_per_second",
            lambda value: _optional_non_negative_number(
                value,
                name="BenchmarkBudget min_throughput_per_second",
            ),
        ),
    )


def _set_frozen_field(instance: object, field_name: str, value: object) -> None:
    object.__setattr__(instance, field_name, value)


def _validate_benchmark_budget_thresholds(budget: object) -> None:
    if any(
        getattr(budget, field_name) is not None for field_name in _BENCHMARK_BUDGET_THRESHOLD_FIELDS
    ):
        return
    raise WorldForgeError("BenchmarkBudget requires at least one threshold.")


@dataclass(slots=True, frozen=True)
class BenchmarkBudget:
    """Thresholds for release or claim-oriented benchmark gates.

    ``provider`` and ``operation`` are optional selectors. When either selector is omitted, the
    budget applies to every matching result on that dimension.
    """

    provider: str | None = None
    operation: str | None = None
    min_success_rate: float | None = None
    max_error_count: int | None = None
    max_retry_count: int | None = None
    max_average_latency_ms: float | None = None
    max_p95_latency_ms: float | None = None
    min_throughput_per_second: float | None = None

    def __post_init__(self) -> None:
        _set_frozen_field(
            self,
            "provider",
            _non_empty_optional_text(self.provider, name="BenchmarkBudget provider"),
        )
        _set_frozen_field(self, "operation", _benchmark_budget_operation(self.operation))
        for field_name, validator in _benchmark_budget_threshold_validators():
            _set_frozen_field(self, field_name, validator(getattr(self, field_name)))
        _validate_benchmark_budget_thresholds(self)

    @classmethod
    def from_dict(cls, payload: JSONDict) -> BenchmarkBudget:
        if not isinstance(payload, dict):
            raise WorldForgeError("Benchmark budget entries must be JSON objects.")
        _reject_unknown_keys(
            payload,
            allowed=_BENCHMARK_BUDGET_KEYS,
            name="Benchmark budget entry",
        )
        return cls(
            provider=payload.get("provider"),
            operation=payload.get("operation"),
            min_success_rate=payload.get("min_success_rate"),
            max_error_count=payload.get("max_error_count"),
            max_retry_count=payload.get("max_retry_count"),
            max_average_latency_ms=payload.get("max_average_latency_ms"),
            max_p95_latency_ms=payload.get("max_p95_latency_ms"),
            min_throughput_per_second=payload.get("min_throughput_per_second"),
        )

    def matches(self, result: BenchmarkResult) -> bool:
        provider_matches = self.provider is None or self.provider == result.provider
        operation_matches = self.operation is None or self.operation == result.operation
        return provider_matches and operation_matches

    def selector_label(self) -> str:
        provider = self.provider or "*"
        operation = self.operation or "*"
        return f"{provider}/{operation}"

    def to_dict(self) -> JSONDict:
        return {
            "provider": self.provider,
            "operation": self.operation,
            "min_success_rate": self.min_success_rate,
            "max_error_count": self.max_error_count,
            "max_retry_count": self.max_retry_count,
            "max_average_latency_ms": self.max_average_latency_ms,
            "max_p95_latency_ms": self.max_p95_latency_ms,
            "min_throughput_per_second": self.min_throughput_per_second,
        }


@dataclass(slots=True, frozen=True)
class BenchmarkGateViolation:
    """One failed benchmark budget check."""

    provider: str
    operation: str
    metric: str
    observed: float | int | None
    threshold: float | int
    condition: str
    budget_selector: str

    def to_dict(self) -> JSONDict:
        return {
            "provider": self.provider,
            "operation": self.operation,
            "metric": self.metric,
            "observed": self.observed,
            "threshold": self.threshold,
            "condition": self.condition,
            "budget_selector": self.budget_selector,
        }


@dataclass(slots=True)
class BenchmarkGateReport:
    """Budget evaluation report for a benchmark run."""

    budgets: list[BenchmarkBudget]
    checked_result_count: int
    violations: list[BenchmarkGateViolation] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return not self.violations

    @property
    def violation_count(self) -> int:
        return len(self.violations)

    def to_dict(self) -> JSONDict:
        return {
            "passed": self.passed,
            "budget_count": len(self.budgets),
            "checked_result_count": self.checked_result_count,
            "violation_count": self.violation_count,
            "budgets": [budget.to_dict() for budget in self.budgets],
            "violations": [violation.to_dict() for violation in self.violations],
        }

    def to_json(self) -> str:
        return dump_json(self.to_dict())

    def to_markdown(self) -> str:
        status = "passed" if self.passed else "failed"
        lines = [
            "# Benchmark Gate Report",
            "",
            f"Status: {status}",
            f"Budgets: {len(self.budgets)}",
            f"Checked results: {self.checked_result_count}",
            f"Violations: {self.violation_count}",
        ]
        if self.violations:
            lines.extend(
                [
                    "",
                    "| provider | operation | metric | observed | threshold | condition | budget |",
                    "| --- | --- | --- | ---: | ---: | --- | --- |",
                ]
            )
            lines.extend(
                (
                    "| "
                    f"{violation.provider} | "
                    f"{violation.operation} | "
                    f"{violation.metric} | "
                    f"{_format_optional_number(violation.observed)} | "
                    f"{_format_optional_number(violation.threshold)} | "
                    f"{violation.condition} | "
                    f"{violation.budget_selector} |"
                )
                for violation in self.violations
            )
        return "\n".join(lines)

    def to_csv(self) -> str:
        buffer = io.StringIO()
        writer = csv.DictWriter(
            buffer,
            fieldnames=[
                "provider",
                "operation",
                "metric",
                "observed",
                "threshold",
                "condition",
                "budget_selector",
            ],
        )
        writer.writeheader()
        for violation in self.violations:
            writer.writerow(
                {
                    "provider": violation.provider,
                    "operation": violation.operation,
                    "metric": violation.metric,
                    "observed": _format_optional_number(violation.observed),
                    "threshold": _format_optional_number(violation.threshold),
                    "condition": violation.condition,
                    "budget_selector": violation.budget_selector,
                }
            )
        return buffer.getvalue().strip()


def load_benchmark_budgets(payload: object) -> list[BenchmarkBudget]:
    """Parse benchmark budget JSON from a list or ``{"budgets": [...]}`` object.

    Each entry's ``provider`` and ``operation`` fields are optional: omit them to apply the
    budget's thresholds as a wildcard across every provider/operation pair in the run. Raises
    :class:`WorldForgeError` if the payload is empty, the wrapper carries unknown keys, or any
    individual budget entry fails validation.
    """

    budget_entries = payload
    if isinstance(payload, dict):
        _reject_unknown_keys(
            payload,
            allowed=_BENCHMARK_BUDGET_WRAPPER_KEYS,
            name="Benchmark budget payload",
        )
        budget_entries = payload.get("budgets")
    if not isinstance(budget_entries, list) or not budget_entries:
        raise WorldForgeError(
            "Benchmark budget payload must be a non-empty list or an object with a non-empty "
            "'budgets' list."
        )
    return [BenchmarkBudget.from_dict(entry) for entry in budget_entries]

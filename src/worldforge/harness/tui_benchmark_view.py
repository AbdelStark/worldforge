"""Textual-free benchmark sample view helpers for TheWorldHarness."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from statistics import median

from worldforge.harness.tui_log_view import RichLogSpec
from worldforge.harness.tui_report_view import ReportCompletionSpec, ReportRunControlSpec

DEFAULT_BENCHMARK_ITERATIONS = 5
BENCHMARK_P95_QUANTILE = 0.95
BENCHMARK_ITERATIONS_ERROR = "Iterations must be an integer."


@dataclass(frozen=True, slots=True)
class BenchmarkSelectSpec:
    widget_id: str
    label: str
    default: str | None = None


@dataclass(frozen=True, slots=True)
class BenchmarkInputSpec:
    widget_id: str
    label: str
    default: str


@dataclass(frozen=True, slots=True)
class BenchmarkButtonSpec:
    widget_id: str
    label: str
    variant: str


@dataclass(frozen=True, slots=True)
class BenchmarkBindingSpec:
    key: str
    action: str
    description: str
    show: bool = True


@dataclass(frozen=True, slots=True)
class BenchmarkOutputSpec:
    widget_id: str
    empty_message: str


@dataclass(frozen=True, slots=True)
class BenchmarkScreenSpec:
    root_id: str
    form_id: str
    output_id: str
    provider: BenchmarkSelectSpec
    operation: BenchmarkSelectSpec
    iterations: BenchmarkInputSpec
    run: BenchmarkButtonSpec
    stats: BenchmarkOutputSpec
    progress_id: str
    log: RichLogSpec
    completion: ReportCompletionSpec
    run_control: ReportRunControlSpec


@dataclass(frozen=True, slots=True)
class BenchmarkSampleProgress:
    samples: tuple[float, ...]
    latency_ms: float
    progress_count: int
    log_line: str
    stats_line: str


@dataclass(frozen=True, slots=True)
class BenchmarkRunRequest:
    provider: str
    operation: str
    iterations: int


@dataclass(frozen=True, slots=True)
class BenchmarkRunValidation:
    request: BenchmarkRunRequest | None = None
    error: str | None = None


BENCHMARK_SCREEN_SPEC = BenchmarkScreenSpec(
    root_id="benchmark-root",
    form_id="benchmark-form",
    output_id="benchmark-output",
    provider=BenchmarkSelectSpec("benchmark-provider", "Provider"),
    operation=BenchmarkSelectSpec("benchmark-operation", "Operation", "predict"),
    iterations=BenchmarkInputSpec(
        "benchmark-iterations",
        "Iterations",
        str(DEFAULT_BENCHMARK_ITERATIONS),
    ),
    run=BenchmarkButtonSpec("benchmark-run", "Run benchmark", "primary"),
    stats=BenchmarkOutputSpec("benchmark-stats", "No benchmark run yet — press r to execute."),
    progress_id="benchmark-progress",
    log=RichLogSpec("benchmark-log"),
    completion=ReportCompletionSpec(
        kind="benchmark",
        export_widget_id="benchmark-export",
        status_widget_id="benchmark-stats",
    ),
    run_control=ReportRunControlSpec(
        worker_group="benchmark",
        worker_name="benchmark.run",
        notify_title="Benchmark",
        cancel_message="Cancelled benchmark run.",
        mismatch_title="Benchmark",
    ),
)
BENCHMARK_BINDING_SPECS: tuple[BenchmarkBindingSpec, ...] = (
    BenchmarkBindingSpec("r", "run_benchmark", "Run"),
    BenchmarkBindingSpec("escape", "cancel_or_back", "Cancel/Back"),
)
BENCHMARK_RUN_BUTTON_ID = BENCHMARK_SCREEN_SPEC.run.widget_id
BENCHMARK_LOG_SELECTOR = BENCHMARK_SCREEN_SPEC.log.selector


def benchmark_request_from_form(
    *,
    provider_value: object,
    operation_value: object,
    iterations_value: str | None,
) -> BenchmarkRunValidation:
    """Return a benchmark run request or a user-facing validation error."""

    try:
        iterations = int(iterations_value or str(DEFAULT_BENCHMARK_ITERATIONS))
    except ValueError:
        return BenchmarkRunValidation(error=BENCHMARK_ITERATIONS_ERROR)
    if not isinstance(provider_value, str) or not isinstance(operation_value, str):
        return BenchmarkRunValidation()
    return BenchmarkRunValidation(
        request=BenchmarkRunRequest(
            provider=provider_value,
            operation=operation_value,
            iterations=iterations,
        )
    )


def benchmark_sample_progress(
    sample: Mapping[str, object],
    previous_samples: Sequence[float],
    *,
    total: int,
) -> BenchmarkSampleProgress:
    """Return the accumulated benchmark-sample view state for one TUI row."""

    latency_ms = float(sample.get("latency_ms") or 0.0)
    samples = (*tuple(previous_samples), latency_ms)
    return BenchmarkSampleProgress(
        samples=samples,
        latency_ms=latency_ms,
        progress_count=min(len(samples), total),
        log_line=benchmark_sample_log_line(sample, latency_ms=latency_ms),
        stats_line=benchmark_sample_stats_line(samples, total=total),
    )


def benchmark_sample_log_line(sample: Mapping[str, object], *, latency_ms: float) -> str:
    return (
        f"{sample.get('provider')}.{sample.get('operation')} "
        f"#{sample.get('iteration')} {latency_ms:.2f} ms"
    )


def benchmark_sample_stats_line(samples: Sequence[float], *, total: int) -> str:
    if not samples:
        return f"Samples: 0/{total}  median=0.00 ms  p95=0.00 ms"
    sorted_samples = sorted(samples)
    p95 = sorted_samples[_percentile_index(len(sorted_samples), BENCHMARK_P95_QUANTILE)]
    return f"Samples: {len(samples)}/{total}  median={median(samples):.2f} ms  p95={p95:.2f} ms"


def _percentile_index(sample_count: int, quantile: float) -> int:
    return max(0, int((sample_count - 1) * quantile))

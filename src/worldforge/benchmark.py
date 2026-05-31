"""Capability-aware provider benchmark harness."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from concurrent.futures import ThreadPoolExecutor, as_completed
from contextlib import contextmanager
from dataclasses import dataclass
from time import perf_counter
from typing import Protocol

from worldforge.benchmark_budgets import (
    BenchmarkBudget,
    BenchmarkGateReport,
    BenchmarkGateViolation,
    load_benchmark_budgets,
)
from worldforge.benchmark_contracts import (
    BENCHMARK_CLAIM_BOUNDARY,
    BENCHMARK_METRIC_SEMANTICS,
    BENCHMARKABLE_OPERATIONS,
)
from worldforge.benchmark_inputs import BenchmarkInputs, load_benchmark_inputs
from worldforge.benchmark_reports import BenchmarkReport, BenchmarkResult
from worldforge.framework import WorldForge
from worldforge.models import (
    BBox,
    JSONDict,
    Position,
    SceneObject,
    WorldForgeError,
    require_positive_int,
)
from worldforge.observability import ProviderMetricsSink, compose_event_handlers
from worldforge.provenance import (
    BENCHMARK_SUITE_CONTRACT_VERSION,
    ProvenanceEnvelope,
    collect_runtime_manifests,
    digest_payload,
)
from worldforge.providers.base import ProviderError

type _EventHandler = Callable[..., None] | None


class _EventHandlerTarget(Protocol):
    event_handler: _EventHandler


def _percentile(values: Sequence[float], quantile: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    index = quantile * (len(ordered) - 1)
    lower = int(index)
    upper = min(len(ordered) - 1, lower + 1)
    weight = index - lower
    return ordered[lower] + ((ordered[upper] - ordered[lower]) * weight)


@dataclass(slots=True)
class _BenchmarkSample:
    latency_ms: float
    error: str | None = None

    @property
    def succeeded(self) -> bool:
        return self.error is None

    def to_dict(self) -> JSONDict:
        return {
            "latency_ms": self.latency_ms,
            "error": self.error,
            "succeeded": self.succeeded,
        }


@dataclass(slots=True, frozen=True)
class _MetricCaptureState:
    provider_instance: _EventHandlerTarget | None
    capability_wrappers: tuple[_EventHandlerTarget, ...]
    original_provider_handler: _EventHandler
    original_capability_handlers: tuple[_EventHandler, ...]


def _compose_metric_handler(
    original_handler: _EventHandler,
    metrics: ProviderMetricsSink,
) -> _EventHandler:
    return compose_event_handlers(original_handler, metrics)


def _install_metric_capture_handlers(
    *,
    provider_instance: _EventHandlerTarget | None,
    capability_wrappers: tuple[_EventHandlerTarget, ...],
    metrics: ProviderMetricsSink,
) -> _MetricCaptureState:
    state = _MetricCaptureState(
        provider_instance=provider_instance,
        capability_wrappers=capability_wrappers,
        original_provider_handler=(
            provider_instance.event_handler if provider_instance is not None else None
        ),
        original_capability_handlers=tuple(
            wrapper.event_handler for wrapper in capability_wrappers
        ),
    )
    if provider_instance is not None:
        provider_instance.event_handler = _compose_metric_handler(
            state.original_provider_handler,
            metrics,
        )
    for wrapper, original_handler in zip(
        capability_wrappers,
        state.original_capability_handlers,
        strict=True,
    ):
        wrapper.event_handler = _compose_metric_handler(original_handler, metrics)
    return state


def _restore_metric_capture_handlers(state: _MetricCaptureState) -> None:
    if state.provider_instance is not None:
        state.provider_instance.event_handler = state.original_provider_handler
    for wrapper, original_handler in zip(
        state.capability_wrappers,
        state.original_capability_handlers,
        strict=True,
    ):
        wrapper.event_handler = original_handler


def _elapsed_ms(started: float) -> float:
    return max(0.1, (perf_counter() - started) * 1000)


def _benchmark_sample_payload(
    *,
    provider: str,
    operation: str,
    iteration: int,
    sample: _BenchmarkSample,
) -> JSONDict:
    return {
        "provider": provider,
        "operation": operation,
        "iteration": iteration,
        **sample.to_dict(),
    }


def _emit_benchmark_sample(
    callback: Callable[[JSONDict], None] | None,
    *,
    provider: str,
    operation: str,
    iteration: int,
    sample: _BenchmarkSample,
) -> None:
    if callback is None:
        return
    callback(
        _benchmark_sample_payload(
            provider=provider,
            operation=operation,
            iteration=iteration,
            sample=sample,
        )
    )


def _benchmark_provider_metrics(metrics: ProviderMetricsSink, provider: str) -> list[JSONDict]:
    return [metric.to_dict() for metric in metrics.snapshot() if metric.provider == provider]


def _benchmark_successful_latencies(samples: Sequence[_BenchmarkSample]) -> list[float]:
    return [sample.latency_ms for sample in samples if sample.succeeded]


def _benchmark_errors(samples: Sequence[_BenchmarkSample]) -> list[str]:
    return [sample.error for sample in samples if sample.error is not None]


def _benchmark_retry_count(provider_metrics: Sequence[JSONDict]) -> int:
    return sum(int(metric["retry_count"]) for metric in provider_metrics)


def _benchmark_throughput(*, success_count: int, total_time_ms: float) -> float:
    total_seconds = total_time_ms / 1000
    if total_seconds <= 0:
        return 0.0
    return success_count / total_seconds


def _average_latency(latencies: Sequence[float]) -> float | None:
    if not latencies:
        return None
    return sum(latencies) / len(latencies)


def _min_latency(latencies: Sequence[float]) -> float | None:
    if not latencies:
        return None
    return min(latencies)


def _max_latency(latencies: Sequence[float]) -> float | None:
    if not latencies:
        return None
    return max(latencies)


def _benchmark_result_from_samples(
    *,
    provider: str,
    operation: str,
    iterations: int,
    concurrency: int,
    samples: Sequence[_BenchmarkSample],
    provider_metrics: Sequence[JSONDict],
    total_time_ms: float,
) -> BenchmarkResult:
    successful_latencies = _benchmark_successful_latencies(samples)
    errors = _benchmark_errors(samples)
    return BenchmarkResult(
        provider=provider,
        operation=operation,
        iterations=iterations,
        concurrency=concurrency,
        success_count=len(successful_latencies),
        error_count=len(errors),
        retry_count=_benchmark_retry_count(provider_metrics),
        total_time_ms=total_time_ms,
        average_latency_ms=_average_latency(successful_latencies),
        min_latency_ms=_min_latency(successful_latencies),
        max_latency_ms=_max_latency(successful_latencies),
        p50_latency_ms=_percentile(successful_latencies, 0.50),
        p95_latency_ms=_percentile(successful_latencies, 0.95),
        throughput_per_second=_benchmark_throughput(
            success_count=len(successful_latencies),
            total_time_ms=total_time_ms,
        ),
        operation_metrics={
            "provider": provider,
            "operation": operation,
            "events": list(provider_metrics),
        },
        errors=errors,
    )


class ProviderBenchmarkHarness:
    """Run latency, retry, and throughput benchmarks across registered providers."""

    benchmarkable_operations = BENCHMARKABLE_OPERATIONS

    def __init__(self, forge: WorldForge | None = None) -> None:
        self._forge = forge or WorldForge()
        self._operation_handlers: dict[str, Callable[[str, BenchmarkInputs], None]] = {
            "predict": self._op_predict,
            "embed": self._op_embed,
            "score": self._op_score,
            "policy": self._op_policy,
        }

    def supported_operations(self, provider: str) -> list[str]:
        profile = self._forge.provider_profile(provider)
        return [
            operation
            for operation in self.benchmarkable_operations
            if profile.capabilities.supports(operation)
        ]

    def _seed_world(self, provider: str) -> tuple[object, object]:
        world = self._forge.create_world("benchmark-world", provider)
        cube = world.add_object(
            SceneObject(
                "cube",
                Position(0.0, 0.5, 0.0),
                BBox(Position(-0.05, 0.45, -0.05), Position(0.05, 0.55, 0.05)),
                is_graspable=True,
            )
        )
        mug = world.add_object(
            SceneObject(
                "mug",
                Position(0.25, 0.8, 0.0),
                BBox(Position(0.2, 0.75, -0.05), Position(0.3, 0.85, 0.05)),
                is_graspable=True,
            )
        )
        return world, (cube, mug)

    def _op_predict(self, provider: str, inputs: BenchmarkInputs) -> None:
        world, _ = self._seed_world(provider)
        world.predict(
            inputs.prediction_action,
            steps=inputs.prediction_steps,
            provider=provider,
        )

    def _op_embed(self, provider: str, inputs: BenchmarkInputs) -> None:
        self._forge.embed(provider, text=inputs.embedding_text)

    def _op_score(self, provider: str, inputs: BenchmarkInputs) -> None:
        self._forge.score_actions(
            provider,
            info=inputs.score_info,
            action_candidates=inputs.score_action_candidates,
        )

    def _op_policy(self, provider: str, inputs: BenchmarkInputs) -> None:
        self._forge.select_actions(provider, info=inputs.policy_info)

    def _invoke_operation(
        self,
        provider: str,
        operation: str,
        inputs: BenchmarkInputs,
    ) -> None:
        handler = self._operation_handlers.get(operation)
        if handler is None:
            raise WorldForgeError(
                f"Unknown benchmark operation '{operation}'. "
                f"Known operations: {', '.join(self.benchmarkable_operations)}."
            )
        handler(provider, inputs)

    def _sample_once(
        self,
        provider: str,
        operation: str,
        inputs: BenchmarkInputs,
    ) -> _BenchmarkSample:
        started = perf_counter()
        try:
            self._invoke_operation(provider, operation, inputs)
        except (ProviderError, WorldForgeError, TimeoutError) as exc:
            return _BenchmarkSample(latency_ms=_elapsed_ms(started), error=str(exc))
        return _BenchmarkSample(latency_ms=_elapsed_ms(started))

    def _metric_capture_state(
        self,
        provider: str,
        metrics: ProviderMetricsSink,
    ) -> _MetricCaptureState:
        provider_instance = self._forge._providers.get(provider)
        capability_wrappers = self._forge._capability_wrappers_for_name(provider)
        if provider_instance is None and not capability_wrappers:
            raise ProviderError(f"Provider '{provider}' is not registered.")
        return _install_metric_capture_handlers(
            provider_instance=provider_instance,
            capability_wrappers=capability_wrappers,
            metrics=metrics,
        )

    @contextmanager
    def _capture_metrics(self, provider: str):
        metrics = ProviderMetricsSink()
        state = self._metric_capture_state(provider, metrics)
        try:
            yield metrics
        finally:
            _restore_metric_capture_handlers(state)

    def _collect_operation_samples(
        self,
        provider: str,
        operation: str,
        *,
        iterations: int,
        concurrency: int,
        inputs: BenchmarkInputs,
        on_sample: Callable[[JSONDict], None] | None,
    ) -> list[_BenchmarkSample]:
        samples: list[_BenchmarkSample] = []
        with ThreadPoolExecutor(max_workers=concurrency) as executor:
            futures = [
                executor.submit(self._sample_once, provider, operation, inputs)
                for _ in range(iterations)
            ]
            for iteration, future in enumerate(as_completed(futures), start=1):
                sample = future.result()
                samples.append(sample)
                _emit_benchmark_sample(
                    on_sample,
                    provider=provider,
                    operation=operation,
                    iteration=iteration,
                    sample=sample,
                )
        return samples

    def _run_operation(
        self,
        provider: str,
        operation: str,
        *,
        iterations: int,
        concurrency: int,
        inputs: BenchmarkInputs,
        on_sample: Callable[[JSONDict], None] | None = None,
    ) -> BenchmarkResult:
        started = perf_counter()
        with self._capture_metrics(provider) as metrics:
            samples = self._collect_operation_samples(
                provider,
                operation,
                iterations=iterations,
                concurrency=concurrency,
                inputs=inputs,
                on_sample=on_sample,
            )
            provider_metrics = _benchmark_provider_metrics(metrics, provider)
        return _benchmark_result_from_samples(
            provider=provider,
            operation=operation,
            iterations=iterations,
            concurrency=concurrency,
            samples=samples,
            provider_metrics=provider_metrics,
            total_time_ms=_elapsed_ms(started),
        )

    def _benchmark_provider_names(self, providers: str | Sequence[str]) -> list[str]:
        provider_names = [providers] if isinstance(providers, str) else list(providers)
        if not provider_names:
            raise WorldForgeError("Benchmark run requires at least one provider.")
        return provider_names

    def _requested_operations(self, operations: Sequence[str] | None) -> list[str]:
        requested_operations = list(dict.fromkeys(operations or self.benchmarkable_operations))
        unknown_operations = [
            operation
            for operation in requested_operations
            if operation not in self.benchmarkable_operations
        ]
        if unknown_operations:
            joined = ", ".join(unknown_operations)
            raise WorldForgeError(
                f"Unknown benchmark operations: {joined}. "
                f"Known operations: {', '.join(self.benchmarkable_operations)}."
            )
        return requested_operations

    def _provider_operation_plan(
        self,
        provider: str,
        *,
        requested_operations: Sequence[str],
        explicit_operations: bool,
    ) -> tuple[str, list[str]]:
        if provider not in self._forge.providers():
            raise ProviderError(f"Provider '{provider}' is not registered.")
        supported = self.supported_operations(provider)
        selected_operations = list(requested_operations) if explicit_operations else supported
        unsupported = [operation for operation in selected_operations if operation not in supported]
        if unsupported:
            joined = ", ".join(unsupported)
            raise WorldForgeError(
                f"Provider '{provider}' cannot benchmark unsupported operations: {joined}."
            )
        if not selected_operations:
            raise WorldForgeError(
                f"Provider '{provider}' does not expose benchmarkable operations."
            )
        return provider, selected_operations

    def _provider_benchmark_plan(
        self,
        provider_names: Sequence[str],
        *,
        requested_operations: Sequence[str],
        explicit_operations: bool,
    ) -> list[tuple[str, list[str]]]:
        return [
            self._provider_operation_plan(
                provider,
                requested_operations=requested_operations,
                explicit_operations=explicit_operations,
            )
            for provider in provider_names
        ]

    @staticmethod
    def _selected_operations_by_provider(
        provider_plan: Sequence[tuple[str, Sequence[str]]],
    ) -> dict[str, list[str]]:
        return {
            provider: list(selected_operations) for provider, selected_operations in provider_plan
        }

    def _run_provider_operations(
        self,
        entry: tuple[str, list[str]],
        *,
        iterations: int,
        concurrency: int,
        inputs: BenchmarkInputs,
        on_sample: Callable[[JSONDict], None] | None,
    ) -> list[BenchmarkResult]:
        provider, selected_operations = entry
        return [
            self._run_operation(
                provider,
                operation,
                iterations=iterations,
                concurrency=concurrency,
                inputs=inputs,
                on_sample=on_sample,
            )
            for operation in selected_operations
        ]

    def _run_provider_plan(
        self,
        provider_plan: Sequence[tuple[str, list[str]]],
        *,
        iterations: int,
        concurrency: int,
        inputs: BenchmarkInputs,
        on_sample: Callable[[JSONDict], None] | None,
    ) -> list[BenchmarkResult]:
        if len(provider_plan) <= 1:
            return [
                result
                for entry in provider_plan
                for result in self._run_provider_operations(
                    entry,
                    iterations=iterations,
                    concurrency=concurrency,
                    inputs=inputs,
                    on_sample=on_sample,
                )
            ]
        with ThreadPoolExecutor(max_workers=min(8, len(provider_plan))) as pool:
            mapped_results = pool.map(
                lambda entry: self._run_provider_operations(
                    entry,
                    iterations=iterations,
                    concurrency=concurrency,
                    inputs=inputs,
                    on_sample=on_sample,
                ),
                provider_plan,
            )
            return [result for provider_results in mapped_results for result in provider_results]

    @staticmethod
    def _benchmark_capabilities(
        selected_operations_by_provider: dict[str, list[str]],
    ) -> list[str]:
        return sorted(
            {
                operation
                for selected_operations in selected_operations_by_provider.values()
                for operation in selected_operations
            }
        )

    @staticmethod
    def _benchmark_event_count(results: Sequence[BenchmarkResult]) -> int:
        return sum(
            int(event.get("request_count", 0))
            for result in results
            for event in result.operation_metrics.get("events", [])
            if isinstance(event, dict)
        )

    def _benchmark_provenance(
        self,
        *,
        provider_names: Sequence[str],
        selected_operations_by_provider: dict[str, list[str]],
        benchmark_inputs: BenchmarkInputs,
        results: Sequence[BenchmarkResult],
    ) -> ProvenanceEnvelope:
        return ProvenanceEnvelope(
            kind="benchmark",
            suite_id="benchmark",
            suite_version=f"benchmark:{BENCHMARK_SUITE_CONTRACT_VERSION}",
            providers=tuple(provider_names),
            capabilities=tuple(self._benchmark_capabilities(selected_operations_by_provider)),
            runtime_manifests=collect_runtime_manifests(provider_names),
            input_digest=digest_payload(benchmark_inputs.to_dict()),
            result_digest=digest_payload([result.to_dict() for result in results]),
            event_count=self._benchmark_event_count(results),
            claim_boundary=BENCHMARK_CLAIM_BOUNDARY,
            metric_semantics=BENCHMARK_METRIC_SEMANTICS,
        )

    @staticmethod
    def _benchmark_run_metadata(
        *,
        provider_names: Sequence[str],
        requested_operations: Sequence[str],
        selected_operations_by_provider: dict[str, list[str]],
        iterations: int,
        concurrency: int,
        benchmark_inputs: BenchmarkInputs,
    ) -> JSONDict:
        return {
            "providers": list(provider_names),
            "requested_operations": list(requested_operations),
            "selected_operations": selected_operations_by_provider,
            "iterations": iterations,
            "concurrency": concurrency,
            "inputs": benchmark_inputs.to_dict(),
        }

    def run(
        self,
        providers: str | Sequence[str],
        *,
        operations: Sequence[str] | None = None,
        iterations: int = 5,
        concurrency: int = 1,
        inputs: BenchmarkInputs | None = None,
        on_sample: Callable[[JSONDict], None] | None = None,
    ) -> BenchmarkReport:
        provider_names = self._benchmark_provider_names(providers)
        require_positive_int(iterations, name="iterations")
        require_positive_int(concurrency, name="concurrency")
        benchmark_inputs = inputs or BenchmarkInputs()
        requested_operations = self._requested_operations(operations)
        provider_plan = self._provider_benchmark_plan(
            provider_names,
            requested_operations=requested_operations,
            explicit_operations=operations is not None,
        )
        selected_operations_by_provider = self._selected_operations_by_provider(provider_plan)
        results = self._run_provider_plan(
            provider_plan,
            iterations=iterations,
            concurrency=concurrency,
            inputs=benchmark_inputs,
            on_sample=on_sample,
        )
        return BenchmarkReport(
            results,
            run_metadata=self._benchmark_run_metadata(
                provider_names=provider_names,
                requested_operations=requested_operations,
                selected_operations_by_provider=selected_operations_by_provider,
                iterations=iterations,
                concurrency=concurrency,
                benchmark_inputs=benchmark_inputs,
            ),
            provenance=self._benchmark_provenance(
                provider_names=provider_names,
                selected_operations_by_provider=selected_operations_by_provider,
                benchmark_inputs=benchmark_inputs,
                results=results,
            ),
        )


def run_benchmark(
    providers: str | Sequence[str],
    *,
    forge: WorldForge | None = None,
    operations: Sequence[str] | None = None,
    iterations: int = 5,
    concurrency: int = 1,
    inputs: BenchmarkInputs | None = None,
    on_sample: Callable[[JSONDict], None] | None = None,
) -> BenchmarkReport:
    """Convenience wrapper around ProviderBenchmarkHarness.run()."""

    return ProviderBenchmarkHarness(forge=forge).run(
        providers,
        operations=operations,
        iterations=iterations,
        concurrency=concurrency,
        inputs=inputs,
        on_sample=on_sample,
    )


__all__ = [
    "BENCHMARKABLE_OPERATIONS",
    "BenchmarkBudget",
    "BenchmarkGateReport",
    "BenchmarkGateViolation",
    "BenchmarkInputs",
    "BenchmarkReport",
    "BenchmarkResult",
    "ProviderBenchmarkHarness",
    "load_benchmark_budgets",
    "load_benchmark_inputs",
    "run_benchmark",
]

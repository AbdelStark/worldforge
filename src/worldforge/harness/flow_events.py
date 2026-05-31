"""Provider-event derivation for harness flow summaries."""

from __future__ import annotations

from collections.abc import Mapping

from worldforge.harness.models import HarnessFlow
from worldforge.models import JSONDict, ProviderEvent


def provider_events_for(
    flow_id: str,
    summary: JSONDict,
    *,
    flows: Mapping[str, HarnessFlow],
) -> tuple[JSONDict, ...]:
    explicit_events = _explicit_provider_events(summary)
    if explicit_events is not None:
        return explicit_events

    benchmark_events = _benchmark_provider_events(flow_id, summary)
    if benchmark_events is not None:
        return benchmark_events

    return _phase_provider_events(flow_id, summary, flows=flows)


def _explicit_provider_events(summary: JSONDict) -> tuple[JSONDict, ...] | None:
    events = summary.get("provider_events")
    if not isinstance(events, list):
        return None
    return tuple(dict(event) for event in events if isinstance(event, dict))


def _benchmark_provider_events(flow_id: str, summary: JSONDict) -> tuple[JSONDict, ...] | None:
    benchmark_results = summary.get("benchmark_results")
    if not isinstance(benchmark_results, list):
        return None
    return tuple(
        _benchmark_metric_provider_event(flow_id, result, metric_event)
        for result in benchmark_results
        if isinstance(result, dict)
        for metric_event in _benchmark_metric_events(result)
    )


def _benchmark_metric_events(result: JSONDict) -> tuple[JSONDict, ...]:
    metrics = result.get("operation_metrics")
    if not isinstance(metrics, dict):
        return ()
    events = metrics.get("events", [])
    if not isinstance(events, list):
        return ()
    return tuple(event for event in events if isinstance(event, dict))


def _benchmark_metric_provider_event(
    flow_id: str,
    result: JSONDict,
    metric_event: JSONDict,
) -> JSONDict:
    request_count = _benchmark_metric_count(metric_event, "request_count")
    retry_count = _benchmark_metric_count(metric_event, "retry_count")
    error_count = _benchmark_metric_count(metric_event, "error_count")
    return ProviderEvent(
        provider=str(metric_event.get("provider", result.get("provider", "mock"))),
        operation=str(metric_event.get("operation", result.get("operation", flow_id))),
        phase=_benchmark_metric_phase(retry_count=retry_count, error_count=error_count),
        metadata={
            "request_count": request_count,
            "retry_count": retry_count,
            "error_count": error_count,
        },
    ).to_dict()


def _benchmark_metric_count(metric_event: JSONDict, key: str) -> int:
    return int(metric_event.get(key, 0) or 0)


def _benchmark_metric_phase(*, retry_count: int, error_count: int) -> str:
    if error_count:
        return "failure"
    if retry_count:
        return "retry"
    return "success"


def _phase_provider_events(
    flow_id: str,
    summary: JSONDict,
    *,
    flows: Mapping[str, HarnessFlow],
) -> tuple[JSONDict, ...]:
    phases = summary.get("event_phases")
    if not isinstance(phases, list):
        return ()
    flow = flows[flow_id]
    return tuple(
        ProviderEvent(
            provider=flow.provider,
            operation=flow.id,
            phase=str(phase),
        ).to_dict()
        for phase in phases
    )

"""Regression analysis helpers for preserved WorldForge run reports."""

from __future__ import annotations

import hashlib
from collections.abc import Iterable
from pathlib import Path
from typing import Protocol

from worldforge.models import JSONDict, dump_json

_SAFE_ARTIFACT_SUFFIXES = {".csv", ".html", ".json", ".jsonl", ".md", ".txt"}


class PreservedRunLike(Protocol):
    """Structural subset of a loaded preserved run report used for analysis."""

    manifest: JSONDict
    report: JSONDict
    run_path: Path

    @property
    def kind(self) -> str: ...

    @property
    def run_id(self) -> str: ...


def build_regression_payload(
    *,
    kind: str,
    reports: list[PreservedRunLike],
    contexts: list[JSONDict],
    runs: list[JSONDict],
    claim_boundary: str,
    comparison_context: JSONDict,
    schema_version: int,
) -> JSONDict:
    """Build the stable regression payload for exactly two compatible reports."""

    metric_deltas = _regression_metric_deltas(kind, reports)
    budget_changes = _regression_budget_changes(contexts)
    failure_changes = _regression_failure_changes(reports)
    artifact_changes = _regression_artifact_changes(reports)
    provenance_changes = _regression_provenance_changes(runs, contexts)
    rows = _regression_rows(
        metric_deltas=metric_deltas,
        budget_changes=budget_changes,
        failure_changes=failure_changes,
        artifact_changes=artifact_changes,
        provenance_changes=provenance_changes,
    )
    status = _regression_status(
        metric_deltas=metric_deltas,
        budget_changes=budget_changes,
        failure_changes=failure_changes,
    )
    summary = {
        "status": status,
        "metric_delta_count": len(metric_deltas),
        "regressed_metric_count": sum(1 for item in metric_deltas if item["status"] == "regressed"),
        "improved_metric_count": sum(1 for item in metric_deltas if item["status"] == "improved"),
        "new_failure_count": len(failure_changes["new_failures"]),
        "removed_failure_count": len(failure_changes["removed_failures"]),
        "artifact_drift_count": len(artifact_changes["added"])
        + len(artifact_changes["removed"])
        + len(artifact_changes["changed"]),
        "provenance_difference_count": len(provenance_changes["differences"]),
        "unsafe_artifact_exclusion_count": artifact_changes["excluded_unsafe_count"],
    }
    return {
        "schema_version": schema_version,
        "mode": "regression",
        "kind": kind,
        "baseline_run_id": reports[0].run_id,
        "candidate_run_id": reports[1].run_id,
        "run_count": 2,
        "claim_boundary": claim_boundary,
        "comparison_context": comparison_context,
        "runs": runs,
        "regression_summary": summary,
        "metric_deltas": metric_deltas,
        "budget_status_changes": budget_changes,
        "failure_changes": failure_changes,
        "artifact_changes": artifact_changes,
        "provenance_changes": provenance_changes,
        "rows": rows,
    }


def safe_artifact_map(report: PreservedRunLike) -> tuple[dict[str, JSONDict], int]:
    """Return attachable artifact metadata and the count of excluded unsafe refs."""

    artifact_paths = report.manifest.get("artifact_paths", {})
    if not isinstance(artifact_paths, dict):
        return {}, 0
    safe: dict[str, JSONDict] = {}
    excluded = 0
    for label, raw_path in sorted(artifact_paths.items()):
        if not isinstance(label, str) or not isinstance(raw_path, str):
            excluded += 1
            continue
        relative = Path(raw_path)
        if (
            not raw_path.strip()
            or relative.is_absolute()
            or ".." in relative.parts
            or relative.suffix.lower() not in _SAFE_ARTIFACT_SUFFIXES
        ):
            excluded += 1
            continue
        artifact_path = report.run_path / relative
        summary: JSONDict = {
            "label": label,
            "path": raw_path,
            "suffix": relative.suffix.lower().removeprefix("."),
            "exists": artifact_path.is_file(),
            "size_bytes": None,
            "sha256": None,
        }
        if artifact_path.is_file():
            data = artifact_path.read_bytes()
            summary["size_bytes"] = len(data)
            summary["sha256"] = hashlib.sha256(data).hexdigest()
        safe[label] = summary
    return safe, excluded


def result_event_count(result: JSONDict) -> int:
    """Count provider request events stored in one benchmark result object."""

    metrics = result.get("operation_metrics", {})
    if not isinstance(metrics, dict):
        return 0
    events = metrics.get("events", [])
    if not isinstance(events, list):
        return 0
    total = 0
    for event in events:
        if isinstance(event, dict):
            total += int(event.get("request_count", 0) or 0)
    return total


def _regression_metric_deltas(
    kind: str,
    reports: list[PreservedRunLike],
) -> list[JSONDict]:
    baseline, candidate = reports
    if kind == "benchmark":
        baseline_metrics = _benchmark_metric_values(baseline)
        candidate_metrics = _benchmark_metric_values(candidate)
        metric_specs = {
            "average_latency_ms": False,
            "p95_latency_ms": False,
            "throughput_per_second": True,
            "error_count": False,
            "retry_count": False,
            "request_count": False,
            "success_count": True,
        }
    elif kind == "eval":
        baseline_metrics = _evaluation_metric_values(baseline)
        candidate_metrics = _evaluation_metric_values(candidate)
        metric_specs = {
            "average_score": True,
            "pass_rate": True,
            "passed_scenario_count": True,
            "failed_scenario_count": False,
        }
    else:
        baseline_metrics = _demo_metric_values(baseline)
        candidate_metrics = _demo_metric_values(candidate)
        metric_specs = {"safe_to_attach": True}
    deltas: list[JSONDict] = []
    for metric, higher_is_better in metric_specs.items():
        baseline_value = baseline_metrics.get(metric)
        candidate_value = candidate_metrics.get(metric)
        if baseline_value is None and candidate_value is None:
            continue
        delta = (
            None
            if baseline_value is None or candidate_value is None
            else candidate_value - baseline_value
        )
        deltas.append(
            {
                "metric": metric,
                "baseline": baseline_value,
                "candidate": candidate_value,
                "delta": delta,
                "higher_is_better": higher_is_better,
                "status": _delta_status(delta, higher_is_better=higher_is_better),
            }
        )
    return deltas


def _regression_budget_changes(contexts: list[JSONDict]) -> JSONDict:
    baseline = contexts[0].get("budget_passed")
    candidate = contexts[1].get("budget_passed")
    baseline_status = _budget_status(baseline)
    candidate_status = _budget_status(candidate)
    if candidate is False and baseline is not False:
        status = "budget-violation"
    elif baseline is False and candidate is True:
        status = "improved"
    elif baseline == candidate:
        status = "unchanged"
    else:
        status = "changed"
    return {
        "status": status,
        "baseline_status": baseline_status,
        "candidate_status": candidate_status,
        "baseline_budget_ref": contexts[0].get("budget_ref"),
        "candidate_budget_ref": contexts[1].get("budget_ref"),
    }


def _regression_failure_changes(reports: list[PreservedRunLike]) -> JSONDict:
    baseline = set(_failure_fingerprints(reports[0]))
    candidate = set(_failure_fingerprints(reports[1]))
    new_failures = sorted(candidate - baseline)
    removed_failures = sorted(baseline - candidate)
    if new_failures:
        status = "new-failures"
    elif removed_failures:
        status = "improved"
    else:
        status = "unchanged"
    return {
        "status": status,
        "new_failures": new_failures,
        "removed_failures": removed_failures,
        "baseline_failure_count": len(baseline),
        "candidate_failure_count": len(candidate),
    }


def _regression_artifact_changes(reports: list[PreservedRunLike]) -> JSONDict:
    baseline, baseline_excluded = safe_artifact_map(reports[0])
    candidate, candidate_excluded = safe_artifact_map(reports[1])
    baseline_labels = set(baseline)
    candidate_labels = set(candidate)
    changed = sorted(
        label
        for label in baseline_labels & candidate_labels
        if _artifact_signature(baseline[label]) != _artifact_signature(candidate[label])
    )
    added = sorted(candidate_labels - baseline_labels)
    removed = sorted(baseline_labels - candidate_labels)
    status = "changed" if added or removed or changed else "unchanged"
    return {
        "status": status,
        "added": added,
        "removed": removed,
        "changed": changed,
        "baseline_safe_count": len(baseline),
        "candidate_safe_count": len(candidate),
        "excluded_unsafe_count": baseline_excluded + candidate_excluded,
    }


def _regression_provenance_changes(runs: list[JSONDict], contexts: list[JSONDict]) -> JSONDict:
    differences = []
    fields = (
        ("provider", runs[0].get("provider"), runs[1].get("provider")),
        ("operation", runs[0].get("operation"), runs[1].get("operation")),
        ("command", runs[0].get("command"), runs[1].get("command")),
        ("fixture_digest", contexts[0].get("fixture_digest"), contexts[1].get("fixture_digest")),
        ("suite_version", contexts[0].get("suite_version"), contexts[1].get("suite_version")),
        ("budget_ref", contexts[0].get("budget_ref"), contexts[1].get("budget_ref")),
    )
    for name, baseline, candidate in fields:
        if baseline != candidate:
            differences.append(name)
    return {
        "status": "changed" if differences else "unchanged",
        "differences": differences,
    }


def _regression_rows(
    *,
    metric_deltas: list[JSONDict],
    budget_changes: JSONDict,
    failure_changes: JSONDict,
    artifact_changes: JSONDict,
    provenance_changes: JSONDict,
) -> list[JSONDict]:
    rows: list[JSONDict] = [
        {
            "category": "metric",
            "name": metric["metric"],
            "status": metric["status"],
            "baseline": metric.get("baseline"),
            "candidate": metric.get("candidate"),
            "delta": metric.get("delta"),
            "detail": "higher is better" if metric.get("higher_is_better") else "lower is better",
        }
        for metric in metric_deltas
    ]
    rows.append(
        {
            "category": "budget",
            "name": "budget_status",
            "status": budget_changes["status"],
            "baseline": budget_changes["baseline_status"],
            "candidate": budget_changes["candidate_status"],
            "delta": "",
            "detail": budget_changes.get("candidate_budget_ref") or "",
        }
    )
    rows.append(
        {
            "category": "failure",
            "name": "new_failures",
            "status": failure_changes["status"],
            "baseline": failure_changes["baseline_failure_count"],
            "candidate": failure_changes["candidate_failure_count"],
            "delta": len(failure_changes["new_failures"])
            - len(failure_changes["removed_failures"]),
            "detail": "; ".join(failure_changes["new_failures"]),
        }
    )
    rows.append(
        {
            "category": "artifact",
            "name": "artifact_drift",
            "status": artifact_changes["status"],
            "baseline": artifact_changes["baseline_safe_count"],
            "candidate": artifact_changes["candidate_safe_count"],
            "delta": len(artifact_changes["added"]) - len(artifact_changes["removed"]),
            "detail": "unsafe artifacts excluded from rendered reports",
        }
    )
    rows.append(
        {
            "category": "provenance",
            "name": "provenance_differences",
            "status": provenance_changes["status"],
            "baseline": "",
            "candidate": "",
            "delta": len(provenance_changes["differences"]),
            "detail": "; ".join(provenance_changes["differences"]),
        }
    )
    return rows


def _regression_status(
    *,
    metric_deltas: list[JSONDict],
    budget_changes: JSONDict,
    failure_changes: JSONDict,
) -> str:
    if (
        any(delta["status"] == "regressed" for delta in metric_deltas)
        or budget_changes["status"] == "budget-violation"
        or failure_changes["new_failures"]
    ):
        return "regressed"
    if (
        any(delta["status"] == "improved" for delta in metric_deltas)
        or budget_changes["status"] == "improved"
        or failure_changes["removed_failures"]
    ):
        return "improved"
    return "unchanged"


def _benchmark_metric_values(report: PreservedRunLike) -> dict[str, float | None]:
    results = _report_objects(report, "results")
    if not results:
        return {}
    return {
        "average_latency_ms": _mean_report_field(results, "average_latency_ms"),
        "p95_latency_ms": _mean_report_field(results, "p95_latency_ms"),
        "throughput_per_second": _mean_report_field(results, "throughput_per_second"),
        "error_count": _sum_report_int_field(results, "error_count"),
        "retry_count": _sum_report_int_field(results, "retry_count"),
        "request_count": _sum_result_request_count(results),
        "success_count": _sum_report_int_field(results, "success_count"),
    }


def _evaluation_metric_values(report: PreservedRunLike) -> dict[str, float | None]:
    summaries = _report_objects(report, "provider_summaries")
    if not summaries:
        return {}
    scenario_count = _sum_report_int_field(summaries, "scenario_count")
    passed = _sum_report_int_field(summaries, "passed_scenario_count")
    failed = _sum_report_int_field(summaries, "failed_scenario_count")
    return {
        "average_score": _mean_report_field(summaries, "average_score"),
        "pass_rate": None if scenario_count <= 0 else passed / scenario_count,
        "passed_scenario_count": passed,
        "failed_scenario_count": failed,
    }


def _demo_metric_values(report: PreservedRunLike) -> dict[str, float | None]:
    safe = bool(
        report.report.get(
            "safe_to_attach",
            _json_object(report.manifest.get("result_summary")).get("safe_to_attach", False),
        )
    )
    return {"safe_to_attach": 1.0 if safe else 0.0}


def _report_objects(report: PreservedRunLike, key: str) -> list[JSONDict]:
    return [item for item in report.report.get(key, []) if isinstance(item, dict)]


def _mean_report_field(items: list[JSONDict], key: str) -> float | None:
    return _mean_optional_float(item.get(key) for item in items)


def _sum_report_int_field(items: list[JSONDict], key: str) -> float:
    return float(sum(_int_field(item, key) for item in items))


def _sum_result_request_count(results: list[JSONDict]) -> float:
    return float(sum(result_event_count(result) for result in results))


def _mean_optional_float(values: Iterable[object]) -> float | None:
    numbers = [_optional_float(value) for value in values]
    finite = [number for number in numbers if number is not None]
    return sum(finite) / len(finite) if finite else None


def _delta_status(delta: float | None, *, higher_is_better: bool) -> str:
    if delta is None or delta == 0:
        return "unchanged"
    if higher_is_better:
        return "improved" if delta > 0 else "regressed"
    return "improved" if delta < 0 else "regressed"


def _budget_status(value: object) -> str:
    if value is True:
        return "passed"
    if value is False:
        return "failed"
    return "not-recorded"


def _failure_fingerprints(report: PreservedRunLike) -> list[str]:
    failures = list(_run_status_failures(report))
    failures.extend(_report_kind_failures(report, has_run_failure=bool(failures)))
    return sorted(dict.fromkeys(failures))


def _run_status_failures(report: PreservedRunLike) -> tuple[str, ...]:
    status = str(report.manifest.get("status"))
    if status not in {"failed", "cancelled", "skipped"}:
        return ()
    return (f"run:{report.manifest.get('status')}:{_run_failure_reason(report, status)}",)


def _run_failure_reason(report: PreservedRunLike, status: str) -> str:
    result_summary = _json_object(report.manifest.get("result_summary"))
    return (
        _optional_text(result_summary.get("failure_reason"))
        or _optional_text(result_summary.get("skip_reason"))
        or _optional_text(result_summary.get("reason"))
        or status
    )


def _report_kind_failures(
    report: PreservedRunLike,
    *,
    has_run_failure: bool,
) -> list[str]:
    if report.kind == "benchmark":
        return _benchmark_failures(report)
    if report.kind == "eval":
        return _evaluation_failures(report)
    if report.kind == "demo_showcase" and not has_run_failure:
        return _demo_showcase_failures(report)
    return []


def _benchmark_failures(report: PreservedRunLike) -> list[str]:
    failures: list[str] = []
    for result in report.report.get("results", []):
        if isinstance(result, dict):
            failures.extend(_benchmark_result_failures(result))
    return failures


def _benchmark_result_failures(result: JSONDict) -> list[str]:
    operation = result.get("operation", "")
    failures = [
        f"benchmark:{operation}:{_failure_text(error)}" for error in result.get("errors", []) or []
    ]
    error_count = int(result.get("error_count", 0) or 0)
    if error_count and not result.get("errors"):
        failures.append(f"benchmark:{operation}:error_count={error_count}")
    return failures


def _evaluation_failures(report: PreservedRunLike) -> list[str]:
    return [
        _evaluation_result_failure(result)
        for result in report.report.get("results", [])
        if isinstance(result, dict) and result.get("passed") is False
    ]


def _evaluation_result_failure(result: JSONDict) -> str:
    return (
        "eval:"
        f"{result.get('provider', '')}:"
        f"{result.get('scenario', '')}:"
        f"{_failure_text(result.get('details') or result.get('error') or 'failed')}"
    )


def _demo_showcase_failures(report: PreservedRunLike) -> list[str]:
    status = report.report.get("status", "passed")
    if str(status) == "passed":
        return []
    return [f"demo:{_demo_workflow(report)}:{status}"]


def _demo_workflow(report: PreservedRunLike) -> str:
    input_summary = _json_object(report.manifest.get("input_summary"))
    for value in (input_summary.get("workflow"), report.manifest.get("operation")):
        text = _optional_text(value)
        if text:
            return text
    return ""


def _failure_text(value: object) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        for key in ("message", "error", "type", "reason"):
            text = _optional_text(value.get(key))
            if text:
                return text
        return dump_json(value)
    return str(value)


def _artifact_signature(summary: JSONDict) -> tuple[object, ...]:
    return (
        summary.get("suffix"),
        summary.get("exists"),
        summary.get("size_bytes"),
        summary.get("sha256"),
    )


def _optional_float(value: object) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _int_field(payload: JSONDict, key: str) -> int:
    return int(payload.get(key, 0) or 0)


def _optional_text(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    stripped = value.strip()
    return stripped or None


def _json_object(value: object) -> JSONDict:
    return dict(value) if isinstance(value, dict) else {}

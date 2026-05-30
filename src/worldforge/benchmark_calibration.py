"""Candidate benchmark budget calibration from preserved benchmark reports."""

from __future__ import annotations

import hashlib
import json
import os
import platform
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from worldforge.artifact_io import write_json_artifact
from worldforge.benchmark import BenchmarkBudget, load_benchmark_budgets
from worldforge.models import JSONDict, WorldForgeError, dump_json, require_finite_number

BENCHMARK_CALIBRATION_SCHEMA_VERSION = 1
DEFAULT_HEADROOM_RATIO = 0.25
DEFAULT_RATIONALE = "review required before applying candidate budget"

_THRESHOLD_FIELDS = (
    "min_success_rate",
    "max_error_count",
    "max_retry_count",
    "max_average_latency_ms",
    "max_p95_latency_ms",
    "min_throughput_per_second",
)


@dataclass(frozen=True, slots=True)
class BudgetCalibrationResult:
    """Generated budget calibration payload and optional written artifacts."""

    payload: JSONDict
    output_dir: Path | None = None
    calibration_path: Path | None = None
    candidate_budget_path: Path | None = None
    markdown_path: Path | None = None


@dataclass(frozen=True, slots=True)
class _CalibrationRows:
    candidate_entries: list[JSONDict]
    baseline_context: list[JSONDict]
    diffs: list[JSONDict]


@dataclass(frozen=True, slots=True)
class _LoadedJsonFile:
    path: Path
    data: bytes
    payload: object

    @property
    def sha256(self) -> str:
        return _sha256_bytes(self.data)


def generate_budget_calibration(
    *,
    report_paths: Sequence[Path],
    current_budget_path: Path | None = None,
    output_dir: Path | None = None,
    headroom_ratio: float = DEFAULT_HEADROOM_RATIO,
    machine_class: str | None = None,
    rationale: str = DEFAULT_RATIONALE,
) -> BudgetCalibrationResult:
    """Generate candidate benchmark budgets from preserved benchmark JSON reports.

    The function never edits existing budget files. It returns a calibration payload and, when
    ``output_dir`` is provided, writes a full calibration report plus a candidate budget file.
    """

    headroom = _headroom(headroom_ratio)
    review_rationale = _rationale(rationale)
    current_budgets, current_digest = _load_current_budgets(current_budget_path)
    reports = _load_calibration_reports(report_paths)
    rows = _build_calibration_rows(
        reports=reports,
        current_budgets=current_budgets,
        headroom=headroom,
        machine_class=machine_class,
        rationale=review_rationale,
    )
    candidate_budgets = _candidate_budget_document(
        candidates=rows.candidate_entries,
        reports=reports,
        current_digest=current_digest,
        headroom=headroom,
        rationale=review_rationale,
    )
    load_benchmark_budgets(candidate_budgets)
    payload = _calibration_payload(
        reports=reports,
        rows=rows,
        candidate_budgets=candidate_budgets,
        current_budget_path=current_budget_path,
        current_digest=current_digest,
        headroom=headroom,
        rationale=review_rationale,
    )
    dump_json(payload)
    if output_dir is None:
        return BudgetCalibrationResult(payload=payload)
    return _write_calibration_artifacts(
        output_dir=output_dir,
        payload=payload,
        candidate_budgets=candidate_budgets,
    )


def _load_calibration_reports(report_paths: Sequence[Path]) -> list[JSONDict]:
    if not report_paths:
        raise WorldForgeError("At least one benchmark report path is required for calibration.")
    return [_load_report(Path(path)) for path in report_paths]


def _build_calibration_rows(
    *,
    reports: Sequence[JSONDict],
    current_budgets: tuple[BenchmarkBudget, ...],
    headroom: float,
    machine_class: str | None,
    rationale: str,
) -> _CalibrationRows:
    candidate_entries: list[JSONDict] = []
    baseline_context: list[JSONDict] = []
    diffs: list[JSONDict] = []
    for report in reports:
        report_payload = report["payload"]
        provenance = _object_or_empty(report_payload.get("provenance"))
        run_metadata = _object_or_empty(report_payload.get("run_metadata"))
        for result in report_payload.get("results", []):
            if not isinstance(result, dict):
                raise WorldForgeError("Benchmark report results must contain JSON objects.")
            candidate = _candidate_budget(result, headroom=headroom)
            BenchmarkBudget.from_dict(candidate)
            candidate_entries.append(candidate)
            baseline_context.append(
                _baseline_context(
                    result=result,
                    report=report,
                    provenance=provenance,
                    run_metadata=run_metadata,
                    machine_class=machine_class,
                )
            )
            diffs.extend(
                _budget_diffs(
                    candidate=candidate,
                    result=result,
                    current_budgets=current_budgets,
                    rationale=rationale,
                )
            )
    return _CalibrationRows(
        candidate_entries=candidate_entries,
        baseline_context=baseline_context,
        diffs=diffs,
    )


def _candidate_budget_document(
    *,
    candidates: list[JSONDict],
    reports: Sequence[JSONDict],
    current_digest: str | None,
    headroom: float,
    rationale: str,
) -> JSONDict:
    return {
        "metadata": {
            "schema_version": BENCHMARK_CALIBRATION_SCHEMA_VERSION,
            "generated_by": "worldforge.benchmark_calibration",
            "generated_at": datetime.now(UTC).replace(microsecond=0).isoformat(),
            "headroom_ratio": headroom,
            "rationale": rationale,
            "source_report_digests": [report["sha256"] for report in reports],
            "current_budget_digest": current_digest,
            "review_required": True,
        },
        "budgets": _dedupe_budget_entries(candidates),
    }


def _calibration_payload(
    *,
    reports: Sequence[JSONDict],
    rows: _CalibrationRows,
    candidate_budgets: JSONDict,
    current_budget_path: Path | None,
    current_digest: str | None,
    headroom: float,
    rationale: str,
) -> JSONDict:
    return {
        "schema_version": BENCHMARK_CALIBRATION_SCHEMA_VERSION,
        "generated_at": candidate_budgets["metadata"]["generated_at"],
        "headroom_ratio": headroom,
        "review_required": True,
        "rationale": rationale,
        "current_budget_path": _display_path(current_budget_path) if current_budget_path else None,
        "current_budget_digest": current_digest,
        "source_reports": [_source_report_summary(report) for report in reports],
        "baseline_context": rows.baseline_context,
        "candidate_budgets": candidate_budgets,
        "diffs": rows.diffs,
    }


def _source_report_summary(report: JSONDict) -> JSONDict:
    return {
        "path": report["path"],
        "sha256": report["sha256"],
        "command": report["command"],
        "worldforge_version": report["worldforge_version"],
        "input_digest": report["input_digest"],
        "budget_file": report["budget_file"],
    }


def _write_calibration_artifacts(
    *,
    output_dir: Path,
    payload: JSONDict,
    candidate_budgets: JSONDict,
) -> BudgetCalibrationResult:
    _validate_calibration_artifacts(payload=payload, candidate_budgets=candidate_budgets)
    output = output_dir.expanduser().resolve()
    calibration_path = output / "budget-calibration.json"
    candidate_budget_path = output / "candidate-budgets.json"
    markdown_path = output / "budget-calibration.md"
    write_json_artifact(calibration_path, payload)
    write_json_artifact(candidate_budget_path, candidate_budgets)
    markdown_path.write_text(render_budget_calibration_markdown(payload), encoding="utf-8")
    return BudgetCalibrationResult(
        payload=payload,
        output_dir=output,
        calibration_path=calibration_path,
        candidate_budget_path=candidate_budget_path,
        markdown_path=markdown_path,
    )


def _validate_calibration_artifacts(*, payload: JSONDict, candidate_budgets: JSONDict) -> None:
    dump_json(payload)
    dump_json(candidate_budgets)


def calibrate_benchmark_budgets(
    report_paths: Sequence[Path],
    *,
    current_budget_path: Path | None = None,
    output_dir: Path | None = None,
    headroom_ratio: float = DEFAULT_HEADROOM_RATIO,
    machine_class: str | None = None,
    rationale: str = DEFAULT_RATIONALE,
) -> BudgetCalibrationResult:
    """Generate candidate budget artifacts from preserved benchmark reports."""

    return generate_budget_calibration(
        report_paths=report_paths,
        current_budget_path=current_budget_path,
        output_dir=output_dir,
        headroom_ratio=headroom_ratio,
        machine_class=machine_class,
        rationale=rationale,
    )


def render_budget_calibration_markdown(payload: JSONDict) -> str:
    """Render a human-reviewable budget calibration report."""

    lines = _calibration_summary_markdown_lines(payload)
    lines.extend(_source_reports_markdown_lines(payload["source_reports"]))
    lines.extend(_baseline_context_markdown_lines(payload["baseline_context"]))
    lines.extend(_candidate_diffs_markdown_lines(payload["diffs"]))
    lines.extend(_human_review_markdown_lines())
    return "\n".join(lines)


def _calibration_summary_markdown_lines(payload: JSONDict) -> list[str]:
    return [
        "# Benchmark Budget Calibration",
        "",
        f"- Schema version: `{payload['schema_version']}`",
        f"- Generated at: `{payload['generated_at']}`",
        f"- Headroom ratio: `{payload['headroom_ratio']}`",
        f"- Review required: `{str(payload['review_required']).lower()}`",
        f"- Rationale: {payload['rationale']}",
        f"- Current budget: `{payload.get('current_budget_path') or '-'}`",
        f"- Current budget digest: `{payload.get('current_budget_digest') or '-'}`",
        "",
    ]


def _source_reports_markdown_lines(source_reports: Sequence[JSONDict]) -> list[str]:
    lines = [
        "## Source Reports",
        "",
        "| Report | SHA256 | Command | Input digest |",
        "| --- | --- | --- | --- |",
    ]
    lines.extend(
        "| `{path}` | `{sha256}` | `{command}` | `{input_digest}` |".format(
            path=report["path"],
            sha256=report["sha256"],
            command=report.get("command") or "-",
            input_digest=report.get("input_digest") or "-",
        )
        for report in source_reports
    )
    return lines


def _baseline_context_markdown_lines(baselines: Sequence[JSONDict]) -> list[str]:
    lines = [
        "",
        "## Baseline Context",
        "",
        (
            "| Provider | Operation | Samples | Machine class | Python | Fixture digest | "
            "Source report |"
        ),
        "| --- | --- | ---: | --- | --- | --- | --- |",
    ]
    lines.extend(
        (
            "| {provider} | {operation} | {samples} | {machine} | {python} | `{fixture}` | "
            "`{report}` |"
        ).format(
            provider=baseline["provider"],
            operation=baseline["operation"],
            samples=baseline["sample_count"],
            machine=baseline["machine_class"],
            python=baseline["python_version"],
            fixture=baseline.get("input_fixture_digest") or "-",
            report=baseline["source_report"],
        )
        for baseline in baselines
    )
    return lines


def _candidate_diffs_markdown_lines(diffs: Sequence[JSONDict]) -> list[str]:
    lines = [
        "",
        "## Candidate Diffs",
        "",
        (
            "| Provider | Operation | Metric | Old threshold | Candidate threshold | "
            "Observed baseline | Rationale |"
        ),
        "| --- | --- | --- | ---: | ---: | ---: | --- |",
    ]
    lines.extend(
        (
            "| {provider} | {operation} | {metric} | {old} | {candidate} | {observed} | "
            "{rationale} |"
        ).format(
            provider=diff["provider"],
            operation=diff["operation"],
            metric=diff["metric"],
            old=_format_diff_value(diff.get("old_threshold")),
            candidate=_format_diff_value(diff.get("candidate_threshold")),
            observed=_format_diff_value(diff.get("observed_baseline")),
            rationale=diff["rationale"],
        )
        for diff in diffs
    )
    return lines


def _human_review_markdown_lines() -> list[str]:
    return [
        "",
        "## Human Review Required",
        "",
        "Candidate budgets are review artifacts. Do not replace release budget files until the "
        "source report, machine class, input fixture digest, old threshold, candidate "
        "threshold, observed baseline, and rationale have been reviewed. Threshold loosening "
        "must reference preserved run artifacts.",
        "",
    ]


def _candidate_budget(result: JSONDict, *, headroom: float) -> JSONDict:
    iterations = _positive_int(result.get("iterations"), name="benchmark result iterations")
    success_count = _non_negative_int(
        result.get("success_count"),
        name="benchmark result success_count",
    )
    error_count = _non_negative_int(result.get("error_count"), name="benchmark result error_count")
    retry_count = _non_negative_int(result.get("retry_count"), name="benchmark result retry_count")
    if success_count + error_count != iterations:
        raise WorldForgeError(
            "benchmark result success_count and error_count must sum to iterations."
        )
    success_rate = success_count / iterations
    candidate: JSONDict = {
        "provider": _required_text(result.get("provider"), name="benchmark result provider"),
        "operation": _required_text(result.get("operation"), name="benchmark result operation"),
        "min_success_rate": round(success_rate, 4),
        "max_error_count": error_count,
        "max_retry_count": retry_count,
    }
    average_latency = _optional_non_negative_number(
        result.get("average_latency_ms"),
        name="benchmark result average_latency_ms",
    )
    if average_latency is not None:
        candidate["max_average_latency_ms"] = round(average_latency * (1.0 + headroom), 4)
    p95_latency = _optional_non_negative_number(
        result.get("p95_latency_ms"),
        name="benchmark result p95_latency_ms",
    )
    if p95_latency is not None:
        candidate["max_p95_latency_ms"] = round(p95_latency * (1.0 + headroom), 4)
    throughput = _optional_non_negative_number(
        result.get("throughput_per_second"),
        name="benchmark result throughput_per_second",
    )
    if throughput is not None and throughput > 0.0:
        candidate["min_throughput_per_second"] = round(throughput / (1.0 + headroom), 4)
    return candidate


def _baseline_context(
    *,
    result: JSONDict,
    report: JSONDict,
    provenance: JSONDict,
    run_metadata: JSONDict,
    machine_class: str | None,
) -> JSONDict:
    return {
        "provider": result["provider"],
        "operation": result["operation"],
        "sample_count": result["iterations"],
        "success_count": result["success_count"],
        "error_count": result["error_count"],
        "retry_count": result["retry_count"],
        "average_latency_ms": result.get("average_latency_ms"),
        "p95_latency_ms": result.get("p95_latency_ms"),
        "throughput_per_second": result.get("throughput_per_second"),
        "machine_class": machine_class or os.environ.get("WORLDFORGE_MACHINE_CLASS") or "unknown",
        "python_version": platform.python_version(),
        "platform": platform.platform(),
        "command": " ".join(provenance.get("command", ()) or ()) or report.get("command") or "",
        "input_fixture_digest": provenance.get("input_digest")
        or _metadata_digest(run_metadata.get("input_file")),
        "source_report": report["path"],
        "source_report_digest": report["sha256"],
    }


def _budget_diffs(
    *,
    candidate: JSONDict,
    result: JSONDict,
    current_budgets: tuple[BenchmarkBudget, ...],
    rationale: str,
) -> list[JSONDict]:
    current = _matching_budget(candidate, current_budgets)
    diffs: list[JSONDict] = []
    for field in _THRESHOLD_FIELDS:
        candidate_threshold = candidate.get(field)
        if candidate_threshold is None:
            continue
        diffs.append(
            {
                "provider": candidate["provider"],
                "operation": candidate["operation"],
                "metric": field,
                "old_threshold": getattr(current, field) if current is not None else None,
                "candidate_threshold": candidate_threshold,
                "observed_baseline": _observed_value_for_threshold(field, result),
                "rationale": rationale,
                "review_required": True,
            }
        )
    return diffs


def _matching_budget(
    candidate: JSONDict,
    current_budgets: tuple[BenchmarkBudget, ...],
) -> BenchmarkBudget | None:
    provider = candidate.get("provider")
    operation = candidate.get("operation")
    exact = [
        budget
        for budget in current_budgets
        if budget.provider == provider and budget.operation == operation
    ]
    if exact:
        return exact[0]
    wildcard = [
        budget
        for budget in current_budgets
        if (budget.provider is None or budget.provider == provider)
        and (budget.operation is None or budget.operation == operation)
    ]
    return wildcard[0] if wildcard else None


def _observed_value_for_threshold(field: str, result: JSONDict) -> float | int | None:
    if field == "min_success_rate":
        return round(result["success_count"] / result["iterations"], 4)
    mapping = {
        "max_error_count": "error_count",
        "max_retry_count": "retry_count",
        "max_average_latency_ms": "average_latency_ms",
        "max_p95_latency_ms": "p95_latency_ms",
        "min_throughput_per_second": "throughput_per_second",
    }
    return result.get(mapping[field])


def _load_report(path: Path) -> JSONDict:
    document = _load_json_file(path, label="Benchmark report")
    payload = _benchmark_report_payload(document.payload, path=document.path)
    provenance = _object_or_empty(payload.get("provenance"))
    return {
        "path": _display_path(document.path),
        "sha256": document.sha256,
        "payload": payload,
        "command": _report_command(provenance),
        "worldforge_version": provenance.get("worldforge_version"),
        "input_digest": provenance.get("input_digest"),
        "budget_file": provenance.get("budget_file"),
    }


def _load_json_file(path: Path, *, label: str) -> _LoadedJsonFile:
    resolved_path = path.expanduser().resolve()
    data = _read_json_bytes(resolved_path, label=label)
    payload = _decode_json_payload(data, path=resolved_path, label=label)
    return _LoadedJsonFile(path=resolved_path, data=data, payload=payload)


def _read_json_bytes(path: Path, *, label: str) -> bytes:
    try:
        return path.read_bytes()
    except FileNotFoundError as exc:
        raise WorldForgeError(f"{label} not found: {path}") from exc


def _decode_json_payload(data: bytes, *, path: Path, label: str) -> object:
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise WorldForgeError(f"{label} must be UTF-8 JSON: {path}") from exc
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise WorldForgeError(f"{label} contains invalid JSON: {path}") from exc


def _benchmark_report_payload(payload: object, *, path: Path) -> JSONDict:
    if not isinstance(payload, dict):
        raise WorldForgeError(f"Benchmark report must contain a JSON object: {path}")
    results = payload.get("results")
    if not isinstance(results, list) or not results:
        raise WorldForgeError(f"Benchmark report must contain non-empty results: {path}")
    return payload


def _report_command(provenance: JSONDict) -> str:
    command = provenance.get("command", ()) or ()
    if isinstance(command, str):
        return command
    if isinstance(command, Sequence):
        return " ".join(str(part) for part in command)
    return ""


def _load_current_budgets(path: Path | None) -> tuple[tuple[BenchmarkBudget, ...], str | None]:
    if path is None:
        return (), None
    document = _load_json_file(path, label="Current budget file")
    return tuple(load_benchmark_budgets(document.payload)), document.sha256


def _dedupe_budget_entries(entries: list[JSONDict]) -> list[JSONDict]:
    deduped: dict[tuple[str, str], JSONDict] = {}
    for entry in entries:
        deduped[(str(entry["provider"]), str(entry["operation"]))] = entry
    return [deduped[key] for key in sorted(deduped)]


def _metadata_digest(value: object) -> str | None:
    if not isinstance(value, dict):
        return None
    digest = value.get("sha256")
    if isinstance(digest, str) and digest:
        return digest if digest.startswith("sha256:") else f"sha256:{digest}"
    return None


def _headroom(value: float) -> float:
    headroom = require_finite_number(value, name="headroom_ratio")
    if headroom < 0.0 or headroom > 10.0:
        raise WorldForgeError("headroom_ratio must be between 0.0 and 10.0.")
    return headroom


def _rationale(value: str) -> str:
    return _required_text(value, name="rationale")


def _object_or_empty(value: object) -> JSONDict:
    return dict(value) if isinstance(value, dict) else {}


def _required_text(value: object, *, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise WorldForgeError(f"{name} must be a non-empty string.")
    return value.strip()


def _positive_int(value: object, *, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise WorldForgeError(f"{name} must be a positive integer.")
    return value


def _non_negative_int(value: object, *, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise WorldForgeError(f"{name} must be a non-negative integer.")
    return value


def _optional_non_negative_number(value: object, *, name: str) -> float | None:
    if value is None:
        return None
    number = require_finite_number(value, name=name)
    if number < 0.0:
        raise WorldForgeError(f"{name} must be greater than or equal to 0.")
    return number


def _sha256_bytes(data: bytes) -> str:
    return f"sha256:{hashlib.sha256(data).hexdigest()}"


def _display_path(path: Path | None) -> str | None:
    if path is None:
        return None
    try:
        return path.resolve().relative_to(Path.cwd().resolve()).as_posix()
    except ValueError:
        return str(path)


def _format_diff_value(value: object) -> str:
    if value is None:
        return "-"
    if isinstance(value, float):
        return f"{value:.4f}"
    return str(value)


__all__ = [
    "BENCHMARK_CALIBRATION_SCHEMA_VERSION",
    "DEFAULT_HEADROOM_RATIO",
    "BudgetCalibrationResult",
    "calibrate_benchmark_budgets",
    "generate_budget_calibration",
    "render_budget_calibration_markdown",
]

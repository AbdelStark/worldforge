"""Compare preserved WorldForge run reports."""

from __future__ import annotations

import csv
import io
import json
from dataclasses import dataclass
from pathlib import Path

from worldforge.models import JSONDict, WorldForgeError, dump_json

_SUPPORTED_KINDS = {"benchmark", "eval"}


@dataclass(frozen=True, slots=True)
class PreservedRunReport:
    """Loaded report and manifest from one preserved run workspace."""

    manifest: JSONDict
    report: JSONDict
    run_path: Path
    report_path: Path

    @property
    def kind(self) -> str:
        return str(self.manifest.get("kind", ""))

    @property
    def run_id(self) -> str:
        return str(self.manifest.get("run_id", self.run_path.name))


def load_preserved_run_report(path: Path) -> PreservedRunReport:
    """Load a preserved run workspace, manifest path, or report JSON path."""

    source = path.expanduser()
    if source.is_dir():
        run_path = source
        manifest_path = run_path / "run_manifest.json"
    elif source.name == "run_manifest.json":
        manifest_path = source
        run_path = source.parent
    else:
        run_path = source.parent.parent if source.parent.name == "reports" else source.parent
        manifest_path = run_path / "run_manifest.json"

    manifest = _read_json_object(manifest_path, name="run manifest")
    kind = str(manifest.get("kind", ""))
    if kind not in _SUPPORTED_KINDS:
        raise WorldForgeError(
            f"Run {manifest.get('run_id', run_path.name)} has unsupported report kind "
            f"'{kind}'. Supported kinds: {', '.join(sorted(_SUPPORTED_KINDS))}."
        )

    report_path = (
        source
        if source.is_file() and source.name != "run_manifest.json"
        else _report_path(run_path)
    )
    report = _read_json_object(report_path, name="run report")
    _validate_report_kind(kind, report, report_path=report_path)
    return PreservedRunReport(
        manifest=manifest,
        report=report,
        run_path=run_path.resolve(),
        report_path=report_path.resolve(),
    )


def compare_preserved_run_reports(paths: list[Path]) -> JSONDict:
    """Return a stable, issue-attachable comparison payload for preserved runs."""

    if len(paths) < 2:
        raise WorldForgeError(
            "runs compare requires at least two run directories or manifest paths."
        )
    reports = [load_preserved_run_report(path) for path in paths]
    kinds = {report.kind for report in reports}
    if len(kinds) != 1:
        details = ", ".join(f"{report.run_id}:{report.kind}" for report in reports)
        raise WorldForgeError(f"Cannot compare incompatible report types: {details}.")

    kind = reports[0].kind
    rows = _benchmark_rows(reports) if kind == "benchmark" else _evaluation_rows(reports)
    payload: JSONDict = {
        "schema_version": 1,
        "kind": kind,
        "baseline_run_id": reports[0].run_id,
        "run_count": len(reports),
        "runs": [_run_summary(report) for report in reports],
        "rows": rows,
    }
    return payload


def comparison_to_markdown(payload: JSONDict) -> str:
    """Render a comparison payload as Markdown."""

    lines = [
        "# WorldForge Run Comparison",
        "",
        f"Kind: {payload['kind']}",
        f"Baseline: `{payload['baseline_run_id']}`",
        "",
        "## Runs",
        "",
        "| run_id | date | status | command | provider | operation | artifacts | provenance |",
        "| --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    lines.extend(
        (
            "| "
            f"`{run['run_id']}` | {run['created_at']} | {run['status']} | "
            f"`{run['command']}` | {run['provider']} | {run['operation']} | "
            f"{_markdown_join(run['artifact_refs'])} | {_markdown_join(run['provenance_refs'])} |"
        )
        for run in payload["runs"]
    )

    if payload["kind"] == "benchmark":
        lines.extend(
            [
                "",
                "## Benchmark Rows",
                "",
                (
                    "| run_id | provider | operation | ok | errors | retries | avg_ms | "
                    "delta_avg_ms | p95_ms | throughput/s | events |"
                ),
                "| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
            ]
        )
        lines.extend(
            (
                "| "
                f"`{row['run_id']}` | {row['provider']} | {row['operation']} | "
                f"{row['success_count']}/{row['iterations']} | {row['error_count']} | "
                f"{row['retry_count']} | {_format_number(row['average_latency_ms'])} | "
                f"{_format_number(row['delta_average_latency_ms'])} | "
                f"{_format_number(row['p95_latency_ms'])} | "
                f"{_format_number(row['throughput_per_second'])} | {row['event_count']} |"
            )
            for row in payload["rows"]
        )
    else:
        lines.extend(
            [
                "",
                "## Evaluation Rows",
                "",
                (
                    "| run_id | provider | average_score | delta_average_score | "
                    "passed | scenarios |"
                ),
                "| --- | --- | ---: | ---: | ---: | ---: |",
            ]
        )
        lines.extend(
            (
                "| "
                f"`{row['run_id']}` | {row['provider']} | "
                f"{_format_number(row['average_score'])} | "
                f"{_format_number(row['delta_average_score'])} | "
                f"{row['passed_scenario_count']}/{row['scenario_count']} | "
                f"{row['scenario_count']} |"
            )
            for row in payload["rows"]
        )
    return "\n".join(lines)


def comparison_to_csv(payload: JSONDict) -> str:
    """Render a comparison payload as stable CSV."""

    buffer = io.StringIO()
    if payload["kind"] == "benchmark":
        fieldnames = [
            "run_id",
            "created_at",
            "command",
            "provider",
            "operation",
            "iterations",
            "success_count",
            "error_count",
            "retry_count",
            "average_latency_ms",
            "delta_average_latency_ms",
            "p95_latency_ms",
            "throughput_per_second",
            "event_count",
            "artifact_refs_json",
            "provenance_refs_json",
        ]
    else:
        fieldnames = [
            "run_id",
            "created_at",
            "command",
            "provider",
            "average_score",
            "delta_average_score",
            "scenario_count",
            "passed_scenario_count",
            "failed_scenario_count",
            "artifact_refs_json",
            "provenance_refs_json",
        ]
    run_lookup = {run["run_id"]: run for run in payload["runs"]}
    writer = csv.DictWriter(buffer, fieldnames=fieldnames)
    writer.writeheader()
    for row in payload["rows"]:
        run = run_lookup[row["run_id"]]
        exported = {field: row.get(field, "") for field in fieldnames}
        exported["created_at"] = run["created_at"]
        exported["command"] = run["command"]
        exported["artifact_refs_json"] = dump_json(run["artifact_refs"])
        exported["provenance_refs_json"] = dump_json(run["provenance_refs"])
        writer.writerow(exported)
    return buffer.getvalue().strip()


def comparison_artifact(payload: JSONDict, *, output_format: str) -> str:
    """Render a comparison payload in one of the public export formats."""

    if output_format == "json":
        return json.dumps(payload, indent=2, sort_keys=True)
    if output_format == "markdown":
        return comparison_to_markdown(payload)
    if output_format == "csv":
        return comparison_to_csv(payload)
    raise WorldForgeError("comparison format must be json, markdown, or csv.")


def _read_json_object(path: Path, *, name: str) -> JSONDict:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise WorldForgeError(f"Failed to read {name} {path}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise WorldForgeError(f"{name.title()} {path} must contain valid JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise WorldForgeError(f"{name.title()} {path} must be a JSON object.")
    return dict(payload)


def _report_path(run_path: Path) -> Path:
    return run_path / "reports" / "report.json"


def _validate_report_kind(kind: str, report: JSONDict, *, report_path: Path) -> None:
    if kind == "benchmark" and not isinstance(report.get("results"), list):
        raise WorldForgeError(f"Benchmark report {report_path} must contain a results list.")
    if kind == "eval" and not isinstance(report.get("provider_summaries"), list):
        raise WorldForgeError(f"Evaluation report {report_path} must contain provider_summaries.")


def _run_summary(report: PreservedRunReport) -> JSONDict:
    artifact_paths = report.manifest.get("artifact_paths", {})
    artifact_refs = []
    if isinstance(artifact_paths, dict):
        artifact_refs = [
            str(report.run_path / str(path))
            for _, path in sorted(artifact_paths.items())
            if isinstance(path, str)
        ]
    provenance_refs = _provenance_refs(report)
    return {
        "run_id": report.run_id,
        "created_at": str(report.manifest.get("created_at", "")),
        "status": str(report.manifest.get("status", "")),
        "command": str(report.manifest.get("command", "")),
        "provider": str(report.manifest.get("provider", "")),
        "operation": str(report.manifest.get("operation", "")),
        "path": str(report.run_path),
        "report_path": str(report.report_path),
        "artifact_refs": artifact_refs,
        "provenance_refs": provenance_refs,
        "event_count": int(report.manifest.get("event_count", 0) or 0),
    }


def _provenance_refs(report: PreservedRunReport) -> list[str]:
    refs: list[str] = []
    run_metadata = report.report.get("run_metadata", {})
    if isinstance(run_metadata, dict):
        for key in ("input_file", "budget_file"):
            value = run_metadata.get(key)
            if isinstance(value, dict) and isinstance(value.get("path"), str):
                sha = value.get("sha256")
                if isinstance(sha, str):
                    refs.append(f"{key}:{value['path']}#{sha}")
                else:
                    refs.append(f"{key}:{value['path']}")
    input_summary = report.manifest.get("input_summary", {})
    if isinstance(input_summary, dict):
        refs.extend(
            f"{key}:{dump_json(input_summary[key])}"
            for key in ("suite_id", "providers", "operations")
            if key in input_summary
        )
    return refs


def _benchmark_rows(reports: list[PreservedRunReport]) -> list[JSONDict]:
    baseline: dict[tuple[str, str], float | None] = {}
    rows: list[JSONDict] = []
    for report_index, report in enumerate(reports):
        for result in report.report.get("results", []):
            if not isinstance(result, dict):
                continue
            key = (str(result.get("provider", "")), str(result.get("operation", "")))
            avg = _optional_float(result.get("average_latency_ms"))
            if report_index == 0:
                baseline[key] = avg
            baseline_avg = baseline.get(key)
            event_count = _result_event_count(result)
            row: JSONDict = {
                "run_id": report.run_id,
                "provider": key[0],
                "operation": key[1],
                "iterations": int(result.get("iterations", 0) or 0),
                "success_count": int(result.get("success_count", 0) or 0),
                "error_count": int(result.get("error_count", 0) or 0),
                "retry_count": int(result.get("retry_count", 0) or 0),
                "average_latency_ms": avg,
                "delta_average_latency_ms": (
                    None if avg is None or baseline_avg is None else avg - baseline_avg
                ),
                "p95_latency_ms": _optional_float(result.get("p95_latency_ms")),
                "throughput_per_second": _optional_float(result.get("throughput_per_second")),
                "event_count": event_count,
            }
            rows.append(row)
    return rows


def _evaluation_rows(reports: list[PreservedRunReport]) -> list[JSONDict]:
    baseline: dict[str, float | None] = {}
    rows: list[JSONDict] = []
    for report_index, report in enumerate(reports):
        for summary in report.report.get("provider_summaries", []):
            if not isinstance(summary, dict):
                continue
            provider = str(summary.get("provider", ""))
            avg = _optional_float(summary.get("average_score"))
            if report_index == 0:
                baseline[provider] = avg
            baseline_avg = baseline.get(provider)
            rows.append(
                {
                    "run_id": report.run_id,
                    "provider": provider,
                    "average_score": avg,
                    "delta_average_score": (
                        None if avg is None or baseline_avg is None else avg - baseline_avg
                    ),
                    "scenario_count": int(summary.get("scenario_count", 0) or 0),
                    "passed_scenario_count": int(summary.get("passed_scenario_count", 0) or 0),
                    "failed_scenario_count": int(summary.get("failed_scenario_count", 0) or 0),
                }
            )
    return rows


def _result_event_count(result: JSONDict) -> int:
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


def _optional_float(value: object) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _format_number(value: object) -> str:
    if value is None:
        return ""
    return f"{float(value):.4f}"


def _markdown_join(values: object) -> str:
    if not isinstance(values, list) or not values:
        return ""
    return "<br>".join(f"`{value}`" for value in values)

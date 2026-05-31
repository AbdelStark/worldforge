"""Render preserved-run comparison payloads."""

from __future__ import annotations

import csv
import io

from worldforge.models import JSONDict, dump_json
from worldforge.report_renderers import ReportRenderer, register_report_renderer


def comparison_to_markdown(payload: JSONDict) -> str:
    """Render a comparison payload as Markdown."""

    if payload.get("mode") == "regression":
        return regression_to_markdown(payload)

    lines = _comparison_header_markdown_lines(payload)
    lines.extend(_comparison_context_markdown_lines(payload["comparison_context"]))
    lines.extend(_comparison_runs_markdown_lines(payload["runs"]))
    lines.extend(_comparison_rows_markdown_lines(payload))
    return "\n".join(lines)


def _comparison_header_markdown_lines(payload: JSONDict) -> list[str]:
    return [
        "# WorldForge Run Comparison",
        "",
        f"Kind: {payload['kind']}",
        f"Baseline: `{payload['baseline_run_id']}`",
        f"Claim boundary: {payload.get('claim_boundary') or '-'}",
        "",
    ]


def _comparison_context_markdown_lines(context: JSONDict) -> list[str]:
    return [
        "## Comparison Context",
        "",
        f"- Capabilities: {_markdown_join(context.get('capabilities')) or '-'}",
        f"- Operations: {_markdown_join(context.get('operations')) or '-'}",
        f"- Fixture digest: `{context.get('fixture_digest') or '-'}`",
        f"- Suite version: `{context.get('suite_version') or '-'}`",
        f"- Budget refs: {_markdown_join(context.get('budget_refs')) or '-'}",
        "",
    ]


def _comparison_runs_markdown_lines(runs: list[JSONDict]) -> list[str]:
    lines = [
        "## Runs",
        "",
        (
            "| run_id | date | status | command | provider | operation | evidence | skip reason | "
            "artifacts | provenance |"
        ),
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    lines.extend(
        (
            "| "
            f"`{run['run_id']}` | {run['created_at']} | {run['status']} | "
            f"`{run['command']}` | {run['provider']} | {run['operation']} | "
            f"{_markdown_join(run['missing_evidence']) or 'complete'} | "
            f"{run['skip_reason'] or ''} | "
            f"{_markdown_join(run['artifact_refs'])} | {_markdown_join(run['provenance_refs'])} |"
        )
        for run in runs
    )
    return lines


def _comparison_rows_markdown_lines(payload: JSONDict) -> list[str]:
    if payload["kind"] == "benchmark":
        return _benchmark_rows_markdown_lines(payload["rows"])
    if payload["kind"] == "eval":
        return _evaluation_rows_markdown_lines(payload["rows"])
    return _demo_showcase_rows_markdown_lines(payload["rows"])


def _benchmark_rows_markdown_lines(rows: list[JSONDict]) -> list[str]:
    lines = [
        "",
        "## Benchmark Rows",
        "",
        (
            "| run_id | provider | capability | operation | ok | errors | retries | "
            "avg_ms | delta_avg_ms | p95_ms | throughput/s | events | budget |"
        ),
        ("| --- | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |"),
    ]
    lines.extend(
        (
            "| "
            f"`{row['run_id']}` | {row['provider']} | {row['capability']} | "
            f"{row['operation']} | "
            f"{row['success_count']}/{row['iterations']} | {row['error_count']} | "
            f"{row['retry_count']} | {_format_number(row['average_latency_ms'])} | "
            f"{_format_number(row['delta_average_latency_ms'])} | "
            f"{_format_number(row['p95_latency_ms'])} | "
            f"{_format_number(row['throughput_per_second'])} | {row['event_count']} | "
            f"{_budget_label(row)} |"
        )
        for row in rows
    )
    return lines


def _evaluation_rows_markdown_lines(rows: list[JSONDict]) -> list[str]:
    lines = [
        "",
        "## Evaluation Rows",
        "",
        (
            "| run_id | provider | capability | suite | average_score | "
            "delta_average_score | passed | scenarios | events |"
        ),
        "| --- | --- | --- | --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    lines.extend(
        (
            "| "
            f"`{row['run_id']}` | {row['provider']} | {row['capability']} | "
            f"{row['suite_id']} | "
            f"{_format_number(row['average_score'])} | "
            f"{_format_number(row['delta_average_score'])} | "
            f"{row['passed_scenario_count']}/{row['scenario_count']} | "
            f"{row['scenario_count']} | {row['event_count']} |"
        )
        for row in rows
    )
    return lines


def _demo_showcase_rows_markdown_lines(rows: list[JSONDict]) -> list[str]:
    lines = [
        "",
        "## Demo Showcase Rows",
        "",
        "| run_id | workflow | status | safe_to_attach | summary |",
        "| --- | --- | --- | --- | --- |",
    ]
    lines.extend(
        (
            "| "
            f"`{row['run_id']}` | {row['workflow']} | {row['status']} | "
            f"{row['safe_to_attach']} | {row['summary']} |"
        )
        for row in rows
    )
    return lines


def regression_to_markdown(payload: JSONDict) -> str:
    """Render a regression comparison payload as Markdown."""

    summary = _json_object(payload.get("regression_summary"))
    artifact_changes = _json_object(payload.get("artifact_changes"))
    failure_changes = _json_object(payload.get("failure_changes"))
    provenance_changes = _json_object(payload.get("provenance_changes"))
    budget_changes = _json_object(payload.get("budget_status_changes"))
    lines = [
        "# WorldForge Regression Comparison",
        "",
        f"Kind: {payload['kind']}",
        f"Baseline: `{payload['baseline_run_id']}`",
        f"Candidate: `{payload['candidate_run_id']}`",
        f"Status: `{summary.get('status', 'unknown')}`",
        f"Claim boundary: {payload.get('claim_boundary') or '-'}",
        "",
        "## Regression Summary",
        "",
        f"- Metric deltas: `{summary.get('metric_delta_count', 0)}`",
        f"- Regressed metrics: `{summary.get('regressed_metric_count', 0)}`",
        f"- Improved metrics: `{summary.get('improved_metric_count', 0)}`",
        f"- New failures: `{summary.get('new_failure_count', 0)}`",
        f"- Removed failures: `{summary.get('removed_failure_count', 0)}`",
        f"- Artifact drift: `{summary.get('artifact_drift_count', 0)}`",
        (f"- Unsafe artifact exclusions: `{summary.get('unsafe_artifact_exclusion_count', 0)}`"),
        "",
        "## Metric Deltas",
        "",
        "| Metric | Baseline | Candidate | Delta | Status |",
        "| --- | ---: | ---: | ---: | --- |",
    ]
    if payload.get("metric_deltas"):
        lines.extend(
            (
                "| "
                f"`{metric['metric']}` | {_format_number(metric.get('baseline'))} | "
                f"{_format_number(metric.get('candidate'))} | "
                f"{_format_number(metric.get('delta'))} | `{metric['status']}` |"
            )
            for metric in payload["metric_deltas"]
            if isinstance(metric, dict)
        )
    else:
        lines.append("| none |  |  |  | `unchanged` |")

    lines.extend(
        [
            "",
            "## Budget Status",
            "",
            (
                f"- Baseline: `{budget_changes.get('baseline_status', 'not-recorded')}`; "
                f"Candidate: `{budget_changes.get('candidate_status', 'not-recorded')}`; "
                f"Status: `{budget_changes.get('status', 'not-recorded')}`"
            ),
            "",
            "## Failures",
            "",
            f"- New failures: {_markdown_join(failure_changes.get('new_failures')) or 'none'}",
            (
                "- Removed failures: "
                f"{_markdown_join(failure_changes.get('removed_failures')) or 'none'}"
            ),
            "",
            "## Artifact Drift",
            "",
            f"- Added safe artifacts: {_markdown_join(artifact_changes.get('added')) or 'none'}",
            (
                "- Removed safe artifacts: "
                f"{_markdown_join(artifact_changes.get('removed')) or 'none'}"
            ),
            (
                "- Changed safe artifacts: "
                f"{_markdown_join(artifact_changes.get('changed')) or 'none'}"
            ),
            (
                "- Unsafe artifacts excluded from rendered reports: "
                f"`{artifact_changes.get('excluded_unsafe_count', 0)}`"
            ),
            "",
            "## Provenance Differences",
            "",
            (f"- Differences: {_markdown_join(provenance_changes.get('differences')) or 'none'}"),
        ]
    )
    return "\n".join(lines)


def comparison_to_csv(payload: JSONDict) -> str:
    """Render a comparison payload as stable CSV."""

    if payload.get("mode") == "regression":
        return regression_to_csv(payload)

    buffer = io.StringIO()
    fieldnames = _comparison_csv_fields(payload["kind"])
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


def _comparison_csv_fields(kind: str) -> list[str]:
    if kind == "benchmark":
        return [
            "run_id",
            "created_at",
            "command",
            "provider",
            "capability",
            "operation",
            "fixture_digest",
            "suite_version",
            "budget_ref",
            "budget_passed",
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
    if kind == "eval":
        return [
            "run_id",
            "created_at",
            "command",
            "provider",
            "capability",
            "suite_id",
            "fixture_digest",
            "suite_version",
            "average_score",
            "delta_average_score",
            "scenario_count",
            "passed_scenario_count",
            "failed_scenario_count",
            "event_count",
            "artifact_refs_json",
            "provenance_refs_json",
        ]
    return [
        "run_id",
        "created_at",
        "command",
        "provider",
        "workflow",
        "status",
        "safe_to_attach",
        "summary",
        "artifact_refs_json",
        "provenance_refs_json",
    ]


def regression_to_csv(payload: JSONDict) -> str:
    """Render regression comparison rows as stable CSV."""

    fieldnames = ["category", "name", "status", "baseline", "candidate", "delta", "detail"]
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=fieldnames)
    writer.writeheader()
    for row in payload.get("rows", []):
        if isinstance(row, dict):
            writer.writerow({field: row.get(field, "") for field in fieldnames})
    return buffer.getvalue().strip()


def register_builtin_comparison_renderers(
    *,
    comparison_schema_version: int,
    regression_schema_version: int,
) -> None:
    schemas = (
        f"comparison:{comparison_schema_version}",
        f"regression:{regression_schema_version}",
    )
    for output_format, media_type, renderer in (
        ("json", "application/json", _comparison_json_renderer),
        ("markdown", "text/markdown", comparison_to_markdown),
        ("csv", "text/csv", comparison_to_csv),
        ("html", "text/html", _comparison_html_renderer),
    ):
        register_report_renderer(
            ReportRenderer(
                artifact_family="comparison",
                output_format=output_format,
                media_type=media_type,
                supported_schemas=schemas,
                safe_to_attach=True,
                render=renderer,
                description=f"Built-in preserved run comparison {output_format} renderer.",
            ),
            replace=True,
        )


def _comparison_json_renderer(payload: JSONDict) -> str:
    return dump_json(payload, indent=2)


def _comparison_html_renderer(payload: JSONDict) -> str:
    from worldforge.html_report import render_comparison_html

    return render_comparison_html(payload)


def _json_object(value: object) -> JSONDict:
    return value if isinstance(value, dict) else {}


def _budget_label(row: JSONDict) -> str:
    verdict = row.get("budget_passed")
    budget_ref = row.get("budget_ref")
    if verdict is True:
        status = "passed"
    elif verdict is False:
        status = "failed"
    else:
        status = "not recorded"
    return f"{status} `{budget_ref}`" if budget_ref else status


def _format_number(value: object) -> str:
    if value is None:
        return ""
    return f"{float(value):.4f}"


def _markdown_join(values: object) -> str:
    if not isinstance(values, list) or not values:
        return ""
    return "<br>".join(f"`{value}`" for value in values)

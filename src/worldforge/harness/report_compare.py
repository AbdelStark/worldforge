"""Compare preserved WorldForge run reports."""

from __future__ import annotations

import csv
import hashlib
import io
import json
from dataclasses import dataclass
from pathlib import Path

from worldforge.models import JSONDict, WorldForgeError, dump_json
from worldforge.report_renderers import (
    ReportRenderer,
    register_report_renderer,
    render_report_artifact,
)

_SUPPORTED_KINDS = {"benchmark", "demo_showcase", "eval"}
_COMPARISON_SCHEMA_VERSION = 2
_REGRESSION_SCHEMA_VERSION = 1
_SAFE_ARTIFACT_SUFFIXES = {".csv", ".html", ".json", ".jsonl", ".md", ".txt"}


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

    _validate_manifest_schema(manifest, run_path=run_path)
    report_path = (
        source
        if source.is_file() and source.name != "run_manifest.json"
        else _report_path(run_path, kind=kind, manifest=manifest)
    )
    report = _read_json_object(report_path, name="run report")
    _validate_report_kind(kind, report, report_path=report_path)
    return PreservedRunReport(
        manifest=manifest,
        report=report,
        run_path=run_path.resolve(),
        report_path=report_path.resolve(),
    )


def compare_preserved_run_reports(paths: list[Path], *, mode: str = "comparison") -> JSONDict:
    """Return a stable, issue-attachable comparison payload for preserved runs."""

    if mode == "regression":
        return compare_preserved_run_regression(paths)
    if mode != "comparison":
        raise WorldForgeError("runs compare mode must be comparison or regression.")
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
    contexts = [_comparison_context(report) for report in reports]
    _ensure_compatible_contexts(kind, contexts)
    if kind == "benchmark":
        rows = _benchmark_rows(reports, contexts)
    elif kind == "eval":
        rows = _evaluation_rows(reports, contexts)
    else:
        rows = _demo_showcase_rows(reports, contexts)
    payload: JSONDict = {
        "schema_version": _COMPARISON_SCHEMA_VERSION,
        "kind": kind,
        "baseline_run_id": reports[0].run_id,
        "run_count": len(reports),
        "claim_boundary": _comparison_claim_boundary(reports),
        "comparison_context": _shared_context(kind, contexts),
        "runs": [
            _run_summary(report, context) for report, context in zip(reports, contexts, strict=True)
        ],
        "rows": rows,
    }
    dump_json(payload)
    return payload


def compare_preserved_run_regression(paths: list[Path]) -> JSONDict:
    """Compare one candidate run against one preserved baseline run."""

    if len(paths) != 2:
        raise WorldForgeError(
            "runs compare --mode regression requires exactly one baseline and one candidate run."
        )
    labels = ("Baseline", "Candidate")
    for label, path in zip(labels, paths, strict=True):
        if not path.expanduser().exists():
            raise WorldForgeError(f"{label} run does not exist: {path}")
    reports = [load_preserved_run_report(path) for path in paths]
    if reports[0].kind != reports[1].kind:
        raise WorldForgeError(
            "Cannot compare incompatible regression runs: "
            f"{reports[0].run_id}:{reports[0].kind}, {reports[1].run_id}:{reports[1].kind}."
        )
    kind = reports[0].kind
    contexts = [_comparison_context(report) for report in reports]
    _ensure_compatible_contexts(kind, contexts)
    runs = [
        _run_summary(report, context) for report, context in zip(reports, contexts, strict=True)
    ]
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
    payload: JSONDict = {
        "schema_version": _REGRESSION_SCHEMA_VERSION,
        "mode": "regression",
        "kind": kind,
        "baseline_run_id": reports[0].run_id,
        "candidate_run_id": reports[1].run_id,
        "run_count": 2,
        "claim_boundary": _comparison_claim_boundary(reports),
        "comparison_context": _shared_context(kind, contexts),
        "runs": runs,
        "regression_summary": summary,
        "metric_deltas": metric_deltas,
        "budget_status_changes": budget_changes,
        "failure_changes": failure_changes,
        "artifact_changes": artifact_changes,
        "provenance_changes": provenance_changes,
        "rows": rows,
    }
    dump_json(payload)
    return payload


def comparison_to_markdown(payload: JSONDict) -> str:
    """Render a comparison payload as Markdown."""

    if payload.get("mode") == "regression":
        return regression_to_markdown(payload)

    lines = [
        "# WorldForge Run Comparison",
        "",
        f"Kind: {payload['kind']}",
        f"Baseline: `{payload['baseline_run_id']}`",
        f"Claim boundary: {payload.get('claim_boundary') or '-'}",
        "",
        "## Comparison Context",
        "",
        (
            "- Capabilities: "
            f"{_markdown_join(payload['comparison_context'].get('capabilities')) or '-'}"
        ),
        f"- Operations: {_markdown_join(payload['comparison_context'].get('operations')) or '-'}",
        f"- Fixture digest: `{payload['comparison_context'].get('fixture_digest') or '-'}`",
        f"- Suite version: `{payload['comparison_context'].get('suite_version') or '-'}`",
        f"- Budget refs: {_markdown_join(payload['comparison_context'].get('budget_refs')) or '-'}",
        "",
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
        for run in payload["runs"]
    )

    if payload["kind"] == "benchmark":
        lines.extend(
            [
                "",
                "## Benchmark Rows",
                "",
                (
                    "| run_id | provider | capability | operation | ok | errors | retries | "
                    "avg_ms | delta_avg_ms | p95_ms | throughput/s | events | budget |"
                ),
                (
                    "| --- | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | "
                    "---: | ---: | --- |"
                ),
            ]
        )
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
            for row in payload["rows"]
        )
    elif payload["kind"] == "eval":
        lines.extend(
            [
                "",
                "## Evaluation Rows",
                "",
                (
                    "| run_id | provider | capability | suite | average_score | "
                    "delta_average_score | passed | scenarios | events |"
                ),
                "| --- | --- | --- | --- | ---: | ---: | ---: | ---: | ---: |",
            ]
        )
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
            for row in payload["rows"]
        )
    else:
        lines.extend(
            [
                "",
                "## Demo Showcase Rows",
                "",
                "| run_id | workflow | status | safe_to_attach | summary |",
                "| --- | --- | --- | --- | --- |",
            ]
        )
        lines.extend(
            (
                "| "
                f"`{row['run_id']}` | {row['workflow']} | {row['status']} | "
                f"{row['safe_to_attach']} | {row['summary']} |"
            )
            for row in payload["rows"]
        )
    return "\n".join(lines)


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
    if payload["kind"] == "benchmark":
        fieldnames = [
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
    elif payload["kind"] == "eval":
        fieldnames = [
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
    else:
        fieldnames = [
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


def comparison_artifact(payload: JSONDict, *, output_format: str) -> str:
    """Render a comparison payload in one of the public export formats."""

    try:
        return render_report_artifact("comparison", output_format, payload).content
    except WorldForgeError as exc:
        if "No report renderer registered" in str(exc):
            raise WorldForgeError(
                "comparison format must be a registered renderer; built-ins are "
                "json, markdown, csv, or html."
            ) from exc
        raise


def _comparison_json_renderer(payload: JSONDict) -> str:
    return json.dumps(payload, indent=2, sort_keys=True)


def _comparison_html_renderer(payload: JSONDict) -> str:
    from worldforge.html_report import render_comparison_html

    return render_comparison_html(payload)


def _register_builtin_report_renderers() -> None:
    schemas = (
        f"comparison:{_COMPARISON_SCHEMA_VERSION}",
        f"regression:{_REGRESSION_SCHEMA_VERSION}",
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


_register_builtin_report_renderers()


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


def _validate_manifest_schema(manifest: JSONDict, *, run_path: Path) -> None:
    schema_version = manifest.get("schema_version")
    if schema_version != 1:
        raise WorldForgeError(
            f"Run {manifest.get('run_id', run_path.name)} uses unsupported run workspace "
            f"schema_version {schema_version!r}; expected 1."
        )


def _report_path(run_path: Path, *, kind: str, manifest: JSONDict) -> Path:
    if kind == "demo_showcase":
        artifact_paths = manifest.get("artifact_paths", {})
        if isinstance(artifact_paths, dict) and isinstance(artifact_paths.get("summary_json"), str):
            return run_path / artifact_paths["summary_json"]
        return run_path / "results" / "summary.json"
    return run_path / "reports" / "report.json"


def _validate_report_kind(kind: str, report: JSONDict, *, report_path: Path) -> None:
    if kind == "benchmark" and not isinstance(report.get("results"), list):
        raise WorldForgeError(f"Benchmark report {report_path} must contain a results list.")
    if kind == "eval" and not isinstance(report.get("provider_summaries"), list):
        raise WorldForgeError(f"Evaluation report {report_path} must contain provider_summaries.")
    if kind == "demo_showcase" and not (
        isinstance(report.get("status"), str) or isinstance(report.get("summary"), str)
    ):
        raise WorldForgeError(f"Demo showcase report {report_path} must contain status or summary.")


def _comparison_context(report: PreservedRunReport) -> JSONDict:
    provenance = _json_object(report.report.get("provenance"))
    run_metadata = _json_object(report.report.get("run_metadata"))
    input_summary = _json_object(report.manifest.get("input_summary"))
    result_summary = _json_object(report.manifest.get("result_summary"))
    providers = (
        _strings(provenance.get("providers"))
        or _report_providers(report)
        or _strings(input_summary.get("providers"))
        or _strings((report.manifest.get("provider"),))
    )
    operations = (
        _report_operations(report)
        or _strings(input_summary.get("operations"))
        or _strings((report.manifest.get("operation"),))
    )
    capabilities = (
        _strings(provenance.get("capabilities"))
        or _strings(input_summary.get("capabilities"))
        or (operations if report.kind == "benchmark" else [])
    )
    budget_ref = _budget_ref(
        _json_object(provenance.get("budget_file")) or _json_object(run_metadata.get("budget_file"))
    )
    context: JSONDict = {
        "run_id": report.run_id,
        "providers": providers,
        "operations": operations,
        "capabilities": capabilities,
        "fixture_digest": _fixture_digest(report, provenance=provenance, run_metadata=run_metadata),
        "suite_version": _optional_text(provenance.get("suite_version")),
        "budget_ref": budget_ref,
        "budget_passed": _budget_passed(report.report, result_summary=result_summary),
        "event_count": _context_event_count(report, provenance=provenance),
        "skip_reason": _skip_reason(report.manifest, result_summary=result_summary),
    }
    context["missing_evidence"] = _missing_evidence(report.kind, context)
    return context


def _ensure_compatible_contexts(kind: str, contexts: list[JSONDict]) -> None:
    _ensure_matching_context_field(kind, contexts, field="operations", label="operation")
    _ensure_matching_context_field(kind, contexts, field="capabilities", label="capability")
    _ensure_matching_context_field(kind, contexts, field="fixture_digest", label="fixture digest")
    _ensure_matching_context_field(kind, contexts, field="suite_version", label="suite version")
    _ensure_matching_context_field(kind, contexts, field="budget_ref", label="budget")


def _ensure_matching_context_field(
    kind: str,
    contexts: list[JSONDict],
    *,
    field: str,
    label: str,
) -> None:
    values = [
        (str(context["run_id"]), _comparison_field_value(context.get(field)))
        for context in contexts
        if _comparison_field_value(context.get(field)) is not None
    ]
    if len({value for _, value in values}) <= 1:
        return
    details = ", ".join(f"{run_id}:{value}" for run_id, value in values)
    raise WorldForgeError(f"Cannot compare incompatible {kind} runs: {label} mismatch ({details}).")


def _comparison_field_value(value: object) -> str | None:
    if isinstance(value, list):
        normalized = sorted(str(item) for item in value if str(item))
        return ",".join(normalized) if normalized else None
    if isinstance(value, str):
        stripped = value.strip()
        return stripped or None
    return None


def _shared_context(kind: str, contexts: list[JSONDict]) -> JSONDict:
    return {
        "kind": kind,
        "providers": _sorted_union(context.get("providers") for context in contexts),
        "capabilities": _sorted_union(context.get("capabilities") for context in contexts),
        "operations": _sorted_union(context.get("operations") for context in contexts),
        "fixture_digest": _shared_scalar(contexts, "fixture_digest"),
        "suite_version": _shared_scalar(contexts, "suite_version"),
        "budget_refs": _sorted_union(
            [context["budget_ref"]] for context in contexts if context.get("budget_ref")
        ),
        "missing_evidence": _sorted_union(context.get("missing_evidence") for context in contexts),
    }


def _shared_scalar(contexts: list[JSONDict], field: str) -> str | None:
    values = [str(context[field]) for context in contexts if isinstance(context.get(field), str)]
    return values[0] if values else None


def _comparison_claim_boundary(reports: list[PreservedRunReport]) -> str:
    boundaries: list[str] = []
    for report in reports:
        for value in (
            report.report.get("claim_boundary"),
            _json_object(report.report.get("provenance")).get("claim_boundary"),
        ):
            text = _optional_text(value)
            if text and text not in boundaries:
                boundaries.append(text)
    if len(boundaries) == 1:
        return boundaries[0]
    if boundaries:
        return (
            "Run-specific claim boundaries differ; this comparison is limited to preserved "
            f"WorldForge artifacts. Boundaries: {' | '.join(boundaries)}"
        )
    return (
        "This comparison is limited to preserved WorldForge run artifacts with matching "
        "capability, operation, fixture, budget, and suite context; it is not a public "
        "leaderboard or cross-task ranking."
    )


def _run_summary(report: PreservedRunReport, context: JSONDict) -> JSONDict:
    safe_artifacts, excluded_unsafe_count = _safe_artifact_map(report)
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
        "artifact_refs": [artifact["path"] for artifact in safe_artifacts.values()],
        "safe_artifacts": safe_artifacts,
        "excluded_unsafe_artifact_count": excluded_unsafe_count,
        "provenance_refs": provenance_refs,
        "providers": list(context["providers"]),
        "capabilities": list(context["capabilities"]),
        "operations": list(context["operations"]),
        "fixture_digest": context["fixture_digest"],
        "suite_version": context["suite_version"],
        "budget_ref": context["budget_ref"],
        "budget_passed": context["budget_passed"],
        "skip_reason": context["skip_reason"],
        "missing_evidence": list(context["missing_evidence"]),
        "event_count": int(context["event_count"]),
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


def _safe_artifact_map(report: PreservedRunReport) -> tuple[dict[str, JSONDict], int]:
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


def _benchmark_rows(reports: list[PreservedRunReport], contexts: list[JSONDict]) -> list[JSONDict]:
    baseline: dict[tuple[str, str], float | None] = {}
    baseline_by_operation: dict[str, float | None] = {}
    rows: list[JSONDict] = []
    for report_index, (report, context) in enumerate(zip(reports, contexts, strict=True)):
        for result in report.report.get("results", []):
            if not isinstance(result, dict):
                continue
            key = (str(result.get("provider", "")), str(result.get("operation", "")))
            avg = _optional_float(result.get("average_latency_ms"))
            if report_index == 0:
                baseline[key] = avg
                baseline_by_operation.setdefault(key[1], avg)
            baseline_avg = baseline.get(key, baseline_by_operation.get(key[1]))
            event_count = _result_event_count(result)
            row: JSONDict = {
                "run_id": report.run_id,
                "provider": key[0],
                "capability": _row_capability(context, fallback=key[1]),
                "operation": key[1],
                "fixture_digest": context["fixture_digest"],
                "suite_version": context["suite_version"],
                "budget_ref": context["budget_ref"],
                "budget_passed": context["budget_passed"],
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
                "event_count": event_count or int(context["event_count"]),
            }
            rows.append(row)
    return rows


def _evaluation_rows(reports: list[PreservedRunReport], contexts: list[JSONDict]) -> list[JSONDict]:
    baseline: dict[str, float | None] = {}
    baseline_average: float | None = None
    rows: list[JSONDict] = []
    for report_index, (report, context) in enumerate(zip(reports, contexts, strict=True)):
        for summary in report.report.get("provider_summaries", []):
            if not isinstance(summary, dict):
                continue
            provider = str(summary.get("provider", ""))
            avg = _optional_float(summary.get("average_score"))
            if report_index == 0:
                baseline[provider] = avg
                if baseline_average is None:
                    baseline_average = avg
            baseline_avg = baseline.get(provider, baseline_average)
            rows.append(
                {
                    "run_id": report.run_id,
                    "provider": provider,
                    "capability": _row_capability(context, fallback=""),
                    "suite_id": _evaluation_suite_id(report, context),
                    "fixture_digest": context["fixture_digest"],
                    "suite_version": context["suite_version"],
                    "average_score": avg,
                    "delta_average_score": (
                        None if avg is None or baseline_avg is None else avg - baseline_avg
                    ),
                    "scenario_count": int(summary.get("scenario_count", 0) or 0),
                    "passed_scenario_count": int(summary.get("passed_scenario_count", 0) or 0),
                    "failed_scenario_count": int(summary.get("failed_scenario_count", 0) or 0),
                    "event_count": int(context["event_count"]),
                }
            )
    return rows


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


def _regression_metric_deltas(
    kind: str,
    reports: list[PreservedRunReport],
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


def _regression_failure_changes(reports: list[PreservedRunReport]) -> JSONDict:
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


def _regression_artifact_changes(reports: list[PreservedRunReport]) -> JSONDict:
    baseline, baseline_excluded = _safe_artifact_map(reports[0])
    candidate, candidate_excluded = _safe_artifact_map(reports[1])
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


def _report_providers(report: PreservedRunReport) -> list[str]:
    if report.kind == "benchmark":
        return _strings(
            result.get("provider")
            for result in report.report.get("results", [])
            if isinstance(result, dict)
        )
    return _strings(
        summary.get("provider")
        for summary in report.report.get("provider_summaries", [])
        if isinstance(summary, dict)
    )


def _report_operations(report: PreservedRunReport) -> list[str]:
    if report.kind == "benchmark":
        return _strings(
            result.get("operation")
            for result in report.report.get("results", [])
            if isinstance(result, dict)
        )
    if report.kind == "demo_showcase":
        workflow = _json_object(report.manifest.get("input_summary")).get("workflow")
        return _strings((workflow, report.manifest.get("operation")))
    suite_id = _optional_text(report.report.get("suite_id"))
    return [suite_id] if suite_id else []


def _fixture_digest(
    report: PreservedRunReport,
    *,
    provenance: JSONDict,
    run_metadata: JSONDict,
) -> str | None:
    input_file = _json_object(run_metadata.get("input_file"))
    input_file_digest = _normalized_digest(input_file.get("sha256"))
    if input_file_digest is not None:
        return input_file_digest
    for source in (
        report.manifest.get("input_digest"),
        _json_object(report.manifest.get("input_summary")).get("input_digest"),
        provenance.get("input_digest"),
    ):
        digest = _normalized_digest(source)
        if digest is not None:
            return digest
    return None


def _budget_ref(value: JSONDict) -> str | None:
    path = _optional_text(value.get("path"))
    if path is None:
        return None
    digest = _normalized_digest(value.get("sha256"))
    return f"{path}#{digest}" if digest is not None else path


def _budget_passed(report: JSONDict, *, result_summary: JSONDict) -> bool | None:
    for value in (
        result_summary.get("budget_passed"),
        _json_object(report.get("budget")).get("passed"),
        _json_object(report.get("gate")).get("passed"),
    ):
        if isinstance(value, bool):
            return value
    return None


def _context_event_count(report: PreservedRunReport, *, provenance: JSONDict) -> int:
    for value in (provenance.get("event_count"), report.manifest.get("event_count")):
        if isinstance(value, int):
            return max(value, 0)
    return 0


def _skip_reason(manifest: JSONDict, *, result_summary: JSONDict) -> str | None:
    for value in (
        manifest.get("skip_reason"),
        result_summary.get("skip_reason"),
        result_summary.get("reason"),
    ):
        text = _optional_text(value)
        if text:
            return text
    if manifest.get("status") == "skipped":
        return "run status is skipped"
    return None


def _missing_evidence(kind: str, context: JSONDict) -> list[str]:
    missing = []
    if kind in {"benchmark", "eval"} and not context["capabilities"]:
        missing.append("capability")
    if kind in {"benchmark", "eval"} and not context["fixture_digest"]:
        missing.append("fixture_digest")
    if kind in {"benchmark", "eval"} and not context["suite_version"]:
        missing.append("suite_version")
    if kind == "benchmark" and context["budget_passed"] is None:
        missing.append("budget_status")
    return missing


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


def _benchmark_metric_values(report: PreservedRunReport) -> dict[str, float | None]:
    results = [result for result in report.report.get("results", []) if isinstance(result, dict)]
    if not results:
        return {}
    return {
        "average_latency_ms": _mean_optional_float(
            result.get("average_latency_ms") for result in results
        ),
        "p95_latency_ms": _mean_optional_float(result.get("p95_latency_ms") for result in results),
        "throughput_per_second": _mean_optional_float(
            result.get("throughput_per_second") for result in results
        ),
        "error_count": float(sum(int(result.get("error_count", 0) or 0) for result in results)),
        "retry_count": float(sum(int(result.get("retry_count", 0) or 0) for result in results)),
        "success_count": float(sum(int(result.get("success_count", 0) or 0) for result in results)),
    }


def _evaluation_metric_values(report: PreservedRunReport) -> dict[str, float | None]:
    summaries = [
        summary
        for summary in report.report.get("provider_summaries", [])
        if isinstance(summary, dict)
    ]
    if not summaries:
        return {}
    scenario_count = sum(int(summary.get("scenario_count", 0) or 0) for summary in summaries)
    passed = sum(int(summary.get("passed_scenario_count", 0) or 0) for summary in summaries)
    failed = sum(int(summary.get("failed_scenario_count", 0) or 0) for summary in summaries)
    return {
        "average_score": _mean_optional_float(
            summary.get("average_score") for summary in summaries
        ),
        "pass_rate": None if scenario_count <= 0 else passed / scenario_count,
        "passed_scenario_count": float(passed),
        "failed_scenario_count": float(failed),
    }


def _demo_metric_values(report: PreservedRunReport) -> dict[str, float | None]:
    safe = bool(
        report.report.get(
            "safe_to_attach",
            _json_object(report.manifest.get("result_summary")).get("safe_to_attach", False),
        )
    )
    return {"safe_to_attach": 1.0 if safe else 0.0}


def _mean_optional_float(values: object) -> float | None:
    numbers = [
        number
        for number in (_optional_float(value) for value in values)  # type: ignore[union-attr]
        if number is not None
    ]
    return sum(numbers) / len(numbers) if numbers else None


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


def _failure_fingerprints(report: PreservedRunReport) -> list[str]:
    failures: list[str] = []
    result_summary = _json_object(report.manifest.get("result_summary"))
    if str(report.manifest.get("status")) in {"failed", "cancelled", "skipped"}:
        reason = (
            _optional_text(result_summary.get("failure_reason"))
            or _optional_text(result_summary.get("skip_reason"))
            or _optional_text(result_summary.get("reason"))
            or str(report.manifest.get("status"))
        )
        failures.append(f"run:{report.manifest.get('status')}:{reason}")
    if report.kind == "benchmark":
        for result in report.report.get("results", []):
            if not isinstance(result, dict):
                continue
            operation = result.get("operation", "")
            failures.extend(
                f"benchmark:{operation}:{_failure_text(error)}"
                for error in result.get("errors", []) or []
            )
            error_count = int(result.get("error_count", 0) or 0)
            if error_count and not result.get("errors"):
                failures.append(f"benchmark:{operation}:error_count={error_count}")
    elif report.kind == "eval":
        failures.extend(
            "eval:"
            f"{result.get('provider', '')}:"
            f"{result.get('scenario', '')}:"
            f"{_failure_text(result.get('details') or result.get('error') or 'failed')}"
            for result in report.report.get("results", [])
            if isinstance(result, dict) and result.get("passed") is False
        )
    elif (
        report.kind == "demo_showcase"
        and not failures
        and str(report.report.get("status", "passed")) != "passed"
    ):
        failures.append(f"demo:{_demo_workflow(report, {})}:{report.report.get('status')}")
    return sorted(dict.fromkeys(failures))


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


def _optional_text(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    stripped = value.strip()
    return stripped or None


def _normalized_digest(value: object) -> str | None:
    text = _optional_text(value)
    if text is None:
        return None
    return text if text.startswith("sha256:") else f"sha256:{text}"


def _json_object(value: object) -> JSONDict:
    return dict(value) if isinstance(value, dict) else {}


def _strings(values: object) -> list[str]:
    if isinstance(values, str):
        raw_values = [values]
    else:
        try:
            raw_values = list(values)  # type: ignore[arg-type]
        except TypeError:
            raw_values = []
    normalized: list[str] = []
    for value in raw_values:
        if not isinstance(value, str):
            continue
        stripped = value.strip()
        if stripped and stripped not in normalized:
            normalized.append(stripped)
    return normalized


def _sorted_union(values: object) -> list[str]:
    union: set[str] = set()
    if isinstance(values, list):
        iterable = values
    else:
        try:
            iterable = list(values)  # type: ignore[arg-type]
        except TypeError:
            iterable = []
    for value in iterable:
        if isinstance(value, str):
            if value:
                union.add(value)
        elif isinstance(value, list):
            union.update(str(item) for item in value if str(item))
    return sorted(union)


def _budget_label(row: JSONDict) -> str:
    verdict = row.get("budget_passed")
    if verdict is True:
        status = "passed"
    elif verdict is False:
        status = "failed"
    else:
        status = "not recorded"
    budget_ref = row.get("budget_ref")
    return f"{status} `{budget_ref}`" if budget_ref else status


def _format_number(value: object) -> str:
    if value is None:
        return ""
    return f"{float(value):.4f}"


def _markdown_join(values: object) -> str:
    if not isinstance(values, list) or not values:
        return ""
    return "<br>".join(f"`{value}`" for value in values)

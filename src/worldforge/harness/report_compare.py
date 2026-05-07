"""Compare preserved WorldForge run reports."""

from __future__ import annotations

import csv
import io
import json
from dataclasses import dataclass
from pathlib import Path

from worldforge.models import JSONDict, WorldForgeError, dump_json

_SUPPORTED_KINDS = {"benchmark", "eval"}
_COMPARISON_SCHEMA_VERSION = 2


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
    contexts = [_comparison_context(report) for report in reports]
    _ensure_compatible_contexts(kind, contexts)
    rows = (
        _benchmark_rows(reports, contexts)
        if kind == "benchmark"
        else _evaluation_rows(reports, contexts)
    )
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


def comparison_to_markdown(payload: JSONDict) -> str:
    """Render a comparison payload as Markdown."""

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
    else:
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
    else:
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
    if output_format == "html":
        from worldforge.html_report import render_comparison_html

        return render_comparison_html(payload)
    raise WorldForgeError("comparison format must be json, markdown, csv, or html.")


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
    if not context["capabilities"]:
        missing.append("capability")
    if not context["fixture_digest"]:
        missing.append("fixture_digest")
    if not context["suite_version"]:
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

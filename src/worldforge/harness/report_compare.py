"""Compare preserved WorldForge run reports."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from worldforge.harness.report_compare_regression import (
    build_regression_payload,
)
from worldforge.harness.report_compare_regression import (
    safe_artifact_map as _safe_artifact_map,
)
from worldforge.harness.report_compare_rendering import (
    comparison_to_csv as comparison_to_csv,
)
from worldforge.harness.report_compare_rendering import (
    comparison_to_markdown as comparison_to_markdown,
)
from worldforge.harness.report_compare_rendering import (
    register_builtin_comparison_renderers,
)
from worldforge.harness.report_compare_rendering import (
    regression_to_csv as regression_to_csv,
)
from worldforge.harness.report_compare_rendering import (
    regression_to_markdown as regression_to_markdown,
)
from worldforge.harness.report_compare_rows import comparison_rows as _comparison_rows
from worldforge.models import JSONDict, WorldForgeError, dump_json, require_json_dict
from worldforge.report_renderers import render_report_artifact

_SUPPORTED_KINDS = {"benchmark", "demo_showcase", "eval"}
_COMPARISON_SCHEMA_VERSION = 2
_REGRESSION_SCHEMA_VERSION = 1


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
    _require_comparison_mode(mode)
    reports = _load_comparison_reports(paths)
    kind = _common_report_kind(reports)
    contexts = _compatible_comparison_contexts(kind, reports)
    payload = _comparison_payload(kind=kind, reports=reports, contexts=contexts)
    dump_json(payload)
    return payload


def _require_comparison_mode(mode: str) -> None:
    if mode != "comparison":
        raise WorldForgeError("runs compare mode must be comparison or regression.")


def _load_comparison_reports(paths: list[Path]) -> list[PreservedRunReport]:
    if len(paths) < 2:
        raise WorldForgeError(
            "runs compare requires at least two run directories or manifest paths."
        )
    return [load_preserved_run_report(path) for path in paths]


def _common_report_kind(reports: list[PreservedRunReport]) -> str:
    kinds = {report.kind for report in reports}
    if len(kinds) != 1:
        details = ", ".join(f"{report.run_id}:{report.kind}" for report in reports)
        raise WorldForgeError(f"Cannot compare incompatible report types: {details}.")
    return reports[0].kind


def _compatible_comparison_contexts(
    kind: str,
    reports: list[PreservedRunReport],
) -> list[JSONDict]:
    contexts = [_comparison_context(report) for report in reports]
    _ensure_compatible_contexts(kind, contexts)
    return contexts


def _comparison_payload(
    *,
    kind: str,
    reports: list[PreservedRunReport],
    contexts: list[JSONDict],
) -> JSONDict:
    return {
        "schema_version": _COMPARISON_SCHEMA_VERSION,
        "kind": kind,
        "baseline_run_id": reports[0].run_id,
        "run_count": len(reports),
        "claim_boundary": _comparison_claim_boundary(reports),
        "comparison_context": _shared_context(kind, contexts),
        "runs": [
            _run_summary(report, context) for report, context in zip(reports, contexts, strict=True)
        ],
        "rows": _comparison_rows(kind, reports, contexts),
    }


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
    payload = build_regression_payload(
        kind=kind,
        reports=reports,
        contexts=contexts,
        runs=runs,
        claim_boundary=_comparison_claim_boundary(reports),
        comparison_context=_shared_context(kind, contexts),
        schema_version=_REGRESSION_SCHEMA_VERSION,
    )
    dump_json(payload)
    return payload


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


def _register_builtin_report_renderers() -> None:
    register_builtin_comparison_renderers(
        comparison_schema_version=_COMPARISON_SCHEMA_VERSION,
        regression_schema_version=_REGRESSION_SCHEMA_VERSION,
    )


_register_builtin_report_renderers()


def _read_json_object(path: Path, *, name: str) -> JSONDict:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise WorldForgeError(f"Failed to read {name} {path}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise WorldForgeError(f"{name.title()} {path} must contain valid JSON: {exc}") from exc
    return require_json_dict(payload, name=f"{name.title()} {path}")


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

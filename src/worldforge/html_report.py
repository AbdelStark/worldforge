"""Static HTML export for WorldForge run artifacts.

Produces self-contained, sanitized HTML documents from existing safe artifacts:

- :func:`render_evaluation_html` — eval reports
- :func:`render_benchmark_html` — benchmark reports
- :func:`render_comparison_html` — preserved-run comparisons
- :func:`render_evidence_bundle_html` — evidence bundle summaries
- :func:`render_issue_bundle_html` — issue-ready bundle templates

Every render function returns a complete HTML document string with inline
styles. There are no external CSS/JS references, no JavaScript, no
network-loaded assets — the output is portable, drop-into-an-issue-attachment
HTML. Every user-supplied string is escaped via :func:`html.escape`; URLs and
host paths are rendered as plain text, never as anchor targets, so a malformed
manifest cannot smuggle an exfiltration link or an XSS payload into a shared
report.

Use HTML when an issue body needs a rendered table for non-developers, or
when local evidence has to be shared as a single static file. Prefer
JSON or Markdown for machine consumption and code review respectively.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from html import escape
from typing import TYPE_CHECKING, cast

from worldforge.models import JSONDict, WorldForgeError

if TYPE_CHECKING:
    from worldforge.benchmark import BenchmarkReport
    from worldforge.evaluation.report import EvaluationReport

HTML_REPORT_SCHEMA_VERSION = 1

_DOCUMENT_STYLE = (
    "body { font-family: -apple-system, BlinkMacSystemFont, "
    '"Segoe UI", Roboto, sans-serif; margin: 0; padding: 1.5rem; '
    "color: #1f2328; background: #ffffff; max-width: 64rem; } "
    "h1 { font-size: 1.5rem; margin-top: 0; "
    "border-bottom: 1px solid #d0d7de; padding-bottom: 0.4rem; } "
    "h2 { font-size: 1.15rem; margin-top: 1.5rem; "
    "border-bottom: 1px solid #eaeef2; padding-bottom: 0.2rem; } "
    "h3 { font-size: 1rem; margin-top: 1rem; } "
    "p, li { line-height: 1.5; } "
    "code, pre { font-family: ui-monospace, SFMono-Regular, "
    '"SF Mono", Menlo, monospace; '
    "background: #f6f8fa; padding: 0.1rem 0.3rem; border-radius: 0.2rem; } "
    "pre { padding: 0.6rem; overflow-x: auto; } "
    "table { border-collapse: collapse; margin: 0.6rem 0 1.2rem; "
    "width: 100%; font-size: 0.92rem; } "
    "th, td { border: 1px solid #d0d7de; padding: 0.35rem 0.55rem; "
    "text-align: left; vertical-align: top; } "
    "th { background: #f6f8fa; font-weight: 600; } "
    "tr:nth-child(even) td { background: #fbfcfd; } "
    ".numeric { text-align: right; font-variant-numeric: tabular-nums; } "
    ".muted { color: #57606a; } "
    "footer { margin-top: 2rem; font-size: 0.85rem; color: #57606a; "
    "border-top: 1px solid #eaeef2; padding-top: 0.6rem; } "
    ".warning { background: #fff8c5; border: 1px solid #d4a72c; "
    "padding: 0.6rem 0.8rem; border-radius: 0.3rem; margin: 0.8rem 0; }"
)


def _document(*, title: str, body: str, footer: str | None = None) -> str:
    """Wrap an HTML fragment in a full document with the shared inline stylesheet."""

    safe_title = escape(title, quote=True)
    safe_footer = escape(footer or "", quote=True) if footer else None
    parts = [
        "<!DOCTYPE html>",
        '<html lang="en">',
        "<head>",
        '<meta charset="utf-8">',
        '<meta name="viewport" content="width=device-width, initial-scale=1">',
        f"<title>{safe_title}</title>",
        f"<style>{_DOCUMENT_STYLE}</style>",
        "</head>",
        "<body>",
        body,
    ]
    if safe_footer:
        parts.append(f"<footer>{safe_footer}</footer>")
    parts.extend(["</body>", "</html>", ""])
    return "\n".join(parts)


def _table(
    headers: Sequence[str],
    rows: Iterable[Sequence[object]],
    *,
    numeric_columns: Sequence[int] = (),
) -> str:
    """Render a sanitized HTML table.

    Cell values are coerced via :class:`str` and escaped. ``numeric_columns``
    indices apply the right-aligned monospace ``numeric`` class.
    """

    numeric = set(numeric_columns)
    head = "".join(f"<th>{escape(str(h))}</th>" for h in headers)
    body_rows: list[str] = []
    rendered_any = False
    for row in rows:
        rendered_any = True
        cells: list[str] = []
        for index, value in enumerate(row):
            klass = ' class="numeric"' if index in numeric else ""
            cells.append(f"<td{klass}>{escape(str(value))}</td>")
        body_rows.append("<tr>" + "".join(cells) + "</tr>")
    if not rendered_any:
        body_rows.append("<tr>" + "".join("<td>-</td>" for _ in headers) + "</tr>")
    return (
        "<table>\n  <thead><tr>"
        + head
        + "</tr></thead>\n  <tbody>\n    "
        + "\n    ".join(body_rows)
        + "\n  </tbody>\n</table>"
    )


def _summary_list(items: Sequence[tuple[str, object]]) -> str:
    """Render a labelled key/value list as a definition-style block."""

    parts = ["<ul>"]
    for label, value in items:
        if value in (None, ""):
            continue
        parts.append(
            f"  <li><strong>{escape(str(label))}:</strong> <code>{escape(str(value))}</code></li>"
        )
    parts.append("</ul>")
    return "\n".join(parts)


def _claim_boundary_block(claim_boundary: str | None, metric_semantics: str | None) -> str:
    if not claim_boundary and not metric_semantics:
        return ""
    parts = ['<section class="warning">']
    if claim_boundary:
        parts.append(f"<p><strong>Claim boundary:</strong> {escape(claim_boundary)}</p>")
    if metric_semantics:
        parts.append(f"<p><strong>Metric semantics:</strong> {escape(metric_semantics)}</p>")
    parts.append("</section>")
    return "\n".join(parts)


def _require_html_payload(payload: object, *, name: str) -> JSONDict:
    if not isinstance(payload, dict):
        raise WorldForgeError(f"{name} must be a JSON object.")
    return cast(JSONDict, payload)


def _dict_rows(value: object) -> list[JSONDict]:
    if not isinstance(value, list):
        return []
    return [cast(JSONDict, item) for item in value if isinstance(item, dict)]


def _append_table_section(
    body_parts: list[str],
    *,
    title: str,
    headers: Sequence[str],
    rows: Sequence[Sequence[object]],
    numeric_columns: Sequence[int] = (),
) -> None:
    if not rows:
        return
    body_parts.append(f"<h2>{escape(title)}</h2>")
    body_parts.append(_table(headers, rows, numeric_columns=numeric_columns))


def _comparison_title(payload: JSONDict) -> str:
    kind = str(payload.get("kind") or "comparison")
    mode = str(payload.get("mode") or "comparison")
    if mode == "regression":
        return f"WorldForge Regression Comparison: {kind}"
    return f"WorldForge Run Comparison: {kind}"


def _comparison_summary_items(payload: JSONDict) -> tuple[tuple[str, object], ...]:
    return (
        ("Kind", payload.get("kind")),
        ("Mode", payload.get("mode") or "comparison"),
        ("Schema version", payload.get("schema_version")),
        ("Baseline run id", payload.get("baseline_run_id")),
        ("Candidate run id", payload.get("candidate_run_id")),
        ("Run count", payload.get("run_count")),
        ("Claim boundary", payload.get("claim_boundary")),
    )


def _comparison_run_rows(runs: Sequence[JSONDict]) -> list[tuple[object, ...]]:
    return [
        (
            run.get("run_id", "-"),
            run.get("created_at", "-"),
            run.get("status", "-"),
            run.get("provider", "-"),
            run.get("operation", "-"),
            run.get("command", "-"),
        )
        for run in runs
    ]


def _comparison_row_keys(rows: Sequence[JSONDict]) -> list[str]:
    seen_keys: list[str] = []
    for row in rows:
        for key in row:
            if key not in seen_keys:
                seen_keys.append(key)
    return seen_keys


def _evidence_summary_items(manifest: JSONDict) -> tuple[tuple[str, object], ...]:
    return (
        ("Schema version", manifest.get("schema_version")),
        ("Generated at", manifest.get("generated_at")),
        ("Source workspace", manifest.get("source_workspace")),
        ("Runs", manifest.get("run_count")),
        ("Included files", manifest.get("included_count")),
        ("Excluded files", manifest.get("excluded_count")),
        ("Safe to attach", manifest.get("safe_to_attach")),
    )


def _evidence_run_rows(runs: Sequence[JSONDict]) -> list[tuple[object, ...]]:
    return [
        (
            run.get("run_id", "-"),
            run.get("kind") or "-",
            run.get("status") or "-",
            run.get("provider") or "-",
            run.get("operation") or "-",
            run.get("command") or "-",
            run.get("skip_reason") or "-",
        )
        for run in runs
    ]


def _evidence_file_rows(files: Sequence[JSONDict]) -> list[tuple[object, ...]]:
    return [
        (
            item.get("path", "-"),
            str(item.get("included", False)).lower(),
            str(item.get("safe_to_attach", False)).lower(),
            item.get("sha256") or "-",
            item.get("reason") or "-",
        )
        for item in files
    ]


def _fixture_digest_rows(digests: Sequence[JSONDict]) -> list[tuple[object, ...]]:
    return [(item.get("path", "-"), item.get("sha256", "-")) for item in digests]


def _issue_primary_run(manifest: JSONDict) -> JSONDict:
    runs = _dict_rows(manifest.get("runs", []))
    return runs[0] if runs else {}


def _append_issue_text_section(
    body_parts: list[str],
    *,
    title: str,
    value: object,
    preformatted: bool = False,
) -> None:
    body_parts.append(f"<h2>{escape(title)}</h2>")
    if preformatted:
        body_parts.append(f"<pre>{escape(str(value or '-'))}</pre>")
        return
    body_parts.append(f"<p>{escape(str(value or '-'))}</p>")


def _append_validation_errors(body_parts: list[str], run: JSONDict) -> None:
    validation_errors = run.get("validation_errors")
    if not isinstance(validation_errors, list) or not validation_errors:
        return
    body_parts.append("<h2>Validation Errors</h2><ul>")
    body_parts.extend(f"  <li>{escape(str(err))}</li>" for err in validation_errors)
    body_parts.append("</ul>")


def _issue_file_rows(files: Sequence[JSONDict]) -> list[tuple[object, ...]]:
    return [
        (
            item.get("path", "-"),
            str(item.get("included", False)).lower(),
            str(item.get("safe_to_attach", False)).lower(),
            item.get("reason") or "-",
        )
        for item in files
    ]


def _append_issue_files(body_parts: list[str], manifest: JSONDict) -> None:
    body_parts.append("<h2>Attached Files</h2>")
    files = _dict_rows(manifest.get("files"))
    if not files:
        body_parts.append("<p>No attached files.</p>")
        return
    body_parts.append(
        _table(
            ("Path", "Included", "Safe to Attach", "Reason"),
            _issue_file_rows(files),
        )
    )


def _append_unsafe_issue_warning(body_parts: list[str], *, safe_to_attach: bool) -> None:
    if safe_to_attach:
        return
    body_parts.append(
        '<section class="warning"><p><strong>Warning:</strong> some bundle '
        "files are not safe to attach. Review the file list before sharing "
        "this report outside the host.</p></section>"
    )


def _evaluation_summary_items(report: EvaluationReport) -> tuple[tuple[str, object], ...]:
    return (
        ("Suite ID", report.suite_id),
        ("Suite", report.suite),
    )


def _evaluation_provider_rows(report: EvaluationReport) -> list[tuple[object, ...]]:
    return [
        (
            summary.provider,
            f"{summary.average_score:.2f}",
            f"{summary.passed_scenario_count}/{summary.scenario_count}",
            summary.scenario_count,
        )
        for summary in report.provider_summaries
    ]


def _evaluation_scenario_rows(report: EvaluationReport) -> list[tuple[object, ...]]:
    return [
        (
            result.provider,
            result.scenario,
            f"{result.score:.2f}",
            "yes" if result.passed else "no",
        )
        for result in report.results
    ]


def _append_failure_gallery(body_parts: list[str], payload: JSONDict) -> None:
    failure_payload = payload.get("failure_gallery")
    if not isinstance(failure_payload, dict) or not failure_payload.get("case_count"):
        return
    body_parts.append("<h2>Failure Gallery</h2>")
    body_parts.append(
        _table(
            ("Provider", "Scenario", "Observed Score", "Expected"),
            [
                (
                    case.get("provider", "-"),
                    case.get("scenario", "-"),
                    case.get("observed_score") or "-",
                    case.get("expected_contract") or "-",
                )
                for case in _dict_rows(failure_payload.get("cases", []))
            ],
        )
    )


def _append_workflow_trace(body_parts: list[str], payload: JSONDict) -> None:
    workflow_trace = payload.get("workflow_trace")
    if not isinstance(workflow_trace, dict):
        return
    body_parts.append("<h2>Workflow Trace</h2>")
    body_parts.append(
        _summary_list(
            (
                ("Workflow", workflow_trace.get("name")),
                ("Status", workflow_trace.get("status")),
                ("Steps", workflow_trace.get("step_count")),
            )
        )
    )
    steps = _dict_rows(workflow_trace.get("steps", []))
    if not steps:
        return
    body_parts.append(
        _table(
            ("Step", "Parent", "Operation", "Provider", "Capability", "Status"),
            [
                (
                    step.get("step_id", "-"),
                    step.get("parent_id", "-"),
                    step.get("operation", "-"),
                    step.get("provider", "-"),
                    step.get("capability", "-"),
                    step.get("status", "-"),
                )
                for step in steps
            ],
        )
    )


def render_evaluation_html(report: EvaluationReport) -> str:
    """Render an :class:`EvaluationReport` as a self-contained HTML document."""

    payload = report.to_dict()
    title = f"WorldForge Evaluation Report: {report.suite}"
    body_parts: list[str] = [f"<h1>{escape(title)}</h1>"]
    body_parts.append(_summary_list(_evaluation_summary_items(report)))
    body_parts.append(
        _claim_boundary_block(
            payload.get("claim_boundary"),
            payload.get("metric_semantics"),
        )
    )

    body_parts.append("<h2>Provider Summaries</h2>")
    body_parts.append(
        _table(
            ("Provider", "Average Score", "Passed", "Scenarios"),
            _evaluation_provider_rows(report),
            numeric_columns=(1, 2, 3),
        )
    )

    body_parts.append("<h2>Scenario Results</h2>")
    body_parts.append(
        _table(
            ("Provider", "Scenario", "Score", "Passed"),
            _evaluation_scenario_rows(report),
            numeric_columns=(2,),
        )
    )

    _append_failure_gallery(body_parts, payload)
    _append_workflow_trace(body_parts, payload)

    return _document(
        title=title,
        body="\n".join(body_parts),
        footer=_provenance_footer(payload.get("provenance")),
    )


def render_benchmark_html(report: BenchmarkReport) -> str:
    """Render a :class:`BenchmarkReport` as a self-contained HTML document."""

    payload = report.to_dict()
    title = "WorldForge Benchmark Report"
    body_parts: list[str] = [f"<h1>{escape(title)}</h1>"]
    body_parts.append(
        _claim_boundary_block(
            payload.get("claim_boundary"),
            payload.get("metric_semantics"),
        )
    )

    body_parts.append("<h2>Results</h2>")
    body_parts.append(
        _table(
            (
                "Provider",
                "Operation",
                "OK",
                "Retries",
                "Avg ms",
                "P95 ms",
                "Throughput / s",
            ),
            (
                (
                    result.provider,
                    result.operation,
                    f"{result.success_count}/{result.iterations}",
                    result.retry_count,
                    f"{(result.average_latency_ms or 0.0):.2f}",
                    f"{(result.p95_latency_ms or 0.0):.2f}",
                    f"{result.throughput_per_second:.2f}",
                )
                for result in report.results
            ),
            numeric_columns=(2, 3, 4, 5, 6),
        )
    )

    return _document(
        title=title,
        body="\n".join(body_parts),
        footer=_provenance_footer(payload.get("provenance")),
    )


def render_comparison_html(payload: JSONDict) -> str:
    """Render a preserved-run comparison payload as a self-contained HTML document.

    ``payload`` is the dict returned by
    :func:`worldforge.harness.report_compare.compare_preserved_run_reports`.
    """

    payload = _require_html_payload(payload, name="comparison payload")
    title = _comparison_title(payload)
    body_parts: list[str] = [f"<h1>{escape(title)}</h1>"]
    body_parts.append(_summary_list(_comparison_summary_items(payload)))

    regression_summary = payload.get("regression_summary")
    if isinstance(regression_summary, dict):
        body_parts.append("<h2>Regression Summary</h2>")
        body_parts.append(_summary_list(sorted(regression_summary.items())))

    runs = _dict_rows(payload.get("runs"))
    _append_table_section(
        body_parts,
        title="Runs",
        headers=("Run", "Created", "Status", "Provider", "Operation", "Command"),
        rows=_comparison_run_rows(runs),
    )

    rows = _dict_rows(payload.get("rows"))
    row_keys = _comparison_row_keys(rows)
    _append_table_section(
        body_parts,
        title="Comparison Rows",
        headers=tuple(row_keys),
        rows=[tuple(row.get(key, "") for key in row_keys) for row in rows],
    )

    return _document(title=title, body="\n".join(body_parts))


def render_evidence_bundle_html(manifest: JSONDict) -> str:
    """Render an evidence-bundle manifest as a self-contained HTML document."""

    manifest = _require_html_payload(manifest, name="evidence bundle manifest")
    title = "WorldForge Evidence Bundle"
    body_parts: list[str] = [f"<h1>{escape(title)}</h1>"]

    body_parts.append(_summary_list(_evidence_summary_items(manifest)))
    _append_table_section(
        body_parts,
        title="Runs",
        headers=("Run", "Kind", "Status", "Provider", "Operation", "Command", "Skip Reason"),
        rows=_evidence_run_rows(_dict_rows(manifest.get("runs"))),
    )
    _append_table_section(
        body_parts,
        title="Files",
        headers=("Path", "Included", "Safe to Attach", "SHA-256", "Reason"),
        rows=_evidence_file_rows(_dict_rows(manifest.get("files"))),
    )
    _append_table_section(
        body_parts,
        title="Fixture Digests",
        headers=("Fixture", "SHA-256"),
        rows=_fixture_digest_rows(_dict_rows(manifest.get("fixture_digests"))),
    )

    body_parts.append("<h2>Claim Boundary</h2>")
    body_parts.append(
        "<p>This bundle copies checkout-safe evidence from preserved WorldForge run "
        "workspaces. Excluded files are listed with reasons. The bundle does not upload "
        "artifacts, execute live providers, include raw secrets, or claim physical "
        "fidelity.</p>"
    )

    return _document(title=title, body="\n".join(body_parts))


def render_issue_bundle_html(manifest: JSONDict) -> str:
    """Render an issue-ready bundle manifest as a self-contained HTML document."""

    manifest = _require_html_payload(manifest, name="issue bundle manifest")
    run = _issue_primary_run(manifest)
    safe = bool(manifest.get("safe_to_attach"))
    title = f"WorldForge Run Issue: {run.get('run_id', '-')}"
    body_parts: list[str] = [f"<h1>{escape(title)}</h1>"]

    _append_issue_text_section(
        body_parts,
        title="Command",
        value=run.get("command"),
        preformatted=True,
    )
    _append_issue_text_section(
        body_parts,
        title="Expected Signal",
        value=run.get("expected_signal"),
    )
    _append_issue_text_section(
        body_parts,
        title="Observed Failure",
        value=run.get("observed_failure"),
    )
    _append_validation_errors(body_parts, run)

    triage = manifest.get("first_triage_step")
    if isinstance(triage, str) and triage.strip():
        body_parts.append("<h2>First Triage Step</h2>")
        body_parts.append(f"<p>{escape(triage)}</p>")

    _append_issue_files(body_parts, manifest)
    _append_unsafe_issue_warning(body_parts, safe_to_attach=safe)

    return _document(title=title, body="\n".join(body_parts))


def _provenance_footer(provenance: object) -> str | None:
    """Build a one-line footer summary from a provenance dict."""

    if not isinstance(provenance, dict):
        return None
    parts: list[str] = []
    version = provenance.get("worldforge_version")
    if version:
        parts.append(f"WorldForge {version}")
    generated_at = provenance.get("generated_at")
    if generated_at:
        parts.append(f"generated {generated_at}")
    if not parts:
        return None
    return " — ".join(parts)


__all__ = [
    "HTML_REPORT_SCHEMA_VERSION",
    "render_benchmark_html",
    "render_comparison_html",
    "render_evaluation_html",
    "render_evidence_bundle_html",
    "render_issue_bundle_html",
]

"""Renderer helpers for checkout-safe WorldForge evidence bundles."""

from __future__ import annotations

from worldforge.html_report import render_evidence_bundle_html, render_issue_bundle_html
from worldforge.models import JSONDict, WorldForgeError, dump_json
from worldforge.report_renderers import (
    ReportRenderer,
    ReportRenderResult,
    register_report_renderer,
    render_report_artifact,
)


def render_evidence_bundle_summary(manifest: JSONDict) -> str:
    """Render a Markdown summary for an evidence bundle manifest."""

    lines = _evidence_summary_header_lines(manifest)
    lines.extend(_evidence_summary_run_lines(manifest["runs"]))
    lines.extend(_evidence_summary_file_lines(manifest["files"]))
    lines.extend(_evidence_summary_fixture_lines(manifest["fixture_digests"]))
    lines.extend(_evidence_summary_claim_boundary_lines())
    return "\n".join(lines)


def _evidence_summary_header_lines(manifest: JSONDict) -> list[str]:
    return [
        "# WorldForge Evidence Bundle",
        "",
        f"- Schema version: `{manifest['schema_version']}`",
        f"- Generated at: `{manifest['generated_at']}`",
        f"- Source workspace: `{manifest['source_workspace']}`",
        f"- Runs: {manifest['run_count']}",
        f"- Included files: {manifest['included_count']}",
        f"- Excluded files: {manifest['excluded_count']}",
        f"- Safe to attach: `{str(manifest['safe_to_attach']).lower()}`",
    ]


def _evidence_summary_run_lines(runs: list[JSONDict]) -> list[str]:
    lines = [
        "",
        "## Runs",
        "",
        "| Run | Kind | Status | Provider | Operation | Command | Skip reason |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    lines.extend(_evidence_summary_run_row(run) for run in runs)
    return lines


def _evidence_summary_run_row(run: JSONDict) -> str:
    return (
        "| {run_id} | {kind} | {status} | {provider} | {operation} | `{command}` | {skip_reason} |"
    ).format(
        run_id=run["run_id"],
        kind=run["kind"] or "-",
        status=run["status"] or "-",
        provider=run.get("provider") or "-",
        operation=run.get("operation") or "-",
        command=run.get("command") or "-",
        skip_reason=run.get("skip_reason") or "-",
    )


def _evidence_summary_file_lines(files: list[JSONDict]) -> list[str]:
    lines = [
        "",
        "## Files",
        "",
        "| Path | Included | Safe to attach | SHA256 | Reason |",
        "| --- | --- | --- | --- | --- |",
    ]
    lines.extend(_evidence_summary_file_row(item) for item in files)
    return lines


def _evidence_summary_file_row(item: JSONDict) -> str:
    digest = str(item.get("sha256") or "-")
    return "| `{path}` | {included} | {safe} | `{digest}` | {reason} |".format(
        path=item["path"],
        included=str(item["included"]).lower(),
        safe=str(item["safe_to_attach"]).lower(),
        digest=digest,
        reason=item.get("reason") or "-",
    )


def _evidence_summary_fixture_lines(fixtures: list[JSONDict]) -> list[str]:
    lines = [
        "",
        "## Fixture Digests",
        "",
        "| Fixture | SHA256 |",
        "| --- | --- |",
    ]
    lines.extend(f"| `{fixture['path']}` | `{fixture['sha256']}` |" for fixture in fixtures)
    return lines


def _evidence_summary_claim_boundary_lines() -> list[str]:
    return [
        "",
        "## Claim Boundary",
        "",
        "This bundle copies checkout-safe evidence from preserved WorldForge run workspaces. "
        "Excluded files are listed with reasons. The bundle does not upload artifacts, execute "
        "live providers, include raw secrets, or claim physical fidelity.",
        "",
    ]


def render_issue_bundle_template(manifest: JSONDict) -> str:
    """Render a short GitHub issue body from an issue-run bundle manifest."""

    run = _issue_bundle_run(manifest)
    lines = _issue_bundle_run_lines(run)
    lines.extend(_issue_bundle_validation_lines(run))
    lines.extend(_issue_bundle_artifact_lines(manifest))
    lines.extend(_issue_bundle_attach_lines(bool(manifest.get("safe_to_attach"))))
    lines.extend(_issue_bundle_triage_lines(manifest))
    return "\n".join(lines)


def _issue_bundle_run(manifest: JSONDict) -> JSONDict:
    runs = manifest.get("runs", [])
    run = runs[0] if isinstance(runs, list) and runs else {}
    return run if isinstance(run, dict) else {}


def _issue_bundle_run_lines(run: JSONDict) -> list[str]:
    return [
        f"## WorldForge Run Issue: `{run.get('run_id', '-')}`",
        "",
        "### Command",
        "",
        f"`{run.get('command') or '-'}`",
        "",
        "### Expected Signal",
        "",
        str(run.get("expected_signal") or "-"),
        "",
        "### Observed Failure",
        "",
        str(run.get("observed_failure") or "-"),
    ]


def _issue_bundle_validation_lines(run: JSONDict) -> list[str]:
    validation_errors = run.get("validation_errors")
    if isinstance(validation_errors, list) and validation_errors:
        return ["", "Validation errors:", *(f"- {error}" for error in validation_errors)]
    return []


def _issue_bundle_artifact_lines(manifest: JSONDict) -> list[str]:
    return [
        "",
        "### Artifacts",
        "",
        "- `evidence_manifest.json`",
        "- `summary.md`",
        "- `issue.md`",
        f"- included files: {manifest.get('included_count', 0)}",
        f"- excluded files: {manifest.get('excluded_count', 0)}",
    ]


def _issue_bundle_attach_lines(safe: bool) -> list[str]:
    return [
        "",
        "### Safe-To-Attach Notes",
        "",
        f"- safe_to_attach: `{str(safe).lower()}`",
        _issue_bundle_attach_instruction(safe),
        "- Excluded files remain listed with reason, digest when available, and `local_only`.",
    ]


def _issue_bundle_attach_instruction(safe: bool) -> str:
    if safe:
        return "- Attach the bundle contents from this directory."
    return (
        "- Review `evidence_manifest.json` before attaching; at least one file was excluded or "
        "marked local-only."
    )


def _issue_bundle_triage_lines(manifest: JSONDict) -> list[str]:
    return [
        "",
        "### First Triage Step",
        "",
        str(manifest.get("first_triage_step") or _first_triage_step(manifest)),
        "",
    ]


def _first_triage_step(manifest: JSONDict) -> str:
    if not bool(manifest.get("safe_to_attach")):
        return (
            "Open evidence_manifest.json, inspect excluded files and local_only entries, and "
            "remove or replace unsafe artifacts before attaching the bundle."
        )
    return (
        "Open summary.md, then inspect the copied run_manifest.json and report artifacts for the "
        "preserved run."
    )


def evidence_bundle_artifact(manifest: JSONDict, output_format: str) -> ReportRenderResult:
    """Render an evidence bundle manifest through the registered renderer surface."""

    try:
        return render_report_artifact("evidence-bundle", output_format, manifest)
    except WorldForgeError as exc:
        if "No report renderer registered" in str(exc):
            raise WorldForgeError(
                "evidence bundle format must be a registered renderer; built-ins are "
                "json, markdown, or html."
            ) from exc
        raise


def issue_bundle_artifact(manifest: JSONDict, output_format: str) -> ReportRenderResult:
    """Render an issue bundle manifest through the registered renderer surface."""

    try:
        return render_report_artifact("issue-bundle", output_format, manifest)
    except WorldForgeError as exc:
        if "No report renderer registered" in str(exc):
            raise WorldForgeError(
                "issue bundle format must be a registered renderer; built-ins are "
                "json, markdown, or html."
            ) from exc
        raise


def register_builtin_evidence_bundle_renderers(*, schema_version: int) -> None:
    for artifact_family, markdown_renderer, html_renderer, description in (
        (
            "evidence-bundle",
            render_evidence_bundle_summary,
            render_evidence_bundle_html,
            "evidence bundle",
        ),
        (
            "issue-bundle",
            render_issue_bundle_template,
            render_issue_bundle_html,
            "issue bundle",
        ),
    ):
        for output_format, media_type, renderer in (
            ("json", "application/json", _json_renderer),
            ("markdown", "text/markdown", markdown_renderer),
            ("html", "text/html", html_renderer),
        ):
            register_report_renderer(
                ReportRenderer(
                    artifact_family=artifact_family,
                    output_format=output_format,
                    media_type=media_type,
                    supported_schemas=(f"{artifact_family}:{schema_version}",),
                    safe_to_attach=True,
                    render=renderer,
                    description=f"Built-in {description} {output_format} renderer.",
                ),
                replace=True,
            )


def _json_renderer(payload: JSONDict) -> str:
    return dump_json(payload, indent=2)

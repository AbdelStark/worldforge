"""Static non-developer evidence review package generator."""

from __future__ import annotations

from dataclasses import dataclass
from html import escape as html_escape
from pathlib import Path

from worldforge.artifact_io import write_json_artifact as _write_json
from worldforge.evidence_bundle import BundleResult, generate_issue_bundle
from worldforge.harness.workspace import create_run_workspace, write_run_manifest
from worldforge.models import JSONDict

EVIDENCE_REVIEW_SUMMARY = (
    "Built a static HTML/JSON/Markdown evidence review package with safe links, escaped "
    "text, and local-only unsafe artifact markers."
)

EVIDENCE_REVIEW_FIRST_TRIAGE_STEP = (
    "Open `review-package.html`, then inspect local-only rows before attaching anything "
    "besides the review package."
)


@dataclass(frozen=True, slots=True)
class EvidenceReviewPayloads:
    evaluation: JSONDict
    benchmark: JSONDict
    world_diff: JSONDict


@dataclass(frozen=True, slots=True)
class EvidenceReviewPackagePaths:
    manifest: Path
    markdown: Path
    html: Path


def run_non_developer_evidence_review_workflow(workflow_dir: Path) -> JSONDict:
    review_dir = workflow_dir / "non-developer-evidence-review"
    review_dir.mkdir(parents=True, exist_ok=True)
    payloads = build_evidence_review_payloads()
    write_evidence_review_inputs(review_dir, payloads)
    issue_bundle = create_evidence_review_issue_bundle(
        workflow_dir=workflow_dir,
        review_dir=review_dir,
        evaluation_payload=payloads.evaluation,
    )
    manifest = build_evidence_review_manifest(
        evaluation_payload=payloads.evaluation,
        issue_manifest=issue_bundle.manifest,
    )
    paths = write_evidence_review_package(review_dir, manifest)
    return evidence_review_result(
        manifest=manifest,
        paths=paths,
        issue_bundle=issue_bundle,
    )


def build_evidence_review_payloads() -> EvidenceReviewPayloads:
    evaluation = {
        "schema_version": 1,
        "kind": "evaluation",
        "title": "Planning report <script>alert(1)</script>",
        "provider": "mock",
        "status": "passed",
        "summary": "2/2 deterministic contract scenarios passed.",
        "claim_boundary": (
            "Evaluation evidence is a checkout-safe contract signal, not model-quality or "
            "physical-fidelity proof."
        ),
    }
    benchmark = {
        "schema_version": 1,
        "kind": "benchmark",
        "provider": "mock",
        "status": "passed",
        "average_latency_ms": 1.25,
        "claim_boundary": "Benchmark row is a fixture for review flow only.",
    }
    world_diff = {
        "schema_version": 1,
        "kind": "world_diff",
        "status": "changed",
        "changes": [
            {
                "path": "objects.cube.position.x",
                "before": 0.0,
                "after": 0.35,
                "safe_to_attach": True,
            }
        ],
    }
    return EvidenceReviewPayloads(
        evaluation=evaluation,
        benchmark=benchmark,
        world_diff=world_diff,
    )


def write_evidence_review_inputs(review_dir: Path, payloads: EvidenceReviewPayloads) -> None:
    _write_json(review_dir / "evaluation-report.json", payloads.evaluation)
    _write_json(review_dir / "benchmark-report.json", payloads.benchmark)
    _write_json(review_dir / "world-diff.json", payloads.world_diff)
    (review_dir / "evaluation-report.md").write_text(
        "# Evaluation Evidence\n\n"
        "- Status: `passed`\n"
        "- Claim boundary: checkout-safe contract signal only.\n",
        encoding="utf-8",
    )


def create_evidence_review_issue_bundle(
    *,
    workflow_dir: Path,
    review_dir: Path,
    evaluation_payload: JSONDict,
) -> BundleResult:
    issue_workspace = workflow_dir / "issue-workspace"
    run_id = "20260101T000000Z-aabbccdd"
    run_workspace = create_run_workspace(
        issue_workspace,
        kind="eval",
        command="worldforge eval --suite planning --provider mock",
        provider="mock",
        operation="planning",
        run_id=run_id,
        input_summary={"suite_id": "planning", "providers": ["mock"]},
    )
    run_workspace.write_json("reports/report.json", evaluation_payload)
    run_workspace.write_text(
        "logs/provider-events.jsonl",
        '{"target":"https://example.invalid/artifact.json?token=secret"}\n',
    )
    write_run_manifest(
        run_workspace,
        kind="eval",
        command="worldforge eval --suite planning --provider mock",
        provider="mock",
        operation="planning",
        status="failed",
        input_summary={"suite_id": "planning", "providers": ["mock"]},
        result_summary={"failed_count": 1, "safe_to_attach": False},
        artifact_paths={
            "report": "reports/report.json",
            "unsafe_events": "logs/provider-events.jsonl",
            "host_local": "/Users/example/private/provider-payload.json",
        },
    )
    return generate_issue_bundle(
        workspace_dir=issue_workspace,
        run_id=run_id,
        output_dir=review_dir / "issue-bundle",
        overwrite=True,
        generated_at="2026-01-01T00:00:00+00:00",
    )


def build_evidence_review_manifest(
    *,
    evaluation_payload: JSONDict,
    issue_manifest: JSONDict,
) -> JSONDict:
    artifacts = review_artifacts(issue_manifest)
    return {
        "schema_version": 1,
        "safe_to_attach": True,
        "review_title": evaluation_payload["title"],
        "review_audience": "issue reviewer, research collaborator, or release reader",
        "artifacts": artifacts,
        "local_only_count": sum(1 for item in artifacts if item["share_policy"] != "safe"),
        "reviewer_guide": [
            "Evidence: safe JSON and Markdown summaries linked from this package.",
            (
                "Local-only: host paths, signed URLs, and raw provider payloads are named "
                "but not embedded."
            ),
            (
                "Unsupported claims: model quality, physical fidelity, robot safety, or live "
                "provider availability."
            ),
        ],
        "claim_boundary": (
            "Static review package only; it does not host a dashboard, execute JavaScript, embed "
            "unsafe local files, or include raw provider payloads."
        ),
    }


def write_evidence_review_package(
    review_dir: Path,
    manifest: JSONDict,
) -> EvidenceReviewPackagePaths:
    paths = EvidenceReviewPackagePaths(
        manifest=review_dir / "review-package.json",
        markdown=review_dir / "review-package.md",
        html=review_dir / "review-package.html",
    )
    _write_json(paths.manifest, manifest)
    paths.markdown.write_text(render_evidence_review_markdown(manifest), encoding="utf-8")
    paths.html.write_text(render_evidence_review_html(manifest), encoding="utf-8")
    return paths


def evidence_review_result(
    *,
    manifest: JSONDict,
    paths: EvidenceReviewPackagePaths,
    issue_bundle: BundleResult,
) -> JSONDict:
    return {
        "status": "passed",
        "provider": "non-developer-evidence-review",
        "safe_to_attach": True,
        "summary": EVIDENCE_REVIEW_SUMMARY,
        "report": manifest,
        "artifact_paths": {
            "review_html": str(paths.html),
            "review_json": str(paths.manifest),
            "review_markdown": str(paths.markdown),
            "issue_bundle_manifest": str(issue_bundle.manifest_path),
        },
        "first_triage_step": EVIDENCE_REVIEW_FIRST_TRIAGE_STEP,
        "claim_boundary": manifest["claim_boundary"],
    }


def review_artifacts(issue_manifest: JSONDict) -> list[JSONDict]:
    issue_bundle_policy = "local-only" if issue_manifest["safe_to_attach"] is False else "safe"
    return [
        review_artifact(
            "evaluation",
            "evaluation-report.json",
            "safe",
            "deterministic evaluation summary",
        ),
        review_artifact(
            "benchmark",
            "benchmark-report.json",
            "safe",
            "checkout-safe benchmark summary",
        ),
        review_artifact(
            "world-diff",
            "world-diff.json",
            "safe",
            "world state change summary",
        ),
        review_artifact(
            "issue-bundle",
            "issue-bundle/evidence_manifest.json",
            issue_bundle_policy,
            "issue bundle manifest with unsafe file exclusions",
        ),
        *local_only_review_entries(),
    ]


def local_only_review_entries() -> list[JSONDict]:
    return [
        {
            "kind": "unsafe-provider-event",
            "path": "<host-local:provider-events.jsonl>",
            "share_policy": "local-only",
            "reason": "secret-like signed URL query string excluded from the review package",
        },
        {
            "kind": "raw-provider-payload",
            "path": "<host-local:provider-payload.json>",
            "share_policy": "local-only",
            "reason": "raw provider payload is host-local and not embedded",
        },
    ]


def review_artifact(kind: str, path: str, share_policy: str, evidence_role: str) -> JSONDict:
    return {
        "kind": kind,
        "path": path,
        "share_policy": share_policy,
        "safe_to_attach": share_policy == "safe",
        "evidence_role": evidence_role,
    }


def render_evidence_review_markdown(manifest: JSONDict) -> str:
    lines = [
        "# Non-Developer Evidence Review",
        "",
        str(manifest["review_title"]),
        "",
        manifest["claim_boundary"],
        "",
        "| Artifact | Share policy | Evidence role |",
        "| --- | --- | --- |",
    ]
    lines.extend(
        f"| `{item['path']}` | `{item['share_policy']}` | "
        f"{item.get('evidence_role') or item.get('reason') or '-'} |"
        for item in manifest["artifacts"]
    )
    lines.extend(["", "## Reviewer Guide", ""])
    lines.extend(f"- {line}" for line in manifest["reviewer_guide"])
    lines.append("")
    return "\n".join(lines)


def render_evidence_review_html(manifest: JSONDict) -> str:
    rows = []
    for item in manifest["artifacts"]:
        path = str(item["path"])
        path_cell = (
            f'<a href="{html_escape(path, quote=True)}">{html_escape(path)}</a>'
            if item["share_policy"] == "safe" and is_safe_relative_link(path)
            else html_escape(path)
        )
        rows.append(
            "<tr>"
            f"<td>{html_escape(str(item['kind']))}</td>"
            f"<td>{path_cell}</td>"
            f"<td>{html_escape(str(item['share_policy']))}</td>"
            f"<td>{html_escape(str(item.get('evidence_role') or item.get('reason') or '-'))}</td>"
            "</tr>"
        )
    guide_items = "\n".join(
        f"<li>{html_escape(str(line))}</li>" for line in manifest["reviewer_guide"]
    )
    return (
        "<!DOCTYPE html>\n"
        '<html lang="en">\n'
        "<head>\n"
        '  <meta charset="utf-8">\n'
        f"  <title>{html_escape(str(manifest['review_title']))}</title>\n"
        "  <style>body{font-family:system-ui,sans-serif;max-width:980px;margin:2rem auto;"
        "line-height:1.45}table{border-collapse:collapse;width:100%}td,th{border:1px solid "
        "#ccd;padding:.5rem;text-align:left}.warning{background:#fff4ce;padding:1rem}</style>\n"
        "</head>\n"
        "<body>\n"
        f"  <h1>{html_escape(str(manifest['review_title']))}</h1>\n"
        f"  <p>{html_escape(str(manifest['claim_boundary']))}</p>\n"
        '  <section class="warning"><strong>Local-only rows are not attachments.</strong> '
        "They name excluded host material so reviewers understand the boundary.</section>\n"
        "  <h2>Artifacts</h2>\n"
        "  <table><thead><tr><th>Kind</th><th>Path</th><th>Share policy</th>"
        "<th>Evidence role</th></tr></thead><tbody>\n"
        f"{''.join(rows)}\n"
        "  </tbody></table>\n"
        "  <h2>Reviewer Guide</h2>\n"
        f"  <ul>{guide_items}</ul>\n"
        "</body>\n"
        "</html>\n"
    )


def is_safe_relative_link(path: str) -> bool:
    candidate = Path(path)
    return not candidate.is_absolute() and ".." not in candidate.parts and "://" not in path

from __future__ import annotations

from pathlib import Path

from worldforge.demos.evidence_review import (
    build_evidence_review_manifest,
    build_evidence_review_payloads,
    is_safe_relative_link,
    render_evidence_review_html,
    render_evidence_review_markdown,
    review_artifacts,
    run_non_developer_evidence_review_workflow,
)


def test_evidence_review_manifest_marks_unsafe_issue_bundle_local_only() -> None:
    payloads = build_evidence_review_payloads()
    manifest = build_evidence_review_manifest(
        evaluation_payload=payloads.evaluation,
        issue_manifest={"safe_to_attach": False},
    )
    artifacts = {artifact["kind"]: artifact for artifact in manifest["artifacts"]}

    assert manifest["safe_to_attach"] is True
    assert manifest["local_only_count"] >= 3
    assert artifacts["evaluation"]["safe_to_attach"] is True
    assert artifacts["issue-bundle"]["share_policy"] == "local-only"
    assert artifacts["unsafe-provider-event"]["share_policy"] == "local-only"
    assert artifacts["raw-provider-payload"]["share_policy"] == "local-only"
    assert "raw provider payloads" in manifest["claim_boundary"]


def test_evidence_review_renderers_escape_text_and_link_only_safe_paths() -> None:
    payloads = build_evidence_review_payloads()
    manifest = build_evidence_review_manifest(
        evaluation_payload=payloads.evaluation,
        issue_manifest={"safe_to_attach": True},
    )
    html = render_evidence_review_html(manifest)
    markdown = render_evidence_review_markdown(manifest)

    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in html
    assert "<script" not in html
    assert '<a href="evaluation-report.json">' in html
    assert '<a href="/Users/example/private.json">' not in html
    assert "<host-local:provider-events.jsonl>" not in html
    assert "Non-Developer Evidence Review" in markdown
    assert "`evaluation-report.json`" in markdown
    assert not is_safe_relative_link("/Users/example/private.json")
    assert not is_safe_relative_link("../escaped.json")
    assert not is_safe_relative_link("https://example.invalid/report.json")
    assert is_safe_relative_link("issue-bundle/evidence_manifest.json")


def test_non_developer_evidence_review_workflow_writes_static_package(tmp_path: Path) -> None:
    summary = run_non_developer_evidence_review_workflow(tmp_path)
    artifact_paths = summary["artifact_paths"]

    assert summary["status"] == "passed"
    assert summary["safe_to_attach"] is True
    assert Path(str(artifact_paths["review_html"])).is_file()
    assert Path(str(artifact_paths["review_json"])).is_file()
    assert Path(str(artifact_paths["review_markdown"])).is_file()
    assert Path(str(artifact_paths["issue_bundle_manifest"])).is_file()


def test_review_artifacts_marks_safe_issue_bundle_attachable() -> None:
    artifacts = review_artifacts({"safe_to_attach": True})
    issue_bundle = next(artifact for artifact in artifacts if artifact["kind"] == "issue-bundle")

    assert issue_bundle["share_policy"] == "safe"
    assert issue_bundle["safe_to_attach"] is True

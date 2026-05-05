from __future__ import annotations

import json

import pytest

from worldforge.evaluation import EvaluationFailureGallery, EvaluationReport, EvaluationResult
from worldforge.evaluation.suites import EVALUATION_CLAIM_BOUNDARY, EVALUATION_METRIC_SEMANTICS
from worldforge.models import WorldForgeError
from worldforge.provenance import ProvenanceEnvelope


def _provenance() -> ProvenanceEnvelope:
    return ProvenanceEnvelope(
        kind="evaluation",
        suite_id="generation",
        suite_version="evaluation:1",
        providers=("unsafe-provider",),
        capabilities=("generate",),
        input_digest="sha256:" + "a" * 64,
        result_digest="sha256:" + "b" * 64,
        event_count=0,
        claim_boundary=EVALUATION_CLAIM_BOUNDARY,
        metric_semantics=EVALUATION_METRIC_SEMANTICS,
    )


def test_failed_evaluation_report_includes_sanitized_failure_gallery() -> None:
    report = EvaluationReport(
        "generation",
        "Generation Evaluation Suite",
        [
            EvaluationResult(
                suite_id="generation",
                suite="Generation Evaluation Suite",
                scenario="text-conditioned-video",
                provider="unsafe-provider",
                score=0.25,
                passed=False,
                metrics={
                    "api_key": "gallery-secret",
                    "artifact_url": (
                        "https://files.example.test/video.mp4"
                        "?X-Amz-Signature=download-secret&token=download-token"
                    ),
                    "local_path": "/Users/abdel/private/report.json",
                    "raw_tensor": [[0.1, 0.2], [0.3, 0.4]],
                    "resolution": [640, 360],
                    "nested": {
                        "signed_url": "https://example.test/object?token=nested-secret",
                    },
                },
            )
        ],
        provenance=_provenance(),
    )

    payload = json.loads(report.to_json())
    gallery = payload["failure_gallery"]
    case = gallery["cases"][0]

    assert gallery["schema_version"] == 1
    assert gallery["source_input_digest"] == "sha256:" + "a" * 64
    assert gallery["source_result_digest"] == "sha256:" + "b" * 64
    assert case["fixture_id"] == "evaluation:generation:text-conditioned-video"
    assert "expected duration" in case["expected_contract_notes"]
    assert "score=0.2500" in case["observed_result"]
    assert case["metrics_preview"]["api_key"] == "[redacted]"
    assert case["metrics_preview"]["artifact_url"] == "https://files.example.test/video.mp4"
    assert case["metrics_preview"]["local_path"] == "[host-local-path]"
    assert case["metrics_preview"]["raw_tensor"] == {
        "type": "array",
        "item_count": 2,
        "nested": True,
    }
    assert case["metrics_preview"]["resolution"] == [640, 360]
    assert case["metrics_preview"]["nested"]["signed_url"] == "[redacted]"

    exported = json.dumps(gallery)
    assert "gallery-secret" not in exported
    assert "download-secret" not in exported
    assert "nested-secret" not in exported
    assert "X-Amz-Signature" not in exported
    assert "/Users/abdel" not in exported
    assert "[[0.1, 0.2]" not in exported

    markdown = report.to_markdown()
    assert "## Failure Gallery" in markdown
    assert "contract triage, not physical fidelity evidence" in markdown
    assert "gallery-secret" not in markdown

    artifacts = report.artifacts()
    assert json.loads(artifacts["failure_gallery.json"])["case_count"] == 1
    assert "# Evaluation Failure Gallery" in artifacts["failure_gallery.md"]


def test_failure_gallery_selects_representative_lowest_score_cases() -> None:
    report = EvaluationReport(
        "custom",
        "Custom Evaluation Suite",
        [
            EvaluationResult("custom", "Custom Evaluation Suite", "case-a", "mock", 0.4, False),
            EvaluationResult("custom", "Custom Evaluation Suite", "case-b", "mock", 0.1, False),
            EvaluationResult("custom", "Custom Evaluation Suite", "case-c", "mock", 0.2, False),
            EvaluationResult("custom", "Custom Evaluation Suite", "case-d", "mock", 1.0, True),
            EvaluationResult(
                "custom",
                "Custom Evaluation Suite",
                "case-e",
                "other",
                0.3,
                False,
            ),
        ],
    )

    gallery = report.failure_gallery(max_cases_per_provider=2)

    assert [case.scenario for case in gallery.cases] == ["case-b", "case-c", "case-e"]
    assert [case.provider for case in gallery.cases] == ["mock", "mock", "other"]
    assert all(
        "deterministic evaluation contract" in case.expected_contract_notes
        for case in gallery.cases
    )


def test_failure_gallery_handles_passing_reports_and_invalid_limits() -> None:
    report = EvaluationReport(
        "physics",
        "Physics Evaluation Suite",
        [
            EvaluationResult(
                "physics",
                "Physics Evaluation Suite",
                "object-stability",
                "mock",
                1.0,
                True,
            )
        ],
    )

    payload = json.loads(report.to_json())
    gallery_payload = json.loads(report.artifacts()["failure_gallery.json"])

    assert "failure_gallery" not in payload
    assert gallery_payload["case_count"] == 0
    assert (
        "No failed evaluation cases."
        in EvaluationFailureGallery(
            "physics",
            "Physics Evaluation Suite",
        ).to_markdown()
    )

    with pytest.raises(WorldForgeError, match="max_cases_per_provider"):
        report.failure_gallery(max_cases_per_provider=0)

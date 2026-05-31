from __future__ import annotations

import importlib.util
import json
import math
import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest

from worldforge.models import WorldForgeError

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "generate_quality_dashboard.py"
SPEC = importlib.util.spec_from_file_location("generate_quality_dashboard", SCRIPT)
assert SPEC is not None
generate_quality_dashboard = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules["generate_quality_dashboard"] = generate_quality_dashboard
SPEC.loader.exec_module(generate_quality_dashboard)
build_quality_dashboard = generate_quality_dashboard.build_quality_dashboard
main = generate_quality_dashboard.main
render_quality_dashboard_markdown = generate_quality_dashboard.render_quality_dashboard_markdown


def test_quality_dashboard_aggregates_mixed_gate_statuses(tmp_path: Path) -> None:
    release_evidence = tmp_path / "release-evidence.json"
    dependency_audit = tmp_path / "dependency-audit.json"
    core_performance = tmp_path / "core-performance.json"
    release_evidence.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "generated_at": "2026-01-01T00:00:00+00:00",
                "validation_gates": [
                    {
                        "name": "Docs command drift",
                        "command": "uv run python scripts/check_docs_commands.py",
                        "status": "failed",
                        "exit_code": 1,
                        "stdout_tail": "",
                        "stderr_tail": "stale command: worldforge old-command",
                        "triage_step": "Fix the stale command reference.",
                    },
                    {
                        "name": "Docs",
                        "command": "uv run mkdocs build --strict",
                        "status": "passed",
                        "exit_code": 0,
                        "stdout_tail": "build passed",
                        "stderr_tail": "",
                        "triage_step": "Fix the reported docs warning.",
                    },
                    {
                        "name": "Coverage",
                        "command": "uv run --extra harness pytest --cov=src/worldforge",
                        "status": "skipped",
                        "triage_step": "Run the coverage gate before release.",
                    },
                ],
                "live_provider_evidence": [
                    {
                        "provider": "leworldmodel",
                        "status": "host-owned",
                        "manifests": [],
                        "reason": "missing host-owned configuration: LEWORLDMODEL_POLICY",
                    },
                    {
                        "provider": "cosmos-policy",
                        "status": "passed",
                        "manifests": [
                            {
                                "path": ".worldforge/runs/cosmos-policy/run_manifest.json",
                                "status": "passed",
                                "capability": "policy",
                            }
                        ],
                        "reason": "",
                    },
                ],
                "extra_live_provider_evidence": [],
            }
        ),
        encoding="utf-8",
    )
    dependency_audit.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "generated_at": "2026-01-01T00:00:00+00:00",
                "status": "tool-unavailable",
                "vulnerability_summary": {
                    "dependency_count": 0,
                    "vulnerable_dependency_count": 0,
                    "vulnerability_count": 0,
                },
                "vulnerabilities": [],
                "commands": {
                    "pip_audit_version": {
                        "command": "uvx --from pip-audit pip-audit --version",
                        "exit_code": 127,
                        "stderr_tail": "command not found",
                    }
                },
                "ignored_advisories": [],
                "first_triage_step": "Install uvx pip-audit and rerun.",
            }
        ),
        encoding="utf-8",
    )
    core_performance.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "passed": False,
                "preserved_workspace": "/Users/example/.worldforge/core-performance",
                "results": [
                    {
                        "name": "world_persistence",
                        "duration_ms": 400.0,
                        "budget_ms": 250.0,
                        "passed": False,
                        "artifact_path": "/Users/example/world.json",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    dashboard = build_quality_dashboard(
        release_evidence=release_evidence,
        dependency_audit=dependency_audit,
        core_performance=core_performance,
        now_utc=lambda: datetime(2026, 1, 2, tzinfo=UTC),
    )

    assert dashboard["status"] == "failed"
    assert dashboard["generated_at"] == "2026-01-02T00:00:00+00:00"
    assert dashboard["summary"]["passed"] >= 2
    assert dashboard["summary"]["failed"] >= 2
    assert dashboard["summary"]["warning"] == 1
    assert dashboard["summary"]["skipped"] >= 2
    assert dashboard["summary"]["not-run"] >= 1
    assert dashboard["first_failed_gate"]["name"] == "Docs command drift"

    gates = {gate["name"]: gate for gate in dashboard["gates"]}
    assert gates["Docs command drift"]["raw_details"]["stderr_tail"] == (
        "stale command: worldforge old-command"
    )
    assert gates["Coverage"]["status"] == "skipped"
    assert gates["Optional live provider: leworldmodel"]["status"] == "skipped"
    assert gates["Optional live provider: leworldmodel"]["host_owned"] is True
    assert gates["Dependency audit artifact"]["status"] == "warning"
    assert gates["Core performance artifact"]["status"] == "failed"
    assert gates["Core performance artifact"]["raw_details"]["failed_results"][0]["name"] == (
        "world_persistence"
    )
    assert "<host-local-path>" in json.dumps(gates["Core performance artifact"]["raw_details"])

    markdown = render_quality_dashboard_markdown(dashboard)
    assert "not a hosted dashboard" in markdown
    assert "Release evidence remains the artifact for release claims" in markdown
    assert "## Raw Failure Details" in markdown
    assert "stale command: worldforge old-command" in markdown


def test_quality_dashboard_sanitizes_raw_detail_keys_without_dropping_collisions(
    tmp_path: Path,
) -> None:
    release_evidence = tmp_path / "release-evidence.json"
    dependency_audit = tmp_path / "dependency-audit.json"
    core_performance = tmp_path / "core-performance.json"
    release_evidence.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "validation_gates": [
                    {
                        "name": gate.name,
                        "command": gate.command,
                        "status": "passed",
                        "exit_code": 0,
                        "triage_step": gate.triage_step,
                    }
                    for gate in generate_quality_dashboard.CHECKOUT_SAFE_GATES
                ],
                "live_provider_evidence": [],
                "extra_live_provider_evidence": [],
            }
        ),
        encoding="utf-8",
    )
    dependency_audit.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "generated_at": "2026-01-01T00:00:00+00:00",
                "status": "passed",
                "vulnerability_summary": {
                    "dependency_count": 0,
                    "vulnerable_dependency_count": 0,
                    "vulnerability_count": 0,
                },
                "vulnerabilities": [
                    {
                        "/Users/alice/private/token=alpha": "first",
                        "/private/tmp/token=beta": "second",
                        "https://example.test/a?token=gamma": "third",
                    }
                ],
                "commands": {},
                "ignored_advisories": [],
                "first_triage_step": "Attach evidence.",
            }
        ),
        encoding="utf-8",
    )
    core_performance.write_text(
        json.dumps({"schema_version": 1, "passed": True, "results": []}),
        encoding="utf-8",
    )

    dashboard = build_quality_dashboard(
        release_evidence=release_evidence,
        dependency_audit=dependency_audit,
        core_performance=core_performance,
        now_utc=lambda: datetime(2026, 1, 2, tzinfo=UTC),
    )
    rendered = json.dumps(dashboard, sort_keys=True) + render_quality_dashboard_markdown(dashboard)

    assert "/Users/alice" not in rendered
    assert "/private/tmp" not in rendered
    assert "alpha" not in rendered
    assert "beta" not in rendered
    assert "gamma" not in rendered
    assert "https://example.test/a?token=gamma" not in rendered
    assert "<host-local-path>" in rendered
    assert "<host-local-path>#2" in rendered
    assert "[redacted-url]" in rendered
    assert "first" in rendered
    assert "second" in rendered
    assert "third" in rendered


def test_quality_dashboard_marks_missing_sources_not_run(tmp_path: Path) -> None:
    dashboard = build_quality_dashboard(
        release_evidence=tmp_path / "missing-release-evidence.json",
        dependency_audit=tmp_path / "missing-dependency-audit.json",
        core_performance=tmp_path / "missing-core-performance.json",
        now_utc=lambda: datetime(2026, 1, 2, tzinfo=UTC),
    )

    gates = {gate["name"]: gate for gate in dashboard["gates"]}
    assert dashboard["status"] == "warning"
    assert dashboard["first_failed_gate"] is None
    assert gates["Docs"]["status"] == "not-run"
    assert gates["Tests"]["status"] == "not-run"
    assert gates["Coverage"]["status"] == "not-run"
    assert gates["Provider catalog drift"]["status"] == "not-run"
    assert gates["Docs snippets"]["status"] == "not-run"
    assert gates["Package contract"]["status"] == "not-run"
    assert gates["Dependency audit artifact"]["status"] == "not-run"
    assert gates["Core performance artifact"]["status"] == "not-run"
    assert gates["Optional live provider: leworldmodel"]["status"] == "skipped"
    assert dashboard["summary"]["not-run"] >= 8


def test_quality_dashboard_marks_malformed_release_gate_table_as_missing_rows(
    tmp_path: Path,
) -> None:
    records = generate_quality_dashboard._release_gate_records(
        tmp_path / "release-evidence.json",
        {
            "schema_version": 1,
            "validation_gates": {"Docs": {"status": "passed"}},
        },
    )

    gates = {record.name: record.to_dict() for record in records}
    docs_gate = gates["Docs"]

    assert docs_gate["status"] == "not-run"
    assert docs_gate["summary"] == "No release evidence row was found for this expected gate."
    assert docs_gate["raw_details"]["reason"] == "missing-row"
    assert docs_gate["raw_details"]["expected_command"] == "uv run mkdocs build --strict"


def test_quality_dashboard_preserves_unexpected_release_gate_rows(tmp_path: Path) -> None:
    records = generate_quality_dashboard._release_gate_records(
        tmp_path / "release-evidence.json",
        {
            "schema_version": 1,
            "validation_gates": [
                {
                    "name": "Custom lab gate",
                    "duration_ms": 12.5,
                }
            ],
        },
    )

    custom_gate = {record.name: record.to_dict() for record in records}["Custom lab gate"]

    assert custom_gate["status"] == "warning"
    assert custom_gate["command"] == ""
    assert custom_gate["summary"] == "release gate reported `warning`, duration 12.5 ms"
    assert custom_gate["first_triage_step"] == "Inspect source."
    assert custom_gate["raw_details"]["release_status"] == ""
    assert custom_gate["raw_details"]["duration_ms"] == 12.5


def test_quality_dashboard_normalizes_extra_live_provider_rows(tmp_path: Path) -> None:
    release_evidence = tmp_path / "release-evidence.json"
    dependency_audit = tmp_path / "dependency-audit.json"
    core_performance = tmp_path / "core-performance.json"
    release_evidence.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "validation_gates": [
                    {
                        "name": gate.name,
                        "command": gate.command,
                        "status": "passed",
                        "exit_code": 0,
                        "triage_step": gate.triage_step,
                    }
                    for gate in generate_quality_dashboard.CHECKOUT_SAFE_GATES
                ],
                "live_provider_evidence": {"provider": "ignored"},
                "extra_live_provider_evidence": [
                    "ignored",
                    {
                        "provider": "lab-provider",
                        "status": "needs-review",
                        "manifests": [
                            {
                                "path": "/Users/alice/.worldforge/runs/lab/run_manifest.json",
                                "authorization": "Bearer abc123",
                            }
                        ],
                    },
                ],
            }
        ),
        encoding="utf-8",
    )
    dependency_audit.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "generated_at": "2026-01-01T00:00:00+00:00",
                "status": "passed",
                "vulnerability_summary": {"vulnerability_count": 0},
                "vulnerabilities": [],
                "commands": {},
                "ignored_advisories": [],
                "first_triage_step": "Attach evidence.",
            }
        ),
        encoding="utf-8",
    )
    core_performance.write_text(
        json.dumps({"schema_version": 1, "passed": True, "results": []}),
        encoding="utf-8",
    )

    dashboard = build_quality_dashboard(
        release_evidence=release_evidence,
        dependency_audit=dependency_audit,
        core_performance=core_performance,
        now_utc=lambda: datetime(2026, 1, 2, tzinfo=UTC),
    )

    gates = {gate["name"]: gate for gate in dashboard["gates"]}
    gate = gates["Optional live provider: lab-provider"]
    rendered_gate = json.dumps(gate, sort_keys=True)

    assert "Optional live provider: ignored" not in gates
    assert dashboard["status"] == "warning"
    assert gate["status"] == "warning"
    assert gate["summary"] == "release evidence reported `needs-review`"
    assert gate["host_owned"] is False
    assert gate["first_triage_step"] == (
        "Inspect the linked run_manifest.json and provider smoke output."
    )
    assert gate["raw_details"]["release_status"] == "needs-review"
    assert "/Users/alice" not in rendered_gate
    assert "Bearer abc123" not in rendered_gate
    assert "<host-local-path>" in rendered_gate
    assert "[redacted]" in rendered_gate


def test_quality_dashboard_rejects_incoherent_core_performance_artifact(tmp_path: Path) -> None:
    release_evidence = tmp_path / "release-evidence.json"
    dependency_audit = tmp_path / "dependency-audit.json"
    core_performance = tmp_path / "core-performance.json"
    release_evidence.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "validation_gates": [
                    {
                        "name": gate.name,
                        "command": gate.command,
                        "status": "passed",
                        "exit_code": 0,
                        "triage_step": gate.triage_step,
                    }
                    for gate in generate_quality_dashboard.CHECKOUT_SAFE_GATES
                ],
                "live_provider_evidence": [],
                "extra_live_provider_evidence": [],
            }
        ),
        encoding="utf-8",
    )
    dependency_audit.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "generated_at": "2026-01-01T00:00:00+00:00",
                "status": "passed",
                "vulnerability_summary": {"vulnerability_count": 0},
                "vulnerabilities": [],
                "commands": {},
                "ignored_advisories": [],
                "first_triage_step": "Attach evidence.",
            }
        ),
        encoding="utf-8",
    )
    core_performance.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "passed": True,
                "results": [
                    {
                        "name": "world_persistence",
                        "duration_ms": 400.0,
                        "budget_ms": 250.0,
                        "passed": False,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    dashboard = build_quality_dashboard(
        release_evidence=release_evidence,
        dependency_audit=dependency_audit,
        core_performance=core_performance,
        now_utc=lambda: datetime(2026, 1, 2, tzinfo=UTC),
    )

    gate = {item["name"]: item for item in dashboard["gates"]}["Core performance artifact"]
    assert dashboard["status"] == "failed"
    assert gate["status"] == "failed"
    assert "contradicted" in gate["summary"]
    assert gate["raw_details"]["incoherent_pass"] is True
    assert gate["raw_details"]["failed_results"][0]["name"] == "world_persistence"


def test_quality_dashboard_warns_on_malformed_core_performance_artifact(tmp_path: Path) -> None:
    dashboard = build_quality_dashboard(
        release_evidence=tmp_path / "missing-release-evidence.json",
        dependency_audit=tmp_path / "missing-dependency-audit.json",
        core_performance=tmp_path / "core-performance.json",
        now_utc=lambda: datetime(2026, 1, 2, tzinfo=UTC),
    )
    assert dashboard["summary"]["warning"] == 0

    core_performance = tmp_path / "core-performance.json"
    core_performance.write_text(json.dumps({"schema_version": 1, "results": []}), encoding="utf-8")

    dashboard = build_quality_dashboard(
        release_evidence=tmp_path / "missing-release-evidence.json",
        dependency_audit=tmp_path / "missing-dependency-audit.json",
        core_performance=core_performance,
        now_utc=lambda: datetime(2026, 1, 2, tzinfo=UTC),
    )

    gate = {item["name"]: item for item in dashboard["gates"]}["Core performance artifact"]
    assert gate["status"] == "warning"
    assert gate["raw_details"]["reason"] == "invalid-shape"


def test_quality_dashboard_records_core_performance_incoherent_failure(tmp_path: Path) -> None:
    gate = generate_quality_dashboard._core_performance_record(
        tmp_path / "core-performance.json",
        {
            "schema_version": 1,
            "passed": False,
            "results": [{"name": "world_persistence", "passed": True}],
        },
    ).to_dict()

    assert gate["status"] == "failed"
    assert gate["summary"] == "top-level passed=false without failed performance budget rows"
    assert gate["raw_details"]["incoherent_failure"] is True
    assert gate["raw_details"]["failed_results"] == []


def test_quality_dashboard_main_writes_json_and_markdown(tmp_path: Path) -> None:
    release_evidence = tmp_path / "release-evidence.json"
    dependency_audit = tmp_path / "dependency-audit.json"
    core_performance = tmp_path / "core-performance.json"
    json_output = tmp_path / "quality-dashboard.json"
    markdown_output = tmp_path / "quality-dashboard.md"
    release_evidence.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "validation_gates": [
                    {
                        "name": gate.name,
                        "command": gate.command,
                        "status": "passed",
                        "exit_code": 0,
                        "triage_step": gate.triage_step,
                    }
                    for gate in generate_quality_dashboard.CHECKOUT_SAFE_GATES
                ],
                "live_provider_evidence": [],
                "extra_live_provider_evidence": [],
            }
        ),
        encoding="utf-8",
    )
    dependency_audit.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "generated_at": "2026-01-01T00:00:00+00:00",
                "status": "passed",
                "vulnerability_summary": {"vulnerability_count": 0},
                "vulnerabilities": [],
                "commands": {},
                "ignored_advisories": [],
                "first_triage_step": "Attach evidence.",
            }
        ),
        encoding="utf-8",
    )
    core_performance.write_text(
        json.dumps({"schema_version": 1, "passed": True, "results": []}),
        encoding="utf-8",
    )

    exit_code = main(
        [
            "--release-evidence",
            str(release_evidence),
            "--dependency-audit",
            str(dependency_audit),
            "--core-performance",
            str(core_performance),
            "--json-output",
            str(json_output),
            "--markdown-output",
            str(markdown_output),
        ]
    )

    assert exit_code == 0
    assert json.loads(json_output.read_text(encoding="utf-8"))["status"] == "passed"
    markdown = markdown_output.read_text(encoding="utf-8")
    assert markdown.startswith("# WorldForge Quality Dashboard")
    assert "- No failed, warning, or not-run gates." in markdown
    assert "- No skipped checks." in markdown


def test_quality_dashboard_main_rejects_non_finite_payload_before_touching_outputs(
    monkeypatch,
    tmp_path: Path,
) -> None:
    json_output = tmp_path / "nested" / "quality-dashboard.json"
    markdown_output = tmp_path / "reports" / "quality-dashboard.md"
    monkeypatch.setattr(
        generate_quality_dashboard,
        "build_quality_dashboard",
        lambda **_: {
            "schema_version": 1,
            "status": "passed",
            "duration_ms": math.inf,
        },
    )

    with pytest.raises(WorldForgeError, match="finite numbers"):
        main(["--json-output", str(json_output), "--markdown-output", str(markdown_output)])

    assert not json_output.exists()
    assert not json_output.parent.exists()
    assert not markdown_output.exists()
    assert not markdown_output.parent.exists()

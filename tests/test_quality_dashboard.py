from __future__ import annotations

import importlib.util
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

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
                        "provider": "runway",
                        "status": "host-owned",
                        "manifests": [],
                        "reason": "missing host-owned configuration: RUNWAYML_API_SECRET",
                    },
                    {
                        "provider": "cosmos",
                        "status": "passed",
                        "manifests": [
                            {
                                "path": ".worldforge/runs/cosmos/run_manifest.json",
                                "status": "passed",
                                "capability": "generate",
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
    assert gates["Optional live provider: runway"]["status"] == "skipped"
    assert gates["Optional live provider: runway"]["host_owned"] is True
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
    assert gates["Optional live provider: runway"]["status"] == "skipped"
    assert dashboard["summary"]["not-run"] >= 8


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
    assert markdown_output.read_text(encoding="utf-8").startswith("# WorldForge Quality Dashboard")

from __future__ import annotations

import importlib.util
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from subprocess import CompletedProcess
from typing import Any

from worldforge.testing import DeterministicClock

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "generate_dependency_audit_evidence.py"
SPEC = importlib.util.spec_from_file_location("generate_dependency_audit_evidence", SCRIPT)
assert SPEC is not None
generate_dependency_audit_evidence_module = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules["generate_dependency_audit_evidence"] = generate_dependency_audit_evidence_module
SPEC.loader.exec_module(generate_dependency_audit_evidence_module)
generate_dependency_audit_evidence = (
    generate_dependency_audit_evidence_module.generate_dependency_audit_evidence
)


def _fake_runner(*, audit_returncode: int, audit_payload: dict[str, Any] | None):
    def runner(command: tuple[str, ...], **kwargs: Any) -> CompletedProcess[str]:
        assert kwargs["cwd"] == ROOT
        assert kwargs["capture_output"] is True
        assert kwargs["text"] is True
        if command == ("uv", "--version"):
            return CompletedProcess(command, 0, stdout="uv 0.8.0\n", stderr="")
        if command == ("uvx", "--from", "pip-audit", "pip-audit", "--version"):
            return CompletedProcess(command, 0, stdout="pip-audit 2.9.0\n", stderr="")
        if command[:2] == ("uv", "export"):
            requirements_path = Path(command[-1])
            requirements_path.write_text(
                "httpx==0.28.1\npytest==8.4.0\n",
                encoding="utf-8",
            )
            return CompletedProcess(command, 0, stdout="", stderr="")
        if command[:4] == ("uvx", "--from", "pip-audit", "pip-audit"):
            stdout = json.dumps(audit_payload or {"dependencies": []})
            return CompletedProcess(
                command,
                audit_returncode,
                stdout=stdout,
                stderr="/Users/alice/work/token=secret should not leak",
            )
        raise AssertionError(f"unexpected command: {command}")

    return runner


def test_dependency_audit_evidence_records_clean_run() -> None:
    evidence = generate_dependency_audit_evidence(
        runner=_fake_runner(
            audit_returncode=0,
            audit_payload={
                "dependencies": [
                    {"name": "httpx", "version": "0.28.1", "vulns": []},
                    {"name": "pytest", "version": "8.4.0", "vulns": []},
                ]
            },
        ),
        now_utc=DeterministicClock(start=datetime(2026, 5, 11, tzinfo=UTC)).now,
    )

    payload = evidence.payload
    assert evidence.status == "passed"
    assert payload["status"] == "passed"
    assert payload["generated_at"] == "2026-05-11T00:00:00+00:00"
    assert payload["requirements"]["requirement_count"] == 2
    assert payload["requirements"]["temporary_file_preserved"] is False
    assert payload["requirements"]["dependency_names"] == ["httpx", "pytest"]
    assert payload["requirements"]["sha256"].startswith("sha256:")
    assert payload["tool_versions"] == {"uv": "uv 0.8.0", "pip_audit": "pip-audit 2.9.0"}
    assert payload["vulnerability_summary"]["vulnerability_count"] == 0
    assert "No vulnerability findings" in evidence.markdown
    assert "Temporary requirements file preserved: `false`" in evidence.markdown


def test_dependency_audit_evidence_preserves_findings_and_ignore_rationales() -> None:
    evidence = generate_dependency_audit_evidence(
        ignored_advisories=(
            {"id": "PYSEC-2026-1", "rationale": "Accepted until upstream releases a fix."},
        ),
        runner=_fake_runner(
            audit_returncode=1,
            audit_payload={
                "dependencies": [
                    {
                        "name": "vulnerable-pkg",
                        "version": "1.0",
                        "vulns": [
                            {
                                "id": "PYSEC-2026-1",
                                "aliases": ["CVE-2026-0001"],
                                "fix_versions": ["1.1"],
                                "description": "bad path /Users/alice/private and token=secret",
                            }
                        ],
                    }
                ]
            },
        ),
    )

    payload_text = json.dumps(evidence.payload, sort_keys=True)
    assert evidence.status == "findings"
    assert evidence.payload["vulnerability_summary"] == {
        "dependency_count": 1,
        "vulnerable_dependency_count": 1,
        "vulnerability_count": 1,
    }
    assert evidence.payload["vulnerabilities"][0]["id"] == "PYSEC-2026-1"
    assert evidence.payload["ignored_advisories"] == [
        {"id": "PYSEC-2026-1", "rationale": "Accepted until upstream releases a fix."}
    ]
    assert "--ignore-vuln PYSEC-2026-1" in evidence.payload["commands"]["pip_audit"]["command"]
    assert "/Users/alice" not in payload_text
    assert "token=secret" not in payload_text
    assert "<host-local-path>" in payload_text
    assert "[redacted]" in payload_text
    assert "Accepted until upstream releases a fix." in evidence.markdown


def test_dependency_audit_evidence_records_tool_unavailable() -> None:
    def runner(command: tuple[str, ...], **_kwargs: Any) -> CompletedProcess[str]:
        if command == ("uv", "--version"):
            return CompletedProcess(command, 0, stdout="uv 0.8.0\n", stderr="")
        if command == ("uvx", "--from", "pip-audit", "pip-audit", "--version"):
            raise FileNotFoundError("uvx not found")
        if command[:2] == ("uv", "export"):
            raise FileNotFoundError("uv not found")
        raise AssertionError(f"unexpected command: {command}")

    evidence = generate_dependency_audit_evidence(runner=runner)

    assert evidence.status == "tool-unavailable"
    assert evidence.payload["status"] == "tool-unavailable"
    assert evidence.payload["tool_versions"]["pip_audit"] == "unavailable"
    assert evidence.payload["commands"]["pip_audit"] is None
    assert "Install uv or run pip-audit through uvx" in evidence.payload["first_triage_step"]
    assert "tool-unavailable" in evidence.markdown

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

from worldforge import (
    LIVE_SMOKE_EVIDENCE_SCHEMA_VERSION,
    LIVE_SMOKE_EVIDENCE_STATUSES,
    WorldForgeError,
    render_live_smoke_registry_table,
    validate_live_smoke_entry,
    validate_live_smoke_registry,
)

ROOT = Path(__file__).resolve().parents[1]
REGISTRY_PATH = ROOT / "docs" / "src" / "live-smoke-evidence.json"
SCRIPT = ROOT / "scripts" / "generate_release_evidence.py"
SPEC = importlib.util.spec_from_file_location("generate_release_evidence_for_registry", SCRIPT)
assert SPEC is not None
generate_release_evidence = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules["generate_release_evidence_for_registry"] = generate_release_evidence
SPEC.loader.exec_module(generate_release_evidence)


def _registry() -> dict[str, object]:
    return json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))


def test_docs_live_smoke_registry_validates_and_records_first_class_skips() -> None:
    registry = validate_live_smoke_registry(_registry())

    assert registry["schema_version"] == LIVE_SMOKE_EVIDENCE_SCHEMA_VERSION
    statuses = {entry["status"] for entry in registry["entries"]}
    assert "skipped_missing_runtime" in statuses
    assert "skipped_missing_credentials" in statuses
    assert "not_run" in statuses
    assert statuses <= LIVE_SMOKE_EVIDENCE_STATUSES

    providers = {(entry["provider"], entry["capability"]) for entry in registry["entries"]}
    assert ("runway", "generate") in providers
    assert ("jepa-wms", "score") in providers

    for entry in registry["entries"]:
        if entry["status"].startswith("skipped") or entry["status"] == "not_run":
            assert entry["skip_reason"]
            assert entry["artifact_path"] is None
        assert entry["command"]
        assert entry["known_limitations"]


def test_live_smoke_registry_rejects_unsafe_entries() -> None:
    entry = {
        "provider": "runway",
        "capability": "generate",
        "command": "uv run worldforge-smoke-runway",
        "runtime_manifest": "runway:schema-1",
        "date": "2026-05-05",
        "version": "0.5.0",
        "status": "passed",
        "artifact_path": "https://example.test/run_manifest.json?token=secret",
        "skip_reason": None,
        "known_limitations": ["fixture"],
    }

    with pytest.raises(WorldForgeError, match="query strings"):
        validate_live_smoke_entry(entry)

    entry = {**entry, "artifact_path": ".worldforge/runs/runway/run_manifest.json"}
    entry["secret_token"] = "redacted"

    with pytest.raises(WorldForgeError, match="secret-like field"):
        validate_live_smoke_entry(entry)


def test_live_smoke_registry_requires_skip_reasons_and_artifacts() -> None:
    skipped = {
        "provider": "cosmos",
        "capability": "generate",
        "command": "uv run worldforge-smoke-cosmos",
        "runtime_manifest": "cosmos:schema-1",
        "date": "2026-05-05",
        "version": "0.5.0",
        "status": "skipped_missing_runtime",
        "artifact_path": None,
        "skip_reason": "",
        "known_limitations": ["fixture"],
    }

    with pytest.raises(WorldForgeError, match="skip_reason"):
        validate_live_smoke_entry(skipped)

    passed = {**skipped, "status": "passed", "skip_reason": None}

    with pytest.raises(WorldForgeError, match="artifact_path"):
        validate_live_smoke_entry(passed)


def test_release_evidence_can_include_registry_without_manual_copy_paste(tmp_path: Path) -> None:
    registry = validate_live_smoke_registry(_registry())
    report = generate_release_evidence.render_release_evidence(
        output=tmp_path / "release-evidence.md",
        manifests=(),
        benchmark_artifacts=(),
        artifacts=(),
        live_smoke_registry=registry,
    )

    assert "## Live Smoke Evidence Registry" in report
    assert "| `runway` | `generate` | skipped_missing_credentials |" in report
    assert "requires RUNWAYML_API_SECRET or RUNWAY_API_SECRET" in report


def test_live_smoke_registry_markdown_renderer_is_stable() -> None:
    lines = render_live_smoke_registry_table(_registry())

    assert lines[0] == "| Provider | Capability | Status | Evidence |"
    assert any("skipped_missing_runtime" in line for line in lines)

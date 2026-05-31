from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

from worldforge.demos.provider_failure_gallery import (
    PROVIDER_FAILURE_GALLERY_CLAIM_BOUNDARY,
    build_provider_failure_gallery_entries,
    build_provider_failure_gallery_report,
    render_provider_failure_gallery_markdown,
    run_provider_failure_gallery_workflow,
)

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "demo_showcases.py"


def _load_demo_showcases():
    spec = importlib.util.spec_from_file_location("provider_failure_gallery_script_test", SCRIPT)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_provider_failure_gallery_report_preserves_attachable_contract() -> None:
    entries = build_provider_failure_gallery_entries()
    report = build_provider_failure_gallery_report(entries)

    assert report["schema_version"] == 1
    assert report["entry_count"] == len(entries)
    assert report["providers"] == sorted({entry["provider"] for entry in entries})
    assert report["safe_to_attach"] is True
    assert report["claim_boundary"] == PROVIDER_FAILURE_GALLERY_CLAIM_BOUNDARY
    assert len(entries) >= 8

    for entry in entries:
        assert entry["id"]
        assert entry["provider"]
        assert entry["expected_event"]
        assert entry["expected_error"]
        assert entry["expected_artifact"]
        assert entry["owner"]
        assert entry["first_triage_command"].startswith(("uv run", "jq "))
        assert entry["first_triage_step"]
        assert entry["safe_artifact_behavior"]
        assert entry["safe_to_attach"] is True


def test_provider_failure_gallery_renders_and_writes_artifacts(tmp_path: Path) -> None:
    result = run_provider_failure_gallery_workflow(tmp_path)
    artifact_paths = result["artifact_paths"]
    assert isinstance(artifact_paths, dict)
    json_path = Path(str(artifact_paths["gallery_json"]))
    markdown_path = Path(str(artifact_paths["gallery_markdown"]))

    assert result["status"] == "passed"
    assert result["safe_to_attach"] is True
    assert json_path.is_file()
    assert markdown_path.is_file()

    payload = json.loads(json_path.read_text(encoding="utf-8"))
    markdown = markdown_path.read_text(encoding="utf-8")
    assert payload == result["report"]
    assert "# Provider Failure Mode Gallery" in markdown
    assert "## Safe Artifact Behavior" in markdown
    assert "`leworldmodel-score-count-mismatch`" in markdown
    assert render_provider_failure_gallery_markdown(payload) == markdown


def test_demo_showcase_script_keeps_provider_failure_gallery_entry_helper() -> None:
    module = _load_demo_showcases()

    assert (
        module.build_provider_failure_gallery_entries() == build_provider_failure_gallery_entries()
    )

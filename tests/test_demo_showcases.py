from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "demo_showcases.py"


def _load_demo_showcases():
    spec = importlib.util.spec_from_file_location("worldforge_demo_showcases_test", SCRIPT)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _summary(result: dict[str, object]) -> dict[str, object]:
    artifact_paths = result["artifact_paths"]
    assert isinstance(artifact_paths, dict)
    summary_json = artifact_paths["summary_json"]
    assert isinstance(summary_json, str)
    return json.loads(Path(summary_json).read_text(encoding="utf-8"))


def test_demo_showcase_cli_lists_all_issue_backed_workflows() -> None:
    completed = subprocess.run(
        [sys.executable, str(SCRIPT), "list", "--format", "json"],
        check=True,
        capture_output=True,
        text=True,
    )
    payload = json.loads(completed.stdout)
    workflows = payload["workflows"]

    assert [workflow["issue"] for workflow in workflows] == [*list(range(189, 199)), 237]
    assert [workflow["id"] for workflow in workflows] == [
        "first-run",
        "diagnostics-issue-bundle",
        "robotics-replay",
        "remote-media-dry-run",
        "adapter-author",
        "batch-eval",
        "service-host",
        "rerun-gallery",
        "failure-lab",
        "use-case-cookbook",
        "external-provider-package",
    ]


def test_demo_showcase_runner_preserves_all_workflow_contracts(tmp_path: Path) -> None:
    module = _load_demo_showcases()
    results = module.run_workflows("all", workspace_dir=tmp_path, overwrite=True)

    assert len(results) == 11
    assert all(result["safe_to_attach"] is True for result in results)
    assert all(result["status"] in {"passed", "skipped"} for result in results)

    summaries = {result["id"]: _summary(result) for result in results}
    run_manifests = [Path(str(result["run_manifest"])) for result in results]
    for manifest_path in run_manifests:
        assert manifest_path.is_file()
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        assert manifest["kind"] == "demo_showcase"
        assert manifest["artifact_paths"]["summary_json"] == "results/summary.json"
        assert manifest["artifact_paths"]["summary_markdown"] == "reports/summary.md"
        for relative_path in manifest["artifact_paths"].values():
            assert (manifest_path.parent / relative_path).exists()

    first_run = summaries["first-run"]
    assert first_run["provider"] == "mock"
    assert first_run["object_count"] == 1
    assert first_run["history_length"] >= 3
    assert first_run["preflight_status"] == "passed"
    assert Path(str(first_run["artifact_paths"]["exported_world"])).is_file()

    diagnostics = summaries["diagnostics-issue-bundle"]
    assert diagnostics["safe_to_attach"] is True
    assert "issue-bundle/issue.md" in diagnostics["artifact_tree"]
    assert Path(str(diagnostics["bundle_manifest"])).is_file()

    robotics = summaries["robotics-replay"]
    replay = robotics["replay"]
    assert replay["uses_optional_runtime"] is False
    assert isinstance(replay["candidate_costs"], list)
    assert replay["selected_candidate_index"] >= 0

    remote_media = summaries["remote-media-dry-run"]
    assert remote_media["redaction_verified"] is True
    rendered_events = json.dumps(remote_media["provider_events"])
    assert "fake-secret" not in rendered_events
    assert "token=fake" not in rendered_events

    adapter_author = summaries["adapter-author"]
    assert adapter_author["scaffold_incomplete"] is True
    assert "src/worldforge/providers/demo_wm.py" in adapter_author["generated_files"]
    assert "Promotion Work" in adapter_author["workbench_report"]

    batch_eval = summaries["batch-eval"]
    assert batch_eval["eval"]["status"] == "passed"
    assert batch_eval["benchmark"]["status"] == "failed"
    assert batch_eval["controlled_failure_exit_code"] == 1

    service_host = summaries["service-host"]
    assert service_host["readiness"]["status"] == "ready"
    assert service_host["request"]["request_id"] == "demo-request"
    assert service_host["shutdown"] == "server_close"

    rerun_gallery = summaries["rerun-gallery"]
    assert rerun_gallery["status"] == "skipped"
    assert rerun_gallery["manifest"]["requires_extra"] == "rerun"
    assert len(rerun_gallery["manifest"]["layers"]) >= 4

    failure_lab = summaries["failure-lab"]
    assert len(failure_lab["report"]["drills"]) == 3
    assert failure_lab["report"]["safe_to_attach"] is True
    assert failure_lab["report"]["recovery_commands"]

    cookbook = summaries["use-case-cookbook"]
    assert cookbook["recipe_count"] >= 7
    assert Path(str(cookbook["artifact_paths"]["cookbook"])).name == "use-case-cookbook.md"

    external_package = summaries["external-provider-package"]
    external_report = external_package["report"]
    assert external_report["entry_point_group"] == "worldforge.providers"
    assert external_report["discovery_enabled"]["discovered"][0]["name"] == "demo-external"
    assert external_report["discovery_disabled"]["enabled"] is False
    assert external_report["provider"]["capabilities"]["predict"] is True
    assert "missing dependency" in external_report["skip_reasons"]["needs-optional"]
    assert "duplicate name" in external_report["skip_reasons"]["mock"]
    assert "pyproject.toml" in external_report["generated_files"]
    assert Path(str(external_package["artifact_paths"]["discovery_report"])).is_file()


def test_demo_showcase_runner_rejects_unknown_workflow(tmp_path: Path) -> None:
    module = _load_demo_showcases()

    try:
        module.run_workflows("missing", workspace_dir=tmp_path)
    except KeyError as exc:
        assert exc.args == ("missing",)
    else:
        raise AssertionError("missing workflow should raise KeyError")

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from worldforge import WorldForgeError

ROOT = Path(__file__).resolve().parents[1]
OPERATOR_APP = ROOT / "examples" / "hosts" / "robotics-operator" / "app.py"


def _load_operator_app():
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "worldforge_robotics_operator_host_example",
        OPERATOR_APP,
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _checklist(app) -> dict[str, bool]:
    return dict.fromkeys(app.REQUIRED_CHECKS, True)


def test_robotics_operator_host_preserves_offline_review_artifacts(tmp_path) -> None:
    app = _load_operator_app()

    result = app.run_operator_review(
        workspace_dir=tmp_path / "workspace",
        state_dir=tmp_path / "worlds",
        action_translator=app.sample_pusht_translator,
        safety_checklist=_checklist(app),
        dry_run_approved=True,
    )

    assert result["status"] == "passed"
    assert result["exit_code"] == 0
    run_workspace = Path(result["run_workspace"])
    manifest = json.loads(Path(result["run_manifest"]).read_text(encoding="utf-8"))
    review = json.loads((run_workspace / "results" / "operator_review.json").read_text())
    approval = json.loads((run_workspace / "results" / "approval.json").read_text())
    replay = json.loads((run_workspace / "results" / "replay.json").read_text())

    assert manifest["kind"] == "robotics_operator_review"
    assert manifest["operation"] == "policy+score"
    assert manifest["status"] == "completed"
    assert manifest["result_summary"]["selected_candidate_index"] == 1
    assert manifest["result_summary"]["controller_executed"] is False
    assert manifest["artifact_paths"]["provider_events"] == "logs/provider-events.jsonl"
    assert (run_workspace / "logs" / "provider-events.jsonl").exists()
    assert (run_workspace / "reports" / "operator_review.md").exists()
    assert approval["dry_run_approved"] is True
    assert approval["controller_execution_requested"] is False
    assert approval["worldforge_certifies_robot_safety"] is False
    assert replay["mode"] == "dry_run_replay"
    assert replay["controller_calls"] == 0
    assert len(review["action_chunks"]) == 3
    assert review["action_chunks"][1]["selected"] is True
    assert review["score_rationale"]["lower_is_better"] is True
    assert review["events"]


def test_robotics_operator_host_requires_explicit_translator(tmp_path) -> None:
    app = _load_operator_app()

    with pytest.raises(WorldForgeError, match="explicit action translator"):
        app.run_operator_review(
            workspace_dir=tmp_path / "workspace",
            state_dir=tmp_path / "worlds",
            action_translator=None,
            safety_checklist=_checklist(app),
            dry_run_approved=True,
        )


def test_robotics_operator_host_blocks_controller_without_hook(tmp_path) -> None:
    app = _load_operator_app()

    with pytest.raises(WorldForgeError, match="controller execution is disabled"):
        app.run_operator_review(
            workspace_dir=tmp_path / "workspace",
            state_dir=tmp_path / "worlds",
            action_translator=app.sample_pusht_translator,
            safety_checklist=_checklist(app),
            dry_run_approved=True,
            execute_controller=True,
        )


def test_robotics_operator_host_records_host_supplied_controller_hook(tmp_path) -> None:
    app = _load_operator_app()
    calls = []

    def hook(actions, approval):
        calls.append((actions, approval))
        return {"status": "dry_run_dispatched", "action_count": len(actions)}

    result = app.run_operator_review(
        workspace_dir=tmp_path / "workspace",
        state_dir=tmp_path / "worlds",
        action_translator=app.sample_pusht_translator,
        safety_checklist=_checklist(app),
        dry_run_approved=True,
        execute_controller=True,
        controller_hook=hook,
    )

    review = json.loads(
        (Path(result["run_workspace"]) / "results" / "operator_review.json").read_text()
    )
    manifest = json.loads(Path(result["run_manifest"]).read_text(encoding="utf-8"))

    assert len(calls) == 1
    assert calls[0][1]["controller_hook_supplied"] is True
    assert manifest["result_summary"]["controller_executed"] is True
    assert review["controller_result"] == {"status": "dry_run_dispatched", "action_count": 2}


def test_robotics_operator_host_cli_defaults_to_safe_validation_error(tmp_path, capsys) -> None:
    app = _load_operator_app()

    exit_code = app.main(
        [
            "--workspace",
            str(tmp_path / "workspace"),
            "--state-dir",
            str(tmp_path / "worlds"),
            "review",
        ]
    )
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 2
    assert payload["error"]["type"] == "validation_error"
    assert "explicit action translator" in payload["error"]["message"]

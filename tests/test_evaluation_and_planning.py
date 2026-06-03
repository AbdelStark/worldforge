from __future__ import annotations

import importlib.util
import json
import math
import sys
from pathlib import Path

import pytest

from worldforge import (
    Position,
    WorldForge,
    WorldForgeError,
    action_candidates_to_score_payload,
    bounded_move_grid_candidates,
    cartesian_offset_candidates,
    list_eval_suites,
    object_near_candidates,
    run_eval,
    swap_action_candidates,
)
from worldforge.evaluation import (
    EvaluationReport,
    EvaluationResult,
    EvaluationSuite,
    ProviderSummary,
)
from worldforge.providers import MockProvider

ROOT = Path(__file__).resolve().parents[1]
DEMO_SHOWCASES = ROOT / "scripts" / "demo_showcases.py"


def test_evaluation_reports_carry_claim_boundaries(tmp_path) -> None:
    forge = WorldForge(state_dir=tmp_path)
    report = EvaluationSuite.from_builtin("physics").run_report(["mock"], forge=forge)
    payload = json.loads(report.to_json())
    markdown = report.to_markdown()
    artifacts = report.artifacts()

    assert "deterministic adapter contract checks" in payload["claim_boundary"]
    assert "typed contract" in payload["metric_semantics"]
    assert "Claim boundary:" in markdown
    assert payload["workflow_trace"]["schema_version"] == 1
    assert payload["workflow_trace"]["workflow_id"] == "evaluation:physics"
    assert payload["workflow_trace"]["status"] == "success"
    assert "workflow_trace.json" in artifacts
    assert "Workflow Trace" in artifacts["workflow_trace.md"]
    assert "Workflow Trace" in artifacts["html"]


def test_evaluation_result_contract_rejects_invalid_public_payloads() -> None:
    result = EvaluationResult(
        suite_id="suite",
        suite="Suite",
        scenario="scenario",
        provider="mock",
        score=0.5,
        passed=True,
        metrics={"nested": {"value": 1.0}},
    )
    result.metrics["nested"]["value"] = 0.25

    assert result.score == 0.5
    assert result.metrics == {"nested": {"value": 0.25}}

    with pytest.raises(WorldForgeError, match="EvaluationResult score"):
        EvaluationResult("suite", "Suite", "scenario", "mock", math.nan, True)
    with pytest.raises(WorldForgeError, match="EvaluationResult passed"):
        EvaluationResult("suite", "Suite", "scenario", "mock", 0.5, "yes")  # type: ignore[arg-type]
    with pytest.raises(WorldForgeError, match="EvaluationResult metrics"):
        EvaluationResult("suite", "Suite", "scenario", "mock", 0.5, True, {"bad": object()})
    with pytest.raises(WorldForgeError, match="ProviderSummary passed and failed"):
        ProviderSummary(
            "mock",
            0.5,
            scenario_count=2,
            passed_scenario_count=2,
            failed_scenario_count=1,
        )
    with pytest.raises(WorldForgeError, match="EvaluationReport results"):
        EvaluationReport("suite", "Suite", [object()])  # type: ignore[list-item]
    with pytest.raises(WorldForgeError, match="workflow_trace"):
        EvaluationReport("suite", "Suite", [], workflow_trace=object())  # type: ignore[arg-type]


def test_action_candidate_helpers_return_validated_action_sequences() -> None:
    plans = cartesian_offset_candidates(
        Position(0.0, 0.5, 0.0),
        [
            Position(0.1, 0.0, 0.0),
            [Position(0.2, 0.0, 0.0), Position(0.4, 0.0, 0.0)],
        ],
        object_id="cube-1",
    )
    assert [[action.to_dict() for action in plan] for plan in plans] == [
        [
            {
                "type": "move_to",
                "parameters": {
                    "target": {"x": 0.1, "y": 0.5, "z": 0.0},
                    "speed": 1.0,
                    "object_id": "cube-1",
                },
            }
        ],
        [
            {
                "type": "move_to",
                "parameters": {
                    "target": {"x": 0.2, "y": 0.5, "z": 0.0},
                    "speed": 1.0,
                    "object_id": "cube-1",
                },
            },
            {
                "type": "move_to",
                "parameters": {
                    "target": {"x": 0.4, "y": 0.5, "z": 0.0},
                    "speed": 1.0,
                    "object_id": "cube-1",
                },
            },
        ],
    ]

    near = object_near_candidates(
        Position(0.5, 0.5, 0.0),
        [Position(0.1, 0.0, 0.0)],
        object_id="cube-1",
    )
    assert near[0][0].parameters["target"] == {"x": 0.6, "y": 0.5, "z": 0.0}

    swap = swap_action_candidates(
        first_object_id="cube-1",
        first_position=Position(0.0, 0.5, 0.0),
        second_object_id="mug-1",
        second_position=Position(0.4, 0.8, 0.0),
    )
    assert len(swap) == 2
    assert [action.parameters["object_id"] for action in swap[0]] == ["cube-1", "mug-1"]
    assert action_candidates_to_score_payload(swap)[0][0]["parameters"]["target"] == {
        "x": 0.4,
        "y": 0.8,
        "z": 0.0,
    }


def test_bounded_move_grid_candidates_validate_bounds_and_non_finite_inputs() -> None:
    grid = bounded_move_grid_candidates(
        x_bounds=(0.1, 0.7),
        y_bounds=(0.5, 0.5),
        z_bounds=(0.0, 0.0),
        x_steps=3,
        y_steps=1,
        z_steps=1,
        object_id="cube-1",
    )

    assert [candidate[0].parameters["target"]["x"] for candidate in grid] == [0.1, 0.4, 0.7]

    with pytest.raises(WorldForgeError, match="x_bounds lower bound"):
        bounded_move_grid_candidates(
            x_bounds=(1.0, 0.0),
            y_bounds=(0.5, 0.5),
            z_bounds=(0.0, 0.0),
            x_steps=3,
            y_steps=1,
            z_steps=1,
        )
    with pytest.raises(WorldForgeError, match="x_bounds must contain exactly two"):
        bounded_move_grid_candidates(
            x_bounds=(0.0, 0.5, 1.0),
            y_bounds=(0.5, 0.5),
            z_bounds=(0.0, 0.0),
            x_steps=3,
            y_steps=1,
            z_steps=1,
        )
    with pytest.raises(WorldForgeError, match=r"y_bounds\[1\]"):
        bounded_move_grid_candidates(
            x_bounds=(0.0, 1.0),
            y_bounds=(0.5, math.nan),
            z_bounds=(0.0, 0.0),
            x_steps=3,
            y_steps=1,
            z_steps=1,
        )
    with pytest.raises(WorldForgeError, match="x_steps"):
        bounded_move_grid_candidates(
            x_bounds=(0.0, 1.0),
            y_bounds=(0.5, 0.5),
            z_bounds=(0.0, 0.0),
            x_steps=0,
            y_steps=1,
            z_steps=1,
        )
    with pytest.raises(WorldForgeError, match="offsets"):
        cartesian_offset_candidates(Position(0.0, 0.0, 0.0), [])
    with pytest.raises(WorldForgeError, match=r"offsets\[0\] must contain only Position"):
        cartesian_offset_candidates(Position(0.0, 0.0, 0.0), [[object()]])  # type: ignore[list-item]
    with pytest.raises(WorldForgeError, match="distinct"):
        swap_action_candidates(
            first_object_id="cube-1",
            first_position=Position(0.0, 0.5, 0.0),
            second_object_id="cube-1",
            second_position=Position(0.4, 0.8, 0.0),
        )


def test_policy_score_candidate_lab_demo_preserves_selection_and_failures(tmp_path) -> None:
    spec = importlib.util.spec_from_file_location(
        "worldforge_policy_score_candidate_lab_test",
        DEMO_SHOWCASES,
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)

    results = module.run_workflows(
        "policy-score-candidate-lab",
        workspace_dir=tmp_path,
        overwrite=True,
    )
    summary_path = Path(results[0]["artifact_paths"]["summary_json"])
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    report = summary["report"]

    assert report["planning_mode"] == "policy+score"
    assert report["selected_candidate_index"] == 1
    assert report["candidate_table"][1]["selected"] is True
    assert report["raw_policy_actions"]["raw_policy_action_preserved"] is True
    assert report["score_metadata"]["candidate_count"] == 3
    assert "lower bound" in report["expected_failures"]["invalid_candidate_bounds"]
    assert "action_translator" in report["expected_failures"]["missing_translator"]


def test_evaluation_reports_and_eval_helpers(tmp_path) -> None:
    forge = WorldForge(state_dir=tmp_path)
    forge.register_provider(MockProvider(name="manual-mock"))

    assert list_eval_suites() == ["physics", "planning"]

    suite = EvaluationSuite.from_builtin("physics")
    report = suite.run_report(["mock", "manual-mock"], forge=forge)
    assert report.suite_id == "physics"
    assert "Physics" in report.suite
    assert {summary.provider for summary in report.provider_summaries} == {"manual-mock", "mock"}
    assert len(report.results) == 4
    assert {result.scenario for result in report.results} == {
        "object-stability",
        "action-response",
    }
    assert all(result.passed for result in report.results)

    artifacts = suite.run_report_artifacts(
        providers=["mock", "manual-mock"],
        forge=forge,
    )
    assert set(artifacts) == {
        "json",
        "markdown",
        "csv",
        "html",
        "failure_gallery.json",
        "failure_gallery.md",
        "workflow_trace.json",
        "workflow_trace.md",
    }
    assert json.loads(artifacts["json"])["suite_id"] == "physics"
    assert artifacts["markdown"].startswith("# Evaluation Report")
    assert "metrics_json" in artifacts["csv"]

    results = run_eval("physics", "mock", forge=forge)
    assert len(results) == 2
    assert results[0].provider == "mock"
    assert all(result.passed for result in results)


def test_planning_suite_covers_core_workflows(tmp_path) -> None:
    forge = WorldForge(state_dir=tmp_path)

    planning_report = EvaluationSuite.from_builtin("planning").run_report("mock", forge=forge)
    assert planning_report.suite_id == "planning"
    assert len(planning_report.results) == 4
    assert {result.scenario for result in planning_report.results} == {
        "object-relocation",
        "object-neighbor-placement",
        "object-swap",
        "object-spawn",
    }
    assert all(result.passed for result in planning_report.results)


def test_evaluation_suite_validation_errors_are_explicit() -> None:
    with pytest.raises(WorldForgeError, match="Unknown evaluation suite"):
        EvaluationSuite.from_builtin("unknown")

    with pytest.raises(WorldForgeError, match="Unknown evaluation suite"):
        EvaluationSuite.from_builtin("reasoning")

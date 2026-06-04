from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType

import pytest

from worldforge.cli import main as cli_main
from worldforge.demos.go2_controlbench_decisiontrace import (
    DEFAULT_TRACE_PATH,
    GO2_CONTROLBENCH_SCORE_PROVIDER,
    Go2ControlBenchTraceScoreProvider,
    load_go2_controlbench_trace,
    render_go2_controlbench_report,
    run_go2_controlbench_decisiontrace,
)
from worldforge.models import WorldForgeError


def _load_demo() -> ModuleType:
    script_path = (
        Path(__file__).resolve().parents[1]
        / "examples"
        / "go2-controlbench-decisiontrace"
        / "run.py"
    )
    spec = importlib.util.spec_from_file_location(
        "go2_controlbench_decisiontrace_demo",
        script_path,
    )
    if spec is None:
        raise AssertionError("go2 controlbench demo module spec could not be created.")
    if spec.loader is None:
        raise AssertionError("go2 controlbench demo module spec has no loader.")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_go2_controlbench_trace_fixture_loads_public_positive_regret() -> None:
    trace = load_go2_controlbench_trace(DEFAULT_TRACE_PATH)

    assert trace["schema_version"] == "decision_trace.v1-draft"
    assert trace["trace_id"] == "combined_inverse_translation_target_0_010049"
    assert trace["observation"]["dataset"] == "combined"
    assert trace["observation"]["task"] == "translation_signed_planar"
    assert len(trace["candidate_actions"]) == 14
    assert len(trace["scores"]) == 14
    assert len(trace["counterfactuals"]) == 14
    assert trace["selected_action"]["name"] == "backward_0.08"
    assert trace["measured_or_analytic_outcome"]["best_measured_candidate"] == "forward_0.08"
    assert trace["regret"]["regret"] > 0.015
    json.dumps(trace)


def test_go2_controlbench_demo_reranks_and_reports_measured_regret(tmp_path: Path) -> None:
    result = run_go2_controlbench_decisiontrace(DEFAULT_TRACE_PATH, tmp_path)
    summary = result.summary

    assert result.decision_trace_path.is_file()
    assert result.report_path.is_file()
    assert summary["demo_kind"] == "go2_controlbench_decisiontrace"
    assert summary["runtime_mode"] == "checkout_safe_public_trace_fixture"
    assert summary["uses_real_robot_hardware"] is False
    assert summary["uses_dimos_runtime"] is False
    assert summary["uses_unitree_sdk"] is False
    assert summary["planning_mode"] == "score"
    assert summary["score_provider"] == GO2_CONTROLBENCH_SCORE_PROVIDER
    assert summary["score_result"]["best_index"] == 1
    assert summary["selected"]["name"] == "backward_0.08"
    assert summary["best_measured"]["name"] == "forward_0.08"
    assert summary["regret"] == pytest.approx(0.015573580206596351)
    assert summary["hit_best"] is False
    assert "positive measured regret" in summary["worldforge_value"]
    assert summary["trace"]["source_outcome_kind"] == "real_measured_native_odom_mean"
    assert result.report_path.read_text(encoding="utf-8") == result.report_markdown
    assert "not mocap-grade ground truth" in result.report_markdown
    json.dumps(summary)


def test_go2_controlbench_demo_uses_deterministic_tie_break(tmp_path: Path) -> None:
    trace = load_go2_controlbench_trace(DEFAULT_TRACE_PATH)
    tied_score = trace["scores"][1]["value"]
    trace["scores"][0]["value"] = tied_score
    trace["selected_action"] = {
        "candidate_index": 0,
        "name": "backward_0.05",
        "selection_rule": "minimize predicted absolute error to target",
    }

    selected_error = trace["counterfactuals"][0]["measured_error"]
    best_error = min(
        counterfactual["measured_error"] for counterfactual in trace["counterfactuals"]
    )
    trace["regret"] = {
        "unit": "m",
        "selected_true_error": selected_error,
        "best_true_error": best_error,
        "regret": selected_error - best_error,
        "hit_best": False,
    }
    trace_path = tmp_path / "equal-score-trace.json"
    trace_path.write_text(json.dumps(trace), encoding="utf-8")

    # A DEFAULT_TRACE_PATH mutation exercised through run_go2_controlbench_decisiontrace
    # should keep GO2_CONTROLBENCH_SCORE_PROVIDER ties stable by candidate order.
    result = run_go2_controlbench_decisiontrace(trace_path, tmp_path / "out")
    summary = result.summary

    assert summary["score_provider"] == GO2_CONTROLBENCH_SCORE_PROVIDER
    assert summary["score_result"]["best_index"] == 0
    assert summary["selected"]["name"] == "backward_0.05"
    assert [row["candidate_index"] for row in summary["ranked_candidates"][:2]] == [0, 1]


def test_go2_controlbench_report_lists_selected_and_counterfactual_best(tmp_path: Path) -> None:
    result = run_go2_controlbench_decisiontrace(DEFAULT_TRACE_PATH, tmp_path)
    report = render_go2_controlbench_report(result.summary)

    assert "Go2 Air ControlBench DecisionTrace" in report
    assert "Selected by predicted score: `backward_0.08`" in report
    assert "Best measured candidate: `forward_0.08`" in report
    assert "Measured regret" in report
    assert "What WorldForge Adds" in report


def test_go2_controlbench_demo_wrapper_runs_default_fixture() -> None:
    demo = _load_demo()

    summary = demo.run_demo(emit=False)

    assert summary["demo_kind"] == "go2_controlbench_decisiontrace"
    assert summary["selected"]["name"] == "backward_0.08"
    assert summary["best_measured"]["name"] == "forward_0.08"


def test_go2_controlbench_provider_rejects_missing_scores() -> None:
    provider = Go2ControlBenchTraceScoreProvider()
    trace = load_go2_controlbench_trace(DEFAULT_TRACE_PATH)

    with pytest.raises(WorldForgeError, match="non-empty scores list"):
        provider.score_actions(info={}, action_candidates=trace["candidate_actions"])


def test_go2_controlbench_fixture_rejects_score_order_drift(tmp_path: Path) -> None:
    trace = load_go2_controlbench_trace(DEFAULT_TRACE_PATH)
    trace["scores"][0]["candidate_index"] = 1
    malformed = tmp_path / "bad-trace.json"
    malformed.write_text(json.dumps(trace), encoding="utf-8")

    with pytest.raises(WorldForgeError, match="candidate_index must match candidate order"):
        load_go2_controlbench_trace(malformed)


def test_go2_controlbench_fixture_rejects_selected_action_drift(tmp_path: Path) -> None:
    trace = load_go2_controlbench_trace(DEFAULT_TRACE_PATH)
    trace["selected_action"]["name"] = "forward_0.08"
    malformed = tmp_path / "bad-selected.json"
    malformed.write_text(json.dumps(trace), encoding="utf-8")

    with pytest.raises(WorldForgeError, match=r"selected_action\.name does not match"):
        load_go2_controlbench_trace(malformed)


def test_go2_controlbench_fixture_rejects_incomplete_counterfactual_outcome(
    tmp_path: Path,
) -> None:
    trace = load_go2_controlbench_trace(DEFAULT_TRACE_PATH)
    del trace["counterfactuals"][0]["measured_outcome"]["n"]
    malformed = tmp_path / "bad-counterfactual-outcome.json"
    malformed.write_text(json.dumps(trace), encoding="utf-8")

    with pytest.raises(WorldForgeError, match=r"counterfactuals\[0\].measured_outcome.n"):
        load_go2_controlbench_trace(malformed)


def test_go2_controlbench_fixture_rejects_incomplete_predicted_outcome(
    tmp_path: Path,
) -> None:
    trace = load_go2_controlbench_trace(DEFAULT_TRACE_PATH)
    del trace["counterfactuals"][0]["predicted_outcome"]["signed_planar_m"]
    malformed = tmp_path / "bad-counterfactual-predicted-outcome.json"
    malformed.write_text(json.dumps(trace), encoding="utf-8")

    with pytest.raises(
        WorldForgeError,
        match=r"counterfactuals\[0\]\.predicted_outcome\.signed_planar_m",
    ):
        load_go2_controlbench_trace(malformed)


def test_go2_controlbench_fixture_rejects_zero_sample_counterfactual_outcome(
    tmp_path: Path,
) -> None:
    trace = load_go2_controlbench_trace(DEFAULT_TRACE_PATH)
    trace["counterfactuals"][0]["measured_outcome"]["n"] = 0
    malformed = tmp_path / "bad-counterfactual-zero-samples.json"
    malformed.write_text(json.dumps(trace), encoding="utf-8")

    with pytest.raises(WorldForgeError, match=r"counterfactuals\[0\]\.measured_outcome\.n"):
        load_go2_controlbench_trace(malformed)


def test_go2_controlbench_fixture_rejects_counterfactual_outcome_kind_drift(
    tmp_path: Path,
) -> None:
    trace = load_go2_controlbench_trace(DEFAULT_TRACE_PATH)
    trace["counterfactuals"][0]["measured_outcome"]["outcome_kind"] = "analytic"
    malformed = tmp_path / "bad-counterfactual-outcome-kind.json"
    malformed.write_text(json.dumps(trace), encoding="utf-8")

    with pytest.raises(WorldForgeError, match=r"measured_outcome\.outcome_kind"):
        load_go2_controlbench_trace(malformed)


def test_go2_controlbench_fixture_accepts_counterfactual_action_float_drift(
    tmp_path: Path,
) -> None:
    trace = load_go2_controlbench_trace(DEFAULT_TRACE_PATH)
    trace["counterfactuals"][0]["action"]["params"]["x"] += 1e-12
    drifted = tmp_path / "counterfactual-action-float-drift.json"
    drifted.write_text(json.dumps(trace), encoding="utf-8")

    loaded = load_go2_controlbench_trace(drifted)

    assert loaded["trace_id"] == trace["trace_id"]


def test_go2_controlbench_fixture_rejects_counterfactual_action_drift(
    tmp_path: Path,
) -> None:
    trace = load_go2_controlbench_trace(DEFAULT_TRACE_PATH)
    trace["counterfactuals"][0], trace["counterfactuals"][1] = (
        trace["counterfactuals"][1],
        trace["counterfactuals"][0],
    )
    malformed = tmp_path / "bad-counterfactual-order.json"
    malformed.write_text(json.dumps(trace), encoding="utf-8")

    with pytest.raises(WorldForgeError, match="counterfactual action must match candidate action"):
        load_go2_controlbench_trace(malformed)


def test_go2_controlbench_examples_index_entry(
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(sys, "argv", ["worldforge", "examples", "--format", "json"])

    assert cli_main() == 0

    examples = json.loads(capsys.readouterr().out)
    controlbench = next(
        item for item in examples if item["name"] == "go2-controlbench-decisiontrace"
    )
    assert controlbench["command"] == "uv run python examples/go2-controlbench-decisiontrace/run.py"
    assert "measured regret" in controlbench["surface"]

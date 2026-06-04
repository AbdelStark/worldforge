"""Go2 Air ControlBench decision-trace replay demo.

This demo is checkout-safe: it does not import DimOS, Unitree SDKs, Hugging Face
datasets, or robot-control libraries, and it never connects to hardware. It consumes
a compact public ``go2-air-controlbench-v1`` DecisionTrace fixture, reranks the
candidate commands through ``forge.score_actions``, and reports the measured regret
against native Go2 odometry outcomes.

The goal is deliberately narrow: show the evidence layer WorldForge should own.
The source dataset remains host-owned; robot execution, raw media, ArUco processing,
and native-rate export stay outside the base package.
"""

from __future__ import annotations

import argparse
import json
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from worldforge import ActionScoreResult, WorldForge
from worldforge.artifact_io import write_json_artifact
from worldforge.models import JSONDict, WorldForgeError, require_finite_number
from worldforge.providers.base import ProviderProfileSpec

_REPO_FIXTURE_RELATIVE_PATH = (
    Path("examples") / "go2-controlbench-decisiontrace" / "fixtures" / "positive_regret_trace.json"
)
DEFAULT_TRACE_PATH = (
    Path.cwd() / _REPO_FIXTURE_RELATIVE_PATH
    if (Path.cwd() / _REPO_FIXTURE_RELATIVE_PATH).is_file()
    else Path(__file__).resolve().parents[3] / _REPO_FIXTURE_RELATIVE_PATH
)

GO2_CONTROLBENCH_SCORE_PROVIDER = "go2-controlbench-deadband-affine-score"
GO2_CONTROLBENCH_DATASET_REFERENCE: JSONDict = {
    "repo_id": "espejelomar/go2-air-controlbench-v1",
    "config": "inverse_command_benchmark",
    "trace_path": "decision_traces/decision_trace_inverse_command_combined_positive_regret.json",
    "source": "Hugging Face public dataset",
    "runtime_mode": "checkout_safe_public_trace_fixture_no_download",
}


@dataclass(frozen=True, slots=True)
class Go2ControlBenchDecisionTraceResult:
    trace: JSONDict
    report_markdown: str
    summary: JSONDict
    decision_trace_path: Path
    report_path: Path


class Go2ControlBenchTraceScoreProvider:
    """Score provider that replays public ControlBench predicted-error scores."""

    name = GO2_CONTROLBENCH_SCORE_PROVIDER
    profile = ProviderProfileSpec(
        description=(
            "Checkout-safe Go2 Air ControlBench scorer over public DecisionTrace candidates."
        ),
        implementation_status="demo",
        is_local=True,
        deterministic=True,
    )

    def score_actions(self, *, info: JSONDict, action_candidates: object) -> ActionScoreResult:
        scores = _score_records(info)
        candidates = _candidate_payloads(action_candidates)
        if len(scores) != len(candidates):
            raise WorldForgeError(
                "Go2 ControlBench trace score count must match candidate action count."
            )

        values: list[float] = []
        score_components: list[JSONDict] = []
        for index, (score, candidate) in enumerate(zip(scores, candidates, strict=True)):
            if int(score["candidate_index"]) != index:
                raise WorldForgeError(
                    "Go2 ControlBench score candidate_index must match candidate order."
                )
            values.append(float(score["value"]))
            score_components.append(
                {
                    "candidate_index": index,
                    "candidate_name": _command_name(candidate),
                    "score_kind": str(score["score_kind"]),
                    "predicted_absolute_error": float(score["value"]),
                    "action": candidate,
                }
            )

        best_index = min(range(len(values)), key=lambda candidate_index: values[candidate_index])
        return ActionScoreResult(
            provider=self.name,
            scores=values,
            best_index=best_index,
            lower_is_better=True,
            metadata={
                "score_source": "public_controlbench_deadband_affine_prediction",
                "trace_id": str(info.get("trace_id", "")),
                "dataset_reference": dict(GO2_CONTROLBENCH_DATASET_REFERENCE),
                "score_components": score_components,
                "claim_boundary": (
                    "In-sample command-selection diagnostic over observed command groups; "
                    "not held-out learned-policy performance."
                ),
            },
        )


def load_go2_controlbench_trace(path: Path = DEFAULT_TRACE_PATH) -> JSONDict:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        message = f"Go2 ControlBench trace fixture not found: {path}"
        if path == DEFAULT_TRACE_PATH:
            message += (
                ". The bundled default is repo-local; pass --trace with a public "
                "DecisionTrace JSON file when running from an installed wheel."
            )
        raise WorldForgeError(message) from exc
    except json.JSONDecodeError as exc:
        raise WorldForgeError(f"Go2 ControlBench trace fixture is invalid JSON: {path}") from exc
    _validate_trace(payload)
    return payload


def run_go2_controlbench_decisiontrace(
    trace_path: Path = DEFAULT_TRACE_PATH,
    output_dir: Path = Path(".worldforge/go2-controlbench-decisiontrace"),
) -> Go2ControlBenchDecisionTraceResult:
    trace = load_go2_controlbench_trace(trace_path)
    output_dir.mkdir(parents=True, exist_ok=True)

    forge = WorldForge(auto_register_remote=False)
    forge.register_cost(Go2ControlBenchTraceScoreProvider())
    score_result = forge.score_actions(
        GO2_CONTROLBENCH_SCORE_PROVIDER,
        info={
            "trace_id": trace["trace_id"],
            "scores": trace["scores"],
        },
        action_candidates=trace["candidate_actions"],
    ).to_dict()
    summary = _summary(trace, score_result)
    report_markdown = render_go2_controlbench_report(summary)

    decision_trace_path = output_dir / "decision-trace.json"
    report_path = output_dir / "report.md"
    write_json_artifact(decision_trace_path, trace)
    report_path.write_text(report_markdown, encoding="utf-8")
    return Go2ControlBenchDecisionTraceResult(
        trace=trace,
        report_markdown=report_markdown,
        summary=summary,
        decision_trace_path=decision_trace_path,
        report_path=report_path,
    )


def run_demo(*, emit: bool = True) -> JSONDict:
    """Run the default public-trace replay and return a JSON-serializable summary."""

    result = run_go2_controlbench_decisiontrace()
    if emit:
        _print_summary(result.summary)
    return result.summary


def render_go2_controlbench_report(summary: JSONDict) -> str:
    trace = _require_mapping(summary["trace"], "summary.trace")
    selected = _require_mapping(summary["selected"], "summary.selected")
    best_measured = _require_mapping(summary["best_measured"], "summary.best_measured")
    rows = summary["ranked_candidates"]
    lines = [
        "# Go2 Air ControlBench DecisionTrace",
        "",
        f"- Trace: `{trace['trace_id']}`",
        f"- Dataset: `{GO2_CONTROLBENCH_DATASET_REFERENCE['repo_id']}`",
        f"- Target: `{summary['target']:.6f} {summary['unit']}`",
        f"- Selected by predicted score: `{selected['name']}`",
        f"- Best measured candidate: `{best_measured['name']}`",
        f"- Measured regret: `{summary['regret']:.6f} {summary['unit']}`",
        f"- Hit measured best: `{summary['hit_best']}`",
        "",
        "## Ranked Candidates",
        "",
        "| Rank | Candidate | Predicted Error | Measured Error | Measured Outcome |",
        "| ---: | --- | ---: | ---: | ---: |",
    ]
    for row in rows[:8]:
        marker = " selected" if row["candidate_index"] == selected["candidate_index"] else ""
        lines.append(
            f"| {row['predicted_rank']} | `{row['name']}`{marker} | "
            f"{row['predicted_error']:.6f} | {row['measured_error']:.6f} | "
            f"{row['measured_outcome']:.6f} |"
        )
    lines.extend(
        [
            "",
            "## What WorldForge Adds",
            "",
            (
                "The demo reranks candidate Go2 commands through the WorldForge `score` "
                "capability, preserves the selected action, exposes counterfactual measured "
                "outcomes, and computes regret against the best measured candidate."
            ),
            "",
            "## Boundary",
            "",
            (
                "Checkout-safe public fixture only. The source outcomes are real measured native "
                "Go2 odometry means from the public ControlBench dataset, not mocap-grade ground "
                "truth. This is an in-sample command-selection diagnostic, not a world-model SOTA "
                "or live-robot claim."
            ),
            "",
        ]
    )
    return "\n".join(lines)


def _summary(trace: JSONDict, score_result: JSONDict) -> JSONDict:
    candidates = list(trace["candidate_actions"])
    counterfactuals = list(trace["counterfactuals"])
    scores = list(score_result["scores"])
    selected_index = int(score_result["best_index"])
    target = _number(trace["goal"]["target"], name="goal.target")
    unit = str(trace["goal"]["unit"])
    ranked_indices = sorted(range(len(scores)), key=scores.__getitem__)
    candidate_rows: list[JSONDict] = []
    for index in ranked_indices:
        counterfactual = _require_mapping(counterfactuals[index], f"counterfactuals[{index}]")
        measured_outcome = _require_mapping(
            counterfactual["measured_outcome"],
            f"counterfactuals[{index}].measured_outcome",
        )
        candidate_rows.append(
            {
                "candidate_index": index,
                "name": _command_name(candidates[index]),
                "action": candidates[index],
                "predicted_rank": ranked_indices.index(index) + 1,
                "predicted_error": float(scores[index]),
                "predicted_outcome": float(counterfactual["predicted_outcome"]["signed_planar_m"]),
                "measured_outcome": float(measured_outcome["signed_planar_m"]),
                "measured_error": abs(float(measured_outcome["signed_planar_m"]) - target),
                "measured_n": int(measured_outcome["n"]),
            }
        )

    selected_row = next(row for row in candidate_rows if row["candidate_index"] == selected_index)
    best_measured_row = min(candidate_rows, key=lambda row: row["measured_error"])
    regret = float(selected_row["measured_error"]) - float(best_measured_row["measured_error"])
    recorded_regret = _require_mapping(trace["regret"], "regret")
    if not math.isclose(regret, float(recorded_regret["regret"]), rel_tol=1e-9, abs_tol=1e-9):
        raise WorldForgeError(
            "Go2 ControlBench trace regret is inconsistent with measured counterfactuals."
        )
    return {
        "demo_kind": "go2_controlbench_decisiontrace",
        "runtime_mode": "checkout_safe_public_trace_fixture",
        "uses_real_robot_hardware": False,
        "uses_dimos_runtime": False,
        "uses_unitree_sdk": False,
        "planning_mode": "score",
        "score_provider": GO2_CONTROLBENCH_SCORE_PROVIDER,
        "dataset_reference": dict(GO2_CONTROLBENCH_DATASET_REFERENCE),
        "trace": {
            "trace_id": str(trace["trace_id"]),
            "schema_version": str(trace["schema_version"]),
            "source_outcome_kind": str(trace["measured_or_analytic_outcome"]["outcome_kind"]),
            "claim_boundaries": list(trace["claim_boundaries"]),
        },
        "target": target,
        "unit": unit,
        "selected": selected_row,
        "best_measured": best_measured_row,
        "regret": regret,
        "hit_best": bool(recorded_regret["hit_best"]),
        "score_result": score_result,
        "ranked_candidates": candidate_rows,
        "worldforge_value": _worldforge_value(regret=regret, selected_index=selected_index),
        "claim_boundary": (
            "WorldForge consumes public measured-outcome evidence and exposes candidate "
            "ranking/regret; hardware execution and dataset production remain host-owned."
        ),
    }


def _worldforge_value(*, regret: float, selected_index: int) -> str:
    if regret > 0.0:
        return (
            "exposed a positive measured regret for the score-selected action and preserved "
            "the counterfactual command that would have done better"
        )
    if selected_index >= 0:
        return "confirmed the score-selected action matched the best measured candidate"
    return "no demonstrated value beyond logging; pivot if this persists"


def _validate_trace(payload: object) -> None:
    trace = _require_mapping(payload, "trace")
    _require_fields(
        trace,
        (
            "schema_version",
            "trace_id",
            "observation",
            "goal",
            "candidate_actions",
            "scores",
            "selected_action",
            "counterfactuals",
            "measured_or_analytic_outcome",
            "regret",
            "claim_boundaries",
        ),
        "trace",
    )
    if trace["schema_version"] != "decision_trace.v1-draft":
        raise WorldForgeError(
            "Go2 ControlBench trace schema_version must be decision_trace.v1-draft."
        )

    candidates = _candidate_payloads(trace["candidate_actions"])
    scores = _score_records({"scores": trace["scores"]})
    counterfactuals = _counterfactual_records(trace["counterfactuals"])
    if len(candidates) != len(scores) or len(candidates) != len(counterfactuals):
        raise WorldForgeError(
            "Go2 ControlBench trace candidates, scores, and counterfactuals must align."
        )
    for index, (candidate, counterfactual) in enumerate(
        zip(candidates, counterfactuals, strict=True)
    ):
        if counterfactual["action"] != candidate:
            raise WorldForgeError(
                "Go2 ControlBench counterfactual action must match candidate action "
                f"at index {index}."
            )

    selected = _require_mapping(trace["selected_action"], "selected_action")
    selected_index = _index(selected.get("candidate_index"), name="selected_action.candidate_index")
    if selected_index >= len(candidates):
        raise WorldForgeError("Go2 ControlBench selected_action.candidate_index is out of range.")
    if str(selected.get("name")) != _command_name(candidates[selected_index]):
        raise WorldForgeError("Go2 ControlBench selected_action.name does not match candidate.")
    best_index = min(range(len(scores)), key=lambda index: float(scores[index]["value"]))
    if selected_index != best_index:
        raise WorldForgeError("Go2 ControlBench selected_action must match the lowest score.")

    goal = _require_mapping(trace["goal"], "goal")
    _number(goal.get("target"), name="goal.target")
    if goal.get("unit") not in {"m", "rad"}:
        raise WorldForgeError("Go2 ControlBench goal.unit must be 'm' or 'rad'.")

    measured = _require_mapping(
        trace["measured_or_analytic_outcome"],
        "measured_or_analytic_outcome",
    )
    if measured.get("outcome_kind") != "real_measured_native_odom_mean":
        raise WorldForgeError(
            "Go2 ControlBench measured outcome must be real_measured_native_odom_mean."
        )
    _number(measured.get("signed_planar_m"), name="measured_or_analytic_outcome.signed_planar_m")

    regret = _require_mapping(trace["regret"], "regret")
    for field_name in ("selected_true_error", "best_true_error", "regret"):
        _number(regret.get(field_name), name=f"regret.{field_name}")
    if not isinstance(regret.get("hit_best"), bool):
        raise WorldForgeError("Go2 ControlBench regret.hit_best must be a boolean.")
    if not isinstance(trace["claim_boundaries"], list) or not trace["claim_boundaries"]:
        raise WorldForgeError("Go2 ControlBench trace must include claim_boundaries.")


def _counterfactual_records(value: object) -> list[JSONDict]:
    if not isinstance(value, list) or not value:
        raise WorldForgeError("Go2 ControlBench counterfactuals must be a non-empty list.")
    records: list[JSONDict] = []
    for index, raw in enumerate(value):
        record = _require_mapping(raw, f"counterfactuals[{index}]")
        _require_fields(
            record,
            (
                "action",
                "predicted_outcome",
                "measured_outcome",
                "predicted_error",
                "measured_error",
            ),
            f"counterfactuals[{index}]",
        )
        action = _validate_action(record["action"], name=f"counterfactuals[{index}].action")
        _number(record["predicted_error"], name=f"counterfactuals[{index}].predicted_error")
        _number(record["measured_error"], name=f"counterfactuals[{index}].measured_error")
        predicted = _require_mapping(
            record["predicted_outcome"],
            f"counterfactuals[{index}].predicted_outcome",
        )
        _number(
            predicted.get("signed_planar_m"),
            name=f"counterfactuals[{index}].predicted_outcome.signed_planar_m",
        )
        measured = _require_mapping(
            record["measured_outcome"],
            f"counterfactuals[{index}].measured_outcome",
        )
        _number(
            measured.get("signed_planar_m"),
            name=f"counterfactuals[{index}].measured_outcome.signed_planar_m",
        )
        _index(measured.get("n"), name=f"counterfactuals[{index}].measured_outcome.n")
        records.append(
            {
                **dict(record),
                "action": action,
                "predicted_outcome": dict(predicted),
                "measured_outcome": dict(measured),
            }
        )
    return records


def _score_records(info: JSONDict) -> list[JSONDict]:
    scores = info.get("scores")
    if not isinstance(scores, list) or not scores:
        raise WorldForgeError("Go2 ControlBench scoring requires a non-empty scores list.")
    records: list[JSONDict] = []
    for index, raw in enumerate(scores):
        record = _require_mapping(raw, f"scores[{index}]")
        _require_fields(
            record,
            ("candidate_index", "score_kind", "value", "lower_is_better"),
            f"scores[{index}]",
        )
        candidate_index = _index(record["candidate_index"], name=f"scores[{index}].candidate_index")
        if candidate_index != index:
            raise WorldForgeError(
                "Go2 ControlBench score candidate_index must match candidate order."
            )
        _number(record["value"], name=f"scores[{index}].value")
        if record["lower_is_better"] is not True:
            raise WorldForgeError("Go2 ControlBench scores must be lower_is_better.")
        records.append(dict(record))
    return records


def _candidate_payloads(action_candidates: object) -> list[JSONDict]:
    if not isinstance(action_candidates, list) or not action_candidates:
        raise WorldForgeError("Go2 ControlBench candidates must be a non-empty list.")
    candidates: list[JSONDict] = []
    for index, raw in enumerate(action_candidates):
        candidate = _validate_action(raw, name=f"candidate_actions[{index}]")
        candidates.append(candidate)
    return candidates


def _validate_action(value: object, *, name: str) -> JSONDict:
    action = _require_mapping(value, name)
    _require_fields(action, ("type", "params", "units"), name)
    if action["type"] != "unitree_go2_sport_move":
        raise WorldForgeError(f"Go2 ControlBench {name}.type must be unitree_go2_sport_move.")
    params = _require_mapping(action["params"], f"{name}.params")
    units = _require_mapping(action["units"], f"{name}.units")
    for field_name in ("x", "y", "z", "duration_s"):
        _number(params.get(field_name), name=f"{name}.params.{field_name}")
        if field_name not in units or not isinstance(units[field_name], str):
            raise WorldForgeError(f"Go2 ControlBench {name}.units.{field_name} must be a string.")
    return {
        "type": action["type"],
        "params": dict(params),
        "units": dict(units),
    }


def _command_name(action: JSONDict) -> str:
    params = _require_mapping(action["params"], "action.params")
    x = float(params["x"])
    z = float(params["z"])
    if x < 0:
        return f"backward_{abs(x):.2f}".rstrip("0").rstrip(".")
    if x > 0:
        return f"forward_{x:.2f}".rstrip("0").rstrip(".")
    if z < 0:
        return f"yaw_right_{abs(z):.2f}".rstrip("0").rstrip(".")
    if z > 0:
        return f"yaw_left_{z:.2f}".rstrip("0").rstrip(".")
    return "hold_noop"


def _require_mapping(value: object, field_name: str) -> JSONDict:
    if not isinstance(value, Mapping):
        raise WorldForgeError(f"Go2 ControlBench '{field_name}' must be a JSON object.")
    return dict(value)


def _require_fields(
    payload: Mapping[str, Any],
    field_names: Sequence[str],
    parent_name: str,
) -> None:
    for field_name in field_names:
        if field_name not in payload:
            raise WorldForgeError(f"Go2 ControlBench {parent_name} is missing '{field_name}'.")


def _index(value: object, *, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise WorldForgeError(f"Go2 ControlBench {name} must be an integer.")
    if value < 0:
        raise WorldForgeError(f"Go2 ControlBench {name} must be non-negative.")
    return value


def _number(value: object, *, name: str) -> float:
    return require_finite_number(value, name=f"Go2 ControlBench {name}")


def _print_summary(summary: JSONDict) -> None:
    print("WorldForge Go2 Air ControlBench DecisionTrace")
    print("=" * 48)
    print("Runtime: checkout-safe public trace fixture")
    print("Hardware: not used by this demo")
    print("Optional runtimes: DimOS/Unitree SDK/Hugging Face datasets not imported")
    print("Planning: forge.score_actions(public predicted-error scores) -> measured regret")
    print()
    print(f"Trace: {summary['trace']['trace_id']}")
    print(f"Target: {summary['target']:.6f} {summary['unit']}")
    print(f"Selected: {summary['selected']['name']}")
    print(f"Best measured: {summary['best_measured']['name']}")
    print(f"Measured regret: {summary['regret']:.6f} {summary['unit']}")
    print(f"WorldForge value: {summary['worldforge_value']}")
    print()
    print("JSON summary:")
    print(json.dumps(summary, indent=2, sort_keys=True))


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--trace",
        type=Path,
        default=DEFAULT_TRACE_PATH,
        help="DecisionTrace JSON fixture to replay.",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=Path(".worldforge/go2-controlbench-decisiontrace"),
        help="Directory for the copied trace and Markdown report.",
    )
    parser.add_argument(
        "--json-only",
        action="store_true",
        help="Print only the JSON summary.",
    )
    return parser


def main() -> int:
    args = _parser().parse_args()
    result = run_go2_controlbench_decisiontrace(args.trace, args.out)
    if args.json_only:
        print(json.dumps(result.summary, indent=2, sort_keys=True))
    else:
        _print_summary(result.summary)
        print(f"decision_trace={result.decision_trace_path}")
        print(f"report={result.report_path}")
    return 0


__all__ = [
    "DEFAULT_TRACE_PATH",
    "GO2_CONTROLBENCH_DATASET_REFERENCE",
    "GO2_CONTROLBENCH_SCORE_PROVIDER",
    "Go2ControlBenchDecisionTraceResult",
    "Go2ControlBenchTraceScoreProvider",
    "load_go2_controlbench_trace",
    "render_go2_controlbench_report",
    "run_demo",
    "run_go2_controlbench_decisiontrace",
]

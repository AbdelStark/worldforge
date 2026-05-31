"""SO-101 replay decision-trace demo.

This demo is checkout-safe: it does not install LeRobot, torch, DimOS, or robot
drivers, and it never talks to hardware. It uses a deterministic SO-101-shaped
pick-and-place replay fixture to show the product boundary WorldForge should own:
candidate actions are scored, a selected action is justified, rejected
alternatives are kept as counterfactuals, and the final trace can be compared
with a Go2 navigation trace.

The fixture is shaped after the public ``lerobot/svla_so101_pickplace`` dataset
metadata: 50 episodes, 11,939 frames, 6D joint state/action, and two RGB video
views. Hosts that own LeRobot or DimOS can replace the fixture with real replay
rows later without changing the trace contract.
"""

from __future__ import annotations

import argparse
import json
import math
import tempfile
from pathlib import Path
from typing import Any

from worldforge import Action, ActionScoreResult, BBox, Position, SceneObject, StructuredGoal
from worldforge.framework import WorldForge
from worldforge.models import (
    JSONDict,
    ProviderCapabilities,
    ProviderHealth,
    WorldForgeError,
    WorldStateError,
)
from worldforge.providers import BaseProvider, ProviderProfileSpec

SO101_TRACE_SCHEMA_VERSION = "worldforge.robot_decision_trace.v0"
SO101_SCORE_PROVIDER = "so101-replay-score"
SO101_CUBE_ID = "so101-blue-cube"
SO101_TARGET_POSITION = Position(0.52, 0.08, 0.03)
SO101_GOAL_TOLERANCE_M = 0.025

SO101_JOINT_NAMES: tuple[str, ...] = (
    "shoulder_pan.pos",
    "shoulder_lift.pos",
    "elbow_flex.pos",
    "wrist_flex.pos",
    "wrist_roll.pos",
    "gripper.pos",
)

SO101_DATASET_REFERENCE: JSONDict = {
    "repo_id": "lerobot/svla_so101_pickplace",
    "metadata_source": "Hugging Face dataset meta/info.json",
    "codebase_version": "v3.0",
    "robot_type": "so100_follower",
    "total_episodes": 50,
    "total_frames": 11939,
    "fps": 30,
    "action_shape": [6],
    "state_shape": [6],
    "video_views": ["observation.images.up", "observation.images.side"],
    "runtime_mode": "deterministic_fixture_no_download",
}


class SO101ReplayScoreProvider(BaseProvider):
    """Deterministic score provider for an SO-101 replay decision point."""

    def __init__(self) -> None:
        super().__init__(
            name=SO101_SCORE_PROVIDER,
            capabilities=ProviderCapabilities(score=True),
            profile=ProviderProfileSpec(
                is_local=True,
                description=(
                    "Checkout-safe SO-101 replay scorer for pick-and-place decision traces."
                ),
                implementation_status="test",
                deterministic=True,
                requires_credentials=False,
                supported_modalities=("robot_state", "world_state", "video_reference"),
                artifact_types=("decision_trace", "score_breakdown"),
            ),
        )

    def health(self) -> ProviderHealth:
        return ProviderHealth(name=self.name, healthy=True, latency_ms=0.1, details="configured")

    def score_actions(self, *, info: JSONDict, action_candidates: object) -> ActionScoreResult:
        target_pose = _require_pose(info.get("target_pose"), name="score info target_pose")
        if not isinstance(action_candidates, list) or not action_candidates:
            raise WorldForgeError("SO-101 replay scoring requires a non-empty candidate list.")

        components: list[JSONDict] = []
        scores: list[float] = []
        for index, candidate in enumerate(action_candidates):
            if not isinstance(candidate, dict):
                raise WorldForgeError("SO-101 replay candidates must be JSON objects.")
            scored = _score_candidate(candidate, target_pose=target_pose)
            components.append({"candidate_index": index, **scored})
            scores.append(float(scored["total_cost_raw"]))

        best_index = min(range(len(scores)), key=scores.__getitem__)
        ranked_indices = sorted(range(len(scores)), key=scores.__getitem__)
        return ActionScoreResult(
            provider=self.name,
            scores=scores,
            best_index=best_index,
            lower_is_better=True,
            metadata={
                "score_type": "weighted_pick_place_replay_cost",
                "components": components,
                "ranked_candidate_ids": [
                    str(action_candidates[index].get("candidate_id", index))
                    for index in ranked_indices
                ],
                "dataset_reference": dict(SO101_DATASET_REFERENCE),
                "claim_boundary": (
                    "Deterministic replay scorer; not a real policy-quality or "
                    "hardware-success claim."
                ),
            },
        )


def _require_pose(value: object, *, name: str) -> JSONDict:
    if not isinstance(value, dict):
        raise WorldForgeError(f"{name} must be a JSON object.")
    required = ("x", "y", "z")
    pose: JSONDict = {}
    for axis in required:
        raw = value.get(axis)
        if not isinstance(raw, int | float) or isinstance(raw, bool) or not math.isfinite(raw):
            raise WorldForgeError(f"{name}.{axis} must be a finite number.")
        pose[axis] = float(raw)
    return pose


def _score_candidate(candidate: JSONDict, *, target_pose: JSONDict) -> JSONDict:
    predicted_pose = _require_pose(
        candidate.get("predicted_object_pose"),
        name="candidate predicted_object_pose",
    )
    joint_delta = _require_number_list(
        candidate.get("joint_delta"),
        name="candidate joint_delta",
        expected_len=len(SO101_JOINT_NAMES),
    )
    grasp_confidence = _require_unit_float(
        candidate.get("predicted_grasp_confidence"),
        name="candidate predicted_grasp_confidence",
    )
    contact_risk = _require_unit_float(
        candidate.get("contact_risk"),
        name="candidate contact_risk",
    )
    occlusion_risk = _require_unit_float(
        candidate.get("occlusion_risk", 0.0),
        name="candidate occlusion_risk",
    )
    clearance_m = _require_non_negative_float(
        candidate.get("workspace_clearance_m"),
        name="candidate workspace_clearance_m",
    )

    placement_error_m = math.dist(
        [float(predicted_pose["x"]), float(predicted_pose["y"]), float(predicted_pose["z"])],
        [float(target_pose["x"]), float(target_pose["y"]), float(target_pose["z"])],
    )
    smoothness_cost = sum(abs(value) for value in joint_delta) / len(joint_delta)
    clearance_penalty = max(0.0, 0.035 - clearance_m) * 6.0
    grasp_penalty = 1.0 - grasp_confidence
    total_cost = (
        (6.0 * placement_error_m)
        + (0.8 * smoothness_cost)
        + (1.4 * grasp_penalty)
        + (1.8 * contact_risk)
        + (0.7 * occlusion_risk)
        + clearance_penalty
    )
    risk_flags = _risk_flags(
        placement_error_m=placement_error_m,
        contact_risk=contact_risk,
        occlusion_risk=occlusion_risk,
        clearance_m=clearance_m,
        grasp_confidence=grasp_confidence,
    )
    return {
        "candidate_id": str(candidate.get("candidate_id", "")),
        "label": str(candidate.get("label", "")),
        "placement_error_m": round(placement_error_m, 4),
        "smoothness_cost": round(smoothness_cost, 4),
        "grasp_penalty": round(grasp_penalty, 4),
        "contact_risk": round(contact_risk, 4),
        "occlusion_risk": round(occlusion_risk, 4),
        "clearance_penalty": round(clearance_penalty, 4),
        "total_cost_raw": total_cost,
        "total_cost_display": round(total_cost, 4),
        "risk_flags": risk_flags,
    }


def _require_number_list(value: object, *, name: str, expected_len: int) -> list[float]:
    if not isinstance(value, list) or len(value) != expected_len:
        raise WorldForgeError(f"{name} must be a list of {expected_len} finite numbers.")
    numbers: list[float] = []
    for index, raw in enumerate(value):
        if not isinstance(raw, int | float) or isinstance(raw, bool) or not math.isfinite(raw):
            raise WorldForgeError(f"{name}[{index}] must be a finite number.")
        numbers.append(float(raw))
    return numbers


def _require_unit_float(value: object, *, name: str) -> float:
    if not isinstance(value, int | float) or isinstance(value, bool) or not math.isfinite(value):
        raise WorldForgeError(f"{name} must be a finite number.")
    resolved = float(value)
    if resolved < 0.0 or resolved > 1.0:
        raise WorldForgeError(f"{name} must be between 0 and 1.")
    return resolved


def _require_non_negative_float(value: object, *, name: str) -> float:
    if not isinstance(value, int | float) or isinstance(value, bool) or not math.isfinite(value):
        raise WorldForgeError(f"{name} must be a finite number.")
    resolved = float(value)
    if resolved < 0.0:
        raise WorldForgeError(f"{name} must be non-negative.")
    return resolved


def _risk_flags(
    *,
    placement_error_m: float,
    contact_risk: float,
    occlusion_risk: float,
    clearance_m: float,
    grasp_confidence: float,
) -> list[str]:
    flags: list[str] = []
    if placement_error_m > SO101_GOAL_TOLERANCE_M:
        flags.append("misses_target_tolerance")
    if contact_risk >= 0.25:
        flags.append("contact_risk")
    if occlusion_risk >= 0.25:
        flags.append("camera_occlusion")
    if clearance_m < 0.035:
        flags.append("low_workspace_clearance")
    if grasp_confidence < 0.85:
        flags.append("weak_grasp")
    return flags


def _observation() -> JSONDict:
    return {
        "episode_index": 7,
        "frame_index": 182,
        "timestamp_s": round(182 / 30, 4),
        "state_names": list(SO101_JOINT_NAMES),
        "observation.state": [0.02, -0.72, 1.31, -0.66, 0.08, 0.62],
        "observation.images.up": "videos/observation.images.up/chunk-000/file-000.mp4#frame=182",
        "observation.images.side": (
            "videos/observation.images.side/chunk-000/file-000.mp4#frame=182"
        ),
        "object_pose": {"x": 0.34, "y": -0.09, "z": 0.03},
        "target_pose": SO101_TARGET_POSITION.to_dict(),
    }


def _candidate_records() -> list[JSONDict]:
    return [
        {
            "candidate_id": "direct-side-push",
            "label": "Direct side push",
            "joint_delta": [0.11, -0.04, 0.10, -0.07, 0.02, -0.18],
            "duration_s": 0.8,
            "predicted_object_pose": {"x": 0.48, "y": 0.06, "z": 0.03},
            "predicted_grasp_confidence": 0.78,
            "contact_risk": 0.28,
            "occlusion_risk": 0.18,
            "workspace_clearance_m": 0.042,
            "expected_outcome": "partial placement with side contact",
        },
        {
            "candidate_id": "lift-place-stable",
            "label": "Lift then place",
            "joint_delta": [0.08, -0.12, 0.14, -0.10, 0.04, -0.22],
            "duration_s": 1.1,
            "predicted_object_pose": {"x": 0.52, "y": 0.08, "z": 0.03},
            "predicted_grasp_confidence": 0.94,
            "contact_risk": 0.07,
            "occlusion_risk": 0.06,
            "workspace_clearance_m": 0.058,
            "expected_outcome": "placed inside target tolerance",
        },
        {
            "candidate_id": "overreach-place",
            "label": "Overreach place",
            "joint_delta": [0.21, -0.18, 0.27, -0.23, 0.16, -0.30],
            "duration_s": 0.9,
            "predicted_object_pose": {"x": 0.58, "y": 0.13, "z": 0.03},
            "predicted_grasp_confidence": 0.84,
            "contact_risk": 0.31,
            "occlusion_risk": 0.24,
            "workspace_clearance_m": 0.026,
            "expected_outcome": "overshoots target with low clearance",
        },
        {
            "candidate_id": "stop-relocalize",
            "label": "Stop and relocalize",
            "joint_delta": [0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
            "duration_s": 0.4,
            "predicted_object_pose": {"x": 0.34, "y": -0.09, "z": 0.03},
            "predicted_grasp_confidence": 0.99,
            "contact_risk": 0.02,
            "occlusion_risk": 0.01,
            "workspace_clearance_m": 0.075,
            "expected_outcome": "safe hold but no task progress",
        },
    ]


def _make_world_object() -> SceneObject:
    start = Position(0.34, -0.09, 0.03)
    return SceneObject(
        "so101_blue_cube",
        start,
        BBox(Position(0.315, -0.115, 0.005), Position(0.365, -0.065, 0.055)),
        id=SO101_CUBE_ID,
        is_graspable=True,
    )


def _goal(cube: SceneObject) -> StructuredGoal:
    return StructuredGoal.object_at(
        object_id=cube.id,
        object_name=cube.name,
        position=SO101_TARGET_POSITION,
        tolerance=SO101_GOAL_TOLERANCE_M,
    )


def _action_plans(candidates: list[JSONDict], *, cube_id: str) -> list[list[Action]]:
    plans: list[list[Action]] = []
    for candidate in candidates:
        pose = _require_pose(candidate["predicted_object_pose"], name="candidate predicted pose")
        plans.append(
            [
                Action(
                    "so101_joint_delta",
                    {
                        "candidate_id": str(candidate["candidate_id"]),
                        "joint_names": list(SO101_JOINT_NAMES),
                        "joint_delta": list(candidate["joint_delta"]),
                        "duration_s": float(candidate["duration_s"]),
                    },
                ),
                Action.move_to(
                    float(pose["x"]),
                    float(pose["y"]),
                    float(pose["z"]),
                    object_id=cube_id,
                ),
            ]
        )
    return plans


def run_demo(*, state_dir: Path | None = None, emit: bool = True) -> JSONDict:
    """Run the SO-101 replay trace demo and return a JSON-serializable summary."""

    if state_dir is None:
        with tempfile.TemporaryDirectory(prefix="worldforge-so101-demo-") as temporary_state_dir:
            return _run_demo(
                resolved_state_dir=Path(temporary_state_dir),
                explicit_state_dir=False,
                emit=emit,
            )
    return _run_demo(resolved_state_dir=state_dir, explicit_state_dir=True, emit=emit)


def _run_demo(
    *,
    resolved_state_dir: Path,
    explicit_state_dir: bool,
    emit: bool,
) -> JSONDict:
    forge = WorldForge(state_dir=resolved_state_dir, auto_register_remote=False)
    world = forge.create_world("so101-replay-trace-demo", provider="mock")
    cube = world.add_object(_make_world_object())
    goal = _goal(cube)
    observation = _observation()
    candidates = _candidate_records()
    action_plans = _action_plans(candidates, cube_id=cube.id)
    score_provider = SO101ReplayScoreProvider()
    forge.register_provider(score_provider)

    score_info: JSONDict = {
        "observation": observation,
        "target_pose": SO101_TARGET_POSITION.to_dict(),
        "goal_tolerance_m": SO101_GOAL_TOLERANCE_M,
    }
    plan = world.plan(
        goal_spec=goal,
        provider=SO101_SCORE_PROVIDER,
        candidate_actions=action_plans,
        score_info=score_info,
        score_action_candidates=candidates,
        execution_provider="mock",
        planner="so101-replay-cem",
    )
    execution = world.execute_plan(plan)
    final_world = execution.final_world()
    saved_world_id = forge.save_world(final_world)
    reloaded_world = forge.load_world(saved_world_id)
    final_cube = reloaded_world.get_object_by_id(cube.id)
    if final_cube is None:
        raise WorldStateError(
            "so101-replay-trace: cube 'so101-blue-cube' was missing after mock replay "
            "reload; first triage step: rerun with --state-dir <empty-dir> and inspect "
            "the persisted world JSON."
        )

    trace = _decision_trace(
        observation=observation,
        goal=goal,
        candidates=candidates,
        plan=plan,
        final_position=final_cube.position.to_dict(),
    )
    summary: JSONDict = {
        "demo_kind": "so101_replay_decision_trace",
        "runtime_mode": "deterministic_replay_fixture",
        "uses_real_robot_hardware": False,
        "uses_lerobot_runtime": False,
        "uses_dimos_runtime": False,
        "persistence": _persistence_summary(
            explicit_state_dir=explicit_state_dir,
            state_dir=resolved_state_dir,
            saved_world_id=saved_world_id,
            saved_worlds=forge.list_worlds(),
        ),
        "providers": forge.providers(),
        "score_provider_health": forge.provider_health(SO101_SCORE_PROVIDER).to_dict(),
        "dataset_reference": dict(SO101_DATASET_REFERENCE),
        "trace": trace,
        "plan": plan.to_dict(),
        "candidate_costs": list(plan.metadata["score_result"]["scores"]),
        "selected_candidate_index": plan.metadata["score_result"]["best_index"],
        "selected_candidate_id": trace["selected_action"]["candidate_id"],
        "counterfactual_count": len(trace["counterfactuals"]),
        "outcome": trace["outcome"],
        "final_object_position": final_cube.position.to_dict(),
    }
    if emit:
        _print_summary(summary)
    return summary


def _persistence_summary(
    *,
    explicit_state_dir: bool,
    state_dir: Path,
    saved_world_id: str,
    saved_worlds: list[str],
) -> JSONDict:
    if explicit_state_dir:
        return {
            "state_dir_provided": True,
            "state_dir": str(state_dir),
            "saved_world_id": saved_world_id,
            "saved_worlds": list(saved_worlds),
        }
    return {
        "state_dir_provided": False,
        "state_dir": "<temporary>",
        "saved_world_id": "<temporary-world-id>",
        "saved_worlds": ["<temporary-world-id>"],
    }


def _decision_trace(
    *,
    observation: JSONDict,
    goal: StructuredGoal,
    candidates: list[JSONDict],
    plan: Any,
    final_position: JSONDict,
) -> JSONDict:
    score_result = plan.metadata["score_result"]
    scores = list(score_result["scores"])
    components = list(score_result["metadata"]["components"])
    selected_index = int(score_result["best_index"])
    selected = candidates[selected_index]
    selected_score = float(scores[selected_index])
    ranked_indices = sorted(range(len(scores)), key=scores.__getitem__)
    runner_up_score = (
        float(scores[ranked_indices[1]]) if len(ranked_indices) > 1 else selected_score
    )
    outcome = _outcome(final_position, selected=selected)
    return {
        "schema_version": SO101_TRACE_SCHEMA_VERSION,
        "embodiment": "so101_manipulation",
        "source": "checkout_safe_replay_fixture",
        "dataset_reference": dict(SO101_DATASET_REFERENCE),
        "observation": observation,
        "goal": goal.to_dict(),
        "candidate_actions": [_candidate_trace_record(candidate) for candidate in candidates],
        "candidate_scores": [
            {
                "candidate_id": str(candidates[index]["candidate_id"]),
                "score": float(scores[index]),
                "rank": ranked_indices.index(index) + 1,
                "lower_is_better": True,
                "components": components[index],
            }
            for index in range(len(candidates))
        ],
        "selected_action": {
            "candidate_id": str(selected["candidate_id"]),
            "label": str(selected["label"]),
            "score": selected_score,
            "score_margin_to_runner_up": round(runner_up_score - selected_score, 4),
            "action_plan": [action.to_dict() for action in plan.actions],
            "why_selected": _selection_reason(components[selected_index]),
        },
        "outcome": outcome,
        "counterfactuals": _counterfactuals(
            candidates=candidates,
            scores=scores,
            components=components,
            selected_index=selected_index,
            selected_score=selected_score,
        ),
        "claim_boundary": (
            "Replay evidence only: no real SO-101 controller, calibration, camera, "
            "or physical success claim."
        ),
    }


def _candidate_trace_record(candidate: JSONDict) -> JSONDict:
    return {
        "candidate_id": str(candidate["candidate_id"]),
        "label": str(candidate["label"]),
        "joint_names": list(SO101_JOINT_NAMES),
        "joint_delta": list(candidate["joint_delta"]),
        "duration_s": float(candidate["duration_s"]),
        "predicted_object_pose": dict(candidate["predicted_object_pose"]),
        "expected_outcome": str(candidate["expected_outcome"]),
    }


def _selection_reason(component: JSONDict) -> str:
    return (
        "Lowest weighted replay cost: target placement inside tolerance with "
        "high grasp confidence and low contact risk."
        if not component["risk_flags"]
        else "Lowest weighted replay cost after balancing target error and safety penalties."
    )


def _outcome(final_position: JSONDict, *, selected: JSONDict) -> JSONDict:
    target_pose = SO101_TARGET_POSITION.to_dict()
    placement_error_m = math.dist(
        [float(final_position["x"]), float(final_position["y"]), float(final_position["z"])],
        [float(target_pose["x"]), float(target_pose["y"]), float(target_pose["z"])],
    )
    contact_risk = float(selected["contact_risk"])
    grasp_confidence = float(selected["predicted_grasp_confidence"])
    success = (
        placement_error_m <= SO101_GOAL_TOLERANCE_M
        and contact_risk < 0.2
        and grasp_confidence >= 0.85
    )
    return {
        "outcome_source": "mock_replay_execution",
        "hardware_executed": False,
        "final_object_pose": final_position,
        "target_pose": target_pose,
        "placement_error_m": round(placement_error_m, 4),
        "success": success,
        "success_label": "placed_at_target" if success else "not_within_target_tolerance",
    }


def _counterfactuals(
    *,
    candidates: list[JSONDict],
    scores: list[float],
    components: list[JSONDict],
    selected_index: int,
    selected_score: float,
) -> list[JSONDict]:
    records: list[JSONDict] = []
    for index, candidate in enumerate(candidates):
        if index == selected_index:
            continue
        component = components[index]
        records.append(
            {
                "candidate_id": str(candidate["candidate_id"]),
                "label": str(candidate["label"]),
                "score": float(scores[index]),
                "score_delta_vs_selected": round(float(scores[index]) - selected_score, 4),
                "predicted_object_pose": dict(candidate["predicted_object_pose"]),
                "expected_outcome": str(candidate["expected_outcome"]),
                "why_rejected": _rejection_reason(component),
                "risk_flags": list(component["risk_flags"]),
            }
        )
    return records


def _rejection_reason(component: JSONDict) -> str:
    flags = list(component["risk_flags"])
    if "misses_target_tolerance" in flags and len(flags) == 1:
        return "Predicted placement stays outside the target tolerance."
    if "contact_risk" in flags or "low_workspace_clearance" in flags:
        return "Higher expected risk around contact or workspace clearance."
    if "weak_grasp" in flags:
        return "Lower grasp confidence than the selected candidate."
    return "Higher weighted replay cost than the selected candidate."


def _print_summary(summary: JSONDict) -> None:
    trace = summary["trace"]
    print("WorldForge SO-101 replay decision trace")
    print("=" * 42)
    print("Runtime: deterministic replay fixture")
    print("Hardware: not used")
    print("Optional runtimes: LeRobot/torch/DimOS not imported")
    print(f"State directory: {summary['persistence']['state_dir']}")
    print(f"Registered providers: {', '.join(summary['providers'])}")
    print()
    print("Candidate costs, lower is better:")
    for score in trace["candidate_scores"]:
        marker = " <- selected" if score["candidate_id"] == summary["selected_candidate_id"] else ""
        print(f"  {score['candidate_id']}: {score['score']:.4f}{marker}")
    print()
    selected = trace["selected_action"]
    print(f"Selected: {selected['candidate_id']} ({selected['label']})")
    print(f"Why: {selected['why_selected']}")
    outcome = trace["outcome"]
    print(
        "Outcome: "
        f"{outcome['success_label']} error={outcome['placement_error_m']:.4f}m "
        f"hardware_executed={outcome['hardware_executed']}"
    )
    print(f"Counterfactuals: {summary['counterfactual_count']}")
    print()
    print("JSON summary:")
    print(json.dumps(summary, indent=2, sort_keys=True))


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--state-dir",
        type=Path,
        default=None,
        help="Directory for persisted demo worlds. Defaults to a temporary directory.",
    )
    parser.add_argument(
        "--json-only",
        action="store_true",
        help="Print only the final JSON summary.",
    )
    return parser


def main() -> int:
    args = _parser().parse_args()
    summary = run_demo(state_dir=args.state_dir, emit=not args.json_only)
    if args.json_only:
        print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

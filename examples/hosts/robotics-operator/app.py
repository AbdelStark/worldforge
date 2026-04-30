"""Stdlib robotics operator-review host for offline policy+score runs."""

from __future__ import annotations

import argparse
import json
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

from worldforge import Action, WorldForge, WorldForgeError
from worldforge.demos import BLUE_CUBE_GOAL, blue_cube_goal, make_blue_cube, make_candidate_plans
from worldforge.demos.lerobot_e2e import (
    DemoDistanceScoreProvider,
    DemoLeRobotPolicy,
)
from worldforge.harness.workspace import create_run_workspace, write_run_manifest
from worldforge.models import JSONDict, ProviderEvent, require_json_dict
from worldforge.observability import RunJsonLogSink, compose_event_handlers
from worldforge.providers import LeRobotPolicyProvider

JSON = dict[str, Any]
ActionTranslator = Callable[
    [object, JSONDict, JSONDict],
    Sequence[Action] | Sequence[Sequence[Action]],
]
ControllerExecutionHook = Callable[[Sequence[Action], JSONDict], JSONDict]
DEFAULT_WORKSPACE = Path(".worldforge/robotics-operator")
DEFAULT_STATE_DIR = Path(".worldforge/robotics-operator/worlds")
REQUIRED_CHECKS = (
    "workspace_clear",
    "emergency_stop_available",
    "operator_present",
    "controller_isolated",
)


def sample_pusht_translator(
    _raw_actions: object,
    info: JSONDict,
    _provider_info: JSONDict,
) -> list[list[Action]]:
    """Translate sample PushT policy outputs into WorldForge action chunks."""

    cube_id = str(info.get("object_id") or "").strip()
    if not cube_id:
        raise WorldForgeError("sample translator requires policy info.object_id.")
    return make_candidate_plans(cube_id)


def sample_policy_info(*, cube_id: str) -> JSONDict:
    """Return deterministic PushT-shaped sample policy inputs for checkout review."""

    return {
        "observation": {
            "observation.state": [[0.0, 0.5, 0.0]],
            "observation.images.top": [[[[0, 0, 0]]]],
            "task": "move the blue cube near the marked target",
        },
        "embodiment_tag": "pusht",
        "action_horizon": 2,
        "object_id": cube_id,
    }


def sample_candidate_tensors() -> list[list[list[float]]]:
    """Return sample raw policy tensors that the explicit translator maps to action chunks."""

    return [
        [[0.20, 0.50, 0.00], [0.35, 0.50, 0.00]],
        [[0.30, 0.50, 0.00], [0.55, 0.50, 0.00]],
        [[0.70, 0.50, 0.00], [0.95, 0.50, 0.00]],
    ]


def run_operator_review(
    *,
    workspace_dir: Path,
    state_dir: Path,
    action_translator: ActionTranslator | None,
    safety_checklist: JSONDict,
    dry_run_approved: bool,
    controller_hook: ControllerExecutionHook | None = None,
    execute_controller: bool = False,
) -> JSON:
    """Run an offline operator review and preserve issue-safe artifacts."""

    if action_translator is None:
        raise WorldForgeError("robotics operator host requires an explicit action translator.")
    checklist = validate_safety_checklist(safety_checklist)
    dry_run_approved = _require_bool(dry_run_approved, name="dry_run_approved")
    if execute_controller and controller_hook is None:
        raise WorldForgeError(
            "controller execution is disabled until the host supplies controller_hook."
        )
    if execute_controller and not dry_run_approved:
        raise WorldForgeError("controller execution requires recorded dry-run approval.")
    if execute_controller and not all(checklist.values()):
        raise WorldForgeError("controller execution requires every safety checklist item.")

    command = _command_string(
        [
            "--workspace",
            str(workspace_dir),
            "--state-dir",
            str(state_dir),
            "review",
        ]
    )
    workspace = create_run_workspace(
        workspace_dir,
        kind="robotics_operator_review",
        command=command,
        provider="lerobot",
        operation="policy+score",
        input_summary={
            "mode": "offline_operator_review",
            "controller_execution_requested": execute_controller,
            "dry_run_approved": dry_run_approved,
            "required_check_count": len(REQUIRED_CHECKS),
        },
    )

    events: list[ProviderEvent] = []
    event_sink = compose_event_handlers(
        events.append,
        RunJsonLogSink(
            workspace.logs_dir / "provider-events.jsonl",
            workspace.run_id,
            extra_fields={"host": "robotics-operator"},
        ),
    )

    try:
        forge = WorldForge(
            state_dir=state_dir,
            auto_register_remote=False,
            event_handler=event_sink,
        )
        world = forge.create_world("robotics-operator-review", provider="mock")
        cube = make_blue_cube(world)
        goal = blue_cube_goal(cube)

        policy_info = sample_policy_info(cube_id=cube.id)
        score_info: JSONDict = {
            "goal": [BLUE_CUBE_GOAL.x, BLUE_CUBE_GOAL.y, BLUE_CUBE_GOAL.z],
            "review_mode": "operator_dry_run",
        }
        policy = DemoLeRobotPolicy(sample_candidate_tensors())

        def loader(
            _policy_path: str,
            _policy_type: str | None,
            _device: str | None,
            _cache_dir: str | None,
        ) -> DemoLeRobotPolicy:
            return policy

        forge.register_provider(
            LeRobotPolicyProvider(
                policy_path="host/sample-pusht-policy",
                policy_type="diffusion",
                embodiment_tag="pusht",
                device="cpu",
                policy_loader=loader,
                action_translator=action_translator,
                event_handler=event_sink,
            )
        )
        forge.register_provider(DemoDistanceScoreProvider())

        policy_result = forge.select_actions("lerobot", info=policy_info)
        score_result = forge.score_actions(
            "demo-distance-score",
            info=score_info,
            action_candidates=[
                [action.to_dict() for action in candidate]
                for candidate in policy_result.action_candidates
            ],
        )
        selected_actions = list(policy_result.action_candidates[score_result.best_index])
        action_chunks = [
            {
                "index": index,
                "selected": index == score_result.best_index,
                "actions": [action.to_dict() for action in candidate],
                "score": score_result.scores[index],
            }
            for index, candidate in enumerate(policy_result.action_candidates)
        ]
        approval = {
            "dry_run_approved": dry_run_approved,
            "safety_checklist": checklist,
            "controller_execution_requested": execute_controller,
            "controller_hook_supplied": controller_hook is not None,
            "worldforge_certifies_robot_safety": False,
        }
        replay = _replay_payload(
            selected_actions,
            goal=goal.to_dict(),
            selected_candidate_index=score_result.best_index,
            dry_run_approved=dry_run_approved,
        )
        controller_result = None
        if execute_controller and controller_hook is not None:
            controller_result = require_json_dict(
                controller_hook(selected_actions, approval),
                name="controller hook result",
            )

        artifacts: JSON = {
            "action_chunks": action_chunks,
            "approval": approval,
            "controller_result": controller_result,
            "events": [event.to_dict() for event in events],
            "policy": policy_result.to_dict(),
            "replay": replay,
            "score_rationale": {
                "provider": score_result.provider,
                "score_type": score_result.metadata.get("score_type"),
                "scores": score_result.scores,
                "lower_is_better": score_result.lower_is_better,
                "best_index": score_result.best_index,
                "best_score": score_result.best_score,
                "metadata": score_result.metadata,
            },
        }
        workspace.write_json("results/action_chunks.json", artifacts["action_chunks"])
        workspace.write_json("results/approval.json", artifacts["approval"])
        workspace.write_json("results/score_rationale.json", artifacts["score_rationale"])
        workspace.write_json("results/replay.json", artifacts["replay"])
        workspace.write_json("results/operator_review.json", artifacts)
        workspace.write_text("reports/operator_review.md", _review_markdown(artifacts))

        artifact_paths = {
            "action_chunks": "results/action_chunks.json",
            "approval": "results/approval.json",
            "operator_review": "results/operator_review.json",
            "provider_events": "logs/provider-events.jsonl",
            "replay": "results/replay.json",
            "report": "reports/operator_review.md",
            "score_rationale": "results/score_rationale.json",
        }
        result_summary = {
            "selected_candidate_index": score_result.best_index,
            "selected_action_count": len(selected_actions),
            "best_score": score_result.best_score,
            "dry_run_approved": dry_run_approved,
            "controller_execution_requested": execute_controller,
            "controller_executed": controller_result is not None,
        }
        write_run_manifest(
            workspace,
            kind="robotics_operator_review",
            command=command,
            provider="lerobot",
            operation="policy+score",
            status="completed",
            input_summary={
                "mode": "offline_operator_review",
                "controller_execution_requested": execute_controller,
                "dry_run_approved": dry_run_approved,
                "required_check_count": len(REQUIRED_CHECKS),
            },
            result_summary=result_summary,
            artifact_paths=artifact_paths,
            event_count=len(events),
        )
        return {
            "status": "passed",
            "exit_code": 0,
            "run_id": workspace.run_id,
            "run_workspace": str(workspace.path),
            "run_manifest": str(workspace.manifest_path),
            "artifact_paths": artifact_paths,
            "summary": result_summary,
        }
    except Exception:
        write_run_manifest(
            workspace,
            kind="robotics_operator_review",
            command=command,
            provider="lerobot",
            operation="policy+score",
            status="failed",
            input_summary={
                "mode": "offline_operator_review",
                "controller_execution_requested": execute_controller,
                "dry_run_approved": dry_run_approved,
                "required_check_count": len(REQUIRED_CHECKS),
            },
            result_summary={"error": "operator review failed"},
            artifact_paths={"provider_events": "logs/provider-events.jsonl"},
            event_count=len(events),
        )
        raise


def validate_safety_checklist(payload: JSONDict) -> dict[str, bool]:
    """Return the required host-owned safety checklist with boolean values."""

    checklist = require_json_dict(payload, name="safety checklist")
    missing = [key for key in REQUIRED_CHECKS if key not in checklist]
    if missing:
        raise WorldForgeError(f"safety checklist is missing required items: {', '.join(missing)}.")
    normalized: dict[str, bool] = {}
    for key in REQUIRED_CHECKS:
        normalized[key] = _require_bool(checklist[key], name=f"safety checklist {key}")
    return normalized


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, default=DEFAULT_WORKSPACE)
    parser.add_argument("--state-dir", type=Path, default=DEFAULT_STATE_DIR)
    subparsers = parser.add_subparsers(dest="command", required=True)
    review = subparsers.add_parser("review", help="Run an offline robotics operator review.")
    review.add_argument(
        "--sample-translator",
        action="store_true",
        help="Use the checkout sample PushT translator for the dry-run review.",
    )
    review.add_argument(
        "--approve-dry-run",
        action="store_true",
        help="Record operator approval for the dry-run artifact.",
    )
    review.add_argument(
        "--check",
        action="append",
        choices=REQUIRED_CHECKS,
        default=[],
        help="Mark one required host-owned safety checklist item true. Can be repeated.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    checklist = {key: key in args.check for key in REQUIRED_CHECKS}
    translator = sample_pusht_translator if args.sample_translator else None
    try:
        result = run_operator_review(
            workspace_dir=args.workspace,
            state_dir=args.state_dir,
            action_translator=translator,
            safety_checklist=checklist,
            dry_run_approved=args.approve_dry_run,
        )
    except WorldForgeError as exc:
        print(json.dumps({"error": {"type": "validation_error", "message": str(exc)}}))
        return 2
    print(json.dumps(result, indent=2, sort_keys=True))
    return int(result["exit_code"])


def _replay_payload(
    actions: Sequence[Action],
    *,
    goal: JSONDict,
    selected_candidate_index: int,
    dry_run_approved: bool,
) -> JSON:
    return {
        "mode": "dry_run_replay",
        "selected_candidate_index": selected_candidate_index,
        "dry_run_approved": dry_run_approved,
        "controller_calls": 0,
        "steps": [
            {
                "step": index,
                "action": action.to_dict(),
                "operator_prompt": "review_only",
            }
            for index, action in enumerate(actions, start=1)
        ],
        "goal": goal,
    }


def _review_markdown(artifacts: JSON) -> str:
    score = artifacts["score_rationale"]
    approval = artifacts["approval"]
    lines = [
        "# Robotics Operator Review",
        "",
        f"- selected_candidate_index: {score['best_index']}",
        f"- best_score: {score['best_score']}",
        f"- dry_run_approved: {approval['dry_run_approved']}",
        f"- controller_execution_requested: {approval['controller_execution_requested']}",
        f"- controller_hook_supplied: {approval['controller_hook_supplied']}",
        "",
        "WorldForge produced offline policy, score, replay, and event artifacts. The host owns "
        "robot controller integration and safety certification.",
    ]
    return "\n".join(lines)


def _command_string(args: list[str]) -> str:
    return "python examples/hosts/robotics-operator/app.py " + " ".join(args)


def _require_bool(value: object, *, name: str) -> bool:
    if not isinstance(value, bool):
        raise WorldForgeError(f"{name} must be a boolean.")
    return value


if __name__ == "__main__":
    raise SystemExit(main())

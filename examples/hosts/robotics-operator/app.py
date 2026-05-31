"""Stdlib robotics operator-review host for offline policy+score runs."""

from __future__ import annotations

import argparse
import json
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from worldforge import Action, WorldForge, WorldForgeError
from worldforge.demos import BLUE_CUBE_GOAL, blue_cube_goal, make_blue_cube, make_candidate_plans
from worldforge.demos.lerobot_e2e import (
    DemoDistanceScoreProvider,
    DemoLeRobotPolicy,
)
from worldforge.harness.workspace import RunWorkspace, create_run_workspace, write_run_manifest
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


@dataclass(frozen=True, slots=True)
class _ReviewRunConfig:
    workspace_dir: Path
    state_dir: Path
    action_translator: ActionTranslator
    safety_checklist: dict[str, bool]
    dry_run_approved: bool
    controller_hook: ControllerExecutionHook | None
    execute_controller: bool


@dataclass(frozen=True, slots=True)
class _ReviewProviders:
    forge: WorldForge


@dataclass(frozen=True, slots=True)
class _ReviewExecution:
    artifacts: JSON
    result_summary: JSON


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

    config = _review_run_config(
        workspace_dir=workspace_dir,
        state_dir=state_dir,
        action_translator=action_translator,
        safety_checklist=safety_checklist,
        dry_run_approved=dry_run_approved,
        controller_hook=controller_hook,
        execute_controller=execute_controller,
    )
    command = _review_command(config)
    workspace = create_run_workspace(
        config.workspace_dir,
        kind="robotics_operator_review",
        command=command,
        provider="lerobot",
        operation="policy+score",
        input_summary=_review_input_summary(config),
    )
    events: list[ProviderEvent] = []

    try:
        review = _run_review_pipeline(config, workspace, events)
        _write_review_artifacts(workspace, review.artifacts)
        _write_review_manifest(
            workspace,
            config=config,
            command=command,
            status="completed",
            result_summary=review.result_summary,
            artifact_paths=_review_artifact_paths(),
            event_count=len(events),
        )
        return _review_result(workspace, review.result_summary)
    except Exception:
        _write_review_manifest(
            workspace,
            config=config,
            command=command,
            status="failed",
            result_summary={"error": "operator review failed"},
            artifact_paths={"provider_events": "logs/provider-events.jsonl"},
            event_count=len(events),
        )
        raise


def _review_run_config(
    *,
    workspace_dir: Path,
    state_dir: Path,
    action_translator: ActionTranslator | None,
    safety_checklist: JSONDict,
    dry_run_approved: bool,
    controller_hook: ControllerExecutionHook | None,
    execute_controller: bool,
) -> _ReviewRunConfig:
    if action_translator is None:
        raise WorldForgeError("robotics operator host requires an explicit action translator.")
    checklist = validate_safety_checklist(safety_checklist)
    approved = _require_bool(dry_run_approved, name="dry_run_approved")
    _validate_controller_request(
        checklist=checklist,
        dry_run_approved=approved,
        controller_hook=controller_hook,
        execute_controller=execute_controller,
    )
    return _ReviewRunConfig(
        workspace_dir=workspace_dir,
        state_dir=state_dir,
        action_translator=action_translator,
        safety_checklist=checklist,
        dry_run_approved=approved,
        controller_hook=controller_hook,
        execute_controller=execute_controller,
    )


def _validate_controller_request(
    *,
    checklist: dict[str, bool],
    dry_run_approved: bool,
    controller_hook: ControllerExecutionHook | None,
    execute_controller: bool,
) -> None:
    if not execute_controller:
        return
    if controller_hook is None:
        raise WorldForgeError(
            "controller execution is disabled until the host supplies controller_hook."
        )
    if not dry_run_approved:
        raise WorldForgeError("controller execution requires recorded dry-run approval.")
    if not all(checklist.values()):
        raise WorldForgeError("controller execution requires every safety checklist item.")


def _review_command(config: _ReviewRunConfig) -> str:
    return _command_string(
        [
            "--workspace",
            str(config.workspace_dir),
            "--state-dir",
            str(config.state_dir),
            "review",
        ]
    )


def _review_input_summary(config: _ReviewRunConfig) -> JSON:
    return {
        "mode": "offline_operator_review",
        "controller_execution_requested": config.execute_controller,
        "dry_run_approved": config.dry_run_approved,
        "required_check_count": len(REQUIRED_CHECKS),
    }


def _review_event_sink(
    workspace_run_id: str,
    events: list[ProviderEvent],
    logs_dir: Path,
) -> Callable[[ProviderEvent], None]:
    return compose_event_handlers(
        events.append,
        RunJsonLogSink(
            logs_dir / "provider-events.jsonl",
            workspace_run_id,
            extra_fields={"host": "robotics-operator"},
        ),
    )


def _run_review_pipeline(
    config: _ReviewRunConfig,
    workspace: RunWorkspace,
    events: list[ProviderEvent],
) -> _ReviewExecution:
    event_sink = _review_event_sink(workspace.run_id, events, workspace.logs_dir)
    providers = _review_providers(config, event_sink)
    cube = make_blue_cube(providers.forge.create_world("robotics-operator-review", provider="mock"))
    goal = blue_cube_goal(cube)
    policy_result = providers.forge.select_actions(
        "lerobot",
        info=sample_policy_info(cube_id=cube.id),
    )
    score_result = _score_review_candidates(providers.forge, policy_result.action_candidates)
    selected_actions = list(policy_result.action_candidates[score_result.best_index])
    approval = _approval_payload(config)
    controller_result = _controller_result(config, selected_actions, approval)
    artifacts = _review_artifacts(
        policy_result=policy_result,
        score_result=score_result,
        selected_actions=selected_actions,
        goal=goal.to_dict(),
        approval=approval,
        controller_result=controller_result,
        events=events,
    )
    return _ReviewExecution(
        artifacts=artifacts,
        result_summary=_review_result_summary(
            score_result=score_result,
            selected_actions=selected_actions,
            config=config,
            controller_result=controller_result,
        ),
    )


def _review_providers(
    config: _ReviewRunConfig,
    event_sink: Callable[[ProviderEvent], None],
) -> _ReviewProviders:
    forge = WorldForge(
        state_dir=config.state_dir,
        auto_register_remote=False,
        event_handler=event_sink,
    )
    policy = DemoLeRobotPolicy(sample_candidate_tensors())
    forge.register_provider(
        LeRobotPolicyProvider(
            policy_path="host/sample-pusht-policy",
            policy_type="diffusion",
            embodiment_tag="pusht",
            device="cpu",
            policy_loader=_sample_policy_loader(policy),
            action_translator=config.action_translator,
            event_handler=event_sink,
        )
    )
    forge.register_provider(DemoDistanceScoreProvider())
    return _ReviewProviders(forge=forge)


def _sample_policy_loader(
    policy: DemoLeRobotPolicy,
) -> Callable[[str, str | None, str | None, str | None], DemoLeRobotPolicy]:
    def loader(
        _policy_path: str,
        _policy_type: str | None,
        _device: str | None,
        _cache_dir: str | None,
    ) -> DemoLeRobotPolicy:
        return policy

    return loader


def _score_review_candidates(
    forge: WorldForge,
    action_candidates: Sequence[Sequence[Action]],
) -> Any:
    score_info: JSONDict = {
        "goal": [BLUE_CUBE_GOAL.x, BLUE_CUBE_GOAL.y, BLUE_CUBE_GOAL.z],
        "review_mode": "operator_dry_run",
    }
    return forge.score_actions(
        "demo-distance-score",
        info=score_info,
        action_candidates=[
            [action.to_dict() for action in candidate] for candidate in action_candidates
        ],
    )


def _approval_payload(config: _ReviewRunConfig) -> JSON:
    return {
        "dry_run_approved": config.dry_run_approved,
        "safety_checklist": config.safety_checklist,
        "controller_execution_requested": config.execute_controller,
        "controller_hook_supplied": config.controller_hook is not None,
        "worldforge_certifies_robot_safety": False,
    }


def _controller_result(
    config: _ReviewRunConfig,
    selected_actions: Sequence[Action],
    approval: JSONDict,
) -> JSONDict | None:
    if not config.execute_controller or config.controller_hook is None:
        return None
    return require_json_dict(
        config.controller_hook(selected_actions, approval),
        name="controller hook result",
    )


def _review_artifacts(
    *,
    policy_result: Any,
    score_result: Any,
    selected_actions: Sequence[Action],
    goal: JSONDict,
    approval: JSONDict,
    controller_result: JSONDict | None,
    events: Sequence[ProviderEvent],
) -> JSON:
    return {
        "action_chunks": _action_chunk_artifacts(policy_result, score_result),
        "approval": approval,
        "controller_result": controller_result,
        "events": [event.to_dict() for event in events],
        "policy": policy_result.to_dict(),
        "replay": _replay_payload(
            selected_actions,
            goal=goal,
            selected_candidate_index=score_result.best_index,
            dry_run_approved=bool(approval["dry_run_approved"]),
        ),
        "score_rationale": _score_rationale(score_result),
    }


def _action_chunk_artifacts(policy_result: Any, score_result: Any) -> list[JSON]:
    return [
        {
            "index": index,
            "selected": index == score_result.best_index,
            "actions": [action.to_dict() for action in candidate],
            "score": score_result.scores[index],
        }
        for index, candidate in enumerate(policy_result.action_candidates)
    ]


def _score_rationale(score_result: Any) -> JSON:
    return {
        "provider": score_result.provider,
        "score_type": score_result.metadata.get("score_type"),
        "scores": score_result.scores,
        "lower_is_better": score_result.lower_is_better,
        "best_index": score_result.best_index,
        "best_score": score_result.best_score,
        "metadata": score_result.metadata,
    }


def _review_result_summary(
    *,
    score_result: Any,
    selected_actions: Sequence[Action],
    config: _ReviewRunConfig,
    controller_result: JSONDict | None,
) -> JSON:
    return {
        "selected_candidate_index": score_result.best_index,
        "selected_action_count": len(selected_actions),
        "best_score": score_result.best_score,
        "dry_run_approved": config.dry_run_approved,
        "controller_execution_requested": config.execute_controller,
        "controller_executed": controller_result is not None,
    }


def _write_review_artifacts(workspace: RunWorkspace, artifacts: JSON) -> None:
    workspace.write_json("results/action_chunks.json", artifacts["action_chunks"])
    workspace.write_json("results/approval.json", artifacts["approval"])
    workspace.write_json("results/score_rationale.json", artifacts["score_rationale"])
    workspace.write_json("results/replay.json", artifacts["replay"])
    workspace.write_json("results/operator_review.json", artifacts)
    workspace.write_text("reports/operator_review.md", _review_markdown(artifacts))


def _review_artifact_paths() -> dict[str, str]:
    return {
        "action_chunks": "results/action_chunks.json",
        "approval": "results/approval.json",
        "operator_review": "results/operator_review.json",
        "provider_events": "logs/provider-events.jsonl",
        "replay": "results/replay.json",
        "report": "reports/operator_review.md",
        "score_rationale": "results/score_rationale.json",
    }


def _write_review_manifest(
    workspace: RunWorkspace,
    *,
    config: _ReviewRunConfig,
    command: str,
    status: str,
    result_summary: JSON,
    artifact_paths: dict[str, str],
    event_count: int,
) -> None:
    write_run_manifest(
        workspace,
        kind="robotics_operator_review",
        command=command,
        provider="lerobot",
        operation="policy+score",
        status=status,
        input_summary=_review_input_summary(config),
        result_summary=result_summary,
        artifact_paths=artifact_paths,
        event_count=event_count,
    )


def _review_result(workspace: RunWorkspace, result_summary: JSON) -> JSON:
    artifact_paths = _review_artifact_paths()
    return {
        "status": "passed",
        "exit_code": 0,
        "run_id": workspace.run_id,
        "run_workspace": str(workspace.path),
        "run_manifest": str(workspace.manifest_path),
        "artifact_paths": artifact_paths,
        "summary": result_summary,
    }


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

"""LeRobot provider policy-plus-score planning demo.

The demo injects a deterministic policy into :class:`LeRobotPolicyProvider`. It
validates the provider, policy selection, score ranking, execution, persistence,
and reload path without requiring LeRobot, torch, or checkpoint weights.

What the demo does:

1. Registers :class:`LeRobotPolicyProvider` alongside the local ``mock``
   execution provider and a deterministic score provider.
2. Creates a small world with one ``blue_cube`` and an ``object_at`` goal.
3. Asks the LeRobot provider to propose three candidate two-step action chunks
   via ``select_actions(...)``.
4. Ranks those candidates by distance-to-goal through the score provider's
   ``score_actions(...)`` surface, selecting the best one via
   ``World.plan(..., planning_mode="policy+score")``.
5. Executes the selected WorldForge actions through ``execution_provider="mock"``,
   saves the final world, reloads it from disk, and reports the final cube
   position.

Use this demo to validate the WorldForge adapter and planner path. Use
``scripts/smoke_lerobot_policy.py`` for host-owned real-checkpoint inference.
"""

from __future__ import annotations

import argparse
import json
import math
import tempfile
from pathlib import Path
from typing import Any

from worldforge import (
    Action,
    ActionScoreResult,
    WorldForge,
)
from worldforge.models import (
    JSONDict,
    ProviderCapabilities,
    ProviderEvent,
    ProviderHealth,
)
from worldforge.providers import BaseProvider, LeRobotPolicyProvider, ProviderProfileSpec

from . import BLUE_CUBE_GOAL, blue_cube_goal, make_blue_cube, make_candidate_plans


class DemoTensor:
    """Minimal tensor-like object accepted by :class:`LeRobotPolicyProvider`."""

    def __init__(self, value: object) -> None:
        self.value = value

    def tolist(self) -> object:
        return self.value


class DemoLeRobotPolicy:
    """Small deterministic policy emulating LeRobot's ``PreTrainedPolicy`` surface.

    Returns three candidate two-step action chunks. Each chunk moves the cube from
    the starting position to a different final position. The score provider ranks
    them by Euclidean distance to the goal.
    """

    def __init__(self, candidates: list[list[list[float]]]) -> None:
        self._candidates = candidates
        self.reset_calls = 0
        self.select_calls = 0
        self.requires_grad_disabled = False
        self.eval_called = False

    def eval(self) -> DemoLeRobotPolicy:
        self.eval_called = True
        return self

    def requires_grad_(self, enabled: bool) -> None:
        self.requires_grad_disabled = not enabled

    def reset(self) -> None:
        self.reset_calls += 1

    def select_action(self, _observation: object) -> object:
        self.select_calls += 1
        return DemoTensor(self._candidates)


class DemoDistanceScoreProvider(BaseProvider):
    """Tiny score provider used by the demo.

    Ranks candidate action chunks by the distance from the chunk's final waypoint
    to a goal position carried in ``info["goal"]``. Scores are costs: lower is
    better.
    """

    def __init__(self) -> None:
        super().__init__(
            name="demo-distance-score",
            capabilities=ProviderCapabilities(predict=False, score=True),
            profile=ProviderProfileSpec(
                is_local=True,
                description="Deterministic distance-to-goal score provider for the LeRobot demo.",
                implementation_status="test",
                deterministic=True,
                requires_credentials=False,
            ),
        )

    def health(self) -> ProviderHealth:
        return ProviderHealth(name=self.name, healthy=True, latency_ms=0.1, details="configured")

    def score_actions(self, *, info: JSONDict, action_candidates: object) -> ActionScoreResult:
        goal = info["goal"]
        if not isinstance(goal, list) or len(goal) != 3:
            raise ValueError("demo score info.goal must be a [x, y, z] list.")
        if not isinstance(action_candidates, list) or not action_candidates:
            raise ValueError("demo score provider requires a non-empty action candidate list.")
        scores: list[float] = []
        for candidate in action_candidates:
            if not isinstance(candidate, list) or not candidate:
                raise ValueError("demo score provider requires non-empty candidate chunks.")
            final = candidate[-1]["parameters"]["target"]
            scores.append(
                round(
                    math.dist(
                        [float(final["x"]), float(final["y"]), float(final["z"])],
                        [float(goal[0]), float(goal[1]), float(goal[2])],
                    ),
                    4,
                )
            )
        best_index = min(range(len(scores)), key=scores.__getitem__)
        return ActionScoreResult(
            provider=self.name,
            scores=scores,
            best_index=best_index,
            lower_is_better=True,
            metadata={"score_type": "distance_to_goal", "candidate_count": len(scores)},
        )


def _policy_info(embodiment_tag: str, task: str) -> JSONDict:
    return {
        "observation": {
            "observation.state": [[0.0, 0.5, 0.0]],
            "observation.images.top": [[[[0, 0, 0]]]],
            "task": task,
        },
        "embodiment_tag": embodiment_tag,
        "action_horizon": 2,
    }


def _make_candidate_tensors() -> list[list[list[float]]]:
    return [
        [[0.20, 0.50, 0.00], [0.35, 0.50, 0.00]],
        [[0.30, 0.50, 0.00], [0.55, 0.50, 0.00]],
        [[0.70, 0.50, 0.00], [0.95, 0.50, 0.00]],
    ]


def _build_translator(cube_id: str) -> Any:
    def translator(
        _raw: object,
        _info: JSONDict,
        _provider_info: JSONDict,
    ) -> list[list[Action]]:
        return make_candidate_plans(cube_id)

    return translator


def run_demo(*, state_dir: Path | None = None, emit: bool = True) -> JSONDict:
    """Run the LeRobot demo and return a JSON-serializable summary."""

    resolved_state_dir = state_dir or Path(tempfile.mkdtemp(prefix="worldforge-lerobot-demo-"))
    events: list[ProviderEvent] = []

    forge = WorldForge(state_dir=resolved_state_dir, auto_register_remote=False)
    world = forge.create_world("lerobot-policy-plus-score-demo", provider="mock")
    cube = make_blue_cube(world)
    goal = blue_cube_goal(cube)
    goal_position = BLUE_CUBE_GOAL

    policy = DemoLeRobotPolicy(_make_candidate_tensors())

    def loader(
        _policy_path: str,
        _policy_type: str | None,
        _device: str | None,
        _cache_dir: str | None,
    ) -> DemoLeRobotPolicy:
        return policy

    provider = LeRobotPolicyProvider(
        policy_path="demo/lerobot-aloha-deterministic",
        policy_type="act",
        embodiment_tag="aloha",
        device="cpu",
        policy_loader=loader,
        action_translator=_build_translator(cube.id),
        event_handler=events.append,
    )
    score_provider = DemoDistanceScoreProvider()
    forge.register_provider(provider)
    forge.register_provider(score_provider)

    policy_info = _policy_info("aloha", "move the blue cube near the goal")
    score_info: JSONDict = {"goal": [goal_position.x, goal_position.y, goal_position.z]}

    policy_result = forge.select_actions("lerobot", info=policy_info)
    plan = world.plan(
        goal_spec=goal,
        provider="demo-distance-score",
        policy_provider="lerobot",
        policy_info=policy_info,
        score_info=score_info,
        execution_provider="mock",
        planner="lerobot-demo-mpc",
    )
    execution = world.execute_plan(plan)
    final_world = execution.final_world()
    saved_world_id = forge.save_world(final_world)
    reloaded_world = forge.load_world(saved_world_id)
    final_cube = reloaded_world.get_object_by_id(cube.id)
    if final_cube is None:
        raise RuntimeError("demo cube was not present after execution")

    summary: JSONDict = {
        "demo_kind": "lerobot_provider_surface",
        "runtime_mode": "injected_deterministic_policy",
        "uses_real_upstream_checkpoint": False,
        "uses_lerobot_provider": True,
        "uses_worldforge_policy_plus_score_planning": True,
        "state_dir": str(resolved_state_dir),
        "providers": forge.providers(),
        "lerobot_health": forge.provider_health("lerobot").to_dict(),
        "goal": goal.to_dict(),
        "policy_candidate_count": len(policy_result.action_candidates),
        "selected_candidate_index": plan.metadata["score_result"]["best_index"],
        "candidate_costs": plan.metadata["score_result"]["scores"],
        "selected_actions": [action.to_dict() for action in plan.actions],
        "plan": plan.to_dict(),
        "final_cube_position": final_cube.position.to_dict(),
        "saved_world_id": saved_world_id,
        "saved_worlds": forge.list_worlds(),
        "event_phases": [event.phase for event in events],
        "provider_events": [event.to_dict() for event in events],
        "policy_reset_calls": policy.reset_calls,
        "policy_eval_called": policy.eval_called,
        "policy_requires_grad_disabled": policy.requires_grad_disabled,
        "policy_select_calls": policy.select_calls,
    }
    if emit:
        _print_summary(summary)
    return summary


def _print_summary(summary: JSONDict) -> None:
    print("WorldForge LeRobot provider demo")
    print("=" * 32)
    print("Provider: LeRobotPolicyProvider")
    print("Runtime: injected deterministic policy")
    print("Checkpoint inference: not used")
    print("Planning: select_actions -> World.plan(policy+score) -> execute_plan")
    print(f"State directory: {summary['state_dir']}")
    print(f"Registered providers: {', '.join(summary['providers'])}")
    print(f"LeRobot health: {summary['lerobot_health']['details']}")
    print()
    print("Candidate costs, lower is better:")
    for index, score in enumerate(summary["candidate_costs"]):
        marker = " <- selected" if index == summary["selected_candidate_index"] else ""
        print(f"  candidate {index}: {score}{marker}")
    print()
    print("Selected actions:")
    for action in summary["selected_actions"]:
        target = action["parameters"]["target"]
        print(f"  {action['type']} -> ({target['x']:.2f}, {target['y']:.2f}, {target['z']:.2f})")
    final = summary["final_cube_position"]
    print()
    print(f"Final cube position: ({final['x']:.2f}, {final['y']:.2f}, {final['z']:.2f})")
    print(f"Saved world id: {summary['saved_world_id']}")
    print(f"Provider event phases: {', '.join(summary['event_phases'])}")
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

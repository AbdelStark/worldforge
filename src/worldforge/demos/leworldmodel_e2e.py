"""LeWorldModel provider score-planning demo.

The demo injects a deterministic cost runtime into ``LeWorldModelProvider``. It
validates the provider as a ``score`` cost oracle, drives the WorldForge capability
surface directly (``forge.score_actions`` to rank candidate action chunks, then
``forge.predict`` to roll the lowest-cost chunk forward), and reports the selected
action and per-candidate costs — all without upstream checkpoint inference.

The loop is the WorldForge backbone: a world model is used as a pure cost oracle to
rank candidate plans, and the lowest-cost plan is executed. There is no symbolic
``World`` runtime: candidates and the seeded world state are plain values.
"""

from __future__ import annotations

import argparse
import json
import math
from typing import Any

from worldforge import Position, WorldForge
from worldforge.models import JSONDict, ProviderEvent
from worldforge.providers import LeWorldModelProvider

from . import (
    BLUE_CUBE_GOAL,
    blue_cube_goal,
    execute_plan_over_state,
    make_blue_cube,
    make_candidate_plans,
    object_position,
    seed_world_state,
)


def _depth(value: object) -> int:
    if isinstance(value, list | tuple) and value:
        return 1 + _depth(value[0])
    return 0


def _flatten(value: object) -> list[object]:
    if isinstance(value, list | tuple):
        flattened: list[object] = []
        for item in value:
            flattened.extend(_flatten(item))
        return flattened
    return [value]


class DemoTensor:
    """Minimal tensor-like object accepted by ``LeWorldModelProvider``."""

    def __init__(self, value: object) -> None:
        self.value = value
        self.ndim = _depth(value)

    def detach(self) -> DemoTensor:
        return self

    def cpu(self) -> DemoTensor:
        return self

    def reshape(self, *_shape: object) -> DemoTensor:
        return DemoTensor(_flatten(self.value))

    def tolist(self) -> object:
        return self.value


class DemoNoGrad:
    def __enter__(self) -> None:
        return None

    def __exit__(self, *_args: object) -> bool:
        return False


class DemoTensorModule:
    """Subset of the torch API used by the provider."""

    Tensor = DemoTensor

    def as_tensor(self, value: object) -> DemoTensor:
        return DemoTensor(value)

    def is_tensor(self, value: object) -> bool:
        return isinstance(value, DemoTensor)

    def no_grad(self) -> DemoNoGrad:
        return DemoNoGrad()


class DemoLeWorldModelRuntime:
    """Deterministic runtime with LeWorldModel's ``get_cost`` shape."""

    def __init__(self) -> None:
        self.eval_called = False
        self.requires_grad_disabled = False
        self.last_scores: list[float] = []

    def eval(self) -> DemoLeWorldModelRuntime:
        self.eval_called = True
        return self

    def requires_grad_(self, enabled: bool) -> None:
        self.requires_grad_disabled = not enabled

    def get_cost(self, info: dict[str, Any], action_candidates: Any) -> DemoTensor:
        goal = _first_vector(info["goal"].tolist())
        samples = action_candidates.tolist()[0]
        scores = [_candidate_cost(sample, goal) for sample in samples]
        self.last_scores = scores
        return DemoTensor(scores)


def _first_vector(value: object) -> list[float]:
    current = value
    while isinstance(current, list | tuple) and current and isinstance(current[0], list | tuple):
        current = current[0]
    if not isinstance(current, list | tuple):
        raise ValueError("expected a nested numeric vector")
    return [float(item) for item in current]


def _candidate_cost(candidate: list[list[float]], goal: list[float]) -> float:
    final = [float(value) for value in candidate[-1]]
    distance_to_goal = math.dist(final[:3], goal[:3])
    path_length = 0.0
    previous = [0.0, 0.5, 0.0]
    for waypoint in candidate:
        point = [float(value) for value in waypoint[:3]]
        path_length += math.dist(previous, point)
        previous = point
    return round(distance_to_goal + (0.05 * path_length), 4)


def _make_score_info(goal: Position) -> JSONDict:
    return {
        "pixels": [
            [
                [
                    [0.0, 0.1],
                    [0.1, 0.2],
                ]
            ]
        ],
        "goal": [[[goal.x, goal.y, goal.z]]],
        "action": [[[0.0, 0.5, 0.0]]],
    }


def _make_candidate_tensors() -> list[list[list[list[float]]]]:
    return [
        [
            [[0.20, 0.50, 0.00], [0.35, 0.50, 0.00]],
            [[0.30, 0.50, 0.00], [0.55, 0.50, 0.00]],
            [[0.70, 0.50, 0.00], [0.95, 0.50, 0.00]],
        ]
    ]


def run_demo(*, emit: bool = True) -> JSONDict:
    """Run the full demo and return a JSON-serializable summary."""

    events: list[ProviderEvent] = []
    runtime = DemoLeWorldModelRuntime()
    provider = LeWorldModelProvider(
        policy="demo/pusht-lewm",
        model_loader=lambda _policy, _cache_dir: runtime,
        tensor_module=DemoTensorModule(),
        event_handler=events.append,
    )
    forge = WorldForge(auto_register_remote=False)
    forge.register_provider(provider)

    cube = make_blue_cube()
    goal = blue_cube_goal(cube)
    score_info = _make_score_info(BLUE_CUBE_GOAL)
    score_action_candidates = _make_candidate_tensors()
    candidate_plans = make_candidate_plans(cube.id)

    score_result = forge.score_actions(
        "leworldmodel",
        info=score_info,
        action_candidates=score_action_candidates,
    )
    selected_plan = candidate_plans[score_result.best_index]
    final_state = execute_plan_over_state(
        forge,
        seed_world_state([cube]),
        selected_plan,
        provider="mock",
    )
    final_position = object_position(final_state, cube.id)
    if final_position is None:
        raise RuntimeError("demo cube was not present after execution")

    summary: JSONDict = {
        "demo_kind": "leworldmodel_provider_surface",
        "runtime_mode": "injected_deterministic_cost_model",
        "uses_real_upstream_checkpoint": False,
        "uses_leworldmodel_provider": True,
        "uses_worldforge_score_planning": True,
        "planning_mode": "score",
        "providers": forge.providers(),
        "leworldmodel_health": forge.provider_health("leworldmodel").to_dict(),
        "goal": goal,
        "candidate_costs": score_result.scores,
        "selected_candidate_index": score_result.best_index,
        "selected_actions": [action.to_dict() for action in selected_plan],
        "score_result": score_result.to_dict(),
        "final_cube_position": final_position,
        "event_phases": [event.phase for event in events],
        "provider_events": [event.to_dict() for event in events],
        "runtime_eval_called": runtime.eval_called,
        "runtime_grad_disabled": runtime.requires_grad_disabled,
    }
    if emit:
        _print_summary(summary)
    return summary


def _print_summary(summary: JSONDict) -> None:
    print("WorldForge LeWorldModel provider demo")
    print("=" * 37)
    print("Provider: LeWorldModelProvider")
    print("Runtime: injected deterministic cost model")
    print("Checkpoint inference: not used")
    print("Planning: forge.score_actions(score oracle) -> forge.predict(lowest-cost plan)")
    print(f"Registered providers: {', '.join(summary['providers'])}")
    print(f"LeWorldModel health: {summary['leworldmodel_health']['details']}")
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
    print(f"Provider event phases: {', '.join(summary['event_phases'])}")
    print()
    print("JSON summary:")
    print(json.dumps(summary, indent=2, sort_keys=True))


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--json-only",
        action="store_true",
        help="Print only the final JSON summary.",
    )
    return parser


def main() -> int:
    args = _parser().parse_args()
    summary = run_demo(emit=not args.json_only)
    if args.json_only:
        print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

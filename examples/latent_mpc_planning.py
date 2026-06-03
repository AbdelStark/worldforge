"""Latent MPC planning over a score oracle — WorldForge's backbone loop.

Runs entirely from a clean checkout with no credentials, GPU, or robot. It demonstrates the loop
WorldForge is built around:

1. Sample candidate action plans in latent space (caller-owned CEM optimizer).
2. Score every candidate through a ``score`` provider used as a cost oracle.
3. Keep the elite candidates, refit the sampling distribution, and repeat (receding horizon).
4. Execute the first action of the lowest-cost plan.

The score oracle here is a deterministic stand-in (cost = squared distance to a goal point). Swap it
for a real ``score``-capable provider — for example a LeWorldModel checkpoint — and the controller
loop is unchanged: the world model stays a pure cost oracle and the controller stays a pure
optimizer.
"""

from __future__ import annotations

from worldforge import LatentMPCController, PlannerConfig
from worldforge.capability_results import ActionScoreResult
from worldforge.models import JSONDict

GOAL = (0.6, 0.5, 0.2)


class LatentDistanceOracle:
    """Minimal ``score`` provider: cost = squared distance from a candidate to the goal.

    Implements only the ``score_actions`` surface that :class:`LatentMPCController` requires, which
    is exactly the contract a real action-conditioned world model fulfils when used as a cost
    oracle.
    """

    name = "latent-distance"

    def score_actions(
        self,
        provider: str,
        *,
        info: JSONDict,
        action_candidates: object,
    ) -> ActionScoreResult:
        goal = info["goal"]["target"]
        candidates = list(action_candidates)  # type: ignore[arg-type]
        scores = [self._plan_cost(plan, goal) for plan in candidates]
        best_index = min(range(len(scores)), key=scores.__getitem__)
        return ActionScoreResult(
            provider=provider,
            scores=scores,
            best_index=best_index,
            lower_is_better=True,
            metadata={"oracle": "latent-distance"},
        )

    @staticmethod
    def _plan_cost(plan: object, goal: list[float]) -> float:
        first_action = next(iter(plan))  # type: ignore[call-overload]
        params = first_action["parameters"]
        point = (params["x"], params["y"], params["z"])
        return sum((value - target) ** 2 for value, target in zip(point, goal, strict=True))


def build_controller() -> LatentMPCController:
    return LatentMPCController(
        forge=LatentDistanceOracle(),
        score_provider="latent-distance",
        config=PlannerConfig(
            horizon=1,
            num_samples=64,
            num_iterations=5,
            num_elites=8,
            action_kind="latent_action",
            action_parameter_bounds={
                "x": (-1.0, 1.0),
                "y": (-1.0, 1.0),
                "z": (-1.0, 1.0),
            },
            seed=0,
        ),
    )


def main() -> int:
    result = build_controller().plan_step(
        observation_info={"point": [0.0, 0.0, 0.0]},
        goal_info={"target": list(GOAL)},
    )
    selected = result.actions[0].parameters

    iteration_best = [round(score, 5) for score in result.iteration_best_scores]
    control = f"{result.metadata['control_mode']} / {result.metadata['optimizer']}"
    print("Latent MPC backbone loop (checkout-safe, no credentials):")
    print(f"  goal target             : {GOAL}")
    print(f"  candidates scored       : {result.candidate_count}")
    print(f"  best cost (lower=better) : {result.best_score:.5f}")
    print(f"  per-iteration best cost  : {iteration_best}")
    print(
        "  selected action          : "
        f"x={selected['x']:.3f} y={selected['y']:.3f} z={selected['z']:.3f}"
    )
    print(f"  control mode             : {control}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

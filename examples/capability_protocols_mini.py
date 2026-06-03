from __future__ import annotations

import json
from tempfile import TemporaryDirectory

import worldforge as wf
from worldforge.providers.base import PredictionPayload


class LocalPredictor:
    name = "local-predictor"
    profile = None

    def predict(self, world_state, action, steps) -> PredictionPayload:
        state = {
            **world_state,
            "step": int(world_state.get("step", 0)) + steps,
            "metadata": {"last_action": action.to_dict()},
        }
        return PredictionPayload(state, 0.92, 0.87, [], {"source": "demo"}, 0.1)


class LocalPolicy:
    name = "local-policy"
    profile = None

    def select_actions(self, *, info):
        object_id = str(info.get("object_id", "cube-1"))
        cautious = wf.Action.move_to(0.2, 0.8, 0.0, object_id=object_id)
        aggressive = wf.Action.move_to(1.2, 0.8, 0.0, object_id=object_id)
        return wf.ActionPolicyResult(
            self.name,
            [cautious],
            action_candidates=[[cautious], [aggressive]],
        )


class LocalCost:
    name = "local-cost"
    profile = None

    def score_actions(self, *, info, action_candidates):
        candidates = action_candidates if isinstance(action_candidates, list) else []
        scores = [0.1 + index for index, _candidate in enumerate(candidates)]
        return wf.ActionScoreResult(self.name, scores or [0.1], 0, metadata={"goal": info["goal"]})


def build_plan_json() -> str:
    """Plan one action chunk through the capability surface (policy proposes, cost ranks).

    There is no symbolic ``World`` runtime: the policy proposes candidate action chunks,
    the cost provider ranks them as costs, and the lowest-cost chunk is selected.
    """

    with TemporaryDirectory() as tmpdir:
        forge = wf.WorldForge(state_dir=tmpdir, auto_register_remote=False)
        forge.register_predictor(LocalPredictor())
        forge.register_policy(LocalPolicy())
        forge.register_cost(LocalCost())

        goal = "keep the blue cube near the origin"
        policy_result = forge.select_actions("local-policy", info={"object_id": "cube-1"})
        candidate_plans = policy_result.action_candidates
        score_result = forge.score_actions(
            "local-cost",
            info={"goal": goal},
            action_candidates=[
                [action.to_dict() for action in candidate] for candidate in candidate_plans
            ],
        )
        selected = candidate_plans[score_result.best_index]
        plan = {
            "provider": "local-cost",
            "goal": goal,
            "actions": [action.to_dict() for action in selected],
            "action_count": len(selected),
            "metadata": {
                "planning_mode": "policy+score",
                "policy_provider": "local-policy",
                "score_provider": "local-cost",
                "candidate_count": len(candidate_plans),
            },
        }
        return json.dumps(plan, indent=2, sort_keys=True)


def main() -> None:
    print(build_plan_json())


if __name__ == "__main__":
    main()

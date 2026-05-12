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
    with TemporaryDirectory() as tmpdir:
        forge = wf.WorldForge(state_dir=tmpdir, auto_register_remote=False)
        forge.register_predictor(LocalPredictor())
        forge.register_policy(LocalPolicy())
        forge.register_cost(LocalCost())

        world = forge.create_world("protocol-demo", provider="local-predictor")
        plan = world.plan(
            goal="keep the blue cube near the origin",
            policy_provider="local-policy",
            policy_info={"object_id": "cube-1"},
            score_provider="local-cost",
            score_info={"goal": "stay near origin"},
        )
        return json.dumps(plan.to_dict(), indent=2, sort_keys=True)


def main() -> None:
    print(build_plan_json())


if __name__ == "__main__":
    main()

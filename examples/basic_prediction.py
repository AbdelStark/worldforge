"""Minimal prediction, latent planning, and evaluation example.

There is no symbolic ``World`` runtime: the scene is a plain world-state dict, the mock
provider rolls it forward through ``forge.predict``, ``LatentMPCController`` plans one step
over the ``score`` cost surface, and the deterministic physics evaluation suite is run
directly through the forge.
"""

import json

from worldforge import (
    Action,
    BBox,
    LatentMPCController,
    PlannerConfig,
    Position,
    SceneObject,
    WorldForge,
)
from worldforge.demos import object_position, seed_world_state
from worldforge.evaluation import EvaluationSuite


def main() -> None:
    forge = WorldForge()

    mug = SceneObject(
        "red_mug",
        Position(0.0, 0.8, 0.0),
        BBox(Position(-0.05, 0.75, -0.05), Position(0.05, 0.85, 0.05)),
        id="red_mug",
    )
    world_state = seed_world_state([mug])

    prediction = forge.predict(world_state, Action.move_to(0.3, 0.8, 0.0), steps=2, provider="mock")

    controller = LatentMPCController(
        forge=forge,
        score_provider="mock",
        config=PlannerConfig(
            horizon=1,
            num_samples=16,
            num_iterations=2,
            num_elites=4,
            action_kind="latent_action",
            action_parameter_bounds={"x": (-1.0, 1.0), "y": (-1.0, 1.0), "z": (-1.0, 1.0)},
            seed=0,
        ),
    )
    plan = controller.plan_step(
        observation_info={"point": [0.0, 0.8, 0.0]},
        goal_info={"target": [0.3, 0.8, 0.0]},
    )

    print(
        json.dumps(
            {
                "prediction": {
                    "provider": prediction.metadata["provider"],
                    "physics_score": prediction.physics_score,
                    "confidence": prediction.confidence,
                    "mug_position": object_position(prediction.state, mug.id),
                },
                "plan": {
                    "provider": "mock",
                    "actions": len(plan.actions),
                    "best_score": plan.best_score,
                    "candidate_count": plan.candidate_count,
                },
            },
            indent=2,
            sort_keys=True,
        )
    )

    report = EvaluationSuite.from_builtin("physics").run_report(["mock"], forge=forge)
    print(report.to_markdown())


if __name__ == "__main__":
    main()

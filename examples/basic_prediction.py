"""Minimal prediction, planning, and evaluation example."""

import json

from worldforge import Action, BBox, Position, SceneObject, WorldForge


def main() -> None:
    forge = WorldForge()
    world = forge.create_world("kitchen", provider="mock")

    world.add_object(
        SceneObject(
            "red_mug",
            Position(0.0, 0.8, 0.0),
            BBox(Position(-0.05, 0.75, -0.05), Position(0.05, 0.85, 0.05)),
        )
    )

    prediction = world.predict(Action.move_to(0.3, 0.8, 0.0), steps=2)
    plan = world.plan(goal="move the mug to the right")

    print(
        json.dumps(
            {
                "prediction": {
                    "provider": prediction.provider,
                    "physics_score": prediction.physics_score,
                    "confidence": prediction.confidence,
                },
                "plan": {
                    "provider": plan.provider,
                    "actions": plan.action_count,
                    "success_probability": plan.success_probability,
                },
            },
            indent=2,
            sort_keys=True,
        )
    )

    report = world.evaluate("physics")
    print(report.to_markdown())


if __name__ == "__main__":
    main()

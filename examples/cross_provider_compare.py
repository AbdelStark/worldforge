"""Compare deterministic provider outputs for the same action.

There is no symbolic ``World`` runtime: the scene is a plain world-state dict and each
provider rolls it forward through ``forge.predict`` so the prediction outputs can be
compared side by side.
"""

import json

from worldforge import Action, BBox, Position, SceneObject, WorldForge
from worldforge.demos import object_position, seed_world_state
from worldforge.providers import MockProvider


def main() -> None:
    forge = WorldForge()
    forge.register_provider(MockProvider(name="manual-mock"))

    cube = SceneObject(
        "cube",
        Position(0.0, 0.5, 0.0),
        BBox(Position(-0.05, 0.45, -0.05), Position(0.05, 0.55, 0.05)),
        id="cube",
    )
    world_state = seed_world_state([cube])
    action = Action.move_to(0.4, 0.5, 0.0)

    comparison = {}
    for provider in ("mock", "manual-mock"):
        payload = forge.predict(world_state, action, steps=1, provider=provider)
        comparison[provider] = {
            "physics_score": payload.physics_score,
            "confidence": payload.confidence,
            "cube_position": object_position(payload.state, cube.id),
        }

    print(json.dumps(comparison, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()

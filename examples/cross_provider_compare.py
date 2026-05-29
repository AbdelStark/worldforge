"""Compare deterministic provider outputs for the same action."""

from worldforge import Action, BBox, Position, SceneObject, WorldForge
from worldforge.providers import MockProvider


def main() -> None:
    forge = WorldForge()
    forge.register_provider(MockProvider(name="manual-mock"))

    world = forge.create_world("comparison", provider="mock")
    world.add_object(
        SceneObject(
            "cube",
            Position(0.0, 0.5, 0.0),
            BBox(Position(-0.05, 0.45, -0.05), Position(0.05, 0.55, 0.05)),
        )
    )

    comparison = world.compare(
        Action.move_to(0.4, 0.5, 0.0),
        providers=["mock", "manual-mock"],
        steps=1,
    )
    print(comparison.to_markdown())


if __name__ == "__main__":
    main()

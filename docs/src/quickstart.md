# Quick Start

## Install

```bash
uv add worldforge-ai          # or: pip install worldforge-ai
```

The import path stays `worldforge`:

```python
import worldforge
```

Textual harness UI as an optional extra:

```bash
uv add "worldforge-ai[harness]"
```

Rerun event and artifact recording as an optional extra:

```bash
uv add "worldforge-ai[rerun]"
```

For local development:

```bash
uv sync --group dev
```

## Create a world

```python
from worldforge import Action, BBox, Position, SceneObject, StructuredGoal, WorldForge

forge = WorldForge()
world = forge.create_world("kitchen", provider="mock")

world.add_object(
    SceneObject(
        "red_mug",
        Position(0.0, 0.8, 0.0),
        BBox(Position(-0.05, 0.75, -0.05), Position(0.05, 0.85, 0.05)),
    )
)
world.add_object(
    SceneObject(
        "blue_mug",
        Position(0.3, 0.8, 0.0),
        BBox(Position(0.25, 0.75, -0.05), Position(0.35, 0.85, 0.05)),
    )
)

prediction = world.predict(Action.move_to(0.3, 0.8, 0.0), steps=2)
print(prediction.physics_score)
```

## Plan and evaluate

```python
plan = world.plan(
    goal_spec=StructuredGoal.object_at(
        object_name="red_mug",
        position=Position(0.3, 0.8, 0.0),
    )
)
print(plan.action_count, plan.success_probability)

swap_plan = world.plan(
    goal_spec=StructuredGoal.swap_objects(
        object_name="red_mug",
        reference_object_name="blue_mug",
    )
)
print(swap_plan.to_json())

planning_report = world.evaluate("planning")
print(planning_report.to_markdown())

reasoning_report = world.evaluate("reasoning")
print(reasoning_report.to_json())
```

`StructuredGoal` also supports `object_near(...)` for relative placement and `spawn_object(...)`
for object creation.

## CLI

```bash
uv run worldforge examples
uv run worldforge doctor --registered-only
uv run worldforge world create lab --provider mock
uv run worldforge world add-object <world-id> cube --x 0 --y 0.5 --z 0 --object-id cube-1
uv run worldforge world predict <world-id> --object-id cube-1 --x 0.4 --y 0.5 --z 0
uv run worldforge world list
uv run worldforge world history <world-id>
uv run worldforge provider list
uv run worldforge provider info mock
uv run worldforge eval --suite planning --provider mock --format json
uv run worldforge benchmark --provider mock --iterations 5 --format json
```

`world history` includes initialization, object add/update/remove mutations, and provider
predictions. Object position updates translate the stored bounding box with the pose.

For the complete command map, see the [CLI Reference](./cli.md). For runnable demos and optional
runtime smoke commands, see [Examples And CLI Commands](./examples.md).

Optional visual E2E harness:

```bash
uv run --extra harness worldforge-harness
uv run --extra harness worldforge-harness --flow lerobot
uv run --extra harness worldforge-harness --flow diagnostics
uv run worldforge harness --list
```

Packaged checkout-safe demos:

```bash
uv run worldforge-demo-leworldmodel
uv run worldforge-demo-lerobot
uv run --extra rerun worldforge-demo-rerun
uv run python scripts/demo_showcases.py run first-run --workspace-dir .worldforge/demo-showcases
```

These demos use real WorldForge provider surfaces with injected deterministic runtimes where
applicable. They verify the adapter, planning, execution, persistence, and reload path without
installing optional model runtimes or downloading checkpoints. The Rerun demo also writes a local
`.rrd` artifact with event, world, plan, and benchmark layers. The demo showcase runner preserves
first-run, diagnostics, replay, dry-run, host, gallery, failure-lab, and cookbook artifacts for
issue and release evidence.

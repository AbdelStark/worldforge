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

## Predict over a world-state dict

There is no symbolic `World` runtime: the scene is a plain, JSON-serializable world-state dict and
the action-conditioned `predict` provider rolls it forward.

```python
from worldforge import Action, WorldForge

forge = WorldForge()
world_state = {
    "step": 0,
    "scene": {
        "objects": {
            "red_mug": {
                "id": "red_mug",
                "name": "red_mug",
                "pose": {"position": {"x": 0.0, "y": 0.8, "z": 0.0}},
                "bbox": {
                    "min": {"x": -0.05, "y": 0.75, "z": -0.05},
                    "max": {"x": 0.05, "y": 0.85, "z": 0.05},
                },
            }
        }
    },
}

prediction = forge.predict(world_state, Action.move_to(0.3, 0.8, 0.0), steps=2, provider="mock")
print(prediction.physics_score)
next_state = prediction.state
```

## Plan with LatentMPCController and evaluate

```python
from worldforge import LatentMPCController, PlannerConfig

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
print(len(plan.actions), plan.best_score)
```

`LatentMPCController` proposes action candidates, ranks them with the `score` provider as a cost
oracle, and returns the lowest-cost chunk. The deterministic evaluation suites run through the
forge directly:

```python
from worldforge.evaluation import EvaluationSuite

planning_report = EvaluationSuite.from_builtin("planning").run_report(["mock"], forge=forge)
print(planning_report.to_markdown())
```

## CLI

```bash
uv run worldforge examples
uv run worldforge doctor --registered-only
uv run worldforge predict kitchen --provider mock --x 0.3 --y 0.8 --z 0.0 --steps 2
uv run worldforge provider list
uv run worldforge provider info mock
uv run worldforge eval --suite planning --provider mock --format json
uv run worldforge benchmark --provider mock --iterations 5 --format json
```

`worldforge predict` seeds a world-state dict, runs the `predict` provider, and prints the result;
it does not persist anything.

For the complete command map, see the [CLI Reference](./cli.md). For runnable demos and optional
runtime smoke commands, see [Examples And CLI Commands](./examples.md).

Optional robotics showcase report:

```bash
scripts/robotics-showcase
scripts/robotics-showcase --no-tui
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

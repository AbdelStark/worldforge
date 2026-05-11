# Scenario Definition Format

WorldForge ships a JSON-native scenario format and a runner that drives a
single `WorldForge` instance through a declarative recipe: a provider, an
initial scene, an ordered sequence of actions, and a list of expected
artifacts. Scenarios let teams capture repeatable world setups in a
single checkout-safe file instead of scattering Python helpers across
examples and ad-hoc test fixtures.

## When to use scenarios

- Onboarding cookbooks: replace bespoke Python with a single
  `worldforge scenario run examples/scenarios/spawn-and-move.json`.
- Regression captures: when a checkout-safe test reproduces a bug, drop
  it in the scenario format so any contributor can re-run it without
  importing internal modules.
- Documentation: the `expected_artifacts` field doubles as a
  human-readable specification of the intended outcome.

## When scenarios are not provider fixtures

Provider fixtures live under `tests/fixtures/providers/` and exercise
adapter contracts in isolation — they capture provider input/output
pairs for `assert_provider_contract()`. Scenarios drive a full
`WorldForge` instance through public-API calls (`create_world`,
`add_object`, `predict`). They are *recipes for end-to-end behavior*,
not adapter-level test data. Scenarios can reference any registered
provider; fixtures are scoped to a single adapter.

## Schema (version 1)

```json
{
  "schema_version": 1,
  "id": "spawn-and-move",
  "name": "Spawn a mug and predict a move",
  "description": "Start with one cube, spawn a mug, then run a predict step.",
  "provider": "mock",
  "world": {
    "name": "spawn-and-move-world",
    "objects": [
      {
        "name": "cube",
        "position": {"x": 0.0, "y": 0.5, "z": 0.0},
        "bbox": {
          "min": {"x": -0.05, "y": 0.45, "z": -0.05},
          "max": {"x":  0.05, "y": 0.55, "z":  0.05}
        }
      }
    ]
  },
  "actions": [
    {
      "kind": "spawn_object",
      "parameters": {
        "name": "mug",
        "x": 0.25, "y": 0.8, "z": 0.0,
        "bbox": {
          "min": {"x": 0.20, "y": 0.75, "z": -0.05},
          "max": {"x": 0.30, "y": 0.85, "z":  0.05}
        }
      }
    },
    {
      "kind": "predict",
      "parameters": {"x": 0.4, "y": 0.5, "z": 0.0, "steps": 1}
    }
  ],
  "expected_artifacts": [
    {"label": "object_count", "kind": "object_count", "value": 2},
    {"label": "step_count",   "kind": "step",          "value": 2}
  ],
  "metadata": {}
}
```

### Action kinds

| `kind` | Effect | Required parameters |
| --- | --- | --- |
| `predict` | Calls `World.predict(Action.move_to(x,y,z), steps)` | `x`, `y`, `z`; optional `speed`, `steps`, `provider` |
| `move_to` | Same as `predict` but accepts `object_id` for targeted moves | `x`, `y`, `z`; optional `object_id`, `speed`, `steps` |
| `spawn_object` | Calls `World.predict(Action.spawn_object(...))` | `name`, `x`, `y`, `z`; optional `bbox` |

Every kind ultimately calls `World.predict` with a typed `Action`; the
provider declared on the scenario is the default but each step can
override it via `parameters.provider`.

### Expected artifact kinds

| `kind` | Description |
| --- | --- |
| `object_count` | Compares `World.object_count` after the run |
| `step` | Compares `World.step` after the run |
| `object_position` | Looks up `value.object_id` and compares position within `value.tolerance` |

Failed expectations do not raise; they appear as `passed: false` rows
in the result so the caller (CI gate, human reviewer, scripted check)
can decide whether to fail the run.

## CLI

```bash
# Validate a scenario without running it.
uv run worldforge scenario validate examples/scenarios/cube-on-table.json

# Run a scenario end-to-end.
uv run worldforge scenario run examples/scenarios/spawn-and-move.json \
    --state-dir .worldforge/worlds --format json
```

`worldforge scenario run` exits non-zero if any expectation fails, so
the command is suitable as a CI gate. Use `--output PATH` to write the
result to a file instead of stdout.

## Python surface

```python
from pathlib import Path
from worldforge import WorldForge, load_scenario, run_scenario

forge = WorldForge()
scenario = load_scenario(Path("examples/scenarios/cube-on-table.json"))
result = run_scenario(forge, scenario)
if not result.all_expectations_passed():
    raise RuntimeError(
        "scenario expectations failed: "
        + ", ".join(
            f"{c.label}={c.observed!r}≠{c.expected!r}"
            for c in result.expectation_checks
            if not c.passed
        )
    )
```

## Out of scope

- **No arbitrary Python execution.** Scenario files are JSON only —
  they cannot import code, evaluate expressions, or reference other
  files. Every action kind is a typed `Action` constructor; new kinds
  require a code change with tests.
- **No simulator-specific schema.** The format is provider-agnostic.
  Embodiment-specific or simulator-specific configuration is not part
  of the scenario; live providers must read those settings from their
  own host environment.
- **No silent failure.** Invalid scenarios fail loudly at parse time
  via `WorldForgeError` with a path to the offending file and field.
  Failed expectations surface in `ScenarioResult.expectation_checks`
  with explicit before/after values.

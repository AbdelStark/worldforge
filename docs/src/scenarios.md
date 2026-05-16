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

## Scenario Gallery

The checkout-safe gallery under `examples/scenarios/` gives contributors
small starting points for local worlds and scenario-result artifacts:

| Scenario | Intent | Expected artifact | First triage step |
| --- | --- | --- | --- |
| `cube-on-table.json` | successful world setup | passing JSON result with one object and two mock steps | inspect the initial cube pose and mock provider setup |
| `spawn-and-move.json` | spawn plus predict workflow | passing result with two objects and two steps | inspect `spawn_object` bbox and the following predict step |
| `expected-failure-object-count.json` | intentionally failed expectation | non-zero `scenario run` result with `passed: false` expectation row | confirm the mismatch is intentional before changing the scenario |
| `invalid-action-missing-target.json` | invalid action boundary | `scenario validate` passes, `scenario run` fails with missing `z` | inspect `actions[0].parameters` for the missing coordinate |
| `evaluation-readiness.json` | evaluation-oriented setup | passing result with two static objects and `step=0` | inspect the initial world object payload before changing evaluation code |
| `report-export-basic.json` | report/export example | passing JSON or Markdown result suitable for `--output` attachment | compare scenario result JSON before checking world export |
| `inheritance/base.json`, `child-a.json`, `child-b.json` | scenario inheritance (`extends`) | base passes alone; children inherit the world setup and override actions / expectations | run the base first to confirm shared setup before debugging a child |

Run the gallery through the same CLI surface as any local scenario:

```bash
uv run worldforge scenario validate examples/scenarios/report-export-basic.json
uv run worldforge scenario run examples/scenarios/report-export-basic.json \
    --state-dir .worldforge/scenario-gallery/report-export --format markdown \
    --output .worldforge/scenario-gallery/report-export.md
```

The failed and invalid examples are deliberate. They are marked in
`metadata.expected_failure` or `metadata.expected_cli_error` so tests can
prove the failure mode without weakening the normal CLI contract.

## Schema (version 2)

The minimal scenario shape is unchanged from version 1; the bump only
adds the optional `extends` top-level field documented under [Scenario
Inheritance](#scenario-inheritance-extends). Files claiming
`schema_version: 1` continue to validate unchanged, but they cannot use
`extends`.


<!-- worldforge-snippet: parse -->
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

## Scenario Inheritance (`extends`)

Schema version 2 adds a single optional top-level field, `extends`, so a
child scenario can reuse a base file instead of copying its full setup.
The base remains a standalone scenario you can run on its own.

<!-- worldforge-snippet: skip-illustrative -->
```json
{
  "schema_version": 2,
  "extends": "./base.json",
  "id": "lab-setup-child-a",
  "name": "Lab setup child A",
  "actions": [
    {"kind": "predict", "parameters": {"x": 0.25, "y": 0.5, "z": 0.0, "steps": 2}}
  ],
  "expected_artifacts": [
    {"label": "object_count", "kind": "object_count", "value": 1},
    {"label": "step_count", "kind": "step", "value": 2}
  ]
}
```

### Merge semantics

- **Replace at the top level, no deep merge.** If the child names a
  top-level key (for example, `world`, `actions`, `expected_artifacts`,
  `metadata`), the child's value replaces the parent's wholesale. To
  tweak a single object inside `world.objects`, the child copies the
  full `world` block.
- **Child wins on conflict.** Identical keys present in both files take
  the child value. Keys the child omits keep the parent value.
- **Single parent only.** `extends` is one string, not a list.
- **Resolution is relative to the child file.** Absolute paths are
  rejected to keep scenario folders checkout-safe.
- **Inheritance happens before matrix expansion.** A child can introduce
  a `matrix` block, override an inherited one, or inherit the parent's
  matrix unchanged.

### Validation rules

| Rule | Behavior |
| --- | --- |
| Missing parent file | `WorldForgeError` with the resolved path |
| Absolute `extends` path | `WorldForgeError`, must be relative |
| Empty or non-string `extends` | `WorldForgeError` |
| `extends` in a `schema_version: 1` file | `WorldForgeError` (requires schema version 2) |
| Cycle in the `extends` chain | `WorldForgeError` listing the offending chain |
| Chain depth above `SCENARIO_MAX_EXTENDS_DEPTH` | `WorldForgeError` |
| `extends` passed to `parse_scenario` (dict, no path) | `WorldForgeError` — use `load_scenario(<path>)` |

The gallery under `examples/scenarios/inheritance/` ships a base plus
two children to exercise these rules end-to-end:

```bash
uv run worldforge scenario run examples/scenarios/inheritance/base.json
uv run worldforge scenario run examples/scenarios/inheritance/child-a.json
uv run worldforge scenario run examples/scenarios/inheritance/child-b.json
```

## Scenario Parameter Matrices

Add a top-level `matrix` object when one scenario should run over a
small bounded sweep. `matrix.parameters` values are JSON-native arrays,
the Cartesian product must fit under `max_cases`, and placeholders must
occupy an entire JSON value such as `"${target_x}"`; they are
whole-value placeholders. Partial
interpolation like `"cube-${target_x}"` is rejected, and there is no
expression language.

<!-- worldforge-snippet: parse -->
```json
{
  "schema_version": 1,
  "id": "target-sweep",
  "name": "Target sweep",
  "description": "Run the same checkout-safe scenario against two target positions.",
  "provider": "${provider_name}",
  "world": {
    "name": "target-sweep-world",
    "objects": [
      {
        "name": "cube",
        "position": {"x": "${object_x}", "y": 0.5, "z": 0.0},
        "bbox": {
          "min": {"x": -0.05, "y": 0.45, "z": -0.05},
          "max": {"x":  0.05, "y": 0.55, "z":  0.05}
        }
      }
    ]
  },
  "actions": [
    {
      "kind": "predict",
      "parameters": {
        "provider": "${provider_name}",
        "x": "${target_x}",
        "y": 0.5,
        "z": 0.0,
        "steps": 2
      }
    }
  ],
  "expected_artifacts": [
    {"label": "object_count", "kind": "object_count", "value": 1},
    {"label": "step_count", "kind": "step", "value": "${expected_step}"}
  ],
  "matrix": {
    "max_cases": 4,
    "parameters": {
      "expected_step": [2],
      "object_x": [0.0],
      "provider_name": ["mock"],
      "target_x": [0.25, 0.5]
    }
  },
  "metadata": {}
}
```

Supported placeholder locations are intentionally narrow:

| Location | Use |
| --- | --- |
| `provider` | Select the scenario provider name |
| `actions[*].parameters.provider` | Override a step provider name |
| `world.objects[*].position` and `.position.x/y/z` | Sweep object positions |
| `actions[*].parameters.x/y/z` | Sweep action targets |
| `expected_artifacts[*].value` and descendants | Sweep expected artifact values |

`worldforge scenario validate <path>` expands and validates every case
before execution. `worldforge scenario run <path>` creates one concrete
scenario per case in the configured `--state-dir`, then returns aggregate
`case_count`, `passed_case_count`, `failed_case_count`, and
`failed_cases` fields. The command exits non-zero when any case fails.

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

<!-- worldforge-snippet: skip-illustrative -->
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

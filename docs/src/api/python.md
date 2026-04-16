# Python API

## Entry points

```python
from worldforge import Action, ActionScoreResult, World, WorldForge
```

## `WorldForge`

Top-level framework object responsible for:

- provider registration
- world creation and persistence
- generation, transfer, reasoning, embedding, and action-scoring helpers
- provider profiles and environment diagnostics

Common inspection helpers:

```python
from worldforge import WorldForge

forge = WorldForge()

profiles = forge.builtin_provider_profiles()
doctor = forge.doctor()

print(profiles[0].supported_tasks)
print(doctor.issues)
```

## Observability

```python
import logging

from worldforge import WorldForge
from worldforge.observability import JsonLoggerSink, ProviderMetricsSink, compose_event_handlers

metrics = ProviderMetricsSink()
forge = WorldForge(
    event_handler=compose_event_handlers(
        JsonLoggerSink(logger=logging.getLogger("demo.worldforge")),
        metrics,
    )
)

forge.generate("orbiting cube", "mock", duration_seconds=1.0)
print(metrics.get("mock", "generate").to_dict())
```

## Action Scoring

Providers that expose the `score` capability can rank candidate action sequences without claiming
prediction, generation, or reasoning support. LeWorldModel uses this path because its upstream
runtime is a JEPA cost model.

```python
from worldforge import WorldForge

forge = WorldForge()
result = forge.score_actions(
    "leworldmodel",
    info={
        "pixels": [[[0.0, 0.1, 0.2]]],
        "goal": [[[0.8, 0.9, 1.0]]],
        "action": [[[0.0, 0.0, 0.0]]],
    },
    action_candidates=[
        [
            [[0.0], [0.1], [0.2]],
            [[0.3], [0.2], [0.1]],
        ]
    ],
)

print(result.best_index, result.best_score)
```

`ActionScoreResult` validates finite scores, exposes `best_index` and `best_score`, and includes
`lower_is_better` so callers do not have to infer score direction from provider-specific docs.

## `World`

Stateful runtime object responsible for:

- scene object management
- prediction
- comparison
- planning with heuristic strings or typed `StructuredGoal`
- evaluation

Example:

```python
from worldforge import Position, StructuredGoal

plan = world.plan(
    goal_spec=StructuredGoal.object_at(
        object_name="red_mug",
        position=Position(0.3, 0.8, 0.0),
    )
)
```

Typed structured goals currently cover:

- `StructuredGoal.object_at(...)`
- `StructuredGoal.object_near(...)`
- `StructuredGoal.spawn_object(...)`
- `StructuredGoal.swap_objects(...)`

## Evaluation

```python
from worldforge.evaluation import EvaluationSuite

print(EvaluationSuite.builtin_names())

suite = EvaluationSuite.from_builtin("reasoning")
report = suite.run_report(["mock"], forge=forge)
print(report.results[0].passed)
print(report.to_markdown())
```

## Benchmarking

```python
from worldforge import ProviderBenchmarkHarness

harness = ProviderBenchmarkHarness(forge=forge)
report = harness.run(["mock"], operations=["predict", "generate"], iterations=5)
print(report.to_json())
```

## Provider contract testing

```python
from worldforge.providers import MockProvider
from worldforge.testing import assert_provider_contract

report = assert_provider_contract(MockProvider())
print(report.to_dict())
```

## Public failure modes

WorldForge uses three public exception families for runtime workflows:

- `WorldForgeError`: invalid caller input, invalid model values, unsupported formats, and invalid
  local configuration values.
- `WorldStateError`: malformed persisted state or provider-supplied world state that cannot be
  safely restored or applied.
- `ProviderError`: provider credentials, transport failures, unsupported provider operations,
  malformed upstream responses, provider-specific input limits, expired artifacts, invalid
  downloaded media, optional dependency failures, and malformed model score outputs.

Provider-facing workflows touched by remote adapters fail before returning partial results:

```python
from worldforge import GenerationOptions, WorldForge
from worldforge.providers import ProviderError

forge = WorldForge()

try:
    clip = forge.generate(
        "a rainy alley at night",
        "runway",
        duration_seconds=4.0,
        options=GenerationOptions(ratio="1280:720"),
    )
except ProviderError as exc:
    # Inspect emitted ProviderEvent records for transport status and attempts.
    raise
```

Important boundary checks:

- `Position`, `Rotation`, `VideoClip`, request policies, provider events, embeddings, reasoning
  confidence, and prediction payload metrics reject non-finite numbers.
- `World.add_object(...)` rejects duplicate scene object IDs.
- Imported or provider-supplied world state rejects scene-object keys that disagree with embedded
  object IDs.
- Cosmos generation responses must include a non-empty base64 `b64_video` field and typed
  optional metadata.
- Runway task creation, polling, and artifact download responses are validated before constructing
  a returned `VideoClip`.
- LeWorldModel scoring requires `pixels`, `goal`, and `action` info fields, four-dimensional
  action candidates, optional `stable_worldmodel` and `torch` runtime dependencies, and finite
  model scores.

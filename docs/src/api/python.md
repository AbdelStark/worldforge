# Python API

## Entry points

```python
from worldforge import (
    Action,
    ActionPolicyResult,
    ActionScoreResult,
    BenchmarkBudget,
    Cost,
    Policy,
    load_benchmark_inputs,
    RunnableModel,
    WorldForge,
)
```

## `WorldForge`

Top-level framework object responsible for:

- provider registration
- world creation and persistence
- generation, transfer, reasoning, embedding, action-scoring, and action-policy helpers
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

Provider capability filters are strict. Valid capability names are `predict`, `generate`,
`reason`, `embed`, `plan`, `transfer`, `score`, and `policy`; unknown names raise
`WorldForgeError` instead of producing an empty result by typo.

## Capability protocols

Provider adapters can still subclass `BaseProvider`, but small integrations can also register a
single capability object. The object declares a non-empty `name`, optional `ProviderProfileSpec`,
and the method for exactly the capability it implements.

```python
from worldforge import ActionScoreResult, WorldForge
from worldforge.providers import ProviderProfileSpec


class LocalCost:
    name = "local-cost"
    profile = ProviderProfileSpec(description="Local score model")

    def score_actions(self, *, info, action_candidates):
        return ActionScoreResult(provider=self.name, scores=[0.2, 0.7], best_index=0)


forge = WorldForge()
forge.register_cost(LocalCost())

result = forge.score_actions(cost="local-cost", info={}, action_candidates=[{}, {}])
print(result.best_index)
```

The same pattern is available through `register_policy`, `register_generator`,
`register_predictor`, `register_reasoner`, `register_embedder`, and `register_transferer`.
`forge.register(...)` dispatches a pure object by protocol membership, and
`RunnableModel(...)` can group several capability implementations. Registered protocol
implementations appear in `providers()`, `provider_profile(...)`, `doctor(...)`, planning, and the
benchmark harness. Existing calls such as `forge.generate("prompt", "mock")` keep resolving
through the legacy provider registry.

## Persistence

```python
from worldforge import WorldForge

forge = WorldForge(state_dir=".worldforge/worlds")
world = forge.create_world("lab", provider="mock")
world_id = forge.save_world(world)

payload = forge.export_world(world_id)
copy = forge.import_world(payload, new_id=True, name="lab-copy")
copy_id = forge.save_world(copy)

forge.delete_world(world_id)
print(forge.list_worlds(), copy_id)
```

`save_world(...)`, `load_world(...)`, `import_world(...)`, `fork_world(...)`, and
`delete_world(...)` all validate world identifiers before touching the filesystem. Delete removes
only the local JSON file for a file-safe world id; missing worlds raise `WorldStateError` instead
of being treated as successful no-ops.

## Observability

```python
import logging
from pathlib import Path

from worldforge import WorldForge
from worldforge.observability import (
    JsonLoggerSink,
    OpenTelemetryProviderEventSink,
    ProviderMetricsSink,
    RunJsonLogSink,
    compose_event_handlers,
)

run_id = "demo-run"
metrics = ProviderMetricsSink()
forge = WorldForge(
    event_handler=compose_event_handlers(
        JsonLoggerSink(logger=logging.getLogger("demo.worldforge"), extra_fields={"run_id": run_id}),
        RunJsonLogSink(Path(".worldforge") / "runs" / run_id / "provider-events.jsonl", run_id),
        metrics,
    )
)

forge.generate("orbiting cube", "mock", duration_seconds=1.0)
print(metrics.get("mock", "generate").to_dict())
```

Provider events are log-safe by default. The `target` field keeps endpoint or artifact path context
but strips URL userinfo, query strings, and fragments; message, metadata, and sink extra fields
redact obvious bearer tokens, API keys, signatures, passwords, and signed URLs. `RunJsonLogSink`
appends one JSON object per line and stamps every record with `run_id` for manifest correlation.
`OpenTelemetryProviderEventSink` is optional and accepts an injected host tracer, so the base
package does not import OpenTelemetry or configure collectors.

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
Metadata must be JSON-native: dict keys are strings, numbers are finite, and object instances or
tuples are rejected instead of being coerced silently.

The planner can consume the same score surface when callers provide WorldForge actions that
correspond to each scored candidate. By default, those actions are serialized and passed to the
score provider. Pass `score_action_candidates` when the scorer expects a provider-native tensor or
latent candidate payload:

```python
from worldforge import Action

plan = world.plan(
    goal="choose the lowest-cost LeWorldModel action",
    provider="leworldmodel",
    planner="leworldmodel-mpc",
    candidate_actions=[
        [Action.move_to(0.1, 0.5, 0.0)],
        [Action.move_to(0.4, 0.5, 0.0)],
    ],
    score_info=info,
    score_action_candidates=action_candidates,
    execution_provider="mock",
)

print(plan.actions, plan.metadata["score_result"]["best_index"])
```

Score-based plans do not ask the score provider to predict state. `Plan.predicted_states` stays
empty, score details are stored in `Plan.metadata`, and `execute_plan(...)` uses
`execution_provider` when the scoring provider does not implement `predict()`. The planner requires
one score per candidate action plan; mismatched score counts fail before a plan is returned.

## Action Policy

Providers that expose the `policy` capability select executable action chunks from observations.
NVIDIA Isaac GR00T uses this surface because it is an embodied VLA policy, not a predictive world
model.

```python
result = forge.select_actions(
    "gr00t",
    info={
        "observation": {
            "video": {"front": video_array},
            "state": {"eef": state_array},
            "language": {"task": [["pick up the cube"]]},
        },
        "embodiment_tag": "LIBERO_PANDA",
        "action_horizon": 16,
    },
)

print(result.actions, result.raw_actions)
```

`ActionPolicyResult` validates that the provider returned at least one WorldForge `Action`,
preserves provider-native raw actions for debugging, and can carry multiple candidate action
chunks for downstream scoring. Preserved raw actions and metadata must be JSON-native so run
artifacts can be serialized without hidden encoder behavior.

Policy-only planning:

```python
plan = world.plan(
    goal="pick up the cube",
    provider="gr00t",
    policy_info=policy_info,
    execution_provider="mock",
)
```

Policy plus score planning:

```python
plan = world.plan(
    goal="choose the lowest-cost policy candidate",
    policy_provider="gr00t",
    score_provider="leworldmodel",
    policy_info=policy_info,
    score_info=lewm_info,
    execution_provider="mock",
)
```

By default, WorldForge serializes the policy candidates as lists of `Action.to_dict()` payloads
before calling the score provider. Pass `score_action_candidates` when the scorer needs a
provider-native tensor or latent candidate format. The host still owns embodiment-specific action
translation and any model-native mapping.

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

Typed structured goals cover:

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
from worldforge import BenchmarkBudget, ProviderBenchmarkHarness, load_benchmark_inputs

harness = ProviderBenchmarkHarness(forge=forge)
inputs = load_benchmark_inputs(
    {
        "embedding_text": "benchmark cube state",
        "generation_prompt": "benchmark orbiting cube",
    }
)
report = harness.run(
    ["mock"],
    operations=["predict", "generate", "embed"],
    iterations=5,
    inputs=inputs,
)
print(report.to_json())

budget = BenchmarkBudget.from_dict({"max_p95_latency_ms": 25.0})
print(report.evaluate_budgets([budget]).passed)
```

## Provider contract testing

```python
from worldforge.providers import MockProvider
from worldforge.testing import assert_provider_contract

report = assert_provider_contract(MockProvider())
print(report.to_dict())
```

For score providers, pass provider-specific score payloads so the helper can exercise
`score_actions(...)`:

```python
report = assert_provider_contract(
    provider,
    score_info={"observation": [[0.0]], "goal": [[1.0]]},
    score_action_candidates=[[[[0.0]]]],
)
```

For policy providers, pass provider-specific policy observations:

```python
report = assert_provider_contract(provider, policy_info=policy_info)
```

## Public failure modes

WorldForge uses three public exception families for runtime workflows:

- `WorldForgeError`: invalid caller input, invalid model values, unsupported formats, and invalid
  local configuration values, including non-file-safe world IDs used for persistence lookup.
- `WorldStateError`: malformed persisted state or provider-supplied world state that cannot be
  safely restored or applied, including invalid scene-object maps and invalid history entries.
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
- `Action.parameters`, `SceneObject.metadata`, provider-event metadata, score metadata, policy raw
  actions, policy metadata, and prediction payload state/metadata reject non-JSON-native values
  rather than accepting object instances that only fail at persistence time.
- Evaluation and benchmark result objects validate finite metrics, score ranges, coherent counts,
  and JSON-native metrics before JSON, Markdown, or CSV artifacts are rendered.
- `World.add_object(...)` rejects duplicate scene object IDs.
- Imported or provider-supplied world state rejects scene-object keys that disagree with embedded
  object IDs.
- Cosmos generation responses must include a non-empty base64 `b64_video` field and typed
  optional metadata.
- Runway task creation, polling, and artifact download responses are validated before constructing
  a returned `VideoClip`.
- LeWorldModel scoring requires `pixels`, `goal`, and `action` info fields, action candidates shaped
  as `(batch=1, samples, horizon, action_dim)`, optional `stable_worldmodel` and `torch` runtime
  dependencies, one returned score per candidate sample, and finite model scores.

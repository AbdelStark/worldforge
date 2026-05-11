# Python API

For compatibility tiers, deprecation expectations, and artifact-schema migration rules, see
[Public API Stability](../api-stability.md).

## Entry points

<!-- worldforge-snippet: execute -->
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

<!-- worldforge-snippet: execute -->
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

<!-- worldforge-snippet: execute -->
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

Capability protocol implementations and `BaseProvider` subclasses may also expose provider-owned
`preflight`, `warmup`, and `teardown` hooks that return `ProviderLifecycleResult`. Diagnostics
surface the aggregate `ProviderLifecycleStatus` through `doctor()` and
`provider_lifecycle_status(...)` without changing the capability method contract.

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

<!-- worldforge-snippet: skip-illustrative -->
```python
import logging
from pathlib import Path

from worldforge import WorldForge
from worldforge.workflow_trace import workflow_trace_from_provider_events
from worldforge.observability import (
    JsonLoggerSink,
    ProviderMetricsExporterSink,
    OpenTelemetryProviderEventSink,
    ProviderMetricsSink,
    RunJsonLogSink,
    compose_event_handlers,
)
from worldforge.rerun import RerunArtifactLogger, RerunEventSink, RerunRecordingConfig, RerunSession

run_id = "demo-run"
metrics = ProviderMetricsSink()
host_metrics_exporter = ...  # supplied by your service
forge = WorldForge(
    event_handler=compose_event_handlers(
        JsonLoggerSink(logger=logging.getLogger("demo.worldforge"), extra_fields={"run_id": run_id}),
        RunJsonLogSink(Path(".worldforge") / "runs" / run_id / "provider-events.jsonl", run_id),
        ProviderMetricsExporterSink(host_metrics_exporter),
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
`ProviderMetricsExporterSink` is also optional and accepts a host-owned metrics exporter with
bounded labels for provider, operation, phase, status class, and capability.

Composed operations can emit safe workflow trace artifacts. `Plan.metadata["workflow_trace"]`
records planning steps, evaluation reports export `workflow_trace.json` and `workflow_trace.md`,
and `workflow_trace_from_provider_events(...)` can compact emitted `ProviderEvent` records into a
schema-versioned trace without storing raw prompts, tensors, credentials, or controller telemetry.

Rerun is available as an optional observability and artifact layer:

<!-- worldforge-snippet: skip-host-owned -->
```python
session = RerunSession(RerunRecordingConfig(save_path=".worldforge/rerun/run.rrd"))
rerun_events = RerunEventSink(session=session)
artifacts = RerunArtifactLogger(session=session)

forge = WorldForge(event_handler=rerun_events)
world = forge.create_world("lab", provider="mock")
plan = world.plan("move the first object right")

artifacts.log_world(world)
artifacts.log_plan(plan)
artifacts.log_workflow_trace(plan.metadata["workflow_trace"])
session.close()
```

Install with `worldforge-ai[rerun]`. Rerun is not a provider and does not advertise WorldForge
capabilities.

## Scene Artifact Validation

Future spatial or 3D scene providers must validate their JSON artifact descriptor before returning
or preserving evidence. The helper is dependency-free and does not fetch assets, render previews,
or run simulators:

<!-- worldforge-snippet: skip-illustrative -->
```python
from worldforge import validate_scene_artifact

artifact = validate_scene_artifact(payload)
```

The validated artifact remains a JSON object. Invalid units, malformed transforms, non-finite
numbers, tuple-shaped values, object instances, unsafe URLs, unmarked host-local paths,
secret-like metadata keys, and oversized metadata raise `WorldForgeError`.

## Action Scoring

Providers that expose the `score` capability can rank candidate action sequences without claiming
prediction, generation, or reasoning support. LeWorldModel uses this path because its upstream
runtime is a JEPA cost model.

<!-- worldforge-snippet: skip-host-owned -->
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
from worldforge import action_candidates_to_score_payload, bounded_move_grid_candidates

candidate_actions = bounded_move_grid_candidates(
    x_bounds=(0.1, 0.7),
    y_bounds=(0.5, 0.5),
    z_bounds=(0.0, 0.0),
    x_steps=3,
    y_steps=1,
    z_steps=1,
)
plan = world.plan(
    goal="choose the lowest-cost LeWorldModel action",
    provider="leworldmodel",
    planner="leworldmodel-mpc",
    candidate_actions=candidate_actions,
    score_info=info,
    score_action_candidates=action_candidates_to_score_payload(candidate_actions),
    execution_provider="mock",
)

print(plan.actions, plan.metadata["score_result"]["best_index"])
```

Score-based plans do not ask the score provider to predict state. `Plan.predicted_states` stays
empty, score details are stored in `Plan.metadata`, and `execute_plan(...)` uses
`execution_provider` when the scoring provider does not implement `predict()`. The planner requires
one score per candidate action plan; mismatched score counts fail before a plan is returned.

Candidate helpers are provider-agnostic and return validated `Action` sequences. Use
`cartesian_offset_candidates(...)` for relative move candidates, `object_near_candidates(...)` for
reference-relative placements, `swap_action_candidates(...)` for two-object swaps, and
`bounded_move_grid_candidates(...)` for inclusive Cartesian grids. They do not preprocess images,
do not infer provider-native tensors, and do not reinterpret robot action spaces; pass
`score_action_candidates`
explicitly when a score provider needs a task-specific tensor instead of serialized `Action`
payloads.

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

gallery = report.failure_gallery()
print(gallery.to_json())
```

Failed reports expose representative, sanitized gallery cases through `failure_gallery()` and
through `report.artifacts()["failure_gallery.json"]` / `["failure_gallery.md"]`. The gallery is
for deterministic contract triage; it does not rank providers or claim physical fidelity.

Custom deterministic suites use the same public report path:

```python
from worldforge.evaluation import EvaluationContext, EvaluationScenario, EvaluationSuite


def check_world(context: EvaluationContext):
    return context.outcome(
        score=1.0,
        passed=context.world.object_count == 0,
        metrics={"object_count": context.world.object_count},
    )


custom = EvaluationSuite.custom(
    suite_id="custom-empty-world",
    name="Custom Empty World Evaluation",
    suite_version="custom-empty-world:1",
    claim_boundary="Checkout-safe custom example; not a model-quality claim.",
    scenarios=[
        EvaluationScenario.from_callable(
            name="empty-world-readable",
            description="Checks that a new world can be inspected.",
            evaluator=check_world,
        )
    ],
)
report = custom.run_report("mock", forge=forge)
print(report.provenance.suite_version)
```

`EvaluationSuite.register(...)` and `EvaluationSuite.from_registered(...)` provide a process-local
registry for host applications that want to name custom suites.

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

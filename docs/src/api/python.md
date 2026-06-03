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
- prediction, embedding, action-scoring, and action-policy helpers
- provider profiles and environment diagnostics

Common inspection helpers:

<!-- worldforge-snippet: execute -->
```python
from worldforge import Action, WorldForge

forge = WorldForge()

profiles = forge.builtin_provider_profiles()
doctor = forge.doctor()

print(profiles[0].supported_tasks)
print(doctor.issues)
```

Provider capability filters are strict. Valid capability names are `predict`, `embed`, `plan`,
`score`, and `policy`; unknown names raise
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

The same pattern is available through `register_policy`, `register_predictor`, and
`register_embedder`.
`forge.register(...)` dispatches a pure object by protocol membership, and
`RunnableModel(...)` can group several capability implementations. Registered protocol
implementations appear in `providers()`, `provider_profile(...)`, `doctor(...)`, planning, and the
benchmark harness.

For a runnable policy-plus-score example that registers plain in-process objects, see
[Capability Protocols Quickstart](../capability-protocols-quickstart.md).

Capability protocol implementations and `BaseProvider` subclasses may also expose provider-owned
`preflight`, `warmup`, and `teardown` hooks that return `ProviderLifecycleResult`. Diagnostics
surface the aggregate `ProviderLifecycleStatus` through `doctor()` and
`provider_lifecycle_status(...)` without changing the capability method contract.

## World State

There is no symbolic `World` runtime or built-in JSON world store. Planning runs over plain,
JSON-serializable world-state dicts: `forge.predict` rolls a `world_state` dict forward one action
at a time.

<!-- worldforge-snippet: execute -->
```python
from worldforge import Action, WorldForge

forge = WorldForge()
world_state = {"step": 0, "scene": {"objects": {}}}
payload = forge.predict(world_state, Action.move_to(0.2, 0.5, 0.0), steps=1, provider="mock")
print(payload.metadata["provider"], payload.physics_score)
next_state = payload.state
```

Invalid public inputs raise `WorldForgeError`, and malformed persisted or provider world-state
payloads raise `WorldStateError` at the boundary. Durable persistence is host-owned: serialize the
plain world-state dict into your own store.

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

world_state = {"step": 0, "scene": {"objects": {}}}
forge.predict(world_state, Action.move_to(0.2, 0.5, 0.0), steps=1, provider="mock")
print(metrics.get("mock", "predict").to_dict())
```

Provider events are log-safe by default. The `target` field keeps endpoint or artifact path context
but strips URL userinfo, query strings, and fragments; message, metadata, and sink extra fields
redact obvious bearer tokens, API keys, signatures, passwords, and signed URLs. `RunJsonLogSink`
appends one JSON object per line and stamps every record with `run_id` for manifest correlation.
`OpenTelemetryProviderEventSink` is optional and accepts an injected host tracer, so the base
package does not import OpenTelemetry or configure collectors.
`ProviderMetricsExporterSink` is also optional and accepts a host-owned metrics exporter with
bounded labels for provider, operation, phase, status class, and capability.

Composed operations can emit safe workflow trace artifacts. Evaluation reports export
`workflow_trace.json` and `workflow_trace.md`, and `workflow_trace_from_provider_events(...)` can
compact emitted `ProviderEvent` records into a schema-versioned trace without storing raw prompts,
tensors, credentials, or controller telemetry.

Rerun is available as an optional observability and artifact layer:

<!-- worldforge-snippet: skip-host-owned -->
```python
session = RerunSession(RerunRecordingConfig(save_path=".worldforge/rerun/run.rrd"))
rerun_events = RerunEventSink(session=session)
artifacts = RerunArtifactLogger(session=session)

forge = WorldForge(event_handler=rerun_events)
world_state = {"step": 0, "scene": {"objects": {}}}
payload = forge.predict(world_state, Action.move_to(0.2, 0.5, 0.0), steps=1, provider="mock")

artifacts.log_json("worlds/initial", world_state)
artifacts.log_json("worlds/predicted", payload.state)
session.close()
```

Install with `worldforge-ai[rerun]`. Rerun is not a provider and does not advertise WorldForge
capabilities.

## Action Scoring

Providers that expose the `score` capability can rank candidate action sequences without claiming
prediction or policy support. LeWorldModel uses this path because its upstream runtime is a JEPA
cost model.

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

`ActionScoreResult` validates finite scores, exposes `best_index` and `best_score`, and requires
`best_index` to match `lower_is_better` so callers do not have to infer score direction from
provider-specific docs.
Metadata must be JSON-native: dict keys are strings, numbers are finite, and object instances or
tuples are rejected instead of being coerced silently.

Candidate helpers are provider-agnostic and return validated `Action` sequences. Use
`cartesian_offset_candidates(...)` for relative move candidates, `object_near_candidates(...)` for
reference-relative placements, `swap_action_candidates(...)` for two-object swaps, and
`bounded_move_grid_candidates(...)` for inclusive Cartesian grids. By default WorldForge serializes
candidate actions with `action_candidates_to_score_payload(...)` before calling
`forge.score_actions(...)`; pass `score_action_candidates` explicitly when a score provider needs a
task-specific tensor instead of serialized `Action` payloads. These helpers
do not preprocess images, do not infer provider-native tensors, and
do not reinterpret robot action spaces.

For a checkout-safe policy+score candidate lab that preserves raw policy actions, ranks generated
candidates, and shows invalid-bounds plus missing-translator failures, run:

```bash
uv run python scripts/demo_showcases.py run policy-score-candidate-lab --workspace-dir .worldforge/demo-showcases --overwrite
```

## Latent Planning

`LatentMPCController` owns the receding-horizon optimizer: it proposes action candidates, ranks them
with a `score` provider as a cost oracle, and returns the lowest-cost chunk. There is no symbolic
`World` runtime — the controller operates over `observation_info`/`goal_info` payloads and the
`score` capability.

<!-- worldforge-snippet: execute -->
```python
from worldforge import LatentMPCController, PlannerConfig, WorldForge

forge = WorldForge()
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
    observation_info={"point": [0.0, 0.5, 0.0]},
    goal_info={"target": [0.55, 0.5, 0.0]},
)
print(len(plan.actions), plan.best_score, plan.candidate_count)
```

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

Policy plus score planning composes the two surfaces directly: `forge.select_actions(...)` proposes
candidate chunks, `forge.score_actions(...)` ranks them, and the caller selects the lowest-cost
chunk by `best_index`. The host owns embodiment-specific action translation and any model-native
mapping.

## Evaluation

```python
from worldforge.evaluation import EvaluationSuite

print(EvaluationSuite.builtin_names())

suite = EvaluationSuite.from_builtin("planning")
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
    }
)
report = harness.run(
    ["mock"],
    operations=["predict", "embed"],
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
  local configuration values.
- `WorldStateError`: malformed persisted state or provider-supplied world state that cannot be
  safely restored or applied, including invalid scene-object maps.
- `ProviderError`: provider credentials, transport failures, unsupported provider operations,
  malformed upstream responses, provider-specific input limits, optional dependency failures, and
  malformed model score or policy outputs.

Provider-facing workflows fail before returning partial results:

```python
from worldforge import Action, WorldForge
from worldforge.providers import ProviderError

forge = WorldForge()
world_state = {"step": 0, "scene": {"objects": {}}}

try:
    prediction = forge.predict(
        world_state,
        Action.move_to(0.1, 0.5, 0.0),
        steps=1,
        provider="mock",
    )
except ProviderError as exc:
    # Inspect emitted ProviderEvent records for transport status and attempts.
    raise
```

Important boundary checks:

- `Position`, `Rotation`, request policies, provider events, embeddings, score results, policy
  results, and prediction payload metrics reject non-finite numbers.
- `Action.parameters`, `SceneObject.metadata`, provider-event metadata, score metadata, policy raw
  actions, policy metadata, and prediction payload state/metadata reject non-JSON-native values
  rather than accepting object instances that only fail at persistence time.
- Evaluation and benchmark result objects validate finite metrics, score ranges, coherent counts,
  and JSON-native metrics before JSON, Markdown, or CSV artifacts are rendered.
- Provider-supplied world state rejects scene-object keys that disagree with embedded object IDs.
- LeWorldModel scoring requires `pixels`, `goal`, and `action` info fields, action candidates shaped
  as `(batch=1, samples, horizon, action_dim)`, optional `stable_worldmodel` and `torch` runtime
  dependencies, one returned score per candidate sample, and finite model scores.

# Architecture

WorldForge is a local-first orchestration library for world-model workflows. Its job is not to
declare that every provider means the same thing by "world model." Its job is to expose each
provider through an honest typed capability surface, validate the boundary, and let host
applications compose planning, prediction, generation, evaluation, persistence, and observability.

The current architecture is shaped around LeWorldModel as the first real latent predictive world
model provider. LeWorldModel does not generate videos and does not mutate WorldForge state
directly. It scores action candidates from observations, actions, and goals. WorldForge treats that
as a first-class planning surface instead of forcing it through a fake video or text interface.

## System Map

Repository layout:

```text
worldforge/
|-- src/worldforge/
|   |-- framework.py       # WorldForge facade, World runtime, planning, persistence
|   |-- models.py          # public data contracts and validation
|   |-- providers/
|   |   |-- base.py        # provider interface, ProviderError, PredictionPayload
|   |   |-- mock.py        # deterministic reference provider
|   |   |-- leworldmodel.py# local JEPA cost-model adapter
|   |   |-- cosmos.py      # HTTP video generation adapter
|   |   |-- gr00t.py       # host-owned embodied policy client adapter
|   |   |-- runway.py      # HTTP video generation/transfer adapter
|   |   `-- remote.py      # scaffold adapters for JEPA and Genie
|   |-- observability.py   # ProviderEvent sinks
|   |-- benchmark.py       # provider benchmark harness
|   |-- evaluation/        # built-in suites and report rendering
|   `-- testing/           # reusable provider contract assertions
|-- docs/
|-- examples/
|-- scripts/
`-- tests/
```

Runtime layers:

```text
Host application
  |
  |  Python API / CLI
  v
+-------------------+
| WorldForge facade |
| provider registry |
| diagnostics       |
+---------+---------+
          |
          | owns
          v
+-------------------+
| World runtime     |
| state/history     |
| planning/execution|
+---------+---------+
          |
          | dispatches by capability
          v
+-------------------+       +---------------------------+
| Provider adapter  | ----> | upstream model/API/runtime|
| validation/events | <---- | checkpoint/task/artifact  |
+-------------------+       +---------------------------+
          |
          v
+-------------------+
| typed result      |
| Prediction        |
| VideoClip         |
| ActionScoreResult |
| ActionPolicyResult|
| ReasoningResult   |
+-------------------+
```

Mermaid equivalent:

```mermaid
flowchart TD
    Host[Host app or CLI]
    Forge[WorldForge facade\nregistry, diagnostics, persistence]
    World[World\nstate, history, planning]
    Provider[Provider adapter\ncapability contract]
    Upstream[Upstream runtime or API\nLeWM, GR00T, Cosmos, Runway, mock]
    Models[Typed public models\nPrediction, VideoClip, ActionScoreResult, ActionPolicyResult]
    Obs[ProviderEvent sinks\nlogs, recorder, metrics]
    Store[Local JSON state]

    Host --> Forge
    Forge --> World
    World --> Provider
    Provider --> Upstream
    Upstream --> Provider
    Provider --> Models
    Provider --> Obs
    World --> Store
    Forge --> Store
```

## Module Responsibilities

`framework.py`

- `WorldForge`: top-level object for provider registration, diagnostics, persistence helpers, and
  provider-wide operations such as `generate(...)`, `transfer(...)`, `reason(...)`, `embed(...)`,
  `score_actions(...)`, and `select_actions(...)`.
- `World`: mutable world state with scene objects, history, prediction, comparison, planning, plan
  execution, and evaluation entry points.
- `Prediction`, `Plan`, `PlanExecution`, and `Comparison`: workflow-level result objects.

`models.py`

- Public data contracts such as `Action`, `SceneObject`, `StructuredGoal`, `VideoClip`,
  `ProviderProfile`, `ProviderHealth`, `ProviderEvent`, `ActionScoreResult`, and
  `ActionPolicyResult`.
- Validation helpers and public framework errors: `WorldForgeError` and `WorldStateError`.

`providers/base.py`

- `BaseProvider`, which defines the common capability surface.
- `ProviderError`, the public provider/runtime failure type.
- `PredictionPayload`, the validated payload returned by `predict(...)` implementations.

`providers/leworldmodel.py`

- Optional local adapter for `stable_worldmodel.policy.AutoCostModel`.
- Exposes only `score=True`.
- Validates `pixels`, `goal`, `action`, four-dimensional action candidates, finite cost outputs,
  and `best_index`.

`providers/cosmos.py` and `providers/runway.py`

- Real HTTP adapters with typed request policy, parser boundaries, retry events, and artifact
  validation.

`providers/gr00t.py`

- Experimental host-owned adapter for NVIDIA Isaac GR00T PolicyClient inference.
- Exposes only `policy=True`.
- Requires an explicit action translator because robot actions are embodiment-specific.

`observability.py`

- Host-side provider event composition through `JsonLoggerSink`, `InMemoryRecorderSink`,
  `ProviderMetricsSink`, and `compose_event_handlers(...)`.

`evaluation/` and `benchmark.py`

- Deterministic evaluation suites and capability-aware benchmark reports for adapter comparison.

## End-to-End Pipeline

The shortest accurate pipeline is:

```text
configure providers
  -> create/load a World
  -> choose a workflow
  -> dispatch through a capability-specific provider method
  -> validate provider result
  -> return a typed result
  -> optionally persist, observe, evaluate, or benchmark
```

Expanded:

```text
1. Provider discovery
   - mock registers unconditionally
   - optional providers register only when their env vars are present
   - hosts may call register_provider(...) for custom adapters

2. World setup
   - create_world(...) starts from empty typed state
   - create_world_from_prompt(...) creates a deterministic local seed scene
   - load_world(...) restores local JSON state after validation

3. Workflow call
   - world.predict(...) requires a provider with predict=True
   - forge.generate(...) requires generate=True
   - forge.transfer(...) requires transfer=True
   - forge.select_actions(...) requires policy=True
   - world.plan(...) can use predictive, score-based, policy, or policy+score planning
   - world.evaluate(...) and benchmark harnesses select operations by capability

4. Provider boundary
   - provider receives a JSON world snapshot, media request, query, embedding request, score
     payload, or policy observation
   - adapter validates local inputs before network/model calls when possible
   - provider emits ProviderEvent records for success, failure, and retries where supported

5. Result boundary
   - PredictionPayload updates world state only after validation
   - VideoClip validates media metadata and bytes/source paths
   - ActionScoreResult validates finite scores and an in-range best_index
   - ActionPolicyResult validates executable actions and JSON-compatible raw actions
   - ProviderError surfaces provider/runtime failures with context

6. Host-owned operation
   - JSON persistence is single-writer local storage
   - production logging, metrics export, trace IDs, dashboards, and locks remain host-owned
```

## Provider Injection

There are three injection points.

```text
Construction-time auto-registration

WorldForge(auto_register_remote=True)
  |
  |-- mock              always registered
  |-- cosmos            if COSMOS_BASE_URL is set
  |-- runway            if RUNWAYML_API_SECRET or RUNWAY_API_SECRET is set
  |-- leworldmodel      if LEWORLDMODEL_POLICY or LEWM_POLICY is set
  |-- gr00t             if GROOT_POLICY_HOST is set
  |-- jepa              if JEPA_MODEL_PATH is set
  `-- genie             if GENIE_API_KEY is set
```

```text
Manual registration

forge = WorldForge(auto_register_remote=False)
forge.register_provider(MyProvider(...))
world = forge.create_world("lab", provider="my-provider")
```

```text
Call-site override

world = forge.create_world("lab", provider="mock")

world.predict(action)                         # uses world.provider
world.predict(action, provider="other")       # overrides for this call
world.plan(..., provider="leworldmodel")      # planner/scorer provider
world.execute_plan(plan, provider="mock")     # execution provider
```

Provider lookup is name-based. Provider dispatch is capability-based. A provider should never
advertise a capability unless the corresponding method is implemented end to end.

```mermaid
flowchart LR
    Env[Environment variables] --> Auto[WorldForge auto-registration]
    Custom[Custom adapter instance] --> Manual[register_provider]
    Auto --> Registry[Provider registry]
    Manual --> Registry
    WorldProvider[world.provider default] --> Resolve[provider resolution]
    CallOverride[method provider override] --> Resolve
    PlanExec[Plan metadata execution_provider] --> Resolve
    Registry --> Resolve
    Resolve --> Capability{capability supported?}
    Capability -- yes --> Invoke[call provider method]
    Capability -- no --> Error[WorldForgeError or ProviderError]
```

## Predictive Planning Pipeline

Predictive planning is the older WorldForge path. It is useful for providers that can take a world
state plus an action and return a future world state.

```text
World.plan(goal_spec=..., provider="mock")
  |
  |-- parse goal_spec or goal_json into StructuredGoal
  |-- resolve scene object selectors
  |-- create one or more WorldForge Action objects
  |-- for each action:
  |     provider.predict(simulated_state, action, steps=1)
  |     validate PredictionPayload
  |     append predicted state and physics score
  |
  `-- return Plan(
        planning_mode="predict",
        actions=[...],
        predicted_states=[...],
        success_probability=heuristic average of physics scores
      )
```

Mermaid sequence:

```mermaid
sequenceDiagram
    participant App as Host app
    participant World
    participant Provider
    participant Plan

    App->>World: plan(goal_spec, provider)
    World->>World: normalize StructuredGoal
    loop per action
        World->>Provider: predict(snapshot, action, steps=1)
        Provider-->>World: PredictionPayload
        World->>World: validate and collect predicted state
    end
    World-->>Plan: Plan(planning_mode="predict")
    Plan-->>App: actions + predicted_states
```

## Score-Based Planning Pipeline

Score-based planning is the LeWorldModel-shaped path. It keeps WorldForge-native actions separate
from optional model-native scorer payloads.

```text
Host owns task preprocessing
  |
  |-- score_info
  |     |-- pixels    task-shaped observation history
  |     |-- goal      task-shaped goal observation
  |     `-- action    task-shaped action history
  |
  |-- score_action_candidates (optional)
  |     |-- omitted: WorldForge serializes candidate_actions with Action.to_dict()
  |     `-- provided: tensor or nested numeric array shaped for the score provider
  |
  `-- candidate_actions
        `-- WorldForge Action sequences, one sequence per scored candidate

World.plan(..., provider="leworldmodel", execution_provider="mock")
  |
  |-- require provider.capabilities.score
  |-- call provider.score_actions(info, action_candidates)
  |-- receive ActionScoreResult(scores, best_index, lower_is_better=True)
  |-- choose candidate_actions[best_index]
  |-- return Plan(planning_mode="score", predicted_states=[])

World.execute_plan(plan)
  |
  |-- choose execution_provider from explicit arg or plan metadata
  |-- require execution provider supports predict
  `-- apply selected WorldForge actions through predict(...)
```

The separation is intentional:

- LeWorldModel ranks action tensors in its own task space.
- WorldForge stores and executes `Action` objects in its own public API.
- The host supplies the mapping between those two spaces because task preprocessing is model- and
  checkpoint-specific.
- A score provider is allowed to be a planner without being a predictor, generator, or reasoner.

```mermaid
sequenceDiagram
    participant Host
    participant World
    participant LeWM as LeWorldModelProvider
    participant Exec as Execution Provider

    Host->>World: plan(provider="leworldmodel", candidate_actions, score_info, score_action_candidates)
    World->>World: validate score planning inputs
    World->>LeWM: score_actions(info, action_candidates)
    LeWM->>LeWM: load AutoCostModel, tensorize inputs, get_cost(...)
    LeWM-->>World: ActionScoreResult(best_index)
    World-->>Host: Plan(actions=candidate_actions[best_index], planning_mode="score")
    Host->>World: execute_plan(plan)
    World->>Exec: predict(snapshot, selected action, steps=1)
    Exec-->>World: PredictionPayload
    World-->>Host: PlanExecution(final_world)
```

Concrete score-planning shape:

```python
from worldforge import Action

plan = world.plan(
    goal="select the lowest-cost LeWorldModel candidate",
    provider="leworldmodel",
    planner="leworldmodel-mpc",
    candidate_actions=[
        [Action.move_to(0.1, 0.5, 0.0)],
        [Action.move_to(0.4, 0.5, 0.0)],
    ],
    score_info={
        "pixels": pixels,
        "goal": goal_pixels,
        "action": action_history,
    },
    score_action_candidates=action_candidate_tensor,
    execution_provider="mock",
)

print(plan.metadata["score_result"]["best_index"])
execution = world.execute_plan(plan)
```

## Policy Planning Pipeline

Policy planning is the GR00T-shaped path. It treats a VLA policy as an actor that proposes
executable action chunks from observations and instructions.

```text
policy_info
  |
  |-- observation
  |     |-- video       camera streams or image history
  |     |-- state       proprioception or environment state
  |     `-- language    task instruction
  |
  |-- embodiment_tag
  `-- action_horizon

World.plan(..., provider="gr00t", policy_info=...)
  |
  |-- require provider.capabilities.policy
  |-- call provider.select_actions(info)
  |-- receive ActionPolicyResult(actions, raw_actions, action_candidates)
  |-- return Plan(planning_mode="policy", predicted_states=[])
```

Policy plus score planning composes an actor with a world-model scorer:

```text
GR00T policy provider
  -> proposes one or more candidate action chunks

LeWorldModel / JEPA-WMS score provider
  -> scores serialized policy candidates or a host-supplied model-native candidate tensor

WorldForge
  -> selects policy_candidates[score_result.best_index]
```

Concrete shape:

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

WorldForge passes serialized policy candidates to the score provider by default. Pass
`score_action_candidates=...` when the scorer requires native tensors or latents. The host still
owns the mapping between GR00T raw actions, WorldForge `Action` objects, and score-provider native
payloads. WorldForge validates that each provider returns a typed result and that the selected
candidate index is in range.

## Provider Capability Surface

WorldForge does not ask "is this a world model?" at runtime. It asks which operations a provider
can honestly perform.

```text
BaseProvider
|-- predict(world_state, action, steps) -> PredictionPayload
|-- generate(prompt, duration_seconds, options) -> VideoClip
|-- transfer(clip, width, height, fps, prompt, options) -> VideoClip
|-- reason(query, world_state) -> ReasoningResult
|-- embed(text) -> EmbeddingResult
|-- score_actions(info, action_candidates) -> ActionScoreResult
`-- select_actions(info) -> ActionPolicyResult
```

Current in-repo mapping:

| Provider | Real integration | Primary capability | Runtime kind |
| --- | --- | --- | --- |
| `mock` | yes | predict, generate, reason, embed, plan, transfer | deterministic local surrogate |
| `leworldmodel` | yes | score | local JEPA cost model |
| `gr00t` | yes | policy | host-owned embodied VLA policy client |
| `cosmos` | yes | generate | remote physical-AI video foundation model API |
| `runway` | yes | generate, transfer | remote video generation API |
| `jepa` | scaffold | mock-backed | placeholder for future JEPA provider work |
| `genie` | scaffold | mock-backed | placeholder for future interactive simulator work |

Provider profiles expose the same information through Python and CLI diagnostics. `doctor()` also
includes known but unregistered optional providers by default, so missing local dependencies and
missing credentials show up before a workflow fails.

## Data Contracts

Important public result contracts:

```text
PredictionPayload
  state: JSON object
  confidence: probability
  physics_score: probability
  frames: list[bytes]
  metadata: JSON object
  latency_ms: finite non-negative number

ActionScoreResult
  provider: non-empty string
  scores: non-empty list of finite numbers
  best_index: index into scores
  best_score: scores[best_index]
  lower_is_better: bool
  metadata: JSON object

ActionPolicyResult
  provider: non-empty string
  actions: non-empty list of Action objects
  raw_actions: JSON object
  action_horizon: optional positive integer
  embodiment_tag: optional non-empty string
  metadata: JSON object
  action_candidates: non-empty list of action plans

Plan
  goal: string
  planner: string
  provider: planner/scorer/predictor provider name
  actions: list[Action]
  predicted_states: list[JSON objects]
  success_probability: probability
  metadata: JSON object
```

State invariants:

- persisted worlds contain `id`, `name`, and `provider`
- world `step` is always a non-negative integer
- `scene.objects` is a JSON object keyed by object ID
- embedded scene object IDs must match their map keys
- metadata and history are JSON containers
- invalid public inputs fail explicitly instead of being silently coerced
- score providers return finite scores and an in-range `best_index`
- policy providers return executable actions and preserve raw provider actions
- remote media artifacts reject unsupported content types before returning a `VideoClip`

## Failure Boundaries

WorldForge uses three public failure families:

```text
WorldForgeError
  invalid caller input, unsupported local operation, invalid public model values

WorldStateError
  malformed persisted state or provider-supplied state that cannot be restored

ProviderError
  provider credentials, optional dependency failures, transport failures, malformed upstream
  responses, provider-specific input limits, expired artifacts, invalid downloaded media,
  unsupported provider operations, malformed model outputs
```

Boundary rule:

```text
caller input error     -> fail before provider call when possible
provider/runtime error -> ProviderError with provider-specific context
state mutation         -> only after provider output validates
remote artifact        -> content type and body validated before VideoClip is returned
score output           -> finite scores + valid best_index before Plan is returned
```

## Observability

Provider events are deliberately small. They are not a complete production telemetry stack; they
are the framework-level hook that host applications can fan out to their own logging and metrics.

```text
Provider operation
  |
  |-- ProviderEvent(provider, operation, phase, duration_ms, attempt, status_code, message, metadata)
  |
  `-- host event_handler
        |-- JsonLoggerSink
        |-- InMemoryRecorderSink
        `-- ProviderMetricsSink
```

Example:

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

## Persistence Ownership

Persistence is intentionally host-owned beyond local JSON state.

```text
WorldForge today
  local JSON files
  single-writer assumption
  import/export validation

Host application owns
  locks
  transactions
  database adapters
  object storage
  retention policy
  multi-writer coordination
  production backup/restore
```

This keeps the library small and makes the alpha contract explicit. A future persistence adapter
must preserve the same state validation invariants before it becomes a supported runtime surface.

## Design Implications

- Capability reporting is part of correctness. A provider that only scores must not be presented
  as a generator or predictor.
- LeWorldModel defines the canonical score-planning path: model-native candidate tensors in,
  `ActionScoreResult.best_index` out, WorldForge `Action` sequence selected.
- GR00T defines the first embodied-policy path: multimodal observation in, action chunk out, with
  host-owned translation from embodiment-specific raw actions to WorldForge actions.
- Generative video providers are useful, but video output is not the core abstraction of
  WorldForge.
- Host applications own preprocessing between sensors, robot task tensors, and WorldForge actions.
- The framework should stay strict at boundaries and flexible in provider registration.
- New provider integrations should add tests for every advertised capability and every documented
  failure mode.

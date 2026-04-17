# WorldForge

WorldForge is a Python library for building, persisting, evaluating, and routing world-model workflows behind a typed local-first API.

## Why It Exists

World-model experiments usually start as notebooks and one-off provider scripts. That makes it hard to compare providers, persist state, add tests, or expose a stable interface to downstream code. WorldForge packages those concerns into a small Python framework with:

- deterministic local execution via `MockProvider`
- provider metadata, health checks, and environment diagnostics
- JSON world persistence and history for reproducible workflows
- typed planning goals, comparison helpers, evaluation suites, and provider benchmarks
- adapter contract tests for in-repo and external providers

## Who It Is For

WorldForge is for Python developers building world-model tooling, provider adapters, local evaluation flows, and testable prototypes. It is not an end-user application and it does not ship a hosted control plane.

## World Model Definition

WorldForge uses a narrow, planning-oriented definition of world model: an action-conditioned
predictive model that helps a caller evaluate, rank, or roll out possible futures from
observations, state, actions, and goals. The term is overloaded in the broader market, where it can
also mean video generation, spatial 3D reconstruction, simulation infrastructure, or active
inference systems. WorldForge supports those systems through explicit provider capabilities, but
LeWorldModel is the reference provider shaping the core score-planning architecture.

Embodied policies such as NVIDIA Isaac GR00T are modeled separately as action-policy providers:
they propose robot action chunks from observations and instructions, then can be paired with a
score provider such as LeWorldModel or JEPA-WMS for policy+score planning.

Read [docs/src/world-model-taxonomy.md](./docs/src/world-model-taxonomy.md) for the taxonomy,
[docs/src/architecture.md](./docs/src/architecture.md) for the end-to-end provider pipeline, and
[docs/src/provider-authoring-guide.md](./docs/src/provider-authoring-guide.md) before adding a new
adapter.

## Status

As of 2026-04-17, WorldForge is **alpha**. It is suitable for local development, contract testing, provider adapter prototyping, deterministic evaluation flows, and single-writer JSON persistence. It is not yet suitable for claiming real-world physics fidelity, running unattended production workloads against third-party providers without host-level operational safeguards, or presenting scaffold adapters as fully implemented integrations. Known limitations are listed in [Current limitations](#current-limitations). User-visible changes are tracked in [CHANGELOG.md](./CHANGELOG.md).

## Installation

Application projects:

```bash
uv add worldforge
```

Repository development:

```bash
uv sync --group dev
cp .env.example .env
```

## Quick Start

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

prediction = world.predict(Action.move_to(0.3, 0.8, 0.0), steps=2)
print(prediction.provider, prediction.physics_score)

plan = world.plan(
    goal_spec=StructuredGoal.object_at(
        object_name="red_mug",
        position=Position(0.3, 0.8, 0.0),
    )
)
print(plan.action_count, plan.success_probability)

doctor = forge.doctor()
print(doctor.healthy_provider_count, doctor.provider_count)
```

`StructuredGoal` currently supports `object_at`, `object_near`, `spawn_object`, and
`swap_objects`. Legacy `goal_json` inputs remain supported and are normalized through the
same typed parser.

Provider observability:

```python
import logging

from worldforge import WorldForge
from worldforge.observability import (
    InMemoryRecorderSink,
    JsonLoggerSink,
    ProviderMetricsSink,
    compose_event_handlers,
)

logger = logging.getLogger("demo.worldforge")
metrics = ProviderMetricsSink()
recorder = InMemoryRecorderSink()

forge = WorldForge(
    event_handler=compose_event_handlers(
        JsonLoggerSink(logger=logger, extra_fields={"service": "demo"}),
        metrics,
        recorder,
    )
)
forge.generate("orbiting cube", "mock", duration_seconds=1.0)

print(metrics.get("mock", "generate").to_dict())
print(recorder.snapshot()[0].to_dict())
```

## Core Workflows

Provider diagnostics:

```bash
uv run worldforge doctor
uv run worldforge provider list
uv run worldforge provider info mock
uv run worldforge provider health
```

Prediction and evaluation:

```bash
uv run worldforge predict kitchen --provider mock --x 0.3 --y 0.8 --z 0.0 --steps 2
uv run worldforge eval --suite generation --provider mock
uv run worldforge eval --suite physics --provider mock
uv run worldforge eval --suite planning --provider mock --format json
uv run worldforge eval --suite reasoning --provider mock --format csv
uv run worldforge eval --suite transfer --provider mock
uv run worldforge benchmark --provider mock --iterations 5 --format json
```

Built-in evaluation suites are `generation`, `physics`, `planning`, `reasoning`, and `transfer`. Evaluation and benchmark reports can be exported as Markdown, JSON, or CSV. Provider configuration lives in [.env.example](./.env.example). WorldForge only auto-registers optional providers when their required environment variables are present.

## Architecture

Repository layout:

```text
worldforge/
├── src/worldforge/
│   ├── __init__.py
│   ├── benchmark.py
│   ├── cli.py
│   ├── framework.py
│   ├── models.py
│   ├── observability.py
│   ├── evaluation/
│   ├── providers/
│   └── testing/
├── tests/
├── examples/
├── docs/
├── scripts/
├── AGENTS.md
├── CHANGELOG.md
├── pyproject.toml
└── uv.lock
```

Module responsibilities:

| Module | Responsibility |
| --- | --- |
| `src/worldforge/benchmark.py` | Capability-aware benchmark harness for latency, retry, and throughput measurements |
| `src/worldforge/models.py` | Typed domain models, serialization helpers, and framework-level validation errors |
| `src/worldforge/framework.py` | `WorldForge`, `World`, persistence, planning, prediction, comparison, and diagnostics |
| `src/worldforge/observability.py` | Composable `ProviderEvent` sinks for JSON logging, in-memory recording, and metrics aggregation |
| `src/worldforge/providers/` | Provider primitives plus `mock`, `cosmos`, `runway`, `leworldmodel`, `gr00t`, `lerobot`, `jepa`, and `genie` adapters |
| `src/worldforge/evaluation/` | Built-in evaluation suites and report rendering |
| `src/worldforge/testing/` | Reusable provider contract assertions for adapter packages |
| `tests/` | Framework, CLI, packaging, and adapter regression coverage |

Operational invariants:

- invalid public inputs fail explicitly instead of being silently coerced
- malformed persisted state raises `WorldStateError` with context
- provider adapters must report only capabilities they actually implement
- score-based providers return explicit `ActionScoreResult` objects and must document score semantics
- missing local assets for remote providers fail before the outbound request
- remote adapters expose a typed `ProviderRequestPolicy` for health, request, polling, and download operations
- `WorldForge(event_handler=...)` propagates a single provider event callback, including composed observability sinks, to builtin and manually registered providers
- retryable read operations are retried with backoff; mutation requests stay single-attempt by default
- remote HTTP adapters emit structured `ProviderEvent` records for `retry`, `success`, and `failure`
- `ProviderMetricsSink.request_count` tracks emitted request attempts, so retry events increment both `request_count` and `retry_count`
- `StructuredGoal` provides the typed planning contract for `object_at`, `object_near`, `spawn_object`, and `swap_objects` workflows while legacy `goal_json` remains supported
- `ProviderBenchmarkHarness` measures per-operation latency percentiles, throughput, and emitted retry/error events across registered providers
- local `mock` and scaffold adapters emit structured success events for provider operations
- the deterministic mock path remains available for local tests and examples

More detail lives in [docs/src/world-model-taxonomy.md](./docs/src/world-model-taxonomy.md), [docs/src/architecture.md](./docs/src/architecture.md), [docs/src/provider-authoring-guide.md](./docs/src/provider-authoring-guide.md), [docs/src/providers/README.md](./docs/src/providers/README.md), and [docs/src/operations.md](./docs/src/operations.md).

## Provider Matrix

| Provider | Status | Registration rule | Notes |
| --- | --- | --- | --- |
| `mock` | stable | always registered | deterministic local provider used by tests, examples, and contract checks |
| `cosmos` | beta | auto-registers when `COSMOS_BASE_URL` is set | real HTTP adapter for Cosmos NIM; optionally sends `NVIDIA_API_KEY` |
| `runway` | beta | auto-registers when `RUNWAYML_API_SECRET` or `RUNWAY_API_SECRET` is set | real HTTP adapter for Runway image-to-video and video-to-video APIs |
| `leworldmodel` | beta | auto-registers when `LEWORLDMODEL_POLICY` or `LEWM_POLICY` is set | real optional adapter for LeWorldModel JEPA cost models via `stable_worldmodel.policy.AutoCostModel`; scores action candidates with lower cost as better |
| `gr00t` | experimental | auto-registers when `GROOT_POLICY_HOST` is set | host-owned NVIDIA Isaac GR00T PolicyClient adapter for embodied action selection; exposes `policy`, not predictive world-model capabilities |
| `lerobot` | beta | auto-registers when `LEROBOT_POLICY_PATH` or `LEROBOT_POLICY` is set | host-owned Hugging Face LeRobot `PreTrainedPolicy` adapter for embodied action selection (ACT, Diffusion, TDMPC, VQBet, Pi0, SmolVLA, ...); exposes `policy` |
| `jepa` | scaffold | auto-registers when `JEPA_MODEL_PATH` is set | credential-gated stub backed by deterministic mock behavior |
| `genie` | scaffold | auto-registers when `GENIE_API_KEY` is set | credential-gated stub backed by deterministic mock behavior |

Provider candidate scaffolds are kept outside package exports and auto-registration until they have
a real runtime adapter. The current candidate is [`jepa-wms`](./docs/src/providers/jepa-wms.md), a
local fake-runtime and host-owned torch-hub contract scaffold for future `facebookresearch/jepa-wms`
score-provider work.

LeWorldModel is a local optional integration. Install the upstream runtime in the host
environment, place checkpoints under `$STABLEWM_HOME` or set `LEWORLDMODEL_CACHE_DIR`, then set
`LEWORLDMODEL_POLICY` to the checkpoint run name without the `_object.ckpt` suffix, for example
`pusht/lewm`. The adapter expects tensors or nested numeric arrays that already match the
checkpoint's task preprocessing contract; WorldForge does not infer raw-image transforms.
Use `scripts/smoke_leworldmodel.py` from an isolated environment with the upstream
`stable-worldmodel[train,env]` runtime to download the public `quentinll/lewm-pusht` weights,
prepare the object checkpoint, and run a real `score_actions(...)` smoke.

Run the smoke script with Python, not `sh` or `bash`:

```bash
uv venv --python=3.10 .venv-lewm
source .venv-lewm/bin/activate
uv pip install -e .
uv pip install "stable-worldmodel[train,env]"

python scripts/smoke_leworldmodel.py \
  --stablewm-home ~/.stable-wm \
  --policy pusht/lewm \
  --device cpu
```

The upstream LeWorldModel README uses Python 3.10, installs `stable-worldmodel[train,env]`, and
expects `$STABLEWM_HOME` to default to `~/.stable-wm`. If you already have checkpoints elsewhere,
pass `--cache-dir /path/to/checkpoint-root` or set `LEWORLDMODEL_CACHE_DIR`.

For a checkout-safe end-to-end walkthrough that does not need torch or checkpoints, run
`uv run python examples/leworldmodel_e2e_demo.py`. It injects a tiny deterministic
LeWorldModel-compatible cost runtime, then demonstrates provider registration, candidate scoring,
score-based planning, mock execution, JSON persistence, and reload through the real WorldForge API.
This demo uses the real `LeWorldModelProvider` and `World.plan(... planning_mode="score")`
pipeline, but it does **not** load Lucas Maes' upstream LeWorldModel checkpoint or run neural
inference. Use `scripts/smoke_leworldmodel.py` for the real-checkpoint path.

Concretely, the demo:

1. Registers the real `LeWorldModelProvider` next to the local `mock` execution provider.
2. Creates a small world with one `blue_cube` and an `object_at` goal.
3. Builds three two-step candidate action plans and matching LeWorldModel-shaped
   `(batch, samples, horizon, action_dim)` action tensors.
4. Calls `WorldForge.score_actions("leworldmodel", ...)`, which validates and tensorizes the
   payload before calling the injected runtime's `get_cost(...)` method under eval/no-grad mode.
5. Calls `World.plan(..., provider="leworldmodel", planning_mode="score")`, which selects the
   candidate with the lowest LeWorldModel cost.
6. Executes the selected WorldForge actions through `execution_provider="mock"`, saves the final
   world, reloads it from disk, and reports the final cube position.

The demo's `predicted_states` list is empty by design: a score provider ranks candidate futures;
it does not mutate the world or emit generated video/world-state rollouts. Execution remains a
separate provider step.

LeRobot is a host-owned live policy integration. Install
[`lerobot`](https://github.com/huggingface/lerobot) in the host environment and set
`LEROBOT_POLICY_PATH` (or `LEROBOT_POLICY`) to a Hugging Face repo id or local checkpoint
directory, for example `lerobot/act_aloha_sim_transfer_cube_human`. LeRobot is an
action-policy provider: observations (state, camera images, task language) go in, raw robot
action tensors come out. WorldForge cannot infer what those tensors mean for a given robot, so
a host-supplied `action_translator` maps them into WorldForge `Action` objects. The adapter
lazily imports `lerobot.policies.pretrained.PreTrainedPolicy` only when a non-injected policy
is loaded, so a clean WorldForge install does not pull in LeRobot, PyTorch, or robot runtime
dependencies.

For a checkout-safe end-to-end walkthrough that does not need `lerobot` or checkpoints, run
`uv run python examples/lerobot_e2e_demo.py`. It wires the real `LeRobotPolicyProvider` to a
deterministic fake policy, then demonstrates provider registration, candidate action
proposal, score-based candidate selection, mock execution, JSON persistence, and reload
through the real WorldForge policy+score planning pipeline. Use
`scripts/smoke_lerobot_policy.py` for the real-checkpoint path.

Concretely, the demo:

1. Registers the real `LeRobotPolicyProvider` next to the local `mock` execution provider and
   a tiny deterministic distance-to-goal score provider.
2. Creates a small world with one `blue_cube` and an `object_at` goal.
3. Calls `WorldForge.select_actions("lerobot", info=...)` to get three candidate two-step
   action chunks from the injected policy through the host-supplied translator.
4. Calls `World.plan(..., policy_provider="lerobot", score_provider=..., policy_info=...)`,
   which ranks the policy's candidates by distance to the goal and picks the best one.
5. Executes the selected WorldForge actions through `execution_provider="mock"`, saves the
   final world, reloads it from disk, and reports the final cube position.

```bash
uv run python examples/lerobot_e2e_demo.py
```

Real-checkpoint path:

```bash
uv venv --python=3.10 .venv-lerobot
source .venv-lerobot/bin/activate
uv pip install -e .
uv pip install "lerobot[aloha]"

python scripts/smoke_lerobot_policy.py \
  --policy-path lerobot/act_aloha_sim_transfer_cube_human \
  --observation-module /path/to/obs.py:build_observation \
  --translator /path/to/translator.py:translate_actions \
  --device cpu
```

GR00T is a host-owned live policy integration. Run `scripts/smoke_gr00t_policy.py` from an
environment that can import Isaac-GR00T and reach a policy server. The script can launch
`gr00t/eval/run_gr00t_server.py` from a local Isaac-GR00T checkout with `--start-server`, but the
host must supply real policy observations and an embodiment-specific action translator.
The latest local smoke attempt on macOS arm64 could not run the upstream server because
Isaac-GR00T's dependency resolver pulled CUDA/TensorRT packages, including `tensorrt-cu13-libs`,
that require an NVIDIA/Linux-style runtime.

## Development

Primary commands:

```bash
uv sync --group dev
uv run ruff check src tests examples scripts
uv run ruff format --check src tests examples scripts
uv run pytest
uv run pytest --cov=src/worldforge --cov-report=term-missing --cov-fail-under=90
bash scripts/test_package.sh
```

Package validation builds a wheel in an isolated virtual environment and reruns the root test suite against the installed artifact.

Provider scaffolding:

```bash
uv run python scripts/scaffold_provider.py "Acme WM" \
  --taxonomy "JEPA latent predictive world model" \
  --planned-capability score
```

The scaffold starts safe: it creates adapter, fixture, test, and docs-stub files without
advertising public capabilities until the implementation is complete.

Contribution guidance:

- keep the public API typed and Pythonic
- use `ProviderError` for provider failures and `WorldForgeError` / `WorldStateError` for invalid caller input or malformed state
- do not advertise provider capabilities that are not implemented end to end
- add a regression test for every bug fix and every documented failure mode
- update docs, changelog, and agent context when the public contract changes

See [CONTRIBUTING.md](./CONTRIBUTING.md) for contributor workflow details.
See [AGENTS.md](./AGENTS.md) for repository context used by AI-assisted and first-time contributors.

## Current Limitations

- Planning still supports heuristic goal strings, but structured goals are now typed and validated through `StructuredGoal`, including relocation, neighbor placement, spawn, and swap workflows.
- Evaluation remains a deterministic harness; the built-in suites now cover generation, transfer, physics, planning, and reasoning baselines.
- `jepa` and `genie` are scaffold adapters and should not be treated as production integrations.
- `leworldmodel` is a real optional cost-model adapter, but callers must install
  `stable-worldmodel[env]`, provide compatible checkpoints, and pass task-shaped pixel/action/goal
  tensors; it does not generate videos or reason over text.
- `gr00t` is a real optional policy-client adapter, but live execution requires a host-owned
  Isaac-GR00T runtime, reachable policy server, compatible NVIDIA CUDA/TensorRT environment when
  launching the upstream server, real observations, and an embodiment-specific action translator.
- `lerobot` is a real optional policy-client adapter, but live execution requires `lerobot`
  and its robot or simulation dependencies installed in the host environment, a Hugging Face
  repo id or local checkpoint path, real observations, and an embodiment-specific action
  translator. The adapter never drives hardware; it only evaluates the policy.
- Remote provider health checks depend on live credentials and network reachability even though they now use typed timeout and retry policy.
- Provider observability includes local JSON logging and in-memory metrics sinks, but host applications still own production logging, metrics export, trace IDs, dashboards, and alerts.
- World persistence is local JSON state, not a concurrent multi-writer store or service.
- Benchmarks focus on operation latency, retries, and throughput; they are not a distributed load-test or content-fidelity system.

## Roadmap

1. Provider hardening.
Exit criteria: remote adapters validate upstream success and failure schemas, expose richer operator-facing error context, document provider-specific limits, and ship fixture-driven non-happy-path coverage for malformed payloads, partial outputs, expired artifacts, bad content types, and transport retries.

2. Planner and evaluator maturity.
Exit criteria: structured planning grows beyond the current `object_at` / `object_near` / `spawn_object` / `swap_objects` goal set, evaluation scoring gets less heuristic, benchmark fixtures expand beyond the synthetic seed clip, and every scoring assumption is documented.

3. Release discipline.
Exit criteria: docs stay in lockstep with tags, the changelog is maintained for every user-visible change, and the first release-candidate criteria are documented with explicit production blockers.

Current release-candidate criteria and persistence decisions are documented in [docs/src/operations.md](./docs/src/operations.md).

## Help

- Issues: <https://github.com/AbdelStark/worldforge/issues>
- Repository: <https://github.com/AbdelStark/worldforge>
- Documentation: <https://docs.worldforge.ai>

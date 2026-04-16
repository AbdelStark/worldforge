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

## Status

As of 2026-04-16, WorldForge is **alpha**. It is suitable for local development, contract testing, provider adapter prototyping, deterministic evaluation flows, and single-writer JSON persistence. It is not yet suitable for claiming real-world physics fidelity, running unattended production workloads against third-party providers without host-level operational safeguards, or presenting scaffold adapters as fully implemented integrations. Known limitations are listed in [Current limitations](#current-limitations). User-visible changes are tracked in [CHANGELOG.md](./CHANGELOG.md).

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
| `src/worldforge/providers/` | Provider primitives plus `mock`, `cosmos`, `runway`, `leworldmodel`, `jepa`, and `genie` adapters |
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

More detail lives in [docs/src/architecture.md](./docs/src/architecture.md), [docs/src/providers/README.md](./docs/src/providers/README.md), and [docs/src/operations.md](./docs/src/operations.md).

## Provider Matrix

| Provider | Status | Registration rule | Notes |
| --- | --- | --- | --- |
| `mock` | stable | always registered | deterministic local provider used by tests, examples, and contract checks |
| `cosmos` | beta | auto-registers when `COSMOS_BASE_URL` is set | real HTTP adapter for Cosmos NIM; optionally sends `NVIDIA_API_KEY` |
| `runway` | beta | auto-registers when `RUNWAYML_API_SECRET` or `RUNWAY_API_SECRET` is set | real HTTP adapter for Runway image-to-video and video-to-video APIs |
| `leworldmodel` | beta | auto-registers when `LEWORLDMODEL_POLICY` or `LEWM_POLICY` is set | real optional adapter for LeWorldModel JEPA cost models via `stable_worldmodel.policy.AutoCostModel`; scores action candidates with lower cost as better |
| `jepa` | scaffold | auto-registers when `JEPA_MODEL_PATH` is set | credential-gated stub backed by deterministic mock behavior |
| `genie` | scaffold | auto-registers when `GENIE_API_KEY` is set | credential-gated stub backed by deterministic mock behavior |

LeWorldModel is a local optional integration. Install the upstream runtime in the host
environment, place checkpoints under `$STABLEWM_HOME` or set `LEWORLDMODEL_CACHE_DIR`, then set
`LEWORLDMODEL_POLICY` to the checkpoint run name without the `_object.ckpt` suffix, for example
`pusht/lewm`. The adapter expects tensors or nested numeric arrays that already match the
checkpoint's task preprocessing contract; WorldForge does not infer raw-image transforms.

## Development

Primary commands:

```bash
uv sync --group dev
uv run ruff check src tests examples
uv run ruff format --check src tests examples
uv run pytest
uv run pytest --cov=src/worldforge --cov-report=term-missing --cov-fail-under=90
bash scripts/test_package.sh
```

Package validation builds a wheel in an isolated virtual environment and reruns the root test suite against the installed artifact.

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

# Architecture

WorldForge follows a standard `src/` layout:

```text
src/worldforge/
├── __init__.py
├── benchmark.py
├── cli.py
├── framework.py
├── models.py
├── observability.py
├── evaluation/
└── providers/
```

## Module responsibilities

### `models.py`

Core domain objects and JSON serialization helpers.

### `benchmark.py`

Capability-aware benchmark harness for provider latency, retries, and throughput.

### `framework.py`

Framework runtime and persistence:

- `WorldForge`
- `World`
- `Prediction`
- `Comparison`
- `Plan`
- import/export and local JSON world storage

### `observability.py`

Composable provider telemetry sinks built on `ProviderEvent`. This module provides
`JsonLoggerSink`, `InMemoryRecorderSink`, `ProviderMetricsSink`, and
`compose_event_handlers(...)` for host-side logging, local debugging, and
lightweight request aggregation.

### `providers/`

Provider primitives and adapters. The mock provider is the reference implementation. `cosmos`
and `runway` are live HTTP adapters. `leworldmodel` is a real optional local adapter for
LeWorldModel JEPA cost-model scoring. `jepa` and `genie` are scaffold adapters.

### `evaluation/`

Evaluation suites, scenario runners, and report rendering.

## Data flow

1. `WorldForge` resolves or registers a provider.
2. `World` snapshots the current state and sends it to the provider.
3. Prediction/generation providers return a `PredictionPayload` or `VideoClip`; score providers
   return an `ActionScoreResult`.
4. The framework validates and applies returned world state when prediction is involved.
5. Optional provider event callbacks receive structured `ProviderEvent` records from local and remote provider operations.
6. Host apps can fan those events out to logging, recording, and metrics sinks through `worldforge.observability.compose_event_handlers(...)`.
7. History, persistence, evaluation, benchmarks, and CLI output are derived from that validated state.

## Invariants

- persisted worlds must contain `id`, `name`, and `provider`
- world `step` is always a non-negative integer
- invalid public inputs fail explicitly instead of being silently coerced
- provider capability metadata must match the implemented surface
- score providers must return finite scores and an in-range `best_index`
- missing local asset files fail before network I/O
- remote provider reads use typed retry/backoff policy; mutation requests default to single-attempt behavior
- forge-level event handlers propagate to builtin providers and to providers later registered at runtime
- `ProviderMetricsSink.request_count` tracks emitted request attempts; retries increment both `request_count` and `retry_count`
- `StructuredGoal` is the typed contract for structured planning inputs, including relocation, neighbor, spawn, and swap goals

## Failure model

- invalid caller input raises `WorldForgeError`
- malformed persisted state raises `WorldStateError`
- provider/runtime integration failures raise `ProviderError`
- remote health checks may fail due to missing credentials, invalid endpoints, or upstream errors
- LeWorldModel health may fail because optional `stable_worldmodel` / `torch` dependencies are
  absent, the policy is unset, or the checkpoint cannot be loaded at scoring time
- remote HTTP adapters share one typed request policy contract for timeout, polling, download, and retry behavior
- provider event callbacks surface structured retry, success, and failure records but do not replace host-level logging or metrics sinks

## Observability example

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

## Design principles

- Python-native API surface
- typed public models
- simple JSON persistence
- honest provider capability reporting
- deterministic local development path
- fail fast on invalid state and invalid inputs

# AGENTS.md

## Project Identity

WorldForge is a Python library for building, persisting, evaluating, and routing world-model workflows behind a typed local-first API.

## Architecture Map

- `src/worldforge/models.py`: domain models, serialization helpers, and framework-level validation errors.
- `src/worldforge/framework.py`: `WorldForge`, `World`, persistence, planning, prediction, comparison, and diagnostics.
- `src/worldforge/observability.py`: composable `ProviderEvent` sinks for JSON logging, in-memory recording, and lightweight metrics aggregation.
- `src/worldforge/providers/`: provider primitives plus the in-repo `mock`, `cosmos`, `runway`, `jepa`, and `genie` adapters.
- `src/worldforge/evaluation/`: built-in evaluation suites and report rendering.
- `src/worldforge/testing/`: reusable provider contract assertions for adapter packages.
- `tests/`: regression coverage for public API, CLI, providers, and packaging behavior.

## Tech Stack

- Python `>=3.10`
- Packaging/build: `uv`, `hatchling`
- HTTP client: `httpx`
- Testing: `pytest`
- Lint/format: `ruff`
- CI: GitHub Actions

## Build And Test Commands

Run these from the repository root:

```bash
uv sync --group dev
uv run ruff check src tests examples
uv run ruff format --check src tests examples
uv run pytest
bash scripts/test_package.sh
uv run pytest --cov=src/worldforge --cov-report=term-missing --cov-fail-under=90
```

## Conventions

- Keep the public API typed and Pythonic.
- Use `ProviderError` for provider/runtime integration failures.
- Use `WorldForgeError` for invalid caller input and `WorldStateError` for malformed persisted state.
- Do not silently coerce invalid public inputs. Reject them with a contextual error.
- Do not advertise provider capabilities that are not implemented end to end.
- Add a regression test for every bug fix and every documented failure mode.
- Keep README, changelog, docs, and this file aligned with the live package surface.

## Critical Constraints

- Do not claim `jepa` or `genie` are production integrations. They are scaffold adapters backed by deterministic mock behavior after credential checks.
- Do not change remote provider auto-registration rules without updating docs and diagnostics.
- Do not reintroduce fallback behavior that turns missing local asset paths into opaque remote strings.
- Do not bypass state validation in persistence or import/export code.

## Gotchas

- Remote providers are only auto-registered when their required environment variables are present.
- `doctor()` includes known providers by default, not just registered providers.
- `scripts/test_package.sh` is the packaging contract check and must keep passing after public API changes.
- Provider health checks may perform live network requests when the relevant provider is configured.
- Remote provider profiles now expose a typed `ProviderRequestPolicy`; read operations retry, mutation operations do not by default.
- `WorldForge(event_handler=...)` propagates to builtin providers and to providers later added with `register_provider()`.
- `worldforge.observability.compose_event_handlers(...)` is the supported way to attach multiple sinks without writing a custom dispatcher.
- Remote adapters emit `ProviderEvent` records for retry, success, and failure. Mock-backed paths emit success events only.
- `ProviderMetricsSink.request_count` counts emitted request attempts, so retries increment both `request_count` and `retry_count`.

## Observability Example

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

## Current State

As of 2026-04-08, the project is alpha.

- Stable path: local `mock` provider, persistence, CLI, contract tests, built-in evaluation flow, and provider telemetry sinks.
- Beta path: `cosmos` and `runway` HTTP adapters.
- Scaffold path: `jepa` and `genie`.
- Known gaps: heuristic planner, limited evaluation suite coverage, no benchmark/load-test harness yet, and no built-in exporter integration for OpenTelemetry or Prometheus yet.

# Agent Guide

## Project Identity

WorldForge is an alpha-stage Python library for building, persisting, evaluating, and routing
world-model workflows behind a typed local-first API. It is a library and CLI, not a hosted
service, on-chain contract, or end-user application.

Intended users are Python developers building provider adapters, local world-model experiments,
evaluation harnesses, and testable prototypes.

## Architecture Map

- `src/worldforge/models.py`: domain models, serialization helpers, validation errors, request
  policies, provider metadata, media/result types, and structured planning goals.
- `src/worldforge/framework.py`: `WorldForge`, `World`, persistence, planning, prediction,
  comparison, diagnostics, and top-level evaluation helpers.
- `src/worldforge/providers/base.py`: provider interfaces, `ProviderError`, remote-provider
  base behavior, and `PredictionPayload`.
- `src/worldforge/providers/mock.py`: deterministic local provider used by tests, examples, and
  contract checks.
- `src/worldforge/providers/cosmos.py` and `runway.py`: real HTTP adapters with typed timeout,
  retry, polling, download policies, and response parsers.
- `src/worldforge/providers/leworldmodel.py`: real optional LeWorldModel JEPA cost-model adapter
  for scoring action candidates through `stable_worldmodel.policy.AutoCostModel`.
- `src/worldforge/providers/remote.py`: credential-gated scaffold providers for `jepa` and
  `genie`; these intentionally use deterministic mock behavior after credential checks.
- `src/worldforge/evaluation/`: built-in generation, physics, planning, reasoning, and transfer
  suites plus report renderers.
- `src/worldforge/benchmark.py`: capability-aware provider latency, retry, and throughput harness.
- `src/worldforge/observability.py`: composable `ProviderEvent` sinks for JSON logging, in-memory
  recording, and metrics aggregation.
- `src/worldforge/testing/`: reusable adapter contract helpers.

## Tech Stack

- Python `>=3.10`, tested in CI on Python 3.10, 3.11, 3.12, and 3.13.
- Packaging/build: `hatchling`, `uv`, `uv.lock`.
- Runtime dependency: `httpx`.
- Optional LeWorldModel runtime: `stable-worldmodel[env]` and `torch`, supplied by the host
  environment only when using `leworldmodel`.
- Development tools: `pytest`, `pytest-cov`, `ruff`, `pip-audit` in CI.
- License: MIT.

## Commands

Run these from the repository root:

```bash
uv sync --group dev
uv lock --check
uv run ruff check src tests examples scripts
uv run ruff format --check src tests examples scripts
uv run pytest
uv run pytest --cov=src/worldforge --cov-report=term-missing --cov-fail-under=90
bash scripts/test_package.sh
```

Local security audit:

```bash
tmp_req="$(mktemp requirements-audit.XXXXXX)"
uv export --frozen --all-groups --no-emit-project --no-hashes -o "$tmp_req" >/dev/null
uvx --from pip-audit pip-audit -r "$tmp_req" --no-deps --disable-pip --progress-spinner off
rm -f "$tmp_req"
```

## Conventions

- Public inputs fail explicitly with `WorldForgeError`; malformed persisted/provider state fails
  with `WorldStateError`; provider/runtime integration failures fail with `ProviderError`.
- Provider capabilities must only advertise operations that are implemented end to end.
- `leworldmodel` exposes `score`, not `predict`, `generate`, or `reason`; do not fake those
  capabilities around a cost model.
- Remote create/mutation requests are single-attempt by default; health, polling, and downloads
  use retry/backoff policy.
- Keep public API models typed and serializable. Validate boundary values before persistence or
  outbound network I/O.
- Add regression tests for every bug fix and every documented failure mode.
- Put remote provider payload fixtures under `tests/fixtures/providers/` and assert both parser
  errors and public provider errors.
- Update README, docs, changelog, and this file when public behavior changes.

## Critical Constraints

- Do not replace scaffold providers with claims of real JEPA/Genie integration; they are
  credential-gated mock-backed adapters until real provider behavior is implemented.
- Do not add `stable_worldmodel`, `torch`, checkpoint archives, or downloaded datasets to the base
  dependency set or repository. Keep LeWorldModel optional and host-owned.
- Do not auto-register optional providers unless their required environment variables are present.
- Do not add hardcoded credentials, test secrets, or environment-specific endpoints.
- Do not weaken coverage gates or remove package validation from CI.
- Do not silently coerce invalid world state. A loud failure is preferable to persisted
  incoherence.

## Gotchas

- `WorldForge.doctor()` includes known unregistered providers by default so missing remote
  configuration appears as diagnostics.
- `ProviderMetricsSink.request_count` counts emitted provider events, not necessarily logical
  user-level operations; retry events increment both `request_count` and `retry_count`.
- World persistence is local JSON under `.worldforge/worlds` by default and is not a concurrent
  multi-writer store.
- Persistence is host-owned for the Provider Hardening RC; do not add a lock file, SQLite store,
  or service adapter without an explicit design.
- Built-in evaluation suites are deterministic contract harnesses, not claims of physical or
  media-quality fidelity.
- LeWorldModel expects preprocessed pixel/action/goal tensors or rectangular nested numeric
  arrays shaped for the configured checkpoint. WorldForge validates the adapter boundary but does
  not infer task-specific image transforms.
- `scripts/smoke_leworldmodel.py` is an optional real-checkpoint smoke. Run it from an isolated
  Python 3.10 environment with the upstream GitHub `stable-worldmodel[train,env]` runtime; do not
  add those dependencies to WorldForge's base package.
- `RUNWAYML_API_SECRET` is preferred, but `RUNWAY_API_SECRET` remains supported as a legacy alias.

## Current State

As of 2026-04-16, WorldForge is alpha. It is suitable for local development, adapter contract
testing, deterministic evaluation, and provider-prototype workflows. It is not suitable for
unattended production operation against third-party providers without host-level monitoring,
credential management, persistence strategy, and operational safeguards.

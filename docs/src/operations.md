# Operations

WorldForge is a Python library plus CLI. Operational responsibility lives in the host application
that imports it. This page documents the runtime assumptions and minimum runbook for teams using
WorldForge in services, jobs, or provider-evaluation pipelines.

## Configuration

Configuration comes from constructor arguments and environment variables documented in
`.env.example`.

- `COSMOS_BASE_URL` enables the Cosmos adapter.
- `NVIDIA_API_KEY` is optional bearer auth for Cosmos.
- `RUNWAYML_API_SECRET` enables the Runway adapter.
- `RUNWAY_API_SECRET` remains supported as the legacy Runway alias.
- `RUNWAYML_BASE_URL` overrides the default Runway API endpoint.
- `JEPA_MODEL_PATH` and `GENIE_API_KEY` enable scaffold adapters only.

Validate configuration at startup with:

```bash
uv run worldforge doctor --registered-only
uv run worldforge provider health
```

## Persistence

World state is persisted as local JSON under `.worldforge/worlds` by default or under the
`state_dir` passed to `WorldForge`.

This store is suitable for local development, tests, examples, and single-writer workflows. It is
not a concurrent database. Services that need multi-writer persistence should store exported world
payloads in their own database and apply their own locking, backup, and retention policy.

Persistence decision for the Provider Hardening RC: persistence remains explicitly host-owned.
WorldForge will continue to provide deterministic local JSON import/export and validation, but it
will not add a library-owned lock file, SQLite store, or network database adapter in this milestone.
The reason is boundary clarity: host applications already own deployment topology, durability,
locking semantics, backup policy, and retention requirements. WorldForge should not imply
production durability guarantees that a local JSON store cannot enforce.

Release-candidate exit criteria for persistence:

- Local JSON imports reject malformed scene object IDs, non-object state payloads, invalid
  metadata, invalid history, and negative steps.
- README and operations docs state that multi-writer persistence is host-owned.
- Any future built-in persistence backend must be introduced as an explicit adapter with its own
  locking, migration, and recovery documentation.

## Observability

Attach a provider event handler at `WorldForge(event_handler=...)` or provider construction time.
Use `compose_event_handlers(...)` to fan out events to:

- `JsonLoggerSink` for structured JSON logs.
- `ProviderMetricsSink` for request, retry, error, and latency aggregates.
- `InMemoryRecorderSink` for tests and local debugging.

Host services should add request or trace IDs through `JsonLoggerSink(extra_fields=...)` and
include those IDs in surrounding application logs.

## Failure Modes

- Invalid caller input raises `WorldForgeError`.
- Malformed persisted or provider-supplied state raises `WorldStateError`.
- Provider runtime, transport, credential, and upstream failures raise `ProviderError`.
- Missing remote credentials leave the provider unregistered unless inspected through
  `doctor()`.
- Remote create-style requests are single-attempt by default; health checks, polling, and
  downloads retry according to `ProviderRequestPolicy`.
- Cosmos and Runway validate typed upstream response payloads before creating returned media
  objects.
- Runway artifact downloads fail explicitly on expired/unavailable URLs, empty downloads, and
  explicit unsupported content types.

## Recovery

- For local state corruption, restore from the host application's backup of exported world JSON.
- For missing credentials, fix the environment and restart the host process so provider
  auto-registration runs again.
- For transient remote failures, inspect emitted `ProviderEvent` records for `operation`,
  `phase`, `status_code`, `attempt`, and `target`.
- For expired Runway artifact URLs, regenerate or persist downloaded outputs immediately after
  task completion.

## Release Checklist

Before publishing a release:

```bash
uv lock --check
uv run ruff check src tests examples
uv run ruff format --check src tests examples
uv run pytest --cov=src/worldforge --cov-report=term-missing --cov-fail-under=90
bash scripts/test_package.sh
```

Also update `CHANGELOG.md`, README status, and provider documentation for any public behavior
change.

## Provider Hardening RC Exit Criteria

- Cosmos and Runway response parsers cover success and malformed upstream payloads with fixture
  tests.
- Remote provider non-happy-path tests cover transport retries, malformed JSON, missing task IDs,
  failed tasks, partial outputs, expired artifacts, bad artifact content types, and provider
  limits.
- Persistence remains documented as host-owned unless a dedicated persistence adapter is designed.
- API documentation lists the public exception families and provider workflow failure modes.
- Remaining work is tracked in GitHub issues with severity labels and measurable exit criteria.

Tracked RC issues:

- [#11 Provider Hardening RC: expand upstream response contract fixtures](https://github.com/AbdelStark/worldforge-backup/issues/11)
- [#12 Provider Hardening RC: document and gate host-owned persistence](https://github.com/AbdelStark/worldforge-backup/issues/12)
- [#13 Planner and evaluator maturity: move beyond deterministic contract checks](https://github.com/AbdelStark/worldforge-backup/issues/13)
- [#14 Release discipline: define first RC checklist and gating policy](https://github.com/AbdelStark/worldforge-backup/issues/14)
- [#15 Provider Hardening RC: complete API failure-mode reference](https://github.com/AbdelStark/worldforge-backup/issues/15)

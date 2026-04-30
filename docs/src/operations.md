# Operations

WorldForge is a Python library plus CLI. Operational responsibility lives in the host application
that imports it. This page documents the runtime assumptions and minimum runbook for developers using
WorldForge in services, jobs, or provider-evaluation pipelines.

For task-specific runbooks, use [User And Operator Playbooks](./playbooks.md). That page covers
clean checkout validation, provider availability, adapter promotion, persistence recovery, remote
artifact handling, optional runtime smokes, benchmarks, and release gates.

## Operational Modes

| Mode | Suitable use | Boundary |
| --- | --- | --- |
| local development | examples, unit tests, adapter prototyping, deterministic demos | `mock` provider and local JSON state |
| provider evaluation job | fixture-backed provider checks, benchmarks, optional runtime smokes | host owns credentials, checkpoints, outputs, and run artifacts |
| embedded service/library use | application calls WorldForge APIs inside a larger system | host owns request IDs, telemetry export, persistence, retries around jobs, and alerts |
| real robot or simulator loop | host supplies policy observations and action translators | host owns safety interlocks, controller semantics, and embodiment-specific execution |

Minimum startup preflight for a host process:

```bash
uv run worldforge doctor --registered-only
uv run worldforge provider health
```

## Health And Readiness

Host applications should expose liveness separately from readiness. Liveness answers whether the
service process can handle an HTTP request. Readiness answers whether the specific provider-backed
workflow should receive traffic.

The stdlib reference host in `examples/hosts/service/app.py` uses this model:

| State | Source | Meaning | Typical HTTP endpoint |
| --- | --- | --- | --- |
| process live | service handler returns `{"status": "live"}` | process and web stack are running | `GET /healthz` |
| framework alive | `WorldForge(...)` can be constructed and `doctor()` can run | library import, local state path, and provider registry are usable | `GET /readyz` |
| provider configured | provider appears in `forge.providers()` | required env vars or host injection registered the provider | `GET /readyz` |
| provider healthy | `forge.provider_health(name).healthy` is true | provider's cheap health check passed | `GET /readyz` |
| workflow failing | provider is configured and health may pass, but a workflow returns a typed error | request input, upstream response, budget, or artifact handling failed | workflow response body |

The reference host returns one of these readiness statuses from `GET /readyz`:

| `/readyz` status | Traffic decision | How to interpret it |
| --- | --- | --- |
| `ready` | accept | framework is alive, the selected provider is registered, and provider health passed. |
| `provider_unconfigured` | drain | framework is alive, but the selected provider is not registered in this process. |
| `provider_unhealthy` | drain | provider is registered, but its health check reports missing optional runtime, bad credentials, unreachable upstream, or another provider-owned failure detail. |

Map CLI diagnostics the same way during incidents:

| Command | Readiness signal |
| --- | --- |
| `uv run worldforge doctor --registered-only` | registered provider count, health count, and local configuration issues. |
| `uv run worldforge doctor --capability <capability>` | whether any known provider can satisfy the requested surface. |
| `uv run worldforge provider health <name>` | provider-specific configured/healthy details. |
| `uv run worldforge provider info <name>` | redacted config summary plus profile, capability, and health. |

WorldForge reports local provider state and adapter errors. It does not own upstream provider SLAs,
deployment load balancers, alert channels, retry orchestration outside one provider call, or
credential rotation.

## Configuration

Configuration comes from constructor arguments and environment variables documented in
`.env.example`.

- `COSMOS_BASE_URL` enables the Cosmos adapter.
- `NVIDIA_API_KEY` is optional bearer auth for Cosmos.
- `RUNWAYML_API_SECRET` enables the Runway adapter.
- `RUNWAY_API_SECRET` remains supported as the legacy Runway alias.
- `RUNWAYML_BASE_URL` overrides the default Runway API endpoint.
- `LEWORLDMODEL_POLICY` or `LEWM_POLICY` enables the optional LeWorldModel adapter.
- `LEWORLDMODEL_CACHE_DIR` overrides the LeWorldModel checkpoint root.
- `LEWORLDMODEL_DEVICE` selects the optional torch device for LeWorldModel scoring.
- `GROOT_POLICY_HOST` enables the optional GR00T embodied-policy adapter.
- `GROOT_POLICY_PORT` defaults to `5555`.
- `GROOT_POLICY_TIMEOUT_MS` defaults to `15000`.
- `GROOT_POLICY_API_TOKEN`, `GROOT_POLICY_STRICT`, and `GROOT_EMBODIMENT_TAG` are optional GR00T
  PolicyClient settings.
- `LEROBOT_POLICY_PATH` or `LEROBOT_POLICY` enables the optional LeRobot embodied-policy adapter.
- `LEROBOT_POLICY_TYPE`, `LEROBOT_DEVICE`, `LEROBOT_CACHE_DIR`, and `LEROBOT_EMBODIMENT_TAG` are
  optional LeRobot settings.
- `JEPA_MODEL_PATH` and `GENIE_API_KEY` only register capability-closed scaffold reservations.
- `WORLDFORGE_ENABLE_SCAFFOLD_SURROGATES=1` is for local scaffold adapter tests only; it does not
  make JEPA or Genie real provider integrations.

Validate configuration when the host process starts:

```bash
uv run worldforge doctor --registered-only
uv run worldforge provider health
```

## Persistence

World state is persisted as local JSON under `.worldforge/worlds` by default or under the
`state_dir` passed to `WorldForge`.

The same local store is available from the CLI for checkout jobs and operator handoffs:

```bash
uv run worldforge world create lab --provider mock
uv run worldforge world add-object <world-id> cube --x 0 --y 0.5 --z 0 --object-id cube-1
uv run worldforge world update-object <world-id> cube-1 --x 0.2 --y 0.5 --z 0
uv run worldforge world predict <world-id> --object-id cube-1 --x 0.4 --y 0.5 --z 0
uv run worldforge world list
uv run worldforge world objects <world-id>
uv run worldforge world history <world-id>
uv run worldforge world export <world-id> --output world.json
uv run worldforge world import world.json --new-id --name lab-copy
uv run worldforge world fork <world-id> --history-index 0 --name lab-start
uv run worldforge world delete <world-id>
```

This store is suitable for local development, tests, examples, and single-writer workflows. It is
not a concurrent database. Services that need multi-writer persistence should store exported world
payloads in their own database and apply their own locking, backup, and retention policy.

Persistence remains explicitly host-owned beyond local JSON import/export. The reason is boundary
clarity: host applications own deployment topology, durability, locking semantics, backup policy,
and retention requirements. WorldForge should not imply production durability guarantees that a
local JSON store cannot enforce.

Supported persistence invariants:

- World IDs are validated as file-safe local storage identifiers before any read or write. Path
  separators, traversal-shaped IDs, empty strings, and non-string IDs are rejected.
- CLI object mutations and persisted predictions load the world, apply typed `SceneObject`,
  `SceneObjectPatch`, or `Action` values, append typed history entries, and write through
  `save_world(...)`.
- Position patches translate the object's bounding box with the pose so local scene edits do not
  leave stale spatial bounds in persisted snapshots.
- `world predict` saves the provider-updated world unless `--dry-run` is supplied.
- `delete_world(...)` and `world delete` validate the world id before unlinking local JSON and fail
  loudly when the requested world is already absent.
- Local JSON imports reject malformed scene object IDs, non-object state payloads, invalid
  metadata, invalid history, negative steps, history entries from future steps, empty history
  summaries, malformed serialized actions, and invalid historical snapshot states.
- `save_world(...)` validates the serialized world before writing and replaces the destination file
  atomically through a temporary file in the same directory.
- README and operations docs state that multi-writer persistence is host-owned.
- Any future built-in persistence backend must be introduced as an explicit adapter with its own
  locking, migration, and recovery documentation.

## Observability

Attach a provider event handler at `WorldForge(event_handler=...)` or provider construction time.
Use `compose_event_handlers(...)` to fan out events to:

- `JsonLoggerSink` for structured JSON logs.
- `RunJsonLogSink` for newline-delimited JSON files tied to one run id.
- `ProviderMetricsSink` for request, retry, error, and latency aggregates.
- `ProviderMetricsExporterSink` for optional host-owned counters and latency histograms.
- `OpenTelemetryProviderEventSink` for optional host-owned tracing spans.
- `InMemoryRecorderSink` for tests and local debugging.
- `RerunEventSink` for optional Rerun recordings of provider events.

`ProviderEvent` sanitizes observable fields before they reach these sinks: HTTP targets keep
scheme, host, port, and path but drop userinfo, query strings, and fragments; message and metadata
fields redact obvious bearer tokens, API keys, signatures, passwords, and signed URLs. Host
applications should still avoid placing raw credentials in provider exception messages or custom
metadata.

Host services can attach correlation IDs directly to a `ProviderEvent` when the provider adapter
knows them, or through `JsonLoggerSink(extra_fields=...)` when the host owns them outside the
adapter. Optional event fields are `run_id`, `request_id`, `trace_id`, `span_id`, `artifact_id`,
and `input_digest`; they are strings, omitted when unset, and sanitized before sink consumption.
The event `phase` is normalized to lowercase so hosts can filter stable `success`, `failure`,
`retry`, and `budget_exceeded` values.

OpenTelemetry export is optional. Importing `worldforge` does not import OpenTelemetry, and the
base package does not install a collector, SDK, or exporter. Production hosts either install
`opentelemetry-api` and let `OpenTelemetryProviderEventSink()` resolve the current tracer lazily, or
inject their already configured tracer:

```python
from worldforge import WorldForge
from worldforge.observability import OpenTelemetryProviderEventSink

forge = WorldForge(
    event_handler=OpenTelemetryProviderEventSink(
        tracer=host_tracer,
        extra_attributes={"service": "batch-eval"},
    )
)
```

Each provider event becomes one span named
`worldforge.provider.<provider>.<operation>.<phase>`. Span attributes are bounded to provider,
operation, phase, attempt, max attempts, optional duration, optional correlation IDs, HTTP method,
HTTP status code, sanitized target, status class, capability, redacted message, and redacted
metadata JSON. Hosts should not add raw prompts, world IDs, target URLs with query strings, or
high-cardinality business metadata as trace attributes.

Metrics export is also optional and dependency-free. `ProviderMetricsExporterSink` accepts any
host exporter with `increment_counter(...)` and `observe_histogram(...)` methods, so production
services can bridge provider events to Prometheus, OpenTelemetry Metrics, StatsD, or an internal
collector without adding dependencies to the base package.

```python
from worldforge import WorldForge
from worldforge.observability import ProviderMetricsExporterSink, compose_event_handlers

host_metrics_exporter = ...  # supplied by your service
forge = WorldForge(
    event_handler=compose_event_handlers(
        ProviderMetricsExporterSink(host_metrics_exporter),
    )
)
```

The sink emits:

| Metric | Meaning |
| --- | --- |
| `worldforge_provider_events_total` | Every provider event, including retries. |
| `worldforge_provider_operations_total` | Logical non-retry outcomes such as `success`, `failure`, and `budget_exceeded`. |
| `worldforge_provider_retries_total` | Retry events only, separate from logical operation totals. |
| `worldforge_provider_errors_total` | Failed or budget-exceeded operation outcomes. |
| `worldforge_provider_latency_ms` | Event `duration_ms` values when providers include them. |

Labels are bounded to `provider`, `operation`, `phase`, `status_class`, and `capability`.
`capability` is exported only when it matches a known WorldForge capability; otherwise it becomes
`unknown`. Do not add raw target URLs, prompts, metadata keys, world IDs, artifact IDs, request IDs,
or user/business identifiers as metric labels. Those values have high cardinality, and some can
carry secrets. Good first alerts are retry-rate or error-rate thresholds by provider/operation, and
latency percentile alerts on `worldforge_provider_latency_ms` grouped by provider/operation.

Example JSON log record:

```json
{
  "artifact_id": "artifact-local-id",
  "attempt": 1,
  "duration_ms": 812.4,
  "event_type": "provider_event",
  "input_digest": "sha256:9fd7...",
  "max_attempts": 3,
  "message": "",
  "metadata": {"status": "submitted"},
  "method": "POST",
  "operation": "task create",
  "phase": "success",
  "provider": "runway",
  "request_id": "host-request-id",
  "run_id": "20260430T120000Z-batch-eval",
  "span_id": "span-456",
  "status_code": 200,
  "target": "https://api.runwayml.com/v1/tasks",
  "trace_id": "trace-123"
}
```

For batch jobs, harness runs, and release evidence, attach a file sink owned by the host process:

```python
from pathlib import Path

from worldforge import WorldForge
from worldforge.observability import JsonLoggerSink, RunJsonLogSink, compose_event_handlers

run_id = "20260430T120000Z-batch-eval"
forge = WorldForge(
    event_handler=compose_event_handlers(
        JsonLoggerSink(extra_fields={"run_id": run_id}),
        RunJsonLogSink(
            Path(".worldforge") / "runs" / run_id / "provider-events.jsonl",
            run_id=run_id,
            extra_fields={"host": "batch-eval"},
        ),
    )
)
```

The file sink creates the parent directory and appends one JSON object per provider event. Its
configured `run_id` wins over any `run_id` supplied by extra fields or adapter events so every line
in the file joins to the same host run manifest. Operator bundles can then correlate
`manifest.json`, `provider-events.jsonl`, benchmark reports, and preserved artifacts without
relying on timestamps. Extra fields are validated as JSON and redacted with the same observable
secret rules as provider event messages and metadata.

Optional live smoke commands can also write a sanitized `run_manifest.json`:

```bash
scripts/robotics-showcase \
  --json-output /tmp/worldforge-robotics-showcase/real-run.json \
  --run-manifest /tmp/worldforge-robotics-showcase/run_manifest.json
```

The manifest records command argv, package version, provider profile, capability, value-free
environment presence, runtime manifest id when available, input fixture digest, event count, result
digest, and artifact paths. Validation rejects raw secret-like fields and unsanitized signed URLs;
artifact URLs are stored without query strings or fragments.

For local run inspection, install the optional `rerun` extra and stream events plus artifacts into
a Rerun recording:

```bash
uv run --extra rerun worldforge-demo-rerun
```

Expected success signal: `.worldforge/rerun/worldforge-rerun-showcase.rrd` exists, the command
prints a byte count, and the recording opens in the Rerun viewer. First triage step: run
`uv run --extra rerun python -c "import rerun; print(rerun.__version__)"`.

## Failure Modes

- Invalid caller input raises `WorldForgeError`.
- Malformed persisted or provider-supplied state raises `WorldStateError`.
- Provider runtime, transport, credential, and upstream failures raise `ProviderError`.
- Missing remote credentials leave the provider unregistered unless inspected through
  `doctor()`.
- Remote create-style requests are single-attempt by default; health checks, polling, and
  downloads retry according to `ProviderRequestPolicy`.
- Provider request budgets are per operation. `timeout_seconds` limits one HTTP attempt;
  optional `max_elapsed_seconds` limits the whole operation including retries, backoff, and task
  polling. Budget violations raise `ProviderBudgetExceededError` and emit a `budget_exceeded`
  provider event when an event handler is attached.
- Circuit breakers stay host-owned. A service can count recent `failure`, `retry`, and
  `budget_exceeded` events from `ProviderMetricsSink`, stop routing new work to a degraded
  provider, and continue serving cached/read-only paths without WorldForge owning alert channels
  or upstream SLAs.
- Cosmos and Runway validate typed upstream response payloads before creating returned media
  objects.
- Runway artifact downloads fail explicitly on expired/unavailable URLs, empty downloads, and
  explicit unsupported content types.
- LeWorldModel scoring fails explicitly when optional dependencies are unavailable, the checkpoint
  cannot load, required `pixels` / `goal` / `action` fields are missing, action candidates do not
  have shape `(batch=1, samples, horizon, action_dim)`, returned score count does not match
  candidate samples, or returned scores are not finite.
- GR00T policy selection fails explicitly when the PolicyClient dependency is unavailable, the
  policy server is unreachable, observations are malformed, raw actions are not JSON-compatible,
  or no host-owned action translator is provided.
- LeRobot policy selection fails explicitly when the LeRobot dependency is unavailable, policy
  loading fails, observations are malformed, raw actions are not JSON-compatible, or no host-owned
  action translator is provided.

## Recovery

- For local state corruption, restore from the host application's backup of exported world JSON.
- For missing credentials, fix the environment and restart the host process so provider
  auto-registration runs again.
- For transient remote failures, inspect emitted `ProviderEvent` records for `operation`,
  `phase`, `status_code`, `attempt`, and sanitized `target`.
- For expired Runway artifact URLs, regenerate or persist downloaded outputs immediately after
  task completion.
- For LeWorldModel failures, run `worldforge provider health leworldmodel`, verify
  `stable-worldmodel`, `torch`, `opencv-python`, and `imageio` are installed in the host
  environment, then confirm the configured policy exists under `$STABLEWM_HOME` or
  `LEWORLDMODEL_CACHE_DIR`.
- To smoke-test a real LeWorldModel checkpoint, run
  `scripts/lewm-real --checkpoint ~/.stable-wm/pusht/lewm_object.ckpt --device cpu`. This requires
  host-owned upstream dependencies and an extracted object checkpoint.
- If you have Hugging Face LeWM `config.json` and `weights.pt` assets rather than an extracted
  `*_object.ckpt` archive, build the object checkpoint first with
  the command below:

  ```bash
  uv run --python 3.13 \
    --with "stable-worldmodel @ git+https://github.com/galilai-group/stable-worldmodel.git" \
    --with "datasets>=2.21" \
    --with huggingface_hub \
    --with hydra-core \
    --with omegaconf \
    --with transformers \
    --with matplotlib \
    --with "opencv-python" \
    --with "imageio" \
    worldforge-build-leworldmodel-checkpoint \
      --stablewm-home ~/.stable-wm \
      --policy pusht/lewm
  ```

  `hydra-core`, `omegaconf`, and `transformers` are required to instantiate the official LeWM
  PushT config. Pass `--revision <tag-or-commit>` or set `LEWORLDMODEL_REVISION` when the run
  must be pinned to a specific Hugging Face revision.
  The builder loads downloaded `weights.pt` with `torch.load(..., weights_only=True)` by default;
  `--allow-unsafe-pickle` exists only for trusted legacy weights and older torch environments. The
  builder downloads assets to `~/.cache/worldforge/leworldmodel` by default and writes the object
  checkpoint under `$STABLEWM_HOME`.
- To demonstrate the LeWorldModel planning flow without optional dependencies, run
  `uv run worldforge-demo-leworldmodel`. It uses the real `LeWorldModelProvider` interface
  with an injected deterministic cost runtime and exercises score planning, execution,
  persistence, and reload. It is not a real upstream-checkpoint inference run; use
  `lewm-real` or `worldforge-smoke-leworldmodel` for that path. The demo should report
  `uses_leworldmodel_provider: true`, `uses_worldforge_score_planning: true`, and
  `uses_real_upstream_checkpoint: false`.
- To demonstrate LeRobot policy-plus-score planning without optional dependencies, run
  `uv run worldforge-demo-lerobot`. It uses the real `LeRobotPolicyProvider` interface with an
  injected deterministic policy runtime and exercises policy selection, score ranking, execution,
  persistence, and reload. It is not a real LeRobot checkpoint inference run.
- To run the real LeRobot plus real LeWorldModel showcase, use `scripts/robotics-showcase`. It
  launches the packaged PushT policy-plus-score bridge, opens the Textual report by default, and
  writes `/tmp/worldforge-robotics-showcase/real-run.rrd` unless `--no-rerun` is passed. For the
  full walkthrough, see [Robotics Replay Showcase](./robotics-showcase.md).
- To smoke-test a real GR00T policy server, install or check out NVIDIA Isaac-GR00T, prepare a
  host-specific observation factory and action translator, then run
  `uv run python scripts/smoke_gr00t_policy.py --gr00t-root /path/to/Isaac-GR00T --start-server ...`.
  The script can also connect to an existing server with `GROOT_POLICY_HOST` and
  `--policy-info-json` or `--observation-module`.
- Starting the upstream GR00T server requires a compatible NVIDIA/Linux runtime for its CUDA and
  TensorRT dependencies. On unsupported hosts, point WorldForge at an already running remote GR00T
  policy server.
- Pytest live runtime coverage is opt-in. Use `uv run pytest` or `uv run pytest -m "not live"` for
  deterministic checkout validation. Prepared hosts can select one live provider profile at a time
  with markers such as `live`, `network`, `credentialed`, `gpu`, `robotics`, and
  `provider_profile`, plus the matching `--run-*` flags and `--provider-profile <name>`. See
  [Run Optional Runtime Smokes](./playbooks.md#8-run-optional-runtime-smokes) for provider-specific
  commands.

## Release Checklist

Before publishing a release:

```bash
uv sync --group dev
uv lock --check
uv run ruff check src tests examples scripts
uv run ruff format --check src tests examples scripts
uv run python scripts/generate_provider_docs.py --check
uv run mkdocs build --strict
uv run pytest
uv run --extra harness pytest --cov=src/worldforge --cov-report=term-missing --cov-fail-under=90
bash scripts/test_package.sh
uv build --out-dir dist --clear --no-build-logs
```

Then run the locked dependency audit:

```bash
tmp_req="$(mktemp requirements-audit.XXXXXX)"
uv export --frozen --all-groups --no-emit-project --no-hashes -o "$tmp_req" >/dev/null
uvx --from pip-audit pip-audit -r "$tmp_req" --no-deps --disable-pip --progress-spinner off
rm -f "$tmp_req"
```

Generate the release evidence bundle after local gates and optional smokes finish:

```bash
uv run python scripts/generate_release_evidence.py \
  --run-manifest .worldforge/runs/<run-id>/run_manifest.json \
  --benchmark-artifact .worldforge/reports/benchmark-<timestamp>-<run-id>.json \
  --artifact dist/worldforge_ai-<version>-py3-none-any.whl
```

The report defaults to `.worldforge/release-evidence/release-evidence.md`. It can be generated
without credentials; providers without linked live-smoke manifests are recorded as `not configured`
or `skipped` rather than being silently omitted. Attach the report and linked artifacts when a
release note or provider promotion claims live-provider coverage.

The tag-triggered release workflow repeats the full quality gate before building distributions or
publishing release artifacts.

Also update `CHANGELOG.md`, the README, and provider documentation for any public behavior change.

## Provider Hardening Criteria

- Cosmos and Runway response parsers cover success and malformed upstream payloads with fixture
  tests.
- Remote provider non-happy-path tests cover transport retries, malformed JSON, missing task IDs,
  failed tasks, partial outputs, expired artifacts, bad artifact content types, and provider
  limits.
- Persistence remains documented as host-owned unless a dedicated persistence adapter is designed.
- API documentation lists the public exception families and provider workflow failure modes.
- Remaining work is tracked with measurable exit criteria before provider capabilities are
  advertised as complete.

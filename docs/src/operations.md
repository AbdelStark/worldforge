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
uv run worldforge provider info <provider> --format json
```

The [Reference Host Deployment Recipes](./examples.md#reference-host-deployment-recipes) cover the
stdlib service host, batch evaluation host, and robotics operator host with env templates, process
commands, readiness checks, smoke commands, logging commands, evidence export commands, expected
success signals, first triage or rollback steps, and owned boundaries. The recipes distinguish
checkout-safe, prepared-host, credentialed, GPU-bound, and robotics-lab paths without moving
deployment, auth, queueing, durable storage, controller integration, alerting, uptime, or safety
certification into WorldForge.

Operator failure drills are available from `worldforge drills`. They rehearse missing credentials,
missing optional dependencies, malformed provider output, budget violations, corrupted local world
state, expired artifacts, and unsafe event metadata with mock providers or fixtures. Drill runs
write manifests under `.worldforge/drills/runs/<run-id>/`, can export an issue bundle with
`--bundle`, and keep generated state inside the requested temporary or documented workspace.

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
| provider lifecycle ready | `forge.provider_lifecycle_status(name).ready` is true | provider-owned preflight is `no-op` or `ready`; skipped and failed hooks stay visible in diagnostics | `GET /readyz` |
| provider healthy | `forge.provider_health(name).healthy` is true | provider's cheap health check passed | `GET /readyz` |
| workflow failing | provider is configured and health may pass, but a workflow returns a typed error | request input, upstream response, budget, or artifact handling failed | workflow response body |

The reference host returns one of these readiness statuses from `GET /readyz`:

| `/readyz` status | Traffic decision | How to interpret it |
| --- | --- | --- |
| `ready` | accept | framework is alive, the selected provider is registered, lifecycle preflight is ready or no-op, and provider health passed. |
| `provider_unconfigured` | drain | framework is alive, but the selected provider is not registered in this process. |
| `provider_unhealthy` | drain | provider is registered, but its health check reports missing optional runtime, bad credentials, unreachable upstream, or another provider-owned failure detail. |

Map CLI diagnostics the same way during incidents:

| Command | Readiness signal |
| --- | --- |
| `uv run worldforge doctor --registered-only` | registered provider count, health count, and local configuration issues. |
| `uv run worldforge doctor --capability <capability>` | whether any known provider can satisfy the requested surface. |
| `uv run worldforge provider health <name>` | provider-specific configured/healthy details. |
| `uv run worldforge provider info <name>` | redacted config summary plus profile, capability, lifecycle, and health. |

Lifecycle diagnostics use typed hook statuses: `no-op`, `ready`, `skipped`, `failed`, and
`teardown-failed`. `skipped` is the expected result when a prepared-host provider is missing
required env vars or host-owned optional dependencies; it is a skip reason, not a hidden install or
credential-provisioning attempt.

WorldForge reports local provider state and adapter errors. It does not own upstream provider SLAs,
deployment load balancers, alert channels, retry orchestration outside one provider call, or
credential rotation.

## Configuration

Configuration comes from constructor arguments and environment variables documented in
`.env.example`. The generated [Provider Configuration Index](./provider-configuration-index.md)
is the canonical cross-provider table for required inputs, optional inputs, host-owned packages,
prepared-host assets, default request timeouts, first diagnostic commands, and smoke commands.

- `COSMOS_BASE_URL` enables the Cosmos adapter.
- `NVIDIA_API_KEY` is optional bearer auth for Cosmos.
- `COSMOS_POLICY_BASE_URL` enables the optional Cosmos-Policy embodied-policy adapter.
- `COSMOS_POLICY_API_TOKEN`, `COSMOS_POLICY_TIMEOUT_SECONDS`, `COSMOS_POLICY_EMBODIMENT_TAG`,
  `COSMOS_POLICY_MODEL`, `COSMOS_POLICY_RETURN_ALL_QUERY_RESULTS`,
  `COSMOS_POLICY_ALLOW_LOCAL_BASE_URL`, and `COSMOS_POLICY_ALLOWED_HOSTS` are optional
  Cosmos-Policy `/act` settings.
- `RUNWAYML_API_SECRET` enables the Runway adapter.
- `RUNWAY_API_SECRET` remains supported as the legacy Runway alias.
- `RUNWAYML_BASE_URL` overrides the default Runway API endpoint.
- `RUNWAYML_ALLOW_LOCAL_ARTIFACT_URLS` is a test-only opt-in for trusted local Runway-compatible
  artifact URLs. Leave it unset in normal remote-provider deployments.
- `RUNWAYML_RESOLVE_ARTIFACT_DNS` overrides artifact URL DNS validation for custom transports.
  Leave it unset for auto mode, or set it for custom network transports that still use system DNS.
- `LEWORLDMODEL_POLICY` or `LEWM_POLICY` enables the optional LeWorldModel adapter.
- `LEWORLDMODEL_CACHE_DIR` overrides the LeWorldModel checkpoint root.
- `LEWORLDMODEL_REVISION` pins the Hugging Face LeWM commit used when the showcase auto-builds
  a missing object checkpoint.
- `LEWORLDMODEL_ASSET_CACHE_DIR` overrides the checkpoint builder's Hugging Face config/weights
  cache directory.
- `LEWORLDMODEL_DEVICE` selects the optional torch device for LeWorldModel scoring.
- `GROOT_POLICY_HOST` enables the optional GR00T embodied-policy adapter.
- `GROOT_POLICY_PORT` defaults to `5555`.
- `GROOT_POLICY_TIMEOUT_MS` defaults to `15000`.
- `GROOT_POLICY_API_TOKEN`, `GROOT_POLICY_STRICT`, and `GROOT_EMBODIMENT_TAG` are optional GR00T
  PolicyClient settings.
- `LEROBOT_POLICY_PATH` or `LEROBOT_POLICY` enables the optional LeRobot embodied-policy adapter.
- `LEROBOT_POLICY_TYPE`, `LEROBOT_DEVICE`, `LEROBOT_CACHE_DIR`, and `LEROBOT_EMBODIMENT_TAG` are
  optional LeRobot settings.
- `JEPA_MODEL_NAME` enables the experimental score-only JEPA adapter backed by the upstream
  `facebookresearch/jepa-wms` torch-hub path.
- `JEPA_MODEL_PATH` is legacy scaffold metadata only; it does not make the provider runnable.
- `GENIE_API_KEY` only registers a capability-closed scaffold reservation.
- `WORLDFORGE_ENABLE_SCAFFOLD_SURROGATES=1` is for local scaffold adapter tests only; it does not
  make Genie a real provider integration.

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
uv run worldforge world preflight --state-dir .worldforge/worlds --workspace-dir .worldforge
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

ADR 0001, [Persistence Adapter Boundary](./adr/0001-persistence-adapter-boundary.md), records the
future `WorldPersistenceAdapter` boundary and the acceptance bar for any durable store.

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
- `world preflight` is read-only and does not create, rewrite, delete, or silently coerce state. It
  reports missing state directories, unsafe requested IDs, corrupted worlds, invalid histories,
  incoherent object bounding boxes, stale run workspaces, unsafe run artifact paths, and retention
  pressure.
- README and operations docs state that multi-writer persistence is host-owned.
- Any future built-in persistence backend must be introduced as an explicit adapter with its own
  locking, migration, and recovery documentation.

Local state preflight is the first operator command before quarantining user data:

```bash
uv run worldforge world preflight \
  --state-dir .worldforge/worlds \
  --workspace-dir .worldforge \
  --world-id <world-id> \
  --retention-keep 20 \
  --format json > worldforge-state-preflight.json
```

Success signal: `status` is `passed`, `safe_to_attach` is `true`, and `error_count` is `0`. Warning
status is allowed for absent local state or retention pressure; failed status means at least one
world file, requested ID, run manifest, or artifact reference needs operator action.

Recovery commands in the report export diagnostics before moving invalid files into
`.worldforge/quarantine/`. They do not run `rm` or silently delete user data. For retention pressure,
the first command is `uv run worldforge runs cleanup --workspace-dir .worldforge --keep 20 --dry-run`;
remove `--dry-run` only after the preserved evidence is no longer needed.

## Run Workspaces

Evaluation, benchmark, and harness jobs can preserve checkout-safe run evidence under
`.worldforge/runs/<run-id>/`. This is separate from local JSON world persistence: run workspaces are
operator evidence bundles, not a database.

```bash
uv run worldforge eval --suite planning --provider mock --run-workspace .worldforge
uv run worldforge benchmark --provider mock --operation predict --run-workspace .worldforge
uv run worldforge runs list
uv run worldforge harness --runs --provider mock --status failed --artifact-type json
uv run worldforge runs bundle <run-id>
uv run worldforge runs cleanup --keep 20
```

Each run directory contains `run_manifest.json`, `inputs/`, `results/`, `reports/`, `artifacts/`,
and `logs/`. The manifest stores a sortable file-safe run ID, command, provider, operation, status,
input summary, result summary, event count, and relative artifact paths.

For public issues, run `worldforge runs bundle <run-id> --workspace-dir .worldforge` first. The
command writes `.worldforge/issue-bundles/<run-id>/evidence_manifest.json`, `summary.md`, and
`issue.md`, then prints the issue template. Success signal: `safe_to_attach` is `true` or the
manifest clearly lists excluded/local-only files with a reason. First triage step after export:
open `evidence_manifest.json`; if anything is excluded or local-only, remove or replace the unsafe
artifact before attaching the bundle.

For repeated local operations, use `worldforge harness --runs` or the TheWorldHarness Runs screen
before opening individual artifacts. It reads preserved manifests without optional model runtimes,
filters by provider, capability, status, created date, and safe artifact type, and prints sanitized
rerun, comparison, and issue-bundle commands. Failed, skipped, and cancelled rows surface the
`worldforge runs bundle <run-id>` recovery command first.

Retention is host-owned. `worldforge runs cleanup --keep <n>` keeps the newest run IDs and removes
older directories; use `--dry-run` before deleting evidence attached to an incident or release gate.
Do not attach raw host-created artifacts that contain private paths, prompts, credentials, signed
URLs, or provider-native payloads.

Candidate benchmark budgets must be generated from preserved benchmark reports and reviewed before
they replace release budget files:

```bash
uv run python scripts/calibrate_benchmark_budgets.py \
  --report .worldforge/reports/benchmark-<timestamp>-<run-id>.json \
  --current-budget src/worldforge/benchmark_presets/_data/budget-release-evidence.json
```

The success signal is a `budget-calibration.md` review report plus a loadable
`candidate-budgets.json`; the command does not weaken existing release gates automatically.
Threshold loosening is allowed only with preserved report digests, machine-class context, observed
baseline values, and reviewer rationale.

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

## Robotics Operator Review

The checkout host at `examples/hosts/robotics-operator/app.py` is an offline review loop for
policy-plus-score robotics runs:

```bash
uv run python examples/hosts/robotics-operator/app.py review --sample-translator
```

By default it does not talk to robot controllers. It requires an explicit action translator in the
host process, records checklist and dry-run approval state, and preserves selected action chunks,
score rationale, provider events, and a replay artifact under
`.worldforge/robotics-operator/runs/<run-id>/`.

WorldForge only certifies that its typed provider, event, replay, and manifest artifacts satisfy
the framework contracts. The lab host remains responsible for embodiment translators, controller
hooks, workspace safety, operator approval policy, emergency stops, hardware behavior, deployment
readiness, and safety certification.

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
  objects. Parser fixtures cover malformed upstream payloads, auth failures, failed-task payloads,
  timeout event metadata, and unsupported artifact-reference responses so release evidence can cite
  the exact failure shape.
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
      --policy pusht/lewm \
      --revision 22b330c28c27ead4bfd1888615af1340e3fe9052
  ```

  `hydra-core`, `omegaconf`, and `transformers` are required to instantiate the official LeWM
  PushT config. Before Hydra is allowed to instantiate anything, the builder validates the
  downloaded config against the known official PushT LeWM target allowlist, rejects any
  interpolated `_target_` value, and rejects nested targets outside that allowlist. The default
  revision is the pinned commit
  `22b330c28c27ead4bfd1888615af1340e3fe9052`; pass `--revision <40-char-commit-sha>` or set
  `LEWORLDMODEL_REVISION` to another audited immutable Hugging Face commit.
  The builder loads downloaded `weights.pt` with `torch.load(..., weights_only=True)` by default;
  `--allow-unsafe-pickle` exists only for trusted legacy weights and older torch environments. The
  builder downloads assets to `~/.cache/worldforge/leworldmodel` by default, or to
  `LEWORLDMODEL_ASSET_CACHE_DIR` / `--asset-cache-dir` when set, and writes the object checkpoint
  under `$STABLEWM_HOME`.
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
- To run the same path in CI, use `.github/workflows/robotics-showcase.yml`. It runs
  `scripts/robotics-showcase --json-only --no-tui --no-rerun` on every pull request update and on
  pushes to `main`, validates real policy/score events, caches Hugging Face assets and the
  LeWorldModel object checkpoint with `actions/cache`, and uploads the JSON summary plus
  `run_manifest.json` as evidence. Checkpoint artifacts are not uploaded.
- To smoke-test a real GR00T policy server, install or check out NVIDIA Isaac-GR00T on a prepared
  NVIDIA/Linux host, prepare a host-specific observation fixture and action translator, then run
  `GROOT_POLICY_HOST=127.0.0.1 GROOT_POLICY_PORT=5555 uv run --with msgpack --with pyzmq --with numpy python scripts/smoke_gr00t_policy.py --health-only --run-manifest .worldforge/runs/gr00t-health/run_manifest.json`.
  Expected success for `--health-only`: the process exits 0 and the run manifest records
  `capability=policy` with `status=skipped`.
  For a full policy request, run
  `GROOT_POLICY_HOST=127.0.0.1 GROOT_POLICY_PORT=5555 uv run --with msgpack --with pyzmq --with numpy python scripts/smoke_gr00t_policy.py --policy-info-json /path/to/policy_info.json --translator /path/to/translator.py:translate_actions --allow-translator-code --run-manifest .worldforge/runs/gr00t-live/run_manifest.json`.
  Expected success: the process exits 0 and the run manifest records `capability=policy` with
  `status=passed`. First triage: run `uv run worldforge provider health gr00t` to confirm the
  client can reach the remote PolicyClient server, then recheck the observation fixture and
  translator path.
- Starting the upstream GR00T server requires a compatible NVIDIA/Linux runtime for its CUDA and
  TensorRT dependencies. On unsupported hosts, point WorldForge at an already running remote GR00T
  policy server. Prefer an SSH tunnel such as `ssh -N -L 5555:127.0.0.1:5555 ubuntu@<gpu-host>`
  or restrict the server port to the operator IP or VPN. Hibernate or terminate remote GPU
  instances when the smoke is done.
- To smoke-test a real Cosmos-Policy ALOHA server, run the upstream server on a compatible
  Linux/NVIDIA host, prepare ALOHA policy info and an action translator, then run
  `COSMOS_POLICY_BASE_URL=http://127.0.0.1:8777 COSMOS_POLICY_ALLOW_LOCAL_BASE_URL=1 uv run worldforge-smoke-cosmos-policy --policy-info-json /path/to/policy_info.json --translator /path/to/translator.py:translate_actions --allow-translator-code --run-manifest .worldforge/runs/cosmos-policy-live/run_manifest.json`.
  For the configuration-only path, run
  `COSMOS_POLICY_BASE_URL=http://127.0.0.1:8777 COSMOS_POLICY_ALLOW_LOCAL_BASE_URL=1 uv run worldforge-smoke-cosmos-policy --health-only --run-manifest .worldforge/runs/cosmos-policy-health/run_manifest.json`.
  `--health-only` validates WorldForge configuration only because the targeted upstream server has
  no non-mutating health endpoint and does not call `/act`.
  Expected success for `--health-only`: the process exits 0 and the run manifest records
  `capability=policy` with `status=skipped`.
  Expected success: the process exits 0 and the run manifest records `capability=policy` with
  `status=passed`. First triage: run `uv run worldforge provider health cosmos-policy` to confirm
  configuration, then run the smoke command to verify the host can reach `/act`.
  For rented or lab GPUs, follow the
  [Cosmos-Policy remote GPU runbook](./providers/cosmos-policy.md#remote-gpu-runbook): use a
  prepared 48 GB or larger Linux/NVIDIA host when required by the upstream model, prefer an SSH
  tunnel to port `8777`, restrict direct firewall exposure to the operator IP or VPN CIDR, preserve
  only sanitized manifests/replay artifacts, and hibernate or terminate the GPU host when done.
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
uv run python scripts/check_docs_commands.py
uv run python scripts/check_docs_snippets.py
uv run python scripts/check_wrapper_portability.py
uv run python scripts/check_optional_import_boundaries.py
uv run python scripts/check_core_performance.py
uv run mkdocs build --strict
uv run pytest
uv run --extra harness pytest --cov=src/worldforge --cov-report=term-missing --cov-fail-under=90
bash scripts/test_package.sh
uv build --out-dir dist --clear --no-build-logs
shasum -a 256 dist/worldforge_ai-*.whl dist/worldforge_ai-*.tar.gz
```

The artifact integrity contract is documented in [Artifact Integrity](./artifact-integrity.md). It
covers package hashes, current package/evidence checks, unsafe artifact exclusions, and future SBOM,
provenance, and attestation work that is not claimed today.

Then generate locked dependency-audit evidence:

```bash
uv run python scripts/generate_dependency_audit_evidence.py
```

The wrapper runs the documented `uv export --frozen --all-groups --no-emit-project --no-hashes`
plus `uvx --from pip-audit pip-audit ... --format json` flow using a temporary requirements file
that is removed after the audit. It writes `.worldforge/dependency-audit/dependency-audit.json`
and `.worldforge/dependency-audit/dependency-audit.md`, records tool versions, dependency-set
digest, vulnerability summary, explicit `--ignore-advisory ADVISORY=RATIONALE` rows, command
output tails, and a first triage step. Success signal: status is `passed`; findings,
tool-unavailable, and failed states still leave safe-to-attach evidence. First triage step for
findings: inspect the Markdown advisory row, upgrade or document the dependency decision, then
rerun the audit.

Generate the release-readiness evidence after local gates and optional smokes finish. The command
writes both Markdown and JSON summaries by default; use `--run-gates` when the evidence run itself
should execute the checkout-safe gates instead of recording them as skipped.

```bash
uv run python scripts/generate_release_evidence.py \
  --run-gates \
  --live-smoke-registry docs/src/live-smoke-evidence.json \
  --run-manifest .worldforge/runs/<run-id>/run_manifest.json \
  --artifact .worldforge/dependency-audit/dependency-audit.json \
  --benchmark-artifact .worldforge/reports/benchmark-<timestamp>-<run-id>.json \
  --artifact dist/worldforge_ai-<version>-py3-none-any.whl
```

The report defaults to `.worldforge/release-evidence/release-evidence.md` and the JSON summary
defaults to `.worldforge/release-evidence/release-evidence.json`. Gate rows are explicit
`passed`, `failed`, or `skipped`; each row includes the command, exit code when available, and first
triage step. Optional live provider evidence is `host-owned` unless a prepared-host
`run_manifest.json` is linked. Attach the Markdown report, JSON summary, and linked artifacts when a
release note or provider promotion claims live-provider coverage.

Generate the local quality dashboard when you need one at-a-glance page for the branch:

```bash
uv run python scripts/generate_quality_dashboard.py
```

The dashboard defaults to `.worldforge/quality-dashboard/quality-dashboard.json` and
`.worldforge/quality-dashboard/quality-dashboard.md`. It reads existing release evidence,
dependency-audit evidence, and core-performance JSON; it does not execute gates. Status rows use
`passed`, `failed`, `warning`, `skipped`, and `not-run`, preserve raw failure output tails, list
skipped host-owned provider checks, and name the first failed gate. Use it as a local quality
index. Release evidence remains the artifact for release claims, artifact hashes, linked
`run_manifest.json` files, and known limitations.

After evidence exists, draft release notes for maintainer editing:

```bash
mkdir -p .worldforge/release-notes
gh issue list --state closed --limit 200 \
  --json number,title,url,labels,closedAt,state \
  > .worldforge/release-notes/closed-issues.json
uv run python scripts/generate_release_notes.py \
  --release-evidence .worldforge/release-evidence/release-evidence.json \
  --issues-json .worldforge/release-notes/closed-issues.json \
  --known-caveat "No prepared-host live smoke was run for <provider>."
```

The release-notes command writes `.worldforge/release-notes/release-notes-draft.md`. It is a draft
artifact only: maintainers must edit it before publishing, and the command never creates a tag,
GitHub release, signature, or trusted-publishing artifact. Success signal: the draft contains
added, changed, fixed, docs, validation, compatibility, caveat, and host-owned optional-runtime
sections. First triage step when validation is missing: run
`uv run python scripts/generate_release_evidence.py --run-gates` and regenerate the draft. Use
`--require-validation-evidence` in release scripts when a missing or invalid evidence JSON should
fail the command.

`uv run python scripts/check_core_performance.py` writes a checkout-safe JSON report for world
persistence, benchmark fixture loading, provider diagnostics, evidence-bundle creation, and report
rendering. Success signal: `passed` is true and each result row has a preserved artifact path when
`--workspace-dir <path>` is supplied. First triage step: inspect the failing row's measured path and
fix the regression before changing a budget. These budgets are local regression guards, not
cross-machine or optional-runtime performance claims.

`uv run python scripts/check_wrapper_portability.py` checks shell wrappers and optional-runtime
smoke commands without installing host-owned runtimes. Success signal: the report passes for
`scripts/robotics-showcase`, `scripts/lewm-real`, `scripts/lewm-lerobot-real`, GR00T and LeRobot
smoke helpers, and `scripts/test_package.sh`. First triage step: fix the named script's shebang,
executable bit, documented command, or Python 3.13 uv invocation.

`uv run python scripts/check_optional_import_boundaries.py` checks optional-runtime import
boundaries without installing host-owned runtimes. Success signal: base package imports, CLI
startup, `worldforge.rerun`, and non-TUI harness modules do not load Textual, Rerun, torch,
stable-worldmodel, LeRobot, GR00T, or Cosmos-Policy packages, and static source checks only find
optional imports inside their allowed provider, smoke, Rerun, or `harness.tui` modules. First
triage step: move the named import behind the allowed lazy boundary in the report.

`uv run python scripts/check_docs_snippets.py` executes selected Python snippets and parses selected
JSON snippets from the public docs. Success signal: the report passes with no snippet failures, and
any host-owned, credentialed, or illustrative snippets are explicitly skipped. First triage step:
fix the file, heading, and line named in the failure before changing surrounding docs.

When release or issue triage needs the underlying evaluation and benchmark artifacts, generate a
separate evidence bundle first:

```bash
uv run worldforge eval --suite planning --provider mock --run-workspace .worldforge
uv run worldforge benchmark --preset mock-smoke --run-workspace .worldforge
uv run python scripts/generate_evidence_bundle.py \
  --workspace-dir .worldforge \
  --output .worldforge/evidence-bundles/mock-planning
uv run python scripts/generate_release_evidence.py \
  --artifact .worldforge/evidence-bundles/mock-planning/evidence_manifest.json
```

Success signal: the bundle writes `evidence_manifest.json` and `summary.md`, every included file
has a `sha256:<hex>` digest, and excluded files carry a reason such as unsupported suffix,
host-local path, or secret-like material. First triage step on failure: inspect the run's
`run_manifest.json` and remove or local-only mark unsafe artifacts before regenerating the bundle.

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

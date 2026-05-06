# Examples And CLI Commands

Use the CLI index for the current runnable examples and optional smoke paths:

```bash
uv run worldforge examples
uv run worldforge examples --format json
```

For the full command surface, see the [CLI Reference](./cli.md).

## Demo Showcase Runner

| Workflow | Surface | Command |
| --- | --- | --- |
| `demo-showcases` | Ten checkout-safe issue-backed workflows for first-run, diagnostics, replay, remote dry-run, adapter authoring, batch eval, service host, Rerun gallery, failure lab, and cookbook evidence | `uv run python scripts/demo_showcases.py run all --workspace-dir .worldforge/demo-showcases` |

```bash
uv run python scripts/demo_showcases.py list
uv run python scripts/demo_showcases.py run first-run --workspace-dir .worldforge/demo-showcases
uv run python scripts/demo_showcases.py run all --workspace-dir .worldforge/demo-showcases --format json --overwrite
```

Each selected workflow writes a preserved `run_manifest.json`, `results/summary.json`, and
`reports/summary.md` under `.worldforge/demo-showcases/<workflow>/runs/<run-id>/`. The runner does
not install optional model runtimes, call paid providers, open a GUI, or control robots. See
[Demo Showcase Workflows](./demo-showcases.md) for the artifact matrix and
[Use Case Cookbook](./use-case-cookbook.md) for task-oriented recipes.

## Visual Harness

| Example | Surface | Command |
| --- | --- | --- |
| `theworldharness` | E2E flows, provider diagnostics, benchmark comparison | `uv run --extra harness worldforge-harness` |

`TheWorldHarness` is an optional Textual TUI for running the packaged E2E demos as visible
provider workflows.

```bash
uv run --extra harness worldforge-harness
uv run --extra harness worldforge-harness --flow lerobot
uv run --extra harness worldforge-harness --flow diagnostics
uv run worldforge harness --list
```

The harness keeps Textual out of the base dependency set. Install or run with the `harness` extra
when you want the visual interface.

Available flows:

| Flow | Purpose |
| --- | --- |
| `leworldmodel` | Visual score-planning path through the LeWorldModel provider surface. |
| `lerobot` | Visual policy-plus-score path through the LeRobot provider surface. |
| `diagnostics` | Visual provider diagnostics and benchmark comparison path. |

## Rerun Recording

| Example | Surface | Command |
| --- | --- | --- |
| `rerun-observability-showcase` | Provider events, world snapshots, 3D object boxes, plan artifacts, benchmark metrics | `uv run --extra rerun worldforge-demo-rerun` |
| `rerun-robotics-showcase` | Real PushT policy+score run with candidate targets, selected trajectory, score bars, latency bars, provider events, and replay snapshots | `scripts/robotics-showcase` |

The Rerun showcase writes `.worldforge/rerun/worldforge-rerun-showcase.rrd` by default. Open it
with:

```bash
uv run --extra rerun rerun .worldforge/rerun/worldforge-rerun-showcase.rrd
```

See [Rerun Integration](./rerun.md) for live viewer modes and Python API usage.

## Prediction And Evaluation

| Example | Command | Purpose |
| --- | --- | --- |
| `basic-prediction` | `uv run python examples/basic_prediction.py` | Create a mock world, predict, plan, and print a physics evaluation report. |

## Provider Comparison

| Example | Command | Purpose |
| --- | --- | --- |
| `cross-provider-compare` | `uv run python examples/cross_provider_compare.py` | Register a second deterministic provider and compare prediction outputs. |

## Score Planning

| Example | Command | Runtime boundary |
| --- | --- | --- |
| `leworldmodel-score-planning` | `uv run worldforge-demo-leworldmodel` | Uses `LeWorldModelProvider` with an injected deterministic cost runtime. |

## Policy Plus Score Planning

| Example | Command | Runtime boundary |
| --- | --- | --- |
| `lerobot-policy-score-planning` | `uv run worldforge-demo-lerobot` | Uses `LeRobotPolicyProvider` with an injected deterministic policy runtime. |

Both packaged demos validate the WorldForge adapter, planning, execution, persistence, reload, and
event path in a clean checkout. They do not install optional ML runtimes or run upstream neural
checkpoint inference.

## Service Host Reference

| Example | Command | Runtime boundary |
| --- | --- | --- |
| `service-host` | `uv run python examples/hosts/service/app.py --provider mock --port 8080` | Stdlib HTTP reference host; the embedding service owns deployment, credentials, telemetry export, alerting, and upstream SLA handling. |

The service host exposes:

| Endpoint | Purpose |
| --- | --- |
| `GET /healthz` | Process liveness only. |
| `GET /readyz` | Framework alive, configured provider, provider health, traffic decision, and `doctor()` summary. |
| `GET /providers` | Registered-provider diagnostics for the current host process. |
| `POST /workflows/mock-predict` | Safe deterministic mock prediction smoke. |
| `POST /workflows/generate` | Configurable provider generate workflow using a JSON body with `provider`, `prompt`, and `duration_seconds`. |

`/readyz` reports `ready`, `provider_unconfigured`, or `provider_unhealthy`. Only `ready`
means the host should accept provider-backed workflow traffic; the other states tell the host
load balancer or job runner to drain this process while operators inspect `checks.provider_health`
and the embedded `doctor` summary.

Every response includes or echoes a request id. Provider events are sent through `JsonLoggerSink`
with that request id so host logs can correlate HTTP requests with provider calls. Public errors
use typed JSON payloads and redact obvious secret-shaped values, but production services still own
credential storage, request authentication, dashboards, alert routing, and provider SLA policy.

## Batch Evaluation Host

| Example | Command | Runtime boundary |
| --- | --- | --- |
| `batch-eval-host` | `uv run python examples/hosts/batch-eval/app.py benchmark --provider mock` | Stdlib job reference host; the embedding batch system owns scheduling, durable storage, credentials, and provider-specific runtime setup. |

Run deterministic mock evaluation and benchmark jobs in a clean checkout:

```bash
uv run python examples/hosts/batch-eval/app.py \
  --workspace .worldforge/batch-eval \
  eval --suite planning --provider mock

uv run python examples/hosts/batch-eval/app.py \
  --workspace .worldforge/batch-eval \
  benchmark --provider mock --operation generate --iterations 1 \
  --input-file examples/benchmark-inputs.json \
  --budget-file examples/benchmark-budget.json
```

Each job writes a shared run workspace under `.worldforge/batch-eval/runs/<run-id>/` with
`run_manifest.json`, JSON/Markdown/CSV reports, copied input and budget files for benchmark jobs,
and a JSON stdout summary that points to the manifest. Benchmark budget violations return exit
code `1` after preserving the failed run, which lets CI or a scheduler fail the job while still
keeping issue-safe artifacts.

To swap in a real provider, run the same command on a prepared host that has the provider
registered, credentials configured, optional runtime dependencies installed, and benchmark inputs
that match that provider's advertised capability. Keep scheduling, retry policy above the process,
long-term artifact storage, and credential rotation outside the base package.

## Robotics Operator Host

| Example | Command | Runtime boundary |
| --- | --- | --- |
| `robotics-operator-host` | `uv run python examples/hosts/robotics-operator/app.py review --sample-translator` | Stdlib offline operator-review host; the lab application owns action translators, checklist policy, approval, controller integration, interlocks, and safety certification. |

The default mode does not call robot controllers. It runs a deterministic LeRobot policy surface and
score provider through an explicit sample PushT translator, then writes a preserved run workspace
under `.worldforge/robotics-operator/runs/<run-id>/` with:

- `results/action_chunks.json` for all candidate action chunks and the selected chunk.
- `results/score_rationale.json` for score values, best index, and score metadata.
- `logs/provider-events.jsonl` for the provider event stream.
- `results/approval.json` for host-owned checklist and dry-run approval state.
- `results/replay.json` for an offline replay artifact.

Controller execution remains disabled unless the embedding host supplies an explicit controller
hook in code, all checklist items are true, and dry-run approval is recorded. WorldForge only
produces typed policy, score, event, replay, and run-manifest artifacts; it does not certify robot
hardware, task safety, emergency stops, workspace readiness, or controller behavior.

## Reference Host Deployment Recipes

These recipes are for embedding WorldForge in a host process, not for deploying WorldForge as a
managed service. WorldForge owns provider contracts, typed validation, local run manifests, report
rendering, and sanitized evidence helpers. The host owns deployment, authentication, queueing,
durable storage, controller integration, alerting, rollback, uptime, and provider or robot safety
policy.

Path taxonomy:

| Path | When to use it | Success signal | Host-owned boundary |
| --- | --- | --- | --- |
| checkout-safe | `mock` provider, deterministic examples, no credentials | command exits `0`, `/readyz` is `ready`, or a run manifest is written | no physical-fidelity, uptime, or durability claim |
| prepared-host | optional provider/runtime already installed by the host | provider health is healthy and the smoke writes evidence | dependency install, checkpoints, cache directories, and runtime patches |
| credentialed | Cosmos, Runway, or another remote provider with secrets loaded outside the repo | `provider info` shows redacted config and health passes | secret storage, credential rotation, upstream SLA, and network egress |
| GPU-bound | LeWorldModel, LeRobot, GR00T, or another device-bound runtime | host preflight names the device and the smoke records a manifest | CUDA/Metal drivers, device scheduling, model assets, and memory pressure |
| robotics-lab | operator review around task-specific policy/action translation | dry-run review records approval and no controller calls by default | workspace safety, interlocks, controller hooks, operator approval, and safety certification |

No new provider environment variables are introduced by these recipes, so `.env.example` stays
unchanged unless a future provider adds real configuration.

### Stdlib Service Host Recipe

Owned boundary: WorldForge maps provider diagnostics to `/readyz`, emits typed public errors, and
can run deterministic mock or generate workflows. The embedding service owns HTTP deployment,
request authentication, routing, queueing, durable state, log shipping, alerting, upstream SLA
policy, and rollback.

Env template:

```bash
export WORLDFORGE_SERVICE_PROVIDER=mock
export WORLDFORGE_SERVICE_STATE_DIR=.worldforge/service-worlds
export WORLDFORGE_SERVICE_PORT=8080
# Credentialed path only: export COSMOS_BASE_URL=... or RUNWAYML_API_SECRET=...
```

Process command:

```bash
mkdir -p .worldforge/service/logs
PYTHONUNBUFFERED=1 uv run python examples/hosts/service/app.py \
  --provider "${WORLDFORGE_SERVICE_PROVIDER:-mock}" \
  --state-dir "${WORLDFORGE_SERVICE_STATE_DIR:-.worldforge/service-worlds}" \
  --port "${WORLDFORGE_SERVICE_PORT:-8080}" \
  2>&1 | tee .worldforge/service/logs/service.log
```

Readiness command:

```bash
curl -fsS http://127.0.0.1:8080/readyz | python -m json.tool
```

Expected success signal: `status` is `ready`, `traffic` is `accept`, and
`checks.provider_healthy` is `true`. First failure triage step: if the status is
`provider_unconfigured` or `provider_unhealthy`, run
`uv run worldforge doctor --registered-only` and `uv run worldforge provider health <provider>`,
then inspect the redacted `checks.provider_health.details` field.

Smoke command:

```bash
curl -fsS -X POST http://127.0.0.1:8080/workflows/mock-predict \
  -H 'content-type: application/json' \
  -H 'x-request-id: service-smoke-001' \
  -d '{}' | python -m json.tool
```

Logging command:

```bash
tail -f .worldforge/service/logs/service.log
```

Evidence export command:

```bash
mkdir -p .worldforge/service/evidence
curl -fsS http://127.0.0.1:8080/readyz > .worldforge/service/evidence/readyz.json
curl -fsS http://127.0.0.1:8080/providers > .worldforge/service/evidence/providers.json
```

First rollback step: drain this host in the embedding service, restart it with the last known good
provider configuration or `WORLDFORGE_SERVICE_PROVIDER=mock`, and keep upstream traffic disabled
until `/readyz` returns `ready`.

### Batch Eval Host Recipe

Owned boundary: WorldForge runs deterministic evaluation and benchmark contracts, writes
`run_manifest.json`, report artifacts, and budget verdicts. The batch platform owns scheduling,
queueing, retries above the process, credentials, long-term artifact storage, budget-change review,
alerting, and rollback.

Env template:

```bash
export WORLDFORGE_BATCH_WORKSPACE=.worldforge/batch-eval
export WORLDFORGE_BATCH_STATE_DIR=.worldforge/batch-eval/worlds
# Prepared-host or credentialed path only: load provider-specific env from .env.example.
```

Readiness command:

```bash
uv run worldforge doctor --registered-only
uv run worldforge doctor --capability generate
uv run worldforge provider health mock
```

Process command:

```bash
uv run python examples/hosts/batch-eval/app.py \
  --workspace "${WORLDFORGE_BATCH_WORKSPACE:-.worldforge/batch-eval}" \
  --state-dir "${WORLDFORGE_BATCH_STATE_DIR:-.worldforge/batch-eval/worlds}" \
  benchmark --provider mock --operation generate --iterations 1 \
  --input-file examples/benchmark-inputs.json \
  --budget-file examples/benchmark-budget.json
```

Smoke command: use the same checkout-safe benchmark command with `--provider mock`; it exercises
report rendering, budget evaluation, manifest preservation, and the batch host exit code without
live credentials.

Expected success signal: JSON stdout contains `status: "passed"`, `exit_code: 0`,
`run_manifest`, and a `budget.passed` value of `true` when a budget file is supplied. Budget
violations exit `1` only after the failed run workspace is preserved.

Logging command:

```bash
uv run worldforge runs list \
  --workspace-dir "${WORLDFORGE_BATCH_WORKSPACE:-.worldforge/batch-eval}" \
  --format markdown
```

Evidence export command:

```bash
uv run worldforge runs bundle <run-id> \
  --workspace-dir "${WORLDFORGE_BATCH_WORKSPACE:-.worldforge/batch-eval}"
```

First failure triage step: open `<workspace>/runs/<run-id>/run_manifest.json`, then export the
bundle before deleting or retrying the run. First rollback step: stop the scheduler queue, restore
the last known good input or budget file, rerun the checkout-safe `mock` benchmark, and only then
reenable prepared-host or credentialed provider jobs.

### Robotics Operator Host Recipe

Owned boundary: WorldForge runs an offline policy-plus-score review, preserves selected action
chunks, score rationale, provider events, dry-run approval, replay artifacts, and a manifest. The
lab host owns task observations, action translators, workspace readiness, emergency stops,
operator approval, controller hooks, robot hardware, and safety certification.

Env template:

```bash
export WORLDFORGE_ROBOTICS_WORKSPACE=.worldforge/robotics-operator
export WORLDFORGE_ROBOTICS_STATE_DIR=.worldforge/robotics-operator/worlds
# Prepared-host, GPU-bound, or robotics-lab path only:
# export LEROBOT_POLICY_PATH=...
# export LEROBOT_DEVICE=cuda
# export LEWORLDMODEL_DEVICE=cuda
```

Readiness command:

```bash
uv run worldforge provider health mock
scripts/robotics-showcase --health-only
```

Use the first command for the checkout-safe operator recipe. Use the `--health-only` showcase
preflight on prepared-host, GPU-bound, or robotics-lab paths before any real LeRobot or
LeWorldModel run.

Process command:

```bash
uv run python examples/hosts/robotics-operator/app.py \
  --workspace "${WORLDFORGE_ROBOTICS_WORKSPACE:-.worldforge/robotics-operator}" \
  --state-dir "${WORLDFORGE_ROBOTICS_STATE_DIR:-.worldforge/robotics-operator/worlds}" \
  review --sample-translator --approve-dry-run \
  --check workspace_clear \
  --check emergency_stop_available \
  --check operator_present \
  --check controller_isolated
```

Smoke command: use the same checkout-safe review command with the sample translator. It records a
dry-run review and keeps controller execution disabled.

Expected success signal: JSON stdout contains `status: "passed"`, `exit_code: 0`,
`run_manifest`, `controller_executed: false`, and paths for `approval`, `action_chunks`,
`score_rationale`, `provider_events`, and `replay`.

Logging command:

```bash
tail -n +1 \
  "${WORLDFORGE_ROBOTICS_WORKSPACE:-.worldforge/robotics-operator}"/runs/<run-id>/logs/provider-events.jsonl
```

Evidence export command:

```bash
uv run worldforge runs bundle <run-id> \
  --workspace-dir "${WORLDFORGE_ROBOTICS_WORKSPACE:-.worldforge/robotics-operator}"
```

First failure triage step: inspect `results/approval.json` and
`logs/provider-events.jsonl` before changing translator or controller code. First rollback step:
keep controller execution disabled, discard the produced action chunks, return to the last approved
translator/checklist bundle, and rerun the offline review before any lab controller hook is
reenabled.

## Optional Runtime Smoke

| Example | Command | Runtime boundary |
| --- | --- | --- |
| `leworldmodel-real-checkpoint-smoke` | `scripts/lewm-real --checkpoint ~/.stable-wm/pusht/lewm_object.ckpt --device cpu` | Requires host-owned `stable_worldmodel`, torch, datasets, OpenCV, imageio, and LeWM checkpoint assets; loads the official LeWorldModel object checkpoint through `stable_worldmodel.policy.AutoCostModel` and prints visual pipeline, tensor, latency, event, and candidate-cost output. |
| `lerobot-leworldmodel-health` | `scripts/robotics-showcase --health-only` | Non-mutating preflight for LeRobot, LeWorldModel, and checkpoint presence before running the full showcase. |
| `lerobot-leworldmodel-real-robotics` | `scripts/robotics-showcase` | Requires host-owned LeRobot, `stable_worldmodel`, torch, datasets, a real policy checkpoint, LeWM checkpoint assets, and PushT simulation dependencies; uses LeRobot's compatible `rerun-sdk` resolution for the default Rerun artifact path, opens a staged Textual report with an `o` shortcut for Rerun, and writes `/tmp/worldforge-robotics-showcase/real-run.rrd` by default. See the [robotics replay showcase walkthrough](./robotics-showcase.md). |

## Operational Commands

```bash
uv run worldforge doctor --registered-only
uv run worldforge world create lab --provider mock
uv run worldforge world add-object <world-id> cube --x 0 --y 0.5 --z 0 --object-id cube-1
uv run worldforge world predict <world-id> --object-id cube-1 --x 0.4 --y 0.5 --z 0
uv run worldforge world list
uv run worldforge world objects <world-id>
uv run worldforge world history <world-id>
uv run worldforge world export <world-id> --output world.json
uv run worldforge world delete <world-id>
uv run worldforge provider list
uv run worldforge provider docs
uv run worldforge provider info mock
uv run worldforge predict kitchen --provider mock --x 0.3 --y 0.8 --z 0.0 --steps 2
uv run worldforge eval --suite planning --provider mock --format json
uv run worldforge benchmark --provider mock --iterations 5 --format json
```

Object add/update/remove commands write typed mutation entries into `world history`; predictions
append their provider action entries after the provider returns the next state.

# Examples And CLI Commands

Use the CLI index for the current runnable examples and optional smoke paths:

```bash
uv run worldforge examples
uv run worldforge examples --format json
```

For the full command surface, see the [CLI Reference](./cli.md).

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

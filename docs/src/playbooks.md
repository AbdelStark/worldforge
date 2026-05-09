# User And Operator Playbooks

These playbooks are for people running WorldForge from a checkout, embedding it in a job or
service, or maintaining provider adapters. Each playbook says when to use it, what to run, what
success looks like, and where to look when it fails.

WorldForge is still a library. It does not own deployment, credential storage, robot safety,
multi-writer persistence, dashboards, or artifact retention. Those remain host responsibilities.

## 1. Bootstrap A Clean Checkout

Use this before changing code, reviewing a provider branch, or reproducing a reported issue.

```bash
uv sync --group dev
uv lock --check
uv run worldforge doctor
uv run worldforge examples
uv run python scripts/generate_provider_docs.py --check
uv run python scripts/check_docs_commands.py
uv run python scripts/check_wrapper_portability.py
uv run mkdocs build --strict
uv run pytest tests/test_cli_help_snapshots.py tests/test_provider_catalog_docs.py
```

Success signal:

- `doctor` shows `mock` registered and reports optional providers as missing or unregistered only
  when their environment variables are absent.
- provider docs are already up to date.
- the MkDocs Material site builds without warnings.
- focused tests pass without live credentials.

If it fails:

| Symptom | First check | Likely owner |
| --- | --- | --- |
| `uv lock --check` fails | dependency files changed without lock refresh | contributor |
| provider docs drift | run `uv run python scripts/generate_provider_docs.py` and inspect diff | contributor |
| optional provider appears registered unexpectedly | check local `.env` and shell environment | operator |
| tests try to reach live services | replace with fixture, fake transport, or injected runtime | contributor |

### 1a. Preserve Checkout-Safe Demo Evidence

Use this when you need a reproducible demo run for a bug report, roadmap issue, release note, or
maintainer review without requiring credentials or optional runtimes.

```bash
uv run python scripts/demo_showcases.py list
uv run python scripts/demo_showcases.py run all --workspace-dir .worldforge/demo-showcases --format json --overwrite
```

Success signal: the top-level status is `passed`; individual workflows are either `passed` or an
intentional `skipped` for a missing optional extra. Each workflow writes
`.worldforge/demo-showcases/<workflow>/workflow-result.json` and a preserved
`.worldforge/demo-showcases/<workflow>/runs/<run-id>/run_manifest.json`.

If it fails:

| Symptom | First check | Likely owner |
| --- | --- | --- |
| `first-run` fails | run `uv run worldforge world preflight --state-dir .worldforge/demo-showcases/first-run/worlds` | contributor |
| diagnostics bundle is not safe to attach | open `issue-bundle/evidence_manifest.json` and inspect excluded files | reporter |
| robotics replay fails | run `uv run worldforge-demo-lerobot` and inspect provider event phases | contributor |
| remote media dry-run leaks a query string | inspect `remote-media-events.json` and the provider-event redaction corpus | contributor |
| batch benchmark status changes | inspect copied budget and benchmark report before editing thresholds | performance maintainer |

The runner does not install LeRobot, LeWorldModel, GR00T, torch, Rerun, checkpoints, simulators, or
provider credentials. It does not make paid API calls, control hardware, or claim physical fidelity.

## 2. Choose The Right Provider Surface

Use this before writing application code or adding an adapter. Start from the operation, not the
provider name.

| Need | Capability | First command |
| --- | --- | --- |
| roll a world state forward from an action | `predict` | `uv run worldforge doctor --capability predict` |
| generate media from text/options | `generate` | `uv run worldforge doctor --capability generate` |
| transform a clip into another clip | `transfer` | `uv run worldforge doctor --capability transfer` |
| rank action candidates | `score` | `uv run worldforge doctor --capability score` |
| select embodied action chunks | `policy` | `uv run worldforge doctor --capability policy` |
| answer typed questions | `reason` | `uv run worldforge doctor --capability reason` |
| embed text | `embed` | `uv run worldforge doctor --capability embed` |

Then inspect the provider profile:

```bash
uv run worldforge provider list
uv run worldforge provider info mock
uv run worldforge provider docs
```

Success signal: the provider advertises exactly the method your workflow calls. If the workflow
needs policy plus scoring, configure one policy provider and one score provider rather than
stretching either adapter into a false capability.

Python integrations can use either a registered full provider or a narrow capability protocol:

```python
from worldforge import ActionScoreResult, WorldForge


class LocalCost:
    name = "local-cost"
    profile = None

    def score_actions(self, *, info, action_candidates):
        return ActionScoreResult(provider=self.name, scores=[0.1], best_index=0)


forge = WorldForge(auto_register_remote=False)
forge.register_cost(LocalCost())
assert forge.doctor(capability="score", registered_only=True).provider_count == 1
```

## 3. Add Or Promote A Provider Adapter

Use this for new provider work and for promoting a scaffold to a real adapter.

```bash
uv run python scripts/scaffold_provider.py "Acme WM" \
  --taxonomy "JEPA latent predictive world model" \
  --implementation-status scaffold \
  --planned-capability score \
  --remote \
  --env-var ACME_WM_API_KEY
```

Before setting any capability flag to `True`, prove the full contract:

- caller inputs are validated before network or model calls where possible.
- upstream outputs are parsed through explicit helpers and malformed fixtures fail.
- supported methods return `PredictionPayload`, `VideoClip`, `ActionScoreResult`,
  `ActionPolicyResult`, `ReasoningResult`, or `EmbeddingResult` as appropriate.
- unsupported methods inherit the `BaseProvider` `ProviderError` behavior.
- `health()` is cheap and reports missing credentials or optional dependencies clearly.
- docs state configuration, runtime ownership, input shape, output schema, limits, failure modes,
  and smoke path.

If the integration is one narrow local surface, prefer a capability protocol implementation instead
of a mostly-empty `BaseProvider` subclass. Register it with `register_cost`, `register_policy`,
`register_generator`, `register_predictor`, `register_reasoner`, `register_embedder`, or
`register_transferer`; it will still appear in `providers()`, `provider_profile(...)`,
`doctor(...)`, planning, and benchmark routing.

Validation:

```bash
uv sync --group dev
uv run ruff check src tests examples scripts
uv run ruff format --check src tests examples scripts
uv run python scripts/generate_provider_docs.py --check
uv run pytest tests/test_provider_contracts.py tests/test_provider_catalog_docs.py
uv run --extra harness pytest --cov=src/worldforge --cov-report=term-missing --cov-fail-under=90
```

Success signal: the provider contract helper passes for supported surfaces, every documented
failure mode has a fixture or fake-runtime test, and the generated provider catalog has no drift.

## 4. Diagnose Provider Availability

Use this when a workflow says a provider is not registered, unhealthy, or missing a capability.

```bash
uv run worldforge doctor
uv run worldforge doctor --registered-only
uv run worldforge doctor --capability score
uv run worldforge provider health
uv run worldforge provider info leworldmodel
```

Read the result this way:

- `doctor` includes known optional providers by default so missing config is visible.
- `--registered-only` shows only providers active in the current process.
- capability filters are strict. A typo such as `generation` raises a framework error rather than
  returning an empty list.
- remote providers usually register from environment variables; injected providers register from
  host code.

If it fails:

| Symptom | Likely cause | Action |
| --- | --- | --- |
| provider is unknown | adapter is not in the catalog or was not manually registered | check `src/worldforge/providers/catalog.py` or host registration |
| provider is known but unregistered | required env vars are missing | load `.env`, export vars, restart process |
| provider is registered but unhealthy | optional dependency, endpoint, or credential is invalid | run provider-specific docs and health command |
| provider lacks capability | capability flag is truthful and workflow picked the wrong provider | choose another provider or implement the capability end to end |

### 4a. Troubleshoot Error Families

Use this matrix when an issue, run manifest, or operator log reports a public WorldForge exception.
Do not catch these errors and continue with coerced state; each family points to a specific owner
and first artifact.

| Error family | Common symptom | Likely owner | First command | Expected artifact or signal | First triage step |
| --- | --- | --- | --- | --- | --- |
| `WorldForgeError` | invalid public input, unknown capability, unsupported output format, non-finite number, unsafe artifact reference | caller or contributor | `uv run worldforge doctor --registered-only` | JSON diagnostics with framework and provider configuration state | fix the caller input or add a regression test for the rejected public boundary |
| `WorldStateError` | corrupted local world JSON, traversal-shaped world id, invalid history entry, incoherent object bounding box | host operator for local state; contributor if the CLI wrote it | `uv run worldforge world preflight --state-dir .worldforge/worlds --workspace-dir .worldforge --format json` | `worldforge-state-preflight.json` with `status`, `safe_to_attach`, `error_count`, and recovery commands | export diagnostics, then quarantine invalid files only after reviewing the report |
| `ProviderError` | missing credentials, missing optional dependency, malformed upstream response, unsupported provider capability, expired artifact URL | host runtime owner first; adapter maintainer if parser or docs are wrong | `uv run worldforge provider info <provider>` | redacted config summary, provider profile, capability flags, health, and typed provider details | attach a sanitized run manifest or issue bundle; never paste raw credentials or signed URLs |
| `AssertionError` from `worldforge.testing` | provider conformance helper reports a contract failure | adapter contributor | `uv run pytest tests/test_provider_contracts.py -q` | explicit helper failure naming the missing capability behavior | fix the adapter or its fixtures; do not replace helper checks with bare `assert` |
| non-zero benchmark budget exit | benchmark gate failed against a JSON budget | release or performance maintainer | `uv run worldforge benchmark --preset mock-smoke --run-workspace .worldforge --format json` | preserved run workspace with `run_manifest.json`, report JSON, and budget status | inspect the budget row and preserved inputs before changing thresholds |
| MkDocs strict warning | bad link, nav drift, or generated docs mismatch | docs contributor | `uv run mkdocs build --strict` | strict build output naming the page or link | sync `mkdocs.yml`, `docs/src/SUMMARY.md`, and source page links |

Public issues should attach `worldforge runs bundle <run-id>` or
`scripts/generate_evidence_bundle.py` output when available. Security-sensitive failures still go
through the private Security tab.

### 4b. Map Health And Readiness During Incidents

Use this when a service host, batch job, or operator dashboard needs to decide whether to send
traffic to a provider-backed workflow. Keep process liveness separate from provider readiness.

| State | Symptom | Likely cause | First command | Expected signal | Escalation point |
| --- | --- | --- | --- | --- | --- |
| process live | `GET /healthz` succeeds, but provider workflows may still fail | HTTP process is running; provider path has not been proven | `curl -fsS http://127.0.0.1:8080/healthz` | JSON status is `live`; no provider fields are implied | host service owner if the process is down |
| provider unconfigured | `/readyz` returns `provider_unconfigured` or `doctor` shows the provider absent from registered providers | missing env vars, missing host injection, or wrong provider name | `uv run worldforge doctor --registered-only` | selected provider is absent; `registered_provider_count` and issues explain the local process | host deployment or credential owner |
| provider unhealthy | `/readyz` returns `provider_unhealthy` or `provider health` reports `healthy=false` | optional runtime missing, bad credentials, unreachable upstream, or failed provider health parsing | `uv run worldforge provider health <name>` | health details name the missing env var, dependency, endpoint, or sanitized upstream error | host runtime owner first; provider adapter maintainer if details are wrong or unsafe |
| upstream degraded | provider health is intermittently false, provider events show retries, 5xx, 429, or budget exhaustion | remote provider outage, throttling, expired credentials, or host budget too tight | `jq 'select(.phase=="retry" or .phase=="budget_exceeded") | {provider, operation, status_code, target, message}' .worldforge/runs/<run-id>/provider-events.jsonl` | sanitized targets, retry counts, status class, and `budget_exceeded` events identify the failing operation | upstream provider support or host SRE; WorldForge does not own upstream SLA |
| workflow failing | `/readyz` stays `ready`, but one request returns a typed error | malformed world state, unsupported capability, invalid input, parser failure, or expired artifact | `uv run worldforge provider info <name>` | profile, capability flags, redacted config summary, and health show whether the request matched the provider contract | application owner for bad input; adapter maintainer for parser/contract bugs |

The stdlib service reference uses the same model: `/healthz` is process-only liveness, while
`/readyz` returns `ready`, `provider_unconfigured`, or `provider_unhealthy` plus a `traffic`
decision of `accept` or `drain`. Alert routing, paging policy, retry orchestration outside a single
provider call, and upstream SLA ownership remain host responsibilities.

## 4c. Deploy Reference Hosts

Use this before handing the stdlib service host, batch evaluation host, or robotics operator host to
another host process owner.

```bash
uv run python examples/hosts/service/app.py --provider mock --port 8080
uv run python examples/hosts/batch-eval/app.py benchmark --provider mock --operation generate --iterations 1
uv run python examples/hosts/robotics-operator/app.py review --sample-translator --approve-dry-run \
  --check workspace_clear --check emergency_stop_available --check operator_present --check controller_isolated
```

Success signal: the service host returns `/readyz` with `status: ready` and `traffic: accept`; the
batch host prints `status: passed` and a `run_manifest`; the robotics operator host prints
`status: passed`, a `run_manifest`, and `controller_executed: false`.

If it fails: use the [Reference Host Deployment Recipes](./examples.md#reference-host-deployment-recipes)
first. They include env templates, process commands, readiness commands, smoke commands, logging
commands, evidence export commands, and first rollback or triage steps for checkout-safe,
prepared-host, credentialed, GPU-bound, and robotics-lab paths. Deployment, auth, queueing,
durable storage, controller integration, alerting, uptime, and safety certification stay
host-owned.

## 4d. Rehearse Operator Failure Drills

Use this before relying on an incident runbook. The drills are deterministic and checkout-safe; each
one writes a preserved run manifest under a temporary or documented workspace and records the
expected failure plus recovery command.

```bash
uv run worldforge drills list
uv run worldforge drills run missing-credentials --workspace-dir .worldforge/drills
uv run worldforge drills run unsafe-event-metadata --workspace-dir .worldforge/drills --bundle
uv run worldforge drills run all --workspace-dir .worldforge/drills
```

| Drill | Expected failure | Recovery command |
| --- | --- | --- |
| `missing-credentials` | required provider credentials are absent in a value-free config summary | load the required env var, then run `uv run worldforge provider health runway` |
| `missing-optional-dependency` | optional runtime import is missing | install the provider optional runtime on a prepared host, then rerun its smoke command |
| `malformed-provider-output` | the Runway task parser rejects a fixture without a task id | attach the sanitized fixture and fix the parser or upstream contract |
| `budget-violation` | a mock benchmark violates an intentionally impossible latency budget | inspect the run bundle, then rerun `uv run worldforge benchmark --provider mock --operation predict --iterations 1` |
| `corrupted-world-state` | a malformed local world JSON file raises `WorldStateError` | export diagnostics, quarantine the bad file, then recreate or import a valid world |
| `expired-artifact` | an artifact descriptor has an expiry timestamp in the past | rerun the provider workflow to refresh the artifact, then export a new issue bundle |
| `unsafe-event-metadata` | non-JSON-native event metadata is rejected and secret-shaped fields are redacted | remove object or tuple metadata, keep JSON-native fields only, then rerun the workflow |

Success signal: the drill command exits `0`, prints `status: passed`, and writes a run manifest
whose status is `failed` because the rehearsed incident was observed. With `--bundle`, the command
also writes `.worldforge/drills/issue-bundles/<run-id>/issue.md`.

If it fails unexpectedly: inspect `<workspace>/runs/<run-id>/results/drill.json` first, then run
`uv run worldforge runs bundle <run-id> --workspace-dir <workspace>` before changing fixtures.
Drills must not mutate user worlds; corrupted-state input files are written under the drill run's
workspace.

## 5. Operate Local JSON Persistence

Use this for local jobs, demos, tests, and single-writer workflows.

CLI:

```bash
uv run worldforge world create lab --provider mock
uv run worldforge world create seeded-lab --provider mock --prompt "A kitchen with a mug"
uv run worldforge world add-object <world-id> cube --x 0 --y 0.5 --z 0 --object-id cube-1
uv run worldforge world update-object <world-id> cube-1 --x 0.2 --y 0.5 --z 0 --graspable true
uv run worldforge world predict <world-id> --object-id cube-1 --x 0.4 --y 0.5 --z 0
uv run worldforge world list
uv run worldforge world objects <world-id>
uv run worldforge world show <world-id>
uv run worldforge world history <world-id>
uv run worldforge world preflight --state-dir .worldforge/worlds --workspace-dir .worldforge
uv run worldforge world export <world-id> --output world.json
uv run worldforge world import world.json --new-id --name lab-copy
uv run worldforge world fork <world-id> --history-index 0 --name lab-start
uv run worldforge world delete <world-id>
```

Python:

```python
from worldforge import WorldForge

forge = WorldForge(state_dir=".worldforge/worlds")
world = forge.create_world("lab", provider="mock")
world_id = forge.save_world(world)

payload = forge.export_world(world_id)
restored = forge.import_world(payload, new_id=True, name="lab-copy")
forge.save_world(restored)
forge.delete_world(world_id)
```

Success signal:

- world IDs are file-safe local identifiers.
- saved JSON validates before it replaces the destination file.
- the CLI create/import/fork/object/predict commands save through the same validation path as Python
  `save_world(...)`.
- object add/update/remove commands append explicit history entries with typed `Action` payloads,
  and position updates translate object bounding boxes with the new pose.
- `world delete` and `WorldForge.delete_world(...)` validate the world id before unlinking the local
  JSON file and raise `WorldStateError` when the file is already absent.
- `world predict` persists the provider-updated state by default; use `--dry-run` to inspect a
  prediction without replacing the local JSON file.
- imported state rejects malformed scene objects, invalid history, negative steps, and traversal
  shaped IDs.
- `world preflight` reports corrupted world JSON, traversal-shaped requested IDs, invalid history
  entries, incoherent object bounding boxes, stale run workspaces, unsafe artifact paths, and
  retention pressure without mutating local files.

Recovery guidance:

- run `uv run worldforge world preflight --state-dir .worldforge/worlds --workspace-dir .worldforge
  --format json > worldforge-state-preflight.json` before moving or deleting any local state.
- if local JSON is corrupted, restore from the host application's backup of exported world JSON.
- if the report names stale run workspaces or unsafe artifact paths, export a run bundle when a
  manifest is valid; otherwise quarantine the run directory after preserving the preflight report.
- if retention pressure is the only issue, run `uv run worldforge runs cleanup --workspace-dir
  .worldforge --keep 20 --dry-run` and remove evidence only after incident or release references
  no longer need it.
- if multiple workers need writes, move persistence into host-owned storage with locking,
  migrations, backups, and recovery drills.
- do not add a lock file, SQLite store, or service adapter to WorldForge without the
  [persistence adapter ADR](./adr/0001-persistence-adapter-boundary.md).

### 5a. Manage Worlds From TheWorldHarness

The Worlds screen in TheWorldHarness is the keyboard-first mirror of the `worldforge world`
CLI. Launch the harness and press `g w` (or pick "Jump: Worlds" from `Ctrl+P`):

```bash
uv run --extra harness worldforge-harness
```

Bindings mirror the CLI commands exactly: `n` maps to `worldforge world create`, `Enter`
opens the editor (`world show` + `add-object` + `update-object`), `d` calls
`WorldForge.delete_world(...)`, `f` maps to `world fork`, and `/` narrows the table by id or
name substring. Every write or unlink goes through `WorldForge` on a
`@work(thread=True, group="persistence")` worker; no JSON is hand-written. Validation errors
raised by the framework (`WorldStateError` / `WorldForgeError`) appear as toasts — the
in-memory edit buffer stays intact so the user can fix and retry.

### 5b. Capture Run-Scoped Provider Logs

Use this when a CLI job, batch host, service request, or TheWorldHarness run needs provider events
that can be attached to an issue, release bundle, or incident note.

For one failed preserved run, export the issue-ready bundle before posting:

```bash
uv run worldforge harness --runs --status failed --artifact-type json
uv run worldforge runs bundle <run-id> \
  --workspace-dir .worldforge \
  --output .worldforge/issue-bundles/<run-id>
```

Success signal: `worldforge harness --runs` lists the failed run with a sanitized rerun command and
the same `worldforge runs bundle <run-id>` recovery command shown in the Runs screen. The bundle
command writes `evidence_manifest.json`, `summary.md`, and `issue.md`, then prints a short issue
template with the command, expected signal, observed failure, artifact list, `safe_to_attach`
status, and first triage step. If `safe_to_attach` is `false`, inspect the manifest's excluded and
`local_only` entries before attaching anything.

```python
from pathlib import Path

from worldforge import WorldForge
from worldforge.observability import JsonLoggerSink, RunJsonLogSink, compose_event_handlers

run_id = "20260430T120000Z-runway-generate"
log_path = Path(".worldforge") / "runs" / run_id / "provider-events.jsonl"

forge = WorldForge(
    event_handler=compose_event_handlers(
        JsonLoggerSink(extra_fields={"run_id": run_id, "host": "service"}),
        RunJsonLogSink(log_path, run_id=run_id, extra_fields={"host": "service"}),
    )
)
```

Success signal:

- each line in `provider-events.jsonl` is a complete JSON object.
- every record has `event_type=provider_event` and the same `run_id` as the host run manifest.
- `target` values keep only route-level context; URL query strings and fragments are removed.
- `message`, `metadata`, and sink `extra_fields` redact bearer tokens, API keys, signatures,
  passwords, signed URLs, and token-like assignments.
- host applications inject sinks into `WorldForge(event_handler=...)` or provider constructors
  instead of changing global logging configuration inside WorldForge.

First triage queries:

```bash
jq 'select(.phase=="failure") | {provider, operation, status_code, target, message}' \
  .worldforge/runs/<run-id>/provider-events.jsonl
jq 'select(.phase=="retry") | {provider, operation, attempt, max_attempts, status_code, target}' \
  .worldforge/runs/<run-id>/provider-events.jsonl
jq -s 'group_by(.provider,.operation)[] | {provider: .[0].provider, operation: .[0].operation, events: length}' \
  .worldforge/runs/<run-id>/provider-events.jsonl
```

For optional live smokes, preserve the manifest beside the event log:

```bash
scripts/robotics-showcase \
  --json-output .worldforge/runs/<run-id>/real-run.json \
  --run-manifest .worldforge/runs/<run-id>/run_manifest.json
jq '{run_id, provider_profile, capability, status, event_count, artifact_paths}' \
  .worldforge/runs/<run-id>/run_manifest.json
```

If it fails:

| Symptom | First check | Likely owner |
| --- | --- | --- |
| no file was written | confirm the host passed `RunJsonLogSink` into the active event handler | host app |
| records have different run IDs | compare sink construction with the run manifest writer | host app |
| raw credential appears in an exported log | remove the raw value from custom metadata or exception text and add a regression test | contributor |
| failures have no status code | inspect provider-specific docs; local dependency failures may not have HTTP status | operator |

## 6. Run Evaluation And Benchmarks

Use evaluation for deterministic behavior checks and benchmarks for adapter latency and event
shape. Do not treat either as a physical-fidelity claim.

```bash
uv run worldforge eval --suite planning --provider mock --format markdown
uv run worldforge eval --suite generation --provider mock --format json
uv run worldforge benchmark --provider mock --iterations 5 --format markdown
uv run worldforge benchmark --provider mock --iterations 5 --format json
uv run worldforge benchmark --provider mock --operation embed --input-file examples/benchmark-inputs.json
uv run worldforge benchmark --provider mock --operation generate --budget-file examples/benchmark-budget.json
```

Success signal:

- suites skip or fail explicitly when a provider does not support the required capability.
- benchmark reports identify provider, operation, pass/fail status, latency, retry counts, and
  exported artifact format for direct provider surfaces such as `score`, `policy`, `generate`,
  `transfer`, and `embed`.
- benchmark budget files fail non-zero when success rate, error count, retry count, latency, or
  throughput thresholds regress.
- `--input-file` fixtures reproduce benchmark inputs for prediction, generation, transfer,
  embedding, score, and policy runs. The checked-in fixture is checkout-safe for `mock`
  `predict`, `generate`, `transfer`, and `embed`; its score and policy fields are provider-specific
  inputs for providers that advertise those capabilities. Transfer clip paths resolve relative to
  the fixture file.
- benchmark input files and result JSON are saved by the host when they are used for release or
  paper claims.

If a score changes, first check provider capability, test fixture changes, input data, and retry
events. Do not rewrite claims around a one-off run without preserving the run artifact.

When a preserved benchmark baseline justifies a budget update, generate review artifacts instead
of editing release budgets directly:

```bash
uv run python scripts/calibrate_benchmark_budgets.py \
  --report .worldforge/reports/benchmark-<timestamp>-<run-id>.json \
  --current-budget src/worldforge/benchmark_presets/_data/budget-release-evidence.json \
  --output .worldforge/benchmark-calibration/release-evidence-candidate
```

Success signal: `candidate-budgets.json` loads through the benchmark budget parser, and
`budget-calibration.md` shows source report digests, machine class, old threshold, candidate
threshold, observed baseline, and rationale. First triage step on an unexpected candidate is to
rerun the preserved benchmark command on the same machine class and compare report digests before
loosening any release gate.

### 6a. Preserve Harness Reports

TheWorldHarness Eval and Benchmark screens preserve completed reports automatically under the
active state directory:

```text
.worldforge/reports/eval-<suite>-<timestamp>-<run-id>.json
.worldforge/reports/benchmark-<timestamp>-<run-id>.json
```

The JSON is written through the same renderer used by the `worldforge eval` and `worldforge
benchmark` commands. Markdown and CSV previews in the TUI are regenerated from the same report
object, so a screenshot and the saved JSON point at the same numbers. Use the path printed in the
success toast whenever a benchmark or evaluation result is cited in a PR, release note, paper, or
slide.

First triage step for a surprising number: open the saved JSON, confirm the provider and
operation/suite, then rerun the matching CLI command with the same provider and operation.

### 6b. Record A Rerun Inspection Artifact

Use Rerun when you need a visual, time-indexed inspection artifact for provider events, world
state, plans, and benchmark metrics:

```bash
uv run --extra rerun worldforge-demo-rerun
uv run --extra rerun rerun .worldforge/rerun/worldforge-rerun-showcase.rrd
```

Success signal: the `.rrd` file contains provider event text logs, world snapshots, plan payloads,
3D object/target markers, and mock benchmark metrics. First triage step: verify the optional SDK
is available with `uv run --extra rerun python -c "import rerun; print(rerun.__version__)"`.

For the real PushT policy+score showcase, the wrapper writes a Rerun artifact by default:

```bash
scripts/robotics-showcase
uvx --from "rerun-sdk>=0.24,<0.32" rerun /tmp/worldforge-robotics-showcase/real-run.rrd
```

Success signal: the recording contains candidate target points, selected replay lines, score bars,
latency bars, provider events, world snapshots, and the plan payload. Use `--no-rerun` for runs
where only the TUI/JSON artifact is needed. In the robotics TUI, press `o` to open the persisted
Rerun recording directly.

## 7. Handle Remote Media Artifacts

Use this for Cosmos, Runway, or any future media adapter.

Preflight:

```bash
uv run worldforge doctor --capability generate
uv run worldforge provider info runway
uv run worldforge provider health runway
```

Operational rules:

- create-style requests are single-attempt unless the provider contract is idempotent.
- health, polling, and downloads can retry through `ProviderRequestPolicy`.
- `timeout_seconds` is a per-attempt request timeout; `max_elapsed_seconds` is the host's
  workflow budget for the operation, including retries, backoff, and poll intervals.
- budget failures raise `ProviderBudgetExceededError` and emit `phase=="budget_exceeded"` so
  alerts can distinguish an exhausted host budget from an upstream HTTP failure.
- returned artifacts are validated before `VideoClip` is returned.
- provider-returned artifact URLs are treated as untrusted input: HTTP(S) only, no embedded
  credentials, no local/private/link-local destinations by default, and streamed with a maximum
  byte cap.
- signed URLs and temporary artifact URLs are not durable storage. Download or persist them in
  host-owned storage immediately after completion.
- provider errors should include operation and provider context without leaking credentials,
  bearer tokens, or signed URLs.
- provider event `target` values are sanitized for logs: use them to identify the endpoint or
  artifact path, not to recover a full signed URL.

If artifact download fails, inspect provider events for `operation`, `phase`, `status_code`,
`attempt`, and sanitized `target`, then rerun with a fresh task when the URL has expired.

## 8. Run Optional Runtime Smokes

Use checkout-safe demos first. Use real runtime smokes only in a host environment that has the
model, checkpoint, CUDA or robot stack, and task-specific preprocessing.

Checkout-safe:

```bash
uv run pytest
uv run pytest -m "not live"
uv run worldforge-demo-leworldmodel
uv run worldforge-demo-lerobot
uv run --extra harness worldforge-harness --flow diagnostics
```

Runtime pytest profiles are opt-in. Mark live provider tests with the smallest truthful set of
markers, for example `@pytest.mark.live`, `@pytest.mark.network`,
`@pytest.mark.credentialed`, `@pytest.mark.gpu`, `@pytest.mark.robotics`, and
`@pytest.mark.provider_profile("runway")`. Default `uv run pytest` skips marked tests before they
can reach live endpoints, GPUs, robot stacks, credentials, or downloaded checkpoints.

Prepared-host provider profiles:

```bash
# Cosmos: requires COSMOS_BASE_URL and a reachable deployment.
COSMOS_BASE_URL=http://localhost:8000 \
  uv run pytest -m "live and network and provider_profile" \
    --run-live --run-network --provider-profile cosmos

COSMOS_BASE_URL=http://localhost:8000 \
  uv run worldforge-smoke-cosmos \
    --output .worldforge/runs/cosmos-live/artifacts/cosmos.mp4 \
    --summary-json .worldforge/runs/cosmos-live/results/summary.json \
    --run-manifest .worldforge/runs/cosmos-live/run_manifest.json

# Cosmos-Policy: requires COSMOS_POLICY_BASE_URL and a reachable ALOHA /act server.
COSMOS_POLICY_BASE_URL=http://127.0.0.1:8777 \
COSMOS_POLICY_ALLOW_LOCAL_BASE_URL=1 \
  uv run pytest -m "live and network and robotics and provider_profile" \
    --run-live --run-network --run-robotics --provider-profile cosmos-policy
# Expected success: pytest completes the selected live profile without failures.
# First triage: run `uv run worldforge provider health cosmos-policy` to confirm
# configuration only; use the smoke command below to verify `/act` reachability.

COSMOS_POLICY_BASE_URL=http://127.0.0.1:8777 \
COSMOS_POLICY_ALLOW_LOCAL_BASE_URL=1 \
  uv run worldforge-smoke-cosmos-policy \
    --health-only \
    --run-manifest .worldforge/runs/cosmos-policy-health/run_manifest.json
# Expected success: run_manifest.json records capability=policy with status=skipped.
# First triage: run `uv run worldforge provider health cosmos-policy` to confirm
# configuration only, then use the full `/act` smoke below for endpoint behavior.

COSMOS_POLICY_BASE_URL=http://127.0.0.1:8777 \
COSMOS_POLICY_ALLOW_LOCAL_BASE_URL=1 \
  uv run worldforge-smoke-cosmos-policy \
    --policy-info-json /path/to/policy_info.json \
    --translator /path/to/translator.py:translate_actions \
    --allow-translator-code \
    --run-manifest .worldforge/runs/cosmos-policy-live/run_manifest.json
# Expected success: run_manifest.json records capability=policy with status=passed.
# First triage: verify the `/act` server is reachable and recheck the translator path plus
# policy_info.json shape.

# Cosmos-Policy remote GPU checklist:
#
# 1. Use a prepared Linux/NVIDIA host that can run the upstream Cosmos-Policy server.
#    Current ALOHA Predict2 smokes should start from a 48 GB or larger GPU memory class unless
#    the upstream requirements are stricter.
# 2. Keep checkpoints, model approvals, CUDA, Docker, and Hugging Face/NVIDIA tokens on the host.
#    WorldForge should only see the `/act` endpoint and sanitized run evidence.
# 3. Prefer an SSH tunnel to `127.0.0.1:8777`. If the server is exposed directly, restrict
#    inbound TCP 8777 to the operator IP or VPN CIDR and set `COSMOS_POLICY_ALLOWED_HOSTS`.
# 4. Run health-only first. It validates WorldForge configuration only; it does not prove `/act`
#    inference because the targeted upstream server has no non-mutating health endpoint.
# 5. Run the full smoke with prepared ALOHA policy info and a trusted translator. Expected success
#    is `run_manifest.json` with capability=policy, status=passed, and a non-empty action shape
#    such as 50 x 14.
# 6. Preserve only sanitized evidence. Do not commit raw images, tokens, checkpoints, Docker
#    layers, or GPU logs with secrets. Hibernate or terminate the GPU host when finished.

# Runway: requires RUNWAYML_API_SECRET or RUNWAY_API_SECRET.
RUNWAYML_API_SECRET=... \
  uv run pytest -m "live and network and credentialed and provider_profile" \
    --run-live --run-network --run-credentialed --provider-profile runway

# LeWorldModel: requires LEWORLDMODEL_POLICY or LEWM_POLICY and host-owned runtime deps.
LEWORLDMODEL_POLICY=pusht/lewm \
  uv run pytest -m "live and gpu and provider_profile" \
    --run-live --run-gpu --provider-profile leworldmodel

# GR00T: requires GROOT_POLICY_HOST and a reachable policy server.
GROOT_POLICY_HOST=127.0.0.1 \
  uv run pytest -m "live and network and robotics and provider_profile" \
    --run-live --run-network --run-robotics --provider-profile gr00t
# Expected success: pytest completes the selected live profile without failures.
# First triage: run `uv run worldforge provider health gr00t` to confirm client
# configuration and server reachability.

GROOT_POLICY_HOST=127.0.0.1 \
GROOT_POLICY_PORT=5555 \
  uv run --with msgpack --with pyzmq --with numpy python scripts/smoke_gr00t_policy.py \
    --health-only \
    --run-manifest .worldforge/runs/gr00t-health/run_manifest.json
# Expected success: run_manifest.json records capability=policy with status=skipped.
# First triage: confirm the remote PolicyClient server is reachable before sending
# observation data.

GROOT_POLICY_HOST=127.0.0.1 \
GROOT_POLICY_PORT=5555 \
  uv run --with msgpack --with pyzmq --with numpy python scripts/smoke_gr00t_policy.py \
    --policy-info-json /path/to/policy_info.json \
    --translator /path/to/translator.py:translate_actions \
    --allow-translator-code \
    --run-manifest .worldforge/runs/gr00t-live/run_manifest.json
# Expected success: run_manifest.json records capability=policy with status=passed.
# First triage: recheck the observation shape, translator import path, and remote
# server logs.

# LeRobot: requires LEROBOT_POLICY_PATH or LEROBOT_POLICY and host-owned policy deps.
LEROBOT_POLICY_PATH=lerobot/diffusion_pusht \
  uv run pytest -m "live and robotics and provider_profile" \
    --run-live --run-robotics --provider-profile lerobot
```

When a test is selected without the matching opt-in flag or provider environment, pytest reports a
skip reason naming the missing flag or environment variable. Save stdout/stderr, JSON summaries, and
provider-event logs from prepared-host runs when the result is used as release or issue evidence.

Real LeWorldModel checkpoint:

```bash
scripts/lewm-real \
  --checkpoint ~/.stable-wm/pusht/lewm_object.ckpt \
  --device cpu
```

Equivalent explicit `uv` command:

```bash
uv run --python 3.13 \
  --with "stable-worldmodel @ git+https://github.com/galilai-group/stable-worldmodel.git" \
  --with "datasets>=2.21" \
  --with "opencv-python" \
  --with "imageio" \
  lewm-real \
    --checkpoint ~/.stable-wm/pusht/lewm_object.ckpt \
    --device cpu
```

The wrapper runs `uv run --python 3.13` with the upstream `stable-worldmodel`, `datasets`, OpenCV,
and imageio runtime requirements, then invokes the packaged `lewm-real` alias.
`stable-worldmodel` is the official LeWorldModel loading/evaluation runtime used by `lucas-maes/le-wm`;
`LeWorldModelProvider` loads the LeWM object checkpoint through
`stable_worldmodel.policy.AutoCostModel`. The live smoke prints what the run demonstrates, a visual
pipeline, tensor shapes, latency metrics, provider events, and a ranked candidate cost landscape.
It exits non-zero before inference if the checkpoint, optional runtime, or provider health check is
missing. Use `--json-only` for the machine-readable result payload, or `--json-output
lewm-real-summary.json` to write the same run data while keeping the visual output.

The live smoke uses deterministic synthetic PushT-shaped tensors. It proves the checkpoint loads
and scores candidates through the WorldForge provider contract; it does not prove task-specific
preprocessing or robot execution.

LeRobot policy plus LeWorldModel checkpoint scoring replay:

```bash
scripts/robotics-showcase
```

The showcase wrapper installs the host-owned optional runtime set for this process, runs the
packaged PushT bridge, opens a Textual visual report with the policy-to-score pipeline, runtime
bars, tensor metrics, staged reveal messages, an illustrative animated robot-arm replay, full-width
candidate ranking, provider events, and tabletop replay map, then writes the full JSON summary under
`/tmp/worldforge-robotics-showcase/real-run.json`. Pass `--tui-stage-delay <seconds>` to tune the
reveal pace, `--no-tui-animation` to disable sleeps and arm motion, `--no-tui` for the plain
terminal report, `--json-only` for automation, or `--health-only` for a dependency preflight. It
requests `lerobot[transformers-dep]==0.5.1` so the Python 3.13 policy import path is stable while
the LeWorldModel runtime is installed, and filters common macOS native-library duplicate class
warnings from the user-facing output while leaving runtime device fallback warnings visible. The
`--health-only` path does not auto-build or download missing LeWorldModel checkpoints; it reports
whether the checkpoint is present and exits before inference. Set `WORLDFORGE_SHOW_RUNTIME_WARNINGS=1`
to see raw third-party stderr.

Prepared-host CI uses `.github/workflows/robotics-showcase.yml` for this path on every pull
request update and on pushes to `main`. That workflow keeps the run non-interactive with
`--json-only --no-tui --no-rerun`, writes a JSON summary plus `run_manifest.json`, and verifies the
real `lerobot.policy` and `leworldmodel.score` success events. Use `actions/cache` for Hugging
Face policy downloads, LeWorldModel config/weights assets, and the built LeWorldModel object
checkpoint. Checkpoint artifacts are not uploaded; normal CI artifacts should be run evidence, not
reusable checkpoint storage.

Use the lower-level runner when replacing the task observation, score tensors, translator, or
candidate bridge:

```bash
scripts/lewm-lerobot-real \
  --policy-path lerobot/diffusion_pusht \
  --policy-type diffusion \
  --checkpoint ~/.stable-wm/pusht/lewm_object.ckpt \
  --device cpu \
  --mode select_action \
  --observation-module /path/to/pusht_obs.py:build_observation \
  --score-info-npz /path/to/lewm_score_tensors.npz \
  --translator worldforge.smoke.lerobot_leworldmodel:translate_pusht_xy_actions \
  --candidate-builder /path/to/pusht_lewm_bridge.py:build_action_candidates \
  --expected-action-dim 10 \
  --expected-horizon 4
```

Equivalent explicit `uv` command:

```bash
uv run --python 3.13 \
  --with "stable-worldmodel @ git+https://github.com/galilai-group/stable-worldmodel.git" \
  --with "datasets>=2.21" \
  --with "huggingface_hub" \
  --with "hydra-core" \
  --with "omegaconf" \
  --with "matplotlib" \
  --with "transformers" \
  --with "lerobot[transformers-dep]==0.5.1" \
  --with "textual>=8.2,<9" \
  --with "pygame" \
  --with "opencv-python" \
  --with "imageio" \
  --with "pymunk" \
  --with "gymnasium" \
  --with "shapely" \
  worldforge-robotics-showcase --tui
```

Equivalent explicit `uv` command for the lower-level runner:

```bash
uv run --python 3.13 \
  --with "stable-worldmodel @ git+https://github.com/galilai-group/stable-worldmodel.git" \
  --with "datasets>=2.21" \
  --with "opencv-python" \
  --with "imageio" \
  --with "lerobot[transformers-dep]==0.5.1" \
  lewm-lerobot-real \
    --policy-path lerobot/diffusion_pusht \
    --policy-type diffusion \
    --checkpoint ~/.stable-wm/pusht/lewm_object.ckpt \
    --device cpu \
    --mode select_action \
    --observation-module /path/to/pusht_obs.py:build_observation \
    --score-info-npz /path/to/lewm_score_tensors.npz \
    --translator worldforge.smoke.lerobot_leworldmodel:translate_pusht_xy_actions \
    --candidate-builder /path/to/pusht_lewm_bridge.py:build_action_candidates
```

This flow demonstrates robotics-builder composition: LeRobot proposes policy action candidates,
LeWorldModel ranks checkpoint-native candidate tensors, and WorldForge selects and mock-executes the
lowest-cost chunk through `World.plan(..., planning_mode="policy+score")`. The packaged
`scripts/robotics-showcase` command owns the PushT demonstration bridge; any other task still needs
a host-owned observation builder and candidate bridge. If the LeRobot raw action dimension or horizon
does not match the LeWorldModel checkpoint contract, provide a task-specific bridge instead of
padding or projecting actions.

GR00T and LeRobot live smokes:

```bash
uv run python scripts/smoke_gr00t_policy.py --help
uv run python scripts/smoke_lerobot_policy.py --help
```

Success signal: the demo or smoke states whether it used injected deterministic runtime, real
checkpoint inference, remote policy server, provider events, persistence, and reload. Do not
describe an injected demo as real neural inference.

## 9. Prepare A Release Or Public Branch

Use this before publishing a package, merging provider work, or pushing a milestone.

```bash
uv sync --group dev
uv lock --check
uv run ruff check src tests examples scripts
uv run ruff format --check src tests examples scripts
uv run python scripts/generate_provider_docs.py --check
uv run python scripts/check_docs_commands.py
uv run python scripts/check_wrapper_portability.py
uv run python scripts/check_core_performance.py
uv run mkdocs build --strict
uv run pytest
uv run --extra harness pytest --cov=src/worldforge --cov-report=term-missing --cov-fail-under=90
bash scripts/test_package.sh
uv build --out-dir dist --clear --no-build-logs
shasum -a 256 dist/worldforge_ai-*.whl dist/worldforge_ai-*.tar.gz
```

The package contract checks both distribution artifacts: the wheel must contain only runtime package
files, the `py.typed` marker, capability protocols, observable capability wrapper, and console
scripts; the sdist must contain docs, tests, examples, scripts, and release metadata needed to
rebuild and audit the source package.

Run the core performance budget gate with a preserved workspace before claiming release
readiness:

```bash
uv run python scripts/check_core_performance.py \
  --workspace-dir .worldforge/core-performance \
  --output .worldforge/core-performance/core-performance.json
```

Success signal: `core-performance.json` has `passed: true` and result rows for world persistence,
benchmark fixture loading, provider catalog diagnostics, evidence-bundle creation, and report
rendering. First triage step: inspect the failing row's artifact path and rerun the single changed
code path before loosening a budget. The report is a local regression guard, not a public
performance claim.

Run the wrapper portability checker whenever shell wrappers, optional-runtime smoke commands, or
documented host commands change:

```bash
uv run python scripts/check_wrapper_portability.py
```

Success signal: every wrapper row passes, including `scripts/robotics-showcase`, LeWorldModel
wrappers, GR00T and LeRobot smoke helpers, and `scripts/test_package.sh`. First triage step: repair
the exact script named in the failure before editing docs around it.

Then run the locked dependency audit:

```bash
tmp_req="$(mktemp requirements-audit.XXXXXX)"
uv export --frozen --all-groups --no-emit-project --no-hashes -o "$tmp_req" >/dev/null
uvx --from pip-audit pip-audit -r "$tmp_req" --no-deps --disable-pip --progress-spinner off
rm -f "$tmp_req"
```

Finally generate the release-readiness evidence. This command writes
`.worldforge/release-evidence/release-evidence.md` and
`.worldforge/release-evidence/release-evidence.json`; add `--run-gates` when the evidence run
should execute the checkout-safe gates itself.

```bash
uv run python scripts/generate_evidence_bundle.py \
  --workspace-dir .worldforge \
  --output .worldforge/evidence-bundles/release-candidate
uv run python scripts/generate_release_evidence.py \
  --run-gates \
  --live-smoke-registry docs/src/live-smoke-evidence.json \
  --run-manifest .worldforge/runs/<run-id>/run_manifest.json \
  --artifact .worldforge/evidence-bundles/release-candidate/evidence_manifest.json \
  --benchmark-artifact .worldforge/reports/benchmark-<timestamp>-<run-id>.json \
  --artifact dist/worldforge_ai-<version>-py3-none-any.whl
```

The generator does not require provider credentials; optional live smokes without linked manifests
are listed explicitly as `host-owned`, the registry records missing-runtime and missing-credential
skips, and passed/failed/skipped live runs link back to their preserved `run_manifest.json` files
and artifact summaries. Gate rows are explicit `passed`, `failed`, or `skipped` and include the
first triage step. Use `--known-limitation` for release-scoped caveats that should travel with the
bundle.

Success signal:

- validation passes from a clean checkout.
- generated provider docs have no drift and the Pages site builds in strict mode.
- release evidence links validation expectations, optional live-smoke manifests, benchmark
  artifacts, generated evidence bundles, distribution artifacts, JSON summaries, first triage
  steps, and known limitations.
- README, docs, changelog, and `AGENTS.md` reflect public behavior.
- no optional runtime dependency, checkpoint, credential, generated artifact, or `.env` file is
  committed accidentally.

## 10. Triage Incidents And Regressions

Use this as the first stop when a user reports a failure.

| Reported failure | First command | Evidence to capture | Usual fix path |
| --- | --- | --- | --- |
| provider missing | `uv run worldforge doctor` | registered providers, required env vars | environment or catalog registration |
| provider unhealthy | `uv run worldforge provider health <name>` | health details, optional dependency versions | host runtime setup or provider health code |
| unsupported capability | `uv run worldforge doctor --capability <capability>` | provider profile and workflow call | choose correct provider or implement capability |
| persistence load failed | reproduce `load_world` with saved JSON | failing JSON, world ID, state dir | restore from backup or fix importer validation |
| remote media failed | provider events and provider-specific docs | status code, attempt, sanitized target | parser, retry policy, artifact handling, or host credentials |
| optional runtime smoke failed | smoke command and `--help` output | host OS, dependency path, checkpoint path | host runtime setup; do not add heavy deps to base package |
| coverage failed | `uv run --extra harness pytest --cov=src/worldforge --cov-report=term-missing --cov-fail-under=90` | missing lines and changed files | add behavior tests, especially error paths |

Do not paper over a failure by widening docs or loosening a capability. Fix the contract or make
the limitation explicit.

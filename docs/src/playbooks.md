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
uv run pytest tests/test_cli_help_snapshots.py tests/test_provider_catalog_docs.py
```

Success signal:

- `doctor` shows `mock` registered and reports optional providers as missing or unregistered only
  when their environment variables are absent.
- provider docs are already up to date.
- focused tests pass without live credentials.

If it fails:

| Symptom | First check | Likely owner |
| --- | --- | --- |
| `uv lock --check` fails | dependency files changed without lock refresh | contributor |
| provider docs drift | run `uv run python scripts/generate_provider_docs.py` and inspect diff | contributor |
| optional provider appears registered unexpectedly | check local `.env` and shell environment | operator |
| tests try to reach live services | replace with fixture, fake transport, or injected runtime | contributor |

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

## 3. Add Or Promote A Provider Adapter

Use this for new provider work and for promoting a scaffold to a real adapter.

```bash
uv run python scripts/scaffold_provider.py "Acme WM" \
  --taxonomy "JEPA latent predictive world model" \
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
uv run worldforge world export <world-id> --output world.json
uv run worldforge world import world.json --new-id --name lab-copy
uv run worldforge world fork <world-id> --history-index 0 --name lab-start
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
```

Success signal:

- world IDs are file-safe local identifiers.
- saved JSON validates before it replaces the destination file.
- the CLI create/import/fork/object/predict commands save through the same validation path as Python
  `save_world(...)`.
- `world predict` persists the provider-updated state by default; use `--dry-run` to inspect a
  prediction without replacing the local JSON file.
- imported state rejects malformed scene objects, invalid history, negative steps, and traversal
  shaped IDs.

Recovery guidance:

- if local JSON is corrupted, restore from the host application's backup of exported world JSON.
- if multiple workers need writes, move persistence into host-owned storage with locking,
  migrations, backups, and recovery drills.
- do not add a lock file, SQLite store, or service adapter to WorldForge without a separate
  persistence design.

### 5a. Manage Worlds From TheWorldHarness

The Worlds screen in TheWorldHarness is the keyboard-first mirror of the `worldforge world`
CLI. Launch the harness and press `g w` (or pick "Jump: Worlds" from `Ctrl+P`):

```bash
uv run --extra harness worldforge-harness
```

Bindings mirror the CLI commands exactly: `n` maps to `worldforge world create`, `Enter`
opens the editor (`world show` + `add-object` + `update-object`), `d` calls the same save
path as `world delete` would, `f` maps to `world fork`, and `/` narrows the table by id or
name substring. Every disk write goes through `WorldForge.save_world` on a
`@work(thread=True, group="persistence")` worker; no JSON is hand-written. Validation errors
raised by the framework (`WorldStateError` / `WorldForgeError`) appear as toasts — the
in-memory edit buffer stays intact so the user can fix and retry.

## 6. Run Evaluation And Benchmarks

Use evaluation for deterministic behavior checks and benchmarks for adapter latency and event
shape. Do not treat either as a physical-fidelity claim.

```bash
uv run worldforge eval --suite planning --provider mock --format markdown
uv run worldforge eval --suite generation --provider mock --format json
uv run worldforge benchmark --provider mock --iterations 5 --format markdown
uv run worldforge benchmark --provider mock --iterations 5 --format json
uv run worldforge benchmark --provider mock --operation generate --budget-file benchmark-budget.json
```

Success signal:

- suites skip or fail explicitly when a provider does not support the required capability.
- benchmark reports identify provider, operation, pass/fail status, latency, retry counts, and
  exported artifact format for direct provider surfaces such as `score`, `policy`, `generate`,
  `transfer`, and `embed`.
- benchmark budget files fail non-zero when success rate, error count, retry count, latency, or
  throughput thresholds regress.
- benchmark inputs and results are saved by the host when they are used for release or paper
  claims.

If a score changes, first check provider capability, test fixture changes, input data, and retry
events. Do not rewrite claims around a one-off run without preserving the run artifact.

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
- returned artifacts are validated before `VideoClip` is returned.
- signed URLs and temporary artifact URLs are not durable storage. Download or persist them in
  host-owned storage immediately after completion.
- provider errors should include operation and provider context without leaking credentials,
  bearer tokens, or signed URLs.

If artifact download fails, inspect provider events for `operation`, `phase`, `status_code`,
`attempt`, and `target`, then rerun with a fresh task when the URL has expired.

## 8. Run Optional Runtime Smokes

Use checkout-safe demos first. Use real runtime smokes only in a host environment that has the
model, checkpoint, CUDA or robot stack, and task-specific preprocessing.

Checkout-safe:

```bash
uv run worldforge-demo-leworldmodel
uv run worldforge-demo-lerobot
uv run --extra harness worldforge-harness --flow diagnostics
```

Real LeWorldModel checkpoint:

```bash
uv run --python 3.10 \
  --with "stable-worldmodel[train,env] @ git+https://github.com/galilai-group/stable-worldmodel.git" \
  --with "datasets>=2.21" \
  worldforge-smoke-leworldmodel \
  --stablewm-home ~/.stable-wm \
  --policy pusht/lewm \
  --device cpu
```

GR00T and LeRobot live smokes:

```bash
python scripts/smoke_gr00t_policy.py --help
python scripts/smoke_lerobot_policy.py --help
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
uv run pytest
uv run --extra harness pytest --cov=src/worldforge --cov-report=term-missing --cov-fail-under=90
bash scripts/test_package.sh
```

Security audit:

```bash
tmp_req="$(mktemp requirements-audit.XXXXXX)"
uv export --frozen --all-groups --no-emit-project --no-hashes -o "$tmp_req" >/dev/null
uvx --from pip-audit pip-audit -r "$tmp_req" --no-deps --disable-pip --progress-spinner off
rm -f "$tmp_req"
```

Success signal:

- validation passes from a clean checkout.
- generated provider docs have no drift.
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

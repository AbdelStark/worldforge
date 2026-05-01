# Provider And Platform Roadmap

This proposal converts the current WorldForge direction into issue-ready workstreams for real
provider integrations, production-grade harnesses, host applications, and operational hardening.
It is written as a planning source for GitHub issues, not as a promise that every item is already
implemented.

Last reviewed: 2026-05-01.

## Completion Snapshot

The first production track is complete. The GitHub tracker issues remain useful as an audit trail,
but new provider and platform work should start from a fresh selection record or a narrowly scoped
follow-up issue rather than reopening these implementation slices.

| Tracker | Scope | Completion signal |
| --- | --- | --- |
| [#47](https://github.com/AbdelStark/worldforge/issues/47) | Provider platform foundation | Promotion gates, runtime manifests, conformance helpers, live-smoke artifacts, and optional runtime profiles are implemented. |
| [#48](https://github.com/AbdelStark/worldforge/issues/48) | Real provider implementations | LeWorldModel, LeRobot, GR00T, Cosmos, Runway, JEPA, JEPA-WMS, and Genie defer decisions are documented against executable capability claims. |
| [#49](https://github.com/AbdelStark/worldforge/issues/49) | Production harness | Run workspaces, connector readiness, live inspection, report comparison, and provider workbench flows preserve safe artifacts. |
| [#50](https://github.com/AbdelStark/worldforge/issues/50) | Reference host applications | Batch eval, service, and robotics operator host examples show host-owned integration boundaries. |
| [#51](https://github.com/AbdelStark/worldforge/issues/51) | Observability monitoring and logging | Provider event schema, logging, metrics, OpenTelemetry, readiness, and incident runbooks are available without changing the base dependency boundary. |
| [#52](https://github.com/AbdelStark/worldforge/issues/52) | Reliability security and release gates | Credential hardening, request budgets, persistence ADR, and release evidence generation are in place. |

Use the release gate below before tagging a release that claims this roadmap milestone.

## Planning Rules

Use these rules when turning this roadmap into issues:

- Keep the base package lightweight. Do not add torch, robot runtimes, checkpoint managers, web
  frameworks, dashboards, or telemetry exporters to the default dependency set.
- Promote a provider only when it calls a real upstream runtime or API, validates the boundary, and
  has fixture-backed failure coverage.
- Keep optional runtimes host-owned. WorldForge can provide adapters, launchers, conformance tests,
  and reference host applications; the host owns credentials, devices, checkpoints, datasets,
  durable stores, dashboards, robot controllers, and safety policy.
- Treat provider events as security-sensitive records. Every new observable field must pass
  redaction tests before it reaches logs, metrics, traces, reports, or exports.
- Keep deterministic checkout tests separate from live runtime smokes. Live smokes should be
  explicit, skip cleanly without credentials/runtime packages, and preserve enough artifacts to
  debug failures.
- Every issue should name the exact capability surface it changes: `predict`, `generate`,
  `transfer`, `reason`, `embed`, `score`, or `policy`.

## Desired End State

The roadmap is complete when WorldForge has moved from "credible framework and demos" to a
production-shaped provider platform with these properties:

| Dimension | End state |
| --- | --- |
| Provider trust | Every advertised provider capability has a real callable implementation, conformance coverage, generated docs, and a prepared-host smoke path. |
| Provider selection | New provider work starts from a written selection record that scores user value, upstream maturity, runtime cost, validation feasibility, and maintenance burden. |
| Runtime boundary | Heavy model packages, GPUs, checkpoints, robot stacks, hosted dashboards, and durable stores remain opt-in host concerns. |
| Harness | TheWorldHarness becomes the local operations workspace for provider readiness, run execution, artifact inspection, eval/benchmark comparison, and provider development. |
| Host apps | Reference hosts show how to embed WorldForge in batch jobs, services, and robotics operator workflows without redefining the base package boundary. |
| Operations | Provider calls produce sanitized events, optional traces/metrics/log files, run manifests, readiness states, and incident runbooks. |
| Release evidence | Releases include reproducible local gates and explicit optional-provider evidence or skip reasons. |

Non-negotiable quality bar:

- A provider is not "real" because its name exists in the catalog. It is real only when a host can
  install the upstream runtime or configure the upstream API, run a documented smoke command, and
  inspect preserved evidence.
- A harness feature is not production-grade because it renders a screen. It is production-grade
  when it preserves state, handles cancellation/failure, exports safe artifacts, and can be tested
  without live credentials.
- An observability feature is not production-grade if it leaks prompts, credentials, signed URL
  query strings, raw tensors, unbounded labels, or robot-specific secrets.

## Current Baseline

| Area | Current state | Constraint |
| --- | --- | --- |
| Base package | `httpx` runtime dependency, Python 3.13 only, hatchling/uv packaging | Keep provider and host extras optional. |
| Provider catalog | `mock`, `cosmos`, `runway`, `leworldmodel`, `gr00t`, `lerobot`, experimental score-only `jepa`, plus scaffold `genie` | Do not advertise scaffold providers as real integrations. |
| Candidate provider | `jepa-wms` direct-construction score candidate, not exported or auto-registered | Promote only after real upstream limits and runtime behavior are validated. |
| Planning | `World.plan(...)` composes `predict`, `score`, `policy`, and `policy+score` flows | Do not treat `plan` as a provider badge unless a provider implements planning directly. |
| Harness | Optional Textual app with worlds, providers, eval, benchmark, run inspector, and robotics report surfaces | Textual remains isolated to `worldforge.harness.tui`. |
| Observability | `ProviderEvent`, `JsonLoggerSink`, `InMemoryRecorderSink`, `ProviderMetricsSink`, handler fanout | Host owns full telemetry export and alerting unless optional integrations are added. |
| Persistence | Validated single-writer local JSON state and report artifacts | Durable multi-writer persistence remains a host concern until a separate adapter design lands. |

## Target Architecture

The roadmap should preserve this dependency direction:

```text
host application / CLI / harness
  -> WorldForge facade
  -> provider registry + capability registry
  -> provider adapter or protocol implementation
  -> upstream runtime/API/checkpoint
```

The reverse direction is forbidden: provider adapters must not import host applications, the base
package must not import optional robotics/model runtimes at module import time, and telemetry
exporters must not own provider behavior.

Target module boundaries:

| Boundary | Owns | Must not own |
| --- | --- | --- |
| `worldforge.models` | JSON-native public contracts, validation, public errors | upstream package types, host telemetry clients |
| `worldforge.providers.*` | adapter configuration, capability methods, upstream parsing, provider events | durable storage, dashboards, robot-controller safety policy |
| `worldforge.testing` | reusable capability conformance helpers and failure assertions | live credentials, network calls by default |
| `worldforge.benchmark` / `worldforge.evaluation` | deterministic contract signals, preserved reports, budget gates | claims of real physical fidelity without external evidence |
| `worldforge.harness.models` / `flows` | structured runs and reports without Textual dependency | TUI widgets, optional model packages |
| `worldforge.harness.tui` | Textual screens over public APIs and structured run data | provider-specific business logic |
| `examples/hosts/*` | optional host integration patterns | new required base dependencies |

Core data flow for real provider runs:

```text
input fixture or host payload
  -> capability-specific validation
  -> provider runtime call
  -> typed result validation
  -> sanitized ProviderEvent stream
  -> run_manifest.json
  -> harness/report/export surfaces
```

Every issue should state which part of this flow it changes.

## Milestone Sequence

| Milestone | Goal | Exit signal |
| --- | --- | --- |
| M0: Issue-ready contracts | Convert this roadmap into labeled GitHub issues with dependencies and owners | Issues exist with acceptance criteria and validation commands. |
| M1: Provider foundation | Shared provider promotion gates, runtime manifests, conformance tests, and live-smoke conventions | New providers can be added without inventing process per adapter. |
| M2: Real provider promotions | Promote the highest-value current adapters and replace scaffold reservations only when real runtime contracts exist | Provider docs/catalog match executable behavior and live-smoke artifacts. |
| M3: Production harness | Turn TheWorldHarness into the canonical local operations workspace for providers, worlds, runs, artifacts, and diagnostics | Operators can configure, run, inspect, compare, export, and recover flows locally. |
| M4: Reference host applications | Provide optional host apps that show how to embed WorldForge in services, batch jobs, and robotics labs | Hosts have runnable templates without changing the base package. |
| M5: Observability and operations | Add optional telemetry exporters, service probes, run manifests, redaction gates, and incident runbooks | Production hosts can integrate with standard monitoring without leaking secrets. |
| M6: Release hardening | Make live-provider releases reproducible, auditable, and explicitly scoped | Release gates include docs, package contract, coverage, provider contract checks, and optional smoke evidence. |

## Dependency Graph

Use this graph when assigning issues. Work in the same row can usually proceed in parallel after
its dependencies are satisfied.

| Wave | Dependencies | Issues | Why this order |
| --- | --- | --- | --- |
| 0 | none | WF-PROV-001, WF-PROVIDER-SELECT-001 | Lock provider standards and avoid adding low-value adapter work. |
| 1 | WF-PROV-001 | WF-PROV-002, WF-PROV-003 | Runtime manifests and conformance checks are the reusable substrate for real providers. |
| 2 | WF-PROV-002, WF-PROV-003 | WF-PROV-004, WF-PROV-005 | Live smokes and markers need manifests plus contract helpers. |
| 3 | Wave 2 | WF-LWM-001, WF-LEROBOT-001, WF-COSMOS-001, WF-RUNWAY-001 | Promote existing high-value real paths before expanding the catalog. |
| 4 | WF-LEROBOT-001 | WF-LEROBOT-002, WF-GROOT-001 | Robotics policy work needs translator contracts before serious host workflows. |
| 5 | WF-PROV-004 | WF-HARNESS-001, WF-OBS-001 | Runs and events need a shared artifact/correlation model. |
| 6 | WF-HARNESS-001, WF-OBS-001 | WF-HARNESS-002 through WF-HARNESS-005, WF-OBS-002 through WF-OBS-005 | UI, exports, traces, logs, and readiness should share run IDs and event semantics. |
| 7 | Waves 3-6 | WF-HOST-001, WF-HOST-002, WF-HOST-003, WF-OPS-004 | Host apps and release evidence are useful after provider/run/observability contracts exist. |
| design-only | varies | WF-OPS-003, WF-JEPA-001, WF-GENIE-001 | Do not implement until the design or upstream runtime contract is credible. |

## Issue Template

Use this shape when creating issues from the sections below:

```text
Title:
Type:
Labels:
Depends on:

Problem:

Scope:
- In:
- Out:

Implementation notes:

Acceptance criteria:
- [ ]
- [ ]
- [ ]

Validation:
- command:
- expected signal:

Docs:
- pages to update:
```

Provider issues should also fill the existing provider adapter template fields: provider/runtime,
implemented capabilities, runtime ownership, validation plan, and failure modes.

## Issue Sizing Rules

Split an issue when it crosses any of these boundaries:

- Adds or changes more than one provider capability.
- Changes both provider runtime code and host application code.
- Adds optional dependencies and changes base package behavior.
- Changes public API contracts and docs in the same large patch.
- Requires live credentials or GPU validation and deterministic checkout validation.
- Touches both durable persistence design and local JSON behavior.

Preferred issue sizes:

| Size | Shape | Expected validation |
| --- | --- | --- |
| Small | One parser, one validator, one docs fix, one fixture family | focused pytest plus docs if public |
| Medium | One capability contract, one provider hardening slice, one harness screen | focused pytest, docs, generated catalog if provider-facing |
| Large | Provider promotion, run workspace, event schema, host app | split implementation issues plus one tracking issue |

Every issue should include an "out of scope" section. The most common out-of-scope items should be
base dependency expansion, real robot execution, durable persistence, and default CI jobs requiring
credentials.

## Provider Prioritization Rubric

Score each new provider proposal before implementation. Use the total to rank issue order, not to
override safety gates.

| Criterion | 0 | 1 | 2 |
| --- | --- | --- | --- |
| User value | Niche or unclear workflow | Useful to one existing workflow | Unlocks a common provider, model family, or robotics workflow |
| Capability clarity | No stable callable surface | Callable surface exists but maps awkwardly | Maps cleanly to one WorldForge capability |
| Upstream maturity | Unreleased or unstable | Works but docs/API are moving | Stable API/package/checkpoint path |
| Runtime feasibility | Requires unavailable hardware or huge setup | Prepared-host only with clear dependencies | Can run locally or through a reachable hosted API |
| Fixture strategy | No fixtureable contract | Partial fixture coverage | Success and failure fixtures cover the boundary |
| Smoke feasibility | No smoke path | Manual smoke only | Documented smoke command with preserved manifest |
| Maintenance burden | High churn or unclear license | Moderate churn | Low churn and clear license/ownership |
| Safety/secret risk | High risk without mitigation | Manageable with redaction/tests | Low risk or already covered by event sanitization |

Interpretation:

- `12-16`: candidate for the next implementation batch.
- `8-11`: write an RFC or keep as experimental/direct-construction only.
- `<8`: defer. Do not add catalog noise.

Current high-priority candidates:

| Candidate | Reason | First issue |
| --- | --- | --- |
| LeWorldModel score | Existing real score path and robotics showcase value | WF-LWM-001 |
| LeRobot policy | Existing real policy path and policy+score planning value | WF-LEROBOT-001 |
| Runway/Cosmos media | Existing remote adapters with production parser/artifact concerns | WF-RUNWAY-001, WF-COSMOS-001 |
| GR00T PolicyClient | Valuable robotics policy path, but prepared-host complexity is higher | WF-GROOT-001 |
| JEPA-WMS | Research-value score candidate, but should remain direct-construction until upstream limits are known | WF-JEPAWMS-001 |

The next expansion batch is recorded in the
[Next Provider Selection RFC](./provider-selection-rfc.md). Keep provider README/catalog wording
unchanged until the selected implementation issue starts.

## Provider Promotion Matrix

Use this matrix before changing `implementation_status`.

| Status | Allowed public claim | Required evidence | Forbidden |
| --- | --- | --- | --- |
| `scaffold` | Reserved name, planned contract, no executable public capability | docs state it is not real; methods fail closed or are test-only | claiming integration, auto-registering as usable, advertising capability flags |
| `experimental` | Real path exists, contract may change | injected-runtime tests, failure docs, optional smoke command or documented blocker | treating outputs as stable, hiding missing runtime limits |
| `beta` | Usable by prepared hosts with documented limits | conformance helper coverage, runtime manifest, live-smoke manifest, generated provider docs | base dependency expansion, undocumented env vars or failure modes |
| `stable` | Recommended provider path for its capability | repeated smoke evidence, release evidence, parser/validation coverage, incident runbook, compatibility policy | unpinned upstream assumptions, unbounded metadata/log fields |

Promotion blockers:

- The provider cannot run without undocumented credentials or local files.
- Returned metadata is not JSON-native.
- Score direction or candidate cardinality is ambiguous.
- Policy output cannot be translated into executable `Action` values without hidden assumptions.
- Health checks cannot distinguish missing config from missing dependency or upstream failure.
- Provider events can leak secrets or signed URL query strings.

## Artifact Contracts

These shapes are intentionally small. Exact schemas can be implemented later, but issues should
preserve these fields unless there is a better reviewed design.

### Runtime Manifest

```json
{
  "manifest_version": 1,
  "provider": "leworldmodel",
  "capabilities": ["score"],
  "runtime": {
    "kind": "local-python",
    "optional_packages": ["stable-worldmodel", "torch"],
    "python": ">=3.13,<3.14",
    "devices": ["cpu", "cuda"]
  },
  "configuration": {
    "required_env": ["LEWORLDMODEL_POLICY"],
    "optional_env": ["LEWORLDMODEL_CACHE_DIR", "LEWORLDMODEL_DEVICE"]
  },
  "artifacts": {
    "checkpoint": "host-owned",
    "datasets": "host-owned"
  },
  "smoke": {
    "command": "scripts/lewm-real --checkpoint ~/.stable-wm/pusht/lewm_object.ckpt --device cpu --json",
    "success_signal": "JSON summary with provider=leworldmodel and capability=score"
  }
}
```

### Run Manifest

```json
{
  "manifest_version": 1,
  "run_id": "20260430T120000Z-leworldmodel-score",
  "worldforge_version": "0.5.0",
  "command": ["scripts/lewm-real", "--device", "cpu", "--json"],
  "provider": "leworldmodel",
  "capability": "score",
  "runtime_manifest": "leworldmodel",
  "status": "passed",
  "input_digest": "sha256:<hex>",
  "result_digest": "sha256:<hex>",
  "event_count": 3,
  "artifacts": [
    {"kind": "json", "path": "summary.json", "safe_to_attach": true}
  ],
  "skip_reason": null
}
```

### Provider Event Correlation

Provider events should be joinable to run artifacts without exposing sensitive payloads:

```json
{
  "provider": "runway",
  "operation": "generate",
  "phase": "success",
  "attempt": 1,
  "max_attempts": 1,
  "duration_ms": 1200.0,
  "run_id": "20260430T120000Z-runway-generate",
  "request_id": "host-request-id",
  "target": "https://api.example.test/v1/tasks",
  "metadata": {
    "artifact_id": "artifact-local-id",
    "input_digest": "sha256:<hex>"
  }
}
```

`metadata` must remain JSON-native and sanitized. Do not store raw prompts, raw tensors, bearer
tokens, signed URL query strings, robot serial numbers, or host-specific paths unless a host
explicitly marks them safe for local-only use.

## Workstream A: Provider Platform Foundation

### WF-PROV-001: Provider Promotion Gate

Type: provider platform  
Labels: `provider`, `quality`, `documentation`  
Depends on: none

Problem: Provider maturity is visible through profiles, but there is no explicit promotion
checklist for moving from `scaffold` to `experimental`, `beta`, or `stable`.

Scope:

- Define required evidence for each status: upstream contract, runtime availability, fixtures,
  live smoke, docs, failure modes, and benchmark inputs.
- Add a provider-promotion checklist to the provider authoring guide or a dedicated provider
  governance page.
- Require status-specific docs wording. Example: `stable` may document expected operator use;
  `experimental` must document known gaps; `scaffold` must advertise no executable capabilities.

Acceptance criteria:

- [ ] Promotion rules cover all current statuses: `scaffold`, `experimental`, `beta`, `stable`.
- [ ] Rules explain when to change provider profile metadata and generated catalog docs.
- [ ] Rules include exact local validation commands.
- [ ] Existing providers are classified against the new checklist without changing behavior.

Validation:

```bash
uv run python scripts/generate_provider_docs.py --check
uv run mkdocs build --strict
uv run pytest tests/test_provider_catalog_docs.py
```

### WF-PROV-002: Provider Runtime Manifest Schema

Type: provider platform  
Labels: `provider`, `operations`, `documentation`  
Depends on: WF-PROV-001

Problem: Optional runtime docs are scattered across provider pages, scripts, and operations docs.
Real provider work needs a machine-readable manifest for runtime requirements and smoke evidence.

Scope:

- Introduce a small JSON or TOML manifest schema for each real provider runtime.
- Capture optional packages, env vars, default model/checkpoint, device support, host-owned
  artifacts, minimum smoke command, and expected success signal.
- Keep manifests in-repo and dependency-free.
- Do not auto-install large runtimes from manifests in the base package.

Acceptance criteria:

- [ ] Manifest schema is documented and validated by tests.
- [ ] Manifests exist for `leworldmodel`, `lerobot`, `gr00t`, `cosmos`, and `runway`.
- [ ] Missing optional dependencies produce actionable health messages using manifest data.
- [ ] Docs link from provider pages to the relevant manifest.

Validation:

```bash
uv run pytest tests/test_provider_runtime_manifests.py
uv run mkdocs build --strict
```

### WF-PROV-003: Provider Conformance Suite v2

Type: provider platform  
Labels: `provider`, `testing`, `quality`  
Depends on: WF-PROV-001

Problem: Contract helpers exist, but real providers need capability-specific conformance suites
that can be reused for deterministic fakes, injected runtimes, HTTP fixtures, and live smokes.

Scope:

- Expand `src/worldforge/testing/` into capability-specific checks for `score`, `policy`,
  `generate`, `transfer`, `predict`, `reason`, and `embed`.
- Verify finite numeric outputs, JSON-native metadata, redacted events, failure typing, health
  behavior, and docs/profile consistency.
- Keep helpers explicit; they should raise useful `AssertionError` messages.

Acceptance criteria:

- [ ] Each capability has a reusable conformance helper.
- [ ] Current provider tests call the helpers where applicable.
- [ ] The helpers can run against injected runtimes without credentials.
- [ ] The helpers do not use bare Python `assert` statements.

Validation:

```bash
uv run pytest tests/test_*provider*.py tests/test_observability.py
uv run --extra harness pytest --cov=src/worldforge --cov-report=term-missing --cov-fail-under=90
```

### WF-PROV-004: Live Smoke Artifact Contract

Type: provider platform  
Labels: `provider`, `operations`, `benchmark`  
Depends on: WF-PROV-002

Problem: Live provider runs are useful only if they preserve the command, environment summary,
input payload, provider profile, event stream, output summary, and artifact paths.

Scope:

- Define a `run_manifest.json` shape for optional live smokes.
- Include command argv, package version, provider profile, capability, sanitized env summary,
  runtime manifest id, input fixture digest, event count, result digest, and artifact paths.
- Write manifests from optional smoke commands and robotics showcase paths.
- Keep credential values and signed URL query strings out of manifests.

Acceptance criteria:

- [ ] Live smoke commands can emit `run_manifest.json`.
- [ ] Manifest validation rejects secret-like metadata.
- [ ] Robotics showcase manifest links policy, score, replay, and report artifacts.
- [ ] Docs explain which artifacts are safe to attach to GitHub issues.

Validation:

```bash
uv run pytest tests/test_smoke_run_manifest.py tests/test_observability.py
uv run mkdocs build --strict
```

### WF-PROV-005: Optional Runtime Test Profiles

Type: provider platform  
Labels: `provider`, `ci`, `testing`  
Depends on: WF-PROV-002, WF-PROV-004

Problem: CI should keep checkout tests deterministic while still making live provider validation
repeatable on prepared hosts.

Scope:

- Add pytest markers and documented commands for `live`, `gpu`, `network`, `robotics`, and
  `credentialed` tests.
- Keep default `uv run pytest` free of live runtime requirements.
- Provide local commands for prepared hosts to run one provider profile at a time.
- Do not add live provider jobs to default CI unless credentials and billing policy are explicit.

Acceptance criteria:

- [ ] Live tests skip with clear reasons when runtime/env is missing.
- [ ] Prepared-host commands are documented for each real provider.
- [ ] Default CI remains deterministic and does not require credentials, network calls, GPUs, or
      downloaded checkpoints.
- [ ] Live-smoke evidence can be attached to release notes or provider issues.

Validation:

```bash
uv run pytest
uv run pytest -m "not live"
uv run mkdocs build --strict
```

## Workstream B: Real Provider Implementations

### WF-LWM-001: LeWorldModel Stable Score Provider

Type: provider promotion  
Labels: `provider`, `score`, `robotics`  
Depends on: WF-PROV-001, WF-PROV-002, WF-PROV-003

Problem: `leworldmodel` already wraps the real `stable_worldmodel.policy.AutoCostModel` path, but
stable promotion needs a stronger runtime matrix, artifact contract, and task bridge evidence.

Scope:

- Pin the exact upstream import boundary in docs and runtime manifest.
- Validate checkpoint loading, CPU fallback, score tensor shapes, candidate cardinality, finite
  costs, score direction, and malformed-output errors.
- Preserve a small deterministic injected-runtime test path for checkout CI.
- Add prepared-host smoke evidence for at least one real checkpoint path.

Acceptance criteria:

- [ ] `ProviderProfile` status and provider docs reflect the promotion decision.
- [ ] Real checkpoint smoke writes a manifest with score payload summary and event stream.
- [ ] Failure docs cover missing package, missing checkpoint, bad tensor shape, non-finite score,
      mismatched candidate count, and device fallback.
- [ ] No LeWorldModel runtime dependency is added to the base package.

Validation:

```bash
uv run pytest tests/test_leworldmodel_provider.py tests/test_provider_contracts.py
uv run python scripts/generate_provider_docs.py --check
uv run mkdocs build --strict
```

Prepared-host smoke:

```bash
scripts/lewm-real --checkpoint ~/.stable-wm/pusht/lewm_object.ckpt --device cpu --json
```

### WF-LWM-002: LeWorldModel Task Bridge Pack

Type: provider extension  
Labels: `provider`, `score`, `examples`  
Depends on: WF-LWM-001, WF-PROV-004

Problem: LeWorldModel scoring depends on task-native tensor preprocessing. WorldForge should
provide clear bridge examples without pretending it can infer every task representation.

Scope:

- Keep PushT as the first complete bridge.
- Add a bridge registry pattern for examples and smoke commands.
- Document required tensors, shapes, and task ownership.
- Add at least one negative test showing that mismatched action spaces fail instead of being
  padded or projected silently.

Acceptance criteria:

- [ ] Bridge docs distinguish WorldForge validation from host preprocessing.
- [ ] Bridge code emits shape summaries into run manifests.
- [ ] Mismatched action dims fail before planning.
- [ ] Existing robotics showcase continues to use the same public provider surfaces.

Validation:

```bash
uv run pytest tests/test_robotics_showcase.py tests/test_leworldmodel_provider.py
uv run mkdocs build --strict
```

### WF-LEROBOT-001: LeRobot Stable Policy Provider

Type: provider promotion  
Labels: `provider`, `policy`, `robotics`  
Depends on: WF-PROV-001, WF-PROV-002, WF-PROV-003

Problem: `lerobot` exposes a real policy adapter, but production use needs a stronger loader
contract, action-output normalization, translator docs, and prepared-host smoke evidence.

Scope:

- Validate supported policy loading modes and default device behavior.
- Normalize raw policy outputs into JSON-native previews without losing shape/type evidence.
- Keep executable WorldForge `Action` creation behind explicit host-supplied translators.
- Add health behavior for missing package, missing checkpoint, unsupported policy type, and
  translator absence.

Acceptance criteria:

- [ ] Provider status is updated only if all promotion gates pass.
- [ ] Provider docs name the supported loader path and unsupported cases.
- [ ] Raw policy action previews are safe for logs and reports.
- [ ] No LeRobot, torch, robot checkpoints, or simulation packages are added to the base package.

Validation:

```bash
uv run pytest tests/test_lerobot_provider.py tests/test_provider_contracts.py
uv run python scripts/generate_provider_docs.py --check
uv run mkdocs build --strict
```

Prepared-host smoke:

```bash
scripts/smoke_lerobot_policy.py --help
```

### WF-LEROBOT-002: Embodiment Translator Contract

Type: provider foundation  
Labels: `provider`, `policy`, `robotics`, `testing`  
Depends on: WF-LEROBOT-001

Problem: Policy providers return embodiment-specific actions. Translators need a formal contract
so host applications can prove a raw policy output became executable WorldForge actions safely.

Scope:

- Define translator input/output shape, metadata, failure behavior, and provenance fields.
- Add reusable tests for translator cardinality, finite values, JSON-native metadata, and
  reversible preview summaries.
- Document how translators map to real robot controllers without WorldForge owning hardware
  safety.

Acceptance criteria:

- [ ] Translators fail loudly on unknown embodiment tags and shape mismatches.
- [ ] Policy provider docs reference the translator contract.
- [ ] Robotics showcase uses the contract without changing its public behavior.
- [ ] Host-owned safety interlocks remain out of core WorldForge.

Validation:

```bash
uv run pytest tests/test_lerobot_provider.py tests/test_robotics_showcase.py
uv run mkdocs build --strict
```

### WF-GROOT-001: GR00T PolicyClient Beta Provider

Type: provider promotion  
Labels: `provider`, `policy`, `robotics`, `operations`  
Depends on: WF-PROV-001, WF-PROV-002, WF-LEROBOT-002

Problem: `gr00t` is experimental. Beta promotion requires a prepared-host story for remote
PolicyClient operation, auth, timeout behavior, action previews, and failure triage.

Scope:

- Document supported remote PolicyClient configuration and unsupported local server assumptions.
- Validate strict and non-strict modes, timeout settings, auth token handling, observation
  validation, translator absence, and server-unreachable errors.
- Add prepared-host smoke instructions for connecting to an existing policy server.
- Keep CUDA, TensorRT, Isaac-GR00T, and robot dependencies host-owned.

Acceptance criteria:

- [ ] Health checks distinguish missing config, missing dependency, and unreachable policy server.
- [ ] Provider events include operation, attempt, sanitized target, and duration.
- [ ] Token-like values cannot appear in events or run manifests.
- [ ] Docs state that unsupported hosts should connect to a remote server instead of starting one.

Validation:

```bash
uv run pytest tests/test_gr00t_provider.py tests/test_observability.py
uv run python scripts/generate_provider_docs.py --check
uv run mkdocs build --strict
```

Prepared-host smoke:

```bash
GROOT_POLICY_HOST=<host> uv run python scripts/smoke_gr00t_policy.py --policy-info-json policy.json
```

### WF-COSMOS-001: Cosmos Generate Provider Production Hardening

Type: provider promotion  
Labels: `provider`, `generate`, `operations`  
Depends on: WF-PROV-003, WF-PROV-004

Problem: `cosmos` is a real HTTP adapter. Production hardening should lock API-version handling,
parser fixtures, retry policy, artifact metadata, and docs around reachable deployments.

Scope:

- Audit request/response parser coverage against current supported Cosmos deployment shape.
- Preserve fixture coverage for success, malformed payloads, auth failures, timeout, polling,
  failed tasks, and unsupported artifacts.
- Emit run manifests for live generate smoke runs.
- Keep endpoint ownership with the host.

Acceptance criteria:

- [ ] Provider docs state required endpoint/auth configuration and first triage step.
- [ ] Parser tests cover every documented failure mode.
- [ ] Retry and timeout behavior is visible in provider events.
- [ ] Live smoke can be run manually without changing default CI.

Validation:

```bash
uv run pytest tests/test_cosmos_provider.py tests/test_remote_video_providers.py
uv run python scripts/generate_provider_docs.py --check
uv run mkdocs build --strict
```

### WF-RUNWAY-001: Runway Generate/Transfer Production Hardening

Type: provider promotion  
Labels: `provider`, `generate`, `transfer`, `operations`  
Depends on: WF-PROV-003, WF-PROV-004

Problem: `runway` supports generate and transfer through a remote API. Production hardening needs
artifact retention policy, expired URL handling, and parser coverage that matches operator docs.

Scope:

- Verify create, polling, download, content-type, and expired-artifact error paths.
- Write live smoke manifests that preserve artifact metadata without storing signed URLs.
- Document host responsibility for persisting downloaded media immediately after task completion.
- Keep legacy `RUNWAY_API_SECRET` alias tested while preferring `RUNWAYML_API_SECRET`.

Acceptance criteria:

- [ ] Signed URL query strings never appear in events, logs, manifests, or reports.
- [ ] Docs cover artifact expiration and first recovery step.
- [ ] Transfer and generate have separate benchmark inputs and capability tests.
- [ ] Provider profile notes model/version limits where known.

Validation:

```bash
uv run pytest tests/test_runway_provider.py tests/test_remote_video_providers.py tests/test_observability.py
uv run python scripts/generate_provider_docs.py --check
uv run mkdocs build --strict
```

### WF-JEPAWMS-001: JEPA-WMS Candidate Promotion

Type: provider promotion  
Labels: `provider`, `score`, `research`  
Depends on: WF-PROV-001, WF-PROV-002, WF-PROV-003

Problem: `jepa-wms` is a direct-construction score candidate. It should stay unregistered until
real upstream runtime limits, model loading, and score semantics are validated.

Scope:

- Verify the selected upstream runtime path, required dependencies, model names, and device
  behavior on a prepared host.
- Define exact score input tensors, action candidate shape, score direction, and unsupported cases.
- Decide whether auto-registration is appropriate or whether direct construction remains the right
  boundary.
- Keep torch and JEPA-WMS dependencies host-owned.

Acceptance criteria:

- [x] Provider status is not upgraded without real runtime smoke evidence.
- [x] Docs state direct-construction versus auto-registration decision.
- [x] Fixture and injected-runtime tests cover parser and validation behavior.
- [x] Prepared-host smoke writes a manifest with runtime version and score summary.

Validation:

```bash
uv run pytest tests/test_jepa_wms_provider.py tests/test_provider_contracts.py
uv run mkdocs build --strict
```

### WF-JEPA-001: Replace JEPA Scaffold With A Real Adapter

Type: provider implementation  
Labels: `provider`, `predict`, `score`, `research`  
Depends on: WF-JEPAWMS-001 or a separate provider-selection RFC

Problem: The catalog contains a fail-closed `jepa` reservation. Replacing it requires choosing a
real upstream JEPA runtime and one honest capability surface.

Scope:

- Write a short provider-selection RFC before implementation.
- Choose whether the first real JEPA surface is `score`, `predict`, or `embed`; do not expose all
  three by default.
- Remove or rename scaffold behavior only when the real adapter has tests, docs, and live smoke
  evidence.
- Preserve a migration note for users who configured the scaffold env var.

Acceptance criteria:

- [ ] The selected upstream package/API/checkpoint is named in docs.
- [ ] The adapter advertises exactly the implemented capability.
- [ ] Scaffold-only surrogate behavior is removed or kept behind a clearly separate test path.
- [ ] Provider catalog no longer implies a fake JEPA integration.

Validation:

```bash
uv run pytest tests/test_jepa_provider.py tests/test_provider_catalog_docs.py
uv run python scripts/generate_provider_docs.py --check
uv run mkdocs build --strict
```

### WF-GENIE-001: Replace Genie Scaffold Only After Runtime Contract Exists

Type: provider implementation  
Labels: `provider`, `generate`, `research`  
Depends on: WF-PROV-001

Problem: `genie` is currently a fail-closed reservation. A real implementation should wait until
there is a concrete upstream runtime/API with stable callable behavior and acceptable host-owned
dependency boundaries.

Scope:

- Create a provider-selection RFC before implementation.
- Decide whether the first surface is `generate`, `predict`, or a new typed scene/world surface.
- Keep the scaffold reservation if no credible upstream contract exists.
- Do not present deterministic local surrogate behavior as a real Genie integration.

Acceptance criteria:

- [ ] Issue closes with either an implementation plan or an explicit decision to defer.
- [ ] If implemented, provider docs include upstream contract, limits, env vars, artifacts, and
      failure modes.
- [ ] If deferred, docs clearly state why it remains a scaffold.

Validation:

```bash
uv run pytest tests/test_remote_scaffold_providers.py
uv run mkdocs build --strict
```

### WF-PROVIDER-SELECT-001: Next Provider Selection RFC

Type: provider planning  
Labels: `provider`, `research`, `roadmap`  
Depends on: WF-PROV-001

Problem: Adding more provider names without real integrations creates noise. The next provider
batch should be chosen by callable surface, user value, runtime feasibility, and validation cost.

Scope:

- Evaluate candidate classes: embodied policy adapters, latent score/predict models, remote media
  generation/transfer APIs, simulator bridges, and spatial/3D world model runtimes.
- For each candidate, record capability surface, package/API maturity, host dependency weight,
  smoke feasibility, licensing, fixture strategy, and expected users.
- Choose at most three providers for the next implementation batch.

Acceptance criteria:

- [ ] RFC recommends no more than three provider additions.
- [ ] Each recommended provider has an issue outline with capability, owner, and validation path.
- [ ] Deferred candidates include the blocking reason.
- [ ] README/provider docs are not changed until implementation starts.

Validation:

```bash
uv run mkdocs build --strict
```

## Workstream C: Production Harness

Harness work should be treated as product engineering, not demo polish. The harness is the
reference implementation of a local operator workspace over WorldForge APIs.

Production harness requirements:

| Requirement | Meaning |
| --- | --- |
| Deterministic checkout path | Every new screen or flow has a `mock` or fixture-backed path that runs without credentials. |
| Prepared-host path | Real provider flows can run when optional runtime packages, credentials, and artifacts are present. |
| Persistent run model | Runs are stored under a stable run directory with manifest, events, summaries, and exported reports. |
| Failure visibility | Failed, cancelled, skipped, misconfigured, and unhealthy states are visually distinct and exported. |
| Safe exports | Report exports are sanitized and suitable for GitHub issue attachments unless marked local-only. |
| Keyboard-first operation | Common provider, run, report, and world actions are reachable from command palette or shortcuts. |
| Testable without Textual import leakage | Flow logic remains testable outside `worldforge.harness.tui`. |

Harness anti-goals:

- Do not turn TheWorldHarness into a hosted dashboard.
- Do not hide provider setup behind implicit installation of heavy optional runtimes.
- Do not execute robot-controller actions from a default harness flow.
- Do not render raw secret-bearing provider metadata.

### WF-HARNESS-001: Harness Run Workspace

Type: harness  
Labels: `harness`, `operations`, `artifacts`  
Depends on: WF-PROV-004

Problem: The harness can display runs and reports, but production-grade local operation needs a
clear workspace model for inputs, outputs, manifests, events, logs, and exports.

Scope:

- Define `.worldforge/runs/<run-id>/` layout for harness and CLI flows.
- Store sanitized run manifest, provider events, input summaries, result summaries, generated
  reports, and exported media paths.
- Add retention and cleanup commands.
- Keep local workspace single-user unless a durable store adapter is explicitly designed.

Acceptance criteria:

- [ ] Harness and CLI flows write the same run layout.
- [ ] Run IDs are file-safe and sortable.
- [ ] Exported artifacts can be attached to issues without leaking secrets.
- [ ] Docs include cleanup and recovery steps.

Validation:

```bash
uv run pytest tests/test_harness_flows.py tests/test_cli_reports.py
uv run --extra harness pytest tests/test_harness_tui.py
uv run mkdocs build --strict
```

### WF-HARNESS-002: Provider Connector Workspace

Type: harness  
Labels: `harness`, `provider`, `operations`  
Depends on: WF-PROV-002, WF-HARNESS-001

Problem: Operators need a local way to inspect provider readiness, missing env vars, optional
runtime health, and first smoke commands before running workflows.

Scope:

- Add a connector screen or panel that reads provider profiles and runtime manifests.
- Show configured, missing, unhealthy, and scaffold providers separately.
- Surface exact next commands without printing secrets.
- Support copyable smoke commands and first triage steps.

Acceptance criteria:

- [ ] `mock`, `cosmos`, `runway`, `leworldmodel`, `gr00t`, `lerobot`, experimental `jepa`, and scaffold
      `genie` render with distinct status.
- [ ] Missing credentials and missing optional dependencies are visibly different.
- [ ] Textual remains isolated to `worldforge.harness.tui`.
- [ ] Non-TUI metadata command exposes the same provider readiness data as JSON.

Validation:

```bash
uv run pytest tests/test_harness_flows.py tests/test_harness_cli.py
uv run --extra harness pytest tests/test_harness_tui.py
```

### WF-HARNESS-003: Live Run Inspector

Type: harness  
Labels: `harness`, `observability`, `provider`  
Depends on: WF-HARNESS-001, WF-OBS-001

Problem: Operators should be able to watch provider events, timing, retries, failures, selected
actions, scores, and artifact creation as a run executes.

Scope:

- Stream sanitized provider events into the run inspector.
- Show timeline, event table, result summary, artifact paths, and validation errors.
- Support cancellation for long-running provider calls where the underlying operation can be
  stopped safely.
- Persist the final view from the same run manifest.

Acceptance criteria:

- [ ] Success, retry, failure, and cancellation states are distinct.
- [ ] Provider event metadata is redacted in TUI and exported reports.
- [ ] A failed run still writes enough manifest data to reproduce the command.
- [ ] Tests cover failure rendering without real provider credentials.

Validation:

```bash
uv run pytest tests/test_harness_flows.py tests/test_observability.py
uv run --extra harness pytest tests/test_harness_tui.py
```

### WF-HARNESS-004: Report Compare And Export

Type: harness  
Labels: `harness`, `benchmark`, `evaluation`  
Depends on: WF-HARNESS-001

Problem: Provider evaluation and benchmark work needs first-class comparison across preserved
runs, not just one-off reports.

Scope:

- Add report comparison for benchmark latency/throughput, evaluation scores, provider health, and
  event counts.
- Export Markdown, JSON, and CSV summaries from preserved run directories.
- Include provenance links to input fixtures and budget files.
- Keep benchmark claims tied to preserved artifacts.

Acceptance criteria:

- [ ] Comparison refuses incompatible report types with a clear error.
- [ ] Exported Markdown includes command, provider, operation, date, and artifact references.
- [ ] CSV and JSON exports are stable enough for issue attachments.
- [ ] Docs explain how to cite benchmark artifacts.

Validation:

```bash
uv run pytest tests/test_benchmark.py tests/test_evaluation_suites.py tests/test_harness_flows.py
uv run mkdocs build --strict
```

### WF-HARNESS-005: Provider Development Workbench

Type: harness  
Labels: `harness`, `provider`, `developer-experience`  
Depends on: WF-PROV-003, WF-HARNESS-002

Problem: Adapter authors need a tight loop for fixture playback, health checks, capability tests,
event inspection, and docs drift before opening a provider PR.

Scope:

- Add a workbench flow that runs provider conformance checks against a selected provider.
- Support fixture playback for HTTP adapters and injected runtimes for local adapters.
- Show missing docs/catalog updates when profile metadata changes.
- Do not run live provider calls unless explicitly selected.

Acceptance criteria:

- [ ] Workbench can run against `mock` in a clean checkout.
- [ ] Workbench lists required tests for each advertised capability.
- [ ] Workbench links to provider authoring docs and generated catalog check.
- [ ] Failures are actionable enough to paste into GitHub issues.

Validation:

```bash
uv run pytest tests/test_provider_contracts.py tests/test_harness_flows.py
uv run --extra harness pytest tests/test_harness_tui.py
```

## Workstream D: Reference Host Applications

Reference host apps are examples of ownership boundaries. They should be complete enough to copy
from, but they should not become required runtime paths for the library.

Track status: complete for [#50](https://github.com/AbdelStark/worldforge/issues/50).

Completion signals:

- `examples/hosts/batch-eval/` runs clean-checkout eval and benchmark jobs with preserved
  `.worldforge/batch-eval/runs/<run-id>/` artifacts, copied benchmark inputs and budgets, and
  non-zero exits for budget violations.
- `examples/hosts/service/` exposes stdlib HTTP liveness, readiness, provider diagnostics, typed
  public error payloads, request-id correlation, and JSON provider-event logging without moving
  deployment or alerting into WorldForge.
- `examples/hosts/robotics-operator/` keeps operator review non-mutating by default, requires an
  explicit action translator, records approval/replay/evidence artifacts, and leaves controller
  execution behind a host-supplied hook.
- [Examples docs](./examples.md) present all three host apps as optional references and repeat the
  host-owned boundaries for scheduling, durable storage, telemetry, credentials, controller
  integration, interlocks, and safety certification.

Host app packaging rules:

- Put reference hosts under `examples/hosts/<name>/`.
- Keep host-specific dependencies outside the base package.
- Prefer `uv run --with ...` instructions or a dedicated optional extra only when the dependency
  set is broadly useful.
- Include `.env.example` fragments only when they do not introduce real secrets.
- Each host app must state whether it is checkout-safe, prepared-host, credentialed, GPU-bound, or
  robotics-lab-only.

Host app acceptance standard:

| Host type | Must demonstrate | Must not imply |
| --- | --- | --- |
| Batch evaluation | CLI/job entrypoint, input fixtures, budgets, run artifacts, non-zero failure exits | hosted scheduling, long-term storage, empirical claims beyond artifacts |
| Service | readiness checks, typed errors, request IDs, logs/metrics hooks, timeout policy | WorldForge owning uptime, auth, routing, or dashboards |
| Robotics operator | dry-run review, policy/score evidence, action translator, approval record | automatic robot safety, controller ownership, certified execution |

### WF-HOST-001: Batch Evaluation Host

Type: host application  
Labels: `examples`, `evaluation`, `operations`  
Depends on: WF-HARNESS-001, WF-PROV-004

Problem: Users need a production-shaped example for running provider evals and benchmarks as
batch jobs with artifacts, budgets, and exit codes.

Scope:

- Add an optional example host under `examples/hosts/batch-eval/`.
- Use WorldForge APIs, benchmark input files, budget files, run manifests, and report exports.
- Keep dependencies optional and installable through `uv run --with ...` or a documented extra.
- Do not add a scheduler or queue to the base package.

Acceptance criteria:

- [x] Host can run `mock` eval and benchmark jobs in a clean checkout.
- [x] Host writes run workspace artifacts and exits non-zero on budget violations.
- [x] Docs explain how to swap in a real provider on a prepared host.
- [x] Package contract remains base-dependency clean.

Validation:

```bash
uv run pytest tests/test_batch_eval_host.py
bash scripts/test_package.sh
uv run mkdocs build --strict
```

### WF-HOST-002: Service Host Reference

Type: host application  
Labels: `examples`, `operations`, `observability`  
Depends on: WF-OBS-001, WF-OBS-002, WF-OPS-002

Problem: Services embedding WorldForge need a reference for request IDs, readiness checks,
provider calls, structured logs, metrics export, timeout budgets, and clean failure responses.

Scope:

- Add an optional service host example under `examples/hosts/service/`.
- Expose health/readiness, provider list, one safe mock workflow, and one configurable provider
  workflow.
- Keep the web framework optional and outside the base package.
- Demonstrate redacted logs, request IDs, and provider event correlation.

Acceptance criteria:

- [x] Service host runs with only optional example dependencies.
- [x] Health/readiness distinguish framework alive, provider configured, and provider healthy.
- [x] Provider errors return typed public error payloads without internal secrets.
- [x] Docs state this is a reference host, not the WorldForge product boundary.

Validation:

```bash
uv run pytest tests/test_service_host.py
uv run mkdocs build --strict
```

### WF-HOST-003: Robotics Lab Operator Host

Type: host application  
Labels: `examples`, `robotics`, `operations`, `safety`  
Depends on: WF-LEROBOT-002, WF-GROOT-001, WF-HARNESS-003

Problem: Robotics users need an example that composes policy, score, replay, and operator approval
without implying WorldForge controls robot hardware.

Scope:

- Add an optional host example for offline operator review of policy+score runs.
- Require explicit action translator, safety checklist, and dry-run approval before any host-owned
  controller integration point.
- Export selected action chunks, score rationale, event stream, and replay artifact.
- Leave real robot execution as an integration hook with documented safety ownership.

Acceptance criteria:

- [x] The default mode is non-mutating and does not talk to robot controllers.
- [x] Controller execution hook is disabled unless the host supplies an explicit implementation.
- [x] Operator approval and dry-run artifacts are recorded.
- [x] Docs state what WorldForge does and does not certify.

Validation:

```bash
uv run pytest tests/test_robotics_operator_host.py tests/test_robotics_showcase.py
uv run mkdocs build --strict
```

## Workstream E: Observability, Monitoring, And Logging

Observability work must keep the core callback model simple while giving production hosts clean
integration points.

Track status: complete for [#51](https://github.com/AbdelStark/worldforge/issues/51).

Completion signals:

- `ProviderEvent` carries sanitized correlation fields and normalized phases for run, request,
  trace, span, artifact, and input-digest joins.
- `JsonLoggerSink`, `RunJsonLogSink`, `ProviderMetricsSink`, `ProviderMetricsExporterSink`,
  `OpenTelemetryProviderEventSink`, and `InMemoryRecorderSink` share the same event model without
  adding base runtime dependencies.
- Run logs and manifests preserve issue-safe provider evidence under `.worldforge/runs/<run-id>/`.
- The service host exposes process liveness separately from `ready`, `provider_unconfigured`, and
  `provider_unhealthy` readiness states.
- Operations docs and playbooks map `worldforge doctor`, provider health, provider events, and
  incident runbooks to host-owned escalation paths.

Telemetry layering:

```text
ProviderEvent
  -> in-process sinks
  -> optional run log / run manifest
  -> optional exporter adapters
  -> host collector / dashboard / alerting
```

Required semantics:

| Signal | Source | Notes |
| --- | --- | --- |
| request attempt | provider event per upstream call or model-boundary call | Retries are attempts, not separate logical user workflows. |
| retry | provider event with `phase=retry` | Include attempt and sanitized target when available. |
| failure | provider event with `phase=failure` plus typed exception | Preserve error family without raw secret payloads. |
| latency | event `duration_ms` | Use histograms for exported metrics; do not compute from wall-clock UI render times. |
| run status | run manifest | Values should include passed, failed, skipped, cancelled, and not configured. |
| readiness | host app or CLI preflight | Distinguish configured, dependency available, upstream reachable, and workflow-ready. |

Exporter rules:

- Exporters are optional adapters over existing events; they must not change provider execution.
- Metrics labels must be bounded. Use provider, operation, capability, phase, and status class.
- Do not use prompts, targets with query strings, world IDs, run IDs, object IDs, or metadata keys
  as metrics labels.
- Trace/span attributes must be sanitized before export.
- Log files and issue bundles must be safe by default; local-only artifacts need explicit marking.

### WF-OBS-001: Provider Event Schema v2

Type: observability  
Labels: `observability`, `provider`, `security`  
Depends on: WF-PROV-004

Problem: `ProviderEvent` is already useful, but production hosts need stable correlation fields,
run IDs, request IDs, normalized phases, and stronger schema documentation.

Scope:

- Add optional `run_id`, `request_id`, `trace_id`, `span_id`, `artifact_id`, and `input_digest`
  fields if they can remain JSON-native and redacted.
- Preserve backward compatibility where possible.
- Document event phases and field semantics.
- Expand redaction tests for new fields.

Acceptance criteria:

- [x] Existing sinks keep working or have documented migration behavior.
- [x] Event fields are JSON-native and sanitized before sink consumption.
- [x] Provider events can be correlated with run manifests.
- [x] Docs include sample JSON log records.

Validation:

```bash
uv run pytest tests/test_observability.py tests/test_remote_video_providers.py
uv run mkdocs build --strict
```

### WF-OBS-002: Optional OpenTelemetry Exporter

Type: observability  
Labels: `observability`, `operations`, `optional-dependency`  
Depends on: WF-OBS-001

Problem: Production hosts often use OpenTelemetry, but WorldForge should not force it into the base
package.

Scope:

- Add an optional exporter module or extra for mapping provider events to spans and attributes.
- Keep exporter disabled by default.
- Document semantic attribute names, redaction guarantees, and host responsibility for collector
  configuration.
- Tests should not require a real collector.

Acceptance criteria:

- [x] Importing `worldforge` does not import OpenTelemetry.
- [x] Exporter maps provider, operation, phase, status, duration, attempt, and sanitized target.
- [x] Secret-like metadata is redacted before span attributes are created.
- [x] Docs show minimal host wiring.

Validation:

```bash
uv run pytest tests/test_observability_opentelemetry.py tests/test_observability.py
bash scripts/test_package.sh
uv run mkdocs build --strict
```

### WF-OBS-003: Optional Metrics Exporter

Type: observability  
Labels: `observability`, `operations`, `optional-dependency`  
Depends on: WF-OBS-001

Problem: `ProviderMetricsSink` aggregates in memory. Hosts need an optional bridge to standard
metrics systems without changing core event semantics.

Scope:

- Add optional exporter hooks for counters, histograms, retries, errors, and latency.
- Keep label cardinality bounded: provider, operation, phase/status class, and capability only.
- Document why raw target URLs, prompts, metadata keys, or world IDs must not be metrics labels.
- Provide tests with an in-memory registry or fake exporter.

Acceptance criteria:

- [x] Metrics bridge is optional and has bounded labels.
- [x] Retry events increment retry metrics distinctly from logical operation count.
- [x] Docs explain metric meanings and alert examples.
- [x] Base package dependency set remains unchanged.

Validation:

```bash
uv run pytest tests/test_observability_metrics_export.py tests/test_observability.py
uv run mkdocs build --strict
```

### WF-OBS-004: Logging Configuration And Run Logs

Type: observability  
Labels: `observability`, `operations`, `logging`  
Depends on: WF-OBS-001, WF-HARNESS-001

Problem: `JsonLoggerSink` exists, but host apps need a consistent recipe for file logs, JSON logs,
run-scoped logs, and operator-safe log exports.

Scope:

- Add a logging playbook for CLI, batch host, service host, and harness runs.
- Provide a helper for run-scoped JSON log files if it stays dependency-free.
- Include redaction tests for exported log files.
- Do not override host logging configuration globally.

Acceptance criteria:

- [x] Logs can be correlated to run manifests by `run_id`.
- [x] Exported logs contain no bearer tokens, API keys, signatures, or signed URL query strings.
- [x] Docs include first triage queries for provider failures and retries.
- [x] Host apps demonstrate logger injection rather than global logging side effects.

Validation:

```bash
uv run pytest tests/test_observability.py tests/test_run_logs.py
uv run mkdocs build --strict
```

### WF-OBS-005: Health, Readiness, And Incident Runbooks

Type: operations  
Labels: `operations`, `observability`, `documentation`  
Depends on: WF-PROV-002, WF-HOST-002

Problem: Production hosts need a clear distinction between process liveness, provider configured,
provider healthy, upstream degraded, and workflow failing.

Scope:

- Document a standard health/readiness model for host applications.
- Add reference host endpoints or commands that expose those states.
- Add incident runbooks for remote provider failures, optional runtime missing dependencies,
  artifact expiration, malformed world state, and benchmark budget failures.
- Keep on-call routing and alert channels host-owned.

Acceptance criteria:

- [x] Runbooks include symptom, likely cause, first command, expected signal, and escalation point.
- [x] Host reference app uses the model.
- [x] Existing `worldforge doctor` and provider health outputs are mapped to readiness states.
- [x] Docs avoid claiming WorldForge owns upstream SLAs.

Validation:

```bash
uv run pytest tests/test_service_host.py tests/test_cli.py
uv run mkdocs build --strict
```

## Workstream F: Reliability, Security, And Release Gates

Reliability work should make failures explicit and diagnosable. It should not hide instability by
retrying indefinitely, weakening validation, or moving host responsibilities into the framework.

Reliability policy:

| Area | Default | Exception path |
| --- | --- | --- |
| Remote create/mutation | single attempt | Host may configure retries only when idempotency is clear. |
| Health checks | cheap and bounded | Deep checks belong in explicit smoke commands. |
| Downloads | retry with bounded timeout where configured | Persist artifacts immediately when upstream URLs expire. |
| Optional runtime import | lazy and failure-explicit | Never import optional model packages from `worldforge.__init__`. |
| Live tests | opt-in markers | Default CI stays deterministic. |
| Coverage gate | keep current gate | Add focused tests for new branches instead of lowering thresholds. |

Completion signal for [#52](https://github.com/AbdelStark/worldforge/issues/52): this workstream is
implemented as baseline reliability, security, and release infrastructure. `WF-OPS-001` added
per-operation provider budgets and budget-exceeded events. `WF-OPS-002` hardened credential
configuration summaries and redaction expectations across safe artifacts. `WF-OPS-003` recorded the
host-owned persistence adapter boundary in ADR 0001. `WF-OPS-004` added the release evidence bundle
and release-gate checklist. Future work should start from a narrow follow-up issue when it changes a
specific provider, host, artifact, or release workflow.

### WF-OPS-001: Provider Budget And Circuit-Breaker Policy

Type: operations  
Labels: `operations`, `provider`, `reliability`  
Depends on: WF-OBS-001

Problem: Remote and live model calls need explicit budgets for timeout, attempts, retry delay,
max run duration, and failure thresholds.

Scope:

- Extend or document `ProviderRequestPolicy` for workflow-level budgets where appropriate.
- Add host-owned circuit-breaker examples without forcing a service dependency.
- Ensure budget violations surface as typed provider/workflow errors and provider events.
- Keep create/mutation single-attempt defaults unless explicitly configured.

Acceptance criteria:

- [ ] Budgets can be set per provider operation in host examples.
- [ ] Budget failures are observable and testable.
- [ ] Docs distinguish request retry policy from workflow run budget.
- [ ] No silent retry loop can hide repeated provider failure.

Validation:

```bash
uv run pytest tests/test_provider_request_policy.py tests/test_remote_video_providers.py
uv run mkdocs build --strict
```

### WF-OPS-002: Credential And Configuration Hardening

Type: security  
Labels: `security`, `operations`, `provider`  
Depends on: WF-PROV-002

Problem: Real providers increase the chance of leaking credentials through config, logs, manifests,
events, docs, or issue attachments.

Scope:

- Audit env var loading and docs for every provider.
- Add config summaries that expose presence, source, and validation status without exposing values.
- Add secret-pattern tests for events, manifests, logs, reports, and docs examples.
- Keep `.env.example` tracked and `.env` files ignored.

Acceptance criteria:

- [ ] Every provider has documented env vars and redacted config summaries.
- [ ] Tests catch bearer/API/signature/password-like leaks in new observable surfaces.
- [ ] Issue docs explain what artifacts are safe to attach.
- [ ] Provider errors do not include raw credentials or signed URL query strings.

Validation:

```bash
uv run pytest tests/test_observability.py tests/test_provider_config.py tests/test_docs_site.py
uv run mkdocs build --strict
```

### WF-OPS-003: Durable Persistence Adapter Design

Type: architecture  
Labels: `operations`, `persistence`, `design`  
Depends on: WF-HOST-001

Problem: Local JSON state is intentionally single-writer. Some hosts will need durable multi-writer
persistence, but adding it to core without design would blur WorldForge's boundary.

Scope:

- Write an ADR for a persistence adapter interface before implementation.
- Define locking, migrations, backup/restore, retention, schema versioning, and failure recovery.
- Decide whether the first implementation belongs in core, an optional extra, or only reference
  host apps.
- Keep current local JSON behavior unchanged unless the ADR explicitly changes it.

Acceptance criteria:

- [ ] ADR names the adapter boundary and rejected alternatives.
- [ ] No database dependency is added before the ADR is accepted.
- [ ] Existing local JSON tests remain authoritative for default behavior.
- [ ] Host-owned responsibility remains clear in docs.

Validation:

```bash
uv run pytest tests/test_persistence*.py tests/test_cli_worlds.py
uv run mkdocs build --strict
```

### WF-OPS-004: Release Evidence Bundle

Type: release  
Labels: `release`, `quality`, `provider`, `documentation`  
Depends on: WF-PROV-004, WF-HARNESS-004

Problem: Provider-heavy releases need evidence bundles that say what was tested locally, what live
smokes ran, what was skipped, and which claims are supported.

Scope:

- Define a release evidence directory or generated Markdown report.
- Include validation commands, coverage, docs build, package contract, provider catalog drift,
  benchmark artifacts, live-smoke manifests, and known limitations.
- Keep live-provider evidence optional but explicit.

Acceptance criteria:

- [ ] Release evidence can be generated without credentials.
- [ ] Live-provider sections say skipped, passed, failed, or not configured.
- [ ] Evidence report links to preserved artifacts.
- [ ] Release checklist references the evidence bundle.

Validation:

```bash
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

## Risk Register

Track these risks in issues and release evidence.

| Risk | Impact | Early warning | Mitigation |
| --- | --- | --- | --- |
| Capability inflation | Users trust a provider for work it cannot do | Provider docs use broad model labels instead of exact capability names | Promotion gate, generated catalog checks, conformance tests |
| Base dependency creep | Package becomes hard to install and test | Optional model package appears in `dependencies` | Keep model/runtime packages in wrappers, extras, or host docs |
| Secret leakage | Logs, manifests, reports, or issues expose credentials | New event metadata includes targets, headers, env, or raw provider messages | Redaction tests for every observable surface |
| Live smoke fragility | Provider validation cannot be reproduced | Smoke command depends on undocumented local files | Runtime manifests, prepared-host commands, skip reasons |
| Harness becoming demo-only | UI looks useful but cannot support real triage | Failed runs do not preserve artifacts | Run workspace, failure states, export tests |
| Host boundary drift | WorldForge starts owning service or robot responsibilities | Docs promise uptime, controller safety, or durable storage | Host app boundary statements and ADRs before implementation |
| Benchmark misuse | Deterministic contract numbers become inflated claims | Reports lack input provenance or claim boundaries | Benchmark input fixtures, budgets, evidence bundles |
| Provider API churn | External provider changes break adapters silently | Fixtures only cover happy paths | Parser fixtures, version/runtime manifests, live smoke manifests |
| Coverage floor erosion | New guard branches lower quality silently | Harness coverage hovers near threshold | Add focused tests with every provider/harness branch |

## Implementation Waves

### Wave 0: Turn Roadmap Into Trackers

Goal: create the GitHub issue backbone.

Open one tracking issue per workstream plus the first ten implementation issues listed below. Each
tracking issue should link child issues, dependency order, labels, and release evidence required.

Validation for this wave:

```bash
uv run mkdocs build --strict
```

### Wave 1: Provider Standards Before Provider Growth

Goal: prevent future provider work from becoming ad hoc.

Implement:

- WF-PROV-001: Provider Promotion Gate
- WF-PROV-002: Provider Runtime Manifest Schema
- WF-PROV-003: Provider Conformance Suite v2

Exit criteria:

- New provider issue template can reference promotion status, runtime manifest, and conformance
  helper expectations.
- Existing providers can be audited against the matrix without behavior changes.
- Default tests remain credential-free.

### Wave 2: Evidence-Carrying Live Smokes

Goal: make live provider validation reproducible and issue-attachable.

Implement:

- WF-PROV-004: Live Smoke Artifact Contract
- WF-PROV-005: Optional Runtime Test Profiles
- WF-OBS-001: Provider Event Schema v2, if run correlation fields are needed first

Exit criteria:

- Optional live smokes can write `run_manifest.json`.
- Missing runtime, missing credentials, and unsupported host states skip with clear reasons.
- Sanitized evidence can be attached to a GitHub issue.

### Wave 3: Promote Existing Real Providers

Goal: make the strongest current provider surfaces dependable before adding new provider names.

Implement:

- WF-LWM-001: LeWorldModel Stable Score Provider
- WF-LEROBOT-001: LeRobot Stable Policy Provider
- WF-COSMOS-001: Cosmos Generate Provider Production Hardening
- WF-RUNWAY-001: Runway Generate/Transfer Production Hardening

Exit criteria:

- Provider docs, generated catalog, conformance helpers, and smoke manifests agree.
- Every advertised capability has fixture-backed failure tests.
- No provider promotion adds heavy runtime packages to the base dependency set.

### Wave 4: Robotics Composition

Goal: make policy+score workflows serious enough for host-owned robotics labs.

Implement:

- WF-LEROBOT-002: Embodiment Translator Contract
- WF-GROOT-001: GR00T PolicyClient Beta Provider
- WF-LWM-002: LeWorldModel Task Bridge Pack
- WF-HOST-003: Robotics Lab Operator Host, only after translator and run evidence contracts exist

Exit criteria:

- Policy raw actions, score candidates, translated `Action` values, selected plans, and replay
  artifacts are traceable through one run manifest.
- Real robot execution remains disabled unless supplied by a host application.

### Wave 5: Harness As Operations Workspace

Goal: make TheWorldHarness useful for provider development and local operations.

Implement:

- WF-HARNESS-001: Harness Run Workspace
- WF-HARNESS-002: Provider Connector Workspace
- WF-HARNESS-003: Live Run Inspector
- WF-HARNESS-004: Report Compare And Export
- WF-HARNESS-005: Provider Development Workbench

Exit criteria:

- Harness features call the same APIs and read the same run artifacts as CLI/host examples.
- Failed runs preserve enough data for issue filing.
- Textual remains optional and isolated.

### Wave 6: Reference Hosts And Production Operations

Goal: give users copyable production shapes without turning WorldForge into a hosted platform.

Implement:

- WF-HOST-001: Batch Evaluation Host
- WF-HOST-002: Service Host Reference
- WF-OBS-002: Optional OpenTelemetry Exporter
- WF-OBS-003: Optional Metrics Exporter
- WF-OBS-004: Logging Configuration And Run Logs
- WF-OBS-005: Health, Readiness, And Incident Runbooks
- WF-OPS-001 through WF-OPS-004 as needed

Exit criteria:

- Host examples demonstrate request IDs, readiness, typed errors, budgets, sanitized logs, and
  artifact exports.
- Release evidence can say which optional providers were tested, skipped, or not configured.

## Release Gate For Roadmap Milestones

Use this gate before marking a milestone complete:

| Gate | Required signal |
| --- | --- |
| Docs | `uv run mkdocs build --strict` passes with nav/SUMMARY synchronized. |
| Generated provider docs | `uv run python scripts/generate_provider_docs.py --check` passes when provider metadata changes. |
| Unit tests | Focused tests for changed modules pass. |
| Full checkout tests | `uv run pytest` passes for deterministic paths. |
| Harness coverage | `uv run --extra harness pytest --cov=src/worldforge --cov-report=term-missing --cov-fail-under=90` passes when harness or optional-provider branches change. |
| Package contract | `bash scripts/test_package.sh` passes when package surface, optional imports, examples, or tests change. |
| Live evidence | Optional provider work includes smoke manifest or explicit skip reason. |
| Security | Observable surfaces have redaction coverage for new fields. |

## First Issue Batch

Open these first; they unblock most later work.

| Order | Issue | Why first |
| --- | --- | --- |
| 1 | WF-PROV-001: Provider Promotion Gate | Prevents noisy provider additions and status drift. |
| 2 | WF-PROV-002: Provider Runtime Manifest Schema | Creates a shared runtime contract for real providers and host apps. |
| 3 | WF-PROV-003: Provider Conformance Suite v2 | Gives every provider implementation a reusable quality bar. |
| 4 | WF-PROV-004: Live Smoke Artifact Contract | Makes live provider validation useful and debuggable. |
| 5 | WF-LWM-001: LeWorldModel Stable Score Provider | Highest-value existing real score path. |
| 6 | WF-LEROBOT-001: LeRobot Stable Policy Provider | Highest-value existing real policy path. |
| 7 | WF-LEROBOT-002: Embodiment Translator Contract | Required before serious robotics host applications. |
| 8 | WF-HARNESS-001: Harness Run Workspace | Common artifact substrate for harness, CLI, and host apps. |
| 9 | WF-OBS-001: Provider Event Schema v2 | Common observability substrate for monitoring and run manifests. |
| 10 | WF-PROVIDER-SELECT-001: Next Provider Selection RFC | Keeps the next provider batch evidence-driven. |

## Deferred Until Design Exists

- Built-in multi-writer persistence.
- Hosted dashboard as a default product surface.
- Automatic robot-controller execution.
- Bundled torch/CUDA/robotics runtime dependencies.
- Claims that deterministic eval suites measure physical fidelity.
- Provider `plan` capability for providers that only expose `score` or `policy`.

## Issue Creation Checklist

Before opening an issue from this roadmap:

- [ ] Confirm the referenced files still exist.
- [ ] Copy the issue's scope, out-of-scope notes, acceptance criteria, and validation commands.
- [ ] Add dependencies in the issue body.
- [ ] Use existing templates where possible: provider adapter, eval/benchmark, docs, or bug.
- [ ] Attach only sanitized artifacts.
- [ ] If the issue changes public behavior, include docs and generated provider catalog updates in
      the acceptance criteria.

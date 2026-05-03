# Roadmap Continuation

Last reviewed: 2026-05-01.

This document defines the next WorldForge roadmap after the first provider/platform track. It is
the source of truth for the next GitHub issue batch. The previous provider/platform roadmap is
complete as a baseline: provider promotion rules, runtime manifests, conformance helpers,
run manifests, harness workspaces, reference hosts, observability sinks, and release evidence
infrastructure exist. The continuation should not repeat that work. It should make the platform
harder to misuse, easier to extend, and more credible when provider or benchmark claims are made.

GitHub issue batch created: 2026-05-01.

| Stream | Meta tracker | Child issue range |
| --- | --- | --- |
| Provider evidence and runtime cohorts | [#127](https://github.com/AbdelStark/worldforge/issues/127) | [#130](https://github.com/AbdelStark/worldforge/issues/130), [#133](https://github.com/AbdelStark/worldforge/issues/133), [#134](https://github.com/AbdelStark/worldforge/issues/134), [#137](https://github.com/AbdelStark/worldforge/issues/137), [#138](https://github.com/AbdelStark/worldforge/issues/138), [#139](https://github.com/AbdelStark/worldforge/issues/139), [#143](https://github.com/AbdelStark/worldforge/issues/143), [#144](https://github.com/AbdelStark/worldforge/issues/144) |
| Evaluation evidence and claim integrity | [#128](https://github.com/AbdelStark/worldforge/issues/128) | [#132](https://github.com/AbdelStark/worldforge/issues/132), [#135](https://github.com/AbdelStark/worldforge/issues/135), [#136](https://github.com/AbdelStark/worldforge/issues/136), [#140](https://github.com/AbdelStark/worldforge/issues/140), [#145](https://github.com/AbdelStark/worldforge/issues/145), [#146](https://github.com/AbdelStark/worldforge/issues/146), [#147](https://github.com/AbdelStark/worldforge/issues/147), [#150](https://github.com/AbdelStark/worldforge/issues/150) |
| Operator workflow and adapter authoring | [#129](https://github.com/AbdelStark/worldforge/issues/129) | [#131](https://github.com/AbdelStark/worldforge/issues/131), [#141](https://github.com/AbdelStark/worldforge/issues/141), [#142](https://github.com/AbdelStark/worldforge/issues/142), [#148](https://github.com/AbdelStark/worldforge/issues/148), [#149](https://github.com/AbdelStark/worldforge/issues/149), [#151](https://github.com/AbdelStark/worldforge/issues/151), [#152](https://github.com/AbdelStark/worldforge/issues/152), [#153](https://github.com/AbdelStark/worldforge/issues/153) |

## Judgment

The best next course is not to add many provider names. WorldForge already has enough surface area
to prove whether the architecture is serious. The next phase should concentrate on three streams:

1. **Provider evidence and runtime cohorts:** promote or defer the next provider batch through
   executable evidence, not catalog aspiration.
2. **Evaluation evidence and claim integrity:** make every public claim traceable to preserved
   fixtures, budgets, reports, and failure cases.
3. **Operator workflow and adapter authoring:** make the happy path and failure path repeatable for
   contributors and prepared hosts without moving host-owned concerns into the base package.

This sequence protects the project from the two biggest risks now: capability inflation and
evidence-free growth. The project should look like a small reliable integration layer with strong
contracts before it tries to look broad.

## Stream A: Provider Evidence And Runtime Cohorts

Meta tracker: [**WF-A0: Provider Evidence And Runtime Cohorts**](https://github.com/AbdelStark/worldforge/issues/127).

Goal: select, promote, or defer the next provider cohort using runtime manifests, injected tests,
prepared-host smokes, and generated docs. A provider is only valuable when its capability surface
is explicit and executable.

Exit signal:

- The selected cohort has one written selection record and no more than three active provider
  implementation candidates.
- Each promoted provider has fixture-backed success and failure tests, runtime manifest coverage,
  a prepared-host smoke command, and generated provider docs.
- Deferred candidates have explicit blockers instead of placeholder scaffold behavior.
- No provider work adds torch, robotics stacks, checkpoint assets, dashboards, or web frameworks to
  the base package.

| Issue | Slice | Type | Depends on | Primary labels |
| --- | --- | --- | --- | --- |
| [WF-A1 #130](https://github.com/AbdelStark/worldforge/issues/130) | Establish the provider cohort selection record | AFK | none | `provider`, `research`, `roadmap` |
| [WF-A2 #133](https://github.com/AbdelStark/worldforge/issues/133) | Promote JEPA-WMS prepared-host score evidence | AFK | WF-A1 | `provider`, `score`, `research` |
| [WF-A3 #137](https://github.com/AbdelStark/worldforge/issues/137) | Stabilize the public JEPA score adapter | AFK | WF-A2 | `provider`, `score`, `research` |
| [WF-A4 #138](https://github.com/AbdelStark/worldforge/issues/138) | Define the spatial/3D scene provider boundary | HITL | WF-A1 | `provider`, `generate`, `design` |
| [WF-A5 #143](https://github.com/AbdelStark/worldforge/issues/143) | Implement scene artifact fixtures and validation | AFK | WF-A4 | `provider`, `generate`, `artifacts` |
| [WF-A6 #139](https://github.com/AbdelStark/worldforge/issues/139) | Resolve the Genie runtime contract decision | HITL | WF-A1 | `provider`, `generate`, `research` |
| [WF-A7 #134](https://github.com/AbdelStark/worldforge/issues/134) | Harden remote media artifact retention for Cosmos and Runway | AFK | none | `provider`, `generate`, `transfer` |
| [WF-A8 #144](https://github.com/AbdelStark/worldforge/issues/144) | Build the provider live-smoke evidence registry | AFK | WF-A2, WF-A7 | `provider`, `operations`, `artifacts` |

### WF-A1: Establish The Provider Cohort Selection Record

Problem: provider growth can become catalog noise if new work starts from name recognition instead
of callable capability, maintenance cost, fixture strategy, and smoke feasibility.

Scope:

- Create a provider cohort selection record under the docs tree.
- Score JEPA-WMS/public JEPA, Genie, spatial/3D scene generation, additional remote video APIs,
  simulator bridges, and new embodied policy stacks against the existing rubric.
- Select at most three active candidates for the next implementation cohort.
- Record explicit deferrals for candidates that do not meet the bar.

Out of scope:

- No provider implementation.
- No generated provider catalog change.
- No README provider table change.

Acceptance criteria:

- [ ] The record names the candidate, capability, upstream runtime/API, runtime ownership,
      fixture strategy, prepared-host smoke feasibility, license/maintenance risk, and decision.
- [ ] The selected cohort contains no more than three active candidates.
- [ ] Deferred candidates include a concrete blocker and a revisit trigger.
- [ ] The record links back to provider promotion rules and the provider prioritization rubric.
- [ ] Public provider docs continue to advertise only executable behavior.

Validation:

```bash
uv run mkdocs build --strict
```

### WF-A2: Promote JEPA-WMS Prepared-Host Score Evidence

Problem: JEPA-WMS is valuable only if the score path can be validated against a real upstream
runtime while keeping PyTorch, checkpoints, and task preprocessing host-owned.

Scope:

- Verify the selected upstream `facebookresearch/jepa-wms` loading path on a prepared host.
- Capture runtime version, model name, device, tensor shape summaries, candidate count, finite
  score output, best-index semantics, and score direction in a sanitized run manifest.
- Keep deterministic injected-runtime tests for checkout CI.
- Document unsupported input shapes, missing runtime, missing checkpoint, non-finite score output,
  and device fallback.

Out of scope:

- No base dependency on torch or JEPA-WMS packages.
- No public `predict`, `embed`, `generate`, or `reason` capability.
- No auto-registration change unless the evidence supports it and docs/catalog are updated.

Acceptance criteria:

- [ ] Prepared-host smoke writes `run_manifest.json` with provider, capability, runtime manifest,
      input digest, result digest, event count, and safe tensor shape summaries.
- [ ] Tests cover success, missing runtime, missing model, malformed tensor shapes, mismatched
      candidate count, and non-finite scores.
- [ ] Provider events and manifests contain no raw tensors, credentials, host-local secrets, or
      signed URLs.
- [ ] Docs state direct-construction versus catalog behavior after the decision.
- [ ] The base dependency set remains unchanged.

Validation:

```bash
uv run pytest tests/test_jepa_wms_provider.py tests/test_provider_contracts.py
uv run python scripts/generate_provider_docs.py --check
uv run mkdocs build --strict
```

### WF-A3: Stabilize The Public JEPA Score Adapter

Problem: the public `jepa` adapter should stay experimental unless it has a sharply defined score
surface backed by the same evidence contract as JEPA-WMS.

Scope:

- Align `jepa` configuration, diagnostics, runtime manifest, docs, and failure typing around a
  score-only adapter.
- Preserve the legacy scaffold variable only as value-free diagnostic metadata.
- Ensure unsupported capabilities fail loudly and are absent from provider capability flags.
- Add migration notes for hosts that previously configured the scaffold reservation.

Out of scope:

- No latent rollout or embedding API without a separate contract.
- No surrogate/mock behavior advertised as real JEPA integration.
- No change to the provider name unless the cohort record recommends it.

Acceptance criteria:

- [ ] `jepa` advertises exactly the implemented score surface.
- [ ] Health output distinguishes missing model name, missing optional dependency, missing
      checkpoint/model, and malformed runtime output.
- [ ] Docs explain why `JEPA_MODEL_PATH` is legacy metadata and `JEPA_MODEL_NAME` controls the real
      runtime path.
- [ ] Generated provider docs match provider profile metadata.
- [ ] Conformance helpers cover the public score surface.

Validation:

```bash
uv run pytest tests/test_jepa_provider.py tests/test_jepa_wms_provider.py tests/test_provider_catalog_docs.py
uv run python scripts/generate_provider_docs.py --check
uv run mkdocs build --strict
```

### WF-A4: Define The Spatial/3D Scene Provider Boundary

Problem: scene and 3D-world generation are distinct from video generation, prediction, and
planning. Adding a provider before defining the artifact contract would blur the capability model.

Scope:

- Write a design record that chooses the first spatial/3D scene runtime or API candidate.
- Define the minimal JSON-native scene artifact boundary: units, coordinate frames, asset
  references, object identifiers, transforms, media references, provenance, and safe metadata.
- Decide whether the first capability is `generate` or a new future surface that should remain out
  of scope for now.
- Define redaction rules for asset URLs, host-local paths, and provider metadata.

Out of scope:

- No provider implementation.
- No viewer, renderer, simulator, or 3D asset dependency in the base package.
- No claim that generated scenes are physically valid.

Acceptance criteria:

- [ ] The design record names accepted and rejected runtime/API candidates.
- [ ] The scene artifact boundary is JSON-native and testable without optional dependencies.
- [ ] The record states whether the work maps to `generate` or remains deferred.
- [ ] Host-owned responsibilities for asset storage, rendering, simulation, and licensing are
      explicit.
- [ ] Follow-up implementation issues can be created without reopening capability semantics.

Validation:

```bash
uv run mkdocs build --strict
```

### WF-A5: Implement Scene Artifact Fixtures And Validation

Problem: if a spatial/3D provider proceeds, WorldForge needs fixtures and validators before any
runtime-specific adapter code.

Scope:

- Add fixture schemas for valid scene artifacts, malformed transforms, invalid units, unsafe asset
  references, and oversized metadata.
- Add validation helpers that reject non-JSON-native metadata and non-finite numeric values.
- Add docs showing the artifact boundary and safe issue-attachment expectations.
- Keep rendering, simulation, and asset fetching host-owned.

Out of scope:

- No live provider call.
- No bundled 3D assets beyond tiny fixtures needed for validation.
- No base runtime dependency changes.

Acceptance criteria:

- [ ] Fixtures cover valid and invalid scene payloads.
- [ ] Validation rejects non-finite numbers, tuple-shaped values, object instances, unsafe URLs, and
      host-local paths unless marked local-only.
- [ ] Docs state what the artifact does and does not prove.
- [ ] Tests run in a clean checkout without network or optional packages.

Validation:

```bash
uv run pytest tests/test_scene_artifacts.py tests/test_provider_contracts.py
uv run mkdocs build --strict
```

### WF-A6: Resolve The Genie Runtime Contract Decision

Problem: Genie remains a fail-closed reservation. It should either gain one concrete upstream
runtime/API contract or stay deferred with a precise reason.

Scope:

- Review current public Genie automation/runtime options.
- Choose one explicit contract or record a defer decision.
- If deferred, harden docs to state the revisit trigger and prevent surrogate expectations.
- If selected, write the implementation issue for fixture-backed `generate` behavior.

Out of scope:

- No deterministic surrogate presented as real Genie behavior.
- No default capability flags before a real runtime/API exists.
- No large runtime, browser automation stack, or model dependency in the base package.

Acceptance criteria:

- [ ] The issue closes with either a selected runtime/API contract or a documented defer decision.
- [ ] Docs explain the decision in provider, roadmap, and selection-record surfaces.
- [ ] If deferred, provider health and docs remain fail-closed and value-free.
- [ ] If selected, the follow-up issue names fixtures, smoke command, artifacts, failure modes, and
      generated docs updates.

Validation:

```bash
uv run pytest tests/test_remote_scaffold_providers.py tests/test_provider_catalog_docs.py
uv run mkdocs build --strict
```

### WF-A7: Harden Remote Media Artifact Retention For Cosmos And Runway

Problem: remote media adapters are useful only if downloaded artifacts, expired URLs, content
types, and retention guidance are consistent across docs, events, and run manifests.

Scope:

- Audit Cosmos and Runway artifact download, retention, content-type, and URL-expiration paths.
- Ensure signed URL query strings never reach events, manifests, logs, reports, or issue bundles.
- Add fixture coverage for expired artifacts, unsupported media, failed task states, and download
  retry exhaustion.
- Document first recovery steps for each provider.

Out of scope:

- No hosted artifact store.
- No automatic media upload service.
- No broad media provider expansion.

Acceptance criteria:

- [ ] Both providers document artifact lifetime assumptions and first triage command.
- [ ] Parser and provider-error tests cover expired URL, unsupported artifact, failed polling, and
      malformed response cases.
- [ ] Run manifests preserve artifact digests or safe local paths, not signed remote URLs.
- [ ] Benchmark inputs for `generate` and `transfer` stay separate and reproducible.

Validation:

```bash
uv run pytest tests/test_cosmos_provider.py tests/test_runway_provider.py tests/test_remote_video_providers.py tests/test_observability.py
uv run python scripts/generate_provider_docs.py --check
uv run mkdocs build --strict
```

### WF-A8: Build The Provider Live-Smoke Evidence Registry

Problem: prepared-host smoke results are currently preserved per run, but maintainers need a
single lightweight registry that records which optional providers have recent evidence and which
were skipped.

Scope:

- Define a docs-backed or generated registry for live-smoke evidence entries.
- Record provider, capability, command, runtime manifest, date, version, status, artifact path,
  skip reason, and known limitations.
- Keep the registry safe to publish by default.
- Link the registry from provider docs and release evidence.

Out of scope:

- No CI job that requires credentials, GPUs, checkpoints, or paid APIs by default.
- No uploading of raw artifacts or secrets.
- No claims that smoke evidence is a benchmark.

Acceptance criteria:

- [ ] Registry entries validate against a small schema.
- [ ] Missing optional runtime and credential skips are first-class statuses.
- [ ] Release evidence can include the registry without manual copy-paste.
- [ ] Docs explain how to attach sanitized run manifests to provider issues.

Validation:

```bash
uv run pytest tests/test_live_smoke_evidence.py tests/test_smoke_run_manifest.py
uv run mkdocs build --strict
```

## Stream B: Evaluation Evidence And Claim Integrity

Meta tracker: [**WF-B0: Evaluation Evidence And Claim Integrity**](https://github.com/AbdelStark/worldforge/issues/128).

Goal: turn evaluations and benchmarks into reproducible evidence, not loose quality claims. The
framework can provide deterministic contract signals, preserved artifacts, budgets, and comparison
tools. It should not imply physical fidelity or provider superiority without evidence.

Exit signal:

- Evaluation and benchmark outputs carry provenance, fixture identity, budget context, and claim
  boundaries.
- Public docs have a claim-to-evidence map that names supported, unsupported, and deferred claims.
- Release evidence can be generated from preserved artifacts without credentials.
- Failures and regressions are inspectable, not hidden behind aggregate scores.

| Issue | Slice | Type | Depends on | Primary labels |
| --- | --- | --- | --- | --- |
| [WF-B1 #132](https://github.com/AbdelStark/worldforge/issues/132) | Define evaluation result provenance v2 | AFK | none | `evaluation`, `artifacts`, `quality` |
| [WF-B2 #135](https://github.com/AbdelStark/worldforge/issues/135) | Build a capability fixture corpus | AFK | WF-B1 | `evaluation`, `testing`, `provider` |
| [WF-B3 #136](https://github.com/AbdelStark/worldforge/issues/136) | Add benchmark preset suites for release regressions | AFK | WF-B1 | `benchmark`, `release`, `quality` |
| [WF-B4 #140](https://github.com/AbdelStark/worldforge/issues/140) | Create a claim-to-evidence map for public docs | AFK | WF-B1 | `documentation`, `quality`, `release` |
| [WF-B5 #145](https://github.com/AbdelStark/worldforge/issues/145) | Generate reproducible evaluation evidence bundles | AFK | WF-B2, WF-B3 | `evaluation`, `benchmark`, `artifacts` |
| [WF-B6 #146](https://github.com/AbdelStark/worldforge/issues/146) | Calibrate benchmark budgets from preserved baselines | AFK | WF-B3 | `benchmark`, `quality`, `release` |
| [WF-B7 #147](https://github.com/AbdelStark/worldforge/issues/147) | Add failure-case galleries for evaluation suites | AFK | WF-B2 | `evaluation`, `documentation`, `quality` |
| [WF-B8 #150](https://github.com/AbdelStark/worldforge/issues/150) | Add cross-provider comparison reports | AFK | WF-B5 | `benchmark`, `evaluation`, `harness` |

### WF-B1: Define Evaluation Result Provenance v2

Problem: evaluation results need enough provenance to support claims, reproduce failures, and
compare runs without relying on console logs.

Scope:

- Define a result provenance envelope for evaluation and benchmark outputs.
- Include WorldForge version, command, provider, capability, input fixture digest, budget file,
  runtime manifest, event count, result digest, suite version, and claim boundary notes.
- Preserve backward compatibility or document migration behavior for existing reports.
- Validate finite numeric metrics and coherent counts before rendering artifacts.

Out of scope:

- No live provider execution.
- No change to score semantics for existing suites.
- No physical-fidelity claim expansion.

Acceptance criteria:

- [x] Evaluation and benchmark reports include a provenance envelope.
- [x] Invalid metrics, missing suite names, non-finite values, and mismatched counts fail before
      report rendering.
- [x] Existing CLI report formats remain stable or have documented migrations.
- [x] Docs explain how provenance should be cited in issues and release evidence.

Validation:

```bash
uv run pytest tests/test_provenance.py tests/test_evaluation_and_planning.py tests/test_benchmark.py
uv run mkdocs build --strict
```

### WF-B2: Build A Capability Fixture Corpus

Problem: provider and evaluation work needs a shared fixture corpus for score, policy, generate,
transfer, predict, reason, and embed paths instead of ad hoc payloads per test.

Scope:

- Add small JSON fixtures for each capability with success and failure cases.
- Include malformed metadata, non-finite numeric values, unsafe artifact references, invalid action
  payloads, and capability mismatch cases.
- Document fixture ownership and how providers should reuse the corpus.
- Keep binary assets tiny or represented by digests/base64 only when necessary.

Out of scope:

- No large datasets.
- No downloaded checkpoints or media artifacts.
- No live provider credentials.

Acceptance criteria:

- [ ] Each capability has at least one valid fixture and two invalid boundary fixtures.
- [ ] Fixtures are used by conformance or evaluation tests.
- [ ] Fixture docs state whether data is synthetic, captured, or host-supplied.
- [ ] Package contract remains small and installable.

Validation:

```bash
uv run pytest tests/test_provider_contracts.py tests/test_evaluation_suites.py
bash scripts/test_package.sh
uv run mkdocs build --strict
```

### WF-B3: Add Benchmark Preset Suites For Release Regressions

Problem: benchmark input files and budget files exist, but maintainers need named presets that
separate fast checkout regression checks from prepared-host provider evidence.

Scope:

- Define benchmark presets for checkout-safe mock runs, provider parser overhead, remote media
  dry-run/fixture runs, optional score/policy prepared-host runs, and release evidence.
- Keep preset inputs deterministic and small.
- Document commands, expected success signals, and when a preset is allowed to fail.
- Ensure failed budgets exit non-zero and preserve enough report data for triage.

Out of scope:

- No default live API calls in CI.
- No performance claims across machines without preserved context.
- No paid-provider benchmark jobs by default.

Acceptance criteria:

- [ ] Presets can be listed and run from the CLI or documented make targets.
- [ ] Checkout-safe presets run without credentials, network, GPUs, or optional runtimes.
- [ ] Prepared-host presets skip or fail with typed reasons when prerequisites are missing.
- [ ] Budget violations include operation, metric, threshold, observed value, and artifact path.

Validation:

```bash
uv run pytest tests/test_benchmark.py tests/test_cli_help_snapshots.py
uv run worldforge benchmark --provider mock --operation generate --budget-file examples/benchmark-budget.json
uv run mkdocs build --strict
```

### WF-B4: Create A Claim-To-Evidence Map For Public Docs

Problem: public docs should make it obvious which claims are supported by deterministic tests,
which need prepared-host evidence, and which are intentionally non-goals.

Scope:

- Add a claim-to-evidence map in docs.
- Classify claims as checkout-tested, fixture-tested, prepared-host smoke-tested, release-gated,
  deferred, or unsupported.
- Link claims to commands, artifacts, tests, docs pages, and known limitations.
- Include non-claims for physical fidelity, robot safety certification, upstream SLA ownership,
  and service-grade persistence.

Out of scope:

- No new benchmark numbers.
- No broader marketing language.
- No change to provider capability flags.

Acceptance criteria:

- [ ] Every README-level capability claim has a corresponding evidence class.
- [ ] Unsupported or deferred claims are visible and specific.
- [ ] Docs route users to preserved artifacts or commands instead of vague confidence language.
- [ ] MkDocs strict build passes with nav and SUMMARY synchronized.

Validation:

```bash
uv run mkdocs build --strict
uv run pytest tests/test_docs_site.py
```

### WF-B5: Generate Reproducible Evaluation Evidence Bundles

Problem: release and issue triage need a single evidence bundle that gathers reports, manifests,
commands, budgets, fixture digests, and skip reasons.

Scope:

- Add a command or script that creates an evaluation evidence directory from selected runs.
- Include JSON and Markdown summaries, copied input fixtures, budget files, run manifests, event
  logs, and a manifest of bundle contents.
- Redact or reject unsafe artifacts by default.
- Keep bundle generation deterministic and credential-free for checkout-safe runs.

Out of scope:

- No artifact upload service.
- No live provider execution unless explicitly requested by the host.
- No inclusion of raw secrets, signed URLs, raw tensors, or large binary outputs by default.

Acceptance criteria:

- [ ] Bundle generation succeeds for mock eval and benchmark runs in a clean checkout.
- [ ] Bundle manifest includes file digests and safe-to-attach flags.
- [ ] Unsafe or local-only artifacts are excluded or clearly marked.
- [ ] Release evidence can link to the generated bundle.

Validation:

```bash
uv run pytest tests/test_evidence_bundle.py tests/test_harness_workspace.py tests/test_observability.py
uv run mkdocs build --strict
```

### WF-B6: Calibrate Benchmark Budgets From Preserved Baselines

Problem: budgets are useful only when they are calibrated from preserved baselines and updated
through an explicit review path.

Scope:

- Add a workflow for generating candidate budgets from preserved benchmark reports.
- Store baseline context: machine class if available, Python version, command, provider,
  operation, sample count, and fixture digest.
- Require human review before replacing release budget files.
- Document when budget changes are allowed.

Out of scope:

- No automatic weakening of release gates.
- No machine-independent performance claims from local runs.
- No flaky live-provider budget in default CI.

Acceptance criteria:

- [ ] Candidate budget generation records source report digests.
- [ ] Budget diffs show old threshold, candidate threshold, observed baseline, and rationale field.
- [ ] Docs require review for threshold loosening.
- [ ] Existing budget failure behavior remains non-zero.

Validation:

```bash
uv run pytest tests/test_benchmark.py tests/test_benchmark_budget_calibration.py
uv run mkdocs build --strict
```

### WF-B7: Add Failure-Case Galleries For Evaluation Suites

Problem: aggregate scores hide what failed. Users need representative failure cases that show
input, expected contract, observed result, and triage steps.

Scope:

- Add failure-case gallery generation for deterministic evaluation suites.
- Include compact examples for physics, planning, reasoning, generation, transfer, score, and
  policy where applicable.
- Keep examples sanitized and small.
- Document how to use galleries when filing issues or reviewing provider changes.

Out of scope:

- No visual-heavy dashboard.
- No large media corpus.
- No provider quality ranking from synthetic failures.

Acceptance criteria:

- [ ] Failed evaluation reports include representative cases with fixture IDs and expected
      contract notes.
- [ ] Galleries are exported as JSON and Markdown.
- [ ] Reports avoid raw secrets, signed URLs, raw tensors, and host-local paths.
- [ ] Docs explain that galleries are deterministic contract triage, not fidelity claims.

Validation:

```bash
uv run pytest tests/test_evaluation_suites.py tests/test_evaluation_failure_gallery.py
uv run mkdocs build --strict
```

### WF-B8: Add Cross-Provider Comparison Reports

Problem: users need to compare preserved runs across providers and capabilities without confusing
capability mismatch with performance or quality.

Scope:

- Extend run comparison to group by provider, capability, operation, fixture digest, budget, and
  suite version.
- Refuse incompatible comparisons with explicit errors.
- Export JSON, Markdown, and CSV reports suitable for issue attachments.
- Surface missing evidence and skip reasons instead of silently omitting providers.

Out of scope:

- No public leaderboard.
- No ranking across different tasks or capabilities.
- No live provider execution by default.

Acceptance criteria:

- [ ] Compatible runs compare with provenance, metric deltas, event counts, and budget status.
- [ ] Incompatible runs fail with provider/capability/fixture mismatch details.
- [ ] Markdown output includes claim-boundary language.
- [ ] Harness and CLI comparison paths use the same underlying report model.

Validation:

```bash
uv run pytest tests/test_harness_report_compare.py tests/test_benchmark.py tests/test_evaluation_suites.py
uv run mkdocs build --strict
```

## Stream C: Operator Workflow And Adapter Authoring

Meta tracker: [**WF-C0: Operator Workflow And Adapter Authoring**](https://github.com/AbdelStark/worldforge/issues/129).

Goal: make WorldForge easier to operate and extend without hiding complexity. Contributors should
have a clear path from provider idea to selection record, scaffold, tests, docs, smoke evidence,
and issue-ready artifacts. Operators should be able to diagnose local runs without reading source.

Exit signal:

- Adapter authors can generate a scaffold with runtime manifest, docs stub, fixtures, tests, and
  workbench checks.
- Operators can export a sanitized issue bundle from a failed run.
- The harness and CLI expose the same operational workflows and recovery commands.
- Contributor triage, labels, and release labels match the roadmap streams.

| Issue | Slice | Type | Depends on | Primary labels |
| --- | --- | --- | --- | --- |
| [WF-C1 #141](https://github.com/AbdelStark/worldforge/issues/141) | Build the adapter author workbench path | AFK | WF-A1 | `developer-experience`, `provider`, `harness` |
| [WF-C2 #142](https://github.com/AbdelStark/worldforge/issues/142) | Upgrade provider scaffold generation for full contracts | AFK | WF-C1 | `developer-experience`, `provider`, `testing` |
| [WF-C3 #148](https://github.com/AbdelStark/worldforge/issues/148) | Export issue-ready run bundles | AFK | WF-B5 | `operations`, `artifacts`, `observability` |
| [WF-C4 #149](https://github.com/AbdelStark/worldforge/issues/149) | Tighten harness workflows for repeated local operations | AFK | WF-C3 | `harness`, `operations`, `developer-experience` |
| [WF-C5 #151](https://github.com/AbdelStark/worldforge/issues/151) | Expand reference host deployment recipes | AFK | WF-C3 | `examples`, `operations`, `documentation` |
| [WF-C6 #152](https://github.com/AbdelStark/worldforge/issues/152) | Add operator runbook drill commands | AFK | WF-C5 | `operations`, `reliability`, `testing` |
| [WF-C7 #153](https://github.com/AbdelStark/worldforge/issues/153) | Add local state preflight and recovery checks | AFK | WF-C6 | `persistence`, `operations`, `reliability` |
| [WF-C8 #131](https://github.com/AbdelStark/worldforge/issues/131) | Define contributor triage taxonomy and release labels | AFK | none | `roadmap`, `documentation`, `quality` |

### WF-C1: Build The Adapter Author Workbench Path

Problem: provider authors need one guided loop that starts from a selection record and ends with
conformance checks, docs drift checks, and issue-ready output.

Scope:

- Extend the provider workbench path to accept a provider candidate or scaffold.
- Show required promotion evidence, runtime manifest status, fixture coverage, docs/catalog drift,
  conformance helper status, and redaction checks.
- Emit Markdown suitable for a GitHub issue or PR description.
- Keep live calls opt-in.

Out of scope:

- No automatic provider implementation.
- No live API calls without explicit flags.
- No dependency installation for optional runtimes.

Acceptance criteria:

- [ ] Workbench can run against `mock` and at least one scaffold/candidate in a clean checkout.
- [ ] Output names missing evidence by promotion status.
- [ ] Markdown output includes validation commands and safe artifact references.
- [ ] TUI and CLI workbench views use the same non-Textual flow logic.

Validation:

```bash
uv run pytest tests/test_provider_workbench.py tests/test_harness_flows.py tests/test_harness_cli.py
uv run --extra harness pytest tests/test_harness_tui.py
uv run mkdocs build --strict
```

### WF-C2: Upgrade Provider Scaffold Generation For Full Contracts

Problem: the scaffold generator should create the right empty contract surfaces so new provider
work starts from tests, docs, manifest stubs, and failure modes rather than only adapter code.

Scope:

- Update scaffold generation to emit provider file, fixture placeholders, tests, docs stub,
  runtime manifest stub, and workbench checklist.
- Require the planned capability and implementation status.
- Generate fail-closed behavior by default.
- Document generated files and next validation commands.

Out of scope:

- No auto-registration of scaffold providers.
- No generated code that claims real runtime behavior.
- No base dependency changes.

Acceptance criteria:

- [ ] Scaffold output includes tests for unsupported capability calls and provider profile metadata.
- [ ] Generated manifest stubs are clearly marked incomplete and not used as real evidence.
- [ ] Generated docs warn that the provider is not executable until promotion criteria pass.
- [ ] Running the scaffold command does not overwrite existing files unless explicitly requested.

Validation:

```bash
uv run pytest tests/test_scaffold_provider.py tests/test_provider_catalog_docs.py
uv run mkdocs build --strict
```

### WF-C3: Export Issue-Ready Run Bundles

Problem: failed runs should produce a small bundle that maintainers can inspect without asking for
raw logs, credentials, or host-local state.

Scope:

- Add a command to export a sanitized bundle from `.worldforge/runs/<run-id>/`.
- Include run manifest, provider events, result summary, validation errors, report exports, and
  digest manifest.
- Redact or reject unsafe fields.
- Print a short issue template section with command, expected signal, observed failure, artifacts,
  and safe-to-attach notes.

Out of scope:

- No automatic GitHub issue creation from failed runs.
- No inclusion of raw prompts, raw tensors, robot serials, signed URLs, or secrets.
- No service-grade artifact store.

Acceptance criteria:

- [ ] Export succeeds for successful, failed, skipped, and cancelled mock runs.
- [ ] Unsafe metadata causes a clear error or local-only marking.
- [ ] Bundle manifest contains digests and safe-to-attach flags.
- [ ] Docs explain the first triage step after export.

Validation:

```bash
uv run pytest tests/test_issue_bundle_export.py tests/test_harness_workspace.py tests/test_observability.py
uv run mkdocs build --strict
```

### WF-C4: Tighten Harness Workflows For Repeated Local Operations

Problem: the harness should feel like an operations workspace, not a collection of demos. Repeated
workflows need history, filtering, rerun commands, and clear failure recovery.

Scope:

- Add run history filtering by provider, capability, status, date, and safe artifact type.
- Add rerun command generation from preserved manifests.
- Surface issue-bundle export and comparison actions.
- Preserve keyboard-first navigation and Textual import isolation.

Out of scope:

- No hosted dashboard.
- No background scheduler.
- No live provider call unless the user explicitly launches it.

Acceptance criteria:

- [ ] Harness can filter and open preserved runs without optional model runtimes.
- [ ] Rerun commands are generated from sanitized manifests and omit secret values.
- [ ] Failed runs show recovery command and issue-bundle export path.
- [ ] Tests cover flow logic without importing Textual outside `worldforge.harness.tui`.

Validation:

```bash
uv run pytest tests/test_harness_flows.py tests/test_harness_workspace.py tests/test_harness_report_compare.py
uv run --extra harness pytest tests/test_harness_tui.py
uv run mkdocs build --strict
```

### WF-C5: Expand Reference Host Deployment Recipes

Problem: reference hosts exist, but users need clearer deployment recipes that state what
WorldForge owns, what the host owns, and how to validate the setup before real traffic or robotics
use.

Scope:

- Add recipes for batch eval, stdlib service, and robotics operator host deployment.
- Include env templates, process command, readiness command, smoke command, logging command,
  evidence export command, and first rollback/triage step.
- Keep deployment, auth, queueing, storage, controller integration, and alerting host-owned.

Out of scope:

- No Kubernetes, cloud, or dashboard dependency in the base package.
- No robot-controller implementation.
- No production SLA claim.

Acceptance criteria:

- [ ] Each recipe includes command, expected success signal, first failure triage step, and owned
      boundary.
- [ ] Recipes distinguish checkout-safe, prepared-host, credentialed, GPU-bound, and robotics-lab
      paths.
- [ ] `.env.example` changes are tracked only when new provider variables are introduced.
- [ ] Docs do not imply WorldForge owns uptime, safety certification, or durable storage.

Validation:

```bash
uv run pytest tests/test_docs_site.py tests/test_service_host.py tests/test_batch_eval_host.py tests/test_robotics_operator_host.py
uv run mkdocs build --strict
```

### WF-C6: Add Operator Runbook Drill Commands

Problem: runbooks are useful only if operators can rehearse common failure modes without real
provider outages.

Scope:

- Add deterministic drill commands for missing credentials, missing optional dependency, malformed
  provider output, budget violation, corrupted local world state, expired artifact, and unsafe
  event metadata.
- Make drills write run manifests or issue bundles when applicable.
- Document expected failure signals and recovery steps.
- Keep drills checkout-safe unless explicitly marked prepared-host.

Out of scope:

- No chaos service or long-running daemon.
- No live paid-provider failure injection.
- No mutation of user worlds without explicit temporary state directories.

Acceptance criteria:

- [ ] Drill commands run in a clean checkout with mock or fixtures.
- [ ] Each drill has a documented expected failure and recovery command.
- [ ] Unsafe metadata drills prove redaction gates fail closed.
- [ ] Drills do not leave persistent state outside a temporary or documented workspace.

Validation:

```bash
uv run pytest tests/test_operator_drills.py tests/test_provider_config.py tests/test_observability.py
uv run mkdocs build --strict
```

### WF-C7: Add Local State Preflight And Recovery Checks

Problem: local JSON persistence is intentionally simple, but operators still need clear preflight
and recovery commands for corrupted worlds, unsafe IDs, invalid histories, and stale run
workspaces.

Scope:

- Add or extend preflight checks for world state directory, file-safe IDs, history coherence,
  object bounding boxes, run workspace manifests, and retention pressure.
- Provide recovery commands that export diagnostics before deleting or quarantining invalid files.
- Keep multi-writer durable persistence out of scope.

Out of scope:

- No lock file.
- No SQLite or database adapter.
- No silent coercion of invalid persisted state.

Acceptance criteria:

- [ ] Preflight identifies corrupted worlds, traversal-shaped IDs, invalid history entries, stale
      run workspaces, and unsafe artifact paths.
- [ ] Recovery commands are explicit and do not silently delete user data.
- [ ] Diagnostics are safe to attach to issues by default.
- [ ] Existing local JSON behavior remains authoritative.

Validation:

```bash
uv run pytest tests/test_world_lifecycle.py tests/test_persistence*.py tests/test_harness_workspace.py
uv run mkdocs build --strict
```

### WF-C8: Define Contributor Triage Taxonomy And Release Labels

Problem: the issue tracker should reflect the roadmap streams so contributors can identify
provider work, evidence work, operator work, blockers, and release-candidate scope.

Scope:

- Document label taxonomy for roadmap stream, capability, severity, and release scope.
- Align GitHub labels with the three continuation streams.
- Add triage guidance for when an issue needs a selection record, design record, provider
  promotion gate, or release evidence.
- Update contributor docs and issue templates if needed.

Out of scope:

- No closing or rewriting existing issues without review.
- No project-management automation dependency.
- No change to security reporting policy.

Acceptance criteria:

- [ ] Labels exist for the three roadmap streams or existing labels are explicitly mapped to them.
- [ ] Contributor docs explain how to classify provider, evidence, and operator workflow issues.
- [ ] Issue templates route provider runtime work to promotion criteria and evidence requirements.
- [ ] Security-sensitive reports still route privately, not to public issues.

Validation:

```bash
uv run pytest tests/test_docs_site.py
uv run mkdocs build --strict
```

## Dependency Order

The practical order is:

1. WF-A1 and WF-C8 establish selection and triage rules.
2. WF-B1 establishes provenance language for the evidence stream.
3. WF-A2, WF-A7, WF-B2, and WF-B3 build the first reusable evidence surfaces.
4. WF-A3, WF-A4, WF-A6, WF-B4, WF-C1, and WF-C2 convert standards into provider and contributor
   workflows.
5. WF-A5, WF-A8, WF-B5, WF-B6, WF-B7, WF-C3, and WF-C4 make evidence and failures reusable.
6. WF-B8, WF-C5, WF-C6, and WF-C7 turn the result into operator-facing practice.

## Issue Creation Checklist

When creating GitHub issues from this roadmap:

- Open the three meta trackers first.
- Create child issues in dependency order and include the parent tracker number in every child.
- Use strict acceptance criteria and validation commands from this file.
- Do not create a provider issue that lacks capability, runtime ownership, failure modes, and
  docs/generated catalog expectations.
- Do not mark HITL design issues as implementation-ready until the design record is accepted.
- Keep issue bodies clear that optional runtimes, checkpoints, credentials, robot controllers,
  durable stores, telemetry collectors, and deployment policy remain host-owned.

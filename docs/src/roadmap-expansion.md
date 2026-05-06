# Roadmap Expansion

This roadmap expands WorldForge beyond the completed continuation tracks. It deliberately excludes
the Nano World Model issue because that work is already assigned. The plan is split into three
major streams with ten implementation issues each:

- Production Grade, Quality, DevX, And Docs
- Demos, End-to-End Showcases, And Use Cases
- New Features

Each issue is intended to be independently actionable. The shared rules still apply: keep optional
runtimes host-owned, keep provider capability claims truthful, preserve checkout-safe validation
paths, and avoid treating deterministic tests as physical-fidelity claims.

## Stream 1: Production Grade, Quality, DevX, And Docs

Goal: make WorldForge easier to trust, maintain, release, document, and contribute to without
moving host-owned runtime or deployment responsibilities into the base package.

### WF-PQDX-001: Add A Release Readiness Evidence Command

GitHub issue: [#179](https://github.com/AbdelStark/worldforge/issues/179)

Problem: release checks are documented, but operators still have to assemble evidence from several
commands by hand.

Scope:

- Add a release-readiness command or script that runs the documented checkout-safe gates and writes
  a structured summary artifact.
- Include docs build, provider docs drift, tests, package contract, dependency audit instructions,
  and optional live-smoke evidence references.
- Record command, timestamps, tool versions, status, and first triage step for failures.

Out of scope:

- No publishing, tagging, signing, or credential handling.
- No optional live runtime execution unless the host explicitly asks for it.

Acceptance criteria:

- [ ] One command produces JSON and Markdown release-readiness summaries.
- [ ] The summary distinguishes passed, failed, skipped, and host-owned checks.
- [ ] Docs explain expected success signals and failure triage.
- [ ] Tests cover success, failed gate, and skipped optional evidence paths.

Validation:

```bash
uv run pytest tests/test_release_evidence.py tests/test_docs_site.py
uv run mkdocs build --strict
```

### WF-PQDX-002: Create A Public API Stability And Deprecation Policy

GitHub issue: [#180](https://github.com/AbdelStark/worldforge/issues/180)

Problem: WorldForge is pre-1.0 but has real users and public adapter surfaces; contributors need a
clear compatibility policy before changing models, CLI commands, and provider contracts.

Scope:

- Document stable, provisional, experimental, and internal API tiers.
- Define deprecation notices for Python API, CLI flags, provider capabilities, docs pages, and
  artifact schemas.
- Add tests or docs checks that make deprecated surfaces visible.

Out of scope:

- No promise of 1.0 semantic stability.
- No retroactive support for removed private helpers.

Acceptance criteria:

- [ ] Docs list API tiers and examples from current modules.
- [ ] Provider capability and artifact-schema changes have a documented migration path.
- [ ] Changelog expectations for breaking changes are explicit.
- [ ] Contributors can tell when an issue needs a deprecation plan.

Validation:

```bash
uv run pytest tests/test_docs_site.py tests/test_public_api.py
uv run mkdocs build --strict
```

### WF-PQDX-003: Harden Provider Event Redaction With A Shared Corpus

GitHub issue: [#181](https://github.com/AbdelStark/worldforge/issues/181)

Problem: provider events are a security boundary, but new sinks and runtime adapters can regress
redaction without a shared malicious-input corpus.

Scope:

- Add a fixture corpus for bearer tokens, API keys, signed URLs, query strings, private endpoints,
  host-local paths, and secret-shaped metadata.
- Exercise JSON logs, metrics, OpenTelemetry, Rerun, issue bundles, and run manifests against the
  same corpus.
- Document the corpus as the contract for future event sinks.

Out of scope:

- No secret scanning of user workspaces.
- No outbound telemetry service integration.

Acceptance criteria:

- [ ] Shared fixtures cover URL, metadata, message, target, and extra-field redaction.
- [ ] Existing event sinks use the same corpus in tests.
- [ ] Unsafe values fail closed or are redacted before serialization.
- [ ] Docs identify provider events as attachable only after sanitizer checks pass.

Validation:

```bash
uv run pytest tests/test_observability.py tests/test_observability_opentelemetry.py tests/test_evidence_bundle.py tests/test_rerun_integration.py
uv run mkdocs build --strict
```

### WF-PQDX-004: Add A Troubleshooting Matrix For Error Families

GitHub issue: [#182](https://github.com/AbdelStark/worldforge/issues/182)

Problem: `WorldForgeError`, `WorldStateError`, and `ProviderError` are meaningful, but users need a
fast route from error family to owner, command, artifact, and recovery step.

Scope:

- Add a troubleshooting matrix for public error families and common messages.
- Link CLI commands, local state preflight, provider diagnostics, run bundles, and operator drills.
- Include first triage command, expected artifact, and likely owner for each row.

Out of scope:

- No change to exception inheritance unless a real contract gap is found.
- No catch-all advice that hides malformed state or provider failures.

Acceptance criteria:

- [ ] Docs map each public error family to examples and first triage steps.
- [ ] CLI and playbook references are concrete commands.
- [ ] Tests guard the presence of the matrix and key command strings.
- [ ] Security-sensitive failures still route to private reporting.

Validation:

```bash
uv run pytest tests/test_docs_site.py tests/test_helper_validations.py
uv run mkdocs build --strict
```

### WF-PQDX-005: Build A Docs Drift Checker For CLI And Public Commands

GitHub issue: [#183](https://github.com/AbdelStark/worldforge/issues/183)

Problem: CLI help snapshots, README snippets, MkDocs pages, and AGENTS guidance can drift as
commands evolve.

Scope:

- Add a checker that compares documented high-level commands with parser help and packaged entry
  points.
- Cover README, CLI reference, examples, operations, playbooks, and AGENTS command lists.
- Provide a clear failure report with stale or missing commands.

Out of scope:

- No generated rewrite of prose.
- No broad docs reformatting.

Acceptance criteria:

- [ ] Checker fails when a documented command no longer exists.
- [ ] Checker reports missing public command docs for new command families.
- [ ] CI or documented quality gates include the checker.
- [ ] Tests cover stale command and missing command cases.

Validation:

```bash
uv run pytest tests/test_cli_help_snapshots.py tests/test_docs_site.py
uv run mkdocs build --strict
```

### WF-PQDX-006: Add Performance Regression Budgets For Core Checkout Paths

GitHub issue: [#184](https://github.com/AbdelStark/worldforge/issues/184)

Problem: provider benchmarks exist, but core framework operations can slow down without a focused
checkout-safe performance gate.

Scope:

- Add reproducible budgets for world persistence, benchmark fixture loading, provider catalog
  diagnostics, evidence-bundle creation, and report rendering.
- Preserve results under run workspaces when requested.
- Document machine-context caveats and review rules before tightening budgets.

Out of scope:

- No public leaderboard or cross-machine performance claim.
- No hardware-specific runtime benchmark as a default gate.

Acceptance criteria:

- [ ] Core performance budgets run without credentials or optional runtimes.
- [ ] Failures include preserved JSON and first triage guidance.
- [ ] Budget calibration remains review-only.
- [ ] Docs distinguish regression detection from product performance claims.

Validation:

```bash
uv run pytest tests/test_benchmark.py tests/test_benchmark_budget_calibration.py tests/test_docs_site.py
uv run mkdocs build --strict
```

### WF-PQDX-007: Create A Contributor Bootstrap Doctor

GitHub issue: [#185](https://github.com/AbdelStark/worldforge/issues/185)

Problem: new contributors need a quick diagnosis of Python, uv, package extras, docs tooling,
GitHub CLI, and optional runtime boundaries before they start.

Scope:

- Add a contributor doctor command or script that checks local development prerequisites.
- Report Python version, uv availability, editable install readiness, docs dependencies, GitHub CLI
  auth status, and optional runtime skip reasons.
- Keep output value-free and safe to paste into public issues.

Out of scope:

- No installation of dependencies or secrets.
- No assumption that optional runtimes are present.

Acceptance criteria:

- [ ] Doctor output is JSON and Markdown capable.
- [ ] Missing optional runtimes are skips, not failures.
- [ ] Docs route contributor setup failures to the doctor.
- [ ] Tests cover missing tool, missing auth, and ready states through fixtures.

Validation:

```bash
uv run pytest tests/test_cli_doctor.py tests/test_docs_site.py
uv run mkdocs build --strict
```

### WF-PQDX-008: Document Supply-Chain And Artifact Integrity Gates

GitHub issue: [#186](https://github.com/AbdelStark/worldforge/issues/186)

Problem: package validation exists, but release readers need a clear integrity story for wheels,
sdists, evidence artifacts, hashes, and future attestations.

Scope:

- Document the current package contract and artifact digest surfaces.
- Define future SBOM, provenance, and attestation expectations without requiring credentials now.
- Link release evidence, package contract, dependency audit, and GitHub release gates.

Out of scope:

- No production signing service.
- No trusted publishing migration unless separately scoped.

Acceptance criteria:

- [ ] Docs explain what is verified today and what remains future work.
- [ ] Release checklist includes hashes, package install, dependency audit, and evidence links.
- [ ] Unsafe artifacts and local-only files remain excluded from public bundles.
- [ ] Tests guard the key documentation claims.

Validation:

```bash
uv run pytest tests/test_package_contract_script.py tests/test_docs_site.py
uv run mkdocs build --strict
```

### WF-PQDX-009: Tighten Cross-Platform Wrapper Validation

GitHub issue: [#187](https://github.com/AbdelStark/worldforge/issues/187)

Problem: shell wrappers and optional runtime commands are easiest to break on macOS, Linux, or
different Python environments.

Scope:

- Add tests or static checks for executable bits, shebangs, documented `uv run` invocations, and
  Python-version expectations.
- Cover scripts for robotics showcase, LeWorldModel, GR00T, LeRobot, and package validation.
- Document host-specific limitations and fallback commands.

Out of scope:

- No Windows support claim unless explicitly validated.
- No optional runtime installation in base CI.

Acceptance criteria:

- [ ] Script portability checks run in checkout-safe CI.
- [ ] Wrapper docs match actual commands and Python-version policy.
- [ ] Failures name the exact script and expected fix.
- [ ] Optional runtime commands remain host-owned.

Validation:

```bash
uv run pytest tests/test_leworldmodel_uv_tasks.py tests/test_robotics_showcase_ci.py tests/test_docs_site.py
uv run mkdocs build --strict
```

### WF-PQDX-010: Add A Documentation Information Architecture Review

GitHub issue: [#188](https://github.com/AbdelStark/worldforge/issues/188)

Problem: the docs have grown quickly; users need clearer routes for provider authors, operators,
research evaluators, and release maintainers.

Scope:

- Audit MkDocs navigation, README links, quickstart, examples, playbooks, provider docs, and
  roadmap pages.
- Propose and implement a tighter navigation structure without removing technical detail.
- Add docs tests that protect the intended reader paths.

Out of scope:

- No marketing rewrite.
- No deletion of roadmap history or evidence records.

Acceptance criteria:

- [ ] Primary docs paths exist for provider authors, operators, evaluator/research users, and
      release maintainers.
- [ ] Roadmap history is discoverable but not confused with active work.
- [ ] Navigation and SUMMARY stay synchronized.
- [ ] MkDocs strict build remains clean.

Validation:

```bash
uv run pytest tests/test_docs_site.py
uv run mkdocs build --strict
```

## Stream 2: Demos, End-to-End Showcases, And Use Cases

Goal: make the existing framework capabilities visible through serious, reproducible walkthroughs
that prove workflows end to end without overclaiming model fidelity.

### WF-DEMO-001: Build A First-Run Local World Workflow

GitHub issue: [#189](https://github.com/AbdelStark/worldforge/issues/189)

Problem: users can run many commands, but the first-run path from install to persisted world to
prediction to export needs a single polished walkthrough.

Scope:

- Add a checkout-safe first-run demo using the mock provider and local JSON persistence.
- Preserve command output, exported world JSON, history, and preflight result.
- Link the flow from README, quickstart, examples, and CLI docs.

Out of scope:

- No optional runtime or credential dependency.
- No physical-fidelity claim.

Acceptance criteria:

- [ ] One documented command or script runs the full first-run workflow.
- [ ] The demo verifies world creation, object mutation, prediction, export, and preflight.
- [ ] The output is deterministic enough for tests.
- [ ] Docs explain expected success signals and first triage step.

Validation:

```bash
uv run pytest tests/test_cli_world_commands.py tests/test_world_lifecycle.py tests/test_docs_site.py
uv run mkdocs build --strict
```

### WF-DEMO-002: Add A Provider Diagnostics To Issue Bundle Walkthrough

GitHub issue: [#190](https://github.com/AbdelStark/worldforge/issues/190)

Problem: the diagnostics, run workspace, and issue-bundle features are strong but not presented as
one operational story.

Scope:

- Add a demo that creates a failed or skipped provider diagnostic run, exports a safe issue bundle,
  and shows the exact artifact tree.
- Include both JSON and Markdown outputs.
- Document how to attach the result safely to a public issue.

Out of scope:

- No real provider credentials.
- No raw logs or local-only files in public artifacts.

Acceptance criteria:

- [ ] Demo creates a preserved run manifest and issue bundle.
- [ ] Bundle `safe_to_attach` behavior is asserted.
- [ ] Docs include command, expected files, and failure triage.
- [ ] Tests cover the demo path.

Validation:

```bash
uv run pytest tests/test_issue_bundle_export.py tests/test_harness_workspace.py tests/test_docs_site.py
uv run mkdocs build --strict
```

### WF-DEMO-003: Create A Guided Robotics Showcase Replay

GitHub issue: [#191](https://github.com/AbdelStark/worldforge/issues/191)

Problem: the robotics showcase has strong runtime pieces, but users need a guided replay artifact
that explains policy result, score result, candidate selection, and safety boundaries.

Scope:

- Add a checkout-safe replay mode using packaged deterministic artifacts.
- Render a step-by-step summary for selected action chunks, score rationale, mock execution, and
  Rerun artifact references.
- Keep the real PushT runtime path separate from replay.

Out of scope:

- No robot control.
- No downloading checkpoints in the replay path.

Acceptance criteria:

- [ ] Replay runs without LeRobot, LeWorldModel, torch, or simulation dependencies.
- [ ] Real-runtime commands remain documented as prepared-host paths.
- [ ] Replay artifacts are safe to attach.
- [ ] Tests cover replay manifest and docs.

Validation:

```bash
uv run pytest tests/test_robotics_showcase.py tests/test_rerun_integration.py tests/test_docs_site.py
uv run mkdocs build --strict
```

### WF-DEMO-004: Add A Remote Media Dry-Run Showcase

GitHub issue: [#192](https://github.com/AbdelStark/worldforge/issues/192)

Problem: Cosmos and Runway have remote-media adapter logic, but users need a safe dry-run showcase
for parser behavior, artifact retention, and signed-URL redaction.

Scope:

- Build a fixture-backed dry-run that exercises remote-media success and failure handling.
- Preserve sanitized run manifest, provider events, and artifact summaries.
- Document prepared-host live-smoke follow-up commands.

Out of scope:

- No paid API calls in checkout-safe mode.
- No storing generated media in the repo.

Acceptance criteria:

- [ ] Dry-run covers Cosmos and Runway fixture paths.
- [ ] Signed URLs and retention warnings are visible but redacted.
- [ ] Docs distinguish dry-run evidence from live-provider evidence.
- [ ] Tests cover the showcase artifacts.

Validation:

```bash
uv run pytest tests/test_remote_video_providers.py tests/test_cosmos_smoke_script.py tests/test_docs_site.py
uv run mkdocs build --strict
```

### WF-DEMO-005: Build An Adapter Author Journey Demo

GitHub issue: [#193](https://github.com/AbdelStark/worldforge/issues/193)

Problem: provider authors have scaffold and workbench tools, but not a single visible path from
idea to scaffold to evidence gaps.

Scope:

- Add a demo that scaffolds a fake provider into a temp directory, runs generated tests, runs the
  workbench, and reports promotion blockers.
- Preserve generated files only under temp or documented demo output.
- Link the journey from provider authoring docs.

Out of scope:

- No claim that the demo provider is real.
- No repository mutation outside temp/demo output.

Acceptance criteria:

- [ ] Demo proves scaffold, generated tests, docs stubs, runtime manifest stub, and workbench
      report.
- [ ] Output calls the provider scaffold explicitly incomplete.
- [ ] Tests assert no generated demo files land in tracked source.
- [ ] Docs explain how to adapt the path for real providers.

Validation:

```bash
uv run pytest tests/test_provider_scaffold_script.py tests/test_provider_workbench.py tests/test_docs_site.py
uv run mkdocs build --strict
```

### WF-DEMO-006: Create A Batch Evaluation Host Walkthrough

GitHub issue: [#194](https://github.com/AbdelStark/worldforge/issues/194)

Problem: the batch evaluation host exists, but users need a complete story from input fixture to
budget gate to preserved evidence.

Scope:

- Add a walkthrough that runs eval and benchmark jobs through the batch host.
- Preserve report JSON, Markdown, CSV, budget result, manifest, and rerun command.
- Include a controlled budget failure path.

Out of scope:

- No production scheduler or queue.
- No remote provider credentials.

Acceptance criteria:

- [ ] Walkthrough covers passing eval and failing budget gate.
- [ ] Preserved artifacts are listed and safe to attach.
- [ ] Docs show rerun and triage commands.
- [ ] Tests cover command output and manifest shape.

Validation:

```bash
uv run pytest tests/test_batch_eval_host.py tests/test_harness_workspace.py tests/test_docs_site.py
uv run mkdocs build --strict
```

### WF-DEMO-007: Expand The Stdlib Service Host Use Case

GitHub issue: [#195](https://github.com/AbdelStark/worldforge/issues/195)

Problem: the service host recipe is useful, but it should demonstrate readiness, provider
diagnostics, run-scoped logs, and a safe request lifecycle end to end.

Scope:

- Extend the stdlib host example with readiness, diagnostics, one mock request, provider events,
  and shutdown behavior.
- Add fixture tests for response shape and log redaction.
- Document deployment boundaries and rollback steps.

Out of scope:

- No hosted service platform.
- No authentication layer beyond host-owned guidance.

Acceptance criteria:

- [ ] Example starts, handles a request, emits sanitized events, and shuts down in tests.
- [ ] Readiness response identifies provider and capability state.
- [ ] Docs show expected success signal and first triage command.
- [ ] Host-owned responsibilities remain explicit.

Validation:

```bash
uv run pytest tests/test_service_host.py tests/test_run_logs.py tests/test_docs_site.py
uv run mkdocs build --strict
```

### WF-DEMO-008: Add A Rerun Visual Gallery Showcase

GitHub issue: [#196](https://github.com/AbdelStark/worldforge/issues/196)

Problem: Rerun support is powerful but scattered across demos and robotics flows; a curated gallery
would make visual evidence easier to inspect.

Scope:

- Add a checkout-safe visual gallery script that logs world snapshots, plans, benchmark summaries,
  and robotics replay layers.
- Write a local `.rrd` and JSON manifest.
- Document how to open the artifact and what each layer means.

Out of scope:

- No remote viewer requirement.
- No live robot or model runtime dependency.

Acceptance criteria:

- [ ] Gallery runs with the `rerun` extra and degrades clearly when missing.
- [ ] Manifest lists every visual layer and source artifact.
- [ ] Docs include open command and troubleshooting.
- [ ] Tests cover manifest generation without requiring a GUI.

Validation:

```bash
uv run pytest tests/test_rerun_integration.py tests/test_robotics_showcase.py tests/test_docs_site.py
uv run mkdocs build --strict
```

### WF-DEMO-009: Create A Failure Recovery Lab

GitHub issue: [#197](https://github.com/AbdelStark/worldforge/issues/197)

Problem: operator drills and preflight checks exist, but users need an intentional lab that teaches
failure recovery without touching real user state.

Scope:

- Add a scripted lab that runs selected drills, local state preflight, run bundle export, and
  recovery preview commands under a temp workspace.
- Include corrupted world state, unsafe artifact path, and missing credential scenarios.
- Preserve a lab report artifact.

Out of scope:

- No mutation of real `.worldforge` state.
- No real credentials or optional runtime installs.

Acceptance criteria:

- [ ] Lab runs checkout-safe under a temp workspace.
- [ ] Report lists expected failures, observed signals, and recovery commands.
- [ ] Unsafe artifacts remain excluded or redacted.
- [ ] Docs route operators to the lab before incidents.

Validation:

```bash
uv run pytest tests/test_operator_drills.py tests/test_persistence_preflight.py tests/test_docs_site.py
uv run mkdocs build --strict
```

### WF-DEMO-010: Publish A Use Case Cookbook

GitHub issue: [#198](https://github.com/AbdelStark/worldforge/issues/198)

Problem: users need task-oriented entry points that map use cases to commands, providers,
artifacts, and boundaries.

Scope:

- Add a cookbook page covering local world experiments, provider authoring, evaluation evidence,
  benchmark budgets, remote media dry-runs, robotics replay, and release evidence.
- Each recipe should include command, expected output, artifact, first triage step, and non-claims.
- Link recipes from README and examples docs.

Out of scope:

- No new runtime integration.
- No decorative landing page.

Acceptance criteria:

- [ ] Cookbook contains at least seven task-oriented recipes.
- [ ] Every recipe names host-owned responsibilities and evidence artifacts.
- [ ] README and examples docs point to the cookbook.
- [ ] Docs tests guard the recipe list.

Validation:

```bash
uv run pytest tests/test_docs_site.py tests/test_examples_index.py
uv run mkdocs build --strict
```

## Stream 3: New Features

Goal: add capabilities that make WorldForge more useful as a Python integration layer while keeping
provider runtimes optional, typed, and testable.

### WF-FEAT-001: Add Provider Package Discovery Through Entry Points

GitHub issue: [#199](https://github.com/AbdelStark/worldforge/issues/199)

Problem: external adapter packages need a clean way to register providers without modifying the
WorldForge repository.

Scope:

- Design and implement Python entry-point discovery for provider factories.
- Keep auto-registration opt-in and safe around missing optional dependencies.
- Document package metadata, factory contracts, and failure behavior.

Out of scope:

- No marketplace or plugin registry service.
- No loading providers that fail dependency or credential checks silently.

Acceptance criteria:

- [ ] External packages can expose provider factories through documented entry points.
- [ ] Discovery reports skipped providers with explicit reasons.
- [ ] Existing in-repo catalog behavior remains unchanged.
- [ ] Tests cover valid entry point, missing dependency, duplicate name, and disabled discovery.

Validation:

```bash
uv run pytest tests/test_provider_catalog.py tests/test_provider_config.py tests/test_docs_site.py
uv run mkdocs build --strict
```

### WF-FEAT-002: Add A Scenario Definition Format For Worlds And Runs

GitHub issue: [#200](https://github.com/AbdelStark/worldforge/issues/200)

Problem: repeated world setup and evaluation scenarios are still scattered across examples,
fixtures, and ad hoc Python code.

Scope:

- Define a JSON-native scenario format for world objects, actions, goals, provider selection, and
  expected artifacts.
- Add loader validation and CLI execution for checkout-safe scenarios.
- Include sample scenarios for local mock worlds and evaluation runs.

Out of scope:

- No arbitrary Python execution from scenario files.
- No simulator-specific schema.

Acceptance criteria:

- [ ] Scenario files are schema-versioned and JSON-native.
- [ ] CLI can validate and run a checkout-safe scenario.
- [ ] Invalid scenario failures are explicit and tested.
- [ ] Docs show how scenarios differ from provider fixtures.

Validation:

```bash
uv run pytest tests/test_world_lifecycle.py tests/test_cli_world_commands.py tests/test_docs_site.py
uv run mkdocs build --strict
```

### WF-FEAT-003: Add An Evaluation Suite Authoring API

GitHub issue: [#201](https://github.com/AbdelStark/worldforge/issues/201)

Problem: built-in suites exist, but external users need a supported way to author, register, and
report custom deterministic evaluation suites.

Scope:

- Add a public authoring API for scenarios, metrics, failure cases, and report artifacts.
- Document suite versioning, provenance, and claim boundaries.
- Provide a small custom suite example.

Out of scope:

- No leaderboard service.
- No non-deterministic scoring as a default path.

Acceptance criteria:

- [ ] Users can define and run a custom suite without touching internal modules.
- [ ] Custom reports include provenance and failure galleries where applicable.
- [ ] Tests cover custom suite success and invalid metric payloads.
- [ ] Docs explain suite authoring and non-claims.

Validation:

```bash
uv run pytest tests/test_evaluation_suites.py tests/test_evaluation_failure_gallery.py tests/test_docs_site.py
uv run mkdocs build --strict
```

### WF-FEAT-004: Add A Local Run Artifact Index

GitHub issue: [#202](https://github.com/AbdelStark/worldforge/issues/202)

Problem: preserved run workspaces accumulate useful evidence, but users cannot search or summarize
them beyond listing manifests.

Scope:

- Add an indexer for `.worldforge/runs` that summarizes providers, capabilities, statuses, safe
  artifact types, dates, and failure reasons.
- Provide JSON, Markdown, and CSV outputs.
- Keep indexing read-only and safe for corrupted or stale run directories.

Out of scope:

- No database, daemon, or multi-writer store.
- No indexing raw unsafe artifacts.

Acceptance criteria:

- [ ] Index command handles valid, stale, and malformed run workspaces.
- [ ] Output is safe to attach by default.
- [ ] Filters work for provider, capability, status, date, and artifact type.
- [ ] Docs explain retention and cleanup interaction.

Validation:

```bash
uv run pytest tests/test_harness_workspace.py tests/test_harness_cli.py tests/test_docs_site.py
uv run mkdocs build --strict
```

### WF-FEAT-005: Add Provider Routing And Fallback Policies

GitHub issue: [#203](https://github.com/AbdelStark/worldforge/issues/203)

Problem: users often need to try one provider and fall back to another, but ad hoc fallback logic
can hide capability mismatches or provider failures.

Scope:

- Add typed routing policy models for preferred provider, fallback providers, capability
  requirements, and failure handling.
- Preserve provider errors and event provenance across attempts.
- Support checkout-safe mock examples and docs.

Out of scope:

- No load balancer, SLA promise, or remote orchestration.
- No fallback that masks malformed provider output.

Acceptance criteria:

- [ ] Routing validates capability compatibility before calls.
- [ ] Failed attempts emit sanitized events and remain visible in results.
- [ ] Policy behavior is deterministic under tests.
- [ ] Docs explain when fallback is appropriate and when it is not.

Validation:

```bash
uv run pytest tests/test_providers.py tests/test_provider_events.py tests/test_docs_site.py
uv run mkdocs build --strict
```

### WF-FEAT-006: Add Action Candidate Generation Helpers

GitHub issue: [#204](https://github.com/AbdelStark/worldforge/issues/204)

Problem: policy-plus-score planning requires action candidates, but hosts currently have to build
candidate sets from scratch.

Scope:

- Add typed helper functions for common candidate patterns such as Cartesian offsets, object-near
  goals, swap actions, and bounded move grids.
- Keep helpers provider-agnostic and JSON-native.
- Document how helpers feed `score` and `policy+score` workflows.

Out of scope:

- No task-specific image preprocessing.
- No reinterpretation of robot action spaces.

Acceptance criteria:

- [ ] Candidate helpers return validated `Action` sequences.
- [ ] Invalid bounds and non-finite inputs fail explicitly.
- [ ] Planning examples use helpers without changing provider capability claims.
- [ ] Tests cover helper output and score-planning integration.

Validation:

```bash
uv run pytest tests/test_evaluation_and_planning.py tests/test_leworldmodel_provider.py tests/test_docs_site.py
uv run mkdocs build --strict
```

### WF-FEAT-007: Add A Fixture Snapshot Manager

GitHub issue: [#205](https://github.com/AbdelStark/worldforge/issues/205)

Problem: provider fixtures, benchmark inputs, and scenario artifacts need consistent digesting,
metadata, and drift checks.

Scope:

- Add a manager for fixture manifests, SHA-256 digests, schema versions, and update review output.
- Cover capability fixtures, provider payload fixtures, benchmark inputs, and future scenarios.
- Keep updates explicit and reviewable.

Out of scope:

- No large dataset storage.
- No automatic fixture refresh from remote providers.

Acceptance criteria:

- [ ] Fixture manifest validation fails on missing, changed, or unsafe fixture references.
- [ ] Review output distinguishes intended updates from drift.
- [ ] Docs explain when to update fixtures.
- [ ] Tests cover manifest load, digest mismatch, and unsafe path cases.

Validation:

```bash
uv run pytest tests/test_capability_fixtures.py tests/test_provider_runtime_manifests.py tests/test_docs_site.py
uv run mkdocs build --strict
```

### WF-FEAT-008: Add World State Diff And Patch Artifacts

GitHub issue: [#206](https://github.com/AbdelStark/worldforge/issues/206)

Problem: world histories and predictions store snapshots, but users need a compact artifact that
explains what changed between two world states.

Scope:

- Add JSON-native diff and patch artifacts for scene objects, metadata, step, history summary, and
  bounding boxes.
- Expose CLI and Python helpers for comparing persisted worlds or exported JSON.
- Include safe rendering for docs and issue bundles.

Out of scope:

- No concurrent merge system.
- No silent patch application over invalid state.

Acceptance criteria:

- [ ] Diff output is schema-versioned and JSON-native.
- [ ] Patch validation rejects traversal-shaped IDs, invalid objects, and incoherent bounding boxes.
- [ ] CLI compares two persisted or exported worlds.
- [ ] Tests cover add, update, remove, invalid patch, and docs examples.

Validation:

```bash
uv run pytest tests/test_world_lifecycle.py tests/test_cli_world_commands.py tests/test_docs_site.py
uv run mkdocs build --strict
```

### WF-FEAT-009: Add Static HTML Report Export For Runs

GitHub issue: [#207](https://github.com/AbdelStark/worldforge/issues/207)

Problem: JSON and Markdown run artifacts are useful, but sharing local evidence with non-developers
often needs a single static HTML report.

Scope:

- Add static HTML export for eval, benchmark, comparison, and issue-bundle summaries.
- Keep HTML self-contained, sanitized, and generated from existing safe artifacts.
- Document when to use HTML versus JSON/Markdown.

Out of scope:

- No hosted dashboard.
- No JavaScript-heavy application.

Acceptance criteria:

- [ ] HTML export works for preserved eval and benchmark runs.
- [ ] Unsafe artifacts are excluded or marked local-only.
- [ ] Tests check escaping, safe links, and report metadata.
- [ ] Docs include open-file workflow and limitations.

Validation:

```bash
uv run pytest tests/test_harness_report_compare.py tests/test_evidence_bundle.py tests/test_docs_site.py
uv run mkdocs build --strict
```

### WF-FEAT-010: Add Provider Capability Negotiation Reports

GitHub issue: [#208](https://github.com/AbdelStark/worldforge/issues/208)

Problem: users can inspect provider capabilities, but there is no report that explains whether a
set of providers can satisfy a workflow before the workflow runs.

Scope:

- Add a negotiation report for workflows requiring capability sets such as generate-only,
  score-only, policy-plus-score, transfer, or eval/benchmark presets.
- Include provider readiness, missing config, missing optional runtime, unsupported capability, and
  recommended next command.
- Expose report through CLI and Python.

Out of scope:

- No automatic installation or credential setup.
- No fallback execution by default.

Acceptance criteria:

- [ ] Report distinguishes registered, configured, dependency-ready, and capability-compatible.
- [ ] Policy-plus-score workflows name both policy and score providers.
- [ ] Output is JSON and Markdown capable.
- [ ] Tests cover ready, missing config, missing dependency, and unsupported capability cases.

Validation:

```bash
uv run pytest tests/test_cli_doctor.py tests/test_provider_profiles.py tests/test_runtime_profiles.py tests/test_docs_site.py
uv run mkdocs build --strict
```

## Issue Creation Notes

- Nano World Model remains excluded from this roadmap because that issue is already assigned.
- Stream labels:
  - `stream: production-quality`
  - `stream: demos-showcases`
  - `stream: new-features`
- Issue bodies should preserve the problem, scope, out-of-scope, acceptance, validation, and source
  pointers from this document.

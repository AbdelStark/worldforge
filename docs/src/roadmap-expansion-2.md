# Roadmap Expansion 2

This is the second expansion batch after the completed provider/platform tracks, the continuation
plan, and the first 30-issue roadmap expansion. It is intentionally additive: it does not reopen
completed production-quality or showcase work, and it does not duplicate the remaining open
feature items from the first expansion.

The plan stays split into the same three major streams, with ten implementation issues each:

- Production Grade, Quality, DevX, And Docs
- Demos, End-to-End Showcases, And Use Cases
- New Features

Each issue is meant to be independently actionable, but several demo issues deliberately depend on
existing feature work so the demo layer follows real product surfaces instead of inventing parallel
paths. The shared constraints remain unchanged: optional runtimes stay host-owned, provider
capabilities stay truthful, deterministic tests are contract signals rather than physical-fidelity
claims, and public artifacts must be safe to attach unless clearly marked local-only.

## Stream 1: Production Grade, Quality, DevX, And Docs

Goal: make the project harder to misuse and easier to maintain as the public surface grows beyond
single-command demos into external provider packages, scenario files, report artifacts, and release
evidence.

### WF-PQDX2-001: Establish Artifact Schema Ownership And Migration Rules

GitHub issue: [#227](https://github.com/AbdelStark/worldforge/issues/227)

Labels: `documentation`, `roadmap`, `quality`, `artifacts`, `developer-experience`, `stream: production-quality`

Problem: WorldForge now has several JSON-native artifact families, including run manifests,
issue bundles, scenarios, world diffs, HTML report metadata, benchmark inputs, and evidence
summaries. Contributors need one ownership map that says which schemas are public, who owns them,
how versions advance, and when migration or compatibility tests are required.

Scope:

- Inventory every public or semi-public artifact schema and link it to the owning module, docs
  page, tests, and CLI entry point.
- Define schema-version bump rules for additive changes, breaking changes, renderer-only changes,
  and private implementation metadata.
- Add a docs or test guard that fails when a new public artifact family is added without ownership
  and migration notes.
- Document examples of acceptable compatibility shims and explicit no-migration decisions.

Out of scope:

- No global schema registry service.
- No compatibility promise for private temp files, cache internals, or local-only unsafe artifacts.

Acceptance criteria:

- [x] Docs list every public artifact schema, owner, version field, and validation surface.
- [x] Contributors can tell when a schema change needs migration notes, changelog text, and tests.
- [x] At least one automated guard catches missing schema ownership for public artifacts.
- [x] Existing artifacts remain JSON-native and safe-artifact boundaries stay explicit.

Validation:

```bash
uv run pytest tests/test_docs_site.py tests/test_public_api.py
uv run mkdocs build --strict
```

### WF-PQDX2-002: Add A Documentation Snippet Execution Gate

GitHub issue: [#228](https://github.com/AbdelStark/worldforge/issues/228)

Labels: `documentation`, `roadmap`, `quality`, `testing`, `developer-experience`, `ci`, `stream: production-quality`

Problem: command drift is now checked, but Python snippets and small JSON examples can still rot
silently in docs, especially around scenarios, provider routing, external providers, and report
rendering.

Scope:

- Add a checkout-safe snippet gate for selected Python and JSON blocks in docs.
- Start with high-value pages: Python API, scenarios, provider routing, external providers,
  benchmarking, evidence bundles, and world diffs.
- Require explicit skip markers for snippets that need credentials, optional runtimes, or prepared
  host assets.
- Report file, heading, language, and failure reason when a snippet breaks.

Out of scope:

- No execution of shell snippets that can mutate user state.
- No optional runtime installation or credential use.

Acceptance criteria:

- [x] Selected Python snippets execute in a temp workspace.
- [x] Selected JSON snippets parse and satisfy the expected schema where a schema exists.
- [x] Skip markers distinguish host-owned, credentialed, and illustrative snippets.
- [x] Docs explain how contributors add new snippets to the gate.

Validation:

```bash
uv run pytest tests/test_docs_site.py tests/test_snippet_gate.py
uv run mkdocs build --strict
```

### WF-PQDX2-003: Build An Optional Dependency Import Boundary Audit

GitHub issue: [#229](https://github.com/AbdelStark/worldforge/issues/229)

Labels: `documentation`, `roadmap`, `quality`, `optional-dependency`, `testing`, `ci`, `stream: production-quality`

Problem: optional runtimes are a core boundary, but new modules can accidentally import Textual,
Rerun, torch, LeRobot, stable-worldmodel, GR00T, or Cosmos-Policy dependencies from base package
paths.

Scope:

- Add a static and import-time audit for base-package modules, CLI startup, and non-TUI harness
  modules.
- Cover known optional boundaries for `harness`, `rerun`, `leworldmodel`, `lerobot`, `gr00t`, and
  `cosmos-policy`.
- Document the allowed import locations and the lazy-import pattern for optional integrations.
- Wire the audit into release-readiness or quality gates.

Out of scope:

- No removal of supported extras.
- No fake stubs that hide missing optional dependencies.

Acceptance criteria:

- [x] Base imports succeed without optional runtime packages installed.
- [x] The audit fails with a precise module path when an optional dependency leaks into base code.
- [x] Docs identify the only modules allowed to import each optional runtime directly.
- [x] Existing optional smoke commands keep their host-owned dependency behavior.

Validation:

```bash
uv run pytest tests/test_import_boundaries.py tests/test_public_api.py tests/test_docs_site.py
uv run mkdocs build --strict
```

### WF-PQDX2-004: Add Deterministic Test Data And Time Controls

GitHub issue: [#230](https://github.com/AbdelStark/worldforge/issues/230)

Labels: `documentation`, `roadmap`, `quality`, `testing`, `reliability`, `stream: production-quality`

Problem: reports, manifests, benchmark summaries, and release evidence often include timestamps,
durations, IDs, ordering, and temporary paths. Without deterministic controls, regression tests
become either brittle or too loose to catch real drift.

Scope:

- Add shared fixtures or helper APIs for stable clocks, temporary workspaces, deterministic IDs,
  and sorted artifact output.
- Apply them to run manifests, issue bundles, benchmark reports, scenario runs, and release
  evidence tests.
- Document when exact snapshot testing is appropriate and when semantic assertions are stronger.

Out of scope:

- No attempt to make real provider latency deterministic.
- No global monkeypatching that affects host-owned optional runtimes.

Acceptance criteria:

- [ ] Tests for artifact renderers avoid local path, clock, and ordering flake.
- [ ] Helpers are reusable by future report and demo tests.
- [ ] Docs explain deterministic fixture policy for contributors.
- [ ] Existing runtime timing fields remain truthful in real runs.

Validation:

```bash
uv run pytest tests/test_harness_workspace.py tests/test_evidence_bundle.py tests/test_release_evidence.py tests/test_docs_site.py
uv run mkdocs build --strict
```

### WF-PQDX2-005: Create A Provider Configuration Contract Index

GitHub issue: [#231](https://github.com/AbdelStark/worldforge/issues/231)

Labels: `documentation`, `roadmap`, `provider`, `quality`, `developer-experience`, `operations`, `stream: production-quality`

Problem: provider configuration requirements are spread across generated provider docs, `.env`
examples, runtime profiles, smoke scripts, and playbooks. Operators need one index that is
generated or checked against the actual provider metadata.

Scope:

- Add a provider configuration index covering environment variables, optional packages, credential
  gates, prepared-host assets, default timeouts, and first diagnostic commands.
- Check the index against provider profiles, generated docs, `.env.example`, and smoke command
  docs.
- Distinguish scaffold, fixture-tested, prepared-host, and live-smoke evidence levels.

Out of scope:

- No storage of secrets or host-local endpoint values.
- No real provider validation beyond existing diagnostics and smoke boundaries.

Acceptance criteria:

- [ ] Each catalog provider has a configuration row with required and optional inputs.
- [ ] The index flags provider docs or `.env.example` drift.
- [ ] Scaffold providers remain clearly marked as scaffold behavior.
- [ ] Docs link the index from provider authoring, operations, and support pages.

Validation:

```bash
uv run pytest tests/test_provider_docs.py tests/test_provider_profiles.py tests/test_docs_site.py
uv run python scripts/generate_provider_docs.py --check
uv run mkdocs build --strict
```

### WF-PQDX2-006: Add User-Facing Error Message Regression Coverage

GitHub issue: [#232](https://github.com/AbdelStark/worldforge/issues/232)

Labels: `documentation`, `roadmap`, `quality`, `testing`, `developer-experience`, `reliability`, `stream: production-quality`

Problem: WorldForge raises explicit error families, but CLI and provider messages can still become
unclear, lose triage commands, or leak internal implementation details as code evolves.

Scope:

- Add a regression corpus for public CLI and Python error messages across malformed world state,
  invalid scenarios, unsupported capabilities, missing provider config, unsafe artifacts, and
  budget failures.
- Require messages to include owner context, first triage step, and safe wording where applicable.
- Keep exact snapshots only for stable user-facing text; use semantic assertions where values are
  intentionally variable.

Out of scope:

- No broad rewrite of exception hierarchy.
- No suppression of stack traces in developer/debug paths where they are explicitly requested.

Acceptance criteria:

- [ ] Error messages for the main public failure modes have regression coverage.
- [ ] Security-sensitive failures do not print secrets, signed URLs, or host-local unsafe payloads.
- [ ] CLI failures point to concrete commands or docs when a recovery path exists.
- [ ] Tests distinguish public message contracts from private implementation details.

Validation:

```bash
uv run pytest tests/test_cli_world_commands.py tests/test_scenarios.py tests/test_helper_validations.py tests/test_docs_site.py
uv run mkdocs build --strict
```

### WF-PQDX2-007: Build Contributor Task Starter Packs

GitHub issue: [#233](https://github.com/AbdelStark/worldforge/issues/233)

Labels: `documentation`, `roadmap`, `developer-experience`, `quality`, `testing`, `stream: production-quality`

Problem: issue bodies are detailed, but contributors still need to translate each roadmap slice
into files to inspect, commands to run, docs surfaces to update, and acceptance evidence to attach.

Scope:

- Add task starter templates for provider work, docs-only work, demo workflows, artifact/report
  work, evaluation work, and CLI changes.
- Each starter should list likely files, forbidden shortcuts, validation commands, evidence
  artifacts, and review checklist.
- Link starters from contributing docs and issue templates.

Out of scope:

- No automatic branch creation, assignment, or GitHub Project automation.
- No replacement for maintainers reading the actual code before editing.

Acceptance criteria:

- [ ] At least six starter packs exist and match current repository structure.
- [ ] Starter packs include validation commands and docs/changelog expectations.
- [ ] Issue templates or contributing docs point contributors to the right starter.
- [ ] Tests guard the presence of required sections.

Validation:

```bash
uv run pytest tests/test_docs_site.py
uv run mkdocs build --strict
```

### WF-PQDX2-008: Add Release Notes Assembly From Evidence And Issues

GitHub issue: [#234](https://github.com/AbdelStark/worldforge/issues/234)

Labels: `documentation`, `roadmap`, `release`, `developer-experience`, `artifacts`, `stream: production-quality`

Problem: release readiness can prove gates, but maintainers still have to assemble human release
notes from changelog entries, issue closures, public API changes, and evidence artifacts by hand.

Scope:

- Add a release-notes draft command that collects changed public surfaces, closed issues by label,
  validation summaries, docs links, and known caveats.
- Keep the output as a draft Markdown artifact for maintainer editing.
- Include sections for added, changed, fixed, docs, validation, compatibility notes, and
  host-owned optional runtime evidence.

Out of scope:

- No automatic GitHub release publishing.
- No tag signing or trusted-publishing workflow changes.

Acceptance criteria:

- [ ] Command produces a Markdown draft from local changelog and optional GitHub issue data.
- [ ] Draft includes validation evidence references and caveats without overclaiming runtime
      behavior.
- [ ] Missing changelog or missing validation evidence is reported clearly.
- [ ] Docs explain how maintainers review and edit the draft before release.

Validation:

```bash
uv run pytest tests/test_release_notes.py tests/test_release_evidence.py tests/test_docs_site.py
uv run mkdocs build --strict
```

### WF-PQDX2-009: Add Dependency Audit Evidence Artifacts

GitHub issue: [#235](https://github.com/AbdelStark/worldforge/issues/235)

Labels: `documentation`, `roadmap`, `quality`, `security`, `release`, `artifacts`, `stream: production-quality`

Problem: local security audit commands are documented, but their results are not preserved in a
consistent evidence format that release review can cite.

Scope:

- Add a dependency-audit evidence wrapper around the documented `uv export` plus `pip-audit`
  flow.
- Preserve command, dependency set, tool versions, status, vulnerability summary, ignored advisory
  rationale, and first triage step.
- Keep generated requirements files temporary and avoid committing environment-specific output.

Out of scope:

- No automated vulnerability suppression policy.
- No remote dependency scanning service.

Acceptance criteria:

- [ ] Audit evidence writes JSON and Markdown summaries.
- [ ] Vulnerability findings are preserved without leaking host-local paths or credentials.
- [ ] Release-readiness docs and package validation docs link the audit artifact.
- [ ] Tests cover clean, finding, and tool-unavailable paths through fixtures.

Validation:

```bash
uv run pytest tests/test_dependency_audit_evidence.py tests/test_docs_site.py
uv run mkdocs build --strict
```

### WF-PQDX2-010: Publish A Quality Dashboard Artifact

GitHub issue: [#236](https://github.com/AbdelStark/worldforge/issues/236)

Labels: `documentation`, `roadmap`, `quality`, `ci`, `artifacts`, `developer-experience`, `stream: production-quality`

Problem: individual quality gates exist, but maintainers need a single local artifact that shows
docs, tests, coverage, command drift, provider docs, snippets, package checks, audit status, and
known optional skips at a glance.

Scope:

- Add a quality dashboard generator that reads existing gate outputs and emits JSON plus Markdown.
- Include statuses, command lines, timestamps, skipped host-owned checks, and first failed gate.
- Link dashboard output from release readiness, contributing docs, and operations docs.

Out of scope:

- No hosted dashboard or badge service.
- No weakening of existing individual gates.

Acceptance criteria:

- [ ] Dashboard aggregates existing gate outputs without hiding raw failure details.
- [ ] Output distinguishes failures, warnings, skips, and not-run checks.
- [ ] Docs explain how the dashboard differs from release evidence.
- [ ] Tests cover mixed pass/fail/skip aggregation.

Validation:

```bash
uv run pytest tests/test_quality_dashboard.py tests/test_release_evidence.py tests/test_docs_site.py
uv run mkdocs build --strict
```

## Stream 2: Demos, End-to-End Showcases, And Use Cases

Goal: turn the next layer of capabilities into serious, reproducible workflows. These demos should
prove actual repository surfaces end to end, while clearly marking dependencies on remaining
feature work.

### WF-DEMO2-001: Build An External Provider Package Demo

GitHub issue: [#237](https://github.com/AbdelStark/worldforge/issues/237)

Labels: `documentation`, `roadmap`, `examples`, `provider`, `developer-experience`, `optional-dependency`, `stream: demos-showcases`

Depends on: [WF-FEAT-001 #199](https://github.com/AbdelStark/worldforge/issues/199)

Problem: entry-point discovery makes external provider packages possible, but users need a
checkout-safe demo that shows the package shape, metadata, registration behavior, skip reasons,
and docs/testing loop without publishing a real adapter.

Scope:

- Add a demo external provider package under examples or generated temp output.
- Show provider discovery enabled, discovery disabled, duplicate-provider handling, and missing
  optional dependency reporting.
- Preserve a demo report that is safe to paste into an issue.

Out of scope:

- No real PyPI publishing.
- No real remote provider or credentialed call.

Acceptance criteria:

- [ ] Demo proves external package discovery through documented entry points.
- [ ] Missing optional dependencies show explicit skip reasons.
- [ ] Generated or example package files do not mutate tracked source during normal demo runs.
- [ ] Docs link the demo from external provider and provider authoring pages.

Validation:

```bash
uv run pytest tests/test_provider_entry_points.py tests/test_provider_scaffold_script.py tests/test_docs_site.py
uv run mkdocs build --strict
```

### WF-DEMO2-002: Create A Custom Evaluation Suite Walkthrough

GitHub issue: [#238](https://github.com/AbdelStark/worldforge/issues/238)

Labels: `documentation`, `roadmap`, `examples`, `evaluation`, `developer-experience`, `artifacts`, `stream: demos-showcases`

Depends on: [WF-FEAT-003 #201](https://github.com/AbdelStark/worldforge/issues/201)

Problem: built-in evaluation suites are documented, but external users need a complete path for a
small custom suite with deterministic metrics, failure gallery, provenance, and report artifacts.

Scope:

- Add a walkthrough that defines a custom suite, runs it against the mock provider, renders
  JSON/Markdown/HTML reports, and preserves failure artifacts.
- Include invalid metric and failed-case examples so users see the boundaries.
- Explain how custom suite claims should be framed.

Out of scope:

- No leaderboard or quality ranking.
- No nondeterministic model scoring as a default example.

Acceptance criteria:

- [ ] Walkthrough runs in a clean checkout without credentials or optional runtimes.
- [ ] Custom suite output includes provenance and failure-gallery behavior.
- [ ] Docs explain deterministic contract-signal framing.
- [ ] Tests cover the walkthrough artifact set.

Validation:

```bash
uv run pytest tests/test_evaluation_suites.py tests/test_evaluation_failure_gallery.py tests/test_docs_site.py
uv run mkdocs build --strict
```

### WF-DEMO2-003: Add A Policy+Score Candidate Lab

GitHub issue: [#239](https://github.com/AbdelStark/worldforge/issues/239)

Labels: `documentation`, `roadmap`, `examples`, `score`, `policy`, `robotics`, `stream: demos-showcases`

Depends on: [WF-FEAT-006 #204](https://github.com/AbdelStark/worldforge/issues/204)

Problem: policy+score planning is central to the robotics story, but users need a controlled lab
that shows candidate generation, candidate scoring, selected action, raw policy action preservation,
and host-owned action translation boundaries.

Scope:

- Add a checkout-safe lab using deterministic candidate helpers and mock/injected policy and score
  surfaces.
- Preserve candidate tables, score metadata, selected action, and Rerun or HTML artifacts where
  available.
- Link the lab from LeRobot, GR00T, LeWorldModel, planning, and robotics docs.

Out of scope:

- No robot controller, simulator, checkpoint download, or action-space reinterpretation.
- No claim that deterministic scoring proves physical performance.

Acceptance criteria:

- [ ] Lab demonstrates candidate generation through score and policy+score planning.
- [ ] Invalid candidate bounds and translator-missing cases are visible and tested.
- [ ] Docs explain how prepared-host robotics runs differ from the lab.
- [ ] Output artifacts are safe to attach.

Validation:

```bash
uv run pytest tests/test_evaluation_and_planning.py tests/test_leworldmodel_provider.py tests/test_lerobot_provider.py tests/test_docs_site.py
uv run mkdocs build --strict
```

### WF-DEMO2-004: Add A Fixture Drift Review Walkthrough

GitHub issue: [#240](https://github.com/AbdelStark/worldforge/issues/240)

Labels: `documentation`, `roadmap`, `examples`, `testing`, `artifacts`, `developer-experience`, `stream: demos-showcases`

Depends on: [WF-FEAT-007 #205](https://github.com/AbdelStark/worldforge/issues/205)

Problem: fixture manifests and digests are useful only if contributors understand how to review
intentional changes versus accidental drift.

Scope:

- Add a walkthrough that introduces a controlled fixture change, runs the snapshot manager, shows
  review output, and demonstrates the approved update path.
- Cover provider payload fixtures, benchmark inputs, scenario fixtures, and unsafe path rejection.
- Keep all mutations under temp/demo output unless the user explicitly runs an update command.

Out of scope:

- No remote fixture refresh.
- No large dataset storage.

Acceptance criteria:

- [ ] Walkthrough distinguishes missing fixture, digest mismatch, schema change, and unsafe path.
- [ ] Approved update path is explicit and reviewable.
- [ ] Docs link from testing and provider authoring pages.
- [ ] Tests cover the demo without changing tracked fixtures.

Validation:

```bash
uv run pytest tests/test_capability_fixtures.py tests/test_provider_runtime_manifests.py tests/test_docs_site.py
uv run mkdocs build --strict
```

### WF-DEMO2-005: Create A Capability Negotiation Preflight Demo

GitHub issue: [#241](https://github.com/AbdelStark/worldforge/issues/241)

Labels: `documentation`, `roadmap`, `examples`, `provider`, `operations`, `stream: demos-showcases`

Depends on: [WF-FEAT-010 #208](https://github.com/AbdelStark/worldforge/issues/208)

Problem: negotiation reports are most valuable when users can see how they prevent bad workflow
starts before credentials, dependencies, or provider capabilities are ready.

Scope:

- Add a demo that runs negotiation for generate-only, transfer-only, score-only, policy+score, and
  evaluation workflows.
- Include ready, missing config, missing dependency, unsupported capability, and not-registered
  examples.
- Preserve JSON and Markdown reports and first recommended commands.

Out of scope:

- No automatic installation or credential setup.
- No fallback execution by default.

Acceptance criteria:

- [ ] Demo runs checkout-safe and covers at least five workflow shapes.
- [ ] Reports name the exact provider/capability slot that blocks a workflow.
- [ ] Docs route users to negotiation before prepared-host smokes.
- [ ] Tests cover the demo report fixtures.

Validation:

```bash
uv run pytest tests/test_capability_negotiation.py tests/test_cli_doctor.py tests/test_docs_site.py
uv run mkdocs build --strict
```

### WF-DEMO2-006: Add A Cross-Provider Embodied Policy Replay Comparison

GitHub issue: [#242](https://github.com/AbdelStark/worldforge/issues/242)

Labels: `documentation`, `roadmap`, `examples`, `policy`, `robotics`, `harness`, `stream: demos-showcases`

Depends on: [GR00T replay tracking #226](https://github.com/AbdelStark/worldforge/issues/226)

Problem: LeRobot, GR00T, and Cosmos-Policy all expose policy-style action chunks, but users need a
side-by-side replay that compares contract shape, readiness, raw action preservation, and
translator requirements without pretending the providers are interchangeable.

Scope:

- Add a fixture-backed comparison replay across LeRobot, GR00T, and Cosmos-Policy policy outputs.
- Show common policy contract fields and provider-specific raw action metadata.
- Include TheWorldHarness or static report output that makes missing translator and prepared-host
  requirements visible.

Out of scope:

- No cross-provider action-space conversion.
- No robot execution or controller safety claim.

Acceptance criteria:

- [ ] Replay compares provider policy contracts without normalizing away provider-specific fields.
- [ ] Missing translator behavior is explicit and tested.
- [ ] Docs explain prepared-host live-smoke follow-ups for each provider.
- [ ] The comparison artifact is safe to attach.

Validation:

```bash
uv run pytest tests/test_lerobot_provider.py tests/test_gr00t_provider.py tests/test_cosmos_policy_provider.py tests/test_docs_site.py
uv run mkdocs build --strict
```

### WF-DEMO2-007: Publish A Scenario Gallery For Local Worlds And Runs

GitHub issue: [#243](https://github.com/AbdelStark/worldforge/issues/243)

Labels: `documentation`, `roadmap`, `examples`, `persistence`, `evaluation`, `predict`, `stream: demos-showcases`

Depends on: [WF-FEAT-002 #200](https://github.com/AbdelStark/worldforge/issues/200)

Problem: scenario files are more useful when users can start from a small gallery that covers
world setup, predictions, expected artifacts, evaluation runs, and failure cases.

Scope:

- Add a scenario gallery with at least five checkout-safe scenarios.
- Include successful world setup, failed expectation, invalid action, evaluation-oriented setup,
  and report/export examples.
- Document how scenarios differ from provider fixtures and demo showcase scripts.

Out of scope:

- No arbitrary Python execution.
- No simulator-specific scenario schema.

Acceptance criteria:

- [ ] Gallery scenarios validate and run through the CLI.
- [ ] Failure scenarios are intentionally marked and tested.
- [ ] Docs show expected artifacts and first triage steps.
- [ ] Scenario examples stay JSON-native and deterministic.

Validation:

```bash
uv run pytest tests/test_scenarios.py tests/test_cli_world_commands.py tests/test_docs_site.py
uv run mkdocs build --strict
```

### WF-DEMO2-008: Add A Release Readiness Drill Showcase

GitHub issue: [#244](https://github.com/AbdelStark/worldforge/issues/244)

Labels: `documentation`, `roadmap`, `examples`, `release`, `quality`, `artifacts`, `stream: demos-showcases`

Problem: release readiness and package checks exist, but maintainers need a no-surprises drill that
shows exactly how evidence, changelog checks, docs build, dependency audit, package validation, and
known optional skips fit together.

Scope:

- Add a checkout-safe release drill command or documented script path that runs non-publishing
  evidence assembly.
- Include a controlled failure mode and a clean-pass fixture.
- Link the drill from release docs, quality docs, operations, and changelog guidance.

Out of scope:

- No tag creation, publishing, trusted publishing, or signing.
- No prepared-host optional runtime execution unless provided as linked evidence.

Acceptance criteria:

- [ ] Drill produces release evidence artifacts without publishing anything.
- [ ] Controlled failure explains first failed gate and first triage command.
- [ ] Docs distinguish drill evidence from actual release approval.
- [ ] Tests cover pass, failure, and skipped optional-runtime evidence.

Validation:

```bash
uv run pytest tests/test_release_evidence.py tests/test_package_contract_script.py tests/test_docs_site.py
uv run mkdocs build --strict
```

### WF-DEMO2-009: Create A Non-Developer Evidence Review Demo

GitHub issue: [#245](https://github.com/AbdelStark/worldforge/issues/245)

Labels: `documentation`, `roadmap`, `examples`, `artifacts`, `harness`, `evaluation`, `stream: demos-showcases`

Problem: JSON and CLI output work for maintainers, but issue reviewers, research collaborators,
and release readers often need a static artifact that explains results without requiring local
commands.

Scope:

- Add a demo that creates a static HTML evidence package from evaluation, benchmark, world diff,
  and issue-bundle artifacts.
- Include a short reviewer guide explaining what is evidence, what is local-only, and what claims
  are not supported.
- Cover escaping and safe-link behavior.

Out of scope:

- No hosted dashboard or JavaScript application.
- No embedding unsafe local files or raw provider payloads.

Acceptance criteria:

- [ ] Demo emits a single reviewable artifact set with HTML, JSON, and Markdown pointers.
- [ ] Unsafe artifacts are excluded or marked local-only.
- [ ] Docs explain how to attach the artifact to issues or release review.
- [ ] Tests cover escaping and artifact manifest shape.

Validation:

```bash
uv run pytest tests/test_harness_report_compare.py tests/test_evidence_bundle.py tests/test_docs_site.py
uv run mkdocs build --strict
```

### WF-DEMO2-010: Build A Provider Failure Mode Gallery

GitHub issue: [#246](https://github.com/AbdelStark/worldforge/issues/246)

Labels: `documentation`, `roadmap`, `examples`, `provider`, `reliability`, `operations`, `stream: demos-showcases`

Problem: support docs describe failure categories, but users learn faster from concrete fixture
examples that show parser errors, provider errors, retry exhaustion, missing config, unsupported
capability, and unsafe artifact handling.

Scope:

- Add a fixture-backed gallery of provider failure modes with expected event, error, artifact, and
  first triage command.
- Cover mock, remote media, optional runtime, and scaffold provider cases where appropriate.
- Keep all examples safe to run without credentials.

Out of scope:

- No live calls to paid or credentialed providers.
- No storing raw provider secrets or signed URLs.

Acceptance criteria:

- [ ] Gallery covers at least eight provider failure modes.
- [ ] Each entry includes expected signal, owner, first triage step, and safe artifact behavior.
- [ ] Docs link from support, provider docs, and troubleshooting.
- [ ] Tests verify gallery entries stay aligned with real error behavior.

Validation:

```bash
uv run pytest tests/test_remote_video_providers.py tests/test_provider_contracts.py tests/test_docs_site.py
uv run mkdocs build --strict
```

## Stream 3: New Features

Goal: add typed framework capabilities that strengthen external adapter work, composed workflow
inspection, scenario reuse, evidence review, and host-owned optional runtime operation.

### WF-FEAT2-001: Add Provider Lifecycle Hooks For Prepared Hosts

GitHub issue: [#247](https://github.com/AbdelStark/worldforge/issues/247)

Labels: `enhancement`, `roadmap`, `provider`, `operations`, `optional-dependency`, `stream: new-features`

Problem: optional provider integrations often need host-specific preflight, setup, warmup, and
teardown behavior, but WorldForge currently treats those steps as script-level concerns.

Scope:

- Add typed lifecycle hooks for provider preflight, warmup, teardown, and readiness evidence.
- Keep hooks optional and provider-owned, with safe defaults for existing providers.
- Expose lifecycle status through diagnostics without importing optional runtimes from base paths.

Out of scope:

- No dependency installation or credential provisioning.
- No long-running daemon lifecycle manager.

Acceptance criteria:

- [ ] Providers can implement lifecycle hooks without changing existing capability methods.
- [ ] Diagnostics report lifecycle readiness and skip reasons.
- [ ] Hooks are safe for missing optional dependencies.
- [ ] Tests cover no-op, ready, skipped, failed, and teardown-failed states.

Validation:

```bash
uv run pytest tests/test_provider_profiles.py tests/test_cli_doctor.py tests/test_docs_site.py
uv run mkdocs build --strict
```

### WF-FEAT2-002: Add Multi-Run Regression Comparison Reports

GitHub issue: [#248](https://github.com/AbdelStark/worldforge/issues/248)

Labels: `enhancement`, `roadmap`, `benchmark`, `artifacts`, `evaluation`, `stream: new-features`

Problem: run comparison exists for preserved artifacts, but maintainers need regression-oriented
reports that compare current and baseline runs across budgets, metrics, failures, and artifact
shape changes.

Scope:

- Add a regression comparison mode for evaluation, benchmark, and demo showcase runs.
- Report metric deltas, budget status changes, new failures, removed failures, artifact changes,
  and provenance differences.
- Output JSON, Markdown, and HTML where existing renderers support it.

Out of scope:

- No cross-machine performance claim.
- No automatic baseline updates.

Acceptance criteria:

- [ ] Users can compare a candidate run against a preserved baseline run.
- [ ] Report distinguishes metric delta, budget violation, and artifact drift.
- [ ] Unsafe artifacts remain excluded from rendered reports.
- [ ] Tests cover improved, regressed, missing baseline, and incompatible schema cases.

Validation:

```bash
uv run pytest tests/test_harness_report_compare.py tests/test_benchmark.py tests/test_docs_site.py
uv run mkdocs build --strict
```

### WF-FEAT2-003: Add Scenario Parameter Matrices

GitHub issue: [#249](https://github.com/AbdelStark/worldforge/issues/249)

Labels: `enhancement`, `roadmap`, `evaluation`, `persistence`, `testing`, `stream: new-features`

Problem: scenarios are useful for one concrete world setup, but users need a safe way to run small
parameter sweeps without embedding Python code or copying many near-identical JSON files.

Scope:

- Add a JSON-native parameter matrix extension for scenario files.
- Support bounded substitutions for object positions, action targets, provider names, and expected
  artifact values.
- Emit per-case results plus an aggregate report.

Out of scope:

- No arbitrary expression language.
- No distributed or long-running scheduler.

Acceptance criteria:

- [ ] Matrix scenarios validate before execution and reject unbounded or non-JSON-native values.
- [ ] CLI runs every case in a temp or configured workspace.
- [ ] Aggregate output reports pass/fail counts and failed case details.
- [ ] Tests cover valid matrix, invalid substitution, failed expectation, and docs examples.

Validation:

```bash
uv run pytest tests/test_scenarios.py tests/test_cli_world_commands.py tests/test_docs_site.py
uv run mkdocs build --strict
```

### WF-FEAT2-004: Add Evaluation Dataset Manifest Contracts

GitHub issue: [#250](https://github.com/AbdelStark/worldforge/issues/250)

Labels: `enhancement`, `roadmap`, `evaluation`, `artifacts`, `security`, `stream: new-features`

Problem: external evaluation suites may reference fixtures, datasets, or prepared host assets, but
WorldForge needs a manifest contract that records provenance and safety without pulling large data
into the repository.

Scope:

- Add dataset manifest models for local fixtures, remote references, checksums, license notes,
  privacy/safety flags, and host-owned acquisition steps.
- Integrate manifests with evaluation provenance and issue/release evidence.
- Reject unsafe paths and missing required provenance fields.

Out of scope:

- No dataset downloader.
- No large dataset storage in the repo.

Acceptance criteria:

- [ ] Dataset manifests are JSON-native, schema-versioned, and validated.
- [ ] Evaluation reports can cite dataset manifests without embedding datasets.
- [ ] Unsafe or under-specified manifests fail explicitly.
- [ ] Docs explain license/provenance boundaries and host-owned assets.

Validation:

```bash
uv run pytest tests/test_evaluation_suites.py tests/test_evidence_bundle.py tests/test_docs_site.py
uv run mkdocs build --strict
```

### WF-FEAT2-005: Add Provider Contract CLI For External Adapters

GitHub issue: [#251](https://github.com/AbdelStark/worldforge/issues/251)

Labels: `enhancement`, `roadmap`, `provider`, `testing`, `developer-experience`, `stream: new-features`

Problem: provider contract helpers exist for tests, but external adapter authors need a CLI that
runs the relevant contract checks against an installed provider and emits issue-ready evidence.

Scope:

- Add a `worldforge provider contract` command for registered providers or direct factory paths.
- Select checks based on advertised capabilities and provider profile metadata.
- Emit JSON and Markdown evidence with passed checks, skipped host-owned checks, failures, and
  next steps.

Out of scope:

- No automatic provider promotion.
- No live-provider calls unless explicitly configured by the host.

Acceptance criteria:

- [ ] CLI can run contract checks for mock and fixture-backed providers.
- [ ] Unsupported or unimplemented advertised capabilities fail loudly.
- [ ] Output is safe to attach and includes validation commands.
- [ ] Docs link the CLI from provider authoring and external provider docs.

Validation:

```bash
uv run pytest tests/test_provider_contracts.py tests/test_provider_entry_points.py tests/test_docs_site.py
uv run mkdocs build --strict
```

### WF-FEAT2-006: Add Runtime Asset Manifest And Cache Policy Helpers

GitHub issue: [#252](https://github.com/AbdelStark/worldforge/issues/252)

Labels: `enhancement`, `roadmap`, `optional-dependency`, `operations`, `artifacts`, `stream: new-features`

Problem: prepared-host runtimes depend on checkpoints, object files, Hugging Face assets, and cache
locations, but WorldForge lacks a typed manifest that describes those assets without owning or
downloading them.

Scope:

- Add runtime asset manifest models for path, source, revision, checksum, size, cache root,
  local-only status, and rebuild command.
- Integrate manifests with optional smoke reports and run manifests.
- Document cache policy expectations for LeWorldModel, LeRobot, GR00T, Cosmos-Policy, and future
  provider candidates.

Out of scope:

- No asset download manager.
- No committing checkpoints, datasets, or generated object files.

Acceptance criteria:

- [ ] Runtime asset manifests validate local-only and attachable fields separately.
- [ ] Optional smoke outputs can reference manifests without embedding assets.
- [ ] Docs explain cache cleanup, rebuild, and evidence boundaries.
- [ ] Tests cover valid, missing, unsafe, and local-only manifest cases.

Validation:

```bash
uv run pytest tests/test_runtime_profiles.py tests/test_robotics_showcase.py tests/test_docs_site.py
uv run mkdocs build --strict
```

### WF-FEAT2-007: Add Non-Secret Configuration Profiles

GitHub issue: [#253](https://github.com/AbdelStark/worldforge/issues/253)

Labels: `enhancement`, `roadmap`, `operations`, `provider`, `developer-experience`, `stream: new-features`

Problem: users repeatedly provide provider names, workspace paths, timeouts, report formats, and
prepared-host cache settings, but WorldForge has no typed non-secret configuration profile that can
be shared safely.

Scope:

- Add JSON or TOML configuration profiles for non-secret defaults.
- Support provider selection, workspace directories, output formats, timeout/retry presets, and
  optional runtime cache roots where safe.
- Keep secrets and credentials in environment variables or host-owned secret stores only.

Out of scope:

- No secret manager.
- No global mutable service configuration.

Acceptance criteria:

- [ ] Profiles reject secret-looking keys and unsafe paths where applicable.
- [ ] CLI commands can opt into a profile without changing existing defaults.
- [ ] Profile provenance appears in run manifests.
- [ ] Docs explain what belongs in profiles and what does not.

Validation:

```bash
uv run pytest tests/test_provider_config.py tests/test_harness_workspace.py tests/test_docs_site.py
uv run mkdocs build --strict
```

### WF-FEAT2-008: Add Report Renderer Extension Points

GitHub issue: [#254](https://github.com/AbdelStark/worldforge/issues/254)

Labels: `enhancement`, `roadmap`, `artifacts`, `developer-experience`, `harness`, `stream: new-features`

Problem: JSON, Markdown, CSV, and HTML reports cover built-in workflows, but external suites and
host applications need a supported way to add safe renderers without modifying internal modules.

Scope:

- Add a renderer registration API for safe report formats and artifact families.
- Validate renderer metadata, declared safety behavior, supported schemas, and output media type.
- Keep built-in renderers unchanged and make extension failure explicit.

Out of scope:

- No execution of untrusted renderer plugins from arbitrary files.
- No web dashboard.

Acceptance criteria:

- [ ] External code can register a renderer for a supported artifact family.
- [ ] Renderer output is marked safe-to-attach or local-only.
- [ ] Invalid renderer metadata fails explicitly.
- [ ] Tests cover built-in renderers, custom renderer, duplicate format, and unsafe output cases.

Validation:

```bash
uv run pytest tests/test_harness_report_compare.py tests/test_evidence_bundle.py tests/test_docs_site.py
uv run mkdocs build --strict
```

### WF-FEAT2-009: Add World State Migration Preview Tools

GitHub issue: [#255](https://github.com/AbdelStark/worldforge/issues/255)

Labels: `enhancement`, `roadmap`, `persistence`, `reliability`, `artifacts`, `stream: new-features`

Problem: local JSON persistence is intentionally simple, but schema changes and imported worlds
need a preview path that shows what would change before any state is rewritten.

Scope:

- Add a migration preview command for persisted worlds and exported world JSON.
- Report schema version, required changes, invalid fields, unsafe IDs, bounding-box corrections,
  and whether migration can be applied safely.
- Keep actual rewrite as an explicit second step if implemented.

Out of scope:

- No concurrent migration service.
- No silent repair of malformed world state.

Acceptance criteria:

- [ ] Preview is read-only by default and works on a temp copy in tests.
- [ ] Invalid state reports exact failure reasons instead of coercing silently.
- [ ] Output can be attached to issues safely.
- [ ] Docs explain import/export and local persistence migration boundaries.

Validation:

```bash
uv run pytest tests/test_world_lifecycle.py tests/test_persistence_preflight.py tests/test_docs_site.py
uv run mkdocs build --strict
```

### WF-FEAT2-010: Add Composed Workflow Trace Artifacts

GitHub issue: [#256](https://github.com/AbdelStark/worldforge/issues/256)

Labels: `enhancement`, `roadmap`, `observability`, `artifacts`, `provider`, `stream: new-features`

Problem: provider events describe individual operations, but composed workflows such as
policy+score planning, batch evaluation, scenario matrices, and demo showcases need a compact trace
artifact that explains step order, provider boundaries, artifacts, and failure propagation.

Scope:

- Add a JSON-native workflow trace model for composed operations.
- Record step IDs, operation names, provider/capability slots, input/output artifact references,
  status, timing, sanitized error summaries, and parent-child relationships.
- Render traces into Markdown and optional Rerun/HTML layers where existing integrations support
  them.

Out of scope:

- No distributed tracing backend.
- No raw prompt, tensor, credential, or robot-controller telemetry capture.

Acceptance criteria:

- [ ] Composed workflows can emit trace artifacts without changing provider capability semantics.
- [ ] Trace artifacts are sanitized and schema-versioned.
- [ ] Failure propagation is visible without hiding the original provider error.
- [ ] Tests cover successful, skipped, failed, and nested workflow traces.

Validation:

```bash
uv run pytest tests/test_provider_events.py tests/test_evaluation_and_planning.py tests/test_rerun_integration.py tests/test_docs_site.py
uv run mkdocs build --strict
```

## Issue Creation Notes

- Existing open issues remain in force and are referenced where this expansion depends on them.
- Stream labels:
  - `stream: production-quality`
  - `stream: demos-showcases`
  - `stream: new-features`
- Batch label:
  - `roadmap: expansion-2`
- Issue bodies should preserve the problem, scope, out-of-scope, acceptance, validation,
  dependencies, and source pointers from this document.

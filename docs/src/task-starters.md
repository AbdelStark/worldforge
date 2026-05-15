# Contributor Task Starters

Use these starter packs to turn an issue into a bounded contribution plan. They are not a
substitute for reading the code and docs before editing; they are the default checklist for files
to inspect, shortcuts to avoid, validation to run, and evidence to attach.

Pick the closest starter before opening a pull request. If an issue spans multiple starters, use
the stricter validation and evidence requirements from each affected surface.

Each starter deliberately includes docs/changelog expectations so user-visible behavior, public
guidance, and release notes stay aligned.

## Provider Adapter Or Runtime Promotion

Use for provider scaffolds, runtime manifests, capability promotion, provider parser fixes,
optional-runtime smokes, or provider documentation.

### Likely Files To Inspect

- `src/worldforge/providers/`
- `src/worldforge/providers/catalog.py`
- `src/worldforge/providers/runtime_manifests/`
- `src/worldforge/testing/`
- `tests/fixtures/providers/`
- `docs/src/providers/`
- `docs/src/provider-authoring-guide.md`
- `docs/src/provider-configuration-index.md`
- `.env.example`

### Files Commonly Updated

- Provider implementation, parser, runtime manifest, and provider-specific tests.
- Generated provider docs through `scripts/generate_provider_docs.py`.
- `.env.example`, `docs/src/providers/<provider>.md`, `docs/src/operations.md`, and
  `docs/src/playbooks.md` when configuration, commands, or failure modes change.
- `CHANGELOG.md` and `AGENTS.md` for user-visible behavior or new contributor constraints.

### Forbidden Shortcuts

- Do not advertise `predict`, `generate`, `reason`, `embed`, `transfer`, `score`, or `policy`
  unless the capability is implemented end to end.
- Do not add optional runtimes, robot stacks, checkpoints, datasets, or CUDA packages to the base
  dependency set.
- Do not auto-register optional providers without their required configuration.
- Do not present scaffold or deterministic mock behavior as real upstream integration.
- Do not commit credentials, signed URLs, private endpoints, host-local paths, checkpoints, or
  downloaded assets.

### Validation Commands

```bash
uv run pytest tests/test_provider_docs.py tests/test_provider_profiles.py tests/test_provider_contracts.py
uv run python scripts/generate_provider_docs.py --check
uv run python scripts/check_optional_import_boundaries.py
uv run mkdocs build --strict
```

Prepared-host or live-runtime work should also name the smoke command from the provider runtime
manifest and attach the sanitized `run_manifest.json` or explicit blocker.

### Evidence Artifacts

- Fixture payloads under `tests/fixtures/providers/` for parser and failure-mode coverage.
- Provider contract test output and generated provider-doc check output.
- Sanitized `run_manifest.json`, live-smoke registry entry, or explicit prepared-host blocker for
  runtime promotion.
- Updated provider docs showing command, expected success signal, and first triage step.

### Docs And Changelog Expectations

- Update provider docs and generated catalog tables for provider behavior changes.
- Update `.env.example` for new public environment variables.
- Update `docs/src/api/python.md`, `docs/src/architecture.md`, `docs/src/operations.md`, or
  `docs/src/playbooks.md` when the provider changes public behavior or operator workflow.
- Add a `CHANGELOG.md` entry for user-visible changes.

### Review Checklist

- Capability metadata matches implemented behavior.
- Missing dependency, missing credential, malformed input, malformed upstream output, and expired
  artifact paths fail with public errors.
- Provider events and artifacts are sanitized.
- Tests cover success and documented failure modes.
- Docs do not overclaim upstream fidelity, availability, or physical safety.

## Docs-Only Or Public Surface

Use for README, MkDocs pages, contributor docs, playbooks, roadmap records, command examples, and
public wording corrections that do not change runtime behavior.

### Likely Files To Inspect

- `README.md`
- `CONTRIBUTING.md`
- `docs/src/`
- `mkdocs.yml`
- `docs/src/SUMMARY.md`
- `docs/src/docs-map.md`
- `CHANGELOG.md`
- `tests/test_docs_site.py`
- `scripts/check_docs_commands.py`
- `scripts/check_docs_snippets.py`

### Files Commonly Updated

- The owning docs page plus any linked navigation page.
- `mkdocs.yml` and `docs/src/SUMMARY.md` when adding, removing, or renaming pages.
- `docs/src/docs-map.md` when reader paths change.
- `tests/test_docs_site.py` for durable public docs contracts.
- `CHANGELOG.md` for user-visible documentation or workflow additions.

### Forbidden Shortcuts

- Do not hand-edit generated provider catalog blocks.
- Do not add example commands that are stale, unowned, or impossible in a clean checkout.
- Do not leave executable Python or JSON examples unmarked when snippet coverage should apply.
- Do not use docs to claim physical fidelity, upstream availability, or real integration beyond
  the available evidence.

### Validation Commands

```bash
uv run pytest tests/test_docs_site.py
uv run python scripts/check_docs_commands.py
uv run python scripts/check_docs_snippets.py
uv run mkdocs build --strict
```

### Evidence Artifacts

- Docs test output and strict MkDocs build output.
- Command drift and snippet-check output when examples changed.
- Screenshots are optional; they do not replace the docs gates.

### Docs And Changelog Expectations

- Link new pages from `mkdocs.yml`, `docs/src/SUMMARY.md`, and the appropriate reader path.
- Update `docs/src/docs-map.md` when navigation or audience routing changes.
- Add a `CHANGELOG.md` entry when the docs change a public workflow, validation gate, or reader
  contract.

### Review Checklist

- The page has one owning contract and does not duplicate deeper operational docs.
- Relative links resolve in strict MkDocs.
- Commands include expected success signal or first triage step when they define an operator
  workflow.
- Public wording is precise and avoids inflated claims.

## Demo Or Showcase Workflow

Use for checkout-safe demos, packaged demo entry points, showcase workflows, cookbook recipes,
TheWorldHarness flows, or prepared-host robotics showcase documentation.

### Likely Files To Inspect

- `src/worldforge/demos/`
- `src/worldforge/harness/`
- `src/worldforge/smoke/`
- `scripts/demo_showcases.py`
- `scripts/robotics-showcase`
- `examples/`
- `docs/src/demo-showcases.md`
- `docs/src/use-case-cookbook.md`
- `docs/src/theworldharness.md`
- `docs/src/robotics-showcase.md`

### Files Commonly Updated

- Demo script, packaged entry point, harness flow metadata, or checkout-safe example.
- Demo docs, cookbook recipe, CLI docs, and playbooks.
- Tests covering the workflow registry, run workspace output, and documented failure path.
- `CHANGELOG.md` and `AGENTS.md` when a new workflow or command becomes part of the public
  contributor surface.

### Forbidden Shortcuts

- Do not require paid APIs, GPU runtimes, checkpoints, robot hardware, or optional packages for
  checkout-safe demos.
- Do not hide prepared-host requirements behind a default path that appears checkout-safe.
- Do not write unredacted host paths, private endpoints, credentials, or signed URLs into demo
  artifacts.
- Do not use deterministic fixtures to imply real physical or media quality.

### Validation Commands

```bash
uv run python scripts/demo_showcases.py list
uv run python scripts/demo_showcases.py run first-run --workspace-dir .worldforge/demo-showcases
uv run pytest tests/test_demo_showcases.py tests/test_harness_workspace.py
uv run mkdocs build --strict
```

Prepared-host demos should add their health-only or `--json-only` smoke command and explain the
expected skipped or passed status.

### Evidence Artifacts

- Preserved run workspace containing `run_manifest.json`.
- Demo output JSON, Markdown, or report artifact marked safe to attach.
- Prepared-host smoke manifest or explicit skip reason for optional-runtime workflows.

### Docs And Changelog Expectations

- Update demo docs, cookbook recipe, CLI examples, and playbooks when commands or artifact layouts
  change.
- Update `docs/src/docs-map.md` when the workflow becomes a reader path.
- Add a `CHANGELOG.md` entry for new or materially changed workflows.

### Review Checklist

- The default path runs in a clean checkout or clearly declares prepared-host requirements.
- The workflow writes a deterministic, sanitized evidence artifact.
- Failure output names the first triage step.
- Optional dependencies remain host-owned.

## Artifact, Report, Or Evidence

Use for run manifests, evidence bundles, issue bundles, release evidence, quality dashboards,
static HTML reports, run indexes, provenance, artifact integrity, or schema-versioned output.

### Likely Files To Inspect

- `src/worldforge/evidence_bundle.py`
- `src/worldforge/html_report.py`
- `src/worldforge/provenance.py`
- `src/worldforge/harness/workspace.py`
- `src/worldforge/harness/run_index.py`
- `src/worldforge/harness/report_compare.py`
- `src/worldforge/smoke/run_manifest.py`
- `scripts/generate_dependency_audit_evidence.py`
- `scripts/generate_quality_dashboard.py`
- `scripts/generate_release_evidence.py`
- `scripts/generate_release_notes.py`
- `docs/src/artifact-schemas.md`
- `docs/src/artifact-integrity.md`
- `docs/src/html-reports.md`
- `docs/src/run-index.md`

### Files Commonly Updated

- Artifact model, renderer, validator, deterministic test helper, and exact snapshot tests.
- Schema ownership docs and API docs for public artifact fields.
- Operations or playbooks when artifact generation becomes part of an operator workflow.
- `CHANGELOG.md` and `AGENTS.md` for schema, redaction, or release-gate changes.

### Forbidden Shortcuts

- Do not silently coerce invalid persisted or provider-supplied state.
- Do not emit non-JSON-native metadata, tuple-shaped values, object instances, non-finite numbers,
  credentials, signed URLs, or host-local paths.
- Do not update rendered artifacts without validating the data model underneath.
- Do not weaken release, package, coverage, or artifact integrity gates to pass a report change.

### Validation Commands

```bash
uv run pytest tests/test_evidence_bundle.py tests/test_html_report.py tests/test_release_evidence.py
uv run pytest tests/test_harness_workspace.py tests/test_run_index.py tests/test_redaction_corpus.py
uv run pytest tests/test_quality_dashboard.py
uv run mkdocs build --strict
```

### Evidence Artifacts

- Stable JSON, Markdown, or HTML fixture output with deterministic clocks, IDs, and path roots
  where exact snapshots are appropriate.
- Redaction-corpus coverage for every new log-facing or issue-facing field.
- Release evidence JSON, quality dashboard output, or bundle output when the change affects release
  readiness.

### Docs And Changelog Expectations

- Update `docs/src/artifact-schemas.md` for new or changed public artifact families.
- Update artifact-specific docs and API docs for new fields, schema versions, or migration rules.
- Add a `CHANGELOG.md` entry for user-visible artifact, report, schema, or redaction changes.

### Review Checklist

- Schema version, owner, validator, docs entry point, and tests agree.
- Exact snapshots use deterministic helpers instead of volatile timestamps, IDs, or host paths.
- Public error messages and artifacts are safe to attach.
- HTML output remains self-contained and escapes user-supplied text.

## Evaluation Or Benchmark

Use for deterministic evaluation suites, benchmark inputs, budgets, calibration, claim-supporting
reports, comparison logic, or evaluation failure galleries.

### Likely Files To Inspect

- `src/worldforge/evaluation/`
- `src/worldforge/benchmark.py`
- `src/worldforge/benchmark_calibration.py`
- `examples/benchmark-inputs.json`
- `examples/benchmark-budget.json`
- `docs/src/evaluation.md`
- `docs/src/benchmarking.md`
- `docs/src/claim-evidence-map.md`
- `docs/src/live-smoke-evidence.md`
- `tests/test_benchmark.py`

### Files Commonly Updated

- Evaluation suite, benchmark harness, input fixture, budget fixture, renderer, and tests.
- Claim-to-evidence docs when public numbers, gates, or supported capability shapes change.
- Release evidence wiring when a benchmark becomes a release gate.
- `CHANGELOG.md` for new eval suites, benchmark operations, budgets, or report behavior.

### Forbidden Shortcuts

- Do not turn deterministic eval suites into physical-fidelity claims.
- Do not benchmark through a different capability than the documented operation.
- Do not change budgets without preserved run evidence and a stated rationale.
- Do not depend on live optional runtimes for checkout-safe benchmark tests.

### Validation Commands

```bash
uv run pytest tests/test_benchmark.py tests/test_evaluation_suites.py tests/test_evaluation_and_planning.py
uv run pytest tests/test_benchmark_budget_calibration.py
uv run worldforge benchmark --provider mock --operation generate --input-file examples/benchmark-inputs.json
uv run worldforge benchmark --provider mock --operation generate --budget-file examples/benchmark-budget.json
uv run mkdocs build --strict
```

### Evidence Artifacts

- Preserved benchmark JSON, budget result, or calibration report.
- Input fixture that is deterministic and committed when it supports public docs.
- Claim-to-evidence update for public benchmark or evaluation statements.

### Docs And Changelog Expectations

- Update evaluation, benchmarking, claim-to-evidence, and release-gate docs when behavior or
  public interpretation changes.
- Update `examples/benchmark-inputs.json` or `examples/benchmark-budget.json` only with tests that
  prove the fixture still loads.
- Add a `CHANGELOG.md` entry for user-visible eval, benchmark, or report changes.

### Review Checklist

- Provider, capability, suite, preset, input file, and budget file are named.
- Metrics are finite, internally coherent, and rendered from validated data.
- Checkout-safe tests remain deterministic.
- Public claims point to preserved evidence and do not overstate runtime coverage.

## CLI Or Operator Workflow

Use for CLI commands, public error behavior, local persistence commands, preflight diagnostics,
operator drills, run cleanup, provider diagnostics, or recovery workflows.

### Likely Files To Inspect

- `src/worldforge/cli.py`
- `src/worldforge/framework.py`
- `src/worldforge/persistence_preflight.py`
- `src/worldforge/harness/`
- `src/worldforge/observability.py`
- `docs/src/cli.md`
- `docs/src/operations.md`
- `docs/src/playbooks.md`
- `docs/src/support.md`
- `tests/test_cli_help_snapshots.py`
- `tests/test_cli_world_commands.py`
- `tests/test_operator_drills.py`

### Files Commonly Updated

- CLI parser and command handler, public API helper, persistence or diagnostics helper, and CLI
  tests.
- Help snapshots when command text changes intentionally.
- CLI docs, operations, playbooks, support docs, and troubleshooting matrix.
- `CHANGELOG.md` and `AGENTS.md` for new commands, constraints, or failure boundaries.

### Forbidden Shortcuts

- Do not leak credentials, signed URL query strings, private endpoints, or host-local paths in CLI
  errors, logs, manifests, or issue bundles.
- Do not silently repair corrupted world state without a visible recovery artifact.
- Do not add service-grade persistence, lock files, or database dependencies without a design
  record.
- Do not import optional TUI, Rerun, torch, LeRobot, GR00T, Cosmos-Policy, or LeWorldModel
  runtimes from base CLI imports.

### Validation Commands

```bash
uv run worldforge --help
uv run pytest tests/test_cli_help_snapshots.py tests/test_cli_world_commands.py tests/test_operator_drills.py
uv run python scripts/check_docs_commands.py
uv run python scripts/check_optional_import_boundaries.py
uv run mkdocs build --strict
```

### Evidence Artifacts

- CLI test output, help snapshot update, or command output fixture.
- Sanitized preflight, diagnostics, run index, or issue bundle artifact when the workflow produces
  operator evidence.
- First-triage command and expected success or failure signal in docs.

### Docs And Changelog Expectations

- Update `docs/src/cli.md`, `docs/src/operations.md`, `docs/src/playbooks.md`, and
  `docs/src/support.md` for new commands or operator behavior.
- Update `docs/src/api/python.md` when command behavior exposes or depends on a public Python API.
- Add a `CHANGELOG.md` entry for user-visible CLI behavior.

### Review Checklist

- CLI errors include command owner context and first triage step.
- Malformed public inputs fail with `WorldForgeError`; malformed persisted/provider state fails
  with `WorldStateError`; provider/runtime failures fail with `ProviderError`.
- Help text, docs commands, and snapshots agree.
- Operator artifacts are JSON-native and safe to attach.

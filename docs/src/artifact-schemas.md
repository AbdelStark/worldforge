# Artifact Schemas

WorldForge artifacts are JSON-native records that may leave one process: run manifests, evidence
bundles, scenarios, benchmark inputs, report metadata, world diffs, and similar files. Each public
or semi-public artifact family needs an owner, a version field, validation coverage, and a migration
decision before the schema changes.

Private temp files, cache internals, checkpoint files, downloaded datasets, and local-only unsafe
artifacts are not part of this compatibility map. They must still stay out of public bundles unless
another documented contract marks them safe to attach.

## Ownership Map

| Artifact family | Version field | Owner and source | Validation surface | Docs and CLI surface | Migration owner |
| --- | --- | --- | --- | --- | --- |
| World state JSON | `schema_version` via `SCHEMA_VERSION` | `src/worldforge/framework.py` | `tests/test_world_lifecycle.py`, `tests/test_cli_world_commands.py` | `worldforge world ...`, [Operations](./operations.md) | Framework and persistence owner |
| Run manifests | `schema_version` via `RUN_MANIFEST_SCHEMA_VERSION` | `src/worldforge/smoke/run_manifest.py` | `tests/test_smoke_run_manifest.py`, optional smoke tests | `--run-manifest`, [Live Smoke Evidence Registry](./live-smoke-evidence.md) | Optional runtime and smoke owner |
| Run workspaces | `schema_version` via `RUN_WORKSPACE_SCHEMA_VERSION` | `src/worldforge/harness/workspace.py` | `tests/test_harness_workspace.py`, `tests/test_harness_flows.py` | `worldforge runs ...`, [Run Artifact Index](./run-index.md) | Harness workspace owner |
| Run index reports | `schema_version` via `RUN_INDEX_SCHEMA_VERSION` | `src/worldforge/harness/run_index.py` | `tests/test_run_index.py` | `worldforge runs index`, [Run Artifact Index](./run-index.md) | Harness workspace owner |
| Evidence bundles and issue bundles | `schema_version` via `EVIDENCE_BUNDLE_SCHEMA_VERSION` | `src/worldforge/evidence_bundle.py` | `tests/test_evidence_bundle.py`, `tests/test_redaction_corpus.py` | `worldforge runs bundle`, [Artifact Integrity](./artifact-integrity.md) | Evidence owner |
| Release evidence JSON | `schema_version` literal `1` | `scripts/generate_release_evidence.py` | `tests/test_release_evidence.py` | `scripts/generate_release_evidence.py`, [Artifact Integrity](./artifact-integrity.md) | Release owner |
| Dependency audit evidence | `schema_version` via `DEPENDENCY_AUDIT_EVIDENCE_SCHEMA_VERSION` | `scripts/generate_dependency_audit_evidence.py` | `tests/test_dependency_audit_evidence.py` | `scripts/generate_dependency_audit_evidence.py`, [Artifact Integrity](./artifact-integrity.md) | Release owner |
| Quality dashboard artifact | `schema_version` via `QUALITY_DASHBOARD_SCHEMA_VERSION` | `scripts/generate_quality_dashboard.py` | `tests/test_quality_dashboard.py` | `scripts/generate_quality_dashboard.py`, [Artifact Integrity](./artifact-integrity.md) | Release owner |
| Benchmark inputs and budgets | `schema_version` in fixture payloads | `src/worldforge/benchmark.py` | `tests/test_benchmark.py`, `tests/test_benchmark_presets.py` | `worldforge benchmark --input-file`, [Benchmarking](./benchmarking.md) | Benchmark owner |
| Benchmark calibration reports | `schema_version` via `BENCHMARK_CALIBRATION_SCHEMA_VERSION` | `src/worldforge/benchmark_calibration.py` | `tests/test_benchmark_budget_calibration.py` | `scripts/calibrate_benchmark_budgets.py`, [Benchmarking](./benchmarking.md) | Benchmark owner |
| Evaluation reports and provenance | `schema_version` via `PROVENANCE_SCHEMA_VERSION` | `src/worldforge/provenance.py`, `src/worldforge/evaluation/suites.py` | `tests/test_evaluation_suites.py` | `worldforge eval`, [Evaluation](./evaluation.md) | Evaluation owner |
| Dataset manifests | `schema_version` via `DATASET_MANIFEST_SCHEMA_VERSION` | `src/worldforge/dataset_manifests.py` | `tests/test_evaluation_suites.py`, `tests/test_evidence_bundle.py` | `worldforge eval --dataset-manifest`, [Evaluation](./evaluation.md) | Evaluation owner |
| Evaluation failure galleries | `schema_version` via `EVALUATION_FAILURE_GALLERY_SCHEMA_VERSION` | `src/worldforge/evaluation/suites.py` | `tests/test_evaluation_failure_gallery.py` | [Evaluation](./evaluation.md) | Evaluation owner |
| Capability fixture corpus | `schema_version` via `FIXTURE_SCHEMA_VERSION` | `src/worldforge/testing/capability_fixtures.py` | `tests/test_capability_fixtures.py` | [Capability Fixture Corpus](./fixtures.md) | Testing owner |
| Fixture snapshot manifests | `schema_version` via `FIXTURE_SNAPSHOT_MANIFEST_SCHEMA_VERSION` | `src/worldforge/testing/fixture_snapshots.py` and `tests/fixtures/fixture-snapshots.json` | `tests/test_capability_fixtures.py` | `scripts/manage_fixture_snapshots.py`, [Capability Fixture Corpus](./fixtures.md) | Testing owner |
| Provider runtime manifests | `schema_version` via `MANIFEST_SCHEMA_VERSION` | `src/worldforge/providers/runtime_manifest.py` and `src/worldforge/providers/runtime_manifests/*.json` | `tests/test_provider_runtime_manifests.py` | generated provider docs, [Provider Authoring Guide](./provider-authoring-guide.md) | Provider owner |
| Runtime asset manifests and references | `schema_version` via `RUNTIME_ASSET_MANIFEST_SCHEMA_VERSION` | `src/worldforge/providers/runtime_manifest.py`, `src/worldforge/smoke/runtime_assets.py` | `tests/test_runtime_profiles.py`, `tests/test_robotics_showcase.py` | `run_manifest.runtime_assets`, [Operations](./operations.md) | Optional runtime and smoke owner |
| Non-secret configuration profiles | `schema_version` via `CONFIG_PROFILE_SCHEMA_VERSION` | `src/worldforge/config_profiles.py` | `tests/test_provider_config.py`, `tests/test_harness_workspace.py` | `worldforge eval --profile`, `worldforge benchmark --profile`, [Operations](./operations.md) | Operations and provider owner |
| Provider contract evidence | `schema_version` via `PROVIDER_CONTRACT_EVIDENCE_SCHEMA_VERSION` | `src/worldforge/provider_contracts.py` | `tests/test_provider_contracts.py`, `tests/test_provider_entry_points.py` | `worldforge provider contract`, [Provider Authoring Guide](./provider-authoring-guide.md), [External Provider Packages](./external-providers.md) | Provider owner |
| Capability negotiation reports | `schema_version` via `CAPABILITY_NEGOTIATION_SCHEMA_VERSION` | `src/worldforge/capability_negotiation.py` | `tests/test_capability_negotiation.py` | `worldforge negotiate`, [Capability Negotiation](./capability-negotiation.md) | Provider diagnostics owner |
| Scenario files and scenario results | `schema_version` via `SCENARIO_SCHEMA_VERSION` | `src/worldforge/scenarios.py` | `tests/test_scenarios.py` | `worldforge scenario ...`, [Scenario Definition Format](./scenarios.md) | Scenario owner |
| World diff and patch artifacts | `schema_version` via `WORLD_DIFF_SCHEMA_VERSION` | `src/worldforge/world_diff.py` | `tests/test_world_diff.py` | `worldforge world diff`, [World State Diff And Patch](./world-diff.md) | Persistence owner |
| Static HTML report metadata | `schema_version` via `HTML_REPORT_SCHEMA_VERSION` | `src/worldforge/html_report.py` | `tests/test_html_report.py` | `--format html`, [Static HTML Reports](./html-reports.md) | Report rendering owner |
| Scene artifacts | `schema_version` via `SCENE_ARTIFACT_SCHEMA_VERSION` | `src/worldforge/scene_artifacts.py` | `tests/test_scene_artifacts.py` | [Spatial Scene Artifact Boundary](./spatial-scene-artifact-boundary.md) | Provider artifact owner |
| Live smoke evidence registry | `schema_version` via `LIVE_SMOKE_EVIDENCE_SCHEMA_VERSION` | `src/worldforge/live_smoke_evidence.py`, `docs/src/live-smoke-evidence.json` | `tests/test_live_smoke_evidence.py` | [Live Smoke Evidence Registry](./live-smoke-evidence.md) | Optional runtime and smoke owner |
| Capability-specific replay artifacts | family-specific `schema_version` constants | `src/worldforge/harness/flows.py` | `tests/test_cosmos_policy_provider.py`, `tests/test_harness_flows.py` | [Robotics Replay Showcase](./robotics-showcase.md) | Harness and robotics owner |

## Change Rules

Use the smallest compatible change that keeps older artifacts honest.

| Change type | Required action |
| --- | --- |
| Additive optional field | Keep the existing schema version if old readers ignore the field safely. Add tests proving absent and present field behavior. Mention the field in the owning docs when users may see it. |
| Additive required field | Bump the schema version or provide a compatibility default that is explicit in code and tests. Add a changelog entry if existing user-authored artifacts need action. |
| Breaking rename, removal, or type change | Bump the schema version, reject unsupported old versions loudly unless a reader migration exists, update this page, update the owning docs, and add changelog migration notes. |
| Renderer-only layout change | Do not bump the source artifact schema if JSON payload semantics are unchanged. Update renderer tests and docs screenshots/examples only when user-visible behavior changes. |
| Private implementation metadata | Keep it out of public artifacts when practical. If it must appear in a public JSON record, document whether it is stable, provisional, or local-only. |
| Security or redaction fix | Prefer immediate strict rejection or redaction over backward compatibility. State the unsafe old behavior, migration or recovery command, and validation coverage in the PR and changelog. |

All public or semi-public artifacts must keep string keys, finite numbers, lists, objects, booleans,
strings, and nulls only. Do not serialize tuples, object instances, exceptions, raw tensors,
credentials, signed URL query strings, private endpoints, checkpoint contents, or host-local cache
payloads into attachable artifacts.

## Migration Decisions

Every artifact PR should answer these questions before merge:

- Is the artifact public, semi-public, local-only, or private?
- Which module owns the writer and reader?
- What is the current `schema_version`, and does this change require a bump?
- If old artifacts remain readable, which test proves that compatibility?
- If old artifacts are rejected, what exact error and recovery path does the user see?
- Do docs and the changelog explain the migration when user-authored files are affected?
- Are unsafe fields excluded or marked local-only before issue, release, HTML, Rerun, or metrics
  rendering?

## Acceptable Compatibility Patterns

- A reader accepts an older additive version and fills a clearly documented default before
  validation.
- A renderer ignores unknown optional keys while preserving the original JSON in the raw artifact.
- A migration preview command reports required changes without rewriting the user's file by
  default.
- A no-migration decision rejects unsupported versions with a `WorldStateError`,
  `WorldForgeError`, or `ProviderError` that names the artifact family, version, owner, and first
  triage command.

Do not silently coerce invalid persisted state, provider output, or security-sensitive artifact
fields to keep an old artifact loading.

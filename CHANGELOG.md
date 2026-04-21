# Changelog

All notable user-visible changes to WorldForge are recorded here.

This project follows the spirit of Keep a Changelog. Versioning is currently pre-1.0, so minor
releases may still include breaking changes when the public API needs to tighten.

## Unreleased

### Harness

- Reskinned TheWorldHarness with registered `worldforge-dark` and `worldforge-light` themes,
  retiring the hard-coded hex literals in `src/worldforge/harness/tui.py` in favour of semantic
  tokens (`$accent`, `$success`, `$warning`, `$error`, `$panel`, `$boost`, `$surface`, plus the
  custom `$muted` variable) so the harness reads as a polished workspace on light terminals.
- Added a header chrome strip with a `worldforge > <flow>` breadcrumb and a
  `<provider> . <capability>` status pill that update reactively when the selected flow changes.
- Added a hidden `Ctrl+T` binding that cycles between the two registered themes without
  restarting the harness.
- Split TheWorldHarness into a screen stack: a `HomeScreen` landing page with three jump cards
  (`n` create a world, `p` run a provider, `e` run an eval), a `RunInspectorScreen` that owns
  the existing flow visualisation, plus modal `HelpScreen` and `PlaceholderScreen` overlays.
  `worldforge-harness` opens on Home by default and on the Run Inspector when `--flow` is
  passed.
- Added the static command palette layer via `App.get_system_commands` (`Ctrl+P`): "Jump:
  Home", "Jump: Run Inspector", "Open Help", one "Run flow: <title>" entry per registered
  flow, "Switch theme", and the stock Quit. The dynamic provider for worlds, providers, and
  recent runs is reserved for a later milestone.
- Added `?` to open a modal `HelpScreen` that lists every binding declared on the screen below
  it, plus chord bindings `g h` / `g r` for jump-to-Home and jump-to-Run-Inspector.
- Updated the `Header` breadcrumb to reflect the active screen, deepening to the selected flow
  on the Run Inspector (`worldforge › run-inspector › <flow>`).

### Added

- Added the `worldforge world` CLI command group for local JSON persistence workflows, including
  create, list, show, history, export, import, and fork commands backed by the existing validated
  `WorldForge` persistence API.
- Added persisted-world mutation and prediction commands:
  `worldforge world objects`, `add-object`, `update-object`, `remove-object`, and `predict`.
  These commands load local JSON worlds, apply typed scene/action values, and save through
  `WorldForge.save_world(...)`; `world predict --dry-run` previews provider output without
  replacing the saved file.
- Added `worldforge examples` with Markdown and JSON output so CLI users can discover checkout
  scripts, packaged demos, and optional smoke commands without scanning repository docs.
- Added the `worldforge-demo-lerobot` console command and packaged the LeRobot policy-plus-score
  planning walkthrough under `src/worldforge/demos/lerobot_e2e.py`, keeping
  `examples/lerobot_e2e_demo.py` as a compatibility wrapper.
- Added `examples/README.md` as a short command index for the checkout scripts and packaged demos.
- Added CLI help snapshot tests for the primary `worldforge` command surface.
- Added `scripts/generate_provider_docs.py` so the provider catalog table can be refreshed and
  checked from `src/worldforge/providers/catalog.py`.
- Added `worldforge provider docs` so users can discover provider documentation paths from the CLI.
- Added TheWorldHarness as an optional Textual TUI (`worldforge-harness` and `worldforge harness`)
  for visually running and inspecting packaged E2E demos.
- Added a TheWorldHarness diagnostics flow for provider catalog inspection and mock benchmark
  comparison across predict, reason, generate, and transfer.
- Added benchmark budget gates for release and claim-oriented checks. `worldforge benchmark` can
  load a JSON budget file, print gate violations, and exit non-zero when success-rate,
  error-count, retry-count, latency, throughput, or unmatched-budget checks fail.
- Added `.env.example` documenting every provider environment variable recognized by
  WorldForge (`COSMOS_BASE_URL`, `NVIDIA_API_KEY`, `RUNWAYML_API_SECRET` and the legacy
  `RUNWAY_API_SECRET` alias, `RUNWAYML_BASE_URL`, `LEWORLDMODEL_POLICY` and the legacy
  `LEWM_POLICY` alias, `LEWORLDMODEL_CACHE_DIR`, `LEWORLDMODEL_DEVICE`, the full
  `GROOT_POLICY_*` and `GROOT_EMBODIMENT_TAG` set, the full `LEROBOT_*` set including the
  legacy `LEROBOT_POLICY` alias, the `JEPA_WMS_*` candidate variables, and the scaffold
  `JEPA_MODEL_PATH` and `GENIE_API_KEY`).
- Added `lerobot` as a first-class optional policy provider for Hugging Face LeRobot
  pretrained policies. The adapter lazily imports LeRobot, supports injectable policies and
  policy loaders for offline testing, validates observation payloads, preserves raw policy
  tensors, and requires a host-owned action translator before returning executable WorldForge
  actions.
- Added `leworldmodel` as a first-class optional score provider for LeWorldModel JEPA cost
  models, including `ActionScoreResult`, `WorldForge.score_actions(...)`, score-output
  validation, provider profile metadata, and fixture-driven tests.
- Added score-based planning, the `policy` capability, `ActionPolicyResult`,
  `WorldForge.select_actions(...)`, policy-only planning, and policy-plus-score planning.
- Added experimental host-owned `gr00t` PolicyClient support, a `jepa-wms` direct-construction
  score-provider candidate scaffold, and `scripts/scaffold_provider.py` for safe provider
  scaffolding.
- Added checkout-safe LeWorldModel and LeRobot demos plus optional LeWorldModel/GR00T/LeRobot
  smoke entry points for host-owned runtimes.

### Changed

- Validated provider capability names across public capability checks and CLI provider filters,
  so typos such as `generation` fail explicitly instead of being treated as unsupported.
- Changed `ProviderCapabilities()` to advertise no operations by default. Providers must opt into
  every capability explicitly, and unsupported `predict()` calls now fail with `ProviderError`
  instead of `NotImplementedError`.
- Centralized in-repo provider discovery in `src/worldforge/providers/catalog.py`, including the
  provider factory list and explicit always-register policy for `mock`. `WorldForge` now uses the
  catalog instead of relying on constructor ordering in `_known_providers()`.
- Extended the provider catalog with documentation-page and runtime-ownership metadata used by the
  generated provider docs table.
- Moved the README provider surface table onto the same generated catalog source as the provider
  docs index.
- Grouped `worldforge examples`, `docs/src/examples.md`, and `examples/README.md` by task so
  prediction, comparison, score planning, policy planning, and optional smoke paths are easier to
  scan.
- Reworked the README, introduction, architecture, provider, and operations docs around the
  capability contract: predictive models, score providers, policy providers, media adapters,
  host-owned optional runtimes, and explicit persistence/evaluation boundaries.
- Added dedicated provider pages for Cosmos, Runway, and LeWorldModel, and normalized the GR00T,
  LeRobot, and JEPA-WMS pages around capability surface, runtime ownership, input/output
  contracts, failure modes, and validation coverage.
- Updated package metadata to describe WorldForge as a typed local-first physical-AI world-model
  framework, removed the development-status classifier, and pointed documentation metadata at
  repository docs instead of a standalone project domain.
- Aligned `make lint` and `make format` with CI, `README.md`, and `AGENTS.md` by adding
  `scripts/` to `ruff check`, `ruff format`, and the `clean` sweep.

### Fixed

- Rejected non-file-safe world IDs before local persistence reads and writes, preventing traversal
  through imported or caller-supplied world identifiers.
- Validated persisted world history entries end to end, including non-negative entry steps,
  historical snapshot states, non-empty summaries, serialized action payloads, and the invariant
  that history entry steps cannot exceed the current world step.
- Wrote saved worlds through validated same-directory temporary files before atomically replacing
  the destination JSON file.
- Rejected stringly-typed booleans for scene object graspability, provider capabilities, and the
  JEPA-WMS `actions_are_normalized` option instead of silently coercing values such as `"false"`
  to `True`.
- Tracked `.env.example` in the repository by adding an explicit `!.env.example` exception
  to `.gitignore`; the general `.env.*` glob was silently excluding the onboarding template.
- Rejected non-finite public numeric inputs for positions, rotations, request policies, provider
  events, video clips, reasoning confidence, embedding vectors, generation FPS, and prediction
  payload metrics.
- Rejected duplicate scene object IDs when adding objects to a world.
- Rejected persisted/provider-supplied world state whose scene-object map key disagrees with the
  object's embedded `id`.
- Made the coverage gate invoke pytest with the `harness` extra so optional Textual TUI tests are
  available during coverage runs while the base package and matrix tests remain free of Textual.
- Validated Runway ratio parsing before constructing returned clip metadata.
- Validated Cosmos health and generation response payloads before decoding returned videos.
- Validated Runway organization, task creation, task polling, task output, artifact content type,
  expired artifact, and empty artifact responses before returning clips.
- Corrected the LeWorldModel smoke task to require an existing upstream object checkpoint instead
  of relying on a nonexistent PyPI checkpoint-preparation helper.
- Updated the real LeWorldModel smoke instructions to use the GitHub `stable-worldmodel` source
  package and `datasets>=2.21`, matching the runtime that can load supported LeWM checkpoints.

### Security

- Hardened local JSON persistence against path traversal by validating world IDs before resolving
  storage paths.
- Raised the development dependency floor to `pytest>=9.0.3` and refreshed `uv.lock` to remove
  the locked `pytest 9.0.2` vulnerability reported as `CVE-2025-71176`.

### Documentation

- Added `AGENTS.md` with repository identity, architecture, commands, conventions, constraints,
  and gotchas for contributors.
- Added user and operator playbooks for checkout validation, provider capability selection,
  provider diagnostics, adapter promotion, local persistence recovery, remote artifacts, optional
  runtime smokes, benchmarks, incident triage, and release gates.
- Added this changelog and linked it from the README.
- Documented host-owned persistence, provider limits, and provider workflow failure modes.
- Added a world-model taxonomy document, plus expanded architecture docs with text and
  Mermaid diagrams for provider injection, predictive planning, score-based planning, observability,
  and the LeWorldModel-shaped runtime pipeline.
- Added a provider authoring guide that turns the taxonomy into capability, validation, testing,
  observability, and documentation checklists for new adapters.
- Documented GR00T live-smoke requirements for Isaac-GR00T's CUDA/TensorRT runtime and the remote
  policy-server path for unsupported hosts.

## 0.3.0 - 2026-04-08

### Added

- Typed planning goals for `object_at`, `object_near`, `spawn_object`, and `swap_objects`.
- Built-in evaluation suites for generation, physics, planning, reasoning, and transfer.
- Provider benchmark harness with latency, retry, throughput, JSON, Markdown, and CSV reporting.
- Provider observability through `ProviderEvent`, JSON logging, in-memory recording, and metrics
  aggregation sinks.
- HTTP-backed Cosmos and Runway beta adapters with typed request policy and retry behavior.
- Reusable provider contract checks under `worldforge.testing`.

### Known Limitations

- JEPA and Genie remain scaffold adapters backed by deterministic mock behavior after credential
  checks.
- Evaluation scores are deterministic adapter contract signals, not physical fidelity or media
  quality guarantees.
- World persistence is local JSON and is not safe as a concurrent multi-writer store.

# Changelog

All notable user-visible changes to WorldForge are recorded here.

This project follows the spirit of Keep a Changelog. Versioning is currently pre-1.0, so minor
releases may still include breaking changes when the public API needs to tighten.

## Unreleased

- Added an optional OpenTelemetry provider-event sink that maps sanitized provider events to
  host-owned tracing spans without adding OpenTelemetry to the base dependency set.

## 0.5.0 - 2026-04-24

### Added

- Added a MkDocs Material documentation site, strict docs-build validation, and a GitHub Pages
  workflow that deploys the site from `main`.
- Added `SECURITY.md` with the vulnerability-reporting path and supported-version policy.
- Added public governance and contributor surfaces: code of conduct, support policy, maintainer
  ownership, citation metadata, issue templates, pull request template, and CODEOWNERS.
- Added documented `examples/benchmark-inputs.json` and `examples/benchmark-budget.json` fixtures
  so README and docs benchmark commands are copy-paste runnable.
- Added explicit claim-boundary and metric-semantics fields to evaluation and benchmark JSON and
  Markdown reports.
- Added capability-protocol registration for narrow `Cost`, `Policy`, `Generator`, `Predictor`,
  `Reasoner`, `Embedder`, and `Transferer` implementations, including diagnostics, planning, and
  benchmark routing without requiring a full `BaseProvider` subclass.
- Added an engineering quality standards page that maps WorldForge's Python packaging, testing,
  linting, typed-distribution, ML reproducibility, and robotics-runtime boundaries to upstream
  Python and scientific-computing guidance.
- Exported benchmark budget and fixture-loading helpers from the top-level Python package so
  provider benchmarking workflows do not need to reach into implementation modules.

### Fixed

- Scene object mutations and prediction actions now validate history payload JSON before committing
  state changes, so malformed metadata or action payloads cannot leave an in-memory world half
  mutated.
- Provider events now sanitize observable request targets and obvious secret-bearing message or
  metadata fields before logs or in-memory sinks can record them. Signed artifact URLs keep
  scheme/host/path context but drop query strings, fragments, and userinfo.
- Cosmos and Runway now strip whitespace and treat blank environment variables as unset, matching
  the behaviour of every other provider. A blank `COSMOS_BASE_URL`, `NVIDIA_API_KEY`,
  `RUNWAYML_BASE_URL`, `RUNWAYML_API_SECRET`, or `RUNWAY_API_SECRET` no longer masks as
  configured.
- `scripts/test_package.sh` now installs the built wheel generically instead of assuming the old
  `worldforge-*.whl` filename prefix, so the package contract still works after the
  `worldforge-ai` rename.
- `scripts/test_package.sh` now validates wheel and sdist contents before installing the wheel,
  including capability protocol files, the `py.typed` marker, console scripts, and source-package
  docs/tests/scripts.
- Public JSON-carrying models now reject non-JSON-native action parameters, scene metadata,
  provider-event metadata, score metadata, policy raw actions, and policy metadata at construction
  time instead of allowing values that fail later during persistence or artifact serialization.
- `PredictionPayload`, `EvaluationResult`, provider summaries, and `BenchmarkResult` now validate
  their JSON fields, finite metrics, score ranges, counts, and result coherence at construction
  time so invalid report artifacts fail before rendering.
- World import/load validation now requires the persisted schema version, validates embedded scene
  object payloads, rejects `SceneObjectPatch` misuse, and treats a single provider string in
  `World.compare(...)` as one provider rather than a sequence of characters.
- Capability protocol adapters now wrap unexpected runtime exceptions as `ProviderError` after
  emitting failure events.
- LeWorldModel direct scoring now validates checkpoint-native candidate shape and requires one
  returned score per candidate sample before constructing `ActionScoreResult`.
- Benchmark budget fixtures now reject unknown top-level or budget-entry keys so typoed release
  thresholds fail closed.
- The LeWorldModel object-checkpoint builder now supports pinned Hugging Face revisions and loads
  downloaded weights with `torch.load(..., weights_only=True)` by default. The
  `--allow-unsafe-pickle` escape hatch is explicit for trusted legacy weights only.
- `scripts/robotics-showcase --health-only` no longer auto-builds or downloads a missing
  LeWorldModel object checkpoint; preflight reports checkpoint absence without mutating the cache.
- Production CLI and LeRobot provider checks now raise explicit WorldForge errors instead of
  relying on Python `assert` statements that disappear under optimized execution.

### Changed

- CI workflows now run on Python 3.13 only. The multi-version OS/Python test matrix was removed,
  and Pages, release, and security jobs were aligned to the same interpreter version.
- Package metadata, docs, optional-runtime wrapper commands, and lint target now declare Python
  3.13 only so the published support contract matches CI.
- Package metadata now uses SPDX license metadata and an explicit `uv` package marker, while the
  Hatch wheel target is restricted to runtime package files.
- Pytest now runs with importlib import mode and strict xfail handling, while Ruff enforces sorted
  exports, explicit mutable class metadata annotations, literal exception-match patterns, and
  clearer pytest imports/assertions.
- Ruff now also enforces comprehension, simplification, return, performance, pytest-style, and
  Ruff-native correctness rules across `src`, `tests`, `examples`, and `scripts`.
- Provider contract helpers now use explicit `AssertionError` checks instead of Python `assert`
  statements, so reusable adapter validation still runs under optimized Python.
- Dedupe repeated provider scaffolding into shared `BaseProvider._emit_operation_event` and
  `BaseProvider._health` helpers, and move `no_grad_context` plus `prepare_model` into
  `providers/_policy.py`. The cosmos, runway, leworldmodel, lerobot, gr00t, and jepa-wms adapters
  are unchanged externally but significantly shorter internally.
- Consolidate the shared `blue_cube` tabletop scenario used by the LeRobot and LeWorldModel demos
  into `worldforge.demos.make_blue_cube` / `blue_cube_goal` / `make_candidate_plans`.
- TheWorldHarness no longer eagerly imports `worldforge.demos.*` at module load; demo flow
  runners import lazily so the harness cold start does not drag the optional-runtime provider
  classes into memory.
- The robotics showcase wrapper no longer suppresses LeRobot runtime device fallback warnings, so
  CUDA-to-MPS or similar execution changes remain visible in the terminal.
- Documentation now routes release validation through explicit `uv`/`bash` gate commands, keeps
  robotics preflight commands visible from the README/CLI/examples pages, and splits long optional
  runtime commands into copy-pasteable blocks.
- The robotics showcase deep dive now includes end-to-end flow, model payload, inference
  responsibility, and sequence diagrams that show how LeRobot policy inference, LeWorldModel cost
  inference, WorldForge planning, mock replay, and the visual report fit together.
- The README, package metadata, citation metadata, docs site description, and introduction now use
  a tighter project pitch: testable world-model workflows for physical-AI systems.
- `save_world` skips a redundant `json.dumps`/`json.loads` round trip; the validation call now
  runs directly against the serialized dict.
- Documentation metadata and README links now point at the published GitHub Pages site.
- Release tags now run the full quality gate before artifacts are built or published: lint,
  formatting, strict docs, coverage, dependency audit, package contract, and tests.
- The release gate now includes the lockfile check, coverage gate, package contract, build, and
  dependency audit using the locked dev environment.
- JEPA and Genie scaffold providers now advertise no executable capabilities. Their deterministic
  mock-backed surrogate path remains available only for local adapter tests with
  `WORLDFORGE_ENABLE_SCAFFOLD_SURROGATES=1`.
- Mock no longer advertises the provider-level `plan` capability; planning remains a WorldForge
  facade workflow built from provider-specific `predict`, `score`, and `policy` surfaces.
- Release publishing now verifies that the pushed tag matches the package version, uses locked
  `pip-audit`, attaches build provenance attestations, and is configured for PyPI trusted
  publishing.

### Security

- Hardened `ProviderEvent` serialization so structured provider logs do not leak bearer tokens,
  API keys, signed URL query strings, or secret-like metadata values.
- Scaffold provider capability fail-closed behavior prevents deterministic surrogate outputs from
  being mistaken for real JEPA or Genie provider results in evals, benchmarks, or public reports.

## 0.4.0 - 2026-04-22

### Harness

- Added the M3-M5 TheWorldHarness surfaces: `ProvidersScreen` with a capability matrix and a
  cancellable real `mock.predict` run; `EvalScreen` and `BenchmarkScreen` with preserved JSON
  reports; Run Inspector report previews; Home recent worlds/runs; dynamic `Ctrl+P` entries for
  worlds, providers, and saved reports.
- Added the `worldforge-high-contrast` theme to the existing theme cycle and documented the three
  shipped themes.
- Added local harness guard scripts that reject raw hex literals in widget CSS and network-egress
  calls under `src/worldforge/harness/`.
- Added a Textual screenshot export matrix for the main harness screens at `100x30`, `120x40`,
  and `160x50`, plus a deterministic README screenshot regeneration script.
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
  flow, "Switch theme", and the stock Quit. Dynamic entries now index worlds, providers, and
  recent runs.
- Added `?` to open a modal `HelpScreen` that lists every binding declared on the screen below
  it, plus chord bindings `g h` / `g r` for jump-to-Home and jump-to-Run-Inspector.
- Updated the `Header` breadcrumb to reflect the active screen, deepening to the selected flow
  on the Run Inspector (`worldforge › run-inspector › <flow>`).
- Added a standalone Textual report for `scripts/robotics-showcase` that renders the real
  LeRobot-plus-LeWorldModel run as a pipeline trace with metric bars, candidate ranking, provider
  events, and a fixed tabletop replay.
- Improved the robotics showcase report layout into a vertical, scrollable story with full-width
  candidate ranking, full-width tabletop replay, staged reveal delays, and an illustrative animated
  robot-arm replay.
- Added an in-report reading guide for runtime, tensor, and candidate-ranking panes plus a `?`
  tabletop-replay help overlay for the real robotics showcase TUI.

### Added

- Added `lewm-real`, a short `uv run` alias for real LeWorldModel checkpoint inference. The command
  now accepts `--checkpoint`, prints a staged pipeline log by default, and preserves machine-readable
  output with `--json-only`.
- Added `lewm-lerobot-real` and `worldforge-smoke-lerobot-leworldmodel`, a host-owned real
  robotics smoke/showcase that composes LeRobot policy inference with LeWorldModel checkpoint
  scoring through WorldForge policy-plus-score planning, including visual logs and JSON output.
- Added `scripts/robotics-showcase` and `worldforge-robotics-showcase`, a one-command PushT real
  robotics entrypoint that packages the LeRobot observation, LeWorldModel score tensor, translator,
  and action-candidate bridge defaults for the LeRobot + LeWorldModel showcase.
- Expanded the real robotics showcase output with an ASCII pipeline map, runtime bars, score
  summary, candidate target table, and tabletop replay diagram while keeping the machine-readable
  JSON path available.
- Made `scripts/robotics-showcase` launch the Textual visual report by default while preserving
  `--no-tui`, `--json-only`, and `--health-only` for plain terminal, automation, and preflight
  runs.
- Added `--tui-stage-delay` and `--no-tui-animation` to control the robotics showcase reveal pace
  and animation.
- Added the `worldforge world` CLI command group for local JSON persistence workflows, including
  create, list, show, history, export, import, and fork commands backed by the existing validated
  `WorldForge` persistence API.
- Added persisted-world mutation and prediction commands:
  `worldforge world objects`, `add-object`, `update-object`, `remove-object`, and `predict`.
  These commands load local JSON worlds, apply typed scene/action values, and save through
  `WorldForge.save_world(...)`; `world predict --dry-run` previews provider output without
  replacing the saved file.
- Added `WorldForge.delete_world(...)` and `worldforge world delete` so local JSON world removal
  uses the same validated persistence boundary as save/load/import/fork. TheWorldHarness now calls
  this public API instead of unlinking world files directly.
- Added persisted history entries for scene object add/update/remove mutations, including typed
  `Action` payloads and snapshots that can be restored or forked. Object position patches now
  translate bounding boxes with the pose to keep local scene state coherent.
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
- Added benchmark input fixtures. `worldforge benchmark --input-file benchmark-inputs.json` now
  loads deterministic JSON inputs for prediction, generation, transfer, embedding, score, and
  policy runs; transfer clips can point at files relative to the input JSON or inline base64
  frames.
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

- Bumped project metadata and public citation references to `0.4.0`.
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
- Updated package metadata around WorldForge's physical-AI world-model integration layer, removed
  the development-status classifier, and pointed documentation metadata at repository docs instead
  of a standalone project domain.
- Aligned documented Ruff commands with CI, `README.md`, and `AGENTS.md` by keeping `scripts/` in
  both `ruff check` and `ruff format` targets.

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
- Rejected score-based plans when the score provider returns a different number of scores than
  executable candidate action plans, preventing provider-native score tensors from drifting away
  from the actions WorldForge can execute or report.

### Security

- Hardened local JSON persistence against path traversal by validating world IDs before resolving
  storage paths.
- Raised the development dependency floor to `pytest>=9.0.3` and refreshed `uv.lock` to remove
  the locked `pytest 9.0.2` vulnerability reported as `CVE-2025-71176`.

### Documentation

- Added `AGENTS.md` with repository identity, architecture, commands, conventions, constraints,
  and gotchas for contributors.
- Promoted the real LeRobot-plus-LeWorldModel robotics showcase to the top of the README with
  screenshots, a one-command entrypoint, and a dedicated walkthrough covering the pipeline,
  runtime boundaries, artifacts, and customization path.
- Added a dedicated CLI reference and reduced duplicate README/provider demo prose so the public
  front face points to one command map instead of repeating optional-runtime narratives.
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

### Notes

Constraints carried forward from this release; see the docs site for the current status of each:

- JEPA and Genie remain scaffold adapters backed by deterministic mock behavior after credential
  checks.
- Evaluation scores are deterministic adapter contract signals, not physical fidelity or media
  quality guarantees.
- World persistence is local JSON and is not safe as a concurrent multi-writer store.

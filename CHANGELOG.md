# Changelog

All notable user-visible changes to WorldForge are recorded here.

This project follows the spirit of Keep a Changelog. Versioning is currently pre-1.0, so minor
releases may still include breaking changes when the public API needs to tighten.

## Unreleased

### Added

- Added `.env.example` documenting every provider environment variable recognized by
  WorldForge (`COSMOS_BASE_URL`, `NVIDIA_API_KEY`, `RUNWAYML_API_SECRET` and the legacy
  `RUNWAY_API_SECRET` alias, `RUNWAYML_BASE_URL`, `LEWORLDMODEL_POLICY` and the legacy
  `LEWM_POLICY` alias, `LEWORLDMODEL_CACHE_DIR`, `LEWORLDMODEL_DEVICE`, the full
  `GROOT_POLICY_*` and `GROOT_EMBODIMENT_TAG` set, the full `LEROBOT_*` set including the
  legacy `LEROBOT_POLICY` alias, the `JEPA_WMS_*` candidate variables, and the scaffold
  `JEPA_MODEL_PATH` and `GENIE_API_KEY`). Each variable is annotated with whether it is
  required for auto-registration or strictly optional, closing the gap between the README's
  `cp .env.example .env` onboarding step and the repository contents.

### Fixed

- Tracked `.env.example` in the repository by adding an explicit `!.env.example` exception
  to `.gitignore`; the general `.env.*` glob was silently excluding the onboarding template.
- Aligned `make lint` and `make format` with CI, `README.md`, and `AGENTS.md` by adding
  `scripts/` to the `ruff check` and `ruff format` invocations and to the `clean` sweep.
  The previous Makefile skipped scripts, so local `make lint` could pass while CI failed on
  changes under `scripts/`.

- Added `lerobot` as a first-class optional policy provider for Hugging Face LeRobot
  pretrained policies (ACT, Diffusion, TDMPC, VQBet, Pi0, Pi0Fast, SAC, SmolVLA). The
  adapter lazily imports `lerobot.policies.pretrained.PreTrainedPolicy`, supports injectable
  policies and policy loaders for offline testing, validates observation payloads, preserves
  raw policy tensors, and requires a host-owned action translator before returning executable
  WorldForge actions. Ships with policy-only and policy+score planning support,
  auto-registration when `LEROBOT_POLICY_PATH` (or `LEROBOT_POLICY`) is set, contract tests,
  a full end-to-end demo at `examples/lerobot_e2e_demo.py`, and a real-checkpoint live smoke
  script at `scripts/smoke_lerobot_policy.py`.
- Added `leworldmodel` as a first-class optional provider for LeWorldModel JEPA cost models,
  including the `score` capability, `ActionScoreResult`, `WorldForge.score_actions(...)`, typed
  input validation, score-output validation, provider profile metadata, and fixture-driven tests.
- Added score-based planning support so `World.plan(...)` can select candidate action plans from
  `ActionScoreResult.best_index`, plus a real-checkpoint LeWorldModel smoke script.
- Added `scripts/scaffold_provider.py` to generate safe provider adapter scaffolds, fixture
  placeholders, generated scaffold tests, and provider docs stubs from planned capabilities.
- Added a `jepa-wms` provider candidate scaffold with fake-runtime and host-owned torch-hub score
  contract tests, parser fixtures, `World.plan(...)` coverage, event assertions, and docs for
  future `facebookresearch/jepa-wms` integration without exporting or auto-registering it as a
  working provider.
- Added a `policy` capability, `ActionPolicyResult`, `WorldForge.select_actions(...)`, and an
  experimental host-owned `gr00t` provider for NVIDIA Isaac GR00T PolicyClient action selection,
  including policy-only and policy+score planning support.
- Added `scripts/smoke_gr00t_policy.py` for host-owned GR00T PolicyClient live smoke testing
  against an existing server or an Isaac-GR00T checkout.
- Added `examples/leworldmodel_e2e_demo.py`, a checkout-safe end-to-end provider-surface demo that
  uses the real `LeWorldModelProvider` with an injected deterministic cost runtime to show
  scoring, planning, execution, persistence, and reload without running upstream checkpoint
  inference.
- Documented the real-checkpoint LeWorldModel smoke setup and made
  `scripts/smoke_leworldmodel.py` executable with the upstream `~/.stable-wm` default.

### Security

- Raised the development dependency floor to `pytest>=9.0.3` and refreshed `uv.lock` to remove
  the locked `pytest 9.0.2` vulnerability reported as `CVE-2025-71176`.

### Fixed

- Rejected non-finite public numeric inputs for positions, rotations, request policies, provider
  events, video clips, reasoning confidence, embedding vectors, generation FPS, and prediction
  payload metrics.
- Rejected duplicate scene object IDs when adding objects to a world.
- Rejected persisted/provider-supplied world state whose scene-object map key disagrees with the
  object's embedded `id`.
- Validated Runway ratio parsing before constructing returned clip metadata.
- Validated Cosmos health and generation response payloads before decoding returned videos.
- Validated Runway organization, task creation, task polling, task output, artifact content type,
  expired artifact, and empty artifact responses before returning clips.

### Documentation

- Added `AGENTS.md` with repository identity, architecture, commands, conventions, constraints,
  and gotchas for AI-assisted and first-time contributors.
- Added this changelog and linked it from the README.
- Documented the Provider Hardening RC persistence decision, provider limits, and provider
  workflow failure modes.
- Added a world-model taxonomy and vision document, plus expanded architecture docs with text and
  Mermaid diagrams for provider injection, predictive planning, score-based planning, observability,
  and the LeWorldModel-shaped runtime pipeline.
- Added a provider authoring guide that turns the taxonomy into capability, validation, testing,
  observability, and documentation checklists for new adapters.
- Documented the current GR00T live-smoke status: local macOS arm64 validation reaches upstream
  dependency resolution but cannot run Isaac-GR00T's CUDA/TensorRT runtime without a compatible
  NVIDIA/Linux host or remote policy server.

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

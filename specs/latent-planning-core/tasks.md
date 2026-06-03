# Tasks: Latent Planning Core

Tracks `plan.md`. `[x]` done, `[ ]` pending.

## Stage 1 — Remove isolated authoring surface

- [x] Delete scenario DSL modules (`scenarios`, `scenario_models`, `scenario_matrix`,
      `scenario_expectations`, `scenario_rendering`) and `cli_scenario`.
- [x] Delete `world_diff`, `world_migration_preview`, `world_migration_preview_reporting`.
- [x] Delete `persistence_preflight` + its 4 helper modules.
- [x] Remove the `scenario` command and `world diff|migration-preview|preflight` subcommands.
- [x] Trim public exports in `__init__.py`; regenerate `tests/fixtures/public_api/exports.json`.
- [x] Delete the matching tests; update CLI-help and docs-site contract tests.
- [x] Remove docs pages (`scenarios`, `world-diff`) + nav entries; fix inbound links + snippet gate.
- [x] Keep `examples/scenarios/*.json` as inert evaluation dataset fixtures.
- [x] Gate green: lint, format, provider-docs, tests.

## Stage 2 — Elevate the backbone loop (docs + example)

- [x] Add `examples/latent_mpc_planning.py` (runnable, checkout-safe latent MPC over a score oracle).
- [x] Reframe README (pitch, what-it-does, first run, quickstart, overview, highlights).
- [x] Reframe CLAUDE.md `<identity>` and priority rules.
- [x] Reframe AGENTS.md project identity.
- [x] Add this spec triad.
- [x] Add a CHANGELOG entry for the pivot.
- [ ] Add `examples/latent_mpc_planning.py` to `EXAMPLE_COMMANDS` and the examples indexes.
- [ ] Enrich `docs/src/control-planning.md`, `index.md`, `introduction.md`, `architecture.md`,
      `quickstart.md` around the backbone loop (+ zh mirrors).
- [ ] Remove the now-dead `world preflight` references from `playbooks.md` (+ the issue-182 test).

## Stage 3 — Remove the symbolic World runtime (next)

- [ ] Re-center `evaluation/` on the capability/latent loop; drop symbolic suites + `suite_fixtures`.
- [ ] Re-center `benchmark.py`; drop `_seed_world`.
- [ ] Rewrite/remove world-based demos; update `pyproject.toml` `[project.scripts]`.
- [ ] Delete `_world*`, `_state`, `_results`, `framework_world_store`, `structured_goals`,
      `cli_world`, the `world` CLI, and `WorldForge.*_world` methods.
- [ ] Trim `scene_models` to action/geometry vocabulary; drop matching exports.
- [ ] Update tests/docs/snapshots; keep the coverage floor.
- [ ] (Interim) Add a deprecation signpost on `World`/`create_world`/the `world` CLI.

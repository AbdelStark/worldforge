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

## Stage 3 — Remove the symbolic World runtime (in progress)

The `World` deletion is an all-or-nothing red→green transition across ~30 source + ~20 test + ~25
doc files (mapped exhaustively). To keep every checkpoint green, **decouple usage first** (each
increment is green because `forge.predict`/`forge.score_actions` work without a `World`), then delete
`World` last.

### Inc A — mock `score` capability (DONE)

- [x] Add deterministic `score_actions` to the mock provider (cost oracle, `lower_is_better`).
- [x] Add `sample_contract_score_*` testing helpers; default them in `assert_provider_contract`;
      wire the workbench score conformance. Update capability/negotiation/benchmark/workbench tests.
- Makes the latent loop and score-only workflows checkout-safe on the default provider.

### Inc B — re-center `evaluation/` on the capability loop (DONE)

- [x] Deleted `evaluation/suite_fixtures.py`.
- [x] `EvaluationContext.world` removed (breaking for custom evaluators) — keep `forge`.
- [x] `suite_base.py` drops `_build_world`/`_ensure_world`/`world` thread; default scenario calls
      `forge.predict(seed_dict, ...)`. `run_report`/`run_report_artifacts` keep an ignored `world`
      kwarg so the still-present `World.evaluate()` keeps working until Inc F.
- [x] `physics_suite.py` → `forge.predict` determinism/response (suite_id `physics`, names kept).
- [x] `planning_suite.py` → `LatentMPCController` over `forge.score_actions` (suite_id `planning`,
      requires `score`, satisfied by mock; names kept).
- [x] `examples/custom_evaluation_suite.py` probes `context.forge.predict`. Tests + `evaluation.md`
      updated. Gates green, coverage 90.88%.

### Inc C — re-center `benchmark.py` (DONE)

- [x] Replaced `_seed_world`/`world.predict` with `_benchmark_world_state()` (plain dict) +
      `forge.predict(...)`. The embed/score/policy ops already called `forge` directly. Gates green,
      coverage 90.88%.

### Inc D — rewrite the world-based demos onto `LatentMPCController`/forge calls (DONE)

- [x] `demos/__init__.py`, `leworldmodel_e2e`, `lerobot_e2e`, `policy_score_candidate_lab`,
      `dimos_go2_replay_arena`, `rerun_showcase`, `so101_replay_trace`,
      `embodied_policy_replay_comparison`. The 4 `worldforge-demo-*` pyproject scripts survive
      (keep `main()`). Each demo now drives `forge.predict`/`forge.score_actions`/
      `forge.select_actions`/`LatentMPCController` directly; output shapes are capability-centric
      (selected action, candidate scores, `best_index`, provider, metadata) with world-persistence
      fields dropped. `make_blue_cube()` returns a standalone `SceneObject`.
- [x] Updated demo tests + the harness flow renderer/tests + `scripts/demo_showcases.py` +
      `examples/hosts/robotics-operator/app.py`. `EXAMPLE_COMMANDS` names/commands unchanged.
      Gates green; coverage 90.96%.

### Inc E — reroute provider-test scaffolding off `World` (DONE)

- [x] Rerouted ~14 provider/integration test files from `create_world`+`world.predict`/`world.plan`
      scaffolding to `forge.predict`/`forge.score_actions`/`forge.select_actions`/`LatentMPCController`.
      Gates green, coverage 90.93%.
- Finding: `World.plan` *composition* (policy+score planning, `workflow_trace`,
      `success_probability`, the goal-resolution validation messages) has **no forge-level
      equivalent** — it lives in `_world_planning.py`. The tests that assert it
      (`test_latent_mpc_controller` World.plan bridge, `test_capability_dual_routing` planning
      composition, and the World-planning parts of `test_evaluation_and_planning`,
      `test_helper_validations`, `test_gr00t_provider`, `test_lerobot_provider`) are removed/trimmed
      together with `World` in Inc F. Inc F must restore equivalent coverage via the
      `LatentMPCController` path or accept the suite shrinking (watch the 90% floor).

### Inc F — delete the World runtime (final sweep)

- [ ] Delete `_world.py`, `_world_goal_resolution.py`, `_world_planning.py`,
      `_world_prompt_seeders.py`, `_state.py`, `_results.py`, `framework_world_store.py`,
      `structured_goals.py`, `cli_world.py`, `cli_args/world.py`.
- [ ] Trim `framework.py` (drop `*_world` methods, `state_dir` if unused, `world_count` from doctor),
      `framework_doctor.py`, `provider_diagnostics.py` (`DoctorReport.world_count` — breaking),
      `cli.py` (`world` command + reroute `_cmd_predict` to `forge.predict`), `models.py`,
      `scene_models.py` (drop `SceneObject`/`SceneObjectPatch`/`HistoryEntry`; keep
      `Action`/`Position`/`Pose`/`BBox`/`Rotation`), `providers/mock.py` (decouple `predict` from
      `SceneObject`), `__init__.py` exports.
- [ ] Delete `test_world_lifecycle.py`, `test_cli_world_commands.py`; reroute remaining tests.
- [ ] Regenerate the public-API snapshot and CLI help snapshots; rewrite world-referencing docs
      (quickstart, cli, operations, playbooks, architecture, api/python, …) + zh mirrors; CHANGELOG.

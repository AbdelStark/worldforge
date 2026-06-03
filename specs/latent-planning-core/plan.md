# Plan: Latent Planning Core

Implements `spec.md`. The pivot is staged so every checkpoint leaves the repository green
(lint, format, provider-docs, tests, coverage, package).

## Target Architecture

```
observation
   │
   ├─ policy provider  ──▶ candidate actions            (capability: policy)
   │
   ▼
LatentMPCController (caller-owned CEM / receding horizon)
   │   sample → encode → score → keep elites → refit → execute first action → replan
   ▼
   ├─ predict provider ──▶ latent rollouts              (capability: predict)
   └─ score provider   ──▶ candidate costs (oracle)     (capability: score)
   │
   ▼
evaluation + benchmarking ──▶ pick provider / horizon / cost configuration
```

Modules that stay: capability contracts (`models`, `provider_profiles`, `capability_results`,
`capabilities/`, `capability_negotiation`), providers (`providers/`), latent control (`control/`,
`action_candidates`, `_planning`, `workflow_trace`), evaluation, benchmark, diagnostics, harness,
reporting, optional Rerun, testing helpers, CLI.

## Staging

### Stage 1 — Remove the isolated authoring surface (DONE)

Deleted the scenario DSL (`scenarios`, `scenario_models`, `scenario_matrix`,
`scenario_expectations`, `scenario_rendering`), world diff (`world_diff`), world migration
(`world_migration_preview`, `world_migration_preview_reporting`), persistence preflight
(`persistence_preflight*`), and `cli_scenario`. Removed the `scenario` command and the
`world diff|migration-preview|preflight` subcommands, the matching public exports, tests, docs
pages, nav entries, and doc-snippet wiring. Kept `examples/scenarios/*.json` as inert evaluation
dataset fixtures only.

### Stage 2 — Elevate the backbone loop (DONE for docs/example; ongoing in code)

- `examples/latent_mpc_planning.py`: runnable, checkout-safe latent MPC loop over an in-example
  score oracle.
- README, CLAUDE.md, AGENTS.md, and core docs reframed around the backbone loop.

### Stage 3 — Remove the symbolic World runtime (PLANNED, next)

The mutable `World` runtime and its JSON persistence are the remaining world-authoring surface. They
are still referenced by the symbolic evaluation suites, benchmark world-seeding, and several demos,
so removal must move together with a re-centering on the capability loop:

1. Re-center `evaluation/` on the capability loop: replace `PlanningEvaluationSuite` /
   `PhysicsEvaluationSuite` / `suite_fixtures` (symbolic `World.plan`) with latent-loop evaluation
   (cost-to-goal reduction by `LatentMPCController`, score/predict latency and determinism).
2. Re-center `benchmark.py`: drop `_seed_world`; benchmark the capability operations directly.
3. Remove or rewrite the world-based demos (`leworldmodel_e2e`, `lerobot_e2e`,
   `policy_score_candidate_lab`, `dimos_go2_replay_arena`, `rerun_showcase`, `so101_replay_trace`)
   onto `LatentMPCController`; update `pyproject.toml` `[project.scripts]` accordingly.
4. Delete `_world*`, `_state`, `_results`, `framework_world_store`, `structured_goals`, and the
   `WorldForge.*_world` methods + `cli_world` + `world` CLI; trim `scene_models` to the action/
   geometry vocabulary; drop the matching exports.
5. Update tests, docs, snapshots, and the coverage floor along the way.

Until Stage 3 lands, `World`/`create_world`/the `world` CLI remain as a documented local-state
convenience and carry a deprecation signpost pointing to the latent loop.

## Constraints

- Keep components small and modular; no monolithic files.
- Never add heavy optional runtimes to base dependencies.
- Public contribution artifacts stay human, maintainer-style, and tool-neutral.

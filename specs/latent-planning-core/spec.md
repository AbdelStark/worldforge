# Spec: Latent Planning Core

## Summary

Narrow WorldForge to a single backbone loop and reposition it as a **harness framework for building
world-model-based workflows for physical AI**. WorldForge is the application builder's counterpart
to model-training stacks like Stable World Model: it helps roboticists and physical-AI builders
*compose, evaluate, and benchmark* workflows built on top of world models — so they can select the
best provider and configuration for a task — rather than *train* the models themselves.

## Problem

The previous scope ("testable world-model workflows for physical-AI systems") had grown a large
symbolic-world surface — world authoring/persistence, a scenario DSL, world diff/migration, and
toy-world planning — that is orthogonal to the loop physical-AI builders actually run. That surface
diluted the product, raised maintenance cost, and obscured the one capability that matters: planning
and scoring with an action-conditioned predictive world model.

## Backbone Loop (the only first-class workflow)

Plan and score action candidates with an action-conditioned predictive world model, in latent space:

1. **Propose** — a `policy` provider proposes candidate actions from an observation (optional
   warm-start).
2. **Predict** — a `predict` provider rolls candidates out as forward dynamics (optional).
3. **Score** — a `score` provider ranks candidates as a cost oracle (latent distance to goal, etc.).
4. **Optimize** — `LatentMPCController` owns a caller-side CEM/MPPI optimizer: sample, keep elites,
   refit, execute the first action, replan under a receding horizon.
5. **Select** — evaluation and benchmarking compare providers/horizons/costs so a builder can pick
   the winning configuration.

The world model is a **dynamics/cost oracle, not a controller**. The controller stays a pure
optimizer; providers stay pure oracles.

## In Scope

- Capability contracts: `predict`, `score`, `policy`, `embed`, `plan` (strict, fail-closed).
- Provider adapters (mock, LeWorldModel, LeRobot, GR00T, Cosmos-Policy, scaffolds) and the HTTP/
  remote/embodiment stack.
- Latent planning/control (`control/`, `action_candidates`, `_planning`, `workflow_trace`).
- Evaluation and benchmarking centered on the capability loop, for configuration selection.
- Diagnostics (`doctor`), provider events, run workspaces, reports, optional Rerun, testing helpers.
- Local JSON state as a *convenience* for runs — not a product surface (see `plan.md` for staging).

## Out of Scope (removed or being removed)

- World generation / media generation.
- Symbolic-scenario DSL, scenario matrices, scenario galleries.
- World diff/patch and world migration previews.
- Local-state preflight as a product feature.
- Symbolic toy-world authoring as the headline planning story.

## Non-Goals

Training world models; a hosted service; a model-API abstraction; durable multi-writer persistence;
robot safety certification; physical-fidelity claims from deterministic suites or the mock provider.

## Success Criteria

- README, docs, and agent context describe the backbone loop as the product.
- A runnable, checkout-safe latent MPC example exists (`examples/latent_mpc_planning.py`).
- The scenario DSL, world diff, world migration, and persistence-preflight surfaces are removed.
- All repository gates stay green (lint, format, provider-docs, tests, coverage, package).

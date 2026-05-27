# Roboto (Atom01) showcase — LeWorldModel-planned humanoid control

## Status
Draft · 2026-05-25 · originating spike [#321](https://github.com/AbdelStark/worldforge/issues/321)

## Outcome (one sentence)
Stand up a host-owned, sim-first WorldForge showcase that drives RoboParty's open-source Atom01 humanoid (`Roboparty/roboto_origin`, `Roboparty/atom01_train`) by composing a `roboto` **policy** that proposes action candidates with a **fine-tuned LeWorldModel** `Cost` that ranks them through `World.plan(... planning_mode="policy+score")` — backed by an end-to-end dataset → training → checkpoint → evaluation pipeline whose heavy runtimes (torch, IsaacLab/IsaacSim, ROS2, RSL_RL, `stable-worldmodel`, checkpoints, datasets) stay entirely out of base dependencies and `src/worldforge/` imports.

## Why this work
WorldForge already ships one end-to-end `policy+score` robotics showcase (PushT: LeRobot diffusion policy proposes candidates, LeWorldModel scores them — see [scripts/robotics-showcase](../../scripts/robotics-showcase), [src/worldforge/smoke/lerobot_leworldmodel.py](../../src/worldforge/smoke/lerobot_leworldmodel.py)). That showcase is tabletop 2D manipulation with a vendor-trained world model checkpoint (`quentinll/lewm-pusht`). It demonstrates the *integration shape* but not the *full lifecycle*: nobody in this repo has collected data, engineered a dataset, trained or fine-tuned a world model, and closed the loop on a new embodiment.

Atom01 is a fully open-source DIY humanoid (ROS2 Humble deploy, IsaacLab/IsaacSim + RSL_RL training, MuJoCo Sim2Sim, USB2CAN motors + IMU). It is a credible, permissively-trainable (BSD-3 `atom01_train`) target for exercising the **entire** world-model lifecycle on a legged embodiment, and a compelling public demo. The spike ([#321](https://github.com/AbdelStark/worldforge/issues/321)) established feasibility questions; this triad turns them into a phased, research-gated implementation plan.

## Background (grounded)
- **Existing planning composition.** `World.plan(...)` in [src/worldforge/framework.py](../../src/worldforge/framework.py) supports `planning_mode ∈ {policy+score, policy, score, predict}`. In `policy+score`, a `policy` returns `ActionPolicyResult.action_candidates`; a `score` (`Cost`) returns `ActionScoreResult` (lower cost = better, `best_index = argmin`); the planner picks `candidate_action_plans[best_index]`.
- **LeWorldModel provider.** [src/worldforge/providers/leworldmodel.py](../../src/worldforge/providers/leworldmodel.py) implements `score` via `stable_worldmodel.policy.AutoCostModel.get_cost`. Registration is env-gated on `LEWORLDMODEL_POLICY` / `LEWM_POLICY`; runtime (`torch`, `stable_worldmodel`) is lazily imported only at call/health time.
- **Checkpoint builder.** [src/worldforge/smoke/leworldmodel_checkpoint.py](../../src/worldforge/smoke/leworldmodel_checkpoint.py) downloads `config.json` + `weights.pt` from a **pinned 40-char HF revision**, validates every Hydra `_target_` against `LEWORLDMODEL_HF_ALLOWED_CONFIG_TARGETS` (currently the PushT ViT-tiny shape: `size="tiny"`, `patch_size=14`, `image_size=224`), instantiates `stable_worldmodel.wm.lewm.LeWM`, loads weights `strict=False`, and saves the object checkpoint to `$STABLEWM_HOME/<policy>_object.ckpt`. An Atom01 world model must either fit this allow-list or extend it.
- **Policy providers.** `lerobot` ([providers/lerobot.py](../../src/worldforge/providers/lerobot.py)) and `gr00t` ([providers/gr00t.py](../../src/worldforge/providers/gr00t.py)) both implement `policy`; both require a host-supplied `action_translator`. `gr00t` is the precedent for a **client/server ZMQ bridge** across a Python-version boundary (the upstream package is pinned to an older Python; WorldForge runs 3.13).
- **LeWM internals (per upstream README + arXiv 2603.19312, to be re-verified in P0).** JEPA from **raw pixels**: ViT encoder → AR predictor → action encoder, ~15M params, two-loss objective (next-embedding prediction + Gaussian latent regularizer), single-GPU training in hours. Built on `stable-worldmodel` (Gymnasium envs, planners CEM/MPPI/Gradient-Descent/Random, MIT) and `stable-pretraining`. Hydra configs (`config/train/`), `python train.py data=<name>`, WandB tracking, HDF5 datasets under `$STABLEWM_HOME` (default `~/.stable-wm/`).
- **Upstream Atom01 (per repo READMEs).** `atom01_train` (BSD-3): IsaacSim 5.1.0 / IsaacLab 2.3.2 / RSL_RL 3.3.0, Python 3.11, `train.py` / `play.py` / `sim2sim_atom01.py` / `dataset_retarget.py`, supports standard RL + AMP + BeyondMimic. `roboto_origin` (GPL-3.0): ROS2 Humble deploy, USB2CAN, IMU, OrangePi, Python 3.10.

## The central technical problem (must be resolved in P0)
LeWM as published consumes **pixels** (a ViT-224 encoder). Atom01's RL control loop is **proprioceptive** (joint positions/velocities, IMU, base velocity, gait/command vector). There is no free lunch:

- **Option A — render to pixels.** Render RGB camera frames during sim rollouts and train/fine-tune LeWM on those, keeping the published architecture and the existing checkpoint-builder allow-list (mostly) intact. Most faithful to "fine-tuned LeWorldModel"; cost is a rendering pipeline + a large visual+embodiment domain gap from PushT.
- **Option B — vector-observation world model.** Adapt the LeWM recipe (same two-loss JEPA objective) to a proprioceptive encoder (MLP/transformer over state vectors). Truer to how Atom01 is actually controlled and cheaper to roll out, but it is an **architecture change**, not a fine-tune, and breaks the current checkpoint-builder allow-list (needs new `_target_`s and validation).

This spec is written **Option-A-first** (preserve the LeWM pixel architecture; warm-start where a compatible pretrained 3D-control checkpoint exists) with Option B as a documented fallback, because Option A maximizes reuse of the existing `leworldmodel` provider and checkpoint builder. P0 must pick one with evidence before P1 data collection begins.

## In scope
- A **sim-first** showcase: `scripts/roboto-showcase` wrapper + a `src/worldforge/smoke/` entry point that runs the planning loop against IsaacLab/IsaacSim or MuJoCo Sim2Sim and emits JSON + a run-manifest, mirroring [src/worldforge/smoke/robotics_showcase.py](../../src/worldforge/smoke/robotics_showcase.py).
- A **`roboto` policy adapter** (`policy` capability only) that yields action candidates from the trained Atom01 RL policy, bridged over a client/server boundary if the Python version forces it (gr00t precedent). Host-supplied `action_translator` maps raw policy tensors → WorldForge `Action`s.
- An **end-to-end world-model pipeline**, all host/GPU-owned and invoked via `uv run --with`:
  1. **Data collection** — roll out the trained (and perturbed) Atom01 policy in sim, capturing observations + actions + goal/cost signal.
  2. **Dataset engineering** — pack rollouts into the `stable-worldmodel` HDF5 format under `$STABLEWM_HOME`, with train/val/test splits, action normalization, and a versioned dataset card pinned by content hash (stored off-repo, never committed).
  3. **Training / fine-tuning** — train the LeWM world model (warm-start from a compatible checkpoint where available) via the upstream Hydra/WandB flow; produce `<name>_object.ckpt` + `<name>_weight.ckpt`.
  4. **Checkpoint packaging** — publish to a pinned HF revision and build the object checkpoint through an Atom01-aware extension of [leworldmodel_checkpoint.py](../../src/worldforge/smoke/leworldmodel_checkpoint.py) (allow-list / ViT-config widened, audited).
  5. **Evaluation** — world-model fidelity (latent prediction error, probes) **and** downstream planning lift (does `policy+score` MPC beat policy-only on a task metric?), with cost calibration.
- Provider wiring so `leworldmodel` (extended) loads the Atom01 checkpoint and `roboto` feeds candidates into `World.plan(... planning_mode="policy+score")` (or a `score`/MPC mode if P0 finds that fits locomotion better).
- Optional **Rerun / TensorBoard** visuals reusing existing bridges, kept out of base deps.
- An **optional CI workflow** for sim inference only (training never runs in CI), modeled on [.github/workflows/robotics-showcase.yml](../../.github/workflows/robotics-showcase.yml), with a recorded-rollout or MuJoCo fallback since IsaacSim is not installable on stock CI runners.
- Docs: a provider page for `roboto`, a playbook section for the data/training/eval pipeline, `<provider_contracts>` and CHANGELOG updates.

## Out of scope (explicit)
- **Real hardware control.** Driving USB2CAN motors / ROS2 deploy on a physical Atom01 is deferred to a **gated** phase (P7) and is not built by this spec. No robot safety layer is added to WorldForge (CLAUDE.md priority rule 4).
- Adding torch, IsaacLab, IsaacSim, ROS2, RSL_RL, `lewm`/`stable-worldmodel`/`stable-pretraining`, robot controllers, checkpoints, or datasets to base dependencies, `src/worldforge/` imports, or the repository tree.
- Training in CI, or uploading checkpoint/dataset artifacts from default CI (`actions/cache` is the reuse mechanism, per the existing robotics workflow).
- Re-implementing LeWM or RSL_RL inside WorldForge. Upstream code stays upstream; WorldForge integrates it.
- New capability *surfaces*. `roboto` advertises only `policy`; the world model uses the existing `score` capability. No new protocol is added.
- Changing the meaning of `World.plan`, `ActionScoreResult`, `ActionPolicyResult`, or persistence.

## Target architecture

```text
  ┌─ host / GPU (never base deps, never CI training) ───────────────────────────┐
  │                                                                             │
  │  atom01_train (BSD-3)            data collection            dataset (HDF5)   │
  │  IsaacLab/IsaacSim + RSL_RL  ─►  roll out policy (+noise) ─► $STABLEWM_HOME  │
  │  MuJoCo Sim2Sim                  render obs / log actions     train/val/test │
  │                                                                  │           │
  │                                                                  ▼           │
  │  LeWM (stable-worldmodel + stable-pretraining)            train / fine-tune  │
  │  Hydra config · WandB · single-GPU                       <name>_object.ckpt  │
  │                                                                  │           │
  │  publish to pinned HF revision  ◄────────────────────────────────┘           │
  └─────────────────────────────────────────────────────────────────│──────────┘
                                                                      ▼
  ┌─ WorldForge (Python 3.13, pure base; runtimes via `uv run --with`) ─────────┐
  │  leworldmodel_checkpoint.py (Atom01-aware) ─► AutoCostModel object ckpt      │
  │  providers/leworldmodel.py  (score)  ◄──┐                                    │
  │  providers/roboto.py        (policy) ───┤   World.plan(policy+score)         │
  │      └─ ZMQ client ─► host policy server │   → ranks candidates by cost      │
  │  smoke/roboto_showcase.py  + scripts/roboto-showcase  ─► JSON + run-manifest │
  │      └─ optional Rerun / TensorBoard                                         │
  └─────────────────────────────────────────────────────────────────────────────┘
```

### Dataset engineering (detail)
- **Sources.** On-policy rollouts of the trained Atom01 RL policy plus **action-perturbed / exploratory** rollouts (Gaussian action noise, command randomization, terrain/dynamics randomization). A world model needs action diversity to learn dynamics — pure expert-only data under-covers the transition space and risks a degenerate cost surface.
- **Observation modality.** Per P0 decision: Option A renders RGB to the LeWM input resolution (e.g. 224×224, ego- and/or third-person camera), control-rate aligned; Option B logs normalized proprioceptive state vectors.
- **Action representation.** Decide between full actuated-joint targets (high-DoF, harder to score) and a reduced locomotion command space (e.g. `vx, vy, ωz`, gait). Reduced command space is preferred for tractable MPC candidate scoring; record the `action_translator` contract that maps it to/from policy tensors. Verify the candidate tensor rank the planner expects (PushT used `[batch, candidates, horizon, action_dim]`).
- **Goal / cost signal.** LeWM cost is goal-relative in latent space. Define goal conditioning for locomotion (target velocity / target pose, rendered as goal image for Option A or goal vector for Option B) and store it per episode.
- **Packaging.** `stable-worldmodel` HDF5 under `$STABLEWM_HOME`: per-episode groups, observation dataset (`uint8` NHWC for pixels / `float32` for vectors), action dataset (`float32`), terminals, and goal/metadata; `<name>_train.h5` / `<name>_val.h5` (P0 to confirm exact upstream schema keys).
- **Splits & balance.** Episode-level train/val/test with held-out commands/terrains for generalization; documented expert/exploratory mix ratio.
- **Versioning.** Dataset card + content hash; stored off-repo (HF dataset or object store), pinned by revision like the checkpoint SHA. Never committed.

### MLOps / training pipeline (detail)
- **Environment.** Reproducible via `uv run --with` (torch, `stable-worldmodel`, `stable-pretraining`, hydra-core, omegaconf, transformers, datasets, h5py, wandb; IsaacSim/IsaacLab/ROS2 host-installed, never pip/uv-resolvable in base). IsaacSim is multi-GB and GPU-bound — host-owned only.
- **Training.** Upstream Hydra flow (`train.py data=atom01`) with WandB tracking. Warm-start from a compatible pretrained LeWM checkpoint as an ablation arm; from-scratch (LeWM recipe) as the baseline. Capture config, seed, dataset revision, and code SHA in the run record.
- **Checkpoint packaging.** Publish `config.json` + `weights.pt` to a pinned HF revision; extend the audited allow-list in [leworldmodel_checkpoint.py](../../src/worldforge/smoke/leworldmodel_checkpoint.py) (and the ViT/encoder config validator) to accept the Atom01 config without weakening the "exact, narrow" `_target_` guarantee. Output object ckpt at `$STABLEWM_HOME/atom01/<name>_object.ckpt`.
- **Evaluation.** Two layers: (1) world-model fidelity — latent next-step prediction error, linear probes for known state variables; (2) downstream planning lift — task success / tracking error for `policy+score` MPC vs policy-only, plus **cost calibration** (does lower predicted cost correlate with better realized outcome?). Surface as a deterministic evaluation/benchmark report where possible.
- **Promotion gate.** The `roboto`+`leworldmodel` showcase advertises real capability only when the checkpoint loads, the planning loop runs end-to-end in sim, and evaluation shows non-trivial, calibrated cost — otherwise it stays a documented scaffold.

## Acceptance criteria
- [ ] P0 decision record committed under `specs/roboto-showcase/` (or `docs/`) resolving: observation modality (Option A vs B), action representation, planning mode, goal conditioning, Python-version bridge, CI sim backend, and licensing — each with evidence.
- [ ] A reproducible data-collection entry point produces sim rollouts (expert + perturbed) with the chosen observation/action/goal schema.
- [ ] A dataset-engineering step packs rollouts into the `stable-worldmodel` HDF5 layout under `$STABLEWM_HOME`, with documented train/val/test splits and a versioned, off-repo dataset card.
- [ ] A training/fine-tuning run produces an Atom01 LeWM checkpoint (`_object.ckpt` + `_weight.ckpt`) via the upstream Hydra/WandB flow, with a captured run record (config, seed, dataset revision, code SHA).
- [ ] An Atom01-aware extension of [leworldmodel_checkpoint.py](../../src/worldforge/smoke/leworldmodel_checkpoint.py) builds the object checkpoint from a pinned HF revision with an audited (still narrow) Hydra allow-list. `worldforge doctor` reports `leworldmodel` configured when the Atom01 env vars are present.
- [ ] A `roboto` policy adapter exists, advertises **only** `policy`, passes `worldforge.testing.assert_provider_contract()` (or the capability-protocol successor), and feeds candidates into `World.plan(...)`.
- [ ] `scripts/roboto-showcase` runs end-to-end in sim and emits JSON + a run-manifest with a truthful `mode` string, both providers' health, candidate/score shapes, `best_index`, and provider events — analogous to the PushT showcase contract.
- [ ] Evaluation artifacts show world-model fidelity and downstream planning lift with cost calibration; the showcase claims real capability only if the gate is met, else is labeled a scaffold.
- [ ] No torch / IsaacSim / IsaacLab / ROS2 / RSL_RL / `lewm` / `stable-worldmodel` / checkpoint / dataset import enters base deps or `src/worldforge/` module top level; `scripts/check_optional_import_boundaries.py` stays clean.
- [ ] Full local gate green (`uv run ruff check ...`, `ruff format --check`, `generate_provider_docs.py --check`, `pytest`, coverage ≥90%, `bash scripts/test_package.sh`).
- [ ] Optional sim-only CI workflow (recorded-rollout or MuJoCo fallback) added behind approval; it never trains and never uploads checkpoint/dataset artifacts.
- [ ] Docs updated: `roboto` provider page, data/training/eval playbook, `<provider_contracts>` (truthful `roboto` = `policy`), README/AGENTS/CLAUDE/CHANGELOG where public behavior changes.

## Non-functional requirements
- **Optional-runtime boundary held.** All heavy runtimes are host-owned, lazily imported only inside `src/worldforge/smoke/` entry points and provider methods, and supplied via `uv run --with`. Base `pyproject.toml`/`uv.lock` unchanged (any change is gated and approved separately).
- **Safety, sim-first.** No real-hardware actuation in this spec. Real hardware (P7) is opt-in, host-owned controller and kill switch, non-mutating defaults, gated approval. WorldForge owns planning, not safety.
- **Capability truthfulness.** `roboto` advertises only callable, tested, typed surfaces; the world model is exposed via the existing `score` capability. No physical-fidelity claims from deterministic/mock paths.
- **Licensing hygiene.** GPL-3.0 `roboto_origin` deploy code is invoked only as a separate host-owned process, never imported into `src/worldforge/`. BSD-3 `atom01_train` is unrestricted for our use. LeWM / `stable-worldmodel` / `stable-pretraining` licenses re-verified in P0 before any redistribution of derived checkpoints.
- **Reproducibility.** Dataset revision, checkpoint HF SHA, training config/seed, and upstream package versions are all pinned and recorded; checkpoint building validates a pinned 40-char SHA as today.
- **Determinism in CI.** The sim-only CI path is deterministic (recorded rollouts or seeded MuJoCo); no network model training; no flakiness from live GPU inference unless on an approved self-hosted runner.

## Open questions (to resolve in P0 — this is a research-gated spec)
1. **Observation modality** — Option A (render to pixels, keep LeWM architecture) vs Option B (vector-obs world model, architecture change). Evidence: rendering cost, domain-gap severity, checkpoint-builder impact.
2. **Does LeWM transfer at all to a 3D legged embodiment?** Warm-start benefit from a pretrained checkpoint is unknown given the PushT visual/embodiment gap; may need from-scratch.
3. **Planning mode for locomotion** — `policy+score` (rank policy candidates) vs `score`/MPC (sample candidates, optimize via CEM/MPPI in `stable-worldmodel`). Which improves a real task metric?
4. **Action space** — full joint targets vs reduced locomotion command space; the candidate tensor rank the planner and cost model expect.
5. **Python-version bridge** — `atom01_train` is 3.11, deploy is 3.10, WorldForge is 3.13. In-process vs ZMQ client/server (gr00t precedent). Likely client/server.
6. **CI sim backend** — IsaacSim is not installable on stock GitHub runners. Recorded-rollout replay, MuJoCo-only, or an approved self-hosted GPU runner?
7. **Checkpoint-builder allow-list** — how to widen `LEWORLDMODEL_HF_ALLOWED_CONFIG_TARGETS` / ViT-config validation for an Atom01 config while keeping it "exact and narrow."
8. **Dataset schema** — confirm the exact `stable-worldmodel` HDF5 keys/layout and goal-conditioning convention from upstream code (not just README).
9. **Licensing** — confirm LeWM / `stable-worldmodel` / `stable-pretraining` licenses permit redistributing an Atom01-derived checkpoint; confirm GPL-3 isolation strategy.
10. **Compute budget** — single-GPU "few hours" is the PushT claim; rendered 3D locomotion data is larger. Estimate data volume, training time, and storage.

## References
- Originating spike: [#321](https://github.com/AbdelStark/worldforge/issues/321)
- Existing showcase: [scripts/robotics-showcase](../../scripts/robotics-showcase), [src/worldforge/smoke/robotics_showcase.py](../../src/worldforge/smoke/robotics_showcase.py), [src/worldforge/smoke/lerobot_leworldmodel.py](../../src/worldforge/smoke/lerobot_leworldmodel.py)
- Checkpoint builder: [src/worldforge/smoke/leworldmodel_checkpoint.py](../../src/worldforge/smoke/leworldmodel_checkpoint.py)
- Providers: [src/worldforge/providers/leworldmodel.py](../../src/worldforge/providers/leworldmodel.py) (`score`), [src/worldforge/providers/lerobot.py](../../src/worldforge/providers/lerobot.py) (`policy`), [src/worldforge/providers/gr00t.py](../../src/worldforge/providers/gr00t.py) (`policy`, ZMQ bridge precedent)
- Planning: `World.plan(...)` in [src/worldforge/framework.py](../../src/worldforge/framework.py)
- CI precedent: [.github/workflows/robotics-showcase.yml](../../.github/workflows/robotics-showcase.yml)
- Boundary rules: [CLAUDE.md](../../CLAUDE.md) (`<priority_rules>`, `<boundaries>`)
- Upstream: https://github.com/Roboparty/roboto_origin (GPL-3.0), https://github.com/Roboparty/atom01_train (BSD-3-Clause), https://roboparty.com
- LeWM: https://github.com/lucas-maes/le-wm , https://github.com/lucas-maes/stable-worldmodel , https://le-wm.github.io/ , arXiv 2603.19312

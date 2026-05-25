# Tasks — Roboto (Atom01) showcase

## Status
Draft · 2026-05-25

Checkable task list matching the phases in [plan.md](./plan.md). P0 is a hard gate; P1–P3 are host/GPU research; P4–P6 are WorldForge `src/` PRs; P7 is gated/deferred. Nothing in P1+ starts until P0 is signed off.

## P0 — Feasibility and decision record (HARD GATE)
- [ ] Read upstream `stable-worldmodel` code and confirm the exact HDF5 dataset schema (keys, dtypes, episode layout) and goal-conditioning convention.
- [ ] Read `le-wm` code; determine whether the encoder is swappable for vector observations (Option B) or pixels are required (Option A).
- [ ] Determine the action-candidate tensor rank/shape that `AutoCostModel.get_cost` expects; confirm against the PushT `[batch, candidates, horizon, action_dim]` precedent.
- [ ] Inspect `atom01_train` `play.py` / `sim2sim_atom01.py` for the exported policy's observation and action shapes and control rate.
- [ ] Check whether a pretrained LeWM checkpoint exists that is plausibly warm-startable for 3D control.
- [ ] Decide observation modality: Option A (render to pixels) vs Option B (vector-obs world model). Record evidence.
- [ ] Decide action space: full joint targets vs reduced locomotion command space.
- [ ] Decide planning mode: `policy+score` vs `score`/MPC (CEM/MPPI) — pick the one expected to lift a real task metric.
- [ ] Decide goal-conditioning representation for locomotion.
- [ ] Decide Python-version bridge: in-process vs ZMQ client/server (gr00t precedent).
- [ ] Decide CI sim backend: recorded-rollout replay vs MuJoCo vs approved self-hosted GPU runner (IsaacSim not on stock runners).
- [ ] Verify licenses: `le-wm`, `stable-worldmodel`, `stable-pretraining` (checkpoint redistribution); confirm GPL-3 `roboto_origin` isolation strategy.
- [ ] Estimate compute/storage budget (data volume, training time, checkpoint/dataset sizes).
- [ ] Off-repo proof: chosen action-candidate shape flows through `World.plan(...)` against the mock/score path.
- [ ] Write the decision record (`specs/roboto-showcase/decisions.md` or triad update); record go/no-go. Every spec open question cited with a source.

## P1 — Sim rollout data-collection harness (host/GPU)
- [ ] Stand up `atom01_train` (BSD-3) on a GPU host; reproduce `play.py` and `sim2sim_atom01.py`.
- [ ] Build a host-owned collector (run via `uv run --with`) that rolls out the trained policy in IsaacLab/IsaacSim and MuJoCo Sim2Sim.
- [ ] Capture the P0-chosen observation modality, actions, terminals, and goal/cost signal per step.
- [ ] Add configurable expert/exploratory mix, command/terrain/dynamics randomization, and seed capture.
- [ ] Emit a raw rollout dump + manifest (counts, seeds, source policy revision) to an off-repo location.
- [ ] Confirm no IsaacSim/IsaacLab/RSL_RL import touches `src/worldforge/`.

## P2 — Dataset engineering → HDF5 (host/GPU)
- [ ] Implement a packing step that converts rollouts into the upstream `stable-worldmodel` HDF5 layout under `$STABLEWM_HOME`.
- [ ] Compute and store action normalization stats and goal-conditioning fields.
- [ ] Produce episode-level train/val/test splits with held-out commands/terrains.
- [ ] Write a dataset card (modality, action space, mix ratio, counts, seeds, source revision) + content hash.
- [ ] Publish the dataset off-repo (HF dataset or object store), pinned by revision. Confirm nothing is committed.
- [ ] Validate: `stable-worldmodel` loads the dataset; a one-batch LeWM step runs.

## P3 — World-model training / fine-tuning + MLOps (host/GPU)
- [ ] Author the host-owned Hydra config (`data=atom01`, encoder/predictor/action-encoder shapes from P0).
- [ ] Document the `uv run --with ...` training command and WandB setup.
- [ ] Run the from-scratch baseline; capture config, seed, dataset revision, code SHA, package versions.
- [ ] Run the warm-start ablation if a compatible checkpoint exists.
- [ ] Add collapse / degenerate-cost diagnostics (loss curves, latent-variance / probe checks).
- [ ] Produce `<name>_object.ckpt` + `<name>_weight.ckpt`.
- [ ] Publish `config.json` + `weights.pt` to a pinned 40-char HF revision.
- [ ] Write a short training debrief (curves, chosen arm, known limitations).
- [ ] Validate: checkpoint loads via `AutoCostModel`; finite, non-degenerate costs over held-out candidates.

## P4 — Checkpoint packaging + provider wiring (WorldForge `src/`)
- [ ] Check tree state for the capability-protocols refactor; target the current provider surface.
- [ ] Extend `LEWORLDMODEL_HF_ALLOWED_CONFIG_TARGETS` and the encoder-config validator in [src/worldforge/smoke/leworldmodel_checkpoint.py](../../src/worldforge/smoke/leworldmodel_checkpoint.py) for the audited Atom01 config; keep the allow-list exact/narrow; support an `atom01/<name>` policy path.
- [ ] Add positive + negative unit tests for the widened allow-list and config validator.
- [ ] Create `src/worldforge/providers/roboto.py` implementing `policy` (or the capability-protocol successor); lazy runtime imports only.
- [ ] Implement the ZMQ client + host policy-server contract if P0 confirms a Python-version split; wire the host-supplied `action_translator`.
- [ ] Env-gated registration (`ROBOTO_POLICY_HOST` / `ROBOTO_POLICY_PATH`); add the catalog entry.
- [ ] Add `<provider_contracts>` row: `roboto` → `policy` (truthful), Atom01 LeWM checkpoint loadable by `leworldmodel`.
- [ ] Unit + contract tests with fixtures (`assert_provider_contract` or `assert_capability_contract`); no live runtime on the unit path.
- [ ] `worldforge doctor` reports `roboto` + `leworldmodel` configured under Atom01 env vars.
- [ ] `scripts/check_optional_import_boundaries.py` clean. Full gate green.

## P5 — Planning loop + showcase wrapper + evidence (WorldForge `src/`)
- [ ] Create `src/worldforge/smoke/roboto_showcase.py` composing `roboto` (policy) + `leworldmodel` (score) via `World.plan(... planning_mode=...)` per P0.
- [ ] Create `scripts/roboto-showcase` wrapper supplying runtime deps via `uv run --with`, with `--json-only` / `--no-tui` / `--no-rerun` / `--no-tensorboard` parity.
- [ ] Emit JSON + run-manifest: truthful `mode` string, both providers' health, candidate/score shapes, `best_index`, provider events, `capability` field.
- [ ] Wire optional Rerun / TensorBoard visuals via existing bridges (out of base deps).
- [ ] Produce evaluation artifacts: world-model fidelity + downstream planning lift vs policy-only + cost calibration.
- [ ] Deterministic showcase contract test (recorded/mock-backed) mirroring the PushT showcase assertions.
- [ ] Decide real-capability vs scaffold labeling based on the planning-lift gate; document the finding.
- [ ] Full gate green.

## P6 — Optional sim-only CI + docs (gated)
- [ ] Draft `.github/workflows/roboto-showcase.yml` (sim-only; recorded-replay or MuJoCo; never trains; never uploads checkpoint/dataset artifacts; `actions/cache` for HF + checkpoint). **Requires explicit approval before merge.**
- [ ] Add `docs/src/providers/roboto.md`.
- [ ] Add a playbook section for the data/training/eval pipeline.
- [ ] Update README / AGENTS / CLAUDE `<provider_contracts>` for `roboto`.
- [ ] Add CHANGELOG entry.
- [ ] `uv run python scripts/generate_provider_docs.py --check` clean; manual docs review.
- [ ] Full gate green including `bash scripts/test_package.sh`.

## P7 — Real-hardware bring-up (GATED · DEFERRED)
- [ ] (Deferred) Separate safety review + its own spec triad + approval before any physical actuation. Not built by this triad.

## Post-merge
- [ ] (Optional) Generalize the data→dataset→train→checkpoint pipeline into a reusable "new embodiment world model" playbook.
- [ ] (Optional) Revisit Option B (vector-obs world model) if Option A's domain gap proves limiting.

# Plan — Roboto (Atom01) showcase

## Status
Draft · 2026-05-25

## Strategy summary
Research-gated, sim-first, phased. **P0 is a hard gate**: no data collection, training, or integration work starts until the observation-modality / planning-mode / licensing / Python-bridge questions in [spec.md](./spec.md) § "Open questions" are resolved with evidence. P0 deliberately front-loads the risk that makes this a spike rather than a copy of the PushT showcase.

After P0, the lifecycle runs left-to-right (data → dataset → train → checkpoint → integrate → showcase), with each phase leaving a usable artifact that the next consumes. Real-hardware bring-up (P7) is **gated** and explicitly out of this spec's delivery scope — it is listed so the architecture does not paint itself into a sim-only corner, not as committed work.

Every phase keeps heavy runtimes host-owned (invoked via `uv run --with`); the only `src/worldforge/` changes are the `roboto` provider, an Atom01-aware extension of the checkpoint builder, a `smoke/` entry point, and tests/docs. Base `pyproject.toml` / `uv.lock` do not change.

## Dependencies on other work
- **Capability-protocols refactor** ([specs/capability-protocols/](../capability-protocols/spec.md)) is in flight and rewrites the provider/registration surface. The `roboto` provider should target whichever surface is current when P4 lands: legacy `BaseProvider` + `assert_provider_contract` if before that refactor merges, or a `Policy` capability class + `assert_capability_contract` after. P4 must check the tree state first.
- Upstream package availability: `atom01_train` (BSD-3), `le-wm`, `stable-worldmodel`, `stable-pretraining`. No version bumps to WorldForge's own toolchain.
- GPU host for P1–P3 and P5 live runs. CI never trains.

## Phases

### P0 — Feasibility and decision record (HARD GATE)
Resolve every open question in [spec.md](./spec.md) with evidence, by reading upstream **code** (not just READMEs) and running minimal probes off-repo.

**Investigate:** exact `stable-worldmodel` HDF5 dataset schema and goal convention; whether LeWM's encoder is swappable for vectors (Option B feasibility) or rendering is required (Option A); whether a pretrained LeWM checkpoint exists that is plausibly warm-startable for 3D control; the candidate tensor rank `get_cost` expects; `atom01_train`'s exported policy interface (obs/action shapes from `play.py` / `sim2sim_atom01.py`); IsaacSim CI installability; LeWM/stable-worldmodel/stable-pretraining licenses; GPL-3 isolation strategy; rough compute/storage budget.

**Deliverables:**
- A decision record (new `specs/roboto-showcase/decisions.md` or an update to this triad) fixing: observation modality, action space, planning mode, goal conditioning, Python-version bridge, CI sim backend, checkpoint-allow-list strategy, dataset schema, licensing, and compute budget.
- A minimal off-repo proof that the chosen action-candidate shape flows through `World.plan(...)` against the mock/score path.

**Acceptance:** Every spec open question marked resolved with a cited source (upstream file path or measured probe). Go/no-go recorded. If no-go, the spec is closed with the finding and the showcase is not built.

### P1 — Sim rollout data-collection harness (host/GPU)
Build a host-owned collector that rolls out the trained Atom01 policy (and perturbed/exploratory variants) in IsaacLab/IsaacSim and MuJoCo Sim2Sim, capturing the P0-chosen observation modality, actions, terminals, and goal/cost signal.

**Deliverables:**
- A collection script run via `uv run --with` (host owns IsaacSim/IsaacLab/RSL_RL). Lives in a host-owned location or `scripts/`-adjacent tooling — **no** IsaacSim import inside `src/worldforge/`.
- Configurable expert/exploratory mix, command/terrain randomization, seed capture.
- Raw rollout dump (pre-HDF5) with a manifest of counts, seeds, and source policy revision.

**Acceptance:** Reproducible rollout dump for a small pilot (enough to smoke the full pipeline) with recorded provenance. No repo-tree pollution; outputs land off-repo.

### P2 — Dataset engineering → stable-worldmodel HDF5 (host/GPU)
Convert rollouts into the upstream HDF5 layout under `$STABLEWM_HOME`, with normalization, splits, and a versioned dataset card.

**Deliverables:**
- A packing step producing `<name>_train.h5` / `<name>_val.h5` (+ test) in the exact upstream schema confirmed in P0.
- Action normalization stats, goal-conditioning fields, episode-level train/val/test split with held-out commands/terrains.
- Dataset card (modality, action space, mix ratio, counts, seeds, source policy revision) + content hash; published off-repo (HF dataset or object store) and pinned by revision. Never committed.

**Acceptance:** `stable-worldmodel` loads the dataset without error; a tiny LeWM training step consumes a batch. Dataset card review confirms reproducibility from pinned inputs.

### P3 — World-model training / fine-tuning + MLOps (host/GPU)
Train the Atom01 LeWM via the upstream Hydra/WandB flow. Two arms: from-scratch (baseline) and warm-start (ablation, if a compatible checkpoint exists).

**Deliverables:**
- Host-owned Hydra config (`data=atom01`, encoder/predictor/action-encoder shapes from P0) and a documented `uv run --with` training command.
- WandB-tracked runs with captured config, seed, dataset revision, code SHA, and upstream package versions.
- `<name>_object.ckpt` + `<name>_weight.ckpt`; `config.json` + `weights.pt` published to a **pinned 40-char HF revision**.
- A short training-debrief note (loss curves, collapse checks, chosen arm).

**Acceptance:** A checkpoint that loads via `stable_worldmodel.policy.AutoCostModel` and produces finite, non-degenerate costs over held-out candidates. (Collapse / degenerate-cost diagnostics borrowed from LeWM training-debugging practice.)

### P4 — Checkpoint packaging + provider wiring (WorldForge `src/`)
Make WorldForge load the Atom01 checkpoint and feed it candidates.

**Deliverables:**
- Extend [src/worldforge/smoke/leworldmodel_checkpoint.py](../../src/worldforge/smoke/leworldmodel_checkpoint.py): widen `LEWORLDMODEL_HF_ALLOWED_CONFIG_TARGETS` and the encoder-config validator to accept the audited Atom01 config, keeping the allow-list exact and narrow; support an `atom01/<name>` policy path. Pinned-SHA validation unchanged.
- New `src/worldforge/providers/roboto.py` implementing the `policy` capability (or the capability-protocol successor — check tree state per "Dependencies"). Client/server ZMQ bridge to a host-owned policy server if P0 confirms a Python-version split; host-supplied `action_translator`. Env-gated registration (e.g. `ROBOTO_POLICY_HOST` / `ROBOTO_POLICY_PATH`), lazy runtime imports only.
- Catalog entry + `<provider_contracts>` row (`roboto` → `policy`, truthful).
- Unit + contract tests with fixtures; no live runtime required for the unit path.

**Acceptance:** `worldforge doctor` reports `roboto` and `leworldmodel` configured under the Atom01 env vars; contract tests pass; checkpoint builder unit tests cover the widened allow-list (positive + negative). Full gate green.

### P5 — Planning loop + showcase wrapper + evidence (WorldForge `src/`)
Close the loop and produce evidence.

**Deliverables:**
- `src/worldforge/smoke/roboto_showcase.py` composing `roboto` (policy) + `leworldmodel` (score) via `World.plan(... planning_mode=...)` (mode per P0), mirroring [robotics_showcase.py](../../src/worldforge/smoke/robotics_showcase.py).
- `scripts/roboto-showcase` wrapper supplying runtime deps via `uv run --with`, with `--json-only` / `--no-tui` / `--no-rerun` / `--no-tensorboard` parity.
- JSON + run-manifest output with a truthful `mode` string, both providers' health, candidate/score shapes, `best_index`, provider events, and a `capability` field.
- Optional Rerun / TensorBoard visuals via existing bridges.
- Evaluation artifacts: world-model fidelity + downstream planning lift vs policy-only + cost calibration.

**Acceptance:** `scripts/roboto-showcase --json-only --no-tui` runs end-to-end on the host and emits a valid manifest; evaluation shows non-trivial, calibrated cost. The showcase claims real capability only if this gate is met; otherwise it ships labeled as a scaffold with the finding documented.

### P6 — Optional sim-only CI + docs (gated, approval required)
**Deliverables:**
- A new optional workflow modeled on [.github/workflows/robotics-showcase.yml](../../.github/workflows/robotics-showcase.yml) that runs `scripts/roboto-showcase --json-only --no-tui --no-rerun` against the P0-chosen CI backend (recorded-rollout replay or MuJoCo; **not** IsaacSim on stock runners). `actions/cache` for HF + checkpoint; upload JSON/manifest evidence only; **never** train; **never** upload checkpoint/dataset artifacts.
- Docs: `docs/src/providers/roboto.md`, a playbook section for the data/training/eval pipeline, README/AGENTS/CLAUDE `<provider_contracts>` updates, CHANGELOG entry. Provider docs regenerated (`generate_provider_docs.py --check` clean).

**Acceptance:** Workflow green on a PR; docs-drift check clean; manual docs review. Workflow addition explicitly approved (CI is a gated path).

### P7 — Real-hardware bring-up (GATED · DEFERRED · out of this spec's delivery)
Listed only to keep the architecture honest. Would require: a separate safety review, host-owned ROS2/USB2CAN controller invoked as a distinct process (GPL-3 isolation preserved), explicit operator opt-in, hardware kill switch, non-mutating defaults, and its own spec triad + approval. **Not built here.**

## Test strategy
- **P0–P3** are host/GPU research phases validated by their own acceptance artifacts (decision record, dataset load, checkpoint load + finite costs), not by the repo test suite.
- **P4–P6** ride the standard gate after every phase: `uv run ruff check src tests examples scripts`, `ruff format --check`, `generate_provider_docs.py --check`, `pytest`, `--extra harness pytest --cov-fail-under=90`, and `bash scripts/test_package.sh` before merge.
- **Provider tests** mirror the existing leworldmodel/lerobot/gr00t suites: fixture-driven, no live runtime on the unit path; lazy-import boundaries asserted by `scripts/check_optional_import_boundaries.py`.
- **Showcase contract test** mirrors the PushT showcase assertions (mode string, provider health, shapes, `best_index`, events) against a recorded or mock-backed run so it stays deterministic.
- **Coverage** stays ≥90% on all `src/worldforge/` changes.

## Risks and rollback

### Risks
1. **LeWM may not transfer to a 3D legged embodiment.** The PushT checkpoint is a 2D manipulation visual domain; warm-start lift is unknown and could be negative. *Mitigation:* P0 go/no-go; from-scratch baseline; Option B fallback. Honest scaffold-labeling if planning lift is not demonstrable.
2. **Observation-modality dead-end.** If rendering is too costly and Option B is too invasive, the world-model angle may not be worth it. *Mitigation:* P0 decides before any data is collected; this is the whole point of the hard gate.
3. **IsaacSim is not CI-installable.** *Mitigation:* P0 picks a CI backend (recorded replay / MuJoCo / self-hosted); CI never trains or runs IsaacSim on stock runners.
4. **Python-version friction.** 3.10/3.11 sim vs 3.13 WorldForge. *Mitigation:* ZMQ client/server bridge (gr00t precedent) confirmed in P0.
5. **Allow-list erosion.** Widening the checkpoint-builder Hydra allow-list could weaken the "exact and narrow" safety property. *Mitigation:* P4 adds the Atom01 config as explicit, audited entries with positive+negative tests; no wildcards.
6. **Licensing.** GPL-3 contamination or non-redistributable upstream checkpoints. *Mitigation:* P0 license verification; GPL code runs only as a separate host process, never imported.
7. **Compute/storage blow-up.** Rendered 3D rollouts are large. *Mitigation:* P0 budget estimate; pilot-scale dataset first (P1/P2) before any full training run.
8. **Scope creep into real hardware.** *Mitigation:* P7 is explicitly gated and deferred; safety stays host-owned.

### Rollback
P0–P3 are off-repo and leave no tree changes to roll back (only host artifacts and an off-repo dataset/checkpoint). P4–P6 are independent PRs; revert the PR to roll back. The `roboto` provider and the checkpoint-builder extension are additive and env-gated, so reverting them cannot affect the existing PushT showcase or default `worldforge doctor` behavior.

## Open questions / decisions needed
All ten are tracked in [spec.md](./spec.md) § "Open questions" and are the deliverable of **P0**. None are resolved yet — this triad is authored pre-research by design.

## Dependencies on other milestones
- Soft coupling to the capability-protocols refactor (provider surface). See "Dependencies on other work." Otherwise self-contained within providers / smoke / docs / CI.

# LeWorldModel Provider

Capability: `score`

Taxonomy category: JEPA latent predictive world model

Maturity: `stable`

`leworldmodel` wraps LeWorldModel's `stable_worldmodel.policy.AutoCostModel` surface. It ranks
candidate action sequences from task-shaped observations, goals, and actions. WorldForge models it
as an action scorer because the upstream runtime returns costs; it does not generate video, answer
text questions, or mutate WorldForge state directly.

```text
pixels + action history + goal + candidate actions
  -> LeWorldModel cost model
  -> ActionScoreResult(scores, best_index, lower_is_better=True)
```

## Runtime Ownership

WorldForge owns provider registration, input validation, score-result validation, planning
selection, metadata, and provider events.

The host owns:

- `stable_worldmodel` and torch installation
- checkpoint download, extraction, and compatibility
- `$STABLEWM_HOME` or `LEWORLDMODEL_CACHE_DIR`
- preprocessing sensor data into checkpoint-shaped `pixels`, `goal`, and `action` tensors
- mapping model-native action candidates back to WorldForge `Action` sequences

WorldForge does not add LeWorldModel, torch, checkpoint archives, or datasets to its base package.

## Configuration

- `LEWORLDMODEL_POLICY` or `LEWM_POLICY`: required for auto-registration. Value is the checkpoint
  run name relative to `$STABLEWM_HOME`, without the `_object.ckpt` suffix. Example: `pusht/lewm`.
- `LEWORLDMODEL_CACHE_DIR`: optional checkpoint root override.
- `LEWORLDMODEL_DEVICE`: optional torch device string such as `cpu`, `cuda`, or `cuda:0`.

Runtime manifest:
`src/worldforge/providers/runtime_manifests/leworldmodel.json` records the policy aliases,
optional checkpoint/device settings, host-owned checkpoint artifacts, minimum real-checkpoint smoke
command, the pinned upstream import boundary
`stable_worldmodel.policy.AutoCostModel`, and expected finite-cost signal.

Programmatic construction can inject a loader and tensor module for tests or host-owned runtimes:

```python
from worldforge.providers import LeWorldModelProvider

provider = LeWorldModelProvider(
    policy="pusht/lewm",
    cache_dir="/models/stable-wm",
    device="cpu",
)
```

## Input Contract

`score_actions(...)` requires:

```python
result = forge.score_actions(
    "leworldmodel",
    info={
        "pixels": pixels,
        "goal": goal,
        "action": action_history,
    },
    action_candidates=action_candidate_tensor,
)
```

Validation rules:

- `info` must be a JSON object.
- `info["pixels"]`, `info["goal"]`, and `info["action"]` are required.
- Required info fields must be tensors or rectangular nested numeric arrays with at least three
  dimensions.
- `action_candidates` must be a tensor or rectangular nested numeric array shaped as
  `(batch, samples, horizon, action_dim)`.
- Returned costs must flatten to finite numeric scores.
- Returned score tensor shape must contain exactly one score per candidate action sample. Shapes
  such as `(samples,)`, `(1, samples)`, or `(samples, 1)` are accepted; ambiguous non-singleton
  dimensions fail before `ActionScoreResult` is returned.
- The number of returned scores must match the scored candidate set.

Scores are costs: lower values are better. WorldForge sets `best_index` to the lowest-cost
candidate unless the provider returns a validated explicit index.

## Planning

Score planning keeps WorldForge actions separate from model-native tensors:

```python
from worldforge import Action

plan = world.plan(
    goal="select the lowest-cost LeWorldModel candidate",
    provider="leworldmodel",
    planner="leworldmodel-mpc",
    candidate_actions=[
        [Action.move_to(0.1, 0.5, 0.0)],
        [Action.move_to(0.4, 0.5, 0.0)],
    ],
    score_info={
        "pixels": pixels,
        "goal": goal_pixels,
        "action": action_history,
    },
    score_action_candidates=action_candidate_tensor,
    execution_provider="mock",
)
```

The selected `Plan.actions` come from `candidate_actions[best_index]`. `Plan.predicted_states`
stays empty because a score provider ranks candidate futures without returning a WorldForge state
rollout. Use `execute_plan(...)` with an execution provider that supports `predict`.

## Task Bridges

WorldForge ships a small bridge registry for smoke commands, not a generic tensor preprocessor.
The first registered bridge is `pusht`; it wires:

- `build_observation()` for the LeRobot PushT policy input
- `build_score_info()` for LeWorldModel `pixels`, `goal`, and `action`
- `translate_candidates_contract` for WorldForge replay actions
- `build_action_candidates()` for `1 x 3 x 4 x 10` PushT score tensors

Use it from the lower-level runner with:

```bash
scripts/lewm-lerobot-real \
  --policy-path lerobot/diffusion_pusht \
  --checkpoint ~/.stable-wm/pusht/lewm_object.ckpt \
  --bridge pusht
```

The bridge registry records expected policy, score, and candidate tensor shapes. Run manifests copy
that shape summary plus the observed score tensor shapes so issue evidence can show whether a host
used the intended task contract. WorldForge validates shape consistency and fails on mismatched
action dimensions before planning; the host still owns task preprocessing and any non-PushT bridge.

## Runtime Checks

Checkout-safe provider/planner demo:

```bash
uv run worldforge-demo-leworldmodel
uv run worldforge-demo-leworldmodel --json-only
```

This uses an injected deterministic cost runtime. It validates WorldForge's provider and planning
path without loading an upstream checkpoint.

Real-checkpoint smoke:

```bash
scripts/lewm-real --checkpoint ~/.stable-wm/pusht/lewm_object.ckpt --device cpu \
  --json-output /tmp/lewm-real-summary.json \
  --run-manifest .worldforge/runs/lewm-real/run_manifest.json
```

This loads the host-owned upstream runtime and object checkpoint, then scores synthetic
PushT-shaped candidate tensors through `LeWorldModelProvider`. It is real checkpoint scoring, not
task-specific preprocessing or robot execution.

The JSON summary and optional run manifest include the score payload summary, input tensor shape
summary, provider event count, runtime API, and sanitized artifact links. They do not include
checkpoint bytes or host credentials.

The upstream dependency shown by the wrapper is `stable-worldmodel` because the official
`lucas-maes/le-wm` repository documents `stable_worldmodel.policy.AutoCostModel("pusht/lewm")` as
the loading path for LeWorldModel object checkpoints. WorldForge uses that runtime API to call the
LeWM checkpoint's `get_cost(...)`; it does not replace LeWorldModel with a generic SWM baseline.

LeRobot + LeWorldModel robotics replay showcase:

```bash
scripts/robotics-showcase
```

This uses `LeWorldModelProvider` as the score half of the real policy-plus-score showcase. Full
runnable context lives in [CLI Reference](../cli.md), [Examples And CLI Commands](../examples.md),
and [Robotics Replay Showcase](../robotics-showcase.md).

## Failure Modes

- Missing `LEWORLDMODEL_POLICY` and `LEWM_POLICY` leaves the provider unregistered.
- Missing `torch` or `stable_worldmodel.policy.AutoCostModel` is reported by `health()`.
- Checkpoint loading failures are wrapped in `ProviderError`.
- If no device is configured, the provider prepares the runtime on `cpu`; pass
  `LEWORLDMODEL_DEVICE` or `device=` for a host-owned accelerator.
- Missing required `pixels`, `goal`, or `action` fields fail before model invocation.
- Ragged nested arrays, non-finite values, or low-rank tensors fail before model invocation.
- Non-four-dimensional action candidates fail before model invocation.
- Non-finite model outputs fail before `ActionScoreResult` is returned.
- Score tensor shapes with more than one non-singleton dimension fail before
  `ActionScoreResult` is returned.
- Returned score count must match the candidate sample count.
- Score planning fails if the score result cannot identify an in-range candidate.

## Tests

- `tests/test_leworldmodel_provider.py` covers input validation, score outputs, provider health,
  event emission, and planning integration.
- `tests/test_leworldmodel_e2e_demo.py` covers the checkout-safe end-to-end demo.
- `tests/test_leworldmodel_smoke_script.py` and `tests/test_leworldmodel_uv_tasks.py` cover smoke
  command parsing and checkpoint-builder behavior without requiring a real checkpoint.
- `tests/test_lerobot_leworldmodel_smoke_script.py` and `tests/test_robotics_showcase.py` cover
  the combined LeRobot + LeWorldModel runner and showcase defaults without requiring optional
  runtimes.

## Primary References

- [LeWorldModel paper](https://arxiv.org/abs/2603.19312)
- [LeWorldModel project page](https://le-wm.github.io/)
- [LeWorldModel code](https://github.com/lucas-maes/le-wm)

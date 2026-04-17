# LeRobot Provider

Status: beta host-owned policy-client adapter

Taxonomy category: embodied policy / imitation + RL action model

This adapter wraps Hugging Face [LeRobot](https://github.com/huggingface/lerobot)'s pretrained
policy interface. LeRobot is modeled as an actor: it accepts multimodal observations
(state, cameras, language) and returns robot action tensors. It is not modeled as a
predictive world model, video generator, or candidate scorer.

```text
observation (+ language instruction) -> action tensor
```

WorldForge keeps the boundary explicit:

```text
LeRobot PreTrainedPolicy
  -> raw embodiment-specific action tensors
  -> host-supplied action_translator
  -> ActionPolicyResult
  -> World.plan(... planning_mode="policy")
```

For actor plus world-model planning:

```text
LeRobot proposes candidate action chunks
  -> LeWorldModel / JEPA-WMS / another score provider ranks candidates
  -> World.plan(... planning_mode="policy+score")
  -> execution_provider runs the chosen WorldForge actions
```

## Configuration

- `LEROBOT_POLICY_PATH` (alias `LEROBOT_POLICY`): required for auto-registration. Hugging Face
  repo id (e.g. `lerobot/act_aloha_sim_transfer_cube_human`) or local checkpoint directory.
- `LEROBOT_POLICY_TYPE`: optional. One of `act`, `diffusion`, `tdmpc`, `vqbet`, `pi0`,
  `pi0fast`, `sac`, `smolvla`. Skipped policy-type auto-detection goes through
  `PreTrainedPolicy.from_pretrained`, which reads the checkpoint metadata itself.
- `LEROBOT_DEVICE`: optional. Device string passed to `policy.to(...)` after loading
  (e.g. `cpu`, `cuda`, `cuda:0`, `mps`).
- `LEROBOT_CACHE_DIR`: optional. Hugging Face cache directory override.
- `LEROBOT_EMBODIMENT_TAG`: optional. Metadata string stored on the returned
  `ActionPolicyResult`.

The adapter does not add `lerobot`, PyTorch, NumPy, or robot runtime dependencies to
WorldForge's base install. Those dependencies remain host-owned and are only imported when
a non-injected policy is loaded.

## Policy Runtime Contract

Direct construction with a fake or host-owned policy:

```python
from worldforge.providers import LeRobotPolicyProvider

provider = LeRobotPolicyProvider(
    policy=policy,
    embodiment_tag="aloha",
    action_translator=translate_actions,
)
```

The injected or lazily loaded policy must expose:

```python
policy.select_action(observation) -> action_tensor              # required
policy.predict_action_chunk(observation) -> action_chunk_tensor # optional
policy.reset()                                                  # optional
```

If no policy is injected, WorldForge lazily imports:

```python
from lerobot.policies.pretrained import PreTrainedPolicy
policy = PreTrainedPolicy.from_pretrained(LEROBOT_POLICY_PATH, cache_dir=...)
```

When `LEROBOT_POLICY_TYPE` is set, the adapter imports the specific policy class (for example
`lerobot.policies.act.modeling_act.ACTPolicy`) and calls `from_pretrained` on that class
instead. Both lookup paths are lazy: `lerobot` is only imported when a real policy needs to
load.

After loading, the adapter calls `policy.to(device)`, `policy.eval()`, `policy.requires_grad_(False)`,
and `policy.reset()` when those methods exist.

## Input Shape

`select_actions(...)` expects:

```python
provider.select_actions(
    info={
        "observation": {
            "observation.state": state_tensor_or_array,
            "observation.images.top": image_tensor_or_array,
            "task": "pick up the red cube",
        },
        "embodiment_tag": "aloha",
        "action_horizon": 16,
        "options": {},
        "mode": "select_action",   # or "predict_chunk"
    }
)
```

- `info["observation"]` must be a non-empty JSON object. Keys follow LeRobot's naming convention
  (e.g. `observation.state`, `observation.images.<camera>`, `task`). Arrays may be tensor-like
  objects with `tolist()`; the adapter normalizes raw provider output into JSON-compatible
  metadata.
- `info["options"]` is optional, must be a JSON object when provided, and is passed through to
  the translator via `info`.
- `info["mode"]` selects between `select_action` (one step) and `predict_chunk` (full action
  chunk). `predict_chunk` only works when the policy implements `predict_action_chunk`.

## Action Translation

LeRobot actions are embodiment-specific: a 7-DoF arm, a bimanual 14-DoF setup, a
gripper-plus-mobile-base, or something else entirely. WorldForge cannot safely infer what a
joint command means for a host robot. The provider therefore requires a host-supplied
`action_translator` before it can return executable WorldForge `Action` objects:

```python
from worldforge import Action

def translate_actions(raw_actions, info, provider_info):
    tensor = raw_actions.tolist() if hasattr(raw_actions, "tolist") else raw_actions
    return [
        Action.move_to(float(x), float(y), float(z))
        for (x, y, z) in tensor[0]
    ]
```

The translator may return a single action chunk:

```python
[Action.move_to(...), Action.move_to(...)]
```

or multiple candidate chunks:

```python
[
    [Action.move_to(0.1, 0.5, 0.0)],
    [Action.move_to(0.4, 0.5, 0.0)],
]
```

Multiple candidates are useful when pairing LeRobot with a score provider (policy+score
planning).

## Planning

Policy-only planning:

```python
plan = world.plan(
    goal="pick up the red cube",
    provider="lerobot",
    policy_info=policy_info,
    execution_provider="mock",
)
```

Policy plus score planning:

```python
plan = world.plan(
    goal="choose the lowest-cost policy candidate",
    policy_provider="lerobot",
    score_provider="leworldmodel",
    policy_info=policy_info,
    score_info=lewm_info,
    execution_provider="mock",
)
```

WorldForge serializes policy candidates into `Action.to_dict()` payloads by default before
calling the score provider. If the scorer needs native tensors or latents, pass
`score_action_candidates=...`; WorldForge only requires that the number of policy candidates
and native score candidates describe the same candidate set.

## Checkout-Safe Demo

`examples/lerobot_e2e_demo.py` runs the real `LeRobotPolicyProvider` with an injected
deterministic policy. It exercises `select_actions`, `World.plan(policy+score)`,
`execute_plan`, JSON persistence, and reload without needing `lerobot`, torch, or checkpoint
downloads:

```bash
uv run python examples/lerobot_e2e_demo.py
```

## Live Smoke

Use `scripts/smoke_lerobot_policy.py` for a real `PreTrainedPolicy` smoke. It loads the
checkpoint in the host environment, so `lerobot` and the robot's dependencies must already be
installed.

```bash
uv venv --python=3.10 .venv-lerobot
source .venv-lerobot/bin/activate
uv pip install -e .
uv pip install "lerobot[aloha]"

python scripts/smoke_lerobot_policy.py \
  --policy-path lerobot/act_aloha_sim_transfer_cube_human \
  --observation-module /path/to/obs.py:build_observation \
  --translator /path/to/translator.py:translate_actions \
  --device cpu
```

`--policy-info-json` accepts a complete `policy_info` JSON payload. `--observation-json`
accepts an observation-only payload. `--observation-module module_or_file:function` is the
right escape hatch when observations need NumPy arrays, PyTorch tensors, or host-side
preprocessing that JSON cannot represent cleanly.

The translator callable receives `(raw_actions, info, provider_info)` and must return either
a single WorldForge action chunk or multiple candidate chunks. `--health-only` reports
provider health without running inference and is useful during environment setup.

## Failure Modes

- Missing `LEROBOT_POLICY_PATH` leaves the auto-registered provider unavailable.
- Missing `lerobot` (or `lerobot.policies.pretrained.PreTrainedPolicy`) is reported by
  `health()`.
- Missing `action_translator` fails with `ProviderError`.
- Malformed `info.observation` (not a non-empty JSON object, non-string keys, options not a
  dict, unknown `mode`) fails before invoking the policy.
- Non-JSON-compatible raw actions or provider info fail before returning
  `ActionPolicyResult`.
- Failed policy inference is wrapped in `ProviderError`.
- Requesting `mode="predict_chunk"` against a policy that does not implement
  `predict_action_chunk` fails explicitly instead of returning stale single-step output.

## Tests

- `tests/test_lerobot_provider.py` covers fake-policy contract checks, event emission,
  malformed inputs, missing translator, unconfigured health, env configuration, lazy import
  of `PreTrainedPolicy`, select/predict_chunk modes, `reset()` delegation, auto-registration,
  and policy+score planning.
- `tests/test_lerobot_e2e_demo.py` runs the full end-to-end demo and asserts the planning,
  execution, persistence, reload, and event-emission output.
- `tests/test_lerobot_smoke_script.py` covers the smoke script's JSON-file and factory input
  loaders, callable resolution, and input validation. It does not require `lerobot` or a GPU.

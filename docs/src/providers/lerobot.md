# LeRobot Provider

Capability: `policy`

Taxonomy category: embodied policy / imitation and RL action model

`lerobot` wraps Hugging Face LeRobot's `PreTrainedPolicy` interface. LeRobot is modeled as an
actor: it accepts robot observations and returns action tensors. It is not modeled as a predictive
world model, video generator, or candidate scorer.

```text
observation + optional task language
  -> LeRobot policy
  -> raw embodiment-specific action tensors
  -> host action_translator
  -> ActionPolicyResult
```

## Runtime Ownership

WorldForge owns provider registration, policy-call envelope validation, raw-action preservation,
action-result validation, planning composition, and provider events.

The host owns:

- LeRobot installation and robot-specific dependencies
- Hugging Face repo id or local checkpoint directory
- observation construction and preprocessing
- translation from raw policy tensors to WorldForge `Action` objects
- robot execution, safety interlocks, and controller integration

WorldForge never drives hardware directly.

## Configuration

- `LEROBOT_POLICY_PATH` or `LEROBOT_POLICY`: required for auto-registration. Value is a Hugging
  Face repo id or local checkpoint directory, for example
  `lerobot/act_aloha_sim_transfer_cube_human`.
- `LEROBOT_POLICY_TYPE`: optional policy class hint. Supported values include `act`, `diffusion`,
  `tdmpc`, `vqbet`, `pi0`, `pi0fast`, `sac`, and `smolvla`.
- `LEROBOT_DEVICE`: optional device string passed to `policy.to(...)`. Defaults to `cpu`.
- `LEROBOT_CACHE_DIR`: optional Hugging Face cache directory.
- `LEROBOT_EMBODIMENT_TAG`: optional metadata for the robot embodiment.

The adapter does not add LeRobot, PyTorch, NumPy, checkpoints, simulation packages, or robot
runtime dependencies to WorldForge's base install.

Runtime manifest:
`src/worldforge/providers/runtime_manifests/lerobot.json` records the policy path aliases,
optional device/cache settings, host-owned checkpoint and translator artifacts, minimum smoke
command, and expected policy selection signal.

## Runtime Contract

Direct construction with an injected test policy or host-owned policy:

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

Supported loading modes are explicit:

- injected `policy=...` for tests or host-managed runtimes
- injected `policy_loader=...` for host-owned custom loading
- `PreTrainedPolicy.from_pretrained(...)` for the configured path
- typed policy-class loading when `LEROBOT_POLICY_TYPE` is set

Without an injected policy, WorldForge lazily imports `PreTrainedPolicy` and loads the configured
checkpoint. If `LEROBOT_POLICY_TYPE` is set, it resolves the specific policy class before calling
`from_pretrained(...)`.

After loading, the adapter calls `policy.to(device)`, `policy.eval()`,
`policy.requires_grad_(False)`, and `policy.reset()` when those methods exist. The default device is
`cpu`; hosts must opt into `cuda`, `mps`, or another runtime-specific device with `LEROBOT_DEVICE`
or `device=`.

## Input Contract

```python
result = forge.select_actions(
    "lerobot",
    info={
        "observation": {
            "observation.state": state_tensor_or_array,
            "observation.images.top": image_tensor_or_array,
            "task": "pick up the red cube",
        },
        "embodiment_tag": "aloha",
        "action_horizon": 16,
        "options": {},
        "mode": "select_action",
    },
)
```

Validation rules:

- `info["observation"]` must be a non-empty JSON object.
- Observation keys should follow LeRobot conventions such as `observation.state`,
  `observation.images.<camera>`, and `task`.
- `info["options"]`, when supplied, must be a JSON object.
- `info["mode"]` is `select_action` or `predict_chunk`.
- `predict_chunk` requires a policy that implements `predict_action_chunk`.
- Tensor-like values with `tolist()` are normalized for metadata and raw-action preservation.
- A host-supplied `action_translator` is required before `ActionPolicyResult` can be returned.
- Result metadata includes `loader_mode` and a bounded `raw_action_summary` with type, rectangular
  shape when available, and a small preview suitable for run reports.

## Action Translation

LeRobot action tensors are embodiment-specific: a 7-DoF arm, a bimanual setup, a mobile base, or a
custom robot may all encode actions differently. The translator owns that mapping:

```python
from worldforge import Action

def translate_actions(raw_actions, info, provider_info):
    tensor = raw_actions.tolist() if hasattr(raw_actions, "tolist") else raw_actions
    return [
        Action.move_to(float(x), float(y), float(z))
        for (x, y, z) in tensor[0]
    ]
```

The translator may return:

- a single action chunk: `[Action.move_to(...), Action.move_to(...)]`
- multiple candidate chunks: `[[Action.move_to(...)], [Action.move_to(...)] ]`

Multiple candidates are useful for policy-plus-score planning.

Use `EmbodimentTranslatorContract` and `EmbodimentActionTranslator` when a translator has a known
robot or task boundary:

```python
from worldforge import Action
from worldforge.providers import EmbodimentActionTranslator, EmbodimentTranslatorContract

contract = EmbodimentTranslatorContract(
    embodiment_tag="aloha",
    action_dim=3,
    action_horizon=16,
    metadata={"controller": "host-owned", "units": "meters"},
)

def translate_actions(raw_actions, info, provider_info):
    tensor = raw_actions.tolist() if hasattr(raw_actions, "tolist") else raw_actions
    return [Action.move_to(float(x), float(y), float(z)) for (x, y, z) in tensor]

translator = EmbodimentActionTranslator(contract, translate_actions)
```

The contract validates the incoming `embodiment_tag`, rectangular numeric raw actions, finite
values, optional action dimension, optional horizon, JSON-native metadata, and returned candidate
cardinality. It fails before planning on unknown embodiment tags or shape mismatches instead of
padding, projecting, or silently dropping policy outputs. The provider stores a
`translator_contract` summary in `ActionPolicyResult.metadata` so run artifacts can cite the
validated translation boundary without including robot credentials or controller state.

The packaged PushT robotics showcase uses this wrapper for its visual `x, y` translator while the
separate LeWorldModel candidate builder owns the checkpoint-native 10-dimensional score tensor.
Hosts should follow the same split: WorldForge validates the boundary and preserves provenance;
host code owns preprocessing, controller semantics, safety interlocks, and any hardware execution.

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

WorldForge serializes policy candidates into `Action.to_dict()` payloads before calling the score
provider unless `score_action_candidates=...` supplies model-native candidates.

## Runtime Checks

Checkout-safe end-to-end demo:

```bash
uv run worldforge-demo-lerobot
uv run worldforge-demo-lerobot --json-only
```

The demo injects a deterministic policy into the real `LeRobotPolicyProvider`. It validates the
WorldForge policy-plus-score path without requiring LeRobot, torch, or checkpoints.

Real policy smoke:

```bash
uv run python scripts/smoke_lerobot_policy.py \
  --policy-path lerobot/act_aloha_sim_transfer_cube_human \
  --observation-module /path/to/obs.py:build_observation \
  --translator /path/to/translator.py:translate_actions \
  --device cpu
```

This requires a host-owned LeRobot install, policy checkpoint, observation source, and
embodiment-specific action translator.

LeRobot + LeWorldModel robotics replay showcase:

```bash
scripts/robotics-showcase
```

This is the real-checkpoint counterpart to `worldforge-demo-lerobot` for the packaged PushT
showcase. Full runnable context lives in [CLI Reference](../cli.md),
[Examples And CLI Commands](../examples.md), and
[Robotics Replay Showcase](../robotics-showcase.md).

## Failure Modes

- Missing `LEROBOT_POLICY_PATH` and `LEROBOT_POLICY` leaves the provider unregistered.
- Missing `lerobot` or `PreTrainedPolicy` is reported by `health()`.
- Local-looking checkpoint paths that do not exist are reported by `health()` before runtime import.
- Unsupported `LEROBOT_POLICY_TYPE` values fail during provider construction.
- Policy class resolution or checkpoint loading failures are wrapped in `ProviderError`.
- Missing `action_translator` fails with `ProviderError`.
- Contracted translators fail on unknown embodiment tags, non-finite raw action values, raw action
  shape mismatches, and candidate cardinality mismatches.
- Malformed observations, options, or modes fail before invoking the policy.
- Requesting `mode="predict_chunk"` against a policy without `predict_action_chunk` fails
  explicitly.
- Non-JSON-compatible raw actions or provider info fail before returning `ActionPolicyResult`.
- Failed policy inference is wrapped in `ProviderError`.

## Tests

- `tests/test_lerobot_provider.py` covers injected-policy contract checks, event emission, malformed
  inputs, missing translator, unconfigured health, env configuration, lazy import,
  select/predict_chunk modes, reset delegation, auto-registration, translator contracts, and
  policy-plus-score planning.
- `tests/test_lerobot_e2e_demo.py` covers the full checkout-safe demo.
- `tests/test_lerobot_smoke_script.py` covers smoke-script input loading, callable resolution, and
  validation without requiring LeRobot or a GPU.
- `tests/test_lerobot_leworldmodel_smoke_script.py` and `tests/test_robotics_showcase.py` cover
  the combined real-runtime runner, packaged showcase defaults, dynamic candidate bridge behavior,
  and JSON output.

## Primary References

- [Hugging Face LeRobot code](https://github.com/huggingface/lerobot)
- [LeRobot policy documentation](https://huggingface.co/docs/lerobot/bring_your_own_policies)
- [LeRobot PushT diffusion policy](https://huggingface.co/lerobot/diffusion_pusht)

# GR00T Provider

Status: experimental host-owned policy-client adapter

Taxonomy category: embodied policy / VLA action model

This adapter wraps NVIDIA Isaac GR00T's policy-client shape. GR00T is modeled as an actor: it
accepts multimodal observations and language instructions, then returns robot action chunks. It is
not modeled as a predictive world model, video generator, or candidate scorer.

```text
observation + language instruction -> action chunk
```

WorldForge keeps the boundary explicit:

```text
GR00T policy client
  -> raw embodiment-specific action arrays
  -> host-supplied action_translator
  -> ActionPolicyResult
  -> World.plan(... planning_mode="policy")
```

For actor plus world-model planning:

```text
GR00T proposes candidate action chunks
  -> LeWorldModel / JEPA-WMS / another score provider ranks candidates
  -> World.plan(... planning_mode="policy+score")
  -> execution_provider runs the chosen WorldForge actions
```

## Configuration

- `GROOT_POLICY_HOST`: required for auto-registration. Hostname or IP of a running GR00T policy
  server.
- `GROOT_POLICY_PORT`: optional, defaults to `5555`.
- `GROOT_POLICY_TIMEOUT_MS`: optional, defaults to `15000`.
- `GROOT_POLICY_API_TOKEN`: optional token passed to the policy client.
- `GROOT_POLICY_STRICT`: optional boolean. Defaults to `false` on the client.
- `GROOT_EMBODIMENT_TAG`: optional profile metadata for the robot embodiment.

The adapter does not add Isaac GR00T, PyTorch, CUDA, TensorRT, checkpoints, or robot runtime
dependencies to WorldForge's base install. Those dependencies remain host-owned.

## Policy Runtime Contract

Direct construction with a fake or host-owned client:

```python
from worldforge.providers import GrootPolicyClientProvider

provider = GrootPolicyClientProvider(
    policy_client=client,
    embodiment_tag="LIBERO_PANDA",
    action_translator=translate_actions,
)
```

The injected or lazily created client must expose:

```python
get_action(observation, options=None) -> actions | (actions, info)
```

If no client is injected, WorldForge lazily imports:

```python
from gr00t.policy.server_client import PolicyClient
```

and creates:

```python
PolicyClient(
    host=GROOT_POLICY_HOST,
    port=GROOT_POLICY_PORT or 5555,
    timeout_ms=GROOT_POLICY_TIMEOUT_MS or 15000,
    api_token=GROOT_POLICY_API_TOKEN,
    strict=GROOT_POLICY_STRICT or False,
)
```

## Input Shape

`select_actions(...)` expects:

```python
provider.select_actions(
    info={
        "observation": {
            "video": {"front": video_array},
            "state": {"eef": state_array},
            "language": {"task": [["pick up the cube"]]},
        },
        "embodiment_tag": "LIBERO_PANDA",
        "action_horizon": 16,
        "options": {},
    }
)
```

`info["observation"]` must be a JSON object and include at least one of `video`, `state`, or
`language`. Arrays may be tensor-like objects with `tolist()` because the adapter normalizes raw
provider output into JSON-compatible metadata.

## Action Translation

GR00T actions are embodiment-specific physical action arrays. WorldForge cannot safely infer what a
joint position, gripper channel, or end-effector delta means for a host robot. The provider
therefore requires an `action_translator` before it can return executable WorldForge `Action`
objects.

```python
from worldforge import Action

def translate_actions(raw_actions, info, provider_info):
    return [
        Action.move_to(0.3, 0.5, 0.0),
        Action.move_to(0.4, 0.5, 0.0),
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

Multiple candidates are useful when pairing GR00T with a score provider.

## Planning

Policy-only planning:

```python
plan = world.plan(
    goal="pick up the cube",
    provider="gr00t",
    policy_info=policy_info,
    execution_provider="mock",
)
```

Policy plus score planning:

```python
plan = world.plan(
    goal="choose the lowest-cost policy candidate",
    policy_provider="gr00t",
    score_provider="leworldmodel",
    policy_info=policy_info,
    score_info=lewm_info,
    execution_provider="mock",
)
```

WorldForge serializes policy candidates into `Action.to_dict()` payloads by default before calling
the score provider. If the scorer needs native tensors or latents, pass
`score_action_candidates=...`; WorldForge only requires that the number of policy candidates and
native score candidates describe the same candidate set.

## Failure Modes

- Missing `GROOT_POLICY_HOST` leaves the auto-registered provider unavailable.
- Missing `gr00t.policy.server_client.PolicyClient` is reported by `health()`.
- Missing `action_translator` fails with `ProviderError`.
- Malformed observations fail before invoking the policy client.
- Non-JSON-compatible raw actions or provider info fail before returning `ActionPolicyResult`.
- Failed policy inference is wrapped in `ProviderError`.
- Policy+score planning fails if the score provider selects an index outside the policy candidate
  list.

## Tests

- `tests/test_gr00t_provider.py` covers fake-client contract checks, event emission, malformed
  inputs, missing translator, health failures, policy-only planning, and policy+score planning.

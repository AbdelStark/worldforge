# GR00T Provider

Capability: `policy`

Taxonomy category: embodied policy / VLA action model

`gr00t` wraps NVIDIA Isaac GR00T's policy-client shape. GR00T is modeled as an actor: it accepts
multimodal observations and language instructions, then returns robot action chunks. It is not
modeled as a predictive world model, video generator, or candidate scorer.

```text
observation + language instruction
  -> GR00T policy client
  -> raw embodiment-specific action arrays
  -> host action_translator
  -> ActionPolicyResult
```

## Runtime Ownership

WorldForge owns provider registration, observation envelope validation, raw-action preservation,
action-result validation, planning composition, and provider events.

The host owns:

- Isaac GR00T installation and dependencies
- reachable policy server
- model checkpoints and robot-specific runtime setup
- observations from sensors, simulator, or logs
- translation from raw policy arrays to WorldForge `Action` objects
- robot execution, safety interlocks, and controller integration

WorldForge never drives hardware directly.

## Configuration

- `GROOT_POLICY_HOST`: required for auto-registration. Hostname or IP of a running GR00T policy
  server.
- `GROOT_POLICY_PORT`: optional, defaults to `5555`.
- `GROOT_POLICY_TIMEOUT_MS`: optional, defaults to `15000`.
- `GROOT_POLICY_API_TOKEN`: optional token passed to the policy client.
- `GROOT_POLICY_STRICT`: optional boolean, defaults to `false`.
- `GROOT_EMBODIMENT_TAG`: optional metadata for the robot embodiment.

The adapter does not add Isaac GR00T, PyTorch, CUDA, TensorRT, checkpoints, or robot runtime
dependencies to WorldForge's base install.

Runtime manifest:
`src/worldforge/providers/runtime_manifests/gr00t.json` records the policy-server environment,
optional client settings, host-owned policy/runtime artifacts, minimum live smoke command, and
expected policy-client health signal.

## Runtime Contract

Maturity: `beta`. Prepared hosts can use the remote PolicyClient path for policy selection when
they provide a reachable server, optional auth token, observation envelope, and action translator.
WorldForge does not start or supervise local GR00T runtime services by default.

Direct construction with an injected test client or host-owned client:

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

Without an injected client, WorldForge lazily imports:

```python
from gr00t.policy.server_client import PolicyClient
```

and creates a client from `GROOT_POLICY_*` settings.

If the full Isaac GR00T package is not importable in the WorldForge process, the provider falls
back to a small ZMQ/msgpack client for the documented PolicyServer protocol. That fallback is useful
for the normal remote-GPU shape because NVIDIA's full `gr00t` runtime is currently Python-3.10
pinned while WorldForge runs on Python 3.13. The fallback still requires host-installed optional
client packages:

```bash
GROOT_POLICY_HOST=127.0.0.1 \
GROOT_POLICY_PORT=5555 \
uv run --with msgpack --with pyzmq --with numpy python scripts/smoke_gr00t_policy.py \
  --health-only \
  --run-manifest .worldforge/runs/gr00t-health/run_manifest.json
```

The GPU server still owns the full Isaac GR00T install, CUDA runtime, checkpoints, and robot-specific
dependencies.

## Input Contract

```python
result = forge.select_actions(
    "gr00t",
    info={
        "observation": {
            "video": {"front": video_array},
            "state": {"eef": state_array},
            "language": {"task": [["pick up the cube"]]},
        },
        "embodiment_tag": "LIBERO_PANDA",
        "action_horizon": 16,
        "options": {},
    },
)
```

Validation rules:

- `info["observation"]` must be a JSON object.
- Observation must include at least one of `video`, `state`, or `language`.
- `options`, when supplied, must be a JSON object.
- Tensor-like values with `tolist()` are normalized for metadata and raw-action preservation.
- A host-supplied `action_translator` is required before `ActionPolicyResult` can be returned.

Provider events emitted by `select_actions()` include operation `policy`, attempt `1`, max attempts
`1`, method `POLICYCLIENT.GET_ACTION`, a sanitized target, elapsed duration, timeout settings, and
the strict-mode flag. Token-like values in messages, targets, or metadata are redacted before they
reach logs or run manifests.

## Action Translation

GR00T actions are embodiment-specific physical action arrays. WorldForge cannot infer joint
meaning, gripper semantics, controller timing, or coordinate frames. The translator owns that
mapping:

```python
from worldforge import Action

def translate_actions(raw_actions, info, provider_info):
    return [
        Action.move_to(0.3, 0.5, 0.0),
        Action.move_to(0.4, 0.5, 0.0),
    ]
```

The translator may return:

- a single action chunk: `[Action.move_to(...), Action.move_to(...)]`
- multiple candidate chunks: `[[Action.move_to(...)], [Action.move_to(...)] ]`

Multiple candidates are useful for policy-plus-score planning.

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

WorldForge serializes policy candidates into `Action.to_dict()` payloads before calling the score
provider unless `score_action_candidates=...` supplies model-native candidates.

For a checkout-safe version of the same policy+score boundary without GR00T, CUDA, or a robot
controller, run `uv run python scripts/demo_showcases.py run policy-score-candidate-lab`. The lab
keeps provider-specific raw actions visible and makes missing translator behavior explicit.

## Live Smoke Evidence

Connect to an existing GR00T policy server:

```bash
GROOT_POLICY_HOST=127.0.0.1 \
GROOT_POLICY_PORT=5555 \
uv run --with msgpack --with pyzmq --with numpy python scripts/smoke_gr00t_policy.py \
  --policy-info-json /path/to/policy_info.json \
  --translator /path/to/translator.py:translate_actions \
  --allow-translator-code \
  --run-manifest .worldforge/runs/gr00t-live/run_manifest.json
```

`--translator` imports and executes local Python code. The smoke command requires
`--allow-translator-code` so operators explicitly opt into running trusted translator code. If
policy inputs are created through `--observation-module`, pass `--allow-observation-code` after
auditing that observation factory too.

Prepared hosts can run a configuration and connectivity check without a policy request:

```bash
GROOT_POLICY_HOST=127.0.0.1 \
GROOT_POLICY_PORT=5555 \
uv run --with msgpack --with pyzmq --with numpy python scripts/smoke_gr00t_policy.py \
  --health-only \
  --run-manifest .worldforge/runs/gr00t-health/run_manifest.json
```

Start the upstream server from a host-owned Isaac-GR00T checkout:

```bash
uv run python scripts/smoke_gr00t_policy.py \
  --start-server \
  --gr00t-root /path/to/Isaac-GR00T \
  --model-path nvidia/GR00T-N1.6-3B \
  --embodiment-tag GR1 \
  --policy-info-json /path/to/policy_info.json \
  --translator /path/to/translator.py:translate_actions \
  --allow-translator-code \
  --run-manifest .worldforge/runs/gr00t-live/run_manifest.json
```

Starting upstream Isaac GR00T requires a compatible NVIDIA/Linux runtime for CUDA and TensorRT
dependencies. On unsupported hosts, connect WorldForge to an already running remote policy server.

For a remote GPU, keep the GR00T server private and connect over an SSH tunnel when possible:

```bash
ssh -N -L 5555:127.0.0.1:5555 ubuntu@<gpu-host>
```

If direct networking is required, restrict the server port to the operator IP or a VPN. Do not
expose a GR00T policy server broadly on the public internet.

Expected success signal:

- `--health-only`: run manifest records `capability=policy` with `status=skipped`.
- Full smoke (`--policy-info-json` or `--observation-json` plus `--translator`): run manifest
  records `capability=policy` with `status=passed`.

First triage step:

- Run `uv run worldforge provider health gr00t` to confirm client configuration and server
  reachability, then re-run the smoke command with `--run-manifest` so the failure has a
  sanitized digest.

The smoke can write a sanitized `run_manifest.json` with value-free environment presence, runtime
manifest id, input fixture digest, event count, and result digest. The manifest does not store
tokens, raw sensor tensors, checkpoint bytes, or robot controller state. Hibernate or terminate
remote GPU instances when the smoke is done.

## Failure Modes

- Missing `GROOT_POLICY_HOST` leaves the provider unregistered.
- Missing `gr00t.policy.server_client.PolicyClient` is reported by `health()`.
- Unreachable policy servers or ping failures are reported by `health()` without leaking tokens.
- Missing `action_translator` fails with `ProviderError`.
- Malformed observations fail before invoking the policy client.
- Non-JSON-compatible raw actions or provider info fail before returning `ActionPolicyResult`.
- Failed policy inference is wrapped in `ProviderError`.
- Starting the upstream server on an unsupported host can fail before WorldForge can connect.
- Policy-plus-score planning fails if the score provider selects an index outside the policy
  candidate list.

## Tests

- `tests/test_gr00t_provider.py` covers injected-client contract checks, event emission, malformed
  inputs, missing translator, health failures, policy-only planning, and policy-plus-score
  planning.
- `tests/test_gr00t_smoke_script.py` covers smoke-script input loading and server preflight
  validation without requiring Isaac GR00T or a GPU.

## Primary References

- [NVIDIA Isaac GR00T code](https://github.com/NVIDIA/Isaac-GR00T)

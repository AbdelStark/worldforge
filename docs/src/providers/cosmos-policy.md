# Cosmos-Policy Provider

Capability: `policy`

Maturity: `beta`

Taxonomy category: embodied policy / robot action model

`cosmos-policy` is an HTTP adapter for a host-owned NVIDIA Cosmos-Policy ALOHA server. It sends an
ALOHA observation and task description to `/act`, validates returned action chunks, preserves raw
policy outputs, and requires a host-supplied translator before returning executable WorldForge
`Action` objects.

```text
ALOHA images + proprio + task text
  -> Cosmos-Policy /act
  -> raw 14D bimanual action chunks
  -> host action_translator
  -> ActionPolicyResult
```

This provider is separate from `cosmos`. `cosmos` is a media-generation adapter for Cosmos NIM
`/v1/infer`; `cosmos-policy` is a policy adapter for robot action selection.

## Runtime Ownership

WorldForge owns provider registration, HTTP request policy, ALOHA envelope validation, response
shape validation, raw-action preservation, planning composition, and provider events.

The host owns:

- NVIDIA Cosmos-Policy checkout, Docker image, CUDA runtime, and GPU host
- model checkpoints and any Hugging Face/NVIDIA access setup
- ALOHA observation construction from sensors, simulator state, or dataset rows
- translation from raw 14-dimensional bimanual action rows to WorldForge `Action` objects
- robot execution, safety interlocks, controller semantics, and artifact retention

WorldForge never starts Cosmos-Policy, installs CUDA dependencies, or drives hardware directly.

## Configuration

- `COSMOS_POLICY_BASE_URL`: required for auto-registration. Example:
  `https://cosmos-policy.example.com`. Localhost/private endpoints are blocked by default.
- `COSMOS_POLICY_API_TOKEN`: optional bearer token sent as `Authorization: Bearer ...`.
- `COSMOS_POLICY_TIMEOUT_SECONDS`: optional policy request timeout. Defaults to `600`.
- `COSMOS_POLICY_EMBODIMENT_TAG`: optional result metadata. Defaults to `aloha`.
- `COSMOS_POLICY_MODEL`: optional model metadata. Defaults to
  `nvidia/Cosmos-Policy-ALOHA-Predict2-2B`.
- `COSMOS_POLICY_RETURN_ALL_QUERY_RESULTS`: optional boolean. When set, request all query results
  from servers that support that Cosmos-Policy flag.
- `COSMOS_POLICY_ALLOW_LOCAL_BASE_URL`: optional boolean. Set to `1` only for trusted localhost,
  SSH tunnel, or lab-network servers.

Runtime manifest:
`src/worldforge/providers/runtime_manifests/cosmos-policy.json` records the required endpoint,
optional token/settings, host-owned runtime artifacts, minimum smoke command, and expected policy
selection signal.

Programmatic construction:

```python
from worldforge.providers import CosmosPolicyProvider

provider = CosmosPolicyProvider(
    base_url="http://127.0.0.1:8777",
    action_translator=translate_actions,
)
```

## Input Contract

```python
result = forge.select_actions(
    "cosmos-policy",
    info={
        "observation": {
            "primary_image": primary_image,
            "left_wrist_image": left_wrist_image,
            "right_wrist_image": right_wrist_image,
            "proprio": proprio,
        },
        "task_description": "put the cube into the bowl",
        "embodiment_tag": "aloha",
        "action_horizon": 16,
        "return_all_query_results": True,
    },
)
```

Validation rules:

- `info["observation"]` must be a non-empty JSON object.
- ALOHA observations must include `primary_image`, `left_wrist_image`, `right_wrist_image`, and
  `proprio`.
- `task_description` must be a non-empty string. It may also be included inside the observation.
- `options`, when supplied, must be a JSON object and must not conflict with observation fields.
- `return_all_query_results`, when supplied in `info`, must be a boolean.
- `action_horizon`, when supplied, must be an integer greater than 0.
- A host-supplied `action_translator` is required before `ActionPolicyResult` can be returned.

## Response Contract

The `/act` response must include:

```json
{
  "actions": [[0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0]]
}
```

WorldForge validates:

- `actions` is a non-empty rectangular numeric matrix
- each action row has the configured action dimension, defaulting to 14
- `value_prediction`, when present, is finite
- `all_actions`, when present, is a non-empty list of candidate action matrices
- `all_value_predictions`, when present, is a list of finite numbers
- future image prediction fields are summarized by bounded shape instead of copied into metadata

Returned metadata includes the model label, selected candidate index, candidate count, provider
info, raw action shape summary, and task description. Raw future image tensors are not stored in
public metadata.

## Action Translation

Cosmos-Policy ALOHA actions are embodiment-specific physical control rows. WorldForge validates
their shape but does not infer joint semantics, gripper meaning, controller timing, or coordinate
frames. The host translator owns that boundary:

```python
from worldforge import Action

def translate_actions(raw_actions, info, provider_info):
    rows = raw_actions["actions"]
    return [
        Action.move_to(float(row[0]), float(row[1]), float(row[2]))
        for row in rows
    ]
```

The translator may return:

- a single action chunk: `[Action.move_to(...), Action.move_to(...)]`
- multiple candidate chunks: `[[Action.move_to(...)], [Action.move_to(...)] ]`

Multiple candidates are useful for policy-plus-score planning when the server returns
`all_actions`.

## Planning

Policy-only planning:

```python
plan = world.plan(
    goal="put the cube into the bowl",
    provider="cosmos-policy",
    policy_info=policy_info,
    execution_provider="mock",
)
```

Policy plus score planning:

```python
plan = world.plan(
    goal="choose the lowest-cost Cosmos-Policy candidate",
    policy_provider="cosmos-policy",
    score_provider="leworldmodel",
    policy_info=policy_info,
    score_info=lewm_info,
    execution_provider="mock",
)
```

WorldForge serializes translated policy candidates into `Action.to_dict()` payloads before calling
the score provider unless `score_action_candidates=...` supplies model-native score candidates.

## Live Smoke Evidence

Connect to a running Cosmos-Policy ALOHA server:

```bash
COSMOS_POLICY_BASE_URL=http://127.0.0.1:8777 \
COSMOS_POLICY_ALLOW_LOCAL_BASE_URL=1 \
  uv run worldforge-smoke-cosmos-policy \
    --policy-info-json /path/to/policy_info.json \
    --translator /path/to/translator.py:translate_actions \
    --run-manifest .worldforge/runs/cosmos-policy-live/run_manifest.json
```

Prepared hosts can also pass `--health-only` to validate WorldForge configuration without sending
a policy request. Cosmos-Policy does not expose a non-mutating health endpoint in the server shape
this adapter targets, so health checks confirm configuration only; live inference evidence comes
from `select_actions(...)` or the smoke command above.

The smoke can write a sanitized `run_manifest.json` with value-free environment presence, runtime
manifest id, input fixture digest, event count, and result digest. The manifest does not store
tokens, raw image tensors, checkpoint bytes, or robot controller state.

## Failure Modes

- Missing `COSMOS_POLICY_BASE_URL` leaves the provider unregistered.
- Missing `action_translator` fails with `ProviderError`.
- Malformed observations fail before invoking the policy server.
- Unreachable servers, non-success HTTP statuses, invalid JSON, or malformed response shapes fail
  as provider errors.
- Non-finite raw action values fail before returning `ActionPolicyResult`.
- Policy-plus-score planning fails if a score provider selects a candidate index outside the
  translated policy candidate list.
- Running upstream Cosmos-Policy requires a compatible Linux/NVIDIA runtime. On unsupported hosts,
  connect WorldForge to a remote server instead of trying to install CUDA dependencies into
  WorldForge.

## Tests

- `tests/test_cosmos_policy_provider.py` covers provider contract checks, request payload shape,
  candidate/value preservation, missing translator failures, malformed observations, malformed
  responses, policy-only planning, and policy-plus-score planning.
- `tests/test_cosmos_policy_smoke_script.py` covers the live-smoke entry point without requiring
  Cosmos-Policy, a GPU, or network access.

## Primary References

- [NVIDIA Cosmos-Policy code](https://github.com/nvlabs/cosmos-policy)
- [NVIDIA Cosmos documentation](https://docs.nvidia.com/cosmos/latest/)

# Cosmos-Policy Provider

Runtime capability: `policy` when the provider is constructed with a host
`action_translator`

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
- `COSMOS_POLICY_ALLOWED_HOSTS`: optional comma-separated hostname allowlist for deployments that
  restrict the configured policy endpoint. Shell-style wildcards such as `*.example.com` are
  supported.

URL validation rejects obvious localhost/private/link-local destinations during preflight by
default. DNS checks are best-effort checks before `httpx` connects; they do not pin the TCP
connection to a resolved address. Use host allowlists plus network egress controls when that
distinction matters.

`COSMOS_POLICY_BASE_URL` is enough for endpoint readiness checks. It is not enough for policy
routing: a provider instance without `action_translator` advertises no executable `policy`
capability.

Runtime manifest:
`src/worldforge/providers/runtime_manifests/cosmos-policy.json` records the required endpoint,
optional token/settings, host-owned runtime artifacts, minimum smoke command, and expected policy
selection signal.

Programmatic construction:

```python
from worldforge.providers import CosmosPolicyProvider

provider = CosmosPolicyProvider(
    base_url="http://127.0.0.1:8777",
    allow_local_base_url=True,
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

## Remote GPU Runbook

Use this path when Cosmos-Policy is running on a rented or lab GPU and WorldForge is running from
a local checkout or separate operator host. The boundary stays explicit: the NVIDIA host owns the
server, checkpoint, CUDA runtime, Hugging Face or NVIDIA access, and robot-specific preprocessing.
WorldForge owns the request, response, action-shape validation, action translation boundary,
provider events, and smoke manifest.

### 1. Prepare the GPU host

Recommended host shape:

- 48 GB or larger GPU memory class for the current ALOHA Predict2 path. Use the upstream
  Cosmos-Policy requirements when they are stricter.
- Linux host with working NVIDIA drivers plus the CUDA/Docker runtime required by the upstream
  Cosmos-Policy checkout.
- Access to the required checkpoint files and any gated model approvals. Keep tokens on the GPU
  host or secret manager, not in WorldForge docs, commits, run manifests, or provider events.
- A Cosmos-Policy server listening on `/act`, usually on TCP port `8777`.
- No robot hardware requirement for the smoke path. The smoke sends prepared ALOHA observations
  and translates the returned action chunk into WorldForge actions.

Success signal: the upstream server process is alive, the GPU is visible on the host, and the
server is listening on the configured `/act` port.

First triage: inspect the upstream server logs, confirm the model finished loading, and confirm
the host GPU with the platform's normal NVIDIA tooling before changing WorldForge code.

### 2. Expose the endpoint narrowly

Prefer an SSH tunnel from the operator machine to the GPU host:

```bash
ssh -N -L 8777:127.0.0.1:8777 <user>@<gpu-host>
```

Then point WorldForge at localhost and explicitly allow the trusted local endpoint:

```bash
COSMOS_POLICY_BASE_URL=http://127.0.0.1:8777 \
COSMOS_POLICY_ALLOW_LOCAL_BASE_URL=1 \
  uv run worldforge provider health cosmos-policy
```

If a public or private network URL is required instead, restrict inbound TCP `8777` to the
operator IP or VPN CIDR and set `COSMOS_POLICY_ALLOWED_HOSTS` to the exact host name or IP.
Do not expose the policy server world-open.

### 3. Configure WorldForge

| Setting | Required | Use |
| --- | --- | --- |
| `COSMOS_POLICY_BASE_URL` | yes | Base URL for the host-owned `/act` server. |
| `COSMOS_POLICY_ALLOW_LOCAL_BASE_URL=1` | only for tunnels/lab localhost | Allows trusted localhost, private, or lab-network URLs. |
| `COSMOS_POLICY_ALLOWED_HOSTS` | recommended for network URLs | Restricts the configured endpoint to known hosts. |
| `COSMOS_POLICY_API_TOKEN` | optional | Bearer token for a reverse proxy or protected server. |
| `COSMOS_POLICY_TIMEOUT_SECONDS` | optional | Request timeout for slow first inference. Defaults to `600`. |

`COSMOS_POLICY_BASE_URL` is enough for endpoint readiness checks. A provider instance still needs
a trusted host `action_translator` before it can return executable policy actions.

For a checkout-safe side-by-side policy replay comparison across LeRobot, GR00T, and Cosmos-Policy,
run `uv run python scripts/demo_showcases.py run embodied-policy-replay-comparison`. Use the report
to inspect the 50 x 14 ALOHA action rows, value prediction metadata, and translator blockers before
moving to the prepared-host `uv run worldforge-smoke-cosmos-policy --help` path.

### 4. Run the health-only smoke

Prepared hosts can pass `--health-only` to validate WorldForge configuration without sending a
policy request. Cosmos-Policy does not expose a non-mutating health endpoint in the server shape
this adapter targets, so health checks confirm configuration only; live inference evidence comes
from `select_actions(...)` or the full smoke command below.

```bash
COSMOS_POLICY_BASE_URL=http://127.0.0.1:8777 \
COSMOS_POLICY_ALLOW_LOCAL_BASE_URL=1 \
  uv run worldforge-smoke-cosmos-policy \
    --health-only \
    --run-manifest .worldforge/runs/cosmos-policy-health/run_manifest.json
```

Expected success signal: `run_manifest.json` records `capability=policy` with `status=skipped`.

First triage: run `uv run worldforge provider health cosmos-policy` to confirm configuration,
then check tunnel/firewall reachability before sending a full `/act` request.

### 5. Run the full `/act` smoke

The full smoke requires ALOHA policy information to be prepared and a trusted action translator to
be provided. The translator is host code, so the command requires `--allow-translator-code` as an
explicit opt-in.

Connect to a running Cosmos-Policy ALOHA server:

```bash
COSMOS_POLICY_BASE_URL=http://127.0.0.1:8777 \
COSMOS_POLICY_ALLOW_LOCAL_BASE_URL=1 \
  uv run worldforge-smoke-cosmos-policy \
    --policy-info-json /path/to/policy_info.json \
    --translator /path/to/translator.py:translate_actions \
    --allow-translator-code \
    --run-manifest .worldforge/runs/cosmos-policy-live/run_manifest.json
```

Expected success signal: `run_manifest.json` records `capability=policy` with `status=passed`,
the summary includes a non-empty action shape such as `50 x 14`, and provider events stay
sanitized.

First triage: if configuration is healthy but the full smoke fails, inspect the GPU server logs,
the `policy_info.json` ALOHA observation shape, the translator import path, and the raw action
shape. The live RTX A6000 validation found that real Cosmos responses can use `json_numpy`-style
action rows rather than plain JSON rows; WorldForge decodes and validates that shape before
translation.

The smoke can write a sanitized `run_manifest.json` with value-free environment presence, runtime
manifest id, input fixture digest, event count, and result digest. The manifest does not store
tokens, raw image tensors, checkpoint bytes, or robot controller state.

### 6. Shut down or preserve evidence

Copy only sanitized evidence such as `run_manifest.json`, provider event counts, result digests,
and small checkout-safe replay artifacts. Do not commit GPU logs with tokens, raw images, raw
future tensors, checkpoint files, Docker layers, or downloaded datasets.

Hibernate or terminate the GPU host when the smoke is done. Cloud billing usually continues while
the VM is running, and hibernated machines can still incur disk or public IP charges.

## Live Smoke Evidence

Use the runbook above to produce live evidence. A committed replay artifact should be sanitized
and deterministic; it should not be described as a committed live GPU artifact unless the raw
runtime output is intentionally preserved outside the repository.

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

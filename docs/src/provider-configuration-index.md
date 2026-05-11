# Provider Configuration Index

This index is generated from the in-repo provider catalog, provider profiles, request policies, and
runtime manifests. It is the operator-facing contract for which inputs enable each provider, which
optional packages stay host-owned, which assets the host must preserve, and which command to run
first when configuration fails.

Evidence levels:

- `scaffold`: name reservation only; no real runtime capability is claimed.
- `fixture-tested`: deterministic in-repo behavior is covered by local tests and fixtures.
- `prepared-host`: WorldForge ships a runtime manifest and smoke command, but the host supplies
  credentials, endpoints, optional packages, checkpoints, or robot-specific assets.
- `live-smoke`: a prepared host has preserved a sanitized run manifest for the provider and
  capability in the [Live Smoke Evidence Registry](./live-smoke-evidence.md).

WorldForge never stores secrets, host-local endpoint values, checkpoint archives, or robot
controller credentials in this index.

<!-- provider-config-index:start -->
| Provider | Evidence level | Required inputs | Optional inputs | Optional packages | Prepared-host assets | Default timeouts | First diagnostic |
| --- | --- | --- | --- | --- | --- | --- | --- |
| [`mock`](providers/README.md) | `fixture-tested` | none | none | none | none | none | `uv run worldforge provider health mock` |
| [`cosmos`](providers/cosmos.md) | `prepared-host` | `COSMOS_BASE_URL` | `NVIDIA_API_KEY` | none | generated video bytes<br>artifact retention path | health 10s x3; request 300s x1; poll 30s x3; download 300s x3 | `uv run worldforge provider health cosmos` |
| [`cosmos-policy`](providers/cosmos-policy.md) | `prepared-host` | `COSMOS_POLICY_BASE_URL` | `COSMOS_POLICY_API_TOKEN`, `COSMOS_POLICY_TIMEOUT_SECONDS`, `COSMOS_POLICY_EMBODIMENT_TAG`, `COSMOS_POLICY_MODEL`, `COSMOS_POLICY_RETURN_ALL_QUERY_RESULTS`, `COSMOS_POLICY_ALLOW_LOCAL_BASE_URL`, `COSMOS_POLICY_ALLOWED_HOSTS` | nvidia/cosmos-policy server | Cosmos-Policy Docker/runtime environment<br>ALOHA policy server<br>model checkpoints<br>observation builder<br>action translator | health 10s x3; request 600s x1; poll 30s x3; download 600s x3 | `uv run worldforge provider health cosmos-policy` |
| [`runway`](providers/runway.md) | `prepared-host` | `RUNWAYML_API_SECRET` or `RUNWAY_API_SECRET` | `RUNWAYML_BASE_URL`, `RUNWAYML_ALLOW_LOCAL_ARTIFACT_URLS`, `RUNWAYML_RESOLVE_ARTIFACT_DNS` | none | Runway task ids<br>downloaded video artifacts<br>artifact retention path | health 10s x3; request 120s x1; poll 30s x3; download 120s x3 | `uv run worldforge provider health runway` |
| [`leworldmodel`](providers/leworldmodel.md) | `prepared-host` | `LEWORLDMODEL_POLICY` or `LEWM_POLICY` | `STABLEWM_HOME`, `LEWORLDMODEL_CACHE_DIR`, `LEWORLDMODEL_DEVICE` | torch<br>stable_worldmodel | LeWorldModel checkpoint<br>checkpoint cache<br>task-shaped tensors | none | `uv run worldforge provider health leworldmodel` |
| [`gr00t`](providers/gr00t.md) | `prepared-host` | `GROOT_POLICY_HOST` | `GROOT_POLICY_PORT`, `GROOT_POLICY_TIMEOUT_MS`, `GROOT_POLICY_API_TOKEN`, `GROOT_POLICY_STRICT`, `GROOT_EMBODIMENT_TAG` | gr00t.policy.server_client<br>msgpack<br>numpy<br>pyzmq | GR00T policy server<br>embodiment assets<br>action translator | none | `uv run worldforge provider health gr00t` |
| [`lerobot`](providers/lerobot.md) | `prepared-host` | `LEROBOT_POLICY_PATH` or `LEROBOT_POLICY` | `LEROBOT_POLICY_TYPE`, `LEROBOT_DEVICE`, `LEROBOT_CACHE_DIR`, `LEROBOT_EMBODIMENT_TAG` | lerobot | policy checkpoint<br>policy cache<br>embodiment action translator | none | `uv run worldforge provider health lerobot` |
| [`jepa`](providers/jepa.md) | `prepared-host` | `JEPA_MODEL_NAME` | `JEPA_DEVICE`, `JEPA_MODEL_PATH` | torch | JEPA-WMS checkpoint<br>torch-hub cache<br>task-shaped observation, goal, and action tensors | none | `uv run worldforge provider health jepa` |
| [`genie`](providers/genie.md) | `scaffold` | `GENIE_API_KEY` | none | none | none | none | `uv run worldforge provider health genie` |

## Prepared-Host Smoke Commands

| Provider | Smoke command | Credential gate | Runtime ownership |
| --- | --- | --- | --- |
| `mock` | `not smoke-testable from WorldForge` | none | in-repo deterministic local provider |
| `cosmos` | `COSMOS_BASE_URL=https://cosmos.example uv run worldforge-smoke-cosmos --run-manifest .worldforge/runs/cosmos-live/run_manifest.json` | `NVIDIA_API_KEY` | host supplies a reachable Cosmos deployment and optional `NVIDIA_API_KEY` |
| `cosmos-policy` | `COSMOS_POLICY_BASE_URL=http://127.0.0.1:8777 COSMOS_POLICY_ALLOW_LOCAL_BASE_URL=1 uv run worldforge-smoke-cosmos-policy --policy-info-json /path/to/policy_info.json --translator /path/to/translator.py:translate_actions --allow-translator-code` | `COSMOS_POLICY_API_TOKEN` | WorldForge validates `/act` request/response and planning composition; host owns Cosmos-Policy reachability/CUDA/runtime, ALOHA observation construction, and translation of raw 14D rows into executable `Action` objects |
| `runway` | `RUNWAYML_API_SECRET=<secret> uv run worldforge-smoke-runway --run-manifest .worldforge/runs/runway-live/run_manifest.json` | `RUNWAYML_API_SECRET`, `RUNWAY_API_SECRET` | host supplies Runway credentials and persists returned artifacts |
| `leworldmodel` | `scripts/lewm-real --checkpoint ~/.stable-wm/pusht/lewm_object.ckpt --device cpu` | none | host installs the official LeWM loading path (`stable_worldmodel.policy.AutoCostModel`), torch, and compatible checkpoints |
| `gr00t` | `GROOT_POLICY_HOST=127.0.0.1 GROOT_POLICY_PORT=5555 uv run --with msgpack --with pyzmq --with numpy python scripts/smoke_gr00t_policy.py --health-only --run-manifest .worldforge/runs/gr00t-health/run_manifest.json` | `GROOT_POLICY_API_TOKEN` | host runs or reaches an Isaac GR00T policy server |
| `lerobot` | `scripts/smoke_lerobot_policy.py --policy-path <repo-or-checkpoint> --device cpu` | none | host installs LeRobot and compatible policy checkpoints |
| `jepa` | `uv run --with torch worldforge-smoke-jepa-wms --model-name jepa_wm_pusht --device cpu` | none | host supplies torch, facebookresearch/jepa-wms runtime dependencies, and task preprocessing |
| `genie` | `not smoke-testable from WorldForge` | `GENIE_API_KEY` | capability-fail-closed reservation; Project Genie has no supported automation API contract |
<!-- provider-config-index:end -->

The generated block is checked by:

```bash
uv run python scripts/generate_provider_docs.py --check
```

When a provider changes its profile, environment variables, runtime manifest, smoke command, or
request policy, regenerate this page and inspect the diff before publishing.

# JEPA-WMS Provider Candidate

Capability: direct-construction `score` candidate

Taxonomy category: JEPA latent predictive world model

`jepa-wms` is a candidate scaffold for future work against
[`facebookresearch/jepa-wms`](https://github.com/facebookresearch/jepa-wms). It exists to make the
planned score-provider contract explicit without claiming runtime support in the public provider
registry.

It is intentionally not exported from `worldforge.providers`, not present in
`PROVIDER_CATALOG`, and not auto-registered. Tests and host experiments may import
`worldforge.providers.jepa_wms.JEPAWMSProvider` directly.

## Promotion Rule

Do not export or auto-register this provider until the integration has:

- a validated upstream runtime path against real weights
- documented checkpoint, device, task-family, and batch limits
- a stable mapping between JEPA-WMS candidate tensors and WorldForge `Action` sequences
- fixture coverage for malformed inputs, upstream errors, and invalid outputs
- a live smoke path that does not hide optional dependency requirements

Current decision: keep `jepa-wms` as a direct-construction candidate. Even when a prepared host
successfully runs the smoke command below, WorldForge should not auto-register it until there is
checked-in real-runtime evidence for the selected upstream model and task family.

## Runtime Ownership

WorldForge owns the candidate provider shell, score-result validation, event emission, and
score-planning tests.

The host owns:

- PyTorch and JEPA-WMS dependencies
- model download and checkpoint compatibility
- optional torch-hub loading
- observation, goal, action-history, and candidate preprocessing
- mapping between model-native actions and WorldForge `Action` objects

WorldForge does not add JEPA-WMS, torch, datasets, checkpoints, or simulator dependencies to its
base package.

## Direct Construction

Injected runtime:

```python
from worldforge.providers.jepa_wms import JEPAWMSProvider

provider = JEPAWMSProvider(
    model_path="/models/jepa-wms/checkpoint.pt",
    runtime=test_or_host_runtime,
)
```

The injected runtime must be callable or expose:

```python
score_actions(*, model_path: str, info: dict, action_candidates: object) -> object
```

Torch-hub runtime:

```python
from worldforge.providers.jepa_wms import JEPAWMSProvider

provider = JEPAWMSProvider.from_torch_hub(
    model_name="jepa_wm_pusht",
    device="cpu",
)
```

The torch-hub runtime lazily imports torch and loads:

```python
model, preprocessor = torch.hub.load(
    "facebookresearch/jepa-wms",
    "jepa_wm_pusht",
)
```

It first delegates to model-native scoring methods when present. If the loaded model does not
expose a scoring method, it uses the planning shape:

```text
observation -> model.encode(..., act=True) -> z_init
goal        -> model.encode(..., act=False) -> z_goal
actions     -> model.unroll(z_init, act_suffix=actions)
score       -> latent L1/L2 distance between final predicted latent and goal latent
```

## Input Contract

Required score inputs:

- `info["observation"]`: tensor-like object or rectangular nested finite numeric sequence with at
  least two dimensions
- `info["goal"]`: tensor-like object or rectangular nested finite numeric sequence with at least
  two dimensions
- `info["action_history"]`: optional tensor-like object or rectangular nested finite numeric
  sequence with at least two dimensions
- `action_candidates`: tensor-like object or rectangular nested finite numeric sequence shaped as
  `(batch, samples, horizon, action_dim)`

The torch-hub runtime supports exactly one batch and returns one score per sample. Batched score
semantics remain undefined in the public `ActionScoreResult` contract.

`score_info` keys:

- `observation`: observation payload accepted by the upstream model
- `goal`: goal payload accepted by the upstream model
- `objective`: optional, `l2` by default; `l1` is also supported
- `actions_are_normalized`: optional, `true` by default. Set `false` only when the loaded
  preprocessor exposes `normalize_actions(...)`. This value must be a JSON boolean, not a string.

## Runtime Response Contract

Success:

```json
{
  "scores": [0.4, 0.12, 0.9],
  "lower_is_better": true,
  "metadata": {
    "score_units": "latent_cost"
  }
}
```

Failure:

```json
{
  "error": {
    "type": "checkpoint_expired",
    "message": "checkpoint artifact is expired or unavailable"
  }
}
```

`best_index` is optional. If omitted, WorldForge derives it from `scores` and
`lower_is_better`. Failure responses become `ProviderError` and emit a failure event.

## Planning

The candidate can be registered manually for local score-planning experiments:

```python
forge = WorldForge(auto_register_remote=False)
forge.register_provider(provider)

plan = world.plan(
    goal="choose the lowest latent-distance candidate",
    provider="jepa-wms",
    candidate_actions=[candidate_a, candidate_b],
    score_info=score_info,
    score_action_candidates=action_candidate_tensor,
    execution_provider="mock",
)
```

Do not present this as public jepa-wms support until the promotion rule is satisfied.

## Prepared-Host Smoke

Prepared hosts can validate the host-owned torch-hub path and preserve issue-safe evidence:

```bash
uv run --with torch worldforge-smoke-jepa-wms \
  --model-name jepa_wm_pusht \
  --device cpu \
  --json-output .worldforge/runs/jepa-wms-live/results/summary.json \
  --run-manifest .worldforge/runs/jepa-wms-live/run_manifest.json
```

The command imports `torch` only at runtime, calls `JEPAWMSProvider.from_torch_hub(...)`, scores
synthetic observation, goal, action-history, and action-candidate tensors, and writes a sanitized
`run_manifest.json`. The manifest includes value-free environment presence, input shapes, runtime
version fields such as torch version/model class, event count, and a score summary with candidate
count, score direction, best index, and best score.

The smoke command does not download or pin checkpoints for users. Hosts remain responsible for the
compatible `facebookresearch/jepa-wms` runtime, model names, checkpoint availability, device
selection, and task preprocessing.

## Failure Modes

- Missing model path fails provider construction or health.
- Missing runtime keeps health unhealthy.
- Runtime error payloads become `ProviderError`.
- Missing observation or goal fields fail before runtime invocation.
- Ragged nested arrays, non-finite values, unsupported action-candidate shape, multi-batch
  tensors, and score-count mismatches fail explicitly.
- Missing torch-hub loader, unsupported objective, action normalization failures, and unexpected
  runtime exceptions are wrapped in `ProviderError`.

## Tests

- `tests/test_jepa_wms_provider.py` covers injected runtime scoring, torch-hub runtime behavior,
  malformed inputs, runtime error payloads, non-finite scores, score-count mismatches, provider
  contract checks, score planning, provider events, and the prepared-host smoke manifest contract.
- `tests/fixtures/providers/jepa_wms_*.json` stores the contract fixtures.

## Primary References

- [facebookresearch/jepa-wms](https://github.com/facebookresearch/jepa-wms)
- [V-JEPA 2 paper](https://arxiv.org/abs/2506.09985)

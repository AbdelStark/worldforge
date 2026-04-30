# JEPA Provider

Capability: `score`

Taxonomy category: JEPA latent predictive world model

`jepa` is the public, score-only JEPA adapter. The first runtime surface is intentionally narrow:
it scores candidate action tensors with upstream JEPA-WM models and returns `ActionScoreResult`.
It does not expose `predict`, `embed`, `generate`, `transfer`, or `reason`.

## Provider Selection RFC

Decision: use [`facebookresearch/jepa-wms`](https://github.com/facebookresearch/jepa-wms) as the
first public JEPA runtime path, via `torch.hub.load("facebookresearch/jepa-wms", model_name)`.

Why this surface:

- the upstream repository publishes JEPA-WM checkpoints and torch-hub model entry points;
- the upstream planning interface is naturally a candidate-action cost model, so `score` is the
honest WorldForge capability;
- WorldForge already has score-planning contracts and run evidence through the `jepa-wms`
direct-construction candidate;
- `predict` and `embed` would require a separate latent rollout or representation contract that is
not stable enough to expose by default.

Initial model names documented by upstream include `jepa_wm_pusht`, `jepa_wm_droid`,
`jepa_wm_metaworld`, `jepa_wm_pointmaze`, and `jepa_wm_wall`. Use `jepa_wm_pusht` for the
smallest public smoke path unless your host has validated another task family.

## Runtime Ownership

WorldForge owns:

- provider registration and score capability declaration;
- input shape validation before runtime calls;
- score-result validation, best-index selection, and provider events;
- score-planning integration and contract tests.

The host owns:

- installing PyTorch and upstream JEPA-WMS dependencies;
- downloading compatible checkpoints and any optional encoder assets;
- selecting `JEPA_MODEL_NAME`;
- converting observations, goals, action history, and action candidates into task-shaped tensors;
- preserving live smoke evidence for the selected model, checkpoint, and task.

WorldForge does not add PyTorch, JEPA-WMS, datasets, checkpoints, simulators, or robot
preprocessing dependencies to its base package.

## Configuration

Required:

- `JEPA_MODEL_NAME`: upstream torch-hub model name, for example `jepa_wm_pusht`.

Optional:

- `JEPA_DEVICE`: runtime device passed to the torch-hub runtime, for example `cpu` or `cuda`.
- `JEPA_MODEL_PATH`: legacy scaffold variable. It is retained only as value-free diagnostic
  metadata for users who previously configured the fail-closed scaffold. It does not make the
  provider runnable; set `JEPA_MODEL_NAME` instead.

## Runtime Contract

The adapter lazily loads:

```python
model, preprocessor = torch.hub.load(
    "facebookresearch/jepa-wms",
    "jepa_wm_pusht",
)
```

It first delegates to model-native scoring methods such as `score_actions(...)`. If the loaded
model does not expose a scoring method, it uses the same latent-distance fallback documented for
the [`jepa-wms`](./jepa-wms.md) candidate.

Required score inputs:

- `info["observation"]`: tensor-like object or rectangular nested finite numeric sequence with at
  least two dimensions;
- `info["goal"]`: tensor-like object or rectangular nested finite numeric sequence with at least
  two dimensions;
- `info["action_history"]`: optional tensor-like object or rectangular nested finite numeric
  sequence with at least two dimensions;
- `action_candidates`: tensor-like object or rectangular nested finite numeric sequence shaped as
  `(batch, samples, horizon, action_dim)`.

The public adapter supports exactly one batch and returns one score per candidate sample. Scores
default to costs: lower values are better.

## Migration From The Scaffold

Before this adapter, `jepa` was a capability-closed reservation gated by `JEPA_MODEL_PATH`.
That deterministic surrogate path is no longer part of the public `jepa` provider. Tests or host
experiments that need the old candidate shell should construct `JEPAWMSProvider` directly from
`worldforge.providers.jepa_wms`.

Migration checklist:

- replace `JEPA_MODEL_PATH=/path/to/old/scaffold` with `JEPA_MODEL_NAME=jepa_wm_pusht` or another
  validated upstream torch-hub model name;
- keep checkpoint paths and task assets in host-owned configuration, not in issue-safe diagnostic
  payloads;
- use `worldforge-smoke-jepa-wms` to preserve live runtime evidence until a dedicated `jepa` smoke
  command is needed.

## Tests

```bash
uv run pytest tests/test_jepa_provider.py tests/test_provider_catalog_docs.py
uv run python scripts/generate_provider_docs.py --check
uv run mkdocs build --strict
```

## Primary References

- [facebookresearch/jepa-wms](https://github.com/facebookresearch/jepa-wms)
- [facebook/jepa-wms Hugging Face model repository](https://huggingface.co/facebook/jepa-wms)

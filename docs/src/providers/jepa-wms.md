# JEPA WMS Provider

Status: scaffold

Taxonomy category: JEPA latent predictive world model

This is a generated candidate scaffold for a future adapter around
[`facebookresearch/jepa-wms`](https://github.com/facebookresearch/jepa-wms), the Meta FAIR code,
data, weights, training loops, shared planning components, and planning evaluations for
joint-embedding predictive world models.

It is not exported from `worldforge.providers`, not registered by `WorldForge._known_providers`,
and does not advertise public capabilities. Keep it that way until the adapter calls the real
upstream runtime and returns validated WorldForge models.

The scaffold health check remains unhealthy even when `JEPA_WMS_MODEL_PATH` is set because no
runtime adapter exists yet. A configured path only proves that the host has declared intent to use
JEPA-WMS; it does not prove the integration can execute.

## Planned Capabilities

- [ ] `score` implemented, advertised, and tested

The intended public surface is `score_actions(...) -> ActionScoreResult`, matching the
LeWorldModel-shaped planning path. A future implementation should rank candidate action sequences
from task-shaped observations, goals, and action candidates. It should not expose `predict=True`
unless it can return a complete validated WorldForge `PredictionPayload`, not just a latent rollout
internal to JEPA-WMS.

## Configuration

- Required environment variable: `JEPA_WMS_MODEL_PATH`.

- Optional dependencies: expected to be host-owned until a real adapter is implemented. Do not add
  `jepa-wms`, PyTorch, datasets, checkpoints, or simulator dependencies to WorldForge's base
  install.
- Registration rule: none yet. The scaffold is not auto-registered. A real adapter can consider
  registration when `JEPA_WMS_MODEL_PATH` points at a supported checkpoint or local repo/runtime
  layout.

## Contract To Define

- Exact upstream entry point: Python package import path, checkpoint loader, and scoring function.
- Input shape, range, and semantic constraints for observations, goals, action history, and action
  candidates.
- Mapping between JEPA-WMS candidate tensors and WorldForge `Action` sequences.
- Output schema, score direction, score units, and tie handling.
- Provider-specific limits such as context window, rollout horizon, action dimension, batch size,
  device placement, dataset/task family, and checkpoint compatibility.
- Failure modes for missing checkpoints, unsupported task configs, malformed tensor inputs,
  non-finite model outputs, unavailable simulator assets, and optional dependency failures.

## Tests To Add

- Fixture-driven happy path with a fake JEPA-WMS runtime.
- Malformed tensor payloads and unsupported shapes.
- Missing model path and missing optional runtime dependency.
- Non-finite scores and empty score output.
- Best-index selection through `World.plan(...)`.
- Event emission for success and failure.
- Contract test with `worldforge.testing.assert_provider_contract(...)` when the provider
  advertises public capabilities.

## Release Checklist

- [ ] Provider capabilities are narrow and truthful.
- [ ] Provider profile metadata is complete.
- [ ] Public API docs mention new failure modes.
- [ ] `docs/src/providers/README.md` links this provider page.
- [ ] `AGENTS.md` documents any new commands, dependencies, or gotchas.
- [ ] `CHANGELOG.md` records the user-visible behavior.

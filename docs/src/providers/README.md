# Providers

WorldForge providers are capability adapters, not a claim that every upstream system uses the same
definition of "world model." See [World Model Taxonomy](../world-model-taxonomy.md) for the project
definition and [Architecture](../architecture.md) for the end-to-end provider injection pipeline.

## In-repo providers

| Provider | Status | Auto-registration rule | Notes |
| --- | --- | --- | --- |
| `mock` | stable | always registered | deterministic local provider used by tests, examples, framework development, and adapter contract checks |
| `cosmos` | beta | register when `COSMOS_BASE_URL` is set | real HTTP adapter for Cosmos NIM; `NVIDIA_API_KEY` is optional and sent as bearer auth when present |
| `runway` | beta | register when `RUNWAYML_API_SECRET` or `RUNWAY_API_SECRET` is set | real HTTP adapter for Runway image-to-video and video-to-video APIs |
| `leworldmodel` | beta | register when `LEWORLDMODEL_POLICY` or `LEWM_POLICY` is set | real optional adapter for LeWorldModel JEPA cost models through `stable_worldmodel.policy.AutoCostModel` |
| `jepa` | scaffold | register when `JEPA_MODEL_PATH` is set | credential-gated stub backed by deterministic mock behavior |
| `genie` | scaffold | register when `GENIE_API_KEY` is set | credential-gated stub backed by deterministic mock behavior |

## Provider profiles

Every provider exposes a profile describing:

- supported task surface derived from capabilities
- deterministic vs stochastic behavior
- local vs remote runtime
- implementation status such as `stable`, `beta`, or `scaffold`
- credential requirements and environment variables
- supported modalities and artifact types
- maintainer notes for caveats

Programmatically:

```python
import logging

from worldforge import WorldForge
from worldforge.observability import (
    InMemoryRecorderSink,
    JsonLoggerSink,
    ProviderMetricsSink,
    compose_event_handlers,
)

logger = logging.getLogger("demo.worldforge")
metrics = ProviderMetricsSink()
recorder = InMemoryRecorderSink()

forge = WorldForge(
    event_handler=compose_event_handlers(
        JsonLoggerSink(logger=logger),
        metrics,
        recorder,
    )
)
profile = forge.provider_profile("mock")
forge.generate("orbiting cube", "mock", duration_seconds=1.0)

print(profile.supported_tasks, profile.deterministic)
print(metrics.get("mock", "generate").to_dict())
print(recorder.snapshot()[0].phase)
```

From the CLI:

```bash
uv run worldforge provider list
uv run worldforge provider info mock
uv run worldforge doctor
```

## Capability model

Providers can declare support for:

- `predict`
- `generate`
- `reason`
- `embed`
- `plan`
- `transfer`
- `score`

`score` providers return `ActionScoreResult` from `score_actions(...)`. The result contains the
provider name, one score per candidate, `best_index`, `best_score`, and explicit score direction.
For `leworldmodel`, scores are costs and lower values are better.

LeWorldModel is the architectural reference provider for score-based planning. It is first class
because it matches the JEPA planning contract WorldForge is designed to support: observations,
goals, and action candidates in; ranked futures out. WorldForge therefore models it as `score`
instead of pretending it can generate video, reason over text, or mutate world state directly.

## Operational notes

- `doctor()` includes known providers by default so missing configuration shows up in diagnostics.
- Missing local asset paths now fail before the outbound request instead of being treated as opaque remote strings.
- `cosmos` and `runway` expose a typed `ProviderRequestPolicy` through `provider_profile()` and CLI JSON output.
- `cosmos` validates health and generation response payloads before decoding generated video bytes.
- `runway` validates organization, task creation, task polling, task output, artifact content type, and expired artifact responses before returning a `VideoClip`.
- `leworldmodel` validates required `pixels`, `goal`, and `action` fields plus four-dimensional
  action-candidate payloads before invoking the cost model.
- Health checks, polling, and downloads retry with backoff by default. Create-style POST requests remain single-attempt unless a caller passes a custom policy.
- `WorldForge(event_handler=...)` and provider constructor `event_handler=` arguments accept a `ProviderEvent` callback for host-side logging and metrics.
- `worldforge.observability.compose_event_handlers(...)` lets host apps attach multiple sinks without writing a custom dispatcher.
- `ProviderMetricsSink.request_count` counts emitted request attempts, so retry events increment both `request_count` and `retry_count`.
- `cosmos` and `runway` emit `retry`, `success`, and `failure` events for HTTP operations.
  `leworldmodel` emits `success` and `failure` events for local scoring. `mock`, `jepa`, and
  `genie` emit success events for local provider operations.
- `cosmos` and `runway` are the only in-repo adapters that currently perform real HTTP requests.

## Provider-specific limits

Cosmos:

- `duration_seconds` must be greater than 0.
- Output width and height resolved from `GenerationOptions.size` or `GenerationOptions.ratio`
  must be greater than 0 and multiples of 8.
- `fps` must be greater than 0.
- `b64_video` must be a non-empty base64 string.
- Optional `seed` must be an integer when returned by the upstream API.

Runway:

- `duration_seconds` must be greater than 0. WorldForge maps accepted values into Runway's
  2-10 second request range for the current image-to-video endpoint.
- `GenerationOptions.ratio` must use `WIDTH:HEIGHT` with positive integer dimensions.
- `transfer(...)` output `width`, `height`, and `fps` must be greater than 0.
- `poll_interval_seconds` must be non-negative and `max_polls` must be greater than 0.
- Task responses must include a non-empty string `id` when creating tasks and a non-empty string
  `status` when polling tasks.
- Succeeded tasks must include at least one non-empty output URL.
- Downloaded artifacts reject explicit non-video content types such as `text/html`.

LeWorldModel:

- `LEWORLDMODEL_POLICY` or `LEWM_POLICY` must be the checkpoint run name relative to
  `$STABLEWM_HOME`, without the `_object.ckpt` suffix.
- `stable_worldmodel` and `torch` are optional host dependencies and are imported only when the
  provider is configured or used.
- `info` must include `pixels`, `goal`, and `action` as tensors or rectangular nested numeric
  sequences with at least three dimensions.
- `action_candidates` must be a tensor or rectangular nested numeric sequence shaped as
  `(batch, samples, horizon, action_dim)`.
- Model output must flatten to at least one finite numeric score.
- `scripts/smoke_leworldmodel.py` can run a local end-to-end smoke against
  `quentinll/lewm-pusht`; it requires the upstream GitHub version of `stable-worldmodel[train,env]`
  because the PyPI package may lag the LeWM module.

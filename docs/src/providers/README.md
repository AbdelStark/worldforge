# Providers

WorldForge providers are capability adapters. A provider page should explain what the adapter can
actually do, what the host must supply, what WorldForge validates, and which failure modes callers
should expect.

Provider discovery and auto-registration policy live in `src/worldforge/providers/catalog.py`.
Keep this page and the provider pages aligned with that catalog.

## Provider Catalog

<!-- provider-catalog:start -->
| Provider | Maturity | Capability surface | Registration | Runtime ownership |
| --- | --- | --- | --- | --- |
| `mock` | `stable` | `predict`, `generate`, `transfer`, `reason`, `embed` | always registered | in-repo deterministic local provider |
| [`cosmos`](./cosmos.md) | `beta` | `generate` | `COSMOS_BASE_URL` | host supplies a reachable Cosmos deployment and optional `NVIDIA_API_KEY` |
| [`runway`](./runway.md) | `beta` | `generate`, `transfer` | `RUNWAYML_API_SECRET` or `RUNWAY_API_SECRET` | host supplies Runway credentials and persists returned artifacts |
| [`leworldmodel`](./leworldmodel.md) | `beta` | `score` | `LEWORLDMODEL_POLICY` or `LEWM_POLICY` | host installs the official LeWM loading path (`stable_worldmodel.policy.AutoCostModel`), torch, and compatible checkpoints |
| [`gr00t`](./gr00t.md) | `experimental` | `policy` | `GROOT_POLICY_HOST` | host runs or reaches an Isaac GR00T policy server |
| [`lerobot`](./lerobot.md) | `beta` | `policy` | `LEROBOT_POLICY_PATH` or `LEROBOT_POLICY` | host installs LeRobot and compatible policy checkpoints |
| `jepa` | `scaffold` | scaffold | `JEPA_MODEL_PATH` | capability-fail-closed reservation, not a real JEPA runtime |
| `genie` | `scaffold` | scaffold | `GENIE_API_KEY` | capability-fail-closed reservation, not a real Genie runtime |
<!-- provider-catalog:end -->

## Candidate Scaffolds

| Provider | Capability surface | Registration | Runtime ownership |
| --- | --- | --- | --- |
| [`jepa-wms`](./jepa-wms.md) | direct-construction `score` candidate | none | host-owned torch-hub/runtime experiment; not exported or auto-registered |

Candidate scaffolds stay outside package exports and auto-registration until the runtime adapter,
limits, parser coverage, docs, and smoke path are credible enough for callers to depend on.

## Capability Model

WorldForge does not treat provider capabilities as badges. They are callable contracts.

| Capability | Provider method | Result contract |
| --- | --- | --- |
| `predict` | `predict(world_state, action, steps)` | `PredictionPayload` |
| `generate` | `generate(prompt, duration_seconds, options)` | `VideoClip` |
| `transfer` | `transfer(clip, width, height, fps, prompt, options)` | `VideoClip` |
| `reason` | `reason(query, world_state)` | `ReasoningResult` |
| `embed` | `embed(text=...)` | `EmbeddingResult` |
| `score` | `score_actions(info, action_candidates)` | `ActionScoreResult` |
| `policy` | `select_actions(info)` | `ActionPolicyResult` |

Rules:

- Do not advertise a capability unless the adapter implements the method end to end.
- Do not expose `predict` for a model that only returns latent costs.
- Do not expose `policy` unless raw actions are translated into executable WorldForge `Action`
  objects.
- Do not expose `generate` or `transfer` unless the returned media is validated as a `VideoClip`.
- Keep scaffold providers obvious: they reserve names and contracts without claiming runtime
  support.

Full provider classes expose these contracts through `ProviderCapabilities`. Narrow local
integrations can also implement one runtime-checkable capability protocol, such as a `Cost` object
with `score_actions(...)` or a `Policy` object with `select_actions(...)`. Protocol
implementations are registered through `WorldForge.register_cost(...)`,
`register_policy(...)`, or `register(...)`; WorldForge wraps them so diagnostics, provider events,
planning, and benchmarks see the same capability surface as full providers.

## Provider Profiles

Every provider exposes a `ProviderProfile` for routing, diagnostics, and documentation:

- capability surface derived from `ProviderCapabilities` or the registered capability protocol
- local versus remote runtime
- deterministic versus stochastic behavior
- implementation maturity such as `stable`, `beta`, `experimental`, or `scaffold`
- required environment variables
- supported modalities and artifact types
- request policy for HTTP-backed providers
- maintainer notes for caveats

Python:

```python
from worldforge import WorldForge

forge = WorldForge()
profile = forge.provider_profile("leworldmodel")
doctor = forge.doctor()

print(profile.supported_tasks)
print(doctor.issues)
```

CLI:

```bash
uv run worldforge provider list
uv run worldforge provider docs
uv run worldforge provider docs leworldmodel --format json
uv run worldforge provider info leworldmodel
uv run worldforge doctor --registered-only
uv run worldforge doctor --capability score
```

`doctor()` includes known but unregistered optional providers by default. That makes missing
configuration visible before a workflow fails. Use `--registered-only` when a process needs to
check only the providers enabled for that process.

Providers also expose `config_summary()` for issue evidence and host diagnostics. It reports
whether documented fields are present, where they came from (`env:<NAME>`, `direct`, `default`, or
`unset`), whether the field is required, and whether it is secret-like. It never returns raw values,
tokens, endpoint strings, checkpoint paths, or constructor arguments.

```python
from worldforge.providers import RunwayProvider

summary = RunwayProvider().config_summary().to_dict()
print(summary["fields"])
```

## Runtime Manifests

Real optional providers also have packaged JSON runtime manifests in
`src/worldforge/providers/runtime_manifests/`. The manifests are dependency-free records that host
applications, release checks, and docs can read without installing a live runtime.

Schema version `1` includes:

- `provider`: catalog provider name
- `capabilities`: callable WorldForge capabilities covered by the runtime
- `optional_dependencies`: host-owned packages or import paths
- `required_env_vars` and `optional_env_vars`: configuration surface
- `default_model`: default model, checkpoint, or host-selected model slot
- `device_support`: supported device classes such as `cpu`, `cuda`, or `remote`
- `host_owned_artifacts`: checkpoints, policy servers, generated media, or translators the host
  must retain
- `minimum_smoke_command`: smallest live command that proves the runtime is wired
- `expected_success_signal`: concrete pass condition for smoke evidence
- `setup_hint`: short remediation hint used by provider health messages
- `docs_path`: provider page that explains the manifest in context

WorldForge never auto-installs optional provider runtimes from these manifests. Missing optional
dependencies stay explicit in `health()` output and point back to the manifest-backed smoke path.
Manifests also provide the same value-free `config_summary()` shape for tools that need to inspect
declared provider env vars without importing or constructing the provider runtime.

## Runtime Ownership

WorldForge owns:

- provider registration and profile metadata
- typed input and output validation
- local JSON world persistence
- planning composition across `predict`, `score`, and `policy`
- deterministic evaluation and benchmark harnesses
- provider event hooks

The host owns:

- credentials and endpoint reachability
- torch, LeWorldModel, LeRobot, Isaac GR00T, CUDA, TensorRT, checkpoints, datasets, and robot
  runtimes
- observation preprocessing into model-native tensors
- embodiment-specific action translation
- operational telemetry, trace IDs, dashboards, and alerts
- durable persistence and artifact retention

## Observability

HTTP adapters emit `ProviderEvent` records for retries, successes, and failures. Local score and
policy adapters emit success and failure events around the model boundary where supported.

Attach sinks through `WorldForge(event_handler=...)`:

```python
import logging
from pathlib import Path

from worldforge import WorldForge
from worldforge.observability import (
    JsonLoggerSink,
    ProviderMetricsSink,
    RunJsonLogSink,
    compose_event_handlers,
)

run_id = "provider-smoke"
metrics = ProviderMetricsSink()
forge = WorldForge(
    event_handler=compose_event_handlers(
        JsonLoggerSink(logger=logging.getLogger("demo.worldforge"), extra_fields={"run_id": run_id}),
        RunJsonLogSink(Path(".worldforge") / "runs" / run_id / "provider-events.jsonl", run_id),
        metrics,
    )
)
```

`ProviderMetricsSink.request_count` counts emitted provider events, so retry events increment both
`request_count` and `retry_count`. `RunJsonLogSink` writes one redacted JSON record per line and
keeps `run_id` on every record so provider logs can be joined with host-owned run manifests.

Optional live smoke entrypoints accept `--run-manifest <path>` for a validated
`run_manifest.json`. The manifest is safe issue evidence: it stores command argv, package version,
provider profile, capability, value-free env presence, runtime manifest id, input fixture digest,
event count, result digest, and artifact paths. It does not store credential values, raw signed URL
query strings, checkpoint bytes, or generated media bytes.

## Authoring Standard

Before adding or promoting a provider, document:

- taxonomy category and capability surface
- configuration and auto-registration rule
- host-owned dependencies
- input shape and range constraints
- output schema and score direction, if any
- retry, timeout, polling, and artifact behavior
- failure modes
- fixture coverage and smoke path
- primary upstream technical references: papers, repositories, or official API docs only
- generated catalog table checked with `uv run python scripts/generate_provider_docs.py --check`

See [Provider Authoring Guide](../provider-authoring-guide.md) for the implementation checklist.

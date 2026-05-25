# Rerun Integration

WorldForge has a first-class optional integration with
[Rerun](https://github.com/rerun-io/rerun) for local physical-AI run inspection. It logs
sanitized provider events, world snapshots, plans, and benchmark reports into a Rerun recording
without making Rerun a provider capability or a base dependency.

Rerun is used here as an observability and data-artifact layer:

- `ProviderEvent` records become time-indexed text logs, JSON payloads, retry/failure counters,
  latency scalars, and status scalars.
- World snapshots become JSON state documents plus 3D object markers.
- Plans become JSON payloads, action-count and success-probability scalars, and 3D action target
  markers when actions contain `move_to` targets.
- Benchmark reports become a full JSON artifact plus per-provider and per-operation metric
  timeseries.

It does not replace provider adapters, persistence, training data stores, or host telemetry. Rerun
is attached through the same `event_handler` and artifact APIs that hosts already own.

## Install

```bash
uv add "worldforge-ai[rerun]"
```

For repository development:

```bash
uv sync --group dev --extra rerun
```

The extra installs `rerun-sdk>=0.24,<0.32`. Base WorldForge still depends only on `httpx`.
The broad range is intentional so the Rerun bridge can coexist with LeRobot runtimes that pin an
older compatible Rerun SDK.

## Showcase

```bash
uv run --extra rerun worldforge-demo-rerun
```

Default output is a local `.rrd` file:

```text
.worldforge/rerun/worldforge-rerun-showcase.rrd
```

Open it with the Rerun viewer:

```bash
uv run --extra rerun rerun .worldforge/rerun/worldforge-rerun-showcase.rrd
```

Live viewer modes:

```bash
uv run --extra rerun worldforge-demo-rerun --spawn
uv run --extra rerun worldforge-demo-rerun --connect-url rerun+http://127.0.0.1:9876/proxy
uv run --extra rerun worldforge-demo-rerun --serve-grpc-port 9876
```

Expected success signal: the command prints a summary containing the recording path or server URI
plus a byte count, and the recording contains provider event logs, world snapshots, 3D object boxes,
one predictive plan, and a mock-provider benchmark result.

First triage step when it fails:

```bash
uv run --extra rerun python -c "import rerun; print(rerun.__version__)"
```

## Robotics Showcase

The packaged PushT robotics showcase records a more visual Rerun artifact by default when launched
through the wrapper:

```bash
scripts/robotics-showcase
uvx --from "rerun-sdk>=0.24,<0.32" rerun /tmp/worldforge-robotics-showcase/real-run.rrd
```

That artifact contains the same policy+score run as the terminal/TUI report: sanitized provider
events, initial and final world snapshots, 3D object boxes, candidate target points, selected
trajectory lines, score bars, latency bars, and the serialized plan payload. Use `--no-rerun` to
skip the artifact, `--rerun-output <path>` to choose another `.rrd` path, or the lower-level
`--rerun-spawn`, `--rerun-connect-url`, and `--rerun-serve-grpc-port` flags for live viewer modes.

## Python API

```python
from worldforge import Action, RerunArtifactLogger, RerunEventSink, RerunRecordingConfig
from worldforge import RerunSession, WorldForge

session = RerunSession(
    RerunRecordingConfig(save_path=".worldforge/rerun/run.rrd")
)
events = RerunEventSink(session=session)
artifacts = RerunArtifactLogger(session=session)

forge = WorldForge(event_handler=events)
world = forge.create_world("lab", provider="mock")

prediction = world.predict(Action.move_to(0.3, 0.5, 0.0), steps=1)
artifacts.log_world(world, label="after prediction")

report = forge.doctor()
artifacts.log_json("diagnostics/doctor", report.to_dict())

session.close()
print(prediction.physics_score)
```

For one-line event-handler construction:

```python
from worldforge import WorldForge, create_rerun_event_handler
from worldforge.rerun import RerunRecordingConfig

forge = WorldForge(
    event_handler=create_rerun_event_handler(
        config=RerunRecordingConfig(save_path=".worldforge/rerun/events.rrd")
    )
)
```

Use `RerunArtifactLogger` when you want durable run artifacts in addition to provider events.

## Data Layout

Default entity paths:

| Entity path | Contents |
| --- | --- |
| `worldforge/events/<provider>/<operation>/<phase>/log` | Text event entry |
| `worldforge/events/<provider>/<operation>/<phase>/payload` | Sanitized event JSON |
| `worldforge/events/<provider>/<operation>/<phase>/duration_ms` | Event latency scalar |
| `worldforge/worlds/<world-id>/state` | Serialized world snapshot |
| `worldforge/worlds/<world-id>/objects` | 3D object markers |
| `worldforge/worlds/<world-id>/object_boxes` | 3D object bounding boxes |
| `worldforge/plans/<provider>/<planner>/<n>/payload` | Serialized plan |
| `worldforge/plans/<provider>/<planner>/<n>/action_targets` | 3D target markers |
| `worldforge/benchmarks/<provider>/<operation>/result` | Benchmark result JSON |
| `worldforge/benchmarks/<provider>/<operation>/<metric>` | Benchmark metric scalars |
| `worldforge/robotics_showcase/tabletop/*` | PushT candidate targets, selected path, and replay boxes |
| `worldforge/robotics_showcase/scores/*` | Candidate score bars and selected cost scalars |
| `worldforge/robotics_showcase/runtime/*` | Provider and end-to-end latency bars |

Default timelines:

| Timeline | Meaning |
| --- | --- |
| `worldforge_event` | Monotonic provider-event sequence |
| `worldforge_step` | World snapshot step |
| `worldforge_plan` | Monotonic plan sequence |
| `worldforge_benchmark_result` | Benchmark result index |
| `worldforge_robotics_showcase` | Robotics showcase summary |
| `worldforge_candidate` | Candidate-score sequence |

## Boundaries

- Rerun is optional. Do not import or require `rerun-sdk` from provider modules or base package
  paths.
- Rerun is not a WorldForge provider. It does not advertise `predict`, `score`, `policy`,
  `generate`, `transfer`, `reason`, `embed`, or `plan`.
- Provider event targets, messages, and metadata are sanitized before the Rerun sink receives
  them. Host code should still avoid putting secrets, credentials, signed URLs, or sensitive
  dataset contents into custom metadata.
- `.rrd` files are run artifacts. Treat them like logs: they can contain prompts, world metadata,
  object names, benchmark inputs, and derived diagnostics.
- Local JSON persistence remains WorldForge-owned and single-writer. Rerun recordings are
  inspection artifacts, not the authoritative world store.

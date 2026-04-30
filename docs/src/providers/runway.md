# Runway Provider

Capabilities: `generate`, `transfer`

Maturity: `beta`

Taxonomy category: remote video generation and transformation adapter

`runway` is an HTTP adapter for Runway's image-to-video, text-to-video-compatible, video-to-video,
and task-polling APIs. It creates a task, polls until completion, downloads the first output, and
returns a validated `VideoClip`.

```text
prompt/options or input VideoClip
  -> Runway task creation
  -> task polling
  -> artifact download
  -> VideoClip
```

WorldForge treats Runway as a media provider. It does not expose `predict`, `score`, or `policy`
because the adapter does not return a validated WorldForge state transition, action cost, or
executable action chunk.

## Runtime Ownership

WorldForge owns request shaping, typed timeout/retry policy, task response validation, artifact
download validation, and provider events.

The host owns:

- Runway credentials
- endpoint policy and API limits
- prompt/media inputs
- artifact retention after URLs expire
- operational telemetry and usage limits

## Configuration

- `RUNWAYML_API_SECRET`: preferred credential for auto-registration.
- `RUNWAY_API_SECRET`: legacy credential alias.
- `RUNWAYML_BASE_URL`: optional API endpoint override; defaults to
  `https://api.dev.runwayml.com`.

Runtime manifest:
`src/worldforge/providers/runtime_manifests/runway.json` records the credential aliases, optional
endpoint override, host-owned artifact retention, minimum live smoke command, and expected Runway
task signal.

Programmatic construction:

```python
from worldforge.providers import RunwayProvider

provider = RunwayProvider(
    poll_interval_seconds=6.0,
    max_polls=60,
)
```

Live smoke evidence:

```bash
RUNWAYML_API_SECRET=<secret> \
  uv run worldforge-smoke-runway \
    --capability generate \
    --output .worldforge/runs/runway-live/artifacts/runway.mp4 \
    --run-manifest .worldforge/runs/runway-live/run_manifest.json
```

Use `--capability transfer` with `--input-video` to exercise video-to-video separately. The smoke
summary and manifest store task presence, local artifact paths, and artifact URLs with query strings
and fragments removed.

## Generate Contract

```python
from worldforge import GenerationOptions

clip = forge.generate(
    "a lab robot moves a cube",
    provider="runway",
    duration_seconds=5.0,
    options=GenerationOptions(
        image="/path/to/initial-frame.png",
        ratio="1280:720",
        model="gen4.5",
        seed=7,
    ),
)
```

Generation rules:

- `duration_seconds` must be greater than 0.
- Duration is mapped into Runway's 2-10 second request range.
- The default model is `gen4.5`; the catalog currently documents `gen4.5`, `gen4_turbo`,
  `veo3.1`, `veo3.1_fast`, and `gen4_aleph` as known selectable model names.
- `GenerationOptions.ratio` must use `WIDTH:HEIGHT` with positive integer dimensions.
- `options.video` is rejected for `generate(...)`; use `transfer(...)` for video inputs.
- `image`, when supplied, becomes `promptImage`.
- `extras` are forwarded into the task-creation payload.

## Transfer Contract

```python
transferred = forge.transfer(
    clip,
    provider="runway",
    width=1280,
    height=720,
    fps=24,
    prompt="Re-render the clip with better lighting while preserving motion.",
    options=GenerationOptions(reference_images=["/path/to/reference.png"]),
)
```

Transfer rules:

- `width`, `height`, and `fps` must be greater than 0.
- Input video is supplied from `options.video` when provided, otherwise from the source
  `VideoClip`.
- `reference_images` become Runway references.
- The default transfer model is `gen4_aleph` unless `options.model` is supplied.
- Runway model/version limits can change upstream; keep benchmark inputs and smoke evidence tied to
  the exact model used in the result summary.

## Task And Artifact Contract

Runway task creation responses must include a non-empty task `id`.

Task polling responses must include:

- non-empty `status`
- matching task `id` when an id is returned
- `output` as a list of non-empty URLs when the task succeeds

Terminal task behavior:

- `SUCCEEDED`: download the first output URL
- `FAILED` or `CANCELLED`: raise `ProviderError` with returned failure detail
- timeout after `max_polls`: raise `ProviderError`

Artifact downloads accept video content types and `application/octet-stream`. Explicit non-video
content types such as `text/html` are rejected. Empty downloads fail explicitly. Expired or
unavailable artifact URLs are surfaced as provider errors.

Runway output URLs can be temporary signed URLs. WorldForge uses the raw URL only for the immediate
download request, then records `artifact_url` metadata without query strings or fragments. Persist
the downloaded bytes immediately if the media is needed for issue evidence, benchmark comparisons,
or release notes. If an artifact has expired, rerun the task rather than attempting to reconstruct a
signed URL from logs or manifests.

Separate benchmark input fixtures are provided for the two capabilities:

```bash
uv run worldforge benchmark --provider runway --operation generate \
  --input-file examples/runway-generate-benchmark-inputs.json
uv run worldforge benchmark --provider runway --operation transfer \
  --input-file examples/runway-transfer-benchmark-inputs.json
```

## Request Policy

`RunwayProvider` uses `ProviderRequestPolicy.remote_defaults(...)`:

- task creation requests are single-attempt by default
- health checks, polling, and downloads retry with backoff
- the request timeout defaults to 120 seconds unless overridden

Pass a custom `request_policy=` when the host needs different timeout or retry behavior.

## Failure Modes

- Missing `RUNWAYML_API_SECRET` and `RUNWAY_API_SECRET` leaves the provider unregistered.
- Organization health checks fail when credentials are invalid or the payload lacks both `id` and
  `name`.
- Task creation fails when the response lacks a non-empty task id.
- Polling fails when status payloads are malformed or the response id does not match the requested
  task.
- Completed tasks without output URLs fail explicitly.
- Expired, unavailable, empty, or wrong-content-type artifacts fail before returning `VideoClip`.
- Result metadata and run manifests keep only sanitized artifact URLs; signed query strings and
  fragments are not retained.
- Invalid ratios, durations, dimensions, FPS, polling intervals, or poll counts fail before or
  during request construction.

## Tests

- `tests/test_remote_video_providers.py` covers organization parsing, task creation and polling,
  failed tasks, partial outputs, expired artifacts, content-type rejection, transfer behavior, and
  input validation.
- `tests/fixtures/providers/runway_*.json` stores task and organization response fixtures.

## Primary References

- [Runway API reference](https://docs.dev.runwayml.com/api)
- [Runway API input parameters](https://docs.dev.runwayml.com/assets/inputs/)

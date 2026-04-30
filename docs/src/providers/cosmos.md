# Cosmos Provider

Capability: `generate`

Taxonomy category: physical-AI video/world generation adapter

`cosmos` is an HTTP adapter for a reachable NVIDIA Cosmos NIM deployment. It sends text, image, or
video-conditioned generation requests to `/v1/infer` and returns a validated `VideoClip`.

```text
prompt + GenerationOptions
  -> Cosmos /v1/infer
  -> base64 video response
  -> VideoClip
```

WorldForge treats Cosmos as a media generation provider. It does not expose `predict`, `score`, or
`policy` because the adapter does not return a validated WorldForge state transition, candidate
costs, or executable action chunks.

## Runtime Ownership

WorldForge owns request shaping, typed timeout/retry policy, response validation, video decoding,
and provider events.

The host owns:

- Cosmos deployment and endpoint reachability
- optional NVIDIA bearer token
- model availability behind the endpoint
- generated artifact persistence
- operational telemetry and alerting around the endpoint

## Configuration

- `COSMOS_BASE_URL`: required for auto-registration. Example: `http://localhost:8000`.
- `NVIDIA_API_KEY`: optional bearer token sent as `Authorization: Bearer ...`.

Runtime manifest:
`src/worldforge/providers/runtime_manifests/cosmos.json` records the required endpoint, optional
bearer token, host-owned artifacts, minimum live smoke command, and expected health signal.

Programmatic construction:

```python
from worldforge.providers import CosmosProvider

provider = CosmosProvider(base_url="http://localhost:8000")
```

## Request Contract

```python
from worldforge import GenerationOptions

clip = forge.generate(
    "a robot arm moves a mug across a table",
    provider="cosmos",
    duration_seconds=3.0,
    options=GenerationOptions(
        image="/path/to/initial-frame.png",
        size="1280x720",
        fps=24,
        seed=4,
    ),
)
```

Generation rules:

- `duration_seconds` must be greater than 0.
- Output width and height are resolved from `GenerationOptions.size` or
  `GenerationOptions.ratio`; both must be greater than 0 and multiples of 8.
- `fps` must be greater than 0.
- `image` and `video` options are converted to data URIs or passed through as URIs.
- `negative_prompt`, `seed`, and `extras` are forwarded when supplied.

Modes:

- no input media: `text2world`
- `options.image`: `image2world`
- `options.video`: `video2world`

## Response Contract

Cosmos responses must include:

```json
{
  "b64_video": "...",
  "seed": 4,
  "upsampled_prompt": "..."
}
```

WorldForge validates:

- `b64_video` is a non-empty base64 string
- `seed`, when present, is an integer
- `upsampled_prompt`, when present, is a string
- decoded bytes are returned as `VideoClip.frames[0]`

Returned metadata includes provider name, prompt, mode, seed, upsampled prompt, model, content
type, and base URL.

## Request Policy

`CosmosProvider` uses `ProviderRequestPolicy.remote_defaults(...)`:

- create-style generation requests are single-attempt by default
- health checks retry with backoff
- the request timeout defaults to 300 seconds unless overridden

Provider events are emitted for health and generation HTTP calls. `operation`, `phase`,
`status_code`, `attempt`, and sanitized `target` show whether a failure was an auth response,
transport timeout, retryable health read, or successful request without exposing bearer tokens or
response-body secrets.

Pass a custom `request_policy=` when the host needs different timeout or retry behavior.

## Failure Modes

- Missing `COSMOS_BASE_URL` leaves the provider unregistered.
- Health checks fail if `/v1/health/ready` is unreachable, returns malformed JSON, or omits the
  required string `status` field. First triage step: verify the endpoint directly with
  `curl "$COSMOS_BASE_URL/v1/health/ready"` from the same host.
- Generation fails if duration, size, or FPS inputs are invalid.
- Generation fails if the upstream response is missing `b64_video` or returns invalid base64.
- Generation fails with a task-failed message when Cosmos returns a failed/error status payload.
- Generation fails with an unsupported-artifact message when Cosmos returns artifact URLs instead
  of inline `b64_video`; this adapter intentionally does not persist or download provider-owned
  artifact URLs.
- HTTP transport failures and non-success statuses are raised as `ProviderError`.

## Live Smoke Evidence

Prepared hosts can run a real generate smoke without changing default CI:

```bash
COSMOS_BASE_URL=http://localhost:8000 \
  uv run worldforge-smoke-cosmos \
    --output .worldforge/runs/cosmos-live/artifacts/cosmos.mp4 \
    --summary-json .worldforge/runs/cosmos-live/results/summary.json \
    --run-manifest .worldforge/runs/cosmos-live/run_manifest.json
```

The smoke writes generated video bytes to the requested artifact path and can write a sanitized
`run_manifest.json` with value-free environment presence, runtime manifest id, event count,
input shape summary, result digest, and artifact path. Hosts own retention of the generated media;
copy the artifact out of temporary storage immediately when it is needed for release or issue
evidence.

## Tests

- `tests/test_remote_video_providers.py` covers Cosmos health parsing, generation success,
  malformed health payloads, malformed generation payloads, invalid seeds, failed-task payloads,
  unsupported artifact payloads, auth failures, timeout event metadata, and size validation.
- `tests/test_cosmos_smoke_script.py` covers the manual live-smoke entry point without making
  network calls.
- `tests/fixtures/providers/cosmos_*.json` stores the response fixtures used by parser tests.

## Primary References

- [NVIDIA Cosmos documentation](https://docs.nvidia.com/cosmos/latest/)
- [NVIDIA Cosmos Predict2.5 code](https://github.com/nvidia-cosmos/cosmos-predict2.5)

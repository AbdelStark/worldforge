# Provider Failure Mode Gallery

This gallery maps common provider failures to concrete fixture-backed signals. It is for issue
triage and adapter review, not live-provider quality ranking.

Run the checkout-safe artifact generator:

```bash
uv run python scripts/demo_showcases.py run provider-failure-gallery \
  --workspace-dir .worldforge/demo-showcases
```

Expected success signal: the command exits `0` and writes
`provider-failure-gallery/provider-failure-gallery.json` plus
`provider-failure-gallery/provider-failure-gallery.md`. First triage step: find the matching row,
run its first triage command, and attach only the safe artifact named by the row.

| Failure mode | Provider surface | Expected signal | Owner | First triage command | Safe artifact behavior |
| --- | --- | --- | --- | --- | --- |
| invalid prediction state | mock contract fixture | `invalid world state` contract failure | adapter contributor | `uv run pytest tests/test_provider_contracts.py -q` | attach provider contract JSON or Markdown only |
| unsafe provider event metadata | provider event conformance | `secret material` rejection before event sinks | adapter contributor and security reviewer | `uv run pytest tests/test_provider_contracts.py -q` | keep raw event logs local-only until redacted |
| malformed health response | Cosmos health parser | `healthcheck response field 'status'` in health details | adapter maintainer | `uv run worldforge provider health cosmos` | attach sanitized provider health JSON |
| remote authentication failure | Cosmos generation request | provider event with `status_code=401` and redacted target | host runtime owner | `uv run worldforge provider info cosmos` | attach redacted provider events or issue bundle |
| retry exhaustion or timeout | Cosmos generation request | `failed after 1 attempt` and failed provider event | host runtime owner | `jq 'select(.phase=="failure")' .worldforge/runs/<run-id>/logs/provider-events.jsonl` | attach sanitized event rows without raw request bodies |
| malformed task creation response | Runway task parser | `field 'id'` parser error | adapter maintainer | `uv run pytest tests/test_remote_video_providers.py -k missing_id -q` | attach the tiny sanitized fixture |
| expired generated artifact | Runway artifact download | `expired or unavailable` with failed download signal | host runtime owner | `uv run worldforge provider info runway` | rerun and attach a fresh safe artifact path, not a signed URL |
| unsafe artifact URL | Runway artifact validation | `artifact URL` validation failure | adapter maintainer and security reviewer | `uv run pytest tests/test_remote_video_providers.py -k unsafe_artifact_urls -q` | mark unsafe URLs local-only instead of linking them |
| missing optional runtime package | prepared-host optional provider | unhealthy provider info with a setup hint | prepared host owner | `uv run worldforge provider info gr00t` | attach runtime manifest and redacted provider info only |
| scaffold provider remains fail-closed | Genie scaffold contract | configured scaffold with no exercised operations | provider maintainer | `uv run worldforge provider contract genie --format json` | attach contract output; do not claim real Genie integration |

## Boundaries

- The gallery is checkout-safe. It does not call paid APIs, use credentials, install optional
  runtimes, or download checkpoints.
- Provider events, health output, issue bundles, and contract reports must stay sanitized before
  attachment.
- raw provider request bodies, signed artifact URLs, `.env` files, private checkpoints, and
  host-local payload paths remain local-only.
- Scaffold providers are shown as failure boundaries. A fail-closed scaffold row is not evidence of
  a real provider integration.

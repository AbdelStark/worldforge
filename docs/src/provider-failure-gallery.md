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
| score count mismatch | LeWorldModel score boundary | `returned 2 score(s) for 3 candidate` | score adapter maintainer | `uv run pytest tests/test_leworldmodel_provider.py -k score_count -q` | attach sanitized score metadata; do not attach tensors |
| malformed score request payload | LeWorldModel score boundary | `four-dimensional` validation error | score adapter maintainer | `uv run pytest tests/test_leworldmodel_provider.py -k malformed_payload -q` | attach tiny JSON fixtures only; keep host tensors local |
| embodied action translator missing | Cosmos-Policy policy boundary | `provide action_translator` | prepared host owner | `uv run worldforge provider info cosmos-policy` | attach config summaries and shape metadata, not observations |
| unsafe local/private endpoint | Cosmos-Policy configuration | `local/private destination` | host runtime owner and security reviewer | `uv run pytest tests/test_cosmos_policy_provider.py -k local_base_url -q` | do not attach private host names or bearer tokens |
| malformed json_numpy action shape | Cosmos-Policy response parser | `action_dim must be 14` | policy adapter maintainer | `uv run pytest tests/test_cosmos_policy_provider.py -k json_numpy_action_dim -q` | attach bounded shape metadata only; do not attach observations |
| missing optional runtime package | prepared-host optional provider | unhealthy provider info with a setup hint | prepared host owner | `uv run worldforge provider info gr00t` | attach runtime manifest and redacted provider info only |
| scaffold provider remains fail-closed | Genie scaffold contract | configured scaffold with no exercised operations | provider maintainer | `uv run worldforge provider contract genie --format json` | attach contract output; do not claim real Genie integration |

## Boundaries

- The gallery is checkout-safe. It does not call paid APIs, use credentials, install optional
  runtimes, or download checkpoints.
- Provider events, health output, issue bundles, and contract reports must stay sanitized before
  attachment.
- raw provider request bodies, signed URLs, `.env` files, private checkpoints, and host-local
  payload paths remain local-only.
- Scaffold providers are shown as failure boundaries. A fail-closed scaffold row is not evidence of
  a real provider integration.

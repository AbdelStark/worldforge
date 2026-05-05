# Live Smoke Evidence Registry

Issue: [#144](https://github.com/AbdelStark/worldforge/issues/144).

The live-smoke evidence registry is the publishable index for optional provider smokes. It records
which providers have a recent sanitized manifest, which were skipped, and why. It is not a
benchmark and does not claim model quality, physical fidelity, or robot safety.

Registry JSON: [`live-smoke-evidence.json`](./live-smoke-evidence.json).

## Entry Contract

Each entry records:

| Field | Contract |
| --- | --- |
| `provider` | Provider profile or candidate name. |
| `capability` | One WorldForge capability such as `generate`, `score`, or `policy`. |
| `command` | Smoke command to run on a prepared host. Do not inline secrets. |
| `runtime_manifest` | Runtime manifest id such as `runway:schema-1`, or `null` if none exists. |
| `date` | Registry decision date as `YYYY-MM-DD`. |
| `version` | WorldForge package version used for the registry row. |
| `status` | `passed`, `failed`, `not_run`, `skipped_missing_runtime`, `skipped_missing_credentials`, or `skipped_not_configured`. |
| `artifact_path` | Sanitized `run_manifest.json` or artifact path for passed/failed evidence, otherwise `null`. |
| `skip_reason` | Required for skipped or not-run entries. |
| `known_limitations` | List of explicit caveats and host-owned responsibilities. |

Validate the registry in tests or release tooling:

```python
from worldforge import validate_live_smoke_registry

registry = validate_live_smoke_registry(payload)
```

The validator rejects signed URLs, URL query strings, fragments, obvious secret material,
secret-like metadata keys, duplicate provider/capability rows, missing skip reasons, and missing
artifact paths for passed or failed evidence.

## Status Semantics

- `passed`: a prepared host ran the command and preserved a sanitized manifest.
- `failed`: a prepared host ran the command and preserved a sanitized failure manifest.
- `not_run`: the command exists, but no run was attempted or linked for this release.
- `skipped_missing_runtime`: the host lacks an optional runtime, checkpoint, endpoint, device, or
  server needed for the smoke.
- `skipped_missing_credentials`: the host lacks required provider credentials.
- `skipped_not_configured`: the provider is intentionally not configured for this release.

Skipped rows are evidence. They prevent release notes and issues from silently omitting optional
providers that could not run on the current host.

## Attaching Manifests To Issues

When a prepared-host smoke passes, attach the sanitized `run_manifest.json` and any small
checkout-safe summaries it links. Do not attach:

- raw credentials or environment dumps;
- signed artifact URLs or URLs with query strings;
- raw tensors, media blobs, checkpoints, model weights, or robot-controller logs;
- host-local absolute paths unless the issue is explicitly documenting local-only evidence;
- claims that a live smoke is a benchmark or a physical-fidelity proof.

If a smoke is skipped, attach the registry row or paste the provider, status, command, skip reason,
and known limitations. That is enough to show whether the blocker is missing credentials, missing
optional runtime, or an intentional release choice.

## Release Evidence

`scripts/generate_release_evidence.py` includes the registry by default:

```bash
uv run python scripts/generate_release_evidence.py \
  --live-smoke-registry docs/src/live-smoke-evidence.json \
  --output .worldforge/release-evidence/release-evidence.md
```

Release evidence may still link individual `--run-manifest` files. The registry is the summary
surface; the run manifests are the per-run evidence.

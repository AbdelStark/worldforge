---
name: provider-adapter-development
description: "Use for WorldForge provider work: adding adapters, changing capability declarations, promoting scaffolds, debugging provider failures, updating provider catalog docs, or touching Cosmos, Runway, LeWorldModel, GR00T, LeRobot, JEPA, Genie, or JEPA-WMS. Ensures capabilities remain truthful and optional runtimes stay host-owned."
---

# Provider Adapter Development

## Non-Negotiables

- Valid capabilities are `predict`, `generate`, `reason`, `embed`, `plan`, `transfer`, `score`, and `policy`.
- `ProviderCapabilities()` is fail-closed. Advertise only callable, tested operations.
- `plan` is a WorldForge facade workflow. Do not benchmark or advertise it as a provider operation unless a real provider-owned planner exists.
- Optional runtimes, checkpoints, datasets, CUDA, robot packages, credentials, and robot controllers stay out of base dependencies and repo artifacts.
- Provider events are a log boundary. Never emit bearer tokens, API keys, signed URL query strings, or secret-like metadata.

## Capability Map

| Provider | Truthful surface | Registration |
| --- | --- | --- |
| `mock` | `predict`, `generate`, `transfer`, `reason`, `embed` | always |
| `cosmos` | `generate` | `COSMOS_BASE_URL` |
| `runway` | `generate`, `transfer` | `RUNWAYML_API_SECRET` or `RUNWAY_API_SECRET` |
| `leworldmodel` | `score` | `LEWORLDMODEL_POLICY` or `LEWM_POLICY` |
| `gr00t` | `policy` | `GROOT_POLICY_HOST` |
| `lerobot` | `policy` | `LEROBOT_POLICY_PATH` or `LEROBOT_POLICY` |
| `jepa`, `genie` | scaffold only | env-gated reservations |
| `jepa-wms` | direct-construction candidate | not exported or auto-registered |

## Workflow

1. Read the closest existing adapter, then `src/worldforge/providers/base.py`, `src/worldforge/providers/catalog.py`, and `docs/src/provider-authoring-guide.md`.
2. Classify the upstream runtime by what it actually does, not by model marketing language.
3. For a new scaffold, start with `uv run python scripts/scaffold_provider.py ...`; keep capabilities unadvertised until real methods return validated WorldForge models.
4. Validate public inputs before network calls, filesystem reads, or optional runtime calls.
5. Return the correct public model: `PredictionPayload`, `VideoClip`, `ReasoningResult`, `EmbeddingResult`, `ActionScoreResult`, or `ActionPolicyResult`.
6. Add success and malformed/error fixtures under `tests/fixtures/providers/`.
7. Add `worldforge.testing.assert_provider_contract()` coverage for every advertised capability.
8. Update `.env.example`, provider docs, generated catalog surfaces, README, changelog, `AGENTS.md`, or `CLAUDE.md` only when public behavior or env vars change.
9. Validate with focused provider tests, ruff, generated provider-doc check, and the coverage/package gates when the public surface changes.

## Sharp Edges

| Symptom | Cause | Fix |
| --- | --- | --- |
| Provider appears in docs with wrong surface | `ProviderCapabilities` declaration drifted | Fix adapter capabilities, run provider docs generator, update tests |
| Optional provider missing from `doctor` | Required env var absent | Confirm variable name from `.env.example`; do not read `.env` |
| Contract helper fails on JSON | Metadata/raw payload not JSON-native | Validate at construction and convert tuples/objects before return |
| Remote test leaks URL/query | Event target/message metadata not sanitized | Add regression in `tests/test_observability.py` or provider test |

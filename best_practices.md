# WorldForge Review Best Practices

WorldForge is a Python integration layer for testable physical-AI world-model workflows. Review it
as library/runtime infrastructure: small contract drift can make downstream robotics, checkpoint,
provider, or evaluation workflows unsafe or misleading.

## Capability Contracts

WorldForge providers must be truthful about what they implement.

- Advertise only capabilities implemented end to end.
- Keep `score`, `policy`, `predict`, `generate`, `reason`, `embed`, `transfer`, and `plan` separate.
- Unknown capability names should fail explicitly instead of behaving like empty filters.
- Do not wrap a score model as a predictor, a robot policy as a world model, or a mock scaffold as a
  real provider.

Non-compliant pattern:

```python
ProviderCapabilities(predict=True)
```

when the provider only exposes a cost model or policy surface.

Compliant pattern:

```python
ProviderCapabilities(score=True)
```

for a provider that returns validated candidate costs end to end.

## Provider Boundary Hardening

Remote provider code is an adversarial boundary.

- Validate schemes, hosts, redirects, and artifact URLs before fetching provider-controlled URLs.
- Block localhost, private, loopback, link-local, multicast, and metadata-service destinations
  unless the caller has explicitly opted into local network access.
- Enforce connect/read/write/pool timeouts and retry only safe idempotent operations.
- Bound artifact download size before buffering, and stream with a hard cap where possible.
- Parse upstream responses into typed WorldForge errors. Do not leak raw SDK or HTTP exceptions as
  public behavior.
- Add fixture-backed tests for malformed payloads, unexpected status transitions, unsafe URLs,
  oversized artifacts, and content-type mismatches.

## Optional Runtime And Checkpoint Safety

Optional model, robotics, CUDA, torch, and checkpoint integrations are host-owned.

- Keep optional runtime dependencies outside the base dependency set.
- Never execute untrusted remote model configuration through Hydra, pickle, dynamic imports, or
  arbitrary constructors without a narrow allowlist and explicit user opt-in.
- Pin remote model, dataset, and checkpoint revisions in reproducible examples and operator docs.
- Make safety messaging cover every code-execution surface before weights are loaded.
- Provide injectable fakes for tests so CI does not need real checkpoints, GPUs, robot stacks, or
  credentials.

## Secrets, Signed URLs, And Event Metadata

Provider events and result metadata are commonly logged, serialized, or displayed.

- Redact bearer tokens, API keys, signed URL query strings, credentials, and secret-like metadata
  before they enter events, logs, exceptions, transcripts, persisted worlds, or returned result
  objects.
- Sanitizing only the log event is not enough if the same secret remains in public result metadata.
- Preserve enough non-secret context for debugging: provider name, operation, status, sanitized host,
  elapsed time, and stable error category.

## JSON-Native Public Data

WorldForge public models and persisted state must remain JSON-native.

- Accept only string keys, finite numbers, lists, dictionaries, booleans, strings, and null.
- Reject tuples, object instances, bytes, NaN, infinity, and ambiguous coercions at construction or
  boundary validation time.
- Keep prediction payloads, planning results, benchmark metrics, and rendered report data
  internally coherent before serialization.

## Planning And Replay Coherence

Planning output must be auditable.

- Candidate counts, raw actions, translated actions, scores, selected index, selected action chunk,
  provider metadata, and event history must agree.
- Tie-breaking should be deterministic and documented by tests.
- Replays and demos should say clearly when they are mock replay, simulation, injected policy,
  checkpoint inference, or real robot control.

## Tests And Documentation

Every bug fix and documented failure mode needs a focused regression test.

- Prefer narrow negative tests for parser errors, provider failures, invalid public inputs, unsafe
  network destinations, oversized downloads, and secret redaction.
- Keep provider contract helpers explicit: raise `AssertionError` with clear messages instead of
  relying on bare Python `assert`.
- Update docs when public behavior changes. Operator docs should include the command to run, the
  expected success signal, and the first triage step.
- Keep `mkdocs.yml` synchronized with `docs/src/SUMMARY.md` when public docs pages move.

## CI, Packaging, And Supply Chain

Review CI and packaging changes as supply-chain sensitive.

- Preserve Python 3.13, `uv lock --check`, Ruff, pytest, coverage, docs build, package contract, and
  dependency audit gates unless the PR gives a concrete reason.
- Keep GitHub Actions permissions minimal.
- Do not introduce new base dependencies casually; optional runtime dependencies should be exposed
  through extras or host-owned setup instructions.
- Avoid generated artifacts in source commits unless the repository explicitly tracks that artifact
  and has a drift check.

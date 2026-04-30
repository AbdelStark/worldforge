# Genie Provider

Status: scaffold.

WorldForge keeps `genie` as a fail-closed provider reservation. It does not advertise `generate`,
`predict`, or any scene/world capability, and it is not a real Google DeepMind Genie or Project
Genie integration.

## Defer Decision

Decision date: 2026-05-01.

The first real Genie-facing surface should be `generate` only after there is a supported upstream
runtime or API contract that automation can call and test. Google DeepMind describes Genie 3 as a
general-purpose world model for real-time interactive environments, and the January 2026 Project
Genie announcement describes Project Genie as an experimental research prototype web app for U.S.
Google AI Ultra subscribers. Those sources describe an interactive product experience, not a supported automation API, SDK, artifact schema, authentication contract, or smoke-testable runtime
boundary.

Until those boundaries exist, WorldForge must not present deterministic local surrogate behavior as
a Genie implementation. Keeping the provider as `scaffold` is the accurate production behavior.

References:

- [Genie 3 - Google DeepMind](https://deepmind.google/models/genie/)
- [Project Genie announcement - Google Blog](https://blog.google/innovation-and-ai/models-and-research/google-deepmind/project-genie/)

## Current Contract

| Field | Value |
| --- | --- |
| Provider name | `genie` |
| Maturity | `scaffold` |
| Public capabilities | none |
| Auto-registration signal | `GENIE_API_KEY` |
| Runtime ownership | none yet; future runtime/API must be host-owned |
| Artifact types | none |

Setting `GENIE_API_KEY` only makes the reservation visible to diagnostics and readiness surfaces. It
does not make `genie.generate(...)` callable. All capability methods remain fail-closed unless
`WORLDFORGE_ENABLE_SCAFFOLD_SURROGATES=1` is set for local adapter tests.

The surrogate opt-in exists only to exercise shared provider plumbing. It must not be used for
benchmarks, demos, release evidence, or issue evidence that claims Genie runtime behavior.

## Promotion Requirements

Replace this scaffold only when a PR can name and validate one concrete upstream contract:

- supported API, SDK, or local runtime entrypoint;
- authentication and configuration fields with redacted `config_summary()` output;
- exact input contract for prompts, optional image/state inputs, duration, and controls;
- returned artifact schema, MIME/type hints, expiration behavior, and retention expectations;
- typed failure modes for auth errors, validation errors, unavailable capacity, timeouts, and
  unsupported artifacts;
- fixture-backed parser tests for success and failure payloads;
- optional prepared-host smoke command that writes a sanitized `run_manifest.json`.

If the upstream surface remains an interactive web prototype without a supported automation
contract, this provider should stay `scaffold`.

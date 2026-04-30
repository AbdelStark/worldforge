# Next Provider Selection RFC

This RFC records the provider selection decision for the next implementation batch. It is a
planning artifact only: it does not change the provider catalog, generated provider docs, README,
or public capability claims.

Decision date: 2026-04-30.

## Selection Rules

Use the [provider prioritization rubric](./provider-platform-roadmap.md#provider-prioritization-rubric)
before creating implementation issues. A provider is a good next candidate only when it has:

- a stable callable surface that maps to one WorldForge capability;
- a checkout-safe fixture strategy for success and failure cases;
- a prepared-host smoke path with preserved evidence;
- clear runtime ownership, licensing, and maintenance expectations;
- no need for new base-package dependencies.

Provider names alone are not a reason to expand the catalog. The selected batch should improve
real callable behavior or unlock a concrete host workflow.

## Recommended Next Batch

The next batch should contain no more than these three provider additions or promotions.

| Candidate | Capability | Owner | Validation path | Issue outline |
| --- | --- | --- | --- | --- |
| JEPA-WMS score adapter | `score` | provider platform maintainer | injected runtime tests, fixture-backed score outputs, runtime manifest, optional prepared-host smoke manifest | Promote the direct-construction candidate only after upstream runtime loading, tensor shape validation, finite scores, JSON-native metadata, and failure typing are covered. |
| Genie interactive-world adapter | `generate` | media provider maintainer | fail-closed scaffold tests first, then fixture-backed artifact generation and smoke manifest once a runtime/API contract is selected | Replace the scaffold with one explicit upstream contract; document artifact type, prompt/state inputs, and why generated worlds are not planning proofs. |
| Spatial/3D scene adapter | `generate` | provider platform maintainer | design issue, fixture schema for scene artifacts, artifact redaction tests, optional runtime manifest after contract selection | Add a new issue before implementation that chooses one concrete scene/runtime API and defines the minimal JSON-native scene artifact boundary. |

### JEPA-WMS Issue Outline

Capability: `score`.

Owner: provider platform maintainer.

Validation path:

- add a narrow adapter around the upstream JEPA-WMS scoring surface;
- keep optional torch/checkpoint/runtime packages host-owned;
- validate observation, goal, and candidate-action tensor shapes before calling the runtime;
- validate finite score output, coherent `best_index`, and JSON-native metadata;
- cover success, malformed score output, missing runtime, and missing checkpoint paths;
- preserve an optional live-smoke manifest on prepared hosts.

Why now: it extends the JEPA-centered planning path without adding another media generator or
generic provider name.

### Genie Issue Outline

Capability: `generate`.

Owner: media provider maintainer.

Validation path:

- pick one concrete upstream runtime or hosted API before enabling capabilities;
- keep the current scaffold fail-closed until that contract exists;
- validate prompt/state inputs, generated artifact metadata, MIME/type hints, and artifact safety;
- add fixtures for successful artifact creation and upstream failure payloads;
- document the smoke command and preserved run manifest for prepared hosts.

Why now: Genie-style interactive-world generation is valuable, but only after the runtime boundary
is concrete enough to test.

### Spatial/3D Scene Issue Outline

Capability: `generate`.

Owner: provider platform maintainer.

Validation path:

- write a design issue selecting one concrete scene or 3D-world API;
- define a minimal scene artifact schema before adding provider code;
- require fixtures for asset references, dimensions/units, safe metadata, and malformed payloads;
- keep large assets, credentials, viewers, and GPU/runtime packages host-owned;
- add a prepared-host smoke only after the artifact boundary is stable.

Why now: spatial artifacts are a distinct provider family and should not be squeezed into video or
planning contracts.

## Deferred Candidates

| Candidate class | Deferred reason |
| --- | --- |
| Additional remote video APIs | Runway and Cosmos already cover the current remote media hardening path; add another only after it has a clearly different capability or user workflow. |
| General LLM reasoning providers | The `reason` capability needs a stronger world-state question-answering contract before adding ordinary chat/completion adapters. |
| Simulator bridges | The public scene/state boundary and host-owned simulator process model need a design record first. |
| New embodied policy stacks beyond LeRobot/GR00T | Robotics validation cost is high; finish policy conformance, translator contracts, and prepared-host evidence before adding more policy runtimes. |
| Active inference or probabilistic belief adapters | Useful direction, but WorldForge does not yet have typed belief/uncertainty result contracts. |
| More scaffold reservations | Deferred by policy. A name without an executable runtime contract adds catalog noise. |

## Non-Goals

- Do not change generated provider docs or provider README pages in this RFC.
- Do not add provider names to auto-registration.
- Do not add optional runtime packages to the base dependency set.
- Do not present generated videos, scenes, or policies as evidence of physical fidelity without
  preserved run artifacts.

## Follow-Up Rules

Each selected provider still needs its own implementation PR. That PR must state:

- capability surface and implementation status;
- runtime ownership and optional dependency boundary;
- fixture and smoke evidence;
- generated docs behavior;
- redaction and artifact-retention expectations.

If a candidate cannot satisfy those requirements, keep it deferred and document the blocker rather
than adding a scaffold.

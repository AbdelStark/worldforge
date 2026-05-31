# Next Provider Selection RFC

This RFC records the provider selection decision for the next implementation batch. It is a
planning artifact only: it does not change the provider catalog, generated provider docs, README,
or public capability claims.

Decision date: 2026-04-30.

Current cohort note: this RFC records the previous expansion batch. The active issue #130 cohort
decision is recorded in the
[Provider Cohort Selection Record](./provider-cohort-selection.md).

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

The next batch should contain no more than these provider additions or promotions.

| Candidate | Capability | Owner | Validation path | Issue outline |
| --- | --- | --- | --- | --- |
| JEPA-WMS score adapter | `score` | provider platform maintainer | injected runtime tests, fixture-backed score outputs, runtime manifest, optional prepared-host smoke manifest | Promote the direct-construction candidate only after upstream runtime loading, tensor shape validation, finite scores, JSON-native metadata, and failure typing are covered. |

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

### JEPA Public Adapter Addendum

Decision date: 2026-05-01.

Capability: `score`.

Selected upstream: [`facebookresearch/jepa-wms`](https://github.com/facebookresearch/jepa-wms)
through `torch.hub.load("facebookresearch/jepa-wms", model_name)`.

Decision: promote the public `jepa` catalog entry from a fail-closed reservation to an
experimental score-only adapter that reuses the JEPA-WMS runtime contract. The adapter requires
`JEPA_MODEL_NAME`, keeps PyTorch and checkpoints host-owned, and does not expose `predict` or
`embed`.

Migration: `JEPA_MODEL_PATH` was the old scaffold reservation variable. It is retained only as
value-free diagnostic metadata; hosts must set `JEPA_MODEL_NAME` to load a real upstream model.

Why this does not promote every JEPA surface: upstream action-conditioned JEPA-WM planning maps
cleanly to candidate-action scoring. Latent rollout and embedding APIs need separate contracts
before WorldForge can advertise `predict` or `embed`.

## Deferred Candidates

| Candidate class | Deferred reason |
| --- | --- |
| Additional remote providers | Add another only after it has a clearly different planning, prediction, score, or policy workflow. |
| General LLM QA providers | World-state question-answering needs a separate typed contract before adding ordinary chat/completion adapters. |
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

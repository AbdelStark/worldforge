# Provider Cohort Selection Record

Decision date: 2026-05-05.

Issue: [#130](https://github.com/AbdelStark/worldforge/issues/130).

This record selects the next provider evidence cohort without changing provider catalog rows,
generated provider docs, README provider tables, or public capability claims. It exists to prevent
provider growth from becoming catalog noise.

Use it together with:

- [Provider prioritization rubric](./provider-platform-roadmap.md#provider-prioritization-rubric)
- [Provider promotion matrix](./provider-platform-roadmap.md#provider-promotion-matrix)
- [Provider authoring promotion gate](./provider-authoring-guide.md#step-3-apply-the-promotion-gate)
- [Provider catalog rules](./providers/README.md#capability-model)

## Reviewed Inputs

The selection uses the roadmap issue body, current provider docs, current GitHub issue state, and
light upstream checks from 2026-05-05. The upstream checks were intentionally shallow: enough to
score the cohort, not enough to claim runtime support.

| Source | Signal used |
| --- | --- |
| [`facebookresearch/jepa-wms`](https://github.com/facebookresearch/jepa-wms) | Public Python repository for JEPA-WMS physical-planning research; GitHub license detection reports `Other`; updated 2026-05-04 at review time. |
| [`simchowitzlabpublic/nano-world-model`](https://github.com/simchowitzlabpublic/nano-world-model) | Public Python repository for action-conditioned video world models and MPC-style planning; MIT license; updated 2026-05-05 at review time. |
| [`Physical-Intelligence/openpi`](https://github.com/Physical-Intelligence/openpi) | Public Python embodied-policy stack; Apache-2.0 license; useful signal for future policy work, but not a score/predict world-model boundary. |
| [`3DTopia/OpenLRM`](https://github.com/3DTopia/OpenLRM) | Public Python 3D reconstruction/generation project; Apache-2.0 license; useful signal for scene artifacts, but not a selected WorldForge provider API. |
| GitHub repository search for Genie world-model implementations | Returned third-party repositories rather than a supported automation API or official runtime contract. |
| [Nano World Model issue #158](https://github.com/AbdelStark/worldforge/issues/158) | Existing issue-level research on NanoWM fit, host-owned runtime risks, and the likely score-first WorldForge contract. |

## Scoring Method

Each candidate is scored against the eight rubric criteria from the provider platform roadmap:
user value, capability clarity, upstream maturity, runtime feasibility, fixture strategy, smoke
feasibility, maintenance burden, and safety/secret risk. Each criterion is worth 0, 1, or 2.

Interpretation:

- `12-16`: eligible for the next implementation cohort.
- `8-11`: keep as an RFC, direct-construction candidate, or contract-design issue.
- `<8`: defer; do not add catalog surface.

## Candidate Scorecard

| Candidate | Capability | Upstream runtime/API | Runtime ownership | Fixture strategy | Prepared-host smoke feasibility | License/maintenance risk | Score | Decision |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| JEPA-WMS and public `jepa` score path | `score` | `facebookresearch/jepa-wms` through host-owned torch-hub/runtime loading | Host owns torch, checkpoints, device, model names, and task preprocessing | Injected runtime tests, score-output fixtures, runtime-response validation, provider contract helpers | Credible through existing JEPA-WMS prepared-host smoke path once manifest evidence is captured | Moderate: active public repo, but license is not SPDX-classified by GitHub; verify terms before stable promotion | 12 | Active cohort. Finish [#133](https://github.com/AbdelStark/worldforge/issues/133), then [#137](https://github.com/AbdelStark/worldforge/issues/137). |
| Cosmos and Runway remote media retention | `generate`, `transfer` | Existing WorldForge Cosmos and Runway HTTP adapters | Host owns credentials, endpoint reachability, and persisted media artifacts | Parser fixtures, failed-polling fixtures, expired/unsupported artifact fixtures, signed-URL redaction tests | Credible on prepared hosts through remote-media dry-runs and sanitized run manifests | Low to moderate: current adapters are already beta; risk is artifact retention and URL leakage, not new runtime shape | 12 | Active cohort. Harden current providers through [#134](https://github.com/AbdelStark/worldforge/issues/134); do not add another remote video API yet. |
| Nano World Model score candidate | `score` first; `predict` only after a separate contract | `simchowitzlabpublic/nano-world-model` action-conditioned rollout and MPC/CEM planning code | Host owns NanoWM checkout, PyTorch/CUDA or device stack, configs, VAE/checkpoints, datasets, and preprocessing | Start with injected runtime protocol and finite nested JSON-native candidate tensors; no torch import in checkout tests | Plausible, but only after runtime/API reconnaissance proves an importable or subprocess boundary under Python 3.13 | Moderate: MIT and active public repo, but runtime stack is heavy and API may be script/config driven | 10 | Active design candidate, not public provider implementation. Use [#158](https://github.com/AbdelStark/worldforge/issues/158) for runtime/API reconnaissance before any catalog claim. |
| Spatial/3D scene provider family | Future `generate` after a scene artifact contract exists | No single selected API; OpenLRM/I-Scene-style projects are research signals only | Host would own GPU/runtime packages, model weights, asset retention, viewers, and unit conventions | Not ready; first needs JSON-native scene artifact fixtures and malformed payload coverage | Not credible until one concrete API and artifact schema are selected | Moderate to high: fast-moving projects, large artifacts, unclear scene-unit semantics | 7 | Deferred. Revisit through [#138](https://github.com/AbdelStark/worldforge/issues/138) before implementation. |
| Genie interactive-world generation | Future `generate` only after a supported runtime/API exists | No supported automation API or official callable runtime found in current project docs/search; current `genie` remains scaffold | Host would own credentials/runtime/artifact retention if a real contract appears | Scaffold tests only; no real parser fixture until an upstream contract is selected | Not credible now | High: unclear upstream contract and high overclaim risk | 5 | Deferred. Keep `genie` fail-closed until a concrete runtime or API contract exists. |
| Additional remote video APIs | `generate` or `transfer` | No new API selected | Host would own credentials, artifact retention, and provider-specific polling/download policy | Fixtureable after API selection, but current value duplicates Cosmos/Runway hardening | Credible only after provider-specific artifact policy is known | Moderate: signed URL, retention, and provider churn risks | 8 | Deferred. Finish [#134](https://github.com/AbdelStark/worldforge/issues/134) before adding another remote media provider. |
| Simulator bridges | Future `predict`, `generate`, or host workflow, depending on bridge | No selected simulator bridge contract | Host owns simulator process, assets, controllers, safety policy, and durable storage | Not ready; needs scene/state boundary and host-owned process model first | Not credible as a provider smoke until state/artifact schema exists | High: simulator setup and controller assumptions can leak into core | 6 | Deferred. Revisit after the spatial/scene boundary and state-artifact fixtures exist. |
| New embodied policy stacks beyond LeRobot and GR00T | `policy` | Candidate families include OpenPI-style and OpenVLA-style stacks, not score/predict providers | Host owns checkpoints, robot runtime, action translators, safety, and lab process | Possible with injected policy outputs, but action translation and safety review dominate | Prepared-host only and expensive; no checkout-safe robot evidence by default | Moderate to high: heavy runtime and robot-safety burden | 8 | Deferred. Finish existing LeRobot/GR00T evidence and operator workflows before adding another policy runtime. |

## Active Cohort

The selected cohort contains three active work items and no public catalog expansion:

1. **JEPA-WMS/public JEPA score evidence.** Complete [#133](https://github.com/AbdelStark/worldforge/issues/133) and then [#137](https://github.com/AbdelStark/worldforge/issues/137). The first implementation focus is score-result evidence, runtime manifest coverage, finite output validation, JSON-native metadata, and explicit failure typing.
2. **Cosmos/Runway remote media retention hardening.** Complete [#134](https://github.com/AbdelStark/worldforge/issues/134) before adding any new remote video API. The focus is artifact lifetime, expired/unsupported media handling, safe local digests/paths, retry exhaustion, and signed-URL redaction.
3. **Nano World Model score-candidate reconnaissance.** Use [#158](https://github.com/AbdelStark/worldforge/issues/158) for a host-owned optional-runtime contract design. It is not a provider catalog entry until a real callable score boundary, fixtures, event redaction, and prepared-host smoke path exist.

This active cohort deliberately excludes new scaffold reservations.

## Deferred Candidates

| Candidate | Concrete blocker | Revisit trigger |
| --- | --- | --- |
| Genie runtime/API | No supported automation API or official runtime contract is documented for WorldForge to wrap. | A maintained upstream runtime or hosted API exposes a callable artifact-generation contract with license, inputs, outputs, and smoke evidence. |
| Spatial/3D scene provider | WorldForge does not yet have a typed scene artifact schema or one selected provider API. | [#138](https://github.com/AbdelStark/worldforge/issues/138) selects a JSON-native scene boundary and [#143](https://github.com/AbdelStark/worldforge/issues/143) adds fixtures/validation. |
| Additional remote video APIs | Current production risk is in artifact retention and redaction for existing beta adapters, not breadth. | [#134](https://github.com/AbdelStark/worldforge/issues/134) closes and a new API offers a distinct capability or user workflow. |
| Simulator bridges | Simulator process ownership, scene/state translation, asset retention, and safety boundaries are not provider-ready. | Scene/state artifacts have stable schemas and a host-owned simulator process design exists. |
| New embodied policy stacks | Existing LeRobot and GR00T paths still need stronger evidence, workbench, and operator-runbook coverage. | Provider live-smoke evidence registry and adapter workbench paths make policy promotion repeatable. |
| NanoWM `predict` or `generate` surfaces | Score is the only plausible first contract. Visual rollouts are not yet typed as WorldForge prediction payloads or media artifacts. | The score path is proven and a separate design records prediction/artifact shape, fidelity limits, and validation fixtures. |

## Public Claim Guardrails

- The generated provider catalog remains unchanged by this record.
- README provider tables remain unchanged by this record.
- `genie` remains a capability-fail-closed scaffold.
- `jepa-wms` remains a direct-construction candidate until runtime behavior and smoke evidence are credible.
- `nanowm` is not a provider name in the package, catalog, docs index, or auto-registration policy.
- Deferred candidates must not be added as placeholders merely to reserve names.

## Recommended Issue Order

Use this sequence unless a maintainer explicitly reprioritizes:

1. Close this selection record through [#130](https://github.com/AbdelStark/worldforge/issues/130).
2. Complete [#133](https://github.com/AbdelStark/worldforge/issues/133) because it is the highest-scoring new evidence path and unlocks [#137](https://github.com/AbdelStark/worldforge/issues/137) and [#144](https://github.com/AbdelStark/worldforge/issues/144).
3. Complete [#134](https://github.com/AbdelStark/worldforge/issues/134) because it hardens existing beta media providers and also unlocks [#144](https://github.com/AbdelStark/worldforge/issues/144).
4. Complete [#137](https://github.com/AbdelStark/worldforge/issues/137) only after [#133](https://github.com/AbdelStark/worldforge/issues/133) establishes evidence.
5. Treat [#158](https://github.com/AbdelStark/worldforge/issues/158) as a design/reconnaissance issue until it proves a callable score boundary.
6. Do not start [#138](https://github.com/AbdelStark/worldforge/issues/138), [#139](https://github.com/AbdelStark/worldforge/issues/139), [#143](https://github.com/AbdelStark/worldforge/issues/143), or new policy/provider expansions until their blockers above are cleared.

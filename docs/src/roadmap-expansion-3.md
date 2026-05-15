# Roadmap Expansion 3

This is the third expansion batch after the original provider/platform tracks, the continuation
plan, and the first two 30-issue roadmap expansions. It is intentionally additive: it does not
reopen completed quality, showcase, or feature work, and it does not duplicate the now-closed items
from the first two expansions. Each issue follows the same template (Context, Problem /
Opportunity, Proposed Scope, Out of Scope, Acceptance Criteria, Validation, References) used by
the prior expansions.

The plan stays split into the same three streams, with ten implementation issues each:

- Production Grade, Quality, DevX, And Docs
- Demos, End-to-End Showcases, And Use Cases
- New Features

Cross-stream dependencies are noted inline so the order of work matches the build order of the
underlying primitives. Shared constraints from prior expansions remain unchanged: optional runtimes
stay host-owned, provider capabilities stay truthful, deterministic tests are contract signals
rather than physical-fidelity claims, and public artifacts must be safe to attach unless clearly
marked local-only.

## Stream 1 — Production Grade, Quality, DevX, And Docs

Goal: bring the public surface closer to a 1.0-ready discipline. Add the gates and contracts that
adopters need to integrate confidently — static typing, locked export surface, doctor JSON
guarantees, anchor and CHANGELOG integrity, runtime manifest completeness, concurrent persistence
boundaries, workflow file linting, stable error codes, and CHANGELOG-to-release-notes round-trip.

Milestone: `Roadmap: Quality`.

| # | Title | Priority | Effort |
|---|-------|----------|--------|
| [#260](https://github.com/AbdelStark/worldforge/issues/260) | WF-PQDX3-001: Add static type-check gate (Pyright) for the public package surface | p1 | M |
| [#261](https://github.com/AbdelStark/worldforge/issues/261) | WF-PQDX3-002: Add a snapshot test for the public Python export surface | p2 | S |
| [#262](https://github.com/AbdelStark/worldforge/issues/262) | WF-PQDX3-003: Add a stable JSON contract guarantee for `worldforge doctor` output | p1 | M |
| [#263](https://github.com/AbdelStark/worldforge/issues/263) | WF-PQDX3-004: Add a docs cross-reference and anchor link gate | p2 | S |
| [#264](https://github.com/AbdelStark/worldforge/issues/264) | WF-PQDX3-005: Add a CHANGELOG.md structural format gate | p2 | S |
| [#265](https://github.com/AbdelStark/worldforge/issues/265) | WF-PQDX3-006: Enforce provider runtime manifest completeness for every catalog provider | p1 | S |
| [#266](https://github.com/AbdelStark/worldforge/issues/266) | WF-PQDX3-007: Add a concurrent persistence regression test for the single-writer boundary | p1 | M |
| [#267](https://github.com/AbdelStark/worldforge/issues/267) | WF-PQDX3-008: Add an actionlint gate for GitHub Actions workflow files | p2 | S |
| [#268](https://github.com/AbdelStark/worldforge/issues/268) | WF-PQDX3-009: Add a stable error code registry and docs index | p2 | M |
| [#269](https://github.com/AbdelStark/worldforge/issues/269) | WF-PQDX3-010: Add a CHANGELOG to release-notes round-trip test | p2 | S |

## Stream 2 — Demos, End-to-End Showcases, And Use Cases

Goal: convert the project's existing surface area into adoption material. Add the recorded
sessions, notebooks, narrative walkthroughs, and templates that turn the existing demos into a
coherent story for new users, including operators who already run a real robot.

Milestone: `Roadmap: Showcases`.

| # | Title | Priority | Effort |
|---|-------|----------|--------|
| [#270](https://github.com/AbdelStark/worldforge/issues/270) | WF-DEMO3-001: Publish VHS-recorded CLI tours for the first-run workflow | p2 | M |
| [#271](https://github.com/AbdelStark/worldforge/issues/271) | WF-DEMO3-002: Publish Jupyter notebook walkthroughs for the Python API | p1 | M |
| [#272](https://github.com/AbdelStark/worldforge/issues/272) | WF-DEMO3-003: Add a TheWorldHarness keyboard-driven tour gallery | p2 | S |
| [#273](https://github.com/AbdelStark/worldforge/issues/273) | WF-DEMO3-004: Add a scenario to release-evidence narrative walkthrough | p2 | M |
| [#274](https://github.com/AbdelStark/worldforge/issues/274) | WF-DEMO3-005: Add an adopt-your-robot 20-minute guided demo | p1 | M |
| [#275](https://github.com/AbdelStark/worldforge/issues/275) | WF-DEMO3-006: Add a capability protocol registration mini-demo | p2 | S |
| [#276](https://github.com/AbdelStark/worldforge/issues/276) | WF-DEMO3-007: Add a provider migration walkthrough (BaseProvider to capability protocol) | p2 | S |
| [#277](https://github.com/AbdelStark/worldforge/issues/277) | WF-DEMO3-008: Add an end-to-end incident-response triage walkthrough | p1 | M |
| [#278](https://github.com/AbdelStark/worldforge/issues/278) | WF-DEMO3-009: Add a benchmark sweep showcase across mock provider configurations | p2 | M |
| [#279](https://github.com/AbdelStark/worldforge/issues/279) | WF-DEMO3-010: Add an external adoption case-study template and gallery | p2 | S |

## Stream 3 — New Features

Goal: extend the framework's capability where the prior expansions left obvious next steps. Cost
accounting, named snapshots, run retention, capability-aware deltas, audit logs, scenario
inheritance, a Prometheus exporter, trace redaction policy, a non-mutating preview probe, and a
pluggable persistence backend interface. None of these change the optional-runtime boundary, and
several are designed to support new host-owned implementations without pulling them into base
dependencies.

Milestone: `Roadmap: Features`.

| # | Title | Priority | Effort |
|---|-------|----------|--------|
| [#280](https://github.com/AbdelStark/worldforge/issues/280) | WF-FEAT3-001: Add provider cost and usage accounting | p1 | M |
| [#281](https://github.com/AbdelStark/worldforge/issues/281) | WF-FEAT3-002: Add named world snapshot save, list, restore, and delete | p1 | M |
| [#282](https://github.com/AbdelStark/worldforge/issues/282) | WF-FEAT3-003: Add run artifact retention policy with `worldforge runs prune` | p2 | M |
| [#283](https://github.com/AbdelStark/worldforge/issues/283) | WF-FEAT3-004: Add capability-aware comparison report deltas | p2 | M |
| [#284](https://github.com/AbdelStark/worldforge/issues/284) | WF-FEAT3-005: Add an append-only world audit log artifact | p2 | M |
| [#285](https://github.com/AbdelStark/worldforge/issues/285) | WF-FEAT3-006: Add scenario inheritance via an `extends` field | p2 | M |
| [#286](https://github.com/AbdelStark/worldforge/issues/286) | WF-FEAT3-007: Add a Prometheus metrics exporter behind an optional extra | p2 | M |
| [#287](https://github.com/AbdelStark/worldforge/issues/287) | WF-FEAT3-008: Add workflow trace redaction allow and deny policy rules | p2 | S |
| [#288](https://github.com/AbdelStark/worldforge/issues/288) | WF-FEAT3-009: Add a non-mutating provider preview probe | p2 | M |
| [#289](https://github.com/AbdelStark/worldforge/issues/289) | WF-FEAT3-010: Add a pluggable persistence backend interface with local JSON default | p1 | M |

## Cross-Stream Dependencies

- [#260](https://github.com/AbdelStark/worldforge/issues/260) (Pyright gate) → [#261](https://github.com/AbdelStark/worldforge/issues/261) (export snapshot): typed enforcement under a static check makes the snapshot test catch type drift too.
- [#264](https://github.com/AbdelStark/worldforge/issues/264) (CHANGELOG format) → [#269](https://github.com/AbdelStark/worldforge/issues/269) (round-trip): release-notes round-trip assumes the format gate is in place.
- [#266](https://github.com/AbdelStark/worldforge/issues/266) (concurrent persistence) ↔ [#289](https://github.com/AbdelStark/worldforge/issues/289) (persistence backend interface): the concurrent-write contract decided in #266 is the promise the pluggable interface must keep.
- [#281](https://github.com/AbdelStark/worldforge/issues/281) (snapshots) ← [#289](https://github.com/AbdelStark/worldforge/issues/289): snapshots persist through the new pluggable backend so future host-owned backends inherit snapshot semantics.
- [#280](https://github.com/AbdelStark/worldforge/issues/280) (cost accounting) → [#278](https://github.com/AbdelStark/worldforge/issues/278) (benchmark sweep), [#286](https://github.com/AbdelStark/worldforge/issues/286) (Prometheus): cost units land in the sweep report and the Prometheus exporter.
- [#285](https://github.com/AbdelStark/worldforge/issues/285) (scenario inheritance) → [#278](https://github.com/AbdelStark/worldforge/issues/278) (benchmark sweep): the sweep gallery uses inheritance to share a base.
- [#262](https://github.com/AbdelStark/worldforge/issues/262) (doctor JSON contract) + [#268](https://github.com/AbdelStark/worldforge/issues/268) (error codes) → [#277](https://github.com/AbdelStark/worldforge/issues/277) (incident triage walkthrough): the walkthrough cites both stable contracts.
- [#264](https://github.com/AbdelStark/worldforge/issues/264) (CHANGELOG format) + [#269](https://github.com/AbdelStark/worldforge/issues/269) (round-trip) → [#273](https://github.com/AbdelStark/worldforge/issues/273) (scenario to release-evidence walkthrough): the walkthrough reaches a release-evidence draft assembled by the verified generator.

## Notes

- The standard 10-issues-per-stream count is preserved. No deviation.
- Priority distribution: 8 × p1, 22 × p2, 0 × p0. Pre-1.0 work has no current release blockers;
  the p1 items are the load-bearing maturation steps.
- Effort distribution: 11 × S, 19 × M, 0 × L. Each issue is sized to a single focused PR; the
  larger features (cost accounting, persistence interface) intentionally stay M by deferring
  host-owned implementations.
- Labels reused: `enhancement`, `documentation`, `roadmap`, capability/category labels
  (`quality`, `testing`, `ci`, `persistence`, `observability`, `provider`, `harness`, etc.),
  stream labels (`stream: production-quality`, `stream: demos-showcases`, `stream: new-features`),
  and `good first issue` / `help wanted` where genuinely applicable.
- Labels created for this expansion: `priority:p0`, `priority:p1`, `priority:p2`, `effort:s`,
  `effort:m`, `effort:l`, `roadmap: expansion-3`.
- Milestones created: `Roadmap: Quality` (#1), `Roadmap: Showcases` (#2), `Roadmap: Features`
  (#3).

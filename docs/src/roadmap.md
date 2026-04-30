# Roadmap

WorldForge is pre-1.0. The roadmap is intentionally capability-driven rather than feature-count
driven: every public surface should stay truthful, typed, reproducible, and host-owned where
upstream runtimes or robot controllers are involved.

## Current Focus

- Treat the provider and platform production track as complete baseline infrastructure; use fresh
  selection records for new provider batches instead of extending the original tracker.
- Keep the provider catalog honest: adapters advertise only capabilities implemented end to end.
- Make checkout validation boring: one command should exercise lint, docs, tests, coverage,
  package build, package install, and dependency audit.
- Preserve reproducible artifacts for evaluation and benchmark claims.
- Keep optional model runtimes out of the base package while making their wrapper commands clear
  enough to run on a prepared host.
- Grow TheWorldHarness as the visual inspection layer for worlds, providers, evals, benchmarks,
  and packaged flows.

## Near-Term Milestones

| Area | Milestone |
| --- | --- |
| Provider adapters | Promote scaffold adapters only after upstream-runtime contracts, fixtures, and failure modes are validated. |
| Benchmarking | Attach provenance and preserved input fixtures to any published benchmark number. |
| Evaluation | Expand suite coverage while keeping scores framed as deterministic contract signals. |
| Harness | Continue world editing, run inspection, report export, and provider diagnostics through optional Textual screens. |
| Release engineering | Prefer signed, attested, tag-verified releases and trusted publishing. |

For issue planning, use the detailed [Provider And Platform Roadmap](./provider-platform-roadmap.md).
It breaks real provider implementation, production harness work, reference host applications,
observability, monitoring, logging, operations, and release hardening into issue-ready workstreams
with dependencies and acceptance criteria.

## Non-Goals

- WorldForge will not bundle LeWorldModel, LeRobot, GR00T, torch, CUDA, checkpoints, datasets, or
  robot controllers into the base package.
- Scaffold adapters will not be presented as real integrations.
- Deterministic evaluation or benchmark outputs will not be used as physical-fidelity claims.
- Local JSON persistence will not be treated as a service-grade concurrent datastore without a
  separate design.

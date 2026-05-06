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

For historical issue planning, use the detailed
[Provider And Platform Roadmap](./provider-platform-roadmap.md). That first production track is
complete and should be treated as baseline infrastructure.

For the next implementation batch, use the
[Roadmap Continuation](./roadmap-continuation.md). It narrows the project to three current streams:
provider evidence and runtime cohorts, evaluation evidence and claim integrity, and operator
workflow plus adapter authoring.

For the expanded next roadmap batch, use the
[Roadmap Expansion](./roadmap-expansion.md). It defines 30 structured issues across production
grade quality/DevX/docs, demos and end-to-end showcases, and new features. Nano World Model work is
excluded because that issue is already assigned.

For the active provider evidence cohort, use the
[Provider Cohort Selection Record](./provider-cohort-selection.md). It selects the next provider
work items, records explicit deferrals, and keeps public provider capability claims unchanged until
implementation evidence exists.

## Non-Goals

- WorldForge will not bundle LeWorldModel, LeRobot, GR00T, torch, CUDA, checkpoints, datasets, or
  robot controllers into the base package.
- Scaffold adapters will not be presented as real integrations.
- Deterministic evaluation or benchmark outputs will not be used as physical-fidelity claims.
- Local JSON persistence will not be treated as a service-grade concurrent datastore without a
  separate design.

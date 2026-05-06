# Documentation Map

Use this page as the reader path map for the public docs. It keeps roadmap history discoverable
while routing active work to the pages that own executable contracts.

## Reader Paths

| Reader | Start here | Then use | Success signal |
| --- | --- | --- | --- |
| First-time local user | [Quick Start](./quickstart.md) | [CLI Reference](./cli.md), [Examples And CLI Commands](./examples.md) | a mock world, provider diagnostic, or checkout-safe demo runs locally |
| Provider author | [Provider Authoring Guide](./provider-authoring-guide.md) | [Providers](./providers/README.md), [Capability Fixture Corpus](./fixtures.md), [Public API Stability](./api-stability.md) | provider capability, profile, fixtures, docs, and tests agree |
| Operator | [Operations](./operations.md) | [User And Operator Playbooks](./playbooks.md), [Security](./security.md), [Artifact Integrity](./artifact-integrity.md) | diagnostics, run manifests, safe bundles, and recovery commands are available |
| Evaluator or research user | [Evaluation](./evaluation.md) | [Benchmarking](./benchmarking.md), [Claim-To-Evidence Map](./claim-evidence-map.md), [Live Smoke Evidence Registry](./live-smoke-evidence.md) | claims point to preserved reports and clear claim boundaries |
| Demo or showcase user | [Examples And CLI Commands](./examples.md) | [Demo Showcase Workflows](./demo-showcases.md), [Use Case Cookbook](./use-case-cookbook.md), [Robotics Replay Showcase](./robotics-showcase.md), [TheWorldHarness](./theworldharness.md), [Rerun Integration](./rerun.md) | checkout-safe demos or prepared-host showcase commands produce artifacts |
| Release maintainer | [Engineering Quality](./quality.md) | [Artifact Integrity](./artifact-integrity.md), [Operations](./operations.md), [Changelog](./changelog.md) | local gates, package checks, audit, evidence JSON, and release notes line up |

## Roadmap History

Roadmap pages remain public because they preserve why the project chose a direction. They are not a
substitute for active issue state or executable docs.

| Page | Role |
| --- | --- |
| [Roadmap](./roadmap.md) | current top-level public direction and links to historical tracks |
| [Roadmap Expansion](./roadmap-expansion.md) | 30-issue expansion record created for the current production, demo, and feature streams |
| [Roadmap Continuation](./roadmap-continuation.md) | earlier continuation plan and completed coordination notes |
| [Provider And Platform Roadmap](./provider-platform-roadmap.md) | prior provider-platform tracker and evidence history |

Active work should be tracked in GitHub issues. When a roadmap item changes public behavior, update
the owning docs page, changelog, tests, and this map if the reader path changes.

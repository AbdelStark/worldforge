# Introduction

WorldForge is a Python integration layer for testable physical-AI world-model workflows. It gives
providers, score models, embodied policies, and media generators explicit capability contracts,
then adds world state, planning, evaluation, benchmarking, diagnostics, and CLI tools for local
experiments and adapter development.

The project is built around a strict provider boundary:

- predictive models roll state forward through `predict`
- score models rank candidate action sequences through `score`
- embodied policies propose action chunks through `policy`
- video and media systems expose `generate` or `transfer`
- auxiliary models expose `reason` or `embed` only when those operations are implemented directly

This keeps provider semantics honest. A JEPA cost model is not treated as a video generator. A VLA
robot policy is not treated as a predictive dynamics model. A media generation API is not treated
as proof of controllable physical planning.

WorldForge is for Python developers building provider adapters, local physical-AI experiments,
world-model planning loops, evaluation harnesses, and testable prototypes. It is not a hosted
control plane and it does not own checkpoints, robot runtimes, production telemetry, or durable
multi-writer persistence.

## Documentation Map

For the complete reader-path map, use [Documentation Map](./docs-map.md).

| Need | Start here |
| --- | --- |
| Install, create a world, and run the mock provider | [Quick Start](./quickstart.md) |
| Find an exact CLI command or optional runtime smoke | [CLI Reference](./cli.md) |
| Understand capability names and provider boundaries | [World Model Taxonomy](./world-model-taxonomy.md) |
| See module responsibilities and planning pipelines | [Architecture](./architecture.md) |
| Record events, worlds, plans, and benchmarks in Rerun | [Rerun Integration](./rerun.md) |
| Validate a checkout, diagnose providers, run smokes, or prepare a release | [User And Operator Playbooks](./playbooks.md) |
| Add or promote a provider adapter | [Provider Authoring Guide](./provider-authoring-guide.md) |
| Check package, testing, typing, and ML-runtime quality rules | [Engineering Quality](./quality.md) |

If a page changes public behavior, update the linked operational page and the changelog in the same
branch. WorldForge docs are treated as part of the package contract, not as post-release notes.

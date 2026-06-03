# Introduction

WorldForge is a harness framework for building world-model-based workflows for physical AI. It is
the application builder's counterpart to model-training stacks like Stable World Model: it helps
roboticists and physical-AI builders compose, evaluate, and benchmark workflows built on top of
world models, rather than train them.

The whole framework is organized around one backbone loop: **planning and scoring action candidates
with an action-conditioned predictive world model, in latent space.**

- a `policy` provider proposes candidate action chunks from an observation
- a `predict` provider rolls candidates forward as action-conditioned dynamics
- a `score` provider ranks candidates as a cost oracle
- `LatentMPCController` owns the caller-side CEM/receding-horizon optimizer that ties them together
- evaluation and benchmarking compare configurations so a builder can select the best one

The provider boundary is strict and fail-closed, which keeps semantics honest: a JEPA cost model is
not treated as a video generator, and a VLA robot policy is not treated as a predictive dynamics
model. The world model is a dynamics/cost oracle, not a controller — the controller stays a pure
optimizer.

WorldForge is for Python developers and roboticists composing provider-backed planning loops,
evaluation harnesses, and benchmarks. It is not a hosted control plane, a world generator, or a
training framework, and it does not own checkpoints, robot runtimes, production telemetry, or
durable multi-writer persistence.

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

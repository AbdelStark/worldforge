# Introduction

WorldForge is a Python framework for orchestrating world-model workflows.

The project is structured as a framework first:

- a typed package under `src/worldforge/`
- a deterministic mock provider for local work
- a provider registry for real, optional, and scaffold adapters
- framework primitives for state, planning, comparison, evaluation, and benchmarking
- action-scoring support for cost-model providers such as LeWorldModel
- action-policy support for embodied VLA providers such as NVIDIA Isaac GR00T

The goal is to provide a clean, public-facing framework surface that fits naturally into the
Python ML ecosystem.

WorldForge uses a precise definition of "world model": an action-conditioned predictive model
that helps a caller evaluate, rank, or roll out possible futures from observations, state, actions,
and goals. That definition is narrower than the current hype cycle, where the same term may refer
to video generators, 3D scene tools, simulation platforms, or cognitive architectures. Read
[World Model Taxonomy](./world-model-taxonomy.md) before evaluating provider semantics, then read
[Architecture](./architecture.md) for the end-to-end runtime pipeline. New adapters should follow
the [Provider Authoring Guide](./provider-authoring-guide.md).

Embodied policies are intentionally separate from predictive world models. GR00T proposes action
chunks from observations and instructions; WorldForge can execute those actions directly or pair
them with a score provider for policy+score planning.

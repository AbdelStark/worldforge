# Introduction

WorldForge is a Python framework for orchestrating world-model workflows.

The project is structured as a framework first:

- a typed package under `src/worldforge/`
- a deterministic mock provider for local work
- a provider registry for real, optional, and scaffold adapters
- framework primitives for state, planning, comparison, evaluation, and benchmarking
- action-scoring support for cost-model providers such as LeWorldModel

The goal is to provide a clean, public-facing framework surface that fits naturally into the Python ML ecosystem.

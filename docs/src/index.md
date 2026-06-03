---
hide:
  - navigation
  - toc
---

# WorldForge

**A harness framework for building world-model-based workflows for physical AI systems.**

WorldForge is the application builder's counterpart to model-training stacks like Stable World
Model: it helps roboticists and physical-AI builders *compose, evaluate, and benchmark* workflows
built on top of world models — so they can pick the best provider and configuration for a task —
rather than *train* the models. The whole framework is organized around one backbone loop: planning
and scoring action candidates with an action-conditioned predictive world model, in latent space.

[Get started](./quickstart.md){ .md-button .md-button--primary }
[Read the introduction](./introduction.md){ .md-button }

## Where to go next

<div class="grid cards" markdown>

- **Quick Start**

    Install WorldForge, create a world, and run the mock provider end to end.

    [Quick Start](./quickstart.md)

- **CLI Reference**

    Look up an exact CLI command or optional-runtime smoke.

    [CLI Reference](./cli.md)

- **Architecture**

    See module responsibilities and the planning pipelines.

    [Architecture](./architecture.md)

- **Provider Authoring**

    Add or promote a provider adapter against the capability contracts.

    [Provider Authoring Guide](./provider-authoring-guide.md)

- **Documentation Map**

    Follow the complete reader path across every section.

    [Documentation Map](./docs-map.md)

- **Evidence And Evaluation**

    Understand how claims map to deterministic, reproducible evidence.

    [Evaluation](./evaluation.md)

</div>

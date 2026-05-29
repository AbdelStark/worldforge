# Support

WorldForge is pre-1.0 open-source software. Support is best-effort and centered on reproducible
technical reports.

## Before Opening An Issue

Run the checkout-safe baseline first:

```bash
uv sync --group dev
uv lock --check
uv run ruff check src tests examples scripts
uv run ruff format --check src tests examples scripts
uv run python scripts/generate_provider_docs.py --check
uv run mkdocs build --strict
uv run pytest
```

For provider configuration problems, include:

```bash
uv run worldforge doctor
uv run worldforge provider info <provider>
```

For optional runtimes such as LeWorldModel, LeRobot, or GR00T, also include the exact wrapper
command, host OS, Python version, checkpoint or policy identifier, and whether the failure happens
before dependency import, checkpoint loading, provider call, or action translation.

## Where To Ask

- Bugs and reproducible failures: GitHub Issues.
- Provider adapter proposals: use the provider adapter issue template.
- Documentation gaps: GitHub Issues with the docs template.
- Security reports: follow [SECURITY.md](./SECURITY.md); do not open a public issue.

## Scope

WorldForge owns the Python framework, provider capability contracts, CLI, local JSON persistence,
evaluation, benchmarking, diagnostics, and packaged demos. Host-owned dependencies such as CUDA,
torch, robot controllers, checkpoints, datasets, credentials, and remote provider availability are
outside the base package support boundary.

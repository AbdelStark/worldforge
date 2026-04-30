# Support

WorldForge support is best-effort and reproduction-first.

Before opening an issue, run:

```bash
uv sync --group dev
uv lock --check
uv run ruff check src tests examples scripts
uv run ruff format --check src tests examples scripts
uv run python scripts/generate_provider_docs.py --check
uv run mkdocs build --strict
uv run pytest
```

For provider configuration issues, include:

```bash
uv run worldforge doctor
uv run worldforge provider info <provider>
```

It is safe to attach provider profiles, doctor output, provider health, runtime manifests,
`config_summary().to_dict()` output, benchmark reports, and preserved JSON inputs after checking
that host-specific object names are acceptable to share. Do not attach `.env` files, raw provider
request bodies, bearer tokens, signed artifact URLs with query strings, private checkpoint files,
robot controller credentials, or logs captured before provider-event redaction.

For optional runtimes, include the exact wrapper command, host OS, Python version, checkpoint or
policy identifier, and the stage that failed: dependency import, checkpoint loading, provider call,
or action translation.

Use:

- GitHub Issues for reproducible bugs, provider proposals, docs gaps, and eval or benchmark issues.
- The Security tab for vulnerabilities.
- Preserved JSON inputs, budget files, and reports for benchmark or evaluation claims.

See the canonical [Support Policy](https://github.com/AbdelStark/worldforge/blob/main/SUPPORT.md).

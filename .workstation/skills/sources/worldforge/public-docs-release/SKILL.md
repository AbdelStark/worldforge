---
name: public-docs-release
description: "Use for WorldForge README, docs, changelog, generated provider docs, MkDocs navigation, version/release metadata, public positioning, and release or publish readiness checks. Keeps public surfaces synchronized without hype or generated-doc drift."
---

# Public Docs And Release

## Voice

- Serious, precise, maintainer-style.
- No hype, no tool branding, no inflated physical-fidelity claims.
- Use "integration layer" for the project frame. Treat "typed" and "local JSON" as supporting details, not the headline.
- README stays concise; route operational depth to `docs/src/playbooks.md`.
- Public docs should help a maintainer reproduce evidence. Avoid narrative process notes and
  personal collaboration context.

## Synchronization Rules

| Change | Usually update |
| --- | --- |
| Provider capability/env var | provider docs, generated catalog, README table, `.env.example`, changelog, AGENTS/CLAUDE if agent-relevant |
| CLI command/help | README, `docs/src/cli.md`, `docs/src/examples.md`, help snapshots |
| Public Python API/error behavior | `docs/src/api/python.md`, changelog, tests, AGENTS/CLAUDE if contract-relevant |
| Runtime/smoke workflow | README, playbooks, operations, provider page, support docs |
| Docs page add/remove | `mkdocs.yml` and `docs/src/SUMMARY.md` |
| Release/version | `pyproject.toml`, `uv.lock`, README/version text, `CITATION.cff`, changelog, docs |

## Generated Docs

Do not hand-edit provider catalog blocks. Change provider profile/catalog metadata, then run:

```bash
uv run python scripts/generate_provider_docs.py
uv run python scripts/generate_provider_docs.py --check
```

## Operational Docs Standard

Every new runtime, provider, persistence, benchmark, or release workflow should include:

1. Command to run.
2. Expected success signal.
3. First triage step when it fails.

## Definition Of Done

- Source docs, generated docs, README tables, changelog, and navigation are synchronized for the changed public behavior.
- Generated provider catalog blocks were regenerated from metadata instead of hand-edited.
- Commands in docs are still executable or explicitly marked host-owned/credentialed/illustrative.
- `mkdocs build --strict` and the relevant docs drift checks pass, or any skipped gate has a concrete blocker.

## Sharp Edges

| Symptom | Cause | Fix |
| --- | --- | --- |
| MkDocs strict warning | Bad link/nav/SUMMARY drift | Fix source page and sync nav/SUMMARY |
| Provider table changes disappear | Edited generated block by hand | Change catalog/profile metadata and regenerate |
| CLI snapshot fails after copy edit | Help text changed | Update `tests/test_cli_help_snapshots.py` intentionally |

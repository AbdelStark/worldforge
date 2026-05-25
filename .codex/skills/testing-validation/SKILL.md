---
name: testing-validation
description: "Use when selecting, running, or fixing WorldForge validation: pytest, coverage, ruff, generated provider docs, MkDocs strict build, package contract, CI failures, and release gates. Produces the smallest credible command set first, then escalates to full validation when public behavior changes."
---

# Testing And Validation

## Choose The Gate

| Change | Minimum useful validation |
| --- | --- |
| Python logic | `uv run pytest tests/test_target.py -q` plus ruff |
| Provider behavior | provider-focused pytest, fixtures, contract helper, provider-doc check |
| CLI help/output | targeted CLI tests and help snapshots |
| Docs/provider catalog | provider-doc check and `uv run mkdocs build --strict` |
| Public API/package surface | full public gate below |
| TUI/harness | focused harness tests plus `--extra harness` coverage when relevant |

## Standard Commands

Focused gate:

```bash
uv run ruff check src tests examples scripts
uv run ruff format --check src tests examples scripts
uv run pytest tests/test_target.py -q
```

Docs gate:

```bash
uv run python scripts/generate_provider_docs.py --check
uv run mkdocs build --strict
```

Public behavior/package gate:

```bash
uv lock --check
uv run ruff check src tests examples scripts
uv run ruff format --check src tests examples scripts
uv run python scripts/generate_provider_docs.py --check
uv run mkdocs build --strict
uv run pytest
uv run --extra harness pytest --cov=src/worldforge --cov-report=term-missing --cov-fail-under=90
bash scripts/test_package.sh
uv build --out-dir dist --clear --no-build-logs
```

Dependency audit for release work:

```bash
tmp_req="$(mktemp requirements-audit.XXXXXX)"
uv export --frozen --all-groups --no-emit-project --no-hashes -o "$tmp_req" >/dev/null
uvx --from pip-audit pip-audit -r "$tmp_req" --no-deps --disable-pip --progress-spinner off
rm -f "$tmp_req"
```

## Rules

- Reproduce the failing command before broad edits.
- Add regression tests for bug fixes and documented failure modes.
- Keep `src tests examples scripts` in Ruff targets.
- Keep `--cov-fail-under=90`; add tests instead of lowering it.
- Do not replace deterministic tests with live-service requirements.
- Report skipped gates with the concrete blocker.

## Sharp Edges

| Symptom | Cause | Fix |
| --- | --- | --- |
| Provider docs check fails | Generated README/provider catalog stale | Run generator without `--check`, inspect diff |
| Coverage barely fails | New branch lacks focused tests | Add direct failure-path tests instead of weakening gate |
| Package contract fails only in isolated venv | Missing package data or import path | Inspect `pyproject.toml` hatch settings and `scripts/test_package.sh` |
| MkDocs strict fails | Nav/SUMMARY/docs link drift | Sync `mkdocs.yml`, `docs/src/SUMMARY.md`, and links |

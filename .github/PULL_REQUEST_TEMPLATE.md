## Summary

- 

## Validation

- [ ] `uv lock --check`
- [ ] `uv run ruff check src tests examples scripts`
- [ ] `uv run ruff format --check src tests examples scripts`
- [ ] `uv run python scripts/generate_provider_docs.py --check`
- [ ] `uv run mkdocs build --strict`
- [ ] `uv run pytest`
- [ ] `uv run --extra harness pytest --cov=src/worldforge --cov-report=term-missing --cov-fail-under=90`
- [ ] `bash scripts/test_package.sh`

## Notes

- Public capability changes advertise only behavior implemented end to end.
- Optional runtime dependencies remain host-owned.
- Evaluation and benchmark claims include preserved inputs/artifacts.

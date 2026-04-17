# Contributing

```bash
uv sync --group dev
make lint
make test
make test-package
```

Key directories:

- `src/worldforge/`
- `src/worldforge/testing/`
- `tests/`
- `examples/`

Provider work belongs in `src/worldforge/providers/`. Keep adapter capabilities honest and add tests for every new supported path.

For adapter packages and in-repo providers, use the reusable contract helper:

```python
from worldforge.testing import assert_provider_contract

report = assert_provider_contract(provider)
print(report.exercised_operations)
```

Score-capable providers must pass provider-specific score fixtures:

```python
report = assert_provider_contract(
    provider,
    score_info=score_fixture["info"],
    score_action_candidates=score_fixture["action_candidates"],
)
```

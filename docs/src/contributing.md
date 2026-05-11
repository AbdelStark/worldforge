# Contributing

WorldForge contributions should keep code, tests, docs, and agent context in sync.

```bash
uv sync --group dev
uv lock --check
uv run ruff check src tests examples scripts
uv run ruff format --check src tests examples scripts
uv run python scripts/generate_provider_docs.py --check
uv run python scripts/check_docs_commands.py
uv run python scripts/check_wrapper_portability.py
uv run python scripts/check_optional_import_boundaries.py
uv run python scripts/check_core_performance.py
uv run mkdocs build --strict
uv run pytest
uv run --extra harness pytest --cov=src/worldforge --cov-report=term-missing --cov-fail-under=90
bash scripts/test_package.sh
uv build --out-dir dist --clear --no-build-logs
```

Before tags or package publishing, also run the locked dependency audit from
[Operations](./operations.md). If setup fails before the gate starts, run:

```bash
uv run python scripts/contributor_doctor.py --format markdown
uv run python scripts/contributor_doctor.py --format json
```

The contributor doctor checks Python 3.13, uv, source-tree shape, docs tooling, GitHub CLI auth
status, and optional runtime skip reasons without installing dependencies, reading secrets, or
assuming LeWorldModel, LeRobot, GR00T, or Rerun are present. Its Markdown output is safe to paste
into public issues.

`uv run python scripts/generate_provider_docs.py --check`,
`uv run python scripts/check_docs_commands.py`, `uv run python scripts/check_wrapper_portability.py`,
`uv run python scripts/check_optional_import_boundaries.py`, and `uv run mkdocs build --strict`
verify generated provider docs, documented command drift, wrapper portability, optional-runtime
import boundaries, and the MkDocs Material site in strict mode. `bash scripts/test_package.sh`
checks the wheel/sdist contents before installing the built wheel and running tests against the
installed package. See [Artifact Integrity](./artifact-integrity.md) for the release artifact
hashing and evidence-linking contract.

Before changing public imports, CLI flags, provider capabilities, or artifact schemas, classify the
surface through [Public API Stability](./api-stability.md) and the
[Artifact Schemas](./artifact-schemas.md) ownership map. Stable and provisional surfaces need a
deprecation or migration plan unless the change fixes a security exposure, false capability claim,
or persisted-state incoherence.

Key directories:

- `src/worldforge/models.py`: public data contracts and validation.
- `src/worldforge/framework.py`: runtime facade, worlds, planning, persistence, and diagnostics.
- `src/worldforge/providers/`: provider interfaces, catalog, adapters, and scaffolds.
- `src/worldforge/testing/`: reusable provider contract helpers.
- `src/worldforge/evaluation/`: deterministic evaluation suites.
- `src/worldforge/benchmark.py`: provider benchmark harness.
- `src/worldforge/observability.py`: provider event sinks.
- `docs/src/`: user docs, architecture, playbooks, provider pages, and API notes.
- `tests/`: behavior and regression tests.
- `examples/`: runnable examples and compatibility wrappers.
- `scripts/`: docs generation, scaffolding, package validation, and optional smokes.

Provider work belongs in `src/worldforge/providers/`. Keep adapter capabilities honest and add
tests for every new supported path.

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

## Contributor Triage And Labels

Use labels to make an issue's roadmap stream and evidence contract clear before work starts.

| Axis | Labels | Use when |
| --- | --- | --- |
| Roadmap stream | `stream: provider-evidence` | provider selection, runtime contracts, provider promotion, runtime manifests, upstream validation |
| Roadmap stream | `stream: evidence-integrity` | evals, benchmarks, budgets, preserved run evidence, release evidence, provenance, public claims |
| Roadmap stream | `stream: ops-authoring` | operator workflows, TheWorldHarness, adapter authoring loops, reference hosts, persistence, runbooks |
| Capability | `predict`, `generate`, `reason`, `embed`, `transfer`, `score`, `policy` | the issue changes or validates that public capability surface |
| Severity | `severity: blocking`, `severity: quality`, `type: hardening` | release blockers, quality regressions, validation/redaction/recovery hardening |
| Release scope | `release`, `release: provider-hardening-rc` | release process or named release-candidate scope |

Provider runtime issues should use the provider adapter template, `stream: provider-evidence`,
`provider`, the claimed capability labels, and any relevant `optional-dependency`, `robotics`,
`security`, or `research` labels. New runtime families or unclear upstream contracts need a
selection record before implementation. Provider promotion work must cite the provider authoring
guide promotion gate, runtime manifest, fixtures, docs, and live-smoke or explicit blocker
evidence.

Evaluation, benchmark, artifact, budget, report, or claim issues should use the eval/benchmark
template with `stream: evidence-integrity`. Release-candidate or public-claim issues need preserved
run evidence, an evidence bundle, or release evidence before closure.

Operator workflow issues should use `stream: ops-authoring` plus `operations`, `harness`,
`developer-experience`, `persistence`, `reliability`, or `examples` as appropriate. The issue should
name the command to run, expected success signal, first triage step, and recovery command.

Architecture, persistence-boundary, provider-selection, or runtime-ownership changes need a design
record or selection record before broad implementation.

Security-sensitive reports still route through the private Security tab. Do not open public issues
containing vulnerabilities, credentials, signed URLs, private endpoints, or host-local artifacts.

Before publishing a branch:

- run the full release gate from [User And Operator Playbooks](./playbooks.md).
- update provider docs and generated catalog tables for provider behavior changes.
- update [Python API](./api/python.md) for public API or exception changes.
- update [Architecture](./architecture.md) for new flows or ownership boundaries.
- update [Artifact Schemas](./artifact-schemas.md) for new or changed public artifact families.
- update [Operations](./operations.md) and [Playbooks](./playbooks.md) for new operator work.
- update `CHANGELOG.md` for user-visible changes.
- update `mkdocs.yml` when the docs navigation changes.
- update `AGENTS.md` for new commands, constraints, gotchas, or architecture facts.

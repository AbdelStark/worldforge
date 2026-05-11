# Engineering Quality Standards

WorldForge treats engineering quality as part of the public API. Provider capabilities, package
metadata, docs, tests, and optional robotics runtimes must stay aligned so users can reason about
what is installed, what is deterministic, and what remains host-owned.

## Reference Baseline

WorldForge's quality rules are grounded in the same upstream sources a production Python ML
framework should track:

- [Python Packaging User Guide: `pyproject.toml` metadata](https://packaging.python.org/specifications/declaring-project-metadata/)
  for static project metadata, build-system configuration, SPDX license metadata, entry points, and
  dependency declarations.
- [Python Packaging User Guide: packaging projects](https://packaging.python.org/tutorials/packaging-projects/)
  for `src` layout packaging and distribution structure.
- [uv package guide](https://docs.astral.sh/uv/guides/package/) for building and publishing
  packages through a modern build frontend while preserving the backend contract.
- [pytest good integration practices](https://docs.pytest.org/en/stable/explanation/goodpractices.html)
  for `src` layout test isolation and `--import-mode=importlib`.
- [Ruff linter configuration](https://docs.astral.sh/ruff/linter/) and
  [Ruff formatter guidance](https://docs.astral.sh/ruff/formatter/) for a single fast lint and
  format toolchain.
- [PEP 561](https://peps.python.org/pep-0561/) and the
  [typing distribution spec](https://typing.python.org/en/latest/spec/distributing.html) for
  shipping inline type information through `py.typed`.
- [PyTorch reproducibility notes](https://docs.pytorch.org/docs/stable/notes/randomness.html) for
  honest ML determinism boundaries: seeds reduce nondeterminism within a platform and release, but
  exact results are not guaranteed across releases, devices, or platforms.
- [scikit-learn developer guide](https://scikit-learn.org/dev/developers/develop.html) for stable
  public imports, estimator-style validation discipline, and explicit randomness contracts.
- [Scientific Python SPEC 0](https://scientific-python.org/specs/spec-0000/) for the expectation
  that scientific Python projects document support windows and dependency policy rather than
  letting compatibility drift silently.

## Project Rules

### Packaging

- The package source lives under `src/worldforge`, and tests run against installed/importable
  package semantics rather than accidental repository-root imports.
- `pyproject.toml` is the single source of truth for package metadata, Python support, scripts,
  optional extras, uv package mode, and tool configuration.
- Wheels contain runtime package files only. Source distributions contain tests, docs, examples,
  scripts, and release metadata so downstream users can inspect and rebuild the project.
- `src/worldforge/py.typed` is part of the wheel contract. Removing it is a typing regression.
- Optional ML and robotics runtimes stay outside the base dependency set. `torch`, LeRobot,
  LeWorldModel, GR00T, CUDA, robot controllers, checkpoints, and datasets are supplied by the host
  environment for the specific smoke or showcase that needs them.

### Testing

- `pytest` runs with `--import-mode=importlib` so tests do not depend on implicit `sys.path`
  mutation.
- Test fixtures must be deterministic unless a test explicitly validates nondeterministic runtime
  handling.
- Artifact and report tests should use `worldforge.testing.DeterministicClock`,
  `DeterministicIdFactory`, `deterministic_run_workspace`, `stable_snapshot`, and
  `stable_json_dumps` when they assert exact JSON or Markdown snapshots. Normalize temporary paths,
  generated IDs, and known volatile fields before comparing text.
- Exact snapshots are appropriate for stable artifact schemas, rendered user-facing report text,
  command snippets, schema-versioned manifests, and failure templates. Prefer semantic assertions
  for real provider latency, throughput, host paths, current git commits, live timestamps, optional
  runtime warnings, and other values whose truth depends on the host environment.
- Every provider capability must have both a positive contract test and a failure-mode test for the
  boundary it documents.
- Reusable provider contract helpers must use explicit exceptions instead of Python `assert`, so
  adapter validation does not disappear when tests run under optimized Python.
- Public exception assertions should match literal messages precisely enough to catch regressions
  without depending on unrelated text.
- Public CLI error contracts must preserve owner context, a first triage step, and safe wording.
  Regression tests should assert exact text only for stable messages; use semantic assertions for
  paths, timings, provider endpoints, and other host-owned values.
- `xfail` is strict. A test that starts passing should be investigated and either promoted or
  removed.

### Linting And Style

- Ruff owns formatting-compatible linting and import ordering for `src`, `tests`, `examples`, and
  `scripts`.
- The enforced Ruff surface includes bugbear-adjacent quality families for comprehensions,
  returns, simplification, pytest style, performance footguns, and Ruff-native correctness checks.
- Public `__all__` exports stay sorted so public API diffs are reviewable.
- Mutable class metadata such as Textual `BINDINGS` and `SCREENS` must be annotated as `ClassVar`
  to separate framework declarations from instance state.
- Tests use direct `pytest` imports and split compound assertions when doing so improves failure
  localization.

### ML And Robotics Boundaries

- Deterministic in-repo suites are contract harnesses, not evidence of physical fidelity.
- Real robotics showcase paths must state which runtime owns preprocessing, checkpoints,
  observations, action translation, safety checks, and hardware execution.
- WorldForge validates tensor and action boundaries; it must not pad, project, or reinterpret
  mismatched action spaces.
- Score providers expose `score`. Policy providers expose `policy`. Predictive world models expose
  `predict`. Branding must not override executable capability truth.
- Provider events are log-facing records. Targets, messages, and metadata must remain sanitized
  before reaching JSON logs, in-memory sinks, or metrics aggregation.
- Downloaded PyTorch weight files load through `torch.load(..., weights_only=True)` by default.
  Falling back to pickle deserialization must be explicit and limited to trusted artifacts.

## Local Gate

Run the full gate from the repository root before publishing behavior, docs, or distribution
changes:

```bash
uv lock --check
uv run ruff check src tests examples scripts
uv run ruff format --check src tests examples scripts
uv run python scripts/generate_provider_docs.py --check
uv run python scripts/check_docs_commands.py
uv run python scripts/check_docs_snippets.py
uv run python scripts/check_wrapper_portability.py
uv run python scripts/check_optional_import_boundaries.py
uv run python scripts/check_core_performance.py
uv run mkdocs build --strict
uv run pytest
uv run --extra harness pytest --cov=src/worldforge --cov-report=term-missing --cov-fail-under=90
bash scripts/test_package.sh
uv build --out-dir dist --clear --no-build-logs
```

The local gate runs the lock check, Ruff, generated-provider-doc drift check, documented-command
drift check, docs snippet gate, wrapper portability check, optional import boundary audit,
checkout-safe core performance budgets, strict MkDocs build, full pytest, harness coverage gate,
wheel/sdist package contract, and distribution build. The docs snippet gate executes only selected
Python snippets and parses only selected JSON snippets; host-owned, credentialed, and illustrative
examples need explicit skip markers. The wrapper portability check verifies shebangs, executable
bits, documented `uv run` commands, and Python 3.13 expectations without installing optional
runtimes. The optional import boundary audit verifies that base package imports, CLI startup,
`worldforge.rerun`, and non-TUI harness modules do not import Textual, Rerun, torch,
stable-worldmodel, LeRobot, GR00T, or Cosmos-Policy packages. Allowed direct imports stay limited
to `worldforge.harness.tui` for Textual and prepared-host smoke modules for torch/stable-worldmodel;
provider adapters must use lazy imports or injected runtimes. The core performance budget gate
writes JSON with measured local paths and a claim boundary; it detects regressions in checkout paths
and is not a cross-machine benchmark or optional-runtime performance claim. Before a release tag,
also run:

```bash
uv run python scripts/generate_dependency_audit_evidence.py
```

For release hardening, use the dependency-audit evidence workflow in
[Operations](./operations.md). It preserves JSON and Markdown summaries without keeping the
temporary requirements file.

## Optional Live Robotics CI

The normal CI workflow stays checkout-safe and deterministic. Real LeRobot plus LeWorldModel
inference runs in `.github/workflows/robotics-showcase.yml` because it downloads optional model
assets, builds or restores a LeWorldModel object checkpoint, and exercises host-owned runtimes.

That workflow runs on every pull request update and on pushes to `main`. It runs
`scripts/robotics-showcase` in non-interactive mode with `--json-only --no-tui --no-rerun`, then
validates the JSON summary and `run_manifest.json` for healthy providers, successful policy/score
events, the PushT candidate tensor shape, score count, and selected candidate index.

Checkpoint caching policy:

- use `actions/cache` for Hugging Face policy downloads, LeWorldModel config/weights assets, the
  built LeWorldModel object checkpoint, and uv package cache;
- key caches by OS, Python 3.13, uv version, LeRobot version, pinned LeWorldModel Hugging Face
  revision, and wrapper/checkpoint-builder source files;
- upload `real-run.json`, `stdout.json`, and `run_manifest.json` as short-retention run evidence;
- do not upload checkpoint artifacts from default CI; use `actions/cache` as the reusable
  checkpoint mechanism.

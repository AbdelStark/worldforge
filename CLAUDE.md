<identity>
WorldForge is a Python integration layer and CLI for physical-AI world-model provider adapters, world state, planning, evaluation, benchmarking, diagnostics, and host-owned optional runtimes.
</identity>

<priority_rules>
1. Keep provider capabilities truthful: advertise only callable, tested, typed WorldForge surfaces.
2. Make the library fault tolerant and developer-friendly while preserving the optional-runtime boundary: never add torch, LeWorldModel, LeRobot, GR00T, CUDA, checkpoints, datasets, or robot controllers to base dependencies or the repo.
3. Fail loudly at boundaries: invalid public inputs raise `WorldForgeError`; malformed persisted/provider state raises `WorldStateError`; provider/runtime failures raise `ProviderError`.
4. Preserve local-first scope: no hosted service, production database, credential store, robot safety layer, telemetry backend, or durable multi-writer persistence unless explicitly designed and approved.
5. Public contribution artifacts must be human, maintainer-style, and tool-neutral. Do not mention agent/tool branding in branch names, commits, PR titles, PR bodies, changelog, docs, or README copy.
</priority_rules>

<stack>
| Layer | Technology | Version source | Notes |
| --- | --- | --- | --- |
| Language | Python | `pyproject.toml`: `>=3.13,<3.14`; CI: 3.13 | Typed package, `src/` layout |
| Package manager | uv | CI setup uses `0.9.18`; lockfile is `uv.lock` | Use uv commands; do not use pip/npm/yarn for project workflow |
| Build backend | hatchling | `pyproject.toml`: `>=1.27.0` | Wheel/sdist from `src/worldforge` |
| Runtime dependency | httpx | `uv.lock`: `0.28.1` | HTTP provider adapters |
| Optional extra | textual | `uv.lock`: `8.2.4`; extra `harness` | Only `src/worldforge/harness/tui.py` may import Textual |
| Optional extra | rerun-sdk | `uv.lock`; extra `rerun`; LeRobot-resolved runtime in `scripts/robotics-showcase` | Optional event/artifact recording; not a provider capability |
| Tests | pytest, pytest-cov | `uv.lock`: pytest `9.0.3`, pytest-cov `7.1.0` | Coverage gate: 90 percent |
| Lint/format | ruff | `uv.lock`: `0.15.9`; target py313; line length 100 | Check and format `src tests examples scripts` |
| CI | GitHub Actions | `.github/workflows/*.yml` | CI, release, security audit, optional live robotics showcase |
</stack>

<structure>
Top-level boundaries:

| Path | Purpose | Agent zone |
| --- | --- | --- |
| `src/worldforge/` | Package source and public runtime | Modify with tests; public API files are gated |
| `src/worldforge/models.py` | Public models, validation, request policy, events, state contracts | Gated for breaking contract changes |
| `src/worldforge/framework.py` | `WorldForge`, `World`, persistence, planning, diagnostics, facade helpers | Gated for persistence/planning/public behavior changes |
| `src/worldforge/providers/` | Provider base classes, catalog, concrete adapters, optional runtimes | Modify with provider skill and fixture tests |
| `src/worldforge/evaluation/` | Deterministic evaluation suites and renderers | Modify with evaluation skill |
| `src/worldforge/harness/` | Optional TheWorldHarness package | Keep Textual isolated to `tui.py` |
| `src/worldforge/rerun.py` | Optional Rerun bridge | Events, worlds, plans, benchmarks, robotics showcase visuals; keep out of base deps |
| `src/worldforge/smoke/` | Packaged optional-runtime smoke entry points | Host-owned dependencies only |
| `src/worldforge/testing/` | Reusable adapter contract helpers | Public testing API; modify carefully |
| `tests/` | Unit, contract, CLI, docs, fixture, regression tests | Create/modify freely for changed behavior |
| `tests/fixtures/providers/` | Remote/provider parser fixtures | Create/modify for provider failure modes |
| `examples/` | Runnable checkout examples and compatibility wrappers | Keep deterministic unless explicitly live-smoke |
| `docs/src/` | User docs, architecture, playbooks, provider pages, API notes | Update with public behavior |
| `specs/` | Per-feature spec triads (`<feature>/{spec.md, plan.md, tasks.md}`) following the GitHub Spec Kit pattern; today populated for the TheWorldHarness M0-M5 milestones | Author a new triad before implementing a multi-task feature; update the triad as scope changes |
| `scripts/` | Docs generator, provider scaffold, package check, smokes | Gated for workflow/CI-impacting changes |
| `.github/workflows/` | CI, release, security pipelines | Explicit approval before modifying |
| `pyproject.toml`, `uv.lock` | Package metadata, deps, lockfile | Explicit approval for dependency/version changes |
| `README.md`, `CHANGELOG.md`, `CONTRIBUTING.md`, `AGENTS.md` | Public front face and canonical agent/multi-agent guide | Update when public behavior or agent context changes; do not create lowercase `agents.md` duplicate |
| `.env.example` | Tracked provider env template | Modify only with provider env changes; never include secrets |
| `.codex/skills/` | Project-local agent skills | Modify only when agent context is the task |
| `.claude/skills`, `.agents/skills` | Symlinks to `.codex/skills` | Keep as symlinks |
</structure>

<commands>
Run from repository root.

| Task | Command | Success signal |
| --- | --- | --- |
| Install dev env | `uv sync --group dev` | `.venv` ready; no lock drift |
| Lock check | `uv lock --check` | exits 0 |
| Lint | `uv run ruff check src tests examples scripts` | zero findings |
| Format check | `uv run ruff format --check src tests examples scripts` | zero diff |
| Format write | `uv run ruff format src tests examples scripts` | formats only Python files |
| Provider docs check | `uv run python scripts/generate_provider_docs.py --check` | no README/provider catalog drift |
| Test | `uv run pytest` | all tests pass |
| Coverage gate | `uv run --extra harness pytest --cov=src/worldforge --cov-report=term-missing --cov-fail-under=90` | >=90 percent with optional TUI tests available |
| Package contract | `bash scripts/test_package.sh` | wheel installs and tests pass in isolated venv |
| Full local gate | `uv lock --check && uv run ruff check src tests examples scripts && uv run ruff format --check src tests examples scripts && uv run python scripts/generate_provider_docs.py --check && uv run pytest && uv run --extra harness pytest --cov=src/worldforge --cov-report=term-missing --cov-fail-under=90 && bash scripts/test_package.sh` | release-quality local validation |
| CLI smoke | `uv run worldforge doctor` | `mock` registered; optional providers report missing/unregistered when env absent |
| World CLI persistence | `uv run worldforge world create lab --provider mock && uv run worldforge world add-object <world-id> cube --x 0 --y 0.5 --z 0 && uv run worldforge world history <world-id> && uv run worldforge world predict <world-id> --x 0.4 --y 0.5 --z 0 && uv run worldforge world delete <world-id>` | local JSON world is saved, edited with history, advanced, and removed through the validated persistence API |
| Examples index | `uv run worldforge examples` | runnable command list prints |
| Harness | `uv run --extra harness worldforge-harness` | Textual extra only |
| Build | `uv build` | wheel and sdist under `dist/` |
| Security audit | see `docs/src/playbooks.md` section 9 | locked deps audited |
</commands>

<provider_contracts>
Capability names are strict: `predict`, `generate`, `reason`, `embed`, `plan`, `transfer`, `score`, `policy`.

| Provider | Truthful surface | Registration trigger | Do not claim |
| --- | --- | --- | --- |
| `mock` | `predict`, `generate`, `transfer`, `reason`, `embed` | always registered | real physical/media fidelity |
| `cosmos` | `generate` | `COSMOS_BASE_URL` | planning, scoring, local runtime |
| `runway` | `generate`, `transfer` | `RUNWAYML_API_SECRET` or `RUNWAY_API_SECRET` | durable artifact storage |
| `leworldmodel` | `score` | `LEWORLDMODEL_POLICY` or `LEWM_POLICY` | predict/generate/reason |
| `gr00t` | `policy` | `GROOT_POLICY_HOST` | world model, score, generate |
| `lerobot` | `policy` | `LEROBOT_POLICY_PATH` or `LEROBOT_POLICY` | world model, score, generate |
| `jepa`, `genie` | scaffold | env-gated mock-backed reservations | real upstream integration |
| `jepa-wms` | direct-construction candidate | none; not exported or auto-registered | catalog availability |
</provider_contracts>

<configuration>
Read tracked config only. Never read `.env`, `.env.*`, keys, or secret files.

Configuration cascade:
1. `pyproject.toml` defines package metadata, scripts, deps, extras, pytest, ruff.
2. `uv.lock` pins resolved dependencies.
3. `.env.example` documents provider environment variables; actual values are host-owned.
4. Provider catalog auto-registers only always-on providers or providers whose required env vars are present.
5. Runtime flags such as CLI `--state-dir`, provider-specific options, and host-injected providers override defaults in process.
</configuration>

<code_conventions>
- Use `from __future__ import annotations` in Python modules.
- Prefer `@dataclass(slots=True)` or `@dataclass(slots=True, frozen=True)` for public models where the surrounding code does.
- Validate constructor and boundary values before persistence, outbound HTTP, optional runtime calls, or provider result return.
- Keep JSON-facing payloads typed as `JSONDict` and copy mutable inputs before storing them.
- Use `ProviderCapabilities()` fail-closed by default; opt into each capability explicitly.
- Unsupported provider methods should inherit or raise `ProviderError` with provider context.
- Remote adapters should use typed `ProviderRequestPolicy`/`RequestOperationPolicy`; create/mutation requests stay single-attempt unless idempotency is proven.
- Provider events should use `ProviderEvent` phases `retry`, `success`, and `failure`; targets,
  messages, and metadata must stay sanitized so logs never retain credentials or signed URL query
  strings.
- Keep docs concrete: command, success signal, first triage step.
- Do not add broad abstractions until they remove real duplication across current modules.
</code_conventions>

<workflows>
<bug_fix>
1. Reproduce with the narrowest failing command or test.
2. Patch the root cause in the smallest module boundary.
3. Add or update regression tests, including error paths for documented failure modes.
4. Run focused tests first, then relevant gates from `<commands>`.
5. Update docs/changelog/agent context when public behavior changes.
</bug_fix>

<provider_change>
1. Load `.codex/skills/provider-adapter-development/SKILL.md`.
2. Classify the provider by actual callable behavior, not marketing label.
3. Add fixtures under `tests/fixtures/providers/` for success and malformed/error outputs.
4. Assert `worldforge.testing.assert_provider_contract()` for supported surfaces.
5. Update provider docs and run `uv run python scripts/generate_provider_docs.py`.
6. Run provider-focused tests, docs check, coverage gate, and package contract if public API changes.
</provider_change>

<docs_change>
1. Prefer editing source docs; generated provider catalog blocks must come from `scripts/generate_provider_docs.py`.
2. Keep README front-door concise; route operational detail to `docs/src/playbooks.md` or provider pages.
3. Public behavior changes require matching README/docs/API/changelog/AGENTS updates where relevant.
</docs_change>

<optional_live_robotics_ci>
1. `.github/workflows/robotics-showcase.yml` runs on every pull request update and on pushes to `main`.
2. It runs `scripts/robotics-showcase --json-only --no-tui --no-rerun` with real LeRobot plus real LeWorldModel inference.
3. Use `actions/cache` for Hugging Face downloads, LeWM config/weights, and the built object checkpoint; upload JSON/run-manifest evidence by default.
4. Do not upload checkpoint artifacts from default CI; `actions/cache` is the reusable checkpoint mechanism.
</optional_live_robotics_ci>

<release_or_public_branch>
1. Verify no secrets, `.env`, checkpoints, datasets, `.worldforge/`, caches, `dist/`, or `build/` are staged.
2. Run full local gate from `<commands>`.
3. Use maintainer-style, tool-neutral branch/commit/PR text.
4. Do not push directly to `main` unless repo policy and the user explicitly allow it.
</release_or_public_branch>
</workflows>

<boundaries>
<forbidden>
- Do not read or modify `.env`, `.env.*`, `*.pem`, `*.key`, credentials, tokens, checkpoints, downloaded datasets, or robot-controller secrets.
- Do not add heavy optional runtimes or model assets to base dependencies or repository files.
- Do not silently coerce invalid world state or provider output.
- Do not weaken coverage gates, lint rules, security checks, package validation, or provider docs generation.
- Do not present deterministic evaluation suites or mock providers as physical-fidelity evidence.
- Do not export or auto-register `JEPAWMSProvider` without explicit validated-runtime design approval.
</forbidden>

<gated>
Require explicit approval before modifying:
- `.github/workflows/*`
- dependency or package metadata in `pyproject.toml` and `uv.lock`
- public API exports in `src/worldforge/__init__.py`
- public model/error/capability contracts in `src/worldforge/models.py`
- persistence contract in `src/worldforge/framework.py`
- provider base/catalog registration semantics in `src/worldforge/providers/base.py` and `src/worldforge/providers/catalog.py`
- release/publish behavior in `scripts/test_package.sh` or release workflow
- deleting tracked files or changing branch/merge/release policy
</gated>

<autonomous>
Safe to do without additional approval when aligned with the task:
- read repo files except forbidden secrets.
- add or update tests for changed behavior.
- fix lint, formatting, type, docs-drift, and focused CI failures.
- update docs/changelog/agent context for changed public behavior.
- add deterministic fixtures and examples that do not require live services.
</autonomous>
</boundaries>

<troubleshooting>
| Symptom | Likely cause | First fix |
| --- | --- | --- |
| `uv lock --check` fails | dependency metadata changed without lock update | confirm dependency change is approved, then refresh lock |
| provider docs drift | catalog/rendered README blocks stale | `uv run python scripts/generate_provider_docs.py`, inspect diff |
| optional provider unexpectedly registered | shell env has provider variables set | inspect sanitized environment names only; never read `.env` |
| capability filter rejects a name | unknown capability string | use one of `CAPABILITY_NAMES` |
| coverage gate fails | changed behavior lacks tests | add focused success and failure-path tests |
| package contract fails after passing local tests | wheel/sdist missing file or import path | inspect `pyproject.toml` hatch include/package settings and `scripts/test_package.sh` output |
| Textual import fails in base CLI/import | optional harness dependency leaked | move Textual import back under `src/worldforge/harness/tui.py` or harness extra path |
| remote media artifact fails | parser/retry/download/expired URL issue | inspect provider events and provider-specific docs; do not log secrets |
</troubleshooting>

<skills>
Project skills live in `.codex/skills/`; `.claude/skills` and `.agents/skills` must be symlinks to that directory.

Load skills on demand:
- `.codex/skills/provider-adapter-development/SKILL.md`: adding, promoting, or debugging providers.
- `.codex/skills/testing-validation/SKILL.md`: test selection, coverage, package, docs, CI gates.
- `.codex/skills/evaluation-benchmarking/SKILL.md`: evaluation suites, benchmarks, report claims.
- `.codex/skills/optional-runtime-smokes/SKILL.md`: LeWorldModel, GR00T, LeRobot live or injected runtime checks.
- `.codex/skills/persistence-state/SKILL.md`: world IDs, local JSON state, history import/export.
- `.codex/skills/tui-development/SKILL.md`: TheWorldHarness Textual TUI - screens, workers, command palette, snapshot tests.
- `.codex/skills/public-docs-release/SKILL.md`: README/docs/changelog/release-surface synchronization and publish-gate checks.
</skills>

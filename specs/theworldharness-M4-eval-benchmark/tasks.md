# Milestone M4 — Eval + Benchmark · Tasks

Each task is a single PR-sized unit. Order matters: a later task may assume an earlier one has landed in main.

## T1 — Textual-free flow helpers + report persistence
- Files: `src/worldforge/harness/flows.py`, `tests/test_harness_flows.py`.
- Change: introduce three Textual-free helpers — `eval_run_artifacts(forge, suite_id, providers, world=None) -> tuple[dict[str, str], EvaluationReport]`, `benchmark_run_artifacts(forge, providers, operations, iterations, concurrency, on_sample=None)`, and `write_report(forge, kind, artifacts) -> Path`. The first two thin-wrap `EvaluationSuite.from_builtin(...).run_report(...)` and `ProviderBenchmarkHarness(forge=forge).run(...)` and return both the JSON / Markdown / CSV artifact dict and the underlying report object. `write_report` resolves `forge.state_dir / "reports"`, creates it on first use, and writes `<kind>-<iso8601-utc>-<run-id>.json` containing `artifacts["json"]`. None of these helpers may import Textual.
- Acceptance: maps to spec acceptance criteria 5 (artifact bytes match canonical renderer) and 7 (`Esc` cancellation can still write whatever JSON was assembled). Capability mismatch surfaces as `WorldForgeError` raised from these helpers without being caught (acceptance criterion 3).
- Tests: `test_eval_run_artifacts_matches_cli_renderer` (byte-equality with `EvaluationReport.to_json()`); `test_benchmark_run_artifacts_invokes_on_sample` (callback called once per iteration); `test_write_report_creates_reports_dir_and_returns_resolved_path`; `test_write_report_filename_contains_kind_timestamp_and_run_id`; `test_capability_mismatch_propagates_as_worldforge_error`.

## T2 — Extend `HarnessRun` to discriminate eval / benchmark / flow kinds
- Files: `src/worldforge/harness/models.py`, `tests/test_harness_flows.py`.
- Change: add `kind: Literal["flow", "eval", "benchmark"]` (default `"flow"` for backward compatibility) and `report_path: Path | None = None` to `HarnessRun`. Add minimal typed view-helpers (`is_eval_run` / `is_benchmark_run`) so `RunInspectorScreen` can branch without `isinstance` gymnastics. **Gated change** — public surface listed in the TUI skill's "Stop and ask the user"; surface for review *before* T3 lands.
- Acceptance: existing tests for `HarnessRun` round-tripping continue to pass with the default `kind="flow"`; new fields participate in `to_dict` / `from_dict`.
- Tests: extend the existing `HarnessRun` round-trip tests with one case per `kind` value and a case with a `report_path`. No Textual imports.

## T3 — `EvalScreen` (form, worker, verdict, export)
- Files: `src/worldforge/harness/tui.py`, `tests/test_harness_tui.py`, `tests/snapshots/eval_screen_idle.svg`, `tests/snapshots/eval_screen_mid_run.svg`, `tests/snapshots/eval_screen_verdict_pass.svg`, `tests/snapshots/eval_screen_verdict_fail.svg`.
- Change: add `EvalScreen(Screen[None])` with reactives (`selected_suite`, `selected_providers`, `report_format`), a left-side form (`Select` for suite, `SelectionList` for providers, `Button("Run", id="run")`), a right-side `RichLog` + verdict banner + `ExportPane` (split out as a small `Widget` so `BenchmarkScreen` and `RunInspectorScreen` reuse it). The `Run` action launches the worker described in plan §Data flow under `group="eval"`. Capability mismatch is caught only in the worker boundary handler and re-posted as `CapabilityMismatch`. Successful completion writes the report via T1's `write_report`, posts `EvalCompleted` and `ReportExported`, and pushes `RunInspectorScreen(run)`. Add a `BINDINGS = [("escape", "cancel_eval", "Cancel"), ("r", "run", "Run"), ...]` and an entry in `App.get_system_commands` plus a dynamic command provider for each built-in suite name.
- Acceptance: spec criteria 1 (worker), 3 (capability error not swallowed), 4 (toast points at `ProvidersScreen`), 5 (canonical renderer for export), 6 (success toast with absolute path), 8 (`Esc` cancels via `cancel_group("eval")`), 9 (mouse + keyboard parity), 10 (Pilot test for capability mismatch), 11 (Pilot test for happy-path report on disk).
- Tests: `test_eval_screen_capability_mismatch_surfaces_worldforge_error`, `test_eval_screen_planning_against_mock_writes_report`, `test_format_tab_switch_does_not_rerun`, plus the four `EvalScreen` snapshots pinned at `terminal_size=(120, 40)` in both `worldforge-dark` and `worldforge-light`.

## T4 — `BenchmarkScreen` (live progress, rolling p95, export)
- Files: `src/worldforge/harness/tui.py`, `tests/test_harness_tui.py`, `tests/snapshots/benchmark_screen_live.svg`.
- Change: add `BenchmarkScreen(Screen[None])` with reactives for provider / operation / iterations / concurrency / format, a left-side form, and a right-side panel containing `ProgressBar(total=None)` until the iteration count is known and a small "rolling stats" `Static` showing the running median + p95 latency from samples received so far. Worker uses `group="benchmark"`, posts `BenchmarkSampleReceived` per iteration via `call_from_thread`, and on completion writes the report and pushes `RunInspectorScreen`. Reuse the `ExportPane` from T3.
- Acceptance: spec criteria 2 (worker), 5 (renderer parity), 6 (success toast with path), 7 (`RunInspectorScreen` reflows formats without rerun), 8 (`Esc` cancellation), 9 (palette + binding + click parity), 12 (snapshot at `terminal_size=(120, 40)`).
- Tests: `test_benchmark_screen_streams_progress` (asserts ≥ N `BenchmarkSampleReceived` messages and `ProgressBar.percentage == 100`); `test_esc_cancels_active_benchmark_and_writes_partial_report`; `test_benchmark_run_renders_same_json_as_cli` (byte-equality with `_cmd_benchmark` JSON output for a fixed seed/iteration count); the `benchmark_screen_live.svg` snapshot.

## T5 — `RunInspectorScreen` extension + `ExportPane` reuse
- Files: `src/worldforge/harness/tui.py`, `tests/test_harness_tui.py`, `tests/snapshots/run_inspector_json_export.svg`.
- Change: extend `RunInspectorScreen` to accept a `HarnessRun` whose `kind` is `"eval"` or `"benchmark"`, mount the same `ExportPane` from T3, and render a `report_path` line linking to the preserved JSON. Format-tab switching is reactive only — no worker spawn — and reflows the preview pane.
- Acceptance: spec criteria 7 (in-place format reflow without rerun), 9 (mouse + keyboard parity), 12 (snapshot).
- Tests: `test_run_inspector_renders_eval_run_metrics`, `test_run_inspector_renders_benchmark_run_metrics`, `test_run_inspector_format_switch_does_not_rerun`, plus the `run_inspector_json_export.svg` snapshot.

## T6 — Wrapper CLI shortcuts and palette discovery
- Files: `src/worldforge/harness/cli.py`, `tests/test_harness_cli.py`.
- Change: extend the wrapper's `--flow` choices with `eval` and `benchmark`. When passed, the harness boots straight onto the corresponding screen instead of `HomeScreen`. Add the dynamic `command.Provider` registration so `Ctrl+P` exposes "Run eval suite: planning", "Run benchmark: mock × predict", etc.
- Acceptance: spec criterion 9 (palette parity); roadmap §5 ("if a feature exists but isn't in the palette, it doesn't exist for new users").
- Tests: `test_wrapper_cli_flow_eval_lands_on_eval_screen`, `test_wrapper_cli_flow_benchmark_lands_on_benchmark_screen`, plus a Pilot test that opens the palette and asserts the eval / benchmark items are present and selectable.

## T7 — Docs, changelog, and (optional) CI grep guard
- Files: `docs/src/playbooks.md`, `docs/src/evaluation.md`, `docs/src/benchmarking.md`, `docs/src/architecture.md`, `CHANGELOG.md`, optionally `.github/workflows/ci.yml`.
- Change: add the "Where TheWorldHarness writes preserved reports" section to `playbooks.md` documenting the `.worldforge/reports/<kind>-<timestamp>-<run-id>.json` convention. Add a one-paragraph cross-link from `evaluation.md` and `benchmarking.md` to "also reachable from TheWorldHarness", and a single line under `architecture.md`'s harness section. Add a Changelog entry under `## Unreleased` in maintainer-style copy. Optional: add a CI grep guard rejecting any `except WorldForgeError` in `src/worldforge/harness/tui.py` that does not lead to a `CapabilityMismatch` post (mitigation R2). The CI workflow change is **gated**; do not land it without explicit approval per `<gated>` rules.
- Acceptance: spec criteria 5 (renderer parity, surfaced in docs as "shared with the `worldforge` CLI"); roadmap "every milestone updates the spec / docs / changelog".
- Tests: `tests/test_docs.py` should already verify referenced files exist; if not, add a check that the new playbook section path is present. Keep `uv run python scripts/generate_provider_docs.py --check` clean (this milestone changes no provider docs).

## Definition of done
- [ ] All tasks T1–T7 merged
- [ ] Pilot tests for capability-mismatch, eval happy path, benchmark live progress, format-tab no-rerun, and `Esc` cancellation are green in CI
- [ ] Six new snapshot SVGs committed and reviewed in PRs (both `worldforge-dark` and `worldforge-light` where the spec calls for theming parity)
- [ ] Coverage gate `uv run --extra harness pytest --cov=src/worldforge --cov-report=term-missing --cov-fail-under=90` passes
- [ ] Package contract `bash scripts/test_package.sh` passes (no new files outside the `src/worldforge` tree are required at runtime)
- [ ] `.worldforge/reports/` convention documented in `docs/src/playbooks.md`
- [ ] CHANGELOG entry under `## Unreleased`
- [ ] Roadmap §8 marked `done · YYYY-MM-DD` in `.codex/skills/tui-development/references/roadmap.md`

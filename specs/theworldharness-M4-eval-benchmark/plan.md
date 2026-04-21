# Milestone M4 — Eval + Benchmark · Implementation Plan

## Builds on
- Roadmap §8 "M4 — Eval + Benchmark" — [`../../.codex/skills/tui-development/references/roadmap.md`](../../.codex/skills/tui-development/references/roadmap.md)
- Skill: [`../../.codex/skills/tui-development/SKILL.md`](../../.codex/skills/tui-development/SKILL.md) — worker idiom, `RichLog` streaming, toast pattern, semantic CSS variables, snapshot tests pinned to `terminal_size=(120, 40)`.
- Skill: [`../../.codex/skills/evaluation-benchmarking/SKILL.md`](../../.codex/skills/evaluation-benchmarking/SKILL.md) — capability-mismatch must stay a hard `WorldForgeError`; every cited number must be traceable to a preserved JSON; renderers have one source of truth.
- Predecessor milestones: M0 (theme + chrome reset — `$success` / `$error` / `$accent` already registered), M1 (screen stack + `RunInspectorScreen` exists and accepts a `HarnessRun`), M3 (worker idiom proven against `mock` predict + `Esc` cancellation). M2 (Worlds CRUD) is *optional but useful*: if `WorldsScreen` is live, eval can default to the currently-selected world; otherwise it falls back to a per-suite scratch world (which is what `EvaluationSuite._build_world` already constructs).
- Source modules consumed (read-only by M4): `src/worldforge/evaluation/suites.py` (`EvaluationSuite`, `EvaluationReport`, `EvaluationResult`, `ProviderSummary`); `src/worldforge/benchmark.py` (`ProviderBenchmarkHarness`, `BENCHMARKABLE_OPERATIONS`, the benchmark report and gate types); `src/worldforge/cli.py` `_cmd_eval` / `_cmd_benchmark` for parity reference.

## Architecture changes
- **New `EvalScreen`** (`Screen[None]`) — two-column form on the left (suite picker, provider multi-select, "Run" button), worker-output `RichLog` and verdict banner on the right. Composes a shared `ExportPane` widget for JSON / Markdown / CSV preview switching.
- **New `BenchmarkScreen`** (`Screen[None]`) — provider × operation × iterations × concurrency × format form on the left, `ProgressBar` + rolling-stats panel + per-iteration `RichLog` on the right, shared `ExportPane` reused.
- **New `ExportPane` widget** — composes a `Tabs("json", "markdown", "csv")` over a `Static` (or `RichLog` for long output). Reactive `report_format`. Pure presentation; no I/O. Reused on `RunInspectorScreen`.
- **New report-persistence helper** in `harness/tui.py` (or a Textual-free helper next to `harness/flows.py`) — `_write_report(forge: WorldForge, kind: str, report_artifacts: dict[str, str]) -> Path` that creates `.worldforge/reports/` on first use, names the file `<kind>-<iso8601>-<run-id>.json`, writes `artifacts["json"]`, and returns the resolved path. Lives off the `WorldForge` state-dir convention so the path follows `--state-dir`.
- **`RunInspectorScreen` extension** — accept either a benchmark or an evaluation `HarnessRun`; mount `ExportPane` so format switches reflow without rerunning.
- **No new files outside `src/worldforge/harness/`.** Textual-free helpers (the report path resolver, the artifact dict builder) sit in `harness/flows.py`; Textual screens stay inside `harness/tui.py` per the import boundary.
- **`.worldforge/reports/`** is a new convention; created lazily on first run; documented in `docs/src/playbooks.md` and called out in M4-completion changelog entry.

## Module touch list
| Path | Change | Notes |
| --- | --- | --- |
| `src/worldforge/harness/tui.py` | Add `EvalScreen`, `BenchmarkScreen`, `ExportPane` widget; extend `RunInspectorScreen`; register new screens with the `App` and add palette entries via `get_system_commands` plus a new `command.Provider` for "Run eval suite …" / "Run benchmark …" dynamic items. | Textual-only file; existing import boundary preserved. |
| `src/worldforge/harness/flows.py` | Add Textual-free helpers: `eval_run_artifacts(forge, suite_id, providers, world=None)`, `benchmark_run_artifacts(forge, providers, operations, iterations, concurrency)`, and `write_report(forge, kind, artifacts) -> Path`. These wrap the existing `EvaluationSuite` / `ProviderBenchmarkHarness` calls so the screens never reach into provider state directly and the same helpers are unit-testable without Textual. | Keeps the wire-up Pilot-testable and CLI-parity-checkable. |
| `src/worldforge/harness/models.py` | Extend `HarnessRun` (or add a discriminated `kind: Literal["flow","eval","benchmark"]`) so `RunInspectorScreen` can render either; add `report_path: Path \| None`. | Needs explicit approval before merging — it touches the public flow surface listed in the TUI skill's "Stop and ask the user" list. Discuss before T2. |
| `src/worldforge/harness/cli.py` | Add `--flow eval` / `--flow benchmark` shortcuts so `worldforge-harness --flow eval` lands directly on `EvalScreen`. | Pure wiring; no new dependencies. |
| `tests/test_harness_tui.py` | Add Pilot tests: capability-mismatch toast, eval happy path, benchmark live progress, format-tab switching, `Esc` cancellation. | Use the slow-mock helper from M3. |
| `tests/test_harness_flows.py` | Unit tests for the new flows-helpers (`eval_run_artifacts`, `benchmark_run_artifacts`, `write_report`) — Textual-free. | Confirms CLI / TUI parity by comparing artifact bytes to `EvaluationReport.to_json()` directly. |
| `tests/snapshots/` | Six new `.svg` snapshots per the spec's snapshot list. | Pinned to `terminal_size=(120, 40)`. |
| `docs/src/playbooks.md` | New section: "Where TheWorldHarness writes preserved reports" — documents the `.worldforge/reports/` convention and the `<kind>-<timestamp>-<run-id>.json` filename shape. | Required because public behavior changed. |
| `docs/src/architecture.md` and `docs/src/evaluation.md` / `docs/src/benchmarking.md` | One-paragraph cross-link from each topic to "also reachable from TheWorldHarness". | Keeps the docs honest about the integration reference claim. |
| `CHANGELOG.md` | Entry under Unreleased: "TheWorldHarness M4 — Eval + Benchmark screens; reports preserved under `.worldforge/reports/`." | Maintainer-style copy, no tool branding. |

## Key technical decisions

### D1 — Shared renderer, not a parallel TUI renderer
- **Decision:** the TUI imports `EvaluationReport.artifacts()` and the benchmark report's equivalent and renders the resulting strings directly in `ExportPane` and `_write_report`.
- **Alternatives considered:** (a) building a TUI-tailored renderer with rich markup; (b) generating a slimmer "preview" JSON in the TUI and a full JSON for export.
- **Rationale:** the evaluation-benchmarking skill's first failure mode is *misclaimed scope*. The cheapest defense against TUI-vs-CLI drift is a single rendering path: if the user sees a number on screen, it came from the same `to_json()` / `to_markdown()` / `to_csv()` that the CLI tests already cover. Renderer regression tests in `tests/test_evaluation_and_planning.py` and `tests/test_benchmark.py` then automatically protect the TUI surface too.

### D2 — Capability mismatch is a toast, not a modal
- **Decision:** raise `WorldForgeError` from the worker → catch in `on_worker_state_changed` → render a `$error`-coloured toast with the verbatim message and a one-key ("p") action that pushes `ProvidersScreen` with the offending provider pre-selected.
- **Alternatives considered:** (a) a blocking modal that demands acknowledgement; (b) silently disabling the provider from the picker; (c) catching and converting to a generic `"Run failed"` line in the log.
- **Rationale:** option (a) is heavier than the moment deserves and breaks keyboard flow. Option (b) hides the capability model — exactly the failure mode the skill warns against. Option (c) is the most dangerous: it silently turns the suite contract harness into a no-op (skill's "Stop and ask the user": "before catching a `WorldForgeError` from a suite"). A toast is loud enough to teach, light enough not to derail.

### D3 — Reports preserved under `.worldforge/reports/`
- **Decision:** mirror the existing `.worldforge/worlds/` convention. Files are named `<kind>-<iso8601-utc>-<run-id>.json` (e.g., `eval-planning-2026-04-21T140332Z-7c9f.json`, `benchmark-2026-04-21T141001Z-3a08.json`).
- **Alternatives considered:** (a) writing to `os.tmpdir`; (b) writing only on user request.
- **Rationale:** the skill mandates that any externally cited number be traceable to a preserved file. Auto-write removes the "I forgot to save and now I quoted it in a PR" failure mode. Following the worlds-dir convention keeps the state-dir override (`--state-dir`) consistent across screens.

### D4 — One worker group per screen, `Esc` is the universal cancel
- **Decision:** `EvalScreen` uses `group="eval"`; `BenchmarkScreen` uses `group="benchmark"`. Both `Esc`-bind to `self.workers.cancel_group(<group>)`.
- **Alternatives considered:** (a) one `group="long-work"` shared across both; (b) per-suite group names.
- **Rationale:** (a) means popping into `RunInspectorScreen` while a benchmark runs would let `Esc` accidentally cancel an unrelated eval. (b) is over-engineered. One group per screen matches roadmap §6 exactly.

### D5 — Multi-provider eval and benchmark are first-class
- **Decision:** the form's provider input is a multi-select; `EvaluationSuite.run_report(providers=...)` and `ProviderBenchmarkHarness.run(...)` already accept sequences and produce per-provider summary rows.
- **Alternatives considered:** single-provider only in M4; defer multi-provider to M5.
- **Rationale:** the CLI accepts repeated `--provider` flags today; if the TUI doesn't, it isn't the integration reference. Cost is one widget, not new model code.

## Data flow

**Reactives (per screen):**
- `selected_suite: reactive[str | None] = reactive(None)` (`EvalScreen`)
- `selected_providers: reactive[tuple[str, ...]] = reactive(())` (both)
- `selected_operations: reactive[tuple[str, ...]] = reactive(("predict",))` (`BenchmarkScreen`)
- `iterations: reactive[int] = reactive(5)` (`BenchmarkScreen`, validated `>= 1`)
- `concurrency: reactive[int] = reactive(1)` (`BenchmarkScreen`, validated `>= 1`)
- `report_format: reactive[Literal["json","markdown","csv"]] = reactive("markdown")` (`ExportPane` on both screens, mirrored to `RunInspectorScreen`)
- `current_run: reactive[HarnessRun | None] = reactive(None)`

Pair each with `watch_<name>` to redraw the affected pane only.

**Messages:**
- `EvalStarted(suite_id: str, providers: tuple[str, ...])`
- `EvalSampleReceived(scenario: str, provider: str, score: float, passed: bool)`
- `EvalCompleted(run: HarnessRun)`
- `BenchmarkStarted(provider: str, operation: str, iterations: int)`
- `BenchmarkSampleReceived(sample: BenchmarkSample)` — emitted from worker via `call_from_thread(self.post_message, ...)`
- `BenchmarkCompleted(run: HarnessRun)`
- `ReportExported(path: Path, kind: str)`
- `CapabilityMismatch(error: WorldForgeError, provider: str, missing: tuple[str, ...])`

**Workers:**
```python
@work(thread=True, group="eval", exclusive=True, name=f"eval.{suite_id}")
def _run_eval(self, suite_id: str, providers: tuple[str, ...]) -> None:
    log = self.query_one(RichLog)
    try:
        artifacts, report = eval_run_artifacts(self.forge, suite_id, providers)
    except WorldForgeError as exc:
        # NOT swallowed — re-posted as a typed message and surfaced as a toast.
        self.app.call_from_thread(self.post_message, CapabilityMismatch(exc, ..., ...))
        return
    path = write_report(self.forge, f"eval-{suite_id}", artifacts)
    self.app.call_from_thread(self.post_message, EvalCompleted(...))
    self.app.call_from_thread(self.post_message, ReportExported(path, "eval"))
```

`BenchmarkScreen` mirrors this with `group="benchmark"`. Per-iteration progress is forwarded by passing a small `on_sample` callback into the helper, which the worker invokes via `call_from_thread` so the `RichLog` and `ProgressBar` update without thread-mutating widgets directly.

**Screen lifecycle:**
- On screen pop: workers are auto-cancelled (Textual default for screen-bound workers); `Esc` is the same code path.
- `RunCompleted` posts cause `app.push_screen(RunInspectorScreen(run))` so the inspector screen is the destination, not an inline panel.

## Theming and CSS
- All new TCSS uses semantic variables only:
  - Pass verdict banner: `background: $success 20%; color: $success;`
  - Fail verdict banner / capability-mismatch toast: `background: $error 20%; color: $error;`
  - Selected format tab in `ExportPane`: `border-bottom: thick $accent;`
  - Cancelled-state badge: `color: $warning;`
  - Progress bar: rely on Textual stock `ProgressBar` styling; do not override colours.
- `:focus-within` on the form pane gets `border: round $accent`; idle panes stay `border: round $panel`.
- No hex literals. Light-theme contrast verified by snapshot tests in both themes.

## Testing
- **Pilot tests** (`tests/test_harness_tui.py`):
  - `test_eval_screen_capability_mismatch_surfaces_worldforge_error`: pick `generation` × `leworldmodel` (mock-registered for the test); assert the rendered toast contains the exact `WorldForgeError` message and that the worker did not silently complete.
  - `test_eval_screen_planning_against_mock_writes_report`: pick `planning` × `mock`; assert (a) `RunInspectorScreen` becomes active, (b) the file at `ReportExported.path` exists, (c) `json.loads(path.read_text())` round-trips to the same `EvaluationReport.to_dict()` produced by calling `EvaluationSuite.from_builtin("planning").run_report("mock", forge=forge).to_dict()` directly.
  - `test_benchmark_screen_streams_progress`: pick `mock` × `predict` × 5 iterations using the slow-mock helper from M3; assert the `RichLog` receives at least 5 `BenchmarkSampleReceived` lines and the `ProgressBar.percentage` reaches 100.
  - `test_format_tab_switch_does_not_rerun`: after a successful eval, switch `report_format` from markdown to csv to json; assert no new worker is spawned and the preview pane updates synchronously.
  - `test_esc_cancels_active_benchmark_and_writes_partial_report`: start a long benchmark, press `Esc`, assert `current_run.status == "cancelled"` and the JSON at `ReportExported.path` is well-formed.
- **Unit tests** (`tests/test_harness_flows.py`):
  - `test_write_report_uses_state_dir`: verify the path is `forge.state_dir / "reports" / "<kind>-..."` and the directory is created on first use.
  - `test_eval_run_artifacts_matches_cli_renderer`: assert `artifacts["json"] == EvaluationReport.to_json()` byte-for-byte for a known fixture.
- **Snapshot tests** (six SVGs, all pinned to `terminal_size=(120, 40)` per skill rule, both themes):
  - `EvalScreen` idle, `EvalScreen` mid-run, `EvalScreen` verdict-pass, `EvalScreen` verdict-fail, `BenchmarkScreen` live metrics, `RunInspectorScreen` JSON-export preview.
- **Coverage gate**: `uv run --extra harness pytest --cov=src/worldforge --cov-report=term-missing --cov-fail-under=90` must stay green. The new helpers are exercised by both Pilot and unit tests, so coverage should rise, not drop.
- **CLI parity check**: a single test compares `EvaluationReport.to_json()` produced via the TUI helper to the one produced via `_cmd_eval`; if they ever drift, the test fails before reviewers do.

## Risks and mitigations
- **R1 — Renderer divergence between CLI and TUI.** The CLI's report is the canonical citation source; if the TUI renders something subtly different, screenshots in PRs would no longer match the JSON. *Mitigation:* D1 (shared renderer) plus the byte-level parity test in `tests/test_harness_flows.py`. Any future change to `EvaluationReport.to_*` regenerates both surfaces by construction.
- **R2 — Capability mismatch silently caught in a bare `except`.** The single most damaging regression; turns the contract harness into a no-op. *Mitigation:* the only `except WorldForgeError` clause in `harness/tui.py` is the one that re-posts `CapabilityMismatch`; a small Pilot test asserts the message reaches the toast verbatim. A grep guard in CI (`! grep -RnE "except (Exception|BaseException|WorldForgeError)" src/worldforge/harness/tui.py | grep -v CapabilityMismatch`) is cheap to add and worth it; defer that to T7 if maintainers agree.
- **R3 — Unpreserved benchmark numbers in screenshots.** A user takes a screenshot of `BenchmarkScreen` with live numbers that were never persisted. *Mitigation:* the screen never displays a *final* "save report" affordance — the JSON is written *first*, and the path-toast is what tells the user the run completed. The screenshot policy lives in M5; M4 just makes preservation automatic.
- **R4 — Slow-mock or noisy CI causes flaky benchmark snapshots.** *Mitigation:* snapshot tests use a frozen-clock fixture for any visible latency numbers; the live `RichLog` is asserted by message count, not by visible content.
- **R5 — `HarnessRun` model change is breaking.** Touches public surface listed in the TUI skill's "Stop and ask the user". *Mitigation:* T2 is gated; raise the discriminated-kind change as a separate review before merging the screens that depend on it.
- **R6 — `.worldforge/reports/` collides with a user-managed directory.** Unlikely (matches the existing `.worldforge/worlds/` convention) but possible. *Mitigation:* document the path in `docs/src/playbooks.md`; never delete files under it; use UTC ISO8601 + run-id so collisions require the same millisecond *and* the same 4-hex run-id.

## Dependencies on other milestones
- **Required before this can ship:** M0 (theme + chrome reset — semantic variables registered), M1 (screen stack and `RunInspectorScreen` accept a `HarnessRun`), M3 (worker idiom proven; `Esc` cancellation pattern reusable; slow-mock test helper available).
- **Optional but useful:** M2 (Worlds CRUD) — when present, `EvalScreen` can default to the currently-selected world for suites that accept one (`run_with_world`). When absent, falls back to the per-suite scratch world built by `EvaluationSuite._build_world`.
- **This milestone blocks:** M5 (recent-runs list on `HomeScreen` and the dynamic command palette provider for "Recent runs" depend on `.worldforge/reports/` existing); M5 README screenshot refresh (the new screens are the reason for the refresh).
- **Cross-milestone non-dependency:** the `optional-runtime-smokes` skill is *not* a prerequisite. M4 explicitly does not run live LeWorldModel / GR00T / LeRobot — those are surfaced as registered providers with their own capability advertisements; if their env vars are absent, they simply do not appear in the picker.

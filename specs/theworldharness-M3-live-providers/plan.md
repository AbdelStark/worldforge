# Milestone M3 — Live providers · Implementation Plan

## Builds on
- Roadmap §8 "M3 — Live providers" — `.codex/skills/tui-development/references/roadmap.md`
- Roadmap §4.4 "ProvidersScreen" — capability matrix shape and bindings
- Roadmap §6 "Long-running work — the worker contract" — the canonical worker idiom this milestone instantiates
- Skill: `.codex/skills/tui-development/SKILL.md` — Fast start, "SOTA Textual practices", "Don't" list (no event-loop blocking, no thread-direct widget mutation)
- Skill: `.codex/skills/provider-adapter-development/SKILL.md` + `references/capability-matrix.md` — capability truthfulness, the eight capability names, `assert_provider_contract`
- Capability and event contracts in code:
  - `src/worldforge/models.py` — `CAPABILITY_NAMES`, `ProviderCapabilities`, `ProviderEvent` (phases `retry` / `success` / `failure`)
  - `src/worldforge/providers/base.py` — `BaseProvider`, `ProviderError`, `event_handler` ctor arg
  - `src/worldforge/providers/catalog.py` — `PROVIDER_CATALOG`, `create_known_providers`
  - `src/worldforge/providers/mock.py` — `MockProvider.predict` (the one real call wired in M3)
  - `src/worldforge/framework.py` — `WorldForge.create_world`, `World.predict`, `register_provider`, `list_providers`
- Predecessor milestones:
  - **Required:** M0 (themes registered, semantic CSS variables, Header status pill reactive), M1 (screen stack with `push_screen` / `push_screen_wait`, `Ctrl+P` system commands, `?` help overlay).
  - **Optional but useful:** M2 (Worlds CRUD). If M2 has landed, M3 reads `selected_world` from the App reactive. If not, M3 falls back to `WorldForge.create_world("scratch")`. The fallback is deterministic and tested.

## Architecture changes
- New `Screen` subclass: `ProvidersScreen` (in `src/worldforge/harness/tui.py`).
- New `ModalScreen[ProviderHandle]` subclass: `RegisterProviderModal` (same file).
- New widget composition inside `ProvidersScreen`:
  - `DataTable(zebra_stripes=True, cursor_type="row")` for the capability matrix (rows = providers, columns = capabilities).
  - `Static` detail pane on the right (health + env-var requirements + last-call summary).
  - `RichLog(highlight=True, markup=True, max_lines=5000)` event stream below.
  - `ProgressBar` (indeterminate while a provider call is in flight).
- New typed messages (defined inside `tui.py`):
  - `class ProviderEventReceived(Message): event: ProviderEvent`
  - `class RunRequested(Message): provider: str; capability: str`
  - `class RunCompleted(Message): provider: str; latency_ms: float`
  - `class RunCancelled(Message): provider: str`
- New reactives on `ProvidersScreen`:
  - `current_row_provider: reactive[str | None]` — the highlighted row.
  - `running_operation: reactive[Literal["idle", "running", "cancelled", "error", "done"]]`.
  - `last_call_summary: reactive[dict[str, dict[str, Any]]]` — keyed by provider name, holds `{phase, latency_ms, retries}` for the most recent call.
- The App's `current_provider` reactive (introduced in M0) stays the cross-screen source of truth; `ProvidersScreen` writes it on `Enter`.
- A small adapter, `_QueueingEventHandler`, is a `Callable[[ProviderEvent], None]` that pushes events into a thread-safe `queue.Queue`. It is passed to `WorldForge(event_handler=queueing_handler)` at App startup so every registered provider inherits it (per `WorldForge.register_provider`'s "inherits the global handler if the provider does not declare one" contract). The worker drains the queue and uses `call_from_thread` to mutate the UI. Re-attaching a handler to an already-registered provider is not a public surface and is intentionally not used.

## Module touch list
| Path | Change | Notes |
| --- | --- | --- |
| `src/worldforge/harness/tui.py` | Add `ProvidersScreen`, `RegisterProviderModal`, `ProviderEventReceived` / `RunRequested` / `RunCompleted` / `RunCancelled` message classes, the `provider` worker, the `_QueueingEventHandler` helper. Add a Ctrl+P system command "Open providers". Add binding to push `ProvidersScreen`. | The only Textual-touching file. Keep `flows.py`, `cli.py`, `models.py` unchanged so the base package's installability stays intact. |
| `tests/test_harness_tui.py` | Add Pilot tests: open `ProvidersScreen`, assert row count = `len(WorldForge().list_providers())`, assert column count = `len(CAPABILITY_NAMES)`; press Enter → `current_provider` updates; press `p` → events appear in `RichLog`; press `Esc` mid-run → `running_operation == "cancelled"`. | Use a slow-mock fixture that yields events with controllable cadence so cancellation is observable without wall-clock flake. |
| `tests/test_harness_tui_snapshots.py` (new file or extend existing) | Snapshot tests at `terminal_size=(120, 40)`: `ProvidersScreen` idle, mid-run with populated `RichLog`, cancelled, `worldforge-light` variant of idle. | Commit SVGs; review diffs in PR. |
| `tests/conftest.py` | Add `slow_mock_provider` fixture (a `MockProvider` subclass whose `predict` sleeps 50 ms × N between simulated event emissions; emits via `event_handler`). | Private fixture by default; promote to `worldforge.testing` only if a second consumer appears (open question in spec). |
| `.codex/skills/tui-development/references/roadmap.md` | After merge: mark §8 M3 "done · YYYY-MM-DD". Honest spec rule (`<context_lifecycle>`). | Roadmap-only edit; not part of the implementation tasks below — added by the closing PR. |

No changes to `pyproject.toml`, `uv.lock`, `src/worldforge/__init__.py`, `src/worldforge/models.py`, `src/worldforge/framework.py`, `src/worldforge/providers/*`, or `.github/workflows/*`. M3 is purely a TUI surfacing layer over the existing provider contract.

## Key technical decisions

### D1 — Where the `current_provider` reactive lives
- **Decision:** on `TheWorldHarnessApp`, not on `ProvidersScreen`.
- **Alternatives:** screen-local reactive read by other screens via `self.app.query_one(ProvidersScreen).current_provider`.
- **Rationale:** the status pill in the Header (M0) and future `EvalScreen` / `BenchmarkScreen` (M4) all need this value. Reaching across the screen stack to query it would be the "reach across the DOM" anti-pattern called out in SKILL.md "Don't". App-level reactive is the right scope.

### D2 — Capability cell glyphs
- **Decision:** `●` real, `○` scaffold, blank for "not advertised".
- **Alternatives:** letters (`R` / `S` / blank), Unicode shapes (`■` / `□`), color-only (no glyph).
- **Rationale:** matches roadmap §4.4 verbatim. Glyph plus semantic color (`$success` / `$warning` / `$muted`) is dual-coded so a colorblind reader still parses it, satisfying the "honest UX" theme of the milestone.

### D3 — Event streaming channel: `post_message` vs `call_from_thread(log.write, ...)`
- **Decision:** `self.app.call_from_thread(self.post_message, ProviderEventReceived(event))` — i.e., post a typed message and let the screen's `on_provider_event_received` handler write to the `RichLog`.
- **Alternatives:** the SKILL.md fast-start example uses `call_from_thread(log.write, format_event(event))` directly; that is shorter but skips the typed message hop.
- **Rationale:** the typed message is the same channel that updates `last_call_summary`, the status pill, and the `running_operation` reactive. Funneling everything through one `Message` keeps state transitions atomic in the event loop and makes Pilot tests assert against `running_operation` rather than against parsed `RichLog` text. Slightly more code; much better testability.

### D4 — Cancellation surface: `Esc` key vs visible "Cancel" button
- **Decision:** both. `Esc` is the binding (footer entry, `show=True`); a clickable "Cancel" target sits next to the `ProgressBar` for mouse parity (SKILL.md "Pair every footer binding with a click target").
- **Alternatives:** keyboard-only (faster to ship, fails the parity rule).
- **Rationale:** mouse + keyboard parity is a hard rule in the skill. Without the visible target, `ProvidersScreen` would silently fail the parity audit at M5.

### D5 — Worker → provider event seam
- **Decision:** the App constructs `WorldForge(event_handler=self._queueing_handler)` at startup, so every always-registered and auto-registered provider inherits the handler at registration time (per `WorldForge.register_provider`'s documented inheritance behavior). The worker drains the shared `queue.Queue` inline after the synchronous `predict` call returns — and, for the slow-mock test, between simulated event emissions.
- **Alternatives:** mutate `provider.event_handler` post-registration (no public API; relies on attribute access); patch `MockProvider` to be async; add a streaming method to `BaseProvider`.
- **Rationale:** changing the provider base class or `WorldForge` registration semantics is gated (`<gated>`) and out of scope for M3. Using `WorldForge`'s existing `event_handler` constructor arg is the smallest seam that keeps the provider contract untouched while still letting the worker stream events. M4's longer-running providers (e.g., HTTP `cosmos.generate`) will already emit events progressively, so the same drain pattern works without refactor.

### D6 — Throwaway world fallback
- **Decision:** if `selected_world` is `None`, call `WorldForge.create_world("scratch")` and use it for the predict; the empty state of `ProvidersScreen` documents this.
- **Alternatives:** require M2 first; refuse to run; prompt the user with a modal.
- **Rationale:** M3 must not block on M2 — the milestone outcome ("the harness stops being a slideshow") is the bar. The scratch world is a real `World` that hits the real `WorldForge` API, which is the reference example M3 owes downstream callers.

### D7 — RichLog formatting
- **Decision:** `f"[dim]{ts}[/] [{phase_color}]{event.phase:^9}[/] {event.provider}.{event.operation} ({event.duration_ms or 0:.1f}ms)"` where `phase_color` maps `success → $success`, `failure → $error`, `retry → $warning`. Markup only — no f-strings interpolating raw `event.message` or `event.metadata` (those go to the metrics pane to keep the log scannable).
- **Alternatives:** dump `event.to_dict()` as JSON per line; use plain text.
- **Rationale:** `RichLog(markup=True)` lets us dual-code phase via color and the right-aligned text glyph. JSON dump is unscannable; plain text loses the phase-at-a-glance. Critically: nothing here interpolates secrets; `event.metadata` rendering happens elsewhere through the same sanitisation contract the provider already enforces.

## Data flow

### Reactives
- `App.current_provider: reactive[str]` (introduced in M0; `ProvidersScreen` writes on `Enter`).
- `ProvidersScreen.current_row_provider: reactive[str | None]`.
- `ProvidersScreen.running_operation: reactive[Literal["idle", "running", "cancelled", "error", "done"]] = reactive("idle")`.
- `ProvidersScreen.last_call_summary: reactive[dict[str, dict[str, Any]]]` — watch redraws the detail pane.

### Messages
- `ProviderEventReceived(event: ProviderEvent)` — child → screen, on every drained event.
- `RunRequested(provider: str, capability: str)` — emitted on key `p`, listened by the screen which spawns the worker.
- `RunCompleted(provider: str, latency_ms: float)` — worker → screen on success. `Prediction` does not expose an `id`; the latency is what the detail pane needs.
- `RunCancelled(provider: str)` — worker → screen when `is_cancelled` returns True.

### Worker contract (the heart of M3)
```python
@work(thread=True, group="provider", exclusive=True, name="provider.predict")
def _run_predict(self, provider_name: str) -> None:
    worker = get_current_worker()
    # The App constructed `WorldForge(event_handler=self._queueing_handler)` at startup,
    # so every registered provider already drains into `self._event_queue`.
    forge = self.app.forge
    world = self._current_or_scratch_world(forge)

    try:
        # mock.predict is synchronous and emits the success event before returning;
        # remote providers (M4+) emit retry / success / failure progressively, so the
        # drain loop already handles streaming providers without further refactor.
        prediction = world.predict(Action(kind="noop"), steps=1, provider=provider_name)
    except ProviderError as exc:
        self.app.call_from_thread(
            self.post_message,
            ProviderEventReceived(_failure_event(provider_name, exc)),
        )
        return

    while not self._event_queue.empty():
        if worker.is_cancelled:
            self.app.call_from_thread(self.post_message, RunCancelled(provider_name))
            return
        event = self._event_queue.get_nowait()
        self.app.call_from_thread(self.post_message, ProviderEventReceived(event))

    self.app.call_from_thread(
        self.post_message,
        RunCompleted(provider=provider_name, latency_ms=prediction.latency_ms),
    )
```

`Esc` binding:
```python
def action_cancel_run(self) -> None:
    if self.running_operation == "running":
        self.workers.cancel_group("provider")  # the worker checks is_cancelled
```

The worker contract above maps 1:1 to roadmap §6 and SKILL.md "Long-running work uses workers." It is the only worker shape this milestone introduces; M4 reuses it.

## Theming and CSS

All TCSS for `ProvidersScreen` references semantic variables only — zero hex literals (this milestone exists partly to demonstrate the practice).

| Element | Variable |
| --- | --- |
| Capability cell, "real" dot | `$success` |
| Capability cell, "scaffold" dot | `$warning` |
| Capability cell, "not advertised" | `$muted` |
| Selected row gutter | `$accent` |
| Active pane border | `border: round $accent` (per roadmap §2.2) |
| Idle pane border | `border: round $panel` |
| RichLog "failure" line | `$error` |
| RichLog "retry" line | `$warning` |
| Default text | `$surface` |
| Hint / secondary text | `$muted` |

A snapshot test of `worldforge-light` confirms the matrix and `RichLog` remain readable on a light terminal — that is the M0 → M3 regression bar (failure mode #3 in SKILL.md "Why this skill exists").

## Testing

### Pilot interaction tests (`tests/test_harness_tui.py`)
- `test_providers_screen_rows_match_registered_providers` — open `ProvidersScreen`, assert `DataTable.row_count == len(WorldForge().list_providers())`.
- `test_providers_screen_columns_match_capability_names` — assert `DataTable.column_count == len(CAPABILITY_NAMES)`.
- `test_capability_cells_reflect_provider_capabilities` — register a fixture provider with `ProviderCapabilities(predict=True, generate=False)`; assert the rendered cells dual-code "●" + `$success` for predict and blank + `$muted` for generate.
- `test_enter_sets_current_provider` — focus row "mock"; `pilot.press("enter")`; assert `app.current_provider == "mock"` and the Header status pill text contains "mock".
- `test_p_runs_real_mock_predict_and_streams_events` — `pilot.press("p")`; await `pilot.pause()`; assert at least one `ProviderEvent` with `phase == "success"` was rendered into the `RichLog`.
- `test_esc_cancels_running_predict` — using the `slow_mock_provider` fixture; press `p`; press `esc` mid-run; assert `running_operation == "cancelled"` within one frame; assert a `RunCancelled` message was posted.
- `test_event_loop_remains_responsive_during_run` — using the slow-mock; press `p`; press `ctrl+t` (theme switch); assert the theme actually changed mid-run (the App's `theme` reactive flipped).
- `test_register_provider_modal_appends_row` — press `r`; dismiss modal with a constructed handle; assert the matrix row count increased by one and the new row appears.
- `test_no_blocking_io_in_compose_or_on_mount` — Pilot test that opening `ProvidersScreen` does not hit any `WorldForge` heavy method on the main task (use a recorder around `world.predict` and assert it is not called from `compose` / `on_mount`).

### Snapshot tests (`tests/test_harness_tui_snapshots.py`)
- `test_providers_screen_idle_dark_snapshot` — `terminal_size=(120, 40)`, default theme.
- `test_providers_screen_idle_light_snapshot` — same, `worldforge-light`.
- `test_providers_screen_mid_run_snapshot` — drive `pilot.press("p")` then `pilot.pause()` for a fixed simulated tick count from the slow-mock; capture.
- `test_providers_screen_cancelled_snapshot` — drive run, press `esc`, capture.

All snapshots use `terminal_size=(120, 40)` per SKILL.md "Snapshot test default screens at `terminal_size=(120, 40)`."

### Coverage gate
- `uv run --extra harness pytest --cov=src/worldforge --cov-report=term-missing --cov-fail-under=90` must still pass. The new code is in `tui.py` (covered by Pilot tests) and the test fixtures themselves; no decrease in baseline expected.

### Truthfulness regression test
- `test_capability_matrix_is_not_hand_coded` — a static test that grep / AST-walks `tui.py` for any literal capability dict (e.g., `{"mock": {"predict": True, ...}}`) and fails if found. The matrix must derive from `provider.capabilities` at render time only.

## Risks and mitigations
- **Risk:** worker thread mutates a widget directly (e.g., `log.write(...)` from inside the worker body). **Mitigation:** all worker-to-UI hops go through `self.app.call_from_thread(self.post_message, ...)`; reviewer rule + a code comment at the top of the worker function. The Pilot test `test_event_loop_remains_responsive_during_run` would surface a stall in CI.
- **Risk:** capability matrix drifts from `ProviderCapabilities` (someone edits `tui.py` to "fix a wrong cell"). **Mitigation:** the matrix is derived at render time from `provider.capabilities` only; `test_capability_matrix_is_not_hand_coded` plus `test_capability_cells_reflect_provider_capabilities` catch a hand-coded override. Capability flag drift is caught upstream by `assert_provider_contract` in `tests/test_provider_contracts.py`, which is the right layer per `<priority_rules>` #1.
- **Risk:** secrets or signed URLs leak into the `RichLog`. **Mitigation:** the TUI never interpolates `event.message` / `event.metadata` into the log line; the line is built from `phase`, `provider`, `operation`, `duration_ms` only. The provider's own sanitisation contract (per `<code_conventions>`) handles its event payloads.
- **Risk:** the throwaway "scratch" world from the M3 fallback litters `.worldforge/worlds/`. **Mitigation:** `WorldForge.create_world` returns a `World` in memory and only persists when the host calls `save_world(...)` — M3's predict path never calls `save_world`, so no JSON is written. The state dir is still created at `WorldForge.__init__` time but stays empty for the scratch flow. If/when M2 lands, the scratch fallback is replaced by `selected_world`.
- **Risk:** `Esc` swallows the user's intent to back out of the screen rather than cancel the run. **Mitigation:** `Esc` cancels the worker only when `running_operation == "running"`; otherwise it routes to the screen's normal pop. Documented in the footer entry and the `?` help overlay.
- **Risk:** the M0 / M1 dependencies are not yet merged when this lands. **Mitigation:** the spec marks them required; if M0/M1 PRs are still open, M3 sits behind them in the merge queue. M2 is optional and the scratch-world fallback covers its absence.

## Dependencies on other milestones
- **Required before this can ship:**
  - **M0** — semantic CSS variables, `Theme` registrations, Header status pill reactive (`current_provider`).
  - **M1** — screen stack, `push_screen` / `push_screen_wait`, `Ctrl+P` system commands (so "Open providers" can register), `?` help overlay.
- **Optional but improves UX:**
  - **M2** — Worlds CRUD; `selected_world` becomes the predict target. Without M2, the scratch-world fallback is used.
- **This milestone blocks:**
  - **M4** — `EvalScreen` and `BenchmarkScreen` reuse the same worker contract, the same `ProviderEventReceived` message class, and the same `RichLog` styling. M3 is the reference implementation.
  - **M5** — the dynamic command palette `Provider` for "every provider as a fuzzy item" depends on `ProvidersScreen` existing as the jump target.

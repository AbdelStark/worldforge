# Milestone M3 — Live providers · Tasks

Each task is a single PR-sized unit. Order matters: a later task assumes the previous tasks' code is in place. All tasks land on `src/worldforge/harness/tui.py` and `tests/` only — Textual's import boundary is preserved.

## T1 — Add `ProvidersScreen` skeleton with capability matrix (read-only)
- Files: `src/worldforge/harness/tui.py`, `tests/test_harness_tui.py`
- Change: introduce `ProvidersScreen(Screen)` rendering a `DataTable` (rows = `WorldForge.list_providers()`, columns = `worldforge.models.CAPABILITY_NAMES`) plus an empty detail pane. Cells derive from `provider.capabilities` and `provider.implementation_status` only. Register the screen via the M1 screen stack and add a `Ctrl+P` system command "Open providers". TCSS uses semantic variables only (`$success` / `$warning` / `$muted` / `$accent` / `$panel`).
- Acceptance:
  - Acceptance criteria 1, 2, 9 from `spec.md`.
  - `ProvidersScreen` reachable from the command palette and from a top-level binding.
  - Empty state rendered when `WorldForge.list_providers()` is empty.
- Tests:
  - `test_providers_screen_rows_match_registered_providers`
  - `test_providers_screen_columns_match_capability_names`
  - `test_capability_cells_reflect_provider_capabilities`
  - `test_capability_matrix_is_not_hand_coded`

## T2 — Wire selection: `current_row_provider` reactive + `Enter` sets `App.current_provider`
- Files: `src/worldforge/harness/tui.py`, `tests/test_harness_tui.py`
- Change: add `current_row_provider: reactive[str | None]` on `ProvidersScreen` watching `DataTable` cursor; bind `Enter` to set `self.app.current_provider` to the highlighted provider. The Header status pill (introduced in M0) updates via its existing `watch_current_provider`.
- Acceptance:
  - User story 3 from `spec.md`.
  - Footer shows the `Enter` binding (`show=True`).
- Tests:
  - `test_enter_sets_current_provider`

## T3 — Detail pane: `health()`, env-var names, last-call summary
- Files: `src/worldforge/harness/tui.py`, `tests/test_harness_tui.py`
- Change: render the detail pane on `watch_current_row_provider`. Source: `WorldForge.provider_profile(name)` for env-var names + `implementation_status`, `WorldForge.provider_health(name)` for status / latency, `last_call_summary` reactive for the most recent call's `phase` / `latency_ms` / `retries`. Env-var values are **not** read from `os.environ` (open question in spec; defaulting to names-only for safety).
- Acceptance:
  - User story 2 from `spec.md`.
  - No call to `os.environ` from the detail pane.
- Tests:
  - `test_detail_pane_renders_health_and_env_vars`
  - `test_detail_pane_shows_last_call_summary_after_run` (depends on T5)

## T4 — Worker plumbing: messages, reactives, `_QueueingEventHandler`, `RichLog`
- Files: `src/worldforge/harness/tui.py`, `tests/test_harness_tui.py`
- Change: add the typed `Message` classes (`ProviderEventReceived`, `RunRequested`, `RunCompleted`, `RunCancelled`), the `running_operation` reactive, the `_QueueingEventHandler` adapter (pushes `ProviderEvent` into a `queue.Queue`), and the `RichLog(highlight=True, markup=True, max_lines=5000)` widget. Add the screen handler `on_provider_event_received` that formats the line per decision D7 in `plan.md`.
- Acceptance:
  - All scaffolding for T5 in place; no functional behavior yet beyond rendering posted messages.
- Tests:
  - `test_provider_event_received_writes_to_rich_log` (post a fabricated `ProviderEvent` directly; assert one line appears, with phase color via markup).
  - `test_rich_log_does_not_render_event_metadata` (truthfulness — fabricated event with metadata, assert log line does not contain the metadata text).

## T5 — Real `mock.predict` worker + `p` binding + scratch-world fallback
- Files: `src/worldforge/harness/tui.py`, `tests/test_harness_tui.py`, `tests/conftest.py`
- Change: add the `_run_predict` worker per `plan.md` "Worker contract" — `@work(thread=True, group="provider", exclusive=True, name="provider.predict")`. Bind `p` to post `RunRequested(provider=app.current_provider, capability="predict")`; the screen handler spawns the worker. World source: `selected_world` if set (M2), else `WorldForge.create_world("scratch")` in-memory. Add `slow_mock_provider` fixture in `conftest.py`.
- Acceptance:
  - Acceptance criteria 4, 5, 8 from `spec.md`.
  - User stories 4, 7 from `spec.md`.
- Tests:
  - `test_p_runs_real_mock_predict_and_streams_events`
  - `test_event_loop_remains_responsive_during_run`
  - `test_no_blocking_io_in_compose_or_on_mount`

## T6 — Cancellation: `Esc` binding, `is_cancelled` check, observable status transition
- Files: `src/worldforge/harness/tui.py`, `tests/test_harness_tui.py`
- Change: add `action_cancel_run` bound to `Esc` calling `self.workers.cancel_group("provider")` only when `running_operation == "running"`. The worker checks `get_current_worker().is_cancelled` between drained events; on cancel it posts `RunCancelled(provider)` and the screen flips `running_operation` to `"cancelled"`. Add the visible "Cancel" click target next to the `ProgressBar` (mouse + keyboard parity).
- Acceptance:
  - Acceptance criteria 6, 7 from `spec.md`.
  - User story 5 from `spec.md`.
  - `Esc` falls through to normal screen-pop when `running_operation != "running"`.
- Tests:
  - `test_esc_cancels_running_predict`
  - `test_esc_pops_screen_when_idle`

## T7 — `RegisterProvider[ProviderHandle]` modal + `r` binding
- Files: `src/worldforge/harness/tui.py`, `tests/test_harness_tui.py`
- Change: add `RegisterProviderModal(ModalScreen[ProviderHandle | None])` with a name + class form. On dismiss with a non-`None` handle, the screen calls `WorldForge.register_provider(...)` and refreshes the matrix in place (no screen pop / repush). Bind `r` to `push_screen_wait(RegisterProviderModal())` from inside a worker (per SKILL.md troubleshooting).
- Acceptance:
  - Acceptance criterion 8 from `spec.md`.
  - User story 6 from `spec.md`.
- Tests:
  - `test_register_provider_modal_appends_row`

## T8 — Snapshot tests at `terminal_size=(120, 40)`
- Files: `tests/test_harness_tui_snapshots.py`
- Change: add four snapshots — `idle_dark`, `idle_light`, `mid_run`, `cancelled`. All use `terminal_size=(120, 40)` and a deterministic seed via the `slow_mock_provider` fixture; mid-run uses `pilot.pause()` after a fixed simulated tick count to remove timing flake.
- Acceptance:
  - Acceptance criterion 9 from `spec.md` (snapshots exist for the three states + the light variant).
- Tests:
  - `test_providers_screen_idle_dark_snapshot`
  - `test_providers_screen_idle_light_snapshot`
  - `test_providers_screen_mid_run_snapshot`
  - `test_providers_screen_cancelled_snapshot`

## T9 — Roadmap honesty + AGENTS / CLAUDE notes (closing PR)
- Files: `.codex/skills/tui-development/references/roadmap.md`, `CHANGELOG.md`
- Change: mark roadmap §8 "M3 — Live providers" as `done · YYYY-MM-DD`. Add a CHANGELOG entry under "Unreleased": `feat(harness): live mock.predict from ProvidersScreen with cancellable worker and event streaming`.
- Acceptance:
  - Roadmap is honest per `<context_lifecycle>`.
  - CHANGELOG mentions only the public, user-visible change (no agent / tool branding per `<priority_rules>` #5).
- Tests:
  - none new; the full local gate from `CLAUDE.md <commands>` runs green.

## Definition of done
- [ ] Tasks T1–T9 merged.
- [ ] Pilot tests in `tests/test_harness_tui.py` pass under `uv run --extra harness pytest`.
- [ ] Snapshot SVGs committed and reviewed in the PR diff.
- [ ] Coverage gate passes: `uv run --extra harness pytest --cov=src/worldforge --cov-report=term-missing --cov-fail-under=90`.
- [ ] Package contract passes: `bash scripts/test_package.sh` (no leak of Textual into base imports).
- [ ] Provider docs check passes unchanged (no provider catalog change in M3).
- [ ] Roadmap §8 marked "done · YYYY-MM-DD".
- [ ] No new entries in `[project.optional-dependencies].harness` beyond Textual.
- [ ] Branch / commit / PR text remains maintainer-style, tool-neutral (no agent / tool branding).

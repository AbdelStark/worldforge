# Milestone M1 — Screen architecture · Tasks

Each task is a single PR-sized unit. Order matters: a later task may assume an earlier one has landed in main. Each task should keep `uv run --extra harness pytest` green at the end.

## T1 — Introduce the screen scaffold and `SCREENS` registry
- Files: `src/worldforge/harness/tui.py`
- Change: Add a `RunInspectorScreen(Screen)` class that wraps the existing `compose` body and the existing `_run_flow` / `_refresh_static` / `_on_flow_changed` / `_on_run_pressed` handlers, plus the `r`, `1`, `2`, `3` bindings. `TheWorldHarnessApp.compose` becomes a no-op aside from `Header` / `Footer` (handled by Screen). Register `SCREENS = {"run-inspector": RunInspectorScreen}`. In `on_mount`, `push_screen("run-inspector")`. The App still exposes `selected_flow_id` / `state_dir` / `step_delay` for the screen to read on construction. Behaviour from the user's perspective is unchanged.
- Acceptance: maps to spec criterion "all four existing tests in `tests/test_harness_tui.py` continue to pass after being updated to push `RunInspectorScreen` first". The harness still launches into the flow visualisation with `--flow` working identically.
- Tests: existing `test_the_world_harness_app_runs_leworldmodel_flow`, `test_the_world_harness_app_switches_to_lerobot_flow`, `test_the_world_harness_app_switches_to_diagnostics_flow` pass after asserting on `app.screen.last_run` instead of `app.last_run` (or by exposing `last_run` as a property on the App that delegates to the screen).

## T2 — Add `HomeScreen` with three jump cards and `JumpCard` widget
- Files: `src/worldforge/harness/tui.py`
- Change: Add `JumpCard(Static)` (`can_focus=True`, posts `JumpRequested(target: str)`) and `HomeScreen(Screen)` composing a 30-second intro `Static`, three `JumpCard`s for "Create a world" (`n`), "Run a provider" (`p`), "Run an eval" (`e`), and an empty-state Static for the recent-items area. Register `"home": HomeScreen` in `SCREENS`. Default initial screen becomes `"home"` unless `--flow` was explicitly passed.
- Acceptance: maps to "On launch with no `--flow`, the active screen is `HomeScreen`" and "On launch with `--flow <id>`, the active screen is `RunInspectorScreen`".
- Tests: new `test_initial_screen_is_home_when_no_flow_flag` and `test_initial_screen_is_run_inspector_when_flow_flag_passed`.

## T3 — `--flow` CLI semantic preserved end-to-end
- Files: `src/worldforge/harness/cli.py`, `src/worldforge/harness/tui.py`
- Change: Distinguish "user passed `--flow`" from default. Pass an `initial_screen: Literal["home", "run-inspector"]` argument into `TheWorldHarnessApp.__init__` derived from CLI presence. `TheWorldHarnessApp.on_mount` pushes that screen.
- Acceptance: maps to spec criterion 3 ("On launch with `--flow <id>`, the active screen is `RunInspectorScreen`").
- Tests: extend `tests/test_harness_cli.py` to assert the constructor receives the expected `initial_screen` value for both code paths. Pilot test: `test_initial_screen_is_run_inspector_when_flow_flag_passed`.

## T4 — `HelpScreen` modal bound to `?`
- Files: `src/worldforge/harness/tui.py`
- Change: Add `HelpScreen(ModalScreen[None])` that on mount queries the App's previous screen and renders its `BINDINGS` as a `DataTable` (columns: `key`, `description`, `action`). App-level `BINDINGS` gets `("?", "push_screen('help')", "Help", show=True)`. Help screen dismisses on `escape` or `q`.
- Acceptance: "Pressing `?` from any screen pushes a `HelpScreen` modal that lists the bindings declared on the screen below it" and "Dismissing the `HelpScreen` returns control to the previously active screen".
- Tests: new `test_help_overlay_opens_and_closes`. Snapshot: `HelpScreen` overlay over `RunInspectorScreen` at `terminal_size=(120, 40)`.

## T5 — Static system commands via `get_system_commands` (`Ctrl+P`)
- Files: `src/worldforge/harness/tui.py`
- Change: Implement `App.get_system_commands(self, screen)` that yields `("Jump: Home", "Open Home", lambda: self.push_screen("home"))`, `("Jump: Run Inspector", ...)`, `("Open Help", ...)`, one entry per flow id from `available_flows()` ("Run flow: <title>" — switches `RunInspectorScreen` to that flow, pushing the screen if not already on the stack), `("Switch theme", ...)` (delegates to M0's theme command), and `("Quit", ...)`. App-level `BINDINGS` keeps stock `("ctrl+p", "command_palette", "Commands", show=True)`.
- Acceptance: "Pressing `Ctrl+P` opens the command palette and the listing includes one entry per registered flow … one 'Jump to Home', one 'Jump to Run Inspector', one 'Open Help', one 'Quit'."
- Tests: new `test_command_palette_lists_screens_and_flows`. Existing tests must still pass.

## T6 — Chord bindings `g h` / `g r` and footer hygiene
- Files: `src/worldforge/harness/tui.py`
- Change: Add chord bindings on the App: `("g,h", "switch_screen('home')", "Jump: Home", show=False)` and `("g,r", "switch_screen('run-inspector')", "Jump: Run Inspector", show=False)`. Audit every `BINDINGS` entry across the App and the two new screens to make sure `show=True` only appears on user-facing actions per the skill's footer-cleanliness rule.
- Acceptance: "`g h` jumps to `HomeScreen` from any non-modal screen; `g r` jumps to `RunInspectorScreen`" and "The `Footer` shows only the bindings of the active screen, not stale App-level entries".
- Tests: new `test_jump_to_home_from_run_inspector` and `test_jump_to_run_inspector_from_home`.

## T7 — `PlaceholderScreen` for not-yet-built jump targets
- Files: `src/worldforge/harness/tui.py`
- Change: Add `PlaceholderScreen(ModalScreen[None])` that takes a `target_milestone: str` and a `next_action: str` and renders both. `HomeScreen.on_jump_requested` routes "create a world" / "run a provider" / "run an eval" to a `PlaceholderScreen` with the right milestone label until M2 / M3 / M4 overwrites them.
- Acceptance: "Run a provider" and "Run an eval" cards do not silently fail — they push a clearly labelled placeholder modal.
- Tests: new `test_home_jump_card_keyboard_activation` (asserts `PlaceholderScreen` on stack after `n`). Snapshot: `PlaceholderScreen` overlay over `HomeScreen`.

## T8 — Breadcrumb wiring
- Files: `src/worldforge/harness/tui.py`
- Change: Wire each screen's `on_screen_resume` (and `on_mount`) to update the M0 `Breadcrumb` widget: `worldforge › home`, `worldforge › run-inspector › <flow-id>`, `worldforge › help`, `worldforge › placeholder`.
- Acceptance: "The `Header` breadcrumb text changes when the active screen changes."
- Tests: extend `test_jump_to_home_from_run_inspector` to assert the breadcrumb's text reactive after the jump.

## T9 — Migrate residual hex literals on touched panes
- Files: `src/worldforge/harness/tui.py`
- Change: Replace inline hex literals in `HeroPane`, `FlowCard`, `TimelinePane`, `InspectorPane`, `TranscriptPane`, and the App-level `CSS` block with semantic variables registered by M0. No new tokens introduced.
- Acceptance: spec NFR "No hex literals in any new TCSS — semantic variables only (M0 contract)."
- Tests: relies on existing snapshot tests. New snapshots from T2 / T4 / T7 must contain no raw hex.

## T10 — Roadmap update
- Files: `.codex/skills/tui-development/references/roadmap.md`
- Change: Mark §8 "M1 — Screen architecture" `done · 2026-MM-DD` once T1–T9 are merged. Do not edit the milestone description itself.
- Acceptance: Per skill "Stop and ask the user — before declaring a milestone in `references/roadmap.md` 'done'".
- Tests: docs-only; `uv run python scripts/generate_provider_docs.py --check` still passes (this file is not provider-generated).

## Definition of done
- [ ] All tasks T1–T10 merged.
- [ ] Pilot tests in `tests/test_harness_tui.py` cover: initial screen by CLI flag, `g h` / `g r` jumps, `?` overlay open/close, `Ctrl+P` listing, jump-card keyboard activation.
- [ ] Snapshot tests added for `HomeScreen`, `RunInspectorScreen` mid-flow, `HelpScreen` overlay, `PlaceholderScreen` overlay — all pinned at `terminal_size=(120, 40)`.
- [ ] `uv run --extra harness pytest --cov=src/worldforge --cov-report=term-missing --cov-fail-under=90` passes.
- [ ] `uv run ruff check src tests examples scripts` and `uv run ruff format --check src tests examples scripts` pass.
- [ ] No new runtime dependency in the `harness` extra.
- [ ] `flows.py`, `cli.py`, `models.py` remain Textual-free.
- [ ] Roadmap §8 marked "done · {date}".

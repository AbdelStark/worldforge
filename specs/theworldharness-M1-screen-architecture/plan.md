# Milestone M1 — Screen architecture · Implementation Plan

## Builds on
- Roadmap §8 "M1 — Screen architecture" — `.codex/skills/tui-development/references/roadmap.md`
- Roadmap §3 "Architecture (target)" — single `App`, many `Screen`s; `BINDINGS: ?, q, ctrl+p, ctrl+t, esc`; system commands per screen
- Roadmap §4.1 (HomeScreen), §4.8 (RunInspectorScreen), §4.9 (Modal screens)
- Roadmap §5 (Command palette — static system commands layer only for M1; dynamic `Provider` deferred to M5)
- Skill: `.codex/skills/tui-development/SKILL.md` — "One App, many Screens"; `ModalScreen[T]`; messages over reach-across; bindings on screen with `show=True`; `App.get_system_commands`; worker contract
- Predecessor milestone: M0 (registered `worldforge-dark` / `worldforge-light` `Theme`s, `Header` clock, `Breadcrumb` widget, provider status pill)

## Architecture changes
- **`HomeScreen(Screen)`** — new. Composes a 30-second intro `Static`, three `JumpCard` widgets (`n`, `p`, `e`), and an empty "Recent" placeholder area (the populated recent-items list ships with M5; M1 leaves a per §2.4 empty-state Static there).
- **`RunInspectorScreen(Screen)`** — new. Re-homes the existing `HeroPane`, flow rail (`Select` + `FlowCard`s + Run `Button`), `TimelinePane`, `InspectorPane`, `TranscriptPane`. The `selected_flow_id` and `running` fields move from `App` to this screen.
- **`HelpScreen(ModalScreen[None])`** — new. On mount, queries `self.app.screen` (the screen below it on the stack) and renders its `BINDINGS` as a `DataTable` with columns `key`, `action`, `description`. Dismisses on `escape` or `q`.
- **`PlaceholderScreen(ModalScreen[None])`** — new. Used by the "Run a provider" and "Run an eval" jump cards in M1 to explain that those screens land in M3 / M4. Replaced by real `ProvidersScreen` / `EvalScreen` push targets in those milestones.
- **`JumpCard(Static)`** — new custom widget. `can_focus=True`, posts a `JumpRequested(target: str)` `Message` on `enter`, click, or its bound letter. Border becomes `round $accent` on `:focus`.
- **`TheWorldHarnessApp`** — modified. Slim down to: `SCREENS = {"home": HomeScreen, "run-inspector": RunInspectorScreen}`, App-level `BINDINGS` for `?`, `ctrl+p`, `ctrl+t` (theme — M0 deliverable, kept), `q`, plus chord prefixes `g h` / `g r`. Drop the App-level `r`, `1`, `2`, `3` bindings (those move to `RunInspectorScreen`). Implement `get_system_commands(self, screen)` to yield the static command list. Initial `push_screen` decision moves to `on_mount`: push `"run-inspector"` if `initial_flow_id` was set explicitly via CLI, otherwise `"home"`.

## Module touch list
| Path | Change | Notes |
| --- | --- | --- |
| `src/worldforge/harness/tui.py` | Refactor: extract `HomeScreen`, `RunInspectorScreen`, `HelpScreen`, `PlaceholderScreen`, `JumpCard` from the existing single-screen App. App becomes a scaffold + `SCREENS` registry + `get_system_commands`. | Textual import boundary preserved — everything stays in this file. Existing `HeroPane`, `FlowCard`, `TimelinePane`, `InspectorPane`, `TranscriptPane` move into `RunInspectorScreen.compose` unchanged. |
| `src/worldforge/harness/cli.py` | One change: distinguish "user passed `--flow`" from "default value". Pass `initial_screen` hint into `TheWorldHarnessApp(...)`. | Keep CLI surface backwards-compatible — `--flow` semantics unchanged for users. |
| `tests/test_harness_tui.py` | Update three existing tests to assert against `app.screen` and to push `RunInspectorScreen` (either via `--flow` constructor arg, which still pushes it, or explicitly via `app.push_screen("run-inspector")`). Add new tests per "Testing" below. | Pilot patterns extended; no new test framework dependency. |
| `src/worldforge/harness/flows.py` | No change. | M1 is structural; `available_flows()` / `run_flow()` are reused as-is by `RunInspectorScreen`. |
| `src/worldforge/harness/models.py` | No change. | Public `HarnessFlow` / `HarnessRun` / `HarnessStep` / `HarnessMetric` shapes are stable per skill "Stop and ask". |

## Key technical decisions

### Use `ModalScreen[None]` for help overlay (vs an inline collapsed pane)
- **Decision:** `HelpScreen(ModalScreen[None])`.
- **Alternatives considered:** A `Collapsible` pane on each screen; an `App`-level overlay `Container` toggled by `display:none`.
- **Rationale:** The skill is explicit ("Type `ModalScreen[T]` so dismiss results are checked"). A modal is the only option that preserves screen-stack semantics, restores focus correctly on dismiss, and works uniformly from every screen. `display:none` toggling is the failure mode the roadmap §3 explicitly rejects ("New top-level views are `Screen` subclasses pushed onto the stack — never `display:none` toggling on one mega-screen").

### Static system commands via `App.get_system_commands` (vs a custom `Provider`)
- **Decision:** Implement `App.get_system_commands(self, screen)` only. No `textual.command.Provider` subclass in M1.
- **Alternatives considered:** Build the dynamic `Provider` now, leaving its yield list as just the static items.
- **Rationale:** Roadmap §5 splits the palette into two layers: static system commands (M1) and a dynamic `Provider` (M5). Building the `Provider` now would either hard-code the M5 surface or ship empty stubs that drift before M5 lands. `get_system_commands` is the honest M1 surface; M5 adds the `Provider` subclass without touching it.

### Bindings on the screen, not on the App
- **Decision:** Move `r`, `1`, `2`, `3` to `RunInspectorScreen.BINDINGS`. App keeps only `?`, `ctrl+p`, `ctrl+t`, `q`, plus chord prefixes.
- **Alternatives considered:** Keep flow-selection bindings on the App so they work from Home too.
- **Rationale:** The skill's footer-cleanliness rule ("Bindings on the screen, with `show=True` for the footer") requires this. If `1` / `2` / `3` are App-level, they appear in every screen's footer and confuse Home-screen users. The right discovery surface for "run a flow from Home" is `Ctrl+P` ("run flow leworldmodel"), which the system commands provide.

### Chord bindings `g h` / `g r` for jump navigation
- **Decision:** Use Textual chord syntax (`("g,h", "jump('home')", "Jump: Home", show=False)`).
- **Alternatives considered:** Single-key bindings on the App (`h` for Home, `R` for Run Inspector).
- **Rationale:** The skill cites lazygit / k9s as inspirations; both use chord-prefix navigation (`g`-prefix is the de-facto vim convention). Single keys would collide with future per-screen bindings (e.g. M2 `WorldsScreen` wants `n` for new world).

### Jump cards are a custom `Static` subclass, not stock `Button`s
- **Decision:** `JumpCard(Static)` with `can_focus=True` and a `JumpRequested(target: str)` posted message.
- **Alternatives considered:** Three stock `Button` widgets in a `Horizontal` container.
- **Rationale:** Roadmap §4.1 calls them "three big jump cards" — visual hierarchy that stock buttons cannot carry. Custom `Static` lets us own the border state (`:focus { border: round $accent }`) and the multi-line content (title + binding hint + one-line description). `JumpRequested` keeps the parent–child message contract per the skill's "Messages over reach-across" rule.

### Placeholder modal for not-yet-built jump targets
- **Decision:** "Run a provider" and "Run an eval" cards push a `PlaceholderScreen(ModalScreen[None])` in M1 that says "Lands in M3 / M4 — track in roadmap.md §8".
- **Alternatives considered:** Disable those cards in M1; or omit them entirely.
- **Rationale:** Roadmap §4.1 specifies three jump cards. Disabling two of them would tell first-time users that two thirds of the harness is broken. A placeholder modal is honest (the work is real, just not yet shipped) and creates a target for M3 / M4 to overwrite without changing Home.

## Data flow
- **Reactives:**
  - `RunInspectorScreen.selected_flow_id: reactive[str]` — moved from `App`. Paired with `watch_selected_flow_id` to redraw the rail.
  - `RunInspectorScreen.running: reactive[bool]` — moved from `App`. Paired with `watch_running` to toggle the Run button's `disabled` state and the hero pane's status text.
  - `RunInspectorScreen.last_run: reactive[HarnessRun | None]` — moved from `App`.
- **Messages:**
  - `JumpRequested(target: str)` — posted by `JumpCard` on activation. Handled by `HomeScreen.on_jump_requested` which calls `self.app.push_screen(target)` for routable targets or `self.app.push_screen(PlaceholderScreen(...))` for M3 / M4 placeholders.
- **Workers:**
  - **None in M1.** M1 is structural. The existing `_run_flow` keeps its `asyncio.sleep` rhythm and stays on the screen's main task — replacing it with a real `@work(thread=True, group="provider", exclusive=True, name="<flow-id>")` worker is M3's deliverable per roadmap §8 M3 and the skill's worker contract. Any worker added now would be removed in M3 because the slideshow itself goes away then; M1 must not pre-empt that work.
- **`push_screen_wait` usage:** Reserved for modals that return a value (e.g. M2's `ConfirmDelete[bool]`). M1 modals (`HelpScreen`, `PlaceholderScreen`) are `ModalScreen[None]` and are pushed with plain `push_screen` — `push_screen_wait` is wired into the App scaffold so M2 can use it without further plumbing.

## Theming and CSS
- All borders, backgrounds, text colors come from semantic CSS variables registered by M0: `$accent`, `$success`, `$warning`, `$error`, `$panel`, `$boost`, `$surface`, `$muted`. No hex literals.
- `JumpCard` focus ring: `JumpCard:focus, JumpCard:focus-within { border: round $accent; }`. Idle: `border: round $panel`.
- `HelpScreen` modal background: `background: $surface 90%`; outer container: `border: round $accent`.
- `PlaceholderScreen` modal: same chrome as `HelpScreen` but with `border: round $warning` to signal "scaffold-not-yet-real" per roadmap §2.1.
- `Footer` and `Header` styling stays inherited from the registered theme — no per-screen overrides.
- The existing inline hex literals in `tui.py` (`#d8c46a`, `#8ec5a3`, `#101512`, `#171f1a`, `#d3d6cf`, `#3b423e`, `#6f7770`, `#e4dfc5`, `#9ea89f`) get replaced as part of moving each pane into its new screen — this is partly an M0 cleanup carried into M1 because the surrounding code is already being touched.

## Testing
- **Pilot tests** (extending `tests/test_harness_tui.py`):
  - `test_initial_screen_is_home_when_no_flow_flag`: launch app with no `--flow`, assert `isinstance(app.screen, HomeScreen)`.
  - `test_initial_screen_is_run_inspector_when_flow_flag_passed`: launch with `initial_flow_id="lerobot"` via the explicit CLI path, assert `isinstance(app.screen, RunInspectorScreen)` and `app.screen.selected_flow_id == "lerobot"`.
  - `test_jump_to_home_from_run_inspector`: start on `RunInspectorScreen`, `await pilot.press("g", "h")`, assert `isinstance(app.screen, HomeScreen)`.
  - `test_help_overlay_opens_and_closes`: `await pilot.press("?")`, assert `isinstance(app.screen, HelpScreen)`; `await pilot.press("escape")`, assert previous screen restored.
  - `test_command_palette_lists_screens_and_flows`: `await pilot.press("ctrl+p")`, await pause, assert command palette contains entries for "Jump: Home", "Jump: Run Inspector", "Help", and one per flow id from `available_flows()`.
  - `test_home_jump_card_keyboard_activation`: on `HomeScreen`, `await pilot.press("n")`, assert a `PlaceholderScreen` (or in M2+, `WorldsScreen`) is on the stack.
  - Update existing three tests (`leworldmodel`, `lerobot`, `diagnostics`) to push `RunInspectorScreen` first — either by passing `initial_flow_id` (which now triggers the push in `on_mount`) or via `await app.push_screen("run-inspector")`.
- **Snapshot tests** (`pytest-textual-snapshot`, pinned `terminal_size=(120, 40)` per skill):
  - `HomeScreen` empty (no recent items).
  - `RunInspectorScreen` mid-flow with `leworldmodel` selected.
  - `HelpScreen` overlay over `RunInspectorScreen`.
  - `PlaceholderScreen` overlay over `HomeScreen`.
- **Coverage gate:** `uv run --extra harness pytest --cov=src/worldforge --cov-report=term-missing --cov-fail-under=90` must still pass. The refactor adds new code; the new code is covered by the new Pilot tests.

## Risks and mitigations
- **Risk:** Existing `tests/test_harness_tui.py` asserts `app.query_one("#inspector")` while the inspector lives on the App. After M1 it lives on `RunInspectorScreen`.
  - **Mitigation:** Update the assertion to `app.screen.query_one("#inspector")` and push `RunInspectorScreen` first. Documented as task T6.
- **Risk:** Command palette discoverability tanks if `show=False` is overused on screen bindings.
  - **Mitigation:** Audit every `Binding` introduced in M1: chord prefixes (`g`) stay `show=False` because the chord targets carry the description; jump targets and `?` / `Ctrl+P` stay `show=True`. The acceptance criterion "Footer shows only the bindings of the active screen" enforces this.
- **Risk:** The `--flow` CLI flag's "I want to run this" intent gets diluted if it now opens Home with the flow merely pre-selected.
  - **Mitigation:** Decided in "Key technical decisions": `--flow` keeps pushing `RunInspectorScreen` directly. The CLI test in `tests/test_harness_cli.py` already asserts behaviour and must continue to pass.
- **Risk:** Hex literal cleanup balloons the PR beyond M1's scope.
  - **Mitigation:** Limited to the panes being touched (every pane that moves screens). Any pane that does not move stays as-is for M1 — its hex literals are M0 leftovers and get cleaned up under M0's banner if any remain.
- **Risk:** Extracting screens reorders widget IDs in ways that break snapshot tests added by M0.
  - **Mitigation:** Keep widget `id=` strings stable (`#hero`, `#timeline`, `#inspector`, `#transcript`, `#run-button`, `#flow-select`). Re-snapshot only the screens we are adding (Home, Help, Placeholder).

## Dependencies on other milestones
- **Required before this can ship:** M0 — registered `worldforge-dark` / `worldforge-light` themes, `Header` clock + `Breadcrumb` widget + provider status pill, semantic CSS variable surface. Without M0 the new screens would either ship more hex literals or render with the wrong chrome.
- **Blocks:** M2 (`WorldsScreen` + `WorldEditScreen` need `push_screen` / `push_screen_wait` and the `SCREENS` registry); M3 (`ProvidersScreen` and the worker contract need the screen-local binding pattern and the `get_system_commands` hook); M4 (`EvalScreen` / `BenchmarkScreen` ditto); M5 (the dynamic command palette `Provider` extends the static `get_system_commands` list M1 ships).

# Milestone M1 — Screen architecture

## Status
Draft · 2026-04-21

## Outcome (one sentence)
TheWorldHarness opens on a dedicated `HomeScreen` with three jump targets, the existing flow visualisation lives behind a routed `RunInspectorScreen`, and every action is reachable from `Ctrl+P` or a `?` help overlay so users never have to guess what keys exist.

## Why this milestone
The current TUI is a single mega-screen: `TheWorldHarnessApp` mounts the hero, rail, timeline, inspector, and transcript in one `compose`, and binds `r`, `1`, `2`, `3`, `q` directly on the `App`. There is no navigation layer, no command palette, and no way to discover keys beyond the footer. Per `.codex/skills/tui-development/references/roadmap.md` §1 (Vision), the harness must read like a "keyboard-first, discoverable, polished workspace where every action is one keystroke or one `Ctrl+P` away" — that is impossible without a screen stack and a system command surface.

M1's specific contribution is **navigation**, not interactivity. The slideshow nature of the existing flow runner (canned `asyncio.sleep` step animations) is a separate failure mode addressed by M3 (`.codex/skills/tui-development/SKILL.md` §"Why this skill exists" item 1). M1 is the structural prerequisite: once screens are routable and the command palette exists, M2–M5 can each add their own screen without further App-level surgery. M1 also unblocks the design language work from M0 — a `Header` breadcrumb only carries information once there is more than one screen to point at.

## In scope
- A `HomeScreen` that introduces WorldForge in roughly 30 seconds and presents three jump cards: **Create a world**, **Run a provider**, **Run an eval**, each mapped to a binding (`n`, `p`, `e`) per roadmap §4.1.
- A `RunInspectorScreen` that owns the existing flow visualisation (`HeroPane`, flow rail, `TimelinePane`, `InspectorPane`, `TranscriptPane`) currently composed on the App.
- A `HelpScreen` (`ModalScreen[None]`) bound to `?` that lists the active screen's bindings.
- `App.SCREENS` registry plus `push_screen` / `push_screen_wait` usage so navigation goes through the screen stack rather than `display:none` toggling.
- App-level `Ctrl+P` system commands surfaced via `App.get_system_commands` covering: jump to Home, jump to Run Inspector, open Help, switch each registered flow, run the selected flow, switch theme (registered in M0), and quit.
- `g h` / `g r` chord bindings for jump-to-Home and jump-to-Run-Inspector.
- A breadcrumb in the `Header` that reflects the active screen (`worldforge › home`, `worldforge › run-inspector › <flow-id>`).
- Pilot tests covering screen pushes, the command palette, `?` overlay, and the `--flow` initial-screen hint.

## Out of scope (explicit)
- Worlds CRUD (`WorldsScreen`, `WorldEditScreen`, `ConfirmDelete` modal) — defer to M2.
- Live provider workers, `Esc` cancellation, `RichLog` event streaming — defer to M3.
- `EvalScreen`, `BenchmarkScreen`, capability-mismatch toasts — defer to M4.
- Dynamic command palette `Provider` for worlds, providers, runs, suites — defer to M5. M1 ships only static system commands.
- Theme registration and the semantic CSS variable migration — that is M0's deliverable; M1 consumes it but does not extend it.
- Replacing the canned `asyncio.sleep` flow runner with real workers — M3.
- `DiagnosticsScreen` extraction — not on the roadmap until at least M4 polish.

## User stories
1. As a researcher launching `worldforge-harness` for the first time, I land on `HomeScreen` and read a one-screen explanation of WorldForge before doing anything else, so that I do not have to hunt through the README.
2. As a returning user, I press `Ctrl+P` and type "run flow", so that I find every flow runnable without remembering whether the binding is `1`, `2`, or `3`.
3. As any user, I press `?` from any screen and see the bindings live on that screen, so that I never have to read source to discover keys.
4. As a flow runner, I press `g h` from the Run Inspector, so that I jump back to Home without quitting and reopening the harness.
5. As a CLI user, I run `worldforge-harness --flow lerobot`, so that the harness opens directly on `RunInspectorScreen` with the LeRobot flow pre-selected.
6. As a keyboard-only user, I tab through the three Home jump cards and press `enter` on one, so that mouse and keyboard parity is real (roadmap §2.2).

## Acceptance criteria
- [ ] `App.SCREENS` registers at least `"home"` (`HomeScreen`) and `"run-inspector"` (`RunInspectorScreen`).
- [ ] On launch with no `--flow`, the active screen is `HomeScreen` (assertable via `app.screen.__class__.__name__`).
- [ ] On launch with `--flow <id>`, the active screen is `RunInspectorScreen` and `app.screen.selected_flow_id == <id>` for any id present in `available_flows()`.
- [ ] Pressing `Ctrl+P` opens the command palette and the listing includes one entry per registered flow (one per `available_flows()`), one "Jump to Home", one "Jump to Run Inspector", one "Open Help", one "Quit".
- [ ] Pressing `?` from any screen pushes a `HelpScreen` modal that lists the bindings declared on the screen below it (`show=True` and internal alike).
- [ ] Dismissing the `HelpScreen` (`escape` or `q`) returns control to the previously active screen with no state mutation.
- [ ] `g h` jumps to `HomeScreen` from any non-modal screen; `g r` jumps to `RunInspectorScreen`.
- [ ] The `Header` breadcrumb text changes when the active screen changes.
- [ ] The `Footer` shows only the bindings of the active screen, not stale App-level entries.
- [ ] All four existing tests in `tests/test_harness_tui.py` continue to pass after being updated to push `RunInspectorScreen` first (or to assert against `app.screen` of that type).

## Non-functional requirements
- The breadcrumb in the `Header` reflects the active screen, including the current flow id when `RunInspectorScreen` is active.
- The `Footer` shows only screen-local bindings (`show=True`); internal mechanics (`g`, `?`, chord prefixes) stay `show=False` to keep it scannable per `.codex/skills/tui-development/SKILL.md`.
- Mouse and keyboard parity holds on every jump target: Home jump cards must be activatable by `enter`, by click, and by their letter binding (`n`, `p`, `e`).
- The Textual import boundary is preserved: every new screen lives in `src/worldforge/harness/tui.py` (or a new sibling module that itself only imports Textual), and `flows.py`, `cli.py`, `models.py` stay Textual-free.
- No new runtime dependency in the `harness` extra.
- No hex literals in any new TCSS — semantic variables only (M0 contract).

## Open questions
- Should the three Home jump cards be three stock `Button` widgets or a custom `JumpCard(Static)` widget? Decided in plan.md (custom `Static` subclass with `can_focus=True`, since the roadmap §4.1 calls them "big jump cards" and stock buttons under-sell the visual hierarchy).
- Should the help overlay show only `show=True` bindings or every binding including `show=False`? Decided in plan.md (every binding, since the whole point of the overlay is discovery — `show=False` keeps the footer clean, not the help screen).
- Should the `--flow` CLI flag still default the user to `RunInspectorScreen`, or should it default to Home with the flow merely pre-selected? Decided in plan.md (keep current behaviour: `--flow` is an explicit "I want to run this" intent, so push `RunInspectorScreen` directly to preserve the muscle memory of every existing user).
- Should "Run a provider" and "Run an eval" jump cards be present on Home in M1 even though `ProvidersScreen` and `EvalScreen` do not exist until M3 / M4? Yes, but those cards push a `HelpScreen`-style placeholder modal explaining the milestone they ship in. Tracked in plan.md under "Key technical decisions".

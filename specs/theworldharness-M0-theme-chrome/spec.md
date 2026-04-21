# Milestone M0 — Theme + chrome reset

## Status
Draft · 2026-04-21

## Outcome (one sentence)
A user opening `worldforge-harness` in either a dark or a light terminal sees the same single-screen flow surface they have today, but rendered through registered `worldforge-dark` / `worldforge-light` themes with a clock, breadcrumb, and provider-status pill in the header — so the harness reads as a polished workspace instead of a hard-coded dark demo.

## Why this milestone
The current TUI in `src/worldforge/harness/tui.py` hard-codes hex literals — `#101512`, `#171f1a`, `#9ea89f` in the `CSS` block (see `tui.py:154-215`), and `#d8c46a`, `#8ec5a3`, `#d3d6cf`, `#3b423e`, `#6f7770` inside Rich `Text(style=...)` and `Panel(border_style=...)` calls scattered through `HeroPane`, `FlowCard`, `TimelinePane`, `InspectorPane`, and `TranscriptPane` (see `tui.py:30, 40-44, 53-91, 116-128, 137-139`). This bakes a dark-terminal assumption into the front face of the project; on a light terminal, foreground tokens collide with the user's background and the harness instantly stops looking like a credible workspace. Roadmap §1 names the harness as "the front door of WorldForge" and demands a 30-second first-impression that reads as polished — and SKILL.md "Why this skill exists" §3 ("Theme drift") calls this exact failure mode out: hard-coded hex breaks light terminals and ships an unwanted opinion about background color.

M0 is the foundation milestone. It does not add features. It retires hex literals in favor of semantic CSS variables (`$accent`, `$success`, `$warning`, `$error`, `$panel`, `$boost`, `$surface`, `$muted` — see roadmap §2.1), registers `worldforge-dark` and `worldforge-light` `Theme` objects on the `App`, and adds the chrome (header clock, breadcrumb, provider-status pill) that every subsequent milestone (M1–M5) builds on. Without M0, every later screen would either re-introduce hex drift or have to be rewritten the day a light terminal user shows up.

## In scope
- Register two Textual `Theme` objects on `TheWorldHarnessApp`: `worldforge-dark` (default) and `worldforge-light`. Both bind the eight semantic tokens listed in roadmap §2.1.
- Replace every hex literal currently in `src/worldforge/harness/tui.py` — both in the `CSS` TCSS block and in the inline `style="..."` / `border_style="..."` arguments inside the Rich renderables — with semantic variables (`$accent`, `$success`, `$warning`, `$error`, `$panel`, `$boost`, `$surface`, `$muted`).
- Add `Header(show_clock=True)` (the clock argument is already present at `tui.py:233`; verify it survives the rewrite).
- Add a custom `Breadcrumb` widget that renders the current location as `worldforge › <flow>` for M0 (single-screen app; later milestones will deepen the trail). The widget lives in `tui.py` and uses semantic tokens only.
- Add a provider status pill widget in the header right region showing `<provider> · <capability>` for the currently selected flow's provider/capability tag (e.g. `mock · predict`). Reads from a new `current_provider: reactive[str]` on the App.
- Add a `Ctrl+T` binding (`show=False`) that switches between the two registered themes via `App.theme = "..."` so the light/dark parity can be exercised by the user and by Pilot tests without restart.
- Snapshot tests for the harness in both themes at the existing pinned terminal size (`130, 42`, matching `tests/test_harness_tui.py:19`).

## Out of scope (explicit)
- New screens. The harness stays a single-screen App for M0; the `HomeScreen` / `WorldsScreen` / `RunInspectorScreen` split is M1's job (roadmap §8 "M1 — Screen architecture").
- Command palette / `Ctrl+P` system commands — those land in M1 (roadmap §8).
- The high-contrast theme (`worldforge-high-contrast`). Roadmap §2.1 explicitly defers it until "the layout stabilises" (i.e. after M1+); M5 picks it up (roadmap §8 "M5 — Polish + showcase").
- The dynamic command provider for worlds / providers / runs — M5.
- Replacing the slideshow `asyncio.sleep` step animation with real worker-driven streaming — M3 ("M3 — Live providers"). M0 keeps the existing flow loop intact; only the colors and chrome change.
- Any change to `src/worldforge/harness/flows.py`, `cli.py`, or `models.py`. The Textual import boundary stays strict (SKILL.md §"Module boundary").
- New runtime dependencies. Textual is already in the `harness` extra (`pyproject.toml:55-57`); `pytest-textual-snapshot` for the snapshot tests is the only addition discussed, and is gated to the dev/harness test environment — see `plan.md` "Dependencies on other milestones" and the open questions below.

## User stories
1. As a researcher opening `worldforge-harness` for the first time on a light-themed terminal, I see a harness whose foreground text, borders, and status pills are legible against my background, so I can read what the project does within 30 seconds without recoloring my terminal.
2. As a researcher who already runs everything in a dark terminal, I see the same harness I had before — same flows, same keystrokes, same layout — but with a header clock, a `worldforge › <flow>` breadcrumb, and a `<provider> · <capability>` status pill in the header right, so I always know which flow is "armed" without scanning the cards.
3. As a contributor extending the harness in M1+, I can add a new screen and write its TCSS using semantic tokens (`$accent`, `$panel`, …) without re-deriving a color palette, so theme drift cannot re-enter through new code.
4. As a maintainer reviewing a harness PR, I can `grep -E '#[0-9a-fA-F]{3,8}' src/worldforge/harness/tui.py` and get zero hits, so the "no hex literals" rule (SKILL.md §"Don't") is mechanically enforceable.
5. As a user toggling between dark and light terminals during a demo, I press `Ctrl+T` and the harness switches `worldforge-dark` ↔ `worldforge-light` in place, so I can show both without restarting.

## Acceptance criteria
- [ ] `grep -E '#[0-9a-fA-F]{3,8}' src/worldforge/harness/tui.py` returns no matches (no hex literal remains anywhere — TCSS block, Rich `style=`, Rich `border_style=`).
- [ ] `TheWorldHarnessApp` registers exactly two themes named `worldforge-dark` and `worldforge-light` via `App.register_theme(...)`, and `App.theme` defaults to `worldforge-dark`.
- [ ] Both themes define values for every semantic token listed in roadmap §2.1: `$accent`, `$success`, `$warning`, `$error`, `$panel`, `$boost`, `$surface`, `$muted`.
- [ ] The header renders `Header(show_clock=True)` and contains, in addition to the title/subtitle, a visible `Breadcrumb` reading `worldforge › <flow short_title>` and a status pill reading `<provider> · <capability>` derived from the selected flow.
- [ ] A `Ctrl+T` binding cycles `App.theme` between `worldforge-dark` and `worldforge-light`; it is declared `show=False` so it does not crowd the footer (roadmap §2.2).
- [ ] All existing footer bindings (`r`, `1`, `2`, `3`, `q`) remain visible in the footer with their existing labels.
- [ ] All existing Pilot tests in `tests/test_harness_tui.py` still pass without modification (the run-flow → assert reactive contract is preserved end-to-end).
- [ ] New Pilot test exercises the `Ctrl+T` theme switch and asserts `app.theme` changes.
- [ ] New snapshot tests cover the home view in both themes at `terminal_size=(130, 42)` (the size already pinned in `tests/test_harness_tui.py:19`).
- [ ] Coverage gate `uv run --extra harness pytest --cov=src/worldforge --cov-report=term-missing --cov-fail-under=90` still passes.
- [ ] `uv run ruff check src tests examples scripts` and `uv run ruff format --check src tests examples scripts` are clean.

## Non-functional requirements
- **Light/dark parity.** Every widget that is legible in `worldforge-dark` must be legible in `worldforge-light`. No widget may rely on a token whose computed value is undefined in one of the two themes.
- **Footer never lies.** Bindings shown in the footer must match the bindings that actually fire. Internal-only bindings (theme cycle) stay `show=False` (SKILL.md §"Bindings on the screen, with `show=True` for the footer").
- **Breadcrumb is load-bearing.** It must update when the selected flow changes; it must never render stale state.
- **Status pill never lies.** When the selected flow uses the `mock` provider, the pill says `mock · <capability>` — not the previous flow's provider. It updates on flow change before the next user interaction.
- **No event-loop blocking.** The theme switch and breadcrumb update happen on the main thread (no worker needed for M0); they must not introduce sync I/O or `time.sleep` (SKILL.md §"Don't").
- **Module boundary preserved.** Textual remains imported only from `src/worldforge/harness/tui.py`. The `Breadcrumb` widget lives in `tui.py`.
- **Snapshot determinism.** Snapshots pin `terminal_size=(130, 42)` and call `await pilot.pause()` before assertion (SKILL.md §"Snapshot tests flake" troubleshooting row).

## Open questions
- **Does `pytest-textual-snapshot` need to be added to the `dev` group, or can it stay an opt-in dev-only install?** The snapshot test approach in roadmap §7 and SKILL.md §"Test with `Pilot` and snapshots" assumes it is available. Adding it touches `pyproject.toml`, which is gated (CLAUDE.md `<gated>`). If approval is not granted, M0's snapshot acceptance criterion downgrades to Pilot-only assertions on `app.theme` and on the presence of the breadcrumb / status-pill widgets, with a follow-up to land snapshots once the dependency is approved.
- **Where does the provider-status pill source its `provider · capability` string from for flows whose `HarnessFlow` does not yet carry an explicit capability tag?** For M0 we read `flow.provider` (already exists, see `tui.py:59`) and derive a capability label per flow id (`leworldmodel → score`, `lerobot → policy`, `diagnostics → diagnostics`). If `HarnessFlow` should grow a `capability: str` field, that is a public-models change and belongs to its own milestone — defer.
- **Does the `Breadcrumb` widget belong in `tui.py` or in a new `src/worldforge/harness/widgets.py`?** The Textual import boundary forces `tui.py` for M0; a `widgets.py` would either need to be Textual-importing (which breaks the boundary) or stay empty until M1+. Default: keep it in `tui.py` and revisit during M1's screen split.
- **Should `worldforge-light` be auto-selected when the terminal reports a light background (Textual exposes this via `App.dark`)?** Roadmap §2.1 only mandates that both themes ship; auto-detect is a UX nicety. Default for M0: ship both, default to `worldforge-dark`, expose `Ctrl+T`. Auto-detect is a candidate for M5.

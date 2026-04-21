# Milestone M0 — Theme + chrome reset · Tasks

Each task is a single PR-sized unit. Order matters: a later task may assume an earlier one has landed in main.

## T1 — Register `worldforge-dark` and `worldforge-light` themes
- Files: `src/worldforge/harness/tui.py`
- Change: Define two `Theme` objects (or `Theme`-equivalent dataclass per Textual 8.x API) covering all eight semantic tokens from roadmap §2.1 (`$accent`, `$success`, `$warning`, `$error`, `$panel`, `$boost`, `$surface`, `$muted`) plus the implicit `background` / `foreground` fields the renderer needs. Register both in `on_mount` via `self.register_theme(...)`. Set `self.theme = "worldforge-dark"` immediately after registration so the default is unchanged from the user's perspective.
- Acceptance: maps to spec.md AC "registers exactly two themes named `worldforge-dark` and `worldforge-light`" and "defaults to `worldforge-dark`".
- Tests: extend `tests/test_harness_tui.py` with `test_themes_registered` — mount, assert both names appear in `app.available_themes` (or whatever the public Textual API exposes for registered themes), assert `app.theme == "worldforge-dark"`.

## T2 — Strip every hex literal from TCSS and Rich style strings
- Files: `src/worldforge/harness/tui.py`
- Change: Rewrite the class-level `CSS` block (currently `tui.py:154-215`) to use only `$panel` / `$surface` / `$muted` / `$boost` / `$accent`. Replace every `style="#..."` / `border_style="#..."` inside `HeroPane`, `FlowCard`, `TimelinePane`, `InspectorPane`, `TranscriptPane` with semantic-token references (e.g. via `self.app.get_css_variables()` resolved at render time, or by switching to `Static` with TCSS class names). Keep widget structure and behavior identical; only colors change.
- Acceptance: maps to spec.md AC `grep -E '#[0-9a-fA-F]{3,8}' src/worldforge/harness/tui.py returns no matches`.
- Tests: existing `test_the_world_harness_app_runs_leworldmodel_flow` / `..._lerobot_flow` / `..._diagnostics_flow` continue to pass unmodified; add a tiny CI-friendly assertion in a unit test that scans the file's text for the `#` color pattern as a safety net.

## T3 — Add `Ctrl+T` theme cycle binding
- Files: `src/worldforge/harness/tui.py`, `tests/test_harness_tui.py`
- Change: Add `("ctrl+t", "toggle_theme", "Theme", show=False)` to `BINDINGS`. Implement `action_toggle_theme(self)` that flips between `worldforge-dark` and `worldforge-light` by setting `self.theme`.
- Acceptance: maps to spec.md AC "`Ctrl+T` binding cycles `App.theme` between `worldforge-dark` and `worldforge-light`; declared `show=False`".
- Tests: new `test_theme_toggle_cycles_between_registered_themes` — mount, assert dark, press `ctrl+t`, assert light, press `ctrl+t`, assert dark.

## T4 — Add `Breadcrumb` widget and mount it in the header region
- Files: `src/worldforge/harness/tui.py`, `tests/test_harness_tui.py`
- Change: Define `class Breadcrumb(Static)` with `path: reactive[tuple[str, ...]] = reactive((), layout=True)` and a `watch_path` that re-renders the joined `worldforge › <segment> › ...` string using `$muted` for the separator and `$surface` for the segments. Promote `selected_flow_id` to a reactive on the App; wire `watch_selected_flow_id` to update the breadcrumb's `path` to `("worldforge", flow.short_title)`. Mount the widget inside (or immediately under) `Header(...)` in `compose()`.
- Acceptance: maps to spec.md AC "header contains a visible `Breadcrumb` reading `worldforge › <flow short_title>`".
- Tests: new `test_breadcrumb_reflects_selected_flow` — mount, query `Breadcrumb`, assert path tuple matches initial flow; press `2`, assert path updates.

## T5 — Add `ProviderStatusPill` widget driven by `current_provider` reactive
- Files: `src/worldforge/harness/tui.py`, `tests/test_harness_tui.py`
- Change: Define `class ProviderStatusPill(Static)` rendering `<provider> · <capability>` styled with `$boost` background and `$surface` foreground. Add `current_provider: reactive[str] = reactive("mock · predict")` on the App with a `watch_current_provider` that re-renders the pill. Add a tiny private `_capability_for_flow(flow_id) -> str` helper returning `"score"` / `"policy"` / `"diagnostics"` for the three current flow ids; document it as M0-temporary (will be replaced when `HarnessFlow` grows a typed capability field — see spec.md "Open questions"). Update `current_provider` in `watch_selected_flow_id` (T4) so flow change updates both breadcrumb and pill.
- Acceptance: maps to spec.md AC "status pill reading `<provider> · <capability>` derived from the selected flow" and NFR "Status pill never lies".
- Tests: new `test_status_pill_reflects_selected_flow_provider` — mount, query `ProviderStatusPill`, assert initial `mock · score`; press `2` (lerobot), assert update.

## T6 — Snapshot tests for both themes (gated)
- Files: `tests/test_harness_tui_snapshots.py` (new), possibly `pyproject.toml` (gated dependency add)
- Change: If `pytest-textual-snapshot` is approved as a dev-group dependency, add it to the dev group and create a new test module that calls `snap_compare(app, terminal_size=(130, 42))` once with `app.theme = "worldforge-dark"` and once with `"worldforge-light"`. Each test calls `await pilot.pause()` before snapshotting (SKILL.md troubleshooting). Commit the resulting SVGs.
- Acceptance: maps to spec.md AC "new snapshot tests cover the home view in both themes at `terminal_size=(130, 42)`".
- Tests: the snapshot tests *are* the deliverable. If the dependency add is rejected, this task downgrades to a no-op and the AC drops to Pilot-only theme assertions (already covered by T3).

## T7 — Verify gates and update agent context
- Files: any docs / CHANGELOG entries that public-behavior changes warrant; `.codex/skills/tui-development/references/roadmap.md` §8 marker.
- Change: Run the local gate sequence from `CLAUDE.md` `<commands>` "Full local gate" — lint, format check, provider docs check, tests, coverage gate (`--extra harness`), package contract. After all merge, update roadmap §8 "M0 — Theme + chrome reset (foundation)" with `done · <date>`. Add a CHANGELOG entry describing the chrome reset under "Unreleased / Harness".
- Acceptance: maps to spec.md AC "Coverage gate ... still passes" and "ruff check / format check are clean", and the Definition of Done below.
- Tests: gate scripts themselves (no new test code in this task).

## Definition of done
- [ ] All tasks merged
- [ ] Pilot + snapshot tests in CI (snapshot tests landed iff T6's dependency add was approved; otherwise filed as a follow-up for M5)
- [ ] Roadmap §8 marked "done · {date}"
- [ ] `grep -E '#[0-9a-fA-F]{3,8}' src/worldforge/harness/tui.py` returns no matches
- [ ] `uv run --extra harness pytest --cov=src/worldforge --cov-report=term-missing --cov-fail-under=90` passes
- [ ] CHANGELOG updated under the "Unreleased" / Harness section

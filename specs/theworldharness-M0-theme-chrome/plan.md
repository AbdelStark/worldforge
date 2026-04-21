# Milestone M0 — Theme + chrome reset · Implementation Plan

## Builds on
- Roadmap §8 "M0 — Theme + chrome reset (foundation)" — `../../.codex/skills/tui-development/references/roadmap.md`
- Roadmap §2 "Design language" (especially §2.1 color tokens, §2.2 typography and chrome) — same file.
- Skill: `../../.codex/skills/tui-development/SKILL.md` (Why this skill exists §3 "Theme drift", SOTA Textual practices, worker contract, Stop-and-ask points).
- Predecessor milestones: none (M0 is the foundation).

## Architecture changes
- `TheWorldHarnessApp` (in `src/worldforge/harness/tui.py`) gains:
  - Two registered `Theme` objects: `worldforge-dark` (default) and `worldforge-light`. Registered in `on_mount` via `self.register_theme(...)`; `self.theme = "worldforge-dark"` set immediately after.
  - A new reactive `current_provider: reactive[str] = reactive("mock · predict")` (string form for M0; M3+ may upgrade to a typed pair). Paired with `watch_current_provider(self, old, new)` that re-renders the status pill.
  - A new internal `Ctrl+T` binding `("ctrl+t", "toggle_theme", "Theme", show=False)` and matching `action_toggle_theme(self)` that flips between the two registered theme names.
- A new `Breadcrumb(Static)` widget defined in the same `tui.py` module. It exposes a `path: reactive[tuple[str, ...]]` and renders `worldforge › <segment>` from the tuple. For M0 the tuple is `("worldforge", flow.short_title)`; M1+ will deepen it.
- A new `ProviderStatusPill(Static)` widget defined in the same `tui.py` module. It reads `provider · capability` from a single string reactive on the App and renders inside the header region.
- Existing `HeroPane`, `FlowCard`, `TimelinePane`, `InspectorPane`, `TranscriptPane` are modified to replace every hex literal in their `Panel(border_style=...)` and `Text(style=...)` calls with semantic-token strings (Textual's CSS variables resolve at render via `$accent`, etc., when used in TCSS; for Rich-side `style=` strings, the values resolve through `App.get_css_variables()` which Textual exposes through theme registration).
- The `CSS` class-level TCSS block in `TheWorldHarnessApp` is rewritten to use `$panel`, `$surface`, `$muted`, `$boost`, `$accent` only — no hex.
- No new files are added. No existing files are deleted. No exports change. The Textual import boundary stays at `tui.py` only (SKILL.md §"Module boundary").

## Module touch list
| Path | Change | Notes |
| --- | --- | --- |
| `src/worldforge/harness/tui.py` | Modified | Register two themes; add `Breadcrumb` and `ProviderStatusPill` widgets; add `current_provider` reactive + `watch_current_provider`; add `Ctrl+T` binding + `action_toggle_theme`; replace every hex literal in TCSS and inline `style=`/`border_style=` with semantic tokens; mount the new widgets in `compose()`. |
| `tests/test_harness_tui.py` | Modified | Add Pilot test for theme cycle (`pilot.press("ctrl+t")` → assert `app.theme`); add Pilot assertion that the breadcrumb and status pill are queryable after mount and after a flow switch. |
| `tests/test_harness_tui_snapshots.py` (new, optional) | Added | Snapshot tests via `pytest-textual-snapshot` for the home view in both themes at `terminal_size=(130, 42)`. Gated on whether `pytest-textual-snapshot` is approved as a dev dep — see "Open questions" in `spec.md`. |
| `src/worldforge/harness/flows.py` | Untouched | Flow models do not change. |
| `src/worldforge/harness/cli.py` | Untouched | CLI entry point does not change. |
| `src/worldforge/harness/models.py` | Untouched | No public model changes. |
| `pyproject.toml` | Possibly modified (gated) | If snapshots land in M0, add `pytest-textual-snapshot` to the dev group. Requires explicit approval (CLAUDE.md `<gated>`). |

## Key technical decisions

### Decision 1: Register `Theme` objects, do not ship raw TCSS color blocks
- **Decision**: Use `App.register_theme(Theme(...))` and toggle via `App.theme = "..."`.
- **Alternatives**: (a) Ship a single TCSS variable block at the App level; rely on Textual's built-in `dark` boolean to flip palettes. (b) Define two TCSS files and swap them at runtime.
- **Rationale**: Registered themes are Textual's first-class abstraction for the dark/light/high-contrast triad (roadmap §2.1, §3). They give `Ctrl+T` a one-line implementation, they survive the M5 high-contrast addition without refactor, and they keep all token definitions in Python next to the App definition (one source of truth). The `dark` boolean approach is being phased out in modern Textual; the dual-TCSS approach duplicates token names.

### Decision 2: Keep widgets in `tui.py`; do not split into `widgets.py` yet
- **Decision**: The new `Breadcrumb` and `ProviderStatusPill` widgets live in `tui.py`.
- **Alternatives**: Create `src/worldforge/harness/widgets.py`.
- **Rationale**: SKILL.md §"Module boundary" makes the Textual import boundary load-bearing for the base package's installability (`httpx`-only profile). Adding a `widgets.py` that imports Textual would either break that boundary or require a second gate. Two small classes do not justify the boundary churn for M0; M1's screen split is the right moment to revisit module organisation.

### Decision 3: Provider status pill is a string for M0, not a typed pair
- **Decision**: `current_provider: reactive[str]` carrying a pre-formatted `"mock · predict"` string.
- **Alternatives**: Introduce `class ProviderHandle(provider: str, capability: str)` and reactive over that.
- **Rationale**: A typed pair belongs in the public flow model (see `models.py`), and SKILL.md §"Stop and ask the user" requires explicit approval before reshaping `HarnessFlow` / `HarnessRun` / `HarnessStep` / `HarnessMetric`. M0 must not block on that. M3 ("Live providers") is the natural moment to promote the string into a typed pair, when real provider events start flowing.

### Decision 4: Replace inline Rich `style="#abc123"` with semantic tokens by routing through `self.get_css_variables()`
- **Decision**: For Rich renderables that today take literal `style="#d8c46a"`, replace with the resolved value of `$accent` etc. read at render time from the active theme.
- **Alternatives**: Move every renderable to a TCSS-styled `Static` with no inline Rich style.
- **Rationale**: A full TCSS rewrite of the Rich tables/panels is M1's scope (the screen split is when those panels become real widgets). For M0 the constraint is only "no hex literals"; resolving tokens at render time satisfies it without rewriting the rendering code.

### Decision 5: `Ctrl+T` is a hidden binding, not a visible one
- **Decision**: `("ctrl+t", "toggle_theme", "Theme", show=False)`.
- **Rationale**: Roadmap §2.2 says "the footer never lies" and "internal bindings stay `show=False`". Theme toggling is a meta-action, not a flow action. M1 will surface it through the `Ctrl+P` palette where it belongs.

## Data flow
- **Reactives**:
  - `selected_flow_id: str` — already exists as a plain attribute (`tui.py:226`); upgrade to `reactive[str]` so changes trigger `watch_selected_flow_id` which updates the breadcrumb path and the `current_provider` string. This change is internal; no public API change.
  - `current_provider: reactive[str] = reactive("mock · predict")` — new. `watch_current_provider(self, old, new)` re-renders the `ProviderStatusPill`.
- **Messages**: None new in M0. The single-screen App still reaches into its own children via `query_one`. Cross-widget message passing arrives in M1 with the screen split.
- **Workers**: None new in M0. The existing `_run_flow` loop is left as-is (it uses `asyncio.sleep`, which is M3's problem — see roadmap §8 "M3 — Live providers"). The worker contract from SKILL.md §"Long-running work uses workers" is honored by *not adding* any new long-running call here; we keep the playback shape we already have, just reskinned.
- **Cancel paths**: Not applicable for M0 (no workers added). M3 wires `Esc` → `self.workers.cancel_group("provider")`.
- **Theme switch**: `action_toggle_theme(self)` runs on the main thread; reads `self.theme`, flips it, returns. Textual handles re-render automatically. No `call_from_thread` needed.

## Theming and CSS
- **Semantic tokens used (all eight from roadmap §2.1)**: `$accent`, `$success`, `$warning`, `$error`, `$panel`, `$boost`, `$surface`, `$muted`.
- **Mapping from current hex usage to tokens** (informational; final values defined inside the registered `Theme` objects):
  - `#d8c46a` (running / selected accent) → `$warning` for the running state, `$accent` for the selected state.
  - `#8ec5a3` (success / ready / provider tag) → `$success`.
  - `#d3d6cf` (default body text) → `$surface`.
  - `#3b423e` (idle border) → `$panel`.
  - `#6f7770` (pending step text) → `$muted`.
  - `#101512` (screen background) → `$surface` (background derives from the theme's `background` field, set in the registered `Theme`).
  - `#171f1a` (header / footer background) → `$panel` for chrome backgrounds.
  - `#e4dfc5` (header text) and `#9ea89f` (footer text) → `$surface` and `$muted` respectively.
- **Light/dark parity check method**:
  1. Snapshot the home view at `terminal_size=(130, 42)` in `worldforge-dark` and `worldforge-light`. Visually diff in PR.
  2. Pilot test that programmatically flips themes and asserts both renders complete without exception.
  3. Manual contrast check: every token used as a foreground must have sufficient contrast against the token used as its background in both themes. Both themes ship through Textual's contrast checks (roadmap §2.1) — relying on Textual's own validators is the simplest enforcement for M0.
- **Hex-literal lint**: a CI-friendly check is `grep -E '#[0-9a-fA-F]{3,8}' src/worldforge/harness/tui.py` returning empty. (Promoting this to a real lint rule is M5 polish; for M0 the human-eye review plus the test gating is sufficient.)

## Testing
- **Pilot tests** (modify `tests/test_harness_tui.py`):
  - `test_theme_toggle_cycles_between_registered_themes`: mount, assert `app.theme == "worldforge-dark"`, press `ctrl+t`, assert `app.theme == "worldforge-light"`, press `ctrl+t` again, assert back to `worldforge-dark`.
  - `test_breadcrumb_reflects_selected_flow`: mount, query `Breadcrumb`, assert path tuple includes `"worldforge"` and the initial flow's `short_title`; press `2` to switch flow, assert breadcrumb path updates.
  - `test_status_pill_reflects_selected_flow_provider`: mount, query `ProviderStatusPill`, assert it renders the initial flow's `provider · capability`; press `2`, assert it updates.
  - Existing `test_the_world_harness_app_runs_*_flow` tests pass unchanged (regression coverage that the chrome reset did not break the playback loop).
- **Snapshot tests** (new file, gated on `pytest-textual-snapshot` approval):
  - `test_home_view_dark_snapshot`: `assert snap_compare(app, terminal_size=(130, 42))` with `app.theme = "worldforge-dark"`.
  - `test_home_view_light_snapshot`: same with `"worldforge-light"`.
  - `await pilot.pause()` before assertion to defeat animation timing flake (SKILL.md troubleshooting row).
- **Coverage gate**: must not drop below 90 percent with `--extra harness` (CLAUDE.md `<commands>` "Coverage gate"). The new widgets and reactive watchers each get at least one Pilot exercise above; that should keep coverage at parity.

## Risks and mitigations
- **Risk**: Resolving Rich `style=` strings against the active theme at render time may behave differently across Textual minor versions.
  - **Mitigation**: Pin the `harness` extra to the existing range (`textual>=8.2,<9` per `pyproject.toml:55-57`); add a Pilot assertion that both themes render a representative panel without raising.
- **Risk**: The status pill says `mock · predict` but a flow's actual provider/capability does not match the M0 string we hard-derive.
  - **Mitigation**: Derive the pill string from the flow's existing `provider` field (`tui.py:59`) plus a small `_capability_for_flow(flow_id)` helper local to `tui.py` that returns `"score"` / `"policy"` / `"diagnostics"` for the three known flows. Document in code that this helper is M0-temporary and will be replaced when `HarnessFlow` grows a typed capability field (deferred per Decision 3).
- **Risk**: Snapshot tests flake across CI runners.
  - **Mitigation**: Pin `terminal_size=(130, 42)`; call `await pilot.pause()` before snapshotting; commit SVGs and review diffs in PRs (SKILL.md §"Test with `Pilot` and snapshots").
- **Risk**: Adding `pytest-textual-snapshot` requires a gated dependency change.
  - **Mitigation**: If approval is not granted before M0 ships, downgrade snapshot acceptance to Pilot-only assertions (see `spec.md` "Open questions") and file a follow-up issue tagged for M5 visual-test landing.
- **Risk**: A semantic token chosen for one purpose in `worldforge-dark` is illegible in `worldforge-light` (e.g. a near-white `$boost`).
  - **Mitigation**: Each theme defines its own value for every token; no token is "shared" across themes. PR review checks visual snapshots in both themes before merge.

## Dependencies on other milestones
- **Required before this can ship**: none. M0 is the foundation.
- **Blocks**: M1 (the screen architecture split inherits the registered themes — every new `Screen` reads the same tokens), M2 (`WorldsScreen` and `WorldEditScreen` rely on `$accent` / `$panel` for focus rings), M3 (`ProvidersScreen` capability-matrix cells use `$success` / `$warning` / `$muted` for `●` / `○` / blank), M4 (Eval and Benchmark verdict colors), M5 (the high-contrast theme variant slots into the same registered-theme machinery).

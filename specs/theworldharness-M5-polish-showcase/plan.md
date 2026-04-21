# Milestone M5 — Polish + showcase · Implementation Plan

## Builds on
- Roadmap §8 "M5 — Polish + showcase" — `.codex/skills/tui-development/references/roadmap.md`
- Roadmap §1 Vision, §2 Design language, §4.1 HomeScreen, §5 Command palette, §7 Testing strategy, §10 Anti-goals, §11 Open questions — same file.
- Skill: `.codex/skills/tui-development/SKILL.md` (snapshot testing, command palette patterns, theme rules, worker contract).
- Persistence skill: `.codex/skills/persistence-state/SKILL.md` (sourcing recent worlds via `WorldForge.list_worlds`, no parallel state).
- Predecessor milestones (must have landed first):
  - M0 — Theme + chrome reset: registers `worldforge-dark` / `worldforge-light`, strips hex literals, adds `Header` clock + `Breadcrumb` + provider status pill. M5 extends the theme registration with a third variant.
  - M1 — Screen architecture: introduces `HomeScreen`, `RunInspectorScreen`, `push_screen`, `?` help overlay, static `Ctrl+P` system commands. M5 layers the *dynamic* command provider on top.
  - M2 — Worlds CRUD: `WorldsScreen`, `WorldEditScreen`, `ConfirmDelete`. M5 reads `WorldForge.list_worlds` for recents and palette items.
  - M3 — Live providers: `ProvidersScreen`, capability matrix, real provider call wired through `@work`, `Esc` cancellation. M5 indexes `PROVIDER_CATALOG` plus injected providers in the palette.
  - M4 — Eval + Benchmark: `EvalScreen`, `BenchmarkScreen`, `RunInspectorScreen`, results pinned to `.worldforge/reports/`. M5 sources recent runs from that directory.

## Architecture changes
- Add `WorldForgeCommandProvider` (new), a subclass of `textual.command.Provider`. Lives next to `TheWorldHarnessApp` in `src/worldforge/harness/tui.py` (or a co-located helper file inside `harness/` that only imports Textual when the extra is present). Indexes three sources — worlds, providers, runs — and yields fuzzy-ranked `Hit`s that dispatch existing M2/M3/M4 messages.
- Add `RecentItems` widget (new) on `HomeScreen`, composed of two `Static` lists (recent worlds, recent runs) with row-level click and key activation. Reads through cached helpers; no direct disk access from the widget.
- Register `worldforge-high-contrast` `Theme` (new) alongside the M0 themes. The variant overrides existing semantic tokens; it does not introduce hex literals in widget CSS.
- Add snapshot test helpers and per-screen × per-size fixtures under `tests/test_harness_snapshots.py` (new). One `pytest.mark.parametrize` over `(screen, size)` keeps the matrix declarative and the SVG paths consistent.
- Add `scripts/regen-harness-screenshot.sh` (new), a small wrapper around `uv run --extra harness worldforge-harness` plus a deterministic state-dir fixture, to regenerate `docs/assets/img/theworldharness-tui-screenshot-1.png`. Tracked so the next refresh is one command.
- Extend the existing `TheWorldHarnessApp.get_system_commands` (M1) to surface the high-contrast theme switch action under a stable label. No replacement of the M1 static commands.

## Module touch list
| Path | Change | Notes |
| --- | --- | --- |
| `src/worldforge/harness/tui.py` | Register `worldforge-high-contrast` theme; register `WorldForgeCommandProvider`; mount `RecentItems` on `HomeScreen`; extend system commands. | Only Textual-importing module touched; preserves §3 boundary. |
| `src/worldforge/harness/` (new helper, optional) | If `WorldForgeCommandProvider` grows beyond `tui.py` length, a co-located file (e.g., `palette.py`) may be added; it must guard its Textual import behind the extra check pattern used in `cli.py`. | Stop-and-ask if a new file is added (SKILL.md "Stop and ask"). |
| `tests/test_harness_snapshots.py` | New parametrised snapshot tests across `(screen, size)`. | Uses `pytest-textual-snapshot`; SVGs land under `tests/snapshots/`. |
| `tests/snapshots/` | New SVG outputs committed; reviewed in PRs. | Pinned terminal sizes, animations disabled. |
| `tests/test_harness_tui.py` | Extend with Pilot tests for palette dynamic items, theme cycle including high-contrast, recent-items activation. | Existing flow tests remain; M5 adds new ones rather than replacing. |
| `tests/fixtures/harness/` (new, if needed) | Deterministic fixture state (worlds, providers, reports) for the snapshot matrix and palette tests. | Tracked, deterministic; no host-specific paths. |
| `README.md` | Update the screenshot at line 30 (file replacement); no copy changes unless the screenshot URL filename changes. | Tool-neutral, maintainer-style. |
| `docs/assets/img/theworldharness-tui-screenshot-1.png` | Regenerated. | Deterministic; reproducible from `scripts/regen-harness-screenshot.sh`. |
| `docs/src/theworldharness.md` | Append a short "Themes" section listing the three variants and the cycle binding; append a one-line note that `Ctrl+P` indexes worlds, providers, and recent runs. | Public behaviour change → doc update. |
| `scripts/regen-harness-screenshot.sh` (new) | Reproducible regen for the README image. | Documented in the spec; tracked. |
| `CHANGELOG.md` | Entry under the next version: high-contrast theme, dynamic command palette, HomeScreen recent items, snapshot matrix, screenshot refresh. | Tool-neutral copy. |
| `.codex/skills/tui-development/references/roadmap.md` | Mark §8 M5 "done · {date}" in the closing PR. | Per roadmap §8 closing convention. |

## Key technical decisions
- **Palette item ranking — fuzzy score with a "recent" boost.** Decision: rank by Textual's built-in fuzzy matcher, with a small additive boost for items in the recent-items cache (worlds touched in the last hour, runs from the last hour). Alternatives: (a) pinned "Recent" section above dynamic items, k9s-style; (b) pure fuzzy with no recency awareness. Rationale: a boost preserves predictability for power users (recent items rise) while keeping the palette one ranked list; pinned sections fragment the list and force two layers of attention.
- **Snapshot image format — SVG via `pytest-textual-snapshot`.** Decision: keep the test format as SVG (the library default), commit them under `tests/snapshots/`. PR diffs render as text for SVG, which is reviewable. Alternatives: PNG outputs (binary, opaque diffs) or terminal capture text (no visual fidelity). README image stays PNG to match the current `README.md` line 30 reference and avoid a Markdown renderer regression.
- **High-contrast as a separate registered theme, not an override module.** Decision: `worldforge-high-contrast` is a third `Theme` registered next to the M0 themes, sharing the same variable names but with higher-contrast values. Alternatives: a runtime override layer or a `:contrast` modifier class. Rationale: matches the M0 registration pattern, lets the theme cycle action treat all three uniformly, and keeps Textual's contrast check applicable to the full theme rather than a partial override.
- **Recent runs source — disk only (`.worldforge/reports/`).** Decision: the recent-runs list reads mtime-sorted JSON files under `.worldforge/reports/` written by M4. Alternatives: layer in-memory runs from the current TUI session on top. Rationale: a single source of truth keeps the palette and the HomeScreen consistent and avoids a "ghost" run that disappears on restart. Persistence skill alignment: WorldForge does not maintain a parallel run cache.
- **Recent worlds source — `WorldForge.list_worlds`, sorted by `last_touched`.** Decision: reuse the persistence API from M2; no parallel cache. Alternatives: scan `.worldforge/worlds/` directly. Rationale: the persistence API is the contract; bypassing it would duplicate state and risk drift (CLAUDE.md priority rule #1).
- **README image regeneration via tracked script.** Decision: commit `scripts/regen-harness-screenshot.sh`. Alternatives: document the steps in the spec body only; require a manual capture each refresh. Rationale: a script is reproducible and PR-reviewable; manual capture rotates with whoever runs it last and erodes the front-door image's honesty.
- **Cache scanner output for the palette.** Decision: a small in-memory cache keyed by source (worlds, providers, reports) with a 500 ms TTL plus invalidation on `WorldSelected` / `ProviderSelected` / `RunCompleted` messages. Alternatives: scan on every keystroke (rejected — disk hit per keystroke); event-only invalidation with no TTL (rejected — palette can lag if a message is missed). Rationale: keeps palette latency under one frame and makes invalidation observable.
- **Coverage at `--extra harness`.** Decision: keep the gated coverage command (`testing-validation` skill) at the existing 90% floor. Alternatives: tighten to 95% in this milestone. Rationale: snapshot tests do not lift line coverage meaningfully; the bar should rise as a separate, scoped change.

## Data flow
- Reactives on `HomeScreen`: `recent_worlds: reactive[tuple[WorldSummary, ...]] = reactive(())`, `recent_runs: reactive[tuple[Path, ...]] = reactive(())`. Recomputed in `on_mount` and on receipt of M2's `WorldSaved`-equivalent and M4's `RunCompleted` messages. Paired with `watch_recent_worlds` / `watch_recent_runs` for redraw.
- Messages reused (no new message types unless a gap is found during implementation):
  - `WorldSelected(world_id)` — M2; dispatched by palette world hits and recent-world rows.
  - `ProviderSelected(provider_id)` — M3; dispatched by palette provider hits.
  - `RunSelected(report_path)` — M4 (or its equivalent on `RunInspectorScreen`); dispatched by palette run hits and recent-run rows. If M4 names this differently, the M5 plan reuses M4's name verbatim — no rename.
- Workers: none new. Palette queries are in-memory (cached scanner output). Recent-items refresh is a synchronous, cheap helper scheduled on `on_mount` and on the invalidating messages; if the report directory grows past a few hundred files, the helper can be promoted to `@work(thread=True, group="recent", exclusive=True)` without API change.
- Persistence: all reads route through `WorldForge.list_worlds` (M2) and through filesystem mtime calls scoped to `.worldforge/reports/` (M4). The TUI does not hand-write JSON, hold its own cache of world or run state, or duplicate any persistence logic.
- Theme switching: extends the M0 theme cycle action; stores the active theme in the standard Textual theme reactive. No new persistence of theme preference in M5 (out of scope; deferrable).

## Theming and CSS
- `worldforge-high-contrast` registers overrides for: `$accent`, `$panel`, `$boost`, `$surface`, `$muted`, `$success`, `$warning`, `$error`. Any new semantic tokens needed for the high-contrast pass (e.g., `$focus-ring` if the M0 themes derive it implicitly) are declared in the registration and consumed in widget CSS through the variable name only.
- Zero hex literals introduced in widget CSS as part of M5. The hex-literal lint (recommended in the risks section) extends to the new theme registration block — colour values may appear there once, by definition.
- Contrast verification: rely on Textual's built-in contrast check during `pytest`; supplement with one manual review at `100×30` (smallest matrix size, highest density) for the high-contrast variant.
- Focus rings, panel borders, and status pills carry through unchanged from M0; the high-contrast theme tightens their colour values, not their CSS rules.

## Testing
- **Pilot interaction tests** (`tests/test_harness_tui.py` extensions):
  - Open palette via `Ctrl+P`, type a partial world name from a tracked fixture, assert the first hit dispatches `WorldSelected` and the harness lands on `WorldEditScreen` with that world preselected.
  - Open palette, type a partial provider id (e.g., `mock`), assert `ProviderSelected` dispatch and `ProvidersScreen` landing.
  - Open palette, type a partial report filename, assert `RunSelected`-equivalent dispatch and `RunInspectorScreen` landing with that run loaded.
  - Cycle themes through `worldforge-dark` → `worldforge-light` → `worldforge-high-contrast` → back to `worldforge-dark`; assert the active theme reactive across the cycle.
  - HomeScreen mount: assert `recent_worlds` and `recent_runs` populate from the fixture and that activating a row dispatches the right message.
  - Empty state: with an empty fixture state-dir, assert HomeScreen "Recent" shows the documented next-action copy from spec.md.
- **Snapshot matrix** (`tests/test_harness_snapshots.py`, new): parametrised over `(screen, size)`:
  - Screens: `HomeScreen`, `WorldsScreen`, `ProvidersScreen`, `EvalScreen`, `BenchmarkScreen`, `RunInspectorScreen`, `DiagnosticsScreen`.
  - Sizes: `(100, 30)`, `(120, 40)`, `(160, 50)`.
  - For each combination: drive Pilot to that screen with a deterministic fixture, `await pilot.pause()`, then `assert snap_compare(app, terminal_size=size)`.
  - SVGs commit under `tests/snapshots/`. PR diffs are reviewed by the snapshot test runner.
- **Lint rule — telemetry fence**: a small `pytest`-collected check (or a tracked `scripts/check_no_egress.py`) that greps `src/worldforge/harness/` for `httpx.post`, `requests.post`, `socket.send`, and similar egress patterns and fails if any appear. Roadmap §10 anti-goal made executable.
- **Lint rule — hex-literal fence**: extend any existing TCSS-grep check (or add one) to reject hex literals in widget CSS. Theme registration files are exempt by path.
- **Coverage**: `uv run --extra harness pytest --cov=src/worldforge --cov-report=term-missing --cov-fail-under=90` must stay green. The snapshot matrix may not raise coverage but must not lower it.
- **Package contract**: `bash scripts/test_package.sh` continues to pass; new files must be picked up by hatch include rules in `pyproject.toml`. If a new tracked path is added (e.g., `tests/snapshots/`), confirm it is excluded from the wheel as appropriate.

## Risks and mitigations
- **Risk: snapshot matrix flake on CI.** Mitigation: pin terminal size for every snapshot, disable animation in test mode, await `pilot.pause()` before the assertion, fix all timing-dependent renders (e.g., a clock in the header) with a frozen value or a masked region in the snapshot.
- **Risk: dynamic palette provider hits disk on every keystroke.** Mitigation: in-memory scanner cache with 500 ms TTL plus message-driven invalidation on `WorldSelected`, `ProviderSelected`, `RunSelected`. Pilot test asserts palette latency stays under one frame at the fixture scale.
- **Risk: README image rotates whenever a contributor regenerates it from a different host.** Mitigation: commit `scripts/regen-harness-screenshot.sh`; document the deterministic fixture state-dir; require the screenshot to be refreshed only when the harness chrome changes (PR template note).
- **Risk: high-contrast theme accidentally reuses dark-theme hex.** Mitigation: hex-literal lint extended to the new theme module; PR review checklist item to confirm only semantic variables are referenced from widget CSS.
- **Risk: telemetry creep — a future contributor adds an "anonymous metrics" toggle.** Mitigation: telemetry-fence lint rule rejecting network-egress patterns under `src/worldforge/harness/`; explicit out-of-scope wording in spec.md and CHANGELOG entry.
- **Risk: agent or tool branding leaks into a screenshot, palette item, or commit message.** Mitigation: CLAUDE.md priority rule #5 is enforced by PR review; the regeneration script uses a tracked deterministic state with neutral world / provider names.
- **Risk: snapshot matrix grows unmaintainable as new screens land.** Mitigation: parametrise over `(screen, size)` so adding a screen is one row; document the matrix in `docs/src/theworldharness.md` so the inventory stays visible.
- **Risk: M5 lands before one of M0–M4.** Mitigation: PR description explicitly lists the M0–M4 dependencies; CI snapshot matrix fails loudly if any expected screen does not exist; do not split M5 across earlier milestones.
- **Risk: dynamic command provider couples to internals of `WorldForge` or `PROVIDER_CATALOG`.** Mitigation: read only through public surfaces (`WorldForge.list_worlds`, `PROVIDER_CATALOG` iteration, `Path.iterdir` on `.worldforge/reports/`). No private attribute access.

## Dependencies on other milestones
- **Required before M5 can ship**: M0, M1, M2, M3, M4. M5 is explicitly the polish pass after the functional set is complete; landing it earlier would polish surfaces that do not yet exist.
- **Specifically depends on**:
  - M0 theme registration scaffold (third theme slots into the same registration site).
  - M1 `HomeScreen` and `Ctrl+P` static commands (recent items mount on the former; dynamic provider extends the latter).
  - M2 `WorldsScreen` and `WorldForge.list_worlds` access pattern (palette + recents read worlds).
  - M3 `ProvidersScreen` and `PROVIDER_CATALOG` plus injected-provider handling (palette indexes providers).
  - M4 `RunInspectorScreen` and `.worldforge/reports/` JSON layout (palette + recents read runs).
- **Blocks**: none directly. M5 is the final milestone in the current roadmap. Future work from roadmap §11 — embedded 3-D scene preview, `worldforge harness record` mode — depends on this polish baseline being landed first so that visual regressions in those features are catchable against a stable matrix.

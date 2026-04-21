# Milestone M5 — Polish + showcase · Tasks

Each task is a single PR-sized unit. Order matters: a later task may assume an earlier one has landed in main.

## T1 — Register `worldforge-high-contrast` theme
- Files: `src/worldforge/harness/tui.py`; `tests/test_harness_tui.py`; `docs/src/theworldharness.md`.
- Change: register a third `Theme` named `worldforge-high-contrast` next to the M0 themes. Override `$accent`, `$panel`, `$boost`, `$surface`, `$muted`, `$success`, `$warning`, `$error` with high-contrast values declared inside the theme registration only. Extend the existing M1 theme cycle action to iterate dark → light → high-contrast → dark. Document the third theme in `docs/src/theworldharness.md`.
- Acceptance: maps to spec.md acceptance "Three themes registered… each passes Textual's contrast check" and "No new hex literals introduced in `worldforge-high-contrast` … all colour values are CSS variables".
- Tests: extend `tests/test_harness_tui.py` with a Pilot test that cycles themes through all three and asserts the active theme reactive at each step; rely on Textual's built-in contrast check during pytest run.

## T2 — Hex-literal lint and telemetry-fence guards
- Files: `scripts/check_no_hex_in_widget_css.py` (new) or extend an existing tracked check; `scripts/check_no_egress_in_harness.py` (new); CI wiring in `.github/workflows/*.yml` *only if a gated workflow change is approved* — otherwise wire as a `pytest`-collected test.
- Change: add executable guards that (a) reject hex literals in widget CSS under `src/worldforge/harness/` (theme registration files exempt by path), (b) reject `httpx.post`, `requests.post`, `socket.send`, and similar egress patterns under `src/worldforge/harness/`. Roadmap §10 anti-goals made executable.
- Acceptance: maps to spec.md acceptance "No `httpx.post` … is introduced anywhere under `src/worldforge/harness/`" and the non-functional "lint rule rejecting `httpx.post`/`requests.post` from harness/".
- Tests: each guard ships with a pair of fixtures (one passing, one failing) under `tests/fixtures/lint/` so the guard itself is tested. CI runs the guards as part of `uv run pytest`.
- Note: if the guards must run as a workflow rather than a pytest collection, that is a `<gated>` change per CLAUDE.md and requires explicit approval.

## T3 — `WorldForgeCommandProvider` (dynamic command palette)
- Files: `src/worldforge/harness/tui.py` (or a co-located `palette.py` if size warrants — stop-and-ask per SKILL.md before adding a new file); `tests/test_harness_tui.py`; `tests/fixtures/harness/` (new fixture state-dir).
- Change: implement a `textual.command.Provider` subclass that yields fuzzy-ranked hits for worlds (from `WorldForge.list_worlds`), providers (from `PROVIDER_CATALOG` plus injected providers), and recent runs (from `.worldforge/reports/`). Selecting a hit dispatches the existing M2/M3/M4 messages and lands on the right screen with the item preselected. Cache scanner output with a 500 ms TTL; invalidate on `WorldSelected`, `ProviderSelected`, `RunSelected`.
- Acceptance: maps to spec.md acceptance "A `WorldForgeCommandProvider` subclass … is registered", "Selecting a palette item dispatches the corresponding existing message", and "Palette query latency stays under 1 frame".
- Tests: Pilot tests for each of the three sources (world / provider / run): open palette via `Ctrl+P`, type a fragment from the fixture, assert the first hit dispatches the expected message and the harness lands on the correct screen with the item preselected. Latency assertion uses a fixture sized to the spec target.

## T4 — HomeScreen "Recent" section and `RecentItems` widget
- Files: `src/worldforge/harness/tui.py`; `tests/test_harness_tui.py`; `tests/fixtures/harness/`.
- Change: add a `RecentItems` widget composed of two `Static` lists (recent worlds, recent runs) on `HomeScreen`. Sources: `WorldForge.list_worlds` sorted by `last_touched` (top 5), `.worldforge/reports/` JSON files sorted by mtime (top 5). Reactives `recent_worlds` and `recent_runs` recompute on `on_mount` and on the invalidating messages. Empty states follow roadmap §2.4.
- Acceptance: maps to spec.md acceptance "HomeScreen 'Recent' section renders two sub-lists" and the non-functional "Empty states … follow roadmap §2.4".
- Tests: Pilot tests for (a) populated case — assert both lists render five rows from the fixture and a row activation dispatches the right message, (b) empty case — assert the documented empty-state copy renders.

## T5 — Snapshot test matrix at `100×30`, `120×40`, `160×50`
- Files: `tests/test_harness_snapshots.py` (new); `tests/snapshots/` (new directory of committed SVGs); `tests/fixtures/harness/` extension if needed; possibly `pyproject.toml` if `pytest-textual-snapshot` is not already a dev dependency (stop-and-ask if a dependency change is needed — CLAUDE.md `<gated>`).
- Change: add a parametrised snapshot test over `(screen, size)` covering `HomeScreen`, `WorldsScreen`, `ProvidersScreen`, `EvalScreen`, `BenchmarkScreen`, `RunInspectorScreen`, `DiagnosticsScreen` at `(100, 30)`, `(120, 40)`, `(160, 50)`. Pin terminal size, disable animations in test mode, await `pilot.pause()` before assertion.
- Acceptance: maps to spec.md acceptance "Snapshot matrix runs in CI at `100×30`, `120×40`, `160×50` for HomeScreen, WorldsScreen, ProvidersScreen, EvalScreen, BenchmarkScreen, RunInspectorScreen" (DiagnosticsScreen also covered for completeness).
- Tests: the snapshot tests *are* the artefact; CI executes them under `uv run --extra harness pytest`. PR diffs of `tests/snapshots/*.svg` are reviewed by maintainers.

## T6 — README screenshot regeneration script
- Files: `scripts/regen-harness-screenshot.sh` (new); `docs/assets/img/theworldharness-tui-screenshot-1.png` (regenerated); `README.md` (only if the image filename changes — otherwise unchanged).
- Change: add a tracked, deterministic regeneration script that launches `uv run --extra harness worldforge-harness` against a fixed fixture state-dir, navigates to a chosen showcase screen, and produces the PNG referenced from `README.md` line 30. Replace the existing PNG with the new capture.
- Acceptance: maps to spec.md acceptance "README screenshot is regenerated from a deterministic harness state. The exact command (or script) used to regenerate it is recorded".
- Tests: smoke-only — running the script under CI is out of scope (binary capture in CI is brittle). The script's deterministic behaviour is verifiable manually; PR review confirms the image matches what `worldforge-harness` produces.

## T7 — Polish pass on empty states and focus rings
- Files: `src/worldforge/harness/tui.py`; possibly TCSS adjustments in the same file; `tests/test_harness_snapshots.py` regenerated SVGs as needed.
- Change: walk every snapshot from T5 and fix any empty-state regression (missing centred-Static next-action copy per roadmap §2.4) and any focus-ring inconsistency (roadmap §2.2). Tighten padding or border on screens that read poorly at `100×30`. No functional changes outside polish.
- Acceptance: maps to the spec.md user story "I can capture each as a screenshot … without manual cropping or contrast tweaks" and the non-functional "Empty states … follow roadmap §2.4".
- Tests: snapshot diffs from T5 reviewed and committed. Pilot tests for empty states extended where copy changed.

## T8 — Doc and changelog updates
- Files: `docs/src/theworldharness.md`; `CHANGELOG.md`; `.codex/skills/tui-development/references/roadmap.md`.
- Change: append a "Themes" subsection (three variants and the cycle binding) and a one-line note that `Ctrl+P` indexes worlds, providers, and recent runs to the harness doc. Add a CHANGELOG entry under the next release listing high-contrast theme, dynamic command palette, HomeScreen recent items, snapshot matrix, screenshot refresh — tool-neutral copy. Mark roadmap §8 M5 "done · {date}".
- Acceptance: maps to spec.md user story "I see a current screenshot of the harness that matches what I get when I run `uv run --extra harness worldforge-harness`" (the doc points users at the matching state) and to the SKILL.md procedure step 7 ("Update `references/roadmap.md` if the change resolves a milestone").
- Tests: docs check (`uv run python scripts/generate_provider_docs.py --check`) must stay green; coverage gate at `--extra harness` stays at or above 90%.

## Definition of done
- [ ] All tasks T1–T8 merged to main on independent PRs (or grouped where dependencies are tight, e.g., T3 + T4 share a fixture).
- [ ] `uv run --extra harness pytest` passes locally and in CI, including the new snapshot matrix.
- [ ] `uv run --extra harness pytest --cov=src/worldforge --cov-report=term-missing --cov-fail-under=90` stays green.
- [ ] `uv run ruff check src tests examples scripts` and `uv run ruff format --check src tests examples scripts` are clean.
- [ ] `bash scripts/test_package.sh` passes (no new file path missed by hatch include rules).
- [ ] `tests/snapshots/` SVGs are reviewable in PR diffs.
- [ ] `README.md` line 30 image renders the regenerated screenshot.
- [ ] `docs/src/theworldharness.md` documents the three themes and the dynamic palette.
- [ ] `CHANGELOG.md` carries a tool-neutral entry for the milestone.
- [ ] `.codex/skills/tui-development/references/roadmap.md` §8 M5 is marked "done · {date}".
- [ ] No new runtime dependency added to the `harness` extra; no Textual import outside `src/worldforge/harness/tui.py` (or a co-located helper that itself only imports Textual when the extra is present).
- [ ] Telemetry-fence and hex-literal lint guards from T2 are active in CI.

# Milestone M5 — Polish + showcase

## Status
Draft · 2026-04-21

## Outcome (one sentence)
A reviewer, talk-giver, or first-time contributor can launch the harness, immediately recognise it as the credible front face of WorldForge, jump to any world, provider, or recent run via `Ctrl+P`, and capture a publication-quality screenshot of any main screen at standard terminal sizes without post-processing.

## Why this milestone
Roadmap §1 frames TheWorldHarness as the **front door of WorldForge** — a researcher should understand the project in 30 seconds, do something real in two minutes, and leave with the integration pattern in their head. After M0 lands the theme and chrome, M1 routes navigation, M2 wires worlds, M3 streams provider events, and M4 closes the eval and benchmark loop, every functional surface exists — but the surface is not yet *showcase-quality*. M5 is the polish pass that takes a working harness and makes it worth screenshotting for talks, PRs, and the README front-door image referenced from `README.md` line 30.

The milestone tightens three loose ends that only become visible once the functional set is complete: (1) the design language from roadmap §2 is not fully landed until a high-contrast variant exists alongside `worldforge-dark` / `worldforge-light`; (2) the command palette from roadmap §5 is not actually a discovery surface until it indexes worlds, providers, and runs dynamically; (3) the visual contract has no regression guard until a snapshot matrix at the terminal sizes a screenshotter actually uses (`100×30`, `120×40`, `160×50`) is in CI. All three are scoped here so that future work — the open questions in roadmap §11 — has a stable, testable baseline to build on.

## In scope
- High-contrast theme variant (`worldforge-high-contrast`) registered alongside `worldforge-dark` and `worldforge-light` from M0; cyclable through the existing theme switch action; passes Textual's contrast checks.
- Dynamic command palette `Provider` subclass (`textual.command.Provider`) yielding fuzzy-searchable items for: every world from `WorldForge.list_worlds`, every provider from `PROVIDER_CATALOG` plus injected providers, recent run JSON files under `.worldforge/reports/`. Selecting an item jumps to the right screen with the item pre-selected.
- HomeScreen "Recent" section (roadmap §4.1): last 5 worlds touched (sorted by `last_touched` from the persistence API), last 5 runs (sorted by mtime under `.worldforge/reports/`).
- Snapshot test matrix (roadmap §7): every main screen — `HomeScreen`, `WorldsScreen`, `ProvidersScreen`, `EvalScreen`, `BenchmarkScreen`, `RunInspectorScreen`, `DiagnosticsScreen` — captured at `100×30`, `120×40`, `160×50`. SVGs committed; `pytest-textual-snapshot` reviews diffs in PRs.
- README screenshot refresh: regenerate `docs/assets/img/theworldharness-tui-screenshot-1.png` (referenced from `README.md` line 30) from a deterministic, reproducible harness state.
- Polish pass on empty states (roadmap §2.4) and focus rings (roadmap §2.2) wherever the snapshot matrix surfaces a gap.

## Out of scope (explicit)
- Bespoke widget framework on top of Textual — roadmap §10 anti-goal.
- Telemetry or any phone-home behaviour, including opt-in usage metrics — roadmap §10 anti-goal and CLAUDE.md `<forbidden>`.
- Embedded 3-D scene preview — roadmap §11 open question, decision deferred to a follow-up milestone.
- `worldforge harness record` mode capturing a Pilot trace plus final SVG for PR descriptions — roadmap §11 open question, considered post-M5.
- Auto-publishing benchmark reports to the docs site — roadmap §11; the existing `.worldforge/reports/` JSON plus copyable Markdown excerpt remains the contract.
- Adding new runtime dependencies to the `harness` extra beyond Textual — roadmap §10 anti-goal; see SKILL.md "stop and ask".
- Functional changes to worlds, providers, eval, or benchmark surfaces — those are owned by M2–M4 and are *consumed* here, not modified.
- Agent or tool branding in any user-visible copy or screenshot — CLAUDE.md `<priority_rules>` #5.

## User stories
1. As a talk-giver preparing slides, I run `worldforge-harness`, navigate through HomeScreen → WorldsScreen → RunInspectorScreen at `120×40`, and capture each as a screenshot, so that I can paste them into a deck without manual cropping or contrast tweaks.
2. As a researcher with multiple saved worlds, I press `Ctrl+P`, type a fragment of a world name (e.g., `lab`), and see the matching world surfaced in the palette, so that I jump directly to its `WorldEditScreen` without scrolling a list.
3. As a contributor reviewing a benchmark run from yesterday, I press `Ctrl+P`, type part of the report filename, and select it, so that the harness opens that run in `RunInspectorScreen` without me having to remember the path under `.worldforge/reports/`.
4. As a contributor with reduced colour vision or a high-contrast terminal preference, I cycle to `worldforge-high-contrast`, so that every focus ring, panel border, and status pill has an explicit pass-contrast colour, rather than relying on the default dark theme's hue separation.
5. As a maintainer reviewing a PR that touches `harness/tui.py`, I see the snapshot diff for the affected screens at all three terminal sizes in the PR check, so that any unintended visual regression — focus ring shift, padding drift, theme variable rename — is caught before merge.
6. As a first-time visitor opening `README.md`, I see a current screenshot of the harness that matches what I get when I run `uv run --extra harness worldforge-harness`, so that the front-door image is honest about the state of the tool.

## Acceptance criteria
- [ ] Three themes registered: `worldforge-dark`, `worldforge-light`, `worldforge-high-contrast`. Each passes Textual's built-in contrast check. Theme cycle action (existing in M0) iterates through all three.
- [ ] No new hex literals introduced in `worldforge-high-contrast`; all colour values are CSS variables (`$accent`, `$panel`, `$boost`, `$surface`, `$muted`, `$success`, `$warning`, `$error`, plus any new semantic tokens declared in the theme registration).
- [ ] A `WorldForgeCommandProvider` subclass of `textual.command.Provider` is registered on `TheWorldHarnessApp`. Fuzzy queries return ranked items for worlds (sourced from `WorldForge.list_worlds`), providers (sourced from `PROVIDER_CATALOG` plus injected providers), and recent runs (sourced from `.worldforge/reports/` JSON files).
- [ ] Selecting a palette item dispatches the corresponding existing message (`WorldSelected`, `ProviderSelected`, `RunCompleted`-equivalent for runs) and the harness lands on the correct screen with that item pre-selected.
- [ ] Palette query latency stays under 1 frame (16 ms) at 100 worlds + 50 providers + 50 reports on the test fixture; cached scanner output is invalidated on the relevant message events.
- [ ] HomeScreen "Recent" section renders two sub-lists: last 5 worlds (by `last_touched` from the persistence API) and last 5 runs (by mtime under `.worldforge/reports/`). Each row maps to a single keystroke or click that opens the item.
- [ ] Snapshot matrix runs in CI at `100×30`, `120×40`, `160×50` for `HomeScreen`, `WorldsScreen`, `ProvidersScreen`, `EvalScreen`, `BenchmarkScreen`, `RunInspectorScreen`, `DiagnosticsScreen`. Snapshots are committed under `tests/snapshots/`; PR diffs are reviewable.
- [ ] README screenshot is regenerated from a deterministic harness state. The exact command (or script) used to regenerate it is recorded in the spec or in a tracked script under `scripts/` so the next refresh is reproducible.
- [ ] No new runtime dependency added to the `harness` extra in `pyproject.toml`. Coverage gate at `--extra harness` stays at or above 90%.
- [ ] No `httpx.post`, `requests.post`, socket write, or other network egress is introduced anywhere under `src/worldforge/harness/` for telemetry or analytics purposes.

## Non-functional requirements
- Every action exposed by M5 (palette dynamic items, theme cycle, recent-item activation) is reachable from `Ctrl+P` and from a discoverable footer or screen binding — auditable via a Pilot test that walks the binding map.
- No looping spinners, decorative fades, or animations on idle panels — roadmap §2.3.
- Empty states for the new HomeScreen "Recent" section follow roadmap §2.4 (centred `Static`, tells the user the next action: e.g., "No recent worlds — press [b]n[/] to create one").
- Theme contrast: each of the three themes passes Textual's contrast check; the high-contrast variant passes a stricter manual review at `100×30` (smallest matrix size) where row density is highest.
- Snapshot tests are deterministic: terminal size pinned, animations disabled in test mode (`TheWorldHarnessApp` sets `ANIMATIONS = False` or equivalent under `app.run_test()`), `pilot.pause()` awaited before assertion. No flakes tolerated.
- README screenshot is generated from the harness running against a tracked, deterministic state — no live provider responses, no host-specific paths visible.
- All user-visible copy is maintainer-style and tool-neutral; no agent or tool branding anywhere in the screenshot, palette item formatting, or commit/PR text — CLAUDE.md `<priority_rules>` #5.
- The Textual import boundary (roadmap §3, SKILL.md) is preserved: M5 introduces no Textual import outside `src/worldforge/harness/tui.py`. The command provider and any new helper classes stay co-located with the App or in a new file under `harness/` that itself only imports Textual when the extra is present.

## Open questions
- Should a palette "recent" section precede dynamic fuzzy-matched items unconditionally (k9s-style pinned recents), or be interleaved by fuzzy score? Trade-off: pinned recents are predictable but push fresh matches down; interleaved is discoverable but unpredictable across sessions.
- Should `worldforge-high-contrast` be auto-selected by detecting terminal settings (e.g., `NO_COLOR`, accessibility env vars) on first launch, or always require explicit opt-in via the theme cycle? Default position: explicit opt-in, to keep the first-launch experience predictable; auto-detect can land in a follow-up if requested.
- Should the README image be committed as a terminal-rendered SVG or a PNG capture? SVGs diff cleanly in PRs and scale to any width, but some Markdown renderers (older GitHub mobile clients, some embedded viewers) handle SVG inconsistently. Default position: keep PNG (matches current `README.md` line 30) but commit the regeneration script so refreshes are one command.
- Should the snapshot matrix include a fourth size — `80×24`, the historical default — for graceful-degradation evidence? Roadmap §8 calls out only the three larger sizes; including `80×24` would surface layout overflow, but may also force layout compromises that hurt the showcase sizes.
- Should the recent-runs source extend beyond `.worldforge/reports/` to include in-memory runs from the current TUI session that have not been pinned to disk? Default position: disk-only, to keep the source of truth single and observable.

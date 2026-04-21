# TheWorldHarness — Roadmap and Design Spec

> Living spec. Updated on every change to the harness's user-visible
> surface. Anyone proposing a TUI feature reads this first; anyone
> shipping a TUI feature updates the relevant section before merging.

## 1. Vision

TheWorldHarness is the **front door of WorldForge**. The first time a
researcher, robotics engineer, or world-model practitioner runs
`worldforge-harness`, they should:

1. **Understand what WorldForge is** within 30 seconds — without reading
   the README.
2. **Do something real** within two minutes — create a world, run a
   provider, watch live events stream in, see a verdict.
3. **Leave with the integration pattern in their head** — the harness is
   the canonical, copyable example of how to use WorldForge. Whatever
   the harness does, library callers should be able to reproduce in
   ~20 lines of Python.

The mental model is **"Claude Code, for world models"**: a keyboard-first,
discoverable, polished workspace where every action is one keystroke or
one `Ctrl+P` away, and every long-running operation streams progress
honestly.

What it explicitly is **not**:

- a slideshow of pre-baked transcripts (where it is today),
- a replacement for the `worldforge` CLI (CLI is for scripting; the TUI
  is for exploration and showcase),
- a robot teleop console (that's a separate concern; the harness can
  *visualise* a policy stream but not pilot hardware).

## 2. Design language

A TUI that feels premium reads as a *grid of bordered panels with a
clear focus ring, a status footer that never lies, and a breadcrumb that
tells you where you are*. Concretely:

### 2.1 Color system

All colors come from semantic CSS variables registered on a single
`Theme` object. **Zero hex literals in widget CSS.**

| Token | Use |
| --- | --- |
| `$accent` | Active focus ring, primary action highlight |
| `$success` | OK status, completed steps, healthy provider |
| `$warning` | In-progress, retry, scaffold-not-yet-real |
| `$error` | Provider error, validation failure, capability mismatch |
| `$panel` | Idle border |
| `$boost` | Hover / secondary accent |
| `$surface` | Default text |
| `$muted` | Secondary text, hints |

Two themes ship initially: `worldforge-dark` (default) and
`worldforge-light`. Both pass through Textual's contrast checks. A
`worldforge-high-contrast` variant follows once the layout stabilises.

### 2.2 Typography and chrome

- One border style across the app (`round`). Don't mix `heavy` /
  `double` / `ascii`.
- Hierarchy comes from **borders, padding, and `Rule()`** — never blank
  lines. Active pane gets `border: round $accent`; idle panes get
  `border: round $panel`.
- Header bar: `Header(show_clock=True)` + a custom `Breadcrumb` widget
  reading `worldforge › worlds › lab-42 › predict`. The breadcrumb is
  load-bearing — it tells the user where they are without them having to
  remember screen names.
- Footer: stock `Footer` listing only screen-local bindings (`show=True`).
  Internal bindings stay `show=False` to keep the footer scannable.
- Status pill in the header right shows the current provider + capability
  (`mock · predict`, `cosmos · generate`, `leworldmodel · score`) so the
  user always knows what's "armed".

### 2.3 Motion

Animation is communicative, not decorative. Allowed uses:

- Toast slide-in on success / error (`animate("offset", ...)` over 200 ms).
- Skeleton fade-in on screens that need data fetched.
- Focus-ring transition when moving between panes.

Disallowed: looping spinners on idle panels, decorative fades on every
state change, anything that makes the UI feel "busy" when it isn't.

### 2.4 Empty states

Every list / table / log starts with a centred `Static` that *tells the
user the next action*:

- Worlds screen, no worlds: `"No worlds yet — press [b]n[/] to create one"`.
- Provider screen, none registered: `"No providers registered — set the env vars in .env.example or run with --provider mock"`.
- Run inspector, no run yet: `"No run captured — pick a flow and press [b]r[/]"`.

Empty states are the cheapest UX win in the entire app. Treat them as
required.

## 3. Architecture (target)

```
TheWorldHarnessApp(App)
├── theme: worldforge-dark | worldforge-light | high-contrast
├── BINDINGS: ?, q, ctrl+p, ctrl+t (theme switch), esc (cancel work)
├── system commands: every screen action is exposed via Ctrl+P
│
├── HomeScreen           -- 30-second intro + jump targets
├── WorldsScreen         -- DataTable of worlds + side detail
├── WorldEditScreen      -- form-style editor for a single world
├── ProvidersScreen      -- catalog view + capability matrix
├── EvalScreen           -- pick suite × provider, run, see verdict
├── BenchmarkScreen      -- pick provider × iters, run, see report
├── DiagnosticsScreen    -- doctor output, env, registered providers
├── RunInspectorScreen   -- last run's transcript, metrics, events
└── ModalScreens         -- ConfirmDelete[bool], NewWorld[WorldSpec], etc.
```

### Data flow

- **Reactives** hold per-screen state: `selected_world: reactive[str |
  None]`, `current_provider: reactive[str]`, `last_run: reactive[HarnessRun
  | None]` — paired with `watch_<name>` for redraws.
- **Messages** for cross-widget signals: `WorldSelected(world_id)`,
  `ProviderEventReceived(event)`, `RunCompleted(run_id)`. Children post,
  screens handle.
- **Workers** for every call into WorldForge: `@work(thread=True,
  group="provider", exclusive=True)`. `Esc` calls
  `self.workers.cancel_group("provider")`.
- **Persistence** goes through `WorldForge(state_dir=...)`; the TUI never
  hand-writes JSON. Editing flows hit `save_world` / `import_world` and
  let the validators raise — the `WorldStateError` becomes a toast.

### Module boundary (load-bearing)

Textual may only be imported from `src/worldforge/harness/tui.py`.
`flows.py`, `cli.py`, `models.py` stay Textual-free so the base package
keeps installing on `httpx`-only profiles. Any helper that *does* need
Textual lives next to `tui.py` or inside it.

## 4. Screen inventory (target)

### 4.1 HomeScreen

- 30-second intro pane: "WorldForge is X. Press `Ctrl+P` for everything."
- Three big jump cards: **Create a world**, **Run a provider**, **Run an
  eval**. Each card maps to a binding (`n`, `p`, `e`).
- "Recent" list: last 5 worlds touched, last 5 runs.
- Always reachable via `g h`.

### 4.2 WorldsScreen

- Left: `DataTable(zebra_stripes=True, cursor_type="row")` of worlds
  (id, name, provider, step, last touched).
- Right: detail pane showing scene objects, current provider, history
  count, `state_dir` path.
- Bindings: `n` new, `e` edit, `d` delete (modal confirm), `f` fork,
  `enter` open in WorldEditScreen, `/` filter.
- Empty state: per §2.4.

### 4.3 WorldEditScreen

- Form-style: name, provider select, scene-object list with add / move /
  remove, snapshot preview pane on the right.
- `Ctrl+S` saves through `WorldForge.save_world`; validation errors
  raise `WorldStateError` → toast.
- Live "predict next state" preview when an action is staged.

### 4.4 ProvidersScreen

- Capability matrix: rows = providers (from `PROVIDER_CATALOG` + injected
  ones), columns = `predict | generate | reason | embed | plan |
  transfer | score | policy`. Cells: `●` real, `○` scaffold, ` ` not
  advertised.
- Hover / select a row → right pane shows `health()` output, env-var
  requirements, last call latency / retry count.
- Bindings: `r` register injected provider (modal), `enter` set as
  current.

### 4.5 EvalScreen

- Pick a suite × a provider that advertises the suite's capability.
  Capability mismatch is a hard error toast that points the user at the
  capability matrix.
- Run is a worker; events stream into a `RichLog` below.
- Verdict pane: pass/fail, per-step metrics, JSON export button.

### 4.6 BenchmarkScreen

- Pick provider × iterations × format. Live `ProgressBar` with median /
  p95 latency rolling.
- Output formats: Markdown / JSON / CSV — switching reflows the preview
  pane in place.
- "Save report" pins the JSON to `.worldforge/reports/` and opens a
  toast with the path so any cited number stays preserved.

### 4.7 DiagnosticsScreen

- Wrapper around `worldforge doctor` output, but live: env vars (sanitised
  names only), registered providers, optional-runtime detection
  (LeWorldModel / GR00T / LeRobot), Python + Textual version, state-dir
  path and free space.
- Each row has a one-key remediation tip ("missing `COSMOS_BASE_URL` →
  set in `.env`").

### 4.8 RunInspectorScreen

- Last (or selected) `HarnessRun`: timeline (steps with status), metrics
  table, transcript, raw events `RichLog`, JSON export.
- "Replay" re-runs the same flow with the same inputs.

### 4.9 Modal screens

- `NewWorld[WorldSpec]`, `EditObject[SceneObject]`,
  `ConfirmDelete[bool]`, `RegisterProvider[ProviderHandle]`,
  `SetTheme[str]`, `Help[None]` (key map overlay on `?`).

## 5. Command palette (the discovery surface)

Every action must be reachable from `Ctrl+P`. Two layers:

1. **Static system commands** via `App.get_system_commands` — the screen
   bindings, theme switch, quit, help.
2. **Dynamic command provider** — a `textual.command.Provider` that
   yields fuzzy-searchable items for: every world, every provider,
   recent runs, eval suites, benchmark presets. Selecting an item jumps
   to the right screen with that item pre-selected.

If a feature exists but isn't in the palette, it doesn't exist for new
users.

## 6. Long-running work — the worker contract

Every call that hits the network, the disk for a large file, a planner,
or a provider runs on a worker. The contract:

- `@work(thread=True, group="<group>", exclusive=True, name="<readable>")`.
- The screen owns the worker; it's cancelled on screen pop and on `Esc`.
- Events stream via `app.call_from_thread(log.write, ...)`. Never mutate
  widgets directly from a thread worker.
- Progress is honest: indeterminate `ProgressBar(total=None)` until a
  total is known, then determinate.
- Cancellation is observable: a "Cancelled" status, not a silent drop.

## 7. Testing strategy

- **Unit**: `flows.py`, `cli.py`, `models.py` — no Textual.
- **Pilot interaction tests**: `async with app.run_test() as pilot:` →
  drive `pilot.press(...)`, `pilot.click(...)`, then assert reactives,
  DOM state, posted messages.
- **Snapshot tests** via `pytest-textual-snapshot`:
  `assert snap_compare(app, press=[...], terminal_size=(120, 40))`.
  Commit SVGs; review diffs in PRs. Pin terminal size; otherwise
  snapshots flake on different CIs.
- **Coverage**: `--extra harness` is mandatory in the gated coverage
  command (see `testing-validation/references/release-gate.md`).

## 8. Milestones

Each milestone follows the spec-first workflow: a `spec.md` (WHAT and
WHY) + `plan.md` (HOW) + `tasks.md` (ordered, PR-sized units) lands
under `specs/theworldharness-M{N}-{slug}/` *before* implementation
starts. Implementation PRs reference the relevant task in `tasks.md`.
Each milestone ends with a runnable harness, a Pilot test for the new
flow, snapshot tests for the new screens, and a roadmap update marking
the milestone "done" with the date.

| Milestone | Spec | Plan | Tasks | Implementation status |
| --- | --- | --- | --- | --- |
| M0 — Theme + chrome reset | [spec](../../../../specs/theworldharness-M0-theme-chrome/spec.md) | [plan](../../../../specs/theworldharness-M0-theme-chrome/plan.md) | [tasks](../../../../specs/theworldharness-M0-theme-chrome/tasks.md) | done · 2026-04-21 |
| M1 — Screen architecture | [spec](../../../../specs/theworldharness-M1-screen-architecture/spec.md) | [plan](../../../../specs/theworldharness-M1-screen-architecture/plan.md) | [tasks](../../../../specs/theworldharness-M1-screen-architecture/tasks.md) | not started |
| M2 — Worlds CRUD | [spec](../../../../specs/theworldharness-M2-worlds-crud/spec.md) | [plan](../../../../specs/theworldharness-M2-worlds-crud/plan.md) | [tasks](../../../../specs/theworldharness-M2-worlds-crud/tasks.md) | not started |
| M3 — Live providers | [spec](../../../../specs/theworldharness-M3-live-providers/spec.md) | [plan](../../../../specs/theworldharness-M3-live-providers/plan.md) | [tasks](../../../../specs/theworldharness-M3-live-providers/tasks.md) | not started |
| M4 — Eval + Benchmark | [spec](../../../../specs/theworldharness-M4-eval-benchmark/spec.md) | [plan](../../../../specs/theworldharness-M4-eval-benchmark/plan.md) | [tasks](../../../../specs/theworldharness-M4-eval-benchmark/tasks.md) | not started |
| M5 — Polish + showcase | [spec](../../../../specs/theworldharness-M5-polish-showcase/spec.md) | [plan](../../../../specs/theworldharness-M5-polish-showcase/plan.md) | [tasks](../../../../specs/theworldharness-M5-polish-showcase/tasks.md) | not started |

The summaries below are the load-bearing intent of each milestone; the
linked spec triad is the source of truth for scope, acceptance, and
task breakdown.

### M0 — Theme + chrome reset (foundation)

- Register `worldforge-dark` and `worldforge-light` `Theme`s.
- Strip every hex literal from TCSS; replace with semantic variables.
- Add `Header` clock + `Breadcrumb` widget + provider status pill.
- Outcome: same flows, but the harness reads as a polished workspace
  rather than a single-screen demo.
- Spec triad: `specs/theworldharness-M0-theme-chrome/`.

### M1 — Screen architecture

- Split `TheWorldHarnessApp` into `HomeScreen` + the existing flow view
  re-homed under a `RunInspectorScreen`.
- Introduce `push_screen` / `push_screen_wait` and a `?` help overlay.
- Add `Ctrl+P` system commands.
- Outcome: navigation feels routed; nothing is hidden behind muscle
  memory.
- Spec triad: `specs/theworldharness-M1-screen-architecture/`.

### M2 — Worlds CRUD

- `WorldsScreen` + `WorldEditScreen` + `ConfirmDelete` modal.
- Reads / writes go through `WorldForge`.
- Outcome: a user can create, edit, save, and reopen a world entirely
  from the TUI — and the same code path is what library users would
  call.
- Spec triad: `specs/theworldharness-M2-worlds-crud/`.

### M3 — Live providers

- `ProvidersScreen` with the capability matrix.
- One real provider call (`mock` predict) wired through `@work` with
  events streaming into `RichLog`.
- Cancel via `Esc`.
- Outcome: the harness stops being a slideshow.
- Spec triad: `specs/theworldharness-M3-live-providers/`.

### M4 — Eval + Benchmark

- `EvalScreen` and `BenchmarkScreen`. Capability-mismatch is a hard
  toast; results land in `RunInspectorScreen` and can be exported as
  JSON / Markdown / CSV.
- Outcome: every public WorldForge surface is reachable from the TUI;
  the harness is the integration reference example.
- Spec triad: `specs/theworldharness-M4-eval-benchmark/`.

### M5 — Polish + showcase

- High-contrast theme, command palette dynamic provider for worlds /
  providers / runs, recent-items list on `HomeScreen`, snapshot test
  matrix at common terminal sizes (`100×30`, `120×40`, `160×50`),
  README screenshot refresh.
- Outcome: the harness is a credible "front face of the project" —
  worth screenshotting for talks and PRs.
- Spec triad: `specs/theworldharness-M5-polish-showcase/`.

## 9. Inspirations (and why)

| App | What to steal |
| --- | --- |
| **lazygit** | Bordered-panel grid; focus ring as the only "active" signal; one-key actions with a context-aware footer. |
| **k9s** | Command palette as primary navigation; status header that always shows the current "namespace" (in our case: provider × capability). |
| **harlequin** | TabbedContent for parallel result panes; SQL-editor-style focus rings. |
| **posting** | Form layouts, request/response split, theme switching. |
| **toolong** | RichLog usage for streaming, jump-to-end behavior, markup highlighting. |
| **btop** | Density without visual noise; semantic color usage. |

What we explicitly avoid: 1990s ncurses density (everything-on-one-screen),
decorative ASCII art that doesn't carry information, animations that loop
when nothing is happening.

## 10. Anti-goals

- **No bespoke widget framework on top of Textual.** Compose stock
  widgets; reach for a custom `Widget` only for new render or input
  models.
- **No new runtime dependencies in the `harness` extra** beyond Textual
  unless explicitly approved.
- **No "demo flows" growing beyond their current count.** The roadmap
  *replaces* them with real interactive paths.
- **No telemetry.** Local-first applies to the TUI too; nothing phones
  home.
- **No agent / tool branding** in user-visible copy. The harness is the
  project's face; it stays maintainer-style and tool-neutral.

## 11. Open questions

- Should the harness embed a 3-D scene preview (e.g., box-drawing
  isometric of the current scene)? Useful for showcase, costs
  complexity. **Decide after M3.**
- Should benchmark reports auto-publish to the docs site? Probably
  not — preserved JSON in `.worldforge/reports/` plus a copyable
  Markdown excerpt is enough. **Revisit after M4.**
- Should we ship a `worldforge harness record` mode that captures a
  Pilot trace + final SVG for use in PR descriptions? **Considered
  M5+.**

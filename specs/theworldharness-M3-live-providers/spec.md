# Milestone M3 — Live providers

## Status
Implemented · 2026-04-21

## Outcome (one sentence)
A user can pick a registered provider from `ProvidersScreen`, trigger a real `mock.predict` call against a real `World`, watch `ProviderEvent`s stream into a `RichLog` in real time, and cancel the in-flight call with `Esc` — with the cancellation observable in the UI rather than silently dropped.

## Why this milestone
TheWorldHarness today plays canned `asyncio.sleep` step animations: every "flow" is a slideshow that never crosses a real provider boundary. The roadmap §1 vision is the opposite — within two minutes a newcomer should "do something real": call a provider, watch live events, see a verdict. The first failure mode catalogued in `.codex/skills/tui-development/SKILL.md` "Why this skill exists" §1 names this directly: "Treating the harness as a slideshow." M3 is the milestone that retires it.

It also fixes the second failure mode from the same SKILL section — "Blocking the Textual event loop." The harness has not had to enforce the worker contract because nothing it did was actually long-running. Wiring `mock.predict` (and only `mock.predict`) through `@work(thread=True, group="provider", exclusive=True)` with `call_from_thread` UI mutation establishes the canonical pattern that M4 (Eval / Benchmark) and beyond reuse without further design work.

The choice of `mock` for the first real call is deliberate and aligned with `<priority_rules>` #2 in `CLAUDE.md`: it is the only always-registered provider, requires no credentials, no network, and no optional runtime — so M3 can ship in the `harness` extra without dragging torch / CUDA / robot SDKs into base dependencies.

## In scope
- `ProvidersScreen` (new `Screen` subclass under `src/worldforge/harness/tui.py`) with a capability matrix.
  - Rows: every provider returned by `WorldForge.list_providers()` (covers `PROVIDER_CATALOG` entries that auto-registered + any host-injected provider). For status / env-var detail, the screen also calls `WorldForge.provider_profile(name)` per row — `ProviderInfo` carries `capabilities` but not `implementation_status`, which lives on `ProviderProfile`.
  - Columns: the eight capabilities from `worldforge.models.CAPABILITY_NAMES` in this fixed order: `predict`, `generate`, `reason`, `embed`, `plan`, `transfer`, `score`, `policy` (matches `references/capability-matrix.md`).
  - Cell semantics, sourced **only** from `info.capabilities` (per row) and `profile.implementation_status`:
    - `●` real — `profile.implementation_status` is `"stable"` (or any non-scaffold status) and the capability flag is `True`.
    - `○` scaffold — `profile.implementation_status == "scaffold"` and the capability flag is `True`.
    - blank — capability flag is `False` (not advertised).
  - Currently-selected provider (the App's `current_provider` reactive, introduced in M0) is highlighted in the row gutter.
- Detail pane on the selected provider, sourced from `WorldForge.provider_profile(name)` and `WorldForge.provider_health(name)`:
  - `health()` output (status, latency_ms, details).
  - Required env vars (names only — see "Non-functional requirements" on masking).
  - Last call latency, last call retry count, last call phase (drawn from the most recent `ProviderEvent` for this provider, kept in a per-provider in-memory ring of size 1).
- Bindings (Screen-local, `show=True`):
  - `enter` — set the highlighted provider as the App `current_provider`.
  - `r` — open the `RegisterProvider[ProviderHandle]` modal (see Modal screens in roadmap §4.9). The modal returns a constructed provider; the screen calls `WorldForge.register_provider(...)` and refreshes its rows.
  - `p` — run `mock.predict` against the current world (the only real call wired in M3).
  - `esc` — cancel via `self.workers.cancel_group("provider")`.
- One real `mock.predict` call wired through `@work(thread=True, group="provider", exclusive=True, name="provider.predict")`:
  - The worker iterates the provider's `ProviderEvent` stream (the provider's `event_handler` posts events to a thread-safe queue the worker drains).
  - For each event, the worker calls `self.app.call_from_thread(self.post_message, ProviderEventReceived(event))`. The `ProvidersScreen` handles the message and writes to a `RichLog(highlight=True, markup=True, max_lines=5000)`.
  - On success, the worker posts `ProviderEventReceived` with phase `success` and a final `RunCompleted(provider, latency_ms)`.
  - On `ProviderError`, the worker posts a `ProviderEventReceived` with phase `failure`.
- The world used for the predict:
  - If a world is selected (M2 has landed and `selected_world` is set), use it.
  - Otherwise, the screen creates a throwaway world via `WorldForge.create_world("scratch")` and uses it for the run. The fallback is documented in the empty state.
- Cancellation:
  - Pressing `Esc` calls `self.workers.cancel_group("provider")`.
  - The worker checks `get_current_worker().is_cancelled` between drained events and returns early.
  - The status pill on the Header (introduced in M0) flips from `running` to `cancelled`; a toast notes "Cancelled".
- Empty states (per roadmap §2.4):
  - No providers registered: `"No providers registered — set the env vars in .env.example or run with --provider mock"`.
  - No prior call: `"No run captured — press [b]p[/] to run mock.predict"`.

## Out of scope (explicit)
- Real `generate`, `transfer`, `reason`, `embed`, `plan` calls. They are deferred to M4 (Eval / Benchmark) which exercises providers through the suites rather than ad-hoc bindings on `ProvidersScreen`.
- Real `score` / `policy` calls against live LeWorldModel / GR00T / LeRobot. Those touch optional runtimes (torch, CUDA, robot SDKs) and belong to the optional-runtime-smokes skill / future milestones — `<priority_rules>` #2 forbids dragging them into base or `harness` deps.
- Dynamic command palette provider for providers (every provider as a fuzzy-searchable Ctrl+P entry). That is roadmap §5 layer 2 and is explicitly assigned to M5.
- Persisting `current_provider` across sessions. Listed under "Open questions".
- Registering providers from environment that were not auto-registered at startup (the `r` modal handles direct construction; env-driven re-scan is deferred).
- A 3-D scene preview during the predict (roadmap §11 open question, decided "after M3" — i.e., not in M3).
- Telemetry / phone-home of any kind (anti-goal §10).

## User stories
1. As a researcher who just opened the harness, I open `ProvidersScreen` from the command palette, so that I can see at a glance which of my configured providers advertise `predict` and which do not.
2. As a researcher comparing capability claims, I focus a provider row, so that the right pane shows `health()`, env-var names, and the last call's latency / retry count.
3. As a researcher, I press Enter on `mock`, so that it becomes the current provider — the Header status pill updates to `mock · predict`.
4. As a researcher, I press `p`, so that a real `mock.predict` runs against the current (or scratch) world; events stream into the RichLog in order, with timestamps.
5. As a researcher, I press `Esc` while events are streaming, so that the worker cancels promptly, the RichLog records the cancellation, and the status pill reflects `cancelled`.
6. As a host integrating a custom provider, I press `r`, so that a modal lets me register an injected provider; the matrix refreshes to include the new row immediately.
7. As a user on a light terminal, I switch to `worldforge-light` (Ctrl+T), so that the matrix dots and the focus ring remain readable — neither hex literals nor a dark-only assumption breaks the read.

## Acceptance criteria
- [ ] `ProvidersScreen` renders one row per `WorldForge.list_providers()` entry; row count equals the registered provider count exactly (no hand-coded fallback list in `tui.py`).
- [ ] Capability cells are derived from `provider.capabilities` and `provider.implementation_status` only; a Pilot test asserts that flipping a capability flag on a fixture provider changes the rendered cell.
- [ ] A capability flag set `True` on a provider whose method raises `ProviderError` (a contract drift) is caught by `assert_provider_contract` in the test suite, never by the UI rendering. The UI trusts the flag.
- [ ] Pressing `p` with `mock` as `current_provider` triggers a real `mock.predict` call in a worker; at least one `ProviderEvent` with phase `success` is rendered in the `RichLog`, in order, with a timestamp prefix.
- [ ] The Textual event loop is never blocked: a Pilot test using a deliberate slow-mock (a `MockProvider` subclass whose `predict` sleeps in 50 ms slices between events) keeps the UI responsive — `pilot.press("ctrl+t")` to switch theme during the run still applies within one frame.
- [ ] Pressing `Esc` while a run is in flight cancels the worker within one animation frame; the status pill transitions `running → cancelled`; the `RichLog` records a `cancelled` line; a Pilot test asserts `running_operation == "cancelled"`.
- [ ] Cancellation is observable: a worker that returns due to `is_cancelled` posts a `RunCancelled` message; the screen's `running_operation` reactive reflects it. Silent drops fail the test.
- [ ] Pressing `r` opens `RegisterProvider[ProviderHandle]`; on dismiss with a non-`None` handle, the screen calls `WorldForge.register_provider(...)` and the matrix shows the new row without a screen pop / repush.
- [ ] No hex literals are added to the screen's TCSS; capability cell colors come from `$success` (real), `$warning` (scaffold), `$muted` (not advertised), focus ring from `$accent`. A snapshot test at `terminal_size=(120, 40)` exists for: idle, mid-run (with `RichLog` populated), and cancelled states.
- [ ] No new runtime dependency is added beyond Textual; `pyproject.toml` `[project.optional-dependencies].harness` is unchanged.
- [ ] Textual is still imported only from `src/worldforge/harness/tui.py`; `flows.py`, `cli.py`, `models.py` remain Textual-free.

## Non-functional requirements
- **Honest progress.** The `ProgressBar` for the run starts indeterminate (`total=None`) and only becomes determinate if a total step count is known up front. `mock.predict` finishes in one shot, so the bar advances from indeterminate to "done" — no fake "progress" frames.
- **No secret leakage in event log.** `ProviderEvent` is already sanitised by the provider (per `<code_conventions>`: "must not leak credentials or signed URLs"). The TUI must not append unsanitised payloads on top of what the provider emits — the `RichLog` line is constructed from `event.to_dict()` fields only.
- **Light/dark parity.** Capability cells, dots, focus ring, and the RichLog markup must read on both `worldforge-dark` and `worldforge-light` (a snapshot of each).
- **Mouse + keyboard parity.** Every binding (`enter`, `r`, `p`, `esc`) has a footer entry (`show=True`) and a clickable target (the cell or pane it triggers). No keyboard-only or mouse-only paths.
- **Capability-truthfulness contract.** No string capability is ever introduced by the UI; `ProvidersScreen` references only names from `worldforge.models.CAPABILITY_NAMES`. A Pilot test asserts the column count equals `len(CAPABILITY_NAMES)`.
- **Worker hygiene.** The only mutation paths from inside the `provider` worker group are `self.app.call_from_thread(...)` and `self.app.call_from_thread(self.post_message, ...)`. A grep-based test (or a comment + reviewer rule) keeps direct widget mutation out of the worker body.

## Open questions
- Should the App `current_provider` selection persist across sessions? If so, the persistence layer is already single-writer JSON (per `<project_decisions>` 2026-04-20) — a small `harness.json` next to `.worldforge/worlds/` would be the lightest fit, but it adds a new tracked file shape. Decide before the M3 PR opens.
- Should env-var requirements display a masked-presence check (`COSMOS_BASE_URL: set`, `RUNWAYML_API_SECRET: missing`) or names only? Names-only is safer (matches `worldforge doctor`'s sanitised behavior); masked-presence is more useful but requires reading `os.environ` from the TUI process — confirm with the user before adding.
- Should the `r` modal offer a templated "register a mock variant under a different name" path, or only generic injected-provider registration? The former is convenient for testing; the latter matches `WorldForge.register_provider`'s public surface.
- The slow-mock used for the cancellation test — does it live as a `worldforge.testing` helper (public surface, useful for downstream tests of the same shape) or as a private fixture under `tests/`? Default position: private fixture in M3, promote to `worldforge.testing` only if a second consumer appears.

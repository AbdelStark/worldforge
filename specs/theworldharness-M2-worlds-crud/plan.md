# Milestone M2 — Worlds CRUD · Implementation Plan

## Builds on

- Roadmap §8 "M2 — Worlds CRUD" — `.codex/skills/tui-development/references/roadmap.md`
- Roadmap §4.2 WorldsScreen, §4.3 WorldEditScreen, §4.9 Modal screens, §3 Architecture, §6 worker contract, §10 Anti-goals — same file
- Skill: `.codex/skills/tui-development/SKILL.md` (Textual practices, "Stop and ask" gates)
- Skill: `.codex/skills/persistence-state/SKILL.md` (single-writer, validate-at-boundary, never-coerce contract)
- Predecessor milestones: M0 (theme tokens + chrome), M1 (screen stack, `push_screen` / `push_screen_wait`, modal pattern)
- Public surface: `WorldForge.create_world`, `save_world`, `load_world`, `list_worlds`, `import_world`, `export_world`, `fork_world` in `src/worldforge/framework.py`

## Architecture changes

- New screen `WorldsScreen(Screen)` — table + detail pane; pushed by `g w` from `HomeScreen` and by command-palette "Worlds".
- New screen `WorldEditScreen(Screen)` — form-style editor for a single in-memory `World`; pushed from `WorldsScreen` via `e` / `Enter` / `n` (after `NewWorld` returns) / `f` (after `fork_world`).
- New modal `NewWorldScreen(ModalScreen[WorldSpec | None])` — name + provider + optional description fields.
- New modal `EditObjectScreen(ModalScreen[SceneObject | None])` — kind + position + rotation + metadata fields for a single scene object.
- New modal `ConfirmDeleteScreen(ModalScreen[bool])` — generic yes/no with caller-provided prompt copy.
- All screens push onto the M1 screen stack; modal results are typed via `ModalScreen[T]` (per SKILL.md).
- A small Textual-free helper module (proposed name `worlds_view.py` under `harness/`) holds presentation-pure functions used by tests: row-format for the table, summary-format for the detail pane, validation pre-check that mirrors `WorldForge` rules so error toasts can be raised before round-tripping. The module imports nothing from `textual`; SKILL.md "Stop and ask" gate "before importing Textual outside `tui.py`" is preserved.

## Module touch list

| Path | Change | Notes |
| --- | --- | --- |
| `src/worldforge/harness/tui.py` | Add `WorldsScreen`, `WorldEditScreen`, `NewWorldScreen`, `EditObjectScreen`, `ConfirmDeleteScreen`, related TCSS, and `Ctrl+P` system commands. Wire `g w` into existing screen stack from M1. | Sole Textual import site (load-bearing per SKILL.md). |
| `src/worldforge/harness/worlds_view.py` (new) | Presentation-pure helpers (row formatting, detail summary, dirty check, id pre-validation that mirrors `_validate_storage_id`). | Textual-free; importable without the harness extra. Confirm with the user before adding (SKILL.md "Stop and ask"). |
| `src/worldforge/harness/cli.py` | Optional: `--initial-screen worlds` flag so `worldforge-harness --initial-screen worlds` lands directly on `WorldsScreen`. | Keep Textual-free; no change to existing flow flags. |
| `src/worldforge/harness/__init__.py` | Re-export new screen classes only if tests need them; default to keeping the harness public surface unchanged. | Stay narrow; M5 will revisit public exports for the showcase milestone. |
| `src/worldforge/framework.py` | **Gated proposal**: add `def delete_world(self, world_id: str) -> None` that validates the id via `_validate_storage_id` and unlinks the file (no-op-friendly when absent? — see "Key technical decisions"). Requires explicit approval per `CLAUDE.md` `<gated>`. | If approval is withheld, the TUI uses an internal helper that mirrors `_validate_storage_id` and unlinks; an issue is filed for follow-up CLI parity. |
| `src/worldforge/__init__.py` | Re-export `delete_world` only if added on `WorldForge`. | Gated alongside the framework change. |
| `tests/test_harness_tui.py` | Add Pilot tests covering create, edit-and-save, delete (cancel + confirm), fork, filter, and rejected-id toast. | Pattern matches the existing `test_the_world_harness_app_runs_leworldmodel_flow` shape. |
| `tests/test_harness_worlds_view.py` (new) | Unit tests for the Textual-free `worlds_view` helpers. | No Textual import — runs on the base profile. |
| `tests/test_harness_snapshots/` (new) | `pytest-textual-snapshot` SVGs for the screens listed in spec.md acceptance criteria. | Pin `terminal_size=(120, 40)` per SKILL.md. |
| `docs/src/playbooks.md` | Short subsection: "Manage worlds from TheWorldHarness". | Cross-link to `worldforge world` CLI parity table. |
| `CHANGELOG.md` | "Added — TheWorldHarness M2 (Worlds CRUD)" entry on the next release. | Tool-neutral, maintainer-style. |
| `.codex/skills/tui-development/references/roadmap.md` | Mark §8 M2 "done · YYYY-MM-DD" on landing. | Final task in tasks.md. |

## Key technical decisions

- **Form widget choice (`WorldEditScreen`).** Decision: stock `Input` for name, `Select` for provider (populated from `WorldForge` registered providers), `OptionList` + add/edit/remove buttons for scene objects, `Static` for the snapshot preview. Alternative considered: a single custom `Form` widget. Rejected per SKILL.md "Compose, don't subclass" — there is no new render or input model here.
- **Snapshot preview rendering.** Decision: text-only — multi-line `Static` showing scene-object positions and a step counter; no pseudo-3-D rendering. Alternatives: ASCII iso grid (rejected per roadmap §11 "Decide after M3"); embedded image (no precedent in the codebase, would require asset pipeline).
- **`WorldStateError` surface.** Decision: toast (`app.notify(..., severity="error")`) for boundary errors, with the message verbatim from the exception. The screen also keeps the in-memory edit buffer intact so the user can fix and retry. Alternatives: inline error under each invalid field (rejected — `WorldStateError` is structured by message, not by field; reverse-mapping would couple the TUI to the validator's wording); modal blocking dialog (rejected — too heavy for a save retry).
- **Delete path (gated).** Preferred: add `WorldForge.delete_world(world_id: str) -> None` (validates id via `_validate_storage_id`, unlinks the file, raises `WorldStateError` on failure). This keeps the TUI as the integration reference example — every action reproducible in ~20 lines. Fallback if approval is withheld: a private `_delete_world_file(forge: WorldForge, world_id: str) -> None` helper inside `harness/tui.py` that re-validates the id with the public validator and unlinks; an issue is opened for promoting it later.
- **Filter implementation.** Decision: client-side filter over the already-loaded `list_worlds()` result; substring match on `id` and `name`. Alternative: re-query on every keystroke (rejected — `list_worlds` reads the directory; client filter is cheaper and consistent with single-writer assumption).
- **Worker boundary.** Decision: every call into `WorldForge.{save_world, load_world, list_worlds, import_world, export_world, fork_world, delete_world}` runs inside a `@work(thread=True, group="persistence", exclusive=True, name=...)` worker. The screen owns the worker; `Esc` calls `self.workers.cancel_group("persistence")` (SKILL.md worker contract).
- **`refresh-on-resume` over polling.** Decision: `WorldsScreen.on_screen_resume` re-runs `list_worlds()` so returning from `WorldEditScreen` reflects new state. No filesystem watcher / polling — that would conflict with the single-writer contract.

## Data flow

**Reactives**

- `WorldsScreen.selected_world: reactive[str | None] = reactive(None)` — drives the detail pane; paired with `watch_selected_world(self, old, new)` that loads the row-summary into the right pane.
- `WorldsScreen.filter_query: reactive[str] = reactive("")` — paired with `watch_filter_query` that re-applies the client-side filter.
- `WorldEditScreen.current_world: reactive[World | None] = reactive(None)` — the in-memory edit buffer.
- `WorldEditScreen.dirty: reactive[bool] = reactive(False)` — drives the title-bar `*` marker and the `Esc`-with-confirm path.
- `WorldEditScreen.staged_action: reactive[Action | None] = reactive(None)` — when set, triggers the preview worker.

**Messages**

- `WorldSelected(world_id: str)` — posted by the `DataTable` row-cursor change.
- `WorldSaved(world_id: str)` — posted by `WorldEditScreen` after a successful `save_world` worker; `WorldsScreen` listens via `on_world_saved` to re-query.
- `WorldDeleted(world_id: str)` — posted after a successful delete worker.
- `WorldForked(source_id: str, fork_id: str)` — posted when `fork_world` returns; `WorldsScreen` re-queries and `WorldEditScreen` opens on `fork_id` unsaved.
- `WorldEditDirty(dirty: bool)` — internal to `WorldEditScreen`, drives the dirty marker.

**Workers**

- `@work(thread=True, group="persistence", exclusive=True, name="list_worlds")` — `WorldsScreen.refresh_worlds`.
- `@work(thread=True, group="persistence", exclusive=True, name="load_world")` — `WorldsScreen.open_selected`.
- `@work(thread=True, group="persistence", exclusive=True, name="save_world")` — `WorldEditScreen.save_current`.
- `@work(thread=True, group="persistence", exclusive=True, name="fork_world")` — `WorldsScreen.fork_selected`.
- `@work(thread=True, group="persistence", exclusive=True, name="delete_world")` — `WorldsScreen.delete_selected`.
- `@work(thread=True, group="provider", exclusive=True, name="predict_preview")` — `WorldEditScreen.refresh_preview` (only when `staged_action` is set; preview-only, never persists).

All worker results post messages via `self.app.call_from_thread(self.post_message, ...)` per SKILL.md "Never mutate widgets directly from a thread worker".

## Theming and CSS

Semantic CSS variables only — no hex literals (SKILL.md "Don't ship inline hex colors"). Token usage:

- `$accent` — selected `DataTable` row, focused panel border, active "Save" button.
- `$panel` — idle panel borders.
- `$success` — toast on successful save / fork / delete; the dirty marker reverts to `$success` after save.
- `$warning` — preview caption when `staged_action` is set; the dirty `*` marker.
- `$error` — toast on `WorldStateError`; invalid-input field outline in modals.
- `$boost` — hover state on rows and buttons.
- `$surface` / `$muted` — primary and secondary text inside the detail pane.

Borders use `round` only (per roadmap §2.2). Hierarchy comes from borders + padding + `Rule()`, never blank-line spacers.

## Testing

- **Pilot tests** (`tests/test_harness_tui.py`):
  - Full `n` → `NewWorld` modal → fill → submit → row appears round-trip.
  - `Enter` on row → `WorldEditScreen` populated → add object → `Ctrl+S` → reopen → state preserved.
  - `d` → `ConfirmDelete` cancel returns `False`; row still present.
  - `d` → `ConfirmDelete` confirm returns `True`; row removed; row count decremented.
  - `f` → fork created; new id; opened in `WorldEditScreen` with `dirty=True` until first save.
  - `/lab` filter narrows the table.
  - **Rejected-id path**: feed `"../escape"` to `NewWorld` → `WorldStateError` toast appears → no file is written under `state_dir` (assert via `WorldForge.list_worlds()`).
- **Snapshot tests** (`tests/test_harness_snapshots/`) at `terminal_size=(120, 40)`:
  - `WorldsScreen` empty (empty-state hint visible).
  - `WorldsScreen` with 3 worlds and one selected.
  - `WorldEditScreen` mid-edit with one staged action and the preview pane lit.
  - `NewWorld` modal open over `WorldsScreen`.
  - `ConfirmDelete` modal open over `WorldsScreen`.
  - Save-error toast visible.
- **Unit tests** (`tests/test_harness_worlds_view.py`) for the Textual-free helpers — runnable on the base profile without the `harness` extra.
- **Coverage gate**: `uv run --extra harness pytest --cov=src/worldforge --cov-report=term-missing --cov-fail-under=90` must continue to pass; the new helpers and screens must carry tests sufficient to keep the gate green (per `CLAUDE.md` `<commands>` and `tui-development/SKILL.md` "Coverage" reference).

## Risks and mitigations

- **Risk**: hand-rolling JSON inside `tui.py` (e.g., to "show what's on disk") would bypass `WorldForge` validation and silently diverge from CLI behavior.
  - **Mitigation**: every read/write goes through `WorldForge` public methods. A targeted ruff / Grep check during review rejects `json.dump` / `json.load` inside `harness/`. The detail pane reads from a loaded `World`, not from a parsed file.
- **Risk**: blocking the Textual event loop on disk I/O (e.g., `list_worlds()` directly in `compose`).
  - **Mitigation**: every call into `WorldForge` runs inside a `persistence`-group worker per SKILL.md worker contract; the empty state is rendered synchronously while the worker populates the table.
- **Risk**: silent coercion of an invalid persisted payload (e.g., catching `WorldStateError` and returning a "fixed" world).
  - **Mitigation**: `WorldStateError` is rethrown as a toast and the in-memory state is preserved unchanged. Persistence-state SKILL "Don't" — "silently coerce invalid persisted state" — covered by the rejected-id Pilot test.
- **Risk**: introducing a public API change (`delete_world`) without approval.
  - **Mitigation**: tasks.md splits the work so the framework change is its own gated PR; if approval is withheld, the fallback private helper path is taken and a follow-up issue is opened.
- **Risk**: snapshot flakiness on different CIs.
  - **Mitigation**: pin `terminal_size=(120, 40)`, await `pilot.pause()` before assertion, commit SVGs (SKILL.md "Test with Pilot and snapshots").
- **Risk**: leaking Textual into a non-`tui.py` module.
  - **Mitigation**: the `worlds_view.py` helper file is Textual-free by construction; a unit test imports it without the `harness` extra installed.
- **Risk**: scope creep into M3 territory by streaming events during preview.
  - **Mitigation**: the preview worker is single-shot — it calls `provider.predict` once and renders the resulting snapshot; no `RichLog` wiring, no event streaming, no cancel-mid-stream UX. Streaming is deferred to M3.

## Dependencies on other milestones

- **Required before this can ship**:
  - M0 — semantic theme tokens (`$accent`, `$panel`, `$success`, `$warning`, `$error`, `$boost`, `$surface`, `$muted`) must be registered.
  - M1 — screen stack (`push_screen` / `push_screen_wait`), `?` help overlay, and `Ctrl+P` system commands must exist; `WorldsScreen` and `WorldEditScreen` push onto the M1 stack rather than introducing it.
- **Blocks**:
  - M3 — `ProvidersScreen` will let users change a world's provider in place; that lookup wires into the same `WorldForge.list_providers` plumbing M2 introduces in `WorldEditScreen`.
  - M4 — `EvalScreen` and `BenchmarkScreen` need a "pick a world" affordance that reads from the same listing M2 builds.
  - M5 — `HomeScreen` "Recent worlds" list pulls from the same `WorldForge.list_worlds` cache M2 owns.

# Milestone M2 — Worlds CRUD · Tasks

Each task is a single PR-sized unit. Order matters: a later task may assume an earlier one has landed in main. Every PR keeps the existing test gates green; no task may weaken `--cov-fail-under=90`.

## T1 — Textual-free `worlds_view` helpers

- Files: `src/worldforge/harness/worlds_view.py` (new), `tests/test_harness_worlds_view.py` (new).
- Change: introduce a small Textual-free module under `src/worldforge/harness/` for presentation-pure helpers used by later tasks: `format_world_row(world: World) -> tuple[str, str, str, int, str]` (id, name, provider, step, last-touched ISO string), `format_detail_summary(world: World) -> str`, `is_dirty(original: World, edited: World) -> bool`, and `validate_id_or_reason(world_id: str) -> str | None` (mirrors `_validate_storage_id` so the TUI can render an inline error before round-tripping through `WorldForge`). Confirm with the user before adding the file (SKILL.md "Stop and ask: before introducing a new file under `src/worldforge/harness/`").
- Acceptance: maps to spec.md acceptance "no widget CSS contains a hex literal" only indirectly; primary goal is to keep Textual import boundary intact (`from worldforge.harness.worlds_view import format_world_row` works without the `harness` extra installed).
- Tests: `tests/test_harness_worlds_view.py` covering each helper; one test asserts the module imports without `textual` available (mock `sys.modules['textual']` to `None` and re-import).

## T2 — Gated public API addition: `WorldForge.delete_world`

- Files: `src/worldforge/framework.py`, `src/worldforge/__init__.py` (re-export if needed), `tests/test_world_lifecycle.py` (new tests).
- Change: add `def delete_world(self, world_id: str) -> None` to `WorldForge` that validates `world_id` via `_validate_storage_id` (raising `WorldStateError` on rejection), unlinks the file via `_world_file(...).unlink(missing_ok=False)`, and raises `WorldStateError` on filesystem failure. **Gated** per `CLAUDE.md` `<gated>` ("persistence contract in `src/worldforge/framework.py`"); requires explicit approval before merge. If approval is withheld, this task is replaced by T2-fallback (a private `_delete_world_file` helper inside `harness/tui.py` that re-validates the id with the public validator and unlinks).
- Acceptance: maps to spec.md "Delete only proceeds when ConfirmDelete returns True" and the open-question "delete public API". After this task, the CLI parity command `worldforge world delete <id>` becomes trivial follow-up work.
- Tests: round-trip create → save → delete → `list_worlds()` shrinks; delete with `"../escape"` raises `WorldStateError`; delete of a non-existent id raises `WorldStateError`.

## T3 — `ConfirmDelete[bool]` modal

- Files: `src/worldforge/harness/tui.py`, `tests/test_harness_tui.py`.
- Change: add `class ConfirmDeleteScreen(ModalScreen[bool])` with caller-provided prompt copy, "Cancel" and "Delete" buttons, `Esc` returning `False`, `Enter` while "Delete" is focused returning `True`. Use semantic CSS variables only.
- Acceptance: maps to spec.md acceptance "ConfirmDelete returns False on Esc; True only on explicit confirm".
- Tests: Pilot test that pushes the modal, presses `Esc`, asserts `False`; another that focuses "Delete", presses `Enter`, asserts `True`. Snapshot test of the modal at `terminal_size=(120, 40)`.

## T4 — `NewWorld[WorldSpec]` modal

- Files: `src/worldforge/harness/tui.py`, `src/worldforge/harness/worlds_view.py` (extend with a `WorldSpec` dataclass if needed), `tests/test_harness_tui.py`.
- Change: add `class NewWorldScreen(ModalScreen[WorldSpec | None])` with `Input` for name, `Select` for provider, optional `Input` for description. On submit, return a `WorldSpec`; on `Esc` / Cancel, return `None`. Validate inputs with `worlds_view.validate_id_or_reason` before dismissing — invalid input keeps the modal open and surfaces the reason inline (`$error` outline).
- Acceptance: maps to spec.md acceptance "An invalid id submitted through NewWorld… raises WorldStateError… never reaches the filesystem" — the modal blocks early and the screen also defends via the save worker.
- Tests: Pilot test that submits a valid spec → modal returns `WorldSpec`; submits `"../escape"` → modal stays open with inline error; presses `Esc` → returns `None`. Snapshot test of the modal.

## T5 — `WorldsScreen` (read-only first cut)

- Files: `src/worldforge/harness/tui.py`, `tests/test_harness_tui.py`, `tests/test_harness_snapshots/`.
- Change: add `class WorldsScreen(Screen)` with `DataTable(zebra_stripes=True, cursor_type="row")`, right-side detail pane, `selected_world` and `filter_query` reactives, and a `persistence`-group worker for `list_worlds`. Bindings: `n` (no-op until T7), `e` / `Enter` (no-op until T6), `d` (no-op until T8), `f` (no-op until T9), `/` filter, `r` refresh, `q` quit, `g h` home. Empty state per roadmap §2.4. Wire `g w` from the M1 `HomeScreen` to push this screen.
- Acceptance: maps to spec.md acceptance "On mount, WorldsScreen populates its DataTable from list_worlds()" and "all colors come from semantic CSS variables".
- Tests: Pilot test that mounts `WorldsScreen` over an empty `state_dir` and asserts the empty-state hint; another that pre-creates 3 worlds via `WorldForge.save_world` and asserts the table populates. Snapshot tests for empty and populated states at `terminal_size=(120, 40)`.

## T6 — `WorldEditScreen` (read + save round-trip)

- Files: `src/worldforge/harness/tui.py`, `tests/test_harness_tui.py`, `tests/test_harness_snapshots/`.
- Change: add `class WorldEditScreen(Screen)` with `Input` for name, `Select` for provider, `OptionList` for scene objects, `Static` snapshot preview, dirty marker. Bindings: `Ctrl+S` save, `Esc` close (with `ConfirmDelete[bool]` if dirty), `a` add object (modal in T7), `Delete` remove object, `Ctrl+Up` / `Ctrl+Down` reorder. Wire `e` / `Enter` from `WorldsScreen` to push this screen with the loaded `World`. Save runs through the `save_world` worker; `WorldStateError` becomes a toast and the buffer is preserved.
- Acceptance: maps to spec.md acceptance "Ctrl+S in WorldEditScreen calls WorldForge.save_world; a WorldStateError becomes a toast and does not corrupt state" and "load → edit → save round-trip preserves history and scene objects".
- Tests: Pilot test that opens an existing world, edits the name, presses `Ctrl+S`, asserts the saved file matches the new name on reload (via a fresh `WorldForge.load_world`). Pilot test that simulates a `WorldStateError` (e.g., via a name-empty edit) and asserts the toast renders. Snapshot test of the screen mid-edit.

## T7 — Create flow (`n` → `NewWorld` → `WorldEditScreen` unsaved)

- Files: `src/worldforge/harness/tui.py`, `tests/test_harness_tui.py`.
- Change: wire `n` on `WorldsScreen` to `push_screen_wait(NewWorldScreen())`; on a returned `WorldSpec`, build a fresh `World` via `WorldForge.create_world(name, provider=provider, description=description)` and push `WorldEditScreen` unsaved (`dirty=True`). Add `EditObjectScreen(ModalScreen[SceneObject | None])` for `a` inside `WorldEditScreen` so the user can populate scene objects before first save.
- Acceptance: maps to user story 2 ("As a researcher with an empty state_dir, I see the empty-state hint, press `n`, fill the modal, and after Save I see my new world appear").
- Tests: Pilot test that walks `n` → fill modal → `Ctrl+S` → return to `WorldsScreen` → row visible in table. Snapshot test of the chained modal-over-edit-over-table state.

## T8 — Delete flow (`d` → `ConfirmDelete` → `delete_world` worker)

- Files: `src/worldforge/harness/tui.py`, `tests/test_harness_tui.py`, `tests/test_harness_snapshots/`.
- Change: wire `d` on `WorldsScreen` to `push_screen_wait(ConfirmDeleteScreen(prompt=...))`; on `True`, run the `delete_world` worker (T2 if approved; otherwise the fallback private helper). On worker success, post `WorldDeleted(world_id)`; the table re-queries via `on_world_deleted`. On `WorldStateError`, toast and leave the row alone.
- Acceptance: maps to spec.md acceptance "Delete only proceeds when ConfirmDelete returns True; the worker that removes the world file completes before the row is removed from the table".
- Tests: Pilot test for cancel path (row count unchanged) and confirm path (row count decremented; file gone). Snapshot test of the modal over the table.

## T9 — Fork flow (`f` → `fork_world` → `WorldEditScreen` unsaved)

- Files: `src/worldforge/harness/tui.py`, `tests/test_harness_tui.py`.
- Change: wire `f` on `WorldsScreen` to a `fork_world` worker that calls `WorldForge.fork_world(world_id, history_index=0)`. On success, post `WorldForked(source_id, fork_id)` and push `WorldEditScreen` on the fork with `dirty=True`. The fork is *not* on disk until the user presses `Ctrl+S`.
- Acceptance: maps to spec.md acceptance "Fork creates a world whose id differs from the source, whose history starts with a single 'world forked' entry, and which is not yet on disk".
- Tests: Pilot test that forks an existing world, asserts `WorldEditScreen` opens with `dirty=True`, and asserts `WorldForge.list_worlds()` does not yet include the fork id; after `Ctrl+S`, the fork id is present.

## T10 — Live "predict next state" preview

- Files: `src/worldforge/harness/tui.py`, `tests/test_harness_tui.py`.
- Change: add a `provider`-group worker `refresh_preview` on `WorldEditScreen` triggered by `staged_action` reactive changes. Worker calls `provider.predict(...)` once and renders the predicted snapshot into the right-pane `Static` with a `$warning`-tinted "preview" caption. Cancellation on `Esc` calls `self.workers.cancel_group("provider")` per SKILL.md worker contract. No `RichLog` wiring; no streaming; no persistence side effects (M3 owns streaming).
- Acceptance: maps to spec.md user story 5 ("see the 'predict next state' preview update… preview is not written to history until I commit").
- Tests: Pilot test that stages an action against the `mock` provider, awaits the preview worker, and asserts the caption + the preview text differs from the pre-staging snapshot. Asserts `WorldForge.load_world(world_id).history` length is unchanged after preview.

## T11 — Filter (`/`) on `WorldsScreen`

- Files: `src/worldforge/harness/tui.py`, `tests/test_harness_tui.py`.
- Change: add an `Input` triggered by `/` that drives the `filter_query` reactive; client-side substring match on `id` and `name` over the already-loaded list. `Esc` clears the filter and returns focus to the table.
- Acceptance: maps to spec.md user story 8.
- Tests: Pilot test that types `lab` and asserts only matching rows remain visible.

## T12 — Command-palette entries

- Files: `src/worldforge/harness/tui.py`, `tests/test_harness_tui.py`.
- Change: extend `App.get_system_commands` with: "New world" (push `NewWorldScreen` then route on success), "Open world…" (fuzzy picker over `list_worlds()`), "Fork world…" (fuzzy picker → fork worker), "Delete world…" (fuzzy picker → `ConfirmDelete`). All entries also surface as footer bindings on `WorldsScreen` (mouse + keyboard parity).
- Acceptance: maps to spec.md acceptance "Every binding shown in the screen footer maps to a Ctrl+P command palette entry" and roadmap §5 ("If a feature exists but isn't in the palette, it doesn't exist for new users").
- Tests: Pilot test that opens the palette, types "fork", selects the entry, and asserts the fork picker opens.

## T13 — Docs, changelog, roadmap update

- Files: `docs/src/playbooks.md`, `CHANGELOG.md`, `.codex/skills/tui-development/references/roadmap.md`.
- Change: add a "Manage worlds from TheWorldHarness" subsection in `playbooks.md` cross-linking the `worldforge world` CLI parity table; add a `CHANGELOG.md` entry under "Added" for the next release; mark roadmap §8 M2 "done · YYYY-MM-DD".
- Acceptance: maps to roadmap §8 milestone-completion contract ("Each milestone ends with a runnable harness, a Pilot test for the new flow, snapshot tests for the new screens, and a roadmap update marking the milestone 'done' with the date").
- Tests: `uv run python scripts/generate_provider_docs.py --check` (no drift); `uv run --extra harness pytest --cov=src/worldforge --cov-report=term-missing --cov-fail-under=90` (gate green).

## Definition of done

- [ ] All tasks T1–T13 merged on `main`.
- [ ] Pilot tests for create / edit-and-save / delete-cancel / delete-confirm / fork / filter / rejected-id / preview present in `tests/test_harness_tui.py`.
- [ ] Snapshot tests for the screens listed in spec.md acceptance criteria committed under `tests/test_harness_snapshots/` and reviewed in their landing PRs.
- [ ] Coverage gate (`uv run --extra harness pytest --cov=src/worldforge --cov-report=term-missing --cov-fail-under=90`) green.
- [ ] Provider docs check (`uv run python scripts/generate_provider_docs.py --check`) green.
- [ ] No hex literals in widget CSS introduced by this milestone.
- [ ] Textual import boundary preserved: only `src/worldforge/harness/tui.py` imports `textual`.
- [ ] `.codex/skills/tui-development/references/roadmap.md` §8 marked "done · YYYY-MM-DD".
- [ ] `CHANGELOG.md` entry added under the next unreleased section.

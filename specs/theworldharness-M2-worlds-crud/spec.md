# Milestone M2 — Worlds CRUD

## Status
Draft · 2026-04-21

## Outcome (one sentence)
A user can create, edit, fork, save, reopen, and delete a World entirely from TheWorldHarness TUI without writing Python — and every disk write goes through the same `WorldForge` public API a library caller would use.

## Why this milestone

The roadmap vision (`.codex/skills/tui-development/references/roadmap.md` §1) commits to two promises that depend on this milestone landing: that a newcomer can "do something real within two minutes" (create a world), and that the harness is "the canonical, copyable example of how to use WorldForge" (anything they do in the TUI must be reproducible in ~20 lines of Python). Worlds are the first stateful object a user encounters; until M2 ships, the harness can only display canned demo flows over an empty `state_dir`.

This milestone respects the persistence-state skill's contract (`.codex/skills/persistence-state/SKILL.md`): the TUI is a single-writer, never-coerce client of `WorldForge`. World IDs are validated before any path construction; payloads are validated on every load and import; `WorldStateError` is the firewall and surfaces as a toast — never silently swallowed and never "fixed" by clamping or dropping fields. The project decision recorded in `CLAUDE.md` ("keep local JSON persistence single-writer — rejected adding lock files, SQLite, or service persistence without a dedicated design") is honored: no concurrent-write coordination is introduced by this milestone.

## In scope

- `WorldsScreen` with `DataTable(zebra_stripes=True, cursor_type="row")` listing worlds discovered via `WorldForge.list_worlds()`. Columns: id, name, provider, step, last touched (file mtime).
- Right-side detail pane on `WorldsScreen` showing scene-object count, current provider, history count, and the resolved `state_dir` path (per roadmap §4.2).
- `WorldEditScreen` form with: name `Input`, provider `Select` populated from registered providers, scene-object list with add / move-up / move-down / remove, and a snapshot preview pane on the right (per roadmap §4.3).
- `NewWorld[WorldSpec]` modal (`ModalScreen[WorldSpec | None]`) for the "create a world" path triggered by `n` from `WorldsScreen`.
- `EditObject[SceneObject]` modal (`ModalScreen[SceneObject | None]`) for adding or editing a scene object inside `WorldEditScreen`.
- `ConfirmDelete[bool]` modal (`ModalScreen[bool]`) used before any destructive action (delete world, drop unsaved edits when leaving `WorldEditScreen` dirty).
- `Ctrl+S` in `WorldEditScreen` saves through `WorldForge.save_world`; `Esc` requests cancel (with `ConfirmDelete[bool]` if dirty).
- Filter (`/`) on `WorldsScreen` narrows the table by id / name substring.
- Fork (`f`) on `WorldsScreen` calls `WorldForge.fork_world(world_id, history_index=0, name=...)` and pushes the result into `WorldEditScreen` unsaved.
- Live "predict next state" preview in the snapshot pane when an action is staged (calls `provider.predict` via a worker; preview-only, never persists).
- Round-trip parity with the `worldforge world ...` CLI commands listed in `CLAUDE.md` `<commands>`: anything done in the TUI is loadable / inspectable / editable from the CLI on the same `state_dir`, and vice versa.
- Empty state on `WorldsScreen` per roadmap §2.4 ("No worlds yet — press [b]n[/] to create one").
- Command-palette entries (`Ctrl+P`) for: "New world", "Open world…", "Fork world…", "Delete world…" — per roadmap §5.

## Out of scope (explicit)

- Live provider event streaming during predict beyond the single-shot preview — full streaming UX is M3 (`ProvidersScreen` and `RichLog` wiring).
- A 3-D scene preview — explicitly listed in roadmap §11 as "Decide after M3".
- Multi-writer / concurrent edit coordination — explicitly forbidden by `.codex/skills/persistence-state/SKILL.md` and the `CLAUDE.md` 2026-04-20 project decision; introducing locks or SQLite needs a separate, approved design.
- Migrations of older persisted shapes — gated per the persistence skill; if a payload fails validation it surfaces as a toast and the user must export-and-fix or discard.
- Eval / benchmark integration on a selected world — defer to M4 (`EvalScreen`, `BenchmarkScreen`).
- Provider capability matrix or registration UI — defer to M3 (`ProvidersScreen`).
- Recent-worlds list on `HomeScreen` — defer to M5 (polish + showcase).
- Renaming worlds by changing their `id` — id is the storage key and immutable; renaming is `name` only. (See "Open questions" for the fork-as-rename pattern.)

## User stories

1. As a researcher, I press `g w` (or click "Worlds" from `HomeScreen`), so that I land on `WorldsScreen` and see every world in my `state_dir`.
2. As a researcher with an empty `state_dir`, I see the empty-state hint, press `n`, fill the `NewWorld` modal, and after Save I see my new world appear in the table without needing to restart.
3. As a researcher, I press `e` on a row (or `Enter`), so that `WorldEditScreen` opens with the world's name, provider, and scene objects already populated.
4. As a researcher in `WorldEditScreen`, I press `a` to add a scene object via the `EditObject` modal, see it appear in the list and snapshot preview, then press `Ctrl+S` to persist.
5. As a researcher in `WorldEditScreen` with a staged action, I see the "predict next state" preview update in the snapshot pane, and that preview is *not* written to history until I commit.
6. As a researcher, I press `d` on a row, see `ConfirmDelete` modal, press `Esc` (returns `False`) and the world is still there; I press `d` again and confirm (returns `True`) and the row disappears.
7. As a researcher, I press `f` on a row, the world is forked (new id, history reset to a "world forked" entry per `WorldForge.fork_world`) and `WorldEditScreen` opens unsaved on the fork.
8. As a researcher, I type `/lab` in the filter box, so that only rows whose id or name contains `lab` remain visible.
9. As a researcher, I save a world the validator rejects (e.g. an empty name), and I see a toast carrying the `WorldStateError` message — the row in the table is unchanged and the screen does not crash.
10. As a researcher, I open the command palette (`Ctrl+P`), type "fork", select "Fork world…", and a fuzzy-search picker over existing world ids opens.

## Acceptance criteria

- [ ] On mount, `WorldsScreen` populates its `DataTable` from `WorldForge.list_worlds()` and reflects a freshly saved world without app restart (re-query on `WorldSaved` / `WorldDeleted` messages).
- [ ] `Ctrl+S` in `WorldEditScreen` invokes `WorldForge.save_world` on a worker; on `WorldStateError` the screen surfaces the message via a toast and the in-memory edit buffer is preserved (no data loss).
- [ ] An invalid id submitted through `NewWorld` (e.g., `"../escape"`, an empty string, or a value containing path separators) raises `WorldStateError` from `WorldForge.save_world` and is rendered as a toast — *never reaches the filesystem* (matches the persistence-state procedure step 1).
- [ ] `ConfirmDelete[bool]` returns `False` on `Esc`, on the explicit "Cancel" button, and when dismissed by clicking outside; it returns `True` only on the explicit "Delete" button or `Enter` while "Delete" is focused.
- [ ] Delete only proceeds when `ConfirmDelete` returns `True`; the worker that removes the world file completes before the row is removed from the table.
- [ ] A round trip — create in `NewWorld` → save → close `WorldEditScreen` → reopen via `Enter` on the row — preserves the world's `id`, `name`, `provider`, scene objects, and full history (matches the invariants asserted in `tests/test_world_lifecycle.py`).
- [ ] Fork creates a world whose `id` differs from the source, whose history starts with a single "world forked" entry, and which is *not* yet on disk (matches `WorldForge.fork_world` semantics in `src/worldforge/framework.py:1259`).
- [ ] All disk-touching operations (save, load, list, import, export, delete-file) run on workers in the `persistence` group; the UI never blocks on them. `Esc` while a worker is active calls `self.workers.cancel_group("persistence")`.
- [ ] Every binding shown in the screen footer maps to a `Ctrl+P` command palette entry (mouse + keyboard parity per roadmap §5 and SKILL.md "Patterns" → "Pair every footer binding with a click target and a tooltip").
- [ ] No widget CSS contains a hex literal; all colors come from semantic CSS variables (`$accent`, `$success`, `$error`, `$panel`, `$boost`, `$surface`, `$muted`).
- [ ] `tests/test_harness_tui.py`-style Pilot tests cover: create round-trip, edit-and-save round-trip, delete cancel + confirm paths, rejected-id toast, fork path, filter narrowing.
- [ ] Snapshot tests exist at `terminal_size=(120, 40)` for: `WorldsScreen` empty, `WorldsScreen` with N worlds, `WorldEditScreen` mid-edit, `NewWorld` modal, `ConfirmDelete` modal, save-error toast.
- [ ] Coverage gate (`uv run --extra harness pytest --cov=src/worldforge --cov-report=term-missing --cov-fail-under=90`) still passes after this milestone.

## Non-functional requirements

- Empty states per roadmap §2.4 — never a blank panel.
- Validation errors are toasts, not exceptions — the TUI never panics, and a `WorldStateError` from `WorldForge` is treated as expected control flow at the boundary.
- Disk I/O on workers (`@work(thread=True, group="persistence", exclusive=True, name="<readable>")`) — UI thread never calls `save_world` / `load_world` / file unlink directly.
- Keyboard-first: every action reachable in one keystroke or via `Ctrl+P`.
- Footer never lies: only screen-local bindings shown; internal bindings stay `show=False`.
- Single-writer contract preserved: the TUI assumes one `WorldForge(state_dir=...)` per process and does not introduce coordination primitives.
- Tool-neutral copy in every visible string (per `CLAUDE.md` `<priority_rules>` item 5).

## Open questions

- Should `f` (fork) prompt for a new id / name immediately via a `NewWorld`-shaped modal, auto-generate (current `WorldForge.fork_world` behavior), or both via a chord (`f` auto, `F` prompt)? Default proposal: `f` auto-generates and opens `WorldEditScreen` unsaved so the user can rename before `Ctrl+S`.
- When an action is staged but not yet committed, should the snapshot preview render the predicted next state (history step N+1) or the current state (N) with an overlay indicator? Default proposal: render N+1, with a `$warning`-tinted "preview" caption so it's unambiguous.
- Should "delete" hard-unlink the JSON file immediately, or move it to `.worldforge/trash/<world_id>-<timestamp>.json` for one-keystroke recovery? Default proposal: hard delete with an "Undo" toast that survives 5 seconds and re-saves the in-memory state if pressed; deferred-recovery storage is out of scope unless approved.
- Public-API question (gated, see plan.md): should this milestone introduce a `WorldForge.delete_world(world_id: str) -> None` method (currently absent — only `_world_file` helper exists), or should the TUI use a private helper inside `harness/tui.py` that mirrors the same id validation? Default proposal: add `delete_world` to the public API behind explicit approval, because the TUI is the integration reference and CLI parity (`worldforge world delete <id>`) likely wants the same surface.
- Should `WorldsScreen` poll the `state_dir` for external changes (another process or a CLI invocation between TUI sessions added a file), or only refresh on intra-app messages and explicit `r`? Default proposal: refresh on `on_screen_resume` and on explicit `r`; no polling — polling would conflict with the single-writer contract messaging.

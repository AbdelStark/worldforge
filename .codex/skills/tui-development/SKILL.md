---
name: tui-development
description: "Use for TheWorldHarness work: Textual screens, flows, launchpad, command palette, world editor, screenshots, visual tests, and changes under `src/worldforge/harness/`. Preserves the optional Textual boundary while keeping flow logic testable without the TUI."
---

# TUI Development

## Architecture Boundary

- `src/worldforge/harness/models.py`: dataclasses only.
- `src/worldforge/harness/flows.py`: runnable flow logic and summaries.
- `src/worldforge/harness/cli.py`: list/launch surface that works without importing Textual.
- `src/worldforge/harness/tui.py`: primary Textual import surface.
- `src/worldforge/harness/worlds_view.py`: TUI-specific world editor/view code.

Never import Textual from `worldforge.__init__`, `worldforge.cli`, or non-TUI harness modules.

## Workflow

1. Read `models.py`, `flows.py`, and `cli.py` before touching TUI modules.
2. Keep `worldforge harness --list --format json` runnable without the `harness` extra.
3. Use deterministic `mock` providers and temporary state dirs for diagnostics flows.
4. Keep screen state, flow records, and summaries JSON-native where rendered or tested.
5. Update the relevant tests: `test_harness_cli.py`, `test_harness_flows.py`, `test_harness_guards.py`, `test_harness_tui.py`, `test_harness_worlds_view.py`, or `test_harness_snapshots.py`.
6. Update screenshots only when UI behavior or documented visual state changed.
7. Validate with focused harness tests and the `--extra harness` coverage gate when behavior changes.

## Spec Map

Current harness spec triads live under:

- `specs/theworldharness-M0-theme-chrome/`
- `specs/theworldharness-M1-screen-architecture/`
- `specs/theworldharness-M2-worlds-crud/`
- `specs/theworldharness-M3-live-providers/`
- `specs/theworldharness-M4-eval-benchmark/`
- `specs/theworldharness-M5-polish-showcase/`

Update the relevant `spec.md`, `plan.md`, or `tasks.md` before implementing a new milestone.

## Sharp Edges

| Symptom | Cause | Fix |
| --- | --- | --- |
| Base import fails without Textual | Optional import leaked | Move Textual import under `harness/tui.py` or guarded launch path |
| Harness list command fails | Flow metadata coupled to TUI | Move metadata back into `models.py`/`flows.py` |
| Snapshot drift | UI text or command surface changed | Update snapshot only after verifying behavior |

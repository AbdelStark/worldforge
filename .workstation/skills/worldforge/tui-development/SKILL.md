---
name: tui-development
description: "Use for the robotics showcase Textual UI: report panes, launch helpers, screenshots, visual tests, and changes under `src/worldforge/harness/tui.py` or robotics view/rendering modules. Preserves the optional Textual boundary while keeping robotics flow logic testable without the TUI."
---

# TUI Development

## Architecture Boundary

- `src/worldforge/harness/robotics_launch.py`: launcher and host-owned viewer helpers.
- `src/worldforge/harness/robotics_view.py`: Textual-free robotics report model and constants.
- `src/worldforge/harness/robotics_tui_rendering.py`: pure Rich renderable builders for panes.
- `src/worldforge/harness/tui.py`: robotics-showcase-only Textual import surface.
- `src/worldforge/harness/tui_styles.py` and `tui_robotics_styles.py`: Textual CSS constants.

Never import Textual from `worldforge.__init__`, `worldforge.cli`, or non-TUI harness modules.

## Robotics TUI Engineering Contract

- Treat the robotics showcase as a testable report renderer first and a Textual screen second.
- Keep robotics summaries and screen state JSON-native so evidence can move between CLI,
  tests, screenshots, and docs.
- Keep long-running optional runtime work behind explicit commands; UI state should report
  progress and failure without hiding the underlying exception context.
- The removed world-creation/provider/eval/benchmark harness screens must not come back through
  this skill. Use CLI/docs surfaces for those workflows.

## Workflow

1. Read `robotics_view.py`, `robotics_tui_rendering.py`, `robotics_launch.py`, and `tui.py` before touching TUI modules.
2. Keep all Textual imports inside `harness/tui.py`.
3. Keep report rendering pure and deterministic outside Textual so tests can run without the `harness` extra.
4. Update the relevant tests: `test_robotics_tui_rendering.py`, `test_robotics_showcase.py`, `test_robotics_showcase_scripts.py`, or focused harness report tests.
5. Update screenshots only when UI behavior or documented visual state changed.
6. Validate with focused robotics tests, optional-import boundary checks, and the `--extra harness` coverage gate when behavior changes.

## Definition Of Done

- Robotics report rendering works without the `harness` extra.
- Changed robotics UI behavior is covered at the pure-rendering level before TUI-specific tests.
- Textual imports remain isolated and optional-import boundary checks pass when imports moved.
- Snapshot or screenshot updates are intentional and tied to verified behavior.

## Spec Map

Current robotics showcase spec triads live under:

- `specs/roboto-showcase/`

Update the relevant `spec.md`, `plan.md`, or `tasks.md` before implementing a new milestone.

## Sharp Edges

| Symptom | Cause | Fix |
| --- | --- | --- |
| Base import fails without Textual | Optional import leaked | Move Textual import under `harness/tui.py` or guarded launch path |
| Robotics report import fails | Rendering coupled to Textual | Move pure report logic back into `robotics_view.py` or `robotics_tui_rendering.py` |
| Snapshot drift | UI text or command surface changed | Update snapshot only after verifying behavior |

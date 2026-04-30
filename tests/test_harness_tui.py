from __future__ import annotations

import asyncio
import re
from pathlib import Path

import pytest

HARNESS_TUI_PATH = Path(__file__).resolve().parents[1] / "src" / "worldforge" / "harness" / "tui.py"


def test_harness_tui_has_no_hex_color_literals() -> None:
    """The semantic-token rule from spec.md is mechanically enforceable here."""
    pattern = re.compile(r"#[0-9a-fA-F]{3,8}")
    matches = pattern.findall(HARNESS_TUI_PATH.read_text())
    assert matches == [], f"hex color literals leaked into tui.py: {matches}"


def test_harness_themes_registered_with_dark_default(tmp_path) -> None:
    pytest.importorskip("textual")

    from worldforge.harness.tui import TheWorldHarnessApp

    async def scenario() -> None:
        app = TheWorldHarnessApp(initial_flow_id="leworldmodel", state_dir=tmp_path)
        async with app.run_test(size=(130, 42)):
            assert "worldforge-dark" in app.available_themes
            assert "worldforge-light" in app.available_themes
            assert "worldforge-high-contrast" in app.available_themes
            assert app.theme == "worldforge-dark"

    asyncio.run(scenario())


def test_harness_theme_toggle_cycles_between_registered_themes(tmp_path) -> None:
    pytest.importorskip("textual")

    from worldforge.harness.tui import TheWorldHarnessApp

    async def scenario() -> None:
        app = TheWorldHarnessApp(initial_flow_id="leworldmodel", state_dir=tmp_path)
        async with app.run_test(size=(130, 42)) as pilot:
            assert app.theme == "worldforge-dark"
            await pilot.press("ctrl+t")
            await pilot.pause()
            assert app.theme == "worldforge-light"
            await pilot.press("ctrl+t")
            await pilot.pause()
            assert app.theme == "worldforge-high-contrast"
            await pilot.press("ctrl+t")
            await pilot.pause()
            assert app.theme == "worldforge-dark"

    asyncio.run(scenario())


def _robotics_summary() -> dict[str, object]:
    return {
        "checkpoint_display": "~/.stable-wm/pusht/lewm_object.ckpt",
        "inputs": {
            "policy_path": "lerobot/diffusion_pusht",
            "approx_float32_mb": 3.446,
            "total_tensor_elements": 903318,
        },
        "score_result": {
            "best_index": 2,
            "best_score": 9.331253051757812,
            "scores": [17.086671829223633, 12.75649642944336, 9.331253051757812],
        },
        "execution": {
            "final_block_position": {"x": 0.375, "y": 0.375, "z": 0.0},
        },
        "provider_events": [
            {
                "provider": "lerobot",
                "operation": "policy",
                "phase": "success",
                "duration_ms": 5211.61,
            },
            {
                "provider": "leworldmodel",
                "operation": "score",
                "phase": "success",
                "duration_ms": 67.77,
            },
        ],
        "visualization": {
            "selected_candidate": 2,
            "candidate_targets": [
                {"index": 0, "x": 0.75, "y": 0.75, "z": 0.0},
                {"index": 1, "x": 0.625, "y": 0.625, "z": 0.0},
                {"index": 2, "x": 0.375, "y": 0.375, "z": 0.0},
            ],
        },
        "metrics": {"plan_latency_ms": 5279.53, "total_latency_ms": 9597.51},
    }


def test_robotics_showcase_app_renders_visual_report(tmp_path) -> None:
    pytest.importorskip("textual")

    from worldforge.harness.tui import (
        ROBOTICS_REPORT_GUIDE_ROWS,
        RoboticsArmPane,
        RoboticsCandidatePane,
        RoboticsEventPane,
        RoboticsReportGuidePane,
        RoboticsShowcaseApp,
        RoboticsTabletopPane,
    )

    summary = _robotics_summary()
    assert any(row[0] == "Runtime bars" for row in ROBOTICS_REPORT_GUIDE_ROWS)
    assert any("lower cost wins" in row[1] for row in ROBOTICS_REPORT_GUIDE_ROWS)

    async def scenario() -> None:
        app = RoboticsShowcaseApp(
            summary=summary,
            summary_path=tmp_path / "summary.json",
            stage_delay=0.0,
            animate_arm=False,
        )
        async with app.run_test(size=(150, 48)) as pilot:
            await pilot.pause()
            assert app.query_one(RoboticsArmPane) is not None
            assert app.query_one(RoboticsCandidatePane) is not None
            assert app.query_one(RoboticsTabletopPane) is not None
            assert app.query_one(RoboticsReportGuidePane) is not None
            assert app.query_one(RoboticsEventPane) is not None
            await pilot.press("ctrl+t")
            await pilot.pause()
            assert app.theme == "worldforge-light"

    asyncio.run(scenario())


def test_robotics_showcase_help_overlay_explains_tabletop_replay(tmp_path) -> None:
    pytest.importorskip("textual")

    from worldforge.harness.tui import (
        ROBOTICS_TABLETOP_HELP_TEXT,
        RoboticsShowcaseApp,
        RoboticsTabletopHelpScreen,
    )

    assert "selected target and mock final state overlap" in ROBOTICS_TABLETOP_HELP_TEXT
    assert "not a hardware camera feed" in ROBOTICS_TABLETOP_HELP_TEXT

    async def scenario() -> None:
        app = RoboticsShowcaseApp(
            summary=_robotics_summary(),
            summary_path=tmp_path / "summary.json",
            stage_delay=0.0,
            animate_arm=False,
        )
        async with app.run_test(size=(150, 48)) as pilot:
            await pilot.press("?")
            await pilot.pause()
            assert isinstance(app.screen, RoboticsTabletopHelpScreen)
            await pilot.press("escape")
            await pilot.pause()
            assert not isinstance(app.screen, RoboticsTabletopHelpScreen)

    asyncio.run(scenario())


def test_robotics_showcase_app_stages_visual_report(tmp_path) -> None:
    pytest.importorskip("textual")

    from textual.css.query import NoMatches

    from worldforge.harness.tui import (
        RoboticsArmPane,
        RoboticsCandidatePane,
        RoboticsEventPane,
        RoboticsProgressPane,
        RoboticsReportGuidePane,
        RoboticsShowcaseApp,
        RoboticsTabletopPane,
    )

    async def scenario() -> None:
        app = RoboticsShowcaseApp(
            summary=_robotics_summary(),
            summary_path=tmp_path / "summary.json",
            stage_delay=0.001,
            animate_arm=True,
        )
        async with app.run_test(size=(150, 48)) as pilot:
            expected_panes = (
                RoboticsArmPane,
                RoboticsCandidatePane,
                RoboticsTabletopPane,
                RoboticsReportGuidePane,
                RoboticsEventPane,
            )

            def staged_report_complete() -> bool:
                try:
                    for pane in expected_panes:
                        app.query_one(pane)
                    app.query_one(RoboticsProgressPane)
                except NoMatches:
                    return all(len(app.query(pane)) == 1 for pane in expected_panes)
                return False

            for _ in range(100):
                if staged_report_complete():
                    break
                await pilot.pause(0.01)
            else:
                pytest.fail("staged robotics report did not finish mounting all panes")

            assert app.query_one(RoboticsArmPane) is not None
            assert app.query_one(RoboticsCandidatePane) is not None
            assert app.query_one(RoboticsTabletopPane) is not None
            assert app.query_one(RoboticsReportGuidePane) is not None
            assert app.query_one(RoboticsEventPane) is not None
            with pytest.raises(NoMatches):
                app.query_one(RoboticsProgressPane)

    asyncio.run(scenario())


def test_robotics_arm_pane_advances_frame(tmp_path) -> None:
    pytest.importorskip("textual")

    from worldforge.harness.tui import RoboticsArmPane, RoboticsShowcaseApp

    async def scenario() -> None:
        app = RoboticsShowcaseApp(
            summary=_robotics_summary(),
            summary_path=tmp_path / "summary.json",
            stage_delay=0.0,
            animate_arm=False,
        )
        async with app.run_test(size=(150, 48)) as pilot:
            await pilot.pause()
            arm = app.query_one(RoboticsArmPane)
            assert arm._frame_index == 0
            arm._advance()
            assert arm._frame_index == 1

    asyncio.run(scenario())


def test_harness_breadcrumb_reflects_selected_flow(tmp_path) -> None:
    pytest.importorskip("textual")

    from worldforge.harness.tui import Breadcrumb, TheWorldHarnessApp

    async def scenario() -> None:
        app = TheWorldHarnessApp(
            initial_flow_id="leworldmodel",
            initial_screen="run-inspector",
            state_dir=tmp_path,
        )
        async with app.run_test(size=(130, 42)) as pilot:
            crumb = app.screen.query_one("#breadcrumb", Breadcrumb)
            assert crumb.path == ("worldforge", "run-inspector", "LeWorldModel")
            await pilot.press("2")
            await pilot.pause()
            assert crumb.path == ("worldforge", "run-inspector", "LeRobot")

    asyncio.run(scenario())


def test_harness_status_pill_reflects_selected_flow_provider(tmp_path) -> None:
    pytest.importorskip("textual")

    from worldforge.harness.tui import ProviderStatusPill, TheWorldHarnessApp

    async def scenario() -> None:
        app = TheWorldHarnessApp(
            initial_flow_id="leworldmodel",
            initial_screen="run-inspector",
            state_dir=tmp_path,
        )
        async with app.run_test(size=(130, 42)) as pilot:
            pill = app.screen.query_one("#provider-pill", ProviderStatusPill)
            assert "LeWorldModelProvider" in pill.label
            assert pill.label.endswith("· score")
            await pilot.press("2")
            await pilot.pause()
            assert "LeRobotPolicyProvider" in pill.label
            assert pill.label.endswith("· policy")
            await pilot.press("3")
            await pilot.pause()
            assert pill.label.endswith("· diagnostics")

    asyncio.run(scenario())


def test_the_world_harness_app_runs_leworldmodel_flow(tmp_path) -> None:
    pytest.importorskip("textual")

    from worldforge.harness.tui import RunInspectorScreen, TheWorldHarnessApp

    async def scenario() -> None:
        app = TheWorldHarnessApp(
            initial_flow_id="leworldmodel",
            initial_screen="run-inspector",
            state_dir=tmp_path,
            step_delay=0.0,
        )
        async with app.run_test(size=(130, 42)) as pilot:
            await pilot.press("r")
            await pilot.pause()
            screen = app.screen
            assert isinstance(screen, RunInspectorScreen)
            assert screen.last_run is not None
            assert screen.last_run.flow.id == "leworldmodel"
            assert screen.last_run.summary["selected_candidate_index"] == 1
            assert screen.query_one("#inspector") is not None

    asyncio.run(scenario())


def test_the_world_harness_app_switches_to_lerobot_flow(tmp_path) -> None:
    pytest.importorskip("textual")

    from worldforge.harness.tui import RunInspectorScreen, TheWorldHarnessApp

    async def scenario() -> None:
        app = TheWorldHarnessApp(
            initial_flow_id="leworldmodel",
            initial_screen="run-inspector",
            state_dir=tmp_path,
            step_delay=0.0,
        )
        async with app.run_test(size=(130, 42)) as pilot:
            await pilot.press("2")
            await pilot.press("r")
            await pilot.pause()
            screen = app.screen
            assert isinstance(screen, RunInspectorScreen)
            assert screen.last_run is not None
            assert screen.last_run.flow.id == "lerobot"
            assert screen.last_run.summary["policy_candidate_count"] == 3

    asyncio.run(scenario())


def test_the_world_harness_app_switches_to_diagnostics_flow(tmp_path) -> None:
    pytest.importorskip("textual")

    from worldforge.harness.tui import RunInspectorScreen, TheWorldHarnessApp

    async def scenario() -> None:
        app = TheWorldHarnessApp(
            initial_flow_id="leworldmodel",
            initial_screen="run-inspector",
            state_dir=tmp_path,
            step_delay=0.0,
        )
        async with app.run_test(size=(140, 44)) as pilot:
            await pilot.press("3")
            await pilot.press("r")
            await pilot.pause()
            screen = app.screen
            assert isinstance(screen, RunInspectorScreen)
            assert screen.last_run is not None
            assert screen.last_run.flow.id == "diagnostics"
            assert screen.last_run.summary["benchmark_operation_count"] == 5

    asyncio.run(scenario())


# ---------------------------------------------------------------------------
# M1 — Screen architecture tests
# ---------------------------------------------------------------------------


def test_initial_screen_is_home_when_no_flow_flag(tmp_path) -> None:
    pytest.importorskip("textual")

    from worldforge.harness.tui import HomeScreen, TheWorldHarnessApp

    async def scenario() -> None:
        app = TheWorldHarnessApp(state_dir=tmp_path)  # no initial_screen → "home"
        async with app.run_test(size=(130, 42)):
            assert isinstance(app.screen, HomeScreen)

    asyncio.run(scenario())


def test_initial_screen_is_run_inspector_when_flow_flag_passed(tmp_path) -> None:
    pytest.importorskip("textual")

    from worldforge.harness.tui import RunInspectorScreen, TheWorldHarnessApp

    async def scenario() -> None:
        app = TheWorldHarnessApp(
            initial_flow_id="lerobot",
            initial_screen="run-inspector",
            state_dir=tmp_path,
        )
        async with app.run_test(size=(130, 42)):
            assert isinstance(app.screen, RunInspectorScreen)
            assert app.screen.selected_flow_id == "lerobot"

    asyncio.run(scenario())


def test_jump_to_home_from_run_inspector(tmp_path) -> None:
    pytest.importorskip("textual")

    from worldforge.harness.tui import Breadcrumb, HomeScreen, TheWorldHarnessApp

    async def scenario() -> None:
        app = TheWorldHarnessApp(
            initial_flow_id="leworldmodel",
            initial_screen="run-inspector",
            state_dir=tmp_path,
        )
        async with app.run_test(size=(130, 42)) as pilot:
            await pilot.press("g", "h")
            await pilot.pause()
            assert isinstance(app.screen, HomeScreen)
            crumb = app.screen.query_one("#breadcrumb", Breadcrumb)
            assert crumb.path == ("worldforge", "home")

    asyncio.run(scenario())


def test_jump_to_run_inspector_from_home(tmp_path) -> None:
    pytest.importorskip("textual")

    from worldforge.harness.tui import RunInspectorScreen, TheWorldHarnessApp

    async def scenario() -> None:
        app = TheWorldHarnessApp(state_dir=tmp_path)
        async with app.run_test(size=(130, 42)) as pilot:
            await pilot.press("g", "r")
            await pilot.pause()
            assert isinstance(app.screen, RunInspectorScreen)

    asyncio.run(scenario())


def test_help_overlay_opens_and_closes(tmp_path) -> None:
    pytest.importorskip("textual")

    from worldforge.harness.tui import HelpScreen, RunInspectorScreen, TheWorldHarnessApp

    async def scenario() -> None:
        app = TheWorldHarnessApp(
            initial_flow_id="leworldmodel",
            initial_screen="run-inspector",
            state_dir=tmp_path,
        )
        async with app.run_test(size=(130, 42)) as pilot:
            assert isinstance(app.screen, RunInspectorScreen)
            await pilot.press("?")
            await pilot.pause()
            assert isinstance(app.screen, HelpScreen)
            await pilot.press("escape")
            await pilot.pause()
            assert isinstance(app.screen, RunInspectorScreen)

    asyncio.run(scenario())


def test_command_palette_lists_screens_and_flows(tmp_path) -> None:
    pytest.importorskip("textual")

    from worldforge.harness.flows import available_flows
    from worldforge.harness.tui import TheWorldHarnessApp

    async def scenario() -> None:
        app = TheWorldHarnessApp(state_dir=tmp_path)
        async with app.run_test(size=(130, 42)):
            commands = list(app.get_system_commands(app.screen))
            titles = [cmd.title for cmd in commands]
            assert "Jump: Home" in titles
            assert "Jump: Run Inspector" in titles
            assert "Open Help" in titles
            assert "Switch theme" in titles
            for flow in available_flows():
                assert f"Run flow: {flow.title}" in titles
            # Quit comes from the stock Textual SystemCommands.
            assert any("uit" in t for t in titles)

    asyncio.run(scenario())


def test_home_jump_card_keyboard_activation(tmp_path) -> None:
    pytest.importorskip("textual")

    from worldforge.harness.tui import HomeScreen, TheWorldHarnessApp, WorldsScreen

    async def scenario() -> None:
        app = TheWorldHarnessApp(state_dir=tmp_path)
        async with app.run_test(size=(130, 42)) as pilot:
            assert isinstance(app.screen, HomeScreen)
            await pilot.press("n")
            await pilot.pause()
            # With M2 landed, the "Create a world" jump card opens the real
            # Worlds screen instead of the M2 placeholder.
            assert isinstance(app.screen, WorldsScreen)

    asyncio.run(scenario())


# ---------------------------------------------------------------------------
# M2 — Worlds CRUD tests
# ---------------------------------------------------------------------------


def _seed_world(state_dir, name: str = "lab", world_id: str | None = None) -> str:
    """Save one world through the public WorldForge API so the table has rows."""

    from worldforge import WorldForge

    forge = WorldForge(state_dir=state_dir)
    world = forge.create_world(name, provider="mock")
    if world_id:
        world.id = world_id
    return forge.save_world(world)


def test_worlds_screen_shows_empty_state_on_empty_state_dir(tmp_path) -> None:
    pytest.importorskip("textual")

    from textual.widgets import Static

    from worldforge.harness.tui import TheWorldHarnessApp, WorldsScreen

    async def scenario() -> None:
        app = TheWorldHarnessApp(state_dir=tmp_path, initial_screen="worlds")
        async with app.run_test(size=(130, 42)) as pilot:
            await pilot.pause()
            assert isinstance(app.screen, WorldsScreen)
            empty = app.screen.query_one("#worlds-empty", Static)
            assert "No worlds yet" in empty.render().plain  # type: ignore[union-attr]

    asyncio.run(scenario())


def test_worlds_screen_populates_table_from_state_dir(tmp_path) -> None:
    pytest.importorskip("textual")

    from textual.widgets import DataTable

    from worldforge.harness.tui import TheWorldHarnessApp, WorldsScreen

    _seed_world(tmp_path, name="alpha")
    _seed_world(tmp_path, name="beta")
    _seed_world(tmp_path, name="gamma")

    async def scenario() -> None:
        app = TheWorldHarnessApp(state_dir=tmp_path, initial_screen="worlds")
        async with app.run_test(size=(130, 42)) as pilot:
            await pilot.pause()
            await pilot.pause()
            assert isinstance(app.screen, WorldsScreen)
            table = app.screen.query_one("#worlds-table", DataTable)
            assert table.row_count == 3

    asyncio.run(scenario())


def test_worlds_create_new_world_round_trip(tmp_path) -> None:
    pytest.importorskip("textual")

    from textual.widgets import Input

    from worldforge import WorldForge
    from worldforge.harness.tui import (
        NewWorldScreen,
        TheWorldHarnessApp,
        WorldEditScreen,
        WorldsScreen,
    )

    async def scenario() -> None:
        app = TheWorldHarnessApp(state_dir=tmp_path, initial_screen="worlds")
        async with app.run_test(size=(130, 42)) as pilot:
            await pilot.pause()
            assert isinstance(app.screen, WorldsScreen)
            await pilot.press("n")
            await pilot.pause()
            assert isinstance(app.screen, NewWorldScreen)
            # Fill the name and submit.
            name_input = app.screen.query_one("#new-world-name", Input)
            name_input.value = "kitchen"
            await pilot.pause()
            await pilot.press("enter")
            await pilot.pause()
            assert isinstance(app.screen, WorldEditScreen)
            # Save via Ctrl+S.
            await pilot.press("ctrl+s")
            await pilot.pause()
            await pilot.pause()
            # Back to the Worlds screen: row should have been persisted.
            forge = WorldForge(state_dir=tmp_path)
            ids = forge.list_worlds()
            assert len(ids) == 1

    asyncio.run(scenario())


def test_worlds_delete_cancel_keeps_row(tmp_path) -> None:
    pytest.importorskip("textual")

    from worldforge import WorldForge
    from worldforge.harness.tui import ConfirmDeleteScreen, TheWorldHarnessApp, WorldsScreen

    _seed_world(tmp_path, name="lab-keep", world_id="lab-keep")

    async def scenario() -> None:
        app = TheWorldHarnessApp(state_dir=tmp_path, initial_screen="worlds")
        async with app.run_test(size=(130, 42)) as pilot:
            await pilot.pause()
            await pilot.pause()
            assert isinstance(app.screen, WorldsScreen)
            await pilot.press("d")
            await pilot.pause()
            assert isinstance(app.screen, ConfirmDeleteScreen)
            await pilot.press("escape")
            await pilot.pause()
            await pilot.pause()
            assert isinstance(app.screen, WorldsScreen)
            forge = WorldForge(state_dir=tmp_path)
            assert forge.list_worlds() == ["lab-keep"]

    asyncio.run(scenario())


def test_worlds_delete_confirm_removes_row(tmp_path) -> None:
    pytest.importorskip("textual")

    from worldforge import WorldForge
    from worldforge.harness.tui import ConfirmDeleteScreen, TheWorldHarnessApp, WorldsScreen

    _seed_world(tmp_path, name="lab-drop", world_id="lab-drop")

    async def scenario() -> None:
        app = TheWorldHarnessApp(state_dir=tmp_path, initial_screen="worlds")
        async with app.run_test(size=(130, 42)) as pilot:
            await pilot.pause()
            await pilot.pause()
            assert isinstance(app.screen, WorldsScreen)
            await pilot.press("d")
            await pilot.pause()
            assert isinstance(app.screen, ConfirmDeleteScreen)
            await pilot.click("#confirm-accept")
            # Wait for the persistence worker to complete and post the
            # WorldDeleted message back to the worlds screen.
            for _ in range(10):
                await pilot.pause()
            forge = WorldForge(state_dir=tmp_path)
            assert forge.list_worlds() == []

    asyncio.run(scenario())


def test_worlds_fork_opens_edit_screen_with_fresh_id(tmp_path) -> None:
    pytest.importorskip("textual")

    from worldforge import WorldForge
    from worldforge.harness.tui import TheWorldHarnessApp, WorldEditScreen, WorldsScreen

    _seed_world(tmp_path, name="lab-fork", world_id="lab-fork")

    async def scenario() -> None:
        app = TheWorldHarnessApp(state_dir=tmp_path, initial_screen="worlds")
        async with app.run_test(size=(130, 42)) as pilot:
            await pilot.pause()
            await pilot.pause()
            assert isinstance(app.screen, WorldsScreen)
            await pilot.press("f")
            await pilot.pause()
            await pilot.pause()
            await pilot.pause()
            assert isinstance(app.screen, WorldEditScreen)
            assert app.screen.dirty is True
            # Fork is in-memory only until saved.
            forge = WorldForge(state_dir=tmp_path)
            assert forge.list_worlds() == ["lab-fork"]

    asyncio.run(scenario())


def test_worlds_filter_narrows_table(tmp_path) -> None:
    pytest.importorskip("textual")

    from textual.widgets import DataTable, Input

    from worldforge.harness.tui import TheWorldHarnessApp, WorldsScreen

    _seed_world(tmp_path, name="kitchen-a", world_id="kitchen-a")
    _seed_world(tmp_path, name="kitchen-b", world_id="kitchen-b")
    _seed_world(tmp_path, name="lab-1", world_id="lab-1")

    async def scenario() -> None:
        app = TheWorldHarnessApp(state_dir=tmp_path, initial_screen="worlds")
        async with app.run_test(size=(130, 42)) as pilot:
            await pilot.pause()
            await pilot.pause()
            assert isinstance(app.screen, WorldsScreen)
            filt = app.screen.query_one("#worlds-filter", Input)
            filt.value = "kit"
            await pilot.pause()
            await pilot.pause()
            table = app.screen.query_one("#worlds-table", DataTable)
            assert table.row_count == 2

    asyncio.run(scenario())


def test_worlds_rejected_id_surfaces_toast(tmp_path) -> None:
    pytest.importorskip("textual")

    from textual.widgets import Input

    from worldforge import WorldForge
    from worldforge.harness.tui import (
        NewWorldScreen,
        TheWorldHarnessApp,
        WorldEditScreen,
        WorldsScreen,
    )

    async def scenario() -> None:
        app = TheWorldHarnessApp(state_dir=tmp_path, initial_screen="worlds")
        async with app.run_test(size=(130, 42)) as pilot:
            await pilot.pause()
            assert isinstance(app.screen, WorldsScreen)
            await pilot.press("n")
            await pilot.pause()
            assert isinstance(app.screen, NewWorldScreen)
            # Valid-looking name, but we then rewrite the id to an unsafe one
            # before saving, ensuring the save worker surfaces a toast and
            # does not leave a file on disk.
            name_input = app.screen.query_one("#new-world-name", Input)
            name_input.value = "kitchen"
            await pilot.pause()
            await pilot.press("enter")
            await pilot.pause()
            assert isinstance(app.screen, WorldEditScreen)
            app.screen._world.id = "../escape"
            await pilot.press("ctrl+s")
            await pilot.pause()
            await pilot.pause()
            forge = WorldForge(state_dir=tmp_path)
            # The save worker rejected the id; no file under state_dir.
            assert forge.list_worlds() == []

    asyncio.run(scenario())


def test_worlds_command_palette_exposes_new_and_jump_worlds(tmp_path) -> None:
    pytest.importorskip("textual")

    from worldforge.harness.tui import TheWorldHarnessApp

    async def scenario() -> None:
        app = TheWorldHarnessApp(state_dir=tmp_path)
        async with app.run_test(size=(130, 42)):
            titles = [cmd.title for cmd in app.get_system_commands(app.screen)]
            assert "Jump: Worlds" in titles
            assert "New world" in titles

    asyncio.run(scenario())


def test_worlds_initial_screen_opens_worlds(tmp_path) -> None:
    pytest.importorskip("textual")

    from worldforge.harness.tui import TheWorldHarnessApp, WorldsScreen

    async def scenario() -> None:
        app = TheWorldHarnessApp(state_dir=tmp_path, initial_screen="worlds")
        async with app.run_test(size=(130, 42)):
            assert isinstance(app.screen, WorldsScreen)

    asyncio.run(scenario())


def test_worlds_chord_g_w_jumps_to_worlds(tmp_path) -> None:
    pytest.importorskip("textual")

    from worldforge.harness.tui import TheWorldHarnessApp, WorldsScreen

    async def scenario() -> None:
        app = TheWorldHarnessApp(state_dir=tmp_path)
        async with app.run_test(size=(130, 42)) as pilot:
            await pilot.press("g", "w")
            await pilot.pause()
            assert isinstance(app.screen, WorldsScreen)

    asyncio.run(scenario())


def test_worlds_edit_save_round_trip_preserves_rename(tmp_path) -> None:
    pytest.importorskip("textual")

    from textual.widgets import Input

    from worldforge import WorldForge
    from worldforge.harness.tui import TheWorldHarnessApp, WorldEditScreen, WorldsScreen

    _seed_world(tmp_path, name="lab-rename", world_id="lab-rename")

    async def scenario() -> None:
        app = TheWorldHarnessApp(state_dir=tmp_path, initial_screen="worlds")
        async with app.run_test(size=(130, 42)) as pilot:
            await pilot.pause()
            await pilot.pause()
            assert isinstance(app.screen, WorldsScreen)
            await pilot.press("enter")
            await pilot.pause()
            assert isinstance(app.screen, WorldEditScreen)
            name_input = app.screen.query_one("#edit-name", Input)
            name_input.value = "workbench"
            await pilot.pause()
            assert app.screen.dirty is True
            await pilot.press("ctrl+s")
            await pilot.pause()
            await pilot.pause()
            forge = WorldForge(state_dir=tmp_path)
            reloaded = forge.load_world("lab-rename")
            assert reloaded.name == "workbench"

    asyncio.run(scenario())


def test_worlds_add_object_and_preview(tmp_path) -> None:
    pytest.importorskip("textual")

    from worldforge.harness.tui import (
        EditObjectScreen,
        TheWorldHarnessApp,
        WorldEditScreen,
        WorldsScreen,
    )

    _seed_world(tmp_path, name="lab-add", world_id="lab-add")

    async def scenario() -> None:
        app = TheWorldHarnessApp(state_dir=tmp_path, initial_screen="worlds")
        async with app.run_test(size=(130, 42)) as pilot:
            await pilot.pause()
            await pilot.pause()
            assert isinstance(app.screen, WorldsScreen)
            await pilot.press("enter")
            await pilot.pause()
            assert isinstance(app.screen, WorldEditScreen)
            await pilot.press("a")
            await pilot.pause()
            assert isinstance(app.screen, EditObjectScreen)
            # Accept defaults.
            await pilot.click("#edit-object-save")
            await pilot.pause()
            await pilot.pause()
            assert isinstance(app.screen, WorldEditScreen)
            # Staged action is a preview; history must not be bumped.
            assert len(app.screen._world.scene_objects) == 1
            assert app.screen.staged_action is not None

    asyncio.run(scenario())


def test_confirm_delete_returns_false_on_escape(tmp_path) -> None:
    pytest.importorskip("textual")

    from worldforge.harness.tui import ConfirmDeleteScreen, TheWorldHarnessApp

    outcome: list[bool | None] = []

    async def scenario() -> None:
        app = TheWorldHarnessApp(state_dir=tmp_path)
        async with app.run_test(size=(130, 42)) as pilot:
            await app.push_screen(ConfirmDeleteScreen(), outcome.append)
            await pilot.pause()
            assert isinstance(app.screen, ConfirmDeleteScreen)
            await pilot.press("escape")
            await pilot.pause()

    asyncio.run(scenario())
    assert outcome == [False]


def test_command_palette_new_world_routes_to_modal(tmp_path) -> None:
    pytest.importorskip("textual")

    from worldforge.harness.tui import NewWorldScreen, TheWorldHarnessApp, WorldsScreen

    async def scenario() -> None:
        app = TheWorldHarnessApp(state_dir=tmp_path)
        async with app.run_test(size=(130, 42)) as pilot:
            await pilot.pause()
            app._command_new_world()
            await pilot.pause()
            await pilot.pause()
            assert isinstance(app.screen, (NewWorldScreen, WorldsScreen))

    asyncio.run(scenario())


def test_worlds_jump_palette_command_switches_screen(tmp_path) -> None:
    pytest.importorskip("textual")

    from worldforge.harness.tui import TheWorldHarnessApp, WorldsScreen

    async def scenario() -> None:
        app = TheWorldHarnessApp(state_dir=tmp_path)
        async with app.run_test(size=(130, 42)) as pilot:
            await pilot.pause()
            app.action_switch_screen("worlds")
            await pilot.pause()
            assert isinstance(app.screen, WorldsScreen)
            # Re-issuing the same command is a no-op (already active).
            app.action_switch_screen("worlds")
            await pilot.pause()
            assert isinstance(app.screen, WorldsScreen)

    asyncio.run(scenario())


def test_new_world_modal_inline_validation_blocks_unsafe_id(tmp_path) -> None:
    pytest.importorskip("textual")

    from textual.widgets import Input, Static

    from worldforge.harness.tui import NewWorldScreen, TheWorldHarnessApp, WorldsScreen

    async def scenario() -> None:
        app = TheWorldHarnessApp(state_dir=tmp_path, initial_screen="worlds")
        async with app.run_test(size=(130, 42)) as pilot:
            await pilot.pause()
            assert isinstance(app.screen, WorldsScreen)
            await pilot.press("n")
            await pilot.pause()
            assert isinstance(app.screen, NewWorldScreen)
            name_input = app.screen.query_one("#new-world-name", Input)
            name_input.value = "../escape"
            await pilot.pause()
            await pilot.click("#new-world-create")
            await pilot.pause()
            # Modal stays open with an error visible.
            assert isinstance(app.screen, NewWorldScreen)
            error = app.screen.query_one("#new-world-error", Static)
            assert "hidden" not in error.classes

    asyncio.run(scenario())


def test_new_world_modal_cancel_returns_none(tmp_path) -> None:
    pytest.importorskip("textual")

    from worldforge.harness.tui import NewWorldScreen, TheWorldHarnessApp

    outcome: list[object | None] = []

    async def scenario() -> None:
        app = TheWorldHarnessApp(state_dir=tmp_path)
        async with app.run_test(size=(130, 42)) as pilot:
            await app.push_screen(NewWorldScreen(providers=("mock",)), outcome.append)
            await pilot.pause()
            assert isinstance(app.screen, NewWorldScreen)
            await pilot.click("#new-world-cancel")
            await pilot.pause()

    asyncio.run(scenario())
    assert outcome == [None]


def test_edit_object_modal_cancel_returns_none(tmp_path) -> None:
    pytest.importorskip("textual")

    from worldforge.harness.tui import EditObjectScreen, TheWorldHarnessApp

    outcome: list[object | None] = []

    async def scenario() -> None:
        app = TheWorldHarnessApp(state_dir=tmp_path)
        async with app.run_test(size=(130, 42)) as pilot:
            await app.push_screen(EditObjectScreen(), outcome.append)
            await pilot.pause()
            assert isinstance(app.screen, EditObjectScreen)
            await pilot.click("#edit-object-cancel")
            await pilot.pause()

    asyncio.run(scenario())
    assert outcome == [None]


def test_edit_object_modal_invalid_position_blocks_save(tmp_path) -> None:
    pytest.importorskip("textual")

    from textual.widgets import Input, Static

    from worldforge.harness.tui import EditObjectScreen, TheWorldHarnessApp

    async def scenario() -> None:
        app = TheWorldHarnessApp(state_dir=tmp_path)
        async with app.run_test(size=(130, 42)) as pilot:
            await app.push_screen(EditObjectScreen(), lambda _: None)
            await pilot.pause()
            assert isinstance(app.screen, EditObjectScreen)
            app.screen.query_one("#edit-object-x", Input).value = "not-a-number"
            await pilot.click("#edit-object-save")
            await pilot.pause()
            error = app.screen.query_one("#edit-object-error", Static)
            assert "hidden" not in error.classes

    asyncio.run(scenario())


def test_worlds_close_dirty_requires_confirm(tmp_path) -> None:
    pytest.importorskip("textual")

    from textual.widgets import Input

    from worldforge.harness.tui import (
        ConfirmDeleteScreen,
        TheWorldHarnessApp,
        WorldEditScreen,
        WorldsScreen,
    )

    _seed_world(tmp_path, name="lab", world_id="lab-close")

    async def scenario() -> None:
        app = TheWorldHarnessApp(state_dir=tmp_path, initial_screen="worlds")
        async with app.run_test(size=(130, 42)) as pilot:
            await pilot.pause()
            await pilot.pause()
            assert isinstance(app.screen, WorldsScreen)
            await pilot.press("enter")
            await pilot.pause()
            assert isinstance(app.screen, WorldEditScreen)
            # Make the screen dirty without saving.
            app.screen.query_one("#edit-name", Input).value = "kitchen"
            await pilot.pause()
            # Pressing Esc on a dirty screen opens the discard confirmation.
            await pilot.press("escape")
            await pilot.pause()
            assert isinstance(app.screen, ConfirmDeleteScreen)
            await pilot.press("escape")
            await pilot.pause()
            # Cancelling discard returns to the edit screen.
            assert isinstance(app.screen, WorldEditScreen)

    asyncio.run(scenario())


def test_worlds_filter_substring_and_clear(tmp_path) -> None:
    pytest.importorskip("textual")

    from textual.widgets import DataTable, Input

    from worldforge.harness.tui import TheWorldHarnessApp, WorldsScreen

    _seed_world(tmp_path, name="alpha", world_id="alpha")
    _seed_world(tmp_path, name="beta", world_id="beta")

    async def scenario() -> None:
        app = TheWorldHarnessApp(state_dir=tmp_path, initial_screen="worlds")
        async with app.run_test(size=(130, 42)) as pilot:
            await pilot.pause()
            await pilot.pause()
            assert isinstance(app.screen, WorldsScreen)
            filt = app.screen.query_one("#worlds-filter", Input)
            filt.value = "alp"
            await pilot.pause()
            table = app.screen.query_one("#worlds-table", DataTable)
            assert table.row_count == 1
            # Clear via screen action and confirm all rows reappear.
            app.screen.action_clear_filter()
            await pilot.pause()
            assert table.row_count == 2

    asyncio.run(scenario())


def test_confirm_delete_returns_true_on_enter(tmp_path) -> None:
    pytest.importorskip("textual")

    from worldforge.harness.tui import ConfirmDeleteScreen, TheWorldHarnessApp

    outcome: list[bool | None] = []

    async def scenario() -> None:
        app = TheWorldHarnessApp(state_dir=tmp_path)
        async with app.run_test(size=(130, 42)) as pilot:
            await app.push_screen(ConfirmDeleteScreen(), outcome.append)
            await pilot.pause()
            assert isinstance(app.screen, ConfirmDeleteScreen)
            await pilot.click("#confirm-accept")
            await pilot.pause()

    asyncio.run(scenario())
    assert outcome == [True]


# ---------------------------------------------------------------------------
# M3-M5 — Providers, eval, benchmark, recents
# ---------------------------------------------------------------------------


def test_providers_screen_runs_real_mock_predict(tmp_path) -> None:
    pytest.importorskip("textual")

    from textual.widgets import DataTable

    from worldforge.harness.tui import ProvidersScreen, TheWorldHarnessApp
    from worldforge.models import CAPABILITY_NAMES

    async def scenario() -> None:
        app = TheWorldHarnessApp(state_dir=tmp_path, initial_screen="providers")
        async with app.run_test(size=(130, 42)) as pilot:
            await pilot.pause()
            assert isinstance(app.screen, ProvidersScreen)
            table = app.screen.query_one("#providers-table", DataTable)
            assert table.row_count == 1
            assert len(table.columns) == len(CAPABILITY_NAMES) + 1
            await pilot.press("p")
            for _ in range(8):
                await pilot.pause()
                if app.screen.running_operation == "done":
                    break
            assert app.screen.running_operation == "done"
            assert app.screen._last_call_summary["mock"]["phase"] == "success"

    asyncio.run(scenario())


def test_providers_register_modal_adds_mock_variant(tmp_path) -> None:
    pytest.importorskip("textual")

    from textual.widgets import DataTable, Input

    from worldforge.harness.tui import ProvidersScreen, RegisterProviderModal, TheWorldHarnessApp

    async def scenario() -> None:
        app = TheWorldHarnessApp(state_dir=tmp_path, initial_screen="providers")
        async with app.run_test(size=(130, 42)) as pilot:
            await pilot.pause()
            assert isinstance(app.screen, ProvidersScreen)
            await pilot.press("r")
            await pilot.pause()
            assert isinstance(app.screen, RegisterProviderModal)
            app.screen.query_one("#register-provider-name", Input).value = "mock-alt"
            await pilot.click("#register-provider-submit")
            for _ in range(4):
                await pilot.pause()
            assert isinstance(app.screen, ProvidersScreen)
            table = app.screen.query_one("#providers-table", DataTable)
            assert table.row_count == 2
            assert app.current_provider == "mock-alt"

    asyncio.run(scenario())


def test_eval_screen_planning_against_mock_writes_report(tmp_path) -> None:
    pytest.importorskip("textual")

    from worldforge.harness.tui import EvalScreen, RunInspectorScreen, TheWorldHarnessApp

    async def scenario() -> None:
        app = TheWorldHarnessApp(state_dir=tmp_path, initial_screen="eval")
        async with app.run_test(size=(130, 42)) as pilot:
            await pilot.pause()
            assert isinstance(app.screen, EvalScreen)
            await pilot.press("r")
            for _ in range(12):
                await pilot.pause()
                if isinstance(app.screen, RunInspectorScreen):
                    break
            assert isinstance(app.screen, RunInspectorScreen)
            assert app.screen.last_run is not None
            assert app.screen.last_run.kind == "eval"
            assert app.screen.last_run.report_path is not None
            assert app.screen.last_run.report_path.exists()

    asyncio.run(scenario())


def test_benchmark_screen_streams_progress_and_writes_report(tmp_path) -> None:
    pytest.importorskip("textual")

    from textual.widgets import Input

    from worldforge.harness.tui import BenchmarkScreen, RunInspectorScreen, TheWorldHarnessApp

    async def scenario() -> None:
        app = TheWorldHarnessApp(state_dir=tmp_path, initial_screen="benchmark")
        async with app.run_test(size=(130, 42)) as pilot:
            await pilot.pause()
            assert isinstance(app.screen, BenchmarkScreen)
            app.screen.query_one("#benchmark-iterations", Input).value = "2"
            await pilot.press("r")
            for _ in range(12):
                await pilot.pause()
                if isinstance(app.screen, RunInspectorScreen):
                    break
            assert isinstance(app.screen, RunInspectorScreen)
            assert app.screen.last_run is not None
            assert app.screen.last_run.kind == "benchmark"
            assert app.screen.last_run.report_path is not None
            assert app.screen.last_run.report_path.exists()

    asyncio.run(scenario())


def test_home_recent_lists_worlds_and_reports(tmp_path) -> None:
    pytest.importorskip("textual")

    from textual.widgets import Static

    from worldforge import WorldForge
    from worldforge.harness.flows import eval_run_artifacts, write_report
    from worldforge.harness.tui import TheWorldHarnessApp

    _seed_world(tmp_path, name="recent-lab", world_id="recent-lab")
    forge = WorldForge(state_dir=tmp_path)
    artifacts, _report = eval_run_artifacts(forge, "planning", "mock")
    report_path = write_report(forge, "eval-planning", artifacts)

    async def scenario() -> None:
        app = TheWorldHarnessApp(state_dir=tmp_path)
        async with app.run_test(size=(130, 42)) as pilot:
            await pilot.pause()
            recent = app.screen.query_one("#home-recent", Static)
            text = recent.render().plain  # type: ignore[union-attr]
            assert "recent-lab" in text
            assert report_path.name in text

    asyncio.run(scenario())


def test_dynamic_command_provider_finds_world_provider_and_run(tmp_path) -> None:
    pytest.importorskip("textual")

    from worldforge import WorldForge
    from worldforge.harness.flows import eval_run_artifacts, write_report
    from worldforge.harness.tui import TheWorldHarnessApp, WorldForgeCommandProvider

    _seed_world(tmp_path, name="palette-lab", world_id="palette-lab")
    forge = WorldForge(state_dir=tmp_path)
    artifacts, _report = eval_run_artifacts(forge, "planning", "mock")
    report_path = write_report(forge, "eval-planning", artifacts)

    async def scenario() -> None:
        app = TheWorldHarnessApp(state_dir=tmp_path)
        async with app.run_test(size=(130, 42)):
            provider = WorldForgeCommandProvider(app.screen)
            await provider.startup()
            world_hits = [hit async for hit in provider.search("palette")]
            provider_hits = [hit async for hit in provider.search("mock")]
            run_hits = [hit async for hit in provider.search(report_path.name[:12])]
            assert any(hit.text == "World: palette-lab" for hit in world_hits)
            assert any(hit.text == "Provider: mock" for hit in provider_hits)
            assert any(hit.text and hit.text.startswith("Run: ") for hit in run_hits)

    asyncio.run(scenario())


def test_app_routes_new_harness_screens_and_palette_callbacks(tmp_path) -> None:
    pytest.importorskip("textual")

    from worldforge import WorldForge
    from worldforge.harness.flows import eval_run_artifacts, write_report
    from worldforge.harness.tui import (
        EvalScreen,
        HelpScreen,
        ProvidersScreen,
        RunInspectorScreen,
        TheWorldHarnessApp,
        WorldsScreen,
    )

    _seed_world(tmp_path, name="route-lab", world_id="route-lab")
    forge = WorldForge(state_dir=tmp_path)
    artifacts, _report = eval_run_artifacts(forge, "planning", "mock")
    report_path = write_report(forge, "eval-planning", artifacts)

    async def scenario() -> None:
        app = TheWorldHarnessApp(state_dir=tmp_path)
        async with app.run_test(size=(130, 42)) as pilot:
            await pilot.pause()
            app.action_switch_screen("providers")
            await pilot.pause()
            assert isinstance(app.screen, ProvidersScreen)
            app.action_switch_screen("eval")
            await pilot.pause()
            assert isinstance(app.screen, EvalScreen)
            app._open_world_from_palette("route-lab")
            await pilot.pause()
            assert isinstance(app.screen, WorldsScreen)
            assert app.screen.selected_world == "route-lab"
            app._open_provider_from_palette("mock")
            await pilot.pause()
            assert isinstance(app.screen, ProvidersScreen)
            assert app.current_provider == "mock"
            app._open_report_path(report_path)
            await pilot.pause()
            assert isinstance(app.screen, RunInspectorScreen)
            assert app.screen.last_run is not None
            assert app.screen.last_run.kind == "eval"
            app.action_show_help()
            await pilot.pause()
            assert isinstance(app.screen, HelpScreen)
            app.action_switch_screen("home")
            await pilot.pause()
            assert not isinstance(app.screen, HelpScreen)

    asyncio.run(scenario())


def test_run_flow_command_waits_for_run_inspector_mount(tmp_path) -> None:
    pytest.importorskip("textual")

    from worldforge.harness.tui import RunInspectorScreen, TheWorldHarnessApp

    async def scenario() -> None:
        app = TheWorldHarnessApp(state_dir=tmp_path, step_delay=0.0)
        async with app.run_test(size=(130, 42)) as pilot:
            await pilot.pause()
            command = app._make_run_flow_command("leworldmodel")
            await command()
            assert isinstance(app.screen, RunInspectorScreen)
            assert app.screen.last_run is not None
            assert app.screen.last_run.flow.id == "leworldmodel"

    asyncio.run(scenario())


def test_run_flow_command_replaces_report_inspector_view(tmp_path) -> None:
    pytest.importorskip("textual")

    from dataclasses import replace

    from worldforge.harness.flows import run_flow
    from worldforge.harness.tui import RunInspectorScreen, TheWorldHarnessApp

    async def scenario() -> None:
        app = TheWorldHarnessApp(state_dir=tmp_path, step_delay=0.0)
        report_run = replace(
            run_flow("leworldmodel", state_dir=tmp_path),
            kind="benchmark",
            report_path=tmp_path / "benchmark.json",
            artifacts={"json": "{}"},
        )
        async with app.run_test(size=(130, 42)) as pilot:
            await app.push_screen(RunInspectorScreen(state_dir=tmp_path, run=report_run))
            await pilot.pause()
            assert isinstance(app.screen, RunInspectorScreen)
            assert not app.screen.can_run_flows

            command = app._make_run_flow_command("leworldmodel")
            await command()

            assert isinstance(app.screen, RunInspectorScreen)
            assert app.screen.can_run_flows
            assert app.screen.last_run is not None
            assert app.screen.last_run.flow.id == "leworldmodel"

    asyncio.run(scenario())

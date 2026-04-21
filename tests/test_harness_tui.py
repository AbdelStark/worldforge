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
            assert app.theme == "worldforge-dark"

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


def test_delete_world_file_helper_validates_and_unlinks(tmp_path) -> None:
    pytest.importorskip("textual")

    import pytest as _pytest

    from worldforge import WorldForge, WorldForgeError, WorldStateError
    from worldforge.harness.tui import _delete_world_file

    forge = WorldForge(state_dir=tmp_path)
    world = forge.create_world("lab", provider="mock")
    forge.save_world(world)
    _delete_world_file(tmp_path, world.id)
    assert forge.list_worlds() == []

    with _pytest.raises(WorldForgeError):
        _delete_world_file(tmp_path, "../escape")

    with _pytest.raises(WorldStateError):
        _delete_world_file(tmp_path, world.id)  # already gone


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

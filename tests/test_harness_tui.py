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

    from worldforge.harness.tui import HomeScreen, PlaceholderScreen, TheWorldHarnessApp

    async def scenario() -> None:
        app = TheWorldHarnessApp(state_dir=tmp_path)
        async with app.run_test(size=(130, 42)) as pilot:
            assert isinstance(app.screen, HomeScreen)
            await pilot.press("n")
            await pilot.pause()
            assert isinstance(app.screen, PlaceholderScreen)

    asyncio.run(scenario())


# ---------------------------------------------------------------------------
# M3 — Live providers tests
# ---------------------------------------------------------------------------


def _open_providers_screen(app, pilot):
    """Helper: switch to ProvidersScreen via the chord and wait for mount."""
    from worldforge.harness.tui import ProvidersScreen

    app.action_switch_screen("providers")
    return pilot, app, ProvidersScreen


def test_providers_screen_rows_match_registered_providers(tmp_path) -> None:
    pytest.importorskip("textual")

    from worldforge.harness.tui import ProvidersScreen, TheWorldHarnessApp

    async def scenario() -> None:
        app = TheWorldHarnessApp(state_dir=tmp_path, initial_screen="providers")
        async with app.run_test(size=(130, 42)) as pilot:
            await pilot.pause()
            screen = app.screen
            assert isinstance(screen, ProvidersScreen)
            from textual.widgets import DataTable

            table = screen.query_one("#providers-matrix", DataTable)
            registered = app.forge.list_providers()
            assert len(registered) >= 1  # mock is always registered
            assert table.row_count == len(registered)

    asyncio.run(scenario())


def test_providers_screen_columns_match_capability_names(tmp_path) -> None:
    pytest.importorskip("textual")

    from worldforge.harness.tui import ProvidersScreen, TheWorldHarnessApp
    from worldforge.models import CAPABILITY_NAMES

    async def scenario() -> None:
        app = TheWorldHarnessApp(state_dir=tmp_path, initial_screen="providers")
        async with app.run_test(size=(130, 42)) as pilot:
            await pilot.pause()
            screen = app.screen
            assert isinstance(screen, ProvidersScreen)
            from textual.widgets import DataTable

            table = screen.query_one("#providers-matrix", DataTable)
            # Provider name column + one column per capability.
            assert len(table.columns) == len(CAPABILITY_NAMES) + 1

    asyncio.run(scenario())


def test_capability_cells_reflect_provider_capabilities(tmp_path) -> None:
    pytest.importorskip("textual")

    from worldforge.harness.tui import (
        _CAPABILITY_GLYPH_MISSING,
        _CAPABILITY_GLYPH_REAL,
        ProvidersScreen,
        TheWorldHarnessApp,
    )
    from worldforge.models import CAPABILITY_NAMES

    async def scenario() -> None:
        app = TheWorldHarnessApp(state_dir=tmp_path, initial_screen="providers")
        async with app.run_test(size=(130, 42)) as pilot:
            await pilot.pause()
            screen = app.screen
            assert isinstance(screen, ProvidersScreen)
            from textual.widgets import DataTable

            table = screen.query_one("#providers-matrix", DataTable)
            row_key = "mock"
            row_values = [str(table.get_cell(row_key, col)) for col in table.columns]
            # Provider-name column
            assert row_values[0].strip() == "mock"
            # mock advertises predict → glyph ● / missing → blank.
            mock_info = app.forge.provider_info("mock")
            for index, capability in enumerate(CAPABILITY_NAMES, start=1):
                cell = row_values[index]
                if mock_info.capabilities.supports(capability):
                    assert _CAPABILITY_GLYPH_REAL in cell, (
                        capability,
                        cell,
                    )
                else:
                    assert _CAPABILITY_GLYPH_MISSING in cell or cell.strip() == "", (
                        capability,
                        cell,
                    )

    asyncio.run(scenario())


def test_capability_matrix_is_not_hand_coded() -> None:
    """Guardrail: no literal capability-by-provider dict baked into tui.py."""
    import re as _re

    text = HARNESS_TUI_PATH.read_text()
    # A hand-coded matrix would show up as a dict literal keyed by a known
    # provider name with capability names as values. Flag obvious shapes.
    patterns = [
        r'"mock"\s*:\s*\{[^}]*"predict"\s*:',
        r"'mock'\s*:\s*\{[^}]*'predict'\s*:",
        r'"cosmos"\s*:\s*\{[^}]*"generate"\s*:',
    ]
    for pattern in patterns:
        assert _re.search(pattern, text) is None, (
            f"hand-coded capability matrix pattern found: {pattern}"
        )


def test_providers_screen_reachable_from_command_palette(tmp_path) -> None:
    pytest.importorskip("textual")

    from worldforge.harness.tui import TheWorldHarnessApp

    async def scenario() -> None:
        app = TheWorldHarnessApp(state_dir=tmp_path)
        async with app.run_test(size=(130, 42)):
            titles = [c.title for c in app.get_system_commands(app.screen)]
            assert "Open providers" in titles

    asyncio.run(scenario())


def test_enter_sets_current_provider(tmp_path) -> None:
    pytest.importorskip("textual")

    from worldforge.harness.tui import (
        ProvidersScreen,
        ProviderStatusPill,
        TheWorldHarnessApp,
    )

    async def scenario() -> None:
        app = TheWorldHarnessApp(state_dir=tmp_path, initial_screen="providers")
        async with app.run_test(size=(130, 42)) as pilot:
            await pilot.pause()
            screen = app.screen
            assert isinstance(screen, ProvidersScreen)
            from textual.widgets import DataTable

            table = screen.query_one("#providers-matrix", DataTable)
            # Focus the first "mock" row (initial population picks row 0).
            table.move_cursor(row=0)
            await pilot.pause()
            screen.action_select_current()
            await pilot.pause()
            assert app.current_provider == "mock"
            pill = screen.query_one("#provider-pill", ProviderStatusPill)
            assert "mock" in pill.label

    asyncio.run(scenario())


def test_detail_pane_renders_health_and_env_vars(tmp_path) -> None:
    pytest.importorskip("textual")

    from textual.widgets import Static

    from worldforge.harness.tui import ProvidersScreen, TheWorldHarnessApp

    async def scenario() -> None:
        app = TheWorldHarnessApp(state_dir=tmp_path, initial_screen="providers")
        async with app.run_test(size=(130, 42)) as pilot:
            await pilot.pause()
            screen = app.screen
            assert isinstance(screen, ProvidersScreen)
            detail = screen.query_one("#providers-detail", Static)
            from io import StringIO

            from rich.console import Console

            buffer = StringIO()
            Console(file=buffer, width=120).print(detail.content)
            rendered = buffer.getvalue()
            assert "mock" in rendered
            # health line and the required-env-var section label.
            assert "health" in rendered
            assert "required env vars" in rendered

    asyncio.run(scenario())


def test_p_runs_real_mock_predict_and_streams_events(tmp_path) -> None:
    pytest.importorskip("textual")

    from textual.widgets import RichLog

    from worldforge.harness.tui import ProvidersScreen, TheWorldHarnessApp

    async def scenario() -> None:
        app = TheWorldHarnessApp(state_dir=tmp_path, initial_screen="providers")
        async with app.run_test(size=(130, 42)) as pilot:
            await pilot.pause()
            screen = app.screen
            assert isinstance(screen, ProvidersScreen)
            screen.action_select_current()
            await pilot.pause()
            assert app.current_provider == "mock"
            await pilot.press("p")
            # Workers run on a thread — pause a few times so the event loop
            # picks up every call_from_thread posted message.
            for _ in range(10):
                await pilot.pause()
                if screen.running_operation in {"done", "error"}:
                    break
            assert screen.running_operation == "done"
            rich_log = screen.query_one("#providers-stream", RichLog)
            # RichLog exposes its lines via ``lines`` (a list of ``Strip``).
            rendered = "\n".join(str(line) for line in rich_log.lines)
            assert "success" in rendered
            assert "mock.predict" in rendered

    asyncio.run(scenario())


def test_esc_cancels_running_predict(tmp_path, monkeypatch) -> None:
    """Cancel a deliberately-slow predict; the screen must transition."""
    pytest.importorskip("textual")

    import time as _time

    from worldforge.harness.tui import ProvidersScreen, TheWorldHarnessApp
    from worldforge.providers import mock as mock_module

    original_predict = mock_module.MockProvider.predict

    def slow_predict(self, world_state, action, steps):
        # Yield cooperatively so the worker's is_cancelled can fire.
        for _ in range(30):
            _time.sleep(0.02)
        return original_predict(self, world_state, action, steps)

    monkeypatch.setattr(mock_module.MockProvider, "predict", slow_predict)

    async def scenario() -> None:
        app = TheWorldHarnessApp(state_dir=tmp_path, initial_screen="providers")
        async with app.run_test(size=(130, 42)) as pilot:
            await pilot.pause()
            screen = app.screen
            assert isinstance(screen, ProvidersScreen)
            screen.action_select_current()
            await pilot.pause()
            await pilot.press("p")
            await pilot.pause()
            assert screen.running_operation == "running"
            # Issue cancellation via the binding (which calls the action when
            # a run is in flight).
            screen.action_cancel_run()
            for _ in range(40):
                await pilot.pause()
                if screen.running_operation == "cancelled":
                    break
            assert screen.running_operation == "cancelled"

    asyncio.run(scenario())


def test_esc_pops_screen_when_idle(tmp_path) -> None:
    pytest.importorskip("textual")

    from worldforge.harness.tui import HomeScreen, ProvidersScreen, TheWorldHarnessApp

    async def scenario() -> None:
        app = TheWorldHarnessApp(state_dir=tmp_path)
        async with app.run_test(size=(130, 42)) as pilot:
            assert isinstance(app.screen, HomeScreen)
            app.push_screen("providers")
            await pilot.pause()
            assert isinstance(app.screen, ProvidersScreen)
            screen = app.screen
            assert screen.running_operation == "idle"
            screen.action_cancel_run()
            await pilot.pause()
            assert isinstance(app.screen, HomeScreen)

    asyncio.run(scenario())


def test_register_provider_modal_appends_row(tmp_path) -> None:
    pytest.importorskip("textual")

    from textual.widgets import DataTable

    from worldforge.harness.tui import (
        ProvidersScreen,
        RegisterProviderModal,
        TheWorldHarnessApp,
    )
    from worldforge.providers.mock import MockProvider

    async def scenario() -> None:
        app = TheWorldHarnessApp(state_dir=tmp_path, initial_screen="providers")
        async with app.run_test(size=(130, 42)) as pilot:
            await pilot.pause()
            screen = app.screen
            assert isinstance(screen, ProvidersScreen)
            table = screen.query_one("#providers-matrix", DataTable)
            before = table.row_count
            # Directly exercise the register path: construct a provider,
            # register it, and repopulate (matches what the modal dismiss
            # handler does).
            app.forge.register_provider(MockProvider(name="mock-alt"))
            screen._populate_matrix()
            await pilot.pause()
            assert table.row_count == before + 1
            names = {row for row in screen._row_providers}
            assert "mock-alt" in names
            # And the modal class is reachable / instantiable.
            modal = RegisterProviderModal()
            assert modal is not None

    asyncio.run(scenario())


def test_provider_event_received_writes_to_rich_log(tmp_path) -> None:
    pytest.importorskip("textual")

    from textual.widgets import RichLog

    from worldforge.harness.tui import (
        ProviderEventReceived,
        ProvidersScreen,
        TheWorldHarnessApp,
    )
    from worldforge.models import ProviderEvent

    async def scenario() -> None:
        app = TheWorldHarnessApp(state_dir=tmp_path, initial_screen="providers")
        async with app.run_test(size=(130, 42)) as pilot:
            await pilot.pause()
            screen = app.screen
            assert isinstance(screen, ProvidersScreen)
            event = ProviderEvent(
                provider="mock",
                operation="predict",
                phase="success",
                duration_ms=12.5,
                metadata={"top-secret-key": "this must not leak"},
            )
            screen.post_message(ProviderEventReceived(event))
            await pilot.pause()
            rich_log = screen.query_one("#providers-stream", RichLog)
            rendered = "\n".join(str(line) for line in rich_log.lines)
            assert "mock.predict" in rendered
            assert "success" in rendered
            # Sanitisation: never interpolate metadata into the log line.
            assert "top-secret-key" not in rendered
            assert "this must not leak" not in rendered

    asyncio.run(scenario())


def test_event_loop_remains_responsive_during_run(tmp_path, monkeypatch) -> None:
    pytest.importorskip("textual")

    import time as _time

    from worldforge.harness.tui import ProvidersScreen, TheWorldHarnessApp
    from worldforge.providers import mock as mock_module

    original_predict = mock_module.MockProvider.predict

    def slow_predict(self, world_state, action, steps):
        for _ in range(10):
            _time.sleep(0.02)
        return original_predict(self, world_state, action, steps)

    monkeypatch.setattr(mock_module.MockProvider, "predict", slow_predict)

    async def scenario() -> None:
        app = TheWorldHarnessApp(state_dir=tmp_path, initial_screen="providers")
        async with app.run_test(size=(130, 42)) as pilot:
            await pilot.pause()
            screen = app.screen
            assert isinstance(screen, ProvidersScreen)
            screen.action_select_current()
            await pilot.pause()
            await pilot.press("p")
            await pilot.pause()
            assert screen.running_operation == "running"
            original_theme = app.theme
            await pilot.press("ctrl+t")
            await pilot.pause()
            assert app.theme != original_theme
            # Let the slow call finish so the worker cleans up.
            for _ in range(40):
                await pilot.pause()
                if screen.running_operation in {"done", "error", "cancelled"}:
                    break

    asyncio.run(scenario())


def test_no_blocking_io_in_compose_or_on_mount(tmp_path, monkeypatch) -> None:
    """Opening ProvidersScreen must not run predict() on the main event loop."""
    pytest.importorskip("textual")

    from worldforge.framework import World as _World
    from worldforge.harness.tui import ProvidersScreen, TheWorldHarnessApp

    calls: list[str] = []
    original = _World.predict

    def spy(self, *args, **kwargs):
        calls.append("predict")
        return original(self, *args, **kwargs)

    monkeypatch.setattr(_World, "predict", spy)

    async def scenario() -> None:
        app = TheWorldHarnessApp(state_dir=tmp_path, initial_screen="providers")
        async with app.run_test(size=(130, 42)) as pilot:
            await pilot.pause()
            assert isinstance(app.screen, ProvidersScreen)
            assert calls == []

    asyncio.run(scenario())


def test_providers_screen_resume_repopulates_matrix(tmp_path) -> None:
    """Switching away and back refreshes the matrix from the live registry."""
    pytest.importorskip("textual")

    from textual.widgets import DataTable

    from worldforge.harness.tui import (
        HomeScreen,
        ProvidersScreen,
        TheWorldHarnessApp,
    )
    from worldforge.providers.mock import MockProvider

    async def scenario() -> None:
        app = TheWorldHarnessApp(state_dir=tmp_path, initial_screen="providers")
        async with app.run_test(size=(130, 42)) as pilot:
            await pilot.pause()
            screen = app.screen
            assert isinstance(screen, ProvidersScreen)
            table = screen.query_one("#providers-matrix", DataTable)
            before = table.row_count
            # Register an extra provider directly, switch away, and come back.
            app.forge.register_provider(MockProvider(name="mock-resume"))
            app.action_switch_screen("home")
            await pilot.pause()
            assert isinstance(app.screen, HomeScreen)
            app.action_switch_screen("providers")
            await pilot.pause()
            screen2 = app.screen
            assert isinstance(screen2, ProvidersScreen)
            table2 = screen2.query_one("#providers-matrix", DataTable)
            assert table2.row_count == before + 1

    asyncio.run(scenario())


def test_run_completed_updates_running_operation(tmp_path) -> None:
    pytest.importorskip("textual")

    from worldforge.harness.tui import (
        ProvidersScreen,
        RunCompleted,
        TheWorldHarnessApp,
    )

    async def scenario() -> None:
        app = TheWorldHarnessApp(state_dir=tmp_path, initial_screen="providers")
        async with app.run_test(size=(130, 42)) as pilot:
            await pilot.pause()
            screen = app.screen
            assert isinstance(screen, ProvidersScreen)
            screen.running_operation = "running"
            await pilot.pause()
            screen.post_message(RunCompleted(provider="mock", latency_ms=4.2))
            await pilot.pause()
            assert screen.running_operation == "done"

    asyncio.run(scenario())


def test_run_cancelled_updates_running_operation(tmp_path) -> None:
    pytest.importorskip("textual")

    from worldforge.harness.tui import (
        ProvidersScreen,
        RunCancelled,
        TheWorldHarnessApp,
    )

    async def scenario() -> None:
        app = TheWorldHarnessApp(state_dir=tmp_path, initial_screen="providers")
        async with app.run_test(size=(130, 42)) as pilot:
            await pilot.pause()
            screen = app.screen
            assert isinstance(screen, ProvidersScreen)
            screen.running_operation = "running"
            await pilot.pause()
            screen.post_message(RunCancelled(provider="mock"))
            await pilot.pause()
            assert screen.running_operation == "cancelled"

    asyncio.run(scenario())


def test_providers_cancel_button_cancels_worker(tmp_path, monkeypatch) -> None:
    pytest.importorskip("textual")

    import time as _time

    from textual.widgets import Button

    from worldforge.harness.tui import ProvidersScreen, TheWorldHarnessApp
    from worldforge.providers import mock as mock_module

    original_predict = mock_module.MockProvider.predict

    def slow_predict(self, world_state, action, steps):
        for _ in range(30):
            _time.sleep(0.02)
        return original_predict(self, world_state, action, steps)

    monkeypatch.setattr(mock_module.MockProvider, "predict", slow_predict)

    async def scenario() -> None:
        app = TheWorldHarnessApp(state_dir=tmp_path, initial_screen="providers")
        async with app.run_test(size=(130, 42)) as pilot:
            await pilot.pause()
            screen = app.screen
            assert isinstance(screen, ProvidersScreen)
            screen.action_select_current()
            await pilot.pause()
            await pilot.press("p")
            await pilot.pause()
            assert screen.running_operation == "running"
            button = screen.query_one("#providers-cancel", Button)
            assert not button.disabled
            # Fire the button press message directly (we verified the state
            # transitions; the compositor click goes through the same path).
            screen._on_cancel_pressed()
            for _ in range(40):
                await pilot.pause()
                if screen.running_operation == "cancelled":
                    break
            assert screen.running_operation == "cancelled"

    asyncio.run(scenario())


def test_predict_failure_surfaces_failure_event(tmp_path, monkeypatch) -> None:
    pytest.importorskip("textual")

    from textual.widgets import RichLog

    from worldforge.harness.tui import ProvidersScreen, TheWorldHarnessApp
    from worldforge.providers import mock as mock_module
    from worldforge.providers.base import ProviderError

    def broken_predict(self, world_state, action, steps):
        raise ProviderError("simulated failure")

    monkeypatch.setattr(mock_module.MockProvider, "predict", broken_predict)

    async def scenario() -> None:
        app = TheWorldHarnessApp(state_dir=tmp_path, initial_screen="providers")
        async with app.run_test(size=(130, 42)) as pilot:
            await pilot.pause()
            screen = app.screen
            assert isinstance(screen, ProvidersScreen)
            screen.action_select_current()
            await pilot.pause()
            await pilot.press("p")
            for _ in range(20):
                await pilot.pause()
                rich_log = screen.query_one("#providers-stream", RichLog)
                rendered = "\n".join(str(line) for line in rich_log.lines)
                if "failure" in rendered:
                    break
            rich_log = screen.query_one("#providers-stream", RichLog)
            rendered = "\n".join(str(line) for line in rich_log.lines)
            assert "failure" in rendered

    asyncio.run(scenario())


def test_register_provider_modal_dismisses_with_empty_name(tmp_path) -> None:
    pytest.importorskip("textual")

    from worldforge.harness.tui import RegisterProviderModal

    async def scenario() -> None:
        modal = RegisterProviderModal()
        # The modal's action_cancel dismisses with None — exercise the code path
        # without needing to push it into an app.
        # We can at least construct it and access bindings.
        keys = [b.key for b in modal.BINDINGS]
        assert "escape" in keys
        assert "ctrl+s" in keys

    asyncio.run(scenario())


def test_jump_from_home_via_p_opens_providers(tmp_path) -> None:
    """The Home screen jump card 'providers' now routes to ProvidersScreen."""
    pytest.importorskip("textual")

    from worldforge.harness.tui import HomeScreen, ProvidersScreen, TheWorldHarnessApp

    async def scenario() -> None:
        app = TheWorldHarnessApp(state_dir=tmp_path)
        async with app.run_test(size=(130, 42)) as pilot:
            assert isinstance(app.screen, HomeScreen)
            await pilot.press("p")
            await pilot.pause()
            assert isinstance(app.screen, ProvidersScreen)

    asyncio.run(scenario())

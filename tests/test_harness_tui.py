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
        app = TheWorldHarnessApp(initial_flow_id="leworldmodel", state_dir=tmp_path)
        async with app.run_test(size=(130, 42)) as pilot:
            crumb = app.query_one("#breadcrumb", Breadcrumb)
            assert crumb.path == ("worldforge", "LeWorldModel")
            await pilot.press("2")
            await pilot.pause()
            assert crumb.path == ("worldforge", "LeRobot")

    asyncio.run(scenario())


def test_harness_status_pill_reflects_selected_flow_provider(tmp_path) -> None:
    pytest.importorskip("textual")

    from worldforge.harness.tui import ProviderStatusPill, TheWorldHarnessApp

    async def scenario() -> None:
        app = TheWorldHarnessApp(initial_flow_id="leworldmodel", state_dir=tmp_path)
        async with app.run_test(size=(130, 42)) as pilot:
            pill = app.query_one("#provider-pill", ProviderStatusPill)
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

    from worldforge.harness.tui import TheWorldHarnessApp

    async def scenario() -> None:
        app = TheWorldHarnessApp(
            initial_flow_id="leworldmodel",
            state_dir=tmp_path,
            step_delay=0.0,
        )
        async with app.run_test(size=(130, 42)) as pilot:
            await pilot.press("r")
            await pilot.pause()
            assert app.last_run is not None
            assert app.last_run.flow.id == "leworldmodel"
            assert app.last_run.summary["selected_candidate_index"] == 1
            assert app.query_one("#inspector") is not None

    asyncio.run(scenario())


def test_the_world_harness_app_switches_to_lerobot_flow(tmp_path) -> None:
    pytest.importorskip("textual")

    from worldforge.harness.tui import TheWorldHarnessApp

    async def scenario() -> None:
        app = TheWorldHarnessApp(
            initial_flow_id="leworldmodel",
            state_dir=tmp_path,
            step_delay=0.0,
        )
        async with app.run_test(size=(130, 42)) as pilot:
            await pilot.press("2")
            await pilot.press("r")
            await pilot.pause()
            assert app.last_run is not None
            assert app.last_run.flow.id == "lerobot"
            assert app.last_run.summary["policy_candidate_count"] == 3

    asyncio.run(scenario())


def test_the_world_harness_app_switches_to_diagnostics_flow(tmp_path) -> None:
    pytest.importorskip("textual")

    from worldforge.harness.tui import TheWorldHarnessApp

    async def scenario() -> None:
        app = TheWorldHarnessApp(
            initial_flow_id="leworldmodel",
            state_dir=tmp_path,
            step_delay=0.0,
        )
        async with app.run_test(size=(140, 44)) as pilot:
            await pilot.press("3")
            await pilot.press("r")
            await pilot.pause()
            assert app.last_run is not None
            assert app.last_run.flow.id == "diagnostics"
            assert app.last_run.summary["benchmark_operation_count"] == 5

    asyncio.run(scenario())

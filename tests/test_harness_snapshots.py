from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

SCREEN_CASES = (
    ("home", "home", "leworldmodel"),
    ("worlds", "worlds", "leworldmodel"),
    ("providers", "providers", "leworldmodel"),
    ("eval", "eval", "leworldmodel"),
    ("benchmark", "benchmark", "leworldmodel"),
    ("run-inspector", "run-inspector", "leworldmodel"),
    ("cosmos-policy", "run-inspector", "cosmos-policy"),
    ("diagnostics", "run-inspector", "diagnostics"),
)

TERMINAL_SIZES = ((100, 30), (120, 40), (160, 50))


def _seed_showcase_state(state_dir: Path) -> None:
    from worldforge import WorldForge
    from worldforge.harness.flows import eval_run_artifacts, write_report

    forge = WorldForge(state_dir=state_dir)
    world = forge.create_world("snapshot lab", provider="mock")
    world.id = "snapshot-lab"
    forge.save_world(world)
    artifacts, _report = eval_run_artifacts(forge, "planning", "mock")
    write_report(forge, "eval-planning", artifacts)


@pytest.mark.parametrize(("screen_id", "initial_screen", "flow_id"), SCREEN_CASES)
@pytest.mark.parametrize("terminal_size", TERMINAL_SIZES)
def test_harness_main_screens_export_svg_screenshots(
    tmp_path,
    screen_id: str,
    initial_screen: str,
    flow_id: str,
    terminal_size: tuple[int, int],
) -> None:
    pytest.importorskip("textual")

    from worldforge.harness.tui import TheWorldHarnessApp

    _seed_showcase_state(tmp_path)

    async def scenario() -> None:
        app = TheWorldHarnessApp(
            initial_flow_id=flow_id,
            initial_screen=initial_screen,  # type: ignore[arg-type]
            state_dir=tmp_path,
            step_delay=0.0,
        )
        async with app.run_test(size=terminal_size) as pilot:
            await pilot.pause()
            svg = app.export_screenshot(
                title=f"{screen_id}-{terminal_size[0]}x{terminal_size[1]}",
                simplify=True,
            )
        assert svg.startswith('<svg class="rich-terminal"')
        assert "Traceback" not in svg
        assert "NoMatches" not in svg
        assert len(svg) > 1000

    asyncio.run(scenario())

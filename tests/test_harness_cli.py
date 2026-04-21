from __future__ import annotations

import json
import sys

from worldforge.cli import main as worldforge_main
from worldforge.harness.cli import main as harness_main


def test_worldforge_harness_lists_flows_without_textual(monkeypatch, capsys) -> None:
    monkeypatch.setattr(sys, "argv", ["worldforge", "harness", "--list"])

    assert worldforge_main() == 0
    output = capsys.readouterr().out

    assert output.startswith("# TheWorldHarness Flows")
    assert "leworldmodel" in output
    assert "lerobot" in output
    assert "diagnostics" in output


def test_worldforge_harness_lists_json_without_textual(monkeypatch, capsys) -> None:
    monkeypatch.setattr(
        sys,
        "argv",
        ["worldforge", "harness", "--list", "--format", "json"],
    )

    assert worldforge_main() == 0
    payload = json.loads(capsys.readouterr().out)

    assert [flow["id"] for flow in payload] == ["leworldmodel", "lerobot", "diagnostics"]


def test_worldforge_harness_console_entry_lists_flows(capsys) -> None:
    assert harness_main(["--list"]) == 0
    assert "TheWorldHarness Flows" in capsys.readouterr().out


def test_launch_harness_passes_home_when_no_flow(monkeypatch) -> None:
    """No --flow → initial_screen='home', resolved_flow_id falls back to leworldmodel."""
    import pytest as _pytest

    _pytest.importorskip("rich")
    _pytest.importorskip("textual")

    captured: dict[str, object] = {}

    class _StubApp:
        def __init__(self, **kwargs: object) -> None:
            captured.update(kwargs)

        def run(self) -> None:
            return None

    import worldforge.harness.tui as tui

    monkeypatch.setattr(tui, "TheWorldHarnessApp", _StubApp)

    from worldforge.harness.cli import launch_harness

    rc = launch_harness(flow_id=None, state_dir=None, animate=False)
    assert rc == 0
    assert captured["initial_screen"] == "home"
    assert captured["initial_flow_id"] == "leworldmodel"


def test_launch_harness_passes_run_inspector_when_flow_supplied(monkeypatch) -> None:
    """--flow X → initial_screen='run-inspector', initial_flow_id=X."""
    import pytest as _pytest

    _pytest.importorskip("rich")
    _pytest.importorskip("textual")

    captured: dict[str, object] = {}

    class _StubApp:
        def __init__(self, **kwargs: object) -> None:
            captured.update(kwargs)

        def run(self) -> None:
            return None

    import worldforge.harness.tui as tui

    monkeypatch.setattr(tui, "TheWorldHarnessApp", _StubApp)

    from worldforge.harness.cli import launch_harness

    rc = launch_harness(flow_id="lerobot", state_dir=None, animate=True)
    assert rc == 0
    assert captured["initial_screen"] == "run-inspector"
    assert captured["initial_flow_id"] == "lerobot"

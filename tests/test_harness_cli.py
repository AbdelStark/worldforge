from __future__ import annotations

import json
import sys

import pytest

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


def test_worldforge_harness_lists_connector_readiness_without_textual(monkeypatch, capsys) -> None:
    for name in (
        "COSMOS_BASE_URL",
        "RUNWAYML_API_SECRET",
        "RUNWAY_API_SECRET",
        "LEWORLDMODEL_POLICY",
        "LEWM_POLICY",
        "GROOT_POLICY_HOST",
        "LEROBOT_POLICY_PATH",
        "LEROBOT_POLICY",
    ):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(
        sys,
        "argv",
        ["worldforge", "harness", "--connectors", "--format", "json"],
    )

    assert worldforge_main() == 0
    payload = {row["name"]: row for row in json.loads(capsys.readouterr().out)}

    assert set(payload) >= {
        "mock",
        "cosmos",
        "runway",
        "leworldmodel",
        "gr00t",
        "lerobot",
        "jepa",
        "genie",
    }
    assert payload["mock"]["status"] == "configured"
    assert payload["cosmos"]["status"] == "missing_credentials"
    assert payload["runway"]["missing_env_vars"] == ["RUNWAYML_API_SECRET"]
    assert payload["jepa"]["status"] == "scaffold"
    assert payload["genie"]["status"] == "scaffold"
    assert "worldforge-smoke-runway" in payload["runway"]["smoke_command"]


def test_connector_readiness_distinguishes_missing_dependency(monkeypatch, tmp_path) -> None:
    from worldforge import WorldForge
    from worldforge.harness.connectors import provider_connector_summaries

    monkeypatch.setenv("LEWORLDMODEL_POLICY", "demo/pusht")
    rows = {row.name: row for row in provider_connector_summaries(WorldForge(state_dir=tmp_path))}

    assert rows["leworldmodel"].status == "missing_dependency"
    assert "stable_worldmodel" in rows["leworldmodel"].optional_dependencies
    assert rows["leworldmodel"].missing_env_vars == ()


def test_launch_harness_passes_home_when_no_flow(monkeypatch) -> None:
    """No --flow → initial_screen='home', resolved_flow_id falls back to leworldmodel."""
    pytest.importorskip("rich")
    pytest.importorskip("textual")

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
    pytest.importorskip("rich")
    pytest.importorskip("textual")

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


def test_launch_harness_passes_eval_and_benchmark_screens(monkeypatch) -> None:
    pytest.importorskip("rich")
    pytest.importorskip("textual")

    captured: list[dict[str, object]] = []

    class _StubApp:
        def __init__(self, **kwargs: object) -> None:
            captured.append(dict(kwargs))

        def run(self) -> None:
            return None

    import worldforge.harness.tui as tui

    monkeypatch.setattr(tui, "TheWorldHarnessApp", _StubApp)

    from worldforge.harness.cli import launch_harness

    assert launch_harness(flow_id="eval", state_dir=None, animate=True) == 0
    assert launch_harness(flow_id="benchmark", state_dir=None, animate=True) == 0
    assert captured[0]["initial_screen"] == "eval"
    assert captured[1]["initial_screen"] == "benchmark"
    assert captured[0]["initial_flow_id"] == "leworldmodel"

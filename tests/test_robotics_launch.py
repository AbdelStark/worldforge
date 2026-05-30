from __future__ import annotations

import asyncio
import importlib
import sys
import webbrowser
from pathlib import Path

import pytest


def test_robotics_launch_imports_without_textual() -> None:
    import worldforge.harness.robotics_launch as launch

    saved_textual = sys.modules.pop("textual", None)
    sys.modules["textual"] = None  # type: ignore[assignment]
    try:
        reloaded = importlib.reload(launch)
        assert reloaded.TensorBoardLaunch.__name__ == "TensorBoardLaunch"
    finally:
        if saved_textual is not None:
            sys.modules["textual"] = saved_textual
        else:
            sys.modules.pop("textual", None)
        importlib.reload(launch)


def test_launch_rerun_viewer_uses_silent_detached_process(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from worldforge.harness import robotics_launch

    recording = tmp_path / "real-run.rrd"
    recording.write_bytes(b"rrd")
    launched: dict[str, object] = {}

    def fake_popen(command: list[str], **kwargs: object) -> object:
        launched["command"] = command
        launched["kwargs"] = dict(kwargs)
        return object()

    monkeypatch.setattr(robotics_launch.subprocess, "Popen", fake_popen)

    command_text = robotics_launch.launch_rerun_viewer(recording)

    assert launched["command"] == [
        "uvx",
        "--from",
        "rerun-sdk>=0.24,<0.32",
        "rerun",
        str(recording),
    ]
    assert command_text.endswith(str(recording))
    kwargs = launched["kwargs"]
    assert isinstance(kwargs, dict)
    assert kwargs["stdout"] is robotics_launch.subprocess.DEVNULL
    assert kwargs["stderr"] is robotics_launch.subprocess.DEVNULL
    assert kwargs["start_new_session"] is True


def test_rerun_recording_preflight_reports_missing_inputs(tmp_path: Path) -> None:
    from worldforge.harness import robotics_launch

    missing = tmp_path / "missing.rrd"
    valid = tmp_path / "real-run.rrd"
    valid.write_bytes(b"rrd")

    disabled = robotics_launch.rerun_recording_preflight(None)
    not_found = robotics_launch.rerun_recording_preflight(missing)

    assert disabled == robotics_launch.ViewerPreflightIssue(
        "This run does not include a persisted Rerun recording.",
        severity="warning",
        title="Rerun",
    )
    assert not_found == robotics_launch.ViewerPreflightIssue(
        f"Rerun recording not found: {missing}",
        severity="error",
        title="Rerun",
    )
    assert robotics_launch.rerun_recording_preflight(valid) is None


def test_launch_tensorboard_viewer_captures_output_with_context_managers(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from worldforge.harness import robotics_launch

    launched: dict[str, object] = {}

    def fake_popen(command: list[str], **kwargs: object) -> object:
        launched["command"] = command
        launched["kwargs"] = dict(kwargs)
        return object()

    monkeypatch.setattr(robotics_launch.subprocess, "Popen", fake_popen)

    launch = robotics_launch.launch_tensorboard_viewer(tmp_path)

    assert launched["command"] == [
        "uvx",
        "--from",
        "tensorboard>=2.16,<3",
        "--with",
        "setuptools<81",
        "tensorboard",
        "--logdir",
        str(tmp_path),
        "--port",
        "6006",
    ]
    kwargs = launched["kwargs"]
    assert isinstance(kwargs, dict)
    assert kwargs["start_new_session"] is True
    assert kwargs["stdout"] is not robotics_launch.subprocess.DEVNULL
    assert kwargs["stderr"] is not robotics_launch.subprocess.DEVNULL
    assert kwargs["stdout"].closed is True
    assert kwargs["stderr"].closed is True
    assert launch.url == "http://localhost:6006/"
    assert launch.stdout_log == tmp_path / "tensorboard.stdout.log"
    assert launch.stderr_log == tmp_path / "tensorboard.stderr.log"
    assert launch.command_text.startswith("uvx --from")


def test_tensorboard_log_dir_preflight_reports_missing_inputs(tmp_path: Path) -> None:
    from worldforge.harness import robotics_launch

    missing = tmp_path / "missing"
    valid = tmp_path / "tensorboard"
    valid.mkdir()

    disabled = robotics_launch.tensorboard_log_dir_preflight(None)
    not_found = robotics_launch.tensorboard_log_dir_preflight(missing)

    assert disabled == robotics_launch.ViewerPreflightIssue(
        "This run does not include a TensorBoard log directory.",
        severity="warning",
        title="TensorBoard",
    )
    assert not_found == robotics_launch.ViewerPreflightIssue(
        f"TensorBoard log directory not found: {missing}",
        severity="error",
        title="TensorBoard",
    )
    assert robotics_launch.tensorboard_log_dir_preflight(valid) is None


def test_wait_for_tensorboard_ready_polls_until_success() -> None:
    from worldforge.harness import robotics_launch

    calls = 0

    def port_open(_host: str, _port: int) -> bool:
        nonlocal calls
        calls += 1
        return calls == 2

    ready = asyncio.run(
        robotics_launch.wait_for_tensorboard_ready(
            host="localhost",
            port=6006,
            timeout_s=1.0,
            interval_s=0.001,
            port_open=port_open,
        )
    )

    assert ready is True
    assert calls == 2


def test_open_browser_url_reports_browser_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    from worldforge.harness import robotics_launch

    monkeypatch.setattr(
        robotics_launch.webbrowser,
        "open",
        lambda _url: (_ for _ in ()).throw(webbrowser.Error("no browser")),
    )

    result = asyncio.run(robotics_launch.open_browser_url("http://localhost:6006/"))

    assert result.opened is False
    assert result.error == "no browser"

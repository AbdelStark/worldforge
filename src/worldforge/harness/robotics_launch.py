"""Textual-free launcher helpers for robotics showcase viewers."""

from __future__ import annotations

import asyncio
import subprocess
import time
import webbrowser
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from worldforge.harness import robotics_view

ViewerNotificationSeverity = Literal["warning", "error", "information"]


@dataclass(frozen=True, slots=True)
class TensorBoardLaunch:
    """Host-side launch details the TUI can surface without owning subprocess setup."""

    url: str
    stdout_log: Path
    stderr_log: Path
    command_text: str


@dataclass(frozen=True, slots=True)
class BrowserOpenResult:
    opened: bool
    error: str | None = None


@dataclass(frozen=True, slots=True)
class ViewerPreflightIssue:
    message: str
    severity: ViewerNotificationSeverity
    title: str


def rerun_recording_preflight(path: Path | None) -> ViewerPreflightIssue | None:
    if path is None:
        return ViewerPreflightIssue(
            "This run does not include a persisted Rerun recording.",
            severity="warning",
            title="Rerun",
        )
    if not path.is_file():
        return ViewerPreflightIssue(
            f"Rerun recording not found: {path}",
            severity="error",
            title="Rerun",
        )
    return None


def tensorboard_log_dir_preflight(path: Path | None) -> ViewerPreflightIssue | None:
    if path is None:
        return ViewerPreflightIssue(
            "This run does not include a TensorBoard log directory.",
            severity="warning",
            title="TensorBoard",
        )
    if not path.is_dir():
        return ViewerPreflightIssue(
            f"TensorBoard log directory not found: {path}",
            severity="error",
            title="TensorBoard",
        )
    return None


def launch_rerun_viewer(path: Path) -> str:
    """Launch the Rerun viewer for ``path`` and return the shell-safe command text."""

    command = robotics_view.robotics_rerun_viewer_command(path)
    subprocess.Popen(
        command,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    return robotics_view.robotics_rerun_viewer_command_text(path)


def launch_tensorboard_viewer(path: Path) -> TensorBoardLaunch:
    """Launch TensorBoard for ``path`` with stdout/stderr captured under the log directory."""

    stdout_log = path / robotics_view.ROBOTICS_TENSORBOARD_STDOUT_LOG
    stderr_log = path / robotics_view.ROBOTICS_TENSORBOARD_STDERR_LOG
    command = robotics_view.robotics_tensorboard_viewer_command(path)
    with stdout_log.open("wb") as stdout_handle, stderr_log.open("wb") as stderr_handle:
        subprocess.Popen(
            command,
            stdout=stdout_handle,
            stderr=stderr_handle,
            start_new_session=True,
        )
    return TensorBoardLaunch(
        url=robotics_view.robotics_tensorboard_url(),
        stdout_log=stdout_log,
        stderr_log=stderr_log,
        command_text=robotics_view.robotics_tensorboard_viewer_command_text(path),
    )


async def wait_for_tensorboard_ready(
    *,
    host: str,
    port: int,
    timeout_s: float,
    interval_s: float,
    port_open: Callable[[str, int], bool],
) -> bool:
    """Wait asynchronously for TensorBoard to bind its port."""

    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if await asyncio.to_thread(port_open, host, port):
            return True
        await asyncio.sleep(interval_s)
    return False


async def open_browser_url(url: str) -> BrowserOpenResult:
    """Open ``url`` in the default browser without blocking the Textual event loop."""

    try:
        opened = bool(await asyncio.to_thread(webbrowser.open, url))
    except webbrowser.Error as exc:
        return BrowserOpenResult(opened=False, error=str(exc))
    return BrowserOpenResult(opened=opened)

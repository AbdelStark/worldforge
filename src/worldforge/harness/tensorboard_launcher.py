"""Launch, poll, and probe a TensorBoard server for the robotics showcase.

This module owns the host-side launch logic the TUI uses for its ``t``
keybinding, and exposes the same logic as a non-interactive CLI
(``worldforge-open-tensorboard``) so the flow can be validated end-to-end
from a shell - launch a TensorBoard subprocess, poll its TCP port, fetch the
index page, and assert it contains a TensorBoard marker - without opening the
Textual report.

The launched command pins ``setuptools<81`` because TensorBoard still does
``import pkg_resources`` at startup and ``setuptools>=81`` removed that
package. The constraint lives only inside the ``uvx``-launched environment;
WorldForge's own dependency set is unaffected.
"""

from __future__ import annotations

import argparse
import http.client
import shlex
import socket
import subprocess
import sys
import time
import webbrowser
from collections.abc import Sequence
from pathlib import Path

DEFAULT_PORT = 6006
DEFAULT_HOST = "localhost"
DEFAULT_READY_TIMEOUT_S = 60.0
DEFAULT_POLL_INTERVAL_S = 0.5
DEFAULT_PROBE_TIMEOUT_S = 5.0
DEFAULT_SHUTDOWN_TIMEOUT_S = 5.0
STDOUT_LOG = "tensorboard.stdout.log"
STDERR_LOG = "tensorboard.stderr.log"
HEALTH_MARKER = "TensorBoard"
TENSORBOARD_PIN = "tensorboard>=2.16,<3"
SETUPTOOLS_PIN = "setuptools<81"


def viewer_command(log_dir: Path, *, port: int = DEFAULT_PORT) -> list[str]:
    """Return the argv that launches a TensorBoard server via uvx.

    The pinned ``setuptools<81`` constraint keeps ``pkg_resources`` available
    so TensorBoard can finish importing.
    """

    return [
        "uvx",
        "--from",
        TENSORBOARD_PIN,
        "--with",
        SETUPTOOLS_PIN,
        "tensorboard",
        "--logdir",
        str(log_dir),
        "--port",
        str(port),
    ]


def viewer_command_text(log_dir: Path, *, port: int = DEFAULT_PORT) -> str:
    """Return :func:`viewer_command` as a shell-safe single line."""

    return " ".join(shlex.quote(part) for part in viewer_command(log_dir, port=port))


def viewer_url(*, host: str = DEFAULT_HOST, port: int = DEFAULT_PORT) -> str:
    """Return the user-facing URL for a launched TensorBoard server."""

    return f"http://{host}:{port}/"


def port_open(host: str, port: int, *, timeout: float = 1.0) -> bool:
    """Return ``True`` when a TCP connect to ``host:port`` succeeds in ``timeout``."""

    try:
        sock = socket.create_connection((host, port), timeout=timeout)
    except OSError:
        return False
    sock.close()
    return True


def wait_until_ready(
    host: str,
    port: int,
    *,
    timeout: float,
    interval: float,
    sleep: object = time.sleep,
    monotonic: object = time.monotonic,
) -> bool:
    """Block until ``host:port`` opens or ``timeout`` seconds elapse.

    The ``sleep`` and ``monotonic`` hooks exist so tests can drive the loop
    without actually waiting.
    """

    if timeout <= 0 or interval <= 0:
        raise ValueError("timeout and interval must be positive numbers.")
    deadline = monotonic() + timeout  # type: ignore[operator]
    probe_timeout = min(1.0, max(0.05, interval * 4))
    while monotonic() < deadline:  # type: ignore[operator]
        if port_open(host, port, timeout=probe_timeout):
            return True
        sleep(interval)  # type: ignore[operator]
    return False


def probe_html(
    host: str,
    port: int,
    *,
    path: str = "/",
    timeout: float = DEFAULT_PROBE_TIMEOUT_S,
) -> tuple[int, str]:
    """Fetch ``http://host:port/path`` and return ``(status, body)``."""

    conn = http.client.HTTPConnection(host, port, timeout=timeout)
    try:
        conn.request("GET", path)
        response = conn.getresponse()
        body_bytes = response.read()
        body = body_bytes.decode("utf-8", errors="replace")
        return response.status, body
    finally:
        conn.close()


def launch(
    log_dir: Path,
    *,
    port: int = DEFAULT_PORT,
    stdout_log: Path | None = None,
    stderr_log: Path | None = None,
) -> subprocess.Popen[bytes]:
    """Spawn the TensorBoard subprocess in a detached session.

    Stdout/stderr are routed to the log files inside ``log_dir`` so launch
    failures are captured for debugging instead of being silently discarded.
    """

    resolved = Path(log_dir).expanduser()
    if not resolved.is_dir():
        raise FileNotFoundError(f"TensorBoard log directory not found: {resolved}")
    stdout_target = stdout_log or (resolved / STDOUT_LOG)
    stderr_target = stderr_log or (resolved / STDERR_LOG)
    command = viewer_command(resolved, port=port)
    stdout_handle = stdout_target.open("wb")
    try:
        stderr_handle = stderr_target.open("wb")
        try:
            return subprocess.Popen(
                command,
                stdout=stdout_handle,
                stderr=stderr_handle,
                start_new_session=True,
            )
        finally:
            stderr_handle.close()
    finally:
        stdout_handle.close()


def _terminate(process: subprocess.Popen[bytes], *, timeout: float) -> None:
    if process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait()


def _open_browser(url: str, *, no_browser: bool) -> bool:
    if no_browser:
        return False
    try:
        return bool(webbrowser.open(url))
    except webbrowser.Error:
        return False


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Launch a TensorBoard server for a robotics showcase run, wait for it to "
            "come up, and optionally probe its HTML index page. Use --probe to validate "
            "the launch flow end-to-end from a shell."
        ),
    )
    parser.add_argument(
        "--logdir",
        type=Path,
        required=True,
        help="Directory containing ``events.out.tfevents.*`` files to serve.",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=DEFAULT_PORT,
        help=f"TCP port to bind (default {DEFAULT_PORT}).",
    )
    parser.add_argument(
        "--host",
        default=DEFAULT_HOST,
        help=f"Host to poll and probe (default {DEFAULT_HOST}).",
    )
    parser.add_argument(
        "--ready-timeout",
        type=float,
        default=DEFAULT_READY_TIMEOUT_S,
        help="Seconds to wait for TensorBoard to bind the port (default 60).",
    )
    parser.add_argument(
        "--poll-interval",
        type=float,
        default=DEFAULT_POLL_INTERVAL_S,
        help="Seconds between port probes during the ready wait (default 0.5).",
    )
    parser.add_argument(
        "--probe",
        action="store_true",
        help=(
            "After the server binds, fetch ``http://host:port/`` and assert the body "
            "contains the ``TensorBoard`` marker. Exits 1 on probe failure and tears "
            "down the subprocess."
        ),
    )
    parser.add_argument(
        "--no-browser",
        action="store_true",
        help="Skip the post-ready ``webbrowser.open`` call.",
    )
    parser.add_argument(
        "--keep-running",
        action="store_true",
        help=(
            "After a successful launch (and probe), block until the subprocess exits "
            "or until SIGINT is received. Implied when --probe is not set."
        ),
    )
    parser.add_argument(
        "--shutdown-timeout",
        type=float,
        default=DEFAULT_SHUTDOWN_TIMEOUT_S,
        help="Seconds to give TensorBoard to exit on teardown (default 5).",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """CLI entry point for ``worldforge-open-tensorboard``."""

    parser = _build_parser()
    args = parser.parse_args(argv)
    log_dir = _main_log_dir(args)
    if log_dir is None:
        return 2
    if not _main_timing_args_valid(args):
        return 2

    process = _main_launch_process(log_dir=log_dir, port=args.port)
    if process is None:
        return 2

    url = viewer_url(host=args.host, port=args.port)
    _print_launch_wait(log_dir=log_dir, port=args.port, url=url, ready_timeout=args.ready_timeout)
    if not _main_wait_until_ready(args, log_dir=log_dir, process=process, url=url):
        return 1

    print(f"tensorboard ready at {url}", flush=True)

    if args.probe and not _main_probe(args, process=process):
        return 1
    _main_open_browser(url, no_browser=args.no_browser)
    if not _main_keep_running(args):
        _terminate(process, timeout=args.shutdown_timeout)
        return 0
    return _main_wait_for_process(process, shutdown_timeout=args.shutdown_timeout)


def _main_log_dir(args: argparse.Namespace) -> Path | None:
    log_dir = Path(args.logdir).expanduser()
    if log_dir.is_dir():
        return log_dir
    print(f"error: --logdir is not a directory: {log_dir}", file=sys.stderr)
    return None


def _main_timing_args_valid(args: argparse.Namespace) -> bool:
    if args.ready_timeout > 0 and args.poll_interval > 0:
        return True
    print(
        "error: --ready-timeout and --poll-interval must be positive numbers.",
        file=sys.stderr,
    )
    return False


def _main_launch_process(
    *,
    log_dir: Path,
    port: int,
) -> subprocess.Popen[bytes] | None:
    try:
        return launch(log_dir, port=port)
    except OSError as exc:
        print(f"error: failed to launch tensorboard: {exc}", file=sys.stderr)
        return None


def _print_launch_wait(*, log_dir: Path, port: int, url: str, ready_timeout: float) -> None:
    print(f"launching: {viewer_command_text(log_dir, port=port)}", flush=True)
    print(
        f"waiting for {url} (timeout {ready_timeout:.0f}s, logs in {log_dir})",
        flush=True,
    )


def _main_wait_until_ready(
    args: argparse.Namespace,
    *,
    log_dir: Path,
    process: subprocess.Popen[bytes],
    url: str,
) -> bool:
    ready = wait_until_ready(
        args.host,
        args.port,
        timeout=args.ready_timeout,
        interval=args.poll_interval,
    )
    if ready:
        return True
    print(
        f"error: TensorBoard did not bind {url} within "
        f"{args.ready_timeout:.0f}s; see {log_dir / STDERR_LOG}",
        file=sys.stderr,
    )
    _terminate(process, timeout=args.shutdown_timeout)
    return False


def _main_probe(args: argparse.Namespace, *, process: subprocess.Popen[bytes]) -> bool:
    try:
        status, body = probe_html(args.host, args.port)
    except OSError as exc:
        print(f"error: probe failed: {exc}", file=sys.stderr)
        _terminate(process, timeout=args.shutdown_timeout)
        return False
    print(f"probe: HTTP {status}, body {len(body)} bytes", flush=True)
    if status == 200 and HEALTH_MARKER in body:
        print(f"probe ok: index contains '{HEALTH_MARKER}' marker", flush=True)
        return True
    print(
        f"error: probe failed: HTTP {status}, missing '{HEALTH_MARKER}' marker",
        file=sys.stderr,
    )
    _terminate(process, timeout=args.shutdown_timeout)
    return False


def _main_open_browser(url: str, *, no_browser: bool) -> None:
    opened = _open_browser(url, no_browser=no_browser)
    if no_browser or opened:
        return
    print(f"warning: could not auto-open a browser, visit {url} manually", flush=True)


def _main_keep_running(args: argparse.Namespace) -> bool:
    return bool(args.keep_running or not args.probe)


def _main_wait_for_process(
    process: subprocess.Popen[bytes],
    *,
    shutdown_timeout: float,
) -> int:
    print("press Ctrl+C to stop tensorboard", flush=True)
    try:
        process.wait()
    except KeyboardInterrupt:
        _terminate(process, timeout=shutdown_timeout)
        return 0
    return process.returncode or 0


__all__ = [
    "DEFAULT_HOST",
    "DEFAULT_POLL_INTERVAL_S",
    "DEFAULT_PORT",
    "DEFAULT_PROBE_TIMEOUT_S",
    "DEFAULT_READY_TIMEOUT_S",
    "DEFAULT_SHUTDOWN_TIMEOUT_S",
    "HEALTH_MARKER",
    "SETUPTOOLS_PIN",
    "STDERR_LOG",
    "STDOUT_LOG",
    "TENSORBOARD_PIN",
    "launch",
    "main",
    "port_open",
    "probe_html",
    "viewer_command",
    "viewer_command_text",
    "viewer_url",
    "wait_until_ready",
]

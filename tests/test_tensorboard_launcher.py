from __future__ import annotations

import socket
import subprocess
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any

import pytest

from worldforge.harness import tensorboard_launcher


class _StubHandler(BaseHTTPRequestHandler):
    """Minimal request handler used by the probe and main-CLI tests."""

    body = b"<!doctype html><title>TensorBoard</title>fake body"
    status = 200

    def do_GET(self) -> None:
        self.send_response(self.__class__.status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(self.__class__.body)))
        self.end_headers()
        self.wfile.write(self.__class__.body)

    def log_message(self, format: str, *args: object) -> None:
        # Silence default stderr noise in tests.
        return


def _spawn_local_http_server() -> tuple[HTTPServer, int]:
    server = HTTPServer(("127.0.0.1", 0), _StubHandler)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, port


def test_viewer_command_pins_setuptools_and_tensorboard(tmp_path: Path) -> None:
    command = tensorboard_launcher.viewer_command(tmp_path, port=6007)
    assert command == [
        "uvx",
        "--from",
        "tensorboard>=2.16,<3",
        "--with",
        "setuptools<81",
        "tensorboard",
        "--logdir",
        str(tmp_path),
        "--port",
        "6007",
    ]


def test_viewer_command_text_quotes_path(tmp_path: Path) -> None:
    path = tmp_path / "with spaces"
    path.mkdir()
    text = tensorboard_launcher.viewer_command_text(path)
    assert "'" in text or '"' in text or " " not in str(path)
    assert "tensorboard>=2.16,<3" in text
    assert "setuptools<81" in text


def test_viewer_url_defaults_to_localhost_6006() -> None:
    assert tensorboard_launcher.viewer_url() == "http://localhost:6006/"
    assert tensorboard_launcher.viewer_url(host="127.0.0.1", port=6010) == "http://127.0.0.1:6010/"


def test_port_open_returns_false_for_closed_port() -> None:
    # 0 is reserved and never bound; create_connection should fail fast.
    assert tensorboard_launcher.port_open("127.0.0.1", 1, timeout=0.2) is False


def test_port_open_returns_true_for_a_bound_socket() -> None:
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    listener.bind(("127.0.0.1", 0))
    listener.listen(1)
    try:
        host, port = listener.getsockname()
        assert tensorboard_launcher.port_open(host, port, timeout=0.5) is True
    finally:
        listener.close()


def test_wait_until_ready_rejects_non_positive_timeouts() -> None:
    with pytest.raises(ValueError):
        tensorboard_launcher.wait_until_ready(
            "127.0.0.1",
            1,
            timeout=0,
            interval=0.1,
        )
    with pytest.raises(ValueError):
        tensorboard_launcher.wait_until_ready(
            "127.0.0.1",
            1,
            timeout=0.1,
            interval=0,
        )


def test_wait_until_ready_returns_true_when_port_opens_during_polling(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = {"count": 0}

    def fake_port_open(host: str, port: int, *, timeout: float = 1.0) -> bool:
        calls["count"] += 1
        return calls["count"] >= 3

    monkeypatch.setattr(tensorboard_launcher, "port_open", fake_port_open)
    sleeps: list[float] = []
    times = iter([0.0, 0.1, 0.2, 0.3, 0.4, 0.5])

    assert (
        tensorboard_launcher.wait_until_ready(
            "127.0.0.1",
            6006,
            timeout=1.0,
            interval=0.05,
            sleep=lambda value: sleeps.append(value),
            monotonic=lambda: next(times),
        )
        is True
    )
    assert calls["count"] == 3
    assert sleeps == [0.05, 0.05]


def test_wait_until_ready_returns_false_on_timeout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        tensorboard_launcher,
        "port_open",
        lambda *args, **kwargs: False,
    )
    times = iter([0.0, 0.5, 0.9, 1.0, 1.5])
    sleeps: list[float] = []
    assert (
        tensorboard_launcher.wait_until_ready(
            "127.0.0.1",
            6006,
            timeout=1.0,
            interval=0.5,
            sleep=lambda value: sleeps.append(value),
            monotonic=lambda: next(times),
        )
        is False
    )
    assert sleeps == [0.5, 0.5]


def test_probe_html_returns_status_and_body() -> None:
    server, port = _spawn_local_http_server()
    try:
        status, body = tensorboard_launcher.probe_html("127.0.0.1", port, timeout=2.0)
    finally:
        server.shutdown()
        server.server_close()
    assert status == 200
    assert "TensorBoard" in body


def test_launch_rejects_missing_logdir(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        tensorboard_launcher.launch(tmp_path / "does-not-exist")


def test_launch_writes_log_files_and_forwards_argv(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    captured: dict[str, Any] = {}

    def fake_popen(command: list[str], **kwargs: object) -> object:
        captured["command"] = command
        captured["kwargs"] = dict(kwargs)
        for handle in (kwargs.get("stdout"), kwargs.get("stderr")):
            if hasattr(handle, "write"):
                handle.write(b"hello\n")
        return object()

    monkeypatch.setattr(tensorboard_launcher.subprocess, "Popen", fake_popen)

    tensorboard_launcher.launch(tmp_path, port=6007)

    assert captured["command"][:5] == [
        "uvx",
        "--from",
        "tensorboard>=2.16,<3",
        "--with",
        "setuptools<81",
    ]
    stdout_log = tmp_path / tensorboard_launcher.STDOUT_LOG
    stderr_log = tmp_path / tensorboard_launcher.STDERR_LOG
    assert stdout_log.exists()
    assert stderr_log.exists()
    assert stdout_log.read_bytes() == b"hello\n"
    assert stderr_log.read_bytes() == b"hello\n"


def _stub_popen(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    state: dict[str, Any] = {"terminated": False, "killed": False, "waited": False}

    class _StubProcess:
        returncode = 0

        def poll(self) -> int | None:
            return None if not state["terminated"] else 0

        def terminate(self) -> None:
            state["terminated"] = True

        def kill(self) -> None:
            state["killed"] = True

        def wait(self, timeout: float | None = None) -> int:
            state["waited"] = True
            return 0

    def fake_launch(log_dir: Path, **kwargs: object) -> _StubProcess:
        state["launched_with"] = (log_dir, kwargs)
        return _StubProcess()

    monkeypatch.setattr(tensorboard_launcher, "launch", fake_launch)
    return state


def test_main_rejects_missing_logdir(
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    exit_code = tensorboard_launcher.main(
        ["--logdir", str(tmp_path / "missing"), "--probe", "--no-browser"]
    )
    err = capsys.readouterr().err
    assert exit_code == 2
    assert "not a directory" in err


def test_main_returns_one_on_ready_timeout(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    state = _stub_popen(monkeypatch)
    monkeypatch.setattr(
        tensorboard_launcher,
        "wait_until_ready",
        lambda *args, **kwargs: False,
    )

    exit_code = tensorboard_launcher.main(
        [
            "--logdir",
            str(tmp_path),
            "--probe",
            "--no-browser",
            "--ready-timeout",
            "1",
            "--poll-interval",
            "0.1",
        ]
    )

    assert exit_code == 1
    err = capsys.readouterr().err
    assert "did not bind" in err
    assert tensorboard_launcher.STDERR_LOG in err
    assert state["terminated"] is True


def test_main_probe_success(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    state = _stub_popen(monkeypatch)
    monkeypatch.setattr(
        tensorboard_launcher,
        "wait_until_ready",
        lambda *args, **kwargs: True,
    )
    monkeypatch.setattr(
        tensorboard_launcher,
        "probe_html",
        lambda *args, **kwargs: (200, "<title>TensorBoard</title>"),
    )

    exit_code = tensorboard_launcher.main(
        [
            "--logdir",
            str(tmp_path),
            "--probe",
            "--no-browser",
        ]
    )

    assert exit_code == 0
    out = capsys.readouterr().out
    assert "tensorboard ready" in out
    assert "probe ok" in out
    # --probe without --keep-running tears the subprocess down.
    assert state["terminated"] is True


def test_main_probe_html_marker_missing_fails(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    state = _stub_popen(monkeypatch)
    monkeypatch.setattr(
        tensorboard_launcher,
        "wait_until_ready",
        lambda *args, **kwargs: True,
    )
    monkeypatch.setattr(
        tensorboard_launcher,
        "probe_html",
        lambda *args, **kwargs: (200, "this body does not mention the tool"),
    )

    exit_code = tensorboard_launcher.main(
        [
            "--logdir",
            str(tmp_path),
            "--probe",
            "--no-browser",
        ]
    )

    assert exit_code == 1
    err = capsys.readouterr().err
    assert "missing 'TensorBoard' marker" in err
    assert state["terminated"] is True


def test_main_probe_html_connection_error(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    state = _stub_popen(monkeypatch)
    monkeypatch.setattr(
        tensorboard_launcher,
        "wait_until_ready",
        lambda *args, **kwargs: True,
    )

    def boom(*args: object, **kwargs: object) -> tuple[int, str]:
        raise ConnectionResetError("nope")

    monkeypatch.setattr(tensorboard_launcher, "probe_html", boom)

    exit_code = tensorboard_launcher.main(
        [
            "--logdir",
            str(tmp_path),
            "--probe",
            "--no-browser",
        ]
    )

    assert exit_code == 1
    err = capsys.readouterr().err
    assert "probe failed" in err
    assert state["terminated"] is True


def test_main_launch_oserror_returns_two(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    def fake_launch(log_dir: Path, **kwargs: object) -> object:
        raise OSError("permission denied")

    monkeypatch.setattr(tensorboard_launcher, "launch", fake_launch)
    exit_code = tensorboard_launcher.main(
        [
            "--logdir",
            str(tmp_path),
            "--probe",
            "--no-browser",
        ]
    )
    err = capsys.readouterr().err
    assert exit_code == 2
    assert "failed to launch" in err


def test_main_rejects_non_positive_timing_arguments(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    exit_code = tensorboard_launcher.main(
        [
            "--logdir",
            str(tmp_path),
            "--ready-timeout",
            "0",
        ]
    )
    err = capsys.readouterr().err
    assert exit_code == 2
    assert "must be positive" in err


def test_main_keep_running_skips_teardown_until_subprocess_exits(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    state = _stub_popen(monkeypatch)
    monkeypatch.setattr(
        tensorboard_launcher,
        "wait_until_ready",
        lambda *args, **kwargs: True,
    )

    # Stub process.wait that returns immediately (no subprocess timeout argument).
    class _Quick:
        returncode = 0

        def poll(self) -> int | None:
            return None

        def terminate(self) -> None:
            state["terminated"] = True

        def kill(self) -> None:
            state["killed"] = True

        def wait(self, timeout: float | None = None) -> int:
            state["waited"] = True
            return 0

    monkeypatch.setattr(tensorboard_launcher, "launch", lambda *args, **kwargs: _Quick())

    exit_code = tensorboard_launcher.main(
        [
            "--logdir",
            str(tmp_path),
            "--no-browser",
            "--keep-running",
        ]
    )
    assert exit_code == 0
    assert state["waited"] is True
    # --keep-running lets the subprocess complete on its own.
    assert state["terminated"] is False


def test_main_browser_open_called_when_browser_allowed(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    state = _stub_popen(monkeypatch)
    monkeypatch.setattr(
        tensorboard_launcher,
        "wait_until_ready",
        lambda *args, **kwargs: True,
    )
    monkeypatch.setattr(
        tensorboard_launcher,
        "probe_html",
        lambda *args, **kwargs: (200, "<title>TensorBoard</title>"),
    )
    opened_urls: list[str] = []
    monkeypatch.setattr(
        tensorboard_launcher.webbrowser,
        "open",
        lambda url, *args, **kwargs: opened_urls.append(url) or True,
    )

    exit_code = tensorboard_launcher.main(
        [
            "--logdir",
            str(tmp_path),
            "--probe",
        ]
    )

    assert exit_code == 0
    assert opened_urls == ["http://localhost:6006/"]
    assert state["terminated"] is True


def test_terminate_kills_when_wait_times_out(monkeypatch: pytest.MonkeyPatch) -> None:
    state = {"terminated": False, "killed": False, "wait_calls": 0}

    class _Stub:
        def poll(self) -> int | None:
            return None

        def terminate(self) -> None:
            state["terminated"] = True

        def kill(self) -> None:
            state["killed"] = True

        def wait(self, timeout: float | None = None) -> int:
            state["wait_calls"] += 1
            if state["wait_calls"] == 1:
                raise subprocess.TimeoutExpired(cmd="x", timeout=timeout or 0.0)
            return 0

    tensorboard_launcher._terminate(_Stub(), timeout=0.01)  # type: ignore[arg-type]
    assert state["terminated"] is True
    assert state["killed"] is True

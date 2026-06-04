#!/usr/bin/env python
"""Run a live NVIDIA Isaac GR00T policy smoke through WorldForge."""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import re
import shlex
import subprocess
import sys
import time
from collections.abc import Callable, Sequence
from contextlib import suppress
from pathlib import Path
from types import ModuleType
from typing import Any

from worldforge.models import JSONDict, _redact_observable_text
from worldforge.providers import GrootPolicyClientProvider
from worldforge.smoke.run_manifest import build_run_manifest, write_run_manifest
from worldforge.smoke.trusted_inputs import (
    callable_attribute as _trusted_callable_attribute,
)
from worldforge.smoke.trusted_inputs import (
    callable_spec_parts as _trusted_callable_spec_parts,
)
from worldforge.smoke.trusted_inputs import (
    code_opt_in_message as _trusted_code_opt_in_message,
)
from worldforge.smoke.trusted_inputs import (
    load_callable as _trusted_load_callable,
)
from worldforge.smoke.trusted_inputs import (
    load_callable_module as _trusted_load_callable_module,
)
from worldforge.smoke.trusted_inputs import (
    load_json_object as _trusted_load_json_object,
)
from worldforge.smoke.trusted_inputs import (
    looks_like_module_path as _trusted_looks_like_module_path,
)
from worldforge.smoke.trusted_inputs import (
    module_from_path as _trusted_module_from_path,
)
from worldforge.smoke.trusted_inputs import (
    require_code_allowed as _trusted_require_code_allowed,
)

DEFAULT_MODEL_PATH = "nvidia/GR00T-N1.6-3B"
DEFAULT_EMBODIMENT_TAG = "GR1"
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 5555
DEFAULT_TIMEOUT_MS = 15_000
DEFAULT_STARTUP_TIMEOUT_SECONDS = 300.0
_SECRET_ARG_FLAGS = {"--api-token"}
_SECRET_ARG_NAME_PATTERN = re.compile(
    r"(api[-_]?key|authorization|credential|password|secret|token)",
    re.IGNORECASE,
)
_HOST_LOCAL_PATH_PATTERN = re.compile(
    r"(?<![A-Za-z0-9:])/(?:Users|private|Volumes|var/folders|tmp)/[^\s)`|]+"
)
_MANIFEST_ENV_VARS = (
    "GROOT_POLICY_HOST",
    "GROOT_POLICY_PORT",
    "GROOT_POLICY_TIMEOUT_MS",
    "GROOT_POLICY_API_TOKEN",
    "GROOT_POLICY_STRICT",
    "GROOT_EMBODIMENT_TAG",
    "GROOT_REPO",
    "GROOT_MODEL_PATH",
    "GROOT_DATASET_PATH",
    "GROOT_POLICY_DEVICE",
    "GROOT_POLICY_BIND_HOST",
)


class _SmokeRunState:
    __slots__ = ("args", "command_argv", "output", "process", "provider_events")

    def __init__(self, *, args: argparse.Namespace, command_argv: tuple[str, ...]) -> None:
        self.args = args
        self.command_argv = command_argv
        self.provider_events: list[object] = []
        self.output: JSONDict = {}
        self.process: subprocess.Popen[bytes] | None = None


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None or not raw.strip():
        return default
    try:
        value = int(raw)
    except ValueError as exc:
        raise SystemExit(f"{name} must be an integer.") from exc
    if value <= 0:
        raise SystemExit(f"{name} must be greater than 0.")
    return value


def _env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None or not raw.strip():
        return default
    normalized = raw.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise SystemExit(f"{name} must be a boolean.")


def _load_json_file(path: Path, *, name: str) -> JSONDict:
    return _trusted_load_json_object(path, name=name)


def _code_opt_in_message(name: str, flag: str) -> str:
    return _trusted_code_opt_in_message(name, flag=flag)


def _module_from_path(path: Path, *, name: str, allow_code: bool, flag: str) -> ModuleType:
    return _trusted_module_from_path(
        path,
        name=name,
        allow_code=allow_code,
        flag=flag,
    )


def _require_code_allowed(*, name: str, allow_code: bool, flag: str) -> None:
    _trusted_require_code_allowed(name=name, allow_code=allow_code, flag=flag)


def _split_callable_spec(spec: str, *, name: str) -> tuple[str, str]:
    return _trusted_callable_spec_parts(spec, name=name)


def _looks_like_module_path(module_ref: str) -> bool:
    return _trusted_looks_like_module_path(module_ref)


def _load_callable_module(
    module_ref: str,
    *,
    name: str,
    allow_code: bool,
    flag: str,
) -> ModuleType:
    return _trusted_load_callable_module(
        module_ref,
        name=name,
        allow_code=allow_code,
        flag=flag,
    )


def _callable_attribute(module: ModuleType, function_name: str, *, name: str) -> Callable[..., Any]:
    return _trusted_callable_attribute(module, function_name, name=name)


def _load_callable(
    spec: str,
    *,
    name: str,
    allow_code: bool = False,
    flag: str = "--allow-translator-code",
) -> Callable[..., Any]:
    return _trusted_load_callable(
        spec,
        name=name,
        allow_code=allow_code,
        flag=flag,
        require_code=True,
    )


def _load_base_policy_info(args: argparse.Namespace) -> JSONDict:
    if args.policy_info_json is not None:
        return _load_json_file(args.policy_info_json, name="policy-info")
    if args.observation_json is not None:
        return {
            "observation": _load_json_file(args.observation_json, name="observation"),
        }
    if args.observation_module is not None:
        return _load_observation_factory_policy_info(args)
    raise SystemExit(
        "Live policy smoke requires --policy-info-json, --observation-json, "
        "or --observation-module."
    )


def _load_observation_factory_policy_info(args: argparse.Namespace) -> JSONDict:
    factory = _load_callable(
        args.observation_module,
        name="observation factory",
        allow_code=args.allow_observation_code,
        flag="--allow-observation-code",
    )
    try:
        produced = factory()
    except Exception as exc:
        raise SystemExit(f"Observation factory failed: {exc}") from exc
    return _policy_info_from_observation_factory_output(produced)


def _policy_info_from_observation_factory_output(produced: object) -> JSONDict:
    if not isinstance(produced, dict):
        raise SystemExit("Observation factory must return a dictionary.")
    if "observation" in produced:
        return dict(produced)
    return {"observation": dict(produced)}


def _apply_policy_info_overrides(info: JSONDict, args: argparse.Namespace) -> None:
    if args.options_json is not None:
        info["options"] = _load_json_file(args.options_json, name="options")
    if args.embodiment_tag is not None:
        info.setdefault("embodiment_tag", args.embodiment_tag)
    if args.action_horizon is not None:
        info["action_horizon"] = args.action_horizon


def _load_policy_info(args: argparse.Namespace) -> JSONDict:
    info = _load_base_policy_info(args)
    _apply_policy_info_overrides(info, args)
    _validate_policy_info_controls(info)
    return info


def _validate_policy_info_controls(info: JSONDict) -> None:
    embodiment_tag = info.get("embodiment_tag")
    if embodiment_tag is not None and (
        not isinstance(embodiment_tag, str) or not embodiment_tag.strip()
    ):
        raise SystemExit("GR00T policy info.embodiment_tag must be a non-empty string.")

    action_horizon = info.get("action_horizon")
    if action_horizon is not None and (
        isinstance(action_horizon, bool)
        or not isinstance(action_horizon, int)
        or action_horizon <= 0
    ):
        raise SystemExit("GR00T policy info.action_horizon must be an integer greater than 0.")


def _server_module_available() -> bool:
    try:
        return importlib.util.find_spec("gr00t.eval.run_gr00t_server") is not None
    except ModuleNotFoundError:
        return False


def _server_command_prefix(args: argparse.Namespace) -> tuple[list[str], Path | None]:
    if args.gr00t_root is not None:
        return _checkout_server_command_prefix(args.gr00t_root)
    if _server_module_available():
        return [sys.executable, "-m", "gr00t.eval.run_gr00t_server"], None
    raise SystemExit(
        "Cannot start GR00T policy server: provide --gr00t-root pointing to an "
        "Isaac-GR00T checkout, or run this script in an environment where "
        "gr00t.eval.run_gr00t_server is importable."
    )


def _checkout_server_command_prefix(gr00t_root: Path) -> tuple[list[str], Path]:
    root = gr00t_root.expanduser().resolve()
    _validate_gr00t_server_checkout(root)
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    return ["uv", "run", "python", "gr00t/eval/run_gr00t_server.py"], root


def _validate_gr00t_server_checkout(root: Path) -> None:
    server_script = root / "gr00t" / "eval" / "run_gr00t_server.py"
    if not server_script.exists():
        raise SystemExit(
            "--gr00t-root must point at an Isaac-GR00T checkout containing "
            "gr00t/eval/run_gr00t_server.py."
        )


def _server_identity_args(args: argparse.Namespace) -> list[str]:
    embodiment_tag = args.embodiment_tag or DEFAULT_EMBODIMENT_TAG
    return [
        "--embodiment-tag",
        embodiment_tag,
        "--host",
        args.server_host,
        "--port",
        str(args.port),
    ]


def _server_runtime_args(args: argparse.Namespace) -> list[str]:
    if args.dataset_path is not None:
        return ["--dataset-path", args.dataset_path]
    return ["--model-path", args.model_path or DEFAULT_MODEL_PATH]


def _server_device_args(args: argparse.Namespace) -> list[str]:
    if args.device is not None:
        return ["--device", args.device]
    return []


def _server_extra_args(args: argparse.Namespace) -> list[str]:
    return list(args.server_arg or [])


def _server_command(args: argparse.Namespace) -> tuple[list[str], Path | None]:
    command_prefix, cwd = _server_command_prefix(args)
    command = [
        *command_prefix,
        *_server_identity_args(args),
        *_server_runtime_args(args),
        *_server_device_args(args),
        *_server_extra_args(args),
    ]
    return command, cwd


def _start_server(args: argparse.Namespace) -> subprocess.Popen[bytes] | None:
    if not args.start_server:
        return None
    command, cwd = _server_command(args)
    print("Starting GR00T policy server:", _sanitized_command_display(command), file=sys.stderr)
    return subprocess.Popen(command, cwd=str(cwd) if cwd is not None else None)


def _wait_for_health(
    provider: GrootPolicyClientProvider,
    *,
    process: subprocess.Popen[bytes] | None,
    timeout_seconds: float,
) -> JSONDict:
    deadline = time.monotonic() + timeout_seconds
    last_health = provider.health()
    while time.monotonic() < deadline:
        if process is not None and process.poll() is not None:
            raise SystemExit(f"GR00T policy server exited early with code {process.returncode}.")
        last_health = provider.health()
        if last_health.healthy:
            return last_health.to_dict()
        time.sleep(2.0)
    raise SystemExit(
        "GR00T policy server did not become healthy before timeout. "
        f"Last health details: {last_health.details}"
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default=os.environ.get("GROOT_POLICY_HOST", DEFAULT_HOST))
    parser.add_argument("--port", type=int, default=_env_int("GROOT_POLICY_PORT", DEFAULT_PORT))
    parser.add_argument(
        "--timeout-ms",
        type=int,
        default=_env_int("GROOT_POLICY_TIMEOUT_MS", DEFAULT_TIMEOUT_MS),
    )
    parser.add_argument("--api-token", default=os.environ.get("GROOT_POLICY_API_TOKEN"))
    parser.add_argument(
        "--strict",
        action=argparse.BooleanOptionalAction,
        default=_env_bool("GROOT_POLICY_STRICT", False),
    )
    parser.add_argument("--embodiment-tag", default=os.environ.get("GROOT_EMBODIMENT_TAG"))
    parser.add_argument("--action-horizon", type=int, default=None)
    parser.add_argument("--health-only", action="store_true")
    parser.add_argument(
        "--run-manifest",
        type=Path,
        default=None,
        help="Write a sanitized run_manifest.json evidence file for this live smoke.",
    )

    input_group = parser.add_mutually_exclusive_group()
    input_group.add_argument(
        "--policy-info-json",
        type=Path,
        help="JSON file containing the full WorldForge policy_info object.",
    )
    input_group.add_argument(
        "--observation-json",
        type=Path,
        help="JSON file containing only the GR00T observation object.",
    )
    input_group.add_argument(
        "--observation-module",
        help=(
            "Python factory formatted as module_or_file:function. Returns observation or "
            "policy_info."
        ),
    )
    parser.add_argument(
        "--translator",
        help=(
            "Python action translator formatted as module_or_file:function. The callable receives "
            "(raw_actions, info, provider_info) and returns WorldForge Action objects. "
            "This imports and executes local Python; requires --allow-translator-code."
        ),
    )
    parser.add_argument(
        "--allow-translator-code",
        action="store_true",
        help="Acknowledge that --translator imports and executes trusted local Python code.",
    )
    parser.add_argument(
        "--allow-observation-code",
        action="store_true",
        help=(
            "Acknowledge that --observation-module imports and executes trusted local Python code."
        ),
    )
    parser.add_argument(
        "--options-json", type=Path, help="Optional JSON file passed as info.options."
    )

    parser.add_argument("--start-server", action="store_true")
    parser.add_argument(
        "--gr00t-root",
        type=Path,
        default=Path(os.environ["GROOT_REPO"]) if os.environ.get("GROOT_REPO") else None,
        help="Isaac-GR00T checkout used to start gr00t/eval/run_gr00t_server.py.",
    )
    parser.add_argument("--model-path", default=os.environ.get("GROOT_MODEL_PATH"))
    parser.add_argument("--dataset-path", default=os.environ.get("GROOT_DATASET_PATH"))
    parser.add_argument("--device", default=os.environ.get("GROOT_POLICY_DEVICE", "cuda:0"))
    parser.add_argument(
        "--server-host",
        default=os.environ.get("GROOT_POLICY_BIND_HOST", DEFAULT_HOST),
        help="Bind host passed to the started GR00T server.",
    )
    parser.add_argument(
        "--startup-timeout-seconds",
        type=float,
        default=DEFAULT_STARTUP_TIMEOUT_SECONDS,
    )
    parser.add_argument(
        "--server-arg",
        action="append",
        default=[],
        help="Extra argument forwarded to run_gr00t_server.py. Repeat as needed.",
    )
    parser.add_argument("--leave-server-running", action="store_true")
    return parser


def _manifest_run_id(path: Path) -> str:
    expanded = path.expanduser()
    return expanded.parent.name.strip() or expanded.stem.strip() or "gr00t-policy-smoke"


def _redacted_exit_message(exc: BaseException) -> str:
    if isinstance(exc, SystemExit):
        code = exc.code
        if code is None:
            return "GR00T policy smoke failed."
        if isinstance(code, int):
            return f"GR00T policy smoke failed with exit code {code}."
        return _redact_observable_text(str(code))
    return _redact_observable_text(str(exc))


def _sanitized_command_argv(command_argv: Sequence[str]) -> tuple[str, ...]:
    redacted: list[str] = []
    redact_next = False
    for raw_arg in command_argv:
        arg = str(raw_arg)
        sanitized, redact_next = _sanitize_command_arg(arg, redact_next=redact_next)
        redacted.append(sanitized)
    return tuple(redacted)


def _sanitize_command_arg(arg: str, *, redact_next: bool) -> tuple[str, bool]:
    if redact_next:
        return _redacted_following_arg(arg)
    inline_secret = _redacted_inline_secret_arg(arg)
    if inline_secret is not None:
        return inline_secret, False
    forwarded_secret = _redacted_forwarded_server_secret_arg(arg)
    if forwarded_secret is not None:
        return forwarded_secret
    return _sanitized_non_secret_arg(arg), _looks_secret_arg_flag(arg)


def _redacted_following_arg(arg: str) -> tuple[str, bool]:
    if arg == "--server-arg":
        return arg, True
    return "[redacted]", False


def _redacted_inline_secret_arg(arg: str) -> str | None:
    flag, separator, _value = arg.partition("=")
    if separator and _looks_secret_arg_flag(flag):
        return f"{flag}=[redacted]"
    return None


def _redacted_forwarded_server_secret_arg(arg: str) -> tuple[str, bool] | None:
    flag, separator, value = arg.partition("=")
    if flag != "--server-arg" or not separator or not _looks_secret_arg_flag(value):
        return None
    value_flag, value_separator, _value_secret = value.partition("=")
    if value_separator:
        return f"--server-arg={value_flag}=[redacted]", False
    return arg, True


def _sanitized_non_secret_arg(arg: str) -> str:
    safe_arg = _redact_observable_text(arg)
    return safe_arg if safe_arg.strip() else "[redacted]"


def _sanitized_command_display(command_argv: Sequence[str]) -> str:
    return shlex.join(_sanitize_display_arg(arg) for arg in _sanitized_command_argv(command_argv))


def _sanitize_display_arg(value: str) -> str:
    return _HOST_LOCAL_PATH_PATTERN.sub("<host-local-path>", value)


def _looks_secret_arg_flag(arg: str) -> bool:
    if not arg.startswith("-"):
        return False
    flag = arg.split("=", maxsplit=1)[0]
    return flag in _SECRET_ARG_FLAGS or _SECRET_ARG_NAME_PATTERN.search(flag) is not None


def _command_argv_from_input(argv: Sequence[str] | None) -> tuple[str, ...]:
    if argv is None:
        return _sanitized_command_argv(sys.argv)
    return _sanitized_command_argv(("smoke_gr00t_policy.py", *argv))


def _manifest_path_from_command_argv(command_argv: Sequence[str]) -> Path | None:
    for index, arg in enumerate(command_argv):
        if arg == "--run-manifest" and index + 1 < len(command_argv):
            return Path(command_argv[index + 1])
        if arg.startswith("--run-manifest="):
            value = arg.split("=", maxsplit=1)[1]
            return Path(value) if value.strip() else None
    return None


def _write_manifest(
    run_manifest: Path,
    *,
    input_fixture: Path | None,
    provider_events: list[object],
    output: JSONDict,
    status: str,
    command_argv: Sequence[str],
) -> None:
    if input_fixture is not None and not input_fixture.expanduser().exists():
        input_fixture = None
    write_run_manifest(
        run_manifest,
        build_run_manifest(
            run_id=_manifest_run_id(run_manifest),
            provider_profile="gr00t",
            capability="policy",
            status=status,
            env_vars=_MANIFEST_ENV_VARS,
            event_count=len(provider_events),
            input_fixture=input_fixture,
            result=output,
            command_argv=command_argv,
        ),
    )


def _write_manifest_if_requested(
    args: argparse.Namespace,
    *,
    provider_events: list[object],
    output: JSONDict,
    status: str,
    command_argv: Sequence[str],
) -> None:
    if args.run_manifest is None:
        return
    input_fixture = args.policy_info_json or args.observation_json
    _write_manifest(
        args.run_manifest,
        input_fixture=input_fixture,
        provider_events=provider_events,
        output=output,
        status=status,
        command_argv=command_argv,
    )


def _parse_args_or_write_manifest(
    argv: list[str] | None,
    command_argv: tuple[str, ...],
) -> argparse.Namespace:
    try:
        return _parser().parse_args(argv)
    except SystemExit as exc:
        if _parser_exit_succeeded(exc):
            raise
        _write_parse_failure_manifest(exc, command_argv)
    except Exception as exc:
        _write_parse_failure_manifest(exc, command_argv)


def _parser_exit_succeeded(exc: SystemExit) -> bool:
    return exc.code is None or exc.code == 0


def _write_parse_failure_manifest(
    exc: BaseException,
    command_argv: tuple[str, ...],
) -> None:
    redacted_error = _redacted_exit_message(exc)
    output: JSONDict = {"error": redacted_error}
    manifest_path = _manifest_path_from_command_argv(command_argv)
    if manifest_path is not None:
        _write_manifest(
            manifest_path,
            input_fixture=None,
            provider_events=[],
            output=output,
            status="failed",
            command_argv=command_argv,
        )
    raise SystemExit(redacted_error) from None


def _ensure_gr00t_root_importable(args: argparse.Namespace) -> None:
    if args.gr00t_root is not None:
        root = args.gr00t_root.expanduser().resolve()
        if str(root) not in sys.path:
            sys.path.insert(0, str(root))


def _validate_smoke_args(args: argparse.Namespace) -> None:
    if args.timeout_ms <= 0:
        raise SystemExit("--timeout-ms must be greater than 0.")
    if args.port <= 0:
        raise SystemExit("--port must be greater than 0.")
    if args.action_horizon is not None and args.action_horizon <= 0:
        raise SystemExit("--action-horizon must be greater than 0.")
    if not args.health_only and args.translator is None:
        raise SystemExit("--translator is required unless --health-only is set.")


def _load_translator(args: argparse.Namespace) -> Callable[..., Any] | None:
    if args.translator is None:
        return None
    return _load_callable(
        args.translator,
        name="translator",
        allow_code=args.allow_translator_code,
        flag="--allow-translator-code",
    )


def _create_provider(
    state: _SmokeRunState,
    translator: Callable[..., Any] | None,
) -> GrootPolicyClientProvider:
    args = state.args
    return GrootPolicyClientProvider(
        host=args.host,
        port=args.port,
        timeout_ms=args.timeout_ms,
        api_token=args.api_token,
        strict=args.strict,
        embodiment_tag=args.embodiment_tag,
        action_translator=translator,
        event_handler=state.provider_events.append,
    )


def _preflight_provider(
    state: _SmokeRunState,
    provider: GrootPolicyClientProvider,
) -> JSONDict:
    state.process = _start_server(state.args)
    if state.process is not None:
        return _wait_for_health(
            provider,
            process=state.process,
            timeout_seconds=state.args.startup_timeout_seconds,
        )
    health = provider.health()
    health_payload = health.to_dict()
    if not health.healthy:
        raise SystemExit(f"GR00T provider is not healthy: {health.details}")
    return health_payload


def _run_policy_selection(
    state: _SmokeRunState,
    provider: GrootPolicyClientProvider,
) -> None:
    state.output["health"] = _preflight_provider(state, provider)
    if state.args.health_only:
        return
    result = provider.select_actions(info=_load_policy_info(state.args))
    state.output["result"] = result.to_dict()


def _successful_manifest_status(args: argparse.Namespace) -> str:
    return "skipped" if args.health_only else "passed"


def _write_success_manifest(state: _SmokeRunState) -> None:
    _write_manifest_if_requested(
        state.args,
        provider_events=state.provider_events,
        output=state.output,
        status=_successful_manifest_status(state.args),
        command_argv=state.command_argv,
    )


def _write_failure_manifest(state: _SmokeRunState, exc: BaseException) -> None:
    redacted_error = _redacted_exit_message(exc)
    state.output.setdefault("error", redacted_error)
    _write_manifest_if_requested(
        state.args,
        provider_events=state.provider_events,
        output=state.output,
        status="failed",
        command_argv=state.command_argv,
    )
    raise SystemExit(redacted_error) from None


def _terminate_started_server(state: _SmokeRunState) -> None:
    process = state.process
    if process is None or state.args.leave_server_running or process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait()


def _print_output(output: JSONDict) -> None:
    with suppress(BrokenPipeError):
        print(json.dumps(output, indent=2, sort_keys=True))


def _run_smoke(state: _SmokeRunState) -> None:
    _validate_smoke_args(state.args)
    translator = _load_translator(state.args)
    provider = _create_provider(state, translator)
    _run_policy_selection(state, provider)
    _write_success_manifest(state)


def main(argv: list[str] | None = None) -> int:
    command_argv = _command_argv_from_input(argv)
    args = _parse_args_or_write_manifest(argv, command_argv)
    _ensure_gr00t_root_importable(args)
    state = _SmokeRunState(args=args, command_argv=command_argv)
    try:
        _run_smoke(state)
    except (Exception, SystemExit) as exc:
        _write_failure_manifest(state, exc)
    finally:
        _terminate_started_server(state)
    _print_output(state.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

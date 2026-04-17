#!/usr/bin/env python
"""Run a live NVIDIA Isaac GR00T policy smoke through WorldForge."""

from __future__ import annotations

import argparse
import importlib
import importlib.util
import json
import os
import subprocess
import sys
import time
from collections.abc import Callable
from pathlib import Path
from types import ModuleType
from typing import Any

from worldforge.models import JSONDict
from worldforge.providers import GrootPolicyClientProvider

DEFAULT_MODEL_PATH = "nvidia/GR00T-N1.6-3B"
DEFAULT_EMBODIMENT_TAG = "GR1"
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 5555
DEFAULT_TIMEOUT_MS = 15_000
DEFAULT_STARTUP_TIMEOUT_SECONDS = 300.0


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
    try:
        payload = json.loads(path.expanduser().read_text())
    except FileNotFoundError as exc:
        raise SystemExit(f"{name} file does not exist: {path}") from exc
    except json.JSONDecodeError as exc:
        raise SystemExit(f"{name} file is not valid JSON: {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise SystemExit(f"{name} must decode to a JSON object.")
    return payload


def _module_from_path(path: Path) -> ModuleType:
    resolved = path.expanduser().resolve()
    if not resolved.exists():
        raise SystemExit(f"Python module file does not exist: {path}")
    module_spec = importlib.util.spec_from_file_location(resolved.stem, resolved)
    if module_spec is None or module_spec.loader is None:
        raise SystemExit(f"Could not load Python module from: {path}")
    module = importlib.util.module_from_spec(module_spec)
    module_spec.loader.exec_module(module)
    return module


def _load_callable(spec: str, *, name: str) -> Callable[..., Any]:
    if ":" not in spec:
        raise SystemExit(f"{name} must be formatted as module_or_file:function.")
    module_ref, function_name = spec.rsplit(":", 1)
    if not module_ref.strip() or not function_name.strip():
        raise SystemExit(f"{name} must be formatted as module_or_file:function.")

    candidate_path = Path(module_ref)
    if candidate_path.exists() or module_ref.endswith(".py") or "/" in module_ref:
        module = _module_from_path(candidate_path)
    else:
        try:
            module = importlib.import_module(module_ref)
        except ImportError as exc:
            raise SystemExit(f"Could not import {name} module '{module_ref}': {exc}") from exc

    try:
        loaded = getattr(module, function_name)
    except AttributeError as exc:
        raise SystemExit(f"{name} function '{function_name}' was not found.") from exc
    if not callable(loaded):
        raise SystemExit(f"{name} target '{function_name}' is not callable.")
    return loaded


def _load_policy_info(args: argparse.Namespace) -> JSONDict:
    if args.policy_info_json is not None:
        info = _load_json_file(args.policy_info_json, name="policy-info")
    elif args.observation_json is not None:
        info = {
            "observation": _load_json_file(args.observation_json, name="observation"),
        }
    elif args.observation_module is not None:
        factory = _load_callable(args.observation_module, name="observation factory")
        try:
            produced = factory()
        except Exception as exc:
            raise SystemExit(f"Observation factory failed: {exc}") from exc
        if not isinstance(produced, dict):
            raise SystemExit("Observation factory must return a dictionary.")
        info = dict(produced) if "observation" in produced else {"observation": dict(produced)}
    else:
        raise SystemExit(
            "Live policy smoke requires --policy-info-json, --observation-json, "
            "or --observation-module."
        )

    if args.options_json is not None:
        info["options"] = _load_json_file(args.options_json, name="options")
    if args.embodiment_tag is not None:
        info.setdefault("embodiment_tag", args.embodiment_tag)
    if args.action_horizon is not None:
        info["action_horizon"] = args.action_horizon
    return info


def _server_module_available() -> bool:
    try:
        return importlib.util.find_spec("gr00t.eval.run_gr00t_server") is not None
    except ModuleNotFoundError:
        return False


def _server_command(args: argparse.Namespace) -> tuple[list[str], Path | None]:
    command_prefix: list[str]
    cwd: Path | None = None
    if args.gr00t_root is not None:
        root = args.gr00t_root.expanduser().resolve()
        server_script = root / "gr00t" / "eval" / "run_gr00t_server.py"
        if not server_script.exists():
            raise SystemExit(
                "--gr00t-root must point at an Isaac-GR00T checkout containing "
                "gr00t/eval/run_gr00t_server.py."
            )
        if str(root) not in sys.path:
            sys.path.insert(0, str(root))
        command_prefix = ["uv", "run", "python", "gr00t/eval/run_gr00t_server.py"]
        cwd = root
    elif _server_module_available():
        command_prefix = [sys.executable, "-m", "gr00t.eval.run_gr00t_server"]
    else:
        raise SystemExit(
            "Cannot start GR00T policy server: provide --gr00t-root pointing to an "
            "Isaac-GR00T checkout, or run this script in an environment where "
            "gr00t.eval.run_gr00t_server is importable."
        )

    model_path = args.model_path or DEFAULT_MODEL_PATH
    embodiment_tag = args.embodiment_tag or DEFAULT_EMBODIMENT_TAG
    command = [
        *command_prefix,
        "--embodiment-tag",
        embodiment_tag,
        "--host",
        args.server_host,
        "--port",
        str(args.port),
    ]
    if args.dataset_path is not None:
        command.extend(["--dataset-path", args.dataset_path])
    else:
        command.extend(["--model-path", model_path])
    if args.device is not None:
        command.extend(["--device", args.device])
    command.extend(args.server_arg or [])
    return command, cwd


def _start_server(args: argparse.Namespace) -> subprocess.Popen[bytes] | None:
    if not args.start_server:
        return None
    command, cwd = _server_command(args)
    print("Starting GR00T policy server:", " ".join(command), file=sys.stderr)
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
            "(raw_actions, info, provider_info) and returns WorldForge Action objects."
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
        help="Isaac-GR00T checkout used to launch gr00t/eval/run_gr00t_server.py.",
    )
    parser.add_argument("--model-path", default=os.environ.get("GROOT_MODEL_PATH"))
    parser.add_argument("--dataset-path", default=os.environ.get("GROOT_DATASET_PATH"))
    parser.add_argument("--device", default=os.environ.get("GROOT_POLICY_DEVICE", "cuda:0"))
    parser.add_argument(
        "--server-host",
        default=os.environ.get("GROOT_POLICY_BIND_HOST", DEFAULT_HOST),
        help="Bind host passed to the launched GR00T server.",
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


def main() -> int:
    args = _parser().parse_args()
    if args.gr00t_root is not None:
        root = args.gr00t_root.expanduser().resolve()
        if str(root) not in sys.path:
            sys.path.insert(0, str(root))
    if args.timeout_ms <= 0:
        raise SystemExit("--timeout-ms must be greater than 0.")
    if args.port <= 0:
        raise SystemExit("--port must be greater than 0.")
    if args.action_horizon is not None and args.action_horizon <= 0:
        raise SystemExit("--action-horizon must be greater than 0.")
    if not args.health_only and args.translator is None:
        raise SystemExit("--translator is required unless --health-only is set.")

    translator = (
        None if args.translator is None else _load_callable(args.translator, name="translator")
    )
    provider = GrootPolicyClientProvider(
        host=args.host,
        port=args.port,
        timeout_ms=args.timeout_ms,
        api_token=args.api_token,
        strict=args.strict,
        embodiment_tag=args.embodiment_tag,
        action_translator=translator,
    )

    process = _start_server(args)
    try:
        if process is not None:
            health_payload = _wait_for_health(
                provider,
                process=process,
                timeout_seconds=args.startup_timeout_seconds,
            )
        else:
            health = provider.health()
            health_payload = health.to_dict()
            if not health.healthy:
                raise SystemExit(f"GR00T provider is not healthy: {health.details}")

        output: JSONDict = {"health": health_payload}
        if not args.health_only:
            result = provider.select_actions(info=_load_policy_info(args))
            output["result"] = result.to_dict()
        print(json.dumps(output, indent=2, sort_keys=True))
        return 0
    finally:
        if process is not None and not args.leave_server_running and process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()


if __name__ == "__main__":
    raise SystemExit(main())

"""Run a live NVIDIA Cosmos-Policy server smoke through WorldForge."""

from __future__ import annotations

import argparse
import importlib
import importlib.util
import json
import math
import os
from collections.abc import Callable
from pathlib import Path
from types import ModuleType
from typing import Any

from worldforge.models import JSONDict
from worldforge.providers import CosmosPolicyProvider
from worldforge.providers.cosmos_policy import DEFAULT_COSMOS_POLICY_TIMEOUT_SECONDS
from worldforge.smoke.run_manifest import build_run_manifest, write_run_manifest


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
    else:
        raise SystemExit(
            "Live Cosmos-Policy smoke requires --policy-info-json or --observation-json."
        )

    if args.task_description is not None:
        info["task_description"] = args.task_description
    if args.embodiment_tag is not None:
        info.setdefault("embodiment_tag", args.embodiment_tag)
    if args.action_horizon is not None:
        info["action_horizon"] = args.action_horizon
    if args.return_all_query_results is not None:
        info["return_all_query_results"] = args.return_all_query_results
    return info


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--base-url",
        default=os.environ.get("COSMOS_POLICY_BASE_URL"),
        help="Cosmos-Policy server base URL, e.g. http://127.0.0.1:8777.",
    )
    parser.add_argument("--api-token", default=os.environ.get("COSMOS_POLICY_API_TOKEN"))
    parser.add_argument(
        "--timeout-seconds",
        default=os.environ.get("COSMOS_POLICY_TIMEOUT_SECONDS"),
    )
    parser.add_argument("--model", default=os.environ.get("COSMOS_POLICY_MODEL"))
    parser.add_argument(
        "--embodiment-tag",
        default=os.environ.get("COSMOS_POLICY_EMBODIMENT_TAG", "aloha"),
    )
    parser.add_argument("--action-horizon", type=int, default=None)
    parser.add_argument("--health-only", action="store_true")
    parser.add_argument(
        "--return-all-query-results",
        action=argparse.BooleanOptionalAction,
        default=None,
    )
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
        help="JSON file containing only the ALOHA observation object.",
    )
    parser.add_argument(
        "--task-description",
        help="Task description used with --observation-json or to override policy_info.",
    )
    parser.add_argument(
        "--translator",
        help=(
            "Python action translator formatted as module_or_file:function. The callable receives "
            "(raw_actions, info, provider_info) and returns WorldForge Action objects."
        ),
    )
    return parser


def _parse_timeout_seconds(value: str | None) -> float:
    raw_value = value if value is not None else str(DEFAULT_COSMOS_POLICY_TIMEOUT_SECONDS)
    try:
        parsed = float(raw_value)
    except ValueError:
        raise SystemExit(
            "COSMOS_POLICY_TIMEOUT_SECONDS/--timeout-seconds must be a number greater than 0."
        ) from None
    if not math.isfinite(parsed) or parsed <= 0.0:
        raise SystemExit(
            "COSMOS_POLICY_TIMEOUT_SECONDS/--timeout-seconds must be a number greater than 0."
        )
    return parsed


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    timeout_seconds = _parse_timeout_seconds(args.timeout_seconds)
    if args.action_horizon is not None and args.action_horizon <= 0:
        raise SystemExit("--action-horizon must be greater than 0.")
    if not args.health_only and args.translator is None:
        raise SystemExit("--translator is required unless --health-only is set.")

    translator = (
        None if args.translator is None else _load_callable(args.translator, name="translator")
    )
    provider_events = []
    provider = CosmosPolicyProvider(
        base_url=args.base_url,
        api_token=args.api_token,
        timeout_seconds=timeout_seconds,
        embodiment_tag=args.embodiment_tag,
        model=args.model,
        return_all_query_results=args.return_all_query_results,
        action_translator=translator,
        event_handler=provider_events.append,
    )
    health = provider.health()
    output: JSONDict = {"health": health.to_dict()}
    if not health.healthy:
        raise SystemExit(f"Cosmos-Policy provider is not healthy: {health.details}")
    if not args.health_only:
        result = provider.select_actions(info=_load_policy_info(args))
        output["result"] = result.to_dict()
    if args.run_manifest is not None:
        input_fixture = args.policy_info_json or args.observation_json
        write_run_manifest(
            args.run_manifest,
            build_run_manifest(
                run_id=args.run_manifest.parent.name,
                provider_profile="cosmos-policy",
                capability="policy",
                status="skipped" if args.health_only else "passed",
                env_vars=(
                    "COSMOS_POLICY_BASE_URL",
                    "COSMOS_POLICY_API_TOKEN",
                    "COSMOS_POLICY_TIMEOUT_SECONDS",
                    "COSMOS_POLICY_EMBODIMENT_TAG",
                    "COSMOS_POLICY_MODEL",
                    "COSMOS_POLICY_RETURN_ALL_QUERY_RESULTS",
                    "COSMOS_POLICY_ALLOW_LOCAL_BASE_URL",
                ),
                event_count=len(provider_events),
                input_fixture=input_fixture,
                result=output,
            ),
        )
    print(json.dumps(output, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

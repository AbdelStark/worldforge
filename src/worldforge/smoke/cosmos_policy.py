"""Run a live NVIDIA Cosmos-Policy server smoke through WorldForge."""

from __future__ import annotations

import argparse
import json
import math
import os
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from types import ModuleType
from typing import Any

from worldforge.models import JSONDict, ProviderHealth, _redact_observable_text
from worldforge.providers import CosmosPolicyProvider
from worldforge.providers.cosmos_policy import DEFAULT_COSMOS_POLICY_TIMEOUT_SECONDS
from worldforge.smoke.run_manifest import build_run_manifest, write_run_manifest
from worldforge.smoke.trusted_inputs import (
    callable_attribute as _trusted_callable_attribute,
)
from worldforge.smoke.trusted_inputs import (
    callable_spec_parts as _trusted_callable_spec_parts,
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

_COSMOS_POLICY_MANIFEST_ENV_VARS = (
    "COSMOS_POLICY_BASE_URL",
    "COSMOS_POLICY_API_TOKEN",
    "COSMOS_POLICY_TIMEOUT_SECONDS",
    "COSMOS_POLICY_EMBODIMENT_TAG",
    "COSMOS_POLICY_MODEL",
    "COSMOS_POLICY_RETURN_ALL_QUERY_RESULTS",
    "COSMOS_POLICY_ALLOW_LOCAL_BASE_URL",
    "COSMOS_POLICY_ALLOWED_HOSTS",
)


@dataclass(slots=True)
class _SmokeRunState:
    provider_events: list[object] = field(default_factory=list)
    output: JSONDict = field(default_factory=dict)


def _load_json_file(path: Path, *, name: str) -> JSONDict:
    return _trusted_load_json_object(path, name=name)


def _module_from_path(path: Path, *, allow_code: bool) -> ModuleType:
    return _trusted_module_from_path(
        path,
        name="translator",
        allow_code=allow_code,
        flag="--allow-translator-code",
        trusted_label="translator code",
        opt_in_message=(
            "Loading a translator from a Python file imports and executes local code; "
            "pass --allow-translator-code only for trusted translator code."
        ),
    )


def _require_local_code_allowed(*, name: str, allow_code: bool) -> None:
    _trusted_require_code_allowed(
        name=name,
        allow_code=allow_code,
        flag="--allow-translator-code",
        trusted_label="translator code",
        message=(
            f"Loading {name} imports and executes local Python; pass --allow-translator-code "
            "only for trusted translator code."
        ),
    )


def _split_callable_spec(spec: str, *, name: str) -> tuple[str, str]:
    return _trusted_callable_spec_parts(spec, name=name)


def _looks_like_module_path(module_ref: str) -> bool:
    return _trusted_looks_like_module_path(module_ref)


def _load_callable_module(
    module_ref: str,
    *,
    name: str,
    allow_code: bool,
) -> ModuleType:
    return _trusted_load_callable_module(
        module_ref,
        name=name,
        allow_code=allow_code,
        flag="--allow-translator-code",
        trusted_label="translator code",
    )


def _callable_attribute(module: ModuleType, function_name: str, *, name: str) -> Callable[..., Any]:
    return _trusted_callable_attribute(module, function_name, name=name)


def _load_callable(spec: str, *, name: str, allow_code: bool = False) -> Callable[..., Any]:
    return _trusted_load_callable(
        spec,
        name=name,
        allow_code=allow_code,
        flag="--allow-translator-code",
        trusted_label="translator code",
        require_code=True,
    )


def _load_base_policy_info(args: argparse.Namespace) -> JSONDict:
    if args.policy_info_json is not None:
        return _load_json_file(args.policy_info_json, name="policy-info")
    if args.observation_json is not None:
        return {
            "observation": _load_json_file(args.observation_json, name="observation"),
        }
    raise SystemExit("Live Cosmos-Policy smoke requires --policy-info-json or --observation-json.")


def _apply_policy_info_overrides(info: JSONDict, args: argparse.Namespace) -> None:
    if args.task_description is not None:
        info["task_description"] = args.task_description
    if args.embodiment_tag is not None:
        info.setdefault("embodiment_tag", args.embodiment_tag)
    if args.action_horizon is not None:
        info["action_horizon"] = args.action_horizon
    if args.return_all_query_results is not None:
        info["return_all_query_results"] = args.return_all_query_results


def _load_policy_info(args: argparse.Namespace) -> JSONDict:
    info = _load_base_policy_info(args)
    _apply_policy_info_overrides(info, args)
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
            "(raw_actions, info, provider_info) and returns WorldForge Action objects. "
            "This imports and executes local Python; requires --allow-translator-code."
        ),
    )
    parser.add_argument(
        "--allow-translator-code",
        action="store_true",
        help="Acknowledge that --translator imports and executes trusted local Python code.",
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


def _manifest_run_id(path: Path) -> str:
    expanded = path.expanduser()
    return expanded.parent.name.strip() or expanded.stem.strip() or "cosmos-policy-smoke"


def _redacted_exit_message(exc: BaseException) -> str:
    if isinstance(exc, SystemExit):
        code = exc.code
        if code is None:
            return "Cosmos-Policy smoke failed."
        if isinstance(code, int):
            return f"Cosmos-Policy smoke failed with exit code {code}."
        return _redact_observable_text(str(code))
    return _redact_observable_text(str(exc))


def _validate_smoke_args(args: argparse.Namespace) -> None:
    if args.action_horizon is not None and args.action_horizon <= 0:
        raise SystemExit("--action-horizon must be greater than 0.")
    if not args.health_only and args.translator is None:
        raise SystemExit("--translator is required unless --health-only is set.")


def _load_translator_from_args(args: argparse.Namespace) -> Callable[..., Any] | None:
    if args.translator is None:
        return None
    return _load_callable(
        args.translator,
        name="translator",
        allow_code=args.allow_translator_code,
    )


def _build_provider(
    args: argparse.Namespace,
    *,
    timeout_seconds: float,
    translator: Callable[..., Any] | None,
    provider_events: list[object],
) -> CosmosPolicyProvider:
    return CosmosPolicyProvider(
        base_url=args.base_url,
        api_token=args.api_token,
        timeout_seconds=timeout_seconds,
        embodiment_tag=args.embodiment_tag,
        model=args.model,
        return_all_query_results=args.return_all_query_results,
        action_translator=translator,
        event_handler=provider_events.append,
    )


def _require_healthy_provider(health: ProviderHealth) -> None:
    if not health.healthy:
        raise SystemExit(f"Cosmos-Policy provider is not healthy: {health.details}")


def _success_status(args: argparse.Namespace) -> str:
    return "skipped" if args.health_only else "passed"


def _run_smoke(args: argparse.Namespace, state: _SmokeRunState) -> None:
    _validate_smoke_args(args)
    provider = _build_provider(
        args,
        timeout_seconds=_parse_timeout_seconds(args.timeout_seconds),
        translator=_load_translator_from_args(args),
        provider_events=state.provider_events,
    )
    health = provider.health()
    state.output["health"] = health.to_dict()
    _require_healthy_provider(health)
    if args.health_only:
        return
    result = provider.select_actions(info=_load_policy_info(args))
    state.output["result"] = result.to_dict()


def _write_manifest_if_requested(
    args: argparse.Namespace,
    *,
    provider_events: list[object],
    output: JSONDict,
    status: str,
) -> None:
    if args.run_manifest is None:
        return
    input_fixture = args.policy_info_json or args.observation_json
    if input_fixture is not None and not input_fixture.expanduser().exists():
        input_fixture = None
    write_run_manifest(
        args.run_manifest,
        build_run_manifest(
            run_id=_manifest_run_id(args.run_manifest),
            provider_profile="cosmos-policy",
            capability="policy",
            status=status,
            env_vars=_COSMOS_POLICY_MANIFEST_ENV_VARS,
            event_count=len(provider_events),
            input_fixture=input_fixture,
            result=output,
        ),
    )


def _write_success_manifest(args: argparse.Namespace, state: _SmokeRunState) -> None:
    _write_manifest_if_requested(
        args,
        provider_events=state.provider_events,
        output=state.output,
        status=_success_status(args),
    )


def _write_failure_manifest(
    args: argparse.Namespace,
    state: _SmokeRunState,
    *,
    error: str,
) -> None:
    state.output.setdefault("error", error)
    _write_manifest_if_requested(
        args,
        provider_events=state.provider_events,
        output=state.output,
        status="failed",
    )


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    state = _SmokeRunState()
    try:
        _run_smoke(args, state)
        _write_success_manifest(args, state)
    except (Exception, SystemExit) as exc:
        redacted_error = _redacted_exit_message(exc)
        _write_failure_manifest(args, state, error=redacted_error)
        raise SystemExit(redacted_error) from None
    print(json.dumps(state.output, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python
"""Run a live Hugging Face LeRobot policy smoke through WorldForge.

This is the real-checkpoint counterpart to ``examples/lerobot_e2e_demo.py``. It
loads a LeRobot pretrained policy (``PreTrainedPolicy.from_pretrained``), calls
:class:`LeRobotPolicyProvider.select_actions` with host-supplied observations,
and invokes a host-supplied action translator to map embodiment-specific output
back into WorldForge actions.

The script does not own the LeRobot runtime. Install ``lerobot`` and any robot
or dataset dependencies in the host environment before running:

.. code-block:: bash

   uv venv --python=3.13 .venv-lerobot
   source .venv-lerobot/bin/activate
   uv pip install -e .
   uv pip install "lerobot[aloha]"

Then provide a policy path, an observation source, and a translator:

.. code-block:: bash

   python scripts/smoke_lerobot_policy.py \
     --policy-path lerobot/act_aloha_sim_transfer_cube_human \
     --observation-module /path/to/obs.py:build_observation \
     --translator /path/to/translator.py:translate_actions \
     --device cpu
"""

from __future__ import annotations

import argparse
import json
import os
from collections.abc import Callable
from pathlib import Path
from typing import Any

from worldforge.models import JSONDict
from worldforge.providers import LeRobotPolicyProvider
from worldforge.smoke.run_manifest import build_run_manifest, write_run_manifest
from worldforge.smoke.trusted_inputs import (
    load_callable as _trusted_load_callable,
)
from worldforge.smoke.trusted_inputs import (
    load_json_object as _trusted_load_json_object,
)
from worldforge.smoke.trusted_inputs import (
    module_from_path as _trusted_module_from_path,
)

DEFAULT_DEVICE = "cpu"
DEFAULT_MODE = "select_action"
_RUNTIME_ENV_VARS = (
    "LEROBOT_POLICY_PATH",
    "LEROBOT_POLICY",
    "LEROBOT_POLICY_TYPE",
    "LEROBOT_DEVICE",
    "LEROBOT_CACHE_DIR",
)


class _SmokeRun:
    __slots__ = ("provider", "provider_events")

    def __init__(self, *, provider: LeRobotPolicyProvider, provider_events: list[Any]) -> None:
        self.provider = provider
        self.provider_events = provider_events


def _env_value(name: str) -> str | None:
    raw = os.environ.get(name)
    if raw is None or not raw.strip():
        return None
    return raw.strip()


def _load_json_file(path: Path, *, name: str) -> JSONDict:
    return _trusted_load_json_object(path, name=name)


def _module_from_path(path: Path):
    return _trusted_module_from_path(path)


def _load_callable(spec: str, *, name: str) -> Callable[..., Any]:
    return _trusted_load_callable(spec, name=name)


def _policy_info_from_observation_factory(module_spec: str) -> JSONDict:
    factory = _load_callable(module_spec, name="observation factory")
    try:
        produced = factory()
    except Exception as exc:
        raise SystemExit(f"Observation factory failed: {exc}") from exc
    if not isinstance(produced, dict):
        raise SystemExit("Observation factory must return a dictionary.")
    return dict(produced) if "observation" in produced else {"observation": dict(produced)}


def _base_policy_info(args: argparse.Namespace) -> JSONDict:
    if args.policy_info_json is not None:
        return _load_json_file(args.policy_info_json, name="policy-info")
    if args.observation_json is not None:
        return {"observation": _load_json_file(args.observation_json, name="observation")}
    if args.observation_module is not None:
        return _policy_info_from_observation_factory(args.observation_module)
    raise SystemExit(
        "Live policy smoke requires --policy-info-json, --observation-json, "
        "or --observation-module."
    )


def _apply_policy_info_overrides(info: JSONDict, args: argparse.Namespace) -> JSONDict:
    updated = dict(info)
    if args.options_json is not None:
        updated["options"] = _load_json_file(args.options_json, name="options")
    if args.embodiment_tag is not None:
        updated.setdefault("embodiment_tag", args.embodiment_tag)
    if args.action_horizon is not None:
        updated["action_horizon"] = args.action_horizon
    if args.mode is not None:
        updated["mode"] = args.mode
    return updated


def _load_policy_info(args: argparse.Namespace) -> JSONDict:
    return _apply_policy_info_overrides(_base_policy_info(args), args)


def _validate_smoke_args(args: argparse.Namespace) -> None:
    if not args.policy_path:
        raise SystemExit("Live LeRobot smoke requires --policy-path or LEROBOT_POLICY_PATH.")
    if args.action_horizon is not None and args.action_horizon <= 0:
        raise SystemExit("--action-horizon must be greater than 0.")
    if not args.health_only and args.translator is None:
        raise SystemExit("--translator is required unless --health-only is set.")


def _load_translator(args: argparse.Namespace) -> Callable[..., Any] | None:
    if args.translator is None:
        return None
    return _load_callable(args.translator, name="translator")


def _create_smoke_run(args: argparse.Namespace) -> _SmokeRun:
    provider_events: list[Any] = []
    provider = LeRobotPolicyProvider(
        policy_path=args.policy_path,
        policy_type=args.policy_type,
        device=args.device,
        cache_dir=args.cache_dir,
        embodiment_tag=args.embodiment_tag,
        action_translator=_load_translator(args),
        event_handler=provider_events.append,
    )
    return _SmokeRun(provider=provider, provider_events=provider_events)


def _healthy_provider_output(provider: LeRobotPolicyProvider) -> JSONDict:
    health = provider.health()
    if not health.healthy:
        raise SystemExit(f"LeRobot provider is not healthy: {health.details}")
    return {"health": health.to_dict()}


def _execute_smoke(args: argparse.Namespace, run: _SmokeRun) -> JSONDict:
    output = _healthy_provider_output(run.provider)
    if not args.health_only:
        result = run.provider.select_actions(info=_load_policy_info(args))
        output["result"] = result.to_dict()
    return output


def _manifest_input_fixture(args: argparse.Namespace) -> Path | None:
    return args.policy_info_json or args.observation_json


def _write_smoke_manifest(args: argparse.Namespace, run: _SmokeRun, output: JSONDict) -> None:
    if args.run_manifest is None:
        return
    write_run_manifest(
        args.run_manifest,
        build_run_manifest(
            run_id=args.run_manifest.parent.name,
            provider_profile="lerobot",
            capability="policy",
            status="skipped" if args.health_only else "passed",
            env_vars=_RUNTIME_ENV_VARS,
            event_count=len(run.provider_events),
            input_fixture=_manifest_input_fixture(args),
            result=output,
        ),
    )


def _run_smoke(args: argparse.Namespace) -> JSONDict:
    _validate_smoke_args(args)
    run = _create_smoke_run(args)
    output = _execute_smoke(args, run)
    _write_smoke_manifest(args, run, output)
    return output


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--policy-path",
        default=_env_value("LEROBOT_POLICY_PATH") or _env_value("LEROBOT_POLICY"),
        help="Hugging Face repo id or local directory of a LeRobot checkpoint.",
    )
    parser.add_argument(
        "--policy-type",
        default=_env_value("LEROBOT_POLICY_TYPE"),
        help="Optional LeRobot policy type (act, diffusion, tdmpc, vqbet, pi0, smolvla, ...).",
    )
    parser.add_argument(
        "--device",
        default=_env_value("LEROBOT_DEVICE") or DEFAULT_DEVICE,
        help="Device string passed to policy.to(...) after loading.",
    )
    parser.add_argument(
        "--cache-dir",
        default=_env_value("LEROBOT_CACHE_DIR"),
        help="Optional Hugging Face cache directory override.",
    )
    parser.add_argument(
        "--embodiment-tag",
        default=_env_value("LEROBOT_EMBODIMENT_TAG"),
        help="Optional embodiment tag stored in the ActionPolicyResult.",
    )
    parser.add_argument(
        "--action-horizon",
        type=int,
        default=None,
        help="Optional explicit action horizon. Defaults to the translator's chunk length.",
    )
    parser.add_argument(
        "--mode",
        choices=["select_action", "predict_chunk"],
        default=DEFAULT_MODE,
        help=(
            "Inference mode: 'select_action' for one step or 'predict_chunk' for a full "
            "predicted action chunk (only when the policy implements it)."
        ),
    )
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
        help="JSON file containing only the LeRobot observation dictionary.",
    )
    input_group.add_argument(
        "--observation-module",
        help=(
            "Python factory formatted as module_or_file:function. Returns an observation dict "
            "or a full policy_info object."
        ),
    )
    parser.add_argument(
        "--translator",
        help=(
            "Python action translator formatted as module_or_file:function. The callable "
            "receives (raw_actions, info, provider_info) and returns WorldForge Action "
            "objects, optionally as candidate chunks."
        ),
    )
    parser.add_argument(
        "--options-json",
        type=Path,
        help="Optional JSON file merged into info.options.",
    )
    return parser


def main() -> int:
    args = _parser().parse_args()
    output = _run_smoke(args)
    print(json.dumps(output, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

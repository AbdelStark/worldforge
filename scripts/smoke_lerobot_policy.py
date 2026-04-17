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

   uv venv --python=3.10 .venv-lerobot
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
import importlib
import importlib.util
import json
import os
from collections.abc import Callable
from pathlib import Path
from types import ModuleType
from typing import Any

from worldforge.models import JSONDict
from worldforge.providers import LeRobotPolicyProvider

DEFAULT_DEVICE = "cpu"
DEFAULT_MODE = "select_action"


def _env_value(name: str) -> str | None:
    raw = os.environ.get(name)
    if raw is None or not raw.strip():
        return None
    return raw.strip()


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
        info = {"observation": _load_json_file(args.observation_json, name="observation")}
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
    if args.mode is not None:
        info["mode"] = args.mode
    return info


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
    if not args.policy_path:
        raise SystemExit("Live LeRobot smoke requires --policy-path or LEROBOT_POLICY_PATH.")
    if args.action_horizon is not None and args.action_horizon <= 0:
        raise SystemExit("--action-horizon must be greater than 0.")
    if not args.health_only and args.translator is None:
        raise SystemExit("--translator is required unless --health-only is set.")

    translator = (
        None if args.translator is None else _load_callable(args.translator, name="translator")
    )
    provider = LeRobotPolicyProvider(
        policy_path=args.policy_path,
        policy_type=args.policy_type,
        device=args.device,
        cache_dir=args.cache_dir,
        embodiment_tag=args.embodiment_tag,
        action_translator=translator,
    )
    health = provider.health()
    if not health.healthy:
        raise SystemExit(f"LeRobot provider is not healthy: {health.details}")

    output: JSONDict = {"health": health.to_dict()}
    if not args.health_only:
        result = provider.select_actions(info=_load_policy_info(args))
        output["result"] = result.to_dict()
    print(json.dumps(output, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

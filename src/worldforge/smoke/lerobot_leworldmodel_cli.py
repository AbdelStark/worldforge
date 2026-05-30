"""CLI defaults and validation for the LeRobot plus LeWorldModel smoke runner."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
from typing import Any

from worldforge.providers._config import env_value as _env_value
from worldforge.smoke.leworldmodel import DEFAULT_STABLEWM_HOME
from worldforge.smoke.leworldmodel_bridges import bridge_names, get_bridge

DEFAULT_LEROBOT_POLICY = "lerobot/diffusion_pusht"
DEFAULT_LEWORLDMODEL_POLICY = "pusht/lewm"
DEFAULT_DEVICE = "cpu"
DEFAULT_MODE = "select_action"
DEFAULT_TRANSLATOR = "worldforge.smoke.lerobot_leworldmodel:translate_pusht_xy_actions"
DEFAULT_TASK = (
    "PushT tabletop manipulation: use a LeRobot policy to propose an action chunk, "
    "then rank policy-compatible candidates with a LeWorldModel cost checkpoint."
)
RUNTIME_ENV_VARS = (
    "LEROBOT_POLICY_PATH",
    "LEROBOT_POLICY",
    "LEROBOT_POLICY_TYPE",
    "LEROBOT_DEVICE",
    "LEROBOT_CACHE_DIR",
    "LEWORLDMODEL_CHECKPOINT",
    "LEWORLDMODEL_POLICY",
    "LEWM_POLICY",
    "LEWORLDMODEL_DEVICE",
    "STABLEWM_HOME",
)


def apply_bridge_defaults(args: argparse.Namespace) -> dict[str, Any] | None:
    if args.bridge is None:
        return None
    bridge = require_bridge(args.bridge)
    apply_bridge_input_defaults(args, bridge)
    apply_bridge_runtime_defaults(args, bridge)
    return bridge.to_dict()


def require_bridge(name: str):
    try:
        return get_bridge(name)
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc


def apply_bridge_input_defaults(args: argparse.Namespace, bridge: Any) -> None:
    if should_use_bridge_observation(args):
        args.observation_module = bridge.observation_module
    if should_use_bridge_score_info(args):
        args.score_info_module = bridge.score_info_module
    if should_use_bridge_candidate_builder(args):
        args.candidate_builder = bridge.candidate_builder


def should_use_bridge_observation(args: argparse.Namespace) -> bool:
    return (
        args.observation_module is None
        and args.observation_json is None
        and args.policy_info_json is None
    )


def should_use_bridge_score_info(args: argparse.Namespace) -> bool:
    return (
        args.score_info_module is None
        and args.score_info_json is None
        and args.score_info_npz is None
    )


def should_use_bridge_candidate_builder(args: argparse.Namespace) -> bool:
    return (
        args.candidate_builder is None
        and args.action_candidates_json is None
        and args.action_candidates_npz is None
    )


def apply_bridge_runtime_defaults(args: argparse.Namespace, bridge: Any) -> None:
    if args.translator == DEFAULT_TRANSLATOR:
        args.translator = bridge.translator
    if args.expected_action_dim is None:
        args.expected_action_dim = bridge.expected_action_dim
    if args.expected_horizon is None:
        args.expected_horizon = bridge.expected_horizon
    if args.task == DEFAULT_TASK:
        args.task = bridge.task


def default_policy_path() -> str | None:
    return _env_value("LEROBOT_POLICY_PATH") or _env_value("LEROBOT_POLICY")


def default_lewm_policy() -> str:
    return (
        _env_value("LEWORLDMODEL_POLICY")
        or _env_value("LEWM_POLICY")
        or DEFAULT_LEWORLDMODEL_POLICY
    )


def default_stablewm_home() -> Path:
    return Path(os.environ.get("STABLEWM_HOME", DEFAULT_STABLEWM_HOME)).expanduser()


def default_checkpoint() -> Path | None:
    configured = os.environ.get("LEWORLDMODEL_CHECKPOINT")
    return Path(configured).expanduser() if configured else None


def add_lerobot_runtime_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--policy-path",
        default=default_policy_path(),
        help=(
            "Hugging Face repo id or local directory of a LeRobot checkpoint. "
            f"Example PushT policy: {DEFAULT_LEROBOT_POLICY}."
        ),
    )
    parser.add_argument(
        "--policy-type",
        default=_env_value("LEROBOT_POLICY_TYPE"),
        help="Optional LeRobot policy type such as diffusion, act, vqbet, pi0, or smolvla.",
    )


def add_leworldmodel_runtime_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--lewm-policy",
        default=default_lewm_policy(),
        help="LeWorldModel policy/checkpoint run name relative to STABLEWM_HOME.",
    )
    parser.add_argument(
        "--stablewm-home",
        type=Path,
        default=default_stablewm_home(),
    )
    parser.add_argument(
        "--lewm-cache-dir",
        type=Path,
        default=None,
        help="Checkpoint root passed to LeWorldModelProvider. Defaults to STABLEWM_HOME.",
    )
    parser.add_argument(
        "--checkpoint",
        type=Path,
        default=default_checkpoint(),
        help="Exact LeWorldModel <policy>_object.ckpt path.",
    )


def add_device_runtime_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--device",
        default=DEFAULT_DEVICE,
        help=(
            "Default device for both LeRobot and LeWorldModel unless provider-specific "
            "flags are set."
        ),
    )
    parser.add_argument("--lerobot-device", default=_env_value("LEROBOT_DEVICE"))
    parser.add_argument("--lewm-device", default=_env_value("LEWORLDMODEL_DEVICE"))
    parser.add_argument("--lerobot-cache-dir", default=_env_value("LEROBOT_CACHE_DIR"))
    parser.add_argument("--embodiment-tag", default=_env_value("LEROBOT_EMBODIMENT_TAG") or "pusht")


def add_task_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--mode", choices=("select_action", "predict_chunk"), default=DEFAULT_MODE)
    parser.add_argument(
        "--bridge",
        choices=bridge_names(),
        default=None,
        help=(
            "Use a registered task bridge for observation, score tensors, translator, "
            "candidate builder, and expected LeWorldModel tensor dimensions."
        ),
    )
    parser.add_argument("--action-horizon", type=int, default=None)
    parser.add_argument("--expected-action-dim", type=int, default=None)
    parser.add_argument("--expected-horizon", type=int, default=None)
    parser.add_argument("--task", default=DEFAULT_TASK)
    parser.add_argument(
        "--goal",
        default="choose the lowest-cost PushT policy action chunk",
        help="WorldForge planning goal text.",
    )


def add_artifact_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--state-dir",
        type=Path,
        default=None,
        help="Optional WorldForge state directory. Defaults to a temporary run directory.",
    )
    parser.add_argument(
        "--json-output",
        type=Path,
        default=None,
        help="Write the full run summary JSON while keeping visual terminal output.",
    )
    parser.add_argument(
        "--run-manifest",
        type=Path,
        default=None,
        help="Write a sanitized run_manifest.json evidence file for this live robotics smoke.",
    )


def add_rerun_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--rerun-output",
        type=Path,
        default=None,
        help="Write a visual Rerun .rrd recording of the policy+score run.",
    )
    parser.add_argument(
        "--rerun-spawn",
        action="store_true",
        help="Spawn a local Rerun Viewer and stream the policy+score run to it.",
    )
    parser.add_argument(
        "--rerun-connect-url",
        default=None,
        help="Stream the policy+score run to a remote Rerun gRPC viewer URL.",
    )
    parser.add_argument(
        "--rerun-serve-grpc-port",
        type=int,
        default=None,
        help="Serve the Rerun policy+score recording over an in-process gRPC endpoint.",
    )


def add_tensorboard_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--tensorboard-logdir",
        type=Path,
        default=None,
        help=(
            "Write per-run TensorBoard ``tfevents`` logs to this directory so the "
            "LeWorldModel checkpoint's provenance, score distribution, latencies, and "
            "provider events can be inspected with `tensorboard --logdir <path>`."
        ),
    )
    parser.add_argument(
        "--tensorboard-run-name",
        default=None,
        help=(
            "Optional subdirectory name under --tensorboard-logdir for this run. Defaults "
            "to a timestamped name when --tensorboard-logdir is provided without a run name."
        ),
    )
    parser.add_argument(
        "--tensorboard-flush-secs",
        type=int,
        default=30,
        help="Flush interval (seconds) for the TensorBoard SummaryWriter. Defaults to 30.",
    )


def add_output_control_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--json-only", action="store_true")
    parser.add_argument(
        "--color",
        choices=("auto", "always", "never"),
        default="auto",
        help="Control ANSI colors in the human-readable output.",
    )
    parser.add_argument(
        "--no-color",
        action="store_const",
        const="never",
        dest="color",
        help="Disable ANSI colors in the human-readable output.",
    )
    parser.add_argument(
        "--no-execute",
        action="store_true",
        help="Skip local mock execution after selecting the policy+score plan.",
    )
    parser.add_argument("--health-only", action="store_true")


def add_policy_input_args(parser: argparse.ArgumentParser) -> None:
    input_group = parser.add_mutually_exclusive_group()
    input_group.add_argument("--policy-info-json", type=Path)
    input_group.add_argument("--observation-json", type=Path)
    input_group.add_argument("--observation-module")
    parser.add_argument("--options-json", type=Path)


def add_score_input_args(parser: argparse.ArgumentParser) -> None:
    score_group = parser.add_mutually_exclusive_group()
    score_group.add_argument("--score-info-json", type=Path)
    score_group.add_argument("--score-info-npz", type=Path)
    score_group.add_argument("--score-info-module")


def add_candidate_bridge_args(parser: argparse.ArgumentParser) -> None:
    candidates_group = parser.add_mutually_exclusive_group()
    candidates_group.add_argument("--action-candidates-json", type=Path)
    candidates_group.add_argument("--action-candidates-npz", type=Path)
    candidates_group.add_argument(
        "--candidate-builder",
        help=(
            "Callable module_or_file:function receiving (raw_actions, info, provider_info) "
            "and returning the LeWorldModel action_candidates tensor/list."
        ),
    )
    parser.add_argument("--action-candidates-key", default="action_candidates")
    parser.add_argument(
        "--translator",
        default=DEFAULT_TRANSLATOR,
        help=(
            "Callable module_or_file:function receiving (raw_actions, info, provider_info) "
            "and returning WorldForge Action candidates."
        ),
    )


def parser(description: str | None = None) -> argparse.ArgumentParser:
    argument_parser = argparse.ArgumentParser(
        description=description or __doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    add_lerobot_runtime_args(argument_parser)
    add_leworldmodel_runtime_args(argument_parser)
    add_device_runtime_args(argument_parser)
    add_task_args(argument_parser)
    add_artifact_args(argument_parser)
    add_rerun_args(argument_parser)
    add_tensorboard_args(argument_parser)
    add_output_control_args(argument_parser)
    add_policy_input_args(argument_parser)
    add_score_input_args(argument_parser)
    add_candidate_bridge_args(argument_parser)
    return argument_parser


def validate_main_args(parser: argparse.ArgumentParser, args: argparse.Namespace) -> None:
    validate_policy_path(parser, args)
    validate_positive_integer_options(parser, args)
    validate_planning_inputs_present(parser, args)


def validate_policy_path(parser: argparse.ArgumentParser, args: argparse.Namespace) -> None:
    if not args.policy_path:
        parser.error(
            "real LeRobot+LeWorldModel flow requires --policy-path or LEROBOT_POLICY_PATH."
        )


def validate_positive_integer_options(
    parser: argparse.ArgumentParser,
    args: argparse.Namespace,
) -> None:
    for attr, flag in (
        ("action_horizon", "--action-horizon"),
        ("expected_action_dim", "--expected-action-dim"),
        ("expected_horizon", "--expected-horizon"),
    ):
        value = getattr(args, attr)
        if value is not None and value <= 0:
            parser.error(f"{flag} must be greater than 0.")


def validate_planning_inputs_present(
    parser: argparse.ArgumentParser,
    args: argparse.Namespace,
) -> None:
    if args.health_only:
        return
    if missing_score_info_input(args):
        parser.error(
            "planning requires --score-info-json, --score-info-npz, or --score-info-module."
        )
    if missing_action_candidate_input(args):
        parser.error(
            "planning requires --candidate-builder or prebuilt --action-candidates-* input."
        )


def missing_score_info_input(args: argparse.Namespace) -> bool:
    return (
        args.score_info_json is None
        and args.score_info_npz is None
        and args.score_info_module is None
    )


def missing_action_candidate_input(args: argparse.Namespace) -> bool:
    return (
        args.action_candidates_json is None
        and args.action_candidates_npz is None
        and args.candidate_builder is None
    )

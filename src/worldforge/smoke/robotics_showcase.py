"""One-command real robotics showcase for LeRobot + LeWorldModel."""

from __future__ import annotations

import argparse
import contextlib
import io
import json
import os
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from worldforge.providers._config import env_value as _env_value

from . import lerobot_leworldmodel, leworldmodel_checkpoint
from .lerobot_leworldmodel import (
    DEFAULT_DEVICE,
    DEFAULT_LEROBOT_POLICY,
    DEFAULT_LEWORLDMODEL_POLICY,
    DEFAULT_MODE,
)
from .leworldmodel import DEFAULT_STABLEWM_HOME, _checkpoint_path
from .pusht_showcase_inputs import DEFAULT_ACTION_DIM, DEFAULT_HORIZON

DEFAULT_JSON_OUTPUT = Path("/tmp/worldforge-robotics-showcase/real-run.json")
DEFAULT_RERUN_OUTPUT = Path("/tmp/worldforge-robotics-showcase/real-run.rrd")
PUSHT_INPUT_MODULE = "worldforge.smoke.pusht_showcase_inputs"


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Run the polished WorldForge real robotics showcase: LeRobot proposes "
            "PushT actions, LeWorldModel scores checkpoint-native candidates, and "
            "WorldForge ranks and mock-executes the selected action chunk."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Default command:\n"
            "  scripts/robotics-showcase\n\n"
            "The lower-level configurable runner remains available as:\n"
            "  scripts/lewm-lerobot-real --help"
        ),
    )
    parser.add_argument(
        "--policy-path",
        default=_env_value("LEROBOT_POLICY_PATH")
        or _env_value("LEROBOT_POLICY")
        or DEFAULT_LEROBOT_POLICY,
        help="LeRobot policy repo id or local checkpoint directory.",
    )
    parser.add_argument(
        "--policy-type",
        default=_env_value("LEROBOT_POLICY_TYPE") or "diffusion",
        help="LeRobot policy type. Defaults to the PushT diffusion policy.",
    )
    parser.add_argument(
        "--checkpoint",
        type=Path,
        default=(
            Path(os.environ["LEWORLDMODEL_CHECKPOINT"]).expanduser()
            if os.environ.get("LEWORLDMODEL_CHECKPOINT")
            else None
        ),
        help="Exact LeWorldModel <policy>_object.ckpt path.",
    )
    parser.add_argument(
        "--lewm-policy",
        default=_env_value("LEWORLDMODEL_POLICY")
        or _env_value("LEWM_POLICY")
        or DEFAULT_LEWORLDMODEL_POLICY,
        help="LeWorldModel policy/checkpoint run name relative to STABLEWM_HOME.",
    )
    parser.add_argument(
        "--stablewm-home",
        type=Path,
        default=Path(os.environ.get("STABLEWM_HOME", DEFAULT_STABLEWM_HOME)).expanduser(),
    )
    parser.add_argument("--lewm-cache-dir", type=Path, default=None)
    parser.add_argument(
        "--lewm-revision",
        default=os.environ.get("LEWORLDMODEL_REVISION"),
        help="Optional Hugging Face revision, tag, or commit for auto-built LeWorldModel assets.",
    )
    parser.add_argument("--device", default=DEFAULT_DEVICE)
    parser.add_argument("--lerobot-device", default=_env_value("LEROBOT_DEVICE"))
    parser.add_argument("--lewm-device", default=_env_value("LEWORLDMODEL_DEVICE"))
    parser.add_argument("--lerobot-cache-dir", default=_env_value("LEROBOT_CACHE_DIR"))
    parser.add_argument("--mode", choices=("select_action", "predict_chunk"), default=DEFAULT_MODE)
    parser.add_argument("--state-dir", type=Path, default=None)
    parser.add_argument(
        "--json-output",
        type=Path,
        default=DEFAULT_JSON_OUTPUT,
        help="Write the full summary JSON. Defaults to /tmp to keep the repo clean.",
    )
    parser.add_argument(
        "--run-manifest",
        type=Path,
        default=DEFAULT_JSON_OUTPUT.with_name("run_manifest.json"),
        help="Write a sanitized run_manifest.json beside the default summary artifact.",
    )
    parser.add_argument(
        "--no-json-output",
        action="store_true",
        help="Skip writing the default /tmp JSON artifact.",
    )
    parser.add_argument(
        "--rerun",
        action="store_true",
        help=("Write a visual Rerun recording to /tmp/worldforge-robotics-showcase/real-run.rrd."),
    )
    parser.add_argument(
        "--rerun-output",
        type=Path,
        default=None,
        help="Write a visual Rerun .rrd recording to this path.",
    )
    parser.add_argument(
        "--rerun-spawn",
        action="store_true",
        help="Spawn a local Rerun Viewer for the policy+score run.",
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
    parser.add_argument(
        "--no-rerun",
        action="store_true",
        help="Disable the wrapper's default Rerun recording.",
    )
    parser.add_argument("--json-only", action="store_true")
    parser.add_argument(
        "--tui",
        action="store_true",
        help="Run inference quietly, then open a Textual visual report.",
    )
    parser.add_argument(
        "--no-tui",
        action="store_false",
        dest="tui",
        help="Force the plain terminal report.",
    )
    parser.add_argument(
        "--tui-stage-delay",
        type=float,
        default=0.35,
        help="Seconds between staged Textual report reveals. Defaults to 0.35.",
    )
    parser.add_argument(
        "--no-tui-animation",
        action="store_true",
        help="Disable staged Textual reveal delays and the illustrative arm animation.",
    )
    parser.add_argument(
        "--color",
        choices=("auto", "always", "never"),
        default="auto",
        help="Control ANSI colors in the human-readable output.",
    )
    parser.add_argument("--no-color", action="store_const", const="never", dest="color")
    parser.add_argument("--health-only", action="store_true")
    parser.add_argument("--no-execute", action="store_true")
    parser.add_argument(
        "--allow-unsafe-pickle",
        action="store_true",
        help=(
            "Allow legacy torch.load pickle deserialization while auto-building the "
            "LeWorldModel checkpoint. Use only for trusted weights."
        ),
    )
    return parser


def _append_optional_path(argv: list[str], flag: str, value: Path | str | None) -> None:
    if value is not None:
        argv.extend([flag, str(value)])


def _ensure_checkpoint(args: argparse.Namespace) -> None:
    if args.checkpoint is not None:
        return
    cache_dir = (args.lewm_cache_dir or args.stablewm_home).expanduser()
    target = _checkpoint_path(cache_dir, args.lewm_policy)
    if target.exists():
        return
    print(
        f"LeWorldModel checkpoint missing at {target}; "
        f"building official LeWM checkpoint assets from Hugging Face "
        f"({leworldmodel_checkpoint.DEFAULT_REPO_ID})...",
        file=sys.stderr,
        flush=True,
    )
    leworldmodel_checkpoint.build_checkpoint(
        repo_id=leworldmodel_checkpoint.DEFAULT_REPO_ID,
        policy=args.lewm_policy,
        stablewm_home=cache_dir,
        revision=args.lewm_revision,
        allow_unsafe_pickle=args.allow_unsafe_pickle,
    )


def _forward_args(args: argparse.Namespace) -> list[str]:
    forwarded = [
        "--policy-path",
        args.policy_path,
        "--policy-type",
        args.policy_type,
        "--lewm-policy",
        args.lewm_policy,
        "--stablewm-home",
        str(args.stablewm_home),
        "--device",
        args.device,
        "--mode",
        args.mode,
        "--observation-module",
        f"{PUSHT_INPUT_MODULE}:build_observation",
        "--score-info-module",
        f"{PUSHT_INPUT_MODULE}:build_score_info",
        "--translator",
        f"{PUSHT_INPUT_MODULE}:translate_candidates_contract",
        "--candidate-builder",
        f"{PUSHT_INPUT_MODULE}:build_action_candidates",
        "--expected-action-dim",
        str(DEFAULT_ACTION_DIM),
        "--expected-horizon",
        str(DEFAULT_HORIZON),
        "--task",
        "PushT real LeRobot policy plus LeWorldModel score planning",
        "--goal",
        "rank PushT policy action candidates with a LeWorldModel checkpoint",
        "--color",
        args.color,
    ]
    _append_optional_path(forwarded, "--checkpoint", args.checkpoint)
    _append_optional_path(forwarded, "--lewm-cache-dir", args.lewm_cache_dir)
    _append_optional_path(forwarded, "--lerobot-device", args.lerobot_device)
    _append_optional_path(forwarded, "--lewm-device", args.lewm_device)
    _append_optional_path(forwarded, "--lerobot-cache-dir", args.lerobot_cache_dir)
    _append_optional_path(forwarded, "--state-dir", args.state_dir)
    if not args.no_json_output:
        _append_optional_path(forwarded, "--json-output", args.json_output)
        _append_optional_path(forwarded, "--run-manifest", args.run_manifest)
    if not args.no_rerun and not args.health_only:
        if args.rerun_spawn:
            forwarded.append("--rerun-spawn")
        elif args.rerun_connect_url is not None:
            forwarded.extend(["--rerun-connect-url", args.rerun_connect_url])
        elif args.rerun_serve_grpc_port is not None:
            forwarded.extend(["--rerun-serve-grpc-port", str(args.rerun_serve_grpc_port)])
        elif args.rerun_output is not None:
            forwarded.extend(["--rerun-output", str(args.rerun_output)])
        elif args.rerun:
            forwarded.extend(["--rerun-output", str(DEFAULT_RERUN_OUTPUT)])
    if args.json_only:
        forwarded.append("--json-only")
    if args.health_only:
        forwarded.append("--health-only")
    if args.no_execute:
        forwarded.append("--no-execute")
    return forwarded


def _run_tui_report(
    forwarded: list[str],
    *,
    summary_path: Path | None,
    stage_delay: float,
    animate_arm: bool,
) -> int:
    captured = io.StringIO()
    json_forwarded = list(forwarded)
    if "--json-only" not in json_forwarded:
        json_forwarded.append("--json-only")
    with contextlib.redirect_stdout(captured):
        exit_code = lerobot_leworldmodel.main(json_forwarded)
    output = captured.getvalue()
    if exit_code != 0:
        print(output, end="")
        return exit_code
    try:
        summary = json.loads(output)
    except json.JSONDecodeError as exc:
        raise SystemExit(f"robotics showcase TUI could not parse run summary JSON: {exc}") from exc
    if not isinstance(summary, dict):
        raise SystemExit("robotics showcase TUI expected the run summary to be a JSON object.")
    return _launch_tui(
        summary,
        summary_path=summary_path,
        stage_delay=stage_delay,
        animate_arm=animate_arm,
    )


def _launch_tui(
    summary: dict[str, Any],
    *,
    summary_path: Path | None,
    stage_delay: float,
    animate_arm: bool,
) -> int:
    from worldforge.harness.cli import launch_robotics_showcase_report

    return launch_robotics_showcase_report(
        summary=summary,
        summary_path=summary_path,
        stage_delay=stage_delay,
        animate_arm=animate_arm,
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = _parser()
    args, extra = parser.parse_known_args(argv)
    if not args.health_only:
        _ensure_checkpoint(args)
    forwarded = _forward_args(args)
    forwarded.extend(extra)
    if args.tui and not args.json_only and not args.health_only:
        stage_delay = 0.0 if args.no_tui_animation else max(0.0, args.tui_stage_delay)
        return _run_tui_report(
            forwarded,
            summary_path=None if args.no_json_output else args.json_output,
            stage_delay=stage_delay,
            animate_arm=not args.no_tui_animation,
        )
    return lerobot_leworldmodel.main(forwarded)


if __name__ == "__main__":
    raise SystemExit(main())

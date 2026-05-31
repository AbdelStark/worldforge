"""Shared parser constants and argument helpers."""

from __future__ import annotations

import argparse
from pathlib import Path

from worldforge.models import CAPABILITY_NAMES

CLI_DESCRIPTION = (
    "CLI for WorldForge provider diagnostics, prediction, planning, evaluation, "
    "benchmarking, and runnable demos."
)

CLI_EPILOG = """Common commands:
  worldforge examples
  worldforge doctor
  worldforge world create lab --provider mock
  worldforge world add-object <world-id> cube --x 0 --y 0.5 --z 0
  worldforge world predict <world-id> --object-id <object-id> --x 0.4 --y 0.5 --z 0
  worldforge world list
  worldforge world preflight
  worldforge world migration-preview <world-id>
  worldforge world objects <world-id>
  worldforge world history <world-id>
  worldforge world delete <world-id>
  worldforge provider list
  worldforge provider docs
  worldforge provider info mock
  worldforge provider contract mock
  worldforge provider workbench mock
  worldforge predict kitchen --provider mock --x 0.3 --y 0.8 --z 0.0 --steps 2
  worldforge eval --suite planning --provider mock --format json
  worldforge benchmark --provider mock --iterations 5 --format json
  worldforge runs list
  worldforge drills list
"""

PROFILE_FORMAT_CHOICES: dict[tuple[str, ...], set[str]] = {
    ("eval",): {"markdown", "json", "csv", "html"},
    ("benchmark",): {"markdown", "json", "csv", "html"},
}

DEFAULT_STATE_DIR = ".worldforge/worlds"
DEFAULT_WORKSPACE_DIR = Path(".worldforge")

Subparsers = argparse._SubParsersAction


def _add_state_dir_argument(
    parser: argparse.ArgumentParser,
    *,
    default: str | Path = DEFAULT_STATE_DIR,
    type_: object | None = None,
    help_text: str = "World state directory.",
) -> None:
    kwargs: dict[str, object] = {"default": default, "help": help_text}
    if type_ is not None:
        kwargs["type"] = type_
    parser.add_argument("--state-dir", **kwargs)


def _add_workspace_dir_argument(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--workspace-dir",
        type=Path,
        default=DEFAULT_WORKSPACE_DIR,
        help="WorldForge workspace directory containing runs/.",
    )


def _add_format_argument(
    parser: argparse.ArgumentParser,
    *,
    choices: tuple[str, ...],
    help_text: str,
    default: str = "json",
) -> None:
    parser.add_argument(
        "--format",
        choices=choices,
        default=default,
        help=help_text,
    )


def _add_registered_only_argument(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--registered-only",
        action="store_true",
        help="Show only providers registered for this process.",
    )


def _add_capability_argument(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--capability",
        choices=CAPABILITY_NAMES,
        help="Filter providers by capability name.",
    )


def _add_xyz_arguments(
    parser: argparse.ArgumentParser,
    *,
    required: bool,
    label: str,
) -> None:
    parser.add_argument("--x", type=float, required=required, help=f"{label} x coordinate.")
    parser.add_argument("--y", type=float, required=required, help=f"{label} y coordinate.")
    parser.add_argument("--z", type=float, required=required, help=f"{label} z coordinate.")


def _add_provider_repeat_argument(parser: argparse.ArgumentParser, *, help_text: str) -> None:
    parser.add_argument(
        "--provider",
        dest="providers",
        action="append",
        default=None,
        help=help_text,
    )


def _add_profile_argument(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--profile",
        type=Path,
        help="Non-secret JSON/TOML configuration profile for CLI defaults.",
    )


def _add_run_filter_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--provider",
        help="Filter to runs whose provider name contains this substring (case-insensitive).",
    )
    parser.add_argument(
        "--capability",
        help="Filter to runs that include this capability (exact match).",
    )
    parser.add_argument(
        "--status",
        help="Filter to runs whose status equals this value (case-insensitive).",
    )
    parser.add_argument(
        "--created-from", help="Filter to runs created on or after this YYYY-MM-DD date."
    )
    parser.add_argument(
        "--created-to", help="Filter to runs created on or before this YYYY-MM-DD date."
    )
    parser.add_argument(
        "--artifact-type",
        help="Filter to runs that include a safe artifact of this label or suffix.",
    )

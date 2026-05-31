"""Composable parser construction for the WorldForge CLI."""

from __future__ import annotations

import argparse

from worldforge.cli_args.common import CLI_DESCRIPTION, CLI_EPILOG, PROFILE_FORMAT_CHOICES
from worldforge.cli_args.drills import _add_drills_commands
from worldforge.cli_args.provider import _add_provider_commands
from worldforge.cli_args.runs import _add_runs_commands
from worldforge.cli_args.top_level import (
    _add_doctor_command,
    _add_examples_command,
    _add_legacy_providers_command,
)
from worldforge.cli_args.workflows import (
    _add_benchmark_command,
    _add_eval_command,
    _add_negotiate_command,
    _add_predict_command,
    _add_scenario_commands,
)
from worldforge.cli_args.world import _add_world_commands


def build_parser() -> argparse.ArgumentParser:
    """Build the public WorldForge command-line parser."""

    parser = argparse.ArgumentParser(
        prog="worldforge",
        description=CLI_DESCRIPTION,
        epilog=CLI_EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    subparsers = parser.add_subparsers(dest="command", required=True, metavar="command")

    _add_examples_command(subparsers)
    _add_legacy_providers_command(subparsers)
    _add_provider_commands(subparsers)
    _add_world_commands(subparsers)
    _add_runs_commands(subparsers)
    _add_drills_commands(subparsers)
    _add_doctor_command(subparsers)
    _add_scenario_commands(subparsers)
    _add_negotiate_command(subparsers)
    _add_predict_command(subparsers)
    _add_eval_command(subparsers)
    _add_benchmark_command(subparsers)
    return parser


__all__ = ["PROFILE_FORMAT_CHOICES", "build_parser"]

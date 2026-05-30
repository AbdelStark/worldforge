"""Operator drill command parser construction."""

from __future__ import annotations

from pathlib import Path

from worldforge.cli_args.common import Subparsers, _add_format_argument
from worldforge.operator_drills import DRILL_IDS, DRILL_WORKSPACE_DEFAULT


def _add_drills_commands(subparsers: Subparsers) -> None:
    drills = subparsers.add_parser(
        "drills",
        help="List and run checkout-safe operator failure drills.",
    )
    drills_subparsers = drills.add_subparsers(
        dest="drills_command",
        required=True,
        metavar="command",
    )
    _add_drills_list_command(drills_subparsers)
    _add_drills_run_command(drills_subparsers)


def _add_drills_list_command(subparsers: Subparsers) -> None:
    drills_list = subparsers.add_parser(
        "list",
        help="List deterministic operator failure drills.",
    )
    _add_format_argument(
        drills_list,
        choices=("json", "markdown"),
        default="markdown",
        help_text="Output format for drill metadata.",
    )


def _add_drills_run_command(subparsers: Subparsers) -> None:
    drills_run = subparsers.add_parser(
        "run",
        help="Run one drill or all drills and preserve run manifests.",
    )
    drills_run.add_argument(
        "drill",
        choices=(*DRILL_IDS, "all"),
        help="Drill id to run, or all.",
    )
    drills_run.add_argument(
        "--workspace-dir",
        type=Path,
        default=DRILL_WORKSPACE_DEFAULT,
        help="Workspace directory for drill run manifests.",
    )
    drills_run.add_argument(
        "--bundle",
        action="store_true",
        help="Export an issue bundle for each drill run.",
    )
    _add_format_argument(
        drills_run, choices=("json", "markdown"), help_text="Output format for drill results."
    )

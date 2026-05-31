"""Preserved run command parser construction."""

from __future__ import annotations

from pathlib import Path

from worldforge.cli_args.common import (
    Subparsers,
    _add_format_argument,
    _add_run_filter_arguments,
    _add_workspace_dir_argument,
)


def _add_runs_commands(subparsers: Subparsers) -> None:
    runs = subparsers.add_parser("runs", help="List, bundle, compare, and clean preserved runs.")
    runs_subparsers = runs.add_subparsers(dest="runs_command", required=True, metavar="command")
    _add_runs_list_command(runs_subparsers)
    _add_runs_compare_command(runs_subparsers)
    _add_runs_bundle_command(runs_subparsers)
    _add_runs_index_command(runs_subparsers)
    _add_runs_prune_command(runs_subparsers)
    _add_runs_cleanup_command(runs_subparsers)


def _add_runs_list_command(subparsers: Subparsers) -> None:
    runs_list = subparsers.add_parser("list", help="List preserved run manifests.")
    _add_workspace_dir_argument(runs_list)
    _add_format_argument(
        runs_list, choices=("json", "markdown"), help_text="Output format for run summaries."
    )


def _add_runs_compare_command(subparsers: Subparsers) -> None:
    runs_compare = subparsers.add_parser(
        "compare",
        help="Compare preserved eval or benchmark run reports.",
    )
    runs_compare.add_argument(
        "paths",
        nargs="+",
        type=Path,
        help="Run workspace directories, run_manifest.json files, or report JSON files.",
    )
    _add_format_argument(
        runs_compare,
        choices=("json", "markdown", "csv", "html"),
        help_text="Output format for the comparison summary.",
    )
    runs_compare.add_argument(
        "--mode",
        choices=("comparison", "regression"),
        default="comparison",
        help="Comparison mode: multi-run table or baseline-vs-candidate regression report.",
    )
    runs_compare.add_argument(
        "--output",
        type=Path,
        help="Optional path to write the comparison artifact instead of stdout.",
    )


def _add_runs_bundle_command(subparsers: Subparsers) -> None:
    runs_bundle = subparsers.add_parser(
        "bundle",
        help="Export an issue-ready bundle for one preserved run.",
    )
    runs_bundle.add_argument("run_id", help="Run id under .worldforge/runs/.")
    _add_workspace_dir_argument(runs_bundle)
    runs_bundle.add_argument(
        "--output",
        type=Path,
        help="Bundle output directory. Defaults to <workspace-dir>/issue-bundles/<run-id>.",
    )
    runs_bundle.add_argument(
        "--overwrite",
        action="store_true",
        help="Replace an existing output directory.",
    )
    _add_format_argument(
        runs_bundle,
        choices=("json", "markdown", "html"),
        default="markdown",
        help_text="Output format for the issue bundle summary.",
    )


def _add_runs_index_command(subparsers: Subparsers) -> None:
    runs_index = subparsers.add_parser(
        "index",
        help="Summarize preserved runs with filters and JSON/Markdown/CSV output.",
    )
    _add_workspace_dir_argument(runs_index)
    _add_format_argument(
        runs_index,
        choices=("json", "markdown", "csv"),
        help_text="Output format for the run index.",
    )
    runs_index.add_argument(
        "--output",
        type=Path,
        help="Optional path to write the index instead of stdout.",
    )
    _add_run_filter_arguments(runs_index)


def _add_runs_prune_command(subparsers: Subparsers) -> None:
    runs_prune = subparsers.add_parser(
        "prune",
        help="Plan or apply a retention policy against preserved run workspaces.",
    )
    _add_workspace_dir_argument(runs_prune)
    runs_prune.add_argument(
        "--max-age-days",
        type=int,
        default=None,
        help=(
            "Delete runs older than this many days (default 30). "
            "Pass 0 to override the 24h safety window."
        ),
    )
    runs_prune.add_argument(
        "--keep-latest",
        type=int,
        default=None,
        help="Always retain the newest N runs irrespective of age (default 10).",
    )
    runs_prune.add_argument(
        "--family",
        action="append",
        default=None,
        help=(
            "Restrict pruning to this manifest kind (eval, benchmark, flow, ...). "
            "Repeat to add more."
        ),
    )
    runs_prune.add_argument(
        "--apply",
        action="store_true",
        help="Actually delete selected run workspaces. Default is dry-run.",
    )
    _add_format_argument(
        runs_prune, choices=("json", "markdown"), help_text="Output format for the prune report."
    )
    runs_prune.add_argument(
        "--retention-profile",
        type=Path,
        help="Optional non-secret config profile; uses its runs_retention section as defaults.",
    )


def _add_runs_cleanup_command(subparsers: Subparsers) -> None:
    runs_cleanup = subparsers.add_parser("cleanup", help="Remove old preserved runs.")
    _add_workspace_dir_argument(runs_cleanup)
    runs_cleanup.add_argument(
        "--keep",
        type=int,
        default=10,
        help="Number of newest runs to keep.",
    )
    runs_cleanup.add_argument(
        "--dry-run",
        action="store_true",
        help="Show selected run directories without deleting them.",
    )
    _add_format_argument(
        runs_cleanup, choices=("json", "markdown"), help_text="Output format for cleanup results."
    )

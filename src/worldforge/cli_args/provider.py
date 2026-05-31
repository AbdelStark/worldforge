"""Provider command parser construction."""

from __future__ import annotations

from pathlib import Path

from worldforge.cli_args.common import (
    Subparsers,
    _add_capability_argument,
    _add_registered_only_argument,
    _add_state_dir_argument,
)


def _add_provider_commands(subparsers: Subparsers) -> None:
    provider = subparsers.add_parser("provider", help="Inspect provider profiles and health.")
    provider_subparsers = provider.add_subparsers(dest="provider_command", required=True)
    _add_provider_list_command(provider_subparsers)
    _add_provider_info_command(provider_subparsers)
    _add_provider_health_command(provider_subparsers)
    _add_provider_contract_command(provider_subparsers)
    _add_provider_docs_command(provider_subparsers)
    _add_provider_workbench_command(provider_subparsers)


def _add_provider_list_command(subparsers: Subparsers) -> None:
    provider_list = subparsers.add_parser("list", help="List provider profiles.")
    _add_state_dir_argument(provider_list)
    _add_registered_only_argument(provider_list)
    _add_capability_argument(provider_list)


def _add_provider_info_command(subparsers: Subparsers) -> None:
    provider_info = subparsers.add_parser("info", help="Show provider details.")
    provider_info.add_argument("name", help="Provider name.")
    _add_state_dir_argument(provider_info)


def _add_provider_health_command(subparsers: Subparsers) -> None:
    provider_health = subparsers.add_parser("health", help="Show provider health.")
    provider_health.add_argument("name", nargs="?", help="Optional provider name.")
    _add_state_dir_argument(provider_health)
    _add_registered_only_argument(provider_health)
    _add_capability_argument(provider_health)


def _add_provider_contract_command(subparsers: Subparsers) -> None:
    provider_contract = subparsers.add_parser(
        "contract",
        help="Run provider contract checks and emit issue-ready evidence.",
    )
    provider_contract.add_argument("name", nargs="?", help="Registered or known provider name.")
    provider_contract.add_argument(
        "--factory", help="Direct provider factory path as module:factory."
    )
    provider_contract.add_argument(
        "--format",
        choices=("markdown", "json"),
        default="markdown",
        help="Output format for contract evidence.",
    )
    provider_contract.add_argument(
        "--live",
        action="store_true",
        help="Allow live provider calls on a prepared host.",
    )
    provider_contract.add_argument(
        "--score-info",
        type=Path,
        help="JSON score info payload for score providers.",
    )
    provider_contract.add_argument(
        "--score-candidates",
        type=Path,
        help="JSON action candidates payload for score providers.",
    )
    provider_contract.add_argument(
        "--policy-info",
        type=Path,
        help="JSON policy info payload for policy providers.",
    )
    _add_state_dir_argument(provider_contract)


def _add_provider_docs_command(subparsers: Subparsers) -> None:
    provider_docs = subparsers.add_parser(
        "docs",
        help="List provider documentation paths.",
    )
    provider_docs.add_argument("name", nargs="?", help="Optional provider name.")
    provider_docs.add_argument(
        "--format",
        choices=("markdown", "json"),
        default="markdown",
        help="Output format for provider docs metadata.",
    )


def _add_provider_workbench_command(subparsers: Subparsers) -> None:
    provider_workbench = subparsers.add_parser(
        "workbench",
        help="Run provider authoring checks without launching the TUI.",
    )
    provider_workbench.add_argument("name", help="Provider name.")
    provider_workbench.add_argument(
        "--format",
        choices=("markdown", "json"),
        default="markdown",
        help="Output format for the workbench report.",
    )
    provider_workbench.add_argument(
        "--live",
        action="store_true",
        help="Allow live provider calls on a prepared host.",
    )
    provider_workbench.add_argument(
        "--fixtures-dir",
        type=Path,
        default=Path("tests/fixtures/providers"),
        help="Directory containing provider fixture JSON files.",
    )

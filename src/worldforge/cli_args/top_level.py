"""Top-level miscellaneous command parser construction."""

from __future__ import annotations

from worldforge.cli_args.common import (
    Subparsers,
    _add_capability_argument,
    _add_registered_only_argument,
    _add_state_dir_argument,
)


def _add_examples_command(subparsers: Subparsers) -> None:
    examples = subparsers.add_parser(
        "examples",
        help="List runnable examples grouped by task.",
    )
    examples.add_argument(
        "--format",
        choices=("markdown", "json"),
        default="markdown",
        help="Output format for the examples index.",
    )


def _add_legacy_providers_command(subparsers: Subparsers) -> None:
    providers = subparsers.add_parser("providers", help="List registered providers.")
    _add_state_dir_argument(providers)


def _add_doctor_command(subparsers: Subparsers) -> None:
    doctor = subparsers.add_parser("doctor", help="Inspect the local WorldForge environment.")
    _add_state_dir_argument(doctor)
    _add_registered_only_argument(doctor)
    _add_capability_argument(doctor)

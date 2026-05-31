"""Shared helpers for WorldForge CLI command handlers."""

from __future__ import annotations

import argparse
import json

from worldforge.config_profiles import ConfigProfile


def _print_json(payload: object) -> None:
    print(json.dumps(payload, indent=2))


def _provider_args(providers: list[str]) -> list[str]:
    args: list[str] = []
    for provider in providers:
        args.extend(["--provider", provider])
    return args


def _operation_args(operations: list[str]) -> list[str]:
    args: list[str] = []
    for operation in operations:
        args.extend(["--operation", operation])
    return args


def _command_string(args: list[str]) -> str:
    return "worldforge " + " ".join(args)


def _config_profile_provenance(args: argparse.Namespace) -> dict[str, object] | None:
    profile = getattr(args, "config_profile", None)
    if isinstance(profile, ConfigProfile):
        return profile.to_provenance()
    return None


def _profile_command_args(args: argparse.Namespace) -> list[str]:
    profile = getattr(args, "config_profile", None)
    if not isinstance(profile, ConfigProfile):
        return []
    return ["--profile", profile.source.removeprefix("profile:")]

"""Provider command execution for the WorldForge CLI."""

from __future__ import annotations

import argparse

from worldforge.cli_support import _print_json
from worldforge.framework import WorldForge
from worldforge.models import WorldForgeError
from worldforge.providers import ProviderError
from worldforge.providers.catalog import provider_docs_index


def _provider_docs_entries(name: str | None = None) -> tuple[dict[str, str], ...]:
    entries = provider_docs_index()
    if name is None:
        return entries
    return tuple(entry for entry in entries if entry["name"] == name)


def _print_provider_docs_markdown(entries: tuple[dict[str, str], ...]) -> None:
    print("# WorldForge Provider Docs")
    print()
    print("| Provider | Capability surface | Registration | Docs |")
    print("| --- | --- | --- | --- |")
    for entry in entries:
        print(
            "| "
            f"`{entry['name']}` | "
            f"{entry['capabilities']} | "
            f"{entry['registration']} | "
            f"`{entry['docs_path']}` |"
        )


def _cmd_provider_docs(args: argparse.Namespace, parser: argparse.ArgumentParser) -> int:
    entries = _provider_docs_entries(args.name)
    if not entries:
        parser.exit(2, f"Unknown provider: {args.name}\n")
    if args.format == "json":
        _print_json(entries)
    else:
        _print_provider_docs_markdown(entries)
    return 0


def _cmd_provider_workbench(args: argparse.Namespace) -> int:
    from worldforge.harness.workbench import (
        provider_workbench_markdown,
        provider_workbench_report,
    )

    report = provider_workbench_report(
        args.name,
        live=args.live,
        fixtures_dir=args.fixtures_dir,
    )
    if args.format == "json":
        _print_json(report)
    else:
        print(provider_workbench_markdown(report))
    return 0 if report["status"] == "passed" else 1


def _cmd_providers(args: argparse.Namespace, forge: WorldForge) -> int:
    _print_json([info.to_dict() for info in forge.list_providers()])
    return 0


def _cmd_provider_list(args: argparse.Namespace, forge: WorldForge) -> int:
    report = forge.doctor(
        capability=args.capability,
        registered_only=args.registered_only,
    )
    _print_json([provider.to_dict() for provider in report.providers])
    return 0


def _cmd_provider_info(args: argparse.Namespace, forge: WorldForge) -> int:
    name = args.name
    payload = {
        "registered": name in forge.providers(),
        "profile": forge.provider_profile(name).to_dict(),
        "health": forge.provider_health(name).to_dict(),
        "lifecycle": forge.provider_lifecycle_status(name).to_dict(),
        "config_summary": forge.provider_config_summary(name).to_dict(),
    }
    if name in forge.providers():
        payload["info"] = forge.provider_info(name).to_dict()
    _print_json(payload)
    return 0


def _cmd_provider_health(args: argparse.Namespace, forge: WorldForge) -> int:
    if args.name:
        _print_json(forge.provider_health(args.name).to_dict())
        return 0
    report = forge.doctor(
        capability=args.capability,
        registered_only=args.registered_only,
    )
    _print_json(
        [
            {
                **provider.health.to_dict(),
                "registered": provider.registered,
            }
            for provider in report.providers
        ]
    )
    return 0


def _cmd_provider_contract(args: argparse.Namespace, forge: WorldForge) -> int:
    from worldforge.provider_contracts import (
        load_json_contract_input,
        provider_from_factory_path,
        run_provider_contract,
    )

    if args.factory and args.name:
        raise WorldForgeError("provider contract accepts either a provider name or --factory.")
    if args.factory:
        provider = provider_from_factory_path(args.factory)
        registered = False
        factory_path = args.factory
    else:
        if not args.name:
            raise WorldForgeError("provider contract requires a provider name or --factory.")
        provider = forge._registered_or_known_provider(args.name, include_known=True)
        if provider is None:
            raise ProviderError(f"Provider '{args.name}' is unknown.")
        registered = args.name in forge.providers()
        factory_path = None

    evidence = run_provider_contract(
        provider,
        registered=registered,
        factory_path=factory_path,
        live=args.live,
        score_info=load_json_contract_input(args.score_info, name="score-info"),
        score_action_candidates=load_json_contract_input(
            args.score_candidates,
            name="score-candidates",
        ),
        policy_info=load_json_contract_input(args.policy_info, name="policy-info"),
    )
    if args.format == "json":
        print(evidence.to_json(), end="")
    else:
        print(evidence.to_markdown(), end="")
    return 0 if evidence.status == "passed" else 1


def _cmd_provider(args: argparse.Namespace, forge: WorldForge) -> int | None:
    provider_dispatch = {
        "list": _cmd_provider_list,
        "info": _cmd_provider_info,
        "health": _cmd_provider_health,
        "contract": _cmd_provider_contract,
    }
    handler = provider_dispatch.get(args.provider_command)
    if handler is None:
        return None
    return handler(args, forge)

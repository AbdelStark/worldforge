"""Benchmark command execution for the WorldForge CLI."""

from __future__ import annotations

import argparse
import json
from hashlib import sha256
from pathlib import Path

from worldforge.benchmark import (
    ProviderBenchmarkHarness,
    load_benchmark_budgets,
    load_benchmark_inputs,
)
from worldforge.benchmark_presets import (
    BenchmarkPreset,
    get_preset,
    list_presets,
    load_preset_budgets,
    load_preset_inputs,
    preset_budget_payload,
    preset_inputs_payload,
)
from worldforge.cli_support import (
    _command_string,
    _config_profile_provenance,
    _operation_args,
    _profile_command_args,
    _provider_args,
)
from worldforge.framework import WorldForge
from worldforge.models import JSONDict, WorldForgeError


def _print_preset_list(args: argparse.Namespace) -> int:
    presets = list_presets()
    if args.format == "json":
        print(
            json.dumps(
                {"presets": [preset.to_dict() for preset in presets]},
                sort_keys=True,
                separators=(",", ":"),
            )
        )
        return 0
    if args.format == "csv":
        rows = ["name,category,providers,operations,iterations,budget_file,failure_tolerance"]
        rows.extend(
            f"{preset.name},{preset.category},"
            f"{'+'.join(preset.providers)},"
            f"{'+'.join(preset.operations)},"
            f"{preset.iterations},"
            f"{preset.budget_file or ''},"
            f"{preset.failure_tolerance}"
            for preset in presets
        )
        print("\n".join(rows))
        return 0
    lines = ["# Benchmark Presets", ""]
    for category in ("checkout-safe", "remote-media", "prepared-host", "release"):
        section = [preset for preset in presets if preset.category == category]
        if not section:
            continue
        lines.append(f"## {category}")
        lines.append("")
        for preset in section:
            providers = ", ".join(preset.providers)
            operations = ", ".join(preset.operations)
            skip = preset.skip_reason()
            status = f"skip: {skip}" if skip else "ready"
            lines.append(
                f"- **{preset.name}** — {preset.title}. providers=[{providers}] "
                f"operations=[{operations}] iterations={preset.iterations} "
                f"failure_tolerance={preset.failure_tolerance} status={status}"
            )
            lines.append(f"  {preset.summary}")
        lines.append("")
    print("\n".join(lines).rstrip())
    return 0


def _print_preset_show(args: argparse.Namespace) -> int:
    preset = get_preset(args.show_preset)
    payload = {
        "preset": preset.to_dict(),
        "skip_reason": preset.skip_reason(),
        "configured_providers": list(preset.configured_providers()),
        "inputs_payload": preset_inputs_payload(preset),
        "budget_payload": preset_budget_payload(preset),
    }
    if args.format == "json":
        print(json.dumps(payload, sort_keys=True, separators=(",", ":")))
        return 0
    lines = [
        f"# {preset.title}",
        "",
        f"Name: {preset.name}",
        f"Category: {preset.category}",
        f"Providers: {', '.join(preset.providers)}",
        f"Operations: {', '.join(preset.operations)}",
        f"Iterations: {preset.iterations} (concurrency={preset.concurrency})",
        f"Failure tolerance: {preset.failure_tolerance}",
        f"Inputs file: {preset.inputs_file or '-'}",
        f"Budget file: {preset.budget_file or '-'}",
    ]
    if preset.requires_provider_profiles:
        lines.append(f"Required runtimes: {', '.join(preset.requires_provider_profiles)}")
    if preset.requires_provider_choice:
        lines.append(f"Any-of runtimes: {', '.join(preset.requires_provider_choice)}")
    skip = preset.skip_reason()
    lines.append(f"Skip reason: {skip or 'none (preset can run on this host)'}")
    lines.append("")
    lines.append(preset.summary)
    if preset.notes:
        lines.append("")
        lines.append(preset.notes)
    print("\n".join(lines))
    return 0


def _handle_preset_skip(
    preset: BenchmarkPreset,
    args: argparse.Namespace,
    skip_reason: str | None,
) -> int | None:
    if skip_reason is None:
        return None
    if preset.failure_tolerance != "skip-when-env-missing":
        raise WorldForgeError(
            f"Benchmark preset '{preset.name}' cannot run on this host: {skip_reason}"
        )
    payload = {
        "preset": preset.name,
        "status": "skipped",
        "reason": skip_reason,
    }
    if args.format == "json":
        print(json.dumps(payload, sort_keys=True, separators=(",", ":")))
    else:
        print(f"# Benchmark preset '{preset.name}' skipped\n\nReason: {skip_reason}")
    return 0


def _configured_preset_providers(preset: BenchmarkPreset) -> list[str]:
    providers = list(preset.configured_providers())
    if not providers:
        raise WorldForgeError(
            f"Benchmark preset '{preset.name}' has no configured providers on this host."
        )
    return providers


def _preset_benchmark_report(
    preset: BenchmarkPreset,
    forge: WorldForge,
    providers: list[str],
):
    harness = ProviderBenchmarkHarness(forge=forge)
    return harness.run(
        providers,
        operations=list(preset.operations),
        iterations=preset.iterations,
        concurrency=preset.concurrency,
        inputs=load_preset_inputs(preset),
    )


def _attach_preset_input_metadata(report: object, preset: BenchmarkPreset) -> None:
    inputs_payload = preset_inputs_payload(preset)
    if inputs_payload is None:
        return
    inputs_text = json.dumps(inputs_payload, sort_keys=True).encode("utf-8")
    report.run_metadata["input_file"] = {  # type: ignore[attr-defined]
        "path": f"benchmark_presets/_data/{preset.inputs_file}",
        "sha256": sha256(inputs_text).hexdigest(),
        "metadata": _json_metadata(inputs_payload),
    }


def _preset_budget_gate(
    report: object, preset: BenchmarkPreset
) -> tuple[object | None, JSONDict | None]:
    budgets = load_preset_budgets(preset)
    if not budgets:
        return None, None
    budget_payload = preset_budget_payload(preset)
    budget_file_summary = None
    if budget_payload is not None:
        budget_text = json.dumps(budget_payload, sort_keys=True)
        budget_file_summary = {
            "path": f"benchmark_presets/_data/{preset.budget_file}",
            "sha256": f"sha256:{sha256(budget_text.encode('utf-8')).hexdigest()}",
            "metadata": _json_metadata(budget_payload),
        }
        _attach_benchmark_budget_metadata(report, budget_file_summary)
    return report.evaluate_budgets(budgets), budget_file_summary  # type: ignore[attr-defined]


def _preset_benchmark_command(args: argparse.Namespace, preset: BenchmarkPreset) -> str:
    return _command_string(["benchmark", "--preset", preset.name, *_profile_command_args(args)])


def _preserve_preset_benchmark_run(
    args: argparse.Namespace,
    *,
    preset: BenchmarkPreset,
    providers: list[str],
    report: object,
    benchmark_command: str,
    gate_report: object | None,
) -> None:
    if args.run_workspace is None:
        return
    from worldforge.harness.flows import preserve_benchmark_run_workspace

    preserve_benchmark_run_workspace(
        args.run_workspace,
        providers=providers,
        operations=list(preset.operations),
        artifacts=report.artifacts(),  # type: ignore[attr-defined]
        report=report,
        command=benchmark_command,
        budget_passed=None if gate_report is None else gate_report.passed,  # type: ignore[attr-defined]
        config_profile=_config_profile_provenance(args),
    )


def _print_preset_benchmark_report(
    *,
    preset: BenchmarkPreset,
    report: object,
    gate_report: object | None,
    output_format: str,
) -> int:
    if output_format == "json":
        if gate_report is None:
            print(report.to_json())  # type: ignore[attr-defined]
        else:
            print(
                json.dumps(
                    {
                        "preset": preset.name,
                        "benchmark": report.to_dict(),  # type: ignore[attr-defined]
                        "gate": gate_report.to_dict(),  # type: ignore[attr-defined]
                    },
                    sort_keys=True,
                    separators=(",", ":"),
                )
            )
    elif output_format == "csv":
        print(gate_report.to_csv() if gate_report is not None else report.to_csv())  # type: ignore[attr-defined]
    else:
        print(report.to_markdown())  # type: ignore[attr-defined]
        if gate_report is not None:
            print()
            print(gate_report.to_markdown())  # type: ignore[attr-defined]
    return 0 if gate_report is None or gate_report.passed else 1  # type: ignore[attr-defined]


def _run_preset_benchmark(
    preset: BenchmarkPreset,
    args: argparse.Namespace,
    forge: WorldForge,
) -> int:
    skip_reason = preset.skip_reason()
    skip_result = _handle_preset_skip(preset, args, skip_reason)
    if skip_result is not None:
        return skip_result

    providers = _configured_preset_providers(preset)
    report = _preset_benchmark_report(preset, forge, providers)
    _attach_preset_input_metadata(report, preset)
    gate_report, budget_file_summary = _preset_budget_gate(report, preset)
    report.run_metadata["preset"] = preset.to_dict()
    benchmark_command = _preset_benchmark_command(args, preset)
    _apply_benchmark_provenance(
        report,
        benchmark_command=benchmark_command,
        budget_file_summary=budget_file_summary,
        notes=f"benchmark preset: {preset.name}",
    )
    _preserve_preset_benchmark_run(
        args,
        preset=preset,
        providers=providers,
        report=report,
        benchmark_command=benchmark_command,
        gate_report=gate_report,
    )
    return _print_preset_benchmark_report(
        preset=preset,
        report=report,
        gate_report=gate_report,
        output_format=args.format,
    )


def _read_json_file(path: Path, *, read_error: str, decode_error: str) -> tuple[object, str, Path]:
    resolved_path = path.expanduser()
    try:
        text = resolved_path.read_text(encoding="utf-8")
        payload = json.loads(text)
    except OSError as exc:
        raise WorldForgeError(f"{read_error} {path}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise WorldForgeError(f"{decode_error}: {exc}") from exc
    return payload, text, resolved_path


def _json_metadata(payload: object) -> JSONDict:
    if isinstance(payload, dict) and isinstance(payload.get("metadata"), dict):
        return dict(payload["metadata"])
    return {}


def _load_direct_benchmark_inputs(
    args: argparse.Namespace,
) -> tuple[object | None, JSONDict | None]:
    if not args.input_file:
        return None, None
    input_payload, input_text, input_path = _read_json_file(
        args.input_file,
        read_error="Failed to read benchmark input file",
        decode_error="Benchmark input file must contain valid JSON",
    )
    benchmark_inputs = load_benchmark_inputs(
        input_payload,
        base_path=input_path.parent,
    )
    return benchmark_inputs, {
        "path": str(input_path.resolve()),
        "sha256": sha256(input_text.encode("utf-8")).hexdigest(),
        "metadata": _json_metadata(input_payload),
    }


def _load_direct_benchmark_budgets(
    args: argparse.Namespace,
) -> tuple[list[object], JSONDict | None]:
    if not args.budget_file:
        return [], None
    budget_payload, budget_text, budget_path = _read_json_file(
        args.budget_file,
        read_error="Failed to read benchmark budget file",
        decode_error="Benchmark budget file must contain valid JSON",
    )
    budget_hash = sha256(budget_text.encode("utf-8")).hexdigest()
    return load_benchmark_budgets(budget_payload), {
        "path": str(budget_path.resolve()),
        "sha256": f"sha256:{budget_hash}",
        "metadata": _json_metadata(budget_payload),
    }


def _attach_benchmark_budget_metadata(report: object, budget_file_summary: JSONDict | None) -> None:
    if budget_file_summary is None:
        return
    report.run_metadata["budget_file"] = {  # type: ignore[attr-defined]
        "path": budget_file_summary["path"],
        "sha256": str(budget_file_summary["sha256"]).removeprefix("sha256:"),
        "metadata": budget_file_summary["metadata"],
    }


def _direct_benchmark_command(args: argparse.Namespace, providers: list[str]) -> str:
    return _command_string(
        [
            "benchmark",
            *_provider_args(providers),
            *_operation_args(args.operations or []),
            *_profile_command_args(args),
            "--iterations",
            str(args.iterations),
            "--concurrency",
            str(args.concurrency),
        ]
    )


def _apply_benchmark_provenance(
    report: object,
    *,
    benchmark_command: str,
    budget_file_summary: JSONDict | None,
    notes: str | None = None,
) -> None:
    if report.provenance is None:  # type: ignore[attr-defined]
        return
    envelope_overrides: dict[str, object] = {
        "command": tuple(benchmark_command.split()),
    }
    if notes is not None:
        envelope_overrides["notes"] = notes
    if budget_file_summary is not None:
        envelope_overrides["budget_file"] = budget_file_summary
    report.provenance = report.provenance.with_overrides(**envelope_overrides)  # type: ignore[attr-defined]


def _preserve_direct_benchmark_run(
    args: argparse.Namespace,
    *,
    providers: list[str],
    report: object,
    benchmark_command: str,
    gate_report: object | None,
) -> None:
    if args.run_workspace is None:
        return
    from worldforge.harness.flows import preserve_benchmark_run_workspace

    preserve_benchmark_run_workspace(
        args.run_workspace,
        providers=providers,
        operations=args.operations,
        artifacts=report.artifacts(),  # type: ignore[attr-defined]
        report=report,
        command=benchmark_command,
        budget_passed=None if gate_report is None else gate_report.passed,  # type: ignore[attr-defined]
        config_profile=_config_profile_provenance(args),
    )


def _print_direct_benchmark_report(
    *,
    report: object,
    gate_report: object | None,
    output_format: str,
) -> int:
    if output_format == "json":
        if gate_report is None:
            print(report.to_json())  # type: ignore[attr-defined]
        else:
            print(
                json.dumps(
                    {
                        "benchmark": report.to_dict(),  # type: ignore[attr-defined]
                        "gate": gate_report.to_dict(),  # type: ignore[attr-defined]
                    },
                    sort_keys=True,
                    separators=(",", ":"),
                )
            )
    elif output_format == "csv":
        print(gate_report.to_csv() if gate_report is not None else report.to_csv())  # type: ignore[attr-defined]
    elif output_format == "html":
        print(report.to_html())  # type: ignore[attr-defined]
    elif gate_report is None:
        print(report.to_markdown())  # type: ignore[attr-defined]
    else:
        print(report.to_markdown())  # type: ignore[attr-defined]
        print()
        print(gate_report.to_markdown())  # type: ignore[attr-defined]
    return 0 if gate_report is None or gate_report.passed else 1  # type: ignore[attr-defined]


def _run_direct_benchmark(args: argparse.Namespace, forge: WorldForge) -> int:
    providers = args.providers or ["mock"]
    benchmark_inputs, input_file_metadata = _load_direct_benchmark_inputs(args)
    budgets, budget_file_summary = _load_direct_benchmark_budgets(args)
    harness = ProviderBenchmarkHarness(forge=forge)
    report = harness.run(
        providers,
        operations=args.operations,
        iterations=args.iterations,
        concurrency=args.concurrency,
        inputs=benchmark_inputs,
    )
    if input_file_metadata is not None:
        report.run_metadata["input_file"] = input_file_metadata
    _attach_benchmark_budget_metadata(report, budget_file_summary)
    gate_report = report.evaluate_budgets(budgets) if budgets else None
    benchmark_command = _direct_benchmark_command(args, providers)
    _apply_benchmark_provenance(
        report,
        benchmark_command=benchmark_command,
        budget_file_summary=budget_file_summary,
    )
    _preserve_direct_benchmark_run(
        args,
        providers=providers,
        report=report,
        benchmark_command=benchmark_command,
        gate_report=gate_report,
    )
    return _print_direct_benchmark_report(
        report=report,
        gate_report=gate_report,
        output_format=args.format,
    )


def _cmd_benchmark(args: argparse.Namespace, forge: WorldForge) -> int:
    if args.list_presets:
        return _print_preset_list(args)
    if args.show_preset is not None:
        return _print_preset_show(args)
    if args.preset is not None:
        return _run_preset_benchmark(get_preset(args.preset), args, forge)
    return _run_direct_benchmark(args, forge)

"""Scenario command execution for the WorldForge CLI."""

from __future__ import annotations

import argparse
from collections.abc import Callable
from pathlib import Path

from worldforge.framework import WorldForge


def _cmd_scenario(args: argparse.Namespace) -> int:
    from worldforge.scenarios import load_scenario_matrix, run_scenario, run_scenario_matrix

    matrix = load_scenario_matrix(args.path)
    scenario = matrix.cases[0].scenario
    if args.scenario_command == "validate":
        _print_scenario_validation(matrix, scenario, output_format=args.format)
        return 0

    forge = WorldForge(state_dir=args.state_dir)
    result = _run_loaded_scenario(
        forge=forge,
        matrix=matrix,
        scenario=scenario,
        run_scenario=run_scenario,
        run_scenario_matrix=run_scenario_matrix,
    )
    passed = _scenario_result_passed(result, is_matrix=matrix.is_matrix)
    rendered = _render_scenario_result(result, output_format=args.format)
    _write_or_print_scenario_result(rendered, output_path=args.output)
    return 0 if passed else 1


def _print_scenario_validation(
    matrix: object,
    scenario: object,
    *,
    output_format: str,
) -> None:
    if output_format == "markdown":
        print(_scenario_validation_markdown(matrix, scenario), end="")
        return
    payload = matrix.to_json() if matrix.is_matrix else scenario.to_json()
    print(payload, end="")


def _scenario_validation_markdown(matrix: object, scenario: object) -> str:
    if matrix.is_matrix:
        return _scenario_matrix_validation_markdown(matrix)
    return _scenario_case_validation_markdown(scenario)


def _scenario_matrix_validation_markdown(matrix: object) -> str:
    parameter_names = ", ".join(str(name) for name in matrix.metadata["parameter_names"])
    case_ids = ", ".join(f"`{case.case_id}`" for case in matrix.cases)
    return (
        f"# Scenario Matrix `{matrix.scenario_id}`\n\n"
        f"- case_count: {len(matrix.cases)}\n"
        f"- max_cases: {matrix.metadata['max_cases']}\n"
        f"- parameters: {parameter_names}\n"
        f"- cases: {case_ids}\n\n"
    )


def _scenario_case_validation_markdown(scenario: object) -> str:
    return (
        f"# Scenario `{scenario.id}`\n\n"
        f"- name: {scenario.name}\n"
        f"- provider: {scenario.provider}\n"
        f"- world: {scenario.world_name}\n"
        f"- objects: {len(scenario.objects)}\n"
        f"- actions: {len(scenario.actions)}\n"
        f"- expected_artifacts: {len(scenario.expected_artifacts)}\n\n"
    )


def _run_loaded_scenario(
    *,
    forge: WorldForge,
    matrix: object,
    scenario: object,
    run_scenario: Callable[[WorldForge, object], object],
    run_scenario_matrix: Callable[[WorldForge, object], object],
) -> object:
    return run_scenario_matrix(forge, matrix) if matrix.is_matrix else run_scenario(forge, scenario)


def _scenario_result_passed(result: object, *, is_matrix: bool) -> bool:
    return result.all_cases_passed() if is_matrix else result.all_expectations_passed()


def _render_scenario_result(result: object, *, output_format: str) -> str:
    return result.to_markdown() if output_format == "markdown" else result.to_json()


def _write_or_print_scenario_result(rendered: str, *, output_path: Path | None) -> None:
    if output_path is None:
        print(rendered, end="")
        return
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        rendered if rendered.endswith("\n") else rendered + "\n",
        encoding="utf-8",
    )

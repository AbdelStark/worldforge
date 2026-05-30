"""Markdown rendering helpers for scenario run results."""

from __future__ import annotations

import json
from collections.abc import Sequence
from typing import Protocol

from worldforge.models import JSONDict


class ScenarioExpectationCheckView(Protocol):
    label: str
    kind: str
    expected: object
    observed: object
    passed: bool

    def to_dict(self) -> JSONDict: ...


class ScenarioResultView(Protocol):
    schema_version: int
    scenario_id: str
    world_id: str
    final_step: int
    object_count: int
    expectation_checks: Sequence[ScenarioExpectationCheckView]

    def all_expectations_passed(self) -> bool: ...


class ScenarioMatrixCaseResultView(Protocol):
    case_id: str
    parameters: JSONDict
    result: ScenarioResultView


class ScenarioMatrixResultView(Protocol):
    schema_version: int
    scenario_id: str
    case_results: Sequence[ScenarioMatrixCaseResultView]
    case_count: int
    passed_case_count: int
    failed_case_count: int

    def all_cases_passed(self) -> bool: ...


def scenario_result_to_markdown(result: ScenarioResultView) -> str:
    lines = [
        "# WorldForge Scenario Result",
        "",
        f"- scenario_id: `{result.scenario_id}`",
        f"- world_id: `{result.world_id}`",
        f"- final_step: {result.final_step}",
        f"- object_count: {result.object_count}",
        f"- all_expectations_passed: {result.all_expectations_passed()}",
        "",
        "## Expectations",
        "",
    ]
    if result.expectation_checks:
        lines.extend(_expectation_table_lines(result.expectation_checks))
    else:
        lines.append("- No declared expectations.")
    return "\n".join(lines) + "\n"


def _expectation_table_lines(checks: Sequence[ScenarioExpectationCheckView]) -> list[str]:
    lines = [
        "| Label | Kind | Expected | Observed | Passed |",
        "| --- | --- | --- | --- | --- |",
    ]
    lines.extend(
        f"| {check.label} | {check.kind} | "
        f"{json.dumps(check.expected)} | {json.dumps(check.observed)} | "
        f"{check.passed} |"
        for check in checks
    )
    return lines


def scenario_matrix_result_to_markdown(result: ScenarioMatrixResultView) -> str:
    lines = [
        "# WorldForge Scenario Matrix Result",
        "",
        f"- scenario_id: `{result.scenario_id}`",
        f"- case_count: {result.case_count}",
        f"- passed_case_count: {result.passed_case_count}",
        f"- failed_case_count: {result.failed_case_count}",
        f"- all_cases_passed: {result.all_cases_passed()}",
        "",
        "| Case | Passed | World | Parameters |",
        "| --- | --- | --- | --- |",
    ]
    lines.extend(_matrix_case_rows(result.case_results))
    lines.extend(_failed_case_lines(result.case_results))
    return "\n".join(lines) + "\n"


def _matrix_case_rows(cases: Sequence[ScenarioMatrixCaseResultView]) -> list[str]:
    return [
        "| "
        f"`{case.case_id}` | {case.result.all_expectations_passed()} | "
        f"`{case.result.world_id}` | `{json.dumps(case.parameters, sort_keys=True)}` |"
        for case in cases
    ]


def _failed_case_lines(cases: Sequence[ScenarioMatrixCaseResultView]) -> list[str]:
    failed = [case for case in cases if not case.result.all_expectations_passed()]
    if not failed:
        return []
    lines = ["", "## Failed Cases", ""]
    for case in failed:
        failed_checks = [
            check.to_dict() for check in case.result.expectation_checks if not check.passed
        ]
        lines.append(f"- `{case.case_id}`: `{json.dumps(failed_checks, sort_keys=True)}`")
    return lines

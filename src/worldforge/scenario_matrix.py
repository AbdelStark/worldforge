"""Scenario parameter-matrix expansion helpers."""

from __future__ import annotations

import re
from collections.abc import Mapping
from itertools import product
from typing import Protocol

from worldforge.models import JSONDict, WorldForgeError, require_json_dict
from worldforge.scenario_models import (
    SCENARIO_MATRIX_MAX_CASES,
    SCENARIO_SCHEMA_VERSION,
    SCENARIO_SUPPORTED_SCHEMA_VERSIONS,
    Scenario,
    ScenarioMatrix,
    ScenarioMatrixCase,
)

_MATRIX_PLACEHOLDER_PATTERN = re.compile(r"^\$\{([A-Za-z_][A-Za-z0-9_]*)\}$")
_MATRIX_ALLOWED_EXACT_PATHS: frozenset[tuple[str, ...]] = frozenset(
    {
        ("provider",),
        ("world", "objects", "*", "position"),
    }
)
_MATRIX_ALLOWED_FIELD_PATHS: dict[tuple[str, ...], frozenset[str]] = {
    ("world", "objects", "*", "position"): frozenset({"x", "y", "z"}),
    ("actions", "*", "parameters"): frozenset({"object_id", "provider", "x", "y", "z"}),
}
_MATRIX_ALLOWED_PREFIX_PATHS: tuple[tuple[str, ...], ...] = (("expected_artifacts", "*", "value"),)


class ScenarioFactory(Protocol):
    def __call__(self, payload: JSONDict, *, source: str) -> Scenario: ...


def scenario_matrix_from_payload(
    payload: JSONDict,
    *,
    matrix_payload: JSONDict,
    source: str,
    scenario_factory: ScenarioFactory,
) -> ScenarioMatrix:
    _reject_unresolved_matrix_extends(payload, source=source)
    base_payload = _matrix_base_payload(payload, source=source)
    base_scenario_id = _matrix_base_scenario_id(base_payload, source=source)
    parameters = _matrix_parameters(matrix_payload, source=source)
    max_cases = _matrix_max_cases(matrix_payload.get("max_cases", 16), source=source)
    names = _matrix_parameter_names(parameters, source=source)
    value_lists = _matrix_parameter_value_lists(parameters, names=names, source=source)
    _check_matrix_case_count(value_lists, max_cases=max_cases, source=source)
    return ScenarioMatrix(
        schema_version=SCENARIO_SCHEMA_VERSION,
        scenario_id=base_scenario_id,
        cases=_matrix_cases(
            base_payload,
            base_scenario_id=base_scenario_id,
            names=names,
            value_lists=value_lists,
            source=source,
            scenario_factory=scenario_factory,
        ),
        is_matrix=True,
        metadata={"max_cases": max_cases, "parameter_names": list(names)},
    )


def _reject_unresolved_matrix_extends(payload: JSONDict, *, source: str) -> None:
    if "extends" in payload:
        raise WorldForgeError(
            f"Scenario {source} contains unresolved 'extends'; load it via "
            "load_scenario_matrix(<path>) so the parent path can be resolved from disk."
        )


def _matrix_base_payload(payload: JSONDict, *, source: str) -> JSONDict:
    base_payload = {key: value for key, value in payload.items() if key != "matrix"}
    _check_schema_version(
        base_payload.get("schema_version", SCENARIO_SCHEMA_VERSION), source=source
    )
    return base_payload


def _matrix_base_scenario_id(base_payload: JSONDict, *, source: str) -> str:
    scenario_id = _require_text(base_payload.get("id"), name="scenario id", source=source)
    if scenario_id in {".", ".."} or "/" in scenario_id or "\\" in scenario_id:
        raise WorldForgeError(
            f"Scenario {source} id '{scenario_id}' is traversal-shaped and rejected."
        )
    return scenario_id


def _matrix_parameters(matrix_payload: JSONDict, *, source: str) -> Mapping:
    parameters = matrix_payload.get("parameters")
    if not isinstance(parameters, Mapping) or not parameters:
        raise WorldForgeError(
            f"Scenario {source} matrix.parameters must be a non-empty JSON object."
        )
    return parameters


def _matrix_max_cases(value: object, *, source: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise WorldForgeError(f"Scenario {source} matrix.max_cases must be an integer.")
    if value < 1 or value > SCENARIO_MATRIX_MAX_CASES:
        raise WorldForgeError(
            f"Scenario {source} matrix.max_cases must be between 1 and {SCENARIO_MATRIX_MAX_CASES}."
        )
    return value


def _matrix_parameter_value_lists(
    parameters: Mapping,
    *,
    names: tuple[str, ...],
    source: str,
) -> tuple[tuple[object, ...], ...]:
    return tuple(
        _matrix_parameter_values(parameters[name], name=name, source=source) for name in names
    )


def _check_matrix_case_count(
    value_lists: tuple[tuple[object, ...], ...],
    *,
    max_cases: int,
    source: str,
) -> None:
    case_count = 1
    for values in value_lists:
        case_count *= len(values)
    if case_count > max_cases:
        raise WorldForgeError(
            f"Scenario {source} matrix expands to {case_count} cases, exceeding max_cases "
            f"{max_cases}."
        )


def _matrix_cases(
    base_payload: JSONDict,
    *,
    base_scenario_id: str,
    names: tuple[str, ...],
    value_lists: tuple[tuple[object, ...], ...],
    source: str,
    scenario_factory: ScenarioFactory,
) -> tuple[ScenarioMatrixCase, ...]:
    return tuple(
        _matrix_case(
            base_payload,
            base_scenario_id=base_scenario_id,
            names=names,
            values=values,
            index=index,
            source=source,
            scenario_factory=scenario_factory,
        )
        for index, values in enumerate(product(*value_lists), start=1)
    )


def _matrix_case(
    base_payload: JSONDict,
    *,
    base_scenario_id: str,
    names: tuple[str, ...],
    values: tuple[object, ...],
    index: int,
    source: str,
    scenario_factory: ScenarioFactory,
) -> ScenarioMatrixCase:
    case_parameters = _matrix_case_parameters(names, values=values, source=source)
    case_id = f"{base_scenario_id}-case-{index}"
    substituted = _matrix_case_payload(
        base_payload,
        base_scenario_id=base_scenario_id,
        case_id=case_id,
        case_parameters=case_parameters,
        index=index,
        source=source,
    )
    return ScenarioMatrixCase(
        case_id=case_id,
        parameters=case_parameters,
        scenario=scenario_factory(substituted, source=f"{source}#{case_id}"),
    )


def _matrix_case_parameters(
    names: tuple[str, ...],
    *,
    values: tuple[object, ...],
    source: str,
) -> JSONDict:
    return require_json_dict(
        dict(zip(names, values, strict=True)),
        name=f"Scenario {source} matrix case parameters",
    )


def _matrix_case_payload(
    base_payload: JSONDict,
    *,
    base_scenario_id: str,
    case_id: str,
    case_parameters: JSONDict,
    index: int,
    source: str,
) -> JSONDict:
    substituted = _substitute_matrix_payload(
        base_payload,
        parameters=case_parameters,
        path=(),
        source=source,
    )
    if not isinstance(substituted, dict):
        raise WorldForgeError(f"Scenario {source} matrix expansion must produce an object.")
    substituted["id"] = case_id
    _apply_matrix_case_world_name(substituted, index=index)
    _apply_matrix_case_metadata(
        substituted,
        base_scenario_id=base_scenario_id,
        case_id=case_id,
        case_parameters=case_parameters,
        source=source,
    )
    return substituted


def _apply_matrix_case_world_name(payload: JSONDict, *, index: int) -> None:
    world_payload = payload.get("world")
    if isinstance(world_payload, dict) and isinstance(world_payload.get("name"), str):
        world_payload["name"] = f"{world_payload['name']}-case-{index}"


def _apply_matrix_case_metadata(
    payload: JSONDict,
    *,
    base_scenario_id: str,
    case_id: str,
    case_parameters: JSONDict,
    source: str,
) -> None:
    metadata_payload = payload.get("metadata") or {}
    if not isinstance(metadata_payload, Mapping):
        raise WorldForgeError(f"Scenario {source} 'metadata' must be a JSON object.")
    metadata = dict(metadata_payload)
    metadata["matrix_case"] = {
        "source_id": base_scenario_id,
        "case_id": case_id,
        "parameters": dict(case_parameters),
    }
    payload["metadata"] = metadata


def _matrix_parameter_names(parameters: Mapping, *, source: str) -> tuple[str, ...]:
    names = []
    for name in parameters:
        if not isinstance(name, str) or not name.strip():
            raise WorldForgeError(f"Scenario {source} matrix parameter names must be strings.")
        if _MATRIX_PLACEHOLDER_PATTERN.fullmatch(f"${{{name}}}") is None:
            raise WorldForgeError(
                f"Scenario {source} matrix parameter '{name}' must be a placeholder identifier."
            )
        names.append(name)
    return tuple(sorted(names))


def _matrix_parameter_values(value: object, *, name: str, source: str) -> tuple[object, ...]:
    if not isinstance(value, list) or not value:
        raise WorldForgeError(
            f"Scenario {source} matrix.parameters.{name} must be a non-empty JSON array."
        )
    normalized = []
    for index, item in enumerate(value):
        try:
            checked = require_json_dict(
                {"value": item},
                name=f"Scenario {source} matrix.parameters.{name}[{index}]",
            )["value"]
        except WorldForgeError as exc:
            raise WorldForgeError(
                f"Scenario {source} matrix.parameters.{name}[{index}] must be JSON-native."
            ) from exc
        normalized.append(checked)
    return tuple(normalized)


def _substitute_matrix_payload(
    value: object,
    *,
    parameters: JSONDict,
    path: tuple[str, ...],
    source: str,
) -> object:
    if isinstance(value, str):
        match = _MATRIX_PLACEHOLDER_PATTERN.fullmatch(value)
        if match:
            return _substituted_matrix_value(
                name=match.group(1),
                parameters=parameters,
                path=path,
                source=source,
            )
        if "${" in value:
            raise WorldForgeError(
                f"Scenario {source} matrix placeholders must occupy the entire JSON value."
            )
        return value
    if isinstance(value, list):
        return [
            _substitute_matrix_payload(
                item,
                parameters=parameters,
                path=(*path, "*"),
                source=source,
            )
            for item in value
        ]
    if isinstance(value, dict):
        return {
            key: _substitute_matrix_payload(
                item,
                parameters=parameters,
                path=(*path, str(key)),
                source=source,
            )
            for key, item in value.items()
        }
    return value


def _substituted_matrix_value(
    *,
    name: str,
    parameters: JSONDict,
    path: tuple[str, ...],
    source: str,
) -> object:
    if name not in parameters:
        raise WorldForgeError(
            f"Scenario {source} matrix placeholder '{name}' has no parameter value."
        )
    if not _matrix_substitution_allowed(path):
        raise WorldForgeError(
            f"Scenario {source} matrix placeholder '{name}' is not allowed at "
            f"{_format_matrix_path(path)}."
        )
    return parameters[name]


def _matrix_substitution_allowed(path: tuple[str, ...]) -> bool:
    return any(
        (
            path in _MATRIX_ALLOWED_EXACT_PATHS,
            _matrix_field_substitution_allowed(path),
            _matrix_prefix_substitution_allowed(path),
        )
    )


def _matrix_field_substitution_allowed(path: tuple[str, ...]) -> bool:
    if not path:
        return False
    allowed_fields = _MATRIX_ALLOWED_FIELD_PATHS.get(path[:-1])
    if allowed_fields is None:
        return False
    return path[-1] in allowed_fields


def _matrix_prefix_substitution_allowed(path: tuple[str, ...]) -> bool:
    return any(path[: len(prefix)] == prefix for prefix in _MATRIX_ALLOWED_PREFIX_PATHS)


def _format_matrix_path(path: tuple[str, ...]) -> str:
    return ".".join(path) or "<root>"


def _check_schema_version(value: object, *, source: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise WorldForgeError(
            f"Scenario {source} schema_version must be an integer; got {type(value).__name__}."
        )
    if value not in SCENARIO_SUPPORTED_SCHEMA_VERSIONS:
        raise WorldForgeError(
            f"Scenario {source} schema_version {value} is not supported "
            f"(expected one of {list(SCENARIO_SUPPORTED_SCHEMA_VERSIONS)})."
        )
    return value


def _require_text(value: object, *, name: str, source: str = "") -> str:
    if not isinstance(value, str) or not value.strip():
        prefix = f"Scenario {source} " if source else ""
        raise WorldForgeError(f"{prefix}{name} must be a non-empty string.")
    return value.strip()

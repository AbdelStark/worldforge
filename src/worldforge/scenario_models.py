"""Immutable scenario/result models and action conversion helpers."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field

from worldforge.models import (
    Action,
    BBox,
    JSONDict,
    Position,
    SceneObject,
    WorldForgeError,
    dump_json,
    require_bool,
    require_finite_number,
    require_json_dict,
    require_non_negative_int,
)
from worldforge.scenario_rendering import (
    scenario_matrix_result_to_markdown,
    scenario_result_to_markdown,
)

SCENARIO_SCHEMA_VERSION = 2
SCENARIO_SUPPORTED_SCHEMA_VERSIONS: tuple[int, ...] = (1, 2)
SCENARIO_EXTENDS_MIN_SCHEMA_VERSION = 2
SCENARIO_MAX_EXTENDS_DEPTH = 8

SCENARIO_ACTION_KINDS: tuple[str, ...] = ("move_to", "spawn_object", "predict")
SCENARIO_MATRIX_MAX_CASES = 64


@dataclass(frozen=True, slots=True)
class ScenarioObjectSpec:
    """Initial scene object declared in a scenario."""

    name: str
    position: Position
    bbox: BBox
    id: str | None = None
    is_graspable: bool = False
    metadata: JSONDict = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "name", _scenario_text(self.name, name="ScenarioObjectSpec name"))
        if not isinstance(self.position, Position):
            raise WorldForgeError("ScenarioObjectSpec position must be a Position.")
        if not isinstance(self.bbox, BBox):
            raise WorldForgeError("ScenarioObjectSpec bbox must be a BBox.")
        if self.id is not None:
            object.__setattr__(
                self,
                "id",
                _scenario_text(self.id, name="ScenarioObjectSpec id"),
            )
        object.__setattr__(
            self,
            "is_graspable",
            require_bool(self.is_graspable, name="ScenarioObjectSpec is_graspable"),
        )
        object.__setattr__(
            self,
            "metadata",
            require_json_dict(self.metadata, name="ScenarioObjectSpec metadata"),
        )

    def to_dict(self) -> JSONDict:
        payload: JSONDict = {
            "name": self.name,
            "position": self.position.to_dict(),
            "bbox": self.bbox.to_dict(),
            "is_graspable": self.is_graspable,
            "metadata": dict(self.metadata),
        }
        if self.id is not None:
            payload["id"] = self.id
        return payload

    def to_scene_object(self) -> SceneObject:
        kwargs: dict[str, object] = {
            "name": self.name,
            "position": self.position,
            "bbox": self.bbox,
            "is_graspable": self.is_graspable,
            "metadata": dict(self.metadata),
        }
        if self.id is not None:
            kwargs["id"] = self.id
        return SceneObject(**kwargs)


@dataclass(frozen=True, slots=True)
class ScenarioAction:
    """One action step in a scenario."""

    kind: str
    parameters: JSONDict = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.kind not in SCENARIO_ACTION_KINDS:
            options = ", ".join(SCENARIO_ACTION_KINDS)
            raise WorldForgeError(f"ScenarioAction kind must be one of: {options}.")
        object.__setattr__(
            self,
            "parameters",
            require_json_dict(self.parameters, name="ScenarioAction parameters"),
        )

    def to_dict(self) -> JSONDict:
        return {"kind": self.kind, "parameters": dict(self.parameters)}

    def to_world_action(self) -> Action | None:
        """Return a typed action to apply, or ``None`` for provider prediction steps."""

        if self.kind == "move_to":
            return Action.move_to(
                scenario_required_float(self.parameters, "x"),
                scenario_required_float(self.parameters, "y"),
                scenario_required_float(self.parameters, "z"),
                speed=float(self.parameters.get("speed", 1.0)),
                object_id=self.parameters.get("object_id"),
            )
        if self.kind == "spawn_object":
            position = scenario_position_from_payload(self.parameters, name="spawn_object")
            return Action.spawn_object(
                name=str(self.parameters["name"]),
                position=position,
                bbox=scenario_optional_bbox_from_payload(self.parameters, "bbox"),
            )
        return None


@dataclass(frozen=True, slots=True)
class ScenarioExpectedArtifact:
    """A declared expectation about a scenario's outcome."""

    label: str
    kind: str
    value: object

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "label",
            _scenario_text(self.label, name="ScenarioExpectedArtifact label"),
        )
        if self.kind not in {"object_count", "step", "object_position"}:
            raise WorldForgeError(
                "ScenarioExpectedArtifact kind must be one of: object_count, step, object_position."
            )
        object.__setattr__(
            self,
            "value",
            _scenario_json_value(self.value, name="ScenarioExpectedArtifact value"),
        )

    def to_dict(self) -> JSONDict:
        return {"label": self.label, "kind": self.kind, "value": self.value}


@dataclass(frozen=True, slots=True)
class Scenario:
    """A single, declarative scenario definition."""

    schema_version: int
    id: str
    name: str
    description: str
    provider: str
    world_name: str
    objects: tuple[ScenarioObjectSpec, ...]
    actions: tuple[ScenarioAction, ...]
    expected_artifacts: tuple[ScenarioExpectedArtifact, ...]
    metadata: JSONDict = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "schema_version",
            _scenario_schema_version(self.schema_version, name="Scenario schema_version"),
        )
        object.__setattr__(self, "id", _scenario_text(self.id, name="Scenario id"))
        object.__setattr__(self, "name", _scenario_text(self.name, name="Scenario name"))
        if not isinstance(self.description, str):
            raise WorldForgeError("Scenario description must be a string.")
        object.__setattr__(
            self,
            "provider",
            _scenario_text(self.provider, name="Scenario provider"),
        )
        object.__setattr__(
            self,
            "world_name",
            _scenario_text(self.world_name, name="Scenario world_name"),
        )
        object.__setattr__(
            self,
            "objects",
            _scenario_tuple(
                self.objects,
                item_type=ScenarioObjectSpec,
                name="Scenario objects",
            ),
        )
        object.__setattr__(
            self,
            "actions",
            _scenario_tuple(self.actions, item_type=ScenarioAction, name="Scenario actions"),
        )
        object.__setattr__(
            self,
            "expected_artifacts",
            _scenario_tuple(
                self.expected_artifacts,
                item_type=ScenarioExpectedArtifact,
                name="Scenario expected_artifacts",
            ),
        )
        object.__setattr__(
            self,
            "metadata",
            require_json_dict(self.metadata, name="Scenario metadata"),
        )

    def to_dict(self) -> JSONDict:
        return {
            "schema_version": self.schema_version,
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "provider": self.provider,
            "world": {
                "name": self.world_name,
                "objects": [obj.to_dict() for obj in self.objects],
            },
            "actions": [action.to_dict() for action in self.actions],
            "expected_artifacts": [expected.to_dict() for expected in self.expected_artifacts],
            "metadata": dict(self.metadata),
        }

    def to_json(self, *, indent: int = 2) -> str:
        return dump_json(self.to_dict(), indent=indent) + "\n"


@dataclass(frozen=True, slots=True)
class ScenarioExpectationCheck:
    """Outcome of evaluating one :class:`ScenarioExpectedArtifact`."""

    label: str
    kind: str
    expected: object
    observed: object
    passed: bool

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "label",
            _scenario_text(self.label, name="ScenarioExpectationCheck label"),
        )
        if self.kind not in {"object_count", "step", "object_position"}:
            raise WorldForgeError(
                "ScenarioExpectationCheck kind must be one of: object_count, step, object_position."
            )
        object.__setattr__(
            self,
            "expected",
            _scenario_json_value(self.expected, name="ScenarioExpectationCheck expected"),
        )
        object.__setattr__(
            self,
            "observed",
            _scenario_json_value(self.observed, name="ScenarioExpectationCheck observed"),
        )
        object.__setattr__(
            self,
            "passed",
            require_bool(self.passed, name="ScenarioExpectationCheck passed"),
        )

    def to_dict(self) -> JSONDict:
        return {
            "label": self.label,
            "kind": self.kind,
            "expected": self.expected,
            "observed": self.observed,
            "passed": self.passed,
        }


@dataclass(frozen=True, slots=True)
class ScenarioResult:
    """Outcome of running a scenario."""

    schema_version: int
    scenario_id: str
    world_id: str
    final_step: int
    object_count: int
    expectation_checks: tuple[ScenarioExpectationCheck, ...]

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "schema_version",
            _scenario_schema_version(self.schema_version, name="ScenarioResult schema_version"),
        )
        object.__setattr__(
            self,
            "scenario_id",
            _scenario_text(self.scenario_id, name="ScenarioResult scenario_id"),
        )
        object.__setattr__(
            self,
            "world_id",
            _scenario_text(self.world_id, name="ScenarioResult world_id"),
        )
        object.__setattr__(
            self,
            "final_step",
            require_non_negative_int(self.final_step, name="ScenarioResult final_step"),
        )
        object.__setattr__(
            self,
            "object_count",
            require_non_negative_int(self.object_count, name="ScenarioResult object_count"),
        )
        object.__setattr__(
            self,
            "expectation_checks",
            _scenario_tuple(
                self.expectation_checks,
                item_type=ScenarioExpectationCheck,
                name="ScenarioResult expectation_checks",
            ),
        )

    def all_expectations_passed(self) -> bool:
        return all(check.passed for check in self.expectation_checks)

    def to_dict(self) -> JSONDict:
        return {
            "schema_version": self.schema_version,
            "scenario_id": self.scenario_id,
            "world_id": self.world_id,
            "final_step": self.final_step,
            "object_count": self.object_count,
            "expectation_checks": [check.to_dict() for check in self.expectation_checks],
            "all_expectations_passed": self.all_expectations_passed(),
        }

    def to_json(self, *, indent: int = 2) -> str:
        return dump_json(self.to_dict(), indent=indent) + "\n"

    def to_markdown(self) -> str:
        return scenario_result_to_markdown(self)


@dataclass(frozen=True, slots=True)
class ScenarioMatrixCase:
    """One expanded parameter case for a scenario matrix."""

    case_id: str
    parameters: JSONDict
    scenario: Scenario

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "case_id",
            _scenario_text(self.case_id, name="ScenarioMatrixCase case_id"),
        )
        object.__setattr__(
            self,
            "parameters",
            require_json_dict(self.parameters, name="ScenarioMatrixCase parameters"),
        )
        if not isinstance(self.scenario, Scenario):
            raise WorldForgeError("ScenarioMatrixCase scenario must be a Scenario.")

    def to_dict(self) -> JSONDict:
        return {
            "case_id": self.case_id,
            "parameters": dict(self.parameters),
            "scenario": self.scenario.to_dict(),
        }


@dataclass(frozen=True, slots=True)
class ScenarioMatrix:
    """Expanded scenario matrix with one or more concrete cases."""

    schema_version: int
    scenario_id: str
    cases: tuple[ScenarioMatrixCase, ...]
    is_matrix: bool = False
    metadata: JSONDict = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "schema_version",
            _scenario_schema_version(self.schema_version, name="ScenarioMatrix schema_version"),
        )
        object.__setattr__(
            self,
            "scenario_id",
            _scenario_text(self.scenario_id, name="ScenarioMatrix scenario_id"),
        )
        object.__setattr__(
            self,
            "cases",
            _scenario_tuple(
                self.cases,
                item_type=ScenarioMatrixCase,
                name="ScenarioMatrix cases",
            ),
        )
        object.__setattr__(
            self,
            "is_matrix",
            require_bool(self.is_matrix, name="ScenarioMatrix is_matrix"),
        )
        object.__setattr__(
            self,
            "metadata",
            require_json_dict(self.metadata, name="ScenarioMatrix metadata"),
        )

    def to_dict(self) -> JSONDict:
        return {
            "schema_version": self.schema_version,
            "scenario_id": self.scenario_id,
            "is_matrix": self.is_matrix,
            "case_count": len(self.cases),
            "cases": [case.to_dict() for case in self.cases],
            "metadata": dict(self.metadata),
        }

    def to_json(self, *, indent: int = 2) -> str:
        return dump_json(self.to_dict(), indent=indent) + "\n"


@dataclass(frozen=True, slots=True)
class ScenarioMatrixCaseResult:
    """Outcome for one scenario matrix case."""

    case_id: str
    parameters: JSONDict
    result: ScenarioResult

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "case_id",
            _scenario_text(self.case_id, name="ScenarioMatrixCaseResult case_id"),
        )
        object.__setattr__(
            self,
            "parameters",
            require_json_dict(self.parameters, name="ScenarioMatrixCaseResult parameters"),
        )
        if not isinstance(self.result, ScenarioResult):
            raise WorldForgeError("ScenarioMatrixCaseResult result must be a ScenarioResult.")

    def to_dict(self) -> JSONDict:
        return {
            "case_id": self.case_id,
            "parameters": dict(self.parameters),
            "result": self.result.to_dict(),
            "passed": self.result.all_expectations_passed(),
        }


@dataclass(frozen=True, slots=True)
class ScenarioMatrixResult:
    """Aggregate output from running a scenario matrix."""

    schema_version: int
    scenario_id: str
    case_results: tuple[ScenarioMatrixCaseResult, ...]

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "schema_version",
            _scenario_schema_version(
                self.schema_version,
                name="ScenarioMatrixResult schema_version",
            ),
        )
        object.__setattr__(
            self,
            "scenario_id",
            _scenario_text(self.scenario_id, name="ScenarioMatrixResult scenario_id"),
        )
        object.__setattr__(
            self,
            "case_results",
            _scenario_tuple(
                self.case_results,
                item_type=ScenarioMatrixCaseResult,
                name="ScenarioMatrixResult case_results",
            ),
        )

    @property
    def case_count(self) -> int:
        return len(self.case_results)

    @property
    def passed_case_count(self) -> int:
        return sum(1 for case in self.case_results if case.result.all_expectations_passed())

    @property
    def failed_case_count(self) -> int:
        return self.case_count - self.passed_case_count

    def all_cases_passed(self) -> bool:
        return self.failed_case_count == 0

    def to_dict(self) -> JSONDict:
        failed_cases = [
            case.to_dict()
            for case in self.case_results
            if not case.result.all_expectations_passed()
        ]
        return {
            "schema_version": self.schema_version,
            "scenario_id": self.scenario_id,
            "case_count": self.case_count,
            "passed_case_count": self.passed_case_count,
            "failed_case_count": self.failed_case_count,
            "all_cases_passed": self.all_cases_passed(),
            "cases": [case.to_dict() for case in self.case_results],
            "failed_cases": failed_cases,
        }

    def to_json(self, *, indent: int = 2) -> str:
        return dump_json(self.to_dict(), indent=indent) + "\n"

    def to_markdown(self) -> str:
        return scenario_matrix_result_to_markdown(self)


def scenario_required_float(parameters: Mapping, key: str) -> float:
    value = parameters.get(key)
    if value is None:
        raise WorldForgeError(f"Scenario action parameter '{key}' is required.")
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise WorldForgeError(
            f"Scenario action parameter '{key}' must be a finite number."
        ) from exc
    return require_finite_number(number, name=f"Scenario action parameter '{key}'")


def scenario_position_from_payload(payload: Mapping, *, name: str) -> Position:
    nested = payload.get("position") if "position" in payload else payload
    if not isinstance(nested, Mapping):
        raise WorldForgeError(f"Scenario {name} position must be a JSON object.")
    return Position(
        scenario_required_float(nested, "x"),
        scenario_required_float(nested, "y"),
        scenario_required_float(nested, "z"),
    )


def scenario_optional_bbox_from_payload(payload: Mapping, key: str) -> BBox | None:
    bbox = payload.get(key)
    if bbox is None:
        return None
    if not isinstance(bbox, Mapping):
        raise WorldForgeError(f"Scenario action {key} must be a JSON object or null.")
    bbox_min = bbox.get("min")
    bbox_max = bbox.get("max")
    if not isinstance(bbox_min, Mapping) or not isinstance(bbox_max, Mapping):
        raise WorldForgeError(f"Scenario action {key}.min and {key}.max must be JSON objects.")
    return BBox(
        Position(
            scenario_required_float(bbox_min, "x"),
            scenario_required_float(bbox_min, "y"),
            scenario_required_float(bbox_min, "z"),
        ),
        Position(
            scenario_required_float(bbox_max, "x"),
            scenario_required_float(bbox_max, "y"),
            scenario_required_float(bbox_max, "z"),
        ),
    )


def _scenario_text(value: object, *, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise WorldForgeError(f"{name} must be a non-empty string.")
    return value.strip()


def _scenario_schema_version(value: object, *, name: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise WorldForgeError(f"{name} must be an integer.")
    if value not in SCENARIO_SUPPORTED_SCHEMA_VERSIONS:
        raise WorldForgeError(
            f"{name} {value} is not supported "
            f"(expected one of {list(SCENARIO_SUPPORTED_SCHEMA_VERSIONS)})."
        )
    return value


def _scenario_json_value(value: object, *, name: str) -> object:
    return require_json_dict({"value": value}, name=name)["value"]


def _scenario_tuple(value: object, *, item_type: type, name: str) -> tuple:
    if not isinstance(value, tuple):
        raise WorldForgeError(f"{name} must be a tuple.")
    if not all(isinstance(item, item_type) for item in value):
        raise WorldForgeError(f"{name} must contain only {item_type.__name__}.")
    return value

"""Expectation evaluation helpers for declarative scenario runs."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Protocol

from worldforge.models import JSONDict, SceneObject


class ScenarioWorldView(Protocol):
    object_count: int
    step: int

    def get_object_by_id(self, object_id: str) -> SceneObject | None: ...


class ScenarioExpectedArtifactView(Protocol):
    label: str
    kind: str
    value: object


class CallableExpectationCheckFactory[ExpectationCheckT](Protocol):
    def __call__(
        self,
        *,
        label: str,
        kind: str,
        expected: object,
        observed: object,
        passed: bool,
    ) -> ExpectationCheckT: ...


def evaluate_expectation[ExpectationCheckT](
    world: ScenarioWorldView,
    expected: ScenarioExpectedArtifactView,
    *,
    check_factory: CallableExpectationCheckFactory[ExpectationCheckT],
) -> ExpectationCheckT:
    if expected.kind == "object_count":
        return _object_count_expectation_check(world, expected, check_factory=check_factory)
    if expected.kind == "step":
        return _step_expectation_check(world, expected, check_factory=check_factory)
    return _object_position_expectation_check(world, expected, check_factory=check_factory)


def _object_count_expectation_check[ExpectationCheckT](
    world: ScenarioWorldView,
    expected: ScenarioExpectedArtifactView,
    *,
    check_factory: CallableExpectationCheckFactory[ExpectationCheckT],
) -> ExpectationCheckT:
    return _scalar_expectation_check(
        expected,
        observed=world.object_count,
        check_factory=check_factory,
    )


def _step_expectation_check[ExpectationCheckT](
    world: ScenarioWorldView,
    expected: ScenarioExpectedArtifactView,
    *,
    check_factory: CallableExpectationCheckFactory[ExpectationCheckT],
) -> ExpectationCheckT:
    return _scalar_expectation_check(expected, observed=world.step, check_factory=check_factory)


def _scalar_expectation_check[ExpectationCheckT](
    expected: ScenarioExpectedArtifactView,
    *,
    observed: object,
    check_factory: CallableExpectationCheckFactory[ExpectationCheckT],
) -> ExpectationCheckT:
    return check_factory(
        label=expected.label,
        kind=expected.kind,
        expected=expected.value,
        observed=observed,
        passed=observed == expected.value,
    )


def _object_position_expectation_check[ExpectationCheckT](
    world: ScenarioWorldView,
    expected: ScenarioExpectedArtifactView,
    *,
    check_factory: CallableExpectationCheckFactory[ExpectationCheckT],
) -> ExpectationCheckT:
    target = expected.value if isinstance(expected.value, Mapping) else {}
    found = _expected_object(world, target)
    expected_position = _expected_position_payload(target)
    return check_factory(
        label=expected.label,
        kind=expected.kind,
        expected=expected.value,
        observed=_observed_position_payload(found),
        passed=_position_matches(
            found, expected_position, tolerance=float(target.get("tolerance", 0.05))
        ),
    )


def _expected_object(
    world: ScenarioWorldView, target: Mapping[object, object]
) -> SceneObject | None:
    object_id = target.get("object_id")
    if not object_id:
        return None
    return world.get_object_by_id(str(object_id))


def _expected_position_payload(target: Mapping[object, object]) -> Mapping[object, object]:
    expected_position = target.get("position", {})
    if not isinstance(expected_position, Mapping):
        return {}
    return expected_position


def _observed_position_payload(found: SceneObject | None) -> JSONDict:
    if found is None:
        return {}
    return {
        "x": found.position.x,
        "y": found.position.y,
        "z": found.position.z,
    }


def _position_matches(
    found: SceneObject | None,
    expected_position: Mapping[object, object],
    *,
    tolerance: float,
) -> bool:
    if found is None or not expected_position:
        return False
    observed = {
        "x": found.position.x,
        "y": found.position.y,
        "z": found.position.z,
    }
    return all(
        abs(position - float(expected_position.get(axis, 0.0))) <= tolerance
        for axis, position in observed.items()
    )

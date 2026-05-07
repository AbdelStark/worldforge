"""JSON-native scenario definitions for repeatable WorldForge worlds and runs.

A scenario captures the deterministic setup and execution of a single
WorldForge run as a single, declarative JSON document: which provider to
use, the initial scene objects, an ordered sequence of actions, and the
artifacts a caller expects to see when the scenario completes. The format
is schema-versioned and intentionally narrow — there is no Python execution
from scenario files, no simulator-specific schema, and no environment
mutation.

Use scenarios to:

- Replace ad-hoc Python in examples and onboarding cookbooks with a single
  command (``worldforge scenario run <file>``).
- Capture a regression as a checkout-safe deterministic recipe rather than
  a custom test fixture.
- Document an expected world transition that a contributor can re-run on
  any host with the mock provider registered.

Scenarios are not provider fixtures: provider fixtures live under
``tests/fixtures/providers/`` and exercise individual adapter contracts;
scenarios drive a full ``WorldForge`` instance through a sequence of
public-API calls.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from worldforge.models import (
    Action,
    BBox,
    JSONDict,
    Position,
    SceneObject,
    WorldForgeError,
)

if TYPE_CHECKING:
    from worldforge.framework import World, WorldForge

SCENARIO_SCHEMA_VERSION = 1

SCENARIO_ACTION_KINDS: tuple[str, ...] = ("move_to", "spawn_object", "predict")


@dataclass(frozen=True, slots=True)
class ScenarioObjectSpec:
    """Initial scene object declared in a scenario."""

    name: str
    position: Position
    bbox: BBox
    id: str | None = None
    is_graspable: bool = False
    metadata: JSONDict = field(default_factory=dict)

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
    """One action step in a scenario.

    ``kind`` is one of :data:`SCENARIO_ACTION_KINDS`. ``parameters`` carries
    the kind-specific payload validated by :func:`load_scenario`.
    """

    kind: str
    parameters: JSONDict = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.kind not in SCENARIO_ACTION_KINDS:
            options = ", ".join(SCENARIO_ACTION_KINDS)
            raise WorldForgeError(f"ScenarioAction kind must be one of: {options}.")

    def to_dict(self) -> JSONDict:
        return {"kind": self.kind, "parameters": dict(self.parameters)}

    def to_world_action(self) -> Action | None:
        """Return the typed :class:`Action` to apply, or ``None`` for kind 'predict'.

        ``predict`` does not mutate world state directly — it advances the
        world via :meth:`World.predict`, so the runner constructs a typed
        ``move_to`` action from the parameters at call time.
        """

        if self.kind == "move_to":
            return Action.move_to(
                _require_float(self.parameters, "x"),
                _require_float(self.parameters, "y"),
                _require_float(self.parameters, "z"),
                speed=float(self.parameters.get("speed", 1.0)),
                object_id=self.parameters.get("object_id"),
            )
        if self.kind == "spawn_object":
            position = _position_from_payload(self.parameters, name="spawn_object")
            return Action.spawn_object(
                name=str(self.parameters["name"]),
                position=position,
                bbox=_optional_bbox_from_payload(self.parameters, "bbox"),
            )
        return None


@dataclass(frozen=True, slots=True)
class ScenarioExpectedArtifact:
    """A declared expectation about a scenario's outcome.

    The runner verifies each expectation against the final world state and
    records pass/fail in :class:`ScenarioResult`. Expectations are advisory
    — they do not raise if unmet, they surface as ``failed`` rows so the
    caller (CI gate or human reviewer) decides whether to fail the run.
    """

    label: str
    kind: str  # "object_count" | "step" | "object_position"
    value: object

    def __post_init__(self) -> None:
        if self.kind not in {"object_count", "step", "object_position"}:
            raise WorldForgeError(
                "ScenarioExpectedArtifact kind must be one of: object_count, step, object_position."
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
        return json.dumps(self.to_dict(), indent=indent, sort_keys=True) + "\n"


@dataclass(frozen=True, slots=True)
class ScenarioExpectationCheck:
    """Outcome of evaluating one :class:`ScenarioExpectedArtifact`."""

    label: str
    kind: str
    expected: object
    observed: object
    passed: bool

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
        return json.dumps(self.to_dict(), indent=indent, sort_keys=True) + "\n"

    def to_markdown(self) -> str:
        lines = [
            "# WorldForge Scenario Result",
            "",
            f"- scenario_id: `{self.scenario_id}`",
            f"- world_id: `{self.world_id}`",
            f"- final_step: {self.final_step}",
            f"- object_count: {self.object_count}",
            f"- all_expectations_passed: {self.all_expectations_passed()}",
            "",
            "## Expectations",
            "",
        ]
        if self.expectation_checks:
            lines.extend(
                [
                    "| Label | Kind | Expected | Observed | Passed |",
                    "| --- | --- | --- | --- | --- |",
                ]
            )
            lines.extend(
                f"| {check.label} | {check.kind} | "
                f"{json.dumps(check.expected)} | {json.dumps(check.observed)} | "
                f"{check.passed} |"
                for check in self.expectation_checks
            )
        else:
            lines.append("- No declared expectations.")
        return "\n".join(lines) + "\n"


def load_scenario(path: Path | str) -> Scenario:
    """Load a scenario from a JSON file with strict validation."""

    target = Path(path).expanduser()
    try:
        text = target.read_text(encoding="utf-8")
    except OSError as exc:
        raise WorldForgeError(f"Failed to read scenario file {target}: {exc}") from exc
    return _scenario_from_json_text(text, source=str(target))


def parse_scenario(payload: JSONDict | str) -> Scenario:
    """Parse a scenario from a dict or JSON string."""

    if isinstance(payload, str):
        return _scenario_from_json_text(payload, source="<string>")
    if not isinstance(payload, Mapping):
        raise WorldForgeError("Scenario payload must be a JSON object.")
    return _scenario_from_dict(dict(payload), source="<dict>")


def run_scenario(
    forge: WorldForge,
    scenario: Scenario,
) -> ScenarioResult:
    """Run a scenario against a forge and return a :class:`ScenarioResult`.

    The function creates a new world named ``scenario.world_name`` (if a world
    with that name already exists, ``WorldForgeError`` is raised — scenarios
    do not silently mutate existing state), seeds it with the declared
    objects, and applies the action sequence in order. The function returns a
    structured result; expectations that fail are recorded but do not raise,
    so callers can inspect every check before deciding whether to fail.
    """

    if not isinstance(scenario, Scenario):
        raise WorldForgeError("run_scenario scenario must be a Scenario instance.")

    world = forge.create_world(scenario.world_name, scenario.provider)
    for obj in scenario.objects:
        world.add_object(obj.to_scene_object())

    for action in scenario.actions:
        _apply_scenario_action(world, action, scenario=scenario)

    expectations = tuple(
        _evaluate_expectation(world, expected) for expected in scenario.expected_artifacts
    )
    return ScenarioResult(
        schema_version=SCENARIO_SCHEMA_VERSION,
        scenario_id=scenario.id,
        world_id=world.id,
        final_step=world.step,
        object_count=world.object_count,
        expectation_checks=expectations,
    )


def _apply_scenario_action(world: World, action: ScenarioAction, *, scenario: Scenario) -> None:
    """Apply a scenario action by routing it through ``World.predict``.

    Every scenario action ultimately becomes a typed :class:`Action` passed
    to :meth:`World.predict`, which advances the world state through the
    scenario's declared provider.
    """

    steps = int(action.parameters.get("steps", 1))
    provider = action.parameters.get("provider") or scenario.provider
    if action.kind == "predict":
        world_action = Action.move_to(
            _require_float(action.parameters, "x"),
            _require_float(action.parameters, "y"),
            _require_float(action.parameters, "z"),
            speed=float(action.parameters.get("speed", 1.0)),
        )
    elif action.kind == "move_to":
        world_action = Action.move_to(
            _require_float(action.parameters, "x"),
            _require_float(action.parameters, "y"),
            _require_float(action.parameters, "z"),
            speed=float(action.parameters.get("speed", 1.0)),
            object_id=action.parameters.get("object_id"),
        )
    elif action.kind == "spawn_object":
        position = _position_from_payload(action.parameters, name="spawn_object")
        world_action = Action.spawn_object(
            name=str(action.parameters["name"]),
            position=position,
            bbox=_optional_bbox_from_payload(action.parameters, "bbox"),
        )
    else:  # pragma: no cover - exhaustive guard
        raise WorldForgeError(f"Unsupported scenario action kind: {action.kind}")
    world.predict(world_action, steps=steps, provider=provider)


def _evaluate_expectation(
    world: World, expected: ScenarioExpectedArtifact
) -> ScenarioExpectationCheck:
    if expected.kind == "object_count":
        observed = world.object_count
        return ScenarioExpectationCheck(
            label=expected.label,
            kind=expected.kind,
            expected=expected.value,
            observed=observed,
            passed=observed == expected.value,
        )
    if expected.kind == "step":
        observed = world.step
        return ScenarioExpectationCheck(
            label=expected.label,
            kind=expected.kind,
            expected=expected.value,
            observed=observed,
            passed=observed == expected.value,
        )
    target = expected.value if isinstance(expected.value, Mapping) else {}
    object_id = target.get("object_id")
    found = world.get_object_by_id(str(object_id)) if object_id else None
    observed_payload: JSONDict = (
        {
            "x": found.position.x,
            "y": found.position.y,
            "z": found.position.z,
        }
        if found is not None
        else {}
    )
    tolerance = float(target.get("tolerance", 0.05))
    expected_pos = target.get("position", {}) if isinstance(target, Mapping) else {}
    passed = (
        found is not None
        and isinstance(expected_pos, Mapping)
        and abs(found.position.x - float(expected_pos.get("x", 0.0))) <= tolerance
        and abs(found.position.y - float(expected_pos.get("y", 0.0))) <= tolerance
        and abs(found.position.z - float(expected_pos.get("z", 0.0))) <= tolerance
    )
    return ScenarioExpectationCheck(
        label=expected.label,
        kind=expected.kind,
        expected=expected.value,
        observed=observed_payload,
        passed=passed,
    )


def _scenario_from_json_text(text: str, *, source: str) -> Scenario:
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise WorldForgeError(f"Scenario file {source} contains invalid JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise WorldForgeError(f"Scenario file {source} must be a JSON object.")
    return _scenario_from_dict(payload, source=source)


def _scenario_from_dict(payload: JSONDict, *, source: str) -> Scenario:
    schema_version = payload.get("schema_version", SCENARIO_SCHEMA_VERSION)
    if schema_version != SCENARIO_SCHEMA_VERSION:
        raise WorldForgeError(
            f"Scenario {source} schema_version {schema_version} is not supported "
            f"(expected {SCENARIO_SCHEMA_VERSION})."
        )
    scenario_id = _require_text(payload.get("id"), name="scenario id", source=source)
    if scenario_id in {".", ".."} or "/" in scenario_id or "\\" in scenario_id:
        raise WorldForgeError(
            f"Scenario {source} id '{scenario_id}' is traversal-shaped and rejected."
        )
    name = _require_text(payload.get("name"), name="scenario name", source=source)
    description = str(payload.get("description") or "")
    provider = _require_text(payload.get("provider"), name="scenario provider", source=source)

    world_payload = payload.get("world")
    if not isinstance(world_payload, Mapping):
        raise WorldForgeError(f"Scenario {source} 'world' must be a JSON object.")
    world_name = _require_text(world_payload.get("name"), name="world name", source=source)
    objects_payload = world_payload.get("objects", [])
    if not isinstance(objects_payload, list):
        raise WorldForgeError(f"Scenario {source} world.objects must be a JSON array.")
    objects = tuple(
        _object_from_payload(item, source=source, index=index)
        for index, item in enumerate(objects_payload)
    )

    actions_payload = payload.get("actions", [])
    if not isinstance(actions_payload, list):
        raise WorldForgeError(f"Scenario {source} 'actions' must be a JSON array.")
    actions = tuple(
        _action_from_payload(item, source=source, index=index)
        for index, item in enumerate(actions_payload)
    )

    expected_payload = payload.get("expected_artifacts", [])
    if not isinstance(expected_payload, list):
        raise WorldForgeError(f"Scenario {source} 'expected_artifacts' must be a JSON array.")
    expected_artifacts = tuple(
        _expectation_from_payload(item, source=source, index=index)
        for index, item in enumerate(expected_payload)
    )

    metadata_payload = payload.get("metadata") or {}
    if not isinstance(metadata_payload, Mapping):
        raise WorldForgeError(f"Scenario {source} 'metadata' must be a JSON object.")

    return Scenario(
        schema_version=SCENARIO_SCHEMA_VERSION,
        id=scenario_id,
        name=name,
        description=description,
        provider=provider,
        world_name=world_name,
        objects=objects,
        actions=actions,
        expected_artifacts=expected_artifacts,
        metadata=dict(metadata_payload),
    )


def _object_from_payload(payload: object, *, source: str, index: int) -> ScenarioObjectSpec:
    if not isinstance(payload, Mapping):
        raise WorldForgeError(f"Scenario {source} world.objects[{index}] must be a JSON object.")
    name = _require_text(payload.get("name"), name=f"objects[{index}].name", source=source)
    position = _position_from_payload(payload, name=f"objects[{index}].position")
    bbox = _bbox_from_payload(payload, name=f"objects[{index}]", source=source)
    object_id = payload.get("id")
    if object_id is not None and (not isinstance(object_id, str) or not object_id.strip()):
        raise WorldForgeError(f"Scenario {source} objects[{index}].id must be a non-empty string.")
    metadata = payload.get("metadata") or {}
    if not isinstance(metadata, Mapping):
        raise WorldForgeError(f"Scenario {source} objects[{index}].metadata must be a JSON object.")
    return ScenarioObjectSpec(
        name=name,
        position=position,
        bbox=bbox,
        id=object_id,
        is_graspable=bool(payload.get("is_graspable", False)),
        metadata=dict(metadata),
    )


def _action_from_payload(payload: object, *, source: str, index: int) -> ScenarioAction:
    if not isinstance(payload, Mapping):
        raise WorldForgeError(f"Scenario {source} actions[{index}] must be a JSON object.")
    kind = payload.get("kind")
    if not isinstance(kind, str) or kind not in SCENARIO_ACTION_KINDS:
        options = ", ".join(SCENARIO_ACTION_KINDS)
        raise WorldForgeError(f"Scenario {source} actions[{index}].kind must be one of: {options}.")
    parameters = payload.get("parameters") or {}
    if not isinstance(parameters, Mapping):
        raise WorldForgeError(
            f"Scenario {source} actions[{index}].parameters must be a JSON object."
        )
    return ScenarioAction(kind=kind, parameters=dict(parameters))


def _expectation_from_payload(
    payload: object, *, source: str, index: int
) -> ScenarioExpectedArtifact:
    if not isinstance(payload, Mapping):
        raise WorldForgeError(
            f"Scenario {source} expected_artifacts[{index}] must be a JSON object."
        )
    label = _require_text(
        payload.get("label"),
        name=f"expected_artifacts[{index}].label",
        source=source,
    )
    kind = payload.get("kind")
    if kind not in {"object_count", "step", "object_position"}:
        raise WorldForgeError(
            f"Scenario {source} expected_artifacts[{index}].kind must be one of: "
            "object_count, step, object_position."
        )
    return ScenarioExpectedArtifact(label=label, kind=kind, value=payload.get("value"))


def _require_text(value: object, *, name: str, source: str = "") -> str:
    if not isinstance(value, str) or not value.strip():
        prefix = f"Scenario {source} " if source else ""
        raise WorldForgeError(f"{prefix}{name} must be a non-empty string.")
    return value.strip()


def _require_float(parameters: Mapping, key: str) -> float:
    value = parameters.get(key)
    if value is None:
        raise WorldForgeError(f"Scenario action parameter '{key}' is required.")
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise WorldForgeError(
            f"Scenario action parameter '{key}' must be a finite number."
        ) from exc


def _position_from_payload(payload: Mapping, *, name: str) -> Position:
    nested = payload.get("position") if "position" in payload else payload
    if not isinstance(nested, Mapping):
        raise WorldForgeError(f"Scenario {name} position must be a JSON object.")
    return Position(
        _require_float(nested, "x"),
        _require_float(nested, "y"),
        _require_float(nested, "z"),
    )


def _bbox_from_payload(payload: Mapping, *, name: str, source: str) -> BBox:
    bbox = payload.get("bbox")
    if not isinstance(bbox, Mapping):
        raise WorldForgeError(f"Scenario {source} {name}.bbox must be a JSON object.")
    bbox_min = bbox.get("min")
    bbox_max = bbox.get("max")
    if not isinstance(bbox_min, Mapping) or not isinstance(bbox_max, Mapping):
        raise WorldForgeError(
            f"Scenario {source} {name}.bbox.min and bbox.max must be JSON objects."
        )
    return BBox(
        Position(
            _require_float(bbox_min, "x"),
            _require_float(bbox_min, "y"),
            _require_float(bbox_min, "z"),
        ),
        Position(
            _require_float(bbox_max, "x"),
            _require_float(bbox_max, "y"),
            _require_float(bbox_max, "z"),
        ),
    )


def _optional_bbox_from_payload(payload: Mapping, key: str) -> BBox | None:
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
            _require_float(bbox_min, "x"),
            _require_float(bbox_min, "y"),
            _require_float(bbox_min, "z"),
        ),
        Position(
            _require_float(bbox_max, "x"),
            _require_float(bbox_max, "y"),
            _require_float(bbox_max, "z"),
        ),
    )


__all__ = [
    "SCENARIO_ACTION_KINDS",
    "SCENARIO_SCHEMA_VERSION",
    "Scenario",
    "ScenarioAction",
    "ScenarioExpectationCheck",
    "ScenarioExpectedArtifact",
    "ScenarioObjectSpec",
    "ScenarioResult",
    "load_scenario",
    "parse_scenario",
    "run_scenario",
]

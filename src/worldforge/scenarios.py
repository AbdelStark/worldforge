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
from pathlib import Path
from typing import TYPE_CHECKING

from worldforge.models import (
    Action,
    BBox,
    JSONDict,
    Position,
    WorldForgeError,
    require_bool,
    require_json_dict,
)
from worldforge.scenario_expectations import evaluate_expectation
from worldforge.scenario_matrix import scenario_matrix_from_payload as _matrix_from_payload
from worldforge.scenario_models import (
    SCENARIO_ACTION_KINDS,
    SCENARIO_EXTENDS_MIN_SCHEMA_VERSION,
    SCENARIO_MATRIX_MAX_CASES,
    SCENARIO_MAX_EXTENDS_DEPTH,
    SCENARIO_SCHEMA_VERSION,
    SCENARIO_SUPPORTED_SCHEMA_VERSIONS,
    Scenario,
    ScenarioAction,
    ScenarioExpectationCheck,
    ScenarioExpectedArtifact,
    ScenarioMatrix,
    ScenarioMatrixCase,
    ScenarioMatrixCaseResult,
    ScenarioMatrixResult,
    ScenarioObjectSpec,
    ScenarioResult,
)
from worldforge.scenario_models import (
    scenario_position_from_payload as _position_from_payload,
)
from worldforge.scenario_models import (
    scenario_required_float as _require_float,
)

if TYPE_CHECKING:
    from worldforge.framework import World, WorldForge


def load_scenario(path: Path | str) -> Scenario:
    """Load a scenario from a JSON file with strict validation.

    Supports the ``extends`` field for single-parent scenario inheritance; the
    parent path is resolved relative to the child file. See
    :doc:`scenarios.md <docs/src/scenarios.md>` for merge semantics.
    """

    target = Path(path).expanduser()
    payload = _read_scenario_json(target)
    resolved = _resolve_extends_chain(payload, base_path=target.resolve(), source=str(target))
    return _scenario_from_dict(resolved, source=str(target))


def load_scenario_matrix(path: Path | str) -> ScenarioMatrix:
    """Load and expand a scenario file that may declare a parameter matrix.

    Supports the ``extends`` field; inheritance resolution happens before
    matrix expansion, so a child scenario can override matrix declarations
    inherited from a parent file.
    """

    target = Path(path).expanduser()
    payload = _read_scenario_json(target)
    resolved = _resolve_extends_chain(payload, base_path=target.resolve(), source=str(target))
    return parse_scenario_matrix(resolved, source=str(target))


def parse_scenario(payload: JSONDict | str) -> Scenario:
    """Parse a scenario from a dict or JSON string.

    Inheritance via ``extends`` is only supported through
    :func:`load_scenario` because the parent path is resolved relative to the
    child file on disk. Passing a payload with ``extends`` here raises
    :class:`WorldForgeError`.
    """

    if isinstance(payload, str):
        return _scenario_from_json_text(payload, source="<string>")
    if not isinstance(payload, Mapping):
        raise WorldForgeError("Scenario payload must be a JSON object.")
    return _scenario_from_dict(
        _require_scenario_json_dict(dict(payload), name="Scenario <dict>"),
        source="<dict>",
    )


def parse_scenario_matrix(payload: JSONDict | str, *, source: str = "<dict>") -> ScenarioMatrix:
    """Parse and expand a scenario matrix from a dict or JSON string."""

    if isinstance(payload, str):
        try:
            decoded = json.loads(payload)
        except json.JSONDecodeError as exc:
            raise WorldForgeError(f"Scenario file <string> contains invalid JSON: {exc}") from exc
        return parse_scenario_matrix(
            _require_scenario_json_dict(decoded, name="Scenario file <string>"),
            source="<string>",
        )
    if not isinstance(payload, Mapping):
        raise WorldForgeError("Scenario payload must be a JSON object.")
    raw_payload = _require_scenario_json_dict(dict(payload), name=f"Scenario {source}")
    matrix_payload = raw_payload.get("matrix")
    if matrix_payload is None:
        scenario = _scenario_from_dict(raw_payload, source=source)
        return ScenarioMatrix(
            schema_version=SCENARIO_SCHEMA_VERSION,
            scenario_id=scenario.id,
            cases=(ScenarioMatrixCase(case_id=scenario.id, parameters={}, scenario=scenario),),
            is_matrix=False,
        )
    if not isinstance(matrix_payload, Mapping):
        raise WorldForgeError(f"Scenario {source} matrix must be a JSON object.")
    return _matrix_from_payload(
        raw_payload,
        matrix_payload=dict(matrix_payload),
        source=source,
        scenario_factory=_scenario_from_dict,
    )


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


def run_scenario_matrix(forge: WorldForge, matrix: ScenarioMatrix) -> ScenarioMatrixResult:
    """Run every concrete case in an expanded scenario matrix."""

    if not isinstance(matrix, ScenarioMatrix):
        raise WorldForgeError("run_scenario_matrix matrix must be a ScenarioMatrix instance.")
    results = tuple(
        ScenarioMatrixCaseResult(
            case_id=case.case_id,
            parameters=case.parameters,
            result=run_scenario(forge, case.scenario),
        )
        for case in matrix.cases
    )
    return ScenarioMatrixResult(
        schema_version=SCENARIO_SCHEMA_VERSION,
        scenario_id=matrix.scenario_id,
        case_results=results,
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
    else:
        world_action = action.to_world_action()
        if world_action is None:
            raise WorldForgeError(f"Unsupported scenario action kind: {action.kind}")
    world.predict(world_action, steps=steps, provider=provider)


def _evaluate_expectation(
    world: World, expected: ScenarioExpectedArtifact
) -> ScenarioExpectationCheck:
    return evaluate_expectation(
        world,
        expected,
        check_factory=ScenarioExpectationCheck,
    )


def _scenario_from_json_text(text: str, *, source: str) -> Scenario:
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise WorldForgeError(f"Scenario file {source} contains invalid JSON: {exc}") from exc
    return _scenario_from_dict(
        _require_scenario_json_dict(payload, name=f"Scenario file {source}"),
        source=source,
    )


def _check_schema_version(value: object, *, source: str) -> int:
    """Strictly validate a scenario ``schema_version`` value.

    Rejects ``bool`` and ``float`` (including ``1.0``) so the check cannot
    be silently bypassed by Python's int-equal comparison rules.
    """

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


def _read_scenario_json(target: Path) -> JSONDict:
    try:
        text = target.read_text(encoding="utf-8")
    except OSError as exc:
        raise WorldForgeError(f"Failed to read scenario file {target}: {exc}") from exc
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise WorldForgeError(f"Scenario file {target} contains invalid JSON: {exc}") from exc
    return _require_scenario_json_dict(payload, name=f"Scenario file {target}")


def _resolve_extends_chain(
    payload: JSONDict,
    *,
    base_path: Path,
    source: str,
    seen: tuple[Path, ...] = (),
) -> JSONDict:
    """Resolve a scenario's ``extends`` chain into a single merged payload.

    Returns a new dict with the ``extends`` field removed. Child top-level
    keys replace parent values (no deep merge). Raises
    :class:`WorldForgeError` on missing parents, absolute paths, cycles, or
    depth overruns.
    """

    if "extends" not in payload:
        return dict(payload)

    extends_ref = _scenario_extends_ref(payload, source=source)
    _check_extends_schema_version(payload, source=source)
    parent_path = _scenario_parent_path(
        extends_ref=extends_ref,
        base_path=base_path,
        source=source,
        seen=seen,
    )
    parent_payload = _read_parent_scenario_payload(
        parent_path=parent_path,
        extends_ref=extends_ref,
        source=source,
    )
    resolved_parent = _resolve_extends_chain(
        parent_payload,
        base_path=parent_path,
        source=str(parent_path),
        seen=(*seen, base_path),
    )
    return _merge_extended_payload(parent=resolved_parent, child=payload)


def _scenario_extends_ref(payload: JSONDict, *, source: str) -> str:
    extends_ref = payload["extends"]
    if not isinstance(extends_ref, str) or not extends_ref.strip():
        raise WorldForgeError(f"Scenario {source} 'extends' must be a non-empty string path.")
    return extends_ref


def _check_extends_schema_version(payload: JSONDict, *, source: str) -> None:
    raw_schema_version = payload.get("schema_version", SCENARIO_SCHEMA_VERSION)
    if not (isinstance(raw_schema_version, int) and not isinstance(raw_schema_version, bool)):
        raise WorldForgeError(
            f"Scenario {source} schema_version must be an integer; got "
            f"{type(raw_schema_version).__name__}."
        )
    if raw_schema_version < SCENARIO_EXTENDS_MIN_SCHEMA_VERSION:
        raise WorldForgeError(
            f"Scenario {source} uses 'extends' but schema_version {raw_schema_version} "
            f"predates inheritance support (requires {SCENARIO_EXTENDS_MIN_SCHEMA_VERSION})."
        )


def _scenario_parent_path(
    *,
    extends_ref: str,
    base_path: Path,
    source: str,
    seen: tuple[Path, ...],
) -> Path:
    ref = _scenario_parent_ref(extends_ref, source=source)
    parent_path = (base_path.parent / ref).resolve()
    _reject_extends_cycle(parent_path=parent_path, base_path=base_path, seen=seen)
    if len(seen) + 1 > SCENARIO_MAX_EXTENDS_DEPTH:
        raise WorldForgeError(
            f"Scenario {source} 'extends' chain exceeds maximum depth {SCENARIO_MAX_EXTENDS_DEPTH}."
        )
    return parent_path


def _scenario_parent_ref(extends_ref: str, *, source: str) -> Path:
    ref = Path(extends_ref)
    if ref.is_absolute():
        raise WorldForgeError(
            f"Scenario {source} 'extends' path must be relative; got '{extends_ref}'."
        )
    if any(part == ".." for part in ref.parts):
        raise WorldForgeError(
            f"Scenario {source} 'extends' path may not contain '..' segments; got '{extends_ref}'."
        )
    return ref


def _reject_extends_cycle(
    *,
    parent_path: Path,
    base_path: Path,
    seen: tuple[Path, ...],
) -> None:
    if parent_path == base_path:
        chain = " -> ".join(str(p) for p in (base_path, parent_path))
        raise WorldForgeError(f"Scenario inheritance cycle detected: {chain}.")
    if parent_path in seen:
        chain = " -> ".join(str(p) for p in (*seen, base_path, parent_path))
        raise WorldForgeError(f"Scenario inheritance cycle detected: {chain}.")


def _read_parent_scenario_payload(
    *,
    parent_path: Path,
    extends_ref: str,
    source: str,
) -> JSONDict:
    try:
        parent_text = parent_path.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise WorldForgeError(
            f"Scenario {source} extends parent '{extends_ref}' which does not exist."
        ) from exc
    except OSError as exc:
        raise WorldForgeError(
            f"Scenario {source} extends parent '{extends_ref}' which could not be read: {exc}."
        ) from exc

    try:
        parent_payload = json.loads(parent_text)
    except json.JSONDecodeError as exc:
        raise WorldForgeError(
            f"Scenario {source} extends parent '{extends_ref}' which contains invalid JSON: {exc}"
        ) from exc
    return _require_scenario_json_dict(
        parent_payload,
        name=f"Scenario {source} extends parent '{extends_ref}'",
    )


def _merge_extended_payload(*, parent: JSONDict, child: JSONDict) -> JSONDict:
    merged = dict(parent)
    for key, value in child.items():
        if key == "extends":
            continue
        merged[key] = value
    return merged


def _scenario_from_dict(payload: JSONDict, *, source: str) -> Scenario:
    _reject_unresolved_extends(payload, source=source)
    _check_schema_version(payload.get("schema_version", SCENARIO_SCHEMA_VERSION), source=source)
    scenario_id = _scenario_id(payload, source=source)
    world_name, objects = _scenario_world(payload, source=source)
    return Scenario(
        schema_version=SCENARIO_SCHEMA_VERSION,
        id=scenario_id,
        name=_require_text(payload.get("name"), name="scenario name", source=source),
        description=str(payload.get("description") or ""),
        provider=_require_text(payload.get("provider"), name="scenario provider", source=source),
        world_name=world_name,
        objects=objects,
        actions=_scenario_actions(payload, source=source),
        expected_artifacts=_scenario_expected_artifacts(payload, source=source),
        metadata=_scenario_metadata(payload, source=source),
    )


def _reject_unresolved_extends(payload: JSONDict, *, source: str) -> None:
    if "extends" in payload:
        raise WorldForgeError(
            f"Scenario {source} contains unresolved 'extends'; load it via "
            "load_scenario(<path>) so the parent path can be resolved from disk."
        )


def _scenario_id(payload: JSONDict, *, source: str) -> str:
    scenario_id = _require_text(payload.get("id"), name="scenario id", source=source)
    if scenario_id in {".", ".."} or "/" in scenario_id or "\\" in scenario_id:
        raise WorldForgeError(
            f"Scenario {source} id '{scenario_id}' is traversal-shaped and rejected."
        )
    return scenario_id


def _scenario_world(
    payload: JSONDict,
    *,
    source: str,
) -> tuple[str, tuple[ScenarioObjectSpec, ...]]:
    world_payload = payload.get("world")
    if not isinstance(world_payload, Mapping):
        raise WorldForgeError(f"Scenario {source} 'world' must be a JSON object.")
    world_name = _require_text(world_payload.get("name"), name="world name", source=source)
    return world_name, _scenario_objects(world_payload, source=source)


def _scenario_objects(
    world_payload: Mapping,
    *,
    source: str,
) -> tuple[ScenarioObjectSpec, ...]:
    objects_payload = world_payload.get("objects", [])
    if not isinstance(objects_payload, list):
        raise WorldForgeError(f"Scenario {source} world.objects must be a JSON array.")
    return tuple(
        _object_from_payload(item, source=source, index=index)
        for index, item in enumerate(objects_payload)
    )


def _scenario_actions(payload: JSONDict, *, source: str) -> tuple[ScenarioAction, ...]:
    actions_payload = payload.get("actions", [])
    if not isinstance(actions_payload, list):
        raise WorldForgeError(f"Scenario {source} 'actions' must be a JSON array.")
    return tuple(
        _action_from_payload(item, source=source, index=index)
        for index, item in enumerate(actions_payload)
    )


def _scenario_expected_artifacts(
    payload: JSONDict,
    *,
    source: str,
) -> tuple[ScenarioExpectedArtifact, ...]:
    expected_payload = payload.get("expected_artifacts", [])
    if not isinstance(expected_payload, list):
        raise WorldForgeError(f"Scenario {source} 'expected_artifacts' must be a JSON array.")
    return tuple(
        _expectation_from_payload(item, source=source, index=index)
        for index, item in enumerate(expected_payload)
    )


def _scenario_metadata(payload: JSONDict, *, source: str) -> JSONDict:
    metadata_payload = payload.get("metadata") or {}
    if not isinstance(metadata_payload, Mapping):
        raise WorldForgeError(f"Scenario {source} 'metadata' must be a JSON object.")
    return require_json_dict(
        dict(metadata_payload),
        name=f"Scenario {source} metadata",
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
    is_graspable = require_bool(
        payload.get("is_graspable", False),
        name=f"Scenario {source} objects[{index}].is_graspable",
    )
    return ScenarioObjectSpec(
        name=name,
        position=position,
        bbox=bbox,
        id=object_id,
        is_graspable=is_graspable,
        metadata=require_json_dict(
            dict(metadata),
            name=f"Scenario {source} objects[{index}].metadata",
        ),
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
    return ScenarioAction(
        kind=kind,
        parameters=require_json_dict(
            dict(parameters),
            name=f"Scenario {source} actions[{index}].parameters",
        ),
    )


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
    return ScenarioExpectedArtifact(
        label=label,
        kind=kind,
        value=require_json_dict(
            {"value": payload.get("value")},
            name=f"Scenario {source} expected_artifacts[{index}].value",
        )["value"],
    )


def _require_text(value: object, *, name: str, source: str = "") -> str:
    if not isinstance(value, str) or not value.strip():
        prefix = f"Scenario {source} " if source else ""
        raise WorldForgeError(f"{prefix}{name} must be a non-empty string.")
    return value.strip()


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


def _require_scenario_json_dict(value: object, *, name: str) -> JSONDict:
    try:
        return require_json_dict(value, name=name)
    except WorldForgeError as exc:
        if not isinstance(value, dict):
            raise WorldForgeError(f"{name} must be a JSON object.") from exc
        raise WorldForgeError(
            f"{exc} Scenario payloads must be JSON-native and contain only finite numbers."
        ) from exc


__all__ = [
    "SCENARIO_ACTION_KINDS",
    "SCENARIO_EXTENDS_MIN_SCHEMA_VERSION",
    "SCENARIO_MATRIX_MAX_CASES",
    "SCENARIO_MAX_EXTENDS_DEPTH",
    "SCENARIO_SCHEMA_VERSION",
    "SCENARIO_SUPPORTED_SCHEMA_VERSIONS",
    "Scenario",
    "ScenarioAction",
    "ScenarioExpectationCheck",
    "ScenarioExpectedArtifact",
    "ScenarioMatrix",
    "ScenarioMatrixCase",
    "ScenarioMatrixCaseResult",
    "ScenarioMatrixResult",
    "ScenarioObjectSpec",
    "ScenarioResult",
    "load_scenario",
    "load_scenario_matrix",
    "parse_scenario",
    "parse_scenario_matrix",
    "run_scenario",
    "run_scenario_matrix",
]

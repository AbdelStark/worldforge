"""Tests for scenario inheritance via the `extends` field (WF-FEAT3-006)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from worldforge import WorldForge, WorldForgeError
from worldforge.scenarios import (
    SCENARIO_EXTENDS_MIN_SCHEMA_VERSION,
    SCENARIO_MAX_EXTENDS_DEPTH,
    SCENARIO_SCHEMA_VERSION,
    SCENARIO_SUPPORTED_SCHEMA_VERSIONS,
    load_scenario,
    load_scenario_matrix,
    parse_scenario,
    parse_scenario_matrix,
    run_scenario,
    run_scenario_matrix,
)


def _base_payload(**overrides: object) -> dict:
    payload: dict = {
        "schema_version": SCENARIO_SCHEMA_VERSION,
        "id": "inherit-base",
        "name": "Inheritance base scenario",
        "description": "Base scenario shared by inheritance tests.",
        "provider": "mock",
        "world": {
            "name": "inherit-base-world",
            "objects": [
                {
                    "id": "cube",
                    "name": "cube",
                    "position": {"x": 0.0, "y": 0.5, "z": 0.0},
                    "bbox": {
                        "min": {"x": -0.05, "y": 0.45, "z": -0.05},
                        "max": {"x": 0.05, "y": 0.55, "z": 0.05},
                    },
                }
            ],
        },
        "actions": [{"kind": "predict", "parameters": {"x": 0.25, "y": 0.5, "z": 0.0, "steps": 1}}],
        "expected_artifacts": [
            {"label": "object_count", "kind": "object_count", "value": 1},
            {"label": "step_count", "kind": "step", "value": 1},
        ],
        "metadata": {},
    }
    payload.update(overrides)
    return payload


def _write_json(path: Path, payload: dict) -> Path:
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_supported_versions_include_v1_and_v2() -> None:
    assert 1 in SCENARIO_SUPPORTED_SCHEMA_VERSIONS
    assert SCENARIO_SCHEMA_VERSION in SCENARIO_SUPPORTED_SCHEMA_VERSIONS
    assert SCENARIO_EXTENDS_MIN_SCHEMA_VERSION == 2


def test_load_v1_scenario_still_validates(tmp_path: Path) -> None:
    payload = _base_payload(schema_version=1, id="legacy-v1")
    path = _write_json(tmp_path / "legacy.json", payload)
    scenario = load_scenario(path)
    assert scenario.id == "legacy-v1"


def test_child_inherits_fields_from_parent(tmp_path: Path) -> None:
    _write_json(tmp_path / "parent.json", _base_payload(id="parent-1", provider="mock"))
    child_payload = {
        "schema_version": 2,
        "extends": "./parent.json",
        "id": "child-1",
        "name": "Child only overrides id and name",
    }
    child_path = _write_json(tmp_path / "child.json", child_payload)
    scenario = load_scenario(child_path)
    assert scenario.id == "child-1"
    assert scenario.name == "Child only overrides id and name"
    assert scenario.provider == "mock"
    assert scenario.world_name == "inherit-base-world"
    assert len(scenario.objects) == 1
    assert scenario.objects[0].id == "cube"
    assert len(scenario.actions) == 1


def test_child_overrides_top_level_fields(tmp_path: Path) -> None:
    _write_json(tmp_path / "parent.json", _base_payload(id="parent-2"))
    child_payload = {
        "schema_version": 2,
        "extends": "./parent.json",
        "id": "child-2",
        "name": "Child with overridden expectations",
        "expected_artifacts": [
            {"label": "step_count", "kind": "step", "value": 7},
        ],
    }
    child_path = _write_json(tmp_path / "child.json", child_payload)
    scenario = load_scenario(child_path)
    assert len(scenario.expected_artifacts) == 1
    assert scenario.expected_artifacts[0].value == 7


def test_child_replaces_world_wholesale(tmp_path: Path) -> None:
    _write_json(tmp_path / "parent.json", _base_payload(id="parent-3"))
    child_payload = {
        "schema_version": 2,
        "extends": "./parent.json",
        "id": "child-3",
        "name": "Child fully replaces world block",
        "world": {
            "name": "replaced-world",
            "objects": [],
        },
    }
    child_path = _write_json(tmp_path / "child.json", child_payload)
    scenario = load_scenario(child_path)
    assert scenario.world_name == "replaced-world"
    assert scenario.objects == ()


def test_extends_resolves_multi_level_chain(tmp_path: Path) -> None:
    _write_json(tmp_path / "grand.json", _base_payload(id="grand", provider="mock"))
    _write_json(
        tmp_path / "middle.json",
        {
            "schema_version": 2,
            "extends": "./grand.json",
            "id": "middle",
            "name": "Middle scenario",
            "expected_artifacts": [
                {"label": "step_count", "kind": "step", "value": 2},
            ],
        },
    )
    child_path = _write_json(
        tmp_path / "child.json",
        {
            "schema_version": 2,
            "extends": "./middle.json",
            "id": "child-chain",
            "name": "Chained child",
        },
    )
    scenario = load_scenario(child_path)
    assert scenario.id == "child-chain"
    assert scenario.provider == "mock"
    assert scenario.expected_artifacts[0].value == 2


def test_extends_absolute_path_rejected(tmp_path: Path) -> None:
    absolute_ref = "/etc/parent.json"
    child_path = _write_json(
        tmp_path / "child.json",
        {
            "schema_version": 2,
            "extends": absolute_ref,
            "id": "child-abs",
            "name": "Child with absolute path",
        },
    )
    with pytest.raises(WorldForgeError, match="must be relative"):
        load_scenario(child_path)


def test_extends_missing_parent_raises(tmp_path: Path) -> None:
    child_path = _write_json(
        tmp_path / "child.json",
        {
            "schema_version": 2,
            "extends": "./does-not-exist.json",
            "id": "child-missing",
            "name": "Child with missing parent",
        },
    )
    with pytest.raises(WorldForgeError, match="does not exist"):
        load_scenario(child_path)


def test_extends_non_string_rejected(tmp_path: Path) -> None:
    child_path = _write_json(
        tmp_path / "child.json",
        {
            "schema_version": 2,
            "extends": 42,
            "id": "child-non-string",
            "name": "Child with non-string extends",
        },
    )
    with pytest.raises(WorldForgeError, match="non-empty string path"):
        load_scenario(child_path)


def test_extends_empty_string_rejected(tmp_path: Path) -> None:
    child_path = _write_json(
        tmp_path / "child.json",
        {
            "schema_version": 2,
            "extends": "   ",
            "id": "child-empty",
            "name": "Child with empty extends",
        },
    )
    with pytest.raises(WorldForgeError, match="non-empty string path"):
        load_scenario(child_path)


def test_extends_requires_v2_schema(tmp_path: Path) -> None:
    _write_json(tmp_path / "parent.json", _base_payload(id="parent-v1"))
    child_path = _write_json(
        tmp_path / "child.json",
        {
            "schema_version": 1,
            "extends": "./parent.json",
            "id": "child-v1",
            "name": "Child with stale schema",
        },
    )
    with pytest.raises(WorldForgeError, match="predates inheritance support"):
        load_scenario(child_path)


def test_extends_self_cycle_rejected(tmp_path: Path) -> None:
    target = tmp_path / "self.json"
    _write_json(
        target,
        {
            "schema_version": 2,
            "extends": "./self.json",
            "id": "self-cycle",
            "name": "Self-referencing scenario",
        },
    )
    with pytest.raises(WorldForgeError, match="cycle detected"):
        load_scenario(target)


def test_extends_two_node_cycle_rejected(tmp_path: Path) -> None:
    _write_json(
        tmp_path / "a.json",
        {
            "schema_version": 2,
            "extends": "./b.json",
            "id": "node-a",
            "name": "A",
        },
    )
    _write_json(
        tmp_path / "b.json",
        {
            "schema_version": 2,
            "extends": "./a.json",
            "id": "node-b",
            "name": "B",
        },
    )
    with pytest.raises(WorldForgeError, match="cycle detected"):
        load_scenario(tmp_path / "a.json")


def test_extends_depth_limit_enforced(tmp_path: Path) -> None:
    chain_length = SCENARIO_MAX_EXTENDS_DEPTH + 2
    last_index = chain_length - 1
    for index in range(chain_length):
        body: dict = {
            "schema_version": 2,
            "id": f"link-{index}",
            "name": f"Link {index}",
        }
        if index == last_index:
            body.update(_base_payload(id=f"link-{index}", name=f"Link {index}"))
            body["schema_version"] = 2
        else:
            body["extends"] = f"./link-{index + 1}.json"
        _write_json(tmp_path / f"link-{index}.json", body)
    with pytest.raises(WorldForgeError, match="exceeds maximum depth"):
        load_scenario(tmp_path / "link-0.json")


def test_parse_scenario_rejects_extends_in_dict() -> None:
    payload = _base_payload(extends="./parent.json")
    with pytest.raises(WorldForgeError, match="unresolved 'extends'"):
        parse_scenario(payload)


def test_parse_scenario_matrix_rejects_extends_in_dict() -> None:
    payload = _base_payload(extends="./parent.json")
    with pytest.raises(WorldForgeError, match="unresolved 'extends'"):
        parse_scenario_matrix(payload)


def test_child_can_introduce_matrix(tmp_path: Path) -> None:
    _write_json(tmp_path / "parent.json", _base_payload(id="matrix-parent"))
    child_path = _write_json(
        tmp_path / "child.json",
        {
            "schema_version": 2,
            "extends": "./parent.json",
            "id": "matrix-child",
            "name": "Child with matrix",
            "actions": [
                {
                    "kind": "predict",
                    "parameters": {"x": "${target_x}", "y": 0.5, "z": 0.0, "steps": 1},
                }
            ],
            "expected_artifacts": [
                {"label": "object_count", "kind": "object_count", "value": 1},
                {"label": "step_count", "kind": "step", "value": 1},
            ],
            "matrix": {
                "max_cases": 4,
                "parameters": {
                    "target_x": [0.25, 0.5],
                },
            },
        },
    )
    matrix = load_scenario_matrix(child_path)
    assert matrix.is_matrix is True
    assert len(matrix.cases) == 2
    case_ids = [case.case_id for case in matrix.cases]
    assert case_ids == ["matrix-child-case-1", "matrix-child-case-2"]


def test_child_inherits_matrix_when_not_overridden(tmp_path: Path) -> None:
    parent_payload = _base_payload(id="matrix-parent")
    parent_payload["actions"] = [
        {
            "kind": "predict",
            "parameters": {"x": "${target_x}", "y": 0.5, "z": 0.0, "steps": 1},
        }
    ]
    parent_payload["matrix"] = {
        "max_cases": 4,
        "parameters": {"target_x": [0.1, 0.2, 0.3]},
    }
    _write_json(tmp_path / "parent.json", parent_payload)
    child_path = _write_json(
        tmp_path / "child.json",
        {
            "schema_version": 2,
            "extends": "./parent.json",
            "id": "matrix-child",
            "name": "Child inheriting matrix",
        },
    )
    matrix = load_scenario_matrix(child_path)
    assert matrix.is_matrix is True
    assert len(matrix.cases) == 3


def test_load_scenario_runs_inherited_scenario(tmp_path: Path) -> None:
    _write_json(tmp_path / "parent.json", _base_payload(id="run-parent"))
    child_path = _write_json(
        tmp_path / "child.json",
        {
            "schema_version": 2,
            "extends": "./parent.json",
            "id": "run-child",
            "name": "Runnable child",
            "actions": [
                {"kind": "predict", "parameters": {"x": 0.4, "y": 0.5, "z": 0.0, "steps": 3}}
            ],
            "expected_artifacts": [
                {"label": "object_count", "kind": "object_count", "value": 1},
                {"label": "step_count", "kind": "step", "value": 3},
            ],
        },
    )
    scenario = load_scenario(child_path)
    forge = WorldForge(state_dir=tmp_path / ".worlds")
    result = run_scenario(forge, scenario)
    assert result.all_expectations_passed()
    assert result.final_step == 3


def test_inherited_matrix_runs_end_to_end(tmp_path: Path) -> None:
    parent_payload = _base_payload(id="run-matrix-parent")
    _write_json(tmp_path / "parent.json", parent_payload)
    child_path = _write_json(
        tmp_path / "child.json",
        {
            "schema_version": 2,
            "extends": "./parent.json",
            "id": "run-matrix-child",
            "name": "Inherited matrix run",
            "actions": [
                {
                    "kind": "predict",
                    "parameters": {"x": "${target_x}", "y": 0.5, "z": 0.0, "steps": 1},
                }
            ],
            "expected_artifacts": [
                {"label": "object_count", "kind": "object_count", "value": 1},
                {"label": "step_count", "kind": "step", "value": 1},
            ],
            "matrix": {
                "max_cases": 4,
                "parameters": {"target_x": [0.25, 0.5]},
            },
        },
    )
    matrix = load_scenario_matrix(child_path)
    forge = WorldForge(state_dir=tmp_path / ".worlds")
    matrix_result = run_scenario_matrix(forge, matrix)
    assert matrix_result.all_cases_passed()
    assert matrix_result.case_count == 2


def test_extends_rejects_parent_with_invalid_json(tmp_path: Path) -> None:
    (tmp_path / "parent.json").write_text("{not valid json", encoding="utf-8")
    child_path = _write_json(
        tmp_path / "child.json",
        {
            "schema_version": 2,
            "extends": "./parent.json",
            "id": "child-bad-parent",
            "name": "Child whose parent is malformed",
        },
    )
    with pytest.raises(WorldForgeError, match="invalid JSON"):
        load_scenario(child_path)


def test_extends_rejects_parent_that_is_not_a_json_object(tmp_path: Path) -> None:
    (tmp_path / "parent.json").write_text("[1, 2, 3]", encoding="utf-8")
    child_path = _write_json(
        tmp_path / "child.json",
        {
            "schema_version": 2,
            "extends": "./parent.json",
            "id": "child-array-parent",
            "name": "Child whose parent is an array",
        },
    )
    with pytest.raises(WorldForgeError, match="must be a JSON object"):
        load_scenario(child_path)


def test_extends_handles_permission_error(monkeypatch, tmp_path: Path) -> None:
    _write_json(tmp_path / "parent.json", _base_payload(id="parent-perm"))
    child_path = _write_json(
        tmp_path / "child.json",
        {
            "schema_version": 2,
            "extends": "./parent.json",
            "id": "child-perm",
            "name": "Child triggering OSError",
        },
    )
    real_read_text = Path.read_text

    def fake_read_text(self, *args, **kwargs):
        if self.name == "parent.json":
            raise PermissionError("denied")
        return real_read_text(self, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", fake_read_text)
    with pytest.raises(WorldForgeError, match="could not be read"):
        load_scenario(child_path)


def test_parse_scenario_matrix_rejects_extends_with_matrix() -> None:
    payload = _base_payload(extends="./parent.json")
    payload["matrix"] = {"max_cases": 4, "parameters": {"target_x": [0.1]}}
    with pytest.raises(WorldForgeError, match="unresolved 'extends'"):
        parse_scenario_matrix(payload)


def test_extends_traversal_rejected(tmp_path: Path) -> None:
    nested = tmp_path / "nested"
    nested.mkdir()
    _write_json(tmp_path / "parent.json", _base_payload(id="traversal-parent"))
    child_path = _write_json(
        nested / "child.json",
        {
            "schema_version": 2,
            "extends": "../parent.json",
            "id": "child-traversal",
            "name": "Child with traversal",
        },
    )
    with pytest.raises(WorldForgeError, match=r"may not contain '\.\.'"):
        load_scenario(child_path)


def test_extends_traversal_rejected_in_subpath(tmp_path: Path) -> None:
    nested = tmp_path / "nested"
    nested.mkdir()
    sibling = tmp_path / "sibling"
    sibling.mkdir()
    _write_json(sibling / "target.json", _base_payload(id="sibling-target"))
    child_path = _write_json(
        nested / "child.json",
        {
            "schema_version": 2,
            "extends": "../sibling/target.json",
            "id": "child-sibling-traversal",
            "name": "Child with sibling traversal",
        },
    )
    with pytest.raises(WorldForgeError, match=r"may not contain '\.\.'"):
        load_scenario(child_path)


def test_extends_null_rejected(tmp_path: Path) -> None:
    child_path = _write_json(
        tmp_path / "child.json",
        {
            "schema_version": 2,
            "extends": None,
            "id": "child-null",
            "name": "Child with explicit null extends",
        },
    )
    with pytest.raises(WorldForgeError, match="non-empty string path"):
        load_scenario(child_path)


def test_schema_version_rejects_float(tmp_path: Path) -> None:
    payload = _base_payload(id="float-version")
    payload["schema_version"] = 2.0
    path = _write_json(tmp_path / "scenario.json", payload)
    with pytest.raises(WorldForgeError, match="must be an integer"):
        load_scenario(path)


def test_schema_version_rejects_bool(tmp_path: Path) -> None:
    payload = _base_payload(id="bool-version")
    payload["schema_version"] = True
    path = _write_json(tmp_path / "scenario.json", payload)
    with pytest.raises(WorldForgeError, match="must be an integer"):
        load_scenario(path)


def test_extends_with_float_schema_version_rejected(tmp_path: Path) -> None:
    _write_json(tmp_path / "parent.json", _base_payload(id="float-parent"))
    child_path = _write_json(
        tmp_path / "child.json",
        {
            "schema_version": 2.0,
            "extends": "./parent.json",
            "id": "child-float-version",
            "name": "Child with float schema_version",
        },
    )
    with pytest.raises(WorldForgeError, match="must be an integer"):
        load_scenario(child_path)


def test_inheritance_example_fixtures_round_trip() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    base = load_scenario(repo_root / "examples" / "scenarios" / "inheritance" / "base.json")
    child_a = load_scenario(repo_root / "examples" / "scenarios" / "inheritance" / "child-a.json")
    child_b = load_scenario(repo_root / "examples" / "scenarios" / "inheritance" / "child-b.json")
    assert base.id == "lab-setup-base"
    assert child_a.id == "lab-setup-child-a"
    assert child_b.id == "lab-setup-child-b"
    assert child_a.provider == "mock"
    assert child_b.objects[0].name == "cube"
    assert len(child_b.actions) == 2

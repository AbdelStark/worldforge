"""Tests for the JSON-native scenario definition format (WF-FEAT-002)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from worldforge import WorldForge, WorldForgeError
from worldforge.cli import main as worldforge_main
from worldforge.scenarios import (
    SCENARIO_ACTION_KINDS,
    SCENARIO_SCHEMA_VERSION,
    Scenario,
    ScenarioAction,
    ScenarioExpectedArtifact,
    load_scenario,
    load_scenario_matrix,
    parse_scenario,
    parse_scenario_matrix,
    run_scenario,
    run_scenario_matrix,
)
from worldforge.testing import stable_json_dumps, stable_snapshot

_VALID_PAYLOAD = {
    "schema_version": SCENARIO_SCHEMA_VERSION,
    "id": "first-scenario",
    "name": "First scenario",
    "description": "Spawn a cube and step the world.",
    "provider": "mock",
    "world": {
        "name": "scenario-world",
        "objects": [
            {
                "name": "cube",
                "position": {"x": 0.0, "y": 0.5, "z": 0.0},
                "bbox": {
                    "min": {"x": -0.05, "y": 0.45, "z": -0.05},
                    "max": {"x": 0.05, "y": 0.55, "z": 0.05},
                },
            }
        ],
    },
    "actions": [{"kind": "predict", "parameters": {"x": 0.5, "y": 0.5, "z": 0.0, "steps": 2}}],
    "expected_artifacts": [
        {"label": "object_count", "kind": "object_count", "value": 1},
        {"label": "step_count", "kind": "step", "value": 2},
    ],
}


def _scenario_file(tmp_path: Path, payload: dict) -> Path:
    target = tmp_path / "scenario.json"
    target.write_text(json.dumps(payload), encoding="utf-8")
    return target


def _clone_payload(payload: dict) -> dict:
    return json.loads(json.dumps(payload))


def _valid_matrix_payload() -> dict:
    payload = _clone_payload(_VALID_PAYLOAD)
    payload["provider"] = "${provider_name}"
    payload["world"]["objects"][0]["position"]["x"] = "${object_x}"
    payload["actions"][0]["parameters"]["provider"] = "${provider_name}"
    payload["actions"][0]["parameters"]["x"] = "${target_x}"
    payload["expected_artifacts"][1]["value"] = "${expected_step}"
    payload["matrix"] = {
        "max_cases": 4,
        "parameters": {
            "expected_step": [2],
            "object_x": [0.0],
            "provider_name": ["mock"],
            "target_x": [0.25, 0.5],
        },
    }
    return payload


def test_parse_valid_scenario_round_trips() -> None:
    scenario = parse_scenario(_VALID_PAYLOAD)

    assert scenario.schema_version == SCENARIO_SCHEMA_VERSION
    assert scenario.id == "first-scenario"
    assert scenario.provider == "mock"
    assert len(scenario.objects) == 1
    assert len(scenario.actions) == 1
    assert scenario.actions[0].kind in SCENARIO_ACTION_KINDS

    payload = scenario.to_dict()
    assert payload["schema_version"] == SCENARIO_SCHEMA_VERSION
    assert payload["world"]["name"] == "scenario-world"
    assert json.loads(scenario.to_json())["id"] == "first-scenario"


def test_load_scenario_from_file_round_trips(tmp_path: Path) -> None:
    target = _scenario_file(tmp_path, _VALID_PAYLOAD)
    scenario = load_scenario(target)
    assert scenario.id == "first-scenario"


def test_load_scenario_matrix_without_matrix_returns_single_case(tmp_path: Path) -> None:
    target = _scenario_file(tmp_path, _VALID_PAYLOAD)
    matrix = load_scenario_matrix(target)
    assert matrix.is_matrix is False
    assert len(matrix.cases) == 1
    assert matrix.cases[0].case_id == "first-scenario"


def test_load_scenario_missing_file_raises(tmp_path: Path) -> None:
    with pytest.raises(WorldForgeError, match="Failed to read scenario file"):
        load_scenario(tmp_path / "missing.json")


def test_parse_scenario_rejects_invalid_json(tmp_path: Path) -> None:
    bad = tmp_path / "bad.json"
    bad.write_text("{not-json", encoding="utf-8")
    with pytest.raises(WorldForgeError, match="invalid JSON"):
        load_scenario(bad)


def test_scenario_cli_error_contract_for_invalid_json(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    bad = tmp_path / "bad.json"
    bad.write_text("{not-json", encoding="utf-8")
    monkeypatch.setattr(
        sys,
        "argv",
        ["worldforge", "scenario", "validate", str(bad), "--format", "json"],
    )

    with pytest.raises(SystemExit) as excinfo:
        worldforge_main()

    error = capsys.readouterr().err
    assert excinfo.value.code == 2
    assert "WorldForge CLI error [scenario validate]" in error
    assert "invalid JSON" in error
    assert "First triage:" in error
    assert "worldforge scenario validate <scenario.json>" in error
    assert "Traceback" not in error
    assert str(tmp_path) not in error


def test_parse_scenario_rejects_unsupported_schema_version() -> None:
    payload = {**_VALID_PAYLOAD, "schema_version": 99}
    with pytest.raises(WorldForgeError, match="schema_version"):
        parse_scenario(payload)


def test_parse_scenario_rejects_traversal_id() -> None:
    payload = {**_VALID_PAYLOAD, "id": "../escape"}
    with pytest.raises(WorldForgeError, match="traversal-shaped"):
        parse_scenario(payload)


def test_parse_scenario_rejects_missing_provider() -> None:
    payload = {**_VALID_PAYLOAD, "provider": ""}
    with pytest.raises(WorldForgeError, match="provider"):
        parse_scenario(payload)


def test_parse_scenario_rejects_unknown_action_kind() -> None:
    payload = {
        **_VALID_PAYLOAD,
        "actions": [{"kind": "summon_demon", "parameters": {}}],
    }
    with pytest.raises(WorldForgeError, match="actions"):
        parse_scenario(payload)


def test_parse_scenario_rejects_non_array_actions() -> None:
    payload = {**_VALID_PAYLOAD, "actions": "not-a-list"}
    with pytest.raises(WorldForgeError, match="must be a JSON array"):
        parse_scenario(payload)


def test_parse_scenario_rejects_non_object_world() -> None:
    payload = {**_VALID_PAYLOAD, "world": "scene"}
    with pytest.raises(WorldForgeError, match="'world' must be a JSON object"):
        parse_scenario(payload)


def test_parse_scenario_rejects_invalid_object_position() -> None:
    payload = {
        **_VALID_PAYLOAD,
        "world": {
            "name": "w",
            "objects": [
                {
                    "name": "cube",
                    "position": "nope",
                    "bbox": _VALID_PAYLOAD["world"]["objects"][0]["bbox"],
                }
            ],
        },
    }
    with pytest.raises(WorldForgeError, match="position"):
        parse_scenario(payload)


def test_parse_scenario_rejects_unknown_expectation_kind() -> None:
    payload = {
        **_VALID_PAYLOAD,
        "expected_artifacts": [{"label": "weird", "kind": "purr", "value": 1}],
    }
    with pytest.raises(WorldForgeError, match="expected_artifacts"):
        parse_scenario(payload)


def test_run_scenario_creates_world_and_records_object_count(tmp_path: Path) -> None:
    forge = WorldForge(state_dir=tmp_path)
    scenario = parse_scenario(_VALID_PAYLOAD)
    result = run_scenario(forge, scenario)

    assert result.scenario_id == "first-scenario"
    assert result.object_count == 1
    assert result.final_step >= 1
    assert result.all_expectations_passed() is True


def test_parse_scenario_matrix_expands_valid_parameter_matrix(tmp_path: Path) -> None:
    matrix = parse_scenario_matrix(_valid_matrix_payload())

    assert matrix.is_matrix is True
    assert matrix.scenario_id == "first-scenario"
    assert len(matrix.cases) == 2
    assert matrix.metadata["parameter_names"] == [
        "expected_step",
        "object_x",
        "provider_name",
        "target_x",
    ]
    assert matrix.cases[0].case_id == "first-scenario-case-1"
    assert matrix.cases[0].scenario.provider == "mock"
    assert matrix.cases[0].scenario.world_name == "scenario-world-case-1"
    assert matrix.cases[0].scenario.objects[0].position.x == 0.0
    assert matrix.cases[0].scenario.actions[0].parameters["x"] == 0.25
    assert matrix.cases[1].scenario.actions[0].parameters["x"] == 0.5
    assert matrix.cases[0].scenario.expected_artifacts[1].value == 2
    assert matrix.cases[0].scenario.metadata["matrix_case"]["source_id"] == "first-scenario"

    result = run_scenario_matrix(WorldForge(state_dir=tmp_path), matrix)
    assert result.case_count == 2
    assert result.passed_case_count == 2
    assert result.failed_case_count == 0
    assert result.all_cases_passed() is True


def test_parse_scenario_matrix_rejects_invalid_substitution_location() -> None:
    payload = _valid_matrix_payload()
    payload["world"]["objects"][0]["name"] = "${object_name}"
    payload["matrix"]["parameters"]["object_name"] = ["cube"]

    with pytest.raises(WorldForgeError, match="not allowed"):
        parse_scenario_matrix(payload)


def test_parse_scenario_matrix_rejects_partial_placeholder() -> None:
    payload = _valid_matrix_payload()
    payload["provider"] = "mock-${provider_name}"

    with pytest.raises(WorldForgeError, match="entire JSON value"):
        parse_scenario_matrix(payload)


def test_parse_scenario_matrix_rejects_unbounded_cases() -> None:
    payload = _valid_matrix_payload()
    payload["matrix"]["max_cases"] = 1

    with pytest.raises(WorldForgeError, match="exceeding max_cases"):
        parse_scenario_matrix(payload)


def test_parse_scenario_matrix_rejects_non_json_native_values() -> None:
    payload = _valid_matrix_payload()
    payload["matrix"]["parameters"]["target_x"] = [(0.25, 0.5)]

    with pytest.raises(WorldForgeError, match="JSON-native"):
        parse_scenario_matrix(payload)


def test_run_scenario_matrix_reports_failed_expectation(tmp_path: Path) -> None:
    payload = _valid_matrix_payload()
    payload["expected_artifacts"][0]["value"] = "${expected_object_count}"
    payload["matrix"]["parameters"]["expected_object_count"] = [1, 99]
    payload["matrix"]["max_cases"] = 8

    result = run_scenario_matrix(
        WorldForge(state_dir=tmp_path),
        parse_scenario_matrix(payload),
    )

    assert result.case_count == 4
    assert result.passed_case_count == 2
    assert result.failed_case_count == 2
    rendered = result.to_dict()
    assert len(rendered["failed_cases"]) == 2
    assert rendered["failed_cases"][0]["passed"] is False


def test_run_scenario_result_supports_exact_stable_snapshot(tmp_path: Path) -> None:
    forge = WorldForge(state_dir=tmp_path)
    result = run_scenario(forge, parse_scenario(_VALID_PAYLOAD))

    snapshot = stable_snapshot(
        result.to_dict(),
        path_roots={tmp_path: "<state>"},
        field_replacements={"world_id": "<world-id>"},
    )

    assert stable_json_dumps(snapshot) == (
        "{\n"
        '  "all_expectations_passed": true,\n'
        '  "expectation_checks": [\n'
        "    {\n"
        '      "expected": 1,\n'
        '      "kind": "object_count",\n'
        '      "label": "object_count",\n'
        '      "observed": 1,\n'
        '      "passed": true\n'
        "    },\n"
        "    {\n"
        '      "expected": 2,\n'
        '      "kind": "step",\n'
        '      "label": "step_count",\n'
        '      "observed": 2,\n'
        '      "passed": true\n'
        "    }\n"
        "  ],\n"
        '  "final_step": 2,\n'
        '  "object_count": 1,\n'
        '  "scenario_id": "first-scenario",\n'
        '  "schema_version": 1,\n'
        '  "world_id": "<world-id>"\n'
        "}\n"
    )


def test_run_scenario_records_failed_expectations_without_raising(tmp_path: Path) -> None:
    forge = WorldForge(state_dir=tmp_path)
    payload = {
        **_VALID_PAYLOAD,
        "expected_artifacts": [{"label": "object_count", "kind": "object_count", "value": 99}],
    }
    result = run_scenario(forge, parse_scenario(payload))
    assert result.all_expectations_passed() is False
    assert result.expectation_checks[0].observed == 1


def test_run_scenario_supports_spawn_action(tmp_path: Path) -> None:
    forge = WorldForge(state_dir=tmp_path)
    payload = {
        **_VALID_PAYLOAD,
        "actions": [
            {
                "kind": "spawn_object",
                "parameters": {
                    "name": "mug",
                    "x": 0.25,
                    "y": 0.8,
                    "z": 0.0,
                    "bbox": {
                        "min": {"x": 0.2, "y": 0.75, "z": -0.05},
                        "max": {"x": 0.3, "y": 0.85, "z": 0.05},
                    },
                },
            }
        ],
        "expected_artifacts": [
            {"label": "object_count", "kind": "object_count", "value": 2},
        ],
    }
    result = run_scenario(forge, parse_scenario(payload))
    assert result.object_count == 2
    assert result.all_expectations_passed() is True


def test_run_scenario_supports_object_position_expectation(tmp_path: Path) -> None:
    forge = WorldForge(state_dir=tmp_path)
    payload = {
        **_VALID_PAYLOAD,
        "expected_artifacts": [
            {
                "label": "any-position",
                "kind": "object_position",
                "value": {
                    "object_id": "obj_missing",
                    "position": {"x": 0.0, "y": 0.0, "z": 0.0},
                },
            }
        ],
    }
    result = run_scenario(forge, parse_scenario(payload))
    assert result.expectation_checks[0].passed is False


def test_run_scenario_rejects_non_scenario_argument(tmp_path: Path) -> None:
    forge = WorldForge(state_dir=tmp_path)
    with pytest.raises(WorldForgeError, match="Scenario instance"):
        run_scenario(forge, {"id": "not-a-scenario"})  # type: ignore[arg-type]


def test_scenario_object_spec_to_scene_object_round_trips() -> None:
    scenario = parse_scenario(_VALID_PAYLOAD)
    obj = scenario.objects[0]
    scene_object = obj.to_scene_object()
    assert scene_object.name == "cube"
    assert scene_object.position.x == 0.0


def test_scenario_action_kind_validation() -> None:
    with pytest.raises(WorldForgeError, match="kind must be one of"):
        ScenarioAction(kind="weird", parameters={})


def test_scenario_expected_artifact_kind_validation() -> None:
    with pytest.raises(WorldForgeError, match="kind must be one of"):
        ScenarioExpectedArtifact(label="x", kind="bogus", value=1)


def test_scenario_validate_cli(tmp_path: Path, monkeypatch, capsys) -> None:
    target = _scenario_file(tmp_path, _VALID_PAYLOAD)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "worldforge",
            "scenario",
            "validate",
            str(target),
            "--format",
            "json",
        ],
    )
    assert worldforge_main() == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["id"] == "first-scenario"


def test_scenario_run_cli(tmp_path: Path, monkeypatch, capsys) -> None:
    target = _scenario_file(tmp_path, _VALID_PAYLOAD)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "worldforge",
            "scenario",
            "run",
            str(target),
            "--state-dir",
            str(tmp_path / "worlds"),
            "--format",
            "json",
        ],
    )
    assert worldforge_main() == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["scenario_id"] == "first-scenario"
    assert payload["all_expectations_passed"] is True


def test_scenario_matrix_cli_runs_all_cases(tmp_path: Path, monkeypatch, capsys) -> None:
    target = _scenario_file(tmp_path, _valid_matrix_payload())
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "worldforge",
            "scenario",
            "run",
            str(target),
            "--state-dir",
            str(tmp_path / "worlds"),
            "--format",
            "json",
        ],
    )

    assert worldforge_main() == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["scenario_id"] == "first-scenario"
    assert payload["case_count"] == 2
    assert payload["passed_case_count"] == 2
    assert payload["failed_case_count"] == 0
    assert payload["cases"][0]["case_id"] == "first-scenario-case-1"


def test_scenario_run_cli_writes_output_file(tmp_path: Path, monkeypatch, capsys) -> None:
    target = _scenario_file(tmp_path, _VALID_PAYLOAD)
    output = tmp_path / "out" / "result.json"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "worldforge",
            "scenario",
            "run",
            str(target),
            "--state-dir",
            str(tmp_path / "worlds"),
            "--format",
            "markdown",
            "--output",
            str(output),
        ],
    )
    assert worldforge_main() == 0
    assert capsys.readouterr().out == ""
    assert output.read_text(encoding="utf-8").startswith("# WorldForge Scenario Result")


def test_bundled_sample_scenarios_validate_and_run(tmp_path: Path) -> None:
    sample_dir = Path(__file__).resolve().parents[1] / "examples" / "scenarios"
    samples = sorted(sample_dir.glob("*.json"))
    assert len(samples) >= 5

    intents: set[str] = set()
    for sample in samples:
        scenario = load_scenario(sample)
        assert isinstance(scenario, Scenario)
        assert scenario.metadata
        intent = str(scenario.metadata.get("gallery_intent", "world setup"))
        intents.add(intent)
        forge = WorldForge(state_dir=tmp_path / sample.stem)
        if scenario.metadata.get("expected_cli_error") is True:
            with pytest.raises(
                WorldForgeError,
                match=str(scenario.metadata["expected_error_contains"]),
            ):
                run_scenario(forge, scenario)
            continue

        result = run_scenario(forge, scenario)
        if scenario.metadata.get("expected_failure") is True:
            assert result.all_expectations_passed() is False
            assert any(not check.passed for check in result.expectation_checks)
        else:
            assert result.all_expectations_passed() is True

    assert {
        "world setup",
        "failed expectation",
        "invalid action",
        "evaluation-oriented setup",
        "report/export",
    } <= intents


def test_scenario_gallery_cli_runs_expected_success_and_failure_modes(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    sample_dir = Path(__file__).resolve().parents[1] / "examples" / "scenarios"
    samples = sorted(sample_dir.glob("*.json"))

    for sample in samples:
        monkeypatch.setattr(
            sys,
            "argv",
            ["worldforge", "scenario", "validate", str(sample), "--format", "json"],
        )
        assert worldforge_main() == 0
        validated = json.loads(capsys.readouterr().out)
        metadata = validated.get("metadata", {})

        output = tmp_path / "outputs" / f"{sample.stem}.json"
        monkeypatch.setattr(
            sys,
            "argv",
            [
                "worldforge",
                "scenario",
                "run",
                str(sample),
                "--state-dir",
                str(tmp_path / "worlds" / sample.stem),
                "--format",
                "json",
                "--output",
                str(output),
            ],
        )
        if metadata.get("expected_cli_error") is True:
            with pytest.raises(SystemExit) as excinfo:
                worldforge_main()
            assert excinfo.value.code == 2
            error = capsys.readouterr().err
            assert metadata["expected_error_contains"] in error
            continue

        exit_code = worldforge_main()
        assert output.exists()
        result = json.loads(output.read_text(encoding="utf-8"))
        if metadata.get("expected_failure") is True:
            assert exit_code == 1
            assert result["all_expectations_passed"] is False
        else:
            assert exit_code == 0
            assert result["all_expectations_passed"] is True

"""Tests for the WorldForge capability fixture corpus."""

from __future__ import annotations

import re
from base64 import b64decode
from dataclasses import replace
from pathlib import Path

import pytest

from worldforge import VideoClip, World, WorldForge, WorldForgeError
from worldforge.models import Action
from worldforge.testing import (
    CAPABILITY_FIXTURE_NAMES,
    FIXTURE_SCHEMA_VERSION,
    CapabilityFixture,
    FixtureSnapshotEntry,
    FixtureSnapshotManifest,
    build_fixture_snapshot_manifest,
    iter_all_fixtures,
    iter_capability_fixtures,
    list_fixture_names,
    load_capability_fixture,
    load_fixture_snapshot_manifest,
    validate_fixture_snapshot_manifest,
)

ROOT = Path(__file__).resolve().parents[1]
VALID_SHA256 = "sha256:" + "a" * 64


def test_corpus_covers_every_capability() -> None:
    expected = {
        "predict",
        "reason",
        "embed",
        "generate",
        "transfer",
        "score",
        "policy",
    }
    assert set(CAPABILITY_FIXTURE_NAMES) == expected


@pytest.mark.parametrize("capability", CAPABILITY_FIXTURE_NAMES)
def test_each_capability_has_one_valid_and_two_invalid_fixtures(capability: str) -> None:
    fixtures = list(iter_capability_fixtures(capability))
    valid = [fx for fx in fixtures if fx.is_valid()]
    invalid = [fx for fx in fixtures if not fx.is_valid()]
    assert len(valid) >= 1, f"{capability} must ship a valid baseline fixture"
    assert len(invalid) >= 2, f"{capability} must ship at least two invalid boundary fixtures"


def test_iter_all_fixtures_yields_unique_ids_and_round_trips() -> None:
    fixtures = list(iter_all_fixtures())
    assert len(fixtures) == sum(
        len(list_fixture_names(capability)) for capability in CAPABILITY_FIXTURE_NAMES
    )
    fixture_ids = {fx.id for fx in fixtures}
    assert len(fixture_ids) == len(fixtures)
    for fixture in fixtures:
        assert isinstance(fixture, CapabilityFixture)
        envelope = fixture.to_dict()
        assert envelope["schema_version"] == FIXTURE_SCHEMA_VERSION
        assert envelope["id"] == fixture.id


def test_load_capability_fixture_rejects_unknown_inputs() -> None:
    with pytest.raises(WorldForgeError, match="Unknown capability"):
        load_capability_fixture("plan", "valid_baseline")
    with pytest.raises(WorldForgeError, match="not found"):
        load_capability_fixture("predict", "no_such_fixture")


def test_invalid_fixtures_carry_distinct_error_patterns_per_capability() -> None:
    for capability in CAPABILITY_FIXTURE_NAMES:
        invalid = [fx for fx in iter_capability_fixtures(capability) if not fx.is_valid()]
        patterns = {fx.expected_error_pattern for fx in invalid}
        assert len(patterns) == len(invalid), (
            f"{capability} invalid fixtures duplicate expected_error_pattern: {patterns}"
        )


def test_predict_valid_baseline_runs_through_facade(tmp_path) -> None:
    fixture = load_capability_fixture("predict", "valid_baseline")
    forge = WorldForge(state_dir=tmp_path)
    world = World.from_state(forge, fixture.payload["world_state"])
    action = Action.from_dict(fixture.payload["action"])
    payload = world.predict(action, steps=fixture.payload["steps"], provider="mock")
    assert payload.metadata.get("provider") == "mock"
    assert 0.0 <= payload.confidence <= 1.0


def test_predict_invalid_steps_is_rejected_at_facade(tmp_path) -> None:
    fixture = load_capability_fixture("predict", "invalid_action_steps_zero")
    forge = WorldForge(state_dir=tmp_path)
    world = World.from_state(forge, fixture.payload["world_state"])
    action = Action.from_dict(fixture.payload["action"])
    pattern = re.compile(fixture.expected_error_pattern or ".*", re.IGNORECASE)
    with pytest.raises(WorldForgeError) as excinfo:
        world.predict(action, steps=fixture.payload["steps"], provider="mock")
    assert pattern.search(str(excinfo.value))


def test_predict_invalid_world_state_is_rejected_at_facade(tmp_path) -> None:
    fixture = load_capability_fixture("predict", "invalid_world_state_missing_schema")
    forge = WorldForge(state_dir=tmp_path)
    pattern = re.compile(fixture.expected_error_pattern or ".*", re.IGNORECASE)
    with pytest.raises(WorldForgeError) as excinfo:
        World.from_state(forge, fixture.payload["world_state"])
    assert pattern.search(str(excinfo.value))


def test_reason_valid_baseline_runs_through_facade(tmp_path) -> None:
    fixture = load_capability_fixture("reason", "valid_baseline")
    forge = WorldForge(state_dir=tmp_path)
    world = World.from_state(forge, fixture.payload["world_state"])
    result = forge.reason("mock", fixture.payload["query"], world=world)
    assert result.provider == "mock"
    assert result.answer


def test_reason_invalid_world_state_is_rejected(tmp_path) -> None:
    fixture = load_capability_fixture("reason", "invalid_world_state_corrupt")
    forge = WorldForge(state_dir=tmp_path)
    pattern = re.compile(fixture.expected_error_pattern or ".*", re.IGNORECASE)
    with pytest.raises(WorldForgeError) as excinfo:
        World.from_state(forge, fixture.payload["world_state"])
    assert pattern.search(str(excinfo.value))


def test_reason_invalid_query_documents_contract_claim() -> None:
    fixture = load_capability_fixture("reason", "invalid_query_empty")
    assert fixture.expected == "invalid"
    assert fixture.payload["query"] == ""


def test_embed_valid_baseline_runs_through_facade(tmp_path) -> None:
    fixture = load_capability_fixture("embed", "valid_baseline")
    forge = WorldForge(state_dir=tmp_path)
    result = forge.embed("mock", text=fixture.payload["text"])
    assert result.provider == "mock"
    assert result.vector


def test_embed_invalid_fixtures_document_contract_claims() -> None:
    empty = load_capability_fixture("embed", "invalid_text_empty")
    whitespace = load_capability_fixture("embed", "invalid_text_whitespace")
    assert empty.payload["text"] == ""
    assert whitespace.payload["text"].strip() == ""
    assert empty.expected_error_pattern != whitespace.expected_error_pattern


def test_generate_valid_baseline_runs_through_facade(tmp_path) -> None:
    fixture = load_capability_fixture("generate", "valid_baseline")
    forge = WorldForge(state_dir=tmp_path)
    clip = forge.generate(
        fixture.payload["prompt"],
        "mock",
        duration_seconds=fixture.payload["duration_seconds"],
    )
    assert isinstance(clip, VideoClip)
    assert clip.duration_seconds == fixture.payload["duration_seconds"]


def test_generate_invalid_prompt_is_rejected(tmp_path) -> None:
    fixture = load_capability_fixture("generate", "invalid_prompt_empty")
    forge = WorldForge(state_dir=tmp_path)
    pattern = re.compile(fixture.expected_error_pattern or ".*", re.IGNORECASE)
    with pytest.raises(WorldForgeError) as excinfo:
        forge.generate(
            fixture.payload["prompt"],
            "mock",
            duration_seconds=fixture.payload["duration_seconds"],
        )
    assert pattern.search(str(excinfo.value))


def test_generate_invalid_duration_is_rejected(tmp_path) -> None:
    fixture = load_capability_fixture("generate", "invalid_duration_zero")
    forge = WorldForge(state_dir=tmp_path)
    pattern = re.compile(fixture.expected_error_pattern or ".*", re.IGNORECASE)
    with pytest.raises(WorldForgeError) as excinfo:
        forge.generate(
            fixture.payload["prompt"],
            "mock",
            duration_seconds=fixture.payload["duration_seconds"],
        )
    assert pattern.search(str(excinfo.value))


def _build_clip(payload_clip: dict) -> VideoClip:
    frames = [b64decode(frame, validate=True) for frame in payload_clip["frames_base64"]]
    return VideoClip(
        frames=frames,
        fps=payload_clip["fps"],
        resolution=tuple(payload_clip["resolution"]),
        duration_seconds=payload_clip["duration_seconds"],
        metadata=dict(payload_clip.get("metadata", {})),
    )


def test_transfer_valid_baseline_runs_through_facade(tmp_path) -> None:
    fixture = load_capability_fixture("transfer", "valid_baseline")
    forge = WorldForge(state_dir=tmp_path)
    clip = _build_clip(fixture.payload["clip"])
    transferred = forge.transfer(
        clip,
        "mock",
        width=fixture.payload["width"],
        height=fixture.payload["height"],
        fps=fixture.payload["fps"],
    )
    assert isinstance(transferred, VideoClip)


@pytest.mark.parametrize(
    "fixture_name",
    ["invalid_clip_negative_duration", "invalid_clip_resolution_zero"],
)
def test_transfer_invalid_clip_is_rejected_at_construction(fixture_name: str) -> None:
    fixture = load_capability_fixture("transfer", fixture_name)
    pattern = re.compile(fixture.expected_error_pattern or ".*", re.IGNORECASE)
    with pytest.raises(WorldForgeError) as excinfo:
        _build_clip(fixture.payload["clip"])
    assert pattern.search(str(excinfo.value))


def test_score_valid_baseline_payload_has_required_keys() -> None:
    fixture = load_capability_fixture("score", "valid_baseline")
    info = fixture.payload["info"]
    assert {"pixels", "goal", "action"}.issubset(info.keys())
    assert fixture.payload["action_candidates"]


def test_score_invalid_fixtures_are_distinct_boundary_cases() -> None:
    empty_info = load_capability_fixture("score", "invalid_info_empty")
    empty_candidates = load_capability_fixture("score", "invalid_action_candidates_empty")
    assert empty_info.expected == "invalid"
    assert empty_candidates.expected == "invalid"
    assert empty_info.payload["info"] == {}
    assert empty_candidates.payload["action_candidates"] == []


def test_policy_valid_baseline_payload_has_observation() -> None:
    fixture = load_capability_fixture("policy", "valid_baseline")
    info = fixture.payload["info"]
    assert "observation" in info
    assert info.get("action_horizon", 0) >= 1


def test_policy_invalid_fixtures_are_distinct_boundary_cases() -> None:
    missing = load_capability_fixture("policy", "invalid_observation_missing")
    bad_horizon = load_capability_fixture("policy", "invalid_action_horizon_negative")
    assert "observation" not in missing.payload["info"]
    assert bad_horizon.payload["info"]["action_horizon"] == -1


def test_fixture_snapshot_manifest_loads_and_validates_committed_manifest() -> None:
    manifest = load_fixture_snapshot_manifest(
        ROOT / "tests" / "fixtures" / "fixture-snapshots.json"
    )
    report = validate_fixture_snapshot_manifest(manifest, root=ROOT)

    assert report.passed, report.to_markdown()
    fixture_kinds = {entry.fixture_kind for entry in manifest.entries}
    assert {
        "capability-fixture",
        "provider-payload-fixture",
        "benchmark-fixture",
        "scenario-fixture",
        "scene-artifact-fixture",
    }.issubset(fixture_kinds)
    assert any(
        entry.path == "src/worldforge/testing/fixtures/predict/valid_baseline.json"
        for entry in manifest.entries
    )
    assert any(entry.path == "examples/benchmark-inputs.json" for entry in manifest.entries)


def test_fixture_snapshot_manifest_reports_digest_drift_and_intended_updates(
    tmp_path: Path,
) -> None:
    fixture = tmp_path / "src/worldforge/testing/fixtures/predict/sample.json"
    fixture.parent.mkdir(parents=True)
    fixture.write_text('{"schema_version": 1, "payload": {"value": 1}}\n', encoding="utf-8")
    manifest = build_fixture_snapshot_manifest((fixture,), root=tmp_path)

    fixture.write_text('{"schema_version": 1, "payload": {"value": 2}}\n', encoding="utf-8")
    drift_report = validate_fixture_snapshot_manifest(manifest, root=tmp_path)
    assert drift_report.passed is False
    assert [issue.status for issue in drift_report.issues] == ["changed"]
    assert "without an intended-update marker" in drift_report.to_markdown()

    intended_entry = replace(manifest.entries[0], review_status="intended-update")
    intended_manifest = FixtureSnapshotManifest(entries=(intended_entry,))
    intended_report = validate_fixture_snapshot_manifest(intended_manifest, root=tmp_path)
    assert intended_report.passed is False
    assert [issue.status for issue in intended_report.issues] == ["intended-update"]
    assert "marked for review" in intended_report.to_markdown()

    allowed_report = validate_fixture_snapshot_manifest(
        intended_manifest,
        root=tmp_path,
        allow_intended_updates=True,
    )
    assert allowed_report.passed is True


def test_fixture_snapshot_manifest_rejects_missing_and_unsafe_paths(tmp_path: Path) -> None:
    manifest = FixtureSnapshotManifest(
        entries=(
            FixtureSnapshotEntry(
                path="tests/fixtures/providers/missing.json",
                sha256=VALID_SHA256,
                size_bytes=1,
                fixture_kind="provider-payload-fixture",
            ),
            FixtureSnapshotEntry(
                path="../escape.json",
                sha256=VALID_SHA256,
                size_bytes=1,
                fixture_kind="provider-payload-fixture",
            ),
            FixtureSnapshotEntry(
                path="tests\\fixtures\\providers\\sample.json",
                sha256=VALID_SHA256,
                size_bytes=1,
                fixture_kind="provider-payload-fixture",
            ),
        )
    )

    report = validate_fixture_snapshot_manifest(manifest, root=tmp_path)

    assert report.passed is False
    assert [issue.status for issue in report.issues] == ["missing", "unsafe", "unsafe"]
    assert "fixture path is missing" in report.to_markdown()
    assert "parent-directory" in report.issues[1].message
    assert "backslashes" in report.issues[2].message

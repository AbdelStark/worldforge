from __future__ import annotations

import json

import pytest

from worldforge import (
    Action,
    BBox,
    Position,
    SceneObject,
    SceneObjectPatch,
    WorldForge,
    WorldForgeError,
    WorldStateError,
)
from worldforge.world_migration_preview import (
    preview_world_migration,
    preview_world_migration_from_path,
    preview_world_migration_from_world_id,
    render_world_migration_preview_markdown,
)


def test_world_prediction_compare_and_persistence_flow(tmp_path) -> None:
    forge = WorldForge(state_dir=tmp_path)
    assert "mock" in forge.providers()

    world = forge.create_world("kitchen-counter", "mock")
    world.add_object(
        SceneObject(
            "red_mug",
            Position(0.0, 0.8, 0.0),
            BBox(Position(-0.05, 0.75, -0.05), Position(0.05, 0.85, 0.05)),
        )
    )

    prediction = world.predict(Action.move_to(0.25, 0.8, 0.0, 1.0), steps=4)
    assert prediction.provider == "mock"
    assert prediction.confidence >= 0.0

    comparison = world.compare(Action.move_to(0.3, 0.8, 0.0, 1.0), ["mock"], steps=2)
    assert comparison.best_prediction().provider == "mock"

    world_id = forge.save_world(world)
    assert world_id in forge.list_worlds()
    assert list(tmp_path.glob("*.tmp")) == []
    assert list(tmp_path.glob(".*.tmp")) == []

    snapshot_json = forge.export_world(world_id, format="json")
    payload = json.loads(snapshot_json)
    assert payload["schema_version"] == 1
    assert payload["state"]["metadata"]["name"] == "kitchen-counter"

    snapshot_copy = forge.import_world(snapshot_json, format="json", new_id=True, name="copy")
    assert snapshot_copy.id != world_id
    assert snapshot_copy.name == "copy"
    assert snapshot_copy.object_count == 1

    loaded = forge.load_world(world_id)
    assert "red_mug" in loaded.list_objects()

    objects = loaded.objects()
    assert len(objects) == 1
    object_id = objects[0].id
    fetched = loaded.get_object_by_id(object_id)
    assert fetched is not None
    assert fetched.name == "red_mug"

    patch = SceneObjectPatch()
    patch.set_name("coffee_mug")
    patch.set_position(Position(0.1, 0.8, 0.0))
    patch.set_graspable(True)
    updated = loaded.update_object_patch(object_id, patch)
    assert updated.id == object_id
    assert updated.name == "coffee_mug"
    assert updated.is_graspable is True

    removed = loaded.remove_object_by_id(object_id)
    assert removed is not None
    assert removed.id == object_id
    assert loaded.object_count == 0


def test_world_delete_validates_id_and_removes_persisted_file(tmp_path) -> None:
    forge = WorldForge(state_dir=tmp_path)
    world = forge.create_world("delete-me", provider="mock")
    world_id = forge.save_world(world)

    assert world_id in forge.list_worlds()
    assert forge.delete_world(world_id) == world_id
    assert world_id not in forge.list_worlds()

    with pytest.raises(WorldStateError, match="not present"):
        forge.delete_world(world_id)

    with pytest.raises(WorldForgeError, match="file-safe identifier"):
        forge.delete_world("../outside")


def test_world_delete_can_remove_corrupted_local_json_by_safe_id(tmp_path) -> None:
    forge = WorldForge(state_dir=tmp_path)
    broken_path = tmp_path / "broken.json"
    broken_path.write_text("{not valid json", encoding="utf-8")

    assert "broken" in forge.list_worlds()
    assert forge.delete_world("broken") == "broken"
    assert not broken_path.exists()


def test_world_object_mutations_record_history_and_keep_bbox_coherent(tmp_path) -> None:
    forge = WorldForge(state_dir=tmp_path)
    world = forge.create_world("mutation-history", provider="mock")

    added = world.add_object(
        SceneObject(
            "cube",
            Position(0.0, 0.5, 0.0),
            BBox(Position(-0.05, 0.45, -0.05), Position(0.05, 0.55, 0.05)),
            id="cube-1",
            is_graspable=True,
        )
    )
    assert added.id == "cube-1"
    assert world.history_length == 2

    add_entry = world.history()[-1]
    add_action = json.loads(add_entry.action_json or "{}")
    assert add_entry.summary == "added object cube-1"
    assert add_action["type"] == "add_object"
    assert add_action["parameters"]["object"]["id"] == "cube-1"
    assert "cube-1" in add_entry.state["scene"]["objects"]

    patch = SceneObjectPatch()
    patch.set_name("blue_cube")
    patch.set_position(Position(0.25, 0.5, 0.1))
    patch.set_graspable(False)
    updated = world.update_object_patch("cube-1", patch)
    assert updated.name == "blue_cube"
    assert updated.bbox.min.x == pytest.approx(0.20)
    assert updated.bbox.max.x == pytest.approx(0.30)
    assert updated.bbox.min.z == pytest.approx(0.05)
    assert updated.bbox.max.z == pytest.approx(0.15)

    update_entry = world.history()[-1]
    update_action = json.loads(update_entry.action_json or "{}")
    assert update_entry.summary == "updated object cube-1"
    assert update_action["type"] == "update_object"
    assert update_action["parameters"]["changes"] == {
        "name": "blue_cube",
        "position": {"x": 0.25, "y": 0.5, "z": 0.1},
        "is_graspable": False,
    }
    assert update_action["parameters"]["before"]["name"] == "cube"
    assert update_action["parameters"]["after"]["name"] == "blue_cube"

    history_length = world.history_length
    noop = world.update_object_patch("cube-1", SceneObjectPatch())
    assert noop.id == "cube-1"
    assert world.history_length == history_length

    checkpoint = world.history_state(1)
    checkpoint_object = checkpoint.get_object_by_id("cube-1")
    assert checkpoint_object is not None
    assert checkpoint_object.name == "cube"
    assert checkpoint_object.position == Position(0.0, 0.5, 0.0)

    removed = world.remove_object_by_id("cube-1")
    assert removed is not None
    assert removed.id == "cube-1"
    assert world.object_count == 0
    assert world.history_length == 4

    remove_entry = world.history()[-1]
    remove_action = json.loads(remove_entry.action_json or "{}")
    assert remove_entry.summary == "removed object cube-1"
    assert remove_action["type"] == "remove_object"
    assert remove_action["parameters"]["object_id"] == "cube-1"
    assert "cube-1" not in remove_entry.state["scene"]["objects"]

    world_id = forge.save_world(world)
    loaded = forge.load_world(world_id)
    assert [entry.summary for entry in loaded.history()] == [
        "world initialized",
        "added object cube-1",
        "updated object cube-1",
        "removed object cube-1",
    ]

    loaded.restore_history(1)
    restored_object = loaded.get_object_by_id("cube-1")
    assert restored_object is not None
    assert restored_object.name == "cube"
    assert loaded.history_length == 2


def test_world_object_mutation_rejects_non_json_history_without_state_change(tmp_path) -> None:
    forge = WorldForge(state_dir=tmp_path)
    world = forge.create_world("transactional-history", provider="mock")

    bad_object = SceneObject(
        "bad_cube",
        Position(0.0, 0.5, 0.0),
        BBox(Position(-0.05, 0.45, -0.05), Position(0.05, 0.55, 0.05)),
        id="bad-cube",
    )
    bad_object.metadata["not_json"] = object()

    with pytest.raises(WorldForgeError, match="JSON-compatible"):
        world.add_object(bad_object)

    assert world.object_count == 0
    assert world.history_length == 1
    assert world.list_objects() == []


def test_predict_rejects_non_json_action_before_provider_state_change(tmp_path) -> None:
    forge = WorldForge(state_dir=tmp_path)
    world = forge.create_world("transactional-predict", provider="mock")

    bad_action = Action("custom", {})
    bad_action.parameters["not_json"] = object()

    with pytest.raises(WorldForgeError, match="JSON serializable"):
        world.predict(bad_action, steps=1)

    assert world.step == 0
    assert world.history_length == 1


def test_prompt_seeded_world_history_and_forking(tmp_path) -> None:
    forge = WorldForge(state_dir=tmp_path)
    seeded = forge.create_world_from_prompt(
        "A kitchen with a mug", provider="mock", name="seeded-kitchen"
    )

    assert seeded.name == "seeded-kitchen"
    assert seeded.description == "A kitchen with a mug"
    assert seeded.object_count >= 2

    prediction = seeded.predict(Action.move_to(0.25, 0.5, 0.0), steps=2)
    assert prediction.provider == "mock"
    assert seeded.history_length >= 2

    history = seeded.history()
    assert history[0].action_json is None
    assert history[-1].action_json is not None

    checkpoint = seeded.history_state(0)
    assert checkpoint.step == 0
    assert checkpoint.history_length == 1

    seeded.restore_history(0)
    assert seeded.step == 0

    saved_id = forge.save_world(seeded)
    forked = forge.fork_world(saved_id, history_index=0, name="seeded-kitchen-branch")
    assert forked.id != saved_id
    assert forked.name == "seeded-kitchen-branch"
    assert forked.history_length == 1


def test_world_rejects_invalid_runtime_inputs(tmp_path) -> None:
    forge = WorldForge(state_dir=tmp_path)
    world = forge.create_world("validation-world", "mock")

    with pytest.raises(WorldForgeError, match="steps"):
        world.predict(Action.move_to(0.1, 0.2, 0.3), steps=0)

    with pytest.raises(WorldForgeError, match="compare\\(\\) requires at least one provider"):
        world.compare(Action.move_to(0.1, 0.2, 0.3), [], steps=1)

    with pytest.raises(WorldForgeError, match="max_steps"):
        world.plan(goal="spawn cube", max_steps=0)

    with pytest.raises(WorldForgeError, match="History index"):
        world.history_state(1)

    with pytest.raises(WorldForgeError, match="not present in world"):
        world.update_object_patch("missing-object", SceneObjectPatch(name="ghost"))

    with pytest.raises(WorldForgeError, match="SceneObjectPatch position"):
        SceneObjectPatch(position="bad")  # type: ignore[arg-type]

    with pytest.raises(WorldForgeError, match="SceneObjectPatch"):
        world.update_object_patch("missing-object", "bad")  # type: ignore[arg-type]


def test_world_import_and_load_reject_malformed_state(tmp_path) -> None:
    forge = WorldForge(state_dir=tmp_path)

    with pytest.raises(WorldStateError, match="not valid JSON"):
        forge.import_world("{broken json")

    with pytest.raises(WorldStateError, match="missing required keys"):
        forge.import_world(json.dumps({"state": {"name": "invalid"}}))

    with pytest.raises(WorldStateError, match="JSON object"):
        forge.import_world(json.dumps({"state": "not-a-world"}))

    unsafe_state = {
        "schema_version": 1,
        "id": "../outside",
        "name": "invalid",
        "provider": "mock",
        "scene": {"objects": {}},
        "metadata": {},
        "step": 0,
    }
    with pytest.raises(WorldStateError, match="file-safe identifier"):
        forge.import_world(json.dumps(unsafe_state))

    malformed_object_state = {
        "schema_version": 1,
        "id": "bad_object_world",
        "name": "invalid",
        "provider": "mock",
        "scene": {"objects": {"cube-1": {"id": "cube-1", "name": "cube"}}},
        "metadata": {},
        "step": 0,
    }
    with pytest.raises(WorldStateError, match="scene object 'cube-1' is invalid"):
        forge.import_world(json.dumps(malformed_object_state))

    with pytest.raises(WorldForgeError, match="file-safe identifier"):
        forge.load_world("../outside")

    broken_world_path = tmp_path / "broken.json"
    broken_world_path.write_text('{"state": "not-a-world"}', encoding="utf-8")

    with pytest.raises(WorldStateError, match="World file"):
        forge.load_world("broken")


def test_world_import_rejects_malformed_history_entries(tmp_path) -> None:
    forge = WorldForge(state_dir=tmp_path)
    valid_history_state = {
        "schema_version": 1,
        "id": "world_history",
        "name": "history",
        "provider": "mock",
        "scene": {"objects": {}},
        "metadata": {},
        "step": 0,
    }
    base_state = {
        **valid_history_state,
        "step": 1,
        "history": [
            {
                "step": 0,
                "state": valid_history_state,
                "summary": "world initialized",
                "action_json": None,
            }
        ],
    }

    restored = forge.import_world(json.dumps(base_state))
    assert restored.history_length == 1

    malformed_cases = [
        (
            {**base_state, "history": ["not-an-entry"]},
            "history\\[0\\] must be a JSON object",
        ),
        (
            {
                **base_state,
                "history": [{**base_state["history"][0], "step": -1}],
            },
            "HistoryEntry step",
        ),
        (
            {
                **base_state,
                "history": [{**base_state["history"][0], "step": 2}],
            },
            "step must not be greater than current step",
        ),
        (
            {
                **base_state,
                "history": [{**base_state["history"][0], "summary": ""}],
            },
            "summary",
        ),
        (
            {
                **base_state,
                "history": [{**base_state["history"][0], "action_json": "{broken"}],
            },
            "action_json",
        ),
        (
            {
                **base_state,
                "history": [
                    {
                        **base_state["history"][0],
                        "state": {**valid_history_state, "id": "../bad"},
                    }
                ],
            },
            "invalid state",
        ),
    ]

    for payload, message in malformed_cases:
        with pytest.raises(WorldStateError, match=message):
            forge.import_world(json.dumps(payload))


def test_world_migration_preview_accepts_current_persisted_and_exported_state(tmp_path) -> None:
    forge = WorldForge(state_dir=tmp_path)
    world = forge.create_world("migration-ok", provider="mock")
    world.add_object(
        SceneObject(
            "cube",
            Position(0.0, 0.5, 0.0),
            BBox(Position(-0.05, 0.45, -0.05), Position(0.05, 0.55, 0.05)),
            id="cube-1",
        )
    )
    world_id = forge.save_world(world)
    persisted_path = tmp_path / f"{world_id}.json"
    before = persisted_path.read_text(encoding="utf-8")

    report = preview_world_migration_from_world_id(world_id, state_dir=tmp_path)

    assert report["status"] == "passed"
    assert report["safe_to_attach"] is True
    assert report["read_only"] is True
    assert report["can_apply_safely"] is True
    assert report["schema"]["world_schema_version"] == 1
    assert report["counts"] == {
        "required_change_count": 0,
        "invalid_field_count": 0,
        "unsafe_id_count": 0,
        "bounding_box_correction_count": 0,
        "blocking_issue_count": 0,
    }
    assert persisted_path.read_text(encoding="utf-8") == before

    exported_path = tmp_path / "exported-world.json"
    exported_path.write_text(forge.export_world(world_id), encoding="utf-8")
    exported = preview_world_migration_from_path(exported_path)

    assert exported["status"] == "passed"
    assert exported["source"]["payload_kind"] == "exported-json"
    assert exported["schema"]["export_schema_version"] == 1
    assert str(tmp_path) not in json.dumps(exported)


def test_world_migration_preview_reports_legacy_schema_and_position_changes(tmp_path) -> None:
    forge = WorldForge(state_dir=tmp_path)
    world = forge.create_world("legacy-world", provider="mock")
    world.add_object(
        SceneObject(
            "cube",
            Position(0.0, 0.5, 0.0),
            BBox(Position(-0.05, 0.45, -0.05), Position(0.05, 0.55, 0.05)),
            id="cube-1",
        )
    )
    state = world.to_dict()
    state.pop("schema_version")
    state["history"][0]["state"].pop("schema_version")
    object_state = state["scene"]["objects"]["cube-1"]
    object_state["position"] = object_state["pose"]["position"]
    del object_state["pose"]
    original = json.dumps(state, sort_keys=True)

    report = preview_world_migration(
        state,
        source={"kind": "fixture", "label": "<fixture>/legacy-world.json"},
    )

    assert report["status"] == "migration-needed"
    assert report["can_apply_safely"] is True
    assert report["counts"]["invalid_field_count"] == 0
    kinds = {change["kind"] for change in report["required_changes"]}
    assert {"add-schema-version", "promote-position-to-pose"} <= kinds
    assert any(change["path"] == "state.schema_version" for change in report["required_changes"])
    assert any(
        "history[0].state.schema_version" in change["path"] for change in report["required_changes"]
    )
    assert json.dumps(state, sort_keys=True) == original


def test_world_migration_preview_reports_invalid_fields_and_unsafe_ids(tmp_path) -> None:
    forge = WorldForge(state_dir=tmp_path)
    world = forge.create_world("invalid-history", provider="mock")
    state = world.to_dict()
    state["history"][0]["summary"] = ""

    invalid = preview_world_migration(
        state,
        source={"kind": "fixture", "label": "<fixture>/invalid-history.json"},
    )

    assert invalid["status"] == "blocked"
    assert invalid["can_apply_safely"] is False
    assert any("history[0]" in field["message"] for field in invalid["invalid_fields"])

    unsafe_state = world.to_dict()
    unsafe_state["scene"]["objects"]["../cube"] = {
        "id": "../cube",
        "name": "cube",
        "pose": {
            "position": {"x": 0.0, "y": 0.5, "z": 0.0},
            "rotation": {"w": 1, "x": 0, "y": 0, "z": 0},
        },
        "bbox": {
            "min": {"x": -0.05, "y": 0.45, "z": -0.05},
            "max": {"x": 0.05, "y": 0.55, "z": 0.05},
        },
        "is_graspable": False,
        "metadata": {},
    }

    unsafe = preview_world_migration(
        unsafe_state,
        source={"kind": "fixture", "label": "<fixture>/unsafe-object.json"},
    )

    assert unsafe["status"] == "blocked"
    assert unsafe["counts"]["unsafe_id_count"] >= 1
    assert unsafe["unsafe_ids"][0]["value"] == "<unsafe-object-id>"
    assert "../cube" not in json.dumps(unsafe)


def test_world_migration_preview_reports_bbox_correction_without_rewriting(tmp_path) -> None:
    forge = WorldForge(state_dir=tmp_path)
    world = forge.create_world("bbox-preview", provider="mock")
    world.add_object(
        SceneObject(
            "cube",
            Position(0.0, 0.5, 0.0),
            BBox(Position(-0.05, 0.45, -0.05), Position(0.05, 0.55, 0.05)),
            id="cube-1",
        )
    )
    world_id = forge.save_world(world)
    path = tmp_path / f"{world_id}.json"
    state = json.loads(path.read_text(encoding="utf-8"))
    state["scene"]["objects"]["cube-1"]["bbox"] = {
        "min": {"x": 10.0, "y": 10.0, "z": 10.0},
        "max": {"x": 12.0, "y": 12.0, "z": 12.0},
    }
    path.write_text(json.dumps(state), encoding="utf-8")
    before = path.read_text(encoding="utf-8")

    report = preview_world_migration_from_world_id(world_id, state_dir=tmp_path)

    assert report["status"] == "migration-needed"
    assert report["can_apply_safely"] is True
    correction = report["bounding_box_corrections"][0]
    assert correction["object_id"] == "cube-1"
    assert correction["proposed_bbox"]["min"] == {"x": -1.0, "y": -0.5, "z": -1.0}
    assert correction["proposed_bbox"]["max"] == {"x": 1.0, "y": 1.5, "z": 1.0}
    assert path.read_text(encoding="utf-8") == before

    markdown = render_world_migration_preview_markdown(report)
    assert "# WorldForge World Migration Preview" in markdown
    assert "Bounding Box Corrections" in markdown

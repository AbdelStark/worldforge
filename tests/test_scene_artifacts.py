from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from worldforge import (
    SCENE_ARTIFACT_KIND,
    SCENE_ARTIFACT_MAX_METADATA_BYTES,
    SCENE_ARTIFACT_SCHEMA_VERSION,
    WorldForgeError,
    validate_scene_artifact,
)

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "scene_artifacts"


def _fixture(name: str) -> dict[str, Any]:
    return json.loads((FIXTURE_DIR / name).read_text(encoding="utf-8"))


def test_valid_scene_artifact_fixture_passes_contract() -> None:
    artifact = validate_scene_artifact(_fixture("valid_minimal_scene.json"))

    assert artifact["schema_version"] == SCENE_ARTIFACT_SCHEMA_VERSION
    assert artifact["kind"] == SCENE_ARTIFACT_KIND
    assert artifact["capability"] == "generate"
    assert artifact["assets"][0]["uri"] == "artifacts/block-1.gltf"
    assert artifact["provenance"]["limitations"] == [
        "fixture-only artifact",
        "does not certify physical validity",
    ]


@pytest.mark.parametrize(
    ("fixture_name", "match"),
    [
        ("invalid_malformed_transform.json", "rotation_quat"),
        ("invalid_unit.json", "units"),
        ("invalid_unsafe_asset_reference.json", "query strings"),
        ("invalid_non_finite_transform.json", "finite number"),
        ("invalid_oversized_metadata.json", f"{SCENE_ARTIFACT_MAX_METADATA_BYTES} bytes"),
    ],
)
def test_invalid_scene_artifact_fixtures_fail_with_actionable_errors(
    fixture_name: str,
    match: str,
) -> None:
    with pytest.raises(WorldForgeError, match=match):
        validate_scene_artifact(_fixture(fixture_name))


def test_scene_artifact_rejects_tuple_shaped_and_object_metadata() -> None:
    artifact = _fixture("valid_minimal_scene.json")
    artifact["metadata"] = {"shape": (1, 2, 3)}

    with pytest.raises(WorldForgeError, match="JSON-compatible"):
        validate_scene_artifact(artifact)

    artifact = _fixture("valid_minimal_scene.json")
    artifact["objects"][0]["metadata"] = {"runtime": object()}

    with pytest.raises(WorldForgeError, match="JSON-compatible"):
        validate_scene_artifact(artifact)


def test_scene_artifact_rejects_secret_like_metadata_keys() -> None:
    artifact = _fixture("valid_minimal_scene.json")
    artifact["metadata"] = {"api_token": "redacted-but-wrong-place"}

    with pytest.raises(WorldForgeError, match="secret-like"):
        validate_scene_artifact(artifact)

    artifact = _fixture("valid_minimal_scene.json")
    artifact["assets"][0]["metadata"] = {"nested": [{"signed_url": "https://example.test/a"}]}

    with pytest.raises(WorldForgeError, match="signed_url"):
        validate_scene_artifact(artifact)


@pytest.mark.parametrize(
    "uri",
    [
        "/tmp/worldforge/mesh.gltf",
        "~/worldforge/mesh.gltf",
        "file:///tmp/worldforge/mesh.gltf",
        "http://localhost:8000/mesh.gltf",
        "http://127.0.0.1:8000/mesh.gltf",
    ],
)
def test_scene_artifact_rejects_host_local_paths_unless_marked_local_only(uri: str) -> None:
    artifact = _fixture("valid_minimal_scene.json")
    artifact["assets"][0]["uri"] = uri
    artifact["assets"][0]["local_only"] = False

    with pytest.raises(WorldForgeError, match="local"):
        validate_scene_artifact(artifact)

    artifact["assets"][0]["local_only"] = True
    validate_scene_artifact(artifact)


def test_scene_artifact_rejects_path_traversal_and_public_http() -> None:
    artifact = _fixture("valid_minimal_scene.json")
    artifact["assets"][0]["uri"] = "../mesh.gltf"

    with pytest.raises(WorldForgeError, match="path traversal"):
        validate_scene_artifact(artifact)

    artifact = _fixture("valid_minimal_scene.json")
    artifact["assets"][0]["uri"] = "http://assets.example.test/mesh.gltf"

    with pytest.raises(WorldForgeError, match="must use https"):
        validate_scene_artifact(artifact)


def test_scene_artifact_rejects_incoherent_geometry_and_references() -> None:
    artifact = _fixture("valid_minimal_scene.json")
    artifact["coordinate_frame"]["forward_axis"] = "z"

    with pytest.raises(WorldForgeError, match="must differ"):
        validate_scene_artifact(artifact)

    artifact = _fixture("valid_minimal_scene.json")
    artifact["objects"][0]["bbox"]["min"] = [1.0, 0.0, 0.0]

    with pytest.raises(WorldForgeError, match="min coordinates"):
        validate_scene_artifact(artifact)

    artifact = _fixture("valid_minimal_scene.json")
    artifact["objects"].append(dict(artifact["objects"][0]))

    with pytest.raises(WorldForgeError, match="unique"):
        validate_scene_artifact(artifact)


def test_scene_artifact_public_exports_are_lazy() -> None:
    import worldforge

    assert worldforge.SCENE_ARTIFACT_KIND == SCENE_ARTIFACT_KIND
    assert worldforge.validate_scene_artifact is validate_scene_artifact

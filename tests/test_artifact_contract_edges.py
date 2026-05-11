from __future__ import annotations

import hashlib
import importlib
import json
import sys
from pathlib import Path

import pytest

from worldforge import BBox, Position, ProviderCapabilities, SceneObject
from worldforge.config_profiles import (
    CONFIG_PROFILE_SCHEMA_VERSION,
    load_config_profile,
    parse_config_profile,
    validate_config_profile_provenance,
)
from worldforge.dataset_manifests import (
    DATASET_MANIFEST_SCHEMA_VERSION,
    dataset_manifest_reference,
    dataset_manifest_references,
    load_dataset_manifest,
    parse_dataset_manifest,
)
from worldforge.framework import SCHEMA_VERSION
from worldforge.models import ProviderHealth, WorldForgeError
from worldforge.provider_contracts import (
    ProviderContractCheck,
    load_json_contract_input,
    provider_from_factory_path,
    run_provider_contract,
)
from worldforge.providers import BaseProvider, PredictionPayload, ProviderProfileSpec
from worldforge.providers.runtime_manifest import (
    RuntimeAssetManifest,
    load_runtime_manifest,
    missing_optional_dependency_detail,
    validate_runtime_asset_manifest,
)
from worldforge.report_renderers import (
    ReportRenderer,
    ReportRenderResult,
    get_report_renderer,
    register_report_renderer,
    render_report_artifact,
)
from worldforge.world_migration_preview import (
    preview_world_migration,
    preview_world_migration_from_path,
    preview_world_migration_from_world_id,
    render_world_migration_preview_markdown,
)


class _RemotePredictProvider(BaseProvider):
    def __init__(self) -> None:
        super().__init__(
            name="remote-skip",
            capabilities=ProviderCapabilities(predict=True),
            profile=ProviderProfileSpec(
                description="Remote skip coverage provider",
                is_local=False,
                deterministic=False,
                requires_credentials=False,
            ),
        )

    def configured(self) -> bool:
        return True

    def health(self) -> ProviderHealth:
        return ProviderHealth(name=self.name, healthy=True, latency_ms=0.1, details="ready")

    def predict(self, world_state, action, steps) -> PredictionPayload:  # pragma: no cover
        raise AssertionError("remote provider should be skipped without --live")


def _valid_profile() -> dict[str, object]:
    return {
        "schema_version": CONFIG_PROFILE_SCHEMA_VERSION,
        "name": "safe",
        "provider": "mock",
        "operation": "predict",
    }


def _digest(path: Path) -> str:
    return f"sha256:{hashlib.sha256(path.read_bytes()).hexdigest()}"


def _manifest_payload(entry: dict[str, object]) -> dict[str, object]:
    return {
        "schema_version": DATASET_MANIFEST_SCHEMA_VERSION,
        "id": "fixture-manifest",
        "name": "Fixture Manifest",
        "description": "Coverage fixture manifest",
        "license": "MIT",
        "provenance": {
            "source": "test",
            "version": "1",
            "owner": "tests",
        },
        "privacy": {
            "classification": "public",
            "contains_personal_data": False,
        },
        "safety": {
            "reviewed": True,
            "contains_sensitive_capability_data": False,
            "contains_robot_logs": False,
        },
        "host_acquisition_steps": ["Use checkout fixture."],
        "entries": [entry],
    }


def test_config_profile_edge_cases_cover_invalid_inputs(tmp_path: Path) -> None:
    profile = parse_config_profile(
        {
            **_valid_profile(),
            "providers": ["mock", "runway"],
            "provider": None,
            "operations": ["predict", "generate"],
            "operation": None,
            "workspace_dir": ".worldforge/work",
            "output_format": "html",
            "timeout_preset": "remote",
            "retry_preset": "patient",
            "runtime_cache_roots": {"runway": ".worldforge/cache/runway"},
        },
        source_path=Path("/Users/abdel/profile.json"),
    )
    assert profile.source == "profile:profile.json"
    assert profile.to_provenance()["sha256"].startswith("sha256:")

    toml_profile = tmp_path / "profile.toml"
    toml_profile.write_text(
        "\n".join(
            [
                "schema_version = 1",
                'name = "toml-profile"',
                'provider = "mock"',
                'state_dir = ".worldforge/worlds"',
            ]
        ),
        encoding="utf-8",
    )
    assert load_config_profile(toml_profile).name == "toml-profile"

    invalid_json = tmp_path / "bad.json"
    invalid_json.write_text("{", encoding="utf-8")
    with pytest.raises(WorldForgeError, match="valid JSON or TOML"):
        load_config_profile(invalid_json)
    non_object = tmp_path / "non-object.json"
    non_object.write_text("[1]", encoding="utf-8")
    with pytest.raises(WorldForgeError, match="must contain"):
        load_config_profile(non_object)
    missing_path = tmp_path / "missing.json"
    with pytest.raises(WorldForgeError, match="Failed to read"):
        load_config_profile(missing_path)
    with pytest.raises(TypeError):
        parse_config_profile([1])  # type: ignore[arg-type]

    for payload, match in (
        ({**_valid_profile(), "unknown": True}, "unsupported keys"),
        ({**_valid_profile(), "schema_version": 2}, "schema_version"),
        ({**_valid_profile(), "name": "bad/name"}, "letters, numbers"),
        ({**_valid_profile(), "sha256": "bad"}, "unsupported keys"),
        ({**_valid_profile(), "provider": "mock", "providers": ["mock"]}, "cannot set both"),
        ({**_valid_profile(), "provider": None, "providers": ["mock", 1]}, "string list"),
        ({**_valid_profile(), "output_format": "pdf"}, "must be one of"),
        ({**_valid_profile(), "runtime_cache_roots": []}, "must be an object"),
        (
            {**_valid_profile(), "runtime_cache_roots": {"bad?provider": ".worldforge/cache"}},
            "signed URLs or query strings",
        ),
        ({**_valid_profile(), "state_dir": ".env"}, "env files"),
        ({**_valid_profile(), "workspace_dir": "https://example.test/a"}, "relative"),
        ({**_valid_profile(), "retry_preset": "https://e.test/a?token=x"}, "secret material"),
    ):
        with pytest.raises(WorldForgeError, match=match):
            parse_config_profile(payload)  # type: ignore[arg-type]

    valid_provenance = {
        "schema_version": CONFIG_PROFILE_SCHEMA_VERSION,
        "name": "safe",
        "source": "profile:safe.json",
        "sha256": "sha256:" + "1" * 64,
        "providers": ["mock"],
        "operations": ["predict"],
    }
    assert validate_config_profile_provenance(valid_provenance)["providers"] == ["mock"]
    for payload, match in (
        ({**valid_provenance, "unknown": True}, "unsupported keys"),
        ({**valid_provenance, "schema_version": 2}, "schema_version"),
        ({**valid_provenance, "source": "https://e.test/a?token=x"}, "secret material"),
        ({**valid_provenance, "sha256": "sha256:" + "A" * 64}, "sha256"),
    ):
        with pytest.raises(WorldForgeError, match=match):
            validate_config_profile_provenance(payload)


def test_dataset_manifest_edge_cases_cover_references_and_rejections(tmp_path: Path) -> None:
    fixture = tmp_path / "fixture.json"
    fixture.write_text('{"ok": true}\n', encoding="utf-8")
    manifest_payload = _manifest_payload(
        {
            "id": "local",
            "kind": "local-fixture",
            "description": "Local fixture",
            "sha256": _digest(fixture),
            "path": "fixture.json",
            "license": "MIT",
            "metadata": {"rows": 1},
        }
    )
    manifest = parse_dataset_manifest(manifest_payload, root=tmp_path)
    assert manifest.entry_count == 1
    assert manifest.to_reference(path=tmp_path / "manifest.json", root=tmp_path)["path"] == (
        "manifest.json"
    )
    assert (
        manifest.to_reference(path=Path("/tmp/outside.json"), root=tmp_path)["local_only"] is True
    )
    assert "entries" not in dataset_manifest_reference(manifest)

    manifest_file = tmp_path / "manifest.json"
    manifest_file.write_text(manifest.to_json(), encoding="utf-8")
    loaded_reference = dataset_manifest_reference(str(manifest_file), root=tmp_path)
    assert loaded_reference["id"] == "fixture-manifest"
    assert dataset_manifest_references(None) == ()
    with pytest.raises(WorldForgeError, match="sequence"):
        dataset_manifest_references("not-a-sequence")

    remote = _manifest_payload(
        {
            "id": "remote",
            "kind": "remote-reference",
            "description": "Remote fixture",
            "sha256": "sha256:" + "2" * 64,
            "uri": "https://example.test/fixture.json",
        }
    )
    assert parse_dataset_manifest(json.dumps(remote), root=tmp_path).entries[0].uri

    host_asset = _manifest_payload(
        {
            "id": "asset",
            "kind": "host-asset",
            "description": "Host asset",
            "sha256": "sha256:" + "3" * 64,
            "asset_id": "host:asset",
        }
    )
    assert parse_dataset_manifest(host_asset, root=tmp_path).entries[0].asset_id == "host:asset"

    invalid_payloads = [
        ("[]", "must be a JSON object"),
        ({**manifest_payload, "schema_version": 2}, "schema_version"),
        ({**manifest_payload, "entries": []}, "entries"),
        (
            _manifest_payload(
                {
                    "id": "bad",
                    "kind": "unknown",
                    "description": "Bad",
                    "sha256": "sha256:" + "4" * 64,
                }
            ),
            "kind must be one of",
        ),
        (
            _manifest_payload(
                {
                    "id": "bad",
                    "kind": "local-fixture",
                    "description": "Bad",
                    "sha256": "sha256:" + "4" * 64,
                    "path": "missing.json",
                }
            ),
            "does not exist",
        ),
        (
            _manifest_payload(
                {
                    "id": "bad",
                    "kind": "local-fixture",
                    "description": "Bad",
                    "sha256": "sha256:" + "4" * 64,
                    "path": "fixture.exe",
                }
            ),
            "safe text or JSON",
        ),
        (
            _manifest_payload(
                {
                    "id": "bad",
                    "kind": "local-fixture",
                    "description": "Bad",
                    "sha256": "sha256:" + "4" * 64,
                    "path": "fixture.json",
                }
            ),
            "does not match",
        ),
        (
            _manifest_payload(
                {
                    "id": "bad",
                    "kind": "remote-reference",
                    "description": "Bad",
                    "sha256": "sha256:" + "4" * 64,
                    "uri": "http://example.test/fixture.json",
                }
            ),
            "stable https",
        ),
        (
            _manifest_payload(
                {
                    "id": "bad",
                    "kind": "remote-reference",
                    "description": "Bad",
                    "sha256": "sha256:" + "4" * 64,
                    "uri": "https://example.test/fixture.json?token=x",
                }
            ),
            "query strings",
        ),
        (
            _manifest_payload(
                {
                    "id": "asset",
                    "kind": "host-asset",
                    "description": "Bad",
                    "sha256": "sha256:" + "5" * 64,
                    "asset_id": "asset",
                    "path": "fixture.json",
                }
            ),
            "host-owned assets",
        ),
        ({**manifest_payload, "privacy": {"classification": "private"}}, "classification"),
        (
            {
                **manifest_payload,
                "safety": {"reviewed": True, "contains_sensitive_capability_data": False},
            },
            "contains_robot_logs",
        ),
        ({**manifest_payload, "host_acquisition_steps": []}, "non-empty list"),
    ]
    for payload, match in invalid_payloads:
        with pytest.raises(WorldForgeError, match=match):
            parse_dataset_manifest(payload, root=tmp_path)  # type: ignore[arg-type]

    invalid_file = tmp_path / "invalid.json"
    invalid_file.write_text("{", encoding="utf-8")
    with pytest.raises(WorldForgeError, match="invalid JSON"):
        load_dataset_manifest(invalid_file, root=tmp_path)


def test_provider_contract_edge_cases_cover_factory_and_evidence(tmp_path: Path) -> None:
    with pytest.raises(WorldForgeError, match="status must be one of"):
        ProviderContractCheck("bad", "unknown", "detail", "next")

    evidence = run_provider_contract(_RemotePredictProvider(), registered=True)
    payload = evidence.to_dict()
    assert payload["status"] == "passed"
    assert payload["skipped_count"] == 1
    assert "--live" in payload["next_steps"][0]
    assert "Provider Contract Evidence" in evidence.to_markdown()
    assert json.loads(evidence.to_json())["provider"] == "remote-skip"

    assert load_json_contract_input(None, name="score-info") is None
    missing = tmp_path / "missing.json"
    with pytest.raises(WorldForgeError, match="Failed to read"):
        load_json_contract_input(missing, name="score-info")
    invalid = tmp_path / "invalid.json"
    invalid.write_text("{", encoding="utf-8")
    with pytest.raises(WorldForgeError, match="invalid JSON"):
        load_json_contract_input(invalid, name="score-info")

    module_path = tmp_path / "factory_module.py"
    module_path.write_text(
        "\n".join(
            [
                "from worldforge import ProviderCapabilities",
                "from worldforge.providers import BaseProvider, ProviderProfileSpec",
                "class FactoryProvider(BaseProvider):",
                "    def __init__(self, event_handler=None):",
                "        super().__init__('factory-provider', capabilities=ProviderCapabilities(),",
                "            profile=ProviderProfileSpec(description='factory'),",
                "            event_handler=event_handler)",
                "def keyword_factory(*, event_handler=None):",
                "    return FactoryProvider(event_handler)",
                "def positional_factory(event_handler):",
                "    return FactoryProvider(event_handler)",
                "def noarg_factory():",
                "    return FactoryProvider()",
                "def not_provider():",
                "    return object()",
                "def raises(*, event_handler=None):",
                "    raise RuntimeError('token secret in /Users/example/runtime')",
                "not_callable = 1",
            ]
        ),
        encoding="utf-8",
    )
    sys.path.insert(0, str(tmp_path))
    importlib.invalidate_caches()
    try:
        assert (
            provider_from_factory_path("factory_module:keyword_factory").name == "factory-provider"
        )
        assert provider_from_factory_path("factory_module:positional_factory").name == (
            "factory-provider"
        )
        assert provider_from_factory_path("factory_module:noarg_factory").name == "factory-provider"
        for factory_path, match in (
            ("badpath", "module:factory"),
            ("missing_module:factory", "could not be imported"),
            ("factory_module:missing.attr", "missing attribute"),
            ("factory_module:not_callable", "callable"),
            ("factory_module:not_provider", "expected BaseProvider"),
            ("factory_module:raises", r"\[redacted\]"),
        ):
            with pytest.raises(WorldForgeError, match=match):
                provider_from_factory_path(factory_path)
    finally:
        sys.path.remove(str(tmp_path))
        sys.modules.pop("factory_module", None)


def test_runtime_asset_manifest_edges_cover_local_only_and_validation() -> None:
    asset = RuntimeAssetManifest(
        asset_id="weights",
        provider="leworldmodel",
        asset_kind="checkpoint",
        path="/Users/example/.cache/weights.ckpt",
        source="huggingface:fixture",
        revision="main",
        checksum="sha256:" + "1" * 64,
        size_bytes=8,
        cache_root="/Users/example/.cache",
        exists=False,
        rebuild_command="worldforge-build-leworldmodel-checkpoint --help",
    )
    reference = asset.to_reference()
    assert "path" not in reference
    local = asset.to_dict(include_local_fields=True)
    assert local["path"].startswith("/Users/example")
    assert local["safe_to_attach"] is False

    attachable = RuntimeAssetManifest(
        asset_id="tiny",
        provider="fixture",
        asset_kind="json",
        path="artifacts/tiny.json",
        source="repo",
        cache_root="artifacts/cache",
        local_only=False,
    )
    assert attachable.to_reference()["path"] == "artifacts/tiny.json"

    for kwargs, match in (
        ({"checksum": "bad"}, "checksum"),
        ({"size_bytes": -1}, "greater than or equal to 0"),
        ({"local_only": "yes"}, "local_only"),
        ({"exists": "yes"}, "exists"),
        ({"source": "https://example.test/a?token=x"}, "secret-like material"),
        ({"local_only": False, "path": "/Users/example/model.ckpt"}, "host-local"),
    ):
        with pytest.raises(WorldForgeError, match=match):
            RuntimeAssetManifest(
                asset_id="bad",
                provider="fixture",
                asset_kind="checkpoint",
                path=kwargs.pop("path", "artifacts/model.ckpt"),
                source=kwargs.pop("source", "repo"),
                **kwargs,
            )

    base = {
        "schema_version": 1,
        "asset_id": "asset",
        "provider": "fixture",
        "asset_kind": "json",
        "source": "repo",
        "local_only": True,
        "safe_to_attach": True,
    }
    for payload, match in (
        ({**base, "schema_version": 2}, "schema_version"),
        ({**base, "local_only": "yes"}, "local_only"),
        ({**base, "safe_to_attach": "yes"}, "safe_to_attach"),
        ({**base, "safe_to_attach": False}, "safe_to_attach"),
        ({**base, "path": "artifacts/raw.json"}, "omit path"),
        ({**base, "checksum": "bad"}, "checksum"),
        ({**base, "exists": "yes"}, "exists"),
    ):
        with pytest.raises(WorldForgeError, match=match):
            validate_runtime_asset_manifest(payload)

    assert (
        missing_optional_dependency_detail(
            "runway",
            "not-installed",
        )
        == "missing optional dependency not-installed"
    )
    with pytest.raises(WorldForgeError, match="not found"):
        load_runtime_manifest("not-a-provider")


def test_report_renderer_edges_cover_registration_and_result_validation() -> None:
    with pytest.raises(WorldForgeError, match="content"):
        ReportRenderResult(1, "text/plain", True)  # type: ignore[arg-type]
    with pytest.raises(WorldForgeError, match="media_type"):
        ReportRenderResult("ok", "plain", True)
    with pytest.raises(WorldForgeError, match="safe_to_attach"):
        ReportRenderResult("ok", "text/plain", "yes")  # type: ignore[arg-type]
    with pytest.raises(WorldForgeError, match="local_only"):
        ReportRenderResult("ok", "text/plain", True, local_only="no")  # type: ignore[arg-type]
    with pytest.raises(WorldForgeError, match="secret-like"):
        ReportRenderResult("token=secret", "text/plain", True, local_only=False)

    invalid_renderers = [
        {"artifact_family": "Bad"},
        {"output_format": "Bad"},
        {"supported_schemas": ()},
        {"safe_to_attach": "yes"},
        {"render": "no"},
        {"description": 1},
    ]
    for override in invalid_renderers:
        kwargs = {
            "artifact_family": "edge",
            "output_format": "plain",
            "media_type": "text/plain",
            "supported_schemas": ("edge:1",),
            "safe_to_attach": True,
            "render": lambda payload: "ok",
            "description": "",
        }
        kwargs.update(override)
        with pytest.raises(WorldForgeError):
            ReportRenderer(**kwargs)  # type: ignore[arg-type]

    renderer = ReportRenderer(
        artifact_family="edge",
        output_format="plain",
        media_type="text/plain",
        supported_schemas=("edge:1",),
        safe_to_attach=True,
        render=lambda payload: f"ok {payload['kind']}",
    )
    register_report_renderer(renderer, replace=True)
    register_report_renderer(renderer, replace=True)
    assert render_report_artifact("edge", "plain", {"kind": "artifact"}).content == "ok artifact"

    with pytest.raises(WorldForgeError, match="No report renderer"):
        get_report_renderer("edge", "missing")
    bad_return = ReportRenderer(
        artifact_family="edge",
        output_format="bad-return",
        media_type="text/plain",
        supported_schemas=("edge:1",),
        safe_to_attach=True,
        render=lambda payload: {"bad": True},
    )
    register_report_renderer(bad_return, replace=True)
    with pytest.raises(WorldForgeError, match="must return"):
        render_report_artifact("edge", "bad-return", {"kind": "artifact"})

    bad_media = ReportRenderer(
        artifact_family="edge",
        output_format="bad-media",
        media_type="text/plain",
        supported_schemas=("edge:1",),
        safe_to_attach=True,
        render=lambda payload: ReportRenderResult("ok", "text/html", True, local_only=False),
    )
    register_report_renderer(bad_media, replace=True)
    with pytest.raises(WorldForgeError, match="media_type"):
        render_report_artifact("edge", "bad-media", {"kind": "artifact"})


def test_world_migration_preview_edges_cover_blockers_and_markdown(tmp_path: Path) -> None:
    non_object = preview_world_migration(["bad"])
    assert non_object["status"] == "blocked"

    export_bad_state = preview_world_migration({"schema_version": 1, "state": []})
    assert export_bad_state["source"]["kind"] == "exported-json"

    obj = SceneObject(
        id="bad/object",
        name="cube",
        position=Position(3, 0, 0),
        bbox=BBox(min=Position(0, 0, 0), max=Position(1, 1, 1)),
    ).to_dict()
    obj["position"] = obj.pop("pose")["position"]
    world_state = {
        "schema_version": 0,
        "id": "world/unsafe",
        "name": "Lab",
        "step": 0,
        "scene": {"objects": {"bad/object": obj}},
        "history": [
            {
                "step": 0,
                "summary": "init",
                "state": {
                    "schema_version": 0,
                    "id": "nested/token",
                    "name": "Nested",
                    "step": 0,
                    "scene": {"objects": {}},
                    "history": [],
                },
            }
        ],
    }
    report = preview_world_migration(
        world_state,
        source={"kind": "world-id", "label": "bad.json"},
        expected_world_id="expected",
    )
    assert report["status"] == "blocked"
    assert report["counts"]["required_change_count"] >= 1
    assert report["counts"]["unsafe_id_count"] >= 1
    assert report["counts"]["bounding_box_correction_count"] == 1
    assert "<unsafe-id>" in json.dumps(report)
    markdown = render_world_migration_preview_markdown(report)
    assert "WorldForge World Migration Preview" in markdown
    assert "Unsafe IDs" in markdown

    unsafe_id = preview_world_migration_from_world_id("../bad", state_dir=tmp_path)
    assert unsafe_id["status"] == "blocked"
    missing_world = preview_world_migration_from_world_id("missing", state_dir=tmp_path)
    assert missing_world["invalid_fields"]

    invalid_json = tmp_path / "not-json.json"
    invalid_json.write_text("{", encoding="utf-8")
    from_path = preview_world_migration_from_path(invalid_json)
    assert from_path["status"] == "blocked"
    assert from_path["source"]["label"] == "<input>/not-json.json"

    safe_state = {
        "schema_version": SCHEMA_VERSION,
        "id": "safe",
        "name": "Safe",
        "provider": "mock",
        "step": 0,
        "scene": {"objects": {}},
        "history": [],
    }
    assert preview_world_migration(safe_state)["status"] == "passed"

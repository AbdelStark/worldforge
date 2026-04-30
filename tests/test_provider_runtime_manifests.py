from __future__ import annotations

import json
from importlib import resources

import pytest

from worldforge.models import WorldForgeError
from worldforge.providers.catalog import PROVIDER_CATALOG
from worldforge.providers.gr00t import GrootPolicyClientProvider
from worldforge.providers.lerobot import LeRobotPolicyProvider
from worldforge.providers.leworldmodel import LeWorldModelProvider
from worldforge.providers.runtime_manifest import (
    MANIFEST_PACKAGE,
    ProviderRuntimeManifest,
    load_runtime_manifests,
    missing_optional_dependency_detail,
)

EXPECTED_MANIFEST_PROVIDERS = ("cosmos", "gr00t", "lerobot", "leworldmodel", "runway")


def test_runtime_manifests_cover_real_optional_providers() -> None:
    manifests = load_runtime_manifests()
    manifest_names = tuple(manifest.provider for manifest in manifests)

    assert manifest_names == EXPECTED_MANIFEST_PROVIDERS
    catalog = {entry.name: entry.create().profile() for entry in PROVIDER_CATALOG}
    for manifest in manifests:
        profile = catalog[manifest.provider]
        assert manifest.schema_version == 1
        assert set(manifest.capabilities) <= set(profile.capabilities.enabled_names())
        assert manifest.docs_path == f"docs/src/providers/{manifest.provider}.md"
        assert manifest.minimum_smoke_command
        assert manifest.expected_success_signal
        assert manifest.host_owned_artifacts


def test_runtime_manifest_json_files_validate_without_optional_dependencies() -> None:
    for manifest_file in sorted(resources.files(MANIFEST_PACKAGE).iterdir()):
        if not manifest_file.name.endswith(".json"):
            continue
        payload = json.loads(manifest_file.read_text(encoding="utf-8"))
        assert isinstance(payload, dict)
        manifest = ProviderRuntimeManifest.from_json(payload, source=manifest_file.name)
        assert manifest.provider == manifest_file.name.removesuffix(".json")


def test_runtime_manifest_validation_rejects_weak_records() -> None:
    payload = {
        "schema_version": 1,
        "provider": "example",
        "capabilities": ["score"],
        "optional_dependencies": ["runtime"],
        "required_env_vars": ["EXAMPLE_MODEL"],
        "optional_env_vars": [],
        "default_model": "example/model",
        "device_support": ["cpu"],
        "host_owned_artifacts": ["checkpoint"],
        "minimum_smoke_command": "",
        "expected_success_signal": "scores returned",
        "setup_hint": "install runtime",
        "docs_path": "docs/src/providers/example.md",
    }

    with pytest.raises(WorldForgeError, match="minimum_smoke_command"):
        ProviderRuntimeManifest.from_json(payload, source="example.json")


def test_manifest_backed_dependency_health_messages_are_actionable(monkeypatch) -> None:
    monkeypatch.setenv("LEWORLDMODEL_POLICY", "pusht/lewm")
    health = LeWorldModelProvider().health()

    assert health.healthy is False
    assert "missing optional dependency torch" in health.details
    assert "minimum smoke:" in health.details
    assert "scripts/lewm-real" in health.details


def test_manifest_backed_configuration_health_messages_include_docs(monkeypatch) -> None:
    for name in ("LEWORLDMODEL_POLICY", "LEWM_POLICY", "LEROBOT_POLICY_PATH", "LEROBOT_POLICY"):
        monkeypatch.delenv(name, raising=False)

    leworldmodel = LeWorldModelProvider().health()
    lerobot = LeRobotPolicyProvider().health()
    gr00t = GrootPolicyClientProvider().health()

    assert "docs/src/providers/leworldmodel.md" in leworldmodel.details
    assert "docs/src/providers/lerobot.md" in lerobot.details
    assert "docs/src/providers/gr00t.md" in gr00t.details


def test_manifest_dependency_detail_falls_back_for_unknown_dependency() -> None:
    assert (
        missing_optional_dependency_detail("lerobot", "not-in-manifest")
        == "missing optional dependency not-in-manifest"
    )

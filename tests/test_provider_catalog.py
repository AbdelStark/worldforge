from __future__ import annotations

import pytest

from worldforge import WorldForge
from worldforge.providers.catalog import (
    PROVIDER_CATALOG,
    PROVIDER_PROMOTION_STATUSES,
    create_known_providers,
)


def test_provider_catalog_names_are_unique_and_explicit() -> None:
    names = [entry.name for entry in PROVIDER_CATALOG]

    assert len(names) == len(set(names))
    assert names == [
        "mock",
        "cosmos",
        "cosmos-policy",
        "runway",
        "leworldmodel",
        "gr00t",
        "lerobot",
        "jepa",
        "genie",
    ]
    assert [entry.name for entry in PROVIDER_CATALOG if entry.always_register] == ["mock"]


def test_provider_catalog_instantiates_known_provider_profiles() -> None:
    providers = create_known_providers()
    profiles = {provider.name: provider.profile() for provider in providers}

    assert profiles["mock"].implementation_status == "stable"
    assert profiles["cosmos-policy"].capabilities.enabled_names() == []
    assert profiles["leworldmodel"].capabilities.score is True
    assert profiles["gr00t"].capabilities.policy is True
    assert profiles["lerobot"].capabilities.policy is True
    assert profiles["jepa"].implementation_status == "experimental"
    assert profiles["jepa"].capabilities.enabled_names() == ["score"]
    assert profiles["genie"].implementation_status == "scaffold"
    assert profiles["genie"].capabilities.enabled_names() == []


def test_provider_catalog_statuses_match_promotion_gate() -> None:
    profiles = {provider.name: provider.profile() for provider in create_known_providers()}

    assert set(PROVIDER_PROMOTION_STATUSES) == {
        "scaffold",
        "experimental",
        "beta",
        "stable",
    }
    assert {name: profile.implementation_status for name, profile in profiles.items()} == {
        "mock": "stable",
        "cosmos": "beta",
        "cosmos-policy": "beta",
        "runway": "beta",
        "leworldmodel": "stable",
        "gr00t": "beta",
        "lerobot": "stable",
        "jepa": "experimental",
        "genie": "scaffold",
    }
    for profile in profiles.values():
        assert profile.implementation_status in PROVIDER_PROMOTION_STATUSES


# Pairs of (canonical_env_var, legacy_alias) that provider auto-registration must continue
# to honour. The legacy aliases are documented in CHANGELOG.md; clearing both names and
# setting only the legacy one proves the fallback path is wired end-to-end.
LEGACY_ENV_ALIAS_CASES = (
    pytest.param(
        "leworldmodel",
        ("LEWORLDMODEL_POLICY", "LEWM_POLICY"),
        "cube/lewm",
        ("score",),
        id="leworldmodel-LEWM_POLICY",
    ),
    pytest.param(
        "runway",
        ("RUNWAYML_API_SECRET", "RUNWAY_API_SECRET"),
        "runway-legacy-secret",
        ("generate", "transfer"),
        id="runway-RUNWAY_API_SECRET",
    ),
    pytest.param(
        "lerobot",
        ("LEROBOT_POLICY_PATH", "LEROBOT_POLICY"),
        "lerobot/act_aloha_sim_transfer_cube_human",
        ("policy",),
        id="lerobot-LEROBOT_POLICY",
    ),
)


@pytest.mark.parametrize(
    ("provider_name", "env_names", "legacy_value", "expected_capabilities"),
    LEGACY_ENV_ALIAS_CASES,
)
def test_legacy_env_alias_triggers_provider_registration(
    tmp_path,
    monkeypatch,
    provider_name: str,
    env_names: tuple[str, str],
    legacy_value: str,
    expected_capabilities: tuple[str, ...],
) -> None:
    canonical, legacy = env_names
    monkeypatch.delenv(canonical, raising=False)
    monkeypatch.delenv(legacy, raising=False)
    monkeypatch.setenv(legacy, legacy_value)

    forge = WorldForge(state_dir=tmp_path)

    assert provider_name in forge.providers()
    capabilities = forge.provider_profile(provider_name).capabilities
    for capability in expected_capabilities:
        assert capabilities.supports(capability), (
            f"{provider_name} registered via {legacy} should advertise {capability}"
        )

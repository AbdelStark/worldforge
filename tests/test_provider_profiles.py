from __future__ import annotations

import pytest

from worldforge import DoctorReport, WorldForge, WorldForgeError


def test_provider_profiles_and_doctor_report_include_known_scaffolds(tmp_path, monkeypatch) -> None:
    for env_var in (
        "COSMOS_BASE_URL",
        "NVIDIA_API_KEY",
        "RUNWAYML_API_SECRET",
        "RUNWAY_API_SECRET",
        "LEWORLDMODEL_POLICY",
        "LEWM_POLICY",
        "LEWORLDMODEL_CACHE_DIR",
        "LEWORLDMODEL_DEVICE",
        "GROOT_POLICY_HOST",
        "GROOT_POLICY_PORT",
        "GROOT_POLICY_TIMEOUT_MS",
        "GROOT_POLICY_API_TOKEN",
        "GROOT_POLICY_STRICT",
        "GROOT_EMBODIMENT_TAG",
        "LEROBOT_POLICY_PATH",
        "LEROBOT_POLICY",
        "LEROBOT_POLICY_TYPE",
        "LEROBOT_DEVICE",
        "LEROBOT_CACHE_DIR",
        "LEROBOT_EMBODIMENT_TAG",
        "JEPA_MODEL_PATH",
        "GENIE_API_KEY",
    ):
        monkeypatch.delenv(env_var, raising=False)

    forge = WorldForge(state_dir=tmp_path)

    registered_profiles = {profile.name: profile for profile in forge.list_provider_profiles()}
    assert registered_profiles["mock"].implementation_status == "stable"
    assert registered_profiles["mock"].deterministic is True
    assert registered_profiles["mock"].requires_credentials is False
    assert registered_profiles["mock"].request_policy is None

    builtin_profiles = {profile.name: profile for profile in forge.builtin_provider_profiles()}
    assert {
        "mock",
        "cosmos",
        "runway",
        "leworldmodel",
        "gr00t",
        "lerobot",
        "jepa",
        "genie",
    } <= set(builtin_profiles)
    assert builtin_profiles["cosmos"].implementation_status == "beta"
    assert builtin_profiles["cosmos"].required_env_vars == ["COSMOS_BASE_URL"]
    assert builtin_profiles["cosmos"].request_policy is not None
    assert builtin_profiles["cosmos"].request_policy.request.retry.max_attempts == 1
    assert builtin_profiles["cosmos"].request_policy.health.retry.max_attempts == 3
    assert builtin_profiles["runway"].required_env_vars == [
        "RUNWAYML_API_SECRET",
        "RUNWAY_API_SECRET",
    ]
    assert builtin_profiles["runway"].request_policy is not None
    assert builtin_profiles["runway"].request_policy.download.retry.max_attempts == 3
    assert builtin_profiles["leworldmodel"].implementation_status == "stable"
    assert builtin_profiles["leworldmodel"].capabilities.score is True
    assert builtin_profiles["leworldmodel"].capabilities.predict is False
    assert builtin_profiles["leworldmodel"].required_env_vars == [
        "LEWORLDMODEL_POLICY",
        "LEWM_POLICY",
    ]
    assert builtin_profiles["gr00t"].implementation_status == "beta"
    assert builtin_profiles["gr00t"].capabilities.policy is True
    assert builtin_profiles["gr00t"].capabilities.predict is False
    assert builtin_profiles["gr00t"].required_env_vars == ["GROOT_POLICY_HOST"]
    assert builtin_profiles["lerobot"].implementation_status == "beta"
    assert builtin_profiles["lerobot"].capabilities.policy is True
    assert builtin_profiles["lerobot"].capabilities.predict is False
    assert builtin_profiles["lerobot"].required_env_vars == [
        "LEROBOT_POLICY_PATH",
        "LEROBOT_POLICY",
    ]
    assert builtin_profiles["jepa"].capabilities.enabled_names() == []
    assert builtin_profiles["genie"].capabilities.enabled_names() == []

    report = forge.doctor()
    assert isinstance(report, DoctorReport)

    provider_statuses = {status.profile.name: status for status in report.providers}
    assert provider_statuses["mock"].registered is True
    assert provider_statuses["mock"].health.healthy is True
    assert provider_statuses["cosmos"].registered is False
    assert provider_statuses["cosmos"].health.healthy is False
    assert any("COSMOS_BASE_URL" in issue for issue in report.issues)

    with pytest.raises(WorldForgeError, match="Unknown provider capability"):
        forge.provider_healths(capability="generation")
    with pytest.raises(WorldForgeError, match="Unknown provider capability"):
        forge.doctor(capability="generation")

from __future__ import annotations

import pytest

from worldforge import (
    DoctorReport,
    ProviderLifecycleResult,
    ReasoningResult,
    WorldForge,
    WorldForgeError,
)
from worldforge.providers import BaseProvider, ProviderError, ProviderProfileSpec


def test_provider_profiles_and_doctor_report_include_known_scaffolds(tmp_path, monkeypatch) -> None:
    for env_var in (
        "COSMOS_BASE_URL",
        "NVIDIA_API_KEY",
        "COSMOS_POLICY_BASE_URL",
        "COSMOS_POLICY_API_TOKEN",
        "COSMOS_POLICY_TIMEOUT_SECONDS",
        "COSMOS_POLICY_EMBODIMENT_TAG",
        "COSMOS_POLICY_MODEL",
        "COSMOS_POLICY_RETURN_ALL_QUERY_RESULTS",
        "COSMOS_POLICY_ALLOW_LOCAL_BASE_URL",
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
        "JEPA_MODEL_NAME",
        "JEPA_MODEL_PATH",
        "JEPA_DEVICE",
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
        "cosmos-policy",
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
    assert builtin_profiles["cosmos-policy"].implementation_status == "beta"
    assert builtin_profiles["cosmos-policy"].capabilities.enabled_names() == []
    assert builtin_profiles["cosmos-policy"].capabilities.predict is False
    assert builtin_profiles["cosmos-policy"].required_env_vars == ["COSMOS_POLICY_BASE_URL"]
    assert builtin_profiles["cosmos-policy"].request_policy is not None
    assert builtin_profiles["cosmos-policy"].request_policy.request.retry.max_attempts == 1
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
    assert builtin_profiles["lerobot"].implementation_status == "stable"
    assert builtin_profiles["lerobot"].capabilities.policy is True
    assert builtin_profiles["lerobot"].capabilities.predict is False
    assert builtin_profiles["lerobot"].required_env_vars == [
        "LEROBOT_POLICY_PATH",
        "LEROBOT_POLICY",
    ]
    assert builtin_profiles["jepa"].implementation_status == "experimental"
    assert builtin_profiles["jepa"].capabilities.enabled_names() == ["score"]
    assert builtin_profiles["jepa"].required_env_vars == ["JEPA_MODEL_NAME"]
    assert builtin_profiles["genie"].capabilities.enabled_names() == []

    report = forge.doctor()
    assert isinstance(report, DoctorReport)

    provider_statuses = {status.profile.name: status for status in report.providers}
    assert provider_statuses["mock"].registered is True
    assert provider_statuses["mock"].health.healthy is True
    assert provider_statuses["cosmos"].registered is False
    assert provider_statuses["cosmos"].health.healthy is False
    assert any("COSMOS_BASE_URL" in issue for issue in report.issues)
    assert provider_statuses["cosmos-policy"].registered is False
    assert provider_statuses["cosmos-policy"].health.healthy is False
    assert any("COSMOS_POLICY_BASE_URL" in issue for issue in report.issues)

    with pytest.raises(WorldForgeError, match="Unknown provider capability"):
        forge.provider_healths(capability="generation")
    with pytest.raises(WorldForgeError, match="Unknown provider capability"):
        forge.doctor(capability="generation")


class _LifecycleReadyReasoner:
    name = "lifecycle-ready"
    profile = ProviderProfileSpec(
        description="Reasoner with lifecycle hooks for diagnostics.",
        implementation_status="experimental",
        deterministic=True,
    )

    def preflight(self) -> ProviderLifecycleResult:
        return ProviderLifecycleResult(
            provider=self.name,
            hook="preflight",
            status="ready",
            ready=True,
            latency_ms=0.1,
            details="runtime reachable",
            evidence={"runtime": "fixture"},
        )

    def warmup(self) -> ProviderLifecycleResult:
        return ProviderLifecycleResult(
            provider=self.name,
            hook="warmup",
            status="ready",
            ready=True,
            latency_ms=0.1,
            details="warm cache prepared",
            evidence={"cache": "prepared"},
        )

    def reason(self, query: str, *, world_state=None) -> ReasoningResult:
        return ReasoningResult(
            provider=self.name,
            answer=f"answer: {query}",
            confidence=0.9,
            evidence=["fixture"],
        )


class _FailingPreflightProvider(BaseProvider):
    def __init__(self) -> None:
        super().__init__(
            "lifecycle-failed",
            profile=ProviderProfileSpec(description="Preflight failure fixture."),
        )

    def preflight(self) -> ProviderLifecycleResult:
        raise ProviderError("dependency probe failed")


class _FailingTeardownProvider(BaseProvider):
    def __init__(self) -> None:
        super().__init__(
            "lifecycle-teardown-failed",
            profile=ProviderProfileSpec(description="Teardown failure fixture."),
        )

    def teardown(self) -> ProviderLifecycleResult:
        raise RuntimeError("socket close failed")


def test_provider_lifecycle_status_covers_noop_ready_skipped_failed_and_teardown(
    tmp_path,
    monkeypatch,
) -> None:
    monkeypatch.delenv("WF_LIFECYCLE_REQUIRED", raising=False)
    forge = WorldForge(state_dir=tmp_path)

    noop = forge.provider_lifecycle_status("mock")
    assert noop.status == "no-op"
    assert noop.ready is True
    assert noop.preflight.evidence == {"configured": True}

    skipped = BaseProvider(
        "lifecycle-skipped",
        profile=ProviderProfileSpec(required_env_vars=("WF_LIFECYCLE_REQUIRED",)),
    )
    forge.register_provider(skipped)
    skipped_status = forge.provider_lifecycle_status("lifecycle-skipped")
    assert skipped_status.status == "skipped"
    assert skipped_status.ready is False
    assert "WF_LIFECYCLE_REQUIRED" in skipped_status.skip_reason

    ready_reasoner = _LifecycleReadyReasoner()
    forge.register_reasoner(ready_reasoner)
    ready_status = forge.provider_lifecycle_status("lifecycle-ready", run_warmup=True)
    assert ready_status.status == "ready"
    assert ready_status.ready is True
    assert ready_status.preflight.evidence == {"runtime": "fixture"}
    assert ready_status.warmup is not None
    assert ready_status.warmup.evidence == {"cache": "prepared"}

    forge.register_provider(_FailingPreflightProvider())
    failed_status = forge.provider_lifecycle_status("lifecycle-failed")
    assert failed_status.status == "failed"
    assert failed_status.ready is False
    assert "dependency probe failed" in failed_status.details

    forge.register_provider(_FailingTeardownProvider())
    teardown_status = forge.provider_lifecycle_status(
        "lifecycle-teardown-failed",
        run_teardown=True,
    )
    assert teardown_status.status == "teardown-failed"
    assert teardown_status.ready is False
    assert teardown_status.teardown is not None
    assert "socket close failed" in teardown_status.teardown.details


def test_doctor_report_includes_lifecycle_readiness_and_skip_reasons(
    tmp_path,
    monkeypatch,
) -> None:
    monkeypatch.delenv("WF_LIFECYCLE_REQUIRED", raising=False)
    forge = WorldForge(state_dir=tmp_path)
    forge.register_provider(
        BaseProvider(
            "lifecycle-skipped",
            profile=ProviderProfileSpec(required_env_vars=("WF_LIFECYCLE_REQUIRED",)),
        )
    )

    report = forge.doctor(registered_only=True)
    payload = report.to_dict()
    statuses = {provider["name"]: provider for provider in payload["providers"]}

    assert statuses["mock"]["lifecycle"]["status"] == "no-op"
    skipped = statuses["lifecycle-skipped"]["lifecycle"]
    assert skipped["status"] == "skipped"
    assert skipped["ready"] is False
    assert "WF_LIFECYCLE_REQUIRED" in skipped["skip_reason"]

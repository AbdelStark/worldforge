from __future__ import annotations

import math

import pytest

from worldforge import (
    ActionScoreResult,
    DoctorReport,
    ProviderDoctorStatus,
    ProviderLifecycleResult,
    ProviderLifecycleStatus,
    WorldForge,
    WorldForgeError,
)
from worldforge.providers import BaseProvider, ProviderError, ProviderProfileSpec
from worldforge.providers.base import build_provider_lifecycle_status


def test_provider_base_reexports_lifecycle_builder() -> None:
    import worldforge.providers.base as base_module
    import worldforge.providers.lifecycle as lifecycle_module

    assert base_module.build_provider_lifecycle_status is (
        lifecycle_module.build_provider_lifecycle_status
    )


def test_worldforge_doctor_facade_delegates_to_diagnostics_helper(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    import worldforge.framework as framework_module

    forge = WorldForge(state_dir=tmp_path)
    expected = DoctorReport(state_dir=str(tmp_path), world_count=0, providers=[], issues=[])
    captured: dict[str, object] = {}

    def fake_doctor_report(
        host: object,
        *,
        capability: str | None,
        registered_only: bool,
    ) -> DoctorReport:
        captured["host"] = host
        captured["capability"] = capability
        captured["registered_only"] = registered_only
        return expected

    monkeypatch.setattr(framework_module, "_doctor_report", fake_doctor_report)

    assert forge.doctor(capability="score", registered_only=True) is expected
    assert captured == {
        "host": forge,
        "capability": "score",
        "registered_only": True,
    }


def test_provider_profiles_and_doctor_report_include_known_scaffolds(tmp_path, monkeypatch) -> None:
    for env_var in (
        "COSMOS_POLICY_BASE_URL",
        "COSMOS_POLICY_API_TOKEN",
        "COSMOS_POLICY_TIMEOUT_SECONDS",
        "COSMOS_POLICY_EMBODIMENT_TAG",
        "COSMOS_POLICY_MODEL",
        "COSMOS_POLICY_RETURN_ALL_QUERY_RESULTS",
        "COSMOS_POLICY_ALLOW_LOCAL_BASE_URL",
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
        "cosmos-policy",
        "leworldmodel",
        "gr00t",
        "lerobot",
        "jepa",
        "genie",
    } <= set(builtin_profiles)
    assert builtin_profiles["cosmos-policy"].implementation_status == "beta"
    assert builtin_profiles["cosmos-policy"].capabilities.enabled_names() == []
    assert builtin_profiles["cosmos-policy"].capabilities.predict is False
    assert builtin_profiles["cosmos-policy"].required_env_vars == ["COSMOS_POLICY_BASE_URL"]
    assert builtin_profiles["cosmos-policy"].request_policy is not None
    assert builtin_profiles["cosmos-policy"].request_policy.request.retry.max_attempts == 1
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
    assert provider_statuses["cosmos-policy"].registered is False
    assert provider_statuses["cosmos-policy"].health.healthy is False
    assert any("COSMOS_POLICY_BASE_URL" in issue for issue in report.issues)

    with pytest.raises(WorldForgeError, match="Unknown provider capability"):
        forge.provider_healths(capability="generation")
    with pytest.raises(WorldForgeError, match="Unknown provider capability"):
        forge.doctor(capability="generation")


def test_doctor_capability_filter_includes_known_unregistered_providers(
    tmp_path,
    monkeypatch,
) -> None:
    for env_var in ("LEWORLDMODEL_POLICY", "LEWM_POLICY", "JEPA_MODEL_NAME"):
        monkeypatch.delenv(env_var, raising=False)

    report = WorldForge(state_dir=tmp_path).doctor(capability="score")
    statuses = {status.profile.name: status for status in report.providers}

    assert "leworldmodel" in statuses
    assert statuses["leworldmodel"].registered is False
    assert statuses["leworldmodel"].health.healthy is False
    assert "jepa" in statuses
    assert "mock" not in statuses
    assert any("LEWORLDMODEL_POLICY" in issue for issue in report.issues)


class _LifecycleReadyCost:
    name = "lifecycle-ready"
    profile = ProviderProfileSpec(
        description="Cost model with lifecycle hooks for diagnostics.",
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

    def score_actions(self, *, info, action_candidates) -> ActionScoreResult:
        return ActionScoreResult(
            provider=self.name,
            scores=[0.1],
            best_index=0,
            metadata={"fixture": info.get("fixture", "lifecycle")},
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


def _lifecycle_result(
    *,
    provider: str = "lifecycle-fixture",
    hook: str = "preflight",
    status: str = "ready",
    ready: bool = True,
    details: str = "",
    skip_reason: str = "",
    evidence: dict[str, object] | None = None,
) -> ProviderLifecycleResult:
    return ProviderLifecycleResult(
        provider=provider,
        hook=hook,
        status=status,
        ready=ready,
        latency_ms=0.1,
        details=details,
        skip_reason=skip_reason,
        evidence=evidence or {},
    )


def test_doctor_report_models_validate_and_redact_payloads(tmp_path) -> None:
    provider = BaseProvider("doctor-fixture")
    lifecycle = ProviderLifecycleStatus(
        provider="doctor-fixture",
        status="ready",
        ready=True,
        preflight=_lifecycle_result(provider="doctor-fixture"),
    )
    status = ProviderDoctorStatus(
        registered=True,
        profile=provider.profile(),
        health=provider.health(),
        lifecycle=lifecycle,
    )
    report = DoctorReport(
        state_dir=f" {tmp_path} ",
        world_count=1,
        providers=[status],
        issues=["api_key=abc123"],
    )

    assert report.state_dir == str(tmp_path)
    assert report.provider_count == 1
    assert report.issues == ["api_key=[redacted]"]
    assert report.to_dict()["providers"][0]["registered"] is True

    with pytest.raises(WorldForgeError, match="registered"):
        ProviderDoctorStatus(
            registered="yes",  # type: ignore[arg-type]
            profile=provider.profile(),
            health=provider.health(),
            lifecycle=lifecycle,
        )
    with pytest.raises(WorldForgeError, match="world_count"):
        DoctorReport(state_dir=str(tmp_path), world_count=math.nan, providers=[])
    with pytest.raises(WorldForgeError, match="providers"):
        DoctorReport(
            state_dir=str(tmp_path),
            world_count=0,
            providers=[object()],  # type: ignore[list-item]
        )
    with pytest.raises(WorldForgeError, match="issues"):
        DoctorReport(
            state_dir=str(tmp_path),
            world_count=0,
            providers=[],
            issues=[object()],  # type: ignore[list-item]
        )


class _MixedLifecycleProvider(BaseProvider):
    def __init__(
        self,
        *,
        name: str,
        preflight: ProviderLifecycleResult,
        warmup: ProviderLifecycleResult | None = None,
        teardown: ProviderLifecycleResult | None = None,
    ) -> None:
        super().__init__(name)
        self._preflight_result = preflight
        self._warmup_result = warmup
        self._teardown_result = teardown

    def preflight(self) -> ProviderLifecycleResult:
        return self._preflight_result

    def warmup(self) -> ProviderLifecycleResult:
        if self._warmup_result is None:
            return super().warmup()
        return self._warmup_result

    def teardown(self) -> ProviderLifecycleResult:
        if self._teardown_result is None:
            return super().teardown()
        return self._teardown_result


def test_provider_lifecycle_status_validates_hook_contract_and_redacts_evidence() -> None:
    preflight = _lifecycle_result()

    with pytest.raises(WorldForgeError, match="warmup hook must be 'warmup'"):
        ProviderLifecycleStatus(
            provider="lifecycle-fixture",
            status="ready",
            ready=True,
            preflight=preflight,
            warmup=_lifecycle_result(hook="teardown"),
        )

    with pytest.raises(WorldForgeError, match="hook result providers must match"):
        ProviderLifecycleStatus(
            provider="lifecycle-fixture",
            status="ready",
            ready=True,
            preflight=_lifecycle_result(provider="other-fixture"),
        )

    status = ProviderLifecycleStatus(
        provider=" lifecycle-fixture ",
        status="ready",
        ready=True,
        preflight=preflight,
        details="runtime returned api_key=abc123",
        skip_reason="Bearer secret-token",
        evidence={"token": "abc123", "url": "https://example.test/run?sig=secret"},
    )

    assert status.provider == "lifecycle-fixture"
    assert status.details == "runtime returned api_key=[redacted]"
    assert status.skip_reason == "Bearer [redacted]"
    assert status.evidence == {
        "token": "[redacted]",
        "url": "https://example.test/run",
    }


def test_provider_lifecycle_status_uses_highest_severity_issue_details() -> None:
    provider_name = "lifecycle-mixed"
    provider = _MixedLifecycleProvider(
        name=provider_name,
        preflight=_lifecycle_result(
            provider=provider_name,
            hook="preflight",
            status="ready",
            ready=True,
            details="runtime reachable",
            evidence={"runtime": "ready"},
        ),
        warmup=_lifecycle_result(
            provider=provider_name,
            hook="warmup",
            status="skipped",
            ready=False,
            details="warmup skipped",
            skip_reason="cache missing",
            evidence={"cache": "missing"},
        ),
        teardown=_lifecycle_result(
            provider=provider_name,
            hook="teardown",
            status="teardown-failed",
            ready=False,
            details="teardown socket close failed",
            evidence={"socket": "leaked"},
        ),
    )

    status = provider.lifecycle_status(run_warmup=True, run_teardown=True)

    assert status.status == "teardown-failed"
    assert status.ready is False
    assert status.details == "teardown socket close failed"
    assert status.skip_reason == ""
    assert status.evidence == {
        "preflight": {"runtime": "ready"},
        "warmup": {"cache": "missing"},
        "teardown": {"socket": "leaked"},
    }


def test_provider_lifecycle_hook_invocation_normalizes_invalid_results() -> None:
    invalid_status = build_provider_lifecycle_status(
        provider="lifecycle-fixture",
        preflight=lambda: object(),  # type: ignore[return-value]
    )

    assert invalid_status.status == "failed"
    assert invalid_status.ready is False
    assert "expected ProviderLifecycleResult" in invalid_status.details

    mismatched_status = build_provider_lifecycle_status(
        provider="lifecycle-fixture",
        preflight=lambda: _lifecycle_result(provider="other-fixture"),
    )

    assert mismatched_status.status == "failed"
    assert mismatched_status.ready is False
    assert "provider 'other-fixture'" in mismatched_status.details


def test_provider_lifecycle_hook_invocation_promotes_failed_teardown() -> None:
    status = build_provider_lifecycle_status(
        provider="lifecycle-fixture",
        preflight=lambda: _lifecycle_result(
            provider="lifecycle-fixture",
            hook="preflight",
            status="ready",
            ready=True,
        ),
        teardown=lambda: _lifecycle_result(
            provider="lifecycle-fixture",
            hook="teardown",
            status="failed",
            ready=False,
            details="close failed",
            evidence={"socket": "open"},
        ),
    )

    assert status.status == "teardown-failed"
    assert status.ready is False
    assert status.teardown is not None
    assert status.teardown.status == "teardown-failed"
    assert status.teardown.details == "close failed"
    assert status.evidence == {"teardown": {"socket": "open"}}


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

    ready_cost = _LifecycleReadyCost()
    forge.register_cost(ready_cost)
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

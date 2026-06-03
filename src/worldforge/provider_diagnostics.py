"""Provider health, lifecycle, and doctor-report model contracts."""

from __future__ import annotations

from dataclasses import dataclass, field

from worldforge._model_utils import (
    JSONDict,
    WorldForgeError,
    dump_json,
    require_bool,
    require_finite_number,
    require_json_dict,
)
from worldforge.provider_profiles import ProviderProfile
from worldforge.provider_redaction import _redact_observable_text, _redact_observable_value

PROVIDER_LIFECYCLE_HOOKS = ("preflight", "warmup", "teardown")
PROVIDER_LIFECYCLE_STATUSES = ("no-op", "ready", "skipped", "failed", "teardown-failed")


@dataclass(slots=True)
class ProviderHealth:
    """Health information for a provider."""

    name: str
    healthy: bool
    latency_ms: float
    details: str = ""

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or not self.name.strip():
            raise WorldForgeError("ProviderHealth name must be a non-empty string.")
        self.name = self.name.strip()
        self.healthy = require_bool(self.healthy, name="ProviderHealth healthy")
        self.latency_ms = require_finite_number(
            self.latency_ms,
            name="ProviderHealth latency_ms",
        )
        if self.latency_ms < 0.0:
            raise WorldForgeError("ProviderHealth latency_ms must be non-negative.")
        if not isinstance(self.details, str):
            raise WorldForgeError("ProviderHealth details must be a string.")
        self.details = _redact_observable_text(self.details)

    def to_dict(self) -> JSONDict:
        return {
            "name": self.name,
            "healthy": self.healthy,
            "latency_ms": self.latency_ms,
            "details": self.details,
        }


@dataclass(slots=True)
class ProviderLifecycleResult:
    """Result from one provider lifecycle hook.

    Hooks are provider-owned and optional. A result describes exactly one phase
    (`preflight`, `warmup`, or `teardown`) without leaking host paths, endpoints,
    credentials, or raw runtime payloads into diagnostics.
    """

    provider: str
    hook: str
    status: str
    ready: bool
    latency_ms: float
    details: str = ""
    skip_reason: str = ""
    evidence: JSONDict = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.provider, str) or not self.provider.strip():
            raise WorldForgeError("ProviderLifecycleResult provider must be a non-empty string.")
        if self.hook not in PROVIDER_LIFECYCLE_HOOKS:
            hooks = ", ".join(PROVIDER_LIFECYCLE_HOOKS)
            raise WorldForgeError(f"ProviderLifecycleResult hook must be one of: {hooks}.")
        if self.status not in PROVIDER_LIFECYCLE_STATUSES:
            statuses = ", ".join(PROVIDER_LIFECYCLE_STATUSES)
            raise WorldForgeError(f"ProviderLifecycleResult status must be one of: {statuses}.")
        self.ready = require_bool(self.ready, name="ProviderLifecycleResult ready")
        self.latency_ms = require_finite_number(
            self.latency_ms,
            name="ProviderLifecycleResult latency_ms",
        )
        if self.latency_ms < 0.0:
            raise WorldForgeError("ProviderLifecycleResult latency_ms must be non-negative.")
        if not isinstance(self.details, str):
            raise WorldForgeError("ProviderLifecycleResult details must be a string.")
        if not isinstance(self.skip_reason, str):
            raise WorldForgeError("ProviderLifecycleResult skip_reason must be a string.")
        self.provider = self.provider.strip()
        self.details = _redact_observable_text(self.details)
        self.skip_reason = _redact_observable_text(self.skip_reason)
        self.evidence = require_json_dict(
            _redact_observable_value(dict(self.evidence)),
            name="ProviderLifecycleResult evidence",
        )

    def to_dict(self) -> JSONDict:
        return {
            "provider": self.provider,
            "hook": self.hook,
            "status": self.status,
            "ready": self.ready,
            "latency_ms": self.latency_ms,
            "details": self.details,
            "skip_reason": self.skip_reason,
            "evidence": dict(self.evidence),
        }


@dataclass(slots=True)
class ProviderLifecycleStatus:
    """Aggregate lifecycle readiness for provider diagnostics."""

    provider: str
    status: str
    ready: bool
    preflight: ProviderLifecycleResult
    warmup: ProviderLifecycleResult | None = None
    teardown: ProviderLifecycleResult | None = None
    details: str = ""
    skip_reason: str = ""
    evidence: JSONDict = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.provider = _provider_lifecycle_status_provider(self.provider)
        self.status = _provider_lifecycle_status_status(self.status)
        self.ready = require_bool(self.ready, name="ProviderLifecycleStatus ready")
        _validate_provider_lifecycle_results(
            provider=self.provider,
            preflight=self.preflight,
            warmup=self.warmup,
            teardown=self.teardown,
        )
        self.details = _provider_lifecycle_status_text(self.details, field_name="details")
        self.skip_reason = _provider_lifecycle_status_text(
            self.skip_reason,
            field_name="skip_reason",
        )
        self.evidence = _provider_lifecycle_status_evidence(self.evidence)

    def to_dict(self) -> JSONDict:
        hooks: JSONDict = {"preflight": self.preflight.to_dict()}
        if self.warmup is not None:
            hooks["warmup"] = self.warmup.to_dict()
        if self.teardown is not None:
            hooks["teardown"] = self.teardown.to_dict()
        return {
            "provider": self.provider,
            "status": self.status,
            "ready": self.ready,
            "details": self.details,
            "skip_reason": self.skip_reason,
            "evidence": dict(self.evidence),
            "hooks": hooks,
        }


def _provider_lifecycle_status_provider(provider: object) -> str:
    if not isinstance(provider, str) or not provider.strip():
        raise WorldForgeError("ProviderLifecycleStatus provider must be a non-empty string.")
    return provider.strip()


def _provider_lifecycle_status_status(status: object) -> str:
    if not isinstance(status, str) or status not in PROVIDER_LIFECYCLE_STATUSES:
        statuses = ", ".join(PROVIDER_LIFECYCLE_STATUSES)
        raise WorldForgeError(f"ProviderLifecycleStatus status must be one of: {statuses}.")
    return status


def _validate_provider_lifecycle_results(
    *,
    provider: str,
    preflight: ProviderLifecycleResult,
    warmup: ProviderLifecycleResult | None,
    teardown: ProviderLifecycleResult | None,
) -> None:
    for result in (preflight, warmup, teardown):
        _validate_provider_lifecycle_result(provider=provider, result=result)
    _require_provider_lifecycle_hook(preflight, expected_hook="preflight")
    _require_optional_provider_lifecycle_hook(warmup, expected_hook="warmup")
    _require_optional_provider_lifecycle_hook(teardown, expected_hook="teardown")


def _validate_provider_lifecycle_result(
    *,
    provider: str,
    result: ProviderLifecycleResult | None,
) -> None:
    if result is None:
        return
    if not isinstance(result, ProviderLifecycleResult):
        raise WorldForgeError(
            "ProviderLifecycleStatus hook results must be ProviderLifecycleResult."
        )
    if result.provider != provider:
        raise WorldForgeError(
            "ProviderLifecycleStatus hook result providers must match status provider."
        )


def _require_optional_provider_lifecycle_hook(
    result: ProviderLifecycleResult | None,
    *,
    expected_hook: str,
) -> None:
    if result is not None:
        _require_provider_lifecycle_hook(result, expected_hook=expected_hook)


def _require_provider_lifecycle_hook(
    result: ProviderLifecycleResult,
    *,
    expected_hook: str,
) -> None:
    if result.hook != expected_hook:
        raise WorldForgeError(
            f"ProviderLifecycleStatus {expected_hook} hook must be '{expected_hook}'."
        )


def _provider_lifecycle_status_text(value: object, *, field_name: str) -> str:
    if not isinstance(value, str):
        raise WorldForgeError(f"ProviderLifecycleStatus {field_name} must be a string.")
    return _redact_observable_text(value)


def _provider_lifecycle_status_evidence(evidence: object) -> JSONDict:
    return require_json_dict(
        _redact_observable_value(dict(evidence)),
        name="ProviderLifecycleStatus evidence",
    )


@dataclass(slots=True)
class ProviderDoctorStatus:
    """Diagnostic snapshot for a provider in the active environment."""

    registered: bool
    profile: ProviderProfile
    health: ProviderHealth
    lifecycle: ProviderLifecycleStatus

    def __post_init__(self) -> None:
        self.registered = require_bool(self.registered, name="ProviderDoctorStatus registered")
        if not isinstance(self.profile, ProviderProfile):
            raise WorldForgeError("ProviderDoctorStatus profile must be a ProviderProfile.")
        if not isinstance(self.health, ProviderHealth):
            raise WorldForgeError("ProviderDoctorStatus health must be a ProviderHealth.")
        if not isinstance(self.lifecycle, ProviderLifecycleStatus):
            raise WorldForgeError(
                "ProviderDoctorStatus lifecycle must be a ProviderLifecycleStatus."
            )

    def to_dict(self) -> JSONDict:
        return {
            "name": self.profile.name,
            "registered": self.registered,
            "profile": self.profile.to_dict(),
            "health": self.health.to_dict(),
            "lifecycle": self.lifecycle.to_dict(),
        }


@dataclass(slots=True)
class DoctorReport:
    """Environment diagnostics for the current WorldForge install."""

    state_dir: str
    providers: list[ProviderDoctorStatus]
    issues: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not isinstance(self.state_dir, str) or not self.state_dir.strip():
            raise WorldForgeError("DoctorReport state_dir must be a non-empty string.")
        self.state_dir = self.state_dir.strip()
        if not isinstance(self.providers, list) or not all(
            isinstance(provider, ProviderDoctorStatus) for provider in self.providers
        ):
            raise WorldForgeError("DoctorReport providers must be a list of ProviderDoctorStatus.")
        self.providers = list(self.providers)
        if not isinstance(self.issues, list) or not all(
            isinstance(issue, str) for issue in self.issues
        ):
            raise WorldForgeError("DoctorReport issues must be a list of strings.")
        self.issues = [_redact_observable_text(issue) for issue in self.issues]

    @property
    def provider_count(self) -> int:
        return len(self.providers)

    @property
    def healthy_provider_count(self) -> int:
        return sum(1 for provider in self.providers if provider.health.healthy)

    @property
    def registered_provider_count(self) -> int:
        return sum(1 for provider in self.providers if provider.registered)

    def to_dict(self) -> JSONDict:
        return {
            "state_dir": self.state_dir,
            "provider_count": self.provider_count,
            "healthy_provider_count": self.healthy_provider_count,
            "registered_provider_count": self.registered_provider_count,
            "providers": [provider.to_dict() for provider in self.providers],
            "issues": list(self.issues),
        }

    def to_json(self) -> str:
        return dump_json(self.to_dict())

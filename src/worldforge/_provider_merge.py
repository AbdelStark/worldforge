"""Private helpers for merging legacy providers with capability wrappers."""

from __future__ import annotations

from collections.abc import Sequence
from typing import cast

from worldforge.capabilities import CAPABILITY_FIELD_TO_NAME
from worldforge.models import (
    CAPABILITY_NAMES,
    JSONDict,
    ProviderCapabilities,
    ProviderHealth,
    ProviderLifecycleResult,
    ProviderLifecycleStatus,
    ProviderProfile,
)
from worldforge.providers import BaseProvider, ProviderError
from worldforge.providers.observable import _ObservableCapability

_LIFECYCLE_STATUS_PRECEDENCE = ("teardown-failed", "failed", "skipped", "ready")
_LIFECYCLE_ISSUE_STATUSES = frozenset({"teardown-failed", "failed", "skipped"})


def dedupe_text(values: Sequence[str]) -> list[str]:
    seen: set[str] = set()
    deduped: list[str] = []
    for value in values:
        if value and value not in seen:
            seen.add(value)
            deduped.append(value)
    return deduped


def join_non_empty(values: Sequence[str], *, separator: str = " ") -> str:
    return separator.join(value for value in values if value)


def first_truthy_profile_value(profiles: Sequence[ProviderProfile], attr: str) -> object | None:
    return next((getattr(profile, attr) for profile in profiles if getattr(profile, attr)), None)


def first_present_profile_value(profiles: Sequence[ProviderProfile], attr: str) -> object | None:
    return next(
        (getattr(profile, attr) for profile in profiles if getattr(profile, attr) is not None),
        None,
    )


def merged_profile_text_list(profiles: Sequence[ProviderProfile], attr: str) -> list[str]:
    return dedupe_text(
        [item for profile in profiles for item in cast(Sequence[str], getattr(profile, attr))]
    )


def merged_profile_description(
    primary: ProviderProfile,
    profiles: Sequence[ProviderProfile],
) -> str:
    return primary.description or join_non_empty(
        [profile.description for profile in profiles],
        separator="; ",
    )


def merged_profile_credential_env_var(
    profiles: Sequence[ProviderProfile],
    required_env_vars: Sequence[str],
) -> str | None:
    credential = first_truthy_profile_value(profiles, "credential_env_var")
    if isinstance(credential, str):
        return credential
    return required_env_vars[0] if required_env_vars else None


def merged_provider_capabilities(
    *,
    legacy_profile: ProviderProfile | None,
    wrappers: Sequence[_ObservableCapability],
) -> ProviderCapabilities:
    flags = (
        legacy_profile.capabilities.to_dict()
        if legacy_profile is not None
        else dict.fromkeys(CAPABILITY_NAMES, False)
    )
    for wrapper in wrappers:
        flags[CAPABILITY_FIELD_TO_NAME[wrapper.kind]] = True
    return ProviderCapabilities(**flags)


def merged_provider_profile(
    name: str,
    *,
    legacy_provider: BaseProvider | None,
    wrappers: Sequence[_ObservableCapability],
) -> ProviderProfile:
    wrapper_profiles = tuple(wrapper.profile() for wrapper in wrappers)
    legacy_profile = legacy_provider.profile() if legacy_provider is not None else None
    profiles = tuple(
        profile for profile in (legacy_profile, *wrapper_profiles) if profile is not None
    )
    if not profiles:
        raise ProviderError(f"Provider '{name}' is unknown.")
    primary = profiles[0]
    required_env_vars = merged_profile_text_list(profiles, "required_env_vars")
    credential_env_var = merged_profile_credential_env_var(profiles, required_env_vars)
    return ProviderProfile(
        name=name,
        capabilities=merged_provider_capabilities(
            legacy_profile=legacy_profile,
            wrappers=wrappers,
        ),
        is_local=any(profile.is_local for profile in profiles),
        description=merged_profile_description(primary, profiles),
        package=primary.package,
        implementation_status=primary.implementation_status,
        deterministic=all(profile.deterministic for profile in profiles),
        requires_credentials=any(profile.requires_credentials for profile in profiles),
        credential_env_var=credential_env_var,
        required_env_vars=required_env_vars,
        supported_modalities=merged_profile_text_list(profiles, "supported_modalities"),
        artifact_types=merged_profile_text_list(profiles, "artifact_types"),
        notes=merged_profile_text_list(profiles, "notes"),
        default_model=cast(str | None, first_truthy_profile_value(profiles, "default_model")),
        supported_models=merged_profile_text_list(profiles, "supported_models"),
        request_policy=first_present_profile_value(profiles, "request_policy"),
    )


def provider_missing_configuration(
    *,
    profile: ProviderProfile,
    legacy_provider: BaseProvider | None,
    wrappers: Sequence[_ObservableCapability],
) -> bool:
    if not profile.required_env_vars:
        return False
    legacy_missing = legacy_provider is not None and not legacy_provider.configured()
    wrapper_missing = any(not wrapper.configured() for wrapper in wrappers)
    return legacy_missing or wrapper_missing


def provider_health_components(
    *,
    legacy_provider: BaseProvider | None,
    wrappers: Sequence[_ObservableCapability],
) -> list[ProviderHealth]:
    healths: list[ProviderHealth] = []
    if legacy_provider is not None:
        healths.append(legacy_provider.health())
    healths.extend(wrapper.health() for wrapper in wrappers)
    return healths


def merged_provider_health_details(healths: Sequence[ProviderHealth], *, healthy: bool) -> str:
    if healthy:
        return "configured"
    return "; ".join(f"{health.name}: {health.details}" for health in healths if not health.healthy)


def merged_provider_health(name: str, healths: Sequence[ProviderHealth]) -> ProviderHealth:
    if not healths:
        raise ProviderError(f"Provider '{name}' is unknown.")
    if len(healths) == 1:
        return healths[0]
    healthy = all(health.healthy for health in healths)
    return ProviderHealth(
        name=name,
        healthy=healthy,
        latency_ms=sum(health.latency_ms for health in healths),
        details=merged_provider_health_details(healths, healthy=healthy),
    )


def provider_lifecycle_components(
    *,
    legacy_provider: BaseProvider | None,
    wrappers: Sequence[_ObservableCapability],
    run_warmup: bool,
    run_teardown: bool,
) -> list[ProviderLifecycleStatus]:
    statuses: list[ProviderLifecycleStatus] = []
    if legacy_provider is not None:
        statuses.append(
            legacy_provider.lifecycle_status(
                run_warmup=run_warmup,
                run_teardown=run_teardown,
            )
        )
    statuses.extend(
        wrapper.lifecycle_status(
            run_warmup=run_warmup,
            run_teardown=run_teardown,
        )
        for wrapper in wrappers
    )
    return statuses


def merged_lifecycle_status_value(statuses: Sequence[ProviderLifecycleStatus]) -> str:
    for status_value in _LIFECYCLE_STATUS_PRECEDENCE:
        if any(status.status == status_value for status in statuses):
            return status_value
    return "no-op"


def merged_lifecycle_issue(
    statuses: Sequence[ProviderLifecycleStatus],
) -> ProviderLifecycleStatus | None:
    return next(
        (status for status in statuses if status.status in _LIFECYCLE_ISSUE_STATUSES),
        None,
    )


def merged_lifecycle_details(
    statuses: Sequence[ProviderLifecycleStatus],
    *,
    fallback: str,
) -> str:
    details = join_non_empty(
        [f"{status.provider}: {status.details}" for status in statuses if status.details],
        separator="; ",
    )
    return details or fallback


def merged_lifecycle_skip_reason(issue: ProviderLifecycleStatus | None) -> str:
    if issue is not None and issue.status == "skipped":
        return issue.skip_reason
    return ""


def merged_lifecycle_component_evidence(statuses: Sequence[ProviderLifecycleStatus]) -> JSONDict:
    return {"components": [status.to_dict() for status in statuses]}


def merged_lifecycle_ready(status_value: str) -> bool:
    return status_value in {"no-op", "ready"}


def merged_lifecycle_preflight(
    name: str,
    statuses: Sequence[ProviderLifecycleStatus],
    *,
    status_value: str,
    details: str,
    skip_reason: str,
    evidence: JSONDict,
) -> ProviderLifecycleResult:
    return ProviderLifecycleResult(
        provider=name,
        hook="preflight",
        status=status_value,
        ready=merged_lifecycle_ready(status_value),
        latency_ms=sum(lifecycle.preflight.latency_ms for lifecycle in statuses),
        details=details,
        skip_reason=skip_reason,
        evidence=evidence,
    )


def merged_provider_lifecycle_status(
    name: str,
    statuses: Sequence[ProviderLifecycleStatus],
) -> ProviderLifecycleStatus:
    if not statuses:
        raise ProviderError(f"Provider '{name}' is unknown.")
    if len(statuses) == 1:
        return statuses[0]
    status_value = merged_lifecycle_status_value(statuses)
    issue = merged_lifecycle_issue(statuses)
    details = merged_lifecycle_details(statuses, fallback=status_value)
    skip_reason = merged_lifecycle_skip_reason(issue)
    evidence = merged_lifecycle_component_evidence(statuses)
    return ProviderLifecycleStatus(
        provider=name,
        status=status_value,
        ready=merged_lifecycle_ready(status_value),
        preflight=merged_lifecycle_preflight(
            name,
            statuses,
            status_value=status_value,
            details=details,
            skip_reason=skip_reason,
            evidence=evidence,
        ),
        details=details,
        skip_reason=skip_reason,
        evidence=evidence,
    )

"""Provider diagnostics assembly for :class:`worldforge.framework.WorldForge`."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from worldforge._provider_merge import (
    provider_missing_configuration as _provider_missing_configuration,
)
from worldforge.models import (
    DoctorReport,
    ProviderDoctorStatus,
    ProviderHealth,
    ProviderLifecycleStatus,
    ProviderProfile,
)
from worldforge.providers import BaseProvider
from worldforge.providers.observable import _ObservableCapability


class DoctorHost(Protocol):
    state_dir: Path

    def list_worlds(self) -> list[str]: ...

    def _provider_catalog(self, *, include_known: bool = True) -> dict[str, BaseProvider]: ...

    def _provider_view_names(self, *, include_known: bool) -> list[str]: ...

    def _registered_provider_names(self) -> set[str]: ...

    def _capability_wrappers_for_name(self, name: str) -> tuple[_ObservableCapability, ...]: ...

    def _merged_profile(
        self,
        name: str,
        *,
        legacy_provider: BaseProvider | None,
        wrappers: Sequence[_ObservableCapability],
    ) -> ProviderProfile: ...

    def _merged_health(
        self,
        name: str,
        *,
        legacy_provider: BaseProvider | None,
        wrappers: Sequence[_ObservableCapability],
    ) -> ProviderHealth: ...

    def _merged_lifecycle_status(
        self,
        name: str,
        *,
        legacy_provider: BaseProvider | None,
        wrappers: Sequence[_ObservableCapability],
    ) -> ProviderLifecycleStatus: ...


@dataclass(slots=True, frozen=True)
class DoctorProviderContext:
    name: str
    legacy_provider: BaseProvider | None
    wrappers: tuple[_ObservableCapability, ...]
    profile: ProviderProfile


def doctor_report(
    host: DoctorHost,
    *,
    capability: str | None,
    registered_only: bool,
) -> DoctorReport:
    statuses, issues = doctor_provider_statuses_and_issues(
        host,
        capability=capability,
        include_known=not registered_only,
    )
    return DoctorReport(
        state_dir=str(host.state_dir),
        world_count=len(host.list_worlds()),
        providers=statuses,
        issues=issues,
    )


def doctor_provider_statuses_and_issues(
    host: DoctorHost,
    *,
    capability: str | None = None,
    include_known: bool,
) -> tuple[list[ProviderDoctorStatus], list[str]]:
    legacy_catalog = host._provider_catalog(include_known=include_known)
    registered_names = host._registered_provider_names()
    contexts = doctor_contexts_for_capability(
        doctor_provider_contexts(
            host,
            legacy_catalog=legacy_catalog,
            include_known=include_known,
        ),
        capability=capability,
    )
    results = [
        doctor_status_and_issue_for_context(
            host,
            context,
            registered_names=registered_names,
        )
        for context in contexts
    ]
    statuses = [status for status, _issue in results]
    issues = [issue for _status, issue in results if issue is not None]
    return statuses, issues


def doctor_provider_contexts(
    host: DoctorHost,
    *,
    legacy_catalog: dict[str, BaseProvider],
    include_known: bool,
) -> list[DoctorProviderContext]:
    return [
        doctor_provider_context(host, name, legacy_catalog=legacy_catalog)
        for name in host._provider_view_names(include_known=include_known)
    ]


def doctor_provider_context(
    host: DoctorHost,
    name: str,
    *,
    legacy_catalog: dict[str, BaseProvider],
) -> DoctorProviderContext:
    legacy_provider = legacy_catalog.get(name)
    wrappers = host._capability_wrappers_for_name(name)
    profile = host._merged_profile(
        name,
        legacy_provider=legacy_provider,
        wrappers=wrappers,
    )
    return DoctorProviderContext(
        name=name,
        legacy_provider=legacy_provider,
        wrappers=wrappers,
        profile=profile,
    )


def doctor_contexts_for_capability(
    contexts: Sequence[DoctorProviderContext],
    *,
    capability: str | None,
) -> list[DoctorProviderContext]:
    if capability is None:
        return list(contexts)
    return [context for context in contexts if context.profile.capabilities.supports(capability)]


def doctor_status_and_issue_for_context(
    host: DoctorHost,
    context: DoctorProviderContext,
    *,
    registered_names: set[str],
) -> tuple[ProviderDoctorStatus, str | None]:
    status = doctor_status_for_context(host, context, registered_names=registered_names)
    issue = doctor_provider_issue(
        name=context.name,
        profile=context.profile,
        health=status.health,
        legacy_provider=context.legacy_provider,
        wrappers=context.wrappers,
    )
    return status, issue


def doctor_status_for_context(
    host: DoctorHost,
    context: DoctorProviderContext,
    *,
    registered_names: set[str],
) -> ProviderDoctorStatus:
    health = host._merged_health(
        context.name,
        legacy_provider=context.legacy_provider,
        wrappers=context.wrappers,
    )
    lifecycle = host._merged_lifecycle_status(
        context.name,
        legacy_provider=context.legacy_provider,
        wrappers=context.wrappers,
    )
    return ProviderDoctorStatus(
        registered=context.name in registered_names,
        profile=context.profile,
        health=health,
        lifecycle=lifecycle,
    )


def doctor_provider_issue(
    *,
    name: str,
    profile: ProviderProfile,
    health: ProviderHealth,
    legacy_provider: BaseProvider | None,
    wrappers: Sequence[_ObservableCapability],
) -> str | None:
    if health.healthy:
        return None
    if _provider_missing_configuration(
        profile=profile,
        legacy_provider=legacy_provider,
        wrappers=wrappers,
    ):
        required = ", ".join(profile.required_env_vars)
        return f"Provider '{name}' is unavailable: missing or invalid {required}."
    return f"Provider '{name}' is unhealthy: {health.details}."

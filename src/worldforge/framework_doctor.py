"""Provider diagnostics assembly for :class:`worldforge.framework.WorldForge`."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from worldforge.models import (
    DoctorReport,
    ProviderDoctorStatus,
    ProviderHealth,
    ProviderProfile,
)
from worldforge.provider_view import ProviderView


class DoctorHost(Protocol):
    state_dir: Path

    def _provider_views(self, *, include_known: bool) -> list[ProviderView]: ...


@dataclass(slots=True, frozen=True)
class DoctorProviderContext:
    view: ProviderView
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
        providers=statuses,
        issues=issues,
    )


def doctor_provider_statuses_and_issues(
    host: DoctorHost,
    *,
    capability: str | None = None,
    include_known: bool,
) -> tuple[list[ProviderDoctorStatus], list[str]]:
    contexts = doctor_contexts_for_capability(
        doctor_provider_contexts(host, include_known=include_known),
        capability=capability,
    )
    results = [doctor_status_and_issue_for_context(context) for context in contexts]
    statuses = [status for status, _issue in results]
    issues = [issue for _status, issue in results if issue is not None]
    return statuses, issues


def doctor_provider_contexts(
    host: DoctorHost,
    *,
    include_known: bool,
) -> list[DoctorProviderContext]:
    return [
        DoctorProviderContext(view=view, profile=view.profile())
        for view in host._provider_views(include_known=include_known)
    ]


def doctor_contexts_for_capability(
    contexts: list[DoctorProviderContext],
    *,
    capability: str | None,
) -> list[DoctorProviderContext]:
    if capability is None:
        return list(contexts)
    return [context for context in contexts if context.profile.capabilities.supports(capability)]


def doctor_status_and_issue_for_context(
    context: DoctorProviderContext,
) -> tuple[ProviderDoctorStatus, str | None]:
    status = doctor_status_for_context(context)
    issue = doctor_provider_issue(
        view=context.view,
        profile=context.profile,
        health=status.health,
    )
    return status, issue


def doctor_status_for_context(
    context: DoctorProviderContext,
) -> ProviderDoctorStatus:
    health = context.view.health()
    lifecycle = context.view.lifecycle_status()
    return ProviderDoctorStatus(
        registered=context.view.registered,
        profile=context.profile,
        health=health,
        lifecycle=lifecycle,
    )


def doctor_provider_issue(
    *,
    view: ProviderView,
    profile: ProviderProfile,
    health: ProviderHealth,
) -> str | None:
    if health.healthy:
        return None
    if view.missing_configuration(profile):
        required = ", ".join(profile.required_env_vars)
        return f"Provider '{view.name}' is unavailable: missing or invalid {required}."
    return f"Provider '{view.name}' is unhealthy: {health.details}."

"""Workflow capability negotiation reports for WorldForge.

The negotiation report tells a caller — before a workflow runs — whether the currently
registered and known providers can satisfy a capability set. It groups providers by required
capability, classifies each candidate as registered/configured/dependency-ready/capability-
compatible, and emits a recommended next command for each gap (e.g. ``set LEWORLDMODEL_POLICY``,
``register a policy provider via the worldforge.providers entry-point group``).

Out of scope:

- No automatic credential setup or installation.
- No runtime fallback execution. Callers receive recommendations and decide whether to act.

The report is **provisional** public API. Schema additions are safe; field renames or removals
require a version bump and a migration note in the changelog.
"""

from __future__ import annotations

import os
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING

from worldforge.models import (
    CAPABILITY_NAMES,
    JSONDict,
    ProviderCapabilities,
    WorldForgeError,
)
from worldforge.providers.catalog import PROVIDER_CATALOG
from worldforge.testing.runtime_profiles import (
    PROVIDER_RUNTIME_PROFILES_BY_NAME,
    provider_profile_skip_reason,
)

if TYPE_CHECKING:  # pragma: no cover - import-time only
    from worldforge.framework import WorldForge


CAPABILITY_NEGOTIATION_SCHEMA_VERSION = 1


@dataclass(frozen=True, slots=True)
class WorkflowSpec:
    """Declared capability surface for a named workflow."""

    name: str
    title: str
    description: str
    required_capabilities: tuple[str, ...]
    notes: str = ""

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise WorldForgeError("WorkflowSpec name must be a non-empty string.")
        if not self.required_capabilities:
            raise WorldForgeError(
                f"WorkflowSpec '{self.name}' must declare at least one required capability."
            )
        unknown = [
            capability
            for capability in self.required_capabilities
            if capability not in CAPABILITY_NAMES
        ]
        if unknown:
            joined = ", ".join(unknown)
            known = ", ".join(CAPABILITY_NAMES)
            raise WorldForgeError(
                f"WorkflowSpec '{self.name}' has unknown capabilities: {joined}. "
                f"Known capabilities: {known}."
            )

    def to_dict(self) -> JSONDict:
        return {
            "name": self.name,
            "title": self.title,
            "description": self.description,
            "required_capabilities": list(self.required_capabilities),
            "notes": self.notes,
        }


_WORKFLOWS: tuple[WorkflowSpec, ...] = (
    WorkflowSpec(
        name="predict-only",
        title="Predict-only workflow",
        description="Workflows that only need a world-model predict provider.",
        required_capabilities=("predict",),
        notes="The mock provider always satisfies predict for checkout-safe runs.",
    ),
    WorkflowSpec(
        name="score-only",
        title="Score-only workflow",
        description="Action scoring workflows that only need a score-capable provider.",
        required_capabilities=("score",),
        notes="LeWorldModel requires LEWORLDMODEL_POLICY or LEWM_POLICY.",
    ),
    WorkflowSpec(
        name="policy-only",
        title="Policy-only workflow",
        description="Embodied policy workflows that only need a policy-capable provider.",
        required_capabilities=("policy",),
        notes=(
            "LeRobot requires LEROBOT_POLICY_PATH or LEROBOT_POLICY; "
            "GR00T requires GROOT_POLICY_HOST."
        ),
    ),
    WorkflowSpec(
        name="embed-only",
        title="Embed-only workflow",
        description="Embedding workflows that only need an embed-capable provider.",
        required_capabilities=("embed",),
    ),
    WorkflowSpec(
        name="policy-plus-score",
        title="Policy + score workflow",
        description=(
            "Embodied workflows that propose actions with a policy provider and rank them with "
            "a score provider. Both capabilities must be satisfied — typically by different "
            "providers."
        ),
        required_capabilities=("policy", "score"),
        notes=(
            "A common prepared-host pairing is LeRobot (policy) + LeWorldModel (score); both "
            "require their respective env-var profiles."
        ),
    ),
    WorkflowSpec(
        name="evaluation-physics",
        title="Evaluation suite: physics",
        description=(
            "Mirrors the built-in 'physics' evaluation suite's required capability surface."
        ),
        required_capabilities=("predict",),
    ),
    WorkflowSpec(
        name="evaluation-planning",
        title="Evaluation suite: planning",
        description=(
            "Mirrors the built-in 'planning' evaluation suite's required capability surface."
        ),
        required_capabilities=("predict",),
    ),
)


_WORKFLOWS_BY_NAME: dict[str, WorkflowSpec] = {workflow.name: workflow for workflow in _WORKFLOWS}


def list_workflows() -> tuple[WorkflowSpec, ...]:
    """Return every known workflow spec in display order."""

    return _WORKFLOWS


def list_workflow_names() -> tuple[str, ...]:
    """Return canonical workflow names in display order."""

    return tuple(workflow.name for workflow in _WORKFLOWS)


def get_workflow(name: str) -> WorkflowSpec:
    """Return one workflow by name. Raises :class:`WorldForgeError` on unknown names."""

    try:
        return _WORKFLOWS_BY_NAME[name]
    except KeyError as exc:
        known = ", ".join(_WORKFLOWS_BY_NAME)
        raise WorldForgeError(f"Unknown workflow '{name}'. Known workflows: {known}.") from exc


_READINESS_READY = "ready"
_READINESS_MISSING_CONFIG = "missing-config"
_READINESS_MISSING_DEPENDENCY = "missing-dependency"
_READINESS_UNSUPPORTED = "unsupported"
_READINESS_NOT_REGISTERED = "not-registered"


@dataclass(frozen=True, slots=True)
class CapabilityProviderStatus:
    """Per-provider readiness for one capability inside a workflow."""

    name: str
    capability: str
    registered: bool
    capability_compatible: bool
    configured: bool
    healthy: bool
    readiness: str
    reason: str | None

    def is_ready(self) -> bool:
        """Return ``True`` when the provider can serve the capability right now."""

        return self.readiness == _READINESS_READY

    def to_dict(self) -> JSONDict:
        return {
            "name": self.name,
            "capability": self.capability,
            "registered": self.registered,
            "capability_compatible": self.capability_compatible,
            "configured": self.configured,
            "healthy": self.healthy,
            "readiness": self.readiness,
            "reason": self.reason,
        }


@dataclass(frozen=True, slots=True)
class CapabilityRequirement:
    """One capability slot inside a workflow with all candidate providers."""

    capability: str
    ready: bool
    candidates: tuple[CapabilityProviderStatus, ...]
    recommended_action: str | None

    def ready_providers(self) -> tuple[str, ...]:
        return tuple(status.name for status in self.candidates if status.is_ready())

    def to_dict(self) -> JSONDict:
        return {
            "capability": self.capability,
            "ready": self.ready,
            "ready_providers": list(self.ready_providers()),
            "candidates": [status.to_dict() for status in self.candidates],
            "recommended_action": self.recommended_action,
        }


@dataclass(frozen=True, slots=True)
class WorkflowNegotiation:
    """Negotiation result for one workflow."""

    workflow: WorkflowSpec
    requirements: tuple[CapabilityRequirement, ...]
    ready: bool
    recommended_actions: tuple[str, ...]

    def summary(self) -> str:
        if self.ready:
            providers = sorted(
                {
                    status.name
                    for requirement in self.requirements
                    for status in requirement.candidates
                    if status.is_ready()
                }
            )
            return f"ready with: {', '.join(providers) if providers else 'no providers'}"
        unmet = [
            requirement.capability for requirement in self.requirements if not requirement.ready
        ]
        return f"missing capability coverage: {', '.join(unmet)}"

    def to_dict(self) -> JSONDict:
        return {
            "workflow": self.workflow.to_dict(),
            "ready": self.ready,
            "summary": self.summary(),
            "requirements": [requirement.to_dict() for requirement in self.requirements],
            "recommended_actions": list(self.recommended_actions),
        }


@dataclass(frozen=True, slots=True)
class CapabilityNegotiationReport:
    """Report covering one or more workflow negotiations."""

    workflows: tuple[WorkflowNegotiation, ...]
    schema_version: int = CAPABILITY_NEGOTIATION_SCHEMA_VERSION

    @property
    def ready_count(self) -> int:
        return sum(1 for negotiation in self.workflows if negotiation.ready)

    def to_dict(self) -> JSONDict:
        return {
            "schema_version": self.schema_version,
            "workflow_count": len(self.workflows),
            "ready_count": self.ready_count,
            "workflows": [negotiation.to_dict() for negotiation in self.workflows],
        }

    def to_markdown(self) -> str:
        lines = [
            "# Capability Negotiation Report",
            "",
            f"Workflows: {len(self.workflows)} | Ready: {self.ready_count}",
            "",
        ]
        for negotiation in self.workflows:
            lines.extend(_workflow_markdown_lines(negotiation))
        return "\n".join(lines).rstrip() + "\n"


def _workflow_markdown_lines(negotiation: WorkflowNegotiation) -> list[str]:
    workflow = negotiation.workflow
    status = "READY" if negotiation.ready else "BLOCKED"
    lines = [
        f"## {workflow.title} (`{workflow.name}`) — {status}",
        "",
        workflow.description,
        "",
        f"Required capabilities: {', '.join(workflow.required_capabilities)}",
        f"Summary: {negotiation.summary()}",
        "",
    ]
    for requirement in negotiation.requirements:
        lines.extend(_requirement_markdown_lines(requirement))
    if negotiation.recommended_actions and not negotiation.ready:
        lines.extend(_recommended_actions_markdown_lines(negotiation.recommended_actions))
    return lines


def _requirement_markdown_lines(requirement: CapabilityRequirement) -> list[str]:
    lines = [
        f"### Capability: `{requirement.capability}` "
        f"({'ready' if requirement.ready else 'blocked'})",
        "",
        "| provider | registered | capability | configured | healthy | readiness | reason |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    lines.extend(_provider_status_markdown_row(status) for status in requirement.candidates)
    if requirement.recommended_action:
        lines.extend(["", f"Next step: {requirement.recommended_action}"])
    lines.append("")
    return lines


def _provider_status_markdown_row(status: CapabilityProviderStatus) -> str:
    return (
        f"| {status.name} | "
        f"{_yes_no(status.registered)} | "
        f"{_yes_no(status.capability_compatible)} | "
        f"{_yes_no(status.configured)} | "
        f"{_yes_no(status.healthy)} | "
        f"{status.readiness} | "
        f"{status.reason or '-'} |"
    )


def _yes_no(value: bool) -> str:
    return "yes" if value else "no"


def _recommended_actions_markdown_lines(actions: Sequence[str]) -> list[str]:
    return ["### Recommended actions", "", *(f"- {action}" for action in actions), ""]


def _runtime_profile_missing_reason(provider: str, environ: Mapping[str, str]) -> str | None:
    """Return the env-gating skip reason for a provider, or ``None`` when fully configured."""

    if provider not in PROVIDER_RUNTIME_PROFILES_BY_NAME:
        return None
    return provider_profile_skip_reason(provider, environ)


def _capability_compatible_providers(
    capability: str,
    forge: WorldForge,
) -> list[tuple[str, ProviderCapabilities, bool]]:
    """Return ``(name, capabilities, registered)`` for providers that advertise ``capability``.

    The list combines registered providers and known-but-unregistered catalog providers so a
    caller can see what *could* serve the capability with the right env or registration.
    """

    seen: set[str] = set()
    out: list[tuple[str, ProviderCapabilities, bool]] = []
    registered_names = set(forge.providers())

    for entry in PROVIDER_CATALOG:
        provider = entry.create()
        capabilities = provider.profile().capabilities
        if not capabilities.supports(capability):
            continue
        registered = entry.name in registered_names
        out.append((entry.name, capabilities, registered))
        seen.add(entry.name)

    for name in sorted(registered_names - seen):
        provider = forge._require_provider(name)
        capabilities = provider.profile().capabilities
        if capabilities.supports(capability):
            out.append((name, capabilities, True))

    return out


def _build_recommended_action(
    capability: str,
    statuses: Sequence[CapabilityProviderStatus],
) -> str | None:
    """Generate a single, focused recommendation for unmet capability coverage."""

    if any(status.is_ready() for status in statuses):
        return None
    missing_config = [
        status for status in statuses if status.readiness == _READINESS_MISSING_CONFIG
    ]
    if missing_config:
        provider = missing_config[0]
        if provider.reason:
            return (
                f"Configure provider '{provider.name}' to serve capability '{capability}': "
                f"{provider.reason}."
            )
    if statuses:
        return f"Register or configure a provider that supports capability '{capability}'."
    return (
        f"No provider in the catalog advertises capability '{capability}'. Register a provider "
        "that does, via WorldForge.register_provider()."
    )


def _classify_provider(
    name: str,
    capability: str,
    capabilities: ProviderCapabilities,
    registered: bool,
    forge: WorldForge,
    environ: Mapping[str, str],
) -> CapabilityProviderStatus:
    if not capabilities.supports(capability):
        return _provider_status(
            name=name,
            capability=capability,
            registered=registered,
            capability_compatible=False,
            configured=False,
            healthy=False,
            readiness=_READINESS_UNSUPPORTED,
            reason=f"provider '{name}' does not advertise capability '{capability}'",
        )

    if registered:
        return _registered_provider_status(
            name,
            capability=capability,
            forge=forge,
            environ=environ,
        )

    missing = _runtime_profile_missing_reason(name, environ)
    if missing is not None:
        return _provider_status(
            name=name,
            capability=capability,
            registered=False,
            capability_compatible=True,
            configured=False,
            healthy=False,
            readiness=_READINESS_MISSING_CONFIG,
            reason=missing,
        )
    return _provider_status(
        name=name,
        capability=capability,
        registered=False,
        capability_compatible=True,
        configured=False,
        healthy=False,
        readiness=_READINESS_NOT_REGISTERED,
        reason=f"provider '{name}' is known but not registered on this forge",
    )


def _registered_provider_status(
    name: str,
    *,
    capability: str,
    forge: WorldForge,
    environ: Mapping[str, str],
) -> CapabilityProviderStatus:
    provider = forge._require_provider(name)
    configured = bool(provider.configured())
    healthy = _provider_is_healthy(provider)
    if configured and healthy:
        return _provider_status(
            name=name,
            capability=capability,
            registered=True,
            capability_compatible=True,
            configured=True,
            healthy=True,
            readiness=_READINESS_READY,
            reason=None,
        )
    if not configured:
        missing = _runtime_profile_missing_reason(name, environ)
        return _provider_status(
            name=name,
            capability=capability,
            registered=True,
            capability_compatible=True,
            configured=False,
            healthy=healthy,
            readiness=_READINESS_MISSING_CONFIG,
            reason=missing or f"provider '{name}' reports configured() == False",
        )
    return _provider_status(
        name=name,
        capability=capability,
        registered=True,
        capability_compatible=True,
        configured=True,
        healthy=False,
        readiness=_READINESS_MISSING_DEPENDENCY,
        reason=f"provider '{name}' health check is unhealthy",
    )


def _provider_is_healthy(provider: object) -> bool:
    health = getattr(provider, "health", None)
    if not callable(health):
        return False
    try:
        return bool(getattr(health(), "healthy", False))
    except Exception:
        return False


def _provider_status(
    *,
    name: str,
    capability: str,
    registered: bool,
    capability_compatible: bool,
    configured: bool,
    healthy: bool,
    readiness: str,
    reason: str | None,
) -> CapabilityProviderStatus:
    return CapabilityProviderStatus(
        name=name,
        capability=capability,
        registered=registered,
        capability_compatible=capability_compatible,
        configured=configured,
        healthy=healthy,
        readiness=readiness,
        reason=reason,
    )


def _selected_workflows(workflows: Iterable[WorkflowSpec | str] | None) -> tuple[WorkflowSpec, ...]:
    if workflows is None:
        return _WORKFLOWS
    return tuple(
        workflow if isinstance(workflow, WorkflowSpec) else get_workflow(str(workflow))
        for workflow in workflows
    )


def _statuses_for_capability(
    capability: str,
    *,
    forge: WorldForge,
    environ: Mapping[str, str],
) -> tuple[CapabilityProviderStatus, ...]:
    return tuple(
        _classify_provider(
            name=name,
            capability=capability,
            capabilities=capabilities,
            registered=registered,
            forge=forge,
            environ=environ,
        )
        for name, capabilities, registered in _capability_compatible_providers(capability, forge)
    )


def _requirement_for_capability(
    capability: str,
    *,
    forge: WorldForge,
    environ: Mapping[str, str],
) -> CapabilityRequirement:
    statuses = _statuses_for_capability(capability, forge=forge, environ=environ)
    ready = any(status.is_ready() for status in statuses)
    return CapabilityRequirement(
        capability=capability,
        ready=ready,
        candidates=statuses,
        recommended_action=None if ready else _build_recommended_action(capability, statuses),
    )


def _unique_recommended_actions(
    requirements: Sequence[CapabilityRequirement],
) -> tuple[str, ...]:
    actions: list[str] = []
    seen: set[str] = set()
    for requirement in requirements:
        action = requirement.recommended_action
        if action and action not in seen:
            actions.append(action)
            seen.add(action)
    return tuple(actions)


def _negotiate_workflow(
    workflow: WorkflowSpec,
    *,
    forge: WorldForge,
    environ: Mapping[str, str],
) -> WorkflowNegotiation:
    requirements = tuple(
        _requirement_for_capability(capability, forge=forge, environ=environ)
        for capability in workflow.required_capabilities
    )
    return WorkflowNegotiation(
        workflow=workflow,
        requirements=requirements,
        ready=all(requirement.ready for requirement in requirements),
        recommended_actions=_unique_recommended_actions(requirements),
    )


def negotiate(
    workflows: Iterable[WorkflowSpec | str] | None = None,
    *,
    forge: WorldForge | None = None,
    environ: Mapping[str, str] | None = None,
) -> CapabilityNegotiationReport:
    """Run capability negotiation for ``workflows`` (default: every known workflow).

    ``workflows`` may contain :class:`WorkflowSpec` instances or workflow names. Unknown names
    raise :class:`WorldForgeError`. ``forge`` defaults to a freshly-constructed
    :class:`~worldforge.framework.WorldForge`. ``environ`` defaults to ``os.environ`` and is
    used to evaluate runtime-profile skip reasons.
    """

    from worldforge.framework import WorldForge as _WorldForge

    active_forge = forge or _WorldForge()
    env = os.environ if environ is None else environ
    negotiations = tuple(
        _negotiate_workflow(workflow, forge=active_forge, environ=env)
        for workflow in _selected_workflows(workflows)
    )
    return CapabilityNegotiationReport(workflows=tuple(negotiations))


# Alias exposed from the top-level ``worldforge`` package so callers don't have to import the
# submodule. The shorter ``negotiate`` name is preserved on this module for explicit imports.
negotiate_capabilities = negotiate


__all__ = [
    "CAPABILITY_NEGOTIATION_SCHEMA_VERSION",
    "CapabilityNegotiationReport",
    "CapabilityProviderStatus",
    "CapabilityRequirement",
    "WorkflowNegotiation",
    "WorkflowSpec",
    "get_workflow",
    "list_workflow_names",
    "list_workflows",
    "negotiate",
    "negotiate_capabilities",
]

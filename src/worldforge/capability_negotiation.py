"""Workflow capability negotiation reports for WorldForge.

The negotiation report tells a caller — before a workflow runs — whether the currently
registered and known providers can satisfy a capability set. It groups providers by required
capability, classifies each candidate as registered/configured/dependency-ready/capability-
compatible, and emits a recommended next command for each gap (e.g. ``set COSMOS_BASE_URL``,
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
        name="generate-only",
        title="Generate-only workflow",
        description=(
            "Video or media generation workflows that only need a generate-capable provider."
        ),
        required_capabilities=("generate",),
        notes="Cosmos requires COSMOS_BASE_URL; Runway requires RUNWAYML_API_SECRET.",
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
        name="transfer-only",
        title="Transfer-only workflow",
        description="Video transfer / re-rendering workflows that only need a transfer provider.",
        required_capabilities=("transfer",),
    ),
    WorkflowSpec(
        name="reason-only",
        title="Reason-only workflow",
        description="Scene reasoning workflows that only need a reason-capable provider.",
        required_capabilities=("reason",),
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
        name="evaluation-generation",
        title="Evaluation suite: generation",
        description=(
            "Mirrors the built-in 'generation' evaluation suite's required capability surface."
        ),
        required_capabilities=("generate",),
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
    WorkflowSpec(
        name="evaluation-reasoning",
        title="Evaluation suite: reasoning",
        description=(
            "Mirrors the built-in 'reasoning' evaluation suite's required capability surface."
        ),
        required_capabilities=("reason",),
    ),
    WorkflowSpec(
        name="evaluation-transfer",
        title="Evaluation suite: transfer",
        description=(
            "Mirrors the built-in 'transfer' evaluation suite's required capability surface."
        ),
        required_capabilities=("transfer",),
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
            workflow = negotiation.workflow
            status = "READY" if negotiation.ready else "BLOCKED"
            lines.extend(
                [
                    f"## {workflow.title} (`{workflow.name}`) — {status}",
                    "",
                    workflow.description,
                    "",
                    f"Required capabilities: {', '.join(workflow.required_capabilities)}",
                    f"Summary: {negotiation.summary()}",
                    "",
                ]
            )
            for requirement in negotiation.requirements:
                lines.append(
                    f"### Capability: `{requirement.capability}` "
                    f"({'ready' if requirement.ready else 'blocked'})"
                )
                lines.append("")
                header = (
                    "| provider | registered | capability | configured | "
                    "healthy | readiness | reason |"
                )
                lines.append(header)
                lines.append("| --- | --- | --- | --- | --- | --- | --- |")
                lines.extend(
                    f"| {status.name} | "
                    f"{'yes' if status.registered else 'no'} | "
                    f"{'yes' if status.capability_compatible else 'no'} | "
                    f"{'yes' if status.configured else 'no'} | "
                    f"{'yes' if status.healthy else 'no'} | "
                    f"{status.readiness} | "
                    f"{status.reason or '-'} |"
                    for status in requirement.candidates
                )
                if requirement.recommended_action:
                    lines.append("")
                    lines.append(f"Next step: {requirement.recommended_action}")
                lines.append("")
            if negotiation.recommended_actions and not negotiation.ready:
                lines.append("### Recommended actions")
                lines.append("")
                lines.extend(f"- {action}" for action in negotiation.recommended_actions)
                lines.append("")
        return "\n".join(lines).rstrip() + "\n"


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
    capability_compatible = capabilities.supports(capability)
    if not capability_compatible:
        return CapabilityProviderStatus(
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
        provider = forge._require_provider(name)
        configured = bool(provider.configured())
        try:
            healthy = bool(provider.health().healthy)
        except Exception:
            healthy = False
        if configured and healthy:
            return CapabilityProviderStatus(
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
            return CapabilityProviderStatus(
                name=name,
                capability=capability,
                registered=True,
                capability_compatible=True,
                configured=False,
                healthy=healthy,
                readiness=_READINESS_MISSING_CONFIG,
                reason=missing or f"provider '{name}' reports configured() == False",
            )
        return CapabilityProviderStatus(
            name=name,
            capability=capability,
            registered=True,
            capability_compatible=True,
            configured=True,
            healthy=False,
            readiness=_READINESS_MISSING_DEPENDENCY,
            reason=f"provider '{name}' health check is unhealthy",
        )

    missing = _runtime_profile_missing_reason(name, environ)
    if missing is not None:
        return CapabilityProviderStatus(
            name=name,
            capability=capability,
            registered=False,
            capability_compatible=True,
            configured=False,
            healthy=False,
            readiness=_READINESS_MISSING_CONFIG,
            reason=missing,
        )
    return CapabilityProviderStatus(
        name=name,
        capability=capability,
        registered=False,
        capability_compatible=True,
        configured=False,
        healthy=False,
        readiness=_READINESS_NOT_REGISTERED,
        reason=f"provider '{name}' is known but not registered on this forge",
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
    selected: list[WorkflowSpec] = []
    if workflows is None:
        selected.extend(_WORKFLOWS)
    else:
        for workflow in workflows:
            if isinstance(workflow, WorkflowSpec):
                selected.append(workflow)
            else:
                selected.append(get_workflow(str(workflow)))

    negotiations: list[WorkflowNegotiation] = []
    for workflow in selected:
        requirements: list[CapabilityRequirement] = []
        for capability in workflow.required_capabilities:
            statuses: list[CapabilityProviderStatus] = []
            for name, capabilities, registered in _capability_compatible_providers(
                capability, active_forge
            ):
                statuses.append(
                    _classify_provider(
                        name=name,
                        capability=capability,
                        capabilities=capabilities,
                        registered=registered,
                        forge=active_forge,
                        environ=env,
                    )
                )
            ready = any(status.is_ready() for status in statuses)
            recommended = None if ready else _build_recommended_action(capability, statuses)
            requirements.append(
                CapabilityRequirement(
                    capability=capability,
                    ready=ready,
                    candidates=tuple(statuses),
                    recommended_action=recommended,
                )
            )
        ready_overall = all(requirement.ready for requirement in requirements)
        actions: list[str] = []
        seen_actions: set[str] = set()
        for requirement in requirements:
            if (
                requirement.recommended_action
                and requirement.recommended_action not in seen_actions
            ):
                actions.append(requirement.recommended_action)
                seen_actions.add(requirement.recommended_action)
        negotiations.append(
            WorkflowNegotiation(
                workflow=workflow,
                requirements=tuple(requirements),
                ready=ready_overall,
                recommended_actions=tuple(actions),
            )
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

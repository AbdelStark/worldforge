"""Textual-free provider connector readiness summaries for TheWorldHarness."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from worldforge.framework import WorldForge
from worldforge.models import JSONDict, ProviderDoctorStatus
from worldforge.providers.runtime_manifest import load_runtime_manifest

ConnectorStatus = Literal[
    "configured",
    "missing_credentials",
    "missing_dependency",
    "unhealthy",
    "scaffold",
]


@dataclass(frozen=True, slots=True)
class ProviderConnectorSummary:
    """Operator-facing readiness row for one known provider."""

    name: str
    status: ConnectorStatus
    registered: bool
    health: str
    capabilities: tuple[str, ...]
    implementation_status: str
    required_env_vars: tuple[str, ...]
    missing_env_vars: tuple[str, ...]
    optional_dependencies: tuple[str, ...]
    smoke_command: str
    triage_steps: tuple[str, ...]

    def to_dict(self) -> JSONDict:
        return {
            "name": self.name,
            "status": self.status,
            "registered": self.registered,
            "health": self.health,
            "capabilities": list(self.capabilities),
            "implementation_status": self.implementation_status,
            "required_env_vars": list(self.required_env_vars),
            "missing_env_vars": list(self.missing_env_vars),
            "optional_dependencies": list(self.optional_dependencies),
            "smoke_command": self.smoke_command,
            "triage_steps": list(self.triage_steps),
        }


def provider_connector_summaries(forge: WorldForge) -> tuple[ProviderConnectorSummary, ...]:
    """Return known provider readiness rows without importing Textual."""

    doctor = forge.doctor(registered_only=False)
    rows = [_summary_from_status(status, forge=forge) for status in doctor.providers]
    return tuple(sorted(rows, key=lambda row: row.name))


def provider_connector_summary_markdown(rows: tuple[ProviderConnectorSummary, ...]) -> str:
    """Render connector readiness rows as a compact Markdown table."""

    lines = [
        "# Provider Connector Workspace",
        "",
        "| Provider | Status | Capabilities | Required env | Next command |",
        "| --- | --- | --- | --- | --- |",
    ]
    for row in rows:
        capabilities = ", ".join(f"`{name}`" for name in row.capabilities) or "none"
        required = ", ".join(f"`{name}`" for name in row.required_env_vars) or "none"
        lines.append(
            "| "
            f"`{row.name}` | "
            f"`{row.status}` | "
            f"{capabilities} | "
            f"{required} | "
            f"`{row.smoke_command}` |"
        )
    return "\n".join(lines)


def _summary_from_status(
    status: ProviderDoctorStatus,
    *,
    forge: WorldForge,
) -> ProviderConnectorSummary:
    profile = status.profile
    manifest = _runtime_manifest(profile.name)
    config = forge.provider_config_summary(profile.name)
    missing_env_vars = tuple(
        str(field["name"])
        for field in config.to_dict()["fields"]
        if field.get("required") and not field.get("present")
    )
    optional_dependencies = manifest.optional_dependencies if manifest is not None else ()
    health_detail = status.health.details
    connector_status = _connector_status(
        implementation_status=profile.implementation_status,
        configured=config.configured,
        healthy=status.health.healthy,
        health_detail=health_detail,
    )
    smoke_command = (
        manifest.minimum_smoke_command
        if manifest is not None
        else f"uv run worldforge provider info {profile.name} --format json"
    )
    triage_steps = _triage_steps(
        name=profile.name,
        status=connector_status,
        missing_env_vars=missing_env_vars,
        smoke_command=smoke_command,
    )
    return ProviderConnectorSummary(
        name=profile.name,
        status=connector_status,
        registered=status.registered,
        health=health_detail,
        capabilities=tuple(profile.capabilities.enabled_names()),
        implementation_status=profile.implementation_status,
        required_env_vars=tuple(profile.required_env_vars),
        missing_env_vars=missing_env_vars,
        optional_dependencies=optional_dependencies,
        smoke_command=smoke_command,
        triage_steps=triage_steps,
    )


def _connector_status(
    *,
    implementation_status: str,
    configured: bool,
    healthy: bool,
    health_detail: str,
) -> ConnectorStatus:
    if implementation_status == "scaffold":
        return "scaffold"
    if healthy:
        return "configured"
    if not configured:
        return "missing_credentials"
    if "missing optional dependency" in health_detail.lower():
        return "missing_dependency"
    return "unhealthy"


def _triage_steps(
    *,
    name: str,
    status: ConnectorStatus,
    missing_env_vars: tuple[str, ...],
    smoke_command: str,
) -> tuple[str, ...]:
    if status == "configured":
        return (smoke_command,)
    if status == "missing_credentials":
        missing = ", ".join(missing_env_vars) or "required provider environment"
        return (
            f"Configure {missing}.",
            f"uv run worldforge provider info {name} --format json",
        )
    if status == "missing_dependency":
        return (
            "Install the provider runtime in the host environment.",
            smoke_command,
        )
    if status == "scaffold":
        return (
            "Treat this provider as a fail-closed scaffold.",
            f"uv run worldforge provider info {name} --format json",
        )
    return (
        f"uv run worldforge provider health {name} --format json",
        smoke_command,
    )


def _runtime_manifest(provider: str):
    try:
        return load_runtime_manifest(provider)
    except Exception:
        return None

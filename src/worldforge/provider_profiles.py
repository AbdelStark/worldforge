"""Provider capability and profile model contracts."""

from __future__ import annotations

from dataclasses import dataclass, field

from worldforge._model_utils import (
    JSONDict,
    WorldForgeError,
    require_bool,
)
from worldforge.provider_request_policy import ProviderRequestPolicy

CAPABILITY_NAMES = (
    "predict",
    "embed",
    "plan",
    "score",
    "policy",
)


@dataclass(slots=True)
class ProviderCapabilities:
    """Boolean capability matrix for a provider.

    All flags default to ``False``. Provider adapters must opt into each callable surface
    explicitly so unsupported workflows fail at capability resolution instead of falling through to
    mock behavior or ad hoc string checks.
    """

    predict: bool = False
    embed: bool = False
    plan: bool = False
    score: bool = False
    policy: bool = False

    def __post_init__(self) -> None:
        for capability in CAPABILITY_NAMES:
            setattr(
                self,
                capability,
                require_bool(
                    getattr(self, capability),
                    name=f"ProviderCapabilities {capability}",
                ),
            )

    def to_dict(self) -> JSONDict:
        return {name: getattr(self, name) for name in CAPABILITY_NAMES}

    def supports(self, capability: str) -> bool:
        """Return whether a known capability is enabled.

        Unknown names raise ``WorldForgeError`` because a typo in routing or diagnostics should not
        silently behave like an unsupported provider.
        """

        if not isinstance(capability, str) or capability not in CAPABILITY_NAMES:
            known = ", ".join(CAPABILITY_NAMES)
            raise WorldForgeError(
                f"Unknown provider capability '{capability}'. Known capabilities: {known}."
            )
        return bool(getattr(self, capability))

    def enabled_names(self) -> list[str]:
        """Return the canonical names of every capability set to ``True``.

        The order matches :data:`CAPABILITY_NAMES` so diagnostics, CLI output, and reports
        render capabilities consistently across providers.
        """

        return [name for name in CAPABILITY_NAMES if getattr(self, name)]


@dataclass(slots=True)
class ProviderInfo:
    """Provider metadata returned by registry APIs."""

    name: str
    capabilities: ProviderCapabilities
    is_local: bool
    description: str = ""

    def to_dict(self) -> JSONDict:
        return {
            "name": self.name,
            "capabilities": self.capabilities.to_dict(),
            "is_local": self.is_local,
            "description": self.description,
        }


@dataclass(slots=True)
class ProviderProfile:
    """Provider profile metadata for routing and diagnostics."""

    name: str
    capabilities: ProviderCapabilities
    is_local: bool
    description: str = ""
    package: str = "worldforge"
    implementation_status: str = "experimental"
    deterministic: bool = False
    requires_credentials: bool = False
    credential_env_var: str | None = None
    required_env_vars: list[str] = field(default_factory=list)
    supported_modalities: list[str] = field(default_factory=list)
    artifact_types: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    default_model: str | None = None
    supported_models: list[str] = field(default_factory=list)
    request_policy: ProviderRequestPolicy | None = None

    @property
    def supported_tasks(self) -> list[str]:
        return self.capabilities.enabled_names()

    def to_dict(self) -> JSONDict:
        return {
            "name": self.name,
            "capabilities": self.capabilities.to_dict(),
            "supported_tasks": self.supported_tasks,
            "is_local": self.is_local,
            "description": self.description,
            "package": self.package,
            "implementation_status": self.implementation_status,
            "deterministic": self.deterministic,
            "requires_credentials": self.requires_credentials,
            "credential_env_var": self.credential_env_var,
            "required_env_vars": list(self.required_env_vars),
            "supported_modalities": list(self.supported_modalities),
            "artifact_types": list(self.artifact_types),
            "notes": list(self.notes),
            "default_model": self.default_model,
            "supported_models": list(self.supported_models),
            "request_policy": self.request_policy.to_dict() if self.request_policy else None,
        }

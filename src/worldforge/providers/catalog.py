"""Provider catalog and registration policy for WorldForge."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from worldforge.models import ProviderEvent

from .base import BaseProvider

# Concrete provider classes are imported lazily inside each factory below so
# that `import worldforge.providers.catalog` (reached at CLI cold start through
# `framework.py`) doesn't drag every optional-runtime adapter module into the
# module cache when only one is ever used.

ProviderEventHandler = Callable[[ProviderEvent], None] | None
ProviderFactory = Callable[[ProviderEventHandler], BaseProvider]
DOC_CAPABILITY_ORDER = (
    "predict",
    "generate",
    "transfer",
    "score",
    "policy",
    "reason",
    "embed",
    "plan",
)
PROVIDER_PROMOTION_STATUSES = ("scaffold", "experimental", "beta", "stable")


@dataclass(frozen=True, slots=True)
class ProviderCatalogEntry:
    """Factory and registration policy for an in-repo provider adapter."""

    name: str
    factory: ProviderFactory
    always_register: bool = False
    docs_page: str | None = None
    runtime_ownership: str = "host-owned runtime"

    def create(self, *, event_handler: ProviderEventHandler = None) -> BaseProvider:
        return self.factory(event_handler)

    def display_name(self, *, docs_link_prefix: str = "./") -> str:
        if self.docs_page:
            docs_path = self.docs_page
            if docs_link_prefix.startswith("http") and docs_path.endswith(".md"):
                docs_path = f"{docs_path[:-3]}/"
            return f"[`{self.name}`]({docs_link_prefix}{docs_path})"
        return f"`{self.name}`"


def _mock(event_handler: ProviderEventHandler = None) -> BaseProvider:
    from .mock import MockProvider

    return MockProvider(event_handler=event_handler)


def _cosmos(event_handler: ProviderEventHandler = None) -> BaseProvider:
    from .cosmos import CosmosProvider

    return CosmosProvider(event_handler=event_handler)


def _runway(event_handler: ProviderEventHandler = None) -> BaseProvider:
    from .runway import RunwayProvider

    return RunwayProvider(event_handler=event_handler)


def _leworldmodel(event_handler: ProviderEventHandler = None) -> BaseProvider:
    from .leworldmodel import LeWorldModelProvider

    return LeWorldModelProvider(event_handler=event_handler)


def _gr00t(event_handler: ProviderEventHandler = None) -> BaseProvider:
    from .gr00t import GrootPolicyClientProvider

    return GrootPolicyClientProvider(event_handler=event_handler)


def _lerobot(event_handler: ProviderEventHandler = None) -> BaseProvider:
    from .lerobot import LeRobotPolicyProvider

    return LeRobotPolicyProvider(event_handler=event_handler)


def _jepa(event_handler: ProviderEventHandler = None) -> BaseProvider:
    from .remote import JepaProvider

    return JepaProvider(event_handler=event_handler)


def _genie(event_handler: ProviderEventHandler = None) -> BaseProvider:
    from .remote import GenieProvider

    return GenieProvider(event_handler=event_handler)


PROVIDER_CATALOG: tuple[ProviderCatalogEntry, ...] = (
    ProviderCatalogEntry(
        "mock",
        _mock,
        always_register=True,
        runtime_ownership="in-repo deterministic local provider",
    ),
    ProviderCatalogEntry(
        "cosmos",
        _cosmos,
        docs_page="cosmos.md",
        runtime_ownership=(
            "host supplies a reachable Cosmos deployment and optional `NVIDIA_API_KEY`"
        ),
    ),
    ProviderCatalogEntry(
        "runway",
        _runway,
        docs_page="runway.md",
        runtime_ownership="host supplies Runway credentials and persists returned artifacts",
    ),
    ProviderCatalogEntry(
        "leworldmodel",
        _leworldmodel,
        docs_page="leworldmodel.md",
        runtime_ownership=(
            "host installs the official LeWM loading path "
            "(`stable_worldmodel.policy.AutoCostModel`), torch, and compatible checkpoints"
        ),
    ),
    ProviderCatalogEntry(
        "gr00t",
        _gr00t,
        docs_page="gr00t.md",
        runtime_ownership="host runs or reaches an Isaac GR00T policy server",
    ),
    ProviderCatalogEntry(
        "lerobot",
        _lerobot,
        docs_page="lerobot.md",
        runtime_ownership="host installs LeRobot and compatible policy checkpoints",
    ),
    ProviderCatalogEntry(
        "jepa",
        _jepa,
        runtime_ownership="capability-fail-closed reservation, not a real JEPA runtime",
    ),
    ProviderCatalogEntry(
        "genie",
        _genie,
        runtime_ownership="capability-fail-closed reservation, not a real Genie runtime",
    ),
)


def create_known_providers(
    *, event_handler: ProviderEventHandler = None
) -> tuple[BaseProvider, ...]:
    """Instantiate every in-repo provider adapter without registering it."""

    return tuple(entry.create(event_handler=event_handler) for entry in PROVIDER_CATALOG)


def render_provider_catalog_markdown(*, docs_link_prefix: str = "./") -> str:
    """Render the provider catalog table used by the provider documentation index."""

    lines = [
        "| Provider | Maturity | Capability surface | Registration | Runtime ownership |",
        "| --- | --- | --- | --- | --- |",
    ]
    for entry in PROVIDER_CATALOG:
        profile = entry.create().profile()
        if profile.implementation_status == "scaffold":
            capability_surface = "scaffold"
        else:
            capability_surface = ", ".join(
                f"`{task}`" for task in DOC_CAPABILITY_ORDER if profile.capabilities.supports(task)
            )
        if entry.always_register:
            registration = "always registered"
        elif profile.required_env_vars:
            registration = " or ".join(f"`{env_var}`" for env_var in profile.required_env_vars)
        else:
            registration = "direct construction"
        lines.append(
            "| "
            f"{entry.display_name(docs_link_prefix=docs_link_prefix)} | "
            f"`{profile.implementation_status}` | "
            f"{capability_surface} | "
            f"{registration} | "
            f"{entry.runtime_ownership} |"
        )
    return "\n".join(lines)


def provider_docs_index(
    *, docs_path_prefix: str = "docs/src/providers/"
) -> tuple[dict[str, str], ...]:
    """Return provider documentation metadata for CLI discovery surfaces."""

    docs: list[dict[str, str]] = []
    for entry in PROVIDER_CATALOG:
        profile = entry.create().profile()
        docs_path = (
            f"{docs_path_prefix}{entry.docs_page}"
            if entry.docs_page
            else f"{docs_path_prefix}README.md"
        )
        if profile.implementation_status == "scaffold":
            capabilities = "scaffold"
        else:
            capabilities = ", ".join(
                task for task in DOC_CAPABILITY_ORDER if profile.capabilities.supports(task)
            )
        docs.append(
            {
                "name": entry.name,
                "docs_path": docs_path,
                "implementation_status": profile.implementation_status,
                "capabilities": capabilities,
                "registration": (
                    "always registered"
                    if entry.always_register
                    else " or ".join(profile.required_env_vars)
                    if profile.required_env_vars
                    else "direct construction"
                ),
                "runtime_ownership": entry.runtime_ownership,
            }
        )
    return tuple(docs)

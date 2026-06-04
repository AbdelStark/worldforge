"""Internal provider view over legacy providers and capability adapters."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from worldforge._provider_merge import (
    merged_provider_health,
    merged_provider_lifecycle_status,
    merged_provider_profile,
    provider_health_components,
    provider_lifecycle_components,
    provider_missing_configuration,
)
from worldforge.models import (
    ProviderHealth,
    ProviderLifecycleStatus,
    ProviderProfile,
)
from worldforge.providers import BaseProvider, ProviderConfigSummary, ProviderError
from worldforge.providers.observable import _ObservableCapability


@dataclass(slots=True, frozen=True)
class ProviderView:
    """Merged runtime view for one provider name.

    A provider name can be backed by a legacy :class:`BaseProvider`, one or more capability
    adapters, or both during the protocol migration. This module keeps that compatibility knowledge
    behind one interface so diagnostics, benchmark metrics, and framework public methods do not
    reassemble it themselves.
    """

    name: str
    legacy_provider: BaseProvider | None = None
    wrappers: tuple[_ObservableCapability, ...] = ()
    registered: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "wrappers", tuple(self.wrappers))
        if self.legacy_provider is None and not self.wrappers:
            raise ProviderError(f"Provider '{self.name}' is unknown.")

    def profile(self) -> ProviderProfile:
        return merged_provider_profile(
            name=self.name,
            legacy_provider=self.legacy_provider,
            wrappers=self.wrappers,
        )

    def health(self) -> ProviderHealth:
        return merged_provider_health(
            self.name,
            provider_health_components(
                legacy_provider=self.legacy_provider,
                wrappers=self.wrappers,
            ),
        )

    def lifecycle_status(
        self,
        *,
        run_warmup: bool = False,
        run_teardown: bool = False,
    ) -> ProviderLifecycleStatus:
        return merged_provider_lifecycle_status(
            self.name,
            provider_lifecycle_components(
                legacy_provider=self.legacy_provider,
                wrappers=self.wrappers,
                run_warmup=run_warmup,
                run_teardown=run_teardown,
            ),
        )

    def config_summary(self) -> ProviderConfigSummary:
        if self.legacy_provider is not None:
            return self.legacy_provider.config_summary()
        return ProviderConfigSummary(provider=self.name, configured=True, fields=())

    def missing_configuration(self, profile: ProviderProfile) -> bool:
        return provider_missing_configuration(
            profile=profile,
            legacy_provider=self.legacy_provider,
            wrappers=self.wrappers,
        )

    @property
    def metric_legacy_provider(self) -> BaseProvider | None:
        return self.legacy_provider

    @property
    def metric_wrappers(self) -> tuple[_ObservableCapability, ...]:
        return self.wrappers


def provider_views_for_names(
    names: Sequence[str],
    *,
    registered_names: set[str],
    legacy_catalog: dict[str, BaseProvider],
    wrappers_for_name: dict[str, tuple[_ObservableCapability, ...]],
) -> list[ProviderView]:
    """Build provider views in caller-supplied order."""

    return [
        ProviderView(
            name=name,
            legacy_provider=legacy_catalog.get(name),
            wrappers=wrappers_for_name.get(name, ()),
            registered=name in registered_names,
        )
        for name in names
    ]


__all__ = ["ProviderView", "provider_views_for_names"]

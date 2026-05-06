"""Provider entry-point discovery for external WorldForge adapter packages.

External adapter packages can register provider factories without modifying the WorldForge
repository by exposing them through the ``worldforge.providers`` Python entry-point group.

Example ``pyproject.toml`` for an external package:

    [project.entry-points."worldforge.providers"]
    my-policy = "my_pkg.adapters:make_my_policy_provider"

The referenced callable takes a single optional ``event_handler`` argument and returns a
:class:`~worldforge.providers.base.BaseProvider` whose ``name`` matches the entry-point name.
WorldForge wraps the result in a :class:`~worldforge.providers.catalog.ProviderCatalogEntry`
with ``always_register=False`` and the standard env-gated auto-registration rules apply: the
provider only registers if its ``configured()`` check passes.

Discovery is opt-in and never crashes the host. Entry points whose modules fail to import,
whose factories raise, that duplicate an in-repo provider name, or that fail public-input
validation are recorded with a typed reason on :class:`EntryPointDiscoveryReport.skipped`.

This surface is **provisional** — the entry-point group name and discovery report shape are
stable for the current release, but downstream tooling should treat ``EntryPointSkip.reason``
strings as human-readable rather than machine-parseable.
"""

from __future__ import annotations

import os
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from importlib import metadata as importlib_metadata
from typing import Any

from worldforge.models import JSONDict, WorldForgeError

from .base import BaseProvider
from .catalog import ProviderCatalogEntry, ProviderEventHandler

ENTRY_POINT_GROUP = "worldforge.providers"
"""Canonical entry-point group external packages register provider factories under."""

ENTRY_POINT_DISABLE_ENV_VAR = "WORLDFORGE_DISABLE_ENTRY_POINTS"
"""When set to a non-empty value, suppresses entry-point discovery entirely."""


@dataclass(frozen=True, slots=True)
class EntryPointSkip:
    """One entry-point that could not be wrapped into a catalog entry."""

    name: str
    value: str
    reason: str

    def to_dict(self) -> JSONDict:
        return {"name": self.name, "value": self.value, "reason": self.reason}


@dataclass(frozen=True, slots=True)
class EntryPointDiscoveryReport:
    """Result of running entry-point discovery once."""

    enabled: bool
    entries: tuple[ProviderCatalogEntry, ...]
    skipped: tuple[EntryPointSkip, ...]
    group: str = ENTRY_POINT_GROUP

    @property
    def discovered_count(self) -> int:
        return len(self.entries)

    @property
    def skipped_count(self) -> int:
        return len(self.skipped)

    def to_dict(self) -> JSONDict:
        return {
            "enabled": self.enabled,
            "group": self.group,
            "discovered": [
                {
                    "name": entry.name,
                    "runtime_ownership": entry.runtime_ownership,
                    "always_register": entry.always_register,
                    "docs_page": entry.docs_page,
                }
                for entry in self.entries
            ],
            "skipped": [skip.to_dict() for skip in self.skipped],
        }


def _is_disabled(environ: Mapping[str, str] | None) -> bool:
    env = os.environ if environ is None else environ
    value = env.get(ENTRY_POINT_DISABLE_ENV_VAR, "").strip()
    return bool(value)


def _default_entry_points(group: str) -> Iterable[importlib_metadata.EntryPoint]:
    return importlib_metadata.entry_points(group=group)


def _wrap_factory(factory: Callable[..., Any], name: str) -> Callable[..., BaseProvider]:
    def _entry_point_factory(event_handler: ProviderEventHandler = None) -> BaseProvider:
        try:
            provider = factory(event_handler=event_handler)
        except TypeError:
            # External factories that do not accept the keyword argument form still
            # need to thread the event handler through. Fall back to positional once
            # before propagating the original error to the caller.
            provider = factory(event_handler)
        if not isinstance(provider, BaseProvider):
            raise WorldForgeError(
                f"Entry-point '{name}' factory returned {type(provider).__name__}, "
                "expected BaseProvider."
            )
        if provider.name != name:
            raise WorldForgeError(
                f"Entry-point '{name}' factory returned provider named '{provider.name}'; "
                "the names must match."
            )
        return provider

    return _entry_point_factory


def discover_entry_point_providers(
    *,
    enabled: bool | None = None,
    catalog: Iterable[ProviderCatalogEntry] = (),
    environ: Mapping[str, str] | None = None,
    entry_points_provider: Callable[[str], Iterable[importlib_metadata.EntryPoint]] | None = None,
    group: str = ENTRY_POINT_GROUP,
) -> EntryPointDiscoveryReport:
    """Discover external provider factories exposed via the ``worldforge.providers`` group.

    ``enabled`` defaults to ``True`` unless ``WORLDFORGE_DISABLE_ENTRY_POINTS`` is set in
    ``environ``. ``catalog`` is the in-repo catalog whose names take precedence: an external
    entry-point that re-uses an in-repo name is skipped with a typed reason rather than
    silently shadowing the built-in. ``entry_points_provider`` is an injection seam for tests
    so they can supply a fixed ``EntryPoint`` set without modifying the host's installed
    distributions.
    """

    if enabled is None:
        enabled = not _is_disabled(environ)
    if not enabled:
        return EntryPointDiscoveryReport(
            enabled=False,
            entries=(),
            skipped=(),
            group=group,
        )

    finder = entry_points_provider or _default_entry_points
    reserved_names = {entry.name for entry in catalog}
    seen_names: set[str] = set()
    entries: list[ProviderCatalogEntry] = []
    skipped: list[EntryPointSkip] = []

    try:  # pragma: no cover - importlib.metadata.entry_points is stable, defensive only
        candidates = list(finder(group))
    except Exception as exc:  # pragma: no cover - defensive only
        return EntryPointDiscoveryReport(
            enabled=True,
            entries=(),
            skipped=(EntryPointSkip(name="*", value="", reason=f"discovery failed: {exc}"),),
            group=group,
        )

    for ep in candidates:
        ep_name = getattr(ep, "name", "") or ""
        ep_value = getattr(ep, "value", "") or ""
        if not ep_name.strip():
            skipped.append(EntryPointSkip(name="?", value=ep_value, reason="empty name"))
            continue
        if ep_name in reserved_names:
            skipped.append(
                EntryPointSkip(
                    name=ep_name,
                    value=ep_value,
                    reason="duplicate name (in-repo provider already registered)",
                )
            )
            continue
        if ep_name in seen_names:
            skipped.append(
                EntryPointSkip(
                    name=ep_name,
                    value=ep_value,
                    reason="duplicate name (already discovered earlier in this group)",
                )
            )
            continue
        try:
            factory = ep.load()
        except (ImportError, ModuleNotFoundError) as exc:
            skipped.append(
                EntryPointSkip(
                    name=ep_name,
                    value=ep_value,
                    reason=f"missing dependency: {exc}",
                )
            )
            continue
        except Exception as exc:
            skipped.append(
                EntryPointSkip(
                    name=ep_name,
                    value=ep_value,
                    reason=f"load failed: {exc}",
                )
            )
            continue
        if not callable(factory):
            skipped.append(
                EntryPointSkip(
                    name=ep_name,
                    value=ep_value,
                    reason="entry point did not resolve to a callable",
                )
            )
            continue
        entries.append(
            ProviderCatalogEntry(
                name=ep_name,
                factory=_wrap_factory(factory, ep_name),
                always_register=False,
                runtime_ownership=f"external entry point ({ep_value})",
            )
        )
        seen_names.add(ep_name)

    return EntryPointDiscoveryReport(
        enabled=True,
        entries=tuple(entries),
        skipped=tuple(skipped),
        group=group,
    )


__all__ = [
    "ENTRY_POINT_DISABLE_ENV_VAR",
    "ENTRY_POINT_GROUP",
    "EntryPointDiscoveryReport",
    "EntryPointSkip",
    "discover_entry_point_providers",
]

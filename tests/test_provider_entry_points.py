"""Tests for the provider entry-point discovery surface (WF-FEAT-001)."""

from __future__ import annotations

from collections.abc import Iterable
from importlib.metadata import EntryPoint

import pytest

from worldforge import (
    ENTRY_POINT_DISABLE_ENV_VAR,
    ENTRY_POINT_GROUP,
    EntryPointDiscoveryReport,
    EntryPointSkip,
    ProviderCapabilities,
    WorldForge,
    discover_entry_point_providers,
)
from worldforge.providers import BaseProvider, ProviderProfileSpec
from worldforge.providers.catalog import PROVIDER_CATALOG, ProviderCatalogEntry


class _FakeProvider(BaseProvider):
    def __init__(self, *, name: str = "fake-entry-point", event_handler=None) -> None:
        super().__init__(
            name=name,
            capabilities=ProviderCapabilities(predict=True),
            profile=ProviderProfileSpec(
                description="External entry-point provider used in WF-FEAT-001 tests."
            ),
            event_handler=event_handler,
        )


def _make_factory(name: str = "fake-entry-point"):
    def factory(event_handler=None) -> _FakeProvider:
        return _FakeProvider(name=name, event_handler=event_handler)

    return factory


def _entry_points_provider(*entries: tuple[str, object]):
    """Return a provider that emulates importlib.metadata.entry_points(group=...).

    Each entry is a (name, factory_or_loader) pair. ``factory_or_loader`` may either be the
    factory callable (loaded directly) or a callable that itself raises when ``load`` runs,
    which simulates missing-dependency cases.
    """

    def stub(group: str) -> Iterable[EntryPoint]:
        if group != ENTRY_POINT_GROUP:
            return ()
        out: list[EntryPoint] = []
        for name, target in entries:
            ep = EntryPoint(
                name=name,
                value=f"tests.fake:{name}",
                group=group,
            )
            object.__setattr__(ep, "_target", target)
            out.append(ep)
        return out

    return stub


def _patch_load(monkeypatch: pytest.MonkeyPatch) -> None:
    """Patch EntryPoint.load to return the per-instance ``_target`` set by the stub."""

    def load(self):  # type: ignore[no-untyped-def]
        target = getattr(self, "_target", None)
        if isinstance(target, BaseException):
            raise target
        if callable(target) and getattr(target, "__raises__", False):
            target()  # raises on call; mimics import errors during load
        return target

    monkeypatch.setattr(EntryPoint, "load", load)


def test_discovery_disabled_returns_empty_report() -> None:
    report = discover_entry_point_providers(enabled=False)
    assert report.enabled is False
    assert report.entries == ()
    assert report.skipped == ()


def test_discovery_disabled_via_env_var(monkeypatch) -> None:
    monkeypatch.setenv(ENTRY_POINT_DISABLE_ENV_VAR, "1")
    report = discover_entry_point_providers()
    assert report.enabled is False
    assert report.discovered_count == 0


def test_discovery_loads_valid_entry_point(monkeypatch) -> None:
    _patch_load(monkeypatch)
    factory = _make_factory()
    report = discover_entry_point_providers(
        enabled=True,
        catalog=PROVIDER_CATALOG,
        entry_points_provider=_entry_points_provider(("fake-entry-point", factory)),
    )
    assert report.enabled is True
    assert report.discovered_count == 1
    assert report.entries[0].name == "fake-entry-point"
    assert "external entry point" in report.entries[0].runtime_ownership
    provider = report.entries[0].create()
    assert isinstance(provider, _FakeProvider)
    assert provider.name == "fake-entry-point"


def test_discovery_skips_missing_dependency(monkeypatch) -> None:
    _patch_load(monkeypatch)
    raiser = ImportError("optional torch backend not installed")
    report = discover_entry_point_providers(
        enabled=True,
        catalog=PROVIDER_CATALOG,
        entry_points_provider=_entry_points_provider(("needs-torch", raiser)),
    )
    assert report.discovered_count == 0
    assert report.skipped_count == 1
    skip = report.skipped[0]
    assert skip.name == "needs-torch"
    assert "missing dependency" in skip.reason


def test_discovery_rejects_duplicate_in_repo_name(monkeypatch) -> None:
    _patch_load(monkeypatch)
    factory = _make_factory(name="mock")
    report = discover_entry_point_providers(
        enabled=True,
        catalog=PROVIDER_CATALOG,
        entry_points_provider=_entry_points_provider(("mock", factory)),
    )
    assert report.discovered_count == 0
    assert report.skipped_count == 1
    assert report.skipped[0].name == "mock"
    assert "duplicate name" in report.skipped[0].reason
    assert "in-repo" in report.skipped[0].reason


def test_discovery_rejects_duplicate_within_group(monkeypatch) -> None:
    _patch_load(monkeypatch)
    factory = _make_factory(name="dup-entry")
    report = discover_entry_point_providers(
        enabled=True,
        catalog=PROVIDER_CATALOG,
        entry_points_provider=_entry_points_provider(
            ("dup-entry", factory),
            ("dup-entry", factory),
        ),
    )
    assert report.discovered_count == 1
    assert report.skipped_count == 1
    assert "already discovered" in report.skipped[0].reason


def test_discovery_skips_non_callable(monkeypatch) -> None:
    _patch_load(monkeypatch)
    report = discover_entry_point_providers(
        enabled=True,
        catalog=PROVIDER_CATALOG,
        entry_points_provider=_entry_points_provider(("bad-entry", "not-a-callable")),
    )
    assert report.discovered_count == 0
    assert report.skipped[0].reason == "entry point did not resolve to a callable"


def test_factory_returning_wrong_type_is_rejected_when_invoked(monkeypatch) -> None:
    _patch_load(monkeypatch)

    def bogus_factory(event_handler=None):
        return "definitely not a provider"

    report = discover_entry_point_providers(
        enabled=True,
        catalog=PROVIDER_CATALOG,
        entry_points_provider=_entry_points_provider(("bogus-factory", bogus_factory)),
    )
    assert report.discovered_count == 1
    with pytest.raises(Exception, match="expected BaseProvider"):
        report.entries[0].create()


def test_factory_with_mismatched_provider_name_is_rejected_when_invoked(monkeypatch) -> None:
    _patch_load(monkeypatch)
    factory = _make_factory(name="actually-other-name")
    report = discover_entry_point_providers(
        enabled=True,
        catalog=PROVIDER_CATALOG,
        entry_points_provider=_entry_points_provider(("declared-name", factory)),
    )
    assert report.discovered_count == 1
    with pytest.raises(Exception, match="names must match"):
        report.entries[0].create()


def test_factory_without_keyword_argument_falls_back_to_positional(monkeypatch) -> None:
    _patch_load(monkeypatch)

    def positional_only_factory(event_handler):
        return _FakeProvider(name="positional-fake", event_handler=event_handler)

    report = discover_entry_point_providers(
        enabled=True,
        catalog=PROVIDER_CATALOG,
        entry_points_provider=_entry_points_provider(("positional-fake", positional_only_factory)),
    )
    assert report.discovered_count == 1
    provider = report.entries[0].create()
    assert isinstance(provider, _FakeProvider)


def test_discovery_skips_empty_entry_point_name(monkeypatch) -> None:
    _patch_load(monkeypatch)
    factory = _make_factory()
    report = discover_entry_point_providers(
        enabled=True,
        catalog=PROVIDER_CATALOG,
        entry_points_provider=_entry_points_provider(("", factory)),
    )
    assert report.discovered_count == 0
    assert report.skipped_count == 1
    assert report.skipped[0].reason == "empty name"


def test_discovery_skips_load_failure_other_than_import(monkeypatch) -> None:
    _patch_load(monkeypatch)
    report = discover_entry_point_providers(
        enabled=True,
        catalog=PROVIDER_CATALOG,
        entry_points_provider=_entry_points_provider(
            ("crashy-load", RuntimeError("config decode error")),
        ),
    )
    assert report.discovered_count == 0
    assert "load failed" in report.skipped[0].reason


def test_discovery_report_to_dict_round_trips(monkeypatch) -> None:
    _patch_load(monkeypatch)
    factory = _make_factory()
    report = discover_entry_point_providers(
        enabled=True,
        catalog=PROVIDER_CATALOG,
        entry_points_provider=_entry_points_provider(
            ("fake-entry-point", factory),
            ("mock", factory),
        ),
    )
    payload = report.to_dict()
    assert payload["enabled"] is True
    assert payload["group"] == ENTRY_POINT_GROUP
    assert payload["discovered"][0]["name"] == "fake-entry-point"
    assert payload["skipped"][0]["name"] == "mock"


def test_worldforge_constructor_threads_discovery(tmp_path) -> None:
    forge = WorldForge(state_dir=tmp_path)
    report = forge.entry_point_discovery()
    assert isinstance(report, EntryPointDiscoveryReport)
    assert report.enabled is True


def test_worldforge_constructor_can_disable_discovery(tmp_path) -> None:
    forge = WorldForge(state_dir=tmp_path, discover_entry_points=False)
    report = forge.entry_point_discovery()
    assert report.enabled is False
    assert report.entries == ()


def test_worldforge_disabled_via_env(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv(ENTRY_POINT_DISABLE_ENV_VAR, "yes")
    forge = WorldForge(state_dir=tmp_path)
    assert forge.entry_point_discovery().enabled is False


def test_entry_point_skip_to_dict_shape() -> None:
    skip = EntryPointSkip(name="x", value="pkg:fn", reason="missing dependency: torch")
    assert skip.to_dict() == {"name": "x", "value": "pkg:fn", "reason": "missing dependency: torch"}


def test_top_level_module_exports_entry_point_symbols() -> None:
    import worldforge

    assert worldforge.ENTRY_POINT_GROUP == "worldforge.providers"
    assert worldforge.ENTRY_POINT_DISABLE_ENV_VAR == "WORLDFORGE_DISABLE_ENTRY_POINTS"
    assert worldforge.discover_entry_point_providers is discover_entry_point_providers
    assert worldforge.EntryPointDiscoveryReport is EntryPointDiscoveryReport
    assert worldforge.EntryPointSkip is EntryPointSkip


def test_in_repo_catalog_behavior_unchanged(tmp_path) -> None:
    """The default forge still registers mock and existing in-repo providers."""

    forge = WorldForge(state_dir=tmp_path)
    registered = forge.providers()
    assert "mock" in registered
    expected_names = {entry.name for entry in PROVIDER_CATALOG if entry.always_register}
    assert expected_names <= set(registered)


def test_external_entry_point_factory_failure_records_skip(monkeypatch, tmp_path) -> None:
    """If a discovered factory raises at construction time the forge records a skip."""

    def bad_factory(event_handler=None):
        raise RuntimeError("torch backend missing on this host")

    bad_entry = ProviderCatalogEntry(
        name="brittle-entry",
        factory=bad_factory,
        always_register=False,
        runtime_ownership="external entry point (test)",
    )

    monkeypatch.setattr(
        "worldforge.framework.discover_entry_point_providers",
        lambda *, enabled=None, catalog=PROVIDER_CATALOG: EntryPointDiscoveryReport(
            enabled=True,
            entries=(bad_entry,),
            skipped=(),
        ),
    )

    forge = WorldForge(state_dir=tmp_path)
    assert "brittle-entry" not in forge.providers()
    report = forge.entry_point_discovery()
    assert report.discovered_count == 0
    assert any(skip.name == "brittle-entry" for skip in report.skipped)
    assert any("factory raised" in skip.reason for skip in report.skipped)


def test_external_entry_point_provider_registers_when_configured(monkeypatch, tmp_path) -> None:
    """An entry-point provider whose configured() is True should auto-register."""

    _patch_load(monkeypatch)

    class _AlwaysConfigured(BaseProvider):
        def __init__(self, *, name="external-cfg", event_handler=None):
            super().__init__(
                name=name,
                capabilities=ProviderCapabilities(predict=True),
                profile=ProviderProfileSpec(
                    description="Entry-point provider that reports configured.",
                    is_local=True,
                    deterministic=True,
                    requires_credentials=False,
                ),
                event_handler=event_handler,
            )

        def configured(self) -> bool:  # type: ignore[override]
            return True

    def factory(event_handler=None) -> _AlwaysConfigured:
        return _AlwaysConfigured(event_handler=event_handler)

    monkeypatch.setattr(
        "worldforge.framework.discover_entry_point_providers",
        lambda *, enabled=None, catalog=PROVIDER_CATALOG: EntryPointDiscoveryReport(
            enabled=True,
            entries=(
                ProviderCatalogEntry(
                    name="external-cfg",
                    factory=factory,
                    always_register=False,
                    runtime_ownership="external entry point (test)",
                ),
            ),
            skipped=(),
        ),
    )

    forge = WorldForge(state_dir=tmp_path)
    assert "external-cfg" in forge.providers()
    report = forge.entry_point_discovery()
    assert report.discovered_count == 1

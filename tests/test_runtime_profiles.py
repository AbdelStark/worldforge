from __future__ import annotations

import importlib
from importlib.metadata import entry_points
from typing import Any

import pytest

import worldforge.testing as testing_helpers
from worldforge.testing.runtime_profiles import (
    PROVIDER_RUNTIME_PROFILES_BY_NAME,
    ProviderRuntimeProfile,
    provider_profile_skip_reason,
    pytest_marker_definitions,
    runtime_marker_skip_reason,
)

pytest_plugins = ("pytester",)


def test_testing_helper_lazy_exports_reload_under_coverage() -> None:
    reloaded = importlib.reload(testing_helpers)

    assert "ProviderContractReport" in dir(reloaded)
    assert reloaded.ProviderRuntimeProfile is ProviderRuntimeProfile

    missing_name = "missing_testing_helper"
    with pytest.raises(AttributeError, match=missing_name):
        getattr(reloaded, missing_name)


def test_runtime_profiles_reload_and_required_env_contract(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import worldforge.testing.runtime_profiles as runtime_profiles

    reloaded = importlib.reload(runtime_profiles)
    profile = reloaded.ProviderRuntimeProfile(
        name="demo",
        required_env_vars=("DEMO_ENDPOINT",),
    )

    assert profile.missing_reason({"DEMO_ENDPOINT": " "}) == "missing DEMO_ENDPOINT"
    assert profile.missing_reason({"DEMO_ENDPOINT": "https://example.test"}) is None

    monkeypatch.setenv("DEMO_ENDPOINT", "https://example.test")
    assert profile.missing_reason() is None
    assert "RuntimeMarker" in reloaded.__all__


def test_runtime_markers_require_explicit_opt_in() -> None:
    reason = runtime_marker_skip_reason("live", {"run_live": False})

    assert reason == "requires an explicit --run-live opt-in"
    assert runtime_marker_skip_reason("live", {"run_live": True}) is None
    assert runtime_marker_skip_reason("not-a-marker", {}) is None


def test_provider_profile_reports_missing_any_env_group() -> None:
    reason = provider_profile_skip_reason("runway", {})

    assert reason == (
        "provider profile 'runway' is not configured: "
        "missing RUNWAYML_API_SECRET or RUNWAY_API_SECRET"
    )


def test_provider_profile_accepts_any_env_alias() -> None:
    reason = provider_profile_skip_reason("runway", {"RUNWAY_API_SECRET": "secret"})

    assert reason is None


def test_provider_profile_reports_unknown_profile() -> None:
    reason = provider_profile_skip_reason("missing-provider", {})

    assert reason == "unknown provider runtime profile: missing-provider"


def test_marker_definitions_cover_runtime_profiles() -> None:
    definitions = "\n".join(pytest_marker_definitions())

    assert "live:" in definitions
    assert "provider_profile(name)" in definitions
    assert set(PROVIDER_RUNTIME_PROFILES_BY_NAME) == {
        "cosmos",
        "cosmos-policy",
        "runway",
        "leworldmodel",
        "gr00t",
        "lerobot",
    }


def test_pytest_plugin_entrypoint_is_registered() -> None:
    pytest_plugins = entry_points(group="pytest11")

    assert any(
        plugin.name == "worldforge-runtime-profiles"
        and plugin.value == "worldforge.testing.pytest_plugin"
        for plugin in pytest_plugins
    )


def test_pytest_plugin_skips_live_tests_by_default(pytester: pytest.Pytester) -> None:
    pytester.makepyfile("""
        import pytest

        @pytest.mark.live
        def test_live_runtime():
            raise AssertionError("should be skipped before test body runs")
    """)

    result = pytester.runpytest("-rs")

    result.assert_outcomes(skipped=1)
    result.stdout.fnmatch_lines(["*requires an explicit --run-live opt-in*"])


def test_pytest_plugin_runs_configured_provider_profile(
    pytester: pytest.Pytester,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pytester.makepyfile("""
        import pytest

        @pytest.mark.live
        @pytest.mark.network
        @pytest.mark.credentialed
        @pytest.mark.provider_profile("runway")
        def test_runway_runtime():
            assert True
    """)
    monkeypatch.setenv("RUNWAY_API_SECRET", "test-secret")

    result = pytester.runpytest(
        "--run-live",
        "--run-network",
        "--run-credentialed",
        "--provider-profile",
        "runway",
    )

    result.assert_outcomes(passed=1)


def test_pytest_plugin_skips_unselected_provider_profile(pytester: pytest.Pytester) -> None:
    pytester.makepyfile("""
        import pytest

        @pytest.mark.live
        @pytest.mark.provider_profile("runway")
        def test_runway_runtime():
            raise AssertionError("should be skipped before test body runs")
    """)

    result = pytester.runpytest("-rs", "--run-live", "--provider-profile", "cosmos")

    result.assert_outcomes(skipped=1)
    result.stdout.fnmatch_lines(["*selected provider profile is 'cosmos', not 'runway'*"])


class _PluginOptionGroup:
    def __init__(self) -> None:
        self.options: list[tuple[tuple[Any, ...], dict[str, Any]]] = []

    def addoption(self, *args: Any, **kwargs: Any) -> None:
        self.options.append((args, kwargs))


class _PluginParser:
    def __init__(self) -> None:
        self.group = _PluginOptionGroup()

    def getgroup(self, name: str) -> _PluginOptionGroup:
        assert name == "worldforge-runtime-profiles"
        return self.group


class _PluginConfig:
    def __init__(
        self,
        *,
        selected_provider_profile: str | None = None,
        enabled_options: set[str] | None = None,
    ) -> None:
        self.selected_provider_profile = selected_provider_profile
        self.enabled_options = enabled_options or set()
        self.marker_definitions: list[str] = []

    def getoption(self, option: str) -> object:
        if option == "--provider-profile":
            return self.selected_provider_profile
        return option in self.enabled_options

    def addinivalue_line(self, name: str, value: str) -> None:
        assert name == "markers"
        self.marker_definitions.append(value)


class _PluginMarker:
    def __init__(self, *args: object) -> None:
        self.args = args


class _PluginItem:
    def __init__(
        self,
        *,
        closest_markers: set[str] | None = None,
        provider_markers: list[_PluginMarker] | None = None,
    ) -> None:
        self.closest_markers = closest_markers or set()
        self.provider_markers = provider_markers or []
        self.skip_reasons: list[str] = []

    def get_closest_marker(self, name: str) -> object | None:
        return object() if name in self.closest_markers else None

    def iter_markers(self, name: str) -> list[_PluginMarker]:
        assert name == "provider_profile"
        return self.provider_markers

    def add_marker(self, marker: pytest.MarkDecorator) -> None:
        mark = marker.mark
        self.skip_reasons.append(str(mark.kwargs["reason"]))


def test_pytest_plugin_direct_hooks_cover_runtime_profile_branches(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import worldforge.testing.pytest_plugin as plugin

    plugin = importlib.reload(plugin)
    parser = _PluginParser()
    plugin.pytest_addoption(parser)  # type: ignore[arg-type]
    option_names = [args[0] for args, _kwargs in parser.group.options]
    assert "--run-live" in option_names
    assert "--provider-profile" in option_names

    config = _PluginConfig()
    plugin.pytest_configure(config)  # type: ignore[arg-type]
    assert any(definition.startswith("live:") for definition in config.marker_definitions)

    monkeypatch.delenv("COSMOS_BASE_URL", raising=False)
    items = [
        _PluginItem(closest_markers={"gpu"}),
        _PluginItem(provider_markers=[_PluginMarker("runway")]),
        _PluginItem(provider_markers=[_PluginMarker()]),
    ]
    plugin.pytest_collection_modifyitems(config, items)  # type: ignore[arg-type]
    assert items[0].skip_reasons == ["requires an explicit --run-gpu opt-in"]
    assert items[1].skip_reasons == ["provider profile 'runway' requires --provider-profile runway"]
    assert items[2].skip_reasons == ["provider profile '' requires --provider-profile "]

    selected_config = _PluginConfig(selected_provider_profile="cosmos")
    runway_item = _PluginItem(provider_markers=[_PluginMarker("runway")])
    cosmos_item = _PluginItem(provider_markers=[_PluginMarker("cosmos")])
    non_string_item = _PluginItem(provider_markers=[_PluginMarker(123)])
    plugin.pytest_collection_modifyitems(  # type: ignore[arg-type]
        selected_config,
        [runway_item, cosmos_item, non_string_item],
    )
    assert runway_item.skip_reasons == ["selected provider profile is 'cosmos', not 'runway'"]
    assert cosmos_item.skip_reasons == [
        "provider profile 'cosmos' is not configured: missing COSMOS_BASE_URL"
    ]
    assert non_string_item.skip_reasons == ["selected provider profile is 'cosmos', not ''"]

    monkeypatch.setenv("COSMOS_BASE_URL", "https://cosmos.example.test")
    configured_item = _PluginItem(provider_markers=[_PluginMarker("cosmos")])
    plugin.pytest_collection_modifyitems(  # type: ignore[arg-type]
        selected_config,
        [configured_item],
    )
    assert configured_item.skip_reasons == []

"""Pytest plugin for optional WorldForge runtime profiles."""

from __future__ import annotations

import pytest

from worldforge.testing.runtime_profiles import (
    RUNTIME_MARKERS,
    provider_profile_skip_reason,
    runtime_marker_skip_reason,
)
from worldforge.testing.runtime_profiles import (
    pytest_marker_definitions as worldforge_pytest_marker_definitions,
)


def pytest_addoption(parser: pytest.Parser) -> None:
    group = parser.getgroup("worldforge-runtime-profiles")
    for marker in RUNTIME_MARKERS:
        group.addoption(marker.option, action="store_true", default=False, help=marker.help)
    group.addoption(
        "--provider-profile",
        action="store",
        default=None,
        help="run tests for one provider_profile marker value, such as runway or leworldmodel",
    )


def pytest_configure(config: pytest.Config) -> None:
    for marker_definition in worldforge_pytest_marker_definitions():
        config.addinivalue_line("markers", marker_definition)


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    enabled = {
        marker.option.lstrip("-").replace("-", "_"): bool(config.getoption(marker.option))
        for marker in RUNTIME_MARKERS
    }
    selected_provider_profile = config.getoption("--provider-profile")

    for item in items:
        skip_reasons = [
            reason
            for marker in RUNTIME_MARKERS
            if (reason := runtime_marker_skip_reason(marker.name, enabled))
            and item.get_closest_marker(marker.name) is not None
        ]

        for provider_marker in item.iter_markers("provider_profile"):
            profile_name = _provider_profile_name(provider_marker)
            if selected_provider_profile is None:
                skip_reasons.append(
                    f"provider profile '{profile_name}' requires --provider-profile {profile_name}"
                )
            elif profile_name != selected_provider_profile:
                skip_reasons.append(
                    "selected provider profile is "
                    f"'{selected_provider_profile}', not '{profile_name}'"
                )
            elif reason := provider_profile_skip_reason(profile_name):
                skip_reasons.append(reason)

        if skip_reasons:
            item.add_marker(pytest.mark.skip(reason="; ".join(skip_reasons)))


def _provider_profile_name(marker: pytest.Mark) -> str:
    if not marker.args:
        return ""
    value = marker.args[0]
    return value if isinstance(value, str) else ""

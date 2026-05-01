"""Pytest runtime profile metadata for optional provider smokes."""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class RuntimeMarker:
    """A pytest marker that must be explicitly enabled before collection runs."""

    name: str
    option: str
    help: str
    description: str


@dataclass(frozen=True, slots=True)
class ProviderRuntimeProfile:
    """Environment contract for one live provider profile."""

    name: str
    required_env_vars: tuple[str, ...]
    required_any_env_vars: tuple[str, ...] = ()

    def missing_reason(self, environ: Mapping[str, str] | None = None) -> str | None:
        """Return the first missing environment reason, or ``None`` when configured."""

        env = os.environ if environ is None else environ
        for env_var in self.required_env_vars:
            if not _env_has_value(env, env_var):
                return f"missing {env_var}"
        if self.required_any_env_vars and not any(
            _env_has_value(env, env_var) for env_var in self.required_any_env_vars
        ):
            names = " or ".join(self.required_any_env_vars)
            return f"missing {names}"
        return None


RUNTIME_MARKERS: tuple[RuntimeMarker, ...] = (
    RuntimeMarker(
        name="live",
        option="--run-live",
        help="run live provider/runtime tests",
        description="requires an explicit --run-live opt-in",
    ),
    RuntimeMarker(
        name="network",
        option="--run-network",
        help="run tests that may make network calls",
        description="requires an explicit --run-network opt-in",
    ),
    RuntimeMarker(
        name="gpu",
        option="--run-gpu",
        help="run tests that require a GPU runtime",
        description="requires an explicit --run-gpu opt-in",
    ),
    RuntimeMarker(
        name="robotics",
        option="--run-robotics",
        help="run tests that require robotics/simulator runtimes",
        description="requires an explicit --run-robotics opt-in",
    ),
    RuntimeMarker(
        name="credentialed",
        option="--run-credentialed",
        help="run tests that require credentials or private endpoints",
        description="requires an explicit --run-credentialed opt-in",
    ),
)

PROVIDER_RUNTIME_PROFILES: tuple[ProviderRuntimeProfile, ...] = (
    ProviderRuntimeProfile(name="cosmos", required_env_vars=("COSMOS_BASE_URL",)),
    ProviderRuntimeProfile(
        name="cosmos-policy",
        required_env_vars=("COSMOS_POLICY_BASE_URL",),
    ),
    ProviderRuntimeProfile(
        name="runway",
        required_env_vars=(),
        required_any_env_vars=("RUNWAYML_API_SECRET", "RUNWAY_API_SECRET"),
    ),
    ProviderRuntimeProfile(
        name="leworldmodel",
        required_env_vars=(),
        required_any_env_vars=("LEWORLDMODEL_POLICY", "LEWM_POLICY"),
    ),
    ProviderRuntimeProfile(name="gr00t", required_env_vars=("GROOT_POLICY_HOST",)),
    ProviderRuntimeProfile(
        name="lerobot",
        required_env_vars=(),
        required_any_env_vars=("LEROBOT_POLICY_PATH", "LEROBOT_POLICY"),
    ),
)

RUNTIME_MARKERS_BY_NAME = {marker.name: marker for marker in RUNTIME_MARKERS}
PROVIDER_RUNTIME_PROFILES_BY_NAME = {profile.name: profile for profile in PROVIDER_RUNTIME_PROFILES}


def pytest_marker_definitions() -> list[str]:
    """Return marker definitions for ``tool.pytest.ini_options.markers``."""

    definitions = [
        f"{marker.name}: {marker.help.removeprefix('run ')}" for marker in RUNTIME_MARKERS
    ]
    definitions.append("provider_profile(name): require provider-specific live runtime environment")
    return definitions


def runtime_marker_skip_reason(marker_name: str, enabled: Mapping[str, bool]) -> str | None:
    """Return a clear skip reason for a gated marker when it is not enabled."""

    marker = RUNTIME_MARKERS_BY_NAME.get(marker_name)
    if marker is None or enabled.get(marker.option.lstrip("-").replace("-", "_"), False):
        return None
    return marker.description


def provider_profile_skip_reason(
    profile_name: str,
    environ: Mapping[str, str] | None = None,
) -> str | None:
    """Return a provider profile skip reason for missing runtime environment."""

    profile = PROVIDER_RUNTIME_PROFILES_BY_NAME.get(profile_name)
    if profile is None:
        return f"unknown provider runtime profile: {profile_name}"
    missing = profile.missing_reason(environ)
    if missing is None:
        return None
    return f"provider profile '{profile_name}' is not configured: {missing}"


def _env_has_value(env: Mapping[str, str], name: str) -> bool:
    value = env.get(name)
    return value is not None and bool(value.strip())


__all__ = [
    "PROVIDER_RUNTIME_PROFILES",
    "PROVIDER_RUNTIME_PROFILES_BY_NAME",
    "RUNTIME_MARKERS",
    "RUNTIME_MARKERS_BY_NAME",
    "ProviderRuntimeProfile",
    "RuntimeMarker",
    "provider_profile_skip_reason",
    "pytest_marker_definitions",
    "runtime_marker_skip_reason",
]

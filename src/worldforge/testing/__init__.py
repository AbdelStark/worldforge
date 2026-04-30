"""Testing helpers for WorldForge integrations."""

from __future__ import annotations

from importlib import import_module
from typing import Any

_EXPORTS: dict[str, str] = {  # pragma: no cover - initialized before pytest-cov by plugins
    "ProviderContractReport": "worldforge.testing.providers",
    "assert_embed_conformance": "worldforge.testing.providers",
    "assert_generate_conformance": "worldforge.testing.providers",
    "assert_policy_conformance": "worldforge.testing.providers",
    "assert_predict_conformance": "worldforge.testing.providers",
    "assert_provider_contract": "worldforge.testing.providers",
    "assert_provider_events_conform": "worldforge.testing.providers",
    "assert_reason_conformance": "worldforge.testing.providers",
    "assert_score_conformance": "worldforge.testing.providers",
    "assert_transfer_conformance": "worldforge.testing.providers",
    "sample_contract_action": "worldforge.testing.providers",
    "sample_contract_policy_info": "worldforge.testing.providers",
    "sample_contract_world_state": "worldforge.testing.providers",
    "PROVIDER_RUNTIME_PROFILES": "worldforge.testing.runtime_profiles",
    "PROVIDER_RUNTIME_PROFILES_BY_NAME": "worldforge.testing.runtime_profiles",
    "RUNTIME_MARKERS": "worldforge.testing.runtime_profiles",
    "RUNTIME_MARKERS_BY_NAME": "worldforge.testing.runtime_profiles",
    "ProviderRuntimeProfile": "worldforge.testing.runtime_profiles",
    "RuntimeMarker": "worldforge.testing.runtime_profiles",
    "provider_profile_skip_reason": "worldforge.testing.runtime_profiles",
    "pytest_marker_definitions": "worldforge.testing.runtime_profiles",
    "runtime_marker_skip_reason": "worldforge.testing.runtime_profiles",
}

__all__ = sorted(_EXPORTS)


def __getattr__(name: str) -> Any:
    if name not in _EXPORTS:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    module = import_module(_EXPORTS[name])
    value = getattr(module, name)
    globals()[name] = value
    return value


def __dir__() -> list[str]:  # pragma: no cover - module dir support
    return sorted((*globals(), *_EXPORTS))

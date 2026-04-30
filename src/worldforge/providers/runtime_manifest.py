"""Provider runtime manifest loading and validation."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from importlib import resources
from typing import Any

from worldforge.models import WorldForgeError

from . import runtime_manifests
from ._config import ProviderConfigSummary, config_field_summary

MANIFEST_PACKAGE = "worldforge.providers.runtime_manifests"
_MANIFEST_FILES = resources.files(runtime_manifests)
MANIFEST_SCHEMA_VERSION = 1


@dataclass(frozen=True, slots=True)
class ProviderRuntimeManifest:
    """Machine-readable host-runtime requirements for an optional provider."""

    provider: str
    schema_version: int
    capabilities: tuple[str, ...]
    optional_dependencies: tuple[str, ...]
    required_env_vars: tuple[str, ...]
    optional_env_vars: tuple[str, ...]
    default_model: str
    device_support: tuple[str, ...]
    host_owned_artifacts: tuple[str, ...]
    minimum_smoke_command: str
    expected_success_signal: str
    setup_hint: str
    docs_path: str

    @classmethod
    def from_json(cls, payload: dict[str, Any], *, source: str) -> ProviderRuntimeManifest:
        """Build and validate a runtime manifest from decoded JSON."""

        provider = _required_str(payload, "provider", source=source)
        schema_version = _required_int(payload, "schema_version", source=source)
        if schema_version != MANIFEST_SCHEMA_VERSION:
            raise WorldForgeError(
                f"{source} schema_version must be {MANIFEST_SCHEMA_VERSION}, got {schema_version}."
            )
        return cls(
            provider=provider,
            schema_version=schema_version,
            capabilities=_required_str_tuple(payload, "capabilities", source=source),
            optional_dependencies=_required_str_tuple(
                payload,
                "optional_dependencies",
                source=source,
                allow_empty=True,
            ),
            required_env_vars=_required_str_tuple(payload, "required_env_vars", source=source),
            optional_env_vars=_required_str_tuple(
                payload,
                "optional_env_vars",
                source=source,
                allow_empty=True,
            ),
            default_model=_required_str(payload, "default_model", source=source),
            device_support=_required_str_tuple(payload, "device_support", source=source),
            host_owned_artifacts=_required_str_tuple(
                payload,
                "host_owned_artifacts",
                source=source,
            ),
            minimum_smoke_command=_required_str(
                payload,
                "minimum_smoke_command",
                source=source,
            ),
            expected_success_signal=_required_str(
                payload,
                "expected_success_signal",
                source=source,
            ),
            setup_hint=_required_str(payload, "setup_hint", source=source),
            docs_path=_required_str(payload, "docs_path", source=source),
        )

    def missing_dependency_detail(self, dependency: str) -> str:
        """Return an actionable health detail for a missing optional dependency."""

        if dependency not in self.optional_dependencies:
            return f"missing optional dependency {dependency}"
        return (
            f"missing optional dependency {dependency}; {self.setup_hint}; "
            f"minimum smoke: {self.minimum_smoke_command}"
        )

    def missing_configuration_detail(self) -> str:
        """Return a health detail for missing runtime configuration."""

        required = " or ".join(self.required_env_vars)
        return f"missing {required}; configure runtime using {self.docs_path}"

    def config_summary(
        self,
        *,
        configured: bool | None = None,
        environ: Mapping[str, str] | None = None,
    ) -> ProviderConfigSummary:
        """Return manifest-declared env presence without exposing values."""

        fields = [
            config_field_summary(
                self.required_env_vars[0],
                aliases=self.required_env_vars[1:],
                required=True,
                secret=_looks_secret_name(self.required_env_vars[0]),
                environ=environ,
            )
        ]
        fields.extend(
            config_field_summary(
                env_var,
                required=False,
                secret=_looks_secret_name(env_var),
                environ=environ,
            )
            for env_var in self.optional_env_vars
        )
        resolved_configured = configured
        if resolved_configured is None:
            resolved_configured = fields[0].present and all(field.valid for field in fields)
        return ProviderConfigSummary(
            provider=self.provider,
            configured=resolved_configured,
            fields=tuple(fields),
        )


def load_runtime_manifest(provider: str) -> ProviderRuntimeManifest:
    """Load one provider runtime manifest by provider name."""

    source = f"{provider}.json"
    try:
        text = _MANIFEST_FILES.joinpath(source).read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise WorldForgeError(f"Runtime manifest not found for provider '{provider}'.") from exc
    payload = json.loads(text)
    if not isinstance(payload, dict):
        raise WorldForgeError(f"{source} must contain a JSON object.")
    return ProviderRuntimeManifest.from_json(payload, source=source)


def load_runtime_manifests() -> tuple[ProviderRuntimeManifest, ...]:
    """Load every in-repo optional provider runtime manifest."""

    manifests: list[ProviderRuntimeManifest] = []
    for manifest_file in sorted(_MANIFEST_FILES.iterdir()):
        if manifest_file.name.endswith(".json"):
            payload = json.loads(manifest_file.read_text(encoding="utf-8"))
            if not isinstance(payload, dict):
                raise WorldForgeError(f"{manifest_file.name} must contain a JSON object.")
            manifests.append(ProviderRuntimeManifest.from_json(payload, source=manifest_file.name))
    return tuple(manifests)


def missing_optional_dependency_detail(provider: str, dependency: str) -> str:
    """Return a manifest-backed health detail for a missing optional dependency."""

    return load_runtime_manifest(provider).missing_dependency_detail(dependency)


def missing_runtime_configuration_detail(provider: str) -> str:
    """Return a manifest-backed health detail for missing runtime configuration."""

    return load_runtime_manifest(provider).missing_configuration_detail()


def _looks_secret_name(name: str) -> bool:
    return any(
        marker in name.lower()
        for marker in ("api_key", "api_secret", "secret", "token", "password", "credential")
    )


def _required_str(payload: dict[str, Any], field: str, *, source: str) -> str:
    value = payload.get(field)
    if not isinstance(value, str) or not value.strip():
        raise WorldForgeError(f"{source} field '{field}' must be a non-empty string.")
    return value.strip()


def _required_int(payload: dict[str, Any], field: str, *, source: str) -> int:
    value = payload.get(field)
    if isinstance(value, bool) or not isinstance(value, int):
        raise WorldForgeError(f"{source} field '{field}' must be an integer.")
    return value


def _required_str_tuple(
    payload: dict[str, Any],
    field: str,
    *,
    source: str,
    allow_empty: bool = False,
) -> tuple[str, ...]:
    value = payload.get(field)
    if not isinstance(value, list) or (not value and not allow_empty):
        raise WorldForgeError(f"{source} field '{field}' must be a non-empty string list.")
    items: list[str] = []
    for index, item in enumerate(value):
        if not isinstance(item, str) or not item.strip():
            raise WorldForgeError(
                f"{source} field '{field}' item {index} must be a non-empty string."
            )
        items.append(item.strip())
    return tuple(items)

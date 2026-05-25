"""Provider runtime manifest loading and validation."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from importlib import resources
from pathlib import Path
from typing import Any

from worldforge.models import (
    JSONDict,
    WorldForgeError,
    _redact_observable_value,
    _sanitize_observable_target,
    require_non_negative_int,
)

from . import runtime_manifests
from ._config import ProviderConfigSummary, config_field_summary

MANIFEST_PACKAGE = "worldforge.providers.runtime_manifests"
_MANIFEST_FILES = resources.files(runtime_manifests)
MANIFEST_SCHEMA_VERSION = 1
RUNTIME_ASSET_MANIFEST_SCHEMA_VERSION = 1
_CHECKSUM_PATTERN = re.compile(r"^sha256:[0-9a-f]{64}$")
_HOST_LOCAL_PATH_PATTERN = re.compile(r"^(/Users/|/private/|/tmp/|/var/folders/|~|[A-Za-z]:[\\/])")


@dataclass(frozen=True, slots=True)
class RuntimeAssetManifest:
    """Description of one host-owned runtime asset used by an optional runtime."""

    asset_id: str
    provider: str
    asset_kind: str
    path: str | Path
    source: str
    revision: str | None = None
    checksum: str | None = None
    size_bytes: int | None = None
    cache_root: str | Path | None = None
    local_only: bool = True
    exists: bool | None = None
    rebuild_command: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "asset_id", _required_text(self.asset_id, "asset_id"))
        object.__setattr__(self, "provider", _required_text(self.provider, "provider"))
        object.__setattr__(self, "asset_kind", _required_text(self.asset_kind, "asset_kind"))
        path = _required_text(str(self.path), "path")
        source = _safe_text(self.source, "source")
        object.__setattr__(self, "path", path)
        object.__setattr__(self, "source", source)
        if self.revision is not None:
            object.__setattr__(self, "revision", _safe_text(self.revision, "revision"))
        if self.checksum is not None and not _CHECKSUM_PATTERN.match(self.checksum):
            raise WorldForgeError("Runtime asset checksum must use sha256:<64 lowercase hex>.")
        if self.size_bytes is not None:
            object.__setattr__(
                self,
                "size_bytes",
                require_non_negative_int(self.size_bytes, name="Runtime asset size_bytes"),
            )
        if self.cache_root is not None:
            object.__setattr__(
                self,
                "cache_root",
                _required_text(str(self.cache_root), "cache_root"),
            )
        if not isinstance(self.local_only, bool):
            raise WorldForgeError("Runtime asset local_only must be a boolean.")
        if self.exists is not None and not isinstance(self.exists, bool):
            raise WorldForgeError("Runtime asset exists must be a boolean when provided.")
        if self.rebuild_command is not None:
            object.__setattr__(
                self,
                "rebuild_command",
                _safe_text(self.rebuild_command, "rebuild_command"),
            )
        if not self.local_only:
            _validate_attachable_path(path, field="path")
            if self.cache_root is not None:
                _validate_attachable_path(str(self.cache_root), field="cache_root")

    def to_dict(self, *, include_local_fields: bool = False) -> JSONDict:
        """Return a manifest dict, omitting host-local fields unless explicitly requested."""

        payload: JSONDict = {
            "schema_version": RUNTIME_ASSET_MANIFEST_SCHEMA_VERSION,
            "asset_id": self.asset_id,
            "provider": self.provider,
            "asset_kind": self.asset_kind,
            "source": self.source,
            "revision": self.revision,
            "checksum": self.checksum,
            "size_bytes": self.size_bytes,
            "local_only": self.local_only,
            "exists": self.exists,
            "rebuild_command": self.rebuild_command,
            "safe_to_attach": not include_local_fields,
        }
        if include_local_fields:
            payload["path"] = str(self.path)
            payload["cache_root"] = str(self.cache_root) if self.cache_root is not None else None
        elif not self.local_only:
            payload["path"] = str(self.path)
            if self.cache_root is not None:
                payload["cache_root"] = str(self.cache_root)
        return validate_runtime_asset_manifest(
            payload,
            source=f"runtime asset {self.asset_id}",
            include_local_fields=include_local_fields,
        )

    def to_reference(self) -> JSONDict:
        """Return the safe-to-attach runtime asset reference used in run manifests."""

        return self.to_dict(include_local_fields=False)


def validate_runtime_asset_manifest(
    payload: Mapping[str, Any],
    *,
    source: str = "runtime asset manifest",
    include_local_fields: bool = False,
) -> JSONDict:
    """Validate a full runtime asset manifest or safe attachable reference."""

    manifest = dict(payload)
    schema_version = manifest.get("schema_version")
    if schema_version != RUNTIME_ASSET_MANIFEST_SCHEMA_VERSION:
        raise WorldForgeError(
            f"{source} schema_version must be {RUNTIME_ASSET_MANIFEST_SCHEMA_VERSION}."
        )
    for field in ("asset_id", "provider", "asset_kind", "source"):
        manifest[field] = _safe_text(manifest.get(field), f"{source} field '{field}'")
    local_only = manifest.get("local_only")
    if not isinstance(local_only, bool):
        raise WorldForgeError(f"{source} field 'local_only' must be a boolean.")
    safe_to_attach = manifest.get("safe_to_attach")
    if safe_to_attach is None:
        manifest["safe_to_attach"] = not include_local_fields
    elif not isinstance(safe_to_attach, bool):
        raise WorldForgeError(f"{source} field 'safe_to_attach' must be a boolean.")
    elif not include_local_fields and not safe_to_attach:
        raise WorldForgeError(f"{source} safe reference must set safe_to_attach to true.")
    if manifest.get("revision") is not None:
        manifest["revision"] = _safe_text(manifest["revision"], f"{source} field 'revision'")
    checksum = manifest.get("checksum")
    if checksum is not None and (
        not isinstance(checksum, str) or not _CHECKSUM_PATTERN.match(checksum)
    ):
        raise WorldForgeError(f"{source} field 'checksum' must use sha256:<64 lowercase hex>.")
    if manifest.get("size_bytes") is not None:
        manifest["size_bytes"] = require_non_negative_int(
            manifest["size_bytes"],
            name=f"{source} size_bytes",
        )
    if manifest.get("exists") is not None and not isinstance(manifest.get("exists"), bool):
        raise WorldForgeError(f"{source} field 'exists' must be a boolean when provided.")
    if manifest.get("rebuild_command") is not None:
        manifest["rebuild_command"] = _safe_text(
            manifest["rebuild_command"],
            f"{source} field 'rebuild_command'",
        )
    path = manifest.get("path")
    cache_root = manifest.get("cache_root")
    if include_local_fields:
        manifest["path"] = _required_text(path, f"{source} field 'path'")
        if cache_root is not None:
            manifest["cache_root"] = _required_text(cache_root, f"{source} field 'cache_root'")
    else:
        if local_only and (path is not None or cache_root is not None):
            raise WorldForgeError(
                f"{source} safe reference must omit path and cache_root for local-only assets."
            )
        if path is not None:
            manifest["path"] = _required_text(path, f"{source} field 'path'")
            _validate_attachable_path(manifest["path"], field=f"{source} field 'path'")
        if cache_root is not None:
            manifest["cache_root"] = _required_text(
                cache_root,
                f"{source} field 'cache_root'",
            )
            _validate_attachable_path(
                manifest["cache_root"],
                field=f"{source} field 'cache_root'",
            )
    return manifest


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


def _required_text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise WorldForgeError(f"Runtime asset {field} must be a non-empty string.")
    return value.strip()


def _safe_text(value: object, field: str) -> str:
    text = _required_text(value, field)
    if _redact_observable_value(text) != text:
        raise WorldForgeError(f"Runtime asset {field} must not contain secret-like material.")
    sanitized = _sanitize_observable_target(text)
    if sanitized != text:
        raise WorldForgeError(f"Runtime asset {field} must not contain signed URLs or queries.")
    return text


def _validate_attachable_path(value: str, *, field: str) -> None:
    if _HOST_LOCAL_PATH_PATTERN.search(value):
        raise WorldForgeError(
            f"Runtime asset {field} must be local_only=True before using host-local paths."
        )
    if _redact_observable_value(value) != value:
        raise WorldForgeError(f"Runtime asset {field} must not contain secret-like material.")
    sanitized = _sanitize_observable_target(value)
    if sanitized != value:
        raise WorldForgeError(f"Runtime asset {field} must not contain signed URLs or queries.")


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

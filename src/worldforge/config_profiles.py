"""Non-secret configuration profiles for repeatable CLI defaults."""

from __future__ import annotations

import hashlib
import json
import re
import tomllib
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Any
from urllib.parse import urlsplit

from worldforge.models import (
    JSONDict,
    WorldForgeError,
    _redact_observable_value,
    _sanitize_observable_target,
    require_json_dict,
)

CONFIG_PROFILE_SCHEMA_VERSION = 1
CONFIG_PROFILE_OUTPUT_FORMATS = ("markdown", "json", "csv", "html")
CONFIG_PROFILE_TIMEOUT_PRESETS = ("checkout-safe", "remote", "prepared-host")
CONFIG_PROFILE_RETRY_PRESETS = ("none", "standard", "patient")

_ALLOWED_PROFILE_KEYS = {
    "schema_version",
    "name",
    "description",
    "provider",
    "providers",
    "operation",
    "operations",
    "workspace_dir",
    "run_workspace",
    "state_dir",
    "output_format",
    "timeout_preset",
    "retry_preset",
    "runtime_cache_roots",
}
_ALLOWED_PROFILE_PROVENANCE_KEYS = {
    "schema_version",
    "name",
    "source",
    "sha256",
    "providers",
    "operations",
    "workspace_dir",
    "run_workspace",
    "state_dir",
    "output_format",
    "timeout_preset",
    "retry_preset",
    "runtime_cache_roots",
}
_SECRET_KEY_PATTERN = re.compile(
    r"(api[_-]?key|api[_-]?secret|auth|bearer|credential|password|secret|signed[_-]?url|token)",
    re.IGNORECASE,
)
_SAFE_IDENTIFIER_PATTERN = re.compile(r"^[A-Za-z0-9_.:/-]+$")
_SAFE_PROFILE_NAME_PATTERN = re.compile(r"^[A-Za-z0-9_.-]+$")
_PATH_FIELDS = ("workspace_dir", "run_workspace", "state_dir")


@dataclass(frozen=True, slots=True)
class ConfigProfile:
    """Validated non-secret CLI defaults loaded from a JSON or TOML profile."""

    name: str
    source: str
    sha256: str
    providers: tuple[str, ...] = ()
    operations: tuple[str, ...] = ()
    workspace_dir: str | None = None
    run_workspace: str | None = None
    state_dir: str | None = None
    output_format: str | None = None
    timeout_preset: str | None = None
    retry_preset: str | None = None
    runtime_cache_roots: Mapping[str, str] = field(default_factory=dict)

    def to_provenance(self) -> JSONDict:
        """Return a safe-to-attach profile provenance record for run manifests."""

        return validate_config_profile_provenance(
            {
                "schema_version": CONFIG_PROFILE_SCHEMA_VERSION,
                "name": self.name,
                "source": self.source,
                "sha256": self.sha256,
                "providers": list(self.providers),
                "operations": list(self.operations),
                "workspace_dir": self.workspace_dir,
                "run_workspace": self.run_workspace,
                "state_dir": self.state_dir,
                "output_format": self.output_format,
                "timeout_preset": self.timeout_preset,
                "retry_preset": self.retry_preset,
                "runtime_cache_roots": dict(self.runtime_cache_roots),
            }
        )


def load_config_profile(path: Path | str) -> ConfigProfile:
    """Load a non-secret configuration profile from JSON or TOML."""

    source_path = Path(path).expanduser()
    try:
        raw_bytes = source_path.read_bytes()
    except OSError as exc:
        raise WorldForgeError(f"Failed to read configuration profile {path}: {exc}") from exc
    raw_text = raw_bytes.decode("utf-8")
    suffix = source_path.suffix.lower()
    try:
        payload = tomllib.loads(raw_text) if suffix == ".toml" else json.loads(raw_text)
    except (json.JSONDecodeError, tomllib.TOMLDecodeError) as exc:
        raise WorldForgeError(
            f"Configuration profile {path} must be valid JSON or TOML: {exc}"
        ) from exc
    if not isinstance(payload, dict):
        raise WorldForgeError("Configuration profile must contain a JSON/TOML object.")
    digest = f"sha256:{hashlib.sha256(raw_bytes).hexdigest()}"
    return parse_config_profile(payload, source_path=source_path, sha256=digest)


def parse_config_profile(
    payload: Mapping[str, Any],
    *,
    source_path: Path | None = None,
    sha256: str | None = None,
) -> ConfigProfile:
    """Validate an already-decoded non-secret configuration profile."""

    profile = require_json_dict(dict(payload), name="Configuration profile")
    _reject_secret_material(profile)
    unknown = sorted(set(profile) - _ALLOWED_PROFILE_KEYS)
    if unknown:
        raise WorldForgeError(f"Configuration profile has unsupported keys: {', '.join(unknown)}.")
    schema_version = profile.get("schema_version")
    if schema_version != CONFIG_PROFILE_SCHEMA_VERSION:
        raise WorldForgeError(
            f"Configuration profile schema_version must be {CONFIG_PROFILE_SCHEMA_VERSION}."
        )
    name = _profile_name(profile.get("name"))
    providers = _string_tuple(profile, singular="provider", plural="providers")
    operations = _string_tuple(profile, singular="operation", plural="operations")
    workspace_dir = _optional_profile_path(profile.get("workspace_dir"), field="workspace_dir")
    run_workspace = _optional_profile_path(profile.get("run_workspace"), field="run_workspace")
    state_dir = _optional_profile_path(profile.get("state_dir"), field="state_dir")
    output_format = _optional_choice(
        profile.get("output_format"),
        field="output_format",
        choices=CONFIG_PROFILE_OUTPUT_FORMATS,
    )
    timeout_preset = _optional_choice(
        profile.get("timeout_preset"),
        field="timeout_preset",
        choices=CONFIG_PROFILE_TIMEOUT_PRESETS,
    )
    retry_preset = _optional_choice(
        profile.get("retry_preset"),
        field="retry_preset",
        choices=CONFIG_PROFILE_RETRY_PRESETS,
    )
    runtime_cache_roots = _runtime_cache_roots(profile.get("runtime_cache_roots"))
    return ConfigProfile(
        name=name,
        source=_source_label(source_path, name=name),
        sha256=_profile_digest(sha256),
        providers=providers,
        operations=operations,
        workspace_dir=workspace_dir,
        run_workspace=run_workspace,
        state_dir=state_dir,
        output_format=output_format,
        timeout_preset=timeout_preset,
        retry_preset=retry_preset,
        runtime_cache_roots=runtime_cache_roots,
    )


def validate_config_profile_provenance(payload: Mapping[str, Any]) -> JSONDict:
    """Validate the sanitized profile provenance block stored in run manifests."""

    provenance = require_json_dict(dict(payload), name="Configuration profile provenance")
    _reject_secret_material(provenance)
    unknown = sorted(set(provenance) - _ALLOWED_PROFILE_PROVENANCE_KEYS)
    if unknown:
        raise WorldForgeError(
            f"Configuration profile provenance has unsupported keys: {', '.join(unknown)}."
        )
    if provenance.get("schema_version") != CONFIG_PROFILE_SCHEMA_VERSION:
        raise WorldForgeError(
            f"Configuration profile provenance schema_version must be "
            f"{CONFIG_PROFILE_SCHEMA_VERSION}."
        )
    provenance["name"] = _profile_name(provenance.get("name"))
    provenance["source"] = _safe_text(provenance.get("source"), "source")
    provenance["sha256"] = _profile_digest(provenance.get("sha256"))
    for field_name in ("providers", "operations"):
        provenance[field_name] = list(
            _string_sequence(provenance.get(field_name), field=field_name)
        )
    for field_name in _PATH_FIELDS:
        provenance[field_name] = _optional_profile_path(
            provenance.get(field_name), field=field_name
        )
    provenance["output_format"] = _optional_choice(
        provenance.get("output_format"),
        field="output_format",
        choices=CONFIG_PROFILE_OUTPUT_FORMATS,
    )
    provenance["timeout_preset"] = _optional_choice(
        provenance.get("timeout_preset"),
        field="timeout_preset",
        choices=CONFIG_PROFILE_TIMEOUT_PRESETS,
    )
    provenance["retry_preset"] = _optional_choice(
        provenance.get("retry_preset"),
        field="retry_preset",
        choices=CONFIG_PROFILE_RETRY_PRESETS,
    )
    provenance["runtime_cache_roots"] = _runtime_cache_roots(provenance.get("runtime_cache_roots"))
    return provenance


def _profile_name(value: object) -> str:
    name = _safe_text(value, "name")
    if not _SAFE_PROFILE_NAME_PATTERN.fullmatch(name):
        raise WorldForgeError(
            "Configuration profile name may only contain letters, numbers, '.', '_', and '-'."
        )
    return name


def _profile_digest(value: object | None) -> str:
    if value is None:
        return f"sha256:{'0' * 64}"
    if not isinstance(value, str) or not re.fullmatch(r"sha256:[0-9a-f]{64}", value):
        raise WorldForgeError("Configuration profile sha256 must use sha256:<64 lowercase hex>.")
    return value


def _string_tuple(
    payload: Mapping[str, Any],
    *,
    singular: str,
    plural: str,
) -> tuple[str, ...]:
    singular_value = payload.get(singular)
    plural_value = payload.get(plural)
    if singular_value is not None and plural_value is not None:
        raise WorldForgeError(f"Configuration profile cannot set both {singular} and {plural}.")
    if plural_value is not None:
        return _string_sequence(plural_value, field=plural)
    if singular_value is not None:
        return (_safe_identifier(singular_value, singular),)
    return ()


def _string_sequence(value: object, *, field: str) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise WorldForgeError(f"Configuration profile {field} must be a string list.")
    return tuple(_safe_identifier(item, f"{field} item") for item in value)


def _safe_identifier(value: object, field: str) -> str:
    text = _safe_text(value, field)
    if not _SAFE_IDENTIFIER_PATTERN.fullmatch(text):
        raise WorldForgeError(
            f"Configuration profile {field} may only contain letters, numbers, '.', '_', "
            "':', '/', and '-'."
        )
    return text


def _optional_choice(value: object, *, field: str, choices: Sequence[str]) -> str | None:
    if value is None:
        return None
    text = _safe_text(value, field)
    if text not in choices:
        allowed = ", ".join(choices)
        raise WorldForgeError(f"Configuration profile {field} must be one of: {allowed}.")
    return text


def _runtime_cache_roots(value: object) -> dict[str, str]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise WorldForgeError("Configuration profile runtime_cache_roots must be an object.")
    roots: dict[str, str] = {}
    for provider, root in sorted(value.items()):
        provider_name = _safe_identifier(provider, "runtime_cache_roots provider")
        roots[provider_name] = _optional_profile_path(
            root,
            field=f"runtime_cache_roots.{provider_name}",
        )
    return roots


def _optional_profile_path(value: object, *, field: str) -> str | None:
    if value is None:
        return None
    text = _safe_text(value, field)
    _validate_profile_path(text, field=field)
    return text


def _validate_profile_path(value: str, *, field: str) -> None:
    parts = urlsplit(value)
    if parts.scheme or parts.netloc or parts.query or parts.fragment:
        raise WorldForgeError(f"Configuration profile {field} must be a relative filesystem path.")
    path = PurePosixPath(value.replace("\\", "/"))
    if path.is_absolute() or value.startswith(("~", "$", "%")):
        raise WorldForgeError(f"Configuration profile {field} must use a safe relative path.")
    if not path.parts:
        raise WorldForgeError(f"Configuration profile {field} must be a non-empty path.")
    if ".." in path.parts:
        raise WorldForgeError(f"Configuration profile {field} must not contain '..'.")
    if any(part in {".env", ".env.local"} for part in path.parts):
        raise WorldForgeError(f"Configuration profile {field} must not point at env files.")


def _source_label(path: Path | None, *, name: str) -> str:
    if path is None:
        return f"profile:{name}"
    raw = path.as_posix()
    try:
        if not path.is_absolute():
            _validate_profile_path(raw, field="source")
            return f"profile:{raw}"
    except WorldForgeError:
        pass
    return f"profile:{path.name}"


def _safe_text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise WorldForgeError(f"Configuration profile {field} must be a non-empty string.")
    text = value.strip()
    if _redact_observable_value(text) != text:
        raise WorldForgeError(f"Configuration profile {field} must not contain secret material.")
    sanitized = _sanitize_observable_target(text)
    if sanitized != text:
        raise WorldForgeError(
            f"Configuration profile {field} must not contain signed URLs or query strings."
        )
    return text


def _reject_secret_material(value: object, *, path: str = "profile") -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            key_text = str(key)
            child_path = f"{path}.{key_text}"
            if _SECRET_KEY_PATTERN.search(key_text):
                raise WorldForgeError(
                    f"Configuration profile field '{child_path}' uses a secret-looking key."
                )
            _reject_secret_material(item, path=child_path)
    elif isinstance(value, list):
        for index, item in enumerate(value):
            _reject_secret_material(item, path=f"{path}[{index}]")
    elif isinstance(value, str):
        if _redact_observable_value(value) != value:
            raise WorldForgeError("Configuration profile must not contain secret material.")
        sanitized = _sanitize_observable_target(value)
        if sanitized != value.strip():
            raise WorldForgeError(
                "Configuration profile must not contain signed URLs or query strings."
            )


__all__ = [
    "CONFIG_PROFILE_OUTPUT_FORMATS",
    "CONFIG_PROFILE_RETRY_PRESETS",
    "CONFIG_PROFILE_SCHEMA_VERSION",
    "CONFIG_PROFILE_TIMEOUT_PRESETS",
    "ConfigProfile",
    "load_config_profile",
    "parse_config_profile",
    "validate_config_profile_provenance",
]

"""Private provider configuration parsing helpers."""

from __future__ import annotations

import os
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from worldforge.models import JSONDict, WorldForgeError, require_json_dict, require_positive_int


@dataclass(frozen=True, slots=True)
class ConfigFieldSummary:
    """Value-free provider configuration status for diagnostics and issue evidence."""

    name: str
    present: bool
    source: str
    required: bool
    secret: bool
    valid: bool
    detail: str = ""
    aliases: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or not self.name.strip():
            raise WorldForgeError("ConfigFieldSummary name must be a non-empty string.")
        if not isinstance(self.source, str) or not self.source.strip():
            raise WorldForgeError("ConfigFieldSummary source must be a non-empty string.")
        if not isinstance(self.detail, str):
            raise WorldForgeError("ConfigFieldSummary detail must be a string.")
        if any(not isinstance(alias, str) or not alias.strip() for alias in self.aliases):
            raise WorldForgeError("ConfigFieldSummary aliases must be non-empty strings.")

    def to_dict(self) -> JSONDict:
        return {
            "name": self.name,
            "present": self.present,
            "source": self.source,
            "required": self.required,
            "secret": self.secret,
            "valid": self.valid,
            "detail": self.detail,
            "aliases": list(self.aliases),
        }


@dataclass(frozen=True, slots=True)
class ProviderConfigSummary:
    """Value-free provider configuration summary safe for logs and issue attachments."""

    provider: str
    configured: bool
    fields: tuple[ConfigFieldSummary, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.provider, str) or not self.provider.strip():
            raise WorldForgeError("ProviderConfigSummary provider must be a non-empty string.")

    def to_dict(self) -> JSONDict:
        return require_json_dict(
            {
                "provider": self.provider,
                "configured": self.configured,
                "fields": [field.to_dict() for field in self.fields],
            },
            name="ProviderConfigSummary",
        )


def env_value(name: str) -> str | None:
    """Return a stripped environment value, treating blank strings as unset."""

    value = os.environ.get(name)
    if value is None or not value.strip():
        return None
    return value.strip()


def first_env_value(names: Sequence[str]) -> str | None:
    """Return the first non-blank environment value from an alias list."""

    for name in names:
        value = env_value(name)
        if value is not None:
            return value
    return None


def config_field_summary(
    name: str,
    *,
    aliases: Sequence[str] = (),
    required: bool = True,
    secret: bool = False,
    source: str | None = None,
    present: bool | None = None,
    valid: bool | None = None,
    detail: str = "",
    environ: Mapping[str, str] | None = None,
) -> ConfigFieldSummary:
    """Build a value-free configuration summary for one env-backed field."""

    env = os.environ if environ is None else environ
    names = (name, *tuple(aliases))
    resolved_name = next((env_name for env_name in names if env_value_from(env, env_name)), None)
    resolved_present = present if present is not None else resolved_name is not None
    resolved_source = source or (f"env:{resolved_name}" if resolved_name else "unset")
    resolved_valid = valid if valid is not None else (not required or resolved_present)
    resolved_detail = detail
    if not resolved_detail and required and not resolved_present:
        resolved_detail = "missing"
    return ConfigFieldSummary(
        name=name,
        present=resolved_present,
        source=resolved_source,
        required=required,
        secret=secret,
        valid=resolved_valid,
        detail=resolved_detail,
        aliases=tuple(aliases),
    )


def config_source(name: str, *, direct: bool = False, default: bool = False) -> str:
    """Return the value-free source label for an env/direct/default-backed field."""

    if env_value(name) is not None:
        return f"env:{name}"
    if direct:
        return "direct"
    if default:
        return "default"
    return "unset"


def env_value_from(environ: Mapping[str, str], name: str) -> str | None:
    """Return a stripped value from a supplied environment mapping."""

    value = environ.get(name)
    if value is None or not value.strip():
        return None
    return value.strip()


def optional_non_empty(value: str | None, *, name: str) -> str | None:
    """Normalize an optional string and reject caller-supplied blanks."""

    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise WorldForgeError(f"{name} must be a non-empty string when provided.")
    return value.strip()


def optional_positive_int(value: int | str | None, *, name: str) -> int | None:
    """Normalize an optional positive integer from direct config or env strings."""

    if value is None:
        return None
    if isinstance(value, str):
        if not value.strip():
            return None
        try:
            value = int(value)
        except ValueError:
            raise WorldForgeError(f"{name} must be an integer greater than 0.") from None
    return require_positive_int(value, name=name)


def optional_bool(value: bool | str | None, *, name: str) -> bool | None:
    """Normalize an optional boolean from direct config or common env strings."""

    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if not isinstance(value, str):
        raise WorldForgeError(f"{name} must be a boolean when provided.")
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise WorldForgeError(f"{name} must be a boolean when provided.")

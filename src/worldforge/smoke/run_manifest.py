"""Run manifest helpers for optional live provider smokes."""

from __future__ import annotations

import hashlib
import os
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import worldforge
from worldforge.models import (
    JSONDict,
    WorldForgeError,
    _redact_observable_value,
    _sanitize_observable_target,
    dump_json,
    require_json_dict,
    require_non_negative_int,
)
from worldforge.providers.runtime_manifest import load_runtime_manifest

RUN_MANIFEST_SCHEMA_VERSION = 1


@dataclass(frozen=True, slots=True)
class LiveSmokeRunManifest:
    """Serializable evidence manifest for host-owned live smoke artifacts."""

    run_id: str
    command_argv: tuple[str, ...]
    provider_profile: str
    capability: str
    status: str
    env_summary: tuple[JSONDict, ...]
    artifact_paths: Mapping[str, str] = field(default_factory=dict)
    event_count: int = 0
    input_fixture_digest: str | None = None
    result_digest: str | None = None
    runtime_manifest_id: str | None = None
    package_version: str = field(default_factory=lambda: worldforge.__version__)
    created_at: str = field(
        default_factory=lambda: datetime.now(UTC).replace(microsecond=0).isoformat()
    )

    def __post_init__(self) -> None:
        if not self.run_id.strip():
            raise WorldForgeError("Run manifest run_id must be a non-empty string.")
        if not self.command_argv:
            raise WorldForgeError("Run manifest command_argv must not be empty.")
        if not self.provider_profile.strip():
            raise WorldForgeError("Run manifest provider_profile must be a non-empty string.")
        if not self.capability.strip():
            raise WorldForgeError("Run manifest capability must be a non-empty string.")
        if self.status not in {"passed", "failed", "skipped"}:
            raise WorldForgeError("Run manifest status must be passed, failed, or skipped.")
        require_non_negative_int(self.event_count, name="Run manifest event_count")

    def to_dict(self) -> JSONDict:
        payload = {
            "schema_version": RUN_MANIFEST_SCHEMA_VERSION,
            "run_id": self.run_id,
            "created_at": self.created_at,
            "package_version": self.package_version,
            "command_argv": list(self.command_argv),
            "provider_profile": self.provider_profile,
            "capability": self.capability,
            "status": self.status,
            "runtime_manifest_id": self.runtime_manifest_id,
            "env_summary": [dict(item) for item in self.env_summary],
            "input_fixture_digest": self.input_fixture_digest,
            "event_count": self.event_count,
            "result_digest": self.result_digest,
            "artifact_paths": dict(self.artifact_paths),
        }
        return validate_run_manifest(payload)


def build_run_manifest(
    *,
    run_id: str,
    provider_profile: str,
    capability: str,
    status: str,
    env_vars: Sequence[str],
    artifact_paths: Mapping[str, Path | str] | None = None,
    command_argv: Sequence[str] | None = None,
    event_count: int = 0,
    input_fixture: Path | str | None = None,
    result: Mapping[str, Any] | None = None,
    result_digest: str | None = None,
    environ: Mapping[str, str] | None = None,
) -> LiveSmokeRunManifest:
    """Build a validated live smoke run manifest without exposing secrets."""

    runtime_manifest_id = None
    try:
        runtime_manifest = load_runtime_manifest(provider_profile)
    except WorldForgeError:
        runtime_manifest = None
    if runtime_manifest is not None:
        runtime_manifest_id = (
            f"{runtime_manifest.provider}:schema-{runtime_manifest.schema_version}"
        )

    resolved_result_digest = result_digest
    if resolved_result_digest is None and result is not None:
        resolved_result_digest = digest_json_value(dict(result))

    return LiveSmokeRunManifest(
        run_id=run_id,
        command_argv=tuple(command_argv or sys.argv),
        provider_profile=provider_profile,
        capability=capability,
        status=status,
        runtime_manifest_id=runtime_manifest_id,
        env_summary=tuple(env_summary(env_vars, environ=environ)),
        input_fixture_digest=digest_file(input_fixture) if input_fixture is not None else None,
        event_count=event_count,
        result_digest=resolved_result_digest,
        artifact_paths=_artifact_path_summary(artifact_paths or {}),
    )


def write_run_manifest(
    path: Path | str, manifest: LiveSmokeRunManifest | Mapping[str, Any]
) -> Path:
    """Write a validated run manifest to ``path`` and return the resolved path."""

    payload = manifest.to_dict() if isinstance(manifest, LiveSmokeRunManifest) else dict(manifest)
    output_path = Path(path).expanduser()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(dump_json(validate_run_manifest(payload)) + "\n", encoding="utf-8")
    return output_path


def env_summary(
    names: Sequence[str],
    *,
    environ: Mapping[str, str] | None = None,
) -> list[JSONDict]:
    """Return value-free env presence records for manifest evidence."""

    env = os.environ if environ is None else environ
    records: list[JSONDict] = []
    for raw_name in names:
        name = raw_name.strip()
        if not name:
            raise WorldForgeError("Run manifest env var names must be non-empty strings.")
        records.append(
            {
                "name": name,
                "present": bool(env.get(name, "").strip()),
                "source": f"env:{name}" if env.get(name, "").strip() else "unset",
                "secret": _looks_secret_name(name),
            }
        )
    return records


def digest_file(path: Path | str) -> str:
    """Return a sha256 digest for a smoke input fixture or preserved artifact."""

    digest = hashlib.sha256()
    with Path(path).expanduser().open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return f"sha256:{digest.hexdigest()}"


def digest_json_value(value: Mapping[str, Any]) -> str:
    """Return a stable sha256 digest for a JSON-like result summary."""

    payload = dump_json(require_json_dict(_json_native(dict(value)), name="Run manifest result"))
    return f"sha256:{hashlib.sha256(payload.encode('utf-8')).hexdigest()}"


def validate_run_manifest(payload: Mapping[str, Any]) -> JSONDict:
    """Validate the manifest shape and reject unsanitized secrets or signed URLs."""

    manifest = require_json_dict(dict(payload), name="Run manifest")
    if manifest.get("schema_version") != RUN_MANIFEST_SCHEMA_VERSION:
        raise WorldForgeError(f"Run manifest schema_version must be {RUN_MANIFEST_SCHEMA_VERSION}.")
    for field_name in (
        "run_id",
        "created_at",
        "package_version",
        "provider_profile",
        "capability",
        "status",
    ):
        _require_non_empty_str(manifest.get(field_name), field_name)
    argv = manifest.get("command_argv")
    if (
        not isinstance(argv, list)
        or not argv
        or any(not isinstance(item, str) or not item.strip() for item in argv)
    ):
        raise WorldForgeError("Run manifest command_argv must be a non-empty string list.")
    require_non_negative_int(manifest.get("event_count"), name="Run manifest event_count")
    if not isinstance(manifest.get("env_summary"), list):
        raise WorldForgeError("Run manifest env_summary must be a list.")
    if not isinstance(manifest.get("artifact_paths"), dict):
        raise WorldForgeError("Run manifest artifact_paths must be an object.")
    _reject_secret_like_values(manifest)
    _reject_unsafe_strings(manifest)
    return manifest


def _artifact_path_summary(paths: Mapping[str, Path | str]) -> JSONDict:
    artifacts: JSONDict = {}
    for name, raw_path in paths.items():
        if not isinstance(name, str) or not name.strip():
            raise WorldForgeError("Run manifest artifact names must be non-empty strings.")
        artifacts[name] = _sanitize_path_or_url(str(raw_path))
    return artifacts


def _sanitize_path_or_url(value: str) -> str:
    sanitized = _sanitize_observable_target(value)
    if sanitized is None:
        raise WorldForgeError("Run manifest artifact path must be non-empty.")
    return sanitized


def _reject_unsafe_strings(value: object, *, path: str = "manifest") -> None:
    if isinstance(value, str):
        try:
            sanitized = _sanitize_observable_target(value)
        except WorldForgeError:
            sanitized = value
        if sanitized != value:
            raise WorldForgeError(f"Run manifest {path} contains an unsafe URL or secret.")
    elif isinstance(value, list):
        for index, item in enumerate(value):
            _reject_unsafe_strings(item, path=f"{path}[{index}]")
    elif isinstance(value, dict):
        for key, item in value.items():
            _reject_unsafe_strings(item, path=f"{path}.{key}")


def _reject_secret_like_values(value: object, *, path: str = "manifest") -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            child_path = f"{path}.{key}"
            if _looks_sensitive_key(str(key)) and not child_path.startswith(
                "manifest.env_summary["
            ):
                raise WorldForgeError("Run manifest contains secret-like metadata.")
            _reject_secret_like_values(item, path=child_path)
    elif isinstance(value, list):
        for index, item in enumerate(value):
            _reject_secret_like_values(item, path=f"{path}[{index}]")
    elif isinstance(value, str) and _redact_observable_value(value) != value:
        raise WorldForgeError("Run manifest contains secret-like metadata.")


def _json_native(value: object) -> Any:
    if value is None or isinstance(value, str | bool | int | float):
        return value
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, tuple | list):
        return [_json_native(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _json_native(item) for key, item in value.items()}
    return str(value)


def _require_non_empty_str(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise WorldForgeError(f"Run manifest {field_name} must be a non-empty string.")
    return value


def _looks_secret_name(name: str) -> bool:
    normalized = name.lower()
    return any(
        marker in normalized
        for marker in ("api_key", "api_secret", "secret", "token", "password", "credential")
    )


def _looks_sensitive_key(name: str) -> bool:
    normalized = name.lower()
    return any(
        marker in normalized
        for marker in (
            "api_key",
            "api_secret",
            "authorization",
            "bearer",
            "credential",
            "password",
            "secret",
            "signature",
            "signed_url",
            "token",
        )
    )


__all__ = [
    "RUN_MANIFEST_SCHEMA_VERSION",
    "LiveSmokeRunManifest",
    "build_run_manifest",
    "digest_file",
    "digest_json_value",
    "env_summary",
    "validate_run_manifest",
    "write_run_manifest",
]

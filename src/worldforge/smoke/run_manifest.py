"""Run manifest helpers for optional live provider smokes."""

from __future__ import annotations

import hashlib
import os
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any
from urllib.parse import SplitResult, urlsplit

import worldforge
from worldforge.artifact_io import write_json_artifact
from worldforge.config_profiles import validate_config_profile_provenance
from worldforge.models import (
    JSONDict,
    WorldForgeError,
    _redact_observable_value,
    _sanitize_observable_target,
    dump_json,
    require_json_dict,
    require_non_negative_int,
)
from worldforge.providers.runtime_manifest import (
    RuntimeAssetManifest,
    load_runtime_manifest,
    validate_runtime_asset_manifest,
)

RUN_MANIFEST_SCHEMA_VERSION = 1
_RUN_MANIFEST_STATUSES = ("passed", "failed", "skipped")


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
    input_summary: Mapping[str, Any] = field(default_factory=dict)
    input_digest: str | None = None
    input_fixture_digest: str | None = None
    result_digest: str | None = None
    runtime_manifest_id: str | None = None
    runtime_assets: tuple[JSONDict, ...] = field(default_factory=tuple)
    config_profile: JSONDict | None = None
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
        _require_run_manifest_status(self.status)
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
            "runtime_assets": [dict(item) for item in self.runtime_assets],
            "config_profile": dict(self.config_profile) if self.config_profile else None,
            "env_summary": [dict(item) for item in self.env_summary],
            "input_summary": _json_native(dict(self.input_summary)),
            "input_digest": self.input_digest,
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
    artifact_root: Path | str | None = None,
    command_argv: Sequence[str] | None = None,
    event_count: int = 0,
    input_summary: Mapping[str, Any] | None = None,
    input_fixture: Path | str | None = None,
    input_digest: str | None = None,
    result: Mapping[str, Any] | None = None,
    result_digest: str | None = None,
    runtime_assets: Sequence[RuntimeAssetManifest | Mapping[str, Any]] | None = None,
    config_profile: Mapping[str, Any] | None = None,
    environ: Mapping[str, str] | None = None,
    created_at: str | None = None,
) -> LiveSmokeRunManifest:
    """Build a validated live smoke run manifest without exposing secrets.

    ``artifact_root`` is the local run directory used to turn host-local artifact
    paths into manifest-relative references before serialization.
    """

    runtime_manifest_id = _runtime_manifest_reference(provider_profile)
    resolved_result_digest = _resolved_result_digest(result_digest=result_digest, result=result)
    resolved_input_digest, resolved_input_fixture_digest = _resolved_input_digests(
        input_digest=input_digest,
        input_fixture=input_fixture,
        input_summary=input_summary,
    )
    manifest_kwargs: dict[str, Any] = {
        "run_id": run_id,
        "command_argv": tuple(command_argv or sys.argv),
        "provider_profile": provider_profile,
        "capability": capability,
        "status": status,
        "runtime_manifest_id": runtime_manifest_id,
        "runtime_assets": tuple(_runtime_asset_summary(runtime_assets or ())),
        "config_profile": (
            validate_config_profile_provenance(config_profile)
            if config_profile is not None
            else None
        ),
        "env_summary": tuple(env_summary(env_vars, environ=environ)),
        "input_summary": input_summary or {},
        "input_digest": resolved_input_digest,
        "input_fixture_digest": resolved_input_fixture_digest,
        "event_count": event_count,
        "result_digest": resolved_result_digest,
        "artifact_paths": _artifact_path_summary(
            artifact_paths or {},
            artifact_root=artifact_root,
        ),
    }
    if created_at is not None:
        manifest_kwargs["created_at"] = created_at
    return LiveSmokeRunManifest(**manifest_kwargs)


def _runtime_manifest_reference(provider_profile: str) -> str | None:
    try:
        runtime_manifest = load_runtime_manifest(provider_profile)
    except WorldForgeError:
        return None
    return f"{runtime_manifest.provider}:schema-{runtime_manifest.schema_version}"


def _resolved_result_digest(
    *,
    result_digest: str | None,
    result: Mapping[str, Any] | None,
) -> str | None:
    if result_digest is not None or result is None:
        return result_digest
    return digest_json_value(dict(result))


def _resolved_input_digests(
    *,
    input_digest: str | None,
    input_fixture: Path | str | None,
    input_summary: Mapping[str, Any] | None,
) -> tuple[str | None, str | None]:
    input_fixture_digest = digest_file(input_fixture) if input_fixture is not None else None
    if input_digest is not None:
        return input_digest, input_fixture_digest
    if input_fixture_digest is not None:
        return input_fixture_digest, input_fixture_digest
    if input_summary:
        return digest_json_value(dict(input_summary)), input_fixture_digest
    return None, input_fixture_digest


def write_run_manifest(
    path: Path | str, manifest: LiveSmokeRunManifest | Mapping[str, Any]
) -> Path:
    """Write a validated run manifest to ``path`` and return the resolved path."""

    payload = manifest.to_dict() if isinstance(manifest, LiveSmokeRunManifest) else dict(manifest)
    output_path = Path(path).expanduser()
    return write_json_artifact(output_path, validate_run_manifest(payload))


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
    """Return a stable sha256 digest for a JSON-like summary."""

    payload = dump_json(require_json_dict(_json_native(dict(value)), name="Run manifest result"))
    return f"sha256:{hashlib.sha256(payload.encode('utf-8')).hexdigest()}"


def validate_run_manifest(payload: Mapping[str, Any]) -> JSONDict:
    """Validate the manifest shape and reject unsanitized secrets or signed URLs."""

    manifest = require_json_dict(dict(payload), name="Run manifest")
    _validate_run_manifest_schema(manifest)
    manifest["status"] = _require_run_manifest_status(manifest["status"])
    _validate_run_manifest_command(manifest.get("command_argv"))
    require_non_negative_int(manifest.get("event_count"), name="Run manifest event_count")
    _require_manifest_list(manifest.get("env_summary"), field_name="env_summary")
    manifest["artifact_paths"] = _validate_run_manifest_artifacts(manifest.get("artifact_paths"))
    manifest["runtime_assets"] = _validate_run_manifest_runtime_assets(
        manifest.get("runtime_assets", [])
    )
    if manifest.get("config_profile") is not None:
        manifest["config_profile"] = validate_config_profile_provenance(manifest["config_profile"])
    manifest["input_summary"] = _validate_run_manifest_input_summary(
        manifest.get("input_summary", {})
    )
    _reject_secret_like_values(manifest)
    _reject_unsafe_strings(manifest)
    return manifest


def _validate_run_manifest_schema(manifest: Mapping[str, Any]) -> None:
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


def _validate_run_manifest_command(argv: object) -> None:
    if (
        not isinstance(argv, list)
        or not argv
        or any(not isinstance(item, str) or not item.strip() for item in argv)
    ):
        raise WorldForgeError("Run manifest command_argv must be a non-empty string list.")


def _validate_run_manifest_artifacts(value: object) -> JSONDict:
    if not isinstance(value, dict):
        raise WorldForgeError("Run manifest artifact_paths must be an object.")
    return _validate_artifact_path_references(value)


def _validate_run_manifest_runtime_assets(value: object) -> list[JSONDict]:
    runtime_assets = _require_manifest_list(value, field_name="runtime_assets")
    return [
        validate_runtime_asset_manifest(
            asset,
            source=f"Run manifest runtime_assets[{index}]",
            include_local_fields=False,
        )
        for index, asset in enumerate(runtime_assets)
    ]


def _validate_run_manifest_input_summary(value: object) -> JSONDict:
    if not isinstance(value, dict):
        raise WorldForgeError("Run manifest input_summary must be an object.")
    return value


def _require_manifest_list(value: object, *, field_name: str) -> list[object]:
    if not isinstance(value, list):
        raise WorldForgeError(f"Run manifest {field_name} must be a list.")
    return value


def _artifact_path_summary(
    paths: Mapping[str, Path | str],
    *,
    artifact_root: Path | str | None = None,
) -> JSONDict:
    root = Path(artifact_root).expanduser().resolve() if artifact_root is not None else None
    artifacts: JSONDict = {}
    for name, raw_path in paths.items():
        if not isinstance(name, str) or not name.strip():
            raise WorldForgeError("Run manifest artifact names must be non-empty strings.")
        artifacts[name] = _sanitize_path_or_url(raw_path, artifact_root=root)
    return artifacts


def _validate_artifact_path_references(paths: Mapping[str, Any]) -> JSONDict:
    artifacts: JSONDict = {}
    for name, raw_path in paths.items():
        if not isinstance(name, str) or not name.strip():
            raise WorldForgeError("Run manifest artifact names must be non-empty strings.")
        if not isinstance(raw_path, str):
            raise WorldForgeError("Run manifest artifact paths must be strings.")
        sanitized = _sanitize_path_or_url(raw_path)
        if sanitized != raw_path:
            raise WorldForgeError(
                "Run manifest artifact paths must already be normalized safe references."
            )
        artifacts[name] = sanitized
    return artifacts


def _runtime_asset_summary(
    assets: Sequence[RuntimeAssetManifest | Mapping[str, Any]],
) -> list[JSONDict]:
    summaries: list[JSONDict] = []
    for index, asset in enumerate(assets):
        if isinstance(asset, RuntimeAssetManifest):
            summaries.append(asset.to_reference())
        else:
            summaries.append(
                validate_runtime_asset_manifest(
                    asset,
                    source=f"runtime asset {index}",
                    include_local_fields=False,
                )
            )
    return summaries


def _sanitize_path_or_url(value: Path | str, *, artifact_root: Path | None = None) -> str:
    text = _artifact_path_text(value)
    parts = urlsplit(text)
    if parts.scheme or parts.netloc:
        return _sanitize_artifact_url(text, parts)
    _reject_artifact_url_tail(parts)
    _reject_artifact_env_expansion(text)
    return _sanitize_artifact_path(value, text, artifact_root=artifact_root)


def _artifact_path_text(value: Path | str) -> str:
    text = str(value).strip()
    if not text:
        raise WorldForgeError("Run manifest artifact path must be non-empty.")
    return text


def _sanitize_artifact_url(text: str, parts: SplitResult) -> str:
    if parts.scheme not in {"http", "https"} or not parts.netloc:
        raise WorldForgeError(
            "Run manifest artifact paths must be relative paths or sanitized HTTP(S) URLs."
        )
    sanitized = _sanitize_observable_target(text)
    if sanitized is None:
        raise WorldForgeError("Run manifest artifact path must be non-empty.")
    return sanitized


def _reject_artifact_url_tail(parts: SplitResult) -> None:
    if parts.query or parts.fragment:
        raise WorldForgeError("Run manifest artifact paths must not contain query strings.")


def _reject_artifact_env_expansion(text: str) -> None:
    if text.startswith(("$", "%")):
        raise WorldForgeError("Run manifest artifact paths must not use environment expansion.")


def _sanitize_artifact_path(
    value: Path | str,
    text: str,
    *,
    artifact_root: Path | None,
) -> str:
    candidate = Path(text).expanduser()
    rooted_path = _artifact_path_relative_to_root(
        value,
        text,
        candidate,
        artifact_root=artifact_root,
    )
    if rooted_path is not None:
        return rooted_path
    if candidate.is_absolute() or text.startswith("~"):
        raise WorldForgeError("Run manifest artifact paths must not be absolute host paths.")
    if PureWindowsPath(text).drive:
        raise WorldForgeError("Run manifest artifact paths must not include Windows drive names.")
    sanitized = _safe_relative_artifact_path(text)
    if sanitized is None:
        raise WorldForgeError("Run manifest artifact path must be non-empty.")
    return sanitized


def _artifact_path_relative_to_root(
    value: Path | str,
    text: str,
    candidate: Path,
    *,
    artifact_root: Path | None,
) -> str | None:
    if artifact_root is None:
        return None
    try:
        return _relative_artifact_path(candidate.resolve(), root=artifact_root)
    except ValueError:
        if isinstance(value, Path) or candidate.is_absolute() or text.startswith("~"):
            raise WorldForgeError(
                "Run manifest artifact paths must not reference host-local paths "
                "outside the run directory."
            ) from None
    return None


def _relative_artifact_path(path: Path, *, root: Path) -> str:
    relative = path.relative_to(root)
    return _safe_relative_artifact_path(relative.as_posix())


def _safe_relative_artifact_path(value: str) -> str:
    path = PurePosixPath(value.replace("\\", "/"))
    if str(path) == "." or not path.parts:
        raise WorldForgeError("Run manifest artifact path must be non-empty.")
    if path.is_absolute():
        raise WorldForgeError("Run manifest artifact paths must not be absolute host paths.")
    if ".." in path.parts:
        raise WorldForgeError("Run manifest artifact paths must not contain traversal.")
    if PureWindowsPath(value).drive:
        raise WorldForgeError("Run manifest artifact paths must not include Windows drive names.")
    return path.as_posix()


def _reject_unsafe_strings(value: object, *, path: str = "manifest") -> None:
    if isinstance(value, str):
        _reject_unsafe_manifest_string(value, path=path)
        return
    if isinstance(value, list):
        _reject_unsafe_manifest_sequence(value, path=path)
        return
    if isinstance(value, dict):
        _reject_unsafe_manifest_mapping(value, path=path)


def _reject_unsafe_manifest_string(value: str, *, path: str) -> None:
    if _sanitized_observable_target(value) != value:
        raise WorldForgeError(f"Run manifest {path} contains an unsafe URL or secret.")


def _sanitized_observable_target(value: str) -> str:
    try:
        return _sanitize_observable_target(value)
    except WorldForgeError:
        return value


def _reject_unsafe_manifest_sequence(values: list[object], *, path: str) -> None:
    for index, item in enumerate(values):
        _reject_unsafe_strings(item, path=f"{path}[{index}]")


def _reject_unsafe_manifest_mapping(values: dict[object, object], *, path: str) -> None:
    for key, item in values.items():
        _reject_unsafe_strings(item, path=f"{path}.{key}")


def _reject_secret_like_values(value: object, *, path: str = "manifest") -> None:
    if isinstance(value, dict):
        _reject_secret_like_mapping(value, path=path)
        return
    if isinstance(value, list):
        _reject_secret_like_sequence(value, path=path)
        return
    if isinstance(value, str):
        _reject_secret_like_string(value)


def _reject_secret_like_mapping(values: dict[object, object], *, path: str) -> None:
    for key, item in values.items():
        child_path = f"{path}.{key}"
        _reject_secret_like_key(str(key), path=child_path)
        _reject_secret_like_values(item, path=child_path)


def _reject_secret_like_key(key: str, *, path: str) -> None:
    if _looks_sensitive_key(key) and not _is_env_summary_field(path):
        raise WorldForgeError("Run manifest contains secret-like metadata.")


def _is_env_summary_field(path: str) -> bool:
    return path.startswith("manifest.env_summary[")


def _reject_secret_like_sequence(values: list[object], *, path: str) -> None:
    for index, item in enumerate(values):
        _reject_secret_like_values(item, path=f"{path}[{index}]")


def _reject_secret_like_string(value: str) -> None:
    if _redact_observable_value(value) != value:
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


def _require_run_manifest_status(value: object) -> str:
    if not isinstance(value, str) or value not in _RUN_MANIFEST_STATUSES:
        raise WorldForgeError("Run manifest status must be passed, failed, or skipped.")
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

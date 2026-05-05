"""Validation helpers for host-owned spatial scene artifacts.

Scene artifacts are JSON descriptors for future 3D/spatial provider outputs. They intentionally
do not fetch assets, render previews, run simulators, or certify physical validity.
"""

from __future__ import annotations

import ipaddress
import re
from pathlib import PurePosixPath, PureWindowsPath
from urllib.parse import urlsplit

from worldforge.models import JSONDict, WorldForgeError, dump_json, require_json_dict

SCENE_ARTIFACT_KIND = "worldforge.scene_artifact"
SCENE_ARTIFACT_SCHEMA_VERSION = "1"
SCENE_ARTIFACT_UNITS = frozenset({"meter", "centimeter", "millimeter", "unitless"})
SCENE_ARTIFACT_AXES = frozenset({"x", "y", "z"})
SCENE_ARTIFACT_HANDEDNESS = frozenset({"left", "right"})
SCENE_ARTIFACT_MAX_METADATA_BYTES = 2048

_DIGEST_PATTERN = re.compile(r"^sha256:[A-Za-z0-9._:-]+$")
_SECRET_FIELD_PATTERN = re.compile(
    r"(api[_-]?key|authorization|credential|password|secret|signature|signed[_-]?url|token)",
    re.IGNORECASE,
)


def validate_scene_artifact(payload: object, *, name: str = "Scene artifact") -> JSONDict:
    """Return a validated JSON-native scene artifact copy.

    The validator enforces the checkout-safe contract documented in
    ``docs/src/spatial-scene-artifact-boundary.md``. Host-local asset references are accepted only
    when their descriptor explicitly sets ``local_only: true``.
    """

    artifact = require_json_dict(payload, name=name, allow_empty=False)
    _require_literal(
        artifact.get("schema_version"),
        expected=SCENE_ARTIFACT_SCHEMA_VERSION,
        name=f"{name} schema_version",
    )
    _require_literal(artifact.get("kind"), expected=SCENE_ARTIFACT_KIND, name=f"{name} kind")
    _require_non_empty_string(artifact.get("provider"), name=f"{name} provider")
    _require_literal(artifact.get("capability"), expected="generate", name=f"{name} capability")
    _require_choice(artifact.get("units"), choices=SCENE_ARTIFACT_UNITS, name=f"{name} units")
    _validate_coordinate_frame(artifact.get("coordinate_frame"), name=f"{name} coordinate_frame")
    _validate_objects(artifact.get("objects"), name=f"{name} objects")
    _validate_assets(artifact.get("assets"), name=f"{name} assets")
    if "media" in artifact:
        _validate_assets(artifact.get("media"), name=f"{name} media")
    _validate_provenance(artifact.get("provenance"), name=f"{name} provenance")
    if "metadata" in artifact:
        _validate_metadata(artifact["metadata"], name=f"{name} metadata")
    return artifact


def _validate_coordinate_frame(value: object, *, name: str) -> None:
    frame = _require_json_object(value, name=name)
    up_axis = _require_choice(
        frame.get("up_axis"),
        choices=SCENE_ARTIFACT_AXES,
        name=f"{name}.up_axis",
    )
    forward_axis = _require_choice(
        frame.get("forward_axis"),
        choices=SCENE_ARTIFACT_AXES,
        name=f"{name}.forward_axis",
    )
    if up_axis == forward_axis:
        raise WorldForgeError(f"{name} up_axis and forward_axis must differ.")
    _require_choice(
        frame.get("handedness"),
        choices=SCENE_ARTIFACT_HANDEDNESS,
        name=f"{name}.handedness",
    )


def _validate_objects(value: object, *, name: str) -> None:
    objects = _require_list(value, name=name, allow_empty=True)
    seen_ids: set[str] = set()
    for index, item in enumerate(objects):
        object_name = f"{name}[{index}]"
        scene_object = _require_json_object(item, name=object_name)
        object_id = _require_non_empty_string(scene_object.get("id"), name=f"{object_name}.id")
        if object_id in seen_ids:
            raise WorldForgeError(f"{object_name}.id must be unique.")
        seen_ids.add(object_id)
        if "label" in scene_object:
            _require_non_empty_string(scene_object["label"], name=f"{object_name}.label")
        _validate_transform(scene_object.get("transform"), name=f"{object_name}.transform")
        if "bbox" in scene_object:
            _validate_bbox(scene_object["bbox"], name=f"{object_name}.bbox")
        if "asset_refs" in scene_object:
            for ref_index, ref in enumerate(
                _require_list(scene_object["asset_refs"], name=f"{object_name}.asset_refs")
            ):
                _require_non_empty_string(ref, name=f"{object_name}.asset_refs[{ref_index}]")
        if "metadata" in scene_object:
            _validate_metadata(scene_object["metadata"], name=f"{object_name}.metadata")


def _validate_transform(value: object, *, name: str) -> None:
    transform = _require_json_object(value, name=name)
    _require_number_sequence(
        transform.get("translation"),
        length=3,
        name=f"{name}.translation",
    )
    _require_number_sequence(
        transform.get("rotation_quat"),
        length=4,
        name=f"{name}.rotation_quat",
    )
    scale = _require_number_sequence(transform.get("scale"), length=3, name=f"{name}.scale")
    if any(number <= 0.0 for number in scale):
        raise WorldForgeError(f"{name}.scale values must be greater than 0.")


def _validate_bbox(value: object, *, name: str) -> None:
    bbox = _require_json_object(value, name=name)
    min_values = _require_number_sequence(bbox.get("min"), length=3, name=f"{name}.min")
    max_values = _require_number_sequence(bbox.get("max"), length=3, name=f"{name}.max")
    if any(
        min_value > max_value for min_value, max_value in zip(min_values, max_values, strict=True)
    ):
        raise WorldForgeError(f"{name} min coordinates must be less than or equal to max.")


def _validate_assets(value: object, *, name: str) -> None:
    assets = _require_list(value, name=name, allow_empty=True)
    seen_ids: set[str] = set()
    for index, item in enumerate(assets):
        asset_name = f"{name}[{index}]"
        asset = _require_json_object(item, name=asset_name)
        asset_id = _require_non_empty_string(asset.get("id"), name=f"{asset_name}.id")
        if asset_id in seen_ids:
            raise WorldForgeError(f"{asset_name}.id must be unique.")
        seen_ids.add(asset_id)
        _require_non_empty_string(asset.get("role"), name=f"{asset_name}.role")
        _require_digest(asset.get("digest"), name=f"{asset_name}.digest")
        local_only = _optional_bool(asset.get("local_only", False), name=f"{asset_name}.local_only")
        if "mime_type" in asset:
            _require_non_empty_string(asset["mime_type"], name=f"{asset_name}.mime_type")
        if "size_bytes" in asset:
            size_bytes = asset["size_bytes"]
            if isinstance(size_bytes, bool) or not isinstance(size_bytes, int) or size_bytes < 0:
                raise WorldForgeError(f"{asset_name}.size_bytes must be a non-negative integer.")
        if "uri" in asset:
            _validate_uri(asset["uri"], local_only=local_only, name=f"{asset_name}.uri")
        if "metadata" in asset:
            _validate_metadata(asset["metadata"], name=f"{asset_name}.metadata")


def _validate_provenance(value: object, *, name: str) -> None:
    provenance = _require_json_object(value, name=name)
    for field_name in ("runtime_manifest", "command"):
        if field_name in provenance:
            _require_non_empty_string(provenance[field_name], name=f"{name}.{field_name}")
    for field_name in ("input_digest", "result_digest"):
        _require_digest(provenance.get(field_name), name=f"{name}.{field_name}")
    if "event_count" in provenance:
        event_count = provenance["event_count"]
        if isinstance(event_count, bool) or not isinstance(event_count, int) or event_count < 0:
            raise WorldForgeError(f"{name}.event_count must be a non-negative integer.")
    if "limitations" in provenance:
        limitations = _require_list(provenance["limitations"], name=f"{name}.limitations")
        for index, limitation in enumerate(limitations):
            _require_non_empty_string(limitation, name=f"{name}.limitations[{index}]")


def _validate_metadata(value: object, *, name: str) -> None:
    metadata = _require_json_object(value, name=name)
    _reject_secret_like_metadata_keys(metadata, name=name)
    size = len(dump_json(metadata).encode("utf-8"))
    if size > SCENE_ARTIFACT_MAX_METADATA_BYTES:
        raise WorldForgeError(
            f"{name} must be {SCENE_ARTIFACT_MAX_METADATA_BYTES} bytes or smaller."
        )


def _reject_secret_like_metadata_keys(value: object, *, name: str) -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            if _SECRET_FIELD_PATTERN.search(key):
                raise WorldForgeError(f"{name} key '{key}' is secret-like and must be redacted.")
            _reject_secret_like_metadata_keys(item, name=f"{name}.{key}")
    elif isinstance(value, list):
        for index, item in enumerate(value):
            _reject_secret_like_metadata_keys(item, name=f"{name}[{index}]")


def _validate_uri(value: object, *, local_only: bool, name: str) -> None:
    uri = _require_non_empty_string(value, name=name)
    try:
        parts = urlsplit(uri)
    except ValueError as exc:
        raise WorldForgeError(f"{name} must be a safe relative path or URL.") from exc
    if parts.username or parts.password or parts.query or parts.fragment:
        raise WorldForgeError(f"{name} must not include userinfo, query strings, or fragments.")
    if parts.scheme:
        scheme = parts.scheme.lower()
        if scheme == "file":
            if local_only:
                return
            raise WorldForgeError(f"{name} file URI requires local_only=true.")
        if scheme not in {"http", "https"}:
            raise WorldForgeError(f"{name} must use https or a relative artifact path.")
        host = parts.hostname or ""
        if _is_private_or_loopback_host(host):
            if local_only:
                return
            raise WorldForgeError(f"{name} host-local URL requires local_only=true.")
        if scheme != "https":
            raise WorldForgeError(f"{name} public remote URL must use https.")
        return
    if (
        PurePosixPath(uri).is_absolute()
        or PureWindowsPath(uri).is_absolute()
        or uri.startswith("~")
    ):
        if local_only:
            return
        raise WorldForgeError(f"{name} host-local path requires local_only=true.")
    if ".." in PurePosixPath(uri).parts or ".." in PureWindowsPath(uri).parts:
        raise WorldForgeError(f"{name} must not contain path traversal.")


def _is_private_or_loopback_host(host: str) -> bool:
    normalized = host.strip().lower()
    if not normalized or normalized == "localhost" or normalized.endswith(".local"):
        return True
    try:
        address = ipaddress.ip_address(normalized.strip("[]"))
    except ValueError:
        return False
    return address.is_private or address.is_loopback or address.is_link_local


def _require_json_object(value: object, *, name: str) -> JSONDict:
    if not isinstance(value, dict):
        raise WorldForgeError(f"{name} must be a JSON object.")
    return value


def _require_list(value: object, *, name: str, allow_empty: bool = False) -> list[object]:
    if not isinstance(value, list):
        raise WorldForgeError(f"{name} must be a JSON list.")
    if not allow_empty and not value:
        raise WorldForgeError(f"{name} must not be empty.")
    return value


def _require_number_sequence(value: object, *, length: int, name: str) -> list[float]:
    if not isinstance(value, list) or len(value) != length:
        raise WorldForgeError(f"{name} must be a JSON list with {length} finite numbers.")
    numbers: list[float] = []
    for index, item in enumerate(value):
        if isinstance(item, bool) or not isinstance(item, int | float):
            raise WorldForgeError(f"{name}[{index}] must be a finite number.")
        numbers.append(float(item))
    return numbers


def _require_non_empty_string(value: object, *, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise WorldForgeError(f"{name} must be a non-empty string.")
    return value


def _require_literal(value: object, *, expected: str, name: str) -> str:
    if value != expected:
        raise WorldForgeError(f"{name} must be {expected!r}.")
    return expected


def _require_choice(value: object, *, choices: frozenset[str], name: str) -> str:
    if not isinstance(value, str) or value not in choices:
        formatted = ", ".join(sorted(choices))
        raise WorldForgeError(f"{name} must be one of: {formatted}.")
    return value


def _require_digest(value: object, *, name: str) -> str:
    digest = _require_non_empty_string(value, name=name)
    if not _DIGEST_PATTERN.match(digest):
        raise WorldForgeError(f"{name} must be a sha256 digest string.")
    return digest


def _optional_bool(value: object, *, name: str) -> bool:
    if not isinstance(value, bool):
        raise WorldForgeError(f"{name} must be a boolean.")
    return value


__all__ = [
    "SCENE_ARTIFACT_KIND",
    "SCENE_ARTIFACT_MAX_METADATA_BYTES",
    "SCENE_ARTIFACT_SCHEMA_VERSION",
    "validate_scene_artifact",
]

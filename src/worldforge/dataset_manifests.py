"""Dataset manifest contracts for evaluation evidence without dataset storage."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlsplit

from worldforge.models import JSONDict, WorldForgeError, dump_json, require_json_dict

DATASET_MANIFEST_SCHEMA_VERSION = 1
DATASET_MANIFEST_ENTRY_KINDS: tuple[str, ...] = (
    "local-fixture",
    "remote-reference",
    "host-asset",
)
DATASET_MANIFEST_PRIVACY_CLASSIFICATIONS: tuple[str, ...] = (
    "public",
    "restricted",
    "sensitive",
)
MAX_LOCAL_FIXTURE_BYTES = 1_000_000

_SAFE_LOCAL_SUFFIXES = {".json", ".jsonl", ".csv", ".txt", ".md"}
_REQUIRED_PROVENANCE_FIELDS = ("source", "version", "owner")


@dataclass(frozen=True, slots=True)
class DatasetManifestEntry:
    """One dataset, fixture, or host-owned asset reference inside a manifest."""

    id: str
    kind: str
    description: str
    sha256: str
    path: str | None = None
    uri: str | None = None
    asset_id: str | None = None
    license: str | None = None
    metadata: JSONDict = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "id", _required_text(self.id, name="DatasetManifestEntry id"))
        object.__setattr__(
            self,
            "kind",
            _entry_kind(self.kind, name="DatasetManifestEntry kind"),
        )
        object.__setattr__(
            self,
            "description",
            _required_text(self.description, name="DatasetManifestEntry description"),
        )
        object.__setattr__(
            self,
            "sha256",
            _sha256_digest(self.sha256, name="DatasetManifestEntry sha256"),
        )
        object.__setattr__(
            self,
            "license",
            _optional_text(self.license, name="DatasetManifestEntry license"),
        )
        object.__setattr__(
            self,
            "metadata",
            _json_mapping(self.metadata, name="DatasetManifestEntry metadata"),
        )
        _normalize_entry_reference_fields(self)

    def to_dict(self) -> JSONDict:
        payload: JSONDict = {
            "id": self.id,
            "kind": self.kind,
            "description": self.description,
            "sha256": self.sha256,
            "metadata": dict(self.metadata),
        }
        if self.path is not None:
            payload["path"] = self.path
        if self.uri is not None:
            payload["uri"] = self.uri
        if self.asset_id is not None:
            payload["asset_id"] = self.asset_id
        if self.license is not None:
            payload["license"] = self.license
        return payload

    @classmethod
    def from_dict(
        cls,
        payload: Mapping[str, object],
        *,
        source: str,
        root: Path | None = None,
    ) -> DatasetManifestEntry:
        if not isinstance(payload, Mapping):
            raise WorldForgeError(f"{source} dataset manifest entry must be a JSON object.")
        entry_id = _required_text(payload.get("id"), name=f"{source}.id")
        kind = _required_text(payload.get("kind"), name=f"{source}.kind")
        if kind not in DATASET_MANIFEST_ENTRY_KINDS:
            allowed = ", ".join(DATASET_MANIFEST_ENTRY_KINDS)
            raise WorldForgeError(f"{source}.kind must be one of: {allowed}.")
        description = _required_text(payload.get("description"), name=f"{source}.description")
        sha256 = _sha256_digest(payload.get("sha256"), name=f"{source}.sha256")
        license_note = _optional_text(payload.get("license"), name=f"{source}.license")
        metadata_value = payload.get("metadata", {})
        metadata = _json_mapping(
            {} if metadata_value is None else metadata_value,
            name=f"{source}.metadata",
        )

        path: str | None = None
        uri: str | None = None
        asset_id: str | None = None
        if kind == "local-fixture":
            path = _safe_relative_path(payload.get("path"), name=f"{source}.path")
            _validate_local_fixture(path, sha256=sha256, root=root, source=source)
        elif kind == "remote-reference":
            uri = _safe_remote_uri(payload.get("uri"), name=f"{source}.uri")
        else:
            asset_id = _required_text(payload.get("asset_id"), name=f"{source}.asset_id")
            if "path" in payload:
                raise WorldForgeError(
                    f"{source}.path must not be used for host-owned assets; record "
                    "host_acquisition_steps instead."
                )

        return cls(
            id=entry_id,
            kind=kind,
            description=description,
            sha256=sha256,
            path=path,
            uri=uri,
            asset_id=asset_id,
            license=license_note,
            metadata=metadata,
        )


@dataclass(frozen=True, slots=True)
class DatasetManifest:
    """Schema-versioned manifest for evaluation dataset references."""

    id: str
    name: str
    description: str
    license: str
    provenance: JSONDict
    privacy: JSONDict
    safety: JSONDict
    host_acquisition_steps: tuple[str, ...]
    entries: tuple[DatasetManifestEntry, ...]
    metadata: JSONDict = field(default_factory=dict)
    schema_version: int = DATASET_MANIFEST_SCHEMA_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "schema_version",
            _schema_version(self.schema_version, source="direct construction"),
        )
        object.__setattr__(self, "id", _required_text(self.id, name="DatasetManifest id"))
        object.__setattr__(self, "name", _required_text(self.name, name="DatasetManifest name"))
        object.__setattr__(
            self,
            "description",
            _required_text(self.description, name="DatasetManifest description"),
        )
        object.__setattr__(
            self,
            "license",
            _required_text(self.license, name="DatasetManifest license"),
        )
        object.__setattr__(
            self,
            "provenance",
            _provenance_payload(self.provenance, source="DatasetManifest"),
        )
        object.__setattr__(
            self,
            "privacy",
            _privacy_payload(self.privacy, source="DatasetManifest"),
        )
        object.__setattr__(
            self,
            "safety",
            _safety_payload(self.safety, source="DatasetManifest"),
        )
        object.__setattr__(
            self,
            "host_acquisition_steps",
            _string_tuple(
                self.host_acquisition_steps,
                name="DatasetManifest host_acquisition_steps",
            ),
        )
        object.__setattr__(self, "entries", _manifest_entries(self.entries))
        object.__setattr__(
            self,
            "metadata",
            _json_mapping(self.metadata, name="DatasetManifest metadata"),
        )

    @classmethod
    def from_dict(
        cls,
        payload: Mapping[str, object],
        *,
        source: str = "<dict>",
        root: Path | None = None,
    ) -> DatasetManifest:
        if not isinstance(payload, Mapping):
            raise WorldForgeError(f"Dataset manifest {source} must be a JSON object.")
        schema_version = _schema_version(payload.get("schema_version"), source=source)
        entries_payload = payload.get("entries")
        if not isinstance(entries_payload, list) or not entries_payload:
            raise WorldForgeError(f"Dataset manifest {source} entries must be a non-empty list.")
        manifest = cls(
            id=_required_text(payload.get("id"), name=f"Dataset manifest {source} id"),
            name=_required_text(payload.get("name"), name=f"Dataset manifest {source} name"),
            description=_required_text(
                payload.get("description"),
                name=f"Dataset manifest {source} description",
            ),
            license=_required_text(
                payload.get("license"),
                name=f"Dataset manifest {source} license",
            ),
            provenance=_provenance_payload(payload.get("provenance"), source=source),
            privacy=_privacy_payload(payload.get("privacy"), source=source),
            safety=_safety_payload(payload.get("safety"), source=source),
            host_acquisition_steps=_string_tuple(
                payload.get("host_acquisition_steps"),
                name=f"Dataset manifest {source} host_acquisition_steps",
            ),
            entries=tuple(
                DatasetManifestEntry.from_dict(
                    entry,
                    source=f"Dataset manifest {source} entries[{index}]",
                    root=root,
                )
                for index, entry in enumerate(entries_payload)
            ),
            metadata=_json_mapping(
                {} if payload.get("metadata") is None else payload.get("metadata", {}),
                name=f"Dataset manifest {source} metadata",
            ),
            schema_version=schema_version,
        )
        dump_json(manifest.to_dict())
        return manifest

    @property
    def entry_count(self) -> int:
        return len(self.entries)

    def to_dict(self) -> JSONDict:
        return {
            "schema_version": self.schema_version,
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "license": self.license,
            "provenance": dict(self.provenance),
            "privacy": dict(self.privacy),
            "safety": dict(self.safety),
            "host_acquisition_steps": list(self.host_acquisition_steps),
            "entries": [entry.to_dict() for entry in self.entries],
            "metadata": dict(self.metadata),
        }

    def to_json(self, *, indent: int = 2) -> str:
        return dump_json(self.to_dict(), indent=indent) + "\n"

    def digest(self) -> str:
        encoded = dump_json(self.to_dict()).encode("utf-8")
        return f"sha256:{hashlib.sha256(encoded).hexdigest()}"

    def to_reference(self, *, path: Path | str | None = None, root: Path | None = None) -> JSONDict:
        reference: JSONDict = {
            "schema_version": self.schema_version,
            "id": self.id,
            "name": self.name,
            "sha256": self.digest(),
            "entry_count": self.entry_count,
            "license": self.license,
            "privacy": {
                "classification": self.privacy["classification"],
                "contains_personal_data": self.privacy["contains_personal_data"],
            },
            "safety": {
                "reviewed": self.safety["reviewed"],
                "contains_sensitive_capability_data": self.safety[
                    "contains_sensitive_capability_data"
                ],
                "contains_robot_logs": self.safety["contains_robot_logs"],
            },
            "host_owned": True,
        }
        if path is not None:
            display_path = _repo_relative_reference_path(path, root=root)
            if display_path is None:
                reference["local_only"] = True
            else:
                reference["path"] = display_path
        dump_json(reference)
        return reference


def load_dataset_manifest(
    path: Path | str,
    *,
    root: Path | None = None,
) -> DatasetManifest:
    """Load and validate a dataset manifest JSON file."""

    target = Path(path).expanduser()
    try:
        payload = json.loads(target.read_text(encoding="utf-8"))
    except OSError as exc:
        raise WorldForgeError(f"Failed to read dataset manifest {target}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise WorldForgeError(f"Dataset manifest {target} contains invalid JSON: {exc}") from exc
    return parse_dataset_manifest(payload, source=str(target), root=root or Path.cwd())


def parse_dataset_manifest(
    payload: Mapping[str, object] | str,
    *,
    source: str = "<dict>",
    root: Path | None = None,
) -> DatasetManifest:
    """Parse and validate a dataset manifest from JSON or a mapping."""

    if isinstance(payload, str):
        try:
            decoded = json.loads(payload)
        except json.JSONDecodeError as exc:
            raise WorldForgeError(
                f"Dataset manifest <string> contains invalid JSON: {exc}"
            ) from exc
        if not isinstance(decoded, dict):
            raise WorldForgeError("Dataset manifest <string> must be a JSON object.")
        return DatasetManifest.from_dict(
            _require_manifest_payload(decoded, source="<string>"),
            source="<string>",
            root=root,
        )
    return DatasetManifest.from_dict(
        _require_manifest_payload(payload, source=source),
        source=source,
        root=root,
    )


def dataset_manifest_reference(
    manifest: DatasetManifest | Mapping[str, object] | Path | str,
    *,
    root: Path | None = None,
) -> JSONDict:
    """Return the provenance-safe reference for a manifest-like value."""

    if isinstance(manifest, DatasetManifest):
        return manifest.to_reference(root=root)
    if isinstance(manifest, Path):
        loaded = load_dataset_manifest(manifest, root=root)
        return loaded.to_reference(path=manifest, root=root)
    if isinstance(manifest, str):
        path = Path(manifest)
        if path.exists():
            loaded = load_dataset_manifest(path, root=root)
            return loaded.to_reference(path=path, root=root)
        loaded = parse_dataset_manifest(manifest, root=root)
        return loaded.to_reference(root=root)
    loaded = parse_dataset_manifest(manifest, root=root)
    return loaded.to_reference(root=root)


def dataset_manifest_references(
    manifests: Sequence[DatasetManifest | Mapping[str, object] | Path | str] | None,
    *,
    root: Path | None = None,
) -> tuple[JSONDict, ...]:
    if manifests is None:
        return ()
    if not isinstance(manifests, Sequence) or isinstance(manifests, str | bytes):
        raise WorldForgeError("dataset_manifests must be a sequence of manifest references.")
    return tuple(dataset_manifest_reference(manifest, root=root) for manifest in manifests)


def _required_text(value: object, *, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise WorldForgeError(f"{name} must be a non-empty string.")
    return value.strip()


def _optional_text(value: object, *, name: str) -> str | None:
    if value is None:
        return None
    return _required_text(value, name=name)


def _sha256_digest(value: object, *, name: str) -> str:
    digest = _required_text(value, name=name)
    prefix = "sha256:"
    hex_part = digest.removeprefix(prefix)
    if not digest.startswith(prefix) or len(hex_part) != 64:
        raise WorldForgeError(f"{name} must be a sha256:<64 hex> digest.")
    try:
        int(hex_part, 16)
    except ValueError as exc:
        raise WorldForgeError(f"{name} must be a sha256:<64 hex> digest.") from exc
    return digest


def _schema_version(value: object, *, source: str) -> int:
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or value != DATASET_MANIFEST_SCHEMA_VERSION
    ):
        raise WorldForgeError(
            f"Dataset manifest {source} schema_version must be "
            f"{DATASET_MANIFEST_SCHEMA_VERSION}, got {value!r}."
        )
    return DATASET_MANIFEST_SCHEMA_VERSION


def _entry_kind(value: object, *, name: str) -> str:
    kind = _required_text(value, name=name)
    if kind not in DATASET_MANIFEST_ENTRY_KINDS:
        allowed = ", ".join(DATASET_MANIFEST_ENTRY_KINDS)
        raise WorldForgeError(f"{name} must be one of: {allowed}.")
    return kind


def _normalize_entry_reference_fields(entry: DatasetManifestEntry) -> None:
    if entry.kind == "local-fixture":
        _normalize_local_fixture_entry(entry)
        return
    if entry.kind == "remote-reference":
        _normalize_remote_reference_entry(entry)
        return
    _normalize_host_asset_entry(entry)


def _normalize_local_fixture_entry(entry: DatasetManifestEntry) -> None:
    object.__setattr__(
        entry,
        "path",
        _safe_relative_path(entry.path, name="DatasetManifestEntry path"),
    )
    if entry.uri is not None or entry.asset_id is not None:
        raise WorldForgeError(
            "DatasetManifestEntry local fixtures must not include uri or asset_id."
        )


def _normalize_remote_reference_entry(entry: DatasetManifestEntry) -> None:
    object.__setattr__(
        entry,
        "uri",
        _safe_remote_uri(entry.uri, name="DatasetManifestEntry uri"),
    )
    if entry.path is not None or entry.asset_id is not None:
        raise WorldForgeError(
            "DatasetManifestEntry remote references must not include path or asset_id."
        )


def _normalize_host_asset_entry(entry: DatasetManifestEntry) -> None:
    object.__setattr__(
        entry,
        "asset_id",
        _required_text(entry.asset_id, name="DatasetManifestEntry asset_id"),
    )
    if entry.path is not None or entry.uri is not None:
        raise WorldForgeError("DatasetManifestEntry host assets must not include path or uri.")


def _manifest_entries(value: object) -> tuple[DatasetManifestEntry, ...]:
    if not isinstance(value, tuple) or not value:
        raise WorldForgeError("DatasetManifest entries must be a non-empty tuple.")
    if not all(isinstance(entry, DatasetManifestEntry) for entry in value):
        raise WorldForgeError("DatasetManifest entries must contain only DatasetManifestEntry.")
    return value


def _require_manifest_payload(value: object, *, source: str) -> JSONDict:
    try:
        return require_json_dict(value, name=f"Dataset manifest {source}")
    except WorldForgeError as exc:
        if not isinstance(value, dict):
            raise WorldForgeError(f"Dataset manifest {source} must be a JSON object.") from exc
        raise


def _json_mapping(value: object, *, name: str) -> JSONDict:
    return require_json_dict(value, name=name)


def _provenance_payload(value: object, *, source: str) -> JSONDict:
    payload = _json_mapping(value, name=f"Dataset manifest {source} provenance")
    for field_name in _REQUIRED_PROVENANCE_FIELDS:
        _required_text(
            payload.get(field_name),
            name=f"Dataset manifest {source} provenance.{field_name}",
        )
    return payload


def _privacy_payload(value: object, *, source: str) -> JSONDict:
    payload = _json_mapping(value, name=f"Dataset manifest {source} privacy")
    classification = _required_text(
        payload.get("classification"),
        name=f"Dataset manifest {source} privacy.classification",
    )
    if classification not in DATASET_MANIFEST_PRIVACY_CLASSIFICATIONS:
        allowed = ", ".join(DATASET_MANIFEST_PRIVACY_CLASSIFICATIONS)
        raise WorldForgeError(
            f"Dataset manifest {source} privacy.classification must be one of: {allowed}."
        )
    contains_personal_data = payload.get("contains_personal_data")
    if not isinstance(contains_personal_data, bool):
        raise WorldForgeError(
            f"Dataset manifest {source} privacy.contains_personal_data must be a boolean."
        )
    payload["classification"] = classification
    return payload


def _safety_payload(value: object, *, source: str) -> JSONDict:
    payload = _json_mapping(value, name=f"Dataset manifest {source} safety")
    for key in ("reviewed", "contains_sensitive_capability_data", "contains_robot_logs"):
        if not isinstance(payload.get(key), bool):
            raise WorldForgeError(f"Dataset manifest {source} safety.{key} must be a boolean.")
    return payload


def _string_tuple(value: object, *, name: str) -> tuple[str, ...]:
    if not isinstance(value, list | tuple) or not value:
        raise WorldForgeError(f"{name} must be a non-empty list of strings.")
    out = []
    for index, item in enumerate(value):
        out.append(_required_text(item, name=f"{name}[{index}]"))
    return tuple(out)


def _safe_relative_path(value: object, *, name: str) -> str:
    text = _required_text(value, name=name)
    raw = Path(text)
    if raw.is_absolute() or text.startswith("~") or "\\" in text or ":" in text:
        raise WorldForgeError(f"{name} must be a repository-relative safe path.")
    if any(part in {"", ".", ".."} for part in raw.parts):
        raise WorldForgeError(f"{name} must not contain traversal segments.")
    if raw.suffix.lower() not in _SAFE_LOCAL_SUFFIXES:
        raise WorldForgeError(f"{name} must reference a safe text or JSON fixture file.")
    return raw.as_posix()


def _validate_local_fixture(
    path: str,
    *,
    sha256: str,
    root: Path | None,
    source: str,
) -> None:
    if root is None:
        return
    root_path = root.expanduser().resolve()
    target = (root_path / path).resolve()
    if not _is_relative_to(target, root_path):
        raise WorldForgeError(f"{source}.path resolves outside the manifest root.")
    if not target.is_file():
        raise WorldForgeError(f"{source}.path local fixture does not exist: {path}")
    size = target.stat().st_size
    if size > MAX_LOCAL_FIXTURE_BYTES:
        raise WorldForgeError(
            f"{source}.path exceeds {MAX_LOCAL_FIXTURE_BYTES} bytes; do not store datasets here."
        )
    actual = _sha256_file(target)
    if actual != sha256:
        raise WorldForgeError(f"{source}.sha256 does not match local fixture {path}.")


def _safe_remote_uri(value: object, *, name: str) -> str:
    uri = _required_text(value, name=name)
    try:
        parsed = urlsplit(uri)
    except ValueError as exc:
        raise WorldForgeError(f"{name} must be a valid https URI.") from exc
    if parsed.scheme != "https" or not parsed.netloc:
        raise WorldForgeError(f"{name} must be a stable https URI.")
    if parsed.query or parsed.fragment:
        raise WorldForgeError(f"{name} must not include query strings or fragments.")
    return uri


def _repo_relative_reference_path(path: Path | str, *, root: Path | None) -> str | None:
    root_path = (root or Path.cwd()).expanduser().resolve()
    target = Path(path).expanduser().resolve()
    if not _is_relative_to(target, root_path):
        return None
    try:
        relative = target.relative_to(root_path)
    except ValueError:  # pragma: no cover - guarded by _is_relative_to
        return None
    if relative.suffix.lower() != ".json":
        return None
    return relative.as_posix()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return f"sha256:{digest.hexdigest()}"


def _is_relative_to(path: Path, root: Path) -> bool:
    return path == root or root in path.parents


__all__ = [
    "DATASET_MANIFEST_ENTRY_KINDS",
    "DATASET_MANIFEST_PRIVACY_CLASSIFICATIONS",
    "DATASET_MANIFEST_SCHEMA_VERSION",
    "DatasetManifest",
    "DatasetManifestEntry",
    "dataset_manifest_reference",
    "dataset_manifest_references",
    "load_dataset_manifest",
    "parse_dataset_manifest",
]

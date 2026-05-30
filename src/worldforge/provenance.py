"""Result provenance envelope for evaluation and benchmark reports.

The envelope wraps an :class:`EvaluationReport` or :class:`BenchmarkReport` with the metadata a
maintainer needs to substantiate a claim, reproduce a failure, or audit a release without
chasing console logs: WorldForge version, command, providers, capabilities, input fixture
digest, optional budget file digest, runtime manifest references, emitted ``ProviderEvent``
count, result digest, suite version, claim boundary, and metric semantics.

Envelopes are validated at construction so renderers cannot emit non-finite metrics, missing
suite names, or count mismatches: the report's ``to_dict`` raises :class:`WorldForgeError`
before producing JSON, Markdown, or CSV output.
"""

from __future__ import annotations

import hashlib
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

import worldforge
from worldforge.models import (
    JSONDict,
    WorldForgeError,
    dump_json,
    require_json_dict,
    require_non_negative_int,
)
from worldforge.providers.runtime_manifest import load_runtime_manifest

PROVENANCE_SCHEMA_VERSION = 2
EVALUATION_SUITE_CONTRACT_VERSION = 1
BENCHMARK_SUITE_CONTRACT_VERSION = 1

_SUPPORTED_KINDS = ("evaluation", "benchmark")


def _required_text(value: object, *, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise WorldForgeError(f"{name} must be a non-empty string.")
    return value.strip()


def _string_tuple(values: Sequence[str], *, name: str) -> tuple[str, ...]:
    if not isinstance(values, tuple | list) or any(
        not isinstance(item, str) or not item.strip() for item in values
    ):
        raise WorldForgeError(f"{name} must be a sequence of non-empty strings.")
    return tuple(item.strip() for item in values)


def _runtime_manifest_map(
    value: Mapping[str, str] | None,
    *,
    name: str,
) -> dict[str, str]:
    if value is None:
        return {}
    if not isinstance(value, Mapping):
        raise WorldForgeError(f"{name} must be a mapping of provider to manifest id.")
    out: dict[str, str] = {}
    for provider, manifest_id in value.items():
        if not isinstance(provider, str) or not provider.strip():
            raise WorldForgeError(f"{name} keys must be non-empty provider names.")
        if not isinstance(manifest_id, str) or not manifest_id.strip():
            raise WorldForgeError(f"{name} values must be non-empty manifest ids.")
        out[provider.strip()] = manifest_id.strip()
    return out


def _digest_or_none(value: object, *, name: str) -> str | None:
    if value is None:
        return None
    if (
        not isinstance(value, str)
        or not value.startswith("sha256:")
        or len(value) <= len("sha256:")
    ):
        raise WorldForgeError(f"{name} must be a 'sha256:<hex>' digest or None.")
    return value


def _budget_file_summary(value: object, *, name: str) -> JSONDict | None:
    if value is None:
        return None
    summary = require_json_dict(value, name=name)
    for key in ("path", "sha256"):
        candidate = summary.get(key)
        if not isinstance(candidate, str) or not candidate.strip():
            raise WorldForgeError(f"{name} '{key}' must be a non-empty string.")
    if "metadata" in summary and not isinstance(summary["metadata"], dict):
        raise WorldForgeError(f"{name} 'metadata' must be a JSON object when provided.")
    return summary


def _dataset_manifest_refs(value: object, *, name: str) -> tuple[JSONDict, ...]:
    if value is None:
        return ()
    if not isinstance(value, tuple | list):
        raise WorldForgeError(f"{name} must be a sequence of dataset manifest references.")
    return tuple(
        _dataset_manifest_ref(item, name=f"{name}[{index}]") for index, item in enumerate(value)
    )


def _dataset_manifest_ref(item: object, *, name: str) -> JSONDict:
    ref = require_json_dict(item, name=name)
    _require_dataset_manifest_text_fields(ref, name=name)
    _require_positive_dataset_entry_count(ref, name=name)
    _require_dataset_manifest_sections(ref, name=name)
    _require_optional_dataset_manifest_path(ref, name=name)
    return ref


def _require_dataset_manifest_text_fields(ref: JSONDict, *, name: str) -> None:
    for key in ("id", "name", "sha256", "license"):
        candidate = ref.get(key)
        if not isinstance(candidate, str) or not candidate.strip():
            raise WorldForgeError(f"{name} '{key}' must be a non-empty string.")
    _digest_or_none(ref["sha256"], name=f"{name} sha256")


def _require_positive_dataset_entry_count(ref: JSONDict, *, name: str) -> None:
    require_non_negative_int(ref.get("entry_count"), name=f"{name} entry_count")
    if ref["entry_count"] < 1:
        raise WorldForgeError(f"{name} entry_count must be greater than zero.")


def _require_dataset_manifest_sections(ref: JSONDict, *, name: str) -> None:
    for section in ("privacy", "safety"):
        if not isinstance(ref.get(section), dict):
            raise WorldForgeError(f"{name} '{section}' must be a JSON object.")


def _require_optional_dataset_manifest_path(ref: JSONDict, *, name: str) -> None:
    path = ref.get("path")
    if path is not None and (not isinstance(path, str) or not path.strip()):
        raise WorldForgeError(f"{name} path must be a non-empty string or omitted.")


@dataclass(frozen=True, slots=True)
class ProvenanceEnvelope:
    """Validated provenance metadata wrapping a report."""

    kind: str
    suite_id: str
    suite_version: str
    command: tuple[str, ...] = ()
    providers: tuple[str, ...] = ()
    capabilities: tuple[str, ...] = ()
    runtime_manifests: dict[str, str] = field(default_factory=dict)
    input_digest: str | None = None
    result_digest: str | None = None
    budget_file: JSONDict | None = None
    dataset_manifests: tuple[JSONDict, ...] = ()
    event_count: int = 0
    claim_boundary: str = ""
    metric_semantics: str = ""
    worldforge_version: str = field(default_factory=lambda: worldforge.__version__)
    schema_version: int = PROVENANCE_SCHEMA_VERSION
    created_at: str = field(
        default_factory=lambda: datetime.now(UTC).replace(microsecond=0).isoformat()
    )
    notes: str | None = None

    def __post_init__(self) -> None:
        _validate_provenance_kind(self.kind)
        _validate_provenance_schema_version(self.schema_version)
        _normalize_provenance_text_fields(self)
        _normalize_provenance_collection_fields(self)
        _normalize_provenance_reference_fields(self)
        _normalize_provenance_claim_fields(self)
        _validate_optional_provenance_notes(self.notes)

    def to_dict(self) -> JSONDict:
        payload: JSONDict = {
            "schema_version": self.schema_version,
            "kind": self.kind,
            "suite_id": self.suite_id,
            "suite_version": self.suite_version,
            "worldforge_version": self.worldforge_version,
            "created_at": self.created_at,
            "command": list(self.command),
            "providers": list(self.providers),
            "capabilities": list(self.capabilities),
            "runtime_manifests": dict(self.runtime_manifests),
            "input_digest": self.input_digest,
            "result_digest": self.result_digest,
            "budget_file": dict(self.budget_file) if self.budget_file is not None else None,
            "dataset_manifests": [dict(ref) for ref in self.dataset_manifests],
            "event_count": self.event_count,
            "claim_boundary": self.claim_boundary,
            "metric_semantics": self.metric_semantics,
            "notes": self.notes,
        }
        # Round-trip through ``dump_json`` to reject any sneaky non-finite metrics or non-JSON
        # values that slipped through individual validators (defense in depth).
        dump_json(payload)
        return payload

    def with_overrides(self, **overrides: Any) -> ProvenanceEnvelope:
        """Return a new envelope with selected fields replaced.

        Useful in CLI flows where the harness builds a base envelope and the command later
        attaches ``command`` text or a ``budget_file`` summary discovered at run time.
        """

        from dataclasses import replace

        return replace(self, **overrides)

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> ProvenanceEnvelope:
        """Reconstruct an envelope from its serialized form.

        Used by harness flows that re-render preserved JSON reports without losing the
        envelope. Validates the schema version eagerly: stored payloads must match the
        current schema or be migrated by the caller.
        """

        if not isinstance(payload, Mapping):
            raise WorldForgeError("ProvenanceEnvelope payload must be a JSON object.")
        schema_version = payload.get("schema_version")
        if schema_version != PROVENANCE_SCHEMA_VERSION:
            raise WorldForgeError(
                "ProvenanceEnvelope schema_version must be "
                f"{PROVENANCE_SCHEMA_VERSION}, got {schema_version!r}."
            )
        return cls(
            kind=str(payload.get("kind", "")),
            suite_id=str(payload.get("suite_id", "")),
            suite_version=str(payload.get("suite_version", "")),
            command=tuple(payload.get("command", ()) or ()),
            providers=tuple(payload.get("providers", ()) or ()),
            capabilities=tuple(payload.get("capabilities", ()) or ()),
            runtime_manifests=dict(payload.get("runtime_manifests", {}) or {}),
            input_digest=payload.get("input_digest"),
            result_digest=payload.get("result_digest"),
            budget_file=payload.get("budget_file"),
            dataset_manifests=tuple(payload.get("dataset_manifests", ()) or ()),
            event_count=int(payload.get("event_count", 0) or 0),
            claim_boundary=str(payload.get("claim_boundary", "")),
            metric_semantics=str(payload.get("metric_semantics", "")),
            worldforge_version=str(payload.get("worldforge_version", worldforge.__version__)),
            created_at=str(payload.get("created_at", "")),
            notes=payload.get("notes"),
        )


def _set_envelope_attr(envelope: ProvenanceEnvelope, field_name: str, value: object) -> None:
    object.__setattr__(envelope, field_name, value)


def _validate_provenance_kind(kind: object) -> None:
    if kind in _SUPPORTED_KINDS:
        return
    raise WorldForgeError(f"ProvenanceEnvelope kind must be one of: {', '.join(_SUPPORTED_KINDS)}.")


def _validate_provenance_schema_version(schema_version: object) -> None:
    if schema_version == PROVENANCE_SCHEMA_VERSION:
        return
    raise WorldForgeError(
        "ProvenanceEnvelope schema_version must be "
        f"{PROVENANCE_SCHEMA_VERSION}, got {schema_version}."
    )


def _normalize_provenance_text_fields(envelope: ProvenanceEnvelope) -> None:
    _set_envelope_attr(
        envelope,
        "suite_id",
        _required_text(envelope.suite_id, name="ProvenanceEnvelope suite_id"),
    )
    _set_envelope_attr(
        envelope,
        "suite_version",
        _required_text(envelope.suite_version, name="ProvenanceEnvelope suite_version"),
    )
    _set_envelope_attr(
        envelope,
        "worldforge_version",
        _required_text(
            envelope.worldforge_version,
            name="ProvenanceEnvelope worldforge_version",
        ),
    )
    _set_envelope_attr(
        envelope,
        "created_at",
        _required_text(envelope.created_at, name="ProvenanceEnvelope created_at"),
    )


def _normalize_provenance_collection_fields(envelope: ProvenanceEnvelope) -> None:
    _set_envelope_attr(
        envelope,
        "command",
        _string_tuple(envelope.command, name="ProvenanceEnvelope command"),
    )
    _set_envelope_attr(
        envelope,
        "providers",
        _string_tuple(envelope.providers, name="ProvenanceEnvelope providers"),
    )
    _set_envelope_attr(
        envelope,
        "capabilities",
        _string_tuple(envelope.capabilities, name="ProvenanceEnvelope capabilities"),
    )
    _set_envelope_attr(
        envelope,
        "runtime_manifests",
        _runtime_manifest_map(
            envelope.runtime_manifests,
            name="ProvenanceEnvelope runtime_manifests",
        ),
    )


def _normalize_provenance_reference_fields(envelope: ProvenanceEnvelope) -> None:
    _set_envelope_attr(
        envelope,
        "input_digest",
        _digest_or_none(envelope.input_digest, name="ProvenanceEnvelope input_digest"),
    )
    _set_envelope_attr(
        envelope,
        "result_digest",
        _digest_or_none(envelope.result_digest, name="ProvenanceEnvelope result_digest"),
    )
    _set_envelope_attr(
        envelope,
        "budget_file",
        _budget_file_summary(envelope.budget_file, name="ProvenanceEnvelope budget_file"),
    )
    _set_envelope_attr(
        envelope,
        "dataset_manifests",
        _dataset_manifest_refs(
            envelope.dataset_manifests,
            name="ProvenanceEnvelope dataset_manifests",
        ),
    )


def _normalize_provenance_claim_fields(envelope: ProvenanceEnvelope) -> None:
    require_non_negative_int(envelope.event_count, name="ProvenanceEnvelope event_count")
    _set_envelope_attr(
        envelope,
        "claim_boundary",
        _required_text(envelope.claim_boundary, name="ProvenanceEnvelope claim_boundary"),
    )
    _set_envelope_attr(
        envelope,
        "metric_semantics",
        _required_text(envelope.metric_semantics, name="ProvenanceEnvelope metric_semantics"),
    )


def _validate_optional_provenance_notes(notes: object) -> None:
    if notes is None or (isinstance(notes, str) and notes.strip()):
        return
    raise WorldForgeError("ProvenanceEnvelope notes must be a non-empty string or None.")


def digest_payload(payload: object) -> str:
    """Return ``sha256:<hex>`` for a JSON-native payload using deterministic encoding."""

    encoded = dump_json(payload).encode("utf-8")
    return f"sha256:{hashlib.sha256(encoded).hexdigest()}"


def runtime_manifest_id_for(provider: str) -> str | None:
    """Return ``<provider>:schema-<version>`` if the provider has an in-repo manifest."""

    try:
        manifest = load_runtime_manifest(provider)
    except WorldForgeError:
        return None
    return f"{manifest.provider}:schema-{manifest.schema_version}"


def collect_runtime_manifests(providers: Sequence[str]) -> dict[str, str]:
    """Return runtime-manifest ids for providers that ship one; skip silently otherwise."""

    out: dict[str, str] = {}
    for provider in providers:
        manifest_id = runtime_manifest_id_for(provider)
        if manifest_id is not None:
            out[provider] = manifest_id
    return out


__all__ = [
    "BENCHMARK_SUITE_CONTRACT_VERSION",
    "EVALUATION_SUITE_CONTRACT_VERSION",
    "PROVENANCE_SCHEMA_VERSION",
    "ProvenanceEnvelope",
    "collect_runtime_manifests",
    "digest_payload",
    "runtime_manifest_id_for",
]

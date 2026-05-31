"""File copying, reference resolution, and safety checks for evidence bundles."""

from __future__ import annotations

import hashlib
import json
import re
import shutil
from dataclasses import dataclass
from importlib import resources
from pathlib import Path

from worldforge.harness.workspace import runs_dir, validate_run_id
from worldforge.models import JSONDict, WorldForgeError, dump_json, require_json_dict
from worldforge.testing.capability_fixtures import CAPABILITY_FIXTURE_NAMES

MAX_SAFE_ARTIFACT_BYTES = 1_000_000

_ROOT = Path(__file__).resolve().parents[2]
_SAFE_SUFFIXES = {".json", ".jsonl", ".md", ".csv", ".txt", ".html"}
_SECRET_PATTERN = re.compile(
    r"(api[_-]?key|authorization|bearer\s+[a-z0-9._~-]+|password|secret|signature|token=|"
    r"x-amz-signature|nvidia_api_key)",
    re.IGNORECASE,
)
_HOST_PATH_PATTERN = re.compile(r"(/Users/|/private/|/var/folders/|file://|[A-Za-z]:\\)")
_BENCHMARK_PRESET_RESOURCE_PACKAGE = "worldforge.benchmark_presets._data"
_BENCHMARK_PRESET_RESOURCE_DESTINATION = Path("src/worldforge/benchmark_presets/_data")
_REPORT_REFERENCE_FIELDS: tuple[tuple[str, Path], ...] = (
    ("input_file", Path("inputs")),
    ("budget_file", Path("budgets")),
)


@dataclass(slots=True)
class _BundleContext:
    output: Path
    files: list[JSONDict] | None = None

    def __post_init__(self) -> None:
        if self.files is None:
            self.files = []


@dataclass(slots=True, frozen=True)
class _ReportFileReference:
    key: str
    raw_path: object
    destination_root: Path
    missing_destination: Path


def _select_run_paths(workspace_dir: Path, run_ids: tuple[str, ...]) -> list[Path]:
    root = runs_dir(workspace_dir)
    if run_ids:
        return [root / _validated_run_id(run_id) for run_id in sorted(run_ids)]
    if not root.exists():
        return []
    return sorted(path.parent for path in root.glob("*/run_manifest.json"))


def _validated_run_id(run_id: str) -> str:
    try:
        return validate_run_id(run_id)
    except ValueError as exc:
        raise WorldForgeError(f"Evidence bundle run_id is invalid: {exc}") from exc


def _load_run_manifest(run_path: Path) -> JSONDict:
    manifest_path = run_path / "run_manifest.json"
    try:
        payload = require_json_dict(
            json.loads(manifest_path.read_text(encoding="utf-8")),
            name=f"Run manifest {manifest_path}",
        )
    except FileNotFoundError as exc:
        raise WorldForgeError(f"Run manifest not found: {manifest_path}") from exc
    except json.JSONDecodeError as exc:
        raise WorldForgeError(f"Run manifest contains invalid JSON: {manifest_path}") from exc
    return payload


def _copy_run_workspace(
    context: _BundleContext,
    *,
    run_path: Path,
    run_id: str,
    copied_refs: set[Path],
) -> None:
    run_root = run_path.resolve()
    for source in sorted(path for path in run_path.rglob("*") if path.is_file()):
        resolved = source.resolve()
        relative = source.relative_to(run_path)
        destination = Path("runs") / run_id / relative
        if not _is_relative_to(resolved, run_root):
            _record_excluded(
                context,
                destination=destination,
                source=str(source),
                reason="run artifact resolves outside the run workspace",
                kind="run-artifact",
                local_only=True,
            )
            continue
        if resolved in copied_refs:
            continue
        copied_refs.add(resolved)
        _copy_safe_file(
            context,
            source=source,
            destination=destination,
            kind="run-artifact",
        )


def _copy_report_references(
    context: _BundleContext,
    *,
    run_path: Path,
    run_id: str,
    copied_refs: set[Path],
) -> None:
    for payload in _iter_report_payloads(run_path):
        _copy_benchmark_report_references(
            context,
            payload=payload,
            run_id=run_id,
            copied_refs=copied_refs,
        )
        _copy_dataset_manifest_references(context, payload=payload, copied_refs=copied_refs)


def _iter_report_payloads(run_path: Path) -> tuple[JSONDict, ...]:
    payloads: list[JSONDict] = []
    for report_path in sorted((run_path / "reports").glob("*.json")):
        payload = _load_report_payload(report_path)
        if payload is not None:
            payloads.append(payload)
    return tuple(payloads)


def _load_report_payload(report_path: Path) -> JSONDict | None:
    try:
        payload = require_json_dict(
            json.loads(report_path.read_text(encoding="utf-8")),
            name=f"Run report {report_path}",
        )
    except (OSError, json.JSONDecodeError, WorldForgeError):
        return None
    return payload


def _copy_benchmark_report_references(
    context: _BundleContext,
    *,
    payload: JSONDict,
    run_id: str,
    copied_refs: set[Path],
) -> None:
    for reference in _benchmark_report_references(payload=payload, run_id=run_id):
        _copy_benchmark_report_reference(context, reference=reference, copied_refs=copied_refs)


def _benchmark_report_references(
    *,
    payload: JSONDict,
    run_id: str,
) -> tuple[_ReportFileReference, ...]:
    run_metadata = payload.get("run_metadata", {})
    if not isinstance(run_metadata, dict):
        return ()
    references: list[_ReportFileReference] = []
    for key, destination_root in _REPORT_REFERENCE_FIELDS:
        summary = run_metadata.get(key)
        if isinstance(summary, dict):
            references.append(
                _ReportFileReference(
                    key=key,
                    raw_path=summary.get("path"),
                    destination_root=destination_root,
                    missing_destination=destination_root / run_id / f"{key}.json",
                )
            )
    return tuple(references)


def _copy_benchmark_report_reference(
    context: _BundleContext,
    *,
    reference: _ReportFileReference,
    copied_refs: set[Path],
) -> None:
    resource_name = _benchmark_preset_resource_name(reference.raw_path)
    if resource_name is not None:
        _copy_benchmark_preset_resource(context, reference=reference, name=resource_name)
        return
    resolved_reference = _resolve_report_reference(reference.raw_path)
    if resolved_reference is None:
        _record_missing_report_reference(context, reference)
        return
    _copy_resolved_report_reference(
        context,
        source=resolved_reference,
        destination=reference.destination_root / _repo_relative(resolved_reference),
        kind=reference.key,
        copied_refs=copied_refs,
    )


def _copy_benchmark_preset_resource(
    context: _BundleContext,
    *,
    reference: _ReportFileReference,
    name: str,
) -> None:
    _copy_package_resource(
        context,
        package=_BENCHMARK_PRESET_RESOURCE_PACKAGE,
        name=name,
        destination=reference.destination_root / _BENCHMARK_PRESET_RESOURCE_DESTINATION / name,
        kind=reference.key,
    )


def _record_missing_report_reference(
    context: _BundleContext,
    reference: _ReportFileReference,
) -> None:
    _record_excluded(
        context,
        destination=reference.missing_destination,
        source=str(reference.raw_path or ""),
        reason="referenced path is missing, absolute, or outside the repository",
        kind=reference.key,
        local_only=True,
    )


def _copy_dataset_manifest_references(
    context: _BundleContext,
    *,
    payload: JSONDict,
    copied_refs: set[Path],
) -> None:
    for raw_path in _dataset_manifest_reference_paths(payload):
        referenced = _resolve_report_reference(raw_path)
        if referenced is None:
            continue
        _copy_resolved_report_reference(
            context,
            source=referenced,
            destination=Path("dataset-manifests") / _repo_relative(referenced),
            kind="dataset-manifest",
            copied_refs=copied_refs,
        )


def _dataset_manifest_reference_paths(payload: JSONDict) -> tuple[object, ...]:
    provenance = payload.get("provenance", {})
    if not isinstance(provenance, dict):
        return ()
    dataset_manifests = provenance.get("dataset_manifests", [])
    if not isinstance(dataset_manifests, list):
        return ()
    return tuple(
        reference.get("path") for reference in dataset_manifests if isinstance(reference, dict)
    )


def _copy_resolved_report_reference(
    context: _BundleContext,
    *,
    source: Path,
    destination: Path,
    kind: str,
    copied_refs: set[Path],
) -> None:
    resolved = source.resolve()
    if resolved in copied_refs:
        return
    copied_refs.add(resolved)
    _copy_safe_file(context, source=source, destination=destination, kind=kind)


def _record_manifest_artifact_references(
    context: _BundleContext,
    *,
    run_path: Path,
    run_id: str,
    manifest: JSONDict,
) -> None:
    artifact_paths = manifest.get("artifact_paths", {})
    if not isinstance(artifact_paths, dict):
        return
    for label, raw_path in sorted(artifact_paths.items()):
        if not isinstance(raw_path, str) or not raw_path.strip():
            _record_excluded(
                context,
                destination=Path("runs") / run_id / f"artifacts/{label}",
                source=str(raw_path),
                reason="artifact reference is not a non-empty relative path",
                kind="artifact-reference",
                local_only=True,
            )
            continue
        candidate = Path(raw_path)
        if candidate.is_absolute():
            _record_excluded(
                context,
                destination=Path("runs") / run_id / f"artifacts/{label}",
                source=raw_path,
                reason="absolute artifact path is local-only",
                kind="artifact-reference",
                local_only=True,
            )
            continue
        resolved = (run_path / candidate).resolve()
        if not _is_relative_to(resolved, run_path.resolve()):
            _record_excluded(
                context,
                destination=Path("runs") / run_id / f"artifacts/{label}",
                source=raw_path,
                reason="artifact path escapes the run workspace",
                kind="artifact-reference",
                local_only=True,
            )
            continue
        if not resolved.is_file():
            _record_excluded(
                context,
                destination=Path("runs") / run_id / f"artifacts/{label}",
                source=raw_path,
                reason="artifact reference does not exist",
                kind="artifact-reference",
                local_only=True,
            )


def _resolve_report_reference(value: object) -> Path | None:
    if not isinstance(value, str) or not value.strip():
        return None
    raw = Path(value)
    if raw.is_absolute():
        return _resolve_absolute_report_reference(raw)
    return _first_existing_report_reference(_report_reference_candidates(value, raw))


def _resolve_absolute_report_reference(path: Path) -> Path | None:
    resolved = path.resolve()
    for root in _known_roots():
        if _is_relative_to(resolved, root):
            return resolved
    return None


def _report_reference_candidates(value: str, raw: Path) -> list[Path]:
    candidates = _base_report_reference_candidates(raw)
    if value.startswith("benchmark_presets/_data/"):
        candidates = _benchmark_preset_reference_candidates(value) + candidates
    return candidates


def _base_report_reference_candidates(raw: Path) -> list[Path]:
    return [
        _ROOT / raw,
        _ROOT / "src" / "worldforge" / raw,
        _ROOT / "src" / "worldforge" / raw.parent / raw.name,
        Path.cwd() / raw,
        Path.cwd() / "src" / "worldforge" / raw,
        Path.cwd() / "src" / "worldforge" / raw.parent / raw.name,
    ]


def _benchmark_preset_reference_candidates(value: str) -> list[Path]:
    return [
        _ROOT / "src" / "worldforge" / value,
        Path.cwd() / "src" / "worldforge" / value,
    ]


def _first_existing_report_reference(candidates: list[Path]) -> Path | None:
    for candidate in candidates:
        if candidate.exists() and candidate.is_file():
            return candidate
    return None


def _benchmark_preset_resource_name(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    prefix = "benchmark_presets/_data/"
    if not value.startswith(prefix):
        return None
    name = value.removeprefix(prefix)
    if "/" in name or not name.endswith(".json"):
        return None
    return name


def _copy_safe_file(
    context: _BundleContext,
    *,
    source: Path,
    destination: Path,
    kind: str,
) -> None:
    digest = _sha256_file(source)
    size = source.stat().st_size
    reason = _unsafe_reason(source, size)
    if reason is not None:
        _record_file(
            context,
            destination=destination,
            source=source,
            kind=kind,
            included=False,
            safe_to_attach=False,
            local_only="host-local path" in reason,
            reason=reason,
            sha256=digest,
            size=size,
        )
        return
    target = context.output / destination
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, target)
    _record_file(
        context,
        destination=destination,
        source=source,
        kind=kind,
        included=True,
        safe_to_attach=True,
        local_only=False,
        reason=None,
        sha256=digest,
        size=size,
    )


def _copy_package_resource(
    context: _BundleContext,
    *,
    package: str,
    name: str,
    destination: Path,
    kind: str,
) -> None:
    resource = resources.files(package).joinpath(name)
    if not resource.is_file():
        _record_excluded(
            context,
            destination=destination,
            source=f"{package}/{name}",
            reason="package resource not found",
            kind=kind,
            local_only=False,
        )
        return
    data = resource.read_bytes()
    digest = f"sha256:{hashlib.sha256(data).hexdigest()}"
    size = len(data)
    reason = _unsafe_bytes_reason(suffix=Path(name).suffix, size=size, data=data)
    if reason is not None:
        _record_file(
            context,
            destination=destination,
            source=Path(f"{package}/{name}"),
            kind=kind,
            included=False,
            safe_to_attach=False,
            local_only="host-local path" in reason,
            reason=reason,
            sha256=digest,
            size=size,
        )
        return
    target = context.output / destination
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)
    _record_file(
        context,
        destination=destination,
        source=Path(f"{package}/{name}"),
        kind=kind,
        included=True,
        safe_to_attach=True,
        local_only=False,
        reason=None,
        sha256=digest,
        size=size,
    )


def _unsafe_reason(path: Path, size: int) -> str | None:
    return _unsafe_bytes_reason(
        suffix=path.suffix,
        size=size,
        data=path.read_bytes(),
    )


def _unsafe_bytes_reason(*, suffix: str, size: int, data: bytes) -> str | None:
    if suffix.lower() not in _SAFE_SUFFIXES:
        return f"unsupported artifact suffix '{suffix or '<none>'}'"
    if size > MAX_SAFE_ARTIFACT_BYTES:
        return f"file exceeds {MAX_SAFE_ARTIFACT_BYTES} byte safe attachment limit"
    text = data.decode("utf-8", errors="replace")
    if _SECRET_PATTERN.search(text):
        return "secret-like material detected"
    if _HOST_PATH_PATTERN.search(text):
        return "host-local path detected"
    parsed = _json_or_none(text)
    if parsed is not None:
        json_reason = _json_safety_reason(suffix=suffix, value=parsed)
        if json_reason is not None:
            return json_reason
        if _contains_unsafe_url(parsed):
            return "signed or credentialed URL detected"
    return None


def _json_safety_reason(*, suffix: str, value: object) -> str | None:
    if suffix.lower() != ".json":
        return None
    try:
        dump_json(value)
    except WorldForgeError:
        return "JSON artifact must contain only finite JSON values"
    return None


def _contains_unsafe_url(value: object) -> bool:
    if isinstance(value, dict):
        return any(_contains_unsafe_url(item) for item in value.values())
    if isinstance(value, list):
        return any(_contains_unsafe_url(item) for item in value)
    if not isinstance(value, str):
        return False
    return bool(
        re.search(
            r"https?://[^\s\"']+[?&](token|signature|sig|key|api_key)=",
            value,
            re.I,
        )
    )


def _json_or_none(text: str) -> object | None:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None


def _record_excluded(
    context: _BundleContext,
    *,
    destination: Path,
    source: str,
    reason: str,
    kind: str,
    local_only: bool,
) -> None:
    context.files.append(
        {
            "path": destination.as_posix(),
            "source": _safe_source_display(source),
            "kind": kind,
            "included": False,
            "safe_to_attach": False,
            "local_only": local_only,
            "reason": reason,
            "sha256": None,
            "size_bytes": None,
        }
    )


def _record_file(
    context: _BundleContext,
    *,
    destination: Path,
    source: Path,
    kind: str,
    included: bool,
    safe_to_attach: bool,
    local_only: bool,
    reason: str | None,
    sha256: str,
    size: int,
) -> None:
    context.files.append(
        {
            "path": destination.as_posix(),
            "source": _display_path(source),
            "kind": kind,
            "included": included,
            "safe_to_attach": safe_to_attach,
            "local_only": local_only,
            "reason": reason,
            "sha256": sha256,
            "size_bytes": size,
        }
    )


def _fixture_digests() -> list[JSONDict]:
    fixtures: list[JSONDict] = []
    fixtures.extend(
        _resource_digest(
            package=f"worldforge.testing.fixtures.{capability}",
            name=entry.name,
            display_path=f"src/worldforge/testing/fixtures/{capability}/{entry.name}",
        )
        for capability in CAPABILITY_FIXTURE_NAMES
        for entry in sorted(
            resources.files(f"worldforge.testing.fixtures.{capability}").iterdir(),
            key=lambda item: item.name,
        )
        if entry.name.endswith(".json") and entry.is_file()
    )
    fixtures.extend(
        _resource_digest(
            package="worldforge.benchmark_presets._data",
            name=entry.name,
            display_path=f"src/worldforge/benchmark_presets/_data/{entry.name}",
        )
        for entry in sorted(
            resources.files("worldforge.benchmark_presets._data").iterdir(),
            key=lambda item: item.name,
        )
        if entry.name.endswith(".json") and entry.is_file()
    )
    return sorted(fixtures, key=lambda item: str(item["path"]))


def _resource_digest(*, package: str, name: str, display_path: str) -> JSONDict:
    data = resources.files(package).joinpath(name).read_bytes()
    return {
        "path": display_path,
        "sha256": f"sha256:{hashlib.sha256(data).hexdigest()}",
        "size_bytes": len(data),
    }


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return f"sha256:{digest.hexdigest()}"


def _repo_relative(path: Path) -> Path:
    resolved = path.resolve()
    for root in _known_roots():
        try:
            return resolved.relative_to(root)
        except ValueError:
            continue
    return Path(path.name)


def _display_path(path: Path) -> str:
    resolved = path.resolve()
    for root in _known_roots():
        try:
            return resolved.relative_to(root).as_posix()
        except ValueError:
            continue
    return f"<host-local:{path.name}>"


def _safe_source_display(source: str) -> str:
    if Path(source).is_absolute() or _HOST_PATH_PATTERN.search(source):
        return f"<host-local:{Path(source).name or 'path'}>"
    return source


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def _known_roots() -> tuple[Path, ...]:
    package_root = _ROOT.resolve()
    cwd = Path.cwd().resolve()
    if cwd == package_root:
        return (package_root,)
    return (package_root, cwd)

"""Fixture snapshot manifests for source-controlled WorldForge test artifacts."""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from worldforge.models import JSONDict, WorldForgeError

FIXTURE_SNAPSHOT_MANIFEST_SCHEMA_VERSION = 1
"""Schema version for fixture snapshot manifest files."""

FIXTURE_SNAPSHOT_REVIEW_STATUSES = ("tracked", "intended-update")
"""Review states accepted in fixture snapshot manifest entries."""

FIXTURE_SNAPSHOT_RESULT_STATUSES = (
    "current",
    "missing",
    "changed",
    "unsafe",
    "intended-update",
)
"""Validation statuses emitted by fixture snapshot reports."""

_CAPABILITY_FIXTURE_PREFIX = "src/worldforge/testing/fixtures/"
_PROVIDER_FIXTURE_PREFIX = "tests/fixtures/providers/"
_SCENARIO_FIXTURE_PREFIX = "examples/scenarios/"
_SCENE_ARTIFACT_FIXTURE_PREFIX = "tests/fixtures/scene_artifacts/"
_BENCHMARK_FIXTURE_PREFIX = "examples/"


@dataclass(frozen=True, slots=True)
class FixtureSnapshotEntry:
    """One source-controlled fixture tracked by a snapshot manifest."""

    path: str
    sha256: str
    size_bytes: int
    fixture_kind: str
    fixture_schema_version: int | str | None = None
    review_status: str = "tracked"

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any], *, source: str) -> FixtureSnapshotEntry:
        """Parse one manifest entry without touching the filesystem."""

        if not isinstance(payload, Mapping):
            raise WorldForgeError(f"{source} fixture snapshot entry must be a JSON object.")
        path = payload.get("path")
        if not isinstance(path, str) or not path.strip():
            raise WorldForgeError(f"{source} fixture snapshot entry 'path' must be non-empty.")
        sha256 = payload.get("sha256")
        if not isinstance(sha256, str) or not sha256.strip():
            raise WorldForgeError(f"{source} fixture snapshot entry 'sha256' must be non-empty.")
        size_bytes = payload.get("size_bytes")
        if not _is_int(size_bytes) or size_bytes < 0:
            raise WorldForgeError(
                f"{source} fixture snapshot entry 'size_bytes' must be a non-negative integer."
            )
        fixture_kind = payload.get("fixture_kind")
        if not isinstance(fixture_kind, str) or not fixture_kind.strip():
            raise WorldForgeError(
                f"{source} fixture snapshot entry 'fixture_kind' must be non-empty."
            )
        fixture_schema_version = payload.get("fixture_schema_version")
        if fixture_schema_version is not None and (
            isinstance(fixture_schema_version, bool)
            or not isinstance(fixture_schema_version, int | str)
        ):
            raise WorldForgeError(
                f"{source} fixture snapshot entry 'fixture_schema_version' must be a string, "
                "integer, or null."
            )
        review_status = payload.get("review_status", "tracked")
        if review_status not in FIXTURE_SNAPSHOT_REVIEW_STATUSES:
            known = ", ".join(FIXTURE_SNAPSHOT_REVIEW_STATUSES)
            raise WorldForgeError(
                f"{source} fixture snapshot entry 'review_status' must be one of {known}."
            )
        return cls(
            path=path,
            sha256=sha256,
            size_bytes=size_bytes,
            fixture_kind=fixture_kind,
            fixture_schema_version=fixture_schema_version,
            review_status=review_status,
        )

    def to_dict(self) -> JSONDict:
        """Return the manifest JSON shape for this entry."""

        return {
            "path": self.path,
            "sha256": self.sha256,
            "size_bytes": self.size_bytes,
            "fixture_kind": self.fixture_kind,
            "fixture_schema_version": self.fixture_schema_version,
            "review_status": self.review_status,
        }


@dataclass(frozen=True, slots=True)
class FixtureSnapshotManifest:
    """A fixture snapshot manifest loaded from JSON."""

    entries: tuple[FixtureSnapshotEntry, ...]
    schema_version: int = FIXTURE_SNAPSHOT_MANIFEST_SCHEMA_VERSION

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any], *, source: str) -> FixtureSnapshotManifest:
        """Parse a fixture snapshot manifest from a JSON object."""

        if not isinstance(payload, Mapping):
            raise WorldForgeError(f"{source} fixture snapshot manifest must be a JSON object.")
        schema_version = payload.get("schema_version")
        if (
            not _is_int(schema_version)
            or schema_version != FIXTURE_SNAPSHOT_MANIFEST_SCHEMA_VERSION
        ):
            raise WorldForgeError(
                f"{source} fixture snapshot manifest schema_version must be "
                f"{FIXTURE_SNAPSHOT_MANIFEST_SCHEMA_VERSION}, got {schema_version!r}."
            )
        raw_entries = payload.get("entries")
        if not isinstance(raw_entries, list):
            raise WorldForgeError(f"{source} fixture snapshot manifest 'entries' must be a list.")
        entries = tuple(
            FixtureSnapshotEntry.from_dict(entry, source=f"{source} entries[{index}]")
            for index, entry in enumerate(raw_entries)
        )
        return cls(entries=entries, schema_version=schema_version)

    def to_dict(self) -> JSONDict:
        """Return the manifest JSON shape."""

        return {
            "schema_version": self.schema_version,
            "entries": [entry.to_dict() for entry in self.entries],
        }


@dataclass(frozen=True, slots=True)
class FixtureSnapshotIssue:
    """One fixture snapshot validation issue."""

    path: str
    status: str
    message: str
    expected_sha256: str | None = None
    actual_sha256: str | None = None
    fixture_kind: str | None = None
    review_status: str | None = None

    def to_dict(self) -> JSONDict:
        """Return a JSON-native issue payload."""

        return {
            "path": self.path,
            "status": self.status,
            "message": self.message,
            "expected_sha256": self.expected_sha256,
            "actual_sha256": self.actual_sha256,
            "fixture_kind": self.fixture_kind,
            "review_status": self.review_status,
        }


@dataclass(frozen=True, slots=True)
class FixtureSnapshotReport:
    """Validation report for a fixture snapshot manifest."""

    passed: bool
    manifest_schema_version: int
    entries: tuple[FixtureSnapshotEntry, ...]
    issues: tuple[FixtureSnapshotIssue, ...]
    summary: JSONDict

    def to_dict(self) -> JSONDict:
        """Return a JSON-native report payload."""

        return {
            "passed": self.passed,
            "manifest_schema_version": self.manifest_schema_version,
            "summary": dict(self.summary),
            "entries": [entry.to_dict() for entry in self.entries],
            "issues": [issue.to_dict() for issue in self.issues],
        }

    def to_markdown(self) -> str:
        """Render a review-oriented Markdown report."""

        status = "passed" if self.passed else "failed"
        lines = [
            "# Fixture Snapshot Review",
            "",
            f"- Status: `{status}`",
            f"- Manifest schema version: `{self.manifest_schema_version}`",
            f"- Entries: {len(self.entries)}",
            "",
            "## Summary",
            "",
        ]
        lines.extend(
            f"- `{result_status}`: {self.summary.get(result_status, 0)}"
            for result_status in FIXTURE_SNAPSHOT_RESULT_STATUSES
        )
        lines.extend(["", "## Issues", ""])
        if not self.issues:
            lines.append("- No fixture drift detected.")
            return "\n".join(lines)
        lines.extend(
            [
                "| status | fixture | kind | review status | expected | actual | note |",
                "| --- | --- | --- | --- | --- | --- | --- |",
            ]
        )
        lines.extend(
            (
                "| "
                f"`{issue.status}` | "
                f"`{issue.path}` | "
                f"{issue.fixture_kind or '-'} | "
                f"{issue.review_status or '-'} | "
                f"`{_short_digest(issue.expected_sha256)}` | "
                f"`{_short_digest(issue.actual_sha256)}` | "
                f"{issue.message} |"
            )
            for issue in self.issues
        )
        return "\n".join(lines)


def load_fixture_snapshot_manifest(path: Path) -> FixtureSnapshotManifest:
    """Load a fixture snapshot manifest from ``path``."""

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise WorldForgeError(f"Fixture snapshot manifest not found: {path}.") from exc
    except json.JSONDecodeError as exc:
        raise WorldForgeError(f"Fixture snapshot manifest contains invalid JSON: {path}.") from exc
    return FixtureSnapshotManifest.from_dict(payload, source=str(path))


def default_fixture_snapshot_paths(root: Path = Path(".")) -> tuple[Path, ...]:
    """Return the source-controlled fixtures covered by the default manifest."""

    root = Path(root)
    paths: list[Path] = []
    for pattern in (
        "src/worldforge/testing/fixtures/**/*.json",
        "tests/fixtures/providers/*.json",
        "examples/*benchmark*.json",
        "examples/scenarios/*.json",
        "tests/fixtures/scene_artifacts/*.json",
    ):
        paths.extend(sorted(root.glob(pattern)))
    return tuple(path for path in paths if path.is_file())


def build_fixture_snapshot_manifest(
    paths: Iterable[Path | str],
    *,
    root: Path = Path("."),
) -> FixtureSnapshotManifest:
    """Build a fixture snapshot manifest for explicit source-controlled fixture paths."""

    root = _root(root)
    entries: list[FixtureSnapshotEntry] = []
    seen: set[str] = set()
    for path in paths:
        relative_path = _relative_fixture_path(path, root=root)
        if relative_path in seen:
            raise WorldForgeError(f"Duplicate fixture snapshot path: {relative_path}.")
        seen.add(relative_path)
        candidate = root / relative_path
        kind = _fixture_kind(relative_path)
        if kind is None:
            raise WorldForgeError(f"Unsupported fixture snapshot path: {relative_path}.")
        if not candidate.is_file():
            raise WorldForgeError(f"Fixture snapshot path is not a file: {relative_path}.")
        data = candidate.read_bytes()
        entries.append(
            FixtureSnapshotEntry(
                path=relative_path,
                sha256=_sha256_bytes(data),
                size_bytes=len(data),
                fixture_kind=kind,
                fixture_schema_version=_json_schema_version(candidate),
                review_status="tracked",
            )
        )
    return FixtureSnapshotManifest(entries=tuple(sorted(entries, key=lambda entry: entry.path)))


def validate_fixture_snapshot_manifest(
    manifest: FixtureSnapshotManifest | Path,
    *,
    root: Path = Path("."),
    allow_intended_updates: bool = False,
) -> FixtureSnapshotReport:
    """Validate fixture snapshot entries against files under ``root``."""

    loaded = load_fixture_snapshot_manifest(manifest) if isinstance(manifest, Path) else manifest
    root = _root(root)
    issues: list[FixtureSnapshotIssue] = []
    summary: Counter[str] = Counter()
    seen: set[str] = set()

    for entry in loaded.entries:
        issue = _validate_entry(entry, root=root, seen=seen)
        if issue is None:
            summary["current"] += 1
            continue
        issues.append(issue)
        summary[issue.status] += 1

    passed = not issues or (
        allow_intended_updates and all(issue.status == "intended-update" for issue in issues)
    )
    return FixtureSnapshotReport(
        passed=passed,
        manifest_schema_version=loaded.schema_version,
        entries=loaded.entries,
        issues=tuple(issues),
        summary={status: summary.get(status, 0) for status in FIXTURE_SNAPSHOT_RESULT_STATUSES},
    )


def render_fixture_snapshot_review(report: FixtureSnapshotReport) -> str:
    """Render a fixture snapshot report as Markdown."""

    return report.to_markdown()


def _validate_entry(
    entry: FixtureSnapshotEntry,
    *,
    root: Path,
    seen: set[str],
) -> FixtureSnapshotIssue | None:
    unsafe = _unsafe_path_reason(entry.path)
    kind = _fixture_kind(entry.path)
    if unsafe is not None:
        return _issue(entry, "unsafe", unsafe, fixture_kind=kind)
    if kind is None:
        return _issue(
            entry,
            "unsafe",
            "fixture path is outside the managed fixture roots",
            fixture_kind=entry.fixture_kind,
        )
    if kind != entry.fixture_kind:
        return _issue(
            entry,
            "unsafe",
            f"fixture_kind must be {kind!r} for this path, got {entry.fixture_kind!r}",
            fixture_kind=kind,
        )
    if not _is_sha256(entry.sha256):
        return _issue(entry, "unsafe", "sha256 must be formatted as sha256:<64 hex chars>")
    if entry.path in seen:
        return _issue(entry, "unsafe", "duplicate fixture path in manifest", fixture_kind=kind)
    seen.add(entry.path)

    path = root / entry.path
    try:
        resolved = path.resolve()
    except OSError as exc:
        return _issue(entry, "unsafe", f"fixture path cannot be resolved: {exc}", fixture_kind=kind)
    if not resolved.is_relative_to(root):
        return _issue(entry, "unsafe", "fixture path resolves outside the repository root")
    if not path.exists():
        return _issue(entry, "missing", "fixture path is missing", fixture_kind=kind)
    if not path.is_file():
        return _issue(entry, "unsafe", "fixture path is not a regular file", fixture_kind=kind)

    data = path.read_bytes()
    actual_sha256 = _sha256_bytes(data)
    if actual_sha256 != entry.sha256 or len(data) != entry.size_bytes:
        status = "intended-update" if entry.review_status == "intended-update" else "changed"
        message = (
            "fixture changed and is marked for review"
            if status == "intended-update"
            else "fixture digest or size changed without an intended-update marker"
        )
        return _issue(
            entry,
            status,
            message,
            actual_sha256=actual_sha256,
            fixture_kind=kind,
        )
    actual_schema_version = _json_schema_version(path)
    if actual_schema_version != entry.fixture_schema_version:
        status = "intended-update" if entry.review_status == "intended-update" else "changed"
        return _issue(
            entry,
            status,
            "fixture schema version metadata changed",
            actual_sha256=actual_sha256,
            fixture_kind=kind,
        )
    return None


def _issue(
    entry: FixtureSnapshotEntry,
    status: str,
    message: str,
    *,
    actual_sha256: str | None = None,
    fixture_kind: str | None = None,
) -> FixtureSnapshotIssue:
    return FixtureSnapshotIssue(
        path=entry.path,
        status=status,
        message=message,
        expected_sha256=entry.sha256,
        actual_sha256=actual_sha256,
        fixture_kind=fixture_kind or entry.fixture_kind,
        review_status=entry.review_status,
    )


def _root(path: Path) -> Path:
    return Path(path).resolve()


def _relative_fixture_path(path: Path | str, *, root: Path) -> str:
    candidate = Path(path)
    if candidate.is_absolute():
        try:
            candidate = candidate.resolve().relative_to(root)
        except ValueError as exc:
            raise WorldForgeError(f"Fixture snapshot path is outside the root: {path}.") from exc
    normalized = candidate.as_posix()
    unsafe = _unsafe_path_reason(normalized)
    if unsafe is not None:
        raise WorldForgeError(f"Unsafe fixture snapshot path {normalized!r}: {unsafe}.")
    return normalized


def _unsafe_path_reason(path: str) -> str | None:
    if "\\" in path:
        return "use forward-slash repository-relative paths, not backslashes"
    if "\x00" in path:
        return "path contains a null byte"
    if not path or path.startswith("/"):
        return "path must be repository-relative"
    parts = path.split("/")
    if any(part in {"", ".", ".."} for part in parts):
        return "path must not contain empty, current-directory, or parent-directory segments"
    if not path.endswith(".json"):
        return "fixture snapshot entries must reference JSON files"
    return None


def _fixture_kind(path: str) -> str | None:
    if path.startswith(_CAPABILITY_FIXTURE_PREFIX):
        return "capability-fixture"
    if path.startswith(_PROVIDER_FIXTURE_PREFIX):
        return "provider-payload-fixture"
    if (
        path.startswith(_BENCHMARK_FIXTURE_PREFIX)
        and "/" not in path.removeprefix(_BENCHMARK_FIXTURE_PREFIX)
        and "benchmark" in Path(path).name
    ):
        return "benchmark-fixture"
    if path.startswith(_SCENARIO_FIXTURE_PREFIX):
        return "scenario-fixture"
    if path.startswith(_SCENE_ARTIFACT_FIXTURE_PREFIX):
        return "scene-artifact-fixture"
    return None


def _sha256_bytes(data: bytes) -> str:
    return f"sha256:{hashlib.sha256(data).hexdigest()}"


def _is_sha256(value: str) -> bool:
    if not value.startswith("sha256:"):
        return False
    digest = value.removeprefix("sha256:")
    return len(digest) == 64 and all(char in "0123456789abcdef" for char in digest)


def _json_schema_version(path: Path) -> int | str | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, Mapping):
        return None
    schema_version = payload.get("schema_version")
    if isinstance(schema_version, bool):
        return None
    if isinstance(schema_version, int | str):
        return schema_version
    return None


def _is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _short_digest(value: str | None) -> str:
    if value is None:
        return "-"
    if value.startswith("sha256:") and len(value) > 20:
        return f"{value[:19]}..."
    return value


__all__ = [
    "FIXTURE_SNAPSHOT_MANIFEST_SCHEMA_VERSION",
    "FIXTURE_SNAPSHOT_RESULT_STATUSES",
    "FIXTURE_SNAPSHOT_REVIEW_STATUSES",
    "FixtureSnapshotEntry",
    "FixtureSnapshotIssue",
    "FixtureSnapshotManifest",
    "FixtureSnapshotReport",
    "build_fixture_snapshot_manifest",
    "default_fixture_snapshot_paths",
    "load_fixture_snapshot_manifest",
    "render_fixture_snapshot_review",
    "validate_fixture_snapshot_manifest",
]

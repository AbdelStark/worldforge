"""Retention policy + safe pruning for preserved WorldForge runs.

Walks ``<workspace>/runs/`` read-only by default and proposes which run
workspaces fall outside the configured retention policy. ``apply=True``
removes the selected directories; without it the result is a dry-run
report listing what *would* be deleted.

Safety rules:

- Refuses to operate on anything outside ``<workspace>/runs/`` — the
  ``workspace_dir`` is normalized and any path that escapes via ``..``
  or filesystem links is rejected before walking.
- Never deletes a run workspace younger than 24 hours unless the caller
  passes ``max_age_days=0`` to make the override explicit.
- Always keeps the newest ``keep_latest`` valid runs irrespective of
  age; corrupted run directories (missing ``run_manifest.json``) are
  candidates only when also outside the keep-latest window.
- Family filters (``families``) restrict the policy to a manifest's
  ``kind`` field: ``eval``, ``benchmark``, ``flow``, ``scenario``,
  ``demo-showcase``, etc. Empty families means "every kind".
"""

from __future__ import annotations

import json
import shutil
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

from worldforge.models import JSONDict, WorldForgeError

RUNS_PRUNE_SCHEMA_VERSION = 1

_PRUNE_KEEP_SAFETY_WINDOW = timedelta(hours=24)


@dataclass(frozen=True, slots=True)
class RunsRetentionPolicy:
    """Typed retention policy for preserved run workspaces."""

    max_age_days: int = 30
    keep_latest: int = 10
    families: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.max_age_days, int) or self.max_age_days < 0:
            raise WorldForgeError("max_age_days must be a non-negative integer.")
        if not isinstance(self.keep_latest, int) or self.keep_latest < 0:
            raise WorldForgeError("keep_latest must be a non-negative integer.")
        if not isinstance(self.families, tuple | list):
            raise WorldForgeError("families must be a sequence of non-empty strings.")
        cleaned: list[str] = []
        for entry in self.families:
            if not isinstance(entry, str) or not entry.strip():
                raise WorldForgeError("families entries must be non-empty strings.")
            cleaned.append(entry.strip())
        object.__setattr__(self, "families", tuple(cleaned))

    def to_dict(self) -> JSONDict:
        return {
            "max_age_days": self.max_age_days,
            "keep_latest": self.keep_latest,
            "families": list(self.families),
        }


@dataclass(frozen=True, slots=True)
class PruneCandidate:
    """One run workspace under consideration for pruning."""

    run_id: str
    run_dir: str
    kind: str
    created_at: str
    size_bytes: int
    action: str  # "delete" | "keep" | "skip-young" | "skip-keep-latest" | "skip-family"
    reason: str

    def to_dict(self) -> JSONDict:
        return {
            "run_id": self.run_id,
            "run_dir": self.run_dir,
            "kind": self.kind,
            "created_at": self.created_at,
            "size_bytes": self.size_bytes,
            "action": self.action,
            "reason": self.reason,
        }


@dataclass(frozen=True, slots=True)
class PruneReport:
    """Outcome of :func:`plan_prune` or :func:`apply_prune`."""

    schema_version: int
    workspace_dir: str
    policy: RunsRetentionPolicy
    generated_at: str
    candidates: tuple[PruneCandidate, ...]
    applied: bool

    def selected_for_delete(self) -> tuple[PruneCandidate, ...]:
        return tuple(c for c in self.candidates if c.action == "delete")

    def kept(self) -> tuple[PruneCandidate, ...]:
        return tuple(c for c in self.candidates if c.action != "delete")

    def total_bytes(self) -> int:
        return sum(c.size_bytes for c in self.candidates if c.action == "delete")

    def to_dict(self) -> JSONDict:
        return {
            "schema_version": self.schema_version,
            "workspace_dir": self.workspace_dir,
            "policy": self.policy.to_dict(),
            "generated_at": self.generated_at,
            "applied": self.applied,
            "candidate_count": len(self.candidates),
            "delete_count": len(self.selected_for_delete()),
            "delete_bytes": self.total_bytes(),
            "candidates": [c.to_dict() for c in self.candidates],
        }

    def to_json(self, *, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, sort_keys=True) + "\n"

    def to_markdown(self) -> str:
        lines = [
            "# WorldForge Run Prune Report",
            "",
            f"- workspace: `{self.workspace_dir}`",
            f"- generated_at: {self.generated_at}",
            f"- mode: {'apply' if self.applied else 'dry-run'}",
            f"- max_age_days: {self.policy.max_age_days}",
            f"- keep_latest: {self.policy.keep_latest}",
            (
                f"- families: {', '.join(self.policy.families)}"
                if self.policy.families
                else "- families: (all)"
            ),
            f"- candidates: {len(self.candidates)}",
            f"- to delete: {len(self.selected_for_delete())} ({self.total_bytes()} bytes)",
            "",
            "## Candidates",
            "",
            "| Run | Kind | Created | Size | Action | Reason |",
            "| --- | --- | --- | ---: | --- | --- |",
        ]
        lines.extend(
            f"| `{c.run_id}` | {c.kind or '-'} | {c.created_at or '-'} | "
            f"{c.size_bytes} | {c.action} | {c.reason} |"
            for c in self.candidates
        )
        if not self.candidates:
            lines.append("| - | - | - | - | - | - |")
        return "\n".join(lines) + "\n"


def plan_prune(
    workspace_dir: Path | str,
    *,
    policy: RunsRetentionPolicy | None = None,
    now: datetime | None = None,
) -> PruneReport:
    """Compute a dry-run prune plan against ``<workspace>/runs/``.

    Returns a :class:`PruneReport` with ``applied=False``. Callers that
    want to actually delete the selected runs should pass the report to
    :func:`apply_prune`.
    """

    resolved_policy = policy or RunsRetentionPolicy()
    runs_root, workspace_display = _safe_runs_root(workspace_dir)
    reference_time = (now or datetime.now(UTC)).astimezone(UTC)
    candidates = _scan_candidates(runs_root, policy=resolved_policy, now=reference_time)
    return PruneReport(
        schema_version=RUNS_PRUNE_SCHEMA_VERSION,
        workspace_dir=workspace_display,
        policy=resolved_policy,
        generated_at=reference_time.isoformat().replace("+00:00", "Z"),
        candidates=tuple(candidates),
        applied=False,
    )


def apply_prune(report: PruneReport) -> PruneReport:
    """Apply a previously-computed :class:`PruneReport`.

    Deletes the run workspaces whose ``action`` is ``delete``. Returns a
    new report with ``applied=True``; the candidates list is unchanged
    so callers can render the same table after deletion. Raises
    :class:`WorldForgeError` if the report's workspace points outside a
    runs directory under the caller's control.
    """

    if not isinstance(report, PruneReport):
        raise WorldForgeError("apply_prune expects a PruneReport.")
    if report.applied:
        raise WorldForgeError("PruneReport already applied; build a fresh plan first.")
    workspace_root = Path(report.workspace_dir).expanduser().resolve()
    runs_root = (workspace_root / "runs").resolve()
    for candidate in report.selected_for_delete():
        target = Path(candidate.run_dir).expanduser().resolve()
        _ensure_inside_runs(target, runs_root=runs_root)
        if target.exists():
            try:
                shutil.rmtree(target)
            except OSError as exc:
                raise WorldForgeError(f"Failed to remove run workspace {target}: {exc}") from exc
    return PruneReport(
        schema_version=report.schema_version,
        workspace_dir=report.workspace_dir,
        policy=report.policy,
        generated_at=report.generated_at,
        candidates=report.candidates,
        applied=True,
    )


def parse_runs_retention(payload: object) -> RunsRetentionPolicy:
    """Parse a ``runs_retention`` block from a config profile or JSON dict."""

    if not isinstance(payload, Mapping):
        raise WorldForgeError("runs_retention must be a JSON object.")
    allowed = {"max_age_days", "keep_latest", "families"}
    unknown = sorted(set(payload) - allowed)
    if unknown:
        raise WorldForgeError(f"runs_retention has unsupported keys: {', '.join(unknown)}.")
    max_age_days = _coerce_retention_int(payload.get("max_age_days", 30), name="max_age_days")
    keep_latest = _coerce_retention_int(payload.get("keep_latest", 10), name="keep_latest")
    families_raw = payload.get("families", [])
    if not isinstance(families_raw, list | tuple):
        raise WorldForgeError("runs_retention.families must be an array.")
    for index, item in enumerate(families_raw):
        if not isinstance(item, str):
            raise WorldForgeError(
                f"runs_retention.families[{index}] must be a string; got {type(item).__name__}."
            )
    return RunsRetentionPolicy(
        max_age_days=max_age_days,
        keep_latest=keep_latest,
        families=tuple(families_raw),
    )


def _coerce_retention_int(value: object, *, name: str) -> int:
    """Coerce a retention profile integer field, raising ``WorldForgeError`` on bad shapes."""

    if isinstance(value, bool) or not isinstance(value, int):
        raise WorldForgeError(
            f"runs_retention.{name} must be an integer; got {type(value).__name__}."
        )
    return value


def _safe_runs_root(workspace_dir: Path | str) -> tuple[Path, str]:
    """Resolve and validate ``<workspace>/runs/``."""

    if isinstance(workspace_dir, str):
        if not workspace_dir.strip():
            raise WorldForgeError("workspace_dir must be a non-empty path.")
        workspace_dir = Path(workspace_dir)
    if not isinstance(workspace_dir, Path):
        raise WorldForgeError("workspace_dir must be a Path.")
    display = str(workspace_dir)
    runs_root = (workspace_dir / "runs").expanduser().resolve()
    return runs_root, display


def _ensure_inside_runs(target: Path, *, runs_root: Path) -> None:
    """Refuse to delete anything outside the resolved ``<workspace>/runs/`` root.

    Both paths must already be resolved so that any symlink in either
    side is followed before the relativity check, defeating crafted
    report paths that point at a different ``runs/`` directory on disk.
    """

    if not target.is_relative_to(runs_root):
        raise WorldForgeError(
            f"Refusing to prune outside runs directory; target {target} "
            f"is not inside resolved runs root {runs_root}."
        )


def _scan_candidates(
    runs_root: Path,
    *,
    policy: RunsRetentionPolicy,
    now: datetime,
) -> Iterable[PruneCandidate]:
    if not runs_root.is_dir():
        return ()
    entries: list[tuple[Path, JSONDict | None, datetime | None]] = []
    for run_dir in sorted(runs_root.iterdir(), key=lambda p: p.name, reverse=True):
        if not run_dir.is_dir():
            continue
        manifest = _load_manifest(run_dir)
        created_at = _parse_created_at(manifest, run_dir)
        entries.append((run_dir, manifest, created_at))

    family_filter = {family.lower() for family in policy.families}
    candidates: list[PruneCandidate] = []
    # Compute keep_latest *inside* the filtered family set so a non-matching
    # newer run cannot consume a keep slot when --family is used.
    in_family_indices = [
        index
        for index, (_, manifest, _) in enumerate(entries)
        if not family_filter
        or (isinstance(manifest, dict) and str(manifest.get("kind") or "").lower() in family_filter)
    ]
    kept_indices = set(in_family_indices[: policy.keep_latest])
    safety_cutoff = now - _PRUNE_KEEP_SAFETY_WINDOW
    age_cutoff = now - timedelta(days=policy.max_age_days) if policy.max_age_days > 0 else now

    for index, (run_dir, manifest, created_at) in enumerate(entries):
        run_id = (
            str(manifest.get("run_id"))
            if isinstance(manifest, dict) and manifest.get("run_id")
            else run_dir.name
        )
        kind = str(manifest.get("kind") or "") if isinstance(manifest, dict) else ""
        created_label = str(manifest.get("created_at") or "") if isinstance(manifest, dict) else ""
        size_bytes = _directory_size(run_dir)
        action = "keep"
        reason = "kept by policy"

        if family_filter and kind.lower() not in family_filter:
            action = "skip-family"
            reason = f"kind '{kind}' is not in selected families"
        elif index in kept_indices:
            action = "skip-keep-latest"
            reason = f"within keep_latest={policy.keep_latest}"
        elif policy.max_age_days > 0 and created_at is not None and created_at > safety_cutoff:
            action = "skip-young"
            reason = "younger than 24 hours; pass max_age_days=0 to override"
        elif policy.max_age_days == 0:
            action = "delete"
            reason = "max_age_days=0 forces delete after keep_latest window"
        elif created_at is None:
            action = "skip-young"
            reason = "manifest missing or unparseable created_at; refusing to delete"
        elif created_at <= age_cutoff:
            action = "delete"
            reason = f"older than {policy.max_age_days} days"

        candidates.append(
            PruneCandidate(
                run_id=run_id,
                run_dir=str(run_dir),
                kind=kind,
                created_at=created_label,
                size_bytes=size_bytes,
                action=action,
                reason=reason,
            )
        )
    return candidates


def _load_manifest(run_dir: Path) -> JSONDict | None:
    manifest_path = run_dir / "run_manifest.json"
    if not manifest_path.is_file():
        return None
    try:
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def _parse_created_at(manifest: JSONDict | None, run_dir: Path) -> datetime | None:
    if isinstance(manifest, dict):
        value = manifest.get("created_at")
        if isinstance(value, str) and value.strip():
            try:
                normalized = value.replace("Z", "+00:00")
                return datetime.fromisoformat(normalized).astimezone(UTC)
            except ValueError:
                pass
    # Run ids encode the creation timestamp; fall back to that.
    stem = run_dir.name.split("-", 1)[0]
    try:
        return datetime.strptime(stem, "%Y%m%dT%H%M%SZ").replace(tzinfo=UTC)
    except ValueError:
        return None


def _directory_size(path: Path) -> int:
    total = 0
    try:
        for item in path.rglob("*"):
            try:
                if item.is_file():
                    total += item.stat().st_size
            except OSError:
                continue
    except OSError:
        return total
    return total


__all__ = [
    "RUNS_PRUNE_SCHEMA_VERSION",
    "PruneCandidate",
    "PruneReport",
    "RunsRetentionPolicy",
    "apply_prune",
    "parse_runs_retention",
    "plan_prune",
]

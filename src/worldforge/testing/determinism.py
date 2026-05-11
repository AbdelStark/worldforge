"""Deterministic controls for artifact and report tests."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from worldforge.models import WorldForgeError

_DEFAULT_START = datetime(2026, 1, 1, 0, 0, 0, tzinfo=UTC)


@dataclass(slots=True)
class DeterministicClock:
    """Small deterministic wall-clock and monotonic-clock pair for tests."""

    start: datetime = _DEFAULT_START
    wall_step: timedelta = timedelta(seconds=1)
    monotonic_start: float = 1_000.0
    monotonic_step: float = 0.25
    _wall_ticks: int = field(default=0, init=False)
    _monotonic_ticks: int = field(default=0, init=False)

    def __post_init__(self) -> None:
        if self.start.tzinfo is None:
            self.start = self.start.replace(tzinfo=UTC)
        else:
            self.start = self.start.astimezone(UTC)
        if self.wall_step.total_seconds() < 0:
            raise WorldForgeError("DeterministicClock wall_step must be non-negative.")
        if self.monotonic_step < 0:
            raise WorldForgeError("DeterministicClock monotonic_step must be non-negative.")

    def now(self) -> datetime:
        """Return the next deterministic UTC datetime and advance the wall clock."""

        value = self.start + self.wall_step * self._wall_ticks
        self._wall_ticks += 1
        return value

    def now_iso(self) -> str:
        """Return the next deterministic UTC datetime in ISO-8601 form."""

        return self.now().replace(microsecond=0).isoformat()

    def monotonic(self) -> float:
        """Return the next deterministic monotonic value and advance the timer."""

        value = self.monotonic_start + self.monotonic_step * self._monotonic_ticks
        self._monotonic_ticks += 1
        return value

    def reset(self) -> None:
        """Reset both deterministic counters back to their start values."""

        self._wall_ticks = 0
        self._monotonic_ticks = 0


@dataclass(slots=True)
class DeterministicIdFactory:
    """Generate sortable IDs for snapshot-safe run and report fixtures."""

    start: datetime = _DEFAULT_START
    step: timedelta = timedelta(seconds=1)
    suffix_start: int = 1
    _next_index: int = field(init=False)

    def __post_init__(self) -> None:
        if self.start.tzinfo is None:
            self.start = self.start.replace(tzinfo=UTC)
        else:
            self.start = self.start.astimezone(UTC)
        if self.step.total_seconds() < 0:
            raise WorldForgeError("DeterministicIdFactory step must be non-negative.")
        if self.suffix_start < 0:
            raise WorldForgeError("DeterministicIdFactory suffix_start must be non-negative.")
        self._next_index = self.suffix_start

    def run_id(self, *, index: int | None = None, at: datetime | None = None) -> str:
        """Return a valid preserved-run id with a deterministic timestamp and hex suffix."""

        resolved_index = self._take_index(index)
        if at is None:
            timestamp_source = self.start + self.step * (resolved_index - self.suffix_start)
        elif at.tzinfo is None:
            timestamp_source = at.replace(tzinfo=UTC)
        else:
            timestamp_source = at.astimezone(UTC)
        timestamp = timestamp_source.strftime("%Y%m%dT%H%M%SZ")
        return f"{timestamp}-{_hex_suffix(resolved_index, width=8)}"

    def prefixed_id(self, prefix: str, *, index: int | None = None, width: int = 12) -> str:
        """Return a deterministic opaque id using WorldForge's ``prefix_<hex>`` style."""

        if not isinstance(prefix, str) or not prefix.strip():
            raise WorldForgeError("Deterministic id prefix must be a non-empty string.")
        if width <= 0:
            raise WorldForgeError("Deterministic id width must be greater than 0.")
        return f"{prefix.strip()}_{_hex_suffix(self._take_index(index), width=width)}"

    def reset(self) -> None:
        """Reset the next suffix back to ``suffix_start``."""

        self._next_index = self.suffix_start

    def _take_index(self, index: int | None) -> int:
        if index is not None:
            if index < 0:
                raise WorldForgeError("Deterministic id index must be non-negative.")
            return index
        value = self._next_index
        self._next_index += 1
        return value


def deterministic_run_workspace(
    workspace_dir: Path,
    *,
    kind: str,
    command: str,
    ids: DeterministicIdFactory | None = None,
    provider: str | None = None,
    operation: str | None = None,
    input_summary: Mapping[str, Any] | None = None,
):
    """Create a run workspace with a deterministic id for tests."""

    from worldforge.harness.workspace import create_run_workspace

    factory = ids or DeterministicIdFactory()
    return create_run_workspace(
        workspace_dir,
        kind=kind,
        command=command,
        provider=provider,
        operation=operation,
        run_id=factory.run_id(),
        input_summary=dict(input_summary or {}),
    )


def stable_json_dumps(
    payload: Any,
    *,
    indent: int | None = 2,
    trailing_newline: bool = True,
) -> str:
    """Serialize JSON with sorted keys, finite numbers, and a stable trailing newline."""

    try:
        text = json.dumps(payload, indent=indent, sort_keys=True, allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise WorldForgeError(
            "Stable JSON snapshots must be serializable and contain only finite numbers."
        ) from exc
    if trailing_newline and not text.endswith("\n"):
        text = f"{text}\n"
    return text


def stable_snapshot(
    value: Any,
    *,
    path_roots: Mapping[Path | str, str] | None = None,
    field_replacements: Mapping[str, Any] | None = None,
) -> Any:
    """Return a JSON-like value with local paths and named volatile fields normalized."""

    roots = _path_replacements(path_roots or {})
    replacements = dict(field_replacements or {})
    return _stable_snapshot_value(value, roots=roots, field_replacements=replacements)


def stable_path(
    path: Path | str,
    *,
    path_roots: Mapping[Path | str, str],
) -> str:
    """Return a deterministic label for a path under one of ``path_roots``."""

    return str(stable_snapshot(Path(path), path_roots=path_roots))


def _stable_snapshot_value(
    value: Any,
    *,
    roots: tuple[tuple[str, str], ...],
    field_replacements: Mapping[str, Any],
) -> Any:
    if isinstance(value, Path):
        return _replace_path_roots(str(value.expanduser().resolve()), roots)
    if isinstance(value, str):
        return _replace_path_roots(value, roots)
    if value is None or isinstance(value, bool | int | float):
        return value
    if isinstance(value, tuple | list):
        return [
            _stable_snapshot_value(item, roots=roots, field_replacements=field_replacements)
            for item in value
        ]
    if isinstance(value, Mapping):
        normalized: dict[str, Any] = {}
        for key in value:
            if not isinstance(key, str):
                raise WorldForgeError("Stable snapshot mapping keys must be strings.")
        for key in sorted(value):
            if key in field_replacements:
                normalized[key] = field_replacements[key]
                continue
            normalized[key] = _stable_snapshot_value(
                value[key],
                roots=roots,
                field_replacements=field_replacements,
            )
        return normalized
    raise WorldForgeError(f"Stable snapshot value has unsupported type: {type(value).__name__}.")


def _path_replacements(path_roots: Mapping[Path | str, str]) -> tuple[tuple[str, str], ...]:
    replacements = []
    for root, label in path_roots.items():
        if not isinstance(label, str) or not label:
            raise WorldForgeError("Stable path replacement labels must be non-empty strings.")
        replacements.append((str(Path(root).expanduser().resolve()), label))
    return tuple(sorted(replacements, key=lambda item: len(item[0]), reverse=True))


def _replace_path_roots(value: str, roots: tuple[tuple[str, str], ...]) -> str:
    normalized = value
    for root, label in roots:
        normalized = normalized.replace(root, label)
    return normalized


def _hex_suffix(index: int, *, width: int) -> str:
    if index < 0 or index >= 16**width:
        raise WorldForgeError(f"Deterministic id index must fit in {width} hex characters.")
    return f"{index:0{width}x}"


__all__ = [
    "DeterministicClock",
    "DeterministicIdFactory",
    "deterministic_run_workspace",
    "stable_json_dumps",
    "stable_path",
    "stable_snapshot",
]

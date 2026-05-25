"""Frozen snapshot of the public Python export surface (WF-PQDX3-002).

This test catches accidental drops, renames, or additions to any of the
modules that WorldForge advertises as Stable in
``docs/src/api-stability.md``. The snapshot lives at
``tests/fixtures/public_api/exports.json`` and is the source of truth for the
current export set; intentional changes should regenerate the snapshot in the
same commit as the surface change.

To update the snapshot after an intentional public-API change:

```bash
WORLDFORGE_UPDATE_PUBLIC_API_SNAPSHOT=1 uv run pytest tests/test_public_api_snapshot.py
```

or run ``python scripts/update_public_api_snapshot.py``.
"""

from __future__ import annotations

import importlib
import json
import os
from pathlib import Path

import pytest

SNAPSHOT_PATH = Path(__file__).resolve().parent / "fixtures" / "public_api" / "exports.json"

SNAPSHOT_MODULES: tuple[str, ...] = (
    "worldforge",
    "worldforge.testing",
    "worldforge.observability",
    "worldforge.providers",
    "worldforge.capabilities",
)


def _module_exports(module_name: str) -> list[str]:
    module = importlib.import_module(module_name)
    raw = getattr(module, "__all__", None)
    if raw is not None:
        names = {str(item) for item in raw}
    else:
        names = {name for name in dir(module) if not name.startswith("_")}
    return sorted(names)


def _current_snapshot() -> dict:
    return {
        "schema_version": 1,
        "modules": {name: _module_exports(name) for name in SNAPSHOT_MODULES},
    }


def _load_snapshot() -> dict:
    return json.loads(SNAPSHOT_PATH.read_text(encoding="utf-8"))


def _format_drift(name: str, expected: list[str], observed: list[str]) -> list[str]:
    expected_set = set(expected)
    observed_set = set(observed)
    added = sorted(observed_set - expected_set)
    removed = sorted(expected_set - observed_set)
    lines: list[str] = []
    if added:
        lines.append(f"  added in {name}: {', '.join(added)}")
    if removed:
        lines.append(f"  removed from {name}: {', '.join(removed)}")
    return lines


def _write_snapshot(snapshot: dict) -> None:
    SNAPSHOT_PATH.parent.mkdir(parents=True, exist_ok=True)
    SNAPSHOT_PATH.write_text(
        json.dumps(snapshot, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def test_snapshot_fixture_exists() -> None:
    update_cmd = (
        "WORLDFORGE_UPDATE_PUBLIC_API_SNAPSHOT=1 uv run pytest tests/test_public_api_snapshot.py"
    )
    assert SNAPSHOT_PATH.is_file(), (
        f"Public-API snapshot fixture missing at "
        f"{SNAPSHOT_PATH.relative_to(Path.cwd())}. Run `{update_cmd}` to generate it."
    )


def test_snapshot_schema_shape() -> None:
    payload = _load_snapshot()
    assert payload["schema_version"] == 1
    assert set(payload["modules"]) == set(SNAPSHOT_MODULES)


def test_public_api_matches_snapshot() -> None:
    snapshot = _load_snapshot()
    current = _current_snapshot()

    if os.environ.get("WORLDFORGE_UPDATE_PUBLIC_API_SNAPSHOT") == "1":
        _write_snapshot(current)
        pytest.skip(
            "Public-API snapshot rewritten because WORLDFORGE_UPDATE_PUBLIC_API_SNAPSHOT=1 was set."
        )

    drift: list[str] = []
    for name in SNAPSHOT_MODULES:
        expected = snapshot["modules"].get(name, [])
        observed = current["modules"][name]
        if expected != observed:
            drift.extend(_format_drift(name, expected, observed))

    if drift:
        message_lines = [
            "Public Python export surface drifted from "
            f"`{SNAPSHOT_PATH.relative_to(Path.cwd()).as_posix()}`:",
            *drift,
            "",
            "If the change is intentional, regenerate the snapshot in the same commit:",
            "    WORLDFORGE_UPDATE_PUBLIC_API_SNAPSHOT=1 uv run pytest "
            "tests/test_public_api_snapshot.py",
            "or run `python scripts/update_public_api_snapshot.py`. "
            "Then update `docs/src/api-stability.md` if a Stable symbol was added, "
            "renamed, or removed.",
        ]
        pytest.fail("\n".join(message_lines))


def test_snapshot_is_sorted_and_unique() -> None:
    snapshot = _load_snapshot()
    for module_name, names in snapshot["modules"].items():
        assert names == sorted(set(names)), (
            f"Snapshot for {module_name} must be a sorted list of unique names."
        )
        for entry in names:
            assert isinstance(entry, str), f"Snapshot entry in {module_name} must be a string."
            assert entry, f"Snapshot entry in {module_name} must be non-empty."
            assert entry == "__version__" or not entry.startswith("_"), (
                f"Snapshot entry '{entry}' in {module_name} should not be private."
            )

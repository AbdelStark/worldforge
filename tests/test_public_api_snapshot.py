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
import importlib.util
import json
import math
import os
from pathlib import Path
from types import ModuleType

import pytest

from worldforge.artifact_io import write_json_artifact
from worldforge.models import WorldForgeError

UPDATE_SCRIPT_PATH = (
    Path(__file__).resolve().parents[1] / "scripts" / "update_public_api_snapshot.py"
)
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


def _write_snapshot(snapshot: dict, snapshot_path: Path = SNAPSHOT_PATH) -> None:
    write_json_artifact(snapshot_path, snapshot)


def _load_update_script() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "worldforge_update_public_api_snapshot_test_target",
        UPDATE_SCRIPT_PATH,
    )
    if spec is None or spec.loader is None:  # pragma: no cover - importlib invariant
        raise AssertionError(f"Could not load {UPDATE_SCRIPT_PATH}.")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


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


def test_update_script_rejects_non_finite_snapshot_before_touching_disk(
    tmp_path, monkeypatch
) -> None:
    update_public_api_snapshot = _load_update_script()
    target = tmp_path / "nested" / "exports.json"
    monkeypatch.setattr(update_public_api_snapshot, "SNAPSHOT_PATH", target)
    monkeypatch.setattr(update_public_api_snapshot, "MODULES", ("worldforge",))
    monkeypatch.setattr(
        update_public_api_snapshot,
        "_module_exports",
        lambda _name: ["WorldForge", math.nan],
    )

    with pytest.raises(WorldForgeError, match="finite numbers"):
        update_public_api_snapshot.main()

    assert not target.exists()
    assert not target.parent.exists()


def test_pytest_snapshot_writer_rejects_non_finite_snapshot_before_touching_disk(
    tmp_path,
) -> None:
    target = tmp_path / "nested" / "exports.json"

    with pytest.raises(WorldForgeError, match="finite numbers"):
        _write_snapshot({"schema_version": 1, "modules": {"worldforge": [math.nan]}}, target)

    assert not target.exists()
    assert not target.parent.exists()


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

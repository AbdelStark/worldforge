from __future__ import annotations

import importlib.util
import math
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

from worldforge.models import WorldForgeError

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "manage_fixture_snapshots.py"
SPEC = importlib.util.spec_from_file_location("manage_fixture_snapshots", SCRIPT)
assert SPEC is not None
manage_fixture_snapshots = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules["manage_fixture_snapshots"] = manage_fixture_snapshots
SPEC.loader.exec_module(manage_fixture_snapshots)


@dataclass(frozen=True, slots=True)
class _PayloadCarrier:
    payload: dict[str, Any]
    entries: tuple[object, ...] = ()
    passed: bool = True

    def to_dict(self) -> dict[str, Any]:
        return self.payload

    def to_markdown(self) -> str:
        return "# ok\n"


def test_fixture_snapshot_write_rejects_non_finite_manifest_before_touching_disk(
    monkeypatch,
    tmp_path: Path,
) -> None:
    target = tmp_path / "nested" / "fixture-snapshots.json"
    monkeypatch.setattr(
        manage_fixture_snapshots,
        "build_fixture_snapshot_manifest",
        lambda *_args, **_kwargs: _PayloadCarrier(
            {"schema_version": 1, "entries": [{"size_bytes": math.nan}]}
        ),
    )

    with pytest.raises(WorldForgeError, match="finite numbers"):
        manage_fixture_snapshots.main(["--write", "--manifest", str(target), "--root", str(ROOT)])

    assert not target.exists()
    assert not target.parent.exists()


def test_fixture_snapshot_json_report_rejects_non_finite_payload(
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(
        manage_fixture_snapshots,
        "load_fixture_snapshot_manifest",
        lambda *_args, **_kwargs: object(),
    )
    monkeypatch.setattr(
        manage_fixture_snapshots,
        "validate_fixture_snapshot_manifest",
        lambda *_args, **_kwargs: _PayloadCarrier(
            {"passed": True, "summary": {"duration_ms": math.inf}}
        ),
    )

    with pytest.raises(WorldForgeError, match="finite numbers"):
        manage_fixture_snapshots.main(
            ["--manifest", str(tmp_path / "fixture-snapshots.json"), "--format", "json"]
        )

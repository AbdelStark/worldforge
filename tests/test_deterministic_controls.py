from __future__ import annotations

import math
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from worldforge.harness.workspace import validate_run_id
from worldforge.models import WorldForgeError
from worldforge.testing import (
    DeterministicClock,
    DeterministicIdFactory,
    deterministic_run_workspace,
    stable_json_dumps,
    stable_path,
    stable_snapshot,
)


def test_deterministic_clock_returns_stable_wall_and_monotonic_values() -> None:
    clock = DeterministicClock(
        start=datetime(2026, 1, 1, tzinfo=UTC),
        wall_step=timedelta(seconds=2),
        monotonic_start=10.0,
        monotonic_step=0.125,
    )

    assert clock.now_iso() == "2026-01-01T00:00:00+00:00"
    assert clock.now_iso() == "2026-01-01T00:00:02+00:00"
    assert clock.monotonic() == 10.0
    assert clock.monotonic() == 10.125

    clock.reset()
    assert clock.now_iso() == "2026-01-01T00:00:00+00:00"
    assert clock.monotonic() == 10.0


def test_deterministic_ids_create_valid_sortable_run_ids() -> None:
    ids = DeterministicIdFactory(
        start=datetime(2026, 1, 1, 0, 0, 0, tzinfo=UTC),
        step=timedelta(seconds=5),
    )

    first = ids.run_id()
    second = ids.run_id()

    assert first == "20260101T000000Z-00000001"
    assert second == "20260101T000005Z-00000002"
    assert validate_run_id(first) == first
    assert validate_run_id(second) == second
    assert ids.prefixed_id("world", index=3) == "world_000000000003"


def test_deterministic_run_workspace_pins_manifest_time(tmp_path: Path) -> None:
    ids = DeterministicIdFactory(start=datetime(2026, 1, 1, tzinfo=UTC))

    workspace = deterministic_run_workspace(
        tmp_path,
        kind="eval",
        command="worldforge eval --suite planning --provider mock",
        ids=ids,
        provider="mock",
        operation="planning",
        input_summary={"providers": ["mock"], "suite_id": "planning"},
    )

    manifest = stable_snapshot(workspace.manifest_path)
    assert manifest == str(workspace.manifest_path.resolve())
    assert workspace.run_id == "20260101T000000Z-00000001"
    payload = stable_snapshot(
        workspace.manifest_path.read_text(encoding="utf-8"),
        path_roots={tmp_path: "<workspace>"},
    )
    assert "<workspace>" not in payload
    assert "2026-01-01T00:00:00Z" in payload


def test_stable_snapshot_normalizes_paths_and_volatile_fields(tmp_path: Path) -> None:
    payload = {
        "z": str(tmp_path / "runs" / "20260101T000000Z-00000001"),
        "a": {"world_id": "world_random", "path": tmp_path / "reports" / "report.json"},
    }

    snapshot = stable_snapshot(
        payload,
        path_roots={tmp_path: "<tmp>"},
        field_replacements={"world_id": "<world-id>"},
    )

    assert stable_json_dumps(snapshot) == (
        "{\n"
        '  "a": {\n'
        '    "path": "<tmp>/reports/report.json",\n'
        '    "world_id": "<world-id>"\n'
        "  },\n"
        '  "z": "<tmp>/runs/20260101T000000Z-00000001"\n'
        "}\n"
    )
    assert stable_path(tmp_path / "reports" / "report.json", path_roots={tmp_path: "<tmp>"}) == (
        "<tmp>/reports/report.json"
    )


def test_stable_json_rejects_non_finite_values() -> None:
    with pytest.raises(WorldForgeError, match="finite numbers"):
        stable_json_dumps({"latency_ms": math.nan})

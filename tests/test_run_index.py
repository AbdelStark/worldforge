"""Tests for the local run artifact index (WF-FEAT-004)."""

from __future__ import annotations

import csv
import io
import json
import sys
from pathlib import Path

import pytest

from worldforge import WorldForgeError
from worldforge.cli import main as worldforge_main
from worldforge.harness.run_history import RunHistoryFilter
from worldforge.harness.run_index import (
    RUN_INDEX_SCHEMA_VERSION,
    RunIndexIssue,
    build_run_index,
)
from worldforge.harness.workspace import create_run_workspace, write_run_manifest


def _seed_run(
    workspace_dir: Path,
    *,
    run_id: str,
    kind: str = "eval",
    provider: str | None = "mock",
    operation: str | None = "planning",
    status: str = "completed",
    artifact_paths: dict[str, str] | None = None,
    result_summary: dict[str, object] | None = None,
    input_summary: dict[str, object] | None = None,
) -> Path:
    workspace = create_run_workspace(
        workspace_dir,
        kind=kind,
        command=f"worldforge {kind}",
        provider=provider,
        operation=operation,
        run_id=run_id,
        input_summary=input_summary or {"capabilities": [operation] if operation else []},
    )
    artifacts = (
        artifact_paths
        if artifact_paths is not None
        else {
            "json": "reports/report.json",
            "markdown": "reports/report.md",
        }
    )
    for relative in artifacts.values():
        target = workspace.path / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("{}\n", encoding="utf-8")
    write_run_manifest(
        workspace,
        kind=kind,
        command=f"worldforge {kind}",
        provider=provider,
        operation=operation,
        status=status,
        artifact_paths=artifacts,
        input_summary=input_summary or {"capabilities": [operation] if operation else []},
        result_summary=result_summary or {},
    )
    return workspace.path


def test_build_run_index_returns_empty_for_missing_workspace(tmp_path: Path) -> None:
    index = build_run_index(tmp_path / "absent")

    assert index.entries == ()
    assert index.issues == ()
    assert index.schema_version == RUN_INDEX_SCHEMA_VERSION


def test_build_run_index_summarizes_valid_runs(tmp_path: Path) -> None:
    _seed_run(tmp_path, run_id="20260101T000000Z-00000001", kind="eval", operation="planning")
    _seed_run(tmp_path, run_id="20260102T000000Z-00000002", kind="benchmark", operation="predict")

    index = build_run_index(tmp_path)

    assert len(index.entries) == 2
    assert index.issues == ()
    assert {entry.kind for entry in index.entries} == {"eval", "benchmark"}
    # Newest first ordering matches list_run_workspaces convention.
    assert index.entries[0].run_id == "20260102T000000Z-00000002"


def test_build_run_index_flags_missing_manifest(tmp_path: Path) -> None:
    runs_dir = tmp_path / "runs"
    runs_dir.mkdir(parents=True)
    (runs_dir / "20260101T000000Z-stale001").mkdir()

    index = build_run_index(tmp_path)

    assert index.entries == ()
    assert len(index.issues) == 1
    assert index.issues[0].reason == "manifest-missing"


def test_build_run_index_flags_invalid_json(tmp_path: Path) -> None:
    runs_dir = tmp_path / "runs"
    runs_dir.mkdir(parents=True)
    bad = runs_dir / "20260101T000000Z-bad00001"
    bad.mkdir()
    (bad / "run_manifest.json").write_text("not-json{", encoding="utf-8")

    index = build_run_index(tmp_path)

    assert index.entries == ()
    assert len(index.issues) == 1
    assert index.issues[0].reason == "manifest-invalid-json"


def test_build_run_index_flags_non_object_payload(tmp_path: Path) -> None:
    runs_dir = tmp_path / "runs"
    runs_dir.mkdir(parents=True)
    bad = runs_dir / "20260101T000000Z-bad00002"
    bad.mkdir()
    (bad / "run_manifest.json").write_text("[1, 2, 3]\n", encoding="utf-8")

    index = build_run_index(tmp_path)

    assert index.entries == ()
    assert len(index.issues) == 1
    assert index.issues[0].reason == "manifest-not-object"


def test_build_run_index_partitions_valid_and_invalid(tmp_path: Path) -> None:
    _seed_run(tmp_path, run_id="20260101T000000Z-00000001")
    runs_dir = tmp_path / "runs"
    bad = runs_dir / "20260102T000000Z-baddir99"
    bad.mkdir()
    (bad / "run_manifest.json").write_text("{not-json", encoding="utf-8")

    index = build_run_index(tmp_path)

    assert {entry.run_id for entry in index.entries} == {"20260101T000000Z-00000001"}
    assert {issue.reason for issue in index.issues} == {"manifest-invalid-json"}


def test_filter_by_provider_substring_matches(tmp_path: Path) -> None:
    _seed_run(tmp_path, run_id="20260101T000000Z-00000001", provider="mock")
    _seed_run(tmp_path, run_id="20260102T000000Z-00000002", provider="cosmos")

    index = build_run_index(tmp_path, filters=RunHistoryFilter.from_strings(provider="cos"))

    assert [entry.provider for entry in index.entries] == ["cosmos"]
    assert index.filter_applied == {
        "provider": "cos",
        "capability": None,
        "status": None,
        "created_from": None,
        "created_to": None,
        "artifact_type": None,
    }


def test_filter_by_status_excludes_other_runs(tmp_path: Path) -> None:
    _seed_run(tmp_path, run_id="20260101T000000Z-00000001", status="completed")
    _seed_run(tmp_path, run_id="20260102T000000Z-00000002", status="failed")

    index = build_run_index(tmp_path, filters=RunHistoryFilter.from_strings(status="failed"))

    assert [entry.run_id for entry in index.entries] == ["20260102T000000Z-00000002"]


def test_filter_by_capability_excludes_other_capabilities(tmp_path: Path) -> None:
    _seed_run(
        tmp_path,
        run_id="20260101T000000Z-00000001",
        kind="eval",
        operation="planning",
        input_summary={"capabilities": ["predict"]},
    )
    _seed_run(
        tmp_path,
        run_id="20260102T000000Z-00000002",
        kind="benchmark",
        operation="generate",
        input_summary={"capabilities": ["generate"]},
    )

    index = build_run_index(tmp_path, filters=RunHistoryFilter.from_strings(capability="predict"))

    assert [entry.run_id for entry in index.entries] == ["20260101T000000Z-00000001"]


def test_filter_by_artifact_type(tmp_path: Path) -> None:
    _seed_run(
        tmp_path,
        run_id="20260101T000000Z-00000001",
        artifact_paths={"csv": "reports/report.csv"},
    )
    _seed_run(
        tmp_path,
        run_id="20260102T000000Z-00000002",
        artifact_paths={"json": "reports/report.json"},
    )

    index = build_run_index(tmp_path, filters=RunHistoryFilter.from_strings(artifact_type="csv"))

    assert [entry.run_id for entry in index.entries] == ["20260101T000000Z-00000001"]


def test_filter_by_created_date_range(tmp_path: Path) -> None:
    _seed_run(tmp_path, run_id="20260101T000000Z-00000001")
    _seed_run(tmp_path, run_id="20260102T000000Z-00000002")
    _seed_run(tmp_path, run_id="20260104T000000Z-00000003")

    index = build_run_index(
        tmp_path,
        filters=RunHistoryFilter.from_strings(
            created_from="2026-01-02",
            created_to="2026-01-03",
        ),
    )

    assert [entry.run_id for entry in index.entries] == ["20260102T000000Z-00000002"]


def test_invalid_date_filter_raises() -> None:
    with pytest.raises(WorldForgeError, match="YYYY-MM-DD"):
        RunHistoryFilter.from_strings(created_from="not-a-date")


def test_to_json_payload_is_safe_to_attach(tmp_path: Path) -> None:
    _seed_run(tmp_path, run_id="20260101T000000Z-00000001")

    index = build_run_index(tmp_path)
    payload = json.loads(index.to_json())

    assert payload["schema_version"] == RUN_INDEX_SCHEMA_VERSION
    assert payload["entry_count"] == 1
    assert payload["issue_count"] == 0
    assert payload["entries"][0]["run_id"] == "20260101T000000Z-00000001"
    # No raw artifact contents leaked into the payload — only labelled paths and metadata.
    serialized = json.dumps(payload)
    assert "raw" not in serialized.lower() or "raw_artifact" not in serialized.lower()


def test_to_markdown_includes_envelope_and_table(tmp_path: Path) -> None:
    _seed_run(tmp_path, run_id="20260101T000000Z-00000001")

    rendered = build_run_index(tmp_path).to_markdown()

    assert rendered.startswith("# WorldForge Run Index")
    assert "schema_version: 1" in rendered
    assert "20260101T000000Z-00000001" in rendered
    assert "## Issues" in rendered


def test_to_csv_emits_header_and_one_row_per_entry(tmp_path: Path) -> None:
    _seed_run(tmp_path, run_id="20260101T000000Z-00000001", provider="mock")
    _seed_run(tmp_path, run_id="20260102T000000Z-00000002", provider="cosmos")

    csv_text = build_run_index(tmp_path).to_csv()
    rows = list(csv.reader(io.StringIO(csv_text)))

    assert rows[0] == [
        "run_id",
        "kind",
        "status",
        "provider",
        "capability",
        "created_at",
        "artifact_count",
        "safe_artifact_types",
        "event_count",
        "failure_summary",
        "path",
    ]
    assert {row[0] for row in rows[1:]} == {
        "20260101T000000Z-00000001",
        "20260102T000000Z-00000002",
    }


def test_invalid_workspace_dir_raises() -> None:
    with pytest.raises(WorldForgeError, match="non-empty"):
        build_run_index("")
    with pytest.raises(WorldForgeError, match="must be a Path"):
        build_run_index(123)  # type: ignore[arg-type]


def test_invalid_filters_argument_raises(tmp_path: Path) -> None:
    with pytest.raises(WorldForgeError, match="RunHistoryFilter"):
        build_run_index(tmp_path, filters="not-a-filter")  # type: ignore[arg-type]


def test_run_index_issue_validates_inputs() -> None:
    with pytest.raises(WorldForgeError, match="run_dir"):
        RunIndexIssue(run_dir="", reason="manifest-missing", detail="")
    with pytest.raises(WorldForgeError, match="reason must be one of"):
        RunIndexIssue(run_dir="/runs/x", reason="bogus", detail="")
    with pytest.raises(WorldForgeError, match="detail must be a string"):
        RunIndexIssue(run_dir="/runs/x", reason="manifest-missing", detail=42)  # type: ignore[arg-type]


def test_runs_index_cli_json_format(tmp_path: Path, monkeypatch, capsys) -> None:
    _seed_run(tmp_path, run_id="20260101T000000Z-00000001", provider="mock")

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "worldforge",
            "runs",
            "index",
            "--workspace-dir",
            str(tmp_path),
            "--format",
            "json",
        ],
    )
    assert worldforge_main() == 0

    payload = json.loads(capsys.readouterr().out)
    assert payload["entry_count"] == 1
    assert payload["entries"][0]["provider"] == "mock"


def test_runs_index_cli_markdown_writes_to_output_path(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    _seed_run(tmp_path, run_id="20260101T000000Z-00000001")
    output = tmp_path / "out" / "index.md"

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "worldforge",
            "runs",
            "index",
            "--workspace-dir",
            str(tmp_path),
            "--format",
            "markdown",
            "--output",
            str(output),
        ],
    )
    assert worldforge_main() == 0
    assert capsys.readouterr().out == ""
    assert output.read_text(encoding="utf-8").startswith("# WorldForge Run Index")


def test_runs_index_cli_filters_results(tmp_path: Path, monkeypatch, capsys) -> None:
    _seed_run(tmp_path, run_id="20260101T000000Z-00000001", status="completed")
    _seed_run(tmp_path, run_id="20260102T000000Z-00000002", status="failed")

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "worldforge",
            "runs",
            "index",
            "--workspace-dir",
            str(tmp_path),
            "--status",
            "failed",
            "--format",
            "json",
        ],
    )
    assert worldforge_main() == 0

    payload = json.loads(capsys.readouterr().out)
    assert [entry["run_id"] for entry in payload["entries"]] == [
        "20260102T000000Z-00000002",
    ]
    assert payload["filter_applied"]["status"] == "failed"


def test_run_index_issue_to_dict_round_trip() -> None:
    issue = RunIndexIssue(
        run_dir="/runs/20260101T000000Z-stale001",
        reason="manifest-missing",
        detail="run_manifest.json not found",
    )
    payload = issue.to_dict()
    assert payload == {
        "run_dir": "/runs/20260101T000000Z-stale001",
        "reason": "manifest-missing",
        "detail": "run_manifest.json not found",
    }


def test_to_markdown_with_no_entries_renders_filler_row(tmp_path: Path) -> None:
    rendered = build_run_index(tmp_path).to_markdown()
    assert "| - | - | - | - | - | - | - | - |" in rendered


def test_to_markdown_with_filter_includes_filter_line(tmp_path: Path) -> None:
    _seed_run(tmp_path, run_id="20260101T000000Z-00000001", provider="mock")
    rendered = build_run_index(
        tmp_path,
        filters=RunHistoryFilter.from_strings(provider="mock"),
    ).to_markdown()
    assert "filter: provider=mock" in rendered


def test_to_markdown_with_issues_renders_issue_table(tmp_path: Path) -> None:
    runs = tmp_path / "runs"
    runs.mkdir()
    (runs / "20260101T000000Z-stale001").mkdir()
    rendered = build_run_index(tmp_path).to_markdown()
    assert "| Path | Reason | Detail |" in rendered
    assert "manifest-missing" in rendered


def test_build_run_index_accepts_string_workspace_dir(tmp_path: Path) -> None:
    _seed_run(tmp_path, run_id="20260101T000000Z-00000001")
    index = build_run_index(str(tmp_path))
    assert len(index.entries) == 1


def test_scan_skips_files_inside_runs_dir(tmp_path: Path) -> None:
    runs = tmp_path / "runs"
    runs.mkdir()
    (runs / "stray-file.txt").write_text("not a run dir\n", encoding="utf-8")
    index = build_run_index(tmp_path)
    assert index.entries == ()
    assert index.issues == ()


def test_scan_records_unreadable_manifest(tmp_path: Path, monkeypatch) -> None:
    runs = tmp_path / "runs"
    runs.mkdir()
    bad = runs / "20260101T000000Z-bad00003"
    bad.mkdir()
    manifest_path = bad / "run_manifest.json"
    manifest_path.write_text("{}", encoding="utf-8")

    real_read_text = Path.read_text

    def fake_read_text(self, *args, **kwargs):
        if self == manifest_path:
            raise OSError("simulated unreadable manifest")
        return real_read_text(self, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", fake_read_text)
    index = build_run_index(tmp_path)
    assert index.entries == ()
    assert [issue.reason for issue in index.issues] == ["manifest-unreadable"]


def test_runs_index_cli_csv_includes_header(tmp_path: Path, monkeypatch, capsys) -> None:
    _seed_run(tmp_path, run_id="20260101T000000Z-00000001", provider="mock")

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "worldforge",
            "runs",
            "index",
            "--workspace-dir",
            str(tmp_path),
            "--format",
            "csv",
        ],
    )
    assert worldforge_main() == 0

    output = capsys.readouterr().out
    rows = list(csv.reader(io.StringIO(output)))
    assert rows[0][0] == "run_id"
    assert rows[1][0] == "20260101T000000Z-00000001"

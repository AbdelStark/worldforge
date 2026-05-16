"""Tests for the runs retention policy + prune command (WF-FEAT3-003)."""

from __future__ import annotations

import json
import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest

from worldforge import WorldForgeError
from worldforge.cli import main as worldforge_main
from worldforge.harness.workspace import create_run_workspace, write_run_manifest
from worldforge.runs_prune import (
    RUNS_PRUNE_SCHEMA_VERSION,
    RunsRetentionPolicy,
    apply_prune,
    parse_runs_retention,
    plan_prune,
)


def _seed_run(workspace: Path, run_id: str, *, kind: str = "eval") -> Path:
    ws = create_run_workspace(
        workspace,
        kind=kind,
        command=f"worldforge {kind}",
        provider="mock",
        operation="planning" if kind == "eval" else "predict",
        run_id=run_id,
    )
    write_run_manifest(
        ws,
        kind=kind,
        command=f"worldforge {kind}",
        provider="mock",
        operation="planning" if kind == "eval" else "predict",
        status="completed",
    )
    return ws.path


def test_policy_defaults_and_validation() -> None:
    p = RunsRetentionPolicy()
    assert p.max_age_days == 30
    assert p.keep_latest == 10
    assert p.families == ()

    with pytest.raises(WorldForgeError, match="max_age_days"):
        RunsRetentionPolicy(max_age_days=-1)
    with pytest.raises(WorldForgeError, match="keep_latest"):
        RunsRetentionPolicy(keep_latest=-1)
    with pytest.raises(WorldForgeError, match="families entries"):
        RunsRetentionPolicy(families=("",))


def test_plan_prune_on_empty_workspace(tmp_path: Path) -> None:
    report = plan_prune(tmp_path)
    assert report.schema_version == RUNS_PRUNE_SCHEMA_VERSION
    assert report.candidates == ()
    assert report.applied is False


def test_plan_prune_keeps_latest(tmp_path: Path) -> None:
    for i in range(5):
        _seed_run(tmp_path, f"2026010{i + 1}T000000Z-{i:08x}", kind="eval")
    policy = RunsRetentionPolicy(max_age_days=1, keep_latest=2)
    # Force "now" far in the future so age cutoff fires on the older runs.
    report = plan_prune(
        tmp_path,
        policy=policy,
        now=datetime(2026, 5, 1, tzinfo=UTC),
    )
    actions = [c.action for c in report.candidates]
    # Newest 2 are kept by keep_latest; the other 3 are old enough to delete.
    assert actions.count("skip-keep-latest") == 2
    assert actions.count("delete") == 3


def test_plan_prune_respects_24h_safety_window(tmp_path: Path) -> None:
    _seed_run(tmp_path, "20260101T000000Z-aaaaaaaa")
    # "Now" is only an hour later than the run id timestamp.
    report = plan_prune(
        tmp_path,
        policy=RunsRetentionPolicy(max_age_days=1, keep_latest=0),
        now=datetime(2026, 1, 1, 1, 0, 0, tzinfo=UTC),
    )
    assert [c.action for c in report.candidates] == ["skip-young"]


def test_plan_prune_max_age_zero_overrides_safety(tmp_path: Path) -> None:
    _seed_run(tmp_path, "20260101T000000Z-aaaaaaaa")
    report = plan_prune(
        tmp_path,
        policy=RunsRetentionPolicy(max_age_days=0, keep_latest=0),
        now=datetime(2026, 1, 1, 1, 0, 0, tzinfo=UTC),
    )
    assert [c.action for c in report.candidates] == ["delete"]


def test_plan_prune_family_filter(tmp_path: Path) -> None:
    _seed_run(tmp_path, "20260101T000000Z-bbbbbbbb", kind="eval")
    _seed_run(tmp_path, "20260101T000000Z-cccccccc", kind="benchmark")
    policy = RunsRetentionPolicy(max_age_days=0, keep_latest=0, families=("benchmark",))
    report = plan_prune(
        tmp_path,
        policy=policy,
        now=datetime(2026, 5, 1, tzinfo=UTC),
    )
    by_kind = {c.kind: c.action for c in report.candidates}
    assert by_kind["benchmark"] == "delete"
    assert by_kind["eval"] == "skip-family"


def test_apply_prune_deletes_selected(tmp_path: Path) -> None:
    paths = [_seed_run(tmp_path, f"2026010{i + 1}T000000Z-{i:08x}", kind="eval") for i in range(3)]
    policy = RunsRetentionPolicy(max_age_days=1, keep_latest=1)
    report = plan_prune(
        tmp_path,
        policy=policy,
        now=datetime(2026, 5, 1, tzinfo=UTC),
    )
    applied = apply_prune(report)
    assert applied.applied is True

    # Newest run should still exist; older runs should be gone.
    surviving = sorted(p.name for p in (tmp_path / "runs").iterdir() if p.is_dir())
    assert surviving == [paths[-1].name]


def test_apply_prune_refuses_double_apply(tmp_path: Path) -> None:
    report = plan_prune(tmp_path)
    applied = apply_prune(report)
    with pytest.raises(WorldForgeError, match="already applied"):
        apply_prune(applied)


def test_apply_prune_refuses_paths_outside_runs(tmp_path: Path) -> None:
    from worldforge.runs_prune import PruneCandidate, PruneReport

    outside = tmp_path / "outside"
    outside.mkdir()
    report = PruneReport(
        schema_version=RUNS_PRUNE_SCHEMA_VERSION,
        workspace_dir=str(tmp_path),
        policy=RunsRetentionPolicy(),
        generated_at="2026-01-01T00:00:00Z",
        candidates=(
            PruneCandidate(
                run_id="x",
                run_dir=str(outside),
                kind="eval",
                created_at="2026-01-01T00:00:00Z",
                size_bytes=0,
                action="delete",
                reason="manual",
            ),
        ),
        applied=False,
    )
    with pytest.raises(WorldForgeError, match="outside runs directory"):
        apply_prune(report)


def test_parse_runs_retention_round_trips() -> None:
    policy = parse_runs_retention(
        {
            "max_age_days": 14,
            "keep_latest": 5,
            "families": ["scenario", "eval"],
        }
    )
    assert policy.max_age_days == 14
    assert policy.keep_latest == 5
    assert policy.families == ("scenario", "eval")


def test_parse_runs_retention_rejects_unknown_keys() -> None:
    with pytest.raises(WorldForgeError, match="unsupported keys"):
        parse_runs_retention({"max_age_days": 1, "ttl_hours": 12})


def test_parse_runs_retention_rejects_non_object() -> None:
    with pytest.raises(WorldForgeError, match="JSON object"):
        parse_runs_retention([1, 2, 3])


def test_runs_prune_cli_dry_run(tmp_path: Path, monkeypatch, capsys) -> None:
    _seed_run(tmp_path, "20260101T000000Z-deadbeef")
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "worldforge",
            "runs",
            "prune",
            "--workspace-dir",
            str(tmp_path),
            "--max-age-days",
            "0",
            "--keep-latest",
            "0",
            "--format",
            "json",
        ],
    )
    assert worldforge_main() == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["applied"] is False
    assert payload["delete_count"] == 1
    assert (tmp_path / "runs" / "20260101T000000Z-deadbeef").is_dir()


def test_runs_prune_cli_apply_removes_directories(tmp_path: Path, monkeypatch, capsys) -> None:
    _seed_run(tmp_path, "20260101T000000Z-deadbeef")
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "worldforge",
            "runs",
            "prune",
            "--workspace-dir",
            str(tmp_path),
            "--max-age-days",
            "0",
            "--keep-latest",
            "0",
            "--apply",
            "--format",
            "json",
        ],
    )
    assert worldforge_main() == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["applied"] is True
    assert payload["delete_count"] == 1
    assert not (tmp_path / "runs" / "20260101T000000Z-deadbeef").exists()


def test_runs_prune_cli_reads_config_profile(tmp_path: Path, monkeypatch, capsys) -> None:
    _seed_run(tmp_path, "20260101T000000Z-deadbeef")
    _seed_run(tmp_path, "20260102T000000Z-cafef00d")
    profile = tmp_path / "profile.json"
    profile.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "name": "demo",
                "runs_retention": {"max_age_days": 0, "keep_latest": 1, "families": []},
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "worldforge",
            "runs",
            "prune",
            "--workspace-dir",
            str(tmp_path),
            "--retention-profile",
            str(profile),
            "--format",
            "json",
        ],
    )
    assert worldforge_main() == 0
    payload = json.loads(capsys.readouterr().out)
    # Profile sets keep_latest=1; only the newest of 2 stays, the other becomes a delete candidate.
    assert payload["delete_count"] == 1


def test_runs_prune_report_markdown_renders_envelope(tmp_path: Path) -> None:
    _seed_run(tmp_path, "20260101T000000Z-deadbeef")
    rendered = plan_prune(
        tmp_path,
        policy=RunsRetentionPolicy(max_age_days=0, keep_latest=0),
    ).to_markdown()
    assert rendered.startswith("# WorldForge Run Prune Report")
    assert "20260101T000000Z-deadbeef" in rendered


def test_plan_prune_rejects_blank_workspace_dir() -> None:
    with pytest.raises(WorldForgeError, match="non-empty"):
        plan_prune("")


def test_plan_prune_keeps_runs_with_unparseable_created_at(tmp_path: Path) -> None:
    runs = tmp_path / "runs"
    runs.mkdir(parents=True)
    bad = runs / "weird-run-id"
    bad.mkdir()
    (bad / "run_manifest.json").write_text("{}", encoding="utf-8")
    report = plan_prune(
        tmp_path,
        policy=RunsRetentionPolicy(max_age_days=1, keep_latest=0),
        now=datetime(2026, 5, 1, tzinfo=UTC),
    )
    assert [c.action for c in report.candidates] == ["skip-young"]

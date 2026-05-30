"""Checkout-safe fixture snapshot drift review demo."""

from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path

from worldforge.artifact_io import write_json_artifact as _write_json
from worldforge.models import JSONDict
from worldforge.testing import (
    FixtureSnapshotEntry,
    FixtureSnapshotManifest,
    FixtureSnapshotReport,
    build_fixture_snapshot_manifest,
    validate_fixture_snapshot_manifest,
)

FIXTURE_DRIFT_CLAIM_BOUNDARY = (
    "Checkout-safe fixture drift walkthrough only; all mutations occur under the "
    "selected demo workspace."
)

FIXTURE_DRIFT_SUMMARY = (
    "Created a controlled fixture drift review covering missing, changed, schema-change, "
    "unsafe-path, and intended-update paths under a temp workspace."
)

FIXTURE_DRIFT_FIRST_TRIAGE_STEP = (
    "Open `fixture-drift-review.md`, inspect every changed fixture diff, then approve "
    "intentional updates before rewriting the manifest."
)

FIXTURE_DRIFT_APPROVED_UPDATE_PATH = (
    "Mark the reviewed manifest entry as review_status=intended-update.",
    "Run the snapshot manager with --allow-intended-updates for human review.",
    "After approving fixture and manifest diffs, refresh the manifest with --write.",
)


@dataclass(frozen=True, slots=True)
class FixtureDriftPaths:
    lab_root: Path
    provider_fixture: Path
    benchmark_fixture: Path
    scenario_fixture: Path
    baseline_manifest: Path
    review_manifest: Path
    review_json: Path
    review_markdown: Path
    intended_json: Path
    refreshed_manifest: Path
    summary: Path


@dataclass(frozen=True, slots=True)
class FixtureDriftRun:
    paths: FixtureDriftPaths
    baseline: FixtureSnapshotManifest
    baseline_report: FixtureSnapshotReport
    review_report: FixtureSnapshotReport
    intended_report: FixtureSnapshotReport


def run_fixture_drift_review_workflow(workflow_dir: Path) -> JSONDict:
    run = run_fixture_drift_review(workflow_dir)
    report = fixture_drift_summary_report(run)
    write_fixture_drift_summary(run.paths, report)
    return fixture_drift_result(run.paths, report)


def run_fixture_drift_review(workflow_dir: Path) -> FixtureDriftRun:
    paths = fixture_drift_paths(workflow_dir)
    write_fixture_drift_baseline_payloads(paths)
    baseline = build_fixture_snapshot_manifest(
        (paths.provider_fixture, paths.benchmark_fixture, paths.scenario_fixture),
        root=paths.lab_root,
    )
    baseline_report = validate_fixture_snapshot_manifest(baseline, root=paths.lab_root)
    _write_json(paths.baseline_manifest, baseline.to_dict())

    review_manifest = fixture_drift_review_manifest(paths, baseline)
    review_report = validate_fixture_snapshot_manifest(review_manifest, root=paths.lab_root)
    write_fixture_drift_review_outputs(paths, review_manifest, review_report)

    intended_report = fixture_drift_intended_report(paths, baseline)
    refreshed = build_fixture_snapshot_manifest(
        (paths.provider_fixture, paths.benchmark_fixture, paths.scenario_fixture),
        root=paths.lab_root,
    )
    write_fixture_drift_intended_outputs(paths, refreshed, intended_report)
    return FixtureDriftRun(
        paths=paths,
        baseline=baseline,
        baseline_report=baseline_report,
        review_report=review_report,
        intended_report=intended_report,
    )


def fixture_drift_paths(workflow_dir: Path) -> FixtureDriftPaths:
    lab_root = workflow_dir / "fixture-drift-lab"
    return FixtureDriftPaths(
        lab_root=lab_root,
        provider_fixture=lab_root / "tests/fixtures/providers/demo_provider_payload.json",
        benchmark_fixture=lab_root / "examples/demo-benchmark-inputs.json",
        scenario_fixture=lab_root / "examples/scenarios/demo-scenario.json",
        baseline_manifest=lab_root / "fixture-snapshots-baseline.json",
        review_manifest=lab_root / "fixture-snapshots-review.json",
        review_json=workflow_dir / "fixture-drift-review.json",
        review_markdown=workflow_dir / "fixture-drift-review.md",
        intended_json=workflow_dir / "fixture-drift-intended-update.json",
        refreshed_manifest=lab_root / "fixture-snapshots-refreshed.json",
        summary=workflow_dir / "fixture-drift-summary.json",
    )


def write_fixture_drift_baseline_payloads(paths: FixtureDriftPaths) -> None:
    payloads = {
        paths.provider_fixture: {
            "schema_version": 1,
            "provider": "mock",
            "status": "baseline",
        },
        paths.benchmark_fixture: {
            "schema_version": 1,
            "inputs": [{"provider": "mock", "operation": "predict"}],
        },
        paths.scenario_fixture: {
            "schema_version": 1,
            "id": "demo-scenario",
            "description": "Fixture drift walkthrough scenario.",
        },
    }
    for path, payload in payloads.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        _write_json(path, payload)


def fixture_drift_review_manifest(
    paths: FixtureDriftPaths,
    baseline: FixtureSnapshotManifest,
) -> FixtureSnapshotManifest:
    write_fixture_drift_changed_payloads(paths)
    provider_path = paths.provider_fixture.relative_to(paths.lab_root).as_posix()
    missing_entry = replace(
        next(entry for entry in baseline.entries if entry.path == provider_path),
        path=(paths.lab_root / "tests/fixtures/providers/missing_payload.json")
        .relative_to(paths.lab_root)
        .as_posix(),
    )
    return FixtureSnapshotManifest(
        entries=(
            missing_entry,
            *baseline.entries[1:],
            unsafe_fixture_drift_entry(),
        )
    )


def write_fixture_drift_changed_payloads(paths: FixtureDriftPaths) -> None:
    _write_json(
        paths.benchmark_fixture,
        {"schema_version": 1, "inputs": [{"provider": "mock", "operation": "embed"}]},
    )
    _write_json(
        paths.scenario_fixture,
        {
            "schema_version": 2,
            "id": "demo-scenario",
            "description": "Fixture drift walkthrough schema change.",
        },
    )


def unsafe_fixture_drift_entry() -> FixtureSnapshotEntry:
    return FixtureSnapshotEntry(
        path="../private/provider-secret.json",
        sha256="sha256:" + "0" * 64,
        size_bytes=1,
        fixture_kind="provider-payload-fixture",
        fixture_schema_version=1,
    )


def write_fixture_drift_review_outputs(
    paths: FixtureDriftPaths,
    review_manifest: FixtureSnapshotManifest,
    review_report: FixtureSnapshotReport,
) -> None:
    _write_json(paths.review_manifest, review_manifest.to_dict())
    _write_json(paths.review_json, review_report.to_dict())
    paths.review_markdown.write_text(review_report.to_markdown() + "\n", encoding="utf-8")


def fixture_drift_intended_report(
    paths: FixtureDriftPaths,
    baseline: FixtureSnapshotManifest,
) -> FixtureSnapshotReport:
    changed_paths = fixture_drift_changed_paths(paths)
    intended_manifest = FixtureSnapshotManifest(
        entries=tuple(
            replace(entry, review_status="intended-update")
            if entry.path in changed_paths
            else entry
            for entry in baseline.entries
        )
    )
    return validate_fixture_snapshot_manifest(
        intended_manifest,
        root=paths.lab_root,
        allow_intended_updates=True,
    )


def fixture_drift_changed_paths(paths: FixtureDriftPaths) -> set[str]:
    return {
        paths.benchmark_fixture.relative_to(paths.lab_root).as_posix(),
        paths.scenario_fixture.relative_to(paths.lab_root).as_posix(),
    }


def write_fixture_drift_intended_outputs(
    paths: FixtureDriftPaths,
    refreshed: FixtureSnapshotManifest,
    intended_report: FixtureSnapshotReport,
) -> None:
    _write_json(paths.refreshed_manifest, refreshed.to_dict())
    _write_json(paths.intended_json, intended_report.to_dict())


def fixture_drift_summary_report(run: FixtureDriftRun) -> JSONDict:
    return {
        "schema_version": 1,
        "safe_to_attach": True,
        "baseline_passed": run.baseline_report.passed,
        "review_passed": run.review_report.passed,
        "intended_update_passed": run.intended_report.passed,
        "review_summary": run.review_report.summary,
        "review_statuses": [issue.status for issue in run.review_report.issues],
        "managed_fixture_kinds": sorted({entry.fixture_kind for entry in run.baseline.entries}),
        "approved_update_path": list(FIXTURE_DRIFT_APPROVED_UPDATE_PATH),
        "claim_boundary": FIXTURE_DRIFT_CLAIM_BOUNDARY,
    }


def write_fixture_drift_summary(paths: FixtureDriftPaths, report: JSONDict) -> None:
    _write_json(paths.summary, report)


def fixture_drift_result(paths: FixtureDriftPaths, report: JSONDict) -> JSONDict:
    return {
        "status": "passed",
        "provider": "fixture-snapshot-manager",
        "safe_to_attach": True,
        "summary": FIXTURE_DRIFT_SUMMARY,
        "report": report,
        "artifact_paths": {
            "summary": str(paths.summary),
            "baseline_manifest": str(paths.baseline_manifest),
            "review_manifest": str(paths.review_manifest),
            "review_json": str(paths.review_json),
            "review_markdown": str(paths.review_markdown),
            "intended_update_json": str(paths.intended_json),
            "refreshed_manifest": str(paths.refreshed_manifest),
        },
        "first_triage_step": FIXTURE_DRIFT_FIRST_TRIAGE_STEP,
        "claim_boundary": report["claim_boundary"],
    }

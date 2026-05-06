from __future__ import annotations

import subprocess
import sys
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlparse

import pytest

ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT / "site"


class _ImageSourceParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.sources: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag != "img":
            return
        values = dict(attrs)
        source = values.get("src")
        if source:
            self.sources.append(source)


def _resolved_site_path(page: Path, source: str) -> Path | None:
    parsed = urlparse(source)
    if parsed.scheme or parsed.netloc or parsed.path.startswith("data:"):
        return None
    if parsed.path.startswith("/worldforge/"):
        return SITE / unquote(parsed.path.removeprefix("/worldforge/"))
    if parsed.path.startswith("/"):
        return None
    return (page.parent / unquote(parsed.path)).resolve()


def test_built_docs_image_sources_resolve_to_site_files() -> None:
    pytest.importorskip("mkdocs")
    subprocess.run(
        [sys.executable, "-m", "mkdocs", "build", "--strict"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )

    missing: list[str] = []
    for page in SITE.rglob("*.html"):
        parser = _ImageSourceParser()
        parser.feed(page.read_text(encoding="utf-8"))
        for source in parser.sources:
            resolved = _resolved_site_path(page, source)
            if resolved is None:
                continue
            if not resolved.is_relative_to(SITE):
                missing.append(f"{page.relative_to(SITE)} -> {source} escapes site/")
            elif not resolved.exists():
                missing.append(f"{page.relative_to(SITE)} -> {source}")

    assert missing == []


def test_health_readiness_runbook_documents_required_operational_signals() -> None:
    operations = (ROOT / "docs/src/operations.md").read_text(encoding="utf-8")
    playbooks = (ROOT / "docs/src/playbooks.md").read_text(encoding="utf-8")

    for status in ("ready", "provider_unconfigured", "provider_unhealthy"):
        assert status in operations
        assert status in playbooks

    required_header = (
        "| State | Symptom | Likely cause | First command | Expected signal | Escalation point |"
    )
    assert required_header in playbooks
    for incident in (
        "process live",
        "provider unconfigured",
        "provider unhealthy",
        "upstream degraded",
        "workflow failing",
    ):
        assert incident in playbooks

    assert "WorldForge does not own upstream SLA" in playbooks
    assert "Alert routing, paging policy" in playbooks


def test_persistence_adapter_adr_documents_host_owned_boundary() -> None:
    adr = (ROOT / "docs/src/adr/0001-persistence-adapter-boundary.md").read_text(encoding="utf-8")
    operations = (ROOT / "docs/src/operations.md").read_text(encoding="utf-8")
    architecture = (ROOT / "docs/src/architecture.md").read_text(encoding="utf-8")
    playbooks = (ROOT / "docs/src/playbooks.md").read_text(encoding="utf-8")

    assert "Status: Accepted" in adr
    assert "WorldPersistenceAdapter" in adr
    assert "must not add a database dependency to the base package" in adr
    assert "Current local JSON behavior remains authoritative and unchanged" in adr

    for required_topic in (
        "Locking",
        "Migrations",
        "Backup and restore",
        "Retention",
        "Schema versioning",
        "Failure recovery",
    ):
        assert f"**{required_topic}:**" in adr

    for rejected in (
        "Replace Local JSON With SQLite",
        "Add Lock Files Around The Current Store",
        "Add A Generic Database URL Setting",
        "Move Persistence Entirely Out Of WorldForge",
    ):
        assert rejected in adr

    for doc in (operations, architecture, playbooks):
        assert "0001-persistence-adapter-boundary.md" in doc


def test_observability_roadmap_tracker_records_completion() -> None:
    roadmap = (ROOT / "docs/src/provider-platform-roadmap.md").read_text(encoding="utf-8")
    operations = (ROOT / "docs/src/operations.md").read_text(encoding="utf-8")
    playbooks = (ROOT / "docs/src/playbooks.md").read_text(encoding="utf-8")
    service_host = (ROOT / "examples/hosts/service/app.py").read_text(encoding="utf-8")

    assert "Track status: complete for [#51]" in roadmap
    for child in ("WF-OBS-001", "WF-OBS-002", "WF-OBS-003", "WF-OBS-004", "WF-OBS-005"):
        assert child in roadmap

    for completed_criterion in (
        "Event fields are JSON-native and sanitized before sink consumption.",
        "Importing `worldforge` does not import OpenTelemetry.",
        "Metrics bridge is optional and has bounded labels.",
        "Logs can be correlated to run manifests by `run_id`.",
        "Docs avoid claiming WorldForge owns upstream SLAs.",
    ):
        assert f"- [x] {completed_criterion}" in roadmap

    for signal in (
        "ProviderEvent",
        "RunJsonLogSink",
        "ProviderMetricsExporterSink",
        "OpenTelemetryProviderEventSink",
        "ready",
        "provider_unconfigured",
        "provider_unhealthy",
    ):
        assert signal in operations

    assert "WorldForge does not own upstream SLA" in playbooks
    assert "JsonLoggerSink" in service_host
    assert "request_id" in service_host


def test_provider_platform_foundation_roadmap_tracker_records_completion() -> None:
    roadmap = (ROOT / "docs/src/provider-platform-roadmap.md").read_text(encoding="utf-8")
    authoring = (ROOT / "docs/src/provider-authoring-guide.md").read_text(encoding="utf-8")
    provider_index = (ROOT / "docs/src/providers/README.md").read_text(encoding="utf-8")
    operations = (ROOT / "docs/src/operations.md").read_text(encoding="utf-8")
    playbooks = (ROOT / "docs/src/playbooks.md").read_text(encoding="utf-8")

    runtime_manifests = {
        path.stem for path in (ROOT / "src/worldforge/providers/runtime_manifests").glob("*.json")
    }

    assert "Track status: complete for [#47]" in roadmap
    for child in ("WF-PROV-001", "WF-PROV-002", "WF-PROV-003", "WF-PROV-004", "WF-PROV-005"):
        assert child in roadmap

    for completed_criterion in (
        "Promotion rules cover all current statuses: `scaffold`, `experimental`, `beta`, `stable`.",
        "Rules explain when to change provider profile metadata and generated catalog docs.",
        "Manifest schema is documented and validated by tests.",
        "Manifests exist for `leworldmodel`, `lerobot`, `gr00t`, `cosmos`, and `runway`.",
        "Each capability has a reusable conformance helper.",
        "The helpers do not use bare Python `assert` statements.",
        "Live smoke commands can emit `run_manifest.json`.",
        "Manifest validation rejects secret-like metadata.",
        "Live tests skip with clear reasons when runtime/env is missing.",
        "Prepared-host commands are documented for each real provider.",
        "Live-smoke evidence can be attached to release notes or provider issues.",
    ):
        assert f"- [x] {completed_criterion}" in roadmap

    for status in ("`scaffold`", "`experimental`", "`beta`", "`stable`"):
        assert status in authoring

    for helper in (
        "assert_predict_conformance",
        "assert_generate_conformance",
        "assert_transfer_conformance",
        "assert_reason_conformance",
        "assert_embed_conformance",
        "assert_score_conformance",
        "assert_policy_conformance",
        "assert_provider_events_conform",
    ):
        assert helper in authoring

    assert {"leworldmodel", "lerobot", "gr00t", "cosmos", "runway"} <= runtime_manifests
    assert "`src/worldforge/providers/runtime_manifests/`" in provider_index
    assert "Optional live smoke entrypoints accept `--run-manifest <path>`" in provider_index

    for marker in ("live", "network", "credentialed", "gpu", "robotics", "provider_profile"):
        assert marker in operations
        assert marker in playbooks


def test_reference_host_roadmap_tracker_records_completion() -> None:
    roadmap = (ROOT / "docs/src/provider-platform-roadmap.md").read_text(encoding="utf-8")
    examples = (ROOT / "docs/src/examples.md").read_text(encoding="utf-8")

    host_paths = (
        ROOT / "examples/hosts/batch-eval/app.py",
        ROOT / "examples/hosts/service/app.py",
        ROOT / "examples/hosts/robotics-operator/app.py",
    )
    for host_path in host_paths:
        assert host_path.exists()

    assert "Track status: complete for [#50]" in roadmap
    for child in ("WF-HOST-001", "WF-HOST-002", "WF-HOST-003"):
        assert child in roadmap

    for completed_criterion in (
        "Host can run `mock` eval and benchmark jobs in a clean checkout.",
        "Host writes run workspace artifacts and exits non-zero on budget violations.",
        "Service host runs with only optional example dependencies.",
        "Health/readiness distinguish framework alive, provider configured, and provider healthy.",
        "The default mode is non-mutating and does not talk to robot controllers.",
        (
            "Controller execution hook is disabled unless the host supplies an explicit "
            "implementation."
        ),
        "Operator approval and dry-run artifacts are recorded.",
    ):
        assert f"- [x] {completed_criterion}" in roadmap

    for signal in (
        "batch-eval-host",
        ".worldforge/batch-eval/runs/<run-id>/",
        "service-host",
        "GET /readyz",
        "request id",
        "robotics-operator-host",
        "Controller execution remains disabled",
        "WorldForge only",
        "does not certify robot",
    ):
        assert signal in examples


def test_production_harness_roadmap_tracker_records_completion() -> None:
    roadmap = (ROOT / "docs/src/provider-platform-roadmap.md").read_text(encoding="utf-8")
    harness = (ROOT / "docs/src/theworldharness.md").read_text(encoding="utf-8")

    assert "Track status: complete for [#49]" in roadmap
    for child in (
        "WF-HARNESS-001",
        "WF-HARNESS-002",
        "WF-HARNESS-003",
        "WF-HARNESS-004",
        "WF-HARNESS-005",
    ):
        assert child in roadmap

    for completed_criterion in (
        "Harness and CLI flows write the same run layout.",
        "Run IDs are file-safe and sortable.",
        "Exported artifacts can be attached to issues without leaking secrets.",
        "Non-TUI metadata command exposes the same provider readiness data as JSON.",
        "A failed run still writes enough manifest data to reproduce the command.",
        "Comparison refuses incompatible report types with a clear error.",
        "Workbench can run against `mock` in a clean checkout.",
        "Failures are actionable enough to paste into GitHub issues.",
    ):
        assert f"- [x] {completed_criterion}" in roadmap

    for signal in (
        ".worldforge/runs/<run-id>/",
        "run_manifest.json",
        "logs/provider-events.jsonl",
        "results/inspector.json",
        "worldforge harness --connectors --format json",
        "worldforge provider workbench mock",
        "worldforge runs compare",
        "worldforge runs cleanup --keep 20",
    ):
        assert signal in harness


def test_real_provider_roadmap_tracker_records_completion() -> None:
    roadmap = (ROOT / "docs/src/provider-platform-roadmap.md").read_text(encoding="utf-8")
    provider_index = (ROOT / "docs/src/providers/README.md").read_text(encoding="utf-8")
    selection = (ROOT / "docs/src/provider-selection-rfc.md").read_text(encoding="utf-8")
    showcase = (ROOT / "docs/src/robotics-showcase.md").read_text(encoding="utf-8")

    provider_pages = {
        name: (ROOT / f"docs/src/providers/{name}.md").read_text(encoding="utf-8")
        for name in (
            "leworldmodel",
            "lerobot",
            "gr00t",
            "cosmos",
            "runway",
            "jepa",
            "jepa-wms",
            "genie",
        )
    }
    runtime_manifests = {
        path.stem for path in (ROOT / "src/worldforge/providers/runtime_manifests").glob("*.json")
    }

    assert "Track status: complete for [#48]" in roadmap
    for child in (
        "WF-LWM-001",
        "WF-LWM-002",
        "WF-LEROBOT-001",
        "WF-LEROBOT-002",
        "WF-GROOT-001",
        "WF-COSMOS-001",
        "WF-RUNWAY-001",
        "WF-JEPAWMS-001",
        "WF-JEPA-001",
        "WF-GENIE-001",
        "WF-PROVIDER-SELECT-001",
    ):
        assert child in roadmap

    for status_row in (
        "| [`leworldmodel`](./leworldmodel.md) | `stable` | `score` |",
        "| [`lerobot`](./lerobot.md) | `stable` | `policy` |",
        "| [`gr00t`](./gr00t.md) | `beta` | `policy` |",
        "| [`jepa`](./jepa.md) | `experimental` | `score` |",
        "| [`genie`](./genie.md) | `scaffold` | scaffold |",
    ):
        assert status_row in provider_index

    assert {"leworldmodel", "lerobot", "gr00t", "cosmos", "runway", "jepa"} <= runtime_manifests

    for signal in (
        "stable_worldmodel.policy.AutoCostModel",
        "CPU fallback",
        "score direction",
        "PushT",
        "translator_contract",
        "remote PolicyClient",
        "unreachable policy server",
        "failed tasks",
        "signed URL",
        "facebookresearch/jepa-wms",
        "Status: scaffold",
        "Decision date: 2026-05-01",
    ):
        assert signal in roadmap or any(signal in page for page in provider_pages.values())

    for provider_name in provider_pages:
        assert f"[`{provider_name}`]" in provider_index

    assert 'torch.hub.load("facebookresearch/jepa-wms", model_name)' in selection
    assert "Genie Issue Outline" in selection
    assert "worldforge.smoke.pusht_showcase_inputs" in showcase
    assert "host must provide" in showcase


def test_provider_cohort_selection_record_covers_issue_130_contract() -> None:
    record = (ROOT / "docs/src/provider-cohort-selection.md").read_text(encoding="utf-8")
    roadmap = (ROOT / "docs/src/roadmap.md").read_text(encoding="utf-8")
    continuation = (ROOT / "docs/src/roadmap-continuation.md").read_text(encoding="utf-8")
    summary = (ROOT / "docs/src/SUMMARY.md").read_text(encoding="utf-8")
    mkdocs = (ROOT / "mkdocs.yml").read_text(encoding="utf-8")
    provider_index = (ROOT / "docs/src/providers/README.md").read_text(encoding="utf-8")

    assert "Issue: [#130]" in record
    assert "provider-platform-roadmap.md#provider-prioritization-rubric" in record
    assert "provider-authoring-guide.md#step-3-apply-the-promotion-gate" in record
    assert "## Candidate Scorecard" in record

    for candidate in (
        "JEPA-WMS and public `jepa` score path",
        "Cosmos and Runway remote media retention",
        "Nano World Model score candidate",
        "Spatial/3D scene provider family",
        "Genie interactive-world generation",
        "Additional remote video APIs",
        "Simulator bridges",
        "New embodied policy stacks beyond LeRobot and GR00T",
    ):
        assert candidate in record

    for selected in ("#133", "#134", "#158"):
        assert selected in record

    assert "The selected cohort contains three active work items" in record
    assert "Deferred Candidates" in record
    assert "generated provider catalog remains unchanged" in record
    assert "Provider Cohort Selection Record" in roadmap
    assert "Provider Cohort Selection Record" in continuation
    assert "[Provider Cohort Selection Record](./provider-cohort-selection.md)" in summary
    assert "Provider Cohort Selection Record: provider-cohort-selection.md" in mkdocs
    assert "nanowm" not in provider_index


def test_spatial_scene_artifact_boundary_covers_issue_138_contract() -> None:
    boundary = (ROOT / "docs/src/spatial-scene-artifact-boundary.md").read_text(encoding="utf-8")
    summary = (ROOT / "docs/src/SUMMARY.md").read_text(encoding="utf-8")
    mkdocs = (ROOT / "mkdocs.yml").read_text(encoding="utf-8")
    selection = (ROOT / "docs/src/provider-selection-rfc.md").read_text(encoding="utf-8")
    cohort = (ROOT / "docs/src/provider-cohort-selection.md").read_text(encoding="utf-8")
    continuation = (ROOT / "docs/src/roadmap-continuation.md").read_text(encoding="utf-8")

    assert "Issue: [#138]" in boundary
    assert "Status: design accepted; provider implementation deferred." in boundary
    assert "OpenLRM-style local 3D reconstruction or generation runtime" in boundary
    assert "World Labs Marble-style hosted spatial world products" in boundary
    assert "Generated videos are media artifacts" in boundary
    assert "future `generate` surface" in boundary
    assert "worldforge.scene_artifact" in boundary
    assert "coordinate_frame" in boundary
    assert "host-local absolute paths" in boundary
    assert "does not prove physical validity" in boundary
    assert "Follow-Up Contract For #143" in boundary

    assert "[Spatial Scene Artifact Boundary](./spatial-scene-artifact-boundary.md)" in summary
    assert "Spatial Scene Artifact Boundary: spatial-scene-artifact-boundary.md" in mkdocs
    assert "Spatial Scene Artifact Boundary" in selection
    assert "Spatial Scene Artifact Boundary" in cohort
    assert "Spatial Scene Artifact Boundary" in continuation


def test_live_smoke_evidence_registry_docs_cover_issue_144_contract() -> None:
    registry_doc = (ROOT / "docs/src/live-smoke-evidence.md").read_text(encoding="utf-8")
    registry_json = (ROOT / "docs/src/live-smoke-evidence.json").read_text(encoding="utf-8")
    provider_index = (ROOT / "docs/src/providers/README.md").read_text(encoding="utf-8")
    operations = (ROOT / "docs/src/operations.md").read_text(encoding="utf-8")
    summary = (ROOT / "docs/src/SUMMARY.md").read_text(encoding="utf-8")
    mkdocs = (ROOT / "mkdocs.yml").read_text(encoding="utf-8")

    assert "Issue: [#144]" in registry_doc
    assert "skipped_missing_runtime" in registry_doc
    assert "skipped_missing_credentials" in registry_doc
    assert "validate_live_smoke_registry" in registry_doc
    assert "signed artifact URLs" in registry_doc
    assert "It is not a" in registry_doc
    assert "benchmark" in registry_doc
    assert "skipped_missing_credentials" in registry_json
    assert "Live Smoke Evidence Registry" in provider_index
    assert "--live-smoke-registry docs/src/live-smoke-evidence.json" in operations
    assert "[Live Smoke Evidence Registry](./live-smoke-evidence.md)" in summary
    assert "Live Smoke Evidence Registry: live-smoke-evidence.md" in mkdocs


def test_claim_to_evidence_map_covers_issue_140_contract() -> None:
    claim_map = (ROOT / "docs/src/claim-evidence-map.md").read_text(encoding="utf-8")
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    continuation = (ROOT / "docs/src/roadmap-continuation.md").read_text(encoding="utf-8")
    summary = (ROOT / "docs/src/SUMMARY.md").read_text(encoding="utf-8")
    mkdocs = (ROOT / "mkdocs.yml").read_text(encoding="utf-8")

    assert "Issue: [#140]" in claim_map
    for evidence_class in (
        "`checkout-tested`",
        "`fixture-tested`",
        "`prepared-host smoke-tested`",
        "`release-gated`",
        "`deferred`",
        "`unsupported`",
    ):
        assert evidence_class in claim_map

    for capability in (
        "`predict`",
        "`score`",
        "`policy`",
        "`generate`",
        "`transfer`",
        "`reason`",
        "`embed`",
        "`plan`",
    ):
        assert capability in claim_map

    for non_claim in (
        "Physical fidelity",
        "robot safety certification",
        "Upstream provider SLA",
        "Training LeWorldModel",
        "Service-grade persistence",
    ):
        assert non_claim in claim_map

    for route in (
        "uv run worldforge benchmark --preset mock-smoke",
        "scripts/robotics-showcase --json-only --no-tui --no-rerun",
        "uv run python scripts/generate_release_evidence.py",
        "docs/src/live-smoke-evidence.json",
    ):
        assert route in claim_map

    assert "claim-to-evidence map" in readme
    assert "[Claim-To-Evidence Map](./claim-evidence-map.md)" in summary
    assert "Claim-To-Evidence Map: claim-evidence-map.md" in mkdocs
    assert "- [x] Every README-level capability claim" in continuation


def test_evidence_bundle_docs_cover_issue_145_contract() -> None:
    evaluation = (ROOT / "docs/src/evaluation.md").read_text(encoding="utf-8")
    operations = (ROOT / "docs/src/operations.md").read_text(encoding="utf-8")
    playbooks = (ROOT / "docs/src/playbooks.md").read_text(encoding="utf-8")
    claim_map = (ROOT / "docs/src/claim-evidence-map.md").read_text(encoding="utf-8")
    continuation = (ROOT / "docs/src/roadmap-continuation.md").read_text(encoding="utf-8")

    for doc in (evaluation, operations, playbooks, claim_map):
        assert "scripts/generate_evidence_bundle.py" in doc

    for signal in (
        "evidence_manifest.json",
        "summary.md",
        "safe_to_attach",
        "SHA-256",
        "secret-like",
        "host-local",
    ):
        assert signal in evaluation or signal in operations

    assert "--artifact .worldforge/evidence-bundles" in operations
    assert "generated evidence bundles" in playbooks
    assert "tests/test_evidence_bundle.py" in claim_map
    assert "- [x] Bundle generation succeeds" in continuation


def test_issue_bundle_docs_cover_issue_148_contract() -> None:
    evaluation = (ROOT / "docs/src/evaluation.md").read_text(encoding="utf-8")
    operations = (ROOT / "docs/src/operations.md").read_text(encoding="utf-8")
    playbooks = (ROOT / "docs/src/playbooks.md").read_text(encoding="utf-8")
    continuation = (ROOT / "docs/src/roadmap-continuation.md").read_text(encoding="utf-8")
    changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")

    for signal in (
        "worldforge runs bundle <run-id>",
        "issue.md",
        "expected signal",
        "observed failure",
        "safe_to_attach",
        "first triage step",
        "local_only",
    ):
        assert signal in evaluation or signal in operations or signal in playbooks

    assert "issue-ready bundles" in changelog
    assert "- [x] Export succeeds for successful, failed, skipped, and cancelled mock runs" in (
        continuation
    )
    assert "- [x] Unsafe metadata causes a clear error or local-only marking" in continuation


def test_harness_run_history_docs_cover_issue_149_contract() -> None:
    harness = (ROOT / "docs/src/theworldharness.md").read_text(encoding="utf-8")
    operations = (ROOT / "docs/src/operations.md").read_text(encoding="utf-8")
    playbooks = (ROOT / "docs/src/playbooks.md").read_text(encoding="utf-8")
    continuation = (ROOT / "docs/src/roadmap-continuation.md").read_text(encoding="utf-8")
    changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")

    for signal in (
        "worldforge harness --runs",
        "--artifact-type json",
        "sanitized rerun command",
        "issue-bundle",
        "provider, capability, status, created date, and safe artifact type",
    ):
        assert signal in harness or signal in operations or signal in playbooks

    assert "Runs screen" in harness
    assert "preserved-run history actions" in changelog
    assert "- [x] Harness can filter and open preserved runs without optional model runtimes" in (
        continuation
    )
    assert "- [x] Rerun commands are generated from sanitized manifests" in continuation


def test_benchmark_budget_calibration_docs_cover_issue_146_contract() -> None:
    benchmarking = (ROOT / "docs/src/benchmarking.md").read_text(encoding="utf-8")
    operations = (ROOT / "docs/src/operations.md").read_text(encoding="utf-8")
    playbooks = (ROOT / "docs/src/playbooks.md").read_text(encoding="utf-8")
    claim_map = (ROOT / "docs/src/claim-evidence-map.md").read_text(encoding="utf-8")
    continuation = (ROOT / "docs/src/roadmap-continuation.md").read_text(encoding="utf-8")
    changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")

    for doc in (benchmarking, operations, playbooks, claim_map):
        assert "scripts/calibrate_benchmark_budgets.py" in doc

    for signal in (
        "candidate-budgets.json",
        "budget-calibration.md",
        "source report digests",
        "old threshold",
        "candidate threshold",
        "observed baseline",
        "rationale",
    ):
        assert signal in benchmarking or signal in operations

    assert "Threshold loosening requires human review" in benchmarking
    assert "does not weaken existing release gates automatically" in operations
    assert "tests/test_benchmark_budget_calibration.py" in claim_map
    assert "benchmark budget calibration artifacts" in changelog
    assert "- [x] Candidate budget generation records source report digests" in continuation
    assert "- [x] Existing budget failure behavior remains non-zero" in continuation


def test_evaluation_failure_gallery_docs_cover_issue_147_contract() -> None:
    evaluation = (ROOT / "docs/src/evaluation.md").read_text(encoding="utf-8")
    python_api = (ROOT / "docs/src/api/python.md").read_text(encoding="utf-8")
    claim_map = (ROOT / "docs/src/claim-evidence-map.md").read_text(encoding="utf-8")
    continuation = (ROOT / "docs/src/roadmap-continuation.md").read_text(encoding="utf-8")
    changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")

    for signal in (
        "failure_gallery.json",
        "failure_gallery.md",
        "fixture id",
        "expected contract note",
        "secret-shaped values are redacted",
        "tensor-like arrays are summarized",
        "not provider quality ranking",
    ):
        assert signal in evaluation

    assert "report.failure_gallery()" in python_api
    assert "tests/test_evaluation_failure_gallery.py" in claim_map
    assert "sanitized evaluation failure galleries" in changelog
    assert "- [x] Failed evaluation reports include representative cases" in continuation
    assert "- [x] Reports avoid raw secrets" in continuation


def test_cross_provider_comparison_docs_cover_issue_150_contract() -> None:
    benchmarking = (ROOT / "docs/src/benchmarking.md").read_text(encoding="utf-8")
    harness = (ROOT / "docs/src/theworldharness.md").read_text(encoding="utf-8")
    claim_map = (ROOT / "docs/src/claim-evidence-map.md").read_text(encoding="utf-8")
    continuation = (ROOT / "docs/src/roadmap-continuation.md").read_text(encoding="utf-8")
    changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")

    for signal in (
        "worldforge runs compare",
        "fixture digest",
        "budget status",
        "suite version",
        "capability mismatch",
        "claim boundary",
        "missing evidence",
        "skip reasons",
        "not a public leaderboard",
    ):
        assert signal in benchmarking or signal in harness

    assert "tests/test_harness_report_compare.py" in claim_map
    assert "cross-provider run comparisons" in changelog
    assert "- [x] Compatible runs compare with provenance" in continuation
    assert (
        "- [x] Harness and CLI comparison paths use the same underlying report model"
        in continuation
    )


def test_adapter_workbench_docs_cover_issue_141_contract() -> None:
    harness = (ROOT / "docs/src/theworldharness.md").read_text(encoding="utf-8")
    authoring = (ROOT / "docs/src/provider-authoring-guide.md").read_text(encoding="utf-8")
    continuation = (ROOT / "docs/src/roadmap-continuation.md").read_text(encoding="utf-8")
    changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")

    for signal in (
        "worldforge harness --flow workbench",
        "worldforge provider workbench jepa-wms",
        "promotion evidence",
        "runtime manifest status",
        "safe artifact references",
        "validation commands",
        "missing evidence by promotion status",
        "jepa_wms_*.json",
    ):
        assert signal in harness or signal in authoring

    assert "adapter author workbench flow" in changelog
    assert "- [x] Workbench can run against `mock`" in continuation
    assert "- [x] TUI and CLI workbench views use the same non-Textual flow logic" in continuation


def test_scaffold_provider_docs_cover_issue_142_contract() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    agents = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
    playbooks = (ROOT / "docs/src/playbooks.md").read_text(encoding="utf-8")
    authoring = (ROOT / "docs/src/provider-authoring-guide.md").read_text(encoding="utf-8")
    continuation = (ROOT / "docs/src/roadmap-continuation.md").read_text(encoding="utf-8")
    changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")

    for signal in (
        "--implementation-status scaffold",
        "runtime manifest stubs",
        "workbench checklists",
        "acme-wm.json.stub",
        "not loadable runtime",
        "uv run pytest tests/test_provider_runtime_manifests.py",
        "validation commands",
    ):
        assert signal in readme or signal in agents or signal in playbooks or signal in authoring

    assert "fuller fail-closed contract pack" in changelog
    assert "- [x] Scaffold output includes tests for unsupported capability calls" in continuation
    assert "- [x] Generated manifest stubs are clearly marked incomplete" in continuation


def test_genie_scaffold_docs_record_runtime_contract_defer_decision() -> None:
    provider_page = (ROOT / "docs/src/providers/genie.md").read_text(encoding="utf-8")
    provider_index = (ROOT / "docs/src/providers/README.md").read_text(encoding="utf-8")
    summary = (ROOT / "docs/src/SUMMARY.md").read_text(encoding="utf-8")

    assert "Status: scaffold" in provider_page
    assert "Decision date: 2026-05-01" in provider_page
    assert "Project Genie announcement" in provider_page
    assert "not a supported automation API" in provider_page
    assert "must not present deterministic local surrogate behavior" in provider_page
    assert "Revisit trigger" in provider_page
    assert "fixture-backed parser tests" in provider_page
    assert "sanitized `run_manifest.json`" in provider_page
    assert "| [`genie`](./genie.md) | `scaffold` | scaffold | `GENIE_API_KEY` |" in provider_index
    assert "[Genie](./providers/genie.md)" in summary

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
            "cosmos-policy",
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
        "| [`cosmos-policy`](./cosmos-policy.md) | `beta` | "
        "none (`policy` requires host `action_translator`) |",
        "| [`jepa`](./jepa.md) | `experimental` | `score` |",
        "| [`genie`](./genie.md) | `scaffold` | scaffold |",
    ):
        assert status_row in provider_index

    assert {
        "leworldmodel",
        "lerobot",
        "gr00t",
        "cosmos-policy",
        "cosmos",
        "runway",
        "jepa",
    } <= runtime_manifests

    for signal in (
        "stable_worldmodel.policy.AutoCostModel",
        "CPU fallback",
        "score direction",
        "PushT",
        "translator_contract",
        "Cosmos-Policy /act",
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


def test_cosmos_policy_remote_gpu_runbook_documents_operator_path() -> None:
    provider_doc = (ROOT / "docs/src/providers/cosmos-policy.md").read_text(encoding="utf-8")
    operations = (ROOT / "docs/src/operations.md").read_text(encoding="utf-8")
    playbooks = (ROOT / "docs/src/playbooks.md").read_text(encoding="utf-8")

    for required in (
        "## Remote GPU Runbook",
        "48 GB or larger GPU memory class",
        "WorldForge never starts Cosmos-Policy",
        "ssh -N -L 8777:127.0.0.1:8777",
        "COSMOS_POLICY_BASE_URL=http://127.0.0.1:8777",
        "COSMOS_POLICY_ALLOW_LOCAL_BASE_URL=1",
        "COSMOS_POLICY_ALLOWED_HOSTS",
        "uv run worldforge provider health cosmos-policy",
        "uv run worldforge-smoke-cosmos-policy",
        "--health-only",
        "--policy-info-json /path/to/policy_info.json",
        "--allow-translator-code",
        "status=skipped",
        "status=passed",
        "50 x 14",
        "json_numpy",
        "Hibernate or terminate the GPU host",
    ):
        assert required in provider_doc

    for required in (
        "Cosmos-Policy remote GPU runbook",
        "prefer an SSH",
        "port `8777`",
        "sanitized manifests/replay artifacts",
        "hibernate or terminate the GPU host",
    ):
        assert required in operations

    for required in (
        "Cosmos-Policy remote GPU checklist",
        "48 GB or larger GPU memory class",
        "WorldForge should only see the `/act` endpoint",
        "COSMOS_POLICY_ALLOWED_HOSTS",
        "status=passed",
        "50 x 14",
        "Hibernate or terminate the GPU host",
    ):
        assert required in playbooks


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


def test_reference_host_deployment_recipes_cover_issue_151_contract() -> None:
    examples = (ROOT / "docs/src/examples.md").read_text(encoding="utf-8")
    examples_readme = (ROOT / "examples/README.md").read_text(encoding="utf-8")
    operations = (ROOT / "docs/src/operations.md").read_text(encoding="utf-8")
    playbooks = (ROOT / "docs/src/playbooks.md").read_text(encoding="utf-8")
    continuation = (ROOT / "docs/src/roadmap-continuation.md").read_text(encoding="utf-8")
    changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")

    for recipe in (
        "Stdlib Service Host Recipe",
        "Batch Eval Host Recipe",
        "Robotics Operator Host Recipe",
    ):
        assert recipe in examples

    for signal in (
        "Env template:",
        "Process command:",
        "Readiness command:",
        "Smoke command:",
        "Logging command:",
        "Evidence export command:",
        "Expected success signal:",
        "First failure triage step:",
        "First rollback step:",
        "Owned boundary:",
    ):
        assert signal in examples

    for path in (
        "checkout-safe",
        "prepared-host",
        "credentialed",
        "GPU-bound",
        "robotics-lab",
    ):
        assert path in examples
        assert path in examples_readme or path in operations or path in playbooks

    for command in (
        "uv run python examples/hosts/service/app.py",
        "curl -fsS http://127.0.0.1:8080/readyz",
        "uv run python examples/hosts/batch-eval/app.py",
        "uv run worldforge runs bundle <run-id>",
        "uv run python examples/hosts/robotics-operator/app.py",
        "scripts/robotics-showcase --health-only",
    ):
        assert command in examples or command in playbooks

    for boundary in (
        "deployment, authentication, queueing",
        "durable storage",
        "alerting",
        "uptime",
        "safety certification",
        "does not certify robot",
    ):
        assert boundary in examples or boundary in operations or boundary in playbooks

    assert "No new provider environment variables are introduced" in examples
    assert "`.env.example` stays" in examples
    assert "unchanged" in examples
    assert "reference host deployment recipes" in changelog
    assert "- [x] Each recipe includes command, expected success signal" in continuation
    assert "- [x] Recipes distinguish checkout-safe, prepared-host, credentialed" in continuation
    assert "- [x] `.env.example` changes are tracked only when new provider variables" in (
        continuation
    )
    assert "- [x] Docs do not imply WorldForge owns uptime" in continuation


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


def test_local_state_preflight_docs_cover_issue_153_contract() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    cli = (ROOT / "docs/src/cli.md").read_text(encoding="utf-8")
    operations = (ROOT / "docs/src/operations.md").read_text(encoding="utf-8")
    playbooks = (ROOT / "docs/src/playbooks.md").read_text(encoding="utf-8")
    continuation = (ROOT / "docs/src/roadmap-continuation.md").read_text(encoding="utf-8")
    changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")

    for signal in (
        "worldforge world preflight",
        "corrupted world JSON",
        "traversal-shaped",
        "invalid history entries",
        "object bounding-box coherence",
        "stale run workspaces",
        "unsafe artifact paths",
        "retention pressure",
        "safe to attach",
        "--dry-run",
        ".worldforge/quarantine/",
    ):
        assert signal in cli or signal in operations or signal in playbooks or signal in changelog

    assert "read-only local state diagnostics" in readme
    assert "- [x] Preflight identifies corrupted worlds" in continuation
    assert "- [x] Recovery commands are explicit" in continuation
    assert "- [x] Diagnostics are safe to attach" in continuation


def test_contributor_triage_docs_cover_issue_131_contract() -> None:
    contributing = (ROOT / "CONTRIBUTING.md").read_text(encoding="utf-8")
    docs_contributing = (ROOT / "docs/src/contributing.md").read_text(encoding="utf-8")
    provider_template = (ROOT / ".github/ISSUE_TEMPLATE/provider_adapter.yml").read_text(
        encoding="utf-8"
    )
    eval_template = (ROOT / ".github/ISSUE_TEMPLATE/eval_benchmark.yml").read_text(encoding="utf-8")
    bug_template = (ROOT / ".github/ISSUE_TEMPLATE/bug_report.yml").read_text(encoding="utf-8")
    config_template = (ROOT / ".github/ISSUE_TEMPLATE/config.yml").read_text(encoding="utf-8")
    continuation = (ROOT / "docs/src/roadmap-continuation.md").read_text(encoding="utf-8")
    changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")

    for stream in (
        "stream: provider-evidence",
        "stream: evidence-integrity",
        "stream: ops-authoring",
    ):
        assert stream in contributing
        assert stream in docs_contributing

    for signal in (
        "capability labels",
        "severity: blocking",
        "release: provider-hardening-rc",
        "selection record",
        "promotion gate",
        "release evidence",
        "Security tab",
    ):
        assert signal in contributing or signal in docs_contributing

    assert 'labels: ["provider", "stream: provider-evidence"]' in provider_template
    assert "Triage path" in provider_template
    assert "Promotion and evidence requirements" in provider_template
    assert "Selection record or existing provider-cohort record" in provider_template
    assert 'labels: ["evaluation", "benchmark", "stream: evidence-integrity"]' in eval_template
    assert "Evidence requirements" in eval_template
    assert "Triage stream" in bug_template
    assert "private Security tab" in bug_template
    assert "Report vulnerabilities privately" in config_template
    assert "contributor triage guidance" in changelog
    assert "- [x] Labels exist for the three roadmap streams" in continuation
    assert "- [x] Issue templates route provider runtime work" in continuation
    assert "- [x] Security-sensitive reports still route privately" in continuation


def test_roadmap_expansion_documents_three_streams_and_thirty_issues() -> None:
    expansion = (ROOT / "docs/src/roadmap-expansion.md").read_text(encoding="utf-8")
    roadmap = (ROOT / "docs/src/roadmap.md").read_text(encoding="utf-8")
    summary = (ROOT / "docs/src/SUMMARY.md").read_text(encoding="utf-8")
    mkdocs = (ROOT / "mkdocs.yml").read_text(encoding="utf-8")
    changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")

    assert "Roadmap Expansion" in roadmap
    assert "[Roadmap Expansion](./roadmap-expansion.md)" in summary
    assert "Roadmap Expansion: roadmap-expansion.md" in mkdocs
    assert "30 structured GitHub issues" in changelog
    assert "Nano World Model remains excluded" in expansion

    streams = (
        "Production Grade, Quality, DevX, And Docs",
        "Demos, End-to-End Showcases, And Use Cases",
        "New Features",
    )
    for stream in streams:
        assert stream in expansion

    assert expansion.count("### WF-PQDX-") == 10
    assert expansion.count("### WF-DEMO-") == 10
    assert expansion.count("### WF-FEAT-") == 10
    assert "GitHub issue: pending" not in expansion
    assert expansion.count("https://github.com/AbdelStark/worldforge/issues/") == 30

    for label in (
        "stream: production-quality",
        "stream: demos-showcases",
        "stream: new-features",
    ):
        assert label in expansion

    required_sections = (
        "Problem:",
        "Scope:",
        "Out of scope:",
        "Acceptance criteria:",
        "Validation:",
    )
    for section in required_sections:
        assert expansion.count(section) >= 30


def test_release_readiness_evidence_docs_cover_issue_179_contract() -> None:
    operations = (ROOT / "docs/src/operations.md").read_text(encoding="utf-8")
    playbooks = (ROOT / "docs/src/playbooks.md").read_text(encoding="utf-8")
    release_script = (ROOT / "scripts/generate_release_evidence.py").read_text(encoding="utf-8")

    for signal in (
        "--run-gates",
        ".worldforge/release-evidence/release-evidence.md",
        ".worldforge/release-evidence/release-evidence.json",
        "`passed`, `failed`, or `skipped`",
        "first triage step",
        "`host-owned`",
    ):
        assert signal in operations or signal in playbooks

    for implementation_signal in (
        "class ReleaseGateResult",
        "release_evidence_payload",
        "validation_summary",
        "stdout_tail",
        "stderr_tail",
    ):
        assert implementation_signal in release_script


def test_public_api_stability_docs_cover_issue_180_contract() -> None:
    policy = (ROOT / "docs/src/api-stability.md").read_text(encoding="utf-8")
    python_api = (ROOT / "docs/src/api/python.md").read_text(encoding="utf-8")
    contributing = (ROOT / "docs/src/contributing.md").read_text(encoding="utf-8")
    summary = (ROOT / "docs/src/SUMMARY.md").read_text(encoding="utf-8")
    mkdocs = (ROOT / "mkdocs.yml").read_text(encoding="utf-8")
    changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")

    for tier in ("Stable", "Provisional", "Experimental", "Internal"):
        assert f"| {tier} |" in policy

    for signal in (
        "WorldForgeError",
        "ProviderError",
        "CLI command or flag",
        "provider capability",
        "artifact schema",
        "schema version bump",
        "changelog entry",
        "earliest release where removal may happen",
        "truthful capability advertising",
    ):
        assert signal in policy

    assert "[Public API Stability](../api-stability.md)" in python_api
    assert "[Public API Stability](./api-stability.md)" in contributing
    assert "[Public API Stability](./api-stability.md)" in summary
    assert "Public API Stability: api-stability.md" in mkdocs
    assert "public API stability and deprecation policy" in changelog


def test_redaction_corpus_docs_cover_issue_181_contract() -> None:
    security = (ROOT / "docs/src/security.md").read_text(encoding="utf-8")
    corpus = (ROOT / "tests/fixtures/redaction/provider_event_corpus.json").read_text(
        encoding="utf-8"
    )
    redaction_tests = (ROOT / "tests/test_redaction_corpus.py").read_text(encoding="utf-8")

    assert "tests/fixtures/redaction/provider_event_corpus.json" in security
    for sink in (
        "provider event sinks",
        "run manifests",
        "issue bundles",
        "Rerun layers",
        "metrics exporters",
        "OpenTelemetry bridges",
    ):
        assert sink in security

    for secret_shape in (
        "X-Amz-Signature",
        "Bearer wf-bearer-secret",
        "Authorization",
        "api_key",
        "token=wf-request-secret",
    ):
        assert secret_shape in corpus

    for covered_path in (
        "JsonLoggerSink",
        "RunJsonLogSink",
        "provider_event_metric_labels",
        "provider_event_span_attributes",
        "OpenTelemetryProviderEventSink",
        "RerunEventSink",
        "build_run_manifest",
        "validate_run_manifest",
        "generate_issue_bundle",
    ):
        assert covered_path in redaction_tests


def test_troubleshooting_matrix_docs_cover_issue_182_contract() -> None:
    playbooks = (ROOT / "docs/src/playbooks.md").read_text(encoding="utf-8")

    assert "### 4a. Troubleshoot Error Families" in playbooks
    assert (
        "| Error family | Common symptom | Likely owner | First command | "
        "Expected artifact or signal | First triage step |"
    ) in playbooks

    for error_family in (
        "`WorldForgeError`",
        "`WorldStateError`",
        "`ProviderError`",
        "`AssertionError` from `worldforge.testing`",
    ):
        assert error_family in playbooks

    for command in (
        "uv run worldforge doctor --registered-only",
        "uv run worldforge world preflight --state-dir .worldforge/worlds",
        "uv run worldforge provider info <provider>",
        "uv run pytest tests/test_provider_contracts.py -q",
        "uv run worldforge benchmark --preset mock-smoke",
        "uv run mkdocs build --strict",
        "worldforge runs bundle <run-id>",
        "scripts/generate_evidence_bundle.py",
    ):
        assert command in playbooks

    for signal in (
        "safe_to_attach",
        "run_manifest.json",
        "budget status",
        "private Security tab",
        "do not replace helper checks with bare `assert`",
    ):
        assert signal in playbooks


def test_docs_command_drift_checker_docs_cover_issue_183_contract() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    agents = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
    quality = (ROOT / "docs/src/quality.md").read_text(encoding="utf-8")
    operations = (ROOT / "docs/src/operations.md").read_text(encoding="utf-8")
    playbooks = (ROOT / "docs/src/playbooks.md").read_text(encoding="utf-8")
    release_script = (ROOT / "scripts/generate_release_evidence.py").read_text(encoding="utf-8")
    checker = (ROOT / "scripts/check_docs_commands.py").read_text(encoding="utf-8")
    changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")

    for doc in (readme, agents, quality, operations, playbooks):
        assert "uv run python scripts/check_docs_commands.py" in doc

    assert "Docs command drift" in release_script
    assert "documented-command drift checker" in changelog

    for implementation_signal in (
        "DEFAULT_DOCS",
        "README.md",
        "docs/src/cli.md",
        "docs/src/examples.md",
        "docs/src/operations.md",
        "docs/src/playbooks.md",
        "AGENTS.md",
        "missing_entry_points",
        "stale_commands",
        "undocumented_worldforge_subcommands",
    ):
        assert implementation_signal in checker


def test_core_performance_budget_docs_cover_issue_184_contract() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    agents = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
    quality = (ROOT / "docs/src/quality.md").read_text(encoding="utf-8")
    operations = (ROOT / "docs/src/operations.md").read_text(encoding="utf-8")
    playbooks = (ROOT / "docs/src/playbooks.md").read_text(encoding="utf-8")
    benchmarking = (ROOT / "docs/src/benchmarking.md").read_text(encoding="utf-8")
    release_script = (ROOT / "scripts/generate_release_evidence.py").read_text(encoding="utf-8")
    checker = (ROOT / "scripts/check_core_performance.py").read_text(encoding="utf-8")
    changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")

    for doc in (readme, agents, quality, operations, playbooks):
        assert "uv run python scripts/check_core_performance.py" in doc

    assert "Core performance budgets" in release_script
    assert "checkout-safe core performance budget checker" in changelog

    for doc in (quality, operations, playbooks, benchmarking):
        assert "regression" in doc
        assert "not" in doc
        assert "performance claim" in doc

    for implementation_signal in (
        "DEFAULT_BUDGETS_MS",
        "world_persistence",
        "benchmark_fixture_loading",
        "provider_catalog_diagnostics",
        "evidence_bundle_creation",
        "report_rendering",
        "claim_boundary",
        "--workspace-dir",
        "--budget-file",
    ):
        assert implementation_signal in checker


def test_contributor_bootstrap_doctor_docs_cover_issue_185_contract() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    contributing = (ROOT / "docs/src/contributing.md").read_text(encoding="utf-8")
    cli = (ROOT / "docs/src/cli.md").read_text(encoding="utf-8")
    doctor = (ROOT / "scripts/contributor_doctor.py").read_text(encoding="utf-8")
    changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")

    for doc in (readme, contributing, cli):
        assert "uv run python scripts/contributor_doctor.py --format markdown" in doc

    for signal in (
        "Python 3.13",
        "uv",
        "docs tooling",
        "GitHub CLI auth",
        "optional runtime skip reasons",
        "safe to paste",
    ):
        assert signal in contributing

    for implementation_signal in (
        "run_contributor_doctor",
        "render_contributor_doctor_markdown",
        "overall_status",
        "needs_attention",
        "skipped",
        "gh auth status",
        "stable_worldmodel",
        "lerobot",
        "gr00t",
        "rerun",
    ):
        assert implementation_signal in doctor

    assert "contributor bootstrap doctor" in changelog


def test_artifact_integrity_docs_cover_issue_186_contract() -> None:
    integrity = (ROOT / "docs/src/artifact-integrity.md").read_text(encoding="utf-8")
    operations = (ROOT / "docs/src/operations.md").read_text(encoding="utf-8")
    contributing = (ROOT / "docs/src/contributing.md").read_text(encoding="utf-8")
    summary = (ROOT / "docs/src/SUMMARY.md").read_text(encoding="utf-8")
    mkdocs = (ROOT / "mkdocs.yml").read_text(encoding="utf-8")
    distribution = (ROOT / "scripts/check_distribution.py").read_text(encoding="utf-8")
    changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")

    for signal in (
        "bash scripts/test_package.sh",
        "uv run python scripts/check_distribution.py dist",
        "uvx --from pip-audit pip-audit",
        "shasum -a 256",
        "scripts/generate_evidence_bundle.py",
        "worldforge runs bundle <run-id>",
        "SBOM",
        "build provenance attestation",
        "trusted publishing",
        "signed artifacts",
        "do not claim",
    ):
        assert signal in integrity

    for unsafe in (
        ".env",
        "credentials",
        "signed URL",
        "checkpoint archives",
        "downloaded datasets",
    ):
        assert unsafe in integrity

    assert "[Artifact Integrity](./artifact-integrity.md)" in summary
    assert "Artifact Integrity: artifact-integrity.md" in mkdocs
    assert "[Artifact Integrity](./artifact-integrity.md)" in operations
    assert "[Artifact Integrity](./artifact-integrity.md)" in contributing
    assert "docs/src/artifact-integrity.md" in distribution
    assert "supply-chain and artifact integrity documentation" in changelog


def test_wrapper_portability_docs_cover_issue_187_contract() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    agents = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
    quality = (ROOT / "docs/src/quality.md").read_text(encoding="utf-8")
    operations = (ROOT / "docs/src/operations.md").read_text(encoding="utf-8")
    playbooks = (ROOT / "docs/src/playbooks.md").read_text(encoding="utf-8")
    ci = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    release_script = (ROOT / "scripts/generate_release_evidence.py").read_text(encoding="utf-8")
    checker = (ROOT / "scripts/check_wrapper_portability.py").read_text(encoding="utf-8")
    changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")

    for doc in (readme, agents, quality, operations, playbooks, ci):
        assert "uv run python scripts/check_wrapper_portability.py" in doc

    assert "Wrapper portability" in release_script
    assert "claim Windows" in checker
    assert "support" in checker
    for script in (
        "scripts/robotics-showcase",
        "scripts/lewm-real",
        "scripts/lewm-lerobot-real",
        "scripts/smoke_gr00t_policy.py",
        "scripts/smoke_lerobot_policy.py",
        "scripts/test_package.sh",
    ):
        assert script in checker

    for signal in ("shebang", "executable", "uv run --python 3.13", "host-owned"):
        assert signal in checker or signal in quality or signal in operations

    assert "wrapper portability checker" in changelog


def test_documentation_information_architecture_cover_issue_188_contract() -> None:
    docs_map = (ROOT / "docs/src/docs-map.md").read_text(encoding="utf-8")
    introduction = (ROOT / "docs/src/introduction.md").read_text(encoding="utf-8")
    summary = (ROOT / "docs/src/SUMMARY.md").read_text(encoding="utf-8")
    mkdocs = (ROOT / "mkdocs.yml").read_text(encoding="utf-8")
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")

    for reader in (
        "Provider author",
        "Operator",
        "Evaluator or research user",
        "Release maintainer",
        "Demo or showcase user",
    ):
        assert reader in docs_map

    for route in (
        "Provider Authoring Guide",
        "Operations",
        "Benchmarking",
        "Artifact Integrity",
        "Robotics Replay Showcase",
    ):
        assert route in docs_map

    for roadmap_page in (
        "Roadmap Expansion",
        "Roadmap Continuation",
        "Provider And Platform Roadmap",
    ):
        assert roadmap_page in docs_map

    assert "[Documentation Map](./docs-map.md)" in summary
    assert "Documentation Map: docs-map.md" in mkdocs
    assert "Planning Records:" in mkdocs
    assert "[Documentation Map](./docs-map.md)" in introduction
    assert "Docs Map" in readme
    assert "public docs information architecture" in changelog


def test_demo_showcase_docs_cover_issues_189_to_198_contract() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    cli = (ROOT / "docs/src/cli.md").read_text(encoding="utf-8")
    examples = (ROOT / "docs/src/examples.md").read_text(encoding="utf-8")
    quickstart = (ROOT / "docs/src/quickstart.md").read_text(encoding="utf-8")
    playbooks = (ROOT / "docs/src/playbooks.md").read_text(encoding="utf-8")
    docs_map = (ROOT / "docs/src/docs-map.md").read_text(encoding="utf-8")
    summary = (ROOT / "docs/src/SUMMARY.md").read_text(encoding="utf-8")
    mkdocs = (ROOT / "mkdocs.yml").read_text(encoding="utf-8")
    showcase_docs = (ROOT / "docs/src/demo-showcases.md").read_text(encoding="utf-8")
    cookbook = (ROOT / "docs/src/use-case-cookbook.md").read_text(encoding="utf-8")
    script = (ROOT / "scripts/demo_showcases.py").read_text(encoding="utf-8")
    distribution = (ROOT / "scripts/check_distribution.py").read_text(encoding="utf-8")
    changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")

    assert "[Demo Showcase Workflows](./demo-showcases.md)" in summary
    assert "[Use Case Cookbook](./use-case-cookbook.md)" in summary
    assert "Demo Showcase Workflows: demo-showcases.md" in mkdocs
    assert "Use Case Cookbook: use-case-cookbook.md" in mkdocs
    assert "docs/src/demo-showcases.md" in distribution
    assert "docs/src/use-case-cookbook.md" in distribution
    assert "scripts/demo_showcases.py" in distribution
    assert "checkout-safe demo showcase runner" in changelog

    for doc in (readme, cli, examples, quickstart, playbooks):
        assert "uv run python scripts/demo_showcases.py" in doc

    assert "Demo Showcase Workflows" in docs_map
    assert "Use Case Cookbook" in docs_map
    assert "run_manifest.json" in showcase_docs
    assert "safe_to_attach" in showcase_docs
    assert "First triage step" in showcase_docs
    assert "without installing optional model runtimes" in showcase_docs
    assert cookbook.count("### Recipe") >= 7

    workflows = (
        ("first-run", 189),
        ("diagnostics-issue-bundle", 190),
        ("robotics-replay", 191),
        ("remote-media-dry-run", 192),
        ("adapter-author", 193),
        ("batch-eval", 194),
        ("service-host", 195),
        ("rerun-gallery", 196),
        ("failure-lab", 197),
        ("use-case-cookbook", 198),
    )
    for workflow, issue in workflows:
        assert workflow in script
        assert workflow in showcase_docs
        assert f"#{issue}" in showcase_docs

    for boundary in (
        "no paid API calls",
        "robot hardware",
        "Rerun",
        "scaffold is intentionally fail-closed",
        "physical-fidelity",
    ):
        assert boundary in showcase_docs or boundary in cookbook


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

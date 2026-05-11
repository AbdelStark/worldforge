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


def test_gr00t_live_smoke_docs_cover_remote_policy_contract() -> None:
    provider_doc = (ROOT / "docs/src/providers/gr00t.md").read_text(encoding="utf-8")
    operations = (ROOT / "docs/src/operations.md").read_text(encoding="utf-8")
    playbooks = (ROOT / "docs/src/playbooks.md").read_text(encoding="utf-8")
    evidence = (ROOT / "docs/src/live-smoke-evidence.json").read_text(encoding="utf-8")
    manifest = (ROOT / "src/worldforge/providers/runtime_manifests/gr00t.json").read_text(
        encoding="utf-8"
    )

    for signal in (
        "## Live Smoke Evidence",
        "--health-only",
        "--allow-translator-code",
        "--allow-observation-code",
        "--run-manifest .worldforge/runs/gr00t-health/run_manifest.json",
        "--run-manifest .worldforge/runs/gr00t-live/run_manifest.json",
        "status=skipped",
        "status=passed",
        "ssh -N -L 5555:127.0.0.1:5555",
        "uv run worldforge provider health gr00t",
        "Hibernate or terminate",
    ):
        assert signal in provider_doc or signal in operations or signal in playbooks

    for doc in (operations, playbooks):
        assert "GROOT_POLICY_HOST=127.0.0.1" in doc
        assert "scripts/smoke_gr00t_policy.py" in doc
        assert "status=skipped" in doc
        assert "status=passed" in doc

    assert "--health-only" in evidence
    assert "scripts/smoke_gr00t_policy.py --health-only" in manifest


def test_gr00t_replay_harness_docs_cover_issue_226_contract() -> None:
    harness_doc = (ROOT / "docs/src/theworldharness.md").read_text(encoding="utf-8")
    agents = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
    changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    flows = (ROOT / "src/worldforge/harness/flows.py").read_text(encoding="utf-8")
    fixture = (ROOT / "tests/fixtures/providers/gr00t_policy_replay.json").read_text(
        encoding="utf-8"
    )
    tests = (ROOT / "tests/test_harness_flows.py").read_text(encoding="utf-8")

    for signal in (
        "uv run --extra harness worldforge-harness --flow gr00t",
        "validated_tensors: eef_9d, gripper_position, joint_position",
        "artifacts/gr00t-policy-replay.json",
        "observations, private endpoints, GPU logs, checkpoints",
        "prepared GPU host validates the live GR00T server shape",
    ):
        assert signal in harness_doc

    for implementation_signal in (
        "_run_gr00t_demo",
        "_load_gr00t_replay_artifact",
        "_SavedGrootReplayClient",
        "GrootPolicyClientProvider",
        "eef_9d",
        "gripper_position",
        "joint_position",
    ):
        assert implementation_signal in flows

    for test_signal in (
        "test_harness_runs_gr00t_flow",
        "test_harness_loads_gr00t_replay_artifact",
        "test_harness_rejects_gr00t_replay_missing_named_tensor",
        "test_harness_rejects_gr00t_replay_bad_tensor_shape",
        "test_harness_rejects_unredacted_gr00t_replay_observation",
    ):
        assert test_signal in tests

    assert "GR00T PolicyClient replay" in agents
    assert "checkout-safe GR00T PolicyClient replay flow" in changelog
    assert "raw_actions" in fixture
    assert "observation_summary" in fixture
    assert "checkpoint" not in fixture.lower()


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


def test_custom_evaluation_suite_authoring_docs_cover_issue_201_contract() -> None:
    evaluation = (ROOT / "docs/src/evaluation.md").read_text(encoding="utf-8")
    python_api = (ROOT / "docs/src/api/python.md").read_text(encoding="utf-8")
    changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    expansion = (ROOT / "docs/src/roadmap-expansion.md").read_text(encoding="utf-8")
    suites = (ROOT / "src/worldforge/evaluation/suites.py").read_text(encoding="utf-8")
    evaluation_init = (ROOT / "src/worldforge/evaluation/__init__.py").read_text(encoding="utf-8")
    root_init = (ROOT / "src/worldforge/__init__.py").read_text(encoding="utf-8")
    example = (ROOT / "examples/custom_evaluation_suite.py").read_text(encoding="utf-8")
    tests = (ROOT / "tests/test_evaluation_suites.py").read_text(encoding="utf-8")

    for doc in (evaluation, python_api):
        for signal in (
            "EvaluationSuite.custom",
            "EvaluationScenario.from_callable",
            "EvaluationContext",
            "context.outcome",
            "suite_version",
            "claim_boundary",
            "not a model-quality claim",
        ):
            assert signal in doc

    for implementation_signal in (
        "EvaluationScenarioOutcome",
        "EvaluationSuite.register",
        "from_registered",
        "registered_names",
        "_coerce_custom_result",
        "Custom evaluation scenarios must return",
    ):
        assert implementation_signal in suites

    for export_signal in ("EvaluationContext", "EvaluationScenarioOutcome"):
        assert export_signal in evaluation_init
        assert export_signal in root_init

    assert "build_suite" in example
    assert "run_walkthrough" in example
    assert "examples/custom_evaluation_suite.py" in evaluation
    assert "custom-evaluation-suite" in evaluation
    assert "custom evaluation-suite authoring API" in changelog
    for test_signal in (
        "test_custom_evaluation_suite_runs_with_provenance_and_artifacts",
        "test_custom_evaluation_suite_failure_gallery_uses_custom_claim_boundary",
        "test_custom_evaluation_walkthrough_example_writes_report_artifacts",
        "test_custom_evaluation_suite_rejects_invalid_metric_payload",
    ):
        assert test_signal in tests

    for criterion in (
        "Users can define and run a custom suite",
        "Custom reports include provenance",
        "Tests cover custom suite success",
        "Docs explain suite authoring and non-claims",
    ):
        assert f"- [x] {criterion}" in expansion


def test_action_candidate_helper_docs_cover_issue_204_contract() -> None:
    python_api = (ROOT / "docs/src/api/python.md").read_text(encoding="utf-8")
    changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    expansion = (ROOT / "docs/src/roadmap-expansion.md").read_text(encoding="utf-8")
    action_candidates = (ROOT / "src/worldforge/action_candidates.py").read_text(encoding="utf-8")
    root_init = (ROOT / "src/worldforge/__init__.py").read_text(encoding="utf-8")
    demos = (ROOT / "src/worldforge/demos/__init__.py").read_text(encoding="utf-8")
    planning_tests = (ROOT / "tests/test_evaluation_and_planning.py").read_text(encoding="utf-8")
    leworldmodel_tests = (ROOT / "tests/test_leworldmodel_provider.py").read_text(encoding="utf-8")

    for signal in (
        "bounded_move_grid_candidates",
        "cartesian_offset_candidates",
        "object_near_candidates",
        "swap_action_candidates",
        "action_candidates_to_score_payload",
        "provider-agnostic",
        "score_action_candidates",
        "do not preprocess images",
        "do not reinterpret robot action spaces",
    ):
        assert signal in python_api

    for implementation_signal in (
        "normalize_action_candidates",
        "bounded_move_grid_candidates",
        "cartesian_offset_candidates",
        "object_near_candidates",
        "swap_action_candidates",
        "ActionCandidatePlans",
        "lower bound must be less than or equal to upper bound",
    ):
        assert implementation_signal in action_candidates

    for export_signal in (
        "normalize_action_candidates",
        "bounded_move_grid_candidates",
        "cartesian_offset_candidates",
        "object_near_candidates",
        "swap_action_candidates",
        "ActionCandidatePlans",
        "action_candidates_to_score_payload",
    ):
        assert export_signal in root_init

    assert "cartesian_offset_candidates" in demos
    assert "test_action_candidate_helpers_return_validated_action_sequences" in planning_tests
    assert "test_bounded_move_grid_candidates_validate_bounds_and_non_finite_inputs" in (
        planning_tests
    )
    assert "bounded_move_grid_candidates" in leworldmodel_tests
    assert "action candidate helpers" in changelog
    for criterion in (
        "Candidate helpers return validated `Action` sequences",
        "Invalid bounds and non-finite inputs fail explicitly",
        "Planning examples use helpers",
        "Tests cover helper output and score-planning integration",
    ):
        assert f"- [x] {criterion}" in expansion


def test_fixture_snapshot_manager_docs_cover_issue_205_contract() -> None:
    fixtures_doc = (ROOT / "docs/src/fixtures.md").read_text(encoding="utf-8")
    artifact_schemas = (ROOT / "docs/src/artifact-schemas.md").read_text(encoding="utf-8")
    docs_contributing = (ROOT / "docs/src/contributing.md").read_text(encoding="utf-8")
    root_contributing = (ROOT / "CONTRIBUTING.md").read_text(encoding="utf-8")
    agents = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
    changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    expansion = (ROOT / "docs/src/roadmap-expansion.md").read_text(encoding="utf-8")
    manager = (ROOT / "src/worldforge/testing/fixture_snapshots.py").read_text(encoding="utf-8")
    testing_init = (ROOT / "src/worldforge/testing/__init__.py").read_text(encoding="utf-8")
    script = (ROOT / "scripts/manage_fixture_snapshots.py").read_text(encoding="utf-8")
    manifest = (ROOT / "tests/fixtures/fixture-snapshots.json").read_text(encoding="utf-8")
    tests = (ROOT / "tests/test_capability_fixtures.py").read_text(encoding="utf-8")

    for signal in (
        "tests/fixtures/fixture-snapshots.json",
        "uv run python scripts/manage_fixture_snapshots.py --format markdown",
        "uv run python scripts/manage_fixture_snapshots.py --write",
        "`intended-update`",
        "Do not use the snapshot manager to fetch remote provider payloads",
    ):
        assert signal in fixtures_doc

    for doc in (docs_contributing, root_contributing, agents):
        assert "scripts/manage_fixture_snapshots.py" in doc

    for implementation_signal in (
        "FIXTURE_SNAPSHOT_MANIFEST_SCHEMA_VERSION",
        "FixtureSnapshotManifest",
        "validate_fixture_snapshot_manifest",
        "allow_intended_updates",
        "parent-directory",
        "backslashes",
        "sha256:<64 hex chars>",
    ):
        assert implementation_signal in manager

    for export_signal in (
        "FixtureSnapshotEntry",
        "load_fixture_snapshot_manifest",
        "validate_fixture_snapshot_manifest",
    ):
        assert export_signal in testing_init

    assert "--allow-intended-updates" in script
    assert "src/worldforge/testing/fixtures/predict/valid_baseline.json" in manifest
    assert "tests/fixtures/providers/cosmos_generate_success.json" in manifest
    assert "examples/benchmark-inputs.json" in manifest
    assert "examples/scenarios/cube-on-table.json" in manifest
    assert "tests/fixtures/scene_artifacts/valid_minimal_scene.json" in manifest
    assert "Fixture snapshot manifests" in artifact_schemas
    assert "fixture snapshot governance" in changelog
    for test_signal in (
        "test_fixture_snapshot_manifest_loads_and_validates_committed_manifest",
        "test_fixture_snapshot_manifest_reports_digest_drift_and_intended_updates",
        "test_fixture_snapshot_manifest_rejects_missing_and_unsafe_paths",
    ):
        assert test_signal in tests

    for criterion in (
        "Fixture manifest validation fails",
        "Review output distinguishes intended updates",
        "Docs explain when to update fixtures",
        "Tests cover manifest load",
    ):
        assert f"- [x] {criterion}" in expansion


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


def test_regression_comparison_docs_cover_issue_248_contract() -> None:
    benchmarking = (ROOT / "docs/src/benchmarking.md").read_text(encoding="utf-8")
    harness = (ROOT / "docs/src/theworldharness.md").read_text(encoding="utf-8")
    html_reports = (ROOT / "docs/src/html-reports.md").read_text(encoding="utf-8")
    claim_map = (ROOT / "docs/src/claim-evidence-map.md").read_text(encoding="utf-8")
    roadmap = (ROOT / "docs/src/roadmap-expansion-2.md").read_text(encoding="utf-8")
    changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    compare_impl = (ROOT / "src/worldforge/harness/report_compare.py").read_text(encoding="utf-8")
    cli = (ROOT / "src/worldforge/cli.py").read_text(encoding="utf-8")
    tests = (ROOT / "tests/test_harness_report_compare.py").read_text(encoding="utf-8")

    for signal in (
        "--mode regression",
        "preserved benchmark, evaluation, and demo-showcase runs",
        "metric deltas",
        "budget status changes",
        "new and removed failures",
        "safe artifact drift",
        "provenance differences",
        "Unsafe artifact references",
        "do not update baselines",
    ):
        assert signal in benchmarking or signal in harness or signal in claim_map

    assert "--mode regression --format html" in html_reports
    assert "Regression comparisons review a candidate run" in claim_map
    assert "worldforge runs compare --mode regression" in changelog
    for checkbox in (
        "- [x] Users can compare a candidate run against a preserved baseline run.",
        "- [x] Report distinguishes metric delta, budget violation, and artifact drift.",
        "- [x] Unsafe artifacts remain excluded from rendered reports.",
        "- [x] Tests cover improved, regressed, missing baseline, and incompatible schema cases.",
    ):
        assert checkbox in roadmap

    for implementation_signal in (
        "compare_preserved_run_regression",
        "_regression_artifact_changes",
        "_SAFE_ARTIFACT_SUFFIXES",
        "demo_showcase",
        "regression_to_markdown",
    ):
        assert implementation_signal in compare_impl
    assert 'choices=("comparison", "regression")' in cli
    for test_signal in (
        "test_regression_comparison_reports_improved_candidate",
        "test_regression_comparison_reports_regression_and_excludes_unsafe_artifacts",
        "test_regression_comparison_supports_demo_showcase_runs",
        "test_regression_comparison_reports_missing_baseline",
        "test_regression_comparison_rejects_incompatible_run_schema",
    ):
        assert test_signal in tests


def test_scenario_matrix_docs_cover_issue_249_contract() -> None:
    scenarios = (ROOT / "docs/src/scenarios.md").read_text(encoding="utf-8")
    roadmap = (ROOT / "docs/src/roadmap-expansion-2.md").read_text(encoding="utf-8")
    changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    implementation = (ROOT / "src/worldforge/scenarios.py").read_text(encoding="utf-8")
    cli = (ROOT / "src/worldforge/cli.py").read_text(encoding="utf-8")
    exports = (ROOT / "src/worldforge/__init__.py").read_text(encoding="utf-8")
    snippet_gate = (ROOT / "scripts/check_docs_snippets.py").read_text(encoding="utf-8")
    tests = (ROOT / "tests/test_scenarios.py").read_text(encoding="utf-8")

    for signal in (
        "Scenario Parameter Matrices",
        "`matrix.parameters`",
        "whole-value placeholders",
        "`worldforge scenario validate <path>` expands and validates every case",
        "`failed_cases` fields",
        "No arbitrary Python execution",
    ):
        assert signal in scenarios
    assert "scenario parameter matrices" in changelog
    for checkbox in (
        "- [x] Matrix scenarios validate before execution and reject unbounded or "
        "non-JSON-native values.",
        "- [x] CLI runs every case in a temp or configured workspace.",
        "- [x] Aggregate output reports pass/fail counts and failed case details.",
        "- [x] Tests cover valid matrix, invalid substitution, failed expectation, and docs "
        "examples.",
    ):
        assert checkbox in roadmap

    for implementation_signal in (
        "SCENARIO_MATRIX_MAX_CASES",
        "class ScenarioMatrix",
        "class ScenarioMatrixResult",
        "parse_scenario_matrix",
        "run_scenario_matrix",
        "_matrix_substitution_allowed",
        "_MATRIX_PLACEHOLDER_PATTERN",
    ):
        assert implementation_signal in implementation
    for export_signal in (
        "SCENARIO_MATRIX_MAX_CASES",
        "ScenarioMatrix",
        "ScenarioMatrixResult",
        "parse_scenario_matrix",
        "run_scenario_matrix",
    ):
        assert export_signal in exports
    assert "load_scenario_matrix" in cli
    assert "run_scenario_matrix" in cli
    assert "parse_scenario_matrix(payload)" in snippet_gate
    for test_signal in (
        "test_parse_scenario_matrix_expands_valid_parameter_matrix",
        "test_parse_scenario_matrix_rejects_invalid_substitution_location",
        "test_parse_scenario_matrix_rejects_unbounded_cases",
        "test_run_scenario_matrix_reports_failed_expectation",
        "test_scenario_matrix_cli_runs_all_cases",
    ):
        assert test_signal in tests


def test_scenario_gallery_docs_cover_issue_243_contract() -> None:
    scenarios = (ROOT / "docs/src/scenarios.md").read_text(encoding="utf-8")
    roadmap = (ROOT / "docs/src/roadmap-expansion-2.md").read_text(encoding="utf-8")
    changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    agents = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
    tests = (ROOT / "tests/test_scenarios.py").read_text(encoding="utf-8")
    manifest = (ROOT / "tests/fixtures/fixture-snapshots.json").read_text(encoding="utf-8")
    scenario_paths = sorted((ROOT / "examples/scenarios").glob("*.json"))

    assert len(scenario_paths) >= 5
    for filename in (
        "cube-on-table.json",
        "spawn-and-move.json",
        "expected-failure-object-count.json",
        "invalid-action-missing-target.json",
        "evaluation-readiness.json",
        "report-export-basic.json",
    ):
        path = ROOT / "examples/scenarios" / filename
        payload = path.read_text(encoding="utf-8")
        assert '"gallery_intent"' in payload
        assert filename in scenarios
        assert f"examples/scenarios/{filename}" in manifest

    for signal in (
        "Scenario Gallery",
        "metadata.expected_failure",
        "metadata.expected_cli_error",
        "scenario validate` passes, `scenario run` fails",
        "--output .worldforge/scenario-gallery/report-export.md",
        "Provider fixtures live under `tests/fixtures/providers/`",
    ):
        assert signal in scenarios

    for checkbox in (
        "- [x] Gallery scenarios validate and run through the CLI.",
        "- [x] Failure scenarios are intentionally marked and tested.",
        "- [x] Docs show expected artifacts and first triage steps.",
        "- [x] Scenario examples stay JSON-native and deterministic.",
    ):
        assert checkbox in roadmap

    assert "scenario gallery" in changelog
    assert "checkout-safe local-world gallery" in agents
    assert "test_scenario_gallery_cli_runs_expected_success_and_failure_modes" in tests


def test_dataset_manifest_docs_cover_issue_250_contract() -> None:
    evaluation = (ROOT / "docs/src/evaluation.md").read_text(encoding="utf-8")
    artifact_schemas = (ROOT / "docs/src/artifact-schemas.md").read_text(encoding="utf-8")
    claim_map = (ROOT / "docs/src/claim-evidence-map.md").read_text(encoding="utf-8")
    roadmap = (ROOT / "docs/src/roadmap-expansion-2.md").read_text(encoding="utf-8")
    changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    implementation = (ROOT / "src/worldforge/dataset_manifests.py").read_text(encoding="utf-8")
    provenance = (ROOT / "src/worldforge/provenance.py").read_text(encoding="utf-8")
    eval_impl = (ROOT / "src/worldforge/evaluation/suites.py").read_text(encoding="utf-8")
    evidence = (ROOT / "src/worldforge/evidence_bundle.py").read_text(encoding="utf-8")
    cli = (ROOT / "src/worldforge/cli.py").read_text(encoding="utf-8")
    tests = (ROOT / "tests/test_evaluation_suites.py").read_text(encoding="utf-8")
    bundle_tests = (ROOT / "tests/test_evidence_bundle.py").read_text(encoding="utf-8")

    for signal in (
        "## Dataset Manifests",
        "`schema_version: 1`",
        "license notes",
        "provenance owner/source/version fields",
        "privacy classification",
        "safety review",
        "host-owned acquisition steps",
        "does not embed dataset entries or raw assets",
    ):
        assert signal in evaluation
    assert "Dataset manifests" in artifact_schemas
    assert "DATASET_MANIFEST_SCHEMA_VERSION" in artifact_schemas
    assert "Evaluation reports can cite dataset manifests without embedding datasets" in claim_map
    assert "evaluation dataset manifest contracts" in changelog
    for checkbox in (
        "- [x] Dataset manifests are JSON-native, schema-versioned, and validated.",
        "- [x] Evaluation reports can cite dataset manifests without embedding datasets.",
        "- [x] Unsafe or under-specified manifests fail explicitly.",
        "- [x] Docs explain license/provenance boundaries and host-owned assets.",
    ):
        assert checkbox in roadmap

    for implementation_signal in (
        "DATASET_MANIFEST_SCHEMA_VERSION",
        "class DatasetManifest",
        "class DatasetManifestEntry",
        "load_dataset_manifest",
        "parse_dataset_manifest",
        "dataset_manifest_references",
        "_safe_relative_path",
        "_safe_remote_uri",
    ):
        assert implementation_signal in implementation
    assert "dataset_manifests" in provenance
    assert "dataset_manifest_references" in eval_impl
    assert "dataset-manifest" in evidence
    assert "--dataset-manifest" in cli
    for test_signal in (
        "test_dataset_manifest_validates_and_evaluation_report_cites_it",
        "test_dataset_manifest_rejects_unsafe_or_under_specified_payloads",
        "test_dataset_manifest_validates_remote_reference_boundaries",
    ):
        assert test_signal in tests
    assert "mock-evaluation-fixtures.json" in bundle_tests


def test_provider_contract_cli_docs_cover_issue_251_contract() -> None:
    authoring = (ROOT / "docs/src/provider-authoring-guide.md").read_text(encoding="utf-8")
    external = (ROOT / "docs/src/external-providers.md").read_text(encoding="utf-8")
    cli_docs = (ROOT / "docs/src/cli.md").read_text(encoding="utf-8")
    schemas = (ROOT / "docs/src/artifact-schemas.md").read_text(encoding="utf-8")
    roadmap = (ROOT / "docs/src/roadmap-expansion-2.md").read_text(encoding="utf-8")
    changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    agents = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
    implementation = (ROOT / "src/worldforge/provider_contracts.py").read_text(encoding="utf-8")
    cli = (ROOT / "src/worldforge/cli.py").read_text(encoding="utf-8")
    exports = (ROOT / "src/worldforge/__init__.py").read_text(encoding="utf-8")
    tests = (ROOT / "tests/test_provider_contracts.py").read_text(encoding="utf-8")
    entry_tests = (ROOT / "tests/test_provider_entry_points.py").read_text(encoding="utf-8")

    for signal in (
        "worldforge provider contract mock --format markdown",
        "--factory my_pkg.adapters:make_my_policy_provider",
        "`--live`",
        "skipped host-owned checks",
        "validation commands",
        "does not claim physical fidelity",
    ):
        assert signal in authoring
    for signal in (
        "## Contract CLI",
        "worldforge provider contract my-policy --format json",
        "safe-to-attach JSON or Markdown evidence",
        "skipped host-owned\nchecks",
        "``--live``",
        "``--score-info``",
    ):
        assert signal in external
    assert "uv run worldforge provider contract mock --format json" in cli_docs
    assert "Provider contract evidence" in schemas
    assert "PROVIDER_CONTRACT_EVIDENCE_SCHEMA_VERSION" in schemas
    assert "external adapter authors" in changelog
    assert "`worldforge provider contract` output is issue-facing evidence" in agents
    for checkbox in (
        "- [x] CLI can run contract checks for mock and fixture-backed providers.",
        "- [x] Unsupported or unimplemented advertised capabilities fail loudly.",
        "- [x] Output is safe to attach and includes validation commands.",
        "- [x] Docs link the CLI from provider authoring and external provider docs.",
    ):
        assert checkbox in roadmap

    for implementation_signal in (
        "PROVIDER_CONTRACT_EVIDENCE_SCHEMA_VERSION",
        "class ProviderContractEvidence",
        "class ProviderContractCheck",
        "provider_from_factory_path",
        "run_provider_contract",
        "_host_owned_skips",
        "_safe_detail",
    ):
        assert implementation_signal in implementation
    for cli_signal in (
        "provider contract",
        "_cmd_provider_contract",
        "load_json_contract_input",
        "provider_from_factory_path",
    ):
        assert cli_signal in cli
    for export_signal in (
        "PROVIDER_CONTRACT_EVIDENCE_SCHEMA_VERSION",
        "ProviderContractEvidence",
        "run_provider_contract",
    ):
        assert export_signal in exports
    for test_signal in (
        "test_provider_contract_cli_runs_mock_provider",
        "test_provider_contract_cli_reports_direct_factory_failure",
        "test_provider_contract_cli_skips_configured_remote_without_live",
    ):
        assert test_signal in tests
    assert "test_discovery_loads_valid_entry_point" in entry_tests


def test_runtime_asset_manifest_docs_cover_issue_252_contract() -> None:
    operations = (ROOT / "docs/src/operations.md").read_text(encoding="utf-8")
    schemas = (ROOT / "docs/src/artifact-schemas.md").read_text(encoding="utf-8")
    roadmap = (ROOT / "docs/src/roadmap-expansion-2.md").read_text(encoding="utf-8")
    changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    agents = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
    implementation = (ROOT / "src/worldforge/providers/runtime_manifest.py").read_text(
        encoding="utf-8"
    )
    run_manifest = (ROOT / "src/worldforge/smoke/run_manifest.py").read_text(encoding="utf-8")
    runtime_assets = (ROOT / "src/worldforge/smoke/runtime_assets.py").read_text(encoding="utf-8")
    lewm_smoke = (ROOT / "src/worldforge/smoke/leworldmodel.py").read_text(encoding="utf-8")
    robotics_smoke = (ROOT / "src/worldforge/smoke/lerobot_leworldmodel.py").read_text(
        encoding="utf-8"
    )
    exports = (ROOT / "src/worldforge/__init__.py").read_text(encoding="utf-8")
    runtime_tests = (ROOT / "tests/test_runtime_profiles.py").read_text(encoding="utf-8")
    robotics_tests = (ROOT / "tests/test_robotics_showcase.py").read_text(encoding="utf-8")

    for signal in (
        "## Runtime Asset Manifests And Cache Policy",
        "RUNTIME_ASSET_MANIFEST_SCHEMA_VERSION",
        "`runtime_assets`",
        "`local_only: true`",
        "safe-to-attach references",
        "worldforge-build-leworldmodel-checkpoint",
        "LeWorldModel",
        "LeRobot",
        "GR00T",
        "Cosmos-Policy",
        "Future provider candidates",
        "Cleanup is also host-owned",
    ):
        assert signal in operations
    assert "Runtime asset manifests and references" in schemas
    assert "RUNTIME_ASSET_MANIFEST_SCHEMA_VERSION" in schemas
    assert "runtime asset manifests" in changelog
    assert "Runtime asset manifests are evidence records" in agents
    for checkbox in (
        "- [x] Runtime asset manifests validate local-only and attachable fields separately.",
        "- [x] Optional smoke outputs can reference manifests without embedding assets.",
        "- [x] Docs explain cache cleanup, rebuild, and evidence boundaries.",
        "- [x] Tests cover valid, missing, unsafe, and local-only manifest cases.",
    ):
        assert checkbox in roadmap

    for implementation_signal in (
        "RUNTIME_ASSET_MANIFEST_SCHEMA_VERSION",
        "class RuntimeAssetManifest",
        "validate_runtime_asset_manifest",
        "include_local_fields",
        "safe_to_attach",
        "local_only",
    ):
        assert implementation_signal in implementation
    for run_signal in (
        "runtime_assets",
        "validate_runtime_asset_manifest",
        "_runtime_asset_summary",
    ):
        assert run_signal in run_manifest
    for helper_signal in (
        "leworldmodel_checkpoint_asset",
        "lerobot_policy_asset",
        "LEWORLDMODEL_ASSET_SOURCE",
    ):
        assert helper_signal in runtime_assets
    assert "runtime_assets=runtime_assets" in lewm_smoke
    assert "runtime_assets=runtime_assets" in robotics_smoke
    for export_signal in (
        "RUNTIME_ASSET_MANIFEST_SCHEMA_VERSION",
        "RuntimeAssetManifest",
        "validate_runtime_asset_manifest",
    ):
        assert export_signal in exports
    for test_signal in (
        "test_runtime_asset_manifest_separates_local_and_attachable_fields",
        "test_runtime_asset_manifest_rejects_unsafe_attachable_or_secret_fields",
        "test_run_manifest_references_runtime_assets_without_local_paths",
    ):
        assert test_signal in runtime_tests
    assert "test_robotics_runtime_asset_references_omit_host_paths" in robotics_tests


def test_config_profile_docs_cover_issue_253_contract() -> None:
    operations = (ROOT / "docs/src/operations.md").read_text(encoding="utf-8")
    schemas = (ROOT / "docs/src/artifact-schemas.md").read_text(encoding="utf-8")
    roadmap = (ROOT / "docs/src/roadmap-expansion-2.md").read_text(encoding="utf-8")
    changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    agents = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
    implementation = (ROOT / "src/worldforge/config_profiles.py").read_text(encoding="utf-8")
    cli = (ROOT / "src/worldforge/cli.py").read_text(encoding="utf-8")
    workspace = (ROOT / "src/worldforge/harness/workspace.py").read_text(encoding="utf-8")
    provider_tests = (ROOT / "tests/test_provider_config.py").read_text(encoding="utf-8")
    workspace_tests = (ROOT / "tests/test_harness_workspace.py").read_text(encoding="utf-8")

    for signal in (
        "## Non-Secret Configuration Profiles",
        "Configuration profiles are optional JSON or TOML files",
        '"schema_version": 1',
        '"providers": ["mock"]',
        '"run_workspace": ".worldforge/profiled-runs"',
        "uv run worldforge benchmark --profile",
        "uv run worldforge eval --profile",
        "must not contain credentials",
        "`config_profile` provenance",
    ):
        assert signal in operations
    assert "Non-secret configuration profiles" in schemas
    assert "CONFIG_PROFILE_SCHEMA_VERSION" in schemas
    assert "non-secret JSON/TOML configuration profiles" in changelog
    assert "Non-secret configuration profiles are shareable defaults" in agents
    for checkbox in (
        "- [x] Profiles reject secret-looking keys and unsafe paths where applicable.",
        "- [x] CLI commands can opt into a profile without changing existing defaults.",
        "- [x] Profile provenance appears in run manifests.",
        "- [x] Docs explain what belongs in profiles and what does not.",
    ):
        assert checkbox in roadmap
    for implementation_signal in (
        "CONFIG_PROFILE_SCHEMA_VERSION",
        "class ConfigProfile",
        "load_config_profile",
        "parse_config_profile",
        "validate_config_profile_provenance",
        "runtime_cache_roots",
    ):
        assert implementation_signal in implementation
    assert "_apply_cli_profile" in cli
    assert "--profile" in cli
    assert "validate_config_profile_provenance" in workspace
    assert '"config_profile"' in workspace
    assert "test_config_profile_loads_non_secret_defaults_and_provenance" in provider_tests
    assert "test_config_profile_rejects_secret_keys_and_unsafe_paths" in provider_tests
    assert "test_benchmark_cli_profile_applies_defaults_and_preserves_provenance" in workspace_tests


def test_report_renderer_extension_docs_cover_issue_254_contract() -> None:
    html_docs = (ROOT / "docs/src/html-reports.md").read_text(encoding="utf-8")
    roadmap = (ROOT / "docs/src/roadmap-expansion-2.md").read_text(encoding="utf-8")
    changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    agents = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
    implementation = (ROOT / "src/worldforge/report_renderers.py").read_text(encoding="utf-8")
    comparison = (ROOT / "src/worldforge/harness/report_compare.py").read_text(encoding="utf-8")
    evidence = (ROOT / "src/worldforge/evidence_bundle.py").read_text(encoding="utf-8")
    exports = (ROOT / "src/worldforge/__init__.py").read_text(encoding="utf-8")
    comparison_tests = (ROOT / "tests/test_harness_report_compare.py").read_text(encoding="utf-8")
    evidence_tests = (ROOT / "tests/test_evidence_bundle.py").read_text(encoding="utf-8")

    for signal in (
        "## Renderer Extension Points",
        "ReportRenderer",
        "register_report_renderer",
        "render_report_artifact",
        "safe to attach or local-only",
        "WorldForge does not load renderer plugins from arbitrary files",
        "Built-in renderer families include `comparison`, `evidence-bundle`, and",
    ):
        assert signal in html_docs
    assert "safe report-renderer registry" in changelog
    assert "Report renderer extensions must declare" in agents
    for checkbox in (
        "- [x] External code can register a renderer for a supported artifact family.",
        "- [x] Renderer output is marked safe-to-attach or local-only.",
        "- [x] Invalid renderer metadata fails explicitly.",
        (
            "- [x] Tests cover built-in renderers, custom renderer, duplicate format, "
            "and unsafe output cases."
        ),
    ):
        assert checkbox in roadmap
    for implementation_signal in (
        "class ReportRenderer",
        "class ReportRenderResult",
        "register_report_renderer",
        "render_report_artifact",
        "safe-to-attach or local-only",
    ):
        assert implementation_signal in implementation
    assert "_register_builtin_report_renderers" in comparison
    assert 'render_report_artifact("comparison"' in comparison
    assert "evidence_bundle_artifact" in evidence
    assert "issue_bundle_artifact" in evidence
    for export_signal in (
        "ReportRenderer",
        "ReportRenderResult",
        "register_report_renderer",
        "render_report_artifact",
    ):
        assert export_signal in exports
    assert "test_builtin_comparison_renderers_are_registered_and_safe" in comparison_tests
    assert "test_custom_renderer_registration_duplicate_and_unsafe_output" in comparison_tests
    assert "evidence_bundle_artifact" in evidence_tests
    assert "issue_bundle_artifact" in evidence_tests


def test_world_migration_preview_docs_cover_issue_255_contract() -> None:
    cli_docs = (ROOT / "docs/src/cli.md").read_text(encoding="utf-8")
    operations = (ROOT / "docs/src/operations.md").read_text(encoding="utf-8")
    playbooks = (ROOT / "docs/src/playbooks.md").read_text(encoding="utf-8")
    schemas = (ROOT / "docs/src/artifact-schemas.md").read_text(encoding="utf-8")
    roadmap = (ROOT / "docs/src/roadmap-expansion-2.md").read_text(encoding="utf-8")
    changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    agents = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
    implementation = (ROOT / "src/worldforge/world_migration_preview.py").read_text(
        encoding="utf-8"
    )
    cli = (ROOT / "src/worldforge/cli.py").read_text(encoding="utf-8")
    lifecycle_tests = (ROOT / "tests/test_world_lifecycle.py").read_text(encoding="utf-8")
    cli_tests = (ROOT / "tests/test_cli_world_commands.py").read_text(encoding="utf-8")

    for signal in (
        "worldforge world migration-preview <world-id>",
        "worldforge world migration-preview world.json --source-path",
        "schema version",
        "required changes",
        "invalid fields",
        "unsafe IDs",
        "bounding-box corrections",
        "can_apply_safely",
        "does not rewrite state",
    ):
        assert signal in cli_docs or signal in operations or signal in playbooks
    assert "World migration previews" in schemas
    assert "WORLD_MIGRATION_PREVIEW_SCHEMA_VERSION" in schemas
    assert "read-only world migration previews" in changelog
    assert "World migration previews are read-only issue-facing reports" in agents
    for checkbox in (
        "- [x] Preview is read-only by default and works on a temp copy in tests.",
        "- [x] Invalid state reports exact failure reasons instead of coercing silently.",
        "- [x] Output can be attached to issues safely.",
        "- [x] Docs explain import/export and local persistence migration boundaries.",
    ):
        assert checkbox in roadmap
    for implementation_signal in (
        "WORLD_MIGRATION_PREVIEW_SCHEMA_VERSION",
        "preview_world_migration_from_world_id",
        "preview_world_migration_from_path",
        "render_world_migration_preview_markdown",
        "bounding_box_corrections",
        "can_apply_safely",
    ):
        assert implementation_signal in implementation
    assert '"migration-preview"' in cli
    assert "_cmd_world_migration_preview" in cli
    for test_signal in (
        "test_world_migration_preview_accepts_current_persisted_and_exported_state",
        "test_world_migration_preview_reports_legacy_schema_and_position_changes",
        "test_world_migration_preview_reports_invalid_fields_and_unsafe_ids",
        "test_world_migration_preview_reports_bbox_correction_without_rewriting",
    ):
        assert test_signal in lifecycle_tests
    assert "test_world_cli_migration_preview_is_read_only_and_attachable" in cli_tests


def test_workflow_trace_docs_cover_issue_256_contract() -> None:
    operations = (ROOT / "docs/src/operations.md").read_text(encoding="utf-8")
    python_api = (ROOT / "docs/src/api/python.md").read_text(encoding="utf-8")
    schemas = (ROOT / "docs/src/artifact-schemas.md").read_text(encoding="utf-8")
    roadmap = (ROOT / "docs/src/roadmap-expansion-2.md").read_text(encoding="utf-8")
    changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    agents = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
    implementation = (ROOT / "src/worldforge/workflow_trace.py").read_text(encoding="utf-8")
    framework = (ROOT / "src/worldforge/framework.py").read_text(encoding="utf-8")
    evaluation = (ROOT / "src/worldforge/evaluation/suites.py").read_text(encoding="utf-8")
    html_report = (ROOT / "src/worldforge/html_report.py").read_text(encoding="utf-8")
    rerun = (ROOT / "src/worldforge/rerun.py").read_text(encoding="utf-8")
    provider_tests = (ROOT / "tests/test_provider_events.py").read_text(encoding="utf-8")
    evaluation_tests = (ROOT / "tests/test_evaluation_and_planning.py").read_text(encoding="utf-8")
    rerun_tests = (ROOT / "tests/test_rerun_integration.py").read_text(encoding="utf-8")

    for signal in (
        "WorkflowTrace",
        "schema-versioned",
        "step IDs",
        "provider/capability slots",
        "input/output artifact references",
        "parent-child relationships",
        'Plan.metadata["workflow_trace"]',
        "workflow_trace.json",
        "RerunArtifactLogger.log_workflow_trace",
        "raw prompts, tensors, credentials",
    ):
        assert signal in operations or signal in python_api
    assert "Workflow trace artifacts" in schemas
    assert "WORKFLOW_TRACE_SCHEMA_VERSION" in schemas
    assert "schema-versioned workflow trace artifacts" in changelog
    assert "Workflow traces are artifact-facing records" in agents
    for checkbox in (
        (
            "- [x] Composed workflows can emit trace artifacts without changing provider "
            "capability semantics."
        ),
        "- [x] Trace artifacts are sanitized and schema-versioned.",
        "- [x] Failure propagation is visible without hiding the original provider error.",
        "- [x] Tests cover successful, skipped, failed, and nested workflow traces.",
    ):
        assert checkbox in roadmap
    for implementation_signal in (
        "WORKFLOW_TRACE_SCHEMA_VERSION",
        "class WorkflowTrace",
        "class WorkflowTraceStep",
        "class WorkflowArtifactRef",
        "workflow_trace_from_provider_events",
    ):
        assert implementation_signal in implementation
    assert '"workflow_trace"' in framework
    assert '"workflow_trace.json"' in evaluation
    assert "Workflow Trace" in html_report
    assert "log_workflow_trace" in rerun
    assert (
        "test_workflow_trace_from_provider_events_sanitizes_failures_and_artifacts"
        in provider_tests
    )
    assert "test_workflow_trace_validates_skipped_failed_and_nested_steps" in provider_tests
    assert "workflow_trace.json" in evaluation_tests
    assert "test_rerun_artifact_logger_logs_workflow_trace" in rerun_tests


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


def test_roadmap_expansion_2_documents_three_streams_and_thirty_issues() -> None:
    expansion = (ROOT / "docs/src/roadmap-expansion-2.md").read_text(encoding="utf-8")
    roadmap = (ROOT / "docs/src/roadmap.md").read_text(encoding="utf-8")
    summary = (ROOT / "docs/src/SUMMARY.md").read_text(encoding="utf-8")
    mkdocs = (ROOT / "mkdocs.yml").read_text(encoding="utf-8")
    changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")

    assert "Roadmap Expansion 2" in roadmap
    assert "[Roadmap Expansion 2](./roadmap-expansion-2.md)" in summary
    assert "Roadmap Expansion 2: roadmap-expansion-2.md" in mkdocs
    assert "second 30-issue roadmap expansion" in changelog
    assert "roadmap: expansion-2" in expansion

    streams = (
        "Production Grade, Quality, DevX, And Docs",
        "Demos, End-to-End Showcases, And Use Cases",
        "New Features",
    )
    for stream in streams:
        assert stream in expansion

    assert expansion.count("### WF-PQDX2-") == 10
    assert expansion.count("### WF-DEMO2-") == 10
    assert expansion.count("### WF-FEAT2-") == 10
    assert "GitHub issue: pending" not in expansion
    assert expansion.count("https://github.com/AbdelStark/worldforge/issues/") >= 30

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


def test_contributor_task_starters_cover_issue_233_contract() -> None:
    starters = (ROOT / "docs/src/task-starters.md").read_text(encoding="utf-8")
    docs_contributing = (ROOT / "docs/src/contributing.md").read_text(encoding="utf-8")
    root_contributing = (ROOT / "CONTRIBUTING.md").read_text(encoding="utf-8")
    summary = (ROOT / "docs/src/SUMMARY.md").read_text(encoding="utf-8")
    mkdocs = (ROOT / "mkdocs.yml").read_text(encoding="utf-8")
    docs_map = (ROOT / "docs/src/docs-map.md").read_text(encoding="utf-8")
    changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    expansion = (ROOT / "docs/src/roadmap-expansion-2.md").read_text(encoding="utf-8")
    issue_templates = "\n".join(
        path.read_text(encoding="utf-8") for path in (ROOT / ".github/ISSUE_TEMPLATE").glob("*.yml")
    )

    starter_titles = (
        "Provider Adapter Or Runtime Promotion",
        "Docs-Only Or Public Surface",
        "Demo Or Showcase Workflow",
        "Artifact, Report, Or Evidence",
        "Evaluation Or Benchmark",
        "CLI Or Operator Workflow",
    )
    required_sections = (
        "Likely Files To Inspect",
        "Forbidden Shortcuts",
        "Validation Commands",
        "Evidence Artifacts",
        "Docs And Changelog Expectations",
        "Review Checklist",
    )
    for title in starter_titles:
        assert f"## {title}" in starters
    for section in required_sections:
        assert starters.count(f"### {section}") == len(starter_titles)

    for repo_path in (
        "src/worldforge/providers/",
        "docs/src/",
        "scripts/demo_showcases.py",
        "src/worldforge/evidence_bundle.py",
        "src/worldforge/evaluation/",
        "src/worldforge/cli.py",
    ):
        assert repo_path in starters

    for command in (
        "uv run python scripts/generate_provider_docs.py --check",
        "uv run python scripts/check_docs_snippets.py",
        "uv run python scripts/demo_showcases.py list",
        "uv run pytest tests/test_evidence_bundle.py tests/test_html_report.py",
        "uv run worldforge benchmark --provider mock --operation generate",
        "uv run pytest tests/test_cli_help_snapshots.py tests/test_cli_world_commands.py",
    ):
        assert command in starters

    for signal in (
        "docs/changelog expectations",
        "CHANGELOG.md",
        "Do not advertise",
        "safe to attach",
        "first triage step",
    ):
        assert signal in starters

    assert "[Contributor Task Starters](./task-starters.md)" in docs_contributing
    assert "[Contributor Task Starters](./docs/src/task-starters.md)" in root_contributing
    assert "[Contributor Task Starters](./task-starters.md)" in summary
    assert "Contributor Task Starters: task-starters.md" in mkdocs
    assert "[Contributor Task Starters](./task-starters.md)" in docs_map
    assert "contributor task starter packs" in changelog
    assert "https://abdelstark.github.io/worldforge/task-starters/" in issue_templates
    for criterion in (
        "At least six starter packs exist",
        "Starter packs include validation commands",
        "Issue templates or contributing docs point contributors",
        "Tests guard the presence of required sections",
    ):
        assert f"- [x] {criterion}" in expansion


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


def test_release_notes_draft_docs_cover_issue_234_contract() -> None:
    operations = (ROOT / "docs/src/operations.md").read_text(encoding="utf-8")
    playbooks = (ROOT / "docs/src/playbooks.md").read_text(encoding="utf-8")
    integrity = (ROOT / "docs/src/artifact-integrity.md").read_text(encoding="utf-8")
    changelog_doc = (ROOT / "docs/src/changelog.md").read_text(encoding="utf-8")
    agents = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
    changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    expansion = (ROOT / "docs/src/roadmap-expansion-2.md").read_text(encoding="utf-8")
    distribution = (ROOT / "scripts/check_distribution.py").read_text(encoding="utf-8")
    release_notes_script = (ROOT / "scripts/generate_release_notes.py").read_text(encoding="utf-8")
    release_notes_tests = (ROOT / "tests/test_release_notes.py").read_text(encoding="utf-8")

    for doc in (operations, playbooks, integrity, changelog_doc, agents):
        assert "uv run python scripts/generate_release_notes.py" in doc

    for signal in (
        ".worldforge/release-notes/release-notes-draft.md",
        "--issues-json",
        "--require-validation-evidence",
        "maintainer-editable",
        "never creates a GitHub release",
        "validation evidence is missing",
        "host-owned optional-runtime",
    ):
        assert (
            signal in operations
            or signal in playbooks
            or signal in integrity
            or signal in changelog_doc
        )

    for implementation_signal in (
        "GITHUB_ISSUE_EXPORT_COMMAND",
        "ReleaseNotesDraft",
        "build_release_notes_draft",
        "Closed Issues By Label",
        "Compatibility Notes",
        "Host-Owned Optional Runtime Evidence",
        "Missing changelog",
        "Validation evidence missing",
    ):
        assert implementation_signal in release_notes_script

    for test_signal in (
        "test_release_notes_draft_collects_changelog_issues_and_evidence",
        "test_release_notes_main_reports_missing_validation_evidence",
        "test_release_notes_main_reports_missing_changelog",
    ):
        assert test_signal in release_notes_tests

    assert "scripts/generate_release_notes.py" in distribution
    assert "release notes draft generator" in changelog
    for criterion in (
        "Command produces a Markdown draft",
        "Draft includes validation evidence references",
        "Missing changelog or missing validation evidence",
        "Docs explain how maintainers review",
    ):
        assert f"- [x] {criterion}" in expansion


def test_dependency_audit_evidence_docs_cover_issue_235_contract() -> None:
    operations = (ROOT / "docs/src/operations.md").read_text(encoding="utf-8")
    playbooks = (ROOT / "docs/src/playbooks.md").read_text(encoding="utf-8")
    integrity = (ROOT / "docs/src/artifact-integrity.md").read_text(encoding="utf-8")
    quality = (ROOT / "docs/src/quality.md").read_text(encoding="utf-8")
    agents = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
    schemas = (ROOT / "docs/src/artifact-schemas.md").read_text(encoding="utf-8")
    changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    expansion = (ROOT / "docs/src/roadmap-expansion-2.md").read_text(encoding="utf-8")
    distribution = (ROOT / "scripts/check_distribution.py").read_text(encoding="utf-8")
    release_evidence = (ROOT / "scripts/generate_release_evidence.py").read_text(encoding="utf-8")
    audit_script = (ROOT / "scripts/generate_dependency_audit_evidence.py").read_text(
        encoding="utf-8"
    )
    audit_tests = (ROOT / "tests/test_dependency_audit_evidence.py").read_text(encoding="utf-8")

    for doc in (operations, playbooks, integrity, quality, agents):
        assert "uv run python scripts/generate_dependency_audit_evidence.py" in doc

    for signal in (
        ".worldforge/dependency-audit/dependency-audit.json",
        ".worldforge/dependency-audit/dependency-audit.md",
        "--ignore-advisory ADVISORY=RATIONALE",
        "temporary requirements file",
        "tool-unavailable",
        "findings",
        "uvx --from pip-audit pip-audit",
    ):
        assert (
            signal in operations or signal in playbooks or signal in integrity or signal in quality
        )

    for implementation_signal in (
        "DEPENDENCY_AUDIT_EVIDENCE_SCHEMA_VERSION",
        "generate_dependency_audit_evidence",
        "render_dependency_audit_markdown",
        "temporary uv export file removed after audit",
        "vulnerability_summary",
        "ignored_advisories",
        "tool-unavailable",
        "safe_to_attach",
    ):
        assert implementation_signal in audit_script

    for test_signal in (
        "test_dependency_audit_evidence_records_clean_run",
        "test_dependency_audit_evidence_preserves_findings_and_ignore_rationales",
        "test_dependency_audit_evidence_records_tool_unavailable",
    ):
        assert test_signal in audit_tests

    assert "DEFAULT_DEPENDENCY_AUDIT_DIR" in release_evidence
    assert "generate_dependency_audit_evidence.py" in release_evidence
    assert "scripts/generate_dependency_audit_evidence.py" in distribution
    assert "Dependency audit evidence" in schemas
    assert "tests/test_dependency_audit_evidence.py" in schemas
    assert "dependency-audit evidence" in changelog
    for criterion in (
        "Audit evidence writes JSON and Markdown summaries",
        "Vulnerability findings are preserved",
        "Release-readiness docs and package validation docs",
        "Tests cover clean, finding, and tool-unavailable",
    ):
        assert f"- [x] {criterion}" in expansion


def test_quality_dashboard_docs_cover_issue_236_contract() -> None:
    operations = (ROOT / "docs/src/operations.md").read_text(encoding="utf-8")
    playbooks = (ROOT / "docs/src/playbooks.md").read_text(encoding="utf-8")
    integrity = (ROOT / "docs/src/artifact-integrity.md").read_text(encoding="utf-8")
    quality = (ROOT / "docs/src/quality.md").read_text(encoding="utf-8")
    contributing = (ROOT / "docs/src/contributing.md").read_text(encoding="utf-8")
    root_contributing = (ROOT / "CONTRIBUTING.md").read_text(encoding="utf-8")
    agents = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
    schemas = (ROOT / "docs/src/artifact-schemas.md").read_text(encoding="utf-8")
    task_starters = (ROOT / "docs/src/task-starters.md").read_text(encoding="utf-8")
    docs_map = (ROOT / "docs/src/docs-map.md").read_text(encoding="utf-8")
    changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    expansion = (ROOT / "docs/src/roadmap-expansion-2.md").read_text(encoding="utf-8")
    distribution = (ROOT / "scripts/check_distribution.py").read_text(encoding="utf-8")
    dashboard_script = (ROOT / "scripts/generate_quality_dashboard.py").read_text(encoding="utf-8")
    dashboard_tests = (ROOT / "tests/test_quality_dashboard.py").read_text(encoding="utf-8")

    for doc in (
        operations,
        playbooks,
        integrity,
        quality,
        contributing,
        root_contributing,
        agents,
    ):
        assert "uv run python scripts/generate_quality_dashboard.py" in doc

    for signal in (
        ".worldforge/quality-dashboard/quality-dashboard.json",
        ".worldforge/quality-dashboard/quality-dashboard.md",
        "does not execute gates",
        "Release evidence remains",
        "`failed`",
        "`warning`",
        "`skipped`",
        "`not-run`",
        "first failed gate",
        "host-owned",
    ):
        assert (
            signal in operations
            or signal in playbooks
            or signal in integrity
            or signal in quality
            or signal in agents
        )

    for implementation_signal in (
        "QUALITY_DASHBOARD_SCHEMA_VERSION",
        "build_quality_dashboard",
        "render_quality_dashboard_markdown",
        "first_failed_gate",
        "raw_details",
        "not-run",
        "host_owned",
        "DEFAULT_RELEASE_EVIDENCE",
        "DEFAULT_DEPENDENCY_AUDIT",
        "DEFAULT_CORE_PERFORMANCE",
    ):
        assert implementation_signal in dashboard_script

    for test_signal in (
        "test_quality_dashboard_aggregates_mixed_gate_statuses",
        "test_quality_dashboard_marks_missing_sources_not_run",
        "test_quality_dashboard_main_writes_json_and_markdown",
    ):
        assert test_signal in dashboard_tests

    assert "Quality dashboard artifact" in schemas
    assert "tests/test_quality_dashboard.py" in schemas
    assert "scripts/generate_quality_dashboard.py" in distribution
    assert "quality dashboards" in task_starters
    assert "quality dashboard" in docs_map
    assert "quality dashboard generator" in changelog
    for criterion in (
        "Dashboard aggregates existing gate outputs",
        "Output distinguishes failures",
        "Docs explain how the dashboard differs",
        "Tests cover mixed pass/fail/skip aggregation",
    ):
        assert f"- [x] {criterion}" in expansion


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


def test_artifact_schema_docs_cover_issue_227_contract() -> None:
    artifact_schemas = (ROOT / "docs/src/artifact-schemas.md").read_text(encoding="utf-8")
    summary = (ROOT / "docs/src/SUMMARY.md").read_text(encoding="utf-8")
    mkdocs = (ROOT / "mkdocs.yml").read_text(encoding="utf-8")
    docs_map = (ROOT / "docs/src/docs-map.md").read_text(encoding="utf-8")
    contributing = (ROOT / "docs/src/contributing.md").read_text(encoding="utf-8")
    changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    init_exports = (ROOT / "src/worldforge/__init__.py").read_text(encoding="utf-8")

    assert "[Artifact Schemas](./artifact-schemas.md)" in summary
    assert "Artifact Schemas: artifact-schemas.md" in mkdocs
    assert "[Artifact Schemas](./artifact-schemas.md)" in docs_map
    assert "[Artifact Schemas](./artifact-schemas.md)" in contributing
    assert "docs/src/artifact-schemas.md" in changelog

    required_rows = (
        ("World state JSON", "SCHEMA_VERSION", "src/worldforge/framework.py"),
        ("Run manifests", "RUN_MANIFEST_SCHEMA_VERSION", "src/worldforge/smoke/run_manifest.py"),
        ("Run workspaces", "RUN_WORKSPACE_SCHEMA_VERSION", "src/worldforge/harness/workspace.py"),
        ("Run index reports", "RUN_INDEX_SCHEMA_VERSION", "src/worldforge/harness/run_index.py"),
        (
            "Evidence bundles and issue bundles",
            "EVIDENCE_BUNDLE_SCHEMA_VERSION",
            "src/worldforge/evidence_bundle.py",
        ),
        (
            "Release evidence JSON",
            "scripts/generate_release_evidence.py",
            "tests/test_release_evidence.py",
        ),
        (
            "Dependency audit evidence",
            "DEPENDENCY_AUDIT_EVIDENCE_SCHEMA_VERSION",
            "tests/test_dependency_audit_evidence.py",
        ),
        (
            "Quality dashboard artifact",
            "QUALITY_DASHBOARD_SCHEMA_VERSION",
            "tests/test_quality_dashboard.py",
        ),
        (
            "Benchmark inputs and budgets",
            "src/worldforge/benchmark.py",
            "tests/test_benchmark.py",
        ),
        (
            "Benchmark calibration reports",
            "BENCHMARK_CALIBRATION_SCHEMA_VERSION",
            "src/worldforge/benchmark_calibration.py",
        ),
        (
            "Evaluation reports and provenance",
            "PROVENANCE_SCHEMA_VERSION",
            "src/worldforge/provenance.py",
        ),
        (
            "Dataset manifests",
            "DATASET_MANIFEST_SCHEMA_VERSION",
            "src/worldforge/dataset_manifests.py",
        ),
        (
            "Evaluation failure galleries",
            "EVALUATION_FAILURE_GALLERY_SCHEMA_VERSION",
            "src/worldforge/evaluation/suites.py",
        ),
        (
            "Capability fixture corpus",
            "FIXTURE_SCHEMA_VERSION",
            "src/worldforge/testing/capability_fixtures.py",
        ),
        (
            "Fixture snapshot manifests",
            "FIXTURE_SNAPSHOT_MANIFEST_SCHEMA_VERSION",
            "src/worldforge/testing/fixture_snapshots.py",
        ),
        (
            "Provider runtime manifests",
            "MANIFEST_SCHEMA_VERSION",
            "src/worldforge/providers/runtime_manifest.py",
        ),
        (
            "Runtime asset manifests and references",
            "RUNTIME_ASSET_MANIFEST_SCHEMA_VERSION",
            "src/worldforge/providers/runtime_manifest.py",
        ),
        (
            "Non-secret configuration profiles",
            "CONFIG_PROFILE_SCHEMA_VERSION",
            "src/worldforge/config_profiles.py",
        ),
        (
            "Provider contract evidence",
            "PROVIDER_CONTRACT_EVIDENCE_SCHEMA_VERSION",
            "src/worldforge/provider_contracts.py",
        ),
        (
            "Capability negotiation reports",
            "CAPABILITY_NEGOTIATION_SCHEMA_VERSION",
            "src/worldforge/capability_negotiation.py",
        ),
        (
            "Scenario files and scenario results",
            "SCENARIO_SCHEMA_VERSION",
            "src/worldforge/scenarios.py",
        ),
        (
            "World diff and patch artifacts",
            "WORLD_DIFF_SCHEMA_VERSION",
            "src/worldforge/world_diff.py",
        ),
        (
            "Static HTML report metadata",
            "HTML_REPORT_SCHEMA_VERSION",
            "src/worldforge/html_report.py",
        ),
        ("Scene artifacts", "SCENE_ARTIFACT_SCHEMA_VERSION", "src/worldforge/scene_artifacts.py"),
        (
            "Live smoke evidence registry",
            "LIVE_SMOKE_EVIDENCE_SCHEMA_VERSION",
            "src/worldforge/live_smoke_evidence.py",
        ),
    )
    for row_name, schema_signal, owner_signal in required_rows:
        assert row_name in artifact_schemas
        assert schema_signal in artifact_schemas
        assert owner_signal in artifact_schemas

    exported_schema_symbols = [
        line.split('"')[1]
        for line in init_exports.splitlines()
        if line.strip().startswith('"') and "_SCHEMA_VERSION" in line
    ]
    assert exported_schema_symbols
    for symbol in exported_schema_symbols:
        assert symbol in artifact_schemas

    for migration_signal in (
        "Additive optional field",
        "Breaking rename, removal, or type change",
        "Renderer-only layout change",
        "Security or redaction fix",
        "Do not silently coerce invalid persisted state",
    ):
        assert migration_signal in artifact_schemas


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
        "docs/src/task-starters.md",
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
        "Roadmap Expansion 2",
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


def test_demo_showcase_docs_cover_issues_189_to_198_and_237_contract() -> None:
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
        ("external-provider-package", 237),
        ("custom-evaluation-suite", 238),
        ("policy-score-candidate-lab", 239),
        ("fixture-drift-review", 240),
        ("capability-negotiation-preflight", 241),
        ("embodied-policy-replay-comparison", 242),
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
        "entry-point discovery",
        "failure-gallery",
        "raw action preservation",
        "intended-update",
        "physical-fidelity",
        "fallback workflows",
        "missing-dependency",
        "cross-provider action conversion",
        "controller safety",
    ):
        assert boundary in showcase_docs or boundary in cookbook

    external_docs = (ROOT / "docs/src/external-providers.md").read_text(encoding="utf-8")
    provider_authoring = (ROOT / "docs/src/provider-authoring-guide.md").read_text(encoding="utf-8")
    roadmap = (ROOT / "docs/src/roadmap-expansion-2.md").read_text(encoding="utf-8")
    assert "external-provider-discovery.json" in external_docs
    assert "external-provider-package" in provider_authoring
    for checkbox in (
        "- [x] Demo proves external package discovery through documented entry points.",
        "- [x] Missing optional dependencies show explicit skip reasons.",
        (
            "- [x] Generated or example package files do not mutate tracked source during normal "
            "demo runs."
        ),
        "- [x] Docs link the demo from external provider and provider authoring pages.",
    ):
        assert checkbox in roadmap
    for checkbox in (
        "- [x] Walkthrough runs in a clean checkout without credentials or optional runtimes.",
        "- [x] Custom suite output includes provenance and failure-gallery behavior.",
        "- [x] Docs explain deterministic contract-signal framing.",
        "- [x] Tests cover the walkthrough artifact set.",
    ):
        assert checkbox in roadmap
    for checkbox in (
        "- [x] Lab demonstrates candidate generation through score and policy+score planning.",
        "- [x] Invalid candidate bounds and translator-missing cases are visible and tested.",
        "- [x] Docs explain how prepared-host robotics runs differ from the lab.",
        "- [x] Output artifacts are safe to attach.",
    ):
        assert checkbox in roadmap
    for checkbox in (
        (
            "- [x] Walkthrough distinguishes missing fixture, digest mismatch, schema change, and "
            "unsafe path."
        ),
        "- [x] Approved update path is explicit and reviewable.",
        "- [x] Docs link from testing and provider authoring pages.",
        "- [x] Tests cover the demo without changing tracked fixtures.",
    ):
        assert checkbox in roadmap
    fixtures_doc = (ROOT / "docs/src/fixtures.md").read_text(encoding="utf-8")
    assert "fixture-drift-review" in fixtures_doc
    assert "fixture-drift-review" in provider_authoring

    capability_docs = (ROOT / "docs/src/capability-negotiation.md").read_text(encoding="utf-8")
    capability_tests = (ROOT / "tests/test_capability_negotiation.py").read_text(encoding="utf-8")
    for checkbox in (
        "- [x] Demo runs checkout-safe and covers at least five workflow shapes.",
        "- [x] Reports name the exact provider/capability slot that blocks a workflow.",
        "- [x] Docs route users to negotiation before prepared-host smokes.",
        "- [x] Tests cover the demo report fixtures.",
    ):
        assert checkbox in roadmap
    assert "capability-negotiation-preflight" in capability_docs
    assert "test_capability_negotiation_preflight_demo_preserves_blockers" in capability_tests

    demo_tests = (ROOT / "tests/test_demo_showcases.py").read_text(encoding="utf-8")
    for checkbox in (
        (
            "- [x] Replay compares provider policy contracts without normalizing away "
            "provider-specific fields."
        ),
        "- [x] Missing translator behavior is explicit and tested.",
        "- [x] Docs explain prepared-host live-smoke follow-ups for each provider.",
        "- [x] The comparison artifact is safe to attach.",
    ):
        assert checkbox in roadmap
    assert "embodied-policy-replay-comparison" in demo_tests
    assert "raw_tensor_shapes" in demo_tests
    assert "missing_translator_checks" in demo_tests

    for provider_doc in (
        "docs/src/api/python.md",
        "docs/src/providers/lerobot.md",
        "docs/src/providers/gr00t.md",
        "docs/src/providers/leworldmodel.md",
        "docs/src/robotics-showcase.md",
    ):
        text = (ROOT / provider_doc).read_text(encoding="utf-8")
        assert "policy-score-candidate-lab" in text

    for provider_doc in (
        "docs/src/providers/lerobot.md",
        "docs/src/providers/gr00t.md",
        "docs/src/providers/cosmos-policy.md",
    ):
        text = (ROOT / provider_doc).read_text(encoding="utf-8")
        assert "embodied-policy-replay-comparison" in text


def test_provider_lifecycle_docs_cover_issue_247_contract() -> None:
    authoring = (ROOT / "docs/src/provider-authoring-guide.md").read_text(encoding="utf-8")
    operations = (ROOT / "docs/src/operations.md").read_text(encoding="utf-8")
    api = (ROOT / "docs/src/api/python.md").read_text(encoding="utf-8")
    roadmap = (ROOT / "docs/src/roadmap-expansion-2.md").read_text(encoding="utf-8")
    changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    models = (ROOT / "src/worldforge/models.py").read_text(encoding="utf-8")
    base = (ROOT / "src/worldforge/providers/base.py").read_text(encoding="utf-8")
    observable = (ROOT / "src/worldforge/providers/observable.py").read_text(encoding="utf-8")
    provider_tests = (ROOT / "tests/test_provider_profiles.py").read_text(encoding="utf-8")

    for required in (
        "ProviderLifecycleResult",
        "ProviderLifecycleStatus",
        "`preflight`, `warmup`, and `teardown`",
        "The supported statuses are `no-op`",
        "`teardown-failed`",
        "missing required\nconfiguration reports `skipped`",
        "without changing their capability\nmethods",
        "worldforge provider info gr00t --format json",
    ):
        assert required in authoring

    for required in (
        "forge.provider_lifecycle_status(name).ready",
        "lifecycle preflight is ready or no-op",
        "`teardown-failed`",
        "`skipped` is the expected result",
    ):
        assert required in operations

    assert "provider_lifecycle_status(...)" in api
    assert "lifecycle readiness and skip reasons" in changelog
    for checkbox in (
        "- [x] Providers can implement lifecycle hooks",
        "- [x] Diagnostics report lifecycle readiness and skip reasons.",
        "- [x] Hooks are safe for missing optional dependencies.",
        "- [x] Tests cover no-op, ready, skipped, failed, and teardown-failed states.",
    ):
        assert checkbox in roadmap

    for implementation_signal in (
        "PROVIDER_LIFECYCLE_HOOKS",
        "PROVIDER_LIFECYCLE_STATUSES",
        "class ProviderLifecycleResult",
        "class ProviderLifecycleStatus",
    ):
        assert implementation_signal in models
    for implementation_signal in (
        "def preflight",
        "def warmup",
        "def teardown",
        "build_provider_lifecycle_status",
    ):
        assert implementation_signal in base
        assert implementation_signal in observable
    for test_signal in (
        "test_provider_lifecycle_status_covers_noop_ready_skipped_failed_and_teardown",
        "test_doctor_report_includes_lifecycle_readiness_and_skip_reasons",
        "_LifecycleReadyReasoner",
    ):
        assert test_signal in provider_tests


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

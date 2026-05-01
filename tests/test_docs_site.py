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


def test_genie_scaffold_docs_record_runtime_contract_defer_decision() -> None:
    provider_page = (ROOT / "docs/src/providers/genie.md").read_text(encoding="utf-8")
    provider_index = (ROOT / "docs/src/providers/README.md").read_text(encoding="utf-8")
    summary = (ROOT / "docs/src/SUMMARY.md").read_text(encoding="utf-8")

    assert "Status: scaffold" in provider_page
    assert "Decision date: 2026-05-01" in provider_page
    assert "Project Genie announcement" in provider_page
    assert "not a supported automation API" in provider_page
    assert "must not present deterministic local surrogate behavior" in provider_page
    assert "fixture-backed parser tests" in provider_page
    assert "sanitized `run_manifest.json`" in provider_page
    assert "| [`genie`](./genie.md) | `scaffold` | scaffold | `GENIE_API_KEY` |" in provider_index
    assert "[Genie](./providers/genie.md)" in summary

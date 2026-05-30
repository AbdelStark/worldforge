"""Fixture-backed provider failure gallery artifacts."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from worldforge.artifact_io import write_json_artifact as _write_json
from worldforge.models import JSONDict

PROVIDER_FAILURE_GALLERY_CLAIM_BOUNDARY = (
    "Fixture-backed provider failure gallery only; it does not call paid providers, "
    "install optional runtimes, store secrets, or preserve signed URLs."
)

PROVIDER_FAILURE_GALLERY_SUMMARY = (
    "Built a fixture-backed provider failure mode gallery with expected events, errors, "
    "safe artifacts, owners, and first triage commands."
)

PROVIDER_FAILURE_GALLERY_FIRST_TRIAGE_STEP = (
    "Find the matching gallery row, run its first triage command, and attach only the "
    "listed safe artifacts."
)


@dataclass(frozen=True, slots=True)
class ProviderFailureGallerySpec:
    entry_id: str
    provider: str
    failure_mode: str
    source: str
    expected_event: str
    expected_error: str
    expected_artifact: str
    owner: str
    first_triage_command: str
    first_triage_step: str
    safe_artifact_behavior: str


PROVIDER_FAILURE_GALLERY_SPECS = (
    ProviderFailureGallerySpec(
        entry_id="mock-invalid-prediction-state",
        provider="mock-contract",
        failure_mode="invalid prediction state",
        source="tests/test_provider_contracts.py::test_provider_contract_uses_explicit_failure_for_invalid_prediction_state",
        expected_event="none; contract helper rejects the returned prediction payload",
        expected_error="invalid world state",
        expected_artifact="provider contract JSON with a failed capability-contract row",
        owner="adapter contributor",
        first_triage_command="uv run pytest tests/test_provider_contracts.py -q",
        first_triage_step=(
            "Inspect the failed contract row before changing the provider payload schema."
        ),
        safe_artifact_behavior="Attach the contract JSON or Markdown report only.",
    ),
    ProviderFailureGallerySpec(
        entry_id="provider-event-secret-material",
        provider="provider-events",
        failure_mode="unsafe provider event metadata",
        source="tests/test_provider_contracts.py::test_provider_event_conformance_helper_rejects_secret_material",
        expected_event="ProviderEvent rejected before unsafe metadata reaches an event sink",
        expected_error="secret material",
        expected_artifact="redacted conformance failure; raw provider event stays local-only",
        owner="adapter contributor and security reviewer",
        first_triage_command="uv run pytest tests/test_provider_contracts.py -q",
        first_triage_step=(
            "Remove secret-shaped metadata and preserve only sanitized provider events."
        ),
        safe_artifact_behavior="Do not attach raw event logs captured before redaction.",
    ),
    ProviderFailureGallerySpec(
        entry_id="cosmos-malformed-health",
        provider="cosmos",
        failure_mode="malformed health response",
        source="tests/fixtures/providers/cosmos_health_malformed.json",
        expected_event="healthcheck failure details on ProviderHealth",
        expected_error="healthcheck response field 'status'",
        expected_artifact="provider health JSON with sanitized details",
        owner="adapter maintainer",
        first_triage_command="uv run worldforge provider health cosmos",
        first_triage_step="Compare the health response shape with docs/src/providers/cosmos.md.",
        safe_artifact_behavior="Attach health JSON only after checking host names.",
    ),
    ProviderFailureGallerySpec(
        entry_id="cosmos-generation-unauthorized",
        provider="cosmos",
        failure_mode="remote authentication failure",
        source="tests/test_remote_video_providers.py::test_cosmos_provider_events_cover_auth_failures_and_timeouts",
        expected_event="generation request failure status_code=401 target=/v1/infer",
        expected_error="generation request failed with status 401",
        expected_artifact="redacted provider-events.jsonl",
        owner="host runtime owner",
        first_triage_command="uv run worldforge provider info cosmos",
        first_triage_step="Check credential presence through config_summary; never paste tokens.",
        safe_artifact_behavior="Attach only redacted provider events or issue bundles.",
    ),
    ProviderFailureGallerySpec(
        entry_id="cosmos-generation-timeout",
        provider="cosmos",
        failure_mode="retry exhaustion or timeout",
        source="tests/test_remote_video_providers.py::test_cosmos_provider_events_cover_auth_failures_and_timeouts",
        expected_event="generation request failure target=/v1/infer",
        expected_error="failed after 1 attempt",
        expected_artifact="provider-events.jsonl with operation, phase, and target",
        owner="host runtime owner",
        first_triage_command=(
            "jq 'select(.phase==\"failure\")' .worldforge/runs/<run-id>/logs/provider-events.jsonl"
        ),
        first_triage_step="Inspect timeout and retry policy before increasing request budgets.",
        safe_artifact_behavior="Attach sanitized event rows without raw request bodies.",
    ),
    ProviderFailureGallerySpec(
        entry_id="runway-missing-task-id",
        provider="runway",
        failure_mode="malformed task creation response",
        source="tests/fixtures/providers/runway_create_missing_id.json",
        expected_event="generation request parser failure after create response",
        expected_error="field 'id'",
        expected_artifact="fixture-backed parser error report",
        owner="adapter maintainer",
        first_triage_command="uv run pytest tests/test_remote_video_providers.py -k missing_id -q",
        first_triage_step="Attach the sanitized fixture and fix the parser or docs contract.",
        safe_artifact_behavior="Attach the tiny JSON fixture; do not attach raw provider logs.",
    ),
    ProviderFailureGallerySpec(
        entry_id="runway-expired-artifact",
        provider="runway",
        failure_mode="expired generated artifact",
        source="tests/test_remote_video_providers.py::test_runway_provider_rejects_expired_artifacts_and_bad_content_types",
        expected_event="artifact download failure status_code=403",
        expected_error="expired or unavailable",
        expected_artifact="redacted provider event plus regenerated safe artifact path",
        owner="host runtime owner",
        first_triage_command="uv run worldforge provider info runway",
        first_triage_step="Rerun the provider workflow and preserve a fresh issue bundle.",
        safe_artifact_behavior="Do not attach signed or expired artifact URLs.",
    ),
    ProviderFailureGallerySpec(
        entry_id="runway-unsafe-artifact-url",
        provider="runway",
        failure_mode="unsafe artifact URL",
        source="tests/test_remote_video_providers.py::test_runway_provider_rejects_unsafe_artifact_urls",
        expected_event="task poll success followed by artifact URL validation failure",
        expected_error="artifact URL",
        expected_artifact="local-only unsafe URL marker",
        owner="adapter maintainer and security reviewer",
        first_triage_command=(
            "uv run pytest tests/test_remote_video_providers.py -k unsafe_artifact_urls -q"
        ),
        first_triage_step="Reject local-network, credentialed, or non-HTTP artifact URLs.",
        safe_artifact_behavior="Mark unsafe URLs local-only instead of linking them.",
    ),
    ProviderFailureGallerySpec(
        entry_id="optional-runtime-missing-dependency",
        provider="gr00t",
        failure_mode="missing optional runtime package",
        source="src/worldforge/providers/runtime_manifests/gr00t.json",
        expected_event="provider health unhealthy with setup hint",
        expected_error="missing optional dependency",
        expected_artifact="runtime manifest and provider info JSON",
        owner="prepared host owner",
        first_triage_command="uv run worldforge provider info gr00t",
        first_triage_step=(
            "Install or point to the host-owned runtime; do not add it to base dependencies."
        ),
        safe_artifact_behavior="Attach runtime manifest and redacted provider info only.",
    ),
    ProviderFailureGallerySpec(
        entry_id="genie-scaffold-fail-closed",
        provider="genie",
        failure_mode="scaffold provider remains fail-closed",
        source="tests/test_provider_contracts.py::test_configured_scaffold_remote_providers_stay_fail_closed",
        expected_event="none; no provider capability is exercised",
        expected_error="configured scaffold with exercised_operations=[]",
        expected_artifact="provider contract report showing no exercised operations",
        owner="provider maintainer",
        first_triage_command="uv run worldforge provider contract genie --format json",
        first_triage_step="Keep scaffold behavior explicit until a real upstream contract exists.",
        safe_artifact_behavior="Attach contract output; do not claim real Genie integration.",
    ),
)


def build_provider_failure_gallery_entries() -> list[JSONDict]:
    return [_provider_failure_entry(spec) for spec in PROVIDER_FAILURE_GALLERY_SPECS]


def build_provider_failure_gallery_report(entries: list[JSONDict] | None = None) -> JSONDict:
    gallery_entries = build_provider_failure_gallery_entries() if entries is None else list(entries)
    return {
        "schema_version": 1,
        "entry_count": len(gallery_entries),
        "providers": sorted({str(entry["provider"]) for entry in gallery_entries}),
        "entries": gallery_entries,
        "safe_to_attach": True,
        "claim_boundary": PROVIDER_FAILURE_GALLERY_CLAIM_BOUNDARY,
    }


def render_provider_failure_gallery_markdown(report: JSONDict) -> str:
    lines = [
        "# Provider Failure Mode Gallery",
        "",
        str(report["claim_boundary"]),
        "",
        "| ID | Provider | Failure mode | Expected error | Owner | First triage command |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    lines.extend(
        (
            "| "
            f"`{entry['id']}` | `{entry['provider']}` | {entry['failure_mode']} | "
            f"`{entry['expected_error']}` | {entry['owner']} | "
            f"`{entry['first_triage_command']}` |"
        )
        for entry in report["entries"]
    )
    lines.extend(["", "## Safe Artifact Behavior", ""])
    lines.extend(
        f"- `{entry['id']}`: {entry['safe_artifact_behavior']}" for entry in report["entries"]
    )
    lines.append("")
    return "\n".join(lines)


def write_provider_failure_gallery_artifacts(gallery_dir: Path) -> tuple[JSONDict, dict[str, str]]:
    gallery_dir.mkdir(parents=True, exist_ok=True)
    report = build_provider_failure_gallery_report()
    json_path = gallery_dir / "provider-failure-gallery.json"
    markdown_path = gallery_dir / "provider-failure-gallery.md"
    _write_json(json_path, report)
    markdown_path.write_text(render_provider_failure_gallery_markdown(report), encoding="utf-8")
    return report, {
        "gallery_json": str(json_path),
        "gallery_markdown": str(markdown_path),
    }


def run_provider_failure_gallery_workflow(workflow_dir: Path) -> JSONDict:
    report, artifact_paths = write_provider_failure_gallery_artifacts(
        workflow_dir / "provider-failure-gallery"
    )
    return {
        "status": "passed",
        "provider": "provider-failure-fixtures",
        "safe_to_attach": True,
        "summary": PROVIDER_FAILURE_GALLERY_SUMMARY,
        "report": report,
        "artifact_paths": artifact_paths,
        "first_triage_step": PROVIDER_FAILURE_GALLERY_FIRST_TRIAGE_STEP,
        "claim_boundary": report["claim_boundary"],
    }


def _provider_failure_entry(spec: ProviderFailureGallerySpec) -> JSONDict:
    return {
        "id": spec.entry_id,
        "provider": spec.provider,
        "failure_mode": spec.failure_mode,
        "source": spec.source,
        "expected_event": spec.expected_event,
        "expected_error": spec.expected_error,
        "expected_artifact": spec.expected_artifact,
        "owner": spec.owner,
        "first_triage_command": spec.first_triage_command,
        "first_triage_step": spec.first_triage_step,
        "safe_artifact_behavior": spec.safe_artifact_behavior,
        "safe_to_attach": True,
    }

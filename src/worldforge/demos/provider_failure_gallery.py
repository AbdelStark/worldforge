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
        entry_id="leworldmodel-score-count-mismatch",
        provider="leworldmodel",
        failure_mode="score count mismatch",
        source="tests/test_leworldmodel_provider.py::test_leworldmodel_provider_rejects_score_count_mismatch",
        expected_event="score provider returns a candidate count that does not match inputs",
        expected_error="returned 2 score(s) for 3 candidate",
        expected_artifact="provider contract JSON with the score failure row",
        owner="score adapter maintainer",
        first_triage_command="uv run pytest tests/test_leworldmodel_provider.py -k score_count -q",
        first_triage_step="Fix runtime score cardinality before changing planner behavior.",
        safe_artifact_behavior="Attach sanitized score metadata; do not attach tensors.",
    ),
    ProviderFailureGallerySpec(
        entry_id="leworldmodel-malformed-score-input",
        provider="leworldmodel",
        failure_mode="malformed score request payload",
        source="tests/test_leworldmodel_provider.py::test_leworldmodel_provider_rejects_malformed_payload_fixtures",
        expected_event="score request rejected before runtime invocation",
        expected_error="four-dimensional",
        expected_artifact="fixture-backed score parser error report",
        owner="score adapter maintainer",
        first_triage_command=(
            "uv run pytest tests/test_leworldmodel_provider.py -k malformed_payload -q"
        ),
        first_triage_step="Compare the payload shape to the LeWorldModel provider docs.",
        safe_artifact_behavior="Attach tiny JSON fixtures only; keep host tensors local.",
    ),
    ProviderFailureGallerySpec(
        entry_id="cosmos-policy-missing-translator",
        provider="cosmos-policy",
        failure_mode="embodied action translator missing",
        source="tests/test_cosmos_policy_provider.py::test_cosmos_policy_requires_translator",
        expected_event="policy provider rejects raw action rows without host translator",
        expected_error="provide action_translator",
        expected_artifact="provider health/config summary plus redacted event row",
        owner="prepared host owner",
        first_triage_command="uv run worldforge provider info cosmos-policy",
        first_triage_step="Provide an explicit action translator for the host embodiment.",
        safe_artifact_behavior="Attach config summaries and shape metadata, not observations.",
    ),
    ProviderFailureGallerySpec(
        entry_id="cosmos-policy-unsafe-base-url",
        provider="cosmos-policy",
        failure_mode="unsafe local/private endpoint",
        source="tests/test_cosmos_policy_provider.py::test_cosmos_policy_blocks_local_base_url_without_opt_in",
        expected_event="provider configuration rejected before request dispatch",
        expected_error="local/private destination",
        expected_artifact="provider config summary with redacted target",
        owner="host runtime owner and security reviewer",
        first_triage_command=(
            "uv run pytest tests/test_cosmos_policy_provider.py -k local_base_url -q"
        ),
        first_triage_step="Use a public endpoint or explicitly opt into trusted local testing.",
        safe_artifact_behavior="Do not attach private host names or bearer tokens.",
    ),
    ProviderFailureGallerySpec(
        entry_id="cosmos-policy-json-numpy-shape",
        provider="cosmos-policy",
        failure_mode="malformed json_numpy action shape",
        source="tests/test_cosmos_policy_provider.py::test_cosmos_policy_rejects_json_numpy_action_dim_before_decoding",
        expected_event="policy response rejected before oversized or mismatched action decoding",
        expected_error="action_dim must be 14",
        expected_artifact="response parser error report with bounded shape metadata",
        owner="policy adapter maintainer",
        first_triage_command=(
            "uv run pytest tests/test_cosmos_policy_provider.py -k json_numpy_action_dim -q"
        ),
        first_triage_step="Fix response shape handling before widening accepted action dimensions.",
        safe_artifact_behavior="Attach bounded shape metadata only; do not attach observations.",
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

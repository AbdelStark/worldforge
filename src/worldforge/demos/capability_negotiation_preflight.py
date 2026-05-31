"""Checkout-safe capability negotiation preflight demo."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from worldforge import ProviderCapabilities, ProviderHealth, WorldForge
from worldforge.artifact_io import write_json_artifact as _write_json
from worldforge.capability_negotiation import CapabilityNegotiationReport, negotiate
from worldforge.models import JSONDict
from worldforge.providers import BaseProvider, ProviderProfileSpec

CAPABILITY_NEGOTIATION_WORKFLOWS = (
    "predict-only",
    "score-only",
    "embed-only",
    "policy-plus-score",
    "evaluation-physics",
)

CAPABILITY_NEGOTIATION_CLEAR_ENV = {
    "LEWORLDMODEL_POLICY": "",
    "LEWM_POLICY": "",
    "LEROBOT_POLICY_PATH": "",
    "LEROBOT_POLICY": "",
    "GROOT_POLICY_HOST": "",
}

CAPABILITY_NOT_REGISTERED_ENV = {"LEWORLDMODEL_POLICY": "demo-policy"}

CAPABILITY_UNSUPPORTED_EXAMPLE: JSONDict = {
    "provider": "demo-unhealthy-embed",
    "capability": "policy",
    "readiness": "unsupported",
    "reason": "provider 'demo-unhealthy-embed' does not advertise capability 'policy'",
}

CAPABILITY_NEGOTIATION_CLAIM_BOUNDARY = (
    "Checkout-safe preflight only; this report does not install dependencies, configure "
    "credentials, or execute fallback workflows."
)

CAPABILITY_NEGOTIATION_SUMMARY = (
    "Preserved capability negotiation reports for ready, missing-config, "
    "missing-dependency, unsupported, and not-registered preflight cases."
)

CAPABILITY_NEGOTIATION_FIRST_TRIAGE_STEP = (
    "Open `capability-negotiation/preflight-report.md` and follow the first "
    "recommended action for the blocked capability slot."
)


@dataclass(frozen=True, slots=True)
class CapabilityNegotiationReports:
    preflight: CapabilityNegotiationReport
    not_registered: CapabilityNegotiationReport


@dataclass(frozen=True, slots=True)
class CapabilityNegotiationPaths:
    reports_dir: Path
    summary: Path
    preflight_json: Path
    preflight_markdown: Path
    not_registered_json: Path


class UnhealthyEmbedProvider(BaseProvider):
    def __init__(self) -> None:
        super().__init__(
            "demo-unhealthy-embed",
            capabilities=ProviderCapabilities(embed=True),
            profile=ProviderProfileSpec(
                description="Demo provider with configured runtime but unhealthy dependency.",
                implementation_status="demo",
                is_local=True,
                deterministic=True,
            ),
        )

    def health(self) -> ProviderHealth:
        return ProviderHealth(
            name=self.name,
            healthy=False,
            latency_ms=0.0,
            details="demo optional runtime dependency is unavailable",
        )


def run_capability_negotiation_preflight_workflow(workflow_dir: Path) -> JSONDict:
    reports = capability_negotiation_reports(workflow_dir)
    paths = capability_negotiation_paths(workflow_dir)
    write_capability_negotiation_artifacts(paths, reports)
    report = capability_negotiation_report(reports)
    _write_json(paths.summary, report)
    return capability_negotiation_result(report, paths)


def capability_negotiation_reports(workflow_dir: Path) -> CapabilityNegotiationReports:
    forge = WorldForge(state_dir=workflow_dir / "worlds", auto_register_remote=False)
    forge.register_provider(UnhealthyEmbedProvider())
    preflight = negotiate(
        CAPABILITY_NEGOTIATION_WORKFLOWS,
        forge=forge,
        environ=CAPABILITY_NEGOTIATION_CLEAR_ENV,
    )
    not_registered_forge = WorldForge(
        state_dir=workflow_dir / "not-registered-worlds",
        auto_register_remote=False,
    )
    not_registered = negotiate(
        ["score-only"],
        forge=not_registered_forge,
        environ=CAPABILITY_NOT_REGISTERED_ENV,
    )
    return CapabilityNegotiationReports(preflight=preflight, not_registered=not_registered)


def capability_negotiation_paths(workflow_dir: Path) -> CapabilityNegotiationPaths:
    reports_dir = workflow_dir / "capability-negotiation"
    reports_dir.mkdir(parents=True, exist_ok=True)
    return CapabilityNegotiationPaths(
        reports_dir=reports_dir,
        summary=workflow_dir / "capability-negotiation-preflight.json",
        preflight_json=reports_dir / "preflight-report.json",
        preflight_markdown=reports_dir / "preflight-report.md",
        not_registered_json=reports_dir / "not-registered-report.json",
    )


def write_capability_negotiation_artifacts(
    paths: CapabilityNegotiationPaths,
    reports: CapabilityNegotiationReports,
) -> None:
    _write_json(paths.preflight_json, reports.preflight.to_dict())
    paths.preflight_markdown.write_text(reports.preflight.to_markdown(), encoding="utf-8")
    _write_json(paths.not_registered_json, reports.not_registered.to_dict())


def capability_negotiation_report(reports: CapabilityNegotiationReports) -> JSONDict:
    return {
        "schema_version": 1,
        "safe_to_attach": True,
        "workflow_shapes": list(CAPABILITY_NEGOTIATION_WORKFLOWS),
        "readiness_values": capability_readiness_values(reports),
        "unsupported_example": dict(CAPABILITY_UNSUPPORTED_EXAMPLE),
        "recommended_actions": capability_recommended_actions(reports.preflight),
        "claim_boundary": CAPABILITY_NEGOTIATION_CLAIM_BOUNDARY,
    }


def capability_readiness_values(reports: CapabilityNegotiationReports) -> list[str]:
    return sorted(
        {
            candidate.readiness
            for report in (reports.preflight, reports.not_registered)
            for workflow in report.workflows
            for requirement in workflow.requirements
            for candidate in requirement.candidates
        }
    )


def capability_recommended_actions(report: CapabilityNegotiationReport) -> list[str]:
    return [action for workflow in report.workflows for action in workflow.recommended_actions]


def capability_negotiation_result(
    report: JSONDict,
    paths: CapabilityNegotiationPaths,
) -> JSONDict:
    return {
        "status": "passed",
        "provider": "capability-negotiation",
        "safe_to_attach": True,
        "summary": CAPABILITY_NEGOTIATION_SUMMARY,
        "report": report,
        "artifact_paths": {
            "summary": str(paths.summary),
            "preflight_json": str(paths.preflight_json),
            "preflight_markdown": str(paths.preflight_markdown),
            "not_registered_json": str(paths.not_registered_json),
        },
        "first_triage_step": CAPABILITY_NEGOTIATION_FIRST_TRIAGE_STEP,
        "claim_boundary": report["claim_boundary"],
    }

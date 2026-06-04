"""Evaluation report rendering and artifact export helpers."""

from __future__ import annotations

import csv
import io
from collections.abc import Sequence

from worldforge.evaluation.failure_gallery import (
    EvaluationFailureGallery,
)
from worldforge.evaluation.failure_gallery import (
    failure_gallery_cases as _failure_gallery_cases,
)
from worldforge.evaluation.results import (
    EVALUATION_CLAIM_BOUNDARY,
    EVALUATION_METRIC_SEMANTICS,
    EvaluationResult,
    ProviderSummary,
)
from worldforge.evaluation.results import (
    required_text as _required_text,
)
from worldforge.models import JSONDict, WorldForgeError, average, dump_json
from worldforge.provenance import ProvenanceEnvelope
from worldforge.workflow_trace import WorkflowTrace


def _provenance_markdown_lines(provenance: ProvenanceEnvelope | None) -> list[str]:
    """Render the report-level provenance section for Markdown artifacts."""

    if provenance is None:
        return []
    return [
        "## Provenance",
        "",
        *_required_provenance_markdown_lines(provenance),
        *_optional_provenance_markdown_lines(provenance),
        "",
    ]


def _required_provenance_markdown_lines(provenance: ProvenanceEnvelope) -> list[str]:
    return [
        f"- WorldForge version: {provenance.worldforge_version}",
        f"- Suite version: {provenance.suite_version}",
        f"- Created at: {provenance.created_at}",
        f"- Providers: {_joined_or_dash(provenance.providers)}",
        f"- Capabilities: {_joined_or_dash(provenance.capabilities)}",
        f"- Event count: {provenance.event_count}",
        f"- Input digest: {provenance.input_digest or '-'}",
        f"- Result digest: {provenance.result_digest or '-'}",
    ]


def _optional_provenance_markdown_lines(provenance: ProvenanceEnvelope) -> list[str]:
    return [
        line
        for line in (
            _runtime_manifest_markdown_line(provenance),
            _budget_file_markdown_line(provenance),
            _dataset_manifests_markdown_line(provenance),
            _command_markdown_line(provenance),
            _notes_markdown_line(provenance),
        )
        if line is not None
    ]


def _joined_or_dash(values: Sequence[str]) -> str:
    return ", ".join(values) or "-"


def _runtime_manifest_markdown_line(provenance: ProvenanceEnvelope) -> str | None:
    if provenance.runtime_manifests:
        manifests = ", ".join(
            f"{provider}={manifest_id}"
            for provider, manifest_id in sorted(provenance.runtime_manifests.items())
        )
        return f"- Runtime manifests: {manifests}"
    return None


def _budget_file_markdown_line(provenance: ProvenanceEnvelope) -> str | None:
    if provenance.budget_file is not None:
        return f"- Budget file: {provenance.budget_file['path']}"
    return None


def _dataset_manifests_markdown_line(provenance: ProvenanceEnvelope) -> str | None:
    if provenance.dataset_manifests:
        manifests = ", ".join(
            f"{ref['id']} ({ref['sha256']})" for ref in provenance.dataset_manifests
        )
        return f"- Dataset manifests: {manifests}"
    return None


def _command_markdown_line(provenance: ProvenanceEnvelope) -> str | None:
    if provenance.command:
        return f"- Command: `{' '.join(provenance.command)}`"
    return None


def _notes_markdown_line(provenance: ProvenanceEnvelope) -> str | None:
    if provenance.notes:
        return f"- Notes: {provenance.notes}"
    return None


def _evaluation_report_results(
    results: Sequence[EvaluationResult],
    *,
    suite_id: str,
    suite: str,
) -> list[EvaluationResult]:
    materialized = list(results)
    if not all(isinstance(result, EvaluationResult) for result in materialized):
        raise WorldForgeError("EvaluationReport results must contain only EvaluationResult.")
    for result in materialized:
        _check_evaluation_report_result_scope(result, suite_id=suite_id, suite=suite)
    return materialized


def _check_evaluation_report_result_scope(
    result: EvaluationResult,
    *,
    suite_id: str,
    suite: str,
) -> None:
    if result.suite_id != suite_id:
        raise WorldForgeError(
            "EvaluationReport results must share the report's suite_id "
            f"(got '{result.suite_id}', expected '{suite_id}')."
        )
    if result.suite != suite:
        raise WorldForgeError(
            "EvaluationReport results must share the report's suite name "
            f"(got '{result.suite}', expected '{suite}')."
        )


def _evaluation_report_provenance(
    provenance: ProvenanceEnvelope | None,
    *,
    suite_id: str,
) -> ProvenanceEnvelope | None:
    if provenance is None:
        return None
    if not isinstance(provenance, ProvenanceEnvelope):
        raise WorldForgeError("EvaluationReport provenance must be a ProvenanceEnvelope or None.")
    if provenance.kind != "evaluation":
        raise WorldForgeError("EvaluationReport provenance must have kind='evaluation'.")
    if provenance.suite_id != suite_id:
        raise WorldForgeError(
            "EvaluationReport provenance suite_id must match the report's suite_id."
        )
    return provenance


def _evaluation_report_workflow_trace(
    workflow_trace: WorkflowTrace | JSONDict | None,
) -> WorkflowTrace | None:
    if workflow_trace is None:
        return None
    if isinstance(workflow_trace, WorkflowTrace):
        return workflow_trace
    if isinstance(workflow_trace, dict):
        return WorkflowTrace.from_dict(workflow_trace)
    raise WorldForgeError(
        "EvaluationReport workflow_trace must be a WorkflowTrace, JSON object, or None."
    )


class EvaluationReport:
    """Materialized evaluation report with export helpers."""

    def __init__(
        self,
        suite_id: str,
        suite: str,
        results: Sequence[EvaluationResult],
        *,
        provenance: ProvenanceEnvelope | None = None,
        workflow_trace: WorkflowTrace | JSONDict | None = None,
        claim_boundary: str = EVALUATION_CLAIM_BOUNDARY,
        metric_semantics: str = EVALUATION_METRIC_SEMANTICS,
    ) -> None:
        self.suite_id = _required_text(suite_id, name="EvaluationReport suite_id")
        self.suite = _required_text(suite, name="EvaluationReport suite")
        self.claim_boundary = _required_text(
            claim_boundary,
            name="EvaluationReport claim_boundary",
        )
        self.metric_semantics = _required_text(
            metric_semantics,
            name="EvaluationReport metric_semantics",
        )
        self.results = _evaluation_report_results(
            results,
            suite_id=self.suite_id,
            suite=self.suite,
        )
        self.provider_summaries = self._build_provider_summaries()
        self.provenance = _evaluation_report_provenance(
            provenance,
            suite_id=self.suite_id,
        )
        self.workflow_trace = _evaluation_report_workflow_trace(workflow_trace)

    def _build_provider_summaries(self) -> list[ProviderSummary]:
        provider_names = sorted({result.provider for result in self.results})
        summaries: list[ProviderSummary] = []
        for provider in provider_names:
            provider_results = [result for result in self.results if result.provider == provider]
            passed_count = sum(1 for result in provider_results if result.passed)
            summaries.append(
                ProviderSummary(
                    provider=provider,
                    average_score=average(result.score for result in provider_results),
                    scenario_count=len(provider_results),
                    passed_scenario_count=passed_count,
                    failed_scenario_count=len(provider_results) - passed_count,
                )
            )
        return summaries

    def to_dict(self) -> JSONDict:
        failure_gallery = self.failure_gallery()
        payload: JSONDict = {
            "suite_id": self.suite_id,
            "suite": self.suite,
            "claim_boundary": self.claim_boundary,
            "metric_semantics": self.metric_semantics,
            "provider_summaries": [summary.to_dict() for summary in self.provider_summaries],
            "results": [result.to_dict() for result in self.results],
        }
        if failure_gallery.case_count:
            payload["failure_gallery"] = failure_gallery.to_dict()
        if self.provenance is not None:
            payload["provenance"] = self.provenance.to_dict()
        if self.workflow_trace is not None:
            payload["workflow_trace"] = self.workflow_trace.to_dict()
        return payload

    def to_markdown(self) -> str:
        lines = [
            "# Evaluation Report",
            "",
            f"Suite: {self.suite} ({self.suite_id})",
            "",
            f"Claim boundary: {self.claim_boundary}",
            f"Metric semantics: {self.metric_semantics}",
            "",
        ]
        lines.extend(_provenance_markdown_lines(self.provenance))
        lines.extend(
            [
                "| provider | average_score | passed | scenarios |",
                "| --- | ---: | ---: | ---: |",
            ]
        )
        lines.extend(
            (
                f"| {summary.provider} | {summary.average_score:.2f} | "
                f"{summary.passed_scenario_count}/{summary.scenario_count} | "
                f"{summary.scenario_count} |"
            )
            for summary in self.provider_summaries
        )

        lines.extend(
            [
                "",
                "| provider | scenario | score | passed |",
                "| --- | --- | ---: | ---: |",
            ]
        )
        lines.extend(
            (
                f"| {result.provider} | {result.scenario} | {result.score:.2f} | "
                f"{'yes' if result.passed else 'no'} |"
            )
            for result in self.results
        )
        failure_gallery = self.failure_gallery()
        if failure_gallery.case_count:
            lines.extend(["", "## Failure Gallery", ""])
            lines.extend(failure_gallery.to_markdown(include_title=False).splitlines())
        if self.workflow_trace is not None:
            lines.extend(["", "## Workflow Trace", ""])
            lines.extend(self.workflow_trace.to_markdown().splitlines()[2:])
        return "\n".join(lines)

    def to_csv(self) -> str:
        buffer = io.StringIO()
        writer = csv.DictWriter(
            buffer,
            fieldnames=[
                "suite_id",
                "suite",
                "provider",
                "scenario",
                "score",
                "passed",
                "metrics_json",
            ],
        )
        writer.writeheader()
        for result in self.results:
            writer.writerow(
                {
                    "suite_id": self.suite_id,
                    "suite": self.suite,
                    "provider": result.provider,
                    "scenario": result.scenario,
                    "score": f"{result.score:.4f}",
                    "passed": str(result.passed).lower(),
                    "metrics_json": dump_json(result.metrics),
                }
            )
        return buffer.getvalue().strip()

    def to_json(self) -> str:
        return dump_json(self.to_dict())

    def failure_gallery(
        self,
        *,
        max_cases_per_provider: int | None = 3,
    ) -> EvaluationFailureGallery:
        """Return representative failed scenarios for issue triage."""

        return EvaluationFailureGallery(
            suite_id=self.suite_id,
            suite=self.suite,
            cases=_failure_gallery_cases(
                self.results,
                max_cases_per_provider=max_cases_per_provider,
            ),
            source_input_digest=self.provenance.input_digest if self.provenance else None,
            source_result_digest=self.provenance.result_digest if self.provenance else None,
            suite_version=self.provenance.suite_version if self.provenance else None,
            claim_boundary=self.claim_boundary,
            metric_semantics=self.metric_semantics,
        )

    def to_html(self) -> str:
        from worldforge.html_report import render_evaluation_html

        return render_evaluation_html(self)

    def artifacts(self) -> dict[str, str]:
        failure_gallery = self.failure_gallery(max_cases_per_provider=None)
        return {
            "json": self.to_json(),
            "markdown": self.to_markdown(),
            "csv": self.to_csv(),
            "html": self.to_html(),
            "failure_gallery.json": failure_gallery.to_json(),
            "failure_gallery.md": failure_gallery.to_markdown(),
            **(
                {
                    "workflow_trace.json": self.workflow_trace.to_json(),
                    "workflow_trace.md": self.workflow_trace.to_markdown(),
                }
                if self.workflow_trace is not None
                else {}
            ),
        }


__all__ = ["EvaluationReport"]

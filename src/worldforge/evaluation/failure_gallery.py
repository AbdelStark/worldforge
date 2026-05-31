"""Sanitized evaluation failure-gallery artifacts."""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass, field
from urllib.parse import urlsplit

from worldforge.evaluation.results import (
    EVALUATION_CLAIM_BOUNDARY,
    EVALUATION_METRIC_SEMANTICS,
    EvaluationResult,
    required_text,
)
from worldforge.models import (
    JSONDict,
    WorldForgeError,
    _redact_observable_value,
    dump_json,
    require_json_dict,
    require_probability,
)

EVALUATION_FAILURE_GALLERY_SCHEMA_VERSION = 1

_HOST_LOCAL_PATH_PATTERN = re.compile(
    r"(^|[\s=:])((?:/Users|/private|/tmp)/[^\s,;]+|~/[^\s,;]+|[A-Za-z]:[\\/][^\s,;]+)"
)
_SENSITIVE_GALLERY_KEY_PATTERN = re.compile(
    r"(api[_-]?key|authorization|bearer|credential|password|secret|signature|signed[_-]?url|token)",
    re.IGNORECASE,
)
_CONTRACT_NOTES: dict[tuple[str, str], str] = {
    ("physics", "object-stability"): (
        "A seeded object should remain near its starting pose under a no-op prediction, with "
        "valid physics/confidence scores."
    ),
    ("physics", "action-response"): (
        "A seeded object should move toward the requested target pose and report coherent "
        "prediction metrics."
    ),
    ("planning", "object-relocation"): (
        "The planner should produce at least one executable action that relocates the selected "
        "object toward the typed target."
    ),
    ("planning", "object-neighbor-placement"): (
        "The planner should place the selected object near the reference object without drifting "
        "the reference."
    ),
    ("planning", "object-swap"): (
        "The planner should swap two seeded objects with the expected two-action relational plan."
    ),
    ("planning", "object-spawn"): (
        "The planner should execute a simple spawn goal and increase the object count."
    ),
}


@dataclass(slots=True)
class EvaluationFailureCase:
    """Representative failed evaluation scenario for issue triage."""

    fixture_id: str
    suite_id: str
    suite: str
    scenario: str
    provider: str
    score: float
    expected_contract_notes: str
    observed_result: str
    metrics_preview: JSONDict = field(default_factory=dict)
    triage_steps: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        self.fixture_id = required_text(
            self.fixture_id,
            name="EvaluationFailureCase fixture_id",
        )
        self.suite_id = required_text(self.suite_id, name="EvaluationFailureCase suite_id")
        self.suite = required_text(self.suite, name="EvaluationFailureCase suite")
        self.scenario = required_text(self.scenario, name="EvaluationFailureCase scenario")
        self.provider = required_text(self.provider, name="EvaluationFailureCase provider")
        self.score = require_probability(self.score, name="EvaluationFailureCase score")
        self.expected_contract_notes = required_text(
            self.expected_contract_notes,
            name="EvaluationFailureCase expected_contract_notes",
        )
        self.observed_result = required_text(
            self.observed_result,
            name="EvaluationFailureCase observed_result",
        )
        self.metrics_preview = require_json_dict(
            self.metrics_preview,
            name="EvaluationFailureCase metrics_preview",
        )
        if not isinstance(self.triage_steps, tuple) or not all(
            isinstance(step, str) and step.strip() for step in self.triage_steps
        ):
            raise WorldForgeError(
                "EvaluationFailureCase triage_steps must be a tuple of non-empty strings."
            )

    def to_dict(self) -> JSONDict:
        return {
            "fixture_id": self.fixture_id,
            "suite_id": self.suite_id,
            "suite": self.suite,
            "scenario": self.scenario,
            "provider": self.provider,
            "score": self.score,
            "passed": False,
            "expected_contract_notes": self.expected_contract_notes,
            "observed_result": self.observed_result,
            "metrics_preview": dict(self.metrics_preview),
            "triage_steps": list(self.triage_steps),
        }


@dataclass(slots=True)
class EvaluationFailureGallery:
    """JSON and Markdown export for failed evaluation scenarios."""

    suite_id: str
    suite: str
    cases: list[EvaluationFailureCase] = field(default_factory=list)
    source_input_digest: str | None = None
    source_result_digest: str | None = None
    suite_version: str | None = None
    claim_boundary: str = EVALUATION_CLAIM_BOUNDARY
    metric_semantics: str = EVALUATION_METRIC_SEMANTICS

    def __post_init__(self) -> None:
        self.suite_id = required_text(self.suite_id, name="EvaluationFailureGallery suite_id")
        self.suite = required_text(self.suite, name="EvaluationFailureGallery suite")
        if not isinstance(self.cases, list) or not all(
            isinstance(case, EvaluationFailureCase) for case in self.cases
        ):
            raise WorldForgeError(
                "EvaluationFailureGallery cases must contain only EvaluationFailureCase."
            )
        self.source_input_digest = (
            required_text(
                self.source_input_digest,
                name="EvaluationFailureGallery source_input_digest",
            )
            if self.source_input_digest is not None
            else None
        )
        self.source_result_digest = (
            required_text(
                self.source_result_digest,
                name="EvaluationFailureGallery source_result_digest",
            )
            if self.source_result_digest is not None
            else None
        )
        self.suite_version = (
            required_text(self.suite_version, name="EvaluationFailureGallery suite_version")
            if self.suite_version is not None
            else None
        )
        self.claim_boundary = required_text(
            self.claim_boundary,
            name="EvaluationFailureGallery claim_boundary",
        )
        self.metric_semantics = required_text(
            self.metric_semantics,
            name="EvaluationFailureGallery metric_semantics",
        )

    @property
    def case_count(self) -> int:
        return len(self.cases)

    def to_dict(self) -> JSONDict:
        payload: JSONDict = {
            "schema_version": EVALUATION_FAILURE_GALLERY_SCHEMA_VERSION,
            "suite_id": self.suite_id,
            "suite": self.suite,
            "case_count": self.case_count,
            "claim_boundary": self.claim_boundary,
            "metric_semantics": self.metric_semantics,
            "source_input_digest": self.source_input_digest,
            "source_result_digest": self.source_result_digest,
            "suite_version": self.suite_version,
            "cases": [case.to_dict() for case in self.cases],
        }
        dump_json(payload)
        return payload

    def to_json(self) -> str:
        return dump_json(self.to_dict())

    def to_markdown(self, *, include_title: bool = True) -> str:
        lines: list[str] = []
        if include_title:
            lines.extend(["# Evaluation Failure Gallery", ""])
        lines.extend(
            [
                f"Suite: {self.suite} ({self.suite_id})",
                f"Claim boundary: {self.claim_boundary}",
                f"Metric semantics: {self.metric_semantics}",
                f"Cases: {self.case_count}",
            ]
        )
        if self.source_input_digest:
            lines.append(f"Source input digest: `{self.source_input_digest}`")
        if self.source_result_digest:
            lines.append(f"Source result digest: `{self.source_result_digest}`")
        lines.append("")
        if not self.cases:
            lines.append("No failed evaluation cases.")
            return "\n".join(lines)

        lines.extend(
            [
                "| fixture | provider | scenario | score |",
                "| --- | --- | --- | ---: |",
            ]
        )
        lines.extend(
            f"| `{case.fixture_id}` | {case.provider} | {case.scenario} | {case.score:.2f} |"
            for case in self.cases
        )
        for case in self.cases:
            lines.extend(
                [
                    "",
                    f"### {case.fixture_id} / {case.provider}",
                    "",
                    f"- Expected: {case.expected_contract_notes}",
                    f"- Observed: {case.observed_result}",
                    "- Triage:",
                ]
            )
            lines.extend(f"  - {step}" for step in case.triage_steps)
            lines.extend(
                [
                    "- Metrics preview:",
                    "",
                    "```json",
                    dump_json(case.metrics_preview),
                    "```",
                ]
            )
        return "\n".join(lines)


def failure_gallery_cases(
    results: Sequence[EvaluationResult],
    *,
    max_cases_per_provider: int | None,
) -> list[EvaluationFailureCase]:
    _validate_failure_gallery_limit(max_cases_per_provider)
    selected_results = _representative_failure_results(
        results,
        max_cases_per_provider=max_cases_per_provider,
    )
    return [_failure_case_from_result(result) for result in selected_results]


def _failure_case_from_result(result: EvaluationResult) -> EvaluationFailureCase:
    fixture_id = f"evaluation:{result.suite_id}:{result.scenario}"
    return EvaluationFailureCase(
        fixture_id=fixture_id,
        suite_id=result.suite_id,
        suite=result.suite,
        scenario=result.scenario,
        provider=result.provider,
        score=result.score,
        expected_contract_notes=_expected_contract_notes(result),
        observed_result=_observed_result_summary(result),
        metrics_preview=_sanitize_metrics_preview(result.metrics),
        triage_steps=_triage_steps(result),
    )


def _expected_contract_notes(result: EvaluationResult) -> str:
    return _CONTRACT_NOTES.get(
        (result.suite_id, result.scenario),
        (
            "The provider should satisfy the deterministic evaluation contract for "
            f"`{result.suite_id}/{result.scenario}`."
        ),
    )


def _observed_result_summary(result: EvaluationResult) -> str:
    metric_keys = ", ".join(sorted(result.metrics)) or "none"
    return f"score={result.score:.4f}; passed=false; metric keys: {metric_keys}"


def _triage_steps(result: EvaluationResult) -> tuple[str, ...]:
    return (
        (
            "Open the preserved evaluation JSON and confirm its provenance input and result "
            "digests before citing the failure."
        ),
        (
            f"Rerun `uv run worldforge eval --suite {result.suite_id} "
            f"--provider {result.provider} --format json` in a clean checkout."
        ),
        (
            "Inspect the metrics preview against the expected contract note; treat the result as "
            "contract triage, not physical fidelity evidence."
        ),
    )


def _sanitize_metrics_preview(metrics: JSONDict) -> JSONDict:
    sanitized = _gallery_value_preview(metrics, key="metrics")
    if not isinstance(sanitized, dict):
        raise WorldForgeError("Evaluation failure gallery metrics preview must be a JSON object.")
    return sanitized


def _gallery_value_preview(value: object, *, key: str | None = None, depth: int = 0) -> object:
    value = _redact_observable_value(value, key=key)
    if isinstance(value, str):
        return _sanitize_gallery_text(value)
    if isinstance(value, bool | int | float) or value is None:
        return value
    if isinstance(value, list):
        if _should_summarize_sequence(value, key=key, depth=depth):
            return {
                "type": "array",
                "item_count": len(value),
                "nested": any(isinstance(item, list | dict) for item in value),
            }
        return [_gallery_value_preview(item, key=key, depth=depth + 1) for item in value[:8]]
    if isinstance(value, dict):
        if _SENSITIVE_GALLERY_KEY_PATTERN.search(str(key or "")):
            return "[redacted]"
        items = sorted(value.items(), key=lambda item: str(item[0]))
        preview_items = items[:12]
        payload: JSONDict = {
            str(item_key): _gallery_value_preview(
                item_value,
                key=str(item_key),
                depth=depth + 1,
            )
            for item_key, item_value in preview_items
        }
        omitted = len(items) - len(preview_items)
        if omitted > 0:
            payload["_omitted_key_count"] = omitted
        return payload
    return {"type": type(value).__name__, "preview": "non-json value omitted"}


def _sanitize_gallery_text(value: str) -> str:
    stripped = value.strip()
    if not stripped:
        return ""
    try:
        parts = urlsplit(stripped)
    except ValueError:
        parts = None
    if parts is not None and parts.scheme == "file":
        return "[host-local-path]"
    if parts is not None and parts.hostname in {"localhost", "127.0.0.1", "::1"}:
        return "[host-local-url]"
    if _is_host_local_path(stripped):
        return "[host-local-path]"
    return _HOST_LOCAL_PATH_PATTERN.sub(
        lambda match: f"{match.group(1)}[host-local-path]",
        stripped,
    )


def _is_host_local_path(value: str) -> bool:
    return value.startswith(("/Users/", "/private/", "/tmp/", "~/")) or (
        len(value) >= 3 and value[1:3] in {":\\", ":/"}
    )


def _should_summarize_sequence(value: list[object], *, key: str | None, depth: int) -> bool:
    lowered_key = str(key or "").lower()
    return (
        "tensor" in lowered_key
        or "array" in lowered_key
        or depth >= 2
        or len(value) > 8
        or any(isinstance(item, list | dict) for item in value)
    )


def _validate_failure_gallery_limit(max_cases_per_provider: int | None) -> None:
    if max_cases_per_provider is None:
        return
    if not isinstance(max_cases_per_provider, int) or isinstance(max_cases_per_provider, bool):
        raise WorldForgeError("max_cases_per_provider must be a positive integer or None.")
    if max_cases_per_provider <= 0:
        raise WorldForgeError("max_cases_per_provider must be a positive integer or None.")


def _representative_failure_results(
    results: Sequence[EvaluationResult],
    *,
    max_cases_per_provider: int | None,
) -> list[EvaluationResult]:
    grouped = _failure_results_by_provider(results)
    selected: list[EvaluationResult] = []
    for provider in sorted(grouped):
        selected.extend(
            _lowest_score_failures(
                grouped[provider],
                max_cases=max_cases_per_provider,
            )
        )
    return selected


def _failure_results_by_provider(
    results: Sequence[EvaluationResult],
) -> dict[str, list[EvaluationResult]]:
    grouped: dict[str, list[EvaluationResult]] = {}
    for result in results:
        if result.passed:
            continue
        grouped.setdefault(result.provider, []).append(result)
    return grouped


def _lowest_score_failures(
    results: Sequence[EvaluationResult],
    *,
    max_cases: int | None,
) -> list[EvaluationResult]:
    sorted_results = sorted(results, key=lambda result: (result.score, result.scenario))
    if max_cases is None:
        return sorted_results
    return sorted_results[:max_cases]

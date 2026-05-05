"""Evaluation suites and report rendering for WorldForge."""

from __future__ import annotations

import csv
import io
import re
from collections.abc import Callable, Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, ClassVar
from urllib.parse import urlsplit

from worldforge.models import (
    Action,
    BBox,
    GenerationOptions,
    JSONDict,
    Position,
    SceneObject,
    StructuredGoal,
    VideoClip,
    WorldForgeError,
    _redact_observable_value,
    average,
    dump_json,
    require_bool,
    require_finite_number,
    require_json_dict,
    require_non_negative_int,
    require_probability,
)
from worldforge.provenance import (
    EVALUATION_SUITE_CONTRACT_VERSION,
    ProvenanceEnvelope,
    collect_runtime_manifests,
    digest_payload,
)

if TYPE_CHECKING:
    from worldforge.framework import World, WorldForge

EVALUATION_CLAIM_BOUNDARY = (
    "Built-in evaluation suites are deterministic adapter contract checks. Scores are synthetic "
    "workflow signals, not claims of physical fidelity, media quality, safety, or real robot "
    "performance."
)
EVALUATION_METRIC_SEMANTICS = (
    "Scenario scores and pass rates measure whether a provider satisfied the suite's typed "
    "contract under preserved inputs."
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
    ("generation", "text-conditioned-video"): (
        "The provider should return a non-empty prompt-conditioned clip with expected duration, "
        "resolution, and media metadata."
    ),
    ("generation", "image-conditioned-video"): (
        "The provider should return a non-empty image-conditioned clip and preserve conditioning "
        "metadata."
    ),
    ("transfer", "prompt-guided-transfer"): (
        "The provider should return a non-empty transfer clip with requested resolution, FPS, "
        "prompt metadata, and transfer-mode metadata."
    ),
    ("transfer", "reference-guided-transfer"): (
        "The provider should return a transfer clip that records reference-guidance metadata."
    ),
    ("reasoning", "scene-count"): (
        "The provider should answer with the tracked object count and include supporting evidence."
    ),
    ("reasoning", "scene-identity"): (
        "The provider should identify every tracked object id in its answer or evidence."
    ),
}


def _provenance_markdown_lines(provenance: ProvenanceEnvelope | None) -> list[str]:
    """Render the report-level provenance section for Markdown artifacts."""

    if provenance is None:
        return []
    lines = [
        "## Provenance",
        "",
        f"- WorldForge version: {provenance.worldforge_version}",
        f"- Suite version: {provenance.suite_version}",
        f"- Created at: {provenance.created_at}",
        f"- Providers: {', '.join(provenance.providers) or '-'}",
        f"- Capabilities: {', '.join(provenance.capabilities) or '-'}",
        f"- Event count: {provenance.event_count}",
        f"- Input digest: {provenance.input_digest or '-'}",
        f"- Result digest: {provenance.result_digest or '-'}",
    ]
    if provenance.runtime_manifests:
        manifests = ", ".join(
            f"{provider}={manifest_id}"
            for provider, manifest_id in sorted(provenance.runtime_manifests.items())
        )
        lines.append(f"- Runtime manifests: {manifests}")
    if provenance.budget_file is not None:
        lines.append(f"- Budget file: {provenance.budget_file['path']}")
    if provenance.command:
        lines.append(f"- Command: `{' '.join(provenance.command)}`")
    if provenance.notes:
        lines.append(f"- Notes: {provenance.notes}")
    lines.append("")
    return lines


def _clamp_score(value: float) -> float:
    return max(0.0, min(1.0, require_finite_number(value, name="evaluation score")))


def _required_text(value: object, *, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise WorldForgeError(f"{name} must be a non-empty string.")
    return value.strip()


def _distance(a: Position, b: Position) -> float:
    return ((a.x - b.x) ** 2 + (a.y - b.y) ** 2 + (a.z - b.z) ** 2) ** 0.5


def _seed_object(world: World, name: str, position: Position) -> SceneObject:
    existing = next((obj for obj in world.objects() if obj.name == name), None)
    if existing is not None:
        return existing
    obj = SceneObject(
        name,
        position,
        BBox(
            Position(position.x - 0.05, position.y - 0.05, position.z - 0.05),
            Position(position.x + 0.05, position.y + 0.05, position.z + 0.05),
        ),
        is_graspable=True,
    )
    world.add_object(obj)
    return obj


_SAMPLE_IMAGE_DATA_URI = (
    "data:image/png;base64,"
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jq5kAAAAASUVORK5CYII="
)


def _sample_transfer_clip() -> VideoClip:
    return VideoClip(
        frames=[b"worldforge-transfer-seed"],
        fps=8.0,
        resolution=(160, 90),
        duration_seconds=1.0,
        metadata={
            "provider": "worldforge",
            "content_type": "video/mp4",
            "mode": "evaluation-seed",
        },
    )


def _duration_score(*, actual_seconds: float, expected_seconds: float) -> float:
    if expected_seconds <= 0.0:
        return 1.0 if actual_seconds >= 0.0 else 0.0
    return _clamp_score(
        1.0 - min(1.0, abs(actual_seconds - expected_seconds) / max(expected_seconds, 0.001))
    )


def _resolution_score(clip: VideoClip, *, expected: tuple[int, int] | None = None) -> float:
    width, height = clip.resolution
    if width <= 0 or height <= 0:
        return 0.0
    if expected is None:
        return 1.0
    expected_width, expected_height = expected
    deviation = (
        abs(width - expected_width) / max(expected_width, 1)
        + abs(height - expected_height) / max(expected_height, 1)
    ) / 2
    return _clamp_score(1.0 - min(1.0, deviation))


def _fps_score(clip: VideoClip, *, expected_fps: float) -> float:
    return _clamp_score(1.0 - min(1.0, abs(clip.fps - expected_fps) / max(expected_fps, 0.001)))


def _blob_score(clip: VideoClip) -> float:
    return 1.0 if clip.frame_count >= 1 and bool(clip.blob()) else 0.0


def _content_type_score(clip: VideoClip) -> float:
    content_type = clip.content_type()
    return (
        1.0
        if content_type.startswith("video/") or content_type == "application/octet-stream"
        else 0.0
    )


def _prompt_score(clip: VideoClip, *, expected_prompt: str) -> float:
    return 1.0 if clip.metadata.get("prompt") == expected_prompt else 0.0


def _is_image_conditioned(clip: VideoClip) -> bool:
    options = clip.metadata.get("options", {})
    mode = str(clip.metadata.get("mode", "")).lower()
    return (isinstance(options, dict) and bool(options.get("image"))) or "image" in mode


def _is_transfer_clip(clip: VideoClip) -> bool:
    return bool(clip.metadata.get("transfer")) or (
        str(clip.metadata.get("mode", "")).lower() == "video_to_video"
    )


def _reference_count(clip: VideoClip) -> int:
    value = clip.metadata.get("reference_count")
    if value is not None:
        try:
            return int(value)
        except (TypeError, ValueError):
            return 0
    options = clip.metadata.get("options", {})
    if isinstance(options, dict):
        references = options.get("reference_images", [])
        if isinstance(references, list):
            return len(references)
    return 0


@dataclass(slots=True)
class EvaluationScenario:
    """A single scenario inside an evaluation suite."""

    name: str
    description: str
    required_capabilities: tuple[str, ...] = ()


@dataclass(slots=True)
class EvaluationResult:
    """The result for one scenario/provider pair."""

    suite_id: str
    suite: str
    scenario: str
    provider: str
    score: float
    passed: bool
    metrics: JSONDict = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.suite_id = _required_text(self.suite_id, name="EvaluationResult suite_id")
        self.suite = _required_text(self.suite, name="EvaluationResult suite")
        self.scenario = _required_text(self.scenario, name="EvaluationResult scenario")
        self.provider = _required_text(self.provider, name="EvaluationResult provider")
        self.score = require_probability(self.score, name="EvaluationResult score")
        self.passed = require_bool(self.passed, name="EvaluationResult passed")
        self.metrics = require_json_dict(self.metrics, name="EvaluationResult metrics")

    def to_dict(self) -> JSONDict:
        return {
            "suite_id": self.suite_id,
            "suite": self.suite,
            "scenario": self.scenario,
            "provider": self.provider,
            "score": self.score,
            "passed": self.passed,
            "metrics": self.metrics,
        }


@dataclass(slots=True)
class ProviderSummary:
    """Aggregate summary for a provider across a suite run."""

    provider: str
    average_score: float
    scenario_count: int
    passed_scenario_count: int
    failed_scenario_count: int

    def __post_init__(self) -> None:
        self.provider = _required_text(self.provider, name="ProviderSummary provider")
        self.average_score = require_probability(
            self.average_score,
            name="ProviderSummary average_score",
        )
        self.scenario_count = require_non_negative_int(
            self.scenario_count,
            name="ProviderSummary scenario_count",
        )
        self.passed_scenario_count = require_non_negative_int(
            self.passed_scenario_count,
            name="ProviderSummary passed_scenario_count",
        )
        self.failed_scenario_count = require_non_negative_int(
            self.failed_scenario_count,
            name="ProviderSummary failed_scenario_count",
        )
        if self.passed_scenario_count + self.failed_scenario_count != self.scenario_count:
            raise WorldForgeError(
                "ProviderSummary passed and failed scenario counts must sum to scenario_count."
            )

    @property
    def pass_rate(self) -> float:
        if self.scenario_count == 0:
            return 0.0
        return self.passed_scenario_count / self.scenario_count

    def to_dict(self) -> JSONDict:
        return {
            "provider": self.provider,
            "average_score": self.average_score,
            "scenario_count": self.scenario_count,
            "passed_scenario_count": self.passed_scenario_count,
            "failed_scenario_count": self.failed_scenario_count,
            "pass_rate": self.pass_rate,
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
        self.fixture_id = _required_text(
            self.fixture_id,
            name="EvaluationFailureCase fixture_id",
        )
        self.suite_id = _required_text(self.suite_id, name="EvaluationFailureCase suite_id")
        self.suite = _required_text(self.suite, name="EvaluationFailureCase suite")
        self.scenario = _required_text(self.scenario, name="EvaluationFailureCase scenario")
        self.provider = _required_text(self.provider, name="EvaluationFailureCase provider")
        self.score = require_probability(self.score, name="EvaluationFailureCase score")
        self.expected_contract_notes = _required_text(
            self.expected_contract_notes,
            name="EvaluationFailureCase expected_contract_notes",
        )
        self.observed_result = _required_text(
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

    def __post_init__(self) -> None:
        self.suite_id = _required_text(self.suite_id, name="EvaluationFailureGallery suite_id")
        self.suite = _required_text(self.suite, name="EvaluationFailureGallery suite")
        if not isinstance(self.cases, list) or not all(
            isinstance(case, EvaluationFailureCase) for case in self.cases
        ):
            raise WorldForgeError(
                "EvaluationFailureGallery cases must contain only EvaluationFailureCase."
            )
        self.source_input_digest = (
            _required_text(
                self.source_input_digest,
                name="EvaluationFailureGallery source_input_digest",
            )
            if self.source_input_digest is not None
            else None
        )
        self.source_result_digest = (
            _required_text(
                self.source_result_digest,
                name="EvaluationFailureGallery source_result_digest",
            )
            if self.source_result_digest is not None
            else None
        )
        self.suite_version = (
            _required_text(self.suite_version, name="EvaluationFailureGallery suite_version")
            if self.suite_version is not None
            else None
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
            "claim_boundary": EVALUATION_CLAIM_BOUNDARY,
            "metric_semantics": EVALUATION_METRIC_SEMANTICS,
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
                f"Claim boundary: {EVALUATION_CLAIM_BOUNDARY}",
                f"Metric semantics: {EVALUATION_METRIC_SEMANTICS}",
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


class EvaluationReport:
    """Materialized evaluation report with export helpers."""

    def __init__(
        self,
        suite_id: str,
        suite: str,
        results: Sequence[EvaluationResult],
        *,
        provenance: ProvenanceEnvelope | None = None,
    ) -> None:
        self.suite_id = _required_text(suite_id, name="EvaluationReport suite_id")
        self.suite = _required_text(suite, name="EvaluationReport suite")
        self.results = list(results)
        if not all(isinstance(result, EvaluationResult) for result in self.results):
            raise WorldForgeError("EvaluationReport results must contain only EvaluationResult.")
        for result in self.results:
            if result.suite_id != self.suite_id:
                raise WorldForgeError(
                    "EvaluationReport results must share the report's suite_id "
                    f"(got '{result.suite_id}', expected '{self.suite_id}')."
                )
            if result.suite != self.suite:
                raise WorldForgeError(
                    "EvaluationReport results must share the report's suite name "
                    f"(got '{result.suite}', expected '{self.suite}')."
                )
        self.provider_summaries = self._build_provider_summaries()
        if provenance is not None:
            if not isinstance(provenance, ProvenanceEnvelope):
                raise WorldForgeError(
                    "EvaluationReport provenance must be a ProvenanceEnvelope or None."
                )
            if provenance.kind != "evaluation":
                raise WorldForgeError("EvaluationReport provenance must have kind='evaluation'.")
            if provenance.suite_id != self.suite_id:
                raise WorldForgeError(
                    "EvaluationReport provenance suite_id must match the report's suite_id."
                )
        self.provenance = provenance

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
            "claim_boundary": EVALUATION_CLAIM_BOUNDARY,
            "metric_semantics": EVALUATION_METRIC_SEMANTICS,
            "provider_summaries": [summary.to_dict() for summary in self.provider_summaries],
            "results": [result.to_dict() for result in self.results],
        }
        if failure_gallery.case_count:
            payload["failure_gallery"] = failure_gallery.to_dict()
        if self.provenance is not None:
            payload["provenance"] = self.provenance.to_dict()
        return payload

    def to_markdown(self) -> str:
        lines = [
            "# Evaluation Report",
            "",
            f"Suite: {self.suite} ({self.suite_id})",
            "",
            f"Claim boundary: {EVALUATION_CLAIM_BOUNDARY}",
            f"Metric semantics: {EVALUATION_METRIC_SEMANTICS}",
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

        if max_cases_per_provider is not None and (
            isinstance(max_cases_per_provider, bool) or max_cases_per_provider <= 0
        ):
            raise WorldForgeError("max_cases_per_provider must be a positive integer or None.")
        failures = [result for result in self.results if not result.passed]
        grouped: dict[str, list[EvaluationResult]] = {}
        for result in failures:
            grouped.setdefault(result.provider, []).append(result)

        cases: list[EvaluationFailureCase] = []
        for provider in sorted(grouped):
            provider_failures = sorted(
                grouped[provider],
                key=lambda result: (result.score, result.scenario),
            )
            selected = (
                provider_failures
                if max_cases_per_provider is None
                else provider_failures[:max_cases_per_provider]
            )
            cases.extend(_failure_case_from_result(result) for result in selected)
        return EvaluationFailureGallery(
            suite_id=self.suite_id,
            suite=self.suite,
            cases=cases,
            source_input_digest=self.provenance.input_digest if self.provenance else None,
            source_result_digest=self.provenance.result_digest if self.provenance else None,
            suite_version=self.provenance.suite_version if self.provenance else None,
        )

    def artifacts(self) -> dict[str, str]:
        failure_gallery = self.failure_gallery(max_cases_per_provider=None)
        return {
            "json": self.to_json(),
            "markdown": self.to_markdown(),
            "csv": self.to_csv(),
            "failure_gallery.json": failure_gallery.to_json(),
            "failure_gallery.md": failure_gallery.to_markdown(),
        }


class EvaluationSuite:
    """Group of :class:`EvaluationScenario` instances run against a single provider.

    Use :meth:`from_builtin` to construct one of the bundled suites (``generation``,
    ``physics``, ``planning``, ``reasoning``, ``transfer``); construct directly to assemble
    custom scenario sequences. Suites are deterministic adapter-contract checks: a passing
    score asserts the provider returns well-formed payloads, not that it has physical or
    media fidelity.
    """

    def __init__(
        self,
        name: str,
        scenarios: Sequence[EvaluationScenario],
        *,
        suite_id: str | None = None,
    ) -> None:
        self.name = name
        self.scenarios = list(scenarios)
        self.suite_id = suite_id or name.lower().replace(" ", "-")

    @classmethod
    def _builtin_registry(cls) -> dict[str, Callable[[], EvaluationSuite]]:
        return {
            "generation": GenerationEvaluationSuite,
            "physics": PhysicsEvaluationSuite,
            "planning": PlanningEvaluationSuite,
            "reasoning": ReasoningEvaluationSuite,
            "transfer": TransferEvaluationSuite,
        }

    @classmethod
    def builtin_names(cls) -> list[str]:
        """Return the sorted names of every suite that :meth:`from_builtin` accepts."""

        return sorted(cls._builtin_registry())

    @classmethod
    def from_builtin(cls, name: str) -> EvaluationSuite:
        """Construct a built-in suite by name.

        Accepted names are listed by :meth:`builtin_names`. Raises :class:`WorldForgeError`
        for unknown names with a hint listing the valid set.
        """

        registry = cls._builtin_registry()
        try:
            factory = registry[name]
        except KeyError as exc:
            known = ", ".join(sorted(registry))
            raise WorldForgeError(
                f"Unknown evaluation suite '{name}'. Known suites: {known}."
            ) from exc
        return factory()

    def _required_capabilities(self) -> tuple[str, ...]:
        names = {
            capability
            for scenario in self.scenarios
            for capability in scenario.required_capabilities
        }
        return tuple(sorted(names))

    def _require_provider_capabilities(self, provider: str, *, forge: WorldForge) -> None:
        profile = forge.provider_profile(provider)
        missing = [
            capability
            for capability in self._required_capabilities()
            if not profile.capabilities.supports(capability)
        ]
        if missing:
            joined = ", ".join(missing)
            raise WorldForgeError(
                f"Provider '{provider}' cannot run evaluation suite '{self.suite_id}': "
                f"missing required capabilities: {joined}."
            )

    def _build_world(self, provider: str, *, forge: WorldForge) -> World:
        return forge.create_world(f"{self.suite_id}-evaluation-world", provider)

    def _ensure_world(
        self,
        provider: str,
        *,
        forge: WorldForge,
        world: World | None = None,
    ) -> World:
        from worldforge.framework import World

        if world is not None:
            return World.from_state(forge, world.to_dict())
        return self._build_world(provider, forge=forge)

    def evaluate_scenario(
        self,
        scenario: EvaluationScenario,
        provider: str,
        *,
        world: World,
        forge: WorldForge,
        index: int,
    ) -> EvaluationResult:
        prediction = world.predict(
            Action.move_to(0.1 * (index + 1), 0.5, 0.0),
            steps=1,
            provider=provider,
        )
        score = _clamp_score((prediction.physics_score + prediction.confidence) / 2)
        return EvaluationResult(
            suite_id=self.suite_id,
            suite=self.name,
            scenario=scenario.name,
            provider=provider,
            score=score,
            passed=score >= 0.7,
            metrics={
                "physics_score": prediction.physics_score,
                "confidence": prediction.confidence,
            },
        )

    def run_with_world(
        self,
        provider: str,
        *,
        world: World,
        forge: WorldForge,
    ) -> list[EvaluationResult]:
        self._require_provider_capabilities(provider, forge=forge)
        base_world = self._ensure_world(provider, forge=forge, world=world)
        results: list[EvaluationResult] = []
        for index, scenario in enumerate(self.scenarios):
            sandbox = self._ensure_world(provider, forge=forge, world=base_world)
            results.append(
                self.evaluate_scenario(
                    scenario,
                    provider,
                    world=sandbox,
                    forge=forge,
                    index=index,
                )
            )
        return results

    def run(self, provider: str, *, forge: WorldForge | None = None) -> list[EvaluationResult]:
        from worldforge.framework import WorldForge

        active_forge = forge or WorldForge()
        self._require_provider_capabilities(provider, forge=active_forge)
        world = self._ensure_world(provider, forge=active_forge)
        return self.run_with_world(provider, world=world, forge=active_forge)

    def run_report(
        self,
        providers: str | Sequence[str],
        *,
        world: World | None = None,
        forge: WorldForge | None = None,
    ) -> EvaluationReport:
        from worldforge.framework import WorldForge

        active_forge = forge or WorldForge()
        provider_names = [providers] if isinstance(providers, str) else list(providers)
        if not provider_names:
            raise WorldForgeError("run_report() requires at least one provider.")

        for provider in provider_names:
            # Fail fast on capability mismatch before spinning up threads.
            self._require_provider_capabilities(provider, forge=active_forge)

        def _run_one(provider: str) -> list[EvaluationResult]:
            return self.run_with_world(
                provider,
                world=self._ensure_world(provider, forge=active_forge, world=world),
                forge=active_forge,
            )

        results: list[EvaluationResult] = []
        if len(provider_names) == 1:
            results.extend(_run_one(provider_names[0]))
        else:
            with ThreadPoolExecutor(max_workers=min(8, len(provider_names))) as pool:
                for provider_results in pool.map(_run_one, provider_names):
                    results.extend(provider_results)
        provenance = self._build_provenance(provider_names, results)
        return EvaluationReport(
            self.suite_id,
            self.name,
            results,
            provenance=provenance,
        )

    def _build_provenance(
        self,
        provider_names: Sequence[str],
        results: Sequence[EvaluationResult],
    ) -> ProvenanceEnvelope:
        result_payload = [result.to_dict() for result in results]
        return ProvenanceEnvelope(
            kind="evaluation",
            suite_id=self.suite_id,
            suite_version=f"evaluation:{EVALUATION_SUITE_CONTRACT_VERSION}",
            providers=tuple(provider_names),
            capabilities=self._required_capabilities(),
            runtime_manifests=collect_runtime_manifests(provider_names),
            input_digest=digest_payload(
                {
                    "suite_id": self.suite_id,
                    "suite": self.name,
                    "scenarios": [
                        {
                            "name": scenario.name,
                            "description": scenario.description,
                            "required_capabilities": list(scenario.required_capabilities),
                        }
                        for scenario in self.scenarios
                    ],
                    "providers": list(provider_names),
                }
            ),
            result_digest=digest_payload(result_payload),
            event_count=0,
            claim_boundary=EVALUATION_CLAIM_BOUNDARY,
            metric_semantics=EVALUATION_METRIC_SEMANTICS,
        )

    def run_report_artifacts(
        self,
        *,
        providers: str | Sequence[str],
        world: World | None = None,
        forge: WorldForge | None = None,
    ) -> dict[str, str]:
        report = self.run_report(providers=providers, world=world, forge=forge)
        return report.artifacts()


class PhysicsEvaluationSuite(EvaluationSuite):
    """Built-in suite for deterministic physics-style checks."""

    def __init__(self) -> None:
        super().__init__(
            "Physics Evaluation Suite",
            scenarios=[
                EvaluationScenario(
                    "object-stability",
                    "Checks that an object remains stable under a no-op move.",
                    required_capabilities=("predict",),
                ),
                EvaluationScenario(
                    "action-response",
                    "Checks that a move action reaches the target pose.",
                    required_capabilities=("predict",),
                ),
            ],
            suite_id="physics",
        )

    def _build_world(self, provider: str, *, forge: WorldForge) -> World:
        world = super()._build_world(provider, forge=forge)
        _seed_object(world, "cube", Position(0.0, 0.5, 0.0))
        return world

    def evaluate_scenario(
        self,
        scenario: EvaluationScenario,
        provider: str,
        *,
        world: World,
        forge: WorldForge,
        index: int,
    ) -> EvaluationResult:
        handler = self._SCENARIO_HANDLERS.get(scenario.name)
        if handler is None:
            return super().evaluate_scenario(
                scenario,
                provider,
                world=world,
                forge=forge,
                index=index,
            )
        return handler(self, scenario, provider, world=world, forge=forge, index=index)

    def _evaluate_object_stability(
        self,
        scenario: EvaluationScenario,
        provider: str,
        *,
        world: World,
        forge: WorldForge,
        index: int,
    ) -> EvaluationResult:
        primary = _seed_object(world, "cube", Position(0.0, 0.5, 0.0))
        start = primary.position
        prediction = world.predict(
            Action.move_to(start.x, start.y, start.z),
            steps=1,
            provider=provider,
        )
        current = world.get_object_by_id(primary.id)
        if current is None:  # pragma: no cover - world state corruption guard
            raise WorldForgeError("Evaluation lost the primary object during physics run.")
        displacement = _distance(start, current.position)
        passed = displacement <= 0.01 and prediction.physics_score >= 0.7
        score = _clamp_score(
            ((prediction.physics_score + prediction.confidence) / 2) - min(0.25, displacement)
        )
        return EvaluationResult(
            suite_id=self.suite_id,
            suite=self.name,
            scenario=scenario.name,
            provider=provider,
            score=score,
            passed=passed,
            metrics={
                "physics_score": prediction.physics_score,
                "confidence": prediction.confidence,
                "displacement": displacement,
                "step": world.step,
            },
        )

    def _evaluate_action_response(
        self,
        scenario: EvaluationScenario,
        provider: str,
        *,
        world: World,
        forge: WorldForge,
        index: int,
    ) -> EvaluationResult:
        primary = _seed_object(world, "cube", Position(0.0, 0.5, 0.0))
        start = primary.position
        target = Position(start.x + 0.35, start.y, start.z)
        prediction = world.predict(
            Action.move_to(target.x, target.y, target.z),
            steps=2,
            provider=provider,
        )
        current = world.get_object_by_id(primary.id)
        if current is None:  # pragma: no cover - world state corruption guard
            raise WorldForgeError("Evaluation lost the primary object during physics run.")
        target_error = _distance(target, current.position)
        moved_distance = _distance(start, current.position)
        passed = target_error <= 0.05 and moved_distance >= 0.3
        score = _clamp_score(
            ((prediction.physics_score + prediction.confidence) / 2)
            + min(0.2, moved_distance / 2)
            - min(0.3, target_error)
        )
        return EvaluationResult(
            suite_id=self.suite_id,
            suite=self.name,
            scenario=scenario.name,
            provider=provider,
            score=score,
            passed=passed,
            metrics={
                "physics_score": prediction.physics_score,
                "confidence": prediction.confidence,
                "moved_distance": moved_distance,
                "target_error": target_error,
                "step": world.step,
            },
        )

    _SCENARIO_HANDLERS: ClassVar[dict[str, Callable[..., EvaluationResult]]] = {
        "object-stability": _evaluate_object_stability,
        "action-response": _evaluate_action_response,
    }


class PlanningEvaluationSuite(EvaluationSuite):
    """Built-in suite for heuristic planning and execution checks."""

    def __init__(self) -> None:
        super().__init__(
            "Planning Evaluation Suite",
            scenarios=[
                EvaluationScenario(
                    "object-relocation",
                    "Plans and executes a relocation objective for a seeded object.",
                    required_capabilities=("predict",),
                ),
                EvaluationScenario(
                    "object-neighbor-placement",
                    "Places one object near another using a typed relational goal.",
                    required_capabilities=("predict",),
                ),
                EvaluationScenario(
                    "object-swap",
                    "Swaps the positions of two seeded objects using a typed relational goal.",
                    required_capabilities=("predict",),
                ),
                EvaluationScenario(
                    "object-spawn",
                    "Plans and executes a simple spawn goal.",
                    required_capabilities=("predict",),
                ),
            ],
            suite_id="planning",
        )

    def _build_world(self, provider: str, *, forge: WorldForge) -> World:
        world = super()._build_world(provider, forge=forge)
        _seed_object(world, "cube", Position(0.0, 0.5, 0.0))
        _seed_object(world, "mug", Position(0.3, 0.8, 0.0))
        return world

    def evaluate_scenario(
        self,
        scenario: EvaluationScenario,
        provider: str,
        *,
        world: World,
        forge: WorldForge,
        index: int,
    ) -> EvaluationResult:
        handler = self._SCENARIO_HANDLERS.get(scenario.name)
        if handler is None:
            return super().evaluate_scenario(
                scenario,
                provider,
                world=world,
                forge=forge,
                index=index,
            )
        return handler(self, scenario, provider, world=world, forge=forge, index=index)

    def _evaluate_object_relocation(
        self,
        scenario: EvaluationScenario,
        provider: str,
        *,
        world: World,
        forge: WorldForge,
        index: int,
    ) -> EvaluationResult:
        primary = _seed_object(world, "cube", Position(0.0, 0.5, 0.0))
        _seed_object(world, "mug", Position(0.3, 0.8, 0.0))
        plan = world.plan(
            goal_spec=StructuredGoal.object_at(
                object_id=primary.id,
                object_name=primary.name,
                position=Position(
                    primary.position.x + 0.35,
                    primary.position.y,
                    primary.position.z,
                ),
                tolerance=0.05,
            ),
            max_steps=4,
            provider=provider,
        )
        execution = world.execute_plan(plan, provider)
        final_world = execution.final_world()
        final_object = final_world.get_object_by_id(primary.id)
        if final_object is None:  # pragma: no cover - world state corruption guard
            raise WorldForgeError("Evaluation lost the primary object during plan execution.")
        moved_distance = final_object.position.x - primary.position.x
        passed = plan.action_count >= 1 and moved_distance >= 0.25
        score = _clamp_score((plan.success_probability + min(1.0, moved_distance)) / 2)
        return EvaluationResult(
            suite_id=self.suite_id,
            suite=self.name,
            scenario=scenario.name,
            provider=provider,
            score=score,
            passed=passed,
            metrics={
                "action_count": plan.action_count,
                "success_probability": plan.success_probability,
                "moved_distance": moved_distance,
                "final_step": final_world.step,
            },
        )

    def _evaluate_object_neighbor_placement(
        self,
        scenario: EvaluationScenario,
        provider: str,
        *,
        world: World,
        forge: WorldForge,
        index: int,
    ) -> EvaluationResult:
        primary = _seed_object(world, "cube", Position(0.0, 0.5, 0.0))
        reference = _seed_object(world, "mug", Position(0.3, 0.8, 0.0))
        offset = Position(0.15, 0.0, 0.0)
        target = Position(
            reference.position.x + offset.x,
            reference.position.y + offset.y,
            reference.position.z + offset.z,
        )
        plan = world.plan(
            goal_spec=StructuredGoal.object_near(
                object_id=primary.id,
                object_name=primary.name,
                reference_object_id=reference.id,
                reference_object_name=reference.name,
                offset=offset,
                tolerance=0.05,
            ),
            max_steps=4,
            provider=provider,
        )
        execution = world.execute_plan(plan, provider)
        final_world = execution.final_world()
        final_primary = final_world.get_object_by_id(primary.id)
        final_reference = final_world.get_object_by_id(reference.id)
        if final_primary is None or final_reference is None:  # pragma: no cover
            raise WorldForgeError("Evaluation lost an object during relational plan execution.")
        target_error = _distance(target, final_primary.position)
        reference_drift = _distance(reference.position, final_reference.position)
        passed = plan.action_count >= 1 and target_error <= 0.05 and reference_drift <= 0.01
        score = average(
            [
                plan.success_probability,
                _clamp_score(1.0 - min(1.0, target_error / 0.25)),
                _clamp_score(1.0 - min(1.0, reference_drift / 0.25)),
            ]
        )
        return EvaluationResult(
            suite_id=self.suite_id,
            suite=self.name,
            scenario=scenario.name,
            provider=provider,
            score=score,
            passed=passed,
            metrics={
                "action_count": plan.action_count,
                "success_probability": plan.success_probability,
                "target_error": target_error,
                "reference_drift": reference_drift,
                "final_step": final_world.step,
            },
        )

    def _evaluate_object_swap(
        self,
        scenario: EvaluationScenario,
        provider: str,
        *,
        world: World,
        forge: WorldForge,
        index: int,
    ) -> EvaluationResult:
        primary = _seed_object(world, "cube", Position(0.0, 0.5, 0.0))
        reference = _seed_object(world, "mug", Position(0.3, 0.8, 0.0))
        plan = world.plan(
            goal_spec=StructuredGoal.swap_objects(
                object_id=primary.id,
                object_name=primary.name,
                reference_object_id=reference.id,
                reference_object_name=reference.name,
                tolerance=0.05,
            ),
            max_steps=4,
            provider=provider,
        )
        execution = world.execute_plan(plan, provider)
        final_world = execution.final_world()
        final_primary = final_world.get_object_by_id(primary.id)
        final_reference = final_world.get_object_by_id(reference.id)
        if final_primary is None or final_reference is None:  # pragma: no cover
            raise WorldForgeError("Evaluation lost an object during swap plan execution.")
        primary_target_error = _distance(reference.position, final_primary.position)
        reference_target_error = _distance(primary.position, final_reference.position)
        passed = (
            plan.action_count == 2
            and primary_target_error <= 0.05
            and reference_target_error <= 0.05
        )
        score = average(
            [
                plan.success_probability,
                _clamp_score(1.0 - min(1.0, primary_target_error / 0.25)),
                _clamp_score(1.0 - min(1.0, reference_target_error / 0.25)),
            ]
        )
        return EvaluationResult(
            suite_id=self.suite_id,
            suite=self.name,
            scenario=scenario.name,
            provider=provider,
            score=score,
            passed=passed,
            metrics={
                "action_count": plan.action_count,
                "success_probability": plan.success_probability,
                "primary_target_error": primary_target_error,
                "reference_target_error": reference_target_error,
                "final_step": final_world.step,
            },
        )

    def _evaluate_object_spawn(
        self,
        scenario: EvaluationScenario,
        provider: str,
        *,
        world: World,
        forge: WorldForge,
        index: int,
    ) -> EvaluationResult:
        _seed_object(world, "cube", Position(0.0, 0.5, 0.0))
        _seed_object(world, "mug", Position(0.3, 0.8, 0.0))
        initial_count = world.object_count
        plan = world.plan(goal="spawn cube", max_steps=3, provider=provider)
        execution = world.execute_plan(plan, provider)
        final_world = execution.final_world()
        final_count = final_world.object_count
        spawned = final_count > initial_count
        score = _clamp_score((plan.success_probability + (1.0 if spawned else 0.0)) / 2)
        return EvaluationResult(
            suite_id=self.suite_id,
            suite=self.name,
            scenario=scenario.name,
            provider=provider,
            score=score,
            passed=spawned,
            metrics={
                "action_count": plan.action_count,
                "success_probability": plan.success_probability,
                "initial_object_count": initial_count,
                "final_object_count": final_count,
            },
        )

    _SCENARIO_HANDLERS: ClassVar[dict[str, Callable[..., EvaluationResult]]] = {
        "object-relocation": _evaluate_object_relocation,
        "object-neighbor-placement": _evaluate_object_neighbor_placement,
        "object-swap": _evaluate_object_swap,
        "object-spawn": _evaluate_object_spawn,
    }


class GenerationEvaluationSuite(EvaluationSuite):
    """Built-in suite for text and image-conditioned video generation checks."""

    def __init__(self) -> None:
        super().__init__(
            "Generation Evaluation Suite",
            scenarios=[
                EvaluationScenario(
                    "text-conditioned-video",
                    "Generates a prompt-only clip and scores basic output integrity.",
                    required_capabilities=("generate",),
                ),
                EvaluationScenario(
                    "image-conditioned-video",
                    (
                        "Generates a prompt plus image-conditioned clip and scores "
                        "conditioning metadata."
                    ),
                    required_capabilities=("generate",),
                ),
            ],
            suite_id="generation",
        )

    def evaluate_scenario(
        self,
        scenario: EvaluationScenario,
        provider: str,
        *,
        world: World,
        forge: WorldForge,
        index: int,
    ) -> EvaluationResult:
        handler = self._SCENARIO_HANDLERS.get(scenario.name)
        if handler is None:
            return super().evaluate_scenario(
                scenario,
                provider,
                world=world,
                forge=forge,
                index=index,
            )
        return handler(self, scenario, provider, world=world, forge=forge, index=index)

    def _evaluate_text_conditioned_video(
        self,
        scenario: EvaluationScenario,
        provider: str,
        *,
        world: World,
        forge: WorldForge,
        index: int,
    ) -> EvaluationResult:
        expected_duration = 1.0
        expected_resolution = (640, 360)
        prompt = "orbiting cube over a reflective floor"
        clip = forge.generate(
            prompt,
            provider,
            duration_seconds=expected_duration,
            options=GenerationOptions(ratio="640:360", fps=8.0),
        )
        score = average(
            [
                _blob_score(clip),
                _duration_score(
                    actual_seconds=clip.duration_seconds,
                    expected_seconds=expected_duration,
                ),
                _resolution_score(clip, expected=expected_resolution),
                _content_type_score(clip),
                _prompt_score(clip, expected_prompt=prompt),
            ]
        )
        passed = (
            _blob_score(clip) == 1.0
            and _duration_score(
                actual_seconds=clip.duration_seconds,
                expected_seconds=expected_duration,
            )
            >= 0.75
            and _resolution_score(clip, expected=expected_resolution) >= 0.75
        )
        return EvaluationResult(
            suite_id=self.suite_id,
            suite=self.name,
            scenario=scenario.name,
            provider=provider,
            score=score,
            passed=passed,
            metrics={
                "frame_count": clip.frame_count,
                "fps": clip.fps,
                "resolution": list(clip.resolution),
                "duration_seconds": clip.duration_seconds,
                "content_type": clip.content_type(),
                "mode": clip.metadata.get("mode"),
            },
        )

    def _evaluate_image_conditioned_video(
        self,
        scenario: EvaluationScenario,
        provider: str,
        *,
        world: World,
        forge: WorldForge,
        index: int,
    ) -> EvaluationResult:
        expected_duration = 1.0
        expected_resolution = (640, 360)
        prompt = "orbiting cube over a reflective floor"
        clip = forge.generate(
            prompt,
            provider,
            duration_seconds=expected_duration,
            options=GenerationOptions(
                image=_SAMPLE_IMAGE_DATA_URI,
                ratio="640:360",
                fps=8.0,
            ),
        )
        image_conditioned = _is_image_conditioned(clip)
        score = average(
            [
                _blob_score(clip),
                _duration_score(
                    actual_seconds=clip.duration_seconds,
                    expected_seconds=expected_duration,
                ),
                _resolution_score(clip, expected=expected_resolution),
                _content_type_score(clip),
                _prompt_score(clip, expected_prompt=prompt),
                1.0 if image_conditioned else 0.0,
            ]
        )
        passed = (
            _blob_score(clip) == 1.0
            and image_conditioned
            and _duration_score(
                actual_seconds=clip.duration_seconds,
                expected_seconds=expected_duration,
            )
            >= 0.75
        )
        return EvaluationResult(
            suite_id=self.suite_id,
            suite=self.name,
            scenario=scenario.name,
            provider=provider,
            score=score,
            passed=passed,
            metrics={
                "frame_count": clip.frame_count,
                "fps": clip.fps,
                "resolution": list(clip.resolution),
                "duration_seconds": clip.duration_seconds,
                "content_type": clip.content_type(),
                "mode": clip.metadata.get("mode"),
                "image_conditioned": image_conditioned,
            },
        )

    _SCENARIO_HANDLERS: ClassVar[dict[str, Callable[..., EvaluationResult]]] = {
        "text-conditioned-video": _evaluate_text_conditioned_video,
        "image-conditioned-video": _evaluate_image_conditioned_video,
    }


class TransferEvaluationSuite(EvaluationSuite):
    """Built-in suite for prompt-guided and reference-guided transfer checks."""

    def __init__(self) -> None:
        super().__init__(
            "Transfer Evaluation Suite",
            scenarios=[
                EvaluationScenario(
                    "prompt-guided-transfer",
                    (
                        "Transfers a seed clip to a new render while preserving "
                        "basic media constraints."
                    ),
                    required_capabilities=("transfer",),
                ),
                EvaluationScenario(
                    "reference-guided-transfer",
                    "Transfers a seed clip with reference guidance metadata.",
                    required_capabilities=("transfer",),
                ),
            ],
            suite_id="transfer",
        )

    def evaluate_scenario(
        self,
        scenario: EvaluationScenario,
        provider: str,
        *,
        world: World,
        forge: WorldForge,
        index: int,
    ) -> EvaluationResult:
        handler = self._SCENARIO_HANDLERS.get(scenario.name)
        if handler is None:
            return super().evaluate_scenario(
                scenario,
                provider,
                world=world,
                forge=forge,
                index=index,
            )
        return handler(self, scenario, provider, world=world, forge=forge, index=index)

    def _evaluate_prompt_guided_transfer(
        self,
        scenario: EvaluationScenario,
        provider: str,
        *,
        world: World,
        forge: WorldForge,
        index: int,
    ) -> EvaluationResult:
        input_clip = _sample_transfer_clip()
        expected_resolution = (320, 180)
        expected_fps = 12.0
        prompt = "re-render the clip with sharper cinematic contrast"
        clip = forge.transfer(
            input_clip,
            provider,
            width=expected_resolution[0],
            height=expected_resolution[1],
            fps=expected_fps,
            prompt=prompt,
        )
        transfer_mode = _is_transfer_clip(clip)
        score = average(
            [
                _blob_score(clip),
                _duration_score(
                    actual_seconds=clip.duration_seconds,
                    expected_seconds=input_clip.duration_seconds,
                ),
                _resolution_score(clip, expected=expected_resolution),
                _fps_score(clip, expected_fps=expected_fps),
                _content_type_score(clip),
                _prompt_score(clip, expected_prompt=prompt),
                1.0 if transfer_mode else 0.0,
            ]
        )
        passed = (
            _blob_score(clip) == 1.0
            and transfer_mode
            and _resolution_score(clip, expected=expected_resolution) == 1.0
            and _fps_score(clip, expected_fps=expected_fps) == 1.0
        )
        return EvaluationResult(
            suite_id=self.suite_id,
            suite=self.name,
            scenario=scenario.name,
            provider=provider,
            score=score,
            passed=passed,
            metrics={
                "frame_count": clip.frame_count,
                "fps": clip.fps,
                "resolution": list(clip.resolution),
                "duration_seconds": clip.duration_seconds,
                "content_type": clip.content_type(),
                "mode": clip.metadata.get("mode"),
                "reference_count": _reference_count(clip),
            },
        )

    def _evaluate_reference_guided_transfer(
        self,
        scenario: EvaluationScenario,
        provider: str,
        *,
        world: World,
        forge: WorldForge,
        index: int,
    ) -> EvaluationResult:
        input_clip = _sample_transfer_clip()
        expected_resolution = (320, 180)
        expected_fps = 12.0
        prompt = "re-render the clip with sharper cinematic contrast"
        clip = forge.transfer(
            input_clip,
            provider,
            width=expected_resolution[0],
            height=expected_resolution[1],
            fps=expected_fps,
            prompt=prompt,
            options=GenerationOptions(reference_images=[_SAMPLE_IMAGE_DATA_URI]),
        )
        reference_count = _reference_count(clip)
        transfer_mode = _is_transfer_clip(clip)
        score = average(
            [
                _blob_score(clip),
                _duration_score(
                    actual_seconds=clip.duration_seconds,
                    expected_seconds=input_clip.duration_seconds,
                ),
                _resolution_score(clip, expected=expected_resolution),
                _fps_score(clip, expected_fps=expected_fps),
                _content_type_score(clip),
                _prompt_score(clip, expected_prompt=prompt),
                1.0 if transfer_mode else 0.0,
                1.0 if reference_count >= 1 else 0.0,
            ]
        )
        passed = (
            _blob_score(clip) == 1.0
            and transfer_mode
            and reference_count >= 1
            and _resolution_score(clip, expected=expected_resolution) == 1.0
        )
        return EvaluationResult(
            suite_id=self.suite_id,
            suite=self.name,
            scenario=scenario.name,
            provider=provider,
            score=score,
            passed=passed,
            metrics={
                "frame_count": clip.frame_count,
                "fps": clip.fps,
                "resolution": list(clip.resolution),
                "duration_seconds": clip.duration_seconds,
                "content_type": clip.content_type(),
                "mode": clip.metadata.get("mode"),
                "reference_count": reference_count,
            },
        )

    _SCENARIO_HANDLERS: ClassVar[dict[str, Callable[..., EvaluationResult]]] = {
        "prompt-guided-transfer": _evaluate_prompt_guided_transfer,
        "reference-guided-transfer": _evaluate_reference_guided_transfer,
    }


class ReasoningEvaluationSuite(EvaluationSuite):
    """Built-in suite for scene reasoning quality checks."""

    def __init__(self) -> None:
        super().__init__(
            "Reasoning Evaluation Suite",
            scenarios=[
                EvaluationScenario(
                    "scene-count",
                    "Checks whether the provider reports the tracked object count.",
                    required_capabilities=("reason",),
                ),
                EvaluationScenario(
                    "scene-identity",
                    "Checks whether provider evidence references tracked object identifiers.",
                    required_capabilities=("reason",),
                ),
            ],
            suite_id="reasoning",
        )

    def _build_world(self, provider: str, *, forge: WorldForge) -> World:
        world = super()._build_world(provider, forge=forge)
        _seed_object(world, "cube", Position(0.0, 0.5, 0.0))
        _seed_object(world, "mug", Position(0.3, 0.8, 0.0))
        return world

    def evaluate_scenario(
        self,
        scenario: EvaluationScenario,
        provider: str,
        *,
        world: World,
        forge: WorldForge,
        index: int,
    ) -> EvaluationResult:
        handler = self._SCENARIO_HANDLERS.get(scenario.name)
        if handler is None:
            return super().evaluate_scenario(
                scenario,
                provider,
                world=world,
                forge=forge,
                index=index,
            )
        return handler(self, scenario, provider, world=world, forge=forge, index=index)

    def _evaluate_scene_count(
        self,
        scenario: EvaluationScenario,
        provider: str,
        *,
        world: World,
        forge: WorldForge,
        index: int,
    ) -> EvaluationResult:
        _seed_object(world, "cube", Position(0.0, 0.5, 0.0))
        _seed_object(world, "mug", Position(0.3, 0.8, 0.0))
        expected_count = world.object_count
        reasoning = forge.reason(provider, "How many objects are tracked?", world=world)
        answer = reasoning.answer.lower()
        mentions_count = str(expected_count) in answer
        has_evidence = bool(reasoning.evidence)
        score = _clamp_score(
            (
                reasoning.confidence
                + (1.0 if mentions_count else 0.0)
                + (1.0 if has_evidence else 0.0)
            )
            / 3
        )
        return EvaluationResult(
            suite_id=self.suite_id,
            suite=self.name,
            scenario=scenario.name,
            provider=provider,
            score=score,
            passed=mentions_count and has_evidence,
            metrics={
                "confidence": reasoning.confidence,
                "expected_count": expected_count,
                "evidence_count": len(reasoning.evidence),
                "mentions_count": mentions_count,
            },
        )

    def _evaluate_scene_identity(
        self,
        scenario: EvaluationScenario,
        provider: str,
        *,
        world: World,
        forge: WorldForge,
        index: int,
    ) -> EvaluationResult:
        _seed_object(world, "cube", Position(0.0, 0.5, 0.0))
        _seed_object(world, "mug", Position(0.3, 0.8, 0.0))
        object_ids = sorted(obj.id for obj in world.objects())
        reasoning = forge.reason(provider, "Which object ids are tracked?", world=world)
        haystack = " ".join([reasoning.answer, *reasoning.evidence]).lower()
        matched_ids = [object_id for object_id in object_ids if object_id.lower() in haystack]
        coverage = len(matched_ids) / len(object_ids) if object_ids else 1.0
        score = _clamp_score((reasoning.confidence + coverage) / 2)
        return EvaluationResult(
            suite_id=self.suite_id,
            suite=self.name,
            scenario=scenario.name,
            provider=provider,
            score=score,
            passed=coverage == 1.0,
            metrics={
                "confidence": reasoning.confidence,
                "tracked_object_count": len(object_ids),
                "matched_object_count": len(matched_ids),
                "coverage": coverage,
            },
        )

    _SCENARIO_HANDLERS: ClassVar[dict[str, Callable[..., EvaluationResult]]] = {
        "scene-count": _evaluate_scene_count,
        "scene-identity": _evaluate_scene_identity,
    }


EvalScenario = EvaluationScenario
EvalResult = EvaluationResult
EvalReport = EvaluationReport
EvalSuite = EvaluationSuite
GenerationEval = GenerationEvaluationSuite
PhysicsEval = PhysicsEvaluationSuite
PlanningEval = PlanningEvaluationSuite
ReasoningEval = ReasoningEvaluationSuite
TransferEval = TransferEvaluationSuite

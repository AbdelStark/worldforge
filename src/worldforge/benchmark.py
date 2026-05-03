"""Capability-aware provider benchmark harness."""

from __future__ import annotations

import csv
import io
from base64 import b64decode
from binascii import Error as BinasciiError
from collections.abc import Callable, Sequence
from concurrent.futures import ThreadPoolExecutor, as_completed
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from time import perf_counter

from worldforge.framework import WorldForge
from worldforge.models import (
    Action,
    BBox,
    JSONDict,
    Position,
    SceneObject,
    VideoClip,
    WorldForgeError,
    dump_json,
    require_finite_number,
    require_json_dict,
    require_non_negative_int,
    require_positive_int,
    require_probability,
)
from worldforge.observability import ProviderMetricsSink, compose_event_handlers
from worldforge.provenance import (
    BENCHMARK_SUITE_CONTRACT_VERSION,
    ProvenanceEnvelope,
    collect_runtime_manifests,
    digest_payload,
)
from worldforge.providers.base import ProviderError

BENCHMARKABLE_OPERATIONS = (
    "predict",
    "reason",
    "generate",
    "transfer",
    "embed",
    "score",
    "policy",
)

BENCHMARK_CLAIM_BOUNDARY = (
    "Benchmark reports measure adapter-path latency, retries, throughput, and errors for the "
    "selected provider inputs. They do not measure physical fidelity, media quality, safety, or "
    "production load capacity."
)
BENCHMARK_METRIC_SEMANTICS = (
    "Latency metrics are process-local wall-clock timings for successful samples; retry counts "
    "come from emitted ProviderEvent records; throughput is computed from successful samples over "
    "elapsed time."
)

_BENCHMARK_INPUT_KEYS = (
    "prediction_action",
    "prediction_steps",
    "reason_query",
    "generation_prompt",
    "generation_duration_seconds",
    "transfer_prompt",
    "transfer_width",
    "transfer_height",
    "transfer_fps",
    "transfer_clip",
    "embedding_text",
    "score_info",
    "score_action_candidates",
    "policy_info",
)

_TRANSFER_CLIP_KEYS = (
    "path",
    "frames_base64",
    "fps",
    "resolution",
    "duration_seconds",
    "metadata",
)
_BENCHMARK_BUDGET_KEYS = {
    "provider",
    "operation",
    "min_success_rate",
    "max_error_count",
    "max_retry_count",
    "max_average_latency_ms",
    "max_p95_latency_ms",
    "min_throughput_per_second",
}
_BENCHMARK_BUDGET_WRAPPER_KEYS = {"budgets", "metadata"}


def _benchmark_provenance_markdown_lines(provenance: ProvenanceEnvelope | None) -> list[str]:
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


def _sample_transfer_clip() -> VideoClip:
    return VideoClip(
        frames=[b"worldforge-benchmark-transfer-seed"],
        fps=8.0,
        resolution=(160, 90),
        duration_seconds=1.0,
        metadata={
            "provider": "worldforge",
            "content_type": "video/mp4",
            "mode": "benchmark-seed",
        },
    )


def _sample_score_info() -> JSONDict:
    return {
        "pixels": [[[[0.0], [0.1]], [[0.2], [0.3]]]],
        "goal": [[[0.3, 0.5, 0.0]]],
        "action": [[[0.0, 0.5, 0.0]]],
        "metadata": {"mode": "benchmark-score"},
    }


def _sample_score_action_candidates() -> list[list[list[list[float]]]]:
    return [
        [
            [[0.0, 0.5, 0.0], [0.1, 0.5, 0.0]],
            [[0.0, 0.5, 0.0], [0.3, 0.5, 0.0]],
        ]
    ]


def _sample_policy_info() -> JSONDict:
    return {
        "observation": {
            "state": {
                "cube": [0.0, 0.5, 0.0],
                "mug": [0.25, 0.8, 0.0],
            },
            "language": "move the cube toward the target",
        },
        "options": {"temperature": 0.0},
        "mode": "select_action",
        "action_horizon": 2,
        "embodiment_tag": "benchmark",
    }


def _json_input_preview(value: object) -> object:
    try:
        dump_json(value)
    except WorldForgeError:
        payload: JSONDict = {
            "type": f"{type(value).__module__}.{type(value).__qualname__}",
            "json_serializable": False,
        }
        shape = getattr(value, "shape", None)
        if shape is not None:
            try:
                payload["shape"] = [int(dimension) for dimension in shape]
            except (TypeError, ValueError):
                payload["shape"] = [str(dimension) for dimension in shape]
        return payload
    return value


def _percentile(values: Sequence[float], quantile: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    index = quantile * (len(ordered) - 1)
    lower = int(index)
    upper = min(len(ordered) - 1, lower + 1)
    weight = index - lower
    return ordered[lower] + ((ordered[upper] - ordered[lower]) * weight)


def _non_empty_optional_text(value: object, *, name: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise WorldForgeError(f"{name} must be a non-empty string when provided.")
    return value.strip()


def _optional_non_negative_int(value: object, *, name: str) -> int | None:
    if value is None:
        return None
    return require_non_negative_int(value, name=name)


def _optional_non_negative_number(value: object, *, name: str) -> float | None:
    if value is None:
        return None
    return _non_negative_number(value, name=name)


def _non_negative_number(value: object, *, name: str) -> float:
    number = require_finite_number(value, name=name)
    if number < 0.0:
        raise WorldForgeError(f"{name} must be greater than or equal to 0.")
    return number


def _format_optional_number(value: float | int | None) -> str:
    if value is None:
        return ""
    if isinstance(value, int):
        return str(value)
    return f"{value:.4f}"


def _reject_unknown_keys(payload: JSONDict, *, allowed: set[str], name: str) -> None:
    unknown = sorted(set(payload) - allowed)
    if unknown:
        raise WorldForgeError(
            f"{name} contains unknown key(s): {', '.join(unknown)}. "
            f"Allowed keys: {', '.join(sorted(allowed))}."
        )


def _required_json_object(value: object, *, name: str) -> JSONDict:
    if not isinstance(value, dict) or not value:
        raise WorldForgeError(f"{name} must be a non-empty JSON object.")
    dump_json(value)
    return dict(value)


def _optional_json_object(value: object, *, name: str) -> JSONDict:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise WorldForgeError(f"{name} must be a JSON object.")
    dump_json(value)
    return dict(value)


def _required_text(value: object, *, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise WorldForgeError(f"{name} must be a non-empty string.")
    return value.strip()


def _positive_number(value: object, *, name: str) -> float:
    number = require_finite_number(value, name=name)
    if number <= 0.0:
        raise WorldForgeError(f"{name} must be greater than 0.")
    return number


def _positive_int(value: object, *, name: str) -> int:
    return require_positive_int(value, name=name)


def _positive_resolution(value: object, *, name: str) -> tuple[int, int]:
    if (
        not isinstance(value, list | tuple)
        or len(value) != 2
        or any(isinstance(dimension, bool) or not isinstance(dimension, int) for dimension in value)
    ):
        raise WorldForgeError(f"{name} must contain integer width and height.")
    width, height = value
    if width <= 0 or height <= 0:
        raise WorldForgeError(f"{name} values must be greater than 0.")
    return (width, height)


def _resolve_input_path(path: str, *, base_path: Path | None) -> Path:
    source = Path(path).expanduser()
    if not source.is_absolute():
        source = (base_path or Path.cwd()) / source
    return source


def _load_base64_frames(value: object, *, name: str) -> list[bytes]:
    if not isinstance(value, list) or not value:
        raise WorldForgeError(f"{name} must be a non-empty list of base64 strings.")
    frames: list[bytes] = []
    for index, frame in enumerate(value):
        if not isinstance(frame, str) or not frame:
            raise WorldForgeError(f"{name}[{index}] must be a non-empty base64 string.")
        try:
            frames.append(b64decode(frame, validate=True))
        except (BinasciiError, ValueError) as exc:
            raise WorldForgeError(f"{name}[{index}] must contain valid base64 bytes.") from exc
    return frames


def _load_transfer_clip(value: object, *, base_path: Path | None) -> VideoClip:
    if not isinstance(value, dict):
        raise WorldForgeError("transfer_clip must be a JSON object.")
    unknown_keys = sorted(set(value) - set(_TRANSFER_CLIP_KEYS))
    if unknown_keys:
        joined = ", ".join(unknown_keys)
        raise WorldForgeError(f"Unknown transfer_clip fields: {joined}.")

    fps = _positive_number(value.get("fps", 8.0), name="transfer_clip fps")
    resolution = _positive_resolution(
        value.get("resolution", [160, 90]),
        name="transfer_clip resolution",
    )
    duration_seconds = require_finite_number(
        value.get("duration_seconds", 1.0),
        name="transfer_clip duration_seconds",
    )
    if duration_seconds < 0.0:
        raise WorldForgeError("transfer_clip duration_seconds must be greater than or equal to 0.")
    metadata = _optional_json_object(value.get("metadata"), name="transfer_clip metadata")

    has_path = value.get("path") is not None
    has_frames = value.get("frames_base64") is not None
    if has_path == has_frames:
        raise WorldForgeError(
            "transfer_clip must provide exactly one of 'path' or 'frames_base64'."
        )

    if has_path:
        source = _resolve_input_path(
            _required_text(value.get("path"), name="transfer_clip path"),
            base_path=base_path,
        )
        return VideoClip.from_file(
            source,
            fps=fps,
            resolution=resolution,
            duration_seconds=duration_seconds,
            metadata=metadata,
        )

    return VideoClip(
        frames=_load_base64_frames(value.get("frames_base64"), name="transfer_clip frames_base64"),
        fps=fps,
        resolution=resolution,
        duration_seconds=duration_seconds,
        metadata=metadata,
    )


def _benchmark_inputs_payload(payload: object) -> JSONDict:
    if isinstance(payload, dict) and "inputs" in payload:
        allowed_wrapper_keys = {"inputs", "metadata"}
        unknown_wrapper_keys = sorted(set(payload) - allowed_wrapper_keys)
        if unknown_wrapper_keys:
            joined = ", ".join(unknown_wrapper_keys)
            raise WorldForgeError(f"Unknown benchmark input wrapper fields: {joined}.")
        payload = payload["inputs"]
    if not isinstance(payload, dict):
        raise WorldForgeError("Benchmark input payload must be a JSON object.")
    if not payload:
        raise WorldForgeError("Benchmark input payload must contain at least one input field.")
    unknown_keys = sorted(set(payload) - set(_BENCHMARK_INPUT_KEYS))
    if unknown_keys:
        joined = ", ".join(unknown_keys)
        raise WorldForgeError(f"Unknown benchmark input fields: {joined}.")
    return dict(payload)


@dataclass(slots=True, frozen=True)
class BenchmarkBudget:
    """Thresholds for release or claim-oriented benchmark gates.

    ``provider`` and ``operation`` are optional selectors. When either selector is omitted, the
    budget applies to every matching result on that dimension.
    """

    provider: str | None = None
    operation: str | None = None
    min_success_rate: float | None = None
    max_error_count: int | None = None
    max_retry_count: int | None = None
    max_average_latency_ms: float | None = None
    max_p95_latency_ms: float | None = None
    min_throughput_per_second: float | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "provider",
            _non_empty_optional_text(self.provider, name="BenchmarkBudget provider"),
        )
        operation = _non_empty_optional_text(
            self.operation,
            name="BenchmarkBudget operation",
        )
        if operation is not None and operation not in BENCHMARKABLE_OPERATIONS:
            known = ", ".join(BENCHMARKABLE_OPERATIONS)
            raise WorldForgeError(f"BenchmarkBudget operation must be one of: {known}.")
        object.__setattr__(self, "operation", operation)
        object.__setattr__(
            self,
            "min_success_rate",
            (
                require_probability(
                    self.min_success_rate,
                    name="BenchmarkBudget min_success_rate",
                )
                if self.min_success_rate is not None
                else None
            ),
        )
        object.__setattr__(
            self,
            "max_error_count",
            _optional_non_negative_int(
                self.max_error_count,
                name="BenchmarkBudget max_error_count",
            ),
        )
        object.__setattr__(
            self,
            "max_retry_count",
            _optional_non_negative_int(
                self.max_retry_count,
                name="BenchmarkBudget max_retry_count",
            ),
        )
        object.__setattr__(
            self,
            "max_average_latency_ms",
            _optional_non_negative_number(
                self.max_average_latency_ms,
                name="BenchmarkBudget max_average_latency_ms",
            ),
        )
        object.__setattr__(
            self,
            "max_p95_latency_ms",
            _optional_non_negative_number(
                self.max_p95_latency_ms,
                name="BenchmarkBudget max_p95_latency_ms",
            ),
        )
        object.__setattr__(
            self,
            "min_throughput_per_second",
            _optional_non_negative_number(
                self.min_throughput_per_second,
                name="BenchmarkBudget min_throughput_per_second",
            ),
        )
        if not any(
            value is not None
            for value in (
                self.min_success_rate,
                self.max_error_count,
                self.max_retry_count,
                self.max_average_latency_ms,
                self.max_p95_latency_ms,
                self.min_throughput_per_second,
            )
        ):
            raise WorldForgeError("BenchmarkBudget requires at least one threshold.")

    @classmethod
    def from_dict(cls, payload: JSONDict) -> BenchmarkBudget:
        if not isinstance(payload, dict):
            raise WorldForgeError("Benchmark budget entries must be JSON objects.")
        _reject_unknown_keys(
            payload,
            allowed=_BENCHMARK_BUDGET_KEYS,
            name="Benchmark budget entry",
        )
        return cls(
            provider=payload.get("provider"),
            operation=payload.get("operation"),
            min_success_rate=payload.get("min_success_rate"),
            max_error_count=payload.get("max_error_count"),
            max_retry_count=payload.get("max_retry_count"),
            max_average_latency_ms=payload.get("max_average_latency_ms"),
            max_p95_latency_ms=payload.get("max_p95_latency_ms"),
            min_throughput_per_second=payload.get("min_throughput_per_second"),
        )

    def matches(self, result: BenchmarkResult) -> bool:
        provider_matches = self.provider is None or self.provider == result.provider
        operation_matches = self.operation is None or self.operation == result.operation
        return provider_matches and operation_matches

    def selector_label(self) -> str:
        provider = self.provider or "*"
        operation = self.operation or "*"
        return f"{provider}/{operation}"

    def to_dict(self) -> JSONDict:
        return {
            "provider": self.provider,
            "operation": self.operation,
            "min_success_rate": self.min_success_rate,
            "max_error_count": self.max_error_count,
            "max_retry_count": self.max_retry_count,
            "max_average_latency_ms": self.max_average_latency_ms,
            "max_p95_latency_ms": self.max_p95_latency_ms,
            "min_throughput_per_second": self.min_throughput_per_second,
        }


@dataclass(slots=True, frozen=True)
class BenchmarkGateViolation:
    """One failed benchmark budget check."""

    provider: str
    operation: str
    metric: str
    observed: float | int | None
    threshold: float | int
    condition: str
    budget_selector: str

    def to_dict(self) -> JSONDict:
        return {
            "provider": self.provider,
            "operation": self.operation,
            "metric": self.metric,
            "observed": self.observed,
            "threshold": self.threshold,
            "condition": self.condition,
            "budget_selector": self.budget_selector,
        }


@dataclass(slots=True)
class BenchmarkGateReport:
    """Budget evaluation report for a benchmark run."""

    budgets: list[BenchmarkBudget]
    checked_result_count: int
    violations: list[BenchmarkGateViolation] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return not self.violations

    @property
    def violation_count(self) -> int:
        return len(self.violations)

    def to_dict(self) -> JSONDict:
        return {
            "passed": self.passed,
            "budget_count": len(self.budgets),
            "checked_result_count": self.checked_result_count,
            "violation_count": self.violation_count,
            "budgets": [budget.to_dict() for budget in self.budgets],
            "violations": [violation.to_dict() for violation in self.violations],
        }

    def to_json(self) -> str:
        return dump_json(self.to_dict())

    def to_markdown(self) -> str:
        status = "passed" if self.passed else "failed"
        lines = [
            "# Benchmark Gate Report",
            "",
            f"Status: {status}",
            f"Budgets: {len(self.budgets)}",
            f"Checked results: {self.checked_result_count}",
            f"Violations: {self.violation_count}",
        ]
        if self.violations:
            lines.extend(
                [
                    "",
                    "| provider | operation | metric | observed | threshold | condition | budget |",
                    "| --- | --- | --- | ---: | ---: | --- | --- |",
                ]
            )
            lines.extend(
                (
                    "| "
                    f"{violation.provider} | "
                    f"{violation.operation} | "
                    f"{violation.metric} | "
                    f"{_format_optional_number(violation.observed)} | "
                    f"{_format_optional_number(violation.threshold)} | "
                    f"{violation.condition} | "
                    f"{violation.budget_selector} |"
                )
                for violation in self.violations
            )
        return "\n".join(lines)

    def to_csv(self) -> str:
        buffer = io.StringIO()
        writer = csv.DictWriter(
            buffer,
            fieldnames=[
                "provider",
                "operation",
                "metric",
                "observed",
                "threshold",
                "condition",
                "budget_selector",
            ],
        )
        writer.writeheader()
        for violation in self.violations:
            writer.writerow(
                {
                    "provider": violation.provider,
                    "operation": violation.operation,
                    "metric": violation.metric,
                    "observed": _format_optional_number(violation.observed),
                    "threshold": _format_optional_number(violation.threshold),
                    "condition": violation.condition,
                    "budget_selector": violation.budget_selector,
                }
            )
        return buffer.getvalue().strip()


def load_benchmark_budgets(payload: object) -> list[BenchmarkBudget]:
    """Parse benchmark budget JSON from a list or ``{"budgets": [...]}`` object.

    Each entry's ``provider`` and ``operation`` fields are optional: omit them to apply the
    budget's thresholds as a wildcard across every provider/operation pair in the run. Raises
    :class:`WorldForgeError` if the payload is empty, the wrapper carries unknown keys, or any
    individual budget entry fails validation.
    """

    budget_entries = payload
    if isinstance(payload, dict):
        _reject_unknown_keys(
            payload,
            allowed=_BENCHMARK_BUDGET_WRAPPER_KEYS,
            name="Benchmark budget payload",
        )
        budget_entries = payload.get("budgets")
    if not isinstance(budget_entries, list) or not budget_entries:
        raise WorldForgeError(
            "Benchmark budget payload must be a non-empty list or an object with a non-empty "
            "'budgets' list."
        )
    return [BenchmarkBudget.from_dict(entry) for entry in budget_entries]


@dataclass(slots=True)
class BenchmarkInputs:
    """Inputs the benchmark harness drives into each provider operation.

    Every field has a deterministic default so a benchmark run can succeed without
    user-supplied JSON. Override any subset to tune the workload — for example, supply a
    longer ``generation_prompt`` or a larger ``transfer_clip`` for media providers, or a
    structured ``policy_info`` for embodied policy adapters. All fields are validated at
    construction; pass invalid values and :class:`WorldForgeError` is raised before the
    benchmark starts.
    """

    prediction_action: Action = field(default_factory=lambda: Action.move_to(0.25, 0.5, 0.0))
    prediction_steps: int = 2
    reason_query: str = "How many objects are tracked?"
    generation_prompt: str = "benchmark orbiting cube"
    generation_duration_seconds: float = 1.0
    transfer_prompt: str = "benchmark transfer rerender"
    transfer_width: int = 320
    transfer_height: int = 180
    transfer_fps: float = 12.0
    transfer_clip: VideoClip = field(default_factory=_sample_transfer_clip)
    embedding_text: str = "benchmark cube state"
    score_info: JSONDict = field(default_factory=_sample_score_info)
    score_action_candidates: object = field(default_factory=_sample_score_action_candidates)
    policy_info: JSONDict = field(default_factory=_sample_policy_info)

    def __post_init__(self) -> None:
        if not isinstance(self.prediction_action, Action):
            raise WorldForgeError("prediction_action must be an Action.")
        self.prediction_steps = require_positive_int(
            self.prediction_steps,
            name="prediction_steps",
        )
        self.generation_duration_seconds = _positive_number(
            self.generation_duration_seconds,
            name="generation_duration_seconds",
        )
        self.transfer_width = require_positive_int(self.transfer_width, name="transfer_width")
        self.transfer_height = require_positive_int(self.transfer_height, name="transfer_height")
        self.transfer_fps = _positive_number(self.transfer_fps, name="transfer_fps")
        if not isinstance(self.transfer_clip, VideoClip):
            raise WorldForgeError("transfer_clip must be a VideoClip.")
        if not isinstance(self.embedding_text, str) or not self.embedding_text.strip():
            raise WorldForgeError("embedding_text must be a non-empty string.")
        if not isinstance(self.score_info, dict) or not self.score_info:
            raise WorldForgeError("score_info must be a non-empty JSON object.")
        dump_json(self.score_info)
        if self.score_action_candidates is None:
            raise WorldForgeError("score_action_candidates must not be None.")
        if not isinstance(self.policy_info, dict) or not self.policy_info:
            raise WorldForgeError("policy_info must be a non-empty JSON object.")
        dump_json(self.policy_info)

    def to_dict(self) -> JSONDict:
        return {
            "prediction_action": self.prediction_action.to_dict(),
            "prediction_steps": self.prediction_steps,
            "reason_query": self.reason_query,
            "generation_prompt": self.generation_prompt,
            "generation_duration_seconds": self.generation_duration_seconds,
            "transfer_prompt": self.transfer_prompt,
            "transfer_width": self.transfer_width,
            "transfer_height": self.transfer_height,
            "transfer_fps": self.transfer_fps,
            "transfer_clip": self.transfer_clip.to_dict(),
            "embedding_text": self.embedding_text,
            "score_info": dict(self.score_info),
            "score_action_candidates": _json_input_preview(self.score_action_candidates),
            "policy_info": dict(self.policy_info),
        }


def load_benchmark_inputs(
    payload: object,
    *,
    base_path: str | Path | None = None,
) -> BenchmarkInputs:
    """Parse benchmark input JSON into a validated :class:`BenchmarkInputs`.

    Omitted fields keep deterministic defaults. Relative ``transfer_clip.path`` values resolve
    against ``base_path`` when supplied, which lets benchmark input files carry portable media
    references next to the JSON fixture. Raises :class:`WorldForgeError` if ``payload`` is not
    a JSON object, contains unknown keys, or carries values that fail the same construction
    checks :class:`BenchmarkInputs` enforces directly (positive sizes, finite durations,
    JSON-serialisable score and policy info).
    """

    data = _benchmark_inputs_payload(payload)
    defaults = BenchmarkInputs()
    resolved_base_path = Path(base_path).expanduser().resolve() if base_path is not None else None

    prediction_action = defaults.prediction_action
    if "prediction_action" in data:
        if not isinstance(data["prediction_action"], dict):
            raise WorldForgeError("prediction_action must be a JSON object.")
        prediction_action = Action.from_dict(data["prediction_action"])

    score_action_candidates = defaults.score_action_candidates
    if "score_action_candidates" in data:
        score_action_candidates = data["score_action_candidates"]
        dump_json(score_action_candidates)

    return BenchmarkInputs(
        prediction_action=prediction_action,
        prediction_steps=(
            _positive_int(data["prediction_steps"], name="prediction_steps")
            if "prediction_steps" in data
            else defaults.prediction_steps
        ),
        reason_query=(
            _required_text(data["reason_query"], name="reason_query")
            if "reason_query" in data
            else defaults.reason_query
        ),
        generation_prompt=(
            _required_text(data["generation_prompt"], name="generation_prompt")
            if "generation_prompt" in data
            else defaults.generation_prompt
        ),
        generation_duration_seconds=(
            _positive_number(
                data["generation_duration_seconds"],
                name="generation_duration_seconds",
            )
            if "generation_duration_seconds" in data
            else defaults.generation_duration_seconds
        ),
        transfer_prompt=(
            _required_text(data["transfer_prompt"], name="transfer_prompt")
            if "transfer_prompt" in data
            else defaults.transfer_prompt
        ),
        transfer_width=(
            _positive_int(data["transfer_width"], name="transfer_width")
            if "transfer_width" in data
            else defaults.transfer_width
        ),
        transfer_height=(
            _positive_int(data["transfer_height"], name="transfer_height")
            if "transfer_height" in data
            else defaults.transfer_height
        ),
        transfer_fps=(
            _positive_number(data["transfer_fps"], name="transfer_fps")
            if "transfer_fps" in data
            else defaults.transfer_fps
        ),
        transfer_clip=(
            _load_transfer_clip(data["transfer_clip"], base_path=resolved_base_path)
            if "transfer_clip" in data
            else defaults.transfer_clip
        ),
        embedding_text=(
            _required_text(data["embedding_text"], name="embedding_text")
            if "embedding_text" in data
            else defaults.embedding_text
        ),
        score_info=(
            _required_json_object(data["score_info"], name="score_info")
            if "score_info" in data
            else defaults.score_info
        ),
        score_action_candidates=score_action_candidates,
        policy_info=(
            _required_json_object(data["policy_info"], name="policy_info")
            if "policy_info" in data
            else defaults.policy_info
        ),
    )


@dataclass(slots=True)
class BenchmarkResult:
    """Aggregate result for one provider/operation benchmark case."""

    provider: str
    operation: str
    iterations: int
    concurrency: int
    success_count: int
    error_count: int
    retry_count: int
    total_time_ms: float
    average_latency_ms: float | None
    min_latency_ms: float | None
    max_latency_ms: float | None
    p50_latency_ms: float | None
    p95_latency_ms: float | None
    throughput_per_second: float
    operation_metrics: JSONDict = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.provider = _required_text(self.provider, name="BenchmarkResult provider")
        self.operation = _required_text(self.operation, name="BenchmarkResult operation")
        if self.operation not in BENCHMARKABLE_OPERATIONS:
            known = ", ".join(BENCHMARKABLE_OPERATIONS)
            raise WorldForgeError(f"BenchmarkResult operation must be one of: {known}.")
        self.iterations = require_positive_int(self.iterations, name="BenchmarkResult iterations")
        self.concurrency = require_positive_int(
            self.concurrency,
            name="BenchmarkResult concurrency",
        )
        self.success_count = require_non_negative_int(
            self.success_count,
            name="BenchmarkResult success_count",
        )
        self.error_count = require_non_negative_int(
            self.error_count,
            name="BenchmarkResult error_count",
        )
        if self.success_count + self.error_count != self.iterations:
            raise WorldForgeError(
                "BenchmarkResult success_count and error_count must sum to iterations."
            )
        self.retry_count = require_non_negative_int(
            self.retry_count,
            name="BenchmarkResult retry_count",
        )
        self.total_time_ms = _non_negative_number(
            self.total_time_ms,
            name="BenchmarkResult total_time_ms",
        )
        self.average_latency_ms = _optional_non_negative_number(
            self.average_latency_ms,
            name="BenchmarkResult average_latency_ms",
        )
        self.min_latency_ms = _optional_non_negative_number(
            self.min_latency_ms,
            name="BenchmarkResult min_latency_ms",
        )
        self.max_latency_ms = _optional_non_negative_number(
            self.max_latency_ms,
            name="BenchmarkResult max_latency_ms",
        )
        self.p50_latency_ms = _optional_non_negative_number(
            self.p50_latency_ms,
            name="BenchmarkResult p50_latency_ms",
        )
        self.p95_latency_ms = _optional_non_negative_number(
            self.p95_latency_ms,
            name="BenchmarkResult p95_latency_ms",
        )
        self.throughput_per_second = _non_negative_number(
            self.throughput_per_second,
            name="BenchmarkResult throughput_per_second",
        )
        self.operation_metrics = require_json_dict(
            self.operation_metrics,
            name="BenchmarkResult operation_metrics",
        )
        if not isinstance(self.errors, list) or not all(
            isinstance(error, str) and error for error in self.errors
        ):
            raise WorldForgeError("BenchmarkResult errors must be a list of non-empty strings.")
        if len(self.errors) != self.error_count:
            raise WorldForgeError("BenchmarkResult errors length must match error_count.")
        self.errors = list(self.errors)

    def to_dict(self) -> JSONDict:
        return {
            "provider": self.provider,
            "operation": self.operation,
            "iterations": self.iterations,
            "concurrency": self.concurrency,
            "success_count": self.success_count,
            "error_count": self.error_count,
            "retry_count": self.retry_count,
            "total_time_ms": self.total_time_ms,
            "average_latency_ms": self.average_latency_ms,
            "min_latency_ms": self.min_latency_ms,
            "max_latency_ms": self.max_latency_ms,
            "p50_latency_ms": self.p50_latency_ms,
            "p95_latency_ms": self.p95_latency_ms,
            "throughput_per_second": self.throughput_per_second,
            "operation_metrics": dict(self.operation_metrics),
            "errors": list(self.errors),
        }


def _add_max_violation(
    violations: list[BenchmarkGateViolation],
    *,
    budget: BenchmarkBudget,
    result: BenchmarkResult,
    metric: str,
    observed: float | int | None,
    threshold: float | int | None,
) -> None:
    if threshold is None:
        return
    if observed is None or observed > threshold:
        violations.append(
            BenchmarkGateViolation(
                provider=result.provider,
                operation=result.operation,
                metric=metric,
                observed=observed,
                threshold=threshold,
                condition=f"<= {_format_optional_number(threshold)}",
                budget_selector=budget.selector_label(),
            )
        )


def _add_min_violation(
    violations: list[BenchmarkGateViolation],
    *,
    budget: BenchmarkBudget,
    result: BenchmarkResult,
    metric: str,
    observed: float | int | None,
    threshold: float | int | None,
) -> None:
    if threshold is None:
        return
    if observed is None or observed < threshold:
        violations.append(
            BenchmarkGateViolation(
                provider=result.provider,
                operation=result.operation,
                metric=metric,
                observed=observed,
                threshold=threshold,
                condition=f">= {_format_optional_number(threshold)}",
                budget_selector=budget.selector_label(),
            )
        )


def _evaluate_budget_for_result(
    budget: BenchmarkBudget,
    result: BenchmarkResult,
) -> list[BenchmarkGateViolation]:
    violations: list[BenchmarkGateViolation] = []
    success_rate = result.success_count / result.iterations if result.iterations else None
    _add_min_violation(
        violations,
        budget=budget,
        result=result,
        metric="success_rate",
        observed=success_rate,
        threshold=budget.min_success_rate,
    )
    _add_max_violation(
        violations,
        budget=budget,
        result=result,
        metric="error_count",
        observed=result.error_count,
        threshold=budget.max_error_count,
    )
    _add_max_violation(
        violations,
        budget=budget,
        result=result,
        metric="retry_count",
        observed=result.retry_count,
        threshold=budget.max_retry_count,
    )
    _add_max_violation(
        violations,
        budget=budget,
        result=result,
        metric="average_latency_ms",
        observed=result.average_latency_ms,
        threshold=budget.max_average_latency_ms,
    )
    _add_max_violation(
        violations,
        budget=budget,
        result=result,
        metric="p95_latency_ms",
        observed=result.p95_latency_ms,
        threshold=budget.max_p95_latency_ms,
    )
    _add_min_violation(
        violations,
        budget=budget,
        result=result,
        metric="throughput_per_second",
        observed=result.throughput_per_second,
        threshold=budget.min_throughput_per_second,
    )
    return violations


@dataclass(slots=True)
class BenchmarkReport:
    """Materialized benchmark report with export helpers."""

    results: list[BenchmarkResult]
    run_metadata: JSONDict = field(default_factory=dict)
    provenance: ProvenanceEnvelope | None = None

    def __post_init__(self) -> None:
        self.run_metadata = require_json_dict(
            self.run_metadata,
            name="BenchmarkReport run_metadata",
        )
        if not isinstance(self.results, list) or not all(
            isinstance(result, BenchmarkResult) for result in self.results
        ):
            raise WorldForgeError("BenchmarkReport results must contain only BenchmarkResult.")
        if self.provenance is not None:
            if not isinstance(self.provenance, ProvenanceEnvelope):
                raise WorldForgeError(
                    "BenchmarkReport provenance must be a ProvenanceEnvelope or None."
                )
            if self.provenance.kind != "benchmark":
                raise WorldForgeError("BenchmarkReport provenance must have kind='benchmark'.")

    def to_dict(self) -> JSONDict:
        payload: JSONDict = {
            "claim_boundary": BENCHMARK_CLAIM_BOUNDARY,
            "metric_semantics": BENCHMARK_METRIC_SEMANTICS,
            "run_metadata": dict(self.run_metadata),
            "results": [result.to_dict() for result in self.results],
        }
        if self.provenance is not None:
            payload["provenance"] = self.provenance.to_dict()
        return payload

    def to_json(self) -> str:
        return dump_json(self.to_dict())

    def to_markdown(self) -> str:
        lines = [
            "# Benchmark Report",
            "",
            f"Claim boundary: {BENCHMARK_CLAIM_BOUNDARY}",
            f"Metric semantics: {BENCHMARK_METRIC_SEMANTICS}",
            "",
        ]
        lines.extend(_benchmark_provenance_markdown_lines(self.provenance))
        lines.extend(
            [
                "| provider | operation | ok | retries | avg_ms | p95_ms | throughput/s |",
                "| --- | --- | ---: | ---: | ---: | ---: | ---: |",
            ]
        )
        lines.extend(
            (
                f"| {result.provider} | {result.operation} | "
                f"{result.success_count}/{result.iterations} | {result.retry_count} | "
                f"{(result.average_latency_ms or 0.0):.2f} | "
                f"{(result.p95_latency_ms or 0.0):.2f} | "
                f"{result.throughput_per_second:.2f} |"
            )
            for result in self.results
        )
        return "\n".join(lines)

    def to_csv(self) -> str:
        buffer = io.StringIO()
        writer = csv.DictWriter(
            buffer,
            fieldnames=[
                "provider",
                "operation",
                "iterations",
                "concurrency",
                "success_count",
                "error_count",
                "retry_count",
                "total_time_ms",
                "average_latency_ms",
                "min_latency_ms",
                "max_latency_ms",
                "p50_latency_ms",
                "p95_latency_ms",
                "throughput_per_second",
                "operation_metrics_json",
                "errors_json",
            ],
        )
        writer.writeheader()
        for result in self.results:
            writer.writerow(
                {
                    "provider": result.provider,
                    "operation": result.operation,
                    "iterations": result.iterations,
                    "concurrency": result.concurrency,
                    "success_count": result.success_count,
                    "error_count": result.error_count,
                    "retry_count": result.retry_count,
                    "total_time_ms": f"{result.total_time_ms:.4f}",
                    "average_latency_ms": (
                        f"{result.average_latency_ms:.4f}"
                        if result.average_latency_ms is not None
                        else ""
                    ),
                    "min_latency_ms": (
                        f"{result.min_latency_ms:.4f}" if result.min_latency_ms is not None else ""
                    ),
                    "max_latency_ms": (
                        f"{result.max_latency_ms:.4f}" if result.max_latency_ms is not None else ""
                    ),
                    "p50_latency_ms": (
                        f"{result.p50_latency_ms:.4f}" if result.p50_latency_ms is not None else ""
                    ),
                    "p95_latency_ms": (
                        f"{result.p95_latency_ms:.4f}" if result.p95_latency_ms is not None else ""
                    ),
                    "throughput_per_second": f"{result.throughput_per_second:.4f}",
                    "operation_metrics_json": dump_json(result.operation_metrics),
                    "errors_json": dump_json(result.errors),
                }
            )
        return buffer.getvalue().strip()

    def artifacts(self) -> dict[str, str]:
        return {
            "json": self.to_json(),
            "markdown": self.to_markdown(),
            "csv": self.to_csv(),
        }

    def evaluate_budgets(
        self,
        budgets: Sequence[BenchmarkBudget],
    ) -> BenchmarkGateReport:
        """Evaluate release or claim budgets against materialized benchmark results."""

        if not budgets:
            raise WorldForgeError("evaluate_budgets() requires at least one BenchmarkBudget.")

        violations: list[BenchmarkGateViolation] = []
        checked_result_count = 0
        for budget in budgets:
            if not isinstance(budget, BenchmarkBudget):
                raise WorldForgeError("evaluate_budgets() accepts only BenchmarkBudget entries.")
            matched_results = [result for result in self.results if budget.matches(result)]
            if not matched_results:
                violations.append(
                    BenchmarkGateViolation(
                        provider=budget.provider or "*",
                        operation=budget.operation or "*",
                        metric="matching_results",
                        observed=0,
                        threshold=1,
                        condition=">= 1 matching result",
                        budget_selector=budget.selector_label(),
                    )
                )
                continue

            checked_result_count += len(matched_results)
            for result in matched_results:
                violations.extend(_evaluate_budget_for_result(budget, result))

        return BenchmarkGateReport(
            budgets=list(budgets),
            checked_result_count=checked_result_count,
            violations=violations,
        )


@dataclass(slots=True)
class _BenchmarkSample:
    latency_ms: float
    error: str | None = None

    @property
    def succeeded(self) -> bool:
        return self.error is None

    def to_dict(self) -> JSONDict:
        return {
            "latency_ms": self.latency_ms,
            "error": self.error,
            "succeeded": self.succeeded,
        }


class ProviderBenchmarkHarness:
    """Run latency, retry, and throughput benchmarks across registered providers."""

    benchmarkable_operations = BENCHMARKABLE_OPERATIONS

    def __init__(self, forge: WorldForge | None = None) -> None:
        self._forge = forge or WorldForge()
        self._operation_handlers: dict[str, Callable[[str, BenchmarkInputs], None]] = {
            "predict": self._op_predict,
            "reason": self._op_reason,
            "generate": self._op_generate,
            "transfer": self._op_transfer,
            "embed": self._op_embed,
            "score": self._op_score,
            "policy": self._op_policy,
        }

    def supported_operations(self, provider: str) -> list[str]:
        profile = self._forge.provider_profile(provider)
        return [
            operation
            for operation in self.benchmarkable_operations
            if profile.capabilities.supports(operation)
        ]

    def _seed_world(self, provider: str) -> tuple[object, object]:
        world = self._forge.create_world("benchmark-world", provider)
        cube = world.add_object(
            SceneObject(
                "cube",
                Position(0.0, 0.5, 0.0),
                BBox(Position(-0.05, 0.45, -0.05), Position(0.05, 0.55, 0.05)),
                is_graspable=True,
            )
        )
        mug = world.add_object(
            SceneObject(
                "mug",
                Position(0.25, 0.8, 0.0),
                BBox(Position(0.2, 0.75, -0.05), Position(0.3, 0.85, 0.05)),
                is_graspable=True,
            )
        )
        return world, (cube, mug)

    def _op_predict(self, provider: str, inputs: BenchmarkInputs) -> None:
        world, _ = self._seed_world(provider)
        world.predict(
            inputs.prediction_action,
            steps=inputs.prediction_steps,
            provider=provider,
        )

    def _op_reason(self, provider: str, inputs: BenchmarkInputs) -> None:
        world, _ = self._seed_world(provider)
        self._forge.reason(provider, inputs.reason_query, world=world)

    def _op_generate(self, provider: str, inputs: BenchmarkInputs) -> None:
        self._forge.generate(
            inputs.generation_prompt,
            provider,
            duration_seconds=inputs.generation_duration_seconds,
        )

    def _op_transfer(self, provider: str, inputs: BenchmarkInputs) -> None:
        self._forge.transfer(
            inputs.transfer_clip,
            provider,
            width=inputs.transfer_width,
            height=inputs.transfer_height,
            fps=inputs.transfer_fps,
            prompt=inputs.transfer_prompt,
        )

    def _op_embed(self, provider: str, inputs: BenchmarkInputs) -> None:
        self._forge.embed(provider, text=inputs.embedding_text)

    def _op_score(self, provider: str, inputs: BenchmarkInputs) -> None:
        self._forge.score_actions(
            provider,
            info=inputs.score_info,
            action_candidates=inputs.score_action_candidates,
        )

    def _op_policy(self, provider: str, inputs: BenchmarkInputs) -> None:
        self._forge.select_actions(provider, info=inputs.policy_info)

    def _invoke_operation(
        self,
        provider: str,
        operation: str,
        inputs: BenchmarkInputs,
    ) -> None:
        handler = self._operation_handlers.get(operation)
        if handler is None:
            raise WorldForgeError(
                f"Unknown benchmark operation '{operation}'. "
                f"Known operations: {', '.join(self.benchmarkable_operations)}."
            )
        handler(provider, inputs)

    def _sample_once(
        self,
        provider: str,
        operation: str,
        inputs: BenchmarkInputs,
    ) -> _BenchmarkSample:
        started = perf_counter()
        try:
            self._invoke_operation(provider, operation, inputs)
        except (ProviderError, WorldForgeError, TimeoutError) as exc:
            return _BenchmarkSample(
                latency_ms=max(0.1, (perf_counter() - started) * 1000),
                error=str(exc),
            )
        return _BenchmarkSample(latency_ms=max(0.1, (perf_counter() - started) * 1000))

    @contextmanager
    def _capture_metrics(self, provider: str):
        metrics = ProviderMetricsSink()
        provider_instance = self._forge._providers.get(provider)
        capability_wrappers = self._forge._capability_wrappers_for_name(provider)
        if provider_instance is None and not capability_wrappers:
            raise ProviderError(f"Provider '{provider}' is not registered.")
        original_provider_handler = provider_instance.event_handler if provider_instance else None
        original_capability_handlers = [wrapper.event_handler for wrapper in capability_wrappers]
        if provider_instance is not None:
            provider_instance.event_handler = compose_event_handlers(
                original_provider_handler,
                metrics,
            )
        for wrapper, original_handler in zip(
            capability_wrappers,
            original_capability_handlers,
            strict=True,
        ):
            wrapper.event_handler = compose_event_handlers(original_handler, metrics)
        try:
            yield metrics
        finally:
            if provider_instance is not None:
                provider_instance.event_handler = original_provider_handler
            for wrapper, original_handler in zip(
                capability_wrappers,
                original_capability_handlers,
                strict=True,
            ):
                wrapper.event_handler = original_handler

    def _run_operation(
        self,
        provider: str,
        operation: str,
        *,
        iterations: int,
        concurrency: int,
        inputs: BenchmarkInputs,
        on_sample: Callable[[JSONDict], None] | None = None,
    ) -> BenchmarkResult:
        started = perf_counter()
        samples: list[_BenchmarkSample] = []
        with self._capture_metrics(provider) as metrics:
            with ThreadPoolExecutor(max_workers=concurrency) as executor:
                futures = [
                    executor.submit(self._sample_once, provider, operation, inputs)
                    for _ in range(iterations)
                ]
                for future in as_completed(futures):
                    sample = future.result()
                    samples.append(sample)
                    if on_sample is not None:
                        on_sample(
                            {
                                "provider": provider,
                                "operation": operation,
                                "iteration": len(samples),
                                **sample.to_dict(),
                            }
                        )

            provider_metrics = [
                metric.to_dict() for metric in metrics.snapshot() if metric.provider == provider
            ]

        total_time_ms = max(0.1, (perf_counter() - started) * 1000)
        successful_latencies = [sample.latency_ms for sample in samples if sample.succeeded]
        errors = [sample.error for sample in samples if sample.error is not None]
        retry_count = sum(metric["retry_count"] for metric in provider_metrics)
        total_seconds = total_time_ms / 1000
        throughput = len(successful_latencies) / total_seconds if total_seconds > 0 else 0.0

        average_latency_ms = (
            sum(successful_latencies) / len(successful_latencies) if successful_latencies else None
        )
        min_latency_ms = min(successful_latencies) if successful_latencies else None
        max_latency_ms = max(successful_latencies) if successful_latencies else None

        return BenchmarkResult(
            provider=provider,
            operation=operation,
            iterations=iterations,
            concurrency=concurrency,
            success_count=len(successful_latencies),
            error_count=len(errors),
            retry_count=retry_count,
            total_time_ms=total_time_ms,
            average_latency_ms=average_latency_ms,
            min_latency_ms=min_latency_ms,
            max_latency_ms=max_latency_ms,
            p50_latency_ms=_percentile(successful_latencies, 0.50),
            p95_latency_ms=_percentile(successful_latencies, 0.95),
            throughput_per_second=throughput,
            operation_metrics={
                "provider": provider,
                "operation": operation,
                "events": provider_metrics,
            },
            errors=[error for error in errors if error is not None],
        )

    def run(
        self,
        providers: str | Sequence[str],
        *,
        operations: Sequence[str] | None = None,
        iterations: int = 5,
        concurrency: int = 1,
        inputs: BenchmarkInputs | None = None,
        on_sample: Callable[[JSONDict], None] | None = None,
    ) -> BenchmarkReport:
        provider_names = [providers] if isinstance(providers, str) else list(providers)
        if not provider_names:
            raise WorldForgeError("Benchmark run requires at least one provider.")
        require_positive_int(iterations, name="iterations")
        require_positive_int(concurrency, name="concurrency")
        benchmark_inputs = inputs or BenchmarkInputs()

        requested_operations = list(dict.fromkeys(operations or self.benchmarkable_operations))
        unknown_operations = [
            operation
            for operation in requested_operations
            if operation not in self.benchmarkable_operations
        ]
        if unknown_operations:
            joined = ", ".join(unknown_operations)
            raise WorldForgeError(
                f"Unknown benchmark operations: {joined}. "
                f"Known operations: {', '.join(self.benchmarkable_operations)}."
            )

        provider_plan: list[tuple[str, list[str]]] = []
        for provider in provider_names:
            if provider not in self._forge.providers():
                raise ProviderError(f"Provider '{provider}' is not registered.")
            supported = self.supported_operations(provider)
            selected_operations = supported if operations is None else list(requested_operations)
            unsupported = [
                operation for operation in selected_operations if operation not in supported
            ]
            if unsupported:
                joined = ", ".join(unsupported)
                raise WorldForgeError(
                    f"Provider '{provider}' cannot benchmark unsupported operations: {joined}."
                )
            if not selected_operations:
                raise WorldForgeError(
                    f"Provider '{provider}' does not expose benchmarkable operations."
                )
            provider_plan.append((provider, selected_operations))

        selected_operations_by_provider = {
            provider: list(selected_operations) for provider, selected_operations in provider_plan
        }

        def _run_provider(entry: tuple[str, list[str]]) -> list[BenchmarkResult]:
            # Run all operations for one provider sequentially. `_capture_metrics`
            # swaps the provider instance's `event_handler`, so two operations on
            # the *same* provider cannot overlap — but *different* providers
            # operate on different instances and run safely in parallel.
            provider, selected_operations = entry
            return [
                self._run_operation(
                    provider,
                    operation,
                    iterations=iterations,
                    concurrency=concurrency,
                    inputs=benchmark_inputs,
                    on_sample=on_sample,
                )
                for operation in selected_operations
            ]

        results: list[BenchmarkResult] = []
        if len(provider_plan) <= 1:
            for entry in provider_plan:
                results.extend(_run_provider(entry))
        else:
            with ThreadPoolExecutor(max_workers=min(8, len(provider_plan))) as pool:
                for provider_results in pool.map(_run_provider, provider_plan):
                    results.extend(provider_results)
        capabilities = sorted(
            {
                operation
                for selected_operations in selected_operations_by_provider.values()
                for operation in selected_operations
            }
        )
        event_count = sum(
            int(event.get("request_count", 0))
            for result in results
            for event in result.operation_metrics.get("events", [])
            if isinstance(event, dict)
        )
        provenance = ProvenanceEnvelope(
            kind="benchmark",
            suite_id="benchmark",
            suite_version=f"benchmark:{BENCHMARK_SUITE_CONTRACT_VERSION}",
            providers=tuple(provider_names),
            capabilities=tuple(capabilities),
            runtime_manifests=collect_runtime_manifests(provider_names),
            input_digest=digest_payload(benchmark_inputs.to_dict()),
            result_digest=digest_payload([result.to_dict() for result in results]),
            event_count=event_count,
            claim_boundary=BENCHMARK_CLAIM_BOUNDARY,
            metric_semantics=BENCHMARK_METRIC_SEMANTICS,
        )
        return BenchmarkReport(
            results,
            run_metadata={
                "providers": list(provider_names),
                "requested_operations": list(requested_operations),
                "selected_operations": selected_operations_by_provider,
                "iterations": iterations,
                "concurrency": concurrency,
                "inputs": benchmark_inputs.to_dict(),
            },
            provenance=provenance,
        )


def run_benchmark(
    providers: str | Sequence[str],
    *,
    forge: WorldForge | None = None,
    operations: Sequence[str] | None = None,
    iterations: int = 5,
    concurrency: int = 1,
    inputs: BenchmarkInputs | None = None,
    on_sample: Callable[[JSONDict], None] | None = None,
) -> BenchmarkReport:
    """Convenience wrapper around ProviderBenchmarkHarness.run()."""

    return ProviderBenchmarkHarness(forge=forge).run(
        providers,
        operations=operations,
        iterations=iterations,
        concurrency=concurrency,
        inputs=inputs,
        on_sample=on_sample,
    )


__all__ = [
    "BENCHMARKABLE_OPERATIONS",
    "BenchmarkBudget",
    "BenchmarkGateReport",
    "BenchmarkGateViolation",
    "BenchmarkInputs",
    "BenchmarkReport",
    "BenchmarkResult",
    "ProviderBenchmarkHarness",
    "load_benchmark_budgets",
    "load_benchmark_inputs",
    "run_benchmark",
]

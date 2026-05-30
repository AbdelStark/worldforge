"""Benchmark input fixture contracts and loaders."""

from __future__ import annotations

from base64 import b64decode
from binascii import Error as BinasciiError
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from worldforge.benchmark_contracts import (
    _optional_json_object,
    _positive_int,
    _positive_number,
    _positive_resolution,
    _required_json_object,
    _required_text,
)
from worldforge.models import (
    Action,
    JSONDict,
    VideoClip,
    WorldForgeError,
    dump_json,
    require_finite_number,
    require_positive_int,
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

_BENCHMARK_INPUT_TEXT_FIELDS = (
    "reason_query",
    "generation_prompt",
    "transfer_prompt",
    "embedding_text",
)


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


def _load_prediction_action_input(value: object) -> Action:
    if not isinstance(value, dict):
        raise WorldForgeError("prediction_action must be a JSON object.")
    return Action.from_dict(value)


def _load_score_action_candidates_input(value: object) -> object:
    dump_json(value)
    return value


def _benchmark_input_field(
    data: JSONDict,
    defaults: BenchmarkInputs,
    field_name: str,
    parser: Callable[[object], object],
) -> object:
    if field_name not in data:
        return getattr(defaults, field_name)
    return parser(data[field_name])


def _benchmark_input_parsers(
    *,
    base_path: Path | None,
) -> tuple[tuple[str, Callable[[object], object]], ...]:
    return (
        ("prediction_action", _load_prediction_action_input),
        ("prediction_steps", lambda value: _positive_int(value, name="prediction_steps")),
        ("reason_query", lambda value: _required_text(value, name="reason_query")),
        ("generation_prompt", lambda value: _required_text(value, name="generation_prompt")),
        (
            "generation_duration_seconds",
            lambda value: _positive_number(value, name="generation_duration_seconds"),
        ),
        ("transfer_prompt", lambda value: _required_text(value, name="transfer_prompt")),
        ("transfer_width", lambda value: _positive_int(value, name="transfer_width")),
        ("transfer_height", lambda value: _positive_int(value, name="transfer_height")),
        ("transfer_fps", lambda value: _positive_number(value, name="transfer_fps")),
        ("transfer_clip", lambda value: _load_transfer_clip(value, base_path=base_path)),
        ("embedding_text", lambda value: _required_text(value, name="embedding_text")),
        ("score_info", lambda value: _required_json_object(value, name="score_info")),
        ("score_action_candidates", _load_score_action_candidates_input),
        ("policy_info", lambda value: _required_json_object(value, name="policy_info")),
    )


def _benchmark_prediction_action(value: object) -> Action:
    if not isinstance(value, Action):
        raise WorldForgeError("prediction_action must be an Action.")
    return value


def _benchmark_transfer_clip(value: object) -> VideoClip:
    if not isinstance(value, VideoClip):
        raise WorldForgeError("transfer_clip must be a VideoClip.")
    return value


def _benchmark_score_action_candidates(value: object) -> object:
    if value is None:
        raise WorldForgeError("score_action_candidates must not be None.")
    return value


def _validate_benchmark_input_text_fields(inputs: BenchmarkInputs) -> None:
    for field_name in _BENCHMARK_INPUT_TEXT_FIELDS:
        setattr(inputs, field_name, _required_text(getattr(inputs, field_name), name=field_name))


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
        self.prediction_action = _benchmark_prediction_action(self.prediction_action)
        self.prediction_steps = require_positive_int(
            self.prediction_steps,
            name="prediction_steps",
        )
        _validate_benchmark_input_text_fields(self)
        self.generation_duration_seconds = _positive_number(
            self.generation_duration_seconds,
            name="generation_duration_seconds",
        )
        self.transfer_width = require_positive_int(self.transfer_width, name="transfer_width")
        self.transfer_height = require_positive_int(self.transfer_height, name="transfer_height")
        self.transfer_fps = _positive_number(self.transfer_fps, name="transfer_fps")
        self.transfer_clip = _benchmark_transfer_clip(self.transfer_clip)
        self.score_info = _required_json_object(self.score_info, name="score_info")
        self.score_action_candidates = _benchmark_score_action_candidates(
            self.score_action_candidates
        )
        self.policy_info = _required_json_object(self.policy_info, name="policy_info")

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
    """Parse benchmark input JSON into a validated :class:`BenchmarkInputs`."""

    data = _benchmark_inputs_payload(payload)
    defaults = BenchmarkInputs()
    resolved_base_path = Path(base_path).expanduser().resolve() if base_path is not None else None
    field_values = {
        field_name: _benchmark_input_field(data, defaults, field_name, parser)
        for field_name, parser in _benchmark_input_parsers(base_path=resolved_base_path)
    }
    return BenchmarkInputs(**field_values)


__all__ = ["BenchmarkInputs", "load_benchmark_inputs"]

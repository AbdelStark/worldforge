"""Benchmark input fixture contracts and loaders."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from worldforge.benchmark_contracts import (
    _positive_int,
    _required_json_object,
    _required_text,
)
from worldforge.models import (
    Action,
    JSONDict,
    WorldForgeError,
    dump_json,
    require_positive_int,
)

_BENCHMARK_INPUT_KEYS = (
    "prediction_action",
    "prediction_steps",
    "embedding_text",
    "score_info",
    "score_action_candidates",
    "policy_info",
)

_BENCHMARK_INPUT_TEXT_FIELDS = ("embedding_text",)


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
    del base_path
    return (
        ("prediction_action", _load_prediction_action_input),
        ("prediction_steps", lambda value: _positive_int(value, name="prediction_steps")),
        ("embedding_text", lambda value: _required_text(value, name="embedding_text")),
        ("score_info", lambda value: _required_json_object(value, name="score_info")),
        ("score_action_candidates", _load_score_action_candidates_input),
        ("policy_info", lambda value: _required_json_object(value, name="policy_info")),
    )


def _benchmark_prediction_action(value: object) -> Action:
    if not isinstance(value, Action):
        raise WorldForgeError("prediction_action must be an Action.")
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
    structured ``policy_info`` for embodied policy adapters. All fields are validated at
    construction; pass invalid values and :class:`WorldForgeError` is raised before the
    benchmark starts.
    """

    prediction_action: Action = field(default_factory=lambda: Action.move_to(0.25, 0.5, 0.0))
    prediction_steps: int = 2
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
        self.score_info = _required_json_object(self.score_info, name="score_info")
        self.score_action_candidates = _benchmark_score_action_candidates(
            self.score_action_candidates
        )
        self.policy_info = _required_json_object(self.policy_info, name="policy_info")

    def to_dict(self) -> JSONDict:
        return {
            "prediction_action": self.prediction_action.to_dict(),
            "prediction_steps": self.prediction_steps,
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

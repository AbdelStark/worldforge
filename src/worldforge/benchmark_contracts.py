"""Shared benchmark constants and validation helpers."""

from __future__ import annotations

from collections.abc import Sequence

from worldforge.models import (
    JSONDict,
    WorldForgeError,
    dump_json,
    require_finite_number,
    require_non_negative_int,
    require_positive_int,
)

BENCHMARKABLE_OPERATIONS = (
    "predict",
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


def _comma_join_or_dash(values: Sequence[str]) -> str:
    return ", ".join(values) or "-"

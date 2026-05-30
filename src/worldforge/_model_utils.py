"""Core model validation helpers for WorldForge data contracts."""

from __future__ import annotations

import json
import math
from collections.abc import Iterable
from hashlib import sha256
from pathlib import Path
from typing import Any
from uuid import uuid4

JSONDict = dict[str, Any]


class WorldForgeError(ValueError):
    """Raised when a caller supplies invalid input to the framework."""


class WorldStateError(WorldForgeError):
    """Raised when persisted or provider-supplied world state is malformed."""


def generate_id(prefix: str) -> str:
    """Return an opaque identifier with a stable prefix."""

    return f"{prefix}_{uuid4().hex[:12]}"


def dump_json(payload: Any, *, indent: int | None = None) -> str:
    """Serialize data with deterministic formatting."""

    try:
        if indent is None:
            return json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False)
        return json.dumps(payload, sort_keys=True, indent=indent, allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise WorldForgeError(
            "Payload must be JSON serializable and contain only finite numbers."
        ) from exc


def _clone_json_value(value: Any, *, name: str) -> Any:
    """Return a JSON-native deep copy or raise for non-JSON values."""

    if value is None or isinstance(value, str | bool):
        return value
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return require_finite_number(value, name=name)
    if isinstance(value, list):
        return [_clone_json_value(item, name=f"{name}[]") for item in value]
    if isinstance(value, dict):
        cloned: JSONDict = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise WorldForgeError(f"{name} keys must be strings.")
            cloned[key] = _clone_json_value(item, name=f"{name}.{key}")
        return cloned
    raise WorldForgeError(f"{name} must contain only JSON-compatible values.")


def require_json_dict(value: Any, *, name: str, allow_empty: bool = True) -> JSONDict:
    """Return a JSON-native dict copy with string keys and finite numeric values."""

    if not isinstance(value, dict):
        raise WorldForgeError(f"{name} must be a JSON object.")
    if not allow_empty and not value:
        raise WorldForgeError(f"{name} must be a non-empty JSON object.")
    cloned = _clone_json_value(value, name=name)
    if not isinstance(cloned, dict):  # pragma: no cover - defensive invariant
        raise WorldForgeError(f"{name} must be a JSON object.")
    return cloned


def require_non_empty_text(value: object, *, name: str, message: str | None = None) -> str:
    if not isinstance(value, str) or not value.strip():
        raise WorldForgeError(message or f"{name} must be a non-empty string.")
    return value.strip()


def ensure_directory(path: Path) -> None:
    """Create a directory tree when it does not already exist."""

    path.mkdir(parents=True, exist_ok=True)


def average(values: Iterable[float]) -> float:
    """Return the arithmetic mean for a non-empty iterable."""

    numbers = list(values)
    if not numbers:
        return 0.0
    return sum(numbers) / len(numbers)


def require_positive_int(value: int, *, name: str) -> int:
    """Raise WorldForgeError unless ``value`` is a non-bool positive int."""

    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise WorldForgeError(f"{name} must be an integer greater than 0.")
    return value


def require_non_negative_int(value: int, *, name: str) -> int:
    """Raise WorldForgeError unless ``value`` is a non-bool integer >= 0."""

    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise WorldForgeError(f"{name} must be an integer greater than or equal to 0.")
    return value


def require_finite_number(value: float | int, *, name: str) -> float:
    """Raise WorldForgeError unless ``value`` is a finite real number."""

    if isinstance(value, bool) or not isinstance(value, int | float):
        raise WorldForgeError(f"{name} must be a finite number.")
    number = float(value)
    if not math.isfinite(number):
        raise WorldForgeError(f"{name} must be a finite number.")
    return number


def require_probability(value: float | int, *, name: str) -> float:
    """Raise WorldForgeError unless ``value`` is finite and within [0, 1]."""

    number = require_finite_number(value, name=name)
    if number < 0.0 or number > 1.0:
        raise WorldForgeError(f"{name} must be between 0 and 1.")
    return number


def require_bool(value: bool, *, name: str) -> bool:
    """Raise WorldForgeError unless ``value`` is a real boolean."""

    if not isinstance(value, bool):
        raise WorldForgeError(f"{name} must be a boolean.")
    return value


def deterministic_floats(seed: str, size: int) -> list[float]:
    """Generate deterministic floats in the range [0, 1)."""

    digest = sha256(seed.encode("utf-8")).digest()
    values: list[float] = []
    counter = 0
    while len(values) < size:
        block = sha256(digest + counter.to_bytes(4, "big")).digest()
        for index in range(0, len(block), 4):
            if len(values) >= size:
                break
            chunk = int.from_bytes(block[index : index + 4], "big")
            values.append((chunk % 10_000) / 10_000.0)
        counter += 1
    return values

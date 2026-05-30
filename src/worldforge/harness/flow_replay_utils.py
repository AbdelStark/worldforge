"""Shared validation and codec helpers for checkout-safe harness replays."""

from __future__ import annotations

import base64
import binascii
import json
import math
import struct
from collections.abc import Collection, Sequence
from pathlib import Path

from worldforge.models import JSONDict, WorldStateError

DEFAULT_ACTION_PREVIEW_LIMIT = 6
DEFAULT_ACTION_PREVIEW_COLUMNS = 6


def require_json_object(value: object, name: str) -> JSONDict:
    if not isinstance(value, dict):
        raise WorldStateError(f"{name} must be a JSON object.")
    return value


def read_replay_artifact(path: Path, label: str) -> JSONDict:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise WorldStateError(f"{label} replay artifact is not valid JSON: {path}") from exc
    if not isinstance(payload, dict):
        raise WorldStateError(f"{label} replay artifact must be a JSON object.")
    return payload


def require_exact_keys(
    value: JSONDict,
    expected_keys: Collection[str],
    error_message: str,
) -> None:
    if set(value) != set(expected_keys):
        raise WorldStateError(error_message)


def is_finite_number(value: object) -> bool:
    return isinstance(value, int | float) and not isinstance(value, bool) and math.isfinite(value)


def require_json_native_value(value: object, name: str) -> None:
    if value is None or isinstance(value, str | bool):
        return
    if isinstance(value, int | float):
        _require_json_native_number(value, name)
        return
    if isinstance(value, list):
        _require_json_native_list(value, name)
        return
    if isinstance(value, dict):
        _require_json_native_dict(value, name)
        return
    raise WorldStateError(f"{name} must be JSON-native.")


def validate_numeric_tensor(value: object, *, expected_shape: Sequence[int], name: str) -> None:
    if not expected_shape:
        if not is_finite_number(value):
            raise WorldStateError(f"{name} must contain finite numeric values.")
        return
    if not isinstance(value, list):
        raise WorldStateError(f"{name} must have shape {list(expected_shape)}.")
    if len(value) != expected_shape[0]:
        raise WorldStateError(f"{name} must have shape {list(expected_shape)}.")
    for index, item in enumerate(value):
        validate_numeric_tensor(
            item,
            expected_shape=expected_shape[1:],
            name=f"{name}[{index}]",
        )


def encode_json_numpy_action_row(row: Sequence[float], *, action_dim: int) -> JSONDict:
    values = _validated_action_row_values(row, action_dim=action_dim, label="action row")
    raw = struct.pack(f"<{action_dim}f", *values)
    return {
        "__numpy__": base64.b64encode(raw).decode("ascii"),
        "dtype": "<f4",
        "shape": [action_dim],
    }


def decode_json_numpy_action_row(
    value: object,
    *,
    row_index: int,
    action_dim: int,
    label: str = "Cosmos-Policy replay",
) -> list[float]:
    row = _json_numpy_action_row_object(value, row_index=row_index, label=label)
    encoded = _json_numpy_required_text(row, "__numpy__", row_index=row_index, label=label)
    dtype = _json_numpy_required_text(row, "dtype", row_index=row_index, label=label)
    endian_prefix, item_format, item_size = _json_numpy_float_format_for_replay(
        dtype,
        row_index=row_index,
        label=label,
    )
    _validate_json_numpy_action_shape(
        row,
        row_index=row_index,
        action_dim=action_dim,
        label=label,
    )
    expected_bytes = action_dim * item_size
    _validate_json_numpy_encoded_size(
        encoded,
        expected_bytes=expected_bytes,
        row_index=row_index,
        label=label,
    )
    raw = _decode_json_numpy_base64(
        encoded,
        expected_bytes=expected_bytes,
        row_index=row_index,
        label=label,
    )
    return _unpack_json_numpy_action_row(
        raw,
        endian_prefix=endian_prefix,
        item_format=item_format,
        action_dim=action_dim,
        row_index=row_index,
        label=label,
    )


def preview_action_rows(
    rows: object,
    *,
    limit: int = DEFAULT_ACTION_PREVIEW_LIMIT,
    columns: int = DEFAULT_ACTION_PREVIEW_COLUMNS,
) -> list[list[float]]:
    if not isinstance(rows, list):
        return []
    preview: list[list[float]] = []
    for row in rows[:limit]:
        preview_row = _preview_action_row(row, columns=columns)
        if preview_row is None:
            continue
        preview.append(preview_row)
    return preview


def _preview_action_row(row: object, *, columns: int) -> list[float] | None:
    if not isinstance(row, list):
        return None
    values = row[:columns]
    if not all(is_finite_number(value) for value in values):
        return None
    return [round(float(value), 5) for value in values]


def _validated_action_row_values(
    row: Sequence[float],
    *,
    action_dim: int,
    label: str,
) -> tuple[float, ...]:
    if len(row) != action_dim:
        raise WorldStateError(f"{label} must have shape [{action_dim}].")
    if not all(is_finite_number(value) for value in row):
        raise WorldStateError(f"{label} must contain finite numeric values.")
    return tuple(float(value) for value in row)


def _require_json_native_number(value: int | float, name: str) -> None:
    if isinstance(value, bool) or not math.isfinite(value):
        raise WorldStateError(f"{name} must be JSON-native and finite.")


def _require_json_native_list(value: list[object], name: str) -> None:
    for index, item in enumerate(value):
        require_json_native_value(item, f"{name}[{index}]")


def _require_json_native_dict(value: dict[object, object], name: str) -> None:
    for key, item in value.items():
        if not isinstance(key, str):
            raise WorldStateError(f"{name} keys must be strings.")
        require_json_native_value(item, f"{name}.{key}")


def _json_numpy_action_row_object(value: object, *, row_index: int, label: str) -> JSONDict:
    if not isinstance(value, dict):
        raise WorldStateError(f"{label} action row {row_index} must be JSON numpy.")
    return value


def _json_numpy_required_text(row: JSONDict, key: str, *, row_index: int, label: str) -> str:
    value = row.get(key)
    if isinstance(value, str) and value:
        return value
    if key == "__numpy__":
        raise WorldStateError(f"{label} action row {row_index} is missing __numpy__.")
    raise WorldStateError(f"{label} action row {row_index} must include a numeric dtype.")


def _validate_json_numpy_action_shape(
    row: JSONDict,
    *,
    row_index: int,
    action_dim: int,
    label: str,
) -> None:
    if row.get("shape") != [action_dim]:
        raise WorldStateError(f"{label} action row {row_index} must have shape [{action_dim}].")


def _validate_json_numpy_encoded_size(
    encoded: str,
    *,
    expected_bytes: int,
    row_index: int,
    label: str,
) -> None:
    expected_encoded_length = 4 * math.ceil(expected_bytes / 3)
    if len(encoded) > expected_encoded_length:
        raise WorldStateError(f"{label} action row {row_index} base64 payload is too large.")


def _decode_json_numpy_base64(
    encoded: str,
    *,
    expected_bytes: int,
    row_index: int,
    label: str,
) -> bytes:
    try:
        raw = base64.b64decode(encoded, validate=True)
    except (ValueError, binascii.Error) as exc:
        raise WorldStateError(f"{label} action row {row_index} has invalid base64.") from exc
    if len(raw) != expected_bytes:
        raise WorldStateError(
            f"{label} action row {row_index} must contain {expected_bytes} bytes."
        )
    return raw


def _unpack_json_numpy_action_row(
    raw: bytes,
    *,
    endian_prefix: str,
    item_format: str,
    action_dim: int,
    row_index: int,
    label: str,
) -> list[float]:
    decoded = list(struct.unpack(f"{endian_prefix}{action_dim}{item_format}", raw))
    if not all(math.isfinite(value) for value in decoded):
        raise WorldStateError(f"{label} action row {row_index} must be finite.")
    return decoded


def _json_numpy_float_format_for_replay(
    dtype: str,
    *,
    row_index: int,
    label: str,
) -> tuple[str, str, int]:
    normalized = dtype.strip().lower()
    if not normalized:
        raise WorldStateError(f"{label} action row {row_index} must include a numeric dtype.")
    endian_prefix = "<"
    if normalized[0] in ("<", ">", "=", "|"):
        endian_prefix = "=" if normalized[0] == "|" else normalized[0]
        normalized = normalized[1:]
    if normalized in ("f4", "float32"):
        return endian_prefix, "f", 4
    if normalized in ("f8", "float64"):
        return endian_prefix, "d", 8
    raise WorldStateError(f"{label} action row {row_index} dtype must be float32 or float64.")

"""Cosmos-Policy `/act` response parsing and numeric payload normalization."""

from __future__ import annotations

import base64
import binascii
import math
import struct
from collections.abc import Sequence
from dataclasses import dataclass, field

from worldforge.models import (
    JSONDict,
    WorldStateError,
    require_finite_number,
)

from ._policy import json_object
from .base import ProviderError

_JSON_NUMPY_DATA_FIELD = "__numpy__"
_MAX_JSON_NUMPY_ACTION_ELEMENTS = 1024
_PREDICTION_SUMMARY_MAX_DEPTH = 8
_PREDICTION_SUMMARY_MAX_KEYS = 32


@dataclass(slots=True, frozen=True)
class CosmosPolicyResponse:
    """Validated policy response from a Cosmos-Policy `/act` server."""

    actions: list[list[float]]
    value_prediction: float | None = None
    all_actions: list[list[list[float]]] = field(default_factory=list)
    all_value_predictions: list[float] = field(default_factory=list)
    future_prediction_summary: JSONDict = field(default_factory=dict)
    provider_info: JSONDict = field(default_factory=dict)

    @classmethod
    def from_payload(
        cls,
        payload: JSONDict,
        *,
        provider_name: str,
        expected_action_dim: int | None,
    ) -> CosmosPolicyResponse:
        if not isinstance(payload, dict):
            raise ProviderError(
                f"Provider '{provider_name}' policy response must be a JSON object."
            )
        actions = _normalize_action_matrix(
            payload.get("actions"),
            name=f"Provider '{provider_name}' policy response field 'actions'",
            expected_action_dim=expected_action_dim,
        )
        all_actions = _normalize_all_actions(
            payload.get("all_actions"),
            provider_name=provider_name,
            expected_action_dim=expected_action_dim,
        )
        value_prediction = _optional_float(
            payload.get("value_prediction"),
            name=f"Provider '{provider_name}' policy response field 'value_prediction'",
        )
        all_value_predictions = _all_value_predictions(
            payload=payload,
            provider_name=provider_name,
            all_actions=all_actions,
        )
        future_prediction_summary = _future_prediction_summary(payload)
        provider_info = _provider_info_payload(
            payload=payload,
            provider_name=provider_name,
            value_prediction=value_prediction,
            all_value_predictions=all_value_predictions,
            future_prediction_summary=future_prediction_summary,
        )
        return cls(
            actions=actions,
            value_prediction=value_prediction,
            all_actions=all_actions,
            all_value_predictions=all_value_predictions,
            future_prediction_summary=future_prediction_summary,
            provider_info=json_object(provider_info, name="Cosmos-Policy provider_info"),
        )


def _all_value_predictions(
    *,
    payload: JSONDict,
    provider_name: str,
    all_actions: list[list[list[float]]],
) -> list[float]:
    all_value_predictions = _optional_float_list(
        payload.get("all_value_predictions"),
        name=f"Provider '{provider_name}' policy response field 'all_value_predictions'",
    )
    if "all_value_predictions" not in payload:
        return all_value_predictions
    _validate_all_value_prediction_count(
        provider_name=provider_name,
        all_actions=all_actions,
        all_value_predictions=all_value_predictions,
    )
    return all_value_predictions


def _validate_all_value_prediction_count(
    *,
    provider_name: str,
    all_actions: list[list[list[float]]],
    all_value_predictions: list[float],
) -> None:
    if all_actions and len(all_value_predictions) != len(all_actions):
        raise ProviderError(
            f"Provider '{provider_name}' policy response field 'all_value_predictions' "
            f"must contain {len(all_actions)} value(s) to match 'all_actions'; "
            f"got {len(all_value_predictions)}."
        )
    if not all_actions and len(all_value_predictions) != 1:
        raise ProviderError(
            f"Provider '{provider_name}' policy response field 'all_value_predictions' "
            "must contain exactly 1 value when 'all_actions' is absent."
        )


def _provider_info_payload(
    *,
    payload: JSONDict,
    provider_name: str,
    value_prediction: float | None,
    all_value_predictions: list[float],
    future_prediction_summary: JSONDict,
) -> JSONDict:
    provider_info: JSONDict = {
        "value_prediction": value_prediction,
        "all_value_predictions": all_value_predictions,
        "future_prediction_summary": future_prediction_summary,
    }
    if "all_actions_by_depth" in payload:
        provider_info["all_actions_by_depth_shape"] = _bounded_shape(
            payload["all_actions_by_depth"]
        )
    if "all_value_predictions_by_depth" in payload:
        provider_info["all_value_predictions_by_depth"] = _optional_nested_float_lists(
            payload["all_value_predictions_by_depth"],
            name=(
                f"Provider '{provider_name}' policy response field 'all_value_predictions_by_depth'"
            ),
        )
    return provider_info


def _optional_float(value: object, *, name: str) -> float | None:
    if value is None:
        return None
    return require_finite_number(value, name=name)


def _optional_float_list(value: object, *, name: str) -> list[float]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise ProviderError(f"{name} must be a list when present.")
    return [
        require_finite_number(item, name=f"{name}[{index}]") for index, item in enumerate(value)
    ]


def _optional_nested_float_lists(value: object, *, name: str) -> list[list[float]]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise ProviderError(f"{name} must be a list when present.")
    nested: list[list[float]] = []
    for index, item in enumerate(value):
        nested.append(_optional_float_list(item, name=f"{name}[{index}]"))
    return nested


def _normalize_action_matrix(
    value: object,
    *,
    name: str,
    expected_action_dim: int | None,
) -> list[list[float]]:
    if not isinstance(value, list) or not value:
        raise ProviderError(f"{name} must be a non-empty action matrix.")
    rows: list[list[float]] = []
    width: int | None = None
    for row_index, raw_row in enumerate(value):
        row = _decode_json_numpy_action_row(
            raw_row,
            name=f"{name}[{row_index}]",
            expected_action_dim=expected_action_dim,
        )
        if not isinstance(row, list) or not row:
            raise ProviderError(f"{name}[{row_index}] must be a non-empty action row.")
        width = _validate_action_row_width(
            row,
            width=width,
            expected_action_dim=expected_action_dim,
            name=name,
            row_index=row_index,
        )
        rows.append(_finite_action_row(row, name=name, row_index=row_index))
    return rows


def _validate_action_row_width(
    row: list[object],
    *,
    width: int | None,
    expected_action_dim: int | None,
    name: str,
    row_index: int,
) -> int:
    if width is None:
        width = len(row)
        if expected_action_dim is not None and width != expected_action_dim:
            raise ProviderError(f"{name} action_dim must be {expected_action_dim}; got {width}.")
        return width
    if len(row) != width:
        raise ProviderError(f"{name} must be rectangular.")
    return width


def _finite_action_row(row: list[object], *, name: str, row_index: int) -> list[float]:
    return [
        require_finite_number(value, name=f"{name}[{row_index}][{column_index}]")
        for column_index, value in enumerate(row)
    ]


def _decode_json_numpy_action_row(
    value: object,
    *,
    name: str,
    expected_action_dim: int | None,
) -> object:
    if not _is_json_numpy_payload(value):
        return value
    array_shape = _json_numpy_shape(value, name=name)
    if len(array_shape) != 1:
        raise ProviderError(f"{name} must be a 1-D encoded numpy action row.")
    item_count = array_shape[0]
    if expected_action_dim is not None and item_count != expected_action_dim:
        raise ProviderError(f"{name} action_dim must be {expected_action_dim}; got {item_count}.")
    if item_count > _MAX_JSON_NUMPY_ACTION_ELEMENTS:
        raise ProviderError(
            f"{name} encoded action row exceeds {_MAX_JSON_NUMPY_ACTION_ELEMENTS} elements."
        )
    return _decode_json_numpy_numeric_array(value, name=name, array_shape=array_shape)


def _is_json_numpy_payload(value: object) -> bool:
    return isinstance(value, dict) and _JSON_NUMPY_DATA_FIELD in value


def _json_numpy_shape(value: object, *, name: str) -> list[int]:
    if not isinstance(value, dict):
        raise ProviderError(f"{name} must be an encoded numpy object.")
    shape = value.get("shape")
    if not isinstance(shape, list):
        raise ProviderError(f"{name}.shape must be a list of non-negative integers.")
    normalized_shape: list[int] = []
    for index, item in enumerate(shape):
        if isinstance(item, bool) or not isinstance(item, int) or item < 0:
            raise ProviderError(f"{name}.shape[{index}] must be a non-negative integer.")
        normalized_shape.append(item)
    return normalized_shape


def _decode_json_numpy_numeric_array(
    value: object,
    *,
    name: str,
    array_shape: Sequence[int] | None = None,
) -> list[float]:
    if not isinstance(value, dict):
        raise ProviderError(f"{name} must be an encoded numpy object.")
    if array_shape is None:
        array_shape = _json_numpy_shape(value, name=name)
    dtype = _json_numpy_dtype(value, name=name)
    item_count = _json_numpy_item_count(array_shape, name=name)
    raw_bytes = _json_numpy_raw_bytes(value, name=name)
    endian_prefix, item_format, item_size = _json_numpy_float_format(dtype, name=name)
    _check_json_numpy_byte_length(
        raw_bytes,
        expected_bytes=item_count * item_size,
        name=name,
    )
    decoded = _unpack_json_numpy_values(
        raw_bytes,
        item_count=item_count,
        endian_prefix=endian_prefix,
        item_format=item_format,
        name=name,
    )
    return _finite_json_numpy_values(decoded, name=name)


def _json_numpy_dtype(value: dict, *, name: str) -> str:
    dtype = value.get("dtype")
    if not isinstance(dtype, str) or not dtype.strip():
        raise ProviderError(f"{name}.dtype must be a non-empty string.")
    return dtype


def _json_numpy_item_count(array_shape: Sequence[int], *, name: str) -> int:
    item_count = 1
    for dimension in array_shape:
        item_count *= dimension
    if item_count <= 0:
        raise ProviderError(f"{name} must encode a non-empty action row.")
    return item_count


def _json_numpy_raw_bytes(value: dict, *, name: str) -> bytes:
    raw_payload = value.get(_JSON_NUMPY_DATA_FIELD)
    if not isinstance(raw_payload, str) or not raw_payload:
        raise ProviderError(f"{name}.{_JSON_NUMPY_DATA_FIELD} must be a non-empty string.")
    try:
        return base64.b64decode(raw_payload, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise ProviderError(f"{name}.{_JSON_NUMPY_DATA_FIELD} is not valid base64.") from exc


def _check_json_numpy_byte_length(
    raw_bytes: bytes,
    *,
    expected_bytes: int,
    name: str,
) -> None:
    if len(raw_bytes) != expected_bytes:
        raise ProviderError(
            f"{name} byte length must match shape and dtype; expected {expected_bytes}, "
            f"got {len(raw_bytes)}."
        )


def _unpack_json_numpy_values(
    raw_bytes: bytes,
    *,
    item_count: int,
    endian_prefix: str,
    item_format: str,
    name: str,
) -> tuple[float, ...]:
    try:
        return struct.unpack(f"{endian_prefix}{item_count}{item_format}", raw_bytes)
    except struct.error as exc:
        raise ProviderError(f"{name} could not be decoded as numeric action data.") from exc


def _finite_json_numpy_values(values: Sequence[float], *, name: str) -> list[float]:
    return [
        require_finite_number(item, name=f"{name}[{index}]") for index, item in enumerate(values)
    ]


def _json_numpy_float_format(dtype: str, *, name: str) -> tuple[str, str, int]:
    normalized = dtype.strip().lower()
    endian_prefix = "<"
    if normalized[0] in ("<", ">", "=", "|"):
        endian_prefix = "=" if normalized[0] == "|" else normalized[0]
        normalized = normalized[1:]
    if normalized in ("f8", "float64"):
        return endian_prefix, "d", 8
    if normalized in ("f4", "float32"):
        return endian_prefix, "f", 4
    raise ProviderError(f"{name}.dtype must be float32 or float64 encoded numpy data.")


def _normalize_all_actions(
    value: object,
    *,
    provider_name: str,
    expected_action_dim: int | None,
) -> list[list[list[float]]]:
    if value is None:
        return []
    if not isinstance(value, list) or not value:
        raise ProviderError(
            f"Provider '{provider_name}' policy response field 'all_actions' must be a "
            "non-empty list when present."
        )
    return [
        _normalize_action_matrix(
            candidate,
            name=(
                f"Provider '{provider_name}' policy response field 'all_actions'[{candidate_index}]"
            ),
            expected_action_dim=expected_action_dim,
        )
        for candidate_index, candidate in enumerate(value)
    ]


def _selected_action_index(
    actions: list[list[float]],
    all_actions: list[list[list[float]]],
) -> int:
    if not all_actions:
        return 0
    for index, candidate in enumerate(all_actions):
        if _action_matrices_close(candidate, actions):
            return index
    raise WorldStateError(
        "Cosmos-Policy response field 'actions' must match one entry in 'all_actions'."
    )


def _action_matrices_close(
    left: list[list[float]],
    right: list[list[float]],
    *,
    rel_tol: float = 1e-6,
    abs_tol: float = 1e-6,
) -> bool:
    if len(left) != len(right):
        return False
    for left_row, right_row in zip(left, right, strict=True):
        if len(left_row) != len(right_row):
            return False
        for left_value, right_value in zip(left_row, right_row, strict=True):
            if not math.isclose(left_value, right_value, rel_tol=rel_tol, abs_tol=abs_tol):
                return False
    return True


def _bounded_shape(value: object, *, depth: int = 0, max_depth: int = 8) -> list[int] | None:
    if depth >= max_depth:
        return []
    if _is_json_numpy_payload(value):
        return _json_numpy_shape(value, name="encoded numpy payload")
    if not isinstance(value, list):
        return []
    if not value:
        return [0]
    child_shape = _bounded_shape(value[0], depth=depth + 1, max_depth=max_depth)
    return [len(value), *(child_shape or [])]


def _future_prediction_summary(payload: JSONDict) -> JSONDict:
    summary: JSONDict = {}
    for key in (
        "future_image_predictions",
        "future_image_predictions_by_depth",
        "all_future_image_predictions",
        "all_future_image_predictions_by_depth",
    ):
        if key in payload:
            summary[key] = _summarize_prediction_payload(payload[key])
    return summary


def _summarize_prediction_payload(
    value: object,
    *,
    depth: int = 0,
    max_depth: int = _PREDICTION_SUMMARY_MAX_DEPTH,
    max_keys: int = _PREDICTION_SUMMARY_MAX_KEYS,
) -> JSONDict:
    if depth >= max_depth:
        return {"truncated": True}
    if _is_json_numpy_payload(value):
        return {"shape": _bounded_shape(value)}
    if isinstance(value, dict):
        string_keys = sorted(key for key in value if isinstance(key, str))
        summary = {
            key: _summarize_prediction_payload(
                value[key],
                depth=depth + 1,
                max_depth=max_depth,
                max_keys=max_keys,
            )
            for key in string_keys[:max_keys]
        }
        if len(string_keys) > max_keys:
            summary["truncated_keys"] = len(string_keys) - max_keys
        return summary
    return {"shape": _bounded_shape(value)}

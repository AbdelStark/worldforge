"""Shared tensor shape and numeric-sequence validation helpers.

These helpers are used by JEPA-WMS-style provider adapters to validate
tensor-like inputs without importing heavy optional runtimes (torch, numpy).
They accept either objects exposing a ``shape``/``ndim``/``dim`` attribute or
nested Python numeric sequences, and raise :class:`ProviderError` with
caller-supplied names for boundary-friendly error messages.

The public re-exports are intentionally underscore-prefixed: callers import
them as package-private helpers from a sibling module.
"""

from __future__ import annotations

from worldforge.models import WorldForgeError, require_finite_number

from .base import ProviderError


def _is_sequence(value: object) -> bool:
    return isinstance(value, list | tuple)


def _shape_from_sequence(value: object, *, name: str) -> tuple[int, ...]:
    if _is_sequence(value):
        if not value:
            raise ProviderError(f"{name} must not contain empty sequences.")
        child_shapes = [
            _shape_from_sequence(child, name=f"{name}[{index}]")
            for index, child in enumerate(value)
        ]
        first_shape = child_shapes[0]
        if any(shape != first_shape for shape in child_shapes):
            raise ProviderError(f"{name} must be a rectangular nested numeric sequence.")
        return (len(value), *first_shape)

    try:
        require_finite_number(value, name=name)  # type: ignore[arg-type]
    except WorldForgeError as exc:
        raise ProviderError(f"{name} must contain only finite numbers.") from exc
    return ()


def _shape_from_attr(value: object, *, name: str) -> tuple[int, ...] | None:
    shape = getattr(value, "shape", None)
    if shape is not None:
        return _shape_tuple_from_attr(shape, name=name)
    rank = _rank_from_attr(value)
    if rank is None:
        return None
    return _unknown_shape_from_rank(rank, name=name)


def _rank_from_attr(value: object) -> object | None:
    rank = getattr(value, "ndim", None)
    if rank is not None:
        return rank
    dim = getattr(value, "dim", None)
    return dim() if callable(dim) else None


def _unknown_shape_from_rank(rank: object, *, name: str) -> tuple[int, ...]:
    try:
        rank_int = int(rank)
    except (TypeError, ValueError):
        raise ProviderError(f"{name} tensor rank must be an integer.") from None
    if rank_int <= 0:
        raise ProviderError(f"{name} tensor rank must be positive.")
    return tuple(-1 for _ in range(rank_int))


def _shape_tuple_from_attr(shape: object, *, name: str) -> tuple[int, ...]:
    try:
        parsed = tuple(int(dimension) for dimension in shape)  # type: ignore[union-attr]
    except (TypeError, ValueError):
        raise ProviderError(f"{name} tensor shape must contain integer dimensions.") from None
    if _has_invalid_attr_shape(parsed):
        raise ProviderError(f"{name} tensor shape must contain non-zero dimensions.")
    return parsed


def _has_invalid_attr_shape(shape: tuple[int, ...]) -> bool:
    return not shape or any(dimension == 0 for dimension in shape)


def _shape(value: object, *, name: str) -> tuple[int, ...]:
    attr_shape = _shape_from_attr(value, name=name)
    if attr_shape is not None:
        return attr_shape

    tolist = getattr(value, "tolist", None)
    if callable(tolist):
        return _shape(tolist(), name=name)

    if not _is_sequence(value):
        raise ProviderError(f"{name} must be a tensor-like object or nested numeric sequence.")
    return _shape_from_sequence(value, name=name)


def _require_rank(value: object, *, name: str, min_rank: int | None = None) -> tuple[int, ...]:
    shape = _shape(value, name=name)
    if min_rank is not None and len(shape) < min_rank:
        raise ProviderError(f"{name} must have at least {min_rank} dimensions.")
    return shape


def _flatten_numeric(value: object, *, name: str) -> list[float]:
    if _is_sequence(value):
        flattened: list[float] = []
        for index, child in enumerate(value):
            flattened.extend(_flatten_numeric(child, name=f"{name}[{index}]"))
        return flattened

    tolist = getattr(value, "tolist", None)
    if callable(tolist):
        return _flatten_numeric(tolist(), name=name)

    try:
        return [require_finite_number(value, name=name)]  # type: ignore[arg-type]
    except WorldForgeError as exc:
        raise ProviderError(f"{name} must contain only finite numbers.") from exc


def _tensor_shape(value: object) -> tuple[int, ...] | None:
    shape = getattr(value, "shape", None)
    if shape is None:
        return None
    try:
        return tuple(int(dimension) for dimension in shape)
    except (TypeError, ValueError):
        return None

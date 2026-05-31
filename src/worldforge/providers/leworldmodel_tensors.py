"""Tensor boundary validation for the LeWorldModel provider."""

from __future__ import annotations

from typing import Any

from worldforge.models import JSONDict, WorldForgeError, require_finite_number

from ._tensor_validation import _is_sequence, _shape
from .base import ProviderError

REQUIRED_INFO_FIELDS = ("pixels", "goal", "action")


def is_tensor(torch: Any, value: object) -> bool:
    is_tensor_fn = getattr(torch, "is_tensor", None)
    if callable(is_tensor_fn):
        return bool(is_tensor_fn(value))
    tensor_type = getattr(torch, "Tensor", None)
    if tensor_type is not None:
        return isinstance(value, tensor_type)
    return hasattr(value, "to") and hasattr(value, "tolist")


def nested_numeric_depth(value: object, *, name: str) -> int:
    if _is_sequence(value):
        if not value:
            raise ProviderError(f"{name} must not contain empty sequences.")
        depths = {
            nested_numeric_depth(item, name=f"{name}[{index}]") for index, item in enumerate(value)
        }
        if len(depths) != 1:
            raise ProviderError(f"{name} must be a rectangular nested numeric sequence.")
        return next(iter(depths)) + 1

    try:
        require_finite_number(value, name=name)  # type: ignore[arg-type]
    except WorldForgeError as exc:
        raise ProviderError(f"{name} must contain only finite numbers.") from exc
    return 0


def tensor_rank(value: object) -> int | None:
    rank = getattr(value, "ndim", None)
    if rank is None:
        dim = getattr(value, "dim", None)
        if callable(dim):
            rank = dim()
    if rank is None:
        return None
    try:
        return int(rank)
    except (TypeError, ValueError):
        return None


def as_tensor(torch: Any, value: object, *, name: str) -> Any:
    if is_tensor(torch, value):
        return value
    if not _is_sequence(value):
        raise ProviderError(f"{name} must be a tensor or nested numeric sequence.")
    nested_numeric_depth(value, name=name)
    as_tensor_fn = getattr(torch, "as_tensor", None)
    if not callable(as_tensor_fn):
        raise ProviderError("Configured tensor module does not expose as_tensor().")
    return as_tensor_fn(value)


def tensorize_info(torch: Any, info: JSONDict) -> dict[str, Any]:
    if not isinstance(info, dict):
        raise ProviderError("LeWorldModel info must be a JSON object.")
    missing = [field for field in REQUIRED_INFO_FIELDS if field not in info]
    if missing:
        raise ProviderError(
            f"LeWorldModel info missing required input fields: {', '.join(missing)}."
        )

    tensorized: dict[str, Any] = {}
    for key, value in info.items():
        if not isinstance(key, str) or not key.strip():
            raise ProviderError("LeWorldModel info field names must be non-empty strings.")
        tensorized[key] = as_tensor(torch, value, name=f"LeWorldModel info.{key}")

    for key in REQUIRED_INFO_FIELDS:
        rank = tensor_rank(tensorized[key])
        if rank is not None and rank < 3:
            raise ProviderError(
                f"LeWorldModel info.{key} must have at least 3 dimensions for JEPA scoring."
            )
    return tensorized


def tensorize_action_candidates(torch: Any, action_candidates: object) -> Any:
    tensor = as_tensor(
        torch,
        action_candidates,
        name="LeWorldModel action_candidates",
    )
    rank = tensor_rank(tensor)
    if rank is not None and rank != 4:
        raise ProviderError(
            "LeWorldModel action_candidates must be four-dimensional: "
            "(batch, samples, horizon, action_dim)."
        )
    return tensor


def candidate_sample_count(action_candidates: object) -> int:
    shape = _shape(action_candidates, name="LeWorldModel action_candidates")
    if len(shape) != 4:
        raise ProviderError(
            "LeWorldModel action_candidates must be four-dimensional: "
            "(batch, samples, horizon, action_dim)."
        )
    batch, samples, _horizon, _action_dim = shape
    if batch != 1:
        raise ProviderError("LeWorldModel action_candidates batch dimension must be 1.")
    if samples <= 0:
        raise ProviderError("LeWorldModel action_candidates sample dimension must be positive.")
    return samples


def score_output_shape(raw_scores: object) -> tuple[int, ...]:
    try:
        shape = _shape(raw_scores, name="LeWorldModel scores")
        if any(dimension < 0 for dimension in shape):
            tolist = getattr(raw_scores, "tolist", None)
            if callable(tolist):
                return _shape(tolist(), name="LeWorldModel scores")
        return shape
    except ProviderError:
        try:
            require_finite_number(raw_scores, name="LeWorldModel scores")  # type: ignore[arg-type]
        except WorldForgeError as exc:
            raise ProviderError(
                "LeWorldModel scores must contain only finite score values."
            ) from exc
        return ()


def json_shape(value: object, *, name: str) -> list[int]:
    shape = _shape(value, name=name)
    if any(dimension < 0 for dimension in shape):
        tolist = getattr(value, "tolist", None)
        if callable(tolist):
            shape = _shape(tolist(), name=name)
    return list(shape)


def validate_score_output_shape(shape: tuple[int, ...], *, candidate_count: int) -> None:
    if shape == ():
        if candidate_count == 1:
            return
        raise ProviderError(
            "LeWorldModel score output must contain one finite score per candidate action "
            f"sample; got scalar output for {candidate_count} candidates."
        )
    non_singleton_dimensions = [dimension for dimension in shape if dimension != 1]
    if non_singleton_dimensions not in ([candidate_count], []):
        raise ProviderError(
            "LeWorldModel score output shape must expose only the candidate sample "
            f"dimension plus optional singleton dimensions; got {shape} for "
            f"{candidate_count} candidates."
        )


def tensor_to_scores(raw_scores: object) -> list[float]:
    value = raw_scores
    for method_name in ("detach", "cpu"):
        method = getattr(value, method_name, None)
        if callable(method):
            value = method()
    reshape = getattr(value, "reshape", None)
    if callable(reshape):
        value = reshape(-1)
    tolist = getattr(value, "tolist", None)
    if callable(tolist):
        value = tolist()

    scores: list[float] = []

    def visit(item: object, *, name: str) -> None:
        if _is_sequence(item):
            for index, child in enumerate(item):
                visit(child, name=f"{name}[{index}]")
            return
        try:
            scores.append(require_finite_number(item, name=name))  # type: ignore[arg-type]
        except WorldForgeError as exc:
            raise ProviderError(f"{name} must contain only finite score values.") from exc

    visit(value, name="LeWorldModel scores")
    if not scores:
        raise ProviderError("LeWorldModel returned no action scores.")
    return scores

from __future__ import annotations

import pytest

from worldforge.providers._tensor_validation import _shape_from_attr
from worldforge.providers.base import ProviderError


class ShapeTensor:
    def __init__(self, shape: object) -> None:
        self.shape = shape


class RankTensor:
    def __init__(self, ndim: object) -> None:
        self.ndim = ndim


class DimTensor:
    def __init__(self, rank: object) -> None:
        self.rank = rank

    def dim(self) -> object:
        return self.rank


def test_shape_from_attr_prefers_explicit_shape_and_allows_unknown_dimensions() -> None:
    assert _shape_from_attr(ShapeTensor((2, -1, 3)), name="actions") == (2, -1, 3)


def test_shape_from_attr_uses_rank_attributes_when_shape_is_missing() -> None:
    assert _shape_from_attr(RankTensor(3), name="actions") == (-1, -1, -1)
    assert _shape_from_attr(DimTensor("2"), name="actions") == (-1, -1)


def test_shape_from_attr_returns_none_without_shape_or_rank() -> None:
    assert _shape_from_attr(object(), name="actions") is None


def test_shape_from_attr_rejects_invalid_shape_and_rank() -> None:
    with pytest.raises(ProviderError, match="non-zero dimensions"):
        _shape_from_attr(ShapeTensor((2, 0)), name="actions")

    with pytest.raises(ProviderError, match="shape must contain integer dimensions"):
        _shape_from_attr(ShapeTensor(("bad",)), name="actions")

    with pytest.raises(ProviderError, match="rank must be positive"):
        _shape_from_attr(RankTensor(0), name="actions")

    with pytest.raises(ProviderError, match="rank must be an integer"):
        _shape_from_attr(DimTensor("bad"), name="actions")

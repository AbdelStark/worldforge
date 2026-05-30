from __future__ import annotations

import math

import pytest

from worldforge.providers._policy import json_compatible, json_object
from worldforge.providers.base import ProviderError


class FakeArray:
    def __init__(self, value: object) -> None:
        self.value = value

    def tolist(self) -> object:
        return self.value


def test_json_compatible_materializes_arrays_and_normalizes_containers() -> None:
    payload = {
        " actions ": FakeArray(((1, 2.5), (3, None))),
        "metadata": {"valid": True},
    }

    assert json_compatible(payload, name="policy output") == {
        "actions": [[1, 2.5], [3, None]],
        "metadata": {"valid": True},
    }


def test_json_compatible_rejects_non_finite_numbers_and_bad_keys() -> None:
    with pytest.raises(ProviderError, match="finite numbers"):
        json_compatible({"actions": [math.inf]}, name="policy output")

    with pytest.raises(ProviderError, match="keys must be non-empty strings"):
        json_compatible({"": 1}, name="policy output")


def test_json_object_requires_object_after_normalization() -> None:
    assert json_object(FakeArray({"ok": [1]}), name="policy metadata") == {"ok": [1]}

    with pytest.raises(ProviderError, match="must be a JSON object"):
        json_object([1, 2, 3], name="policy metadata")

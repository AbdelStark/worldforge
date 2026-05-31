from __future__ import annotations

import math

import pytest

from worldforge.artifact_io import write_json_artifact
from worldforge.models import WorldForgeError


def test_write_json_artifact_creates_parent_and_writes_stable_json(tmp_path) -> None:
    target = tmp_path / "nested" / "artifact.json"

    written = write_json_artifact(target, {"b": 1, "a": [2]})

    assert written == target
    assert target.read_text(encoding="utf-8") == '{\n  "a": [\n    2\n  ],\n  "b": 1\n}\n'


def test_write_json_artifact_rejects_non_finite_payload_before_touching_disk(tmp_path) -> None:
    target = tmp_path / "nested" / "artifact.json"

    with pytest.raises(WorldForgeError, match="finite numbers"):
        write_json_artifact(target, {"score": math.nan})

    assert not target.exists()
    assert not target.parent.exists()

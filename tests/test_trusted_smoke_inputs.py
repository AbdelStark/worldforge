from __future__ import annotations

import json
from pathlib import Path

import pytest

from worldforge.smoke.trusted_inputs import (
    load_callable,
    load_json_file,
    load_json_object,
    module_from_path,
)


def test_trusted_smoke_inputs_load_json_and_require_object(tmp_path: Path) -> None:
    object_path = tmp_path / "input.json"
    object_path.write_text(json.dumps({"observation": {"x": 1}}), encoding="utf-8")
    list_path = tmp_path / "list.json"
    list_path.write_text("[1, 2, 3]", encoding="utf-8")

    assert load_json_file(object_path, name="input") == {"observation": {"x": 1}}
    assert load_json_object(object_path, name="input") == {"observation": {"x": 1}}
    with pytest.raises(SystemExit, match="must decode to a JSON object"):
        load_json_object(list_path, name="input")


def test_trusted_smoke_inputs_gate_local_module_loading(tmp_path: Path) -> None:
    module_path = tmp_path / "translator.py"
    module_path.write_text("def translate(raw_actions, info, provider_info):\n    return []\n")

    with pytest.raises(SystemExit, match="allow-translator-code"):
        module_from_path(
            module_path,
            name="translator",
            allow_code=False,
            flag="--allow-translator-code",
            trusted_label="translator code",
        )

    module = module_from_path(
        module_path,
        name="translator",
        allow_code=True,
        flag="--allow-translator-code",
    )
    assert module.translate({}, {}, {}) == []


def test_trusted_smoke_inputs_load_callable_from_file_and_validate_target(
    tmp_path: Path,
) -> None:
    module_path = tmp_path / "observation.py"
    module_path.write_text("value = 1\n\ndef build():\n    return {'observation': {}}\n")

    loaded = load_callable(f"{module_path}:build", name="observation factory")
    assert loaded() == {"observation": {}}

    with pytest.raises(SystemExit, match="not callable"):
        load_callable(f"{module_path}:value", name="observation factory")
    with pytest.raises(SystemExit, match="module_or_file:function"):
        load_callable("missing-colon", name="observation factory")
    with pytest.raises(SystemExit, match="does not exist"):
        load_callable(f"{tmp_path / 'missing.py'}:build", name="observation factory")


def test_trusted_smoke_inputs_require_code_for_importable_callable() -> None:
    with pytest.raises(SystemExit, match="allow-observation-code"):
        load_callable(
            "json:loads",
            name="observation factory",
            allow_code=False,
            flag="--allow-observation-code",
            require_code=True,
        )

    assert (
        load_callable(
            "json:loads",
            name="observation factory",
            allow_code=True,
            flag="--allow-observation-code",
            require_code=True,
        )("{}")
        == {}
    )

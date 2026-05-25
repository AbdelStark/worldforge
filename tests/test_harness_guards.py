from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _load_script(name: str):
    path = ROOT / "scripts" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_harness_has_no_network_egress_calls() -> None:
    assert _load_script("check_no_egress_in_harness").find_violations() == []


def test_harness_widget_css_has_no_hex_literals() -> None:
    assert _load_script("check_no_hex_in_widget_css").find_violations() == []

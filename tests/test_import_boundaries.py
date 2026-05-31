from __future__ import annotations

import importlib
import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "check_optional_import_boundaries.py"
SPEC = importlib.util.spec_from_file_location("check_optional_import_boundaries", SCRIPT)
assert SPEC is not None
check_optional_import_boundaries = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules["check_optional_import_boundaries"] = check_optional_import_boundaries
SPEC.loader.exec_module(check_optional_import_boundaries)


def test_optional_import_boundary_audit_passes_current_tree() -> None:
    payload = check_optional_import_boundaries.check_optional_import_boundaries()

    assert payload["passed"] is True
    assert payload["static"]["passed"] is True
    assert payload["static"]["violations"] == []
    assert payload["import_time"]["passed"] is True
    assert payload["import_time"]["loaded_optional_modules"] == []
    assert "worldforge.cli" in payload["import_time"]["modules"]
    assert "worldforge.harness.flows" in payload["import_time"]["modules"]
    assert "worldforge.harness.tui" not in payload["import_time"]["modules"]
    assert "textual" in payload["import_time"]["optional_roots"]
    assert "torch" in payload["import_time"]["optional_roots"]
    assert "lerobot" in payload["import_time"]["optional_roots"]
    assert "stable_worldmodel" in payload["import_time"]["optional_roots"]
    assert "gr00t" in payload["import_time"]["optional_roots"]


def test_static_audit_rejects_textual_import_outside_tui(tmp_path: Path) -> None:
    bad_module = tmp_path / "src" / "worldforge" / "harness" / "flows.py"
    bad_module.parent.mkdir(parents=True)
    bad_module.write_text("from textual.app import App\n", encoding="utf-8")

    payload = check_optional_import_boundaries.check_static_import_boundaries(root=tmp_path)

    assert payload["passed"] is False
    assert payload["violations"] == [
        {
            "path": "src/worldforge/harness/flows.py",
            "line": 1,
            "boundary": "Textual TUI",
            "imported": "textual.app",
            "kind": "direct import",
            "message": "Move Textual imports into src/worldforge/harness/tui.py.",
        }
    ]


def test_harness_tui_styles_import_without_textual() -> None:
    module_names = [
        "worldforge.harness.tui_robotics_styles",
        "worldforge.harness.tui_styles",
    ]
    modules = [importlib.import_module(name) for name in module_names]

    saved_textual = sys.modules.pop("textual", None)
    sys.modules["textual"] = None  # type: ignore[assignment]
    try:
        reloaded = [importlib.reload(module) for module in modules]
        facade = reloaded[module_names.index("worldforge.harness.tui_styles")]
        assert "#robotics-body" in facade.ROBOTICS_SHOWCASE_APP_CSS
        assert "RoboticsTabletopHelpScreen" in facade.ROBOTICS_TABLETOP_HELP_SCREEN_CSS
        for module in reloaded:
            assert "textual" not in module.__dict__
    finally:
        if saved_textual is not None:
            sys.modules["textual"] = saved_textual
        else:
            sys.modules.pop("textual", None)
        for module in modules:
            importlib.reload(module)


def test_harness_report_compare_rows_import_without_textual() -> None:
    import worldforge.harness.report_compare_rows as module

    saved_textual = sys.modules.pop("textual", None)
    sys.modules["textual"] = None  # type: ignore[assignment]
    try:
        reloaded = importlib.reload(module)
        assert callable(reloaded.comparison_rows)
        assert "textual" not in reloaded.__dict__
    finally:
        if saved_textual is not None:
            sys.modules["textual"] = saved_textual
        else:
            sys.modules.pop("textual", None)
        importlib.reload(module)


def test_static_audit_allows_rerun_lazy_import_in_rerun_module(tmp_path: Path) -> None:
    rerun_module = tmp_path / "src" / "worldforge" / "rerun.py"
    rerun_module.parent.mkdir(parents=True)
    rerun_module.write_text(
        "from importlib import import_module\nsdk = import_module('rerun')\n",
        encoding="utf-8",
    )

    payload = check_optional_import_boundaries.check_static_import_boundaries(root=tmp_path)

    assert payload["passed"] is True
    assert payload["violations"] == []


def test_optional_import_boundary_cli_outputs_json(capsys) -> None:
    assert check_optional_import_boundaries.main(["--format", "json"]) == 0

    payload = json.loads(capsys.readouterr().out)
    assert payload["schema_version"] == 1
    assert payload["passed"] is True
    assert payload["import_time"]["loaded_optional_modules"] == []

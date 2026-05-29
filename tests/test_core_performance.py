from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "check_core_performance.py"
SPEC = importlib.util.spec_from_file_location("check_core_performance", SCRIPT)
assert SPEC is not None
check_core_performance = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules["check_core_performance"] = check_core_performance
SPEC.loader.exec_module(check_core_performance)


def test_core_performance_budgets_emit_checkout_safe_report(tmp_path: Path) -> None:
    payload = check_core_performance.run_core_performance_budgets(
        budgets=dict.fromkeys(check_core_performance.DEFAULT_BUDGETS_MS, 10_000.0),
        workspace_dir=tmp_path,
    )

    assert payload["schema_version"] == 1
    assert payload["passed"] is True
    assert payload["preserved_workspace"] == str(tmp_path.resolve())
    assert (tmp_path / "core-performance.json").exists()
    assert "not a public leaderboard" in payload["claim_boundary"]
    assert {result["name"] for result in payload["results"]} == set(
        check_core_performance.DEFAULT_BUDGETS_MS
    )
    assert all(result["artifact_path"] for result in payload["results"])


def test_core_performance_budgets_fail_on_explicit_threshold(tmp_path: Path) -> None:
    budgets = dict.fromkeys(check_core_performance.DEFAULT_BUDGETS_MS, 0.0)

    payload = check_core_performance.run_core_performance_budgets(
        budgets=budgets,
        workspace_dir=tmp_path,
    )

    assert payload["passed"] is False
    assert any(not result["passed"] for result in payload["results"])


def test_core_performance_preserved_workspace_can_be_reused(tmp_path: Path) -> None:
    budgets = dict.fromkeys(check_core_performance.DEFAULT_BUDGETS_MS, 10_000.0)

    first = check_core_performance.run_core_performance_budgets(
        budgets=budgets,
        workspace_dir=tmp_path,
    )
    second = check_core_performance.run_core_performance_budgets(
        budgets=budgets,
        workspace_dir=tmp_path,
    )

    assert first["passed"] is True
    assert second["passed"] is True
    assert len(list((tmp_path / "runs").iterdir())) == 2


def test_core_performance_script_writes_json_and_exits_nonzero_on_violation(
    tmp_path: Path,
) -> None:
    budget_file = tmp_path / "budgets.json"
    output = tmp_path / "core-performance.json"
    budget_file.write_text(
        json.dumps(dict.fromkeys(check_core_performance.DEFAULT_BUDGETS_MS, 0.0)),
        encoding="utf-8",
    )

    assert (
        check_core_performance.main(
            [
                "--budget-file",
                str(budget_file),
                "--workspace-dir",
                str(tmp_path / "workspace"),
                "--output",
                str(output),
            ]
        )
        == 1
    )

    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["passed"] is False

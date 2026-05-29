from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "check_wrapper_portability.py"
SPEC = importlib.util.spec_from_file_location("check_wrapper_portability", SCRIPT)
assert SPEC is not None
check_wrapper_portability = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules["check_wrapper_portability"] = check_wrapper_portability
SPEC.loader.exec_module(check_wrapper_portability)


def test_wrapper_portability_checker_passes_current_contracts() -> None:
    payload = check_wrapper_portability.check_wrapper_portability()

    assert payload["schema_version"] == 1
    assert payload["passed"] is True
    assert "does not install optional runtimes" in payload["claim_boundary"]
    assert {result["path"] for result in payload["results"]} == {
        contract.path for contract in check_wrapper_portability.WRAPPER_CONTRACTS
    }


def test_wrapper_portability_checker_names_exact_script_and_fix() -> None:
    contract = check_wrapper_portability.WrapperContract(
        path="scripts/robotics-showcase",
        invocation="scripts/robotics-showcase",
        executable=True,
        shebang_prefix="#!/usr/bin/env bash",
        required_text=("definitely-missing-wrapper-token",),
        docs=("README.md",),
        triage_step="restore the wrapper token",
    )

    payload = check_wrapper_portability.check_wrapper_portability(contracts=(contract,))

    assert payload["passed"] is False
    failure = payload["results"][0]["failures"][0]
    assert "scripts/robotics-showcase" in failure
    assert "definitely-missing-wrapper-token" in failure

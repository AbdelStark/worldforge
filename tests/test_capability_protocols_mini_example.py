from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_capability_protocols_mini_example_outputs_plan_json() -> None:
    result = subprocess.run(
        [sys.executable, str(ROOT / "examples/capability_protocols_mini.py")],
        check=True,
        capture_output=True,
        text=True,
    )

    plan = json.loads(result.stdout)

    assert plan["provider"] == "local-cost"
    assert plan["goal"] == "keep the blue cube near the origin"
    assert plan["action_count"] == 1
    assert plan["actions"][0]["type"] == "move_to"
    assert plan["actions"][0]["parameters"]["object_id"] == "cube-1"
    assert plan["metadata"]["planning_mode"] == "policy+score"
    assert plan["metadata"]["policy_provider"] == "local-policy"
    assert plan["metadata"]["score_provider"] == "local-cost"
    assert plan["metadata"]["candidate_count"] == 2


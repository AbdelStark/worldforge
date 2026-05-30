import json
from pathlib import Path

from worldforge.demos.embodied_policy_replay_comparison import (
    policy_missing_translator_checks,
    policy_replay_raw_fields,
    render_embodied_policy_comparison_markdown,
    run_embodied_policy_replay_comparison_workflow,
)


def test_policy_missing_translator_checks_block_all_policy_providers() -> None:
    checks = policy_missing_translator_checks()

    assert {check["provider"] for check in checks} == {"lerobot", "gr00t", "cosmos-policy"}
    assert all(check["status"] == "blocked" for check in checks)
    assert all(check["requires"] == "host action_translator" for check in checks)
    advertised = {check["provider"]: check["advertised_capabilities"] for check in checks}
    assert advertised["lerobot"] == ["policy"]
    assert advertised["gr00t"] == ["policy"]
    assert advertised["cosmos-policy"] == []


def test_embodied_policy_replay_workflow_preserves_provider_specific_shapes(
    tmp_path: Path,
) -> None:
    summary = run_embodied_policy_replay_comparison_workflow(tmp_path)
    report = summary["report"]
    providers = {provider["provider"]: provider for provider in report["providers"]}

    assert summary["status"] == "passed"
    assert summary["safe_to_attach"] is True
    assert set(providers) == {"lerobot", "gr00t", "cosmos-policy"}
    assert providers["lerobot"]["raw_action_shape"] == [3, 2, 3]
    assert "eef_9d" in providers["gr00t"]["raw_tensor_shapes"]
    assert providers["cosmos-policy"]["raw_action_shape"] == [50, 14]
    assert "cross-provider action conversion" in report["claim_boundary"]

    comparison_json = Path(str(summary["artifact_paths"]["comparison_json"]))
    comparison_markdown = Path(str(summary["artifact_paths"]["comparison_markdown"]))
    assert json.loads(comparison_json.read_text(encoding="utf-8")) == report
    assert "Missing Translator Checks" in comparison_markdown.read_text(encoding="utf-8")


def test_embodied_policy_markdown_renders_raw_tensor_shapes() -> None:
    comparison = {
        "claim_boundary": "claim",
        "providers": [
            {
                "provider": "gr00t",
                "action_horizon": 1,
                "translated_action_count": 1,
                "raw_action_keys": ["actions"],
                "raw_tensor_shapes": ["eef_9d"],
                "live_follow_up": "uv run python scripts/smoke_gr00t_policy.py --help",
            }
        ],
        "missing_translator_checks": [
            {"provider": "gr00t", "status": "blocked", "message": "translator required"}
        ],
        "non_normalization_boundary": "do not normalize",
    }

    assert policy_replay_raw_fields(comparison["providers"][0]) == "actions / eef_9d"
    markdown = render_embodied_policy_comparison_markdown(comparison)
    assert "actions / eef_9d" in markdown
    assert "translator required" in markdown

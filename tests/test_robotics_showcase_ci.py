from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_robotics_showcase_ci_workflow_runs_real_noninteractive_inference() -> None:
    workflow = (ROOT / ".github/workflows/robotics-showcase.yml").read_text(encoding="utf-8")

    for required in (
        "name: Robotics Showcase",
        "push:",
        "- main",
        "pull_request:",
        'PYTHON_VERSION: "3.13"',
        'LEROBOT_VERSION: "0.5.1"',
        'LEWORLDMODEL_REVISION: "22b330c28c27ead4bfd1888615af1340e3fe9052"',
        "actions/cache@v4",
        "scripts/robotics-showcase \\",
        "--json-only",
        "--no-tui",
        "--no-rerun",
        '--lewm-asset-cache-dir "$LEWORLDMODEL_ASSET_CACHE_DIR"',
        '--run-manifest "$WORLDFORGE_ROBOTICS_RUN_DIR/run_manifest.json"',
        "actions/upload-artifact@v4",
        "robotics-showcase-real-inference-${{ github.run_id }}",
    ):
        assert required in workflow

    for forbidden in (
        "workflow_dispatch:",
        "schedule:",
        "run-live-robotics",
        "upload_checkpoint_artifact",
        "github.event.pull_request.labels",
    ):
        assert forbidden not in workflow

    assert ".cache/huggingface" in workflow
    assert ".cache/stable-wm" in workflow
    assert ".cache/worldforge/leworldmodel" in workflow
    assert 'score_action_candidates_shape") == [1, 3, 4, 10]' in workflow
    assert '("lerobot", "policy", "success")' in workflow
    assert '("leworldmodel", "score", "success")' in workflow


def test_robotics_showcase_ci_cache_strategy_is_documented() -> None:
    docs = "\n".join(
        [
            (ROOT / "docs/src/quality.md").read_text(encoding="utf-8"),
            (ROOT / "docs/src/robotics-showcase.md").read_text(encoding="utf-8"),
            (ROOT / "docs/src/robotics-showcase-deep-dive.md").read_text(encoding="utf-8"),
            (ROOT / "docs/src/playbooks.md").read_text(encoding="utf-8"),
        ]
    )

    for required in (
        ".github/workflows/robotics-showcase.yml",
        "non-interactive",
        "actions/cache",
        "Hugging Face",
        "LeWorldModel object checkpoint",
        "run_manifest.json",
        "checkpoint artifacts are not uploaded",
    ):
        assert required in docs


def test_leworldmodel_asset_cache_env_is_documented() -> None:
    env_template = (ROOT / ".env.example").read_text(encoding="utf-8")
    operations = (ROOT / "docs/src/operations.md").read_text(encoding="utf-8")
    readme = (ROOT / "README.md").read_text(encoding="utf-8")

    assert "LEWORLDMODEL_ASSET_CACHE_DIR" in env_template
    assert "LEWORLDMODEL_REVISION" in env_template
    assert "LEWORLDMODEL_ASSET_CACHE_DIR" in operations
    assert "--lewm-revision <40-char-commit-sha>" in readme

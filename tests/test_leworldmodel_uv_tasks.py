from __future__ import annotations

import importlib
from pathlib import Path


def test_leworldmodel_uv_commands_are_packaged_console_scripts() -> None:
    root = Path(__file__).resolve().parents[1]
    pyproject_path = root / "pyproject.toml"
    pyproject = pyproject_path.read_text()

    assert 'worldforge-harness = "worldforge.harness.cli:main"' in pyproject
    assert 'worldforge-demo-leworldmodel = "worldforge.demos.leworldmodel_e2e:main"' in pyproject
    assert 'worldforge-smoke-cosmos = "worldforge.smoke.cosmos:main"' in pyproject
    assert ('worldforge-smoke-cosmos-policy = "worldforge.smoke.cosmos_policy:main"') in pyproject
    assert (
        'worldforge-build-leworldmodel-checkpoint = "worldforge.smoke.leworldmodel_checkpoint:main"'
    ) in pyproject
    assert 'worldforge-smoke-leworldmodel = "worldforge.smoke.leworldmodel:main"' in pyproject
    assert (
        'worldforge-smoke-lerobot-leworldmodel = "worldforge.smoke.lerobot_leworldmodel:main"'
    ) in pyproject
    assert ('worldforge-robotics-showcase = "worldforge.smoke.robotics_showcase:main"') in pyproject
    assert 'lewm-real = "worldforge.smoke.leworldmodel:main"' in pyproject
    assert 'lewm-lerobot-real = "worldforge.smoke.lerobot_leworldmodel:main"' in pyproject
    task = root / "scripts" / "lewm-real"
    assert task.exists()
    assert task.stat().st_mode & 0o111
    task_text = task.read_text()
    assert "uv run --python 3.13" in task_text
    assert "stable-worldmodel @ git+" in task_text
    assert "stable-worldmodel[train]" not in task_text
    assert '"opencv-python"' in task_text
    assert '"imageio"' in task_text
    assert 'lewm-real "$@"' in task_text
    robotics_task = root / "scripts" / "lewm-lerobot-real"
    assert robotics_task.exists()
    assert robotics_task.stat().st_mode & 0o111
    robotics_task_text = robotics_task.read_text()
    assert "uv run --python 3.13" in robotics_task_text
    assert "stable-worldmodel @ git+" in robotics_task_text
    assert "stable-worldmodel[train]" not in robotics_task_text
    assert '"datasets>=2.21"' in robotics_task_text
    assert '"opencv-python"' in robotics_task_text
    assert '"imageio"' in robotics_task_text
    assert '"lerobot[transformers-dep]==0.5.1"' in robotics_task_text
    assert 'lewm-lerobot-real "$@"' in robotics_task_text
    showcase_task = root / "scripts" / "robotics-showcase"
    assert showcase_task.exists()
    assert showcase_task.stat().st_mode & 0o111
    showcase_task_text = showcase_task.read_text()
    assert "stable-worldmodel @ git+" in showcase_task_text
    assert "stable-worldmodel[train]" not in showcase_task_text
    assert '"lerobot[transformers-dep]==0.5.1"' in showcase_task_text
    assert "stable-worldmodel[env]" not in showcase_task_text
    assert '"hydra-core"' in showcase_task_text
    assert '"omegaconf"' in showcase_task_text
    assert '"transformers"' in showcase_task_text
    assert '"textual>=8.2,<9"' in showcase_task_text
    assert '"pygame"' in showcase_task_text
    assert '"opencv-python"' in showcase_task_text
    assert '"imageio"' in showcase_task_text
    assert '"pymunk"' in showcase_task_text
    assert '"gymnasium"' in showcase_task_text
    assert '"shapely"' in showcase_task_text
    assert '"rerun-sdk>=0.31,<0.32"' not in showcase_task_text
    assert "is_help_request" in showcase_task_text
    assert "should_enable_rerun" in showcase_task_text
    assert "showcase_args=(--tui" in showcase_task_text
    assert 'runtime_args+=(--with "textual>=8.2,<9")' in showcase_task_text
    assert "--no-tui" in showcase_task_text
    assert "ale-py not found" in showcase_task_text
    assert "Device 'cuda' is not available" not in showcase_task_text
    assert "lerobot\\.configs\\.policies" not in showcase_task_text
    assert 'worldforge-robotics-showcase "${showcase_args[@]}"' in showcase_task_text


def test_leworldmodel_console_script_targets_are_importable() -> None:
    targets = [
        "worldforge.harness.cli:main",
        "worldforge.demos.leworldmodel_e2e:main",
        "worldforge.smoke.cosmos:main",
        "worldforge.smoke.cosmos_policy:main",
        "worldforge.smoke.leworldmodel_checkpoint:main",
        "worldforge.smoke.leworldmodel:main",
        "worldforge.smoke.leworldmodel:main",
        "worldforge.smoke.lerobot_leworldmodel:main",
        "worldforge.smoke.lerobot_leworldmodel:main",
        "worldforge.smoke.robotics_showcase:main",
    ]

    for target in targets:
        module_name, function_name = target.split(":", maxsplit=1)
        module = importlib.import_module(module_name)

        assert callable(getattr(module, function_name))

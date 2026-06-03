# 快速开始

## 安装

```bash
uv add worldforge-ai          # 或：pip install worldforge-ai
```

导入路径保持为 `worldforge`：

```python
import worldforge
```

可选的 Textual 可视化界面作为附加扩展安装：

```bash
uv add "worldforge-ai[harness]"
```

可选的 Rerun 事件与工件记录作为附加扩展安装：

```bash
uv add "worldforge-ai[rerun]"
```

本地开发环境：

```bash
uv sync --group dev
```

## 基于世界状态字典进行预测

不存在符号化的 `World` 运行时：场景是一个纯粹的、可 JSON 序列化的世界状态字典，由动作条件化的 `predict` 提供方推进。

```python
from worldforge import Action, WorldForge

forge = WorldForge()
world_state = {
    "step": 0,
    "scene": {
        "objects": {
            "red_mug": {
                "id": "red_mug",
                "name": "red_mug",
                "pose": {"position": {"x": 0.0, "y": 0.8, "z": 0.0}},
                "bbox": {
                    "min": {"x": -0.05, "y": 0.75, "z": -0.05},
                    "max": {"x": 0.05, "y": 0.85, "z": 0.05},
                },
            }
        }
    },
}

prediction = forge.predict(world_state, Action.move_to(0.3, 0.8, 0.0), steps=2, provider="mock")
print(prediction.physics_score)
next_state = prediction.state
```

## 使用 LatentMPCController 规划并评估

```python
from worldforge import LatentMPCController, PlannerConfig

controller = LatentMPCController(
    forge=forge,
    score_provider="mock",
    config=PlannerConfig(
        horizon=1,
        num_samples=16,
        num_iterations=2,
        num_elites=4,
        action_kind="latent_action",
        action_parameter_bounds={"x": (-1.0, 1.0), "y": (-1.0, 1.0), "z": (-1.0, 1.0)},
        seed=0,
    ),
)
plan = controller.plan_step(
    observation_info={"point": [0.0, 0.8, 0.0]},
    goal_info={"target": [0.3, 0.8, 0.0]},
)
print(len(plan.actions), plan.best_score)
```

`LatentMPCController` 提出动作候选，使用 `score` 提供方作为代价预言机对其排序，并返回代价最低的动作块。确定性评估套件直接通过 forge 运行：

```python
from worldforge.evaluation import EvaluationSuite

planning_report = EvaluationSuite.from_builtin("planning").run_report(["mock"], forge=forge)
print(planning_report.to_markdown())
```

## 命令行工具

```bash
uv run worldforge examples
uv run worldforge doctor --registered-only
uv run worldforge predict kitchen --provider mock --x 0.3 --y 0.8 --z 0.0 --steps 2
uv run worldforge provider list
uv run worldforge provider info mock
uv run worldforge eval --suite planning --provider mock --format json
uv run worldforge benchmark --provider mock --iterations 5 --format json
```

`worldforge predict` 会构造一个世界状态字典、运行 `predict` 提供方并打印结果；它不会持久化任何内容。

完整的命令映射请参阅 [CLI 参考](./cli.md)。可运行的演示及可选运行时冒烟测试命令请参阅[示例与 CLI 命令](./examples.md)。

可选的机器人案例展示报告：

```bash
scripts/robotics-showcase
scripts/robotics-showcase --no-tui
```

打包的签出安全演示：

```bash
uv run worldforge-demo-leworldmodel
uv run worldforge-demo-lerobot
uv run --extra rerun worldforge-demo-rerun
uv run python scripts/demo_showcases.py run first-run --workspace-dir .worldforge/demo-showcases
```

这些演示在适用的情况下使用注入的确定性运行时来调用真实的 WorldForge 提供方接口，无需安装可选模型运行时或下载检查点即可验证适配器、规划、执行、持久化和重载路径。Rerun 演示还会在本地写入一个包含事件、世界状态、规划和基准测试层的 `.rrd` 工件。演示案例运行器会保存首次运行、诊断、回放、空运行、宿主、画廊、故障实验室和示例手册等工件，供问题追踪和发布佐证使用。

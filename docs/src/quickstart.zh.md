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

## 创建世界状态

```python
from worldforge import Action, BBox, Position, SceneObject, StructuredGoal, WorldForge

forge = WorldForge()
world = forge.create_world("kitchen", provider="mock")

world.add_object(
    SceneObject(
        "red_mug",
        Position(0.0, 0.8, 0.0),
        BBox(Position(-0.05, 0.75, -0.05), Position(0.05, 0.85, 0.05)),
    )
)
world.add_object(
    SceneObject(
        "blue_mug",
        Position(0.3, 0.8, 0.0),
        BBox(Position(0.25, 0.75, -0.05), Position(0.35, 0.85, 0.05)),
    )
)

prediction = world.predict(Action.move_to(0.3, 0.8, 0.0), steps=2)
print(prediction.physics_score)
```

## 规划与评估

```python
plan = world.plan(
    goal_spec=StructuredGoal.object_at(
        object_name="red_mug",
        position=Position(0.3, 0.8, 0.0),
    )
)
print(plan.action_count, plan.success_probability)

swap_plan = world.plan(
    goal_spec=StructuredGoal.swap_objects(
        object_name="red_mug",
        reference_object_name="blue_mug",
    )
)
print(swap_plan.to_json())

planning_report = world.evaluate("planning")
print(planning_report.to_markdown())
```

`StructuredGoal` 还支持 `object_near(...)` 用于相对位置放置，以及 `spawn_object(...)` 用于创建对象。

## 命令行工具

```bash
uv run worldforge examples
uv run worldforge doctor --registered-only
uv run worldforge world create lab --provider mock
uv run worldforge world add-object <world-id> cube --x 0 --y 0.5 --z 0 --object-id cube-1
uv run worldforge world predict <world-id> --object-id cube-1 --x 0.4 --y 0.5 --z 0
uv run worldforge world list
uv run worldforge world history <world-id>
uv run worldforge provider list
uv run worldforge provider info mock
uv run worldforge eval --suite planning --provider mock --format json
uv run worldforge benchmark --provider mock --iterations 5 --format json
```

`world history` 记录了初始化、对象添加/更新/删除变更以及提供方的预测结果。对象位置更新时，存储的包围盒也会随姿态一并平移。

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

# Rerun 集成

WorldForge 与 [Rerun](https://github.com/rerun-io/rerun) 提供了一流的可选集成，用于本地物理 AI 运行检查。它将经过清理的提供方事件、世界快照、规划结果和基准测试报告记录到 Rerun 录制文件中，而无需将 Rerun 作为提供方能力或基础依赖项。

Rerun 在此作为可观测性和数据工件层使用：

- `ProviderEvent` 记录将转化为带时间索引的文本日志、JSON 载荷、重试/失败计数器、延迟标量和状态标量。
- 世界快照将转化为 JSON 状态文档以及 3D 对象标记。
- 规划结果将转化为 JSON 载荷、动作数量和成功概率标量，当动作包含 `move_to` 目标时还会生成 3D 动作目标标记。
- 基准测试报告将转化为完整的 JSON 工件，以及各提供方和各操作的指标时间序列。

它不替代提供方适配器、持久化层、训练数据存储或宿主方遥测。Rerun 通过宿主方已有的 `event_handler` 和工件 API 进行挂载。

## 安装

```bash
uv add "worldforge-ai[rerun]"
```

用于仓库开发：

```bash
uv sync --group dev --extra rerun
```

该扩展会安装 `rerun-sdk>=0.24,<0.32`。基础 WorldForge 仍仅依赖 `httpx`。
版本范围较宽是有意为之，以便 Rerun 桥接层能与固定了旧版兼容 Rerun SDK 的 LeRobot 运行时共存。

## 案例展示

```bash
uv run --extra rerun worldforge-demo-rerun
```

默认输出为本地 `.rrd` 文件：

```text
.worldforge/rerun/worldforge-rerun-showcase.rrd
```

使用 Rerun 查看器打开：

```bash
uv run --extra rerun rerun .worldforge/rerun/worldforge-rerun-showcase.rrd
```

实时查看器模式：

```bash
uv run --extra rerun worldforge-demo-rerun --spawn
uv run --extra rerun worldforge-demo-rerun --connect-url rerun+http://127.0.0.1:9876/proxy
uv run --extra rerun worldforge-demo-rerun --serve-grpc-port 9876
```

预期成功信号：命令输出包含录制路径或服务器 URI 以及字节数的摘要，录制内容包含提供方事件日志、世界快照、3D 对象框体、一个预测规划以及 mock 提供方基准测试结果。

失败时的首要排查步骤：

```bash
uv run --extra rerun python -c "import rerun; print(rerun.__version__)"
```

## 机器人案例展示

通过封装脚本启动时，打包的 PushT 机器人案例展示默认会录制视觉效果更丰富的 Rerun 工件：

```bash
scripts/robotics-showcase
uvx --from "rerun-sdk>=0.24,<0.32" rerun /tmp/worldforge-robotics-showcase/real-run.rrd
```

该工件包含与终端/TUI 报告相同的策略+打分运行内容：经过清理的提供方事件、初始和最终世界快照、3D 对象框体、候选目标点、选定轨迹线、打分条、延迟条以及序列化的规划载荷。使用 `--no-rerun` 可跳过工件生成，使用 `--rerun-output <path>` 可指定另一个 `.rrd` 路径，或使用更底层的 `--rerun-spawn`、`--rerun-connect-url` 和 `--rerun-serve-grpc-port` 标志进入实时查看器模式。

## Python API

```python
from worldforge import Action, RerunArtifactLogger, RerunEventSink, RerunRecordingConfig
from worldforge import RerunSession, WorldForge

session = RerunSession(
    RerunRecordingConfig(save_path=".worldforge/rerun/run.rrd")
)
events = RerunEventSink(session=session)
artifacts = RerunArtifactLogger(session=session)

forge = WorldForge(event_handler=events)
world = forge.create_world("lab", provider="mock")

prediction = world.predict(Action.move_to(0.3, 0.5, 0.0), steps=1)
artifacts.log_world(world, label="after prediction")

report = forge.doctor()
artifacts.log_json("diagnostics/doctor", report.to_dict())

session.close()
print(prediction.physics_score)
```

一行代码构建事件处理器：

```python
from worldforge import WorldForge, create_rerun_event_handler
from worldforge.rerun import RerunRecordingConfig

forge = WorldForge(
    event_handler=create_rerun_event_handler(
        config=RerunRecordingConfig(save_path=".worldforge/rerun/events.rrd")
    )
)
```

当需要在提供方事件之外还保留持久运行工件时，请使用 `RerunArtifactLogger`。

## 数据布局

默认实体路径：

| 实体路径 | 内容 |
| --- | --- |
| `worldforge/events/<provider>/<operation>/<phase>/log` | 文本事件条目 |
| `worldforge/events/<provider>/<operation>/<phase>/payload` | 经过清理的事件 JSON |
| `worldforge/events/<provider>/<operation>/<phase>/duration_ms` | 事件延迟标量 |
| `worldforge/worlds/<world-id>/state` | 序列化世界快照 |
| `worldforge/worlds/<world-id>/objects` | 3D 对象标记 |
| `worldforge/worlds/<world-id>/object_boxes` | 3D 对象包围框 |
| `worldforge/plans/<provider>/<planner>/<n>/payload` | 序列化规划 |
| `worldforge/plans/<provider>/<planner>/<n>/action_targets` | 3D 目标标记 |
| `worldforge/benchmarks/<provider>/<operation>/result` | 基准测试结果 JSON |
| `worldforge/benchmarks/<provider>/<operation>/<metric>` | 基准测试指标标量 |
| `worldforge/robotics_showcase/tabletop/*` | PushT 候选目标、选定路径及回放框体 |
| `worldforge/robotics_showcase/scores/*` | 候选打分条和选定代价标量 |
| `worldforge/robotics_showcase/runtime/*` | 提供方和端到端延迟条 |

默认时间线：

| 时间线 | 含义 |
| --- | --- |
| `worldforge_event` | 单调递增的提供方事件序列 |
| `worldforge_step` | 世界快照步骤 |
| `worldforge_plan` | 单调递增的规划序列 |
| `worldforge_benchmark_result` | 基准测试结果索引 |
| `worldforge_robotics_showcase` | 机器人案例展示摘要 |
| `worldforge_candidate` | 候选打分序列 |

## 边界

- Rerun 是可选的。请勿从提供方模块或基础包路径中导入或依赖 `rerun-sdk`。
- Rerun 不是 WorldForge 提供方。它不提供 `predict`、`score`、`policy`、`embed` 或 `plan` 能力。
- 提供方事件的目标、消息和元数据在传入 Rerun 接收器之前均经过清理。宿主代码仍应避免将密钥、凭据、签名 URL 或敏感数据集内容写入自定义元数据。
- `.rrd` 文件是运行工件，应将其视为日志：它们可能包含提示词、世界元数据、对象名称、基准测试输入和派生诊断信息。
- 本地 JSON 持久化仍由 WorldForge 持有，且为单写入者模式。Rerun 录制是检查工件，而非权威世界存储。

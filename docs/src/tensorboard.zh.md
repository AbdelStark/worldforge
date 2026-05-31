# TensorBoard 集成

WorldForge 附带一个可选的 TensorBoard 桥接模块，用于在机器人案例展示的本地推理过程中检查所使用的 LeWorldModel 检查点。它将经脱敏的来源文本、延迟和代价标量、候选代价直方图以及逐事件文本流写入本地 ``tfevents`` 日志目录。

该集成由宿主方持有，仅限本地使用：

- TensorBoard **不是**提供方能力，目录也不会对其进行宣传。
- WorldForge 基础安装**不**依赖 ``tensorboard`` 或 ``torch``。桥接模块懒惰导入 SDK，因此当可选扩展缺失时，该集成为空操作。
- ``tfevents`` 文件保存在宿主方选择的日志目录下。WorldForge 不会将其上传至任何托管服务。

## TensorBoard 中展示的内容

| 标签前缀 | 插件 | 展示内容 |
| --- | --- | --- |
| ``worldforge/leworldmodel/checkpoint/*`` | Text、Scalars | LeWorldModel 检查点路径、策略、仓库、修订版本、来源 JSON，以及 `created` 指示器。 |
| ``worldforge/leworldmodel/robotics_showcase/*`` | Text | 任务描述、检查点显示路径、状态目录、完整运行摘要的脱敏 JSON、输入及健康快照。 |
| ``worldforge/leworldmodel/scores/*`` | Scalars、Histogram | 各候选动作代价、最小/最大/均值、最优索引、最优分数，以及代价分布直方图。 |
| ``worldforge/leworldmodel/metrics/*`` | Scalars | 摘要中的分数统计与端到端延迟指标。 |
| ``worldforge/leworldmodel/events/<provider>/<operation>/*`` | Scalars、Text | 每个事件的尝试次数、持续时间、状态码、失败/重试标志，以及经脱敏的事件消息。 |
| ``worldforge/leworldmodel/weights/*`` | Histogram | 可选的逐参数权重分布，当宿主方将状态字典传入 ``log_state_dict_histograms`` 时生效。 |

桥接模块在写入文本面板前，会对类似秘密的 ``key=value`` 片段及签名 URL 查询参数进行脱敏处理，因此 ``tfevents`` 文件可安全地在采用故事或证明材料中共享。

## 安装

```bash
uv add "worldforge-ai[tensorboard]"
```

用于仓库开发：

```bash
uv sync --group dev --extra tensorboard
```

该扩展安装 ``tensorboard>=2.16,<3``。WorldForge 基础包仍仅依赖 ``httpx``。若宿主方已通过现有的 PyTorch 安装提供了 ``torch.utils.tensorboard``，桥接模块将优先使用；当 ``torch`` 和 ``tensorboard`` 均缺失时，``tensorboardX`` 作为回退被接受。

## 机器人案例展示标志

``scripts/robotics-showcase`` 在请求交互式案例展示时默认启用桥接模块：

| 标志 | 默认值 | 用途 |
| --- | --- | --- |
| ``--tensorboard`` | 隐含（除非指定了 ``--no-tensorboard`` / ``--health-only`` / ``--json-only``） | 启用写入器，默认日志目录位于 ``.worldforge/tensorboard/`` 下。 |
| ``--tensorboard-logdir <path>`` | ``.worldforge/tensorboard`` | 覆盖目标目录。相对路径相对于仓库根目录解析。 |
| ``--tensorboard-run-name <name>`` | 带时间戳的名称 | ``--tensorboard-logdir`` 下本次运行的子目录。指定稳定的名称可使重复运行在同一 TensorBoard 视图中具有可比性。 |
| ``--tensorboard-flush-secs <int>`` | ``30`` | ``SummaryWriter`` 的刷新间隔（秒）。 |
| ``--no-tensorboard`` | 关闭 | 禁用包装器的默认 TensorBoard 记录。 |

典型的检查工作流：

```bash
# Record a real LeRobot + LeWorldModel run (TensorBoard enabled by default).
scripts/robotics-showcase --json-only --no-tui --no-rerun

# Open the run alongside the published checkpoint.
uvx --from "tensorboard>=2.16,<3" tensorboard --logdir .worldforge/tensorboard
```

指定明确目标目录：

```bash
scripts/robotics-showcase \
  --tensorboard-logdir .worldforge/tensorboard/pusht \
  --tensorboard-run-name baseline \
  --no-tui --no-rerun --json-only
```

摘要 JSON 中会新增一个 ``"tensorboard"`` 块，列出 ``log_dir``、``run_name``、``flush_secs``，以及 ``events_written`` 标志，该标志与可视化报告 ``Artifacts`` 部分的包装器显示内容一致。

Textual 案例展示报告（`worldforge.harness.tui.RoboticsShowcaseApp`）通过 ``RoboticsTensorBoardPane`` 和 ``t`` 快捷键展示本次运行，该快捷键在一个分离的子进程中启动：
``uvx --from "tensorboard>=2.16,<3" --with "setuptools<81" tensorboard --logdir <path> --port 6006``。
``setuptools<81`` 约束确保 TensorBoard 导入路径中 ``pkg_resources`` 可用（TensorBoard 在启动时仍调用 ``import pkg_resources``，而 ``setuptools>=81`` 已移除该包）。该快捷键在页脚中与 Rerun 的 ``o`` 快捷键并排显示。

由于 TensorBoard 是一个 Web 服务器（而非类似 Rerun 的 GUI 应用），绑定后会运行一个 Textual 后台工作器，以约 0.5 秒的间隔轮询 ``localhost:6006`` 最长约 60 秒，仅在端口响应后才打开浏览器访问 ``http://localhost:6006/``。这一机制可应对首次运行时 ``uvx`` 解析缓慢、TensorBoard 绑定耗时超过几秒的情况。URL 会显示在面板和通知中，方便无界面/远程用户复制粘贴（或配置 SSH 隧道）。若 ``webbrowser`` 无法找到默认浏览器，绑定将发出警告，提示用户手动访问该 URL。

TensorBoard 子进程的 ``stdout`` 和 ``stderr`` 被捕获至运行目录 ``events.out.tfevents.*`` 文件旁的 ``tensorboard.stdout.log`` 和 ``tensorboard.stderr.log``。若服务器在轮询窗口内始终未启动，绑定将发出错误通知，指向 stderr 日志，以便故障可调试而非静默失败。

若摘要缺少 ``"tensorboard"`` 块（例如传入了 ``--no-tensorboard``），则面板不显示，不启动子进程，不打开浏览器，快捷键改为发出警告通知。

## 非交互式启动器（`worldforge-open-tensorboard`）

相同的启动/轮询/探测流程也可作为 CLI 用于非交互场景——在 CI 中验证接线、无需运行 Textual 报告即可从 Shell 打开 TensorBoard，或测试启动命令的变更：

```bash
uv run worldforge-open-tensorboard --logdir .worldforge/tensorboard/<run>
```

常用标志：

| 标志 | 默认值 | 用途 |
| --- | --- | --- |
| ``--logdir <path>`` | 必填 | 包含 ``events.out.tfevents.*`` 文件的运行目录。 |
| ``--port <int>`` | ``6006`` | 绑定的 TCP 端口。 |
| ``--host <host>`` | ``localhost`` | 轮询和探测的主机。 |
| ``--ready-timeout <sec>`` | ``60`` | 等待端口绑定的最长时间。 |
| ``--poll-interval <sec>`` | ``0.5`` | 就绪等待期间 TCP 探测的间隔秒数。 |
| ``--probe`` | 关闭 | 就绪后，获取 ``http://host:port/`` 并断言响应体包含 ``TensorBoard`` 标记。成功或失败后均关闭子进程。适用于"是否真正工作"的冒烟测试检查。 |
| ``--no-browser`` | 关闭 | 服务器就绪后跳过 ``webbrowser.open``。 |
| ``--keep-running`` | 关闭（不带 ``--probe`` 时隐含） | 阻塞直至子进程退出或收到 SIGINT。 |
| ``--shutdown-timeout <sec>`` | ``5`` | 等待子进程优雅关闭的秒数。 |

退出码：成功时为 ``0``，就绪超时或探测失败时为 ``1``，输入错误（``--logdir`` 缺失、计时参数非正数、启动 ``OSError``）时为 ``2``。

冒烟测试示例：

```bash
mkdir -p /tmp/tb-smoke
uv run worldforge-open-tensorboard \
  --logdir /tmp/tb-smoke \
  --probe --no-browser \
  --ready-timeout 120
```

## 程序化接口

已直接驱动 WorldForge 的宿主方可无需通过案例展示脚本而直接使用桥接模块。公开接口与 ``worldforge.rerun`` 相似，位于 ``worldforge.tensorboard``：

```python
from worldforge.tensorboard import (
    TensorBoardCheckpointInspector,
    TensorBoardLogConfig,
    TensorBoardSession,
    create_tensorboard_inspector,
)

inspector = create_tensorboard_inspector(
    log_dir=".worldforge/tensorboard/checkpoint-inspection",
    run_name="baseline",
)
inspector.log_checkpoint_summary(
    {
        "output": "/path/to/pusht/lewm_object.ckpt",
        "policy": "pusht/lewm",
        "repo_id": "galilai/lewm-pusht",
        "revision": "<commit-sha>",
    }
)
inspector.log_score_distribution(scores, best_index=1, best_score=scores[1])
inspector.log_metrics({"plan_latency_ms": 25.0, "total_latency_ms": 30.0})

# Optional: surface per-parameter weight histograms when host has the live
# checkpoint loaded. Tensor-like values (``detach``/``cpu``/``numpy``) are
# flattened automatically.
inspector.log_state_dict_histograms(model.state_dict())

inspector.flush()
inspector.close()
```

会话为懒惰初始化，因此构造检查器实例不产生任何副作用，直至第一次调用 ``log_*``。``close()`` 为幂等操作。

## 边界

- 桥接模块不宣传 ``predict``、``embed``、``plan``、``score`` 或 ``policy`` 能力。它纯粹用于可观测性。
- 桥接模块不会自行导入 torch。权重直方图需要宿主方通过 ``log_state_dict_histograms`` 传入类张量对象——适用于 LeWorldModel 运行时已在宿主方加载的场景。
- 桥接模块不读取 ``.env`` 或任何其他秘密文件。提供方事件消息在 :mod:`worldforge.models` 中到达桥接模块前已完成脱敏；桥接模块随后再次过滤，在写入文本面板前去除 ``api_key=``、``token=``、``secret=``、``signature=`` 以及签名 URL 的 ``?signature=``/``?token=`` 查询片段。
- ``tfevents`` 文件保留在本地。若需将 TensorBoard 运行作为发布证明共享，请以归档其他案例展示工件的方式归档日志目录。

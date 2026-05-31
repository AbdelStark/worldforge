# 机器人回放案例展示

真实机器人案例展示是 WorldForge 的主要端到端物理 AI 演示。它将 Hugging Face LeRobot 策略与 LeWorldModel 代价模型检查点相结合，然后使用 WorldForge 的策略加打分规划器来选取并 mock 回放最优动作片段。

该命令不控制任何硬件。它演示策略推断、打分模型推断、候选动作排序、提供方事件以及本地回放；机器人控制器、安全检查以及任务专属预处理仍由宿主方持有。

默认任务为 PushT，默认策略为 `lerobot/diffusion_pusht`，默认 LeWorldModel 检查点为 `~/.stable-wm/pusht/lewm_object.ckpt`。

有关实现层面的契约、张量形状、提供方调用序列以及真实机器人映射，请参阅[机器人案例展示技术深入解析](./robotics-showcase-deep-dive.md)。

<div align="center">
<table>
  <tr>
    <td width="50%">
      <img src="../../assets/img/robotics-showcase-lerobot-leworldmodel-2.png" alt="WorldForge robotics showcase TUI with pipeline flow, runtime metrics, and tensor contract" width="100%" />
      <br />
      <sub><strong>流水线：</strong>真实 LeRobot 策略、真实 LeWorldModel 检查点打分、WorldForge 规划、本地 mock 回放。</sub>
    </td>
    <td width="50%">
      <img src="../../assets/img/robotics-showcase-lerobot-leworldmodel-1.png" alt="WorldForge robotics showcase TUI with robot-arm illustration, candidate ranking, and tabletop replay" width="100%" />
      <br />
      <sub><strong>决策：</strong>所选候选、代价分布、提供方事件以及桌面回放。</sub>
    </td>
  </tr>
</table>
</div>

## 运行方式

使用单命令案例展示入口点：

```bash
scripts/robotics-showcase
```

默认情况下，该脚本：

- 启动带有宿主方持有可选依赖的临时 Python 3.13 `uv` 运行时；
- 请求 `lerobot[transformers-dep]==0.5.1`，使 Python 3.13 策略导入路径在 LeWorldModel 运行时也已安装的情况下保持稳定；
- 运行真实的 LeRobot 策略推断和真实的 LeWorldModel 检查点打分；
- 打开分阶段的 Textual 报告，包含流水线跟踪、指标条、张量契约、候选排序、提供方事件日志、机械臂图示、桌面回放以及 Rerun 打开快捷方式；
- 将 JSON 摘要写入 `/tmp/worldforge-robotics-showcase/real-run.json`；
- 将可视化 Rerun 记录写入 `/tmp/worldforge-robotics-showcase/real-run.rrd`；
- 在 `.worldforge/tensorboard/` 下写入 TensorBoard ``tfevents`` 日志，用于 LeWorldModel 检查点检视（来源、得分分布、延迟、提供方事件）。

常用标志：

```bash
scripts/robotics-showcase --health-only       # 无副作用的依赖/检查点预检
scripts/robotics-showcase --no-tui            # 纯终端报告
scripts/robotics-showcase --json-only         # 仅机器可读摘要
scripts/robotics-showcase --no-rerun          # 跳过默认的 Rerun .rrd 工件
scripts/robotics-showcase --rerun-output /tmp/pusht.rrd
scripts/robotics-showcase --no-tensorboard    # 跳过默认的 TensorBoard tfevents
scripts/robotics-showcase --tensorboard-logdir .worldforge/tensorboard/pusht
scripts/robotics-showcase --tui-stage-delay 0.1
scripts/robotics-showcase --no-tui-animation
scripts/robotics-showcase --lewm-asset-cache-dir ~/.cache/worldforge/leworldmodel
scripts/robotics-showcase --lewm-revision 22b330c28c27ead4bfd1888615af1340e3fe9052
```

在 TUI 中按 `o` 打开 Rerun 工件，或从 Shell 运行：

```bash
uvx --from "rerun-sdk>=0.24,<0.32" rerun /tmp/worldforge-robotics-showcase/real-run.rrd
```

在 TUI 中按 `t` 打开 TensorBoard 日志，或从 Shell 运行：

```bash
uvx --from "tensorboard>=2.16,<3" tensorboard --logdir .worldforge/tensorboard
```

有关标签布局和编程式 API，请参阅 [TensorBoard 集成](./tensorboard.md)。

## CI 冒烟测试策略

实时可选运行时工作流为 `.github/workflows/robotics-showcase.yml`。它与普通的可安全检出 CI 门控分开，因为它下载模型资产并在 CPU 上运行真实的 LeRobot 和 LeWorldModel 推断。它在每次拉取请求更新和推送到 `main` 时运行，无需手动触发、定时调度、标签门控或路径过滤器。

CI 命令刻意设计为非交互式：

```bash
scripts/robotics-showcase \
  --json-only \
  --no-tui \
  --no-rerun \
  --stablewm-home "$STABLEWM_HOME" \
  --lewm-cache-dir "$STABLEWM_HOME" \
  --lewm-asset-cache-dir "$LEWORLDMODEL_ASSET_CACHE_DIR" \
  --lewm-revision "$LEWORLDMODEL_REVISION" \
  --lerobot-cache-dir "$LEROBOT_CACHE_DIR" \
  --json-output "$WORLDFORGE_ROBOTICS_RUN_DIR/real-run.json" \
  --run-manifest "$WORLDFORGE_ROBOTICS_RUN_DIR/run_manifest.json"
```

工作流对 Hugging Face 策略下载、LeWorldModel 配置/权重下载、构建的 LeWorldModel 对象检查点以及 uv 包缓存使用 `actions/cache`。缓存键包含 Python 3.13、固定的 LeRobot 运行时版本和固定的 Hugging Face LeWM 修订版本。工作流默认仅上传经净化的 JSON 证据：`real-run.json`、`stdout.json` 和 `run_manifest.json`。LeWorldModel 检查点工件不上传，因为 GitHub Actions 工件是按运行的证据，并非最佳的长期检查点缓存。

## 演示内容

案例展示演练了 WorldForge 所设计的组合方式：

```text
PushT observation
  -> LeRobot policy checkpoint
  -> policy action candidates
  -> WorldForge candidate bridge
  -> LeWorldModel candidate tensors
  -> LeWorldModel cost-model scoring
  -> WorldForge policy+score planner
  -> local mock replay
  -> visual report and JSON artifact
```

核心规划器调用为：

```python
world.plan(
    policy_provider="lerobot",
    score_provider="leworldmodel",
    planning_mode="policy+score",
    ...
)
```

LeRobot 被视为 `policy` 提供方，LeWorldModel 被视为 `score` 提供方。规划器使用策略输出作为候选动作片段，让打分提供方对这些候选排序，选取代价最低的片段，并将所选可执行动作应用于本地 mock 世界。

## 解读报告面板

Textual 报告应被视为一条简短的证据链，而非通用仪表盘：

| 面板 | 解读方式 | 含义 |
| --- | --- | --- |
| 运行时条形图 | `policy`、`score`、`plan` 和 `total` 为已完成运行的挂钟毫秒数。 | `policy` 是 LeRobot 检查点调用，`score` 是 LeWorldModel 代价调用，`plan` 是 WorldForge 编排，`total` 包含整个案例展示流程。 |
| 张量契约 | `tensor MB` 和 `elements` 描述了传递给 LeWorldModel 的预处理打分张量。 | 这些数字解释了运行时形状和大小，不代表任务成功、物理保真度或模型质量得分。 |
| 候选排序 | 代价越低越好。`SELECTED` 行是 WorldForge mock 回放的候选。 | 所选行应与 `best_index`、提供方事件日志以及桌面回放的所选/最终标记一致。 |

综合解读各面板。一次连贯的运行应具有健康的提供方事件、与得分数量匹配的候选数量、一个所选候选，以及所选标记与所选行一致的桌面回放。如果存在不一致，在信任可视化结果之前应检查动作转换器、候选桥接、打分张量或任务预处理。

## 解读桌面回放

桌面回放是 PushT 工作空间的小型俯视图。像从天花板往下看一样阅读它：左/右是归一化的 `x` 轴，垂直位置是任务的桌面平面。它不是完整的物理仿真轨迹，也不是硬件摄像头画面。它是一张紧凑的地图，展示起始位置、目标、候选目标点、所选目标以及最终 mock 回放状态。

示例输出：

```text
Tabletop replay
---------------
  legend: S=start, G=goal, T=selected target, F=mock final, X=selected+final
  selected candidate: #2
  +------------------------------------------+
  |                                          |
  |                                          |
  |                                          |
  |                               0          |
  |                          1               |
  |                                          |
  |S                   G                     |
  |                                          |
  |               X                          |
  |                                          |
  |                                          |
  |                                          |
  |                                          |
  +------------------------------------------+
  x=0.00             x=0.50             x=1.00
```

通俗解读：

- `S` 是方块在本地回放中的起始位置。
- `G` 是期望的目标区域。
- `0` 和 `1` 是由 LeRobot 策略提出并由 LeWorldModel 打分的备选动作候选。
- `selected candidate: #2` 表示规划器选择了候选 `#2` 作为代价最低的候选。
- `X` 表示所选目标和 mock 最终状态落在同一渲染单元格上。在此示例中，候选 `#2` 没有单独打印为 `2`，因为地图将"所选目标"和"最终回放位置"合并为 `X`。
- `x=0.00`、`x=0.50` 和 `x=1.00` 标记归一化桌面的左、中、右侧。

心智模型很简单：想象策略说"这里有几个我可以尝试推动物体的位置"，这些可能的目标以候选标记出现。然后世界模型说"这个在目标下代价最低或最有希望"，WorldForge 选择该候选，将其转换为可执行的本地动作，并运行 mock 回放。地图展示决策结果：哪个候选胜出以及本地回放结束在哪里。

回放很有价值，因为它使策略加打分循环一目了然。如果所选候选接近目标且最终标记与其重叠，则本地规划对于这个玩具回放是连贯的。如果所选标记距目标很远，或最终标记与所选目标偏离，这是检查候选桥接、打分张量、动作转换器或任务预处理的信号。

## 逐步说明

1. 解析运行时设置。
   脚本选择 LeRobot 策略路径、LeWorldModel 策略名称、检查点路径、设备、缓存目录以及 PushT 桥接默认值。

2. 预检可选依赖。
   LeRobot、`stable_worldmodel`、torch、datasets、PushT 仿真包以及 Textual 从宿主方持有的 `uv` 运行时加载，它们不是 WorldForge 基础依赖。

3. 构建任务观测和打分张量。
   `worldforge.smoke.pusht_showcase_inputs` 提供封装好的 PushT 观测、LeWorldModel 打分信息张量、动作转换器以及默认演示所使用的候选构建钩子。

4. 运行 LeRobot 策略。
   `LeRobotPolicyProvider` 加载 `PreTrainedPolicy`，调用配置的策略模式，并保留原始策略输出与提供方事件元数据。

5. 将策略动作桥接为候选张量。
   封装好的 PushT 桥接将策略候选转换为 LeWorldModel 形状的动作候选张量。WorldForge 验证提供方边界，但不推断任务专属图像变换，也不投影不匹配的动作空间。

6. 使用 LeWorldModel 对候选打分。
   `LeWorldModelProvider` 调用 `stable_worldmodel.policy.AutoCostModel`，并通过 WorldForge 的 `score` 能力返回经排序的候选代价。

7. 选取并回放规划。
   WorldForge 从策略加打分规划中选取最优候选，并将转换后的动作片段应用于本地 mock 世界。此回放是本地可视化和状态更新，而非硬件执行。

8. 渲染报告。
   案例展示在 Textual 报告中展示流水线、运行时指标、张量大小、候选代价分布、所选规划、提供方事件以及桌面回放。相同数据以 JSON 格式保存，用于自动化和回归检查。

## 什么是真实的，什么是本地的

| 界面 | 运行时 | 边界 |
| --- | --- | --- |
| LeRobot 策略 | 真实的宿主方持有 LeRobot 检查点 | 产生任务专属的原始策略动作。 |
| LeWorldModel 打分 | 真实的宿主方持有 LeWorldModel 对象检查点 | 对预处理的像素、目标、历史和候选张量打分。 |
| PushT 桥接 | 封装好的 WorldForge 演示钩子 | 提供默认观测、打分信息张量、转换器和候选构建器。 |
| WorldForge 规划器 | 仓库内类型化编排 | 组合 `policy` 和 `score` 提供方，验证数量，选取最优动作片段。 |
| 执行 | 本地 mock 世界回放 | 仅为可视化更新本地场景。 |
| 机器人硬件 | 宿主方持有 | 控制器、安全检查、标定以及物理执行不在本演示范围内。 |

此区分是刻意为之。案例展示证明了真实的策略推断、真实的打分模型推断以及 WorldForge 的规划组合，但不声称物理安全性、硬件就绪性或任务通用预处理能力。

## 工件与指标

JSON 摘要包含：

- 所选候选索引和候选得分；
- LeRobot 策略延迟、LeWorldModel 打分延迟、规划延迟和总延迟；
- 张量形状和近似张量内存；
- 提供方事件日志条目；
- 所选动作数量和最终 mock 世界状态。

默认工件路径：

```text
/tmp/worldforge-robotics-showcase/real-run.json
/tmp/worldforge-robotics-showcase/run_manifest.json
```

需要保存特定工件位置时，在底层运行器上使用 `--json-output <path>`。使用 `--run-manifest <path>` 将证据清单与摘要并排放置在另一个目录中。清单将策略、打分、回放和报告证据链接回保留的摘要 JSON 和状态目录，而不嵌入检查点字节、原始策略输入或凭据。

## 自定义案例展示

封装好的 `scripts/robotics-showcase` 命令是经过完善的 PushT 入口点。对于其他任务，使用底层可配置运行器：

```bash
scripts/lewm-lerobot-real \
  --policy-path lerobot/diffusion_pusht \
  --policy-type diffusion \
  --checkpoint ~/.stable-wm/pusht/lewm_object.ckpt \
  --device cpu \
  --mode select_action \
  --observation-module /path/to/task_inputs.py:build_observation \
  --score-info-npz /path/to/lewm_score_tensors.npz \
  --translator /path/to/task_bridge.py:translate_candidates \
  --candidate-builder /path/to/task_bridge.py:build_action_candidates
```

对于非 PushT 任务，宿主必须提供：

- 与任务对齐的 LeRobot 策略和观测构建器；
- 兼容 LeWorldModel 的 `pixels`、`goal`、`action_history` 和 `action_candidates` 张量；
- 将原始策略动作转换为可执行 WorldForge `Action` 对象的动作转换器；
- 保留模型期望的动作维度和视野长度的候选构建器。

在转到已准备好宿主检查点之前，请使用可安全检出的候选实验室：

```bash
uv run python scripts/demo_showcases.py run policy-score-candidate-lab --workspace-dir .worldforge/demo-showcases --overwrite
```

它证明了 WorldForge 策略加打分工件路径、原始动作保留、所选候选、无效候选边界以及缺少转换器时的失败行为，无需机器人硬件、仿真器或检查点下载。

当默认 LeWorldModel 对象检查点缺失时，经过完善的命令可以从 Hugging Face 资产构建它。默认使用固定的 Hugging Face 提交 `22b330c28c27ead4bfd1888615af1340e3fe9052`；使用 `--lewm-revision <40字符提交SHA>` 或 `LEWORLDMODEL_REVISION` 指定不同的经审计的不可变资产修订版本。构建器在实例化模型或下载权重之前，对照官方 PushT LeWM 目标和参数白名单验证下载的 Hydra 配置。然后默认使用 `torch.load(..., weights_only=True)` 加载 `weights.pt`；`--allow-unsafe-pickle` 标志是针对历史权重的显式可信工件转义通道。此自动构建路径对 `--health-only` 跳过，后者仅报告检查点是否存在。

WorldForge 在遇到不匹配的动作空间时会报错，而不是填充、投影或静默重新解释。

## 源文件映射

- [`src/worldforge/smoke/robotics_showcase.py`](https://github.com/AbdelStark/worldforge/blob/main/src/worldforge/smoke/robotics_showcase.py)
  实现经过完善的报告入口点。
- [`src/worldforge/smoke/lerobot_leworldmodel.py`](https://github.com/AbdelStark/worldforge/blob/main/src/worldforge/smoke/lerobot_leworldmodel.py)
  实现底层真实策略加打分运行器。
- [`src/worldforge/smoke/pusht_showcase_inputs.py`](https://github.com/AbdelStark/worldforge/blob/main/src/worldforge/smoke/pusht_showcase_inputs.py)
  包含封装好的 PushT 观测、打分信息、转换器和候选桥接。
- [`src/worldforge/providers/lerobot.py`](https://github.com/AbdelStark/worldforge/blob/main/src/worldforge/providers/lerobot.py) 实现 LeRobot 策略提供方。
- [`src/worldforge/providers/leworldmodel.py`](https://github.com/AbdelStark/worldforge/blob/main/src/worldforge/providers/leworldmodel.py)
  实现 LeWorldModel 打分提供方。
- [`src/worldforge/_world.py`](https://github.com/AbdelStark/worldforge/blob/main/src/worldforge/_world.py) 包含策略加打分规划路径。

相关文档：

- [机器人案例展示技术深入解析](./robotics-showcase-deep-dive.md)
- [LeRobot 提供方](./providers/lerobot.md)
- [LeWorldModel 提供方](./providers/leworldmodel.md)
- [CLI 参考](./cli.md)
- [可选运行时操作手册](./playbooks.md#8-run-optional-runtime-smokes)

外部参考：

- [Hugging Face LeRobot](https://github.com/huggingface/lerobot)
- [LeRobot 策略文档](https://huggingface.co/docs/lerobot/bring_your_own_policies)
- [LeRobot PushT 扩散策略](https://huggingface.co/lerobot/diffusion_pusht)
- [LeWorldModel 论文](https://arxiv.org/abs/2603.19312)
- [LeWorldModel 项目主页](https://le-wm.github.io/)
- [LeWorldModel 代码](https://github.com/lucas-maes/le-wm)

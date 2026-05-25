# LeWorldModel 提供方

能力：`score`

分类类别：JEPA 潜在预测世界模型

成熟度：`stable`

`leworldmodel` 封装了 LeWorldModel 的 `stable_worldmodel.policy.AutoCostModel` 接口。它从任务形状的观测数据、目标和动作中对候选动作序列进行排序。WorldForge 将其建模为动作打分器，因为上游运行时返回的是代价值；它不生成视频、回答文本问题，也不直接改变 WorldForge 状态。

```text
pixels + action history + goal + candidate actions
  -> LeWorldModel cost model
  -> ActionScoreResult(scores, best_index, lower_is_better=True)
```

## 运行时所有权

WorldForge 负责：提供方注册、输入验证、打分结果验证、规划选择、元数据以及提供方事件。

由宿主方持有：

- `stable_worldmodel` 和 torch 的安装
- 检查点下载、解压及兼容性管理
- `$STABLEWM_HOME` 或 `LEWORLDMODEL_CACHE_DIR`
- 将传感器数据预处理为检查点形状的 `pixels`、`goal` 和 `action` 张量
- 将模型原生候选动作映射回 WorldForge `Action` 序列

WorldForge 不会将 LeWorldModel、torch、检查点存档或数据集添加到其基础包中。

## 配置

- `LEWORLDMODEL_POLICY` 或 `LEWM_POLICY`：自动注册所必需。值为相对于 `$STABLEWM_HOME` 的检查点运行名称，不含 `_object.ckpt` 后缀。示例：`pusht/lewm`。
- `LEWORLDMODEL_CACHE_DIR`：可选的检查点根目录覆盖。
- `LEWORLDMODEL_DEVICE`：可选的 torch 设备字符串，例如 `cpu`、`cuda` 或 `cuda:0`。

运行时清单：
`src/worldforge/providers/runtime_manifests/leworldmodel.json` 记录了策略别名、可选的检查点/设备配置、由宿主方持有的检查点工件、最小真实检查点冒烟测试命令、固定的上游导入边界 `stable_worldmodel.policy.AutoCostModel` 以及预期的有限代价信号。

程序化构建可以为测试或宿主方持有的运行时注入加载器和张量模块：

```python
from worldforge.providers import LeWorldModelProvider

provider = LeWorldModelProvider(
    policy="pusht/lewm",
    cache_dir="/models/stable-wm",
    device="cpu",
)
```

## 输入契约

`score_actions(...)` 要求：

```python
result = forge.score_actions(
    "leworldmodel",
    info={
        "pixels": pixels,
        "goal": goal,
        "action": action_history,
    },
    action_candidates=action_candidate_tensor,
)
```

验证规则：

- `info` 必须是 JSON 对象。
- `info["pixels"]`、`info["goal"]` 和 `info["action"]` 为必填项。
- 必填 info 字段必须是张量或至少具有三个维度的矩形嵌套数值数组。
- `action_candidates` 必须是形状为 `(batch, samples, horizon, action_dim)` 的张量或矩形嵌套数值数组。
- 返回的代价值必须能展平为有限数值分数。
- 返回的打分张量形状必须每个候选动作样本恰好包含一个分数。形状如 `(samples,)`、`(1, samples)` 或 `(samples, 1)` 均可接受；含有模糊非单元素维度的情况在返回 `ActionScoreResult` 之前即会失败。
- 返回的分数数量必须与被打分的候选集数量相匹配。

分数即为代价：值越小越好。WorldForge 将 `best_index` 设置为代价最低的候选，除非提供方返回了经过验证的显式索引。

## 规划

打分规划将 WorldForge 动作与模型原生张量分开处理：

```python
from worldforge import Action

plan = world.plan(
    goal="select the lowest-cost LeWorldModel candidate",
    provider="leworldmodel",
    planner="leworldmodel-mpc",
    candidate_actions=[
        [Action.move_to(0.1, 0.5, 0.0)],
        [Action.move_to(0.4, 0.5, 0.0)],
    ],
    score_info={
        "pixels": pixels,
        "goal": goal_pixels,
        "action": action_history,
    },
    score_action_candidates=action_candidate_tensor,
    execution_provider="mock",
)
```

选定的 `Plan.actions` 来自 `candidate_actions[best_index]`。`Plan.predicted_states` 保持为空，因为打分提供方对候选未来进行排序，但不返回 WorldForge 状态展开。使用支持 `predict` 的执行提供方来调用 `execute_plan(...)`。

如需在无需 LeWorldModel 或 torch 的情况下，以可安全检出的方式构建动作候选、通过策略+打分规划对其排序并记录选定动作工件，请运行 `uv run python scripts/demo_showcases.py run policy-score-candidate-lab`。

## 任务桥接

WorldForge 内置了一个小型桥接注册表，供冒烟测试命令使用，而非通用的张量预处理器。首个注册的桥接为 `pusht`，它连接：

- `build_observation()`：用于 LeRobot PushT 策略输入
- `build_score_info()`：用于 LeWorldModel 的 `pixels`、`goal` 和 `action`
- `translate_candidates_contract`：用于 WorldForge 回放动作
- `build_action_candidates()`：用于 `1 x 3 x 4 x 10` 的 PushT 打分张量

使用较低层级的运行器调用它：

```bash
scripts/lewm-lerobot-real \
  --policy-path lerobot/diffusion_pusht \
  --checkpoint ~/.stable-wm/pusht/lewm_object.ckpt \
  --bridge pusht
```

桥接注册表记录了预期的策略、打分以及候选张量形状。运行清单会复制该形状摘要及观察到的打分张量形状，使问题证据能够显示宿主方是否使用了预期的任务契约。WorldForge 验证形状一致性，并在规划前对动作维度不匹配的情况进行报错；宿主方仍需负责任务预处理和任何非 PushT 桥接。

## 运行时检查

可安全检出的提供方/规划器演示：

```bash
uv run worldforge-demo-leworldmodel
uv run worldforge-demo-leworldmodel --json-only
```

这使用了注入的确定性代价运行时，无需加载上游检查点即可验证 WorldForge 的提供方和规划路径。

真实检查点冒烟测试：

```bash
scripts/lewm-real --checkpoint ~/.stable-wm/pusht/lewm_object.ckpt --device cpu \
  --json-output /tmp/lewm-real-summary.json \
  --run-manifest .worldforge/runs/lewm-real/run_manifest.json
```

这会加载宿主方持有的上游运行时和目标检查点，然后通过 `LeWorldModelProvider` 对合成的 PushT 形状候选张量进行打分。这是真实的检查点打分，而非特定任务的预处理或机器人执行。

JSON 摘要和可选的运行清单包含打分载荷摘要、输入张量形状摘要、提供方事件计数、运行时 API 以及脱敏的工件链接。它们不包含检查点字节或宿主方凭据。

包装器所展示的上游依赖为 `stable-worldmodel`，因为官方的 `lucas-maes/le-wm` 仓库将 `stable_worldmodel.policy.AutoCostModel("pusht/lewm")` 作为 LeWorldModel 目标检查点的加载路径。WorldForge 使用该运行时 API 调用 LeWM 检查点的 `get_cost(...)`；它不会以通用 SWM 基线替代 LeWorldModel。

LeRobot + LeWorldModel 机器人回放案例展示：

```bash
scripts/robotics-showcase
```

这将 `LeWorldModelProvider` 用作真实策略+打分案例展示的打分方。完整的可运行上下文见 [CLI 参考](../cli.md)、[示例与 CLI 命令](../examples.md) 以及 [机器人回放案例展示](../robotics-showcase.md)。

## 故障模式

- 同时缺少 `LEWORLDMODEL_POLICY` 和 `LEWM_POLICY` 会导致提供方未被注册。
- 缺少 `torch` 或 `stable_worldmodel.policy.AutoCostModel` 会由 `health()` 报告。
- 检查点加载失败会被包装为 `ProviderError`。
- 若未配置设备，提供方会在 `cpu` 上准备运行时；如需宿主方持有的加速器，请传入 `LEWORLDMODEL_DEVICE` 或 `device=`。
- 缺少必填的 `pixels`、`goal` 或 `action` 字段会在调用模型之前失败。
- 参差不齐的嵌套数组、非有限值或低秩张量会在调用模型之前失败。
- 非四维的候选动作会在调用模型之前失败。
- 非有限的模型输出会在返回 `ActionScoreResult` 之前失败。
- 打分张量形状含有多个非单元素维度时，会在返回 `ActionScoreResult` 之前失败。
- 返回的分数数量必须与候选样本数量相匹配。
- 若打分结果无法识别范围内的候选动作，打分规划将失败。

## 测试

- `tests/test_leworldmodel_provider.py` 涵盖输入验证、打分输出、提供方健康状态、事件发射以及规划集成。
- `tests/test_leworldmodel_e2e_demo.py` 涵盖可安全检出的端到端演示。
- `tests/test_leworldmodel_smoke_script.py` 和 `tests/test_leworldmodel_uv_tasks.py` 涵盖冒烟命令解析和检查点构建器行为，无需真实检查点。
- `tests/test_lerobot_leworldmodel_smoke_script.py` 和 `tests/test_robotics_showcase.py` 涵盖组合的 LeRobot + LeWorldModel 运行器以及案例展示默认值，无需可选运行时。

## 主要参考资料

- [LeWorldModel 论文](https://arxiv.org/abs/2603.19312)
- [LeWorldModel 项目主页](https://le-wm.github.io/)
- [LeWorldModel 代码](https://github.com/lucas-maes/le-wm)

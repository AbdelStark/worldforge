# 示例与 CLI 命令

使用 CLI 索引查看当前可运行的示例及可选冒烟测试路径：

```bash
uv run worldforge examples
uv run worldforge examples --format json
```

完整的命令接口请参阅 [CLI 参考](./cli.md)。

## 演示案例展示运行器

| 工作流 | 接口 | 命令 |
| --- | --- | --- |
| `demo-showcases` | 针对本地世界状态、诊断、回放、提供方故障、证据审查、发布演练及食谱证据的 checkout 安全、基于 Issue 的工作流 | `uv run python scripts/demo_showcases.py run all --workspace-dir .worldforge/demo-showcases` |

```bash
uv run python scripts/demo_showcases.py list
uv run python scripts/demo_showcases.py run first-run --workspace-dir .worldforge/demo-showcases
uv run python scripts/demo_showcases.py run all --workspace-dir .worldforge/demo-showcases --format json --overwrite
```

每个选定的工作流会在 `.worldforge/demo-showcases/<workflow>/runs/<run-id>/` 下写入
保留的 `run_manifest.json`、`results/summary.json` 和 `reports/summary.md`。
运行器不会安装可选的模型运行时、调用付费提供方、打开 GUI 或控制机器人。
有关工件矩阵，请参阅[演示案例展示工作流](./demo-showcases.md)；
有关面向任务的食谱，请参阅[用例食谱](./use-case-cookbook.md)。

## 机器人案例展示 TUI

| 示例 | 接口 | 命令 |
| --- | --- | --- |
| `robotics-showcase` | 真实 PushT policy+score 运行和 Textual 报告 | `scripts/robotics-showcase` |

机器人案例展示报告是可选的 Textual 界面；同一运行也可以不打开 TUI。

```bash
scripts/robotics-showcase
scripts/robotics-showcase --no-tui
```

该报告将 Textual 排除在基础依赖集之外。若需要可视化界面，请使用 `harness` 附加项
安装或运行。

可用流程：

| 流程 | 用途 |
| --- | --- |
| `leworldmodel` | 通过 LeWorldModel 提供方接口的可视化打分规划路径。 |
| `lerobot` | 通过 LeRobot 提供方接口的可视化策略加打分路径。 |
| `cosmos-policy` | 通过 Cosmos-Policy 提供方接口的可视化已保存 ALOHA `/act` 回放。 |
| `gr00t-replay` | 通过 GR00T 提供方接口的可视化已保存 GR00T N1.7 PolicyClient 回放。 |
| `robotics-compare` | 通过单一回放接口对 LeRobot、Cosmos-Policy 和 GR00T 策略进行可视化比较。 |
| `diagnostics` | 可视化提供方诊断与基准测试比较路径。 |
| `workbench` | 用于适配器晋升工作的可视化提供方创作证据路径。 |

## Rerun 录制

| 示例 | 接口 | 命令 |
| --- | --- | --- |
| `rerun-observability-showcase` | 提供方事件、世界状态快照、3D 对象包围盒、规划工件、基准测试指标 | `uv run --extra rerun worldforge-demo-rerun` |
| `rerun-robotics-showcase` | 带候选目标、选定轨迹、打分柱状图、延迟柱状图、提供方事件及回放快照的真实 PushT 策略+打分运行 | `scripts/robotics-showcase` |

Rerun 案例展示默认将录制写入 `.worldforge/rerun/worldforge-rerun-showcase.rrd`。使用以下命令打开：

```bash
uv run --extra rerun rerun .worldforge/rerun/worldforge-rerun-showcase.rrd
```

有关实时查看器模式和 Python API 用法，请参阅 [Rerun 集成](./rerun.md)。

## 预测与评估

| 示例 | 命令 | 用途 |
| --- | --- | --- |
| `basic-prediction` | `uv run python examples/basic_prediction.py` | 创建模拟世界状态、执行预测和规划，并打印物理评估报告。 |

## 提供方比较

| 示例 | 命令 | 用途 |
| --- | --- | --- |
| `cross-provider-compare` | `uv run python examples/cross_provider_compare.py` | 注册第二个确定性提供方并比较预测输出。 |

## 打分规划

| 示例 | 命令 | 运行时边界 |
| --- | --- | --- |
| `leworldmodel-score-planning` | `uv run worldforge-demo-leworldmodel` | 使用注入了确定性代价运行时的 `LeWorldModelProvider`。 |

## 策略加打分规划

| 示例 | 命令 | 运行时边界 |
| --- | --- | --- |
| `lerobot-policy-score-planning` | `uv run worldforge-demo-lerobot` | 使用注入了确定性策略运行时的 `LeRobotPolicyProvider`。 |

两个打包演示均在干净的 checkout 环境中验证 WorldForge 适配器、规划、执行、
持久化、重载和事件路径。它们不安装可选的机器学习运行时，也不运行上游神经网络
检查点推理。

## 服务宿主参考

| 示例 | 命令 | 运行时边界 |
| --- | --- | --- |
| `service-host` | `uv run python examples/hosts/service/app.py --provider mock --port 8080` | 标准库 HTTP 参考宿主；嵌入服务拥有部署、凭据、遥测导出、告警及上游 SLA 处理。 |

服务宿主暴露以下端点：

| 端点 | 用途 |
| --- | --- |
| `GET /healthz` | 仅进程存活检查。 |
| `GET /readyz` | 框架存活、已配置提供方、提供方健康状态、流量决策及 `doctor()` 摘要。 |
| `GET /providers` | 当前宿主进程的已注册提供方诊断信息。 |
| `POST /workflows/mock-predict` | 安全的确定性 mock 预测冒烟测试。 |
| `POST /workflows/predict` | 使用包含 `provider`、`world_state` 和 `action` 的 JSON 请求体配置提供方预测工作流。 |

`/readyz` 返回 `ready`、`provider_unconfigured` 或 `provider_unhealthy`。
只有 `ready` 意味着宿主应接受提供方支持的工作流流量；其他状态告知宿主负载均衡器
或任务运行器在运维人员检查 `checks.provider_health` 及内嵌 `doctor` 摘要期间
对该进程进行排水处理。

每个响应均包含或回显一个请求 ID。提供方事件通过 `JsonLoggerSink` 以该请求 ID
发送，以便宿主日志能够将 HTTP 请求与提供方调用关联起来。公共错误使用类型化的
JSON 负载并脱敏明显的类密钥值，但生产服务仍然负责凭据存储、请求认证、仪表板、
告警路由以及提供方 SLA 策略。

## 批量评估宿主

| 示例 | 命令 | 运行时边界 |
| --- | --- | --- |
| `batch-eval-host` | `uv run python examples/hosts/batch-eval/app.py benchmark --provider mock` | 标准库任务参考宿主；嵌入式批处理系统拥有调度、持久存储、凭据及提供方专属运行时设置。 |

在干净的 checkout 环境中运行确定性 mock 评估和基准测试任务：

```bash
uv run python examples/hosts/batch-eval/app.py \
  --workspace .worldforge/batch-eval \
  eval --suite planning --provider mock

uv run python examples/hosts/batch-eval/app.py \
  --workspace .worldforge/batch-eval \
  benchmark --provider mock --operation predict --iterations 1 \
  --input-file examples/benchmark-inputs.json \
  --budget-file examples/benchmark-budget.json
```

每个任务在 `.worldforge/batch-eval/runs/<run-id>/` 下写入共享运行工作区，
包含 `run_manifest.json`、JSON/Markdown/CSV 报告、基准测试任务的输入和预算文件副本，
以及指向清单的 JSON 标准输出摘要。预算违规在保留失败运行后返回退出码 `1`，
使 CI 或调度器可以使任务失败，同时保留对 Issue 安全的工件。

若要换用真实提供方，请在已安装该提供方、配置了凭据、安装了可选运行时依赖，
且基准测试输入与该提供方声明能力相匹配的准备好的宿主上运行相同命令。
将调度、进程上层的重试策略、长期工件存储和凭据轮换保持在基础包之外。

## 机器人操作宿主

| 示例 | 命令 | 运行时边界 |
| --- | --- | --- |
| `robotics-operator-host` | `uv run python examples/hosts/robotics-operator/app.py review --sample-translator` | 标准库离线操作员审查宿主；实验室应用拥有动作转换器、检查清单策略、批准、控制器集成、联锁及安全认证。 |

默认模式不调用机器人控制器。它通过显式样本 PushT 转换器运行确定性 LeRobot
策略接口和打分提供方，然后在 `.worldforge/robotics-operator/runs/<run-id>/` 下
写入保留的运行工作区，包含：

- `results/action_chunks.json`：所有候选动作块及选定块。
- `results/score_rationale.json`：分数值、最优索引及打分元数据。
- `logs/provider-events.jsonl`：提供方事件流。
- `results/approval.json`：由宿主方持有的检查清单及试运行批准状态。
- `results/replay.json`：离线回放工件。

除非嵌入宿主在代码中提供了显式的控制器钩子、所有检查清单项均为 true，
且已记录试运行批准，否则控制器执行保持禁用状态。WorldForge 仅生成类型化的
策略、打分、事件、回放和运行清单工件；它不认证机器人硬件、任务安全、紧急停止、
工作空间就绪状态或控制器行为。

## 参考宿主部署食谱

这些食谱用于将 WorldForge 嵌入宿主进程，而非将 WorldForge 作为托管服务部署。
WorldForge 拥有提供方契约、类型化验证、本地运行清单、报告渲染及经脱敏的证据辅助工具。
宿主拥有部署、认证、排队、持久存储、控制器集成、告警、回滚、可用性以及提供方
或机器人安全策略。

路径分类：

| 路径 | 使用场景 | 成功信号 | 由宿主方持有的边界 |
| --- | --- | --- | --- |
| checkout-safe | `mock` 提供方、确定性示例、无凭据 | 命令退出 `0`、`/readyz` 返回 `ready`，或写入运行清单 | 无物理保真度、可用性或持久性声明 |
| prepared-host | 可选提供方/运行时已由宿主安装 | 提供方健康状态正常，冒烟测试写入证据 | 依赖安装、检查点、缓存目录及运行时补丁 |
| credentialed | 在仓库外加载了密钥的远程提供方 | `provider info` 显示脱敏配置且健康检查通过 | 密钥存储、凭据轮换、上游 SLA 及网络出口 |
| GPU-bound | LeWorldModel、LeRobot、GR00T 或其他设备绑定运行时 | 宿主预检命名了设备，冒烟测试记录了清单 | CUDA/Metal 驱动、设备调度、模型资产及内存压力 |
| robotics-lab | 围绕任务专属策略/动作转换的操作员审查 | 试运行审查记录批准，默认不调用控制器 | 工作空间安全、联锁、控制器钩子、操作员批准及安全认证 |

这些食谱不引入新的提供方环境变量，因此 `.env.example` 保持不变，除非未来提供方
添加了真实配置。

### 标准库服务宿主食谱

由宿主方持有的边界：WorldForge 将提供方诊断映射到 `/readyz`，发出类型化公共错误，
并可运行确定性 mock 或生成工作流。嵌入服务拥有 HTTP 部署、请求认证、路由、排队、
持久状态、日志传输、告警、上游 SLA 策略及回滚。

环境变量模板：

```bash
export WORLDFORGE_SERVICE_PROVIDER=mock
export WORLDFORGE_SERVICE_STATE_DIR=.worldforge/service-worlds
export WORLDFORGE_SERVICE_PORT=8080
# Prepared-host path only: export LEWORLDMODEL_POLICY=... or LEROBOT_POLICY_PATH=...
```

进程命令：

```bash
mkdir -p .worldforge/service/logs
PYTHONUNBUFFERED=1 uv run python examples/hosts/service/app.py \
  --provider "${WORLDFORGE_SERVICE_PROVIDER:-mock}" \
  --state-dir "${WORLDFORGE_SERVICE_STATE_DIR:-.worldforge/service-worlds}" \
  --port "${WORLDFORGE_SERVICE_PORT:-8080}" \
  2>&1 | tee .worldforge/service/logs/service.log
```

就绪检查命令：

```bash
curl -fsS http://127.0.0.1:8080/readyz | python -m json.tool
```

预期成功信号：`status` 为 `ready`，`traffic` 为 `accept`，
`checks.provider_healthy` 为 `true`。首次故障排查步骤：若状态为
`provider_unconfigured` 或 `provider_unhealthy`，运行
`uv run worldforge doctor --registered-only` 和 `uv run worldforge provider health <provider>`，
然后检查脱敏后的 `checks.provider_health.details` 字段。

冒烟测试命令：

```bash
curl -fsS -X POST http://127.0.0.1:8080/workflows/mock-predict \
  -H 'content-type: application/json' \
  -H 'x-request-id: service-smoke-001' \
  -d '{}' | python -m json.tool
```

日志查看命令：

```bash
tail -f .worldforge/service/logs/service.log
```

证据导出命令：

```bash
mkdir -p .worldforge/service/evidence
curl -fsS http://127.0.0.1:8080/readyz > .worldforge/service/evidence/readyz.json
curl -fsS http://127.0.0.1:8080/providers > .worldforge/service/evidence/providers.json
```

首次回滚步骤：在嵌入服务中对该宿主进行排水处理，使用最后已知良好的提供方配置或
`WORLDFORGE_SERVICE_PROVIDER=mock` 重启它，并在 `/readyz` 返回 `ready` 之前
保持上游流量禁用。

### 批量评估宿主食谱

由宿主方持有的边界：WorldForge 运行确定性评估和基准测试契约，写入
`run_manifest.json`、报告工件和预算裁定。批处理平台拥有调度、排队、进程上层的
重试、凭据、长期工件存储、预算变更审查、告警及回滚。

环境变量模板：

```bash
export WORLDFORGE_BATCH_WORKSPACE=.worldforge/batch-eval
export WORLDFORGE_BATCH_STATE_DIR=.worldforge/batch-eval/worlds
# Prepared-host or credentialed path only: load provider-specific env from .env.example.
```

就绪检查命令：

```bash
uv run worldforge doctor --registered-only
uv run worldforge doctor --capability predict
uv run worldforge provider health mock
```

进程命令：

```bash
uv run python examples/hosts/batch-eval/app.py \
  --workspace "${WORLDFORGE_BATCH_WORKSPACE:-.worldforge/batch-eval}" \
  --state-dir "${WORLDFORGE_BATCH_STATE_DIR:-.worldforge/batch-eval/worlds}" \
  benchmark --provider mock --operation predict --iterations 1 \
  --input-file examples/benchmark-inputs.json \
  --budget-file examples/benchmark-budget.json
```

冒烟测试命令：使用相同的 checkout 安全基准测试命令加 `--provider mock`；
它在不使用实际凭据的情况下验证报告渲染、预算评估、清单保留及批处理宿主退出码。

预期成功信号：JSON 标准输出包含 `status: "passed"`、`exit_code: 0`、
`run_manifest`，以及在提供预算文件时 `budget.passed` 值为 `true`。
预算违规仅在保留失败运行工作区后退出码为 `1`。

日志查看命令：

```bash
uv run worldforge runs list \
  --workspace-dir "${WORLDFORGE_BATCH_WORKSPACE:-.worldforge/batch-eval}" \
  --format markdown
```

证据导出命令：

```bash
uv run worldforge runs bundle <run-id> \
  --workspace-dir "${WORLDFORGE_BATCH_WORKSPACE:-.worldforge/batch-eval}"
```

首次故障排查步骤：打开 `<workspace>/runs/<run-id>/run_manifest.json`，
然后在删除或重试运行之前导出该包。首次回滚步骤：停止调度器队列，恢复最后已知
良好的输入或预算文件，重新运行 checkout 安全的 `mock` 基准测试，
然后才重新启用准备好的宿主或带凭据的提供方任务。

### 机器人操作宿主食谱

由宿主方持有的边界：WorldForge 运行离线策略加打分审查，保留选定的动作块、
打分依据、提供方事件、试运行批准、回放工件及清单。实验室宿主拥有任务观测数据、
动作转换器、工作空间就绪状态、紧急停止、操作员批准、控制器钩子、机器人硬件
及安全认证。

环境变量模板：

```bash
export WORLDFORGE_ROBOTICS_WORKSPACE=.worldforge/robotics-operator
export WORLDFORGE_ROBOTICS_STATE_DIR=.worldforge/robotics-operator/worlds
# Prepared-host, GPU-bound, or robotics-lab path only:
# export LEROBOT_POLICY_PATH=...
# export LEROBOT_DEVICE=cuda
# export LEWORLDMODEL_DEVICE=cuda
```

就绪检查命令：

```bash
uv run worldforge provider health mock
scripts/robotics-showcase --health-only
```

对于 checkout 安全的操作员食谱，使用第一个命令。在运行实际 LeRobot 或
LeWorldModel 之前，对准备好的宿主、GPU 绑定或机器人实验室路径使用
`--health-only` 案例展示预检。

进程命令：

```bash
uv run python examples/hosts/robotics-operator/app.py \
  --workspace "${WORLDFORGE_ROBOTICS_WORKSPACE:-.worldforge/robotics-operator}" \
  --state-dir "${WORLDFORGE_ROBOTICS_STATE_DIR:-.worldforge/robotics-operator/worlds}" \
  review --sample-translator --approve-dry-run \
  --check workspace_clear \
  --check emergency_stop_available \
  --check operator_present \
  --check controller_isolated
```

冒烟测试命令：使用相同的 checkout 安全审查命令加样本转换器。
它记录试运行审查并保持控制器执行禁用。

预期成功信号：JSON 标准输出包含 `status: "passed"`、`exit_code: 0`、
`run_manifest`、`controller_executed: false`，以及 `approval`、`action_chunks`、
`score_rationale`、`provider_events` 和 `replay` 的路径。

日志查看命令：

```bash
tail -n +1 \
  "${WORLDFORGE_ROBOTICS_WORKSPACE:-.worldforge/robotics-operator}"/runs/<run-id>/logs/provider-events.jsonl
```

证据导出命令：

```bash
uv run worldforge runs bundle <run-id> \
  --workspace-dir "${WORLDFORGE_ROBOTICS_WORKSPACE:-.worldforge/robotics-operator}"
```

首次故障排查步骤：在修改转换器或控制器代码之前，先检查 `results/approval.json` 和
`logs/provider-events.jsonl`。首次回滚步骤：保持控制器执行禁用，丢弃已生成的
动作块，返回最后批准的转换器/检查清单包，并在重新启用任何实验室控制器钩子之前
重新运行离线审查。

## 可选运行时冒烟测试

| 示例 | 命令 | 运行时边界 |
| --- | --- | --- |
| `leworldmodel-real-checkpoint-smoke` | `scripts/lewm-real --checkpoint ~/.stable-wm/pusht/lewm_object.ckpt --device cpu` | 需要由宿主方持有的 `stable_worldmodel`、torch、datasets、OpenCV、imageio 及 LeWM 检查点资产；通过 `stable_worldmodel.policy.AutoCostModel` 加载官方 LeWorldModel 对象检查点，并打印视觉管道、张量、延迟、事件及候选代价输出。 |
| `lerobot-leworldmodel-health` | `scripts/robotics-showcase --health-only` | 在运行完整案例展示之前，对 LeRobot、LeWorldModel 及检查点存在性进行非变更性预检。 |
| `lerobot-leworldmodel-real-robotics` | `scripts/robotics-showcase` | 需要由宿主方持有的 LeRobot、`stable_worldmodel`、torch、datasets、真实策略检查点、LeWM 检查点资产及 PushT 仿真依赖；使用 LeRobot 兼容的 `rerun-sdk` 解析为默认 Rerun 工件路径，打开带有 `o` 快捷键用于 Rerun 的分阶段 Textual 报告，并默认将录制写入 `/tmp/worldforge-robotics-showcase/real-run.rrd`。请参阅[机器人回放案例展示演练](./robotics-showcase.md)。 |

## 运维命令

```bash
uv run worldforge doctor --registered-only
uv run worldforge world create lab --provider mock
uv run worldforge world add-object <world-id> cube --x 0 --y 0.5 --z 0 --object-id cube-1
uv run worldforge world predict <world-id> --object-id cube-1 --x 0.4 --y 0.5 --z 0
uv run worldforge world list
uv run worldforge world objects <world-id>
uv run worldforge world history <world-id>
uv run worldforge world export <world-id> --output world.json
uv run worldforge world delete <world-id>
uv run worldforge provider list
uv run worldforge provider docs
uv run worldforge provider info mock
uv run worldforge predict kitchen --provider mock --x 0.3 --y 0.8 --z 0.0 --steps 2
uv run worldforge eval --suite planning --provider mock --format json
uv run worldforge benchmark --provider mock --iterations 5 --format json
```

对象的添加/更新/删除命令会将类型化的变更条目写入 `world history`；预测操作在
提供方返回下一状态后，将其提供方动作条目追加到历史记录中。

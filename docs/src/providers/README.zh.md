# 提供方

WorldForge 提供方是能力适配器。提供方页面应说明该适配器实际能做什么、宿主方必须提供什么、WorldForge 验证什么，以及调用方应预期哪些故障模式。

提供方发现与自动注册策略位于 `src/worldforge/providers/catalog.py`。请保持本页与提供方页面和该目录的一致性。
对于面向操作员的环境变量、可选包、超时、已准备好的宿主方资产以及首要诊断契约，请参阅[提供方配置索引](../provider-configuration-index.md)。
对于具体的解析器、凭据、重试、可选运行时、脚手架以及安全工件示例，请参阅[提供方故障模式图鉴](../provider-failure-gallery.md)。

## 提供方目录

<!-- provider-catalog:start -->
| 提供方 | 成熟度 | 能力面 | 注册方式 | 运行时所有权 |
| --- | --- | --- | --- | --- |
| `mock` | `stable` | `predict`, `embed` | 始终注册 | 仓库内确定性本地提供方 |
| [`cosmos-policy`](./cosmos-policy.md) | `beta` | 无（`policy` 需要宿主方提供 `action_translator`） | `COSMOS_POLICY_BASE_URL` | WorldForge 验证 `/act` 请求/响应和规划组合；宿主方负责 Cosmos-Policy 可达性/CUDA/运行时、ALOHA 观测构建以及将原始 14 维行数据转换为可执行 `Action` 对象 |
| [`leworldmodel`](./leworldmodel.md) | `stable` | `score` | `LEWORLDMODEL_POLICY` 或 `LEWM_POLICY` | 宿主方安装官方 LeWM 加载路径（`stable_worldmodel.policy.AutoCostModel`）、torch 及兼容的检查点 |
| [`gr00t`](./gr00t.md) | `beta` | `policy` | `GROOT_POLICY_HOST` | 宿主方运行或访问 Isaac GR00T 策略服务器 |
| [`lerobot`](./lerobot.md) | `stable` | `policy` | `LEROBOT_POLICY_PATH` 或 `LEROBOT_POLICY` | 宿主方安装 LeRobot 及兼容的策略检查点 |
| [`jepa`](./jepa.md) | `experimental` | `score` | `JEPA_MODEL_NAME` | 宿主方提供 torch、facebookresearch/jepa-wms 运行时依赖项以及任务预处理 |
| [`genie`](./genie.md) | `scaffold` | 脚手架 | `GENIE_API_KEY` | 能力关闭的保留位；Project Genie 没有受支持的自动化 API 契约 |
<!-- provider-catalog:end -->

## 候选脚手架

| 提供方 | 能力面 | 注册方式 | 运行时所有权 |
| --- | --- | --- | --- |
| [`jepa-wms`](./jepa-wms.md) | 直接构建的 `score` 候选 | 无 | 宿主方持有的 torch-hub/运行时实验；未导出或自动注册 |

候选脚手架在运行时适配器、限制、解析器覆盖率、文档和冒烟路径足够可信、调用方可依赖之前，将保持在包导出和自动注册之外。

## 能力模型

WorldForge 不将提供方能力视为徽章，而是将其作为可调用契约。

| 能力 | 提供方方法 | 结果契约 |
| --- | --- | --- |
| `predict` | `predict(world_state, action, steps)` | `PredictionPayload` |
| `embed` | `embed(text=...)` | `EmbeddingResult` |
| `score` | `score_actions(info, action_candidates)` | `ActionScoreResult` |
| `policy` | `select_actions(info)` | `ActionPolicyResult` |

规则：

- 除非适配器端到端实现了该方法，否则不得声明该能力。
- 对于仅返回潜在代价的模型，不得暴露 `predict`。
- 除非原始动作已被翻译为可执行的 WorldForge `Action` 对象，否则不得暴露 `policy`。
- 保持脚手架提供方的显式性：它们保留名称和契约，但不声明运行时支持。

完整的提供方类通过 `ProviderCapabilities` 暴露这些契约。较为精简的本地集成也可以实现一个可运行时检查的能力协议，例如带有 `score_actions(...)` 的 `Cost` 对象或带有 `select_actions(...)` 的 `Policy` 对象。协议实现通过 `WorldForge.register_cost(...)`、`register_policy(...)` 或 `register(...)` 注册；WorldForge 会对其进行包装，使诊断、提供方事件、规划和基准测试看到与完整提供方相同的能力面。

## 提供方配置文件

每个提供方都会暴露一个 `ProviderProfile`，用于路由、诊断和文档：

- 从 `ProviderCapabilities` 或已注册的能力协议派生的能力面
- 本地运行时与远程运行时
- 确定性行为与随机行为
- 实现成熟度，如 `stable`、`beta`、`experimental` 或 `scaffold`
- 必需的环境变量
- 支持的模态和工件类型
- HTTP 支持提供方的请求策略
- 供维护者说明注意事项的备注

Python：

```python
from worldforge import WorldForge

forge = WorldForge()
profile = forge.provider_profile("leworldmodel")
doctor = forge.doctor()

print(profile.supported_tasks)
print(doctor.issues)
```

CLI：

```bash
uv run worldforge provider list
uv run worldforge provider docs
uv run worldforge provider docs leworldmodel --format json
uv run worldforge provider info leworldmodel
uv run worldforge doctor --registered-only
uv run worldforge doctor --capability score
```

`doctor()` 默认包含已知但未注册的可选提供方，使缺少的配置在工作流失败之前即可见。当进程只需检查该进程已启用的提供方时，使用 `--registered-only`。

提供方还会暴露 `config_summary()` 用于问题证据和宿主方诊断。它报告已文档化的字段是否存在、来源（`env:<NAME>`、`direct`、`default` 或 `unset`）、是否为必填项以及是否类似密钥。它不返回原始值、令牌、端点字符串、检查点路径或构造函数参数。

```python
from worldforge.providers import LeWorldModelProvider

summary = LeWorldModelProvider().config_summary().to_dict()
print(summary["fields"])
```

## 运行时清单

真实的可选提供方还在 `src/worldforge/providers/runtime_manifests/` 中包含打包的 JSON 运行时清单。这些清单是无依赖的记录，宿主应用程序、发布检查和文档可以在不安装实时运行时的情况下读取它们。

架构版本 `1` 包含：

- `provider`：目录中的提供方名称
- `capabilities`：运行时涵盖的可调用 WorldForge 能力
- `optional_dependencies`：宿主方持有的包或导入路径
- `required_env_vars` 和 `optional_env_vars`：配置面
- `default_model`：默认模型、检查点或宿主方选择的模型槽位
- `device_support`：支持的设备类型，如 `cpu`、`cuda` 或 `remote`
- `host_owned_artifacts`：宿主方必须保留的检查点、策略服务器或翻译器
- `minimum_smoke_command`：证明运行时已正确连接的最小实时命令
- `expected_success_signal`：冒烟测试实证的具体通过条件
- `setup_hint`：提供方健康消息使用的简短修复提示
- `docs_path`：在上下文中解释清单的提供方页面

WorldForge 不会从这些清单中自动安装可选提供方运行时。缺少的可选依赖项会在 `health()` 输出中明确显示，并指向清单支持的冒烟路径。清单还为需要在不导入或构建提供方运行时的情况下检查已声明提供方环境变量的工具，提供相同的无值 `config_summary()` 结构。

## 运行时所有权

WorldForge 负责：

- 提供方注册及配置文件元数据
- 类型化的输入和输出验证
- 本地 JSON 世界状态持久化
- 跨 `predict`、`score` 和 `policy` 的规划组合
- 确定性评估和基准测试框架
- 提供方事件钩子

由宿主方持有：

- 凭据和端点可达性
- torch、LeWorldModel、LeRobot、Isaac GR00T、CUDA、TensorRT、检查点、数据集以及机器人运行时
- 将传感器数据预处理为模型原生张量
- 特定具身形态的动作翻译
- 运营遥测、追踪 ID、仪表盘及告警
- 持久化存储和工件保留

## 可观测性

HTTP 适配器会针对重试、成功和失败发出 `ProviderEvent` 记录。本地打分和策略适配器会在受支持时，围绕模型边界发出成功和失败事件。

通过 `WorldForge(event_handler=...)` 附加接收器：

```python
import logging
from pathlib import Path

from worldforge import WorldForge
from worldforge.observability import (
    JsonLoggerSink,
    OpenTelemetryProviderEventSink,
    ProviderMetricsSink,
    RunJsonLogSink,
    compose_event_handlers,
)

run_id = "provider-smoke"
metrics = ProviderMetricsSink()
forge = WorldForge(
    event_handler=compose_event_handlers(
        JsonLoggerSink(logger=logging.getLogger("demo.worldforge"), extra_fields={"run_id": run_id}),
        RunJsonLogSink(Path(".worldforge") / "runs" / run_id / "provider-events.jsonl", run_id),
        metrics,
    )
)
```

`ProviderMetricsSink.request_count` 统计发出的提供方事件数，因此重试事件会同时增加 `request_count` 和 `retry_count`。`RunJsonLogSink` 每行写入一条脱敏 JSON 记录，并在每条记录上保留 `run_id`，使提供方日志可与宿主方持有的运行清单关联。`OpenTelemetryProviderEventSink` 将提供方事件映射到可选的宿主方持有的追踪 span，附带有界属性：提供方、操作、阶段、尝试次数、耗时、状态类别、脱敏目标、能力和关联 ID。WorldForge 不安装 OpenTelemetry 导出器，也不持有采集器配置。

可选的实时冒烟测试入口点接受 `--run-manifest <path>` 以生成经验证的 `run_manifest.json`。该清单是安全的问题证据：它存储命令参数、包版本、提供方配置文件、能力、无值的环境变量存在性、运行时清单 ID、输入摘要、可选的输入夹具摘要、事件计数、结果摘要以及工件路径。它不存储凭据值、原始签名 URL 查询字符串、检查点字节或生成的媒体字节。

请使用[实时冒烟测试实证注册表](../live-smoke-evidence.md)查看哪些可选提供方冒烟测试有当前实证、哪些被跳过，以及如何将脱敏的 `run_manifest.json` 文件附加到提供方问题中。

## 编写规范

在添加或提升提供方之前，请文档化以下内容：

- 分类类别和能力面
- 配置和自动注册规则
- 宿主方持有的依赖项
- 输入形状和范围约束
- 输出架构及打分方向（如适用）
- 重试、超时、轮询和工件行为
- 故障模式
- 夹具覆盖率和冒烟路径
- 主要上游技术参考资料：仅限论文、仓库或官方 API 文档
- 使用 `uv run python scripts/generate_provider_docs.py --check` 检查生成的目录表

完整的实现清单请参阅[提供方编写指南](../provider-authoring-guide.md)。

# 提供方与平台路线图

本文档将 WorldForge 当前的发展方向转化为可直接创建 Issue 的工作流，涵盖真实提供方集成、生产级运行框架、宿主应用以及运维加固。本文作为 GitHub Issue 的规划来源，并不承诺其中每项内容已经实现。

最近审阅日期：2026-05-01。

## 完成情况快照

首个生产轨道已完成。GitHub 追踪器中的 Issue 仍可作为审计记录，但新的提供方和平台工作应从全新的选型记录或范围明确的后续 Issue 开始，而非重新打开这些实现切片。

| 追踪器 | 范围 | 完成信号 |
| --- | --- | --- |
| [#47](https://github.com/AbdelStark/worldforge/issues/47) | 提供方平台基础设施 | 已实现晋升门禁、运行时清单、合规性帮助工具、实时冒烟工件及可选运行时配置文件。 |
| [#48](https://github.com/AbdelStark/worldforge/issues/48) | 真实提供方实现 | LeWorldModel、LeRobot、GR00T、Cosmos-Policy、JEPA、JEPA-WMS 和 Genie 的延迟决策均已与可执行能力声明对照记录。 |
| [#49](https://github.com/AbdelStark/worldforge/issues/49) | 生产级运行框架 | 运行工作区、连接器就绪状态、实时检查、报告对比及提供方工作台流程均保留了安全工件。 |
| [#50](https://github.com/AbdelStark/worldforge/issues/50) | 参考宿主应用 | 批量评估、服务及机器人操作员宿主示例展示了由宿主方持有的集成边界。 |
| [#51](https://github.com/AbdelStark/worldforge/issues/51) | 可观测性、监控与日志 | 提供方事件模式、日志、指标、OpenTelemetry、就绪状态及故障手册均已提供，且不改变基础依赖边界。 |
| [#52](https://github.com/AbdelStark/worldforge/issues/52) | 可靠性、安全与发布门禁 | 凭证加固、请求预算、持久化架构决策记录（ADR）以及发布证据生成均已就位。 |

在为声明此路线图里程碑的版本打标签之前，请使用下方的发布门禁。

## 规划原则

将本路线图转化为 Issue 时，遵循以下原则：

- 保持基础包轻量。不得将 torch、机器人运行时、检查点管理器、Web 框架、仪表盘或遥测导出器添加到默认依赖集。
- 仅当提供方调用了真实的上游运行时或 API、验证了边界并具备基于夹具的故障覆盖时，才对其进行晋升。
- 保持可选运行时由宿主方持有。WorldForge 可提供适配器、启动器、合规性测试和参考宿主应用；宿主方自行管理凭证、设备、检查点、数据集、持久化存储、仪表盘、机器人控制器及安全策略。
- 将提供方事件视为安全敏感记录。每个新的可观测字段在进入日志、指标、链路、报告或导出前，必须通过脱敏测试。
- 将确定性检出测试与实时运行时冒烟测试分开。实时冒烟测试应明确标注，在缺少凭证或运行时包时能干净地跳过，并保留足够的工件以便调试失败。
- 每个 Issue 应明确说明其变更的能力面：`predict`、`embed`、`score` 或 `policy`。

## 目标终态

当 WorldForge 从"可信框架与演示"升级为具备以下特性的生产就绪提供方平台时，路线图即告完成：

| 维度 | 终态 |
| --- | --- |
| 提供方可信度 | 每项已声明的提供方能力均有真实可调用实现、合规性覆盖、生成的文档以及预备宿主冒烟路径。 |
| 提供方选型 | 新的提供方工作从书面选型记录开始，该记录需对用户价值、上游成熟度、运行时成本、验证可行性和维护负担进行评分。 |
| 运行时边界 | 重型模型包、GPU、检查点、机器人技术栈、托管仪表盘和持久化存储均作为可选项由宿主方自行管理。 |
| 机器人案例展示 | Textual 界面仅用于预制宿主机器人 policy+score 案例；运维工作流保持 CLI 优先。 |
| 宿主应用 | 参考宿主展示了如何在批处理任务、服务及机器人操作员工作流中集成 WorldForge，而不重新定义基础包边界。 |
| 运维 | 提供方调用产生脱敏事件、可选链路/指标/日志文件、运行清单、就绪状态及故障手册。 |
| 发布证据 | 发布包含可复现的本地门禁，以及明确的可选提供方证据或跳过原因。 |

不可妥协的质量标准：

- 提供方不因其名称出现在目录中而被视为"真实"。仅当宿主方能够安装上游运行时或配置上游 API、运行已记录的冒烟命令并检查保留的证据时，该提供方才算真实。
- 运行框架功能不因能渲染界面而被视为生产就绪。仅当其能保留状态、处理取消/失败、导出安全工件且无需实时凭证即可测试时，才算生产就绪。
- 可观测性功能若泄漏提示词、凭证、签名 URL 查询字符串、原始张量、无界标签或机器人特定密钥，则不能被视为生产就绪。

## 当前基线

| 领域 | 当前状态 | 约束 |
| --- | --- | --- |
| 基础包 | `httpx` 运行时依赖，仅支持 Python 3.13，使用 hatchling/uv 打包 | 保持提供方和宿主的附加依赖为可选项。 |
| 提供方目录 | `mock`、`cosmos-policy`、`leworldmodel`、`gr00t`、`lerobot`、实验性的仅打分 `jepa`，以及 `genie` 脚手架 | 不得将脚手架提供方声明为真实集成。 |
| 候选提供方 | `jepa-wms` 直接构造打分候选，未导出也未自动注册 | 仅在真实上游限制和运行时行为经过验证后才进行晋升。 |
| 规划 | `World.plan(...)` 组合 `predict`、`score`、`policy` 及 `policy+score` 流程 | 除非提供方直接实现了规划，否则不将 `plan` 视为提供方徽章。 |
| 运行框架 | 面向机器人 showcase 报告的可选 Textual 应用 | Textual 保持隔离在 `worldforge.harness.tui` 中。 |
| 可观测性 | `ProviderEvent`、`JsonLoggerSink`、`InMemoryRecorderSink`、`ProviderMetricsSink`、处理器扇出 | 宿主方自行管理完整的遥测导出和告警，除非添加了可选集成。 |
| 持久化 | 经验证的单写者本地 JSON 状态及报告工件 | 在独立的适配器设计落地之前，持久化多写者存储仍属于宿主方的关切。 |

## 目标架构

路线图应保持以下依赖方向：

```text
宿主应用 / CLI / 运行框架
  -> WorldForge 门面
  -> 提供方注册表 + 能力注册表
  -> 提供方适配器或协议实现
  -> 上游运行时/API/检查点
```

禁止反向依赖：提供方适配器不得导入宿主应用，基础包不得在模块导入时引入可选的机器人/模型运行时，遥测导出器不得拥有提供方行为。

目标模块边界：

| 边界 | 所有权 | 禁止持有 |
| --- | --- | --- |
| `worldforge.models` | JSON 原生公共契约、验证、公共错误 | 上游包类型、宿主遥测客户端 |
| `worldforge.providers.*` | 适配器配置、能力方法、上游解析、提供方事件 | 持久化存储、仪表盘、机器人控制器安全策略 |
| `worldforge.testing` | 可复用的能力合规性帮助工具及故障断言 | 实时凭证、默认情况下的网络调用 |
| `worldforge.benchmark` / `worldforge.evaluation` | 确定性契约信号、保留报告、预算门禁 | 无外部证据的真实物理保真度声明 |
| `worldforge.harness.models` / `flows` | 不依赖 Textual 的结构化运行和报告 | TUI 组件、可选模型包 |
| `worldforge.harness.tui` | 基于公共 API 和结构化运行数据的 Textual 界面 | 提供方特定的业务逻辑 |
| `examples/hosts/*` | 可选宿主集成模式 | 新增必需基础依赖 |

真实提供方运行的核心数据流：

```text
输入夹具或宿主载荷
  -> 能力专属验证
  -> 提供方运行时调用
  -> 类型化结果验证
  -> 脱敏的 ProviderEvent 流
  -> run_manifest.json
  -> 运行框架/报告/导出界面
```

每个 Issue 都应说明其变更的是数据流的哪个环节。

## 里程碑序列

| 里程碑 | 目标 | 退出信号 |
| --- | --- | --- |
| M0：Issue 就绪契约 | 将本路线图转化为带有依赖关系和负责人的带标签 GitHub Issue | Issue 包含验收标准和验证命令。 |
| M1：提供方基础设施 | 共享提供方晋升门禁、运行时清单、合规性测试及实时冒烟规范 | 新提供方无需为每个适配器单独发明流程即可添加。 |
| M2：真实提供方晋升 | 晋升现有最高价值的适配器，仅在真实运行时契约存在时替换脚手架占位 | 提供方文档/目录与可执行行为及实时冒烟工件一致。 |
| M3：运维证据 | 将运行检查、对比、导出和恢复保持为 CLI 优先工作流 | 运维人员可以在本地检查、对比、导出和恢复流程。 |
| M4：参考宿主应用 | 提供可选宿主应用，展示如何在服务、批处理任务和机器人实验室中集成 WorldForge | 宿主方获得可运行的模板，无需改变基础包。 |
| M5：可观测性与运维 | 添加可选遥测导出器、服务探针、运行清单、脱敏门禁及故障手册 | 生产宿主可集成标准监控，同时不泄露密钥。 |
| M6：发布加固 | 使实时提供方发布可复现、可审计且范围明确 | 发布门禁包含文档、包契约、覆盖率、提供方契约检查及可选冒烟证据。 |

## 依赖图

分配 Issue 时使用此图。同一行中的工作通常可在满足其依赖条件后并行推进。

| 波次 | 依赖 | Issue | 此顺序的原因 |
| --- | --- | --- | --- |
| 0 | 无 | WF-PROV-001, WF-PROVIDER-SELECT-001 | 锁定提供方标准，避免添加低价值适配器工作。 |
| 1 | WF-PROV-001 | WF-PROV-002, WF-PROV-003 | 运行时清单和合规性检查是真实提供方的可复用基础设施。 |
| 2 | WF-PROV-002, WF-PROV-003 | WF-PROV-004, WF-PROV-005 | 实时冒烟和标记需要清单及契约帮助工具。 |
| 3 | 第 2 波 | WF-LWM-001, WF-LEROBOT-001, WF-COSMOS-001 | 在扩展目录之前，先晋升现有的高价值真实路径。 |
| 4 | WF-LEROBOT-001 | WF-LEROBOT-002, WF-GROOT-001 | 机器人策略工作在进入正式宿主工作流之前需要转换器契约。 |
| 5 | WF-PROV-004 | WF-HARNESS-001, WF-OBS-001 | 运行和事件需要共享的工件/关联模型。 |
| 6 | WF-HARNESS-001, WF-OBS-001 | WF-HARNESS-002 至 WF-HARNESS-005, WF-OBS-002 至 WF-OBS-005 | UI、导出、链路、日志和就绪状态应共享运行 ID 和事件语义。 |
| 7 | 第 3-6 波 | WF-HOST-001, WF-HOST-002, WF-HOST-003, WF-OPS-004 | 宿主应用和发布证据在提供方/运行/可观测性契约完备后才有意义。 |
| 仅设计 | 不定 | WF-OPS-003, WF-JEPA-001, WF-GENIE-001 | 在设计或上游运行时契约可信之前不实现。 |

## Issue 模板

从以下各节创建 Issue 时，使用此格式：

```text
Title:
Type:
Labels:
Depends on:

Problem:

Scope:
- In:
- Out:

Implementation notes:

Acceptance criteria:
- [ ]
- [ ]
- [ ]

Validation:
- command:
- expected signal:

Docs:
- pages to update:
```

提供方 Issue 还应填写现有提供方适配器模板字段：提供方/运行时、已实现能力、运行时所有权、验证计划及故障模式。

## Issue 规模规则

当 Issue 跨越以下任一边界时，将其拆分：

- 添加或变更了超过一项提供方能力。
- 同时变更了提供方运行时代码和宿主应用代码。
- 添加了可选依赖并变更了基础包行为。
- 在同一大型补丁中变更了公共 API 契约和文档。
- 需要实时凭证或 GPU 验证，同时也需要确定性检出验证。
- 同时涉及持久化设计和本地 JSON 行为。

首选 Issue 规模：

| 规模 | 形态 | 预期验证 |
| --- | --- | --- |
| 小 | 单个解析器、单个验证器、单个文档修复、单个夹具族 | 针对性 pytest，若涉及公共内容则补充文档 |
| 中 | 单项能力契约、单个提供方加固切片、单个运行框架界面 | 针对性 pytest、文档，若面向提供方则包含生成的目录 |
| 大 | 提供方晋升、运行工作区、事件模式、宿主应用 | 拆分为实现 Issue 加一个追踪 Issue |

每个 Issue 都应包含"超出范围"部分。最常见的超出范围项包括：基础依赖扩展、真实机器人执行、持久化存储以及需要凭证的默认 CI 任务。

## 提供方优先级评分标准

在实现前对每个新提供方提案进行评分。使用总分来排列 Issue 优先级，而非覆盖安全门禁。

| 标准 | 0 | 1 | 2 |
| --- | --- | --- | --- |
| 用户价值 | 小众或不明确的工作流 | 对现有某个工作流有用 | 解锁常见提供方、模型族或机器人工作流 |
| 能力清晰度 | 无稳定可调用面 | 可调用面存在但映射不畅 | 清晰映射到 WorldForge 的某一项能力 |
| 上游成熟度 | 未发布或不稳定 | 可用但文档/API 仍在变动 | 稳定的 API/包/检查点路径 |
| 运行时可行性 | 需要不可用的硬件或复杂的搭建过程 | 仅限预备宿主，依赖关系明确 | 可本地运行或通过可达的托管 API 运行 |
| 夹具策略 | 无可夹具化的契约 | 部分夹具覆盖 | 成功和失败夹具均覆盖边界 |
| 冒烟可行性 | 无冒烟路径 | 仅手动冒烟 | 有记录的冒烟命令及保留清单 |
| 维护负担 | 高度变动或许可证不明 | 中度变动 | 低变动且许可证/所有权清晰 |
| 安全/密钥风险 | 高风险且无缓解措施 | 可通过脱敏/测试管控 | 低风险或已被事件脱敏覆盖 |

评分解读：

- `12-16`：纳入下一批实现候选。
- `8-11`：撰写 RFC 或仅保留为实验性/直接构造。
- `<8`：推迟。不要增加目录噪音。

当前高优先级候选：

| 候选 | 原因 | 首个 Issue |
| --- | --- | --- |
| LeWorldModel score | 现有真实打分路径，具有机器人案例展示价值 | WF-LWM-001 |
| LeRobot policy | 现有真实策略路径，具有 policy+score 规划价值 | WF-LEROBOT-001 |
| Cosmos-Policy 策略 | 预制宿主策略适配器，存在解析器、转换器和 `/act` 运行时问题 | WF-COSMOS-001 |
| GR00T PolicyClient | 有价值的机器人策略路径，但预备宿主复杂度较高 | WF-GROOT-001 |
| JEPA-WMS | 研究价值打分候选，但应保持直接构造直至上游限制明确 | WF-JEPAWMS-001 |

下一批扩展记录在[下一提供方选型 RFC](./provider-selection-rfc.md) 中。在选定的实现 Issue 开始前，不得更改提供方 README/目录措辞。

## 提供方晋升矩阵

在变更 `implementation_status` 前，使用此矩阵。

| 状态 | 允许的公开声明 | 所需证据 | 禁止事项 |
| --- | --- | --- | --- |
| `scaffold` | 保留名称、计划中的契约，无可执行公共能力 | 文档声明其尚不真实；方法默认关闭或仅供测试 | 声称已集成、自动注册为可用、声明能力标志 |
| `experimental` | 真实路径存在，契约可能变更 | 注入运行时测试、故障文档、可选冒烟命令或已记录的阻塞原因 | 将输出视为稳定、隐藏缺失的运行时限制 |
| `beta` | 经记录限制后可供预备宿主使用 | 合规性帮助工具覆盖、运行时清单、实时冒烟清单、生成的提供方文档 | 扩展基础依赖、未记录的环境变量或故障模式 |
| `stable` | 推荐的该能力提供方路径 | 反复的冒烟证据、发布证据、解析器/验证覆盖、故障手册、兼容性策略 | 未固定的上游假设、无界的元数据/日志字段 |

晋升阻断项：

- 提供方在没有未记录凭证或本地文件的情况下无法运行。
- 返回的元数据不是 JSON 原生格式。
- 打分方向或候选候选动作的基数不明确。
- 策略输出无法在不做隐含假设的情况下转换为可执行的 `Action` 值。
- 健康检查无法区分配置缺失、依赖缺失和上游故障。
- 提供方事件可能泄露密钥或签名 URL 查询字符串。

## 工件契约

这些格式有意保持精简。具体模式可后续实现，但 Issue 应保留以下字段，除非有经过审查的更优设计。

### 运行时清单

```json
{
  "manifest_version": 1,
  "provider": "leworldmodel",
  "capabilities": ["score"],
  "runtime": {
    "kind": "local-python",
    "optional_packages": ["stable-worldmodel", "torch"],
    "python": ">=3.13,<3.14",
    "devices": ["cpu", "cuda"]
  },
  "configuration": {
    "required_env": ["LEWORLDMODEL_POLICY"],
    "optional_env": ["LEWORLDMODEL_CACHE_DIR", "LEWORLDMODEL_DEVICE"]
  },
  "artifacts": {
    "checkpoint": "host-owned",
    "datasets": "host-owned"
  },
  "smoke": {
    "command": "scripts/lewm-real --checkpoint ~/.stable-wm/pusht/lewm_object.ckpt --device cpu --json",
    "success_signal": "JSON summary with provider=leworldmodel and capability=score"
  }
}
```

### 运行清单

```json
{
  "manifest_version": 1,
  "run_id": "20260430T120000Z-leworldmodel-score",
  "worldforge_version": "0.5.0",
  "command": ["scripts/lewm-real", "--device", "cpu", "--json"],
  "provider": "leworldmodel",
  "capability": "score",
  "runtime_manifest": "leworldmodel",
  "status": "passed",
  "input_digest": "sha256:<hex>",
  "result_digest": "sha256:<hex>",
  "event_count": 3,
  "artifacts": [
    {"kind": "json", "path": "summary.json", "safe_to_attach": true}
  ],
  "skip_reason": null
}
```

### 提供方事件关联

提供方事件应可与运行工件关联，同时不暴露敏感载荷：

```json
{
  "provider": "cosmos-policy",
  "operation": "policy",
  "phase": "success",
  "attempt": 1,
  "max_attempts": 1,
  "duration_ms": 1200.0,
  "run_id": "20260430T120000Z-cosmos-policy",
  "request_id": "host-request-id",
  "target": "https://api.example.test/v1/tasks",
  "metadata": {
    "artifact_id": "artifact-local-id",
    "input_digest": "sha256:<hex>"
  }
}
```

`metadata` 必须保持 JSON 原生格式并经过脱敏处理。不得存储原始提示词、原始张量、Bearer 令牌、签名 URL 查询字符串、机器人序列号或宿主特定路径，除非宿主方明确将其标记为仅限本地使用。

## 工作流 A：提供方平台基础设施

追踪状态：[#47](https://github.com/AbdelStark/worldforge/issues/47) 已完成。

完成信号：

- [提供方编写指南](./provider-authoring-guide.md)中，提供方晋升规则已覆盖 `scaffold`、`experimental`、`beta` 和 `stable`，包括配置文件元数据、生成的目录更新、验证命令及当前提供方分类表。
- 运行时清单已打包至 `src/worldforge/providers/runtime_manifests/`，经测试验证，从提供方文档链接，并在不安装可选运行时的情况下用于健康/配置摘要。
- 能力合规性帮助工具已覆盖 `predict`、`embed`、`score` 和 `policy`，以及用于安全夹具和注入运行时覆盖的提供方事件脱敏检查。
- 可选实时冒烟命令可写入脱敏的 `run_manifest.json` 证据，包含命令、包版本、提供方配置文件、能力、运行时清单、输入摘要、事件数量、结果摘要及工件路径摘要。
- 运行时 pytest 配置文件使默认检出验证保持确定性，同时预备宿主可以选择加入 `live`、`network`、`credentialed`、`gpu`、`robotics` 及特定提供方的测试运行。

### WF-PROV-001：提供方晋升门禁

类型：提供方平台  
标签：`provider`、`quality`、`documentation`  
依赖：无

问题：提供方成熟度可通过配置文件查看，但目前没有明确的晋升检查清单用于从 `scaffold` 升级到 `experimental`、`beta` 或 `stable`。

范围：

- 定义每个状态所需的证据：上游契约、运行时可用性、夹具、实时冒烟、文档、故障模式及基准测试输入。
- 在提供方编写指南或专用提供方治理页面中添加提供方晋升检查清单。
- 要求按状态措辞文档。示例：`stable` 可记录预期操作员使用方式；`experimental` 必须记录已知差距；`scaffold` 必须声明无可执行能力。

验收标准：

- [x] 晋升规则覆盖所有当前状态：`scaffold`、`experimental`、`beta`、`stable`。
- [x] 规则说明何时更改提供方配置文件元数据和生成的目录文档。
- [x] 规则包含确切的本地验证命令。
- [x] 现有提供方按新检查清单分类，不改变行为。

验证：

```bash
uv run python scripts/generate_provider_docs.py --check
uv run mkdocs build --strict
uv run pytest tests/test_provider_catalog_docs.py
```

### WF-PROV-002：提供方运行时清单模式

类型：提供方平台  
标签：`provider`、`operations`、`documentation`  
依赖：WF-PROV-001

问题：可选运行时文档分散在提供方页面、脚本和运维文档中。真实提供方工作需要机器可读的清单来描述运行时要求和冒烟证据。

范围：

- 为每个真实提供方运行时引入小型 JSON 或 TOML 清单模式。
- 捕获可选包、环境变量、默认模型/检查点、设备支持、由宿主方持有的工件、最小冒烟命令及预期成功信号。
- 将清单保存在仓库中，无依赖项。
- 不在基础包中从清单自动安装大型运行时。

验收标准：

- [x] 清单模式已记录并经测试验证。
- [x] `leworldmodel`、`lerobot`、`gr00t` 和 `cosmos-policy` 均有清单。
- [x] 缺少可选依赖时，使用清单数据生成可操作的健康提示信息。
- [x] 文档从提供方页面链接到相关清单。

验证：

```bash
uv run pytest tests/test_provider_runtime_manifests.py
uv run mkdocs build --strict
```

### WF-PROV-003：提供方合规性套件 v2

类型：提供方平台  
标签：`provider`、`testing`、`quality`  
依赖：WF-PROV-001

问题：契约帮助工具已存在，但真实提供方需要能力专属合规性套件，可复用于确定性模拟、注入运行时、HTTP 夹具及实时冒烟。

范围：

- 将 `src/worldforge/testing/` 扩展为 `score`、`policy`、`predict` 和 `embed` 的能力专属检查。
- 验证有限数值输出、JSON 原生元数据、脱敏事件、故障类型、健康行为及文档/配置文件一致性。
- 保持帮助工具的明确性；它们应抛出有意义的 `AssertionError` 消息。

验收标准：

- [x] 每项能力均有可复用的合规性帮助工具。
- [x] 当前提供方测试在适用处调用帮助工具。
- [x] 帮助工具可在无凭证的情况下针对注入运行时运行。
- [x] 帮助工具不使用裸 Python `assert` 语句。

验证：

```bash
uv run pytest tests/test_*provider*.py tests/test_observability.py
uv run --extra harness pytest --cov=src/worldforge --cov-report=term-missing --cov-fail-under=90
```

### WF-PROV-004：实时冒烟工件契约

类型：提供方平台  
标签：`provider`、`operations`、`benchmark`  
依赖：WF-PROV-002

问题：实时提供方运行仅在保留了命令、环境摘要、输入载荷、提供方配置文件、事件流、输出摘要及工件路径时才有意义。

范围：

- 为可选实时冒烟定义 `run_manifest.json` 格式。
- 包含命令参数、包版本、提供方配置文件、能力、脱敏环境摘要、运行时清单 ID、输入夹具摘要、事件数量、结果摘要及工件路径。
- 从可选冒烟命令和机器人案例展示路径写入清单。
- 不将凭证值和签名 URL 查询字符串写入清单。

验收标准：

- [x] 实时冒烟命令可写出 `run_manifest.json`。
- [x] 清单验证会拒绝类似密钥的元数据。
- [x] 机器人案例展示清单链接策略、打分、回放及报告工件。
- [x] 文档说明哪些工件可安全附加到 GitHub Issue。

验证：

```bash
uv run pytest tests/test_smoke_run_manifest.py tests/test_observability.py
uv run mkdocs build --strict
```

### WF-PROV-005：可选运行时测试配置文件

类型：提供方平台  
标签：`provider`、`ci`、`testing`  
依赖：WF-PROV-002, WF-PROV-004

问题：CI 应保持检出测试的确定性，同时使实时提供方验证在预备宿主上可重复执行。

范围：

- 为 `live`、`gpu`、`network`、`robotics` 和 `credentialed` 测试添加 pytest 标记及文档化命令。
- 保持默认 `uv run pytest` 不依赖实时运行时。
- 为预备宿主提供每次运行一个提供方配置文件的本地命令。
- 除非凭证和计费策略明确，否则不将实时提供方任务添加到默认 CI。

验收标准：

- [x] 实时测试在运行时/环境缺失时以清晰的原因跳过。
- [x] 每个真实提供方的预备宿主命令均已记录。
- [x] 默认 CI 保持确定性，不需要凭证、网络调用、GPU 或下载的检查点。
- [x] 实时冒烟证据可附加到发布说明或提供方 Issue。

验证：

```bash
uv run pytest
uv run pytest -m "not live"
uv run mkdocs build --strict
```

## 工作流 B：真实提供方实现

追踪状态：[#48](https://github.com/AbdelStark/worldforge/issues/48) 已完成。

完成信号：

- `leworldmodel` 是基于 `stable_worldmodel.policy.AutoCostModel` 的稳定打分提供方，具备 CPU 回退、打分方向元数据、运行时清单、真实检查点冒烟命令，以及在运行清单中保留形状摘要的 PushT 桥接注册表。
- `lerobot` 是稳定的策略提供方，具备明确的加载器验证、有界原始动作预览、转换器契约证据，以及由宿主方持有的检查点、运行时和控制器边界。
- `gr00t` 是 beta 阶段的远程 PolicyClient 提供方，具备脱敏目标元数据、超时/认证处理、服务不可达健康信号，且文档将 CUDA、TensorRT、Isaac-GR00T 和策略服务器运维保持为宿主方职责。
- `cosmos-policy` 通过解析器夹具、重试/超时事件元数据、可选实时冒烟清单和动作转换指导，保持具身策略回放的生产形态，并将秘密或宿主本地材料排除在可观测记录之外。
- `jepa` 现在仅通过 `facebookresearch/jepa-wms` torch-hub 契约声明选定的实验性 `score` 接口，而 `jepa-wms` 保持为直接构造候选，提供预备宿主冒烟证据，而非自动注册。
- `genie` 保持为默认关闭的脚手架，直到存在可信的上游自动化 API 或运行时契约才有记录的延迟决策。
- [提供方文档](./providers/README.md)、[提供方选型记录](./provider-selection-rfc.md)、[机器人案例展示文档](./robotics-showcase.md)、运行时清单、夹具及合规性测试现已就哪些提供方能力可执行、哪些运行时职责由宿主方承担达成一致。

### WF-LWM-001：LeWorldModel 稳定打分提供方

类型：提供方晋升  
标签：`provider`、`score`、`robotics`  
依赖：WF-PROV-001, WF-PROV-002, WF-PROV-003

问题：`leworldmodel` 已封装了真实的 `stable_worldmodel.policy.AutoCostModel` 路径，但稳定晋升需要更强的运行时矩阵、工件契约和任务桥接证据。

范围：

- 在文档和运行时清单中固定确切的上游导入边界。
- 验证检查点加载、CPU 回退、打分张量形状、候选候选动作基数、有限代价、打分方向及格式错误输出错误。
- 为检出 CI 保留小型确定性注入运行时测试路径。
- 为至少一个真实检查点路径添加预备宿主冒烟证据。

验收标准：

- [ ] `ProviderProfile` 状态和提供方文档反映晋升决策。
- [ ] 真实检查点冒烟写入包含打分载荷摘要和事件流的清单。
- [ ] 故障文档覆盖：包缺失、检查点缺失、张量形状错误、打分非有限、候选数量不匹配及设备回退。
- [ ] 不向基础包添加 LeWorldModel 运行时依赖。

验证：

```bash
uv run pytest tests/test_leworldmodel_provider.py tests/test_provider_contracts.py
uv run python scripts/generate_provider_docs.py --check
uv run mkdocs build --strict
```

预备宿主冒烟：

```bash
scripts/lewm-real --checkpoint ~/.stable-wm/pusht/lewm_object.ckpt --device cpu --json
```

### WF-LWM-002：LeWorldModel 任务桥接包

类型：提供方扩展  
标签：`provider`、`score`、`examples`  
依赖：WF-LWM-001, WF-PROV-004

问题：LeWorldModel 打分依赖任务原生张量预处理。WorldForge 应提供清晰的桥接示例，而不假装能推断每种任务表示。

范围：

- 保持 PushT 作为第一个完整桥接。
- 为示例和冒烟命令添加桥接注册表模式。
- 记录所需张量、形状及任务所有权。
- 添加至少一个负面测试，证明动作空间不匹配时会报错而非静默填充或投影。

验收标准：

- [ ] 桥接文档区分 WorldForge 验证与宿主预处理。
- [ ] 桥接代码将形状摘要写入运行清单。
- [ ] 动作维度不匹配在规划前报错。
- [ ] 现有机器人案例展示继续使用相同的公共提供方接口。

验证：

```bash
uv run pytest tests/test_robotics_showcase.py tests/test_leworldmodel_provider.py
uv run mkdocs build --strict
```

### WF-LEROBOT-001：LeRobot 稳定策略提供方

类型：提供方晋升  
标签：`provider`、`policy`、`robotics`  
依赖：WF-PROV-001, WF-PROV-002, WF-PROV-003

问题：`lerobot` 已暴露了真实策略适配器，但生产使用需要更强的加载器契约、动作输出规范化、转换器文档及预备宿主冒烟证据。

范围：

- 验证支持的策略加载模式和默认设备行为。
- 将原始策略输出规范化为 JSON 原生预览，同时不丢失形状/类型证据。
- 将可执行的 WorldForge `Action` 创建保留在宿主提供的明确转换器之后。
- 为包缺失、检查点缺失、不支持的策略类型及转换器缺失添加健康行为。

验收标准：

- [ ] 仅当所有晋升门禁通过后才更新提供方状态。
- [ ] 提供方文档说明支持的加载器路径和不支持的情况。
- [ ] 原始策略动作预览对日志和报告安全。
- [ ] 不向基础包添加 LeRobot、torch、机器人检查点或仿真包。

验证：

```bash
uv run pytest tests/test_lerobot_provider.py tests/test_provider_contracts.py
uv run python scripts/generate_provider_docs.py --check
uv run mkdocs build --strict
```

预备宿主冒烟：

```bash
scripts/smoke_lerobot_policy.py --help
```

### WF-LEROBOT-002：具身转换器契约

类型：提供方基础设施  
标签：`provider`、`policy`、`robotics`、`testing`  
依赖：WF-LEROBOT-001

问题：策略提供方返回具身专属动作。转换器需要正式契约，以便宿主应用能证明原始策略输出已安全地转换为可执行的 WorldForge 动作。

范围：

- 定义转换器的输入/输出形状、元数据、故障行为及来源字段。
- 为转换器基数、有限值、JSON 原生元数据及可逆预览摘要添加可复用测试。
- 记录转换器如何映射到真实机器人控制器，同时 WorldForge 不拥有硬件安全责任。

验收标准：

- [ ] 转换器对未知具身标签和形状不匹配大声报错。
- [ ] 策略提供方文档引用转换器契约。
- [ ] 机器人案例展示使用该契约而不改变公共行为。
- [ ] 由宿主方持有的安全联锁保持在 WorldForge 核心之外。

验证：

```bash
uv run pytest tests/test_lerobot_provider.py tests/test_robotics_showcase.py
uv run mkdocs build --strict
```

### WF-GROOT-001：GR00T PolicyClient Beta 提供方

类型：提供方晋升  
标签：`provider`、`policy`、`robotics`、`operations`  
依赖：WF-PROV-001, WF-PROV-002, WF-LEROBOT-002

问题：`gr00t` 处于实验阶段。Beta 晋升需要针对远程 PolicyClient 操作、认证、超时行为、动作预览及故障排查的预备宿主方案。

范围：

- 记录支持的远程 PolicyClient 配置及不支持的本地服务器假设。
- 验证严格与非严格模式、超时设置、认证令牌处理、观测验证、转换器缺失及服务不可达错误。
- 为连接到现有策略服务器提供预备宿主冒烟说明。
- 保持 CUDA、TensorRT、Isaac-GR00T 及机器人依赖由宿主方持有。

验收标准：

- [ ] 健康检查区分配置缺失、依赖缺失和策略服务器不可达。
- [ ] 提供方事件包含操作、尝试次数、脱敏目标及耗时。
- [ ] 类令牌值不得出现在事件或运行清单中。
- [ ] 文档声明不支持的宿主应连接远程服务器，而非自行启动。

验证：

```bash
uv run pytest tests/test_gr00t_provider.py tests/test_observability.py
uv run python scripts/generate_provider_docs.py --check
uv run mkdocs build --strict
```

预备宿主冒烟：

```bash
GROOT_POLICY_HOST=<host> uv run python scripts/smoke_gr00t_policy.py --policy-info-json policy.json
```

### WF-COSMOS-001：Cosmos-Policy 提供方生产加固

类型：提供方晋升
标签：`provider`、`operations`
依赖：WF-PROV-003, WF-PROV-004

问题：`cosmos-policy` 是预制宿主 HTTP 策略适配器。生产加固应锁定 `/act` 请求/响应验证、转换器边界、重试策略、运行证据以及围绕可达部署的文档。

范围：

- 对照当前支持的 Cosmos-Policy `/act` 形态，审计请求/响应解析器覆盖情况。
- 保留成功、格式错误载荷、认证失败、超时、错误动作形状及缺失转换器的夹具覆盖。
- 为实时策略冒烟运行写入运行清单。
- 将端点所有权保持在宿主方。

验收标准：

- [ ] 提供方文档说明所需的端点/认证配置及首要排查步骤。
- [ ] 解析器测试覆盖每种已记录的故障模式。
- [ ] 重试和超时行为在提供方事件中可见。
- [ ] 实时冒烟可手动运行，不改变默认 CI。

验证：

```bash
uv run pytest tests/test_cosmos_policy_provider.py tests/test_cosmos_policy_smoke_script.py
uv run python scripts/generate_provider_docs.py --check
uv run mkdocs build --strict
```

### WF-JEPAWMS-001：JEPA-WMS 候选晋升

类型：提供方晋升
标签：`provider`、`score`、`research`
依赖：WF-PROV-001, WF-PROV-002, WF-PROV-003

问题：`jepa-wms` 是直接构造打分候选。在真实上游运行时限制、模型加载及打分语义经过验证之前，应保持未注册状态。

范围：

- 在预备宿主上验证选定的上游运行时路径、所需依赖、模型名称及设备行为。
- 定义确切的打分输入张量、候选动作候选形状、打分方向及不支持情况。
- 决定自动注册是否合适，还是直接构造仍是正确的边界。
- 保持 torch 和 JEPA-WMS 依赖由宿主方持有。

验收标准：

- [x] 未经真实运行时冒烟证据，不升级提供方状态。
- [x] 文档说明直接构造与自动注册的决策。
- [x] 夹具和注入运行时测试覆盖解析器和验证行为。
- [x] 预备宿主冒烟写入包含运行时版本和打分摘要的清单。

验证：

```bash
uv run pytest tests/test_jepa_wms_provider.py tests/test_provider_contracts.py
uv run mkdocs build --strict
```

### WF-JEPA-001：用真实适配器替换 JEPA 脚手架

类型：提供方实现  
标签：`provider`、`predict`、`score`、`research`  
依赖：WF-JEPAWMS-001 或独立的提供方选型 RFC

问题：目录中包含一个默认关闭的 `jepa` 占位。替换它需要选择真实的上游 JEPA 运行时和一个诚实的能力接口。

范围：

- 在实现前撰写简短的提供方选型 RFC。
- 选择第一个真实 JEPA 接口是 `score`、`predict` 还是 `embed`；默认不暴露全部三项。
- 仅当真实适配器具备测试、文档和实时冒烟证据时，才移除或重命名脚手架行为。
- 为配置了脚手架环境变量的用户保留迁移说明。

验收标准：

- [ ] 所选上游包/API/检查点已在文档中命名。
- [ ] 适配器仅声明已实现的能力。
- [ ] 仅脚手架的替代行为已移除或保留在明确隔离的测试路径后。
- [ ] 提供方目录不再暗示虚假的 JEPA 集成。

验证：

```bash
uv run pytest tests/test_jepa_provider.py tests/test_provider_catalog_docs.py
uv run python scripts/generate_provider_docs.py --check
uv run mkdocs build --strict
```

### WF-GENIE-001：仅在运行时契约存在后替换 Genie 脚手架

类型：提供方实现
标签：`provider`、`research`
依赖：WF-PROV-001

问题：`genie` 目前是默认关闭的占位。真实实现应等到存在具有稳定可调用行为和可接受宿主方依赖边界的具体上游运行时/API 后再进行。

范围：

- 在实现前创建提供方选型 RFC。
- 决定第一个接口是 `predict` 还是保持在当前提供方表面之外。
- 如果不存在可信的上游契约，保留脚手架占位。
- 不将确定性本地替代行为呈现为真实的 Genie 集成。

验收标准：

- [ ] Issue 以实现计划或明确的延迟决策关闭。
- [ ] 若已实现，提供方文档包含上游契约、限制、环境变量、工件及故障模式。
- [ ] 若延迟，文档清晰说明其保持脚手架状态的原因。

验证：

```bash
uv run pytest tests/test_remote_scaffold_providers.py
uv run mkdocs build --strict
```

### WF-PROVIDER-SELECT-001：下一提供方选型 RFC

类型：提供方规划  
标签：`provider`、`research`、`roadmap`  
依赖：WF-PROV-001

问题：在无真实集成的情况下添加更多提供方名称会产生噪音。下一批提供方应根据可调用接口、用户价值、运行时可行性和验证成本来选择。

范围：

- 评估候选类别：具身策略适配器、潜在打分/预测模型、仿真器桥接及与规划相关的物理世界模型运行时。
- 对每个候选，记录能力接口、包/API 成熟度、宿主依赖权重、冒烟可行性、许可证、夹具策略及预期用户。
- 为下一批实现最多选择三个提供方。

验收标准：

- [ ] RFC 推荐的提供方新增不超过三个。
- [ ] 每个推荐的提供方均有包含能力、负责人及验证路径的 Issue 概要。
- [ ] 延迟候选包含阻断原因。
- [ ] 在实现开始前不更改 README/提供方文档。

验证：

```bash
uv run mkdocs build --strict
```

## 工作流 C：生产级运行框架

运行框架工作应被视为产品工程，而非演示打磨。运行框架是基于 WorldForge API 的本地运维工作区的参考实现。

生产级运行框架要求：

| 要求 | 含义 |
| --- | --- |
| 确定性检出路径 | 每个新界面或流程都有基于 `mock` 或夹具的路径，无需凭证即可运行。 |
| 预备宿主路径 | 当可选运行时包、凭证和工件存在时，真实提供方流程可以运行。 |
| 持久化运行模型 | 运行存储在稳定的运行目录中，包含清单、事件、摘要和导出报告。 |
| 故障可见性 | 失败、取消、跳过、配置错误和不健康状态在视觉上有所区别且可导出。 |
| 安全导出 | 报告导出经过脱敏处理，适合附加到 GitHub Issue，除非标记为仅本地使用。 |
| 键盘优先操作 | 常见的提供方、运行、报告和世界操作可通过命令面板或快捷键访问。 |
| 无 Textual 导入泄漏的可测试性 | 流程逻辑在 `worldforge.harness.tui` 之外仍可测试。 |

运行框架反目标：

- 不将机器人案例展示 TUI 变成托管仪表盘。
- 不在隐式安装重型可选运行时的背后隐藏提供方设置。
- 不从默认运行框架流程执行机器人控制器动作。
- 不渲染包含原始密钥的提供方元数据。

追踪状态：[#49](https://github.com/AbdelStark/worldforge/issues/49) 已完成。

完成信号：

- 共享运行工作区使用 `.worldforge/runs/<run-id>/`，包含脱敏清单、提供方事件、结果摘要、报告导出、日志、可排序的文件安全运行 ID、保留命令及 Issue 安全工件路径。
- 提供方就绪状态通过 CLI 诊断暴露，区分已配置、缺少凭证、缺少可选依赖、不健康及脚手架状态，不打印密钥值。
- 实时运行检查保留 `results/inspector.json`、脱敏的 `logs/provider-events.jsonl`、失败运行清单、验证错误以及成功和失败流程的最终工件链接。
- 保留的评估和基准测试运行可使用 `worldforge runs compare` 进行对比，并可导出为 Markdown、JSON 或 CSV，附带来源引用。
- `worldforge provider workbench <provider>` 为适配器作者提供安全检出循环，用于能力合规性帮助工具、夹具验证、健康检查、文档/目录漂移及脱敏安全事件检查。
- CLI 文档描述匹配命令和工件布局，使运维行为无需导入 Textual 即可测试。

### WF-HARNESS-001：运行框架运行工作区

类型：运行框架  
标签：`harness`、`operations`、`artifacts`  
依赖：WF-PROV-004

问题：运行框架可以显示运行和报告，但生产级本地运维需要为输入、输出、清单、事件、日志和导出建立清晰的工作区模型。

范围：

- 为运行框架和 CLI 流程定义 `.worldforge/runs/<run-id>/` 布局。
- 存储脱敏运行清单、提供方事件、输入摘要、结果摘要、生成的报告及导出媒体路径。
- 添加保留和清理命令。
- 除非明确设计了持久化存储适配器，否则保持本地工作区单用户。

验收标准：

- [x] 运行框架和 CLI 流程写入相同的运行布局。
- [x] 运行 ID 文件安全且可排序。
- [x] 导出工件可附加到 Issue 而不泄露密钥。
- [x] 文档包含清理和恢复步骤。

验证：

```bash
uv run pytest tests/test_harness_flows.py tests/test_cli_reports.py
uv run --extra harness pytest tests/test_harness_tui.py
uv run mkdocs build --strict
```

### WF-HARNESS-002：提供方连接器工作区

类型：运行框架  
标签：`harness`、`provider`、`operations`  
依赖：WF-PROV-002, WF-HARNESS-001

问题：运维人员需要一种本地方式来检查提供方就绪状态、缺失的环境变量、可选运行时健康状况及首要冒烟命令，然后再运行工作流。

范围：

- 添加读取提供方配置文件和运行时清单的连接器界面或面板。
- 分别显示已配置、缺失、不健康和脚手架提供方。
- 显示确切的后续命令，不打印密钥。
- 支持可复制的冒烟命令和首要排查步骤。

验收标准：

- [x] `mock`、`cosmos-policy`、`leworldmodel`、`gr00t`、`lerobot`、实验性 `jepa` 及脚手架 `genie` 以不同状态渲染。
- [x] 凭证缺失和可选依赖缺失在视觉上有所区别。
- [x] Textual 保持隔离在 `worldforge.harness.tui` 中。
- [x] 非 TUI 元数据命令以 JSON 形式暴露相同的提供方就绪状态数据。

验证：

```bash
uv run pytest tests/test_harness_flows.py tests/test_harness_cli.py
uv run --extra harness pytest tests/test_harness_tui.py
```

### WF-HARNESS-003：实时运行检查器

类型：运行框架  
标签：`harness`、`observability`、`provider`  
依赖：WF-HARNESS-001, WF-OBS-001

问题：运维人员应能够在运行执行时观察提供方事件、计时、重试、失败、选定动作、打分及工件创建。

范围：

- 将脱敏提供方事件流式传输到运行检查器。
- 显示时间线、事件表、结果摘要、工件路径和验证错误。
- 对于底层操作可安全停止的长时间提供方调用，支持取消。
- 从同一运行清单持久化最终视图。

验收标准：

- [x] 成功、重试、失败和取消状态有所区别。
- [x] 提供方事件元数据在 TUI 和导出报告中均已脱敏。
- [x] 失败的运行仍写入足够的清单数据以重现命令。
- [x] 测试在无真实提供方凭证的情况下覆盖故障渲染。

验证：

```bash
uv run pytest tests/test_harness_flows.py tests/test_observability.py
uv run --extra harness pytest tests/test_harness_tui.py
```

### WF-HARNESS-004：报告对比与导出

类型：运行框架  
标签：`harness`、`benchmark`、`evaluation`  
依赖：WF-HARNESS-001

问题：提供方评估和基准测试工作需要跨保留运行的一等对比，而非仅一次性报告。

范围：

- 添加跨基准测试延迟/吞吐量、评估打分、提供方健康状况和事件计数的报告对比。
- 从保留的运行目录导出 Markdown、JSON 和 CSV 摘要。
- 包含指向输入夹具和预算文件的来源链接。
- 将基准测试声明与保留工件绑定。

验收标准：

- [x] 对比拒绝不兼容的报告类型，并给出清晰错误。
- [x] 导出的 Markdown 包含命令、提供方、操作、日期及工件引用。
- [x] CSV 和 JSON 导出足够稳定，可作为 Issue 附件。
- [x] 文档说明如何引用基准测试工件。

验证：

```bash
uv run pytest tests/test_benchmark.py tests/test_evaluation_suites.py tests/test_harness_flows.py
uv run mkdocs build --strict
```

### WF-HARNESS-005：提供方开发工作台

类型：运行框架  
标签：`harness`、`provider`、`developer-experience`  
依赖：WF-PROV-003, WF-HARNESS-002

问题：适配器作者在提交提供方 PR 之前，需要一个用于夹具回放、健康检查、能力测试、事件检查及文档漂移的紧凑循环。

范围：

- 添加针对选定提供方运行提供方合规性检查的工作台流程。
- 为 HTTP 适配器支持夹具回放，为本地适配器支持注入运行时。
- 当配置文件元数据更改时，显示缺失的文档/目录更新。
- 除非明确选择，否则不运行实时提供方调用。

验收标准：

- [x] 工作台可在干净检出中针对 `mock` 运行。
- [x] 工作台列出每项已声明能力所需的测试。
- [x] 工作台链接到提供方编写文档和生成的目录检查。
- [x] 失败信息足够可操作，可直接粘贴到 GitHub Issue。

验证：

```bash
uv run pytest tests/test_provider_contracts.py tests/test_harness_flows.py
uv run --extra harness pytest tests/test_harness_tui.py
```

## 工作流 D：参考宿主应用

参考宿主应用是所有权边界的示例。它们应完整到可以直接复制，但不应成为库的必需运行时路径。

追踪状态：[#50](https://github.com/AbdelStark/worldforge/issues/50) 已完成。

完成信号：

- `examples/hosts/batch-eval/` 运行干净检出的评估和基准测试任务，保留 `.worldforge/batch-eval/runs/<run-id>/` 工件、复制的基准测试输入和预算，以及预算违规时的非零退出码。
- `examples/hosts/service/` 暴露标准库 HTTP 存活性、就绪性、提供方诊断、类型化公共错误载荷、请求 ID 关联及 JSON 提供方事件日志，同时不将部署或告警移入 WorldForge。
- `examples/hosts/robotics-operator/` 默认保持操作员审查为非变更性，要求明确的动作转换器，记录批准/回放/证据工件，并将控制器执行保留在宿主提供的钩子之后。
- [示例文档](./examples.md) 将三种宿主应用均呈现为可选参考，并重申调度、持久化存储、遥测、凭证、控制器集成、联锁及安全认证的宿主方所有权边界。

宿主应用打包规则：

- 将参考宿主放在 `examples/hosts/<name>/` 下。
- 将宿主特定依赖保持在基础包之外。
- 仅当依赖集具有广泛用途时，才优先使用 `uv run --with ...` 说明或专用的可选附加依赖。
- 仅当 `.env.example` 片段不引入真实密钥时才包含。
- 每个宿主应用必须声明其是否适用于：干净检出、预备宿主、需凭证、GPU 受限或仅限机器人实验室。

宿主应用验收标准：

| 宿主类型 | 必须展示 | 不得暗示 |
| --- | --- | --- |
| 批量评估 | CLI/任务入口点、输入夹具、预算、运行工件、非零失败退出码 | 托管调度、长期存储、超出工件范围的经验性声明 |
| 服务 | 就绪性检查、类型化错误、请求 ID、日志/指标钩子、超时策略 | WorldForge 拥有正常运行时间、认证、路由或仪表盘 |
| 机器人操作员 | 试运行审查、策略/打分证据、动作转换器、批准记录 | 自动机器人安全、控制器所有权、认证执行 |

### WF-HOST-001：批量评估宿主

类型：宿主应用  
标签：`examples`、`evaluation`、`operations`  
依赖：WF-HARNESS-001, WF-PROV-004

问题：用户需要一个生产形态的示例，用于以批处理任务方式运行带有工件、预算和退出码的提供方评估和基准测试。

范围：

- 在 `examples/hosts/batch-eval/` 下添加可选示例宿主。
- 使用 WorldForge API、基准测试输入文件、预算文件、运行清单及报告导出。
- 通过 `uv run --with ...` 或已记录的附加依赖保持可选且可安装。
- 不向基础包添加调度器或队列。

验收标准：

- [x] 宿主可在干净检出中运行 `mock` 评估和基准测试任务。
- [x] 宿主写入运行工作区工件，并在预算违规时非零退出。
- [x] 文档说明如何在预备宿主上替换真实提供方。
- [x] 包契约保持基础依赖干净。

验证：

```bash
uv run pytest tests/test_batch_eval_host.py
bash scripts/test_package.sh
uv run mkdocs build --strict
```

### WF-HOST-002：服务宿主参考

类型：宿主应用  
标签：`examples`、`operations`、`observability`  
依赖：WF-OBS-001, WF-OBS-002, WF-OPS-002

问题：嵌入 WorldForge 的服务需要一个涵盖请求 ID、就绪性检查、提供方调用、结构化日志、指标导出、超时预算及干净失败响应的参考。

范围：

- 在 `examples/hosts/service/` 下添加可选服务宿主示例。
- 暴露健康/就绪性检查、提供方列表、一个安全的 mock 工作流及一个可配置的提供方工作流。
- 保持 Web 框架为可选项，不纳入基础包。
- 演示脱敏日志、请求 ID 及提供方事件关联。

验收标准：

- [x] 服务宿主仅使用可选示例依赖运行。
- [x] 健康/就绪性区分框架存活、提供方已配置和提供方健康。
- [x] 提供方错误返回类型化公共错误载荷，不含内部密钥。
- [x] 文档声明这是参考宿主，而非 WorldForge 的产品边界。

验证：

```bash
uv run pytest tests/test_service_host.py
uv run mkdocs build --strict
```

### WF-HOST-003：机器人实验室操作员宿主

类型：宿主应用  
标签：`examples`、`robotics`、`operations`、`safety`  
依赖：WF-LEROBOT-002, WF-GROOT-001, WF-HARNESS-003

问题：机器人用户需要一个示例，组合策略、打分、回放和操作员批准，同时不暗示 WorldForge 控制机器人硬件。

范围：

- 添加用于离线操作员审查 policy+score 运行的可选宿主示例。
- 在任何宿主方控制器集成点之前，要求明确的动作转换器、安全检查清单及试运行批准。
- 导出选定的动作块、打分依据、事件流及回放工件。
- 将真实机器人执行保留为带有记录安全所有权的集成钩子。

验收标准：

- [x] 默认模式为非变更性，不与机器人控制器通信。
- [x] 除非宿主方提供明确实现，否则控制器执行钩子禁用。
- [x] 操作员批准和试运行工件已记录。
- [x] 文档说明 WorldForge 认证和不认证的范围。

验证：

```bash
uv run pytest tests/test_robotics_operator_host.py tests/test_robotics_showcase.py
uv run mkdocs build --strict
```

## 工作流 E：可观测性、监控与日志

可观测性工作必须保持核心回调模型简洁，同时为生产宿主提供干净的集成点。

追踪状态：[#51](https://github.com/AbdelStark/worldforge/issues/51) 已完成。

完成信号：

- `ProviderEvent` 携带脱敏关联字段和规范化阶段，用于运行、请求、链路、跨度、工件及输入摘要关联。
- `JsonLoggerSink`、`RunJsonLogSink`、`ProviderMetricsSink`、`ProviderMetricsExporterSink`、`OpenTelemetryProviderEventSink` 和 `InMemoryRecorderSink` 共享相同的事件模型，且不添加基础运行时依赖。
- 运行日志和清单在 `.worldforge/runs/<run-id>/` 下保留 Issue 安全的提供方证据。
- 服务宿主将进程存活性与 `ready`、`provider_unconfigured` 和 `provider_unhealthy` 就绪状态分开暴露。
- 运维文档和手册将 `worldforge doctor`、提供方健康状况、提供方事件及故障手册映射到宿主方持有的升级路径。

遥测分层：

```text
ProviderEvent
  -> 进程内接收器
  -> 可选运行日志 / 运行清单
  -> 可选导出适配器
  -> 宿主收集器 / 仪表盘 / 告警
```

必需语义：

| 信号 | 来源 | 说明 |
| --- | --- | --- |
| 请求尝试 | 每次上游调用或模型边界调用的提供方事件 | 重试是尝试，而非独立的逻辑用户工作流。 |
| 重试 | `phase=retry` 的提供方事件 | 可用时包含尝试次数和脱敏目标。 |
| 故障 | `phase=failure` 的提供方事件加上类型化异常 | 保留错误类型，不含原始密钥载荷。 |
| 延迟 | 事件 `duration_ms` | 导出指标使用直方图；不从挂钟 UI 渲染时间计算。 |
| 运行状态 | 运行清单 | 值应包含 passed、failed、skipped、cancelled 和 not configured。 |
| 就绪性 | 宿主应用或 CLI 预检 | 区分已配置、依赖可用、上游可达及工作流就绪。 |

导出器规则：

- 导出器是现有事件之上的可选适配器；不得改变提供方执行。
- 指标标签必须有界。使用提供方、操作、能力、阶段和状态类别。
- 不得使用提示词、含查询字符串的目标 URL、世界 ID、运行 ID、对象 ID 或元数据键作为指标标签。
- 链路/跨度属性在导出前必须脱敏。
- 日志文件和 Issue 包默认应安全；仅本地工件需明确标记。

### WF-OBS-001：提供方事件模式 v2

类型：可观测性  
标签：`observability`、`provider`、`security`  
依赖：WF-PROV-004

问题：`ProviderEvent` 已很有用，但生产宿主需要稳定的关联字段、运行 ID、请求 ID、规范化阶段及更强的模式文档。

范围：

- 若能保持 JSON 原生且经过脱敏，可添加可选的 `run_id`、`request_id`、`trace_id`、`span_id`、`artifact_id` 和 `input_digest` 字段。
- 尽可能保持向后兼容性。
- 记录事件阶段和字段语义。
- 为新字段扩展脱敏测试。

验收标准：

- [x] 现有接收器继续工作或有记录的迁移行为。
- [x] 事件字段在接收器消费前为 JSON 原生且经过脱敏。
- [x] 提供方事件可与运行清单关联。
- [x] 文档包含 JSON 日志记录示例。

验证：

```bash
uv run pytest tests/test_observability.py tests/test_cosmos_policy_provider.py
uv run mkdocs build --strict
```

### WF-OBS-002：可选 OpenTelemetry 导出器

类型：可观测性  
标签：`observability`、`operations`、`optional-dependency`  
依赖：WF-OBS-001

问题：生产宿主通常使用 OpenTelemetry，但 WorldForge 不应将其强制纳入基础包。

范围：

- 添加可选导出器模块或附加依赖，将提供方事件映射到跨度和属性。
- 默认禁用导出器。
- 记录语义属性名称、脱敏保证及宿主方负责的收集器配置。
- 测试不应要求真实收集器。

验收标准：

- [x] 导入 `worldforge` 不导入 OpenTelemetry。
- [x] 导出器映射提供方、操作、阶段、状态、耗时、尝试次数及脱敏目标。
- [x] 类密钥元数据在创建跨度属性前已脱敏。
- [x] 文档展示最小宿主接线方式。

验证：

```bash
uv run pytest tests/test_observability_opentelemetry.py tests/test_observability.py
bash scripts/test_package.sh
uv run mkdocs build --strict
```

### WF-OBS-003：可选指标导出器

类型：可观测性  
标签：`observability`、`operations`、`optional-dependency`  
依赖：WF-OBS-001

问题：`ProviderMetricsSink` 在内存中聚合。宿主需要一个可选桥接到标准指标系统，同时不改变核心事件语义。

范围：

- 为计数器、直方图、重试、错误和延迟添加可选导出钩子。
- 保持标签基数有界：仅使用提供方、操作、阶段/状态类别和能力。
- 记录为何原始目标 URL、提示词、元数据键或世界 ID 不得作为指标标签。
- 使用内存注册表或模拟导出器提供测试。

验收标准：

- [x] 指标桥接为可选项且具有有界标签。
- [x] 重试事件独立递增重试指标，区别于逻辑操作计数。
- [x] 文档说明指标含义和告警示例。
- [x] 基础包依赖集保持不变。

验证：

```bash
uv run pytest tests/test_observability_metrics_export.py tests/test_observability.py
uv run mkdocs build --strict
```

### WF-OBS-004：日志配置与运行日志

类型：可观测性  
标签：`observability`、`operations`、`logging`  
依赖：WF-OBS-001, WF-HARNESS-001

问题：`JsonLoggerSink` 已存在，但宿主应用需要一个一致的文件日志、JSON 日志、运行范围日志及操作员安全日志导出配方。

范围：

- 为 CLI、批处理宿主、服务宿主和运行框架添加日志使用手册。
- 若能保持无依赖，提供运行范围 JSON 日志文件帮助工具。
- 包含导出日志文件的脱敏测试。
- 不全局覆盖宿主日志配置。

验收标准：

- [x] 日志可通过 `run_id` 与运行清单关联。
- [x] 导出日志不含 Bearer 令牌、API 密钥、签名或签名 URL 查询字符串。
- [x] 文档包含提供方故障和重试的首要排查查询。
- [x] 宿主应用演示注入日志记录器而非全局日志副作用。

验证：

```bash
uv run pytest tests/test_observability.py tests/test_run_logs.py
uv run mkdocs build --strict
```

### WF-OBS-005：健康状态、就绪性与故障手册

类型：运维  
标签：`operations`、`observability`、`documentation`  
依赖：WF-PROV-002, WF-HOST-002

问题：生产宿主需要清晰区分进程存活性、提供方已配置、提供方健康、上游降级和工作流失败。

范围：

- 为宿主应用记录标准的健康/就绪性模型。
- 添加暴露这些状态的参考宿主端点或命令。
- 为远程提供方故障、可选运行时依赖缺失、工件过期、世界状态格式错误及基准测试预算失败添加故障手册。
- 将值班路由和告警渠道保持为宿主方持有。

验收标准：

- [x] 故障手册包含症状、可能原因、首要命令、预期信号及升级点。
- [x] 宿主参考应用使用该模型。
- [x] 现有的 `worldforge doctor` 和提供方健康输出已映射到就绪状态。
- [x] 文档避免声称 WorldForge 拥有上游 SLA。

验证：

```bash
uv run pytest tests/test_service_host.py tests/test_cli.py
uv run mkdocs build --strict
```

## 工作流 F：可靠性、安全与发布门禁

可靠性工作应使故障明确且可诊断。不应通过无限重试、弱化验证或将宿主方职责移入框架来隐藏不稳定性。

可靠性策略：

| 领域 | 默认 | 例外路径 |
| --- | --- | --- |
| 远程创建/变更 | 单次尝试 | 仅在幂等性明确时，宿主方才可配置重试。 |
| 健康检查 | 廉价且有界 | 深度检查属于明确的冒烟命令。 |
| 下载 | 在配置时使用有界超时重试 | 在上游 URL 过期时立即持久化工件。 |
| 可选运行时导入 | 延迟且明确报错 | 永远不从 `worldforge.__init__` 导入可选模型包。 |
| 实时测试 | 选择性加入标记 | 默认 CI 保持确定性。 |
| 覆盖率门禁 | 保持当前门禁 | 为新分支添加针对性测试，而非降低阈值。 |

[#52](https://github.com/AbdelStark/worldforge/issues/52) 的完成信号：本工作流已作为基线可靠性、安全和发布基础设施实现。`WF-OPS-001` 添加了按操作的提供方预算和预算超限事件。`WF-OPS-002` 加固了凭证配置摘要及跨安全工件的脱敏预期。`WF-OPS-003` 在 ADR 0001 中记录了由宿主方持有的持久化适配器边界。`WF-OPS-004` 添加了发布证据包和发布门禁检查清单。未来工作应从范围明确的后续 Issue 开始，以变更特定提供方、宿主、工件或发布工作流。

### WF-OPS-001：提供方预算与熔断策略

类型：运维  
标签：`operations`、`provider`、`reliability`  
依赖：WF-OBS-001

问题：远程和实时模型调用需要超时、尝试次数、重试延迟、最大运行时长和故障阈值的明确预算。

范围：

- 在适当情况下扩展或记录 `ProviderRequestPolicy` 的工作流级预算。
- 添加由宿主方持有的熔断器示例，不强制引入服务依赖。
- 确保预算违规以类型化提供方/工作流错误和提供方事件的形式呈现。
- 保持创建/变更默认为单次尝试，除非明确配置。

验收标准：

- [ ] 预算可在宿主示例中按提供方操作设置。
- [ ] 预算失败可观测且可测试。
- [ ] 文档区分请求重试策略与工作流运行预算。
- [ ] 无静默重试循环可隐藏反复的提供方故障。

验证：

```bash
uv run pytest tests/test_provider_request_policy.py tests/test_cosmos_policy_provider.py
uv run mkdocs build --strict
```

### WF-OPS-002：凭证与配置加固

类型：安全  
标签：`security`、`operations`、`provider`  
依赖：WF-PROV-002

问题：真实提供方增加了通过配置、日志、清单、事件、文档或 Issue 附件泄露凭证的可能性。

范围：

- 审计每个提供方的环境变量加载和文档。
- 添加配置摘要，暴露存在性、来源和验证状态，不暴露值。
- 为事件、清单、日志、报告和文档示例中的密钥模式添加测试。
- 保持 `.env.example` 被追踪，`.env` 文件被忽略。

验收标准：

- [ ] 每个提供方均有记录的环境变量和脱敏配置摘要。
- [ ] 测试捕获新可观测面中的 Bearer/API/签名/密码类泄露。
- [ ] Issue 文档说明哪些工件可安全附加。
- [ ] 提供方错误不包含原始凭证或签名 URL 查询字符串。

验证：

```bash
uv run pytest tests/test_observability.py tests/test_provider_config.py tests/test_docs_site.py
uv run mkdocs build --strict
```

### WF-OPS-003：持久化适配器设计

类型：架构  
标签：`operations`、`persistence`、`design`  
依赖：WF-HOST-001

问题：本地 JSON 状态设计为单写者。部分宿主将需要持久化多写者存储，但在没有设计的情况下将其添加到核心会模糊 WorldForge 的边界。

范围：

- 在实现前为持久化适配器接口撰写 ADR。
- 定义锁定、迁移、备份/恢复、保留、模式版本控制及故障恢复。
- 决定第一个实现属于核心、可选附加依赖还是仅参考宿主应用。
- 保持当前本地 JSON 行为不变，除非 ADR 明确变更。

验收标准：

- [ ] ADR 说明适配器边界和已否决的替代方案。
- [ ] ADR 被接受前不添加数据库依赖。
- [ ] 现有本地 JSON 测试对默认行为仍具权威性。
- [ ] 宿主方职责在文档中保持清晰。

验证：

```bash
uv run pytest tests/test_persistence*.py tests/test_cli_worlds.py
uv run mkdocs build --strict
```

### WF-OPS-004：发布证据包

类型：发布  
标签：`release`、`quality`、`provider`、`documentation`  
依赖：WF-PROV-004, WF-HARNESS-004

问题：涉及大量提供方的发布需要证据包，说明本地测试了什么、运行了哪些实时冒烟、跳过了什么以及哪些声明得到了支持。

范围：

- 定义发布证据目录或生成的 Markdown 报告。
- 包含验证命令、覆盖率、文档构建、包契约、提供方目录漂移、基准测试工件、实时冒烟清单及已知限制。
- 保持实时提供方证据为可选但明确。

验收标准：

- [ ] 发布证据可在无凭证的情况下生成。
- [ ] 实时提供方部分标注为 skipped、passed、failed 或 not configured。
- [ ] 证据报告链接到保留的工件。
- [ ] 发布检查清单引用证据包。

验证：

```bash
uv lock --check
uv run ruff check src tests examples scripts
uv run ruff format --check src tests examples scripts
uv run python scripts/generate_provider_docs.py --check
uv run mkdocs build --strict
uv run pytest
uv run --extra harness pytest --cov=src/worldforge --cov-report=term-missing --cov-fail-under=90
bash scripts/test_package.sh
uv build --out-dir dist --clear --no-build-logs
```

## 风险登记册

在 Issue 和发布证据中跟踪这些风险。

| 风险 | 影响 | 早期预警 | 缓解措施 |
| --- | --- | --- | --- |
| 能力膨胀 | 用户信任提供方完成其无法完成的工作 | 提供方文档使用宽泛的模型标签而非确切能力名称 | 晋升门禁、生成的目录检查、合规性测试 |
| 基础依赖蔓延 | 包变得难以安装和测试 | 可选模型包出现在 `dependencies` 中 | 将模型/运行时包保持在包装器、附加依赖或宿主文档中 |
| 密钥泄露 | 日志、清单、报告或 Issue 暴露凭证 | 新事件元数据包含目标、请求头、环境变量或原始提供方消息 | 对每个可观测面进行脱敏测试 |
| 实时冒烟脆弱 | 提供方验证无法复现 | 冒烟命令依赖未记录的本地文件 | 运行时清单、预备宿主命令、跳过原因 |
| 运行框架沦为演示 | UI 看起来有用但无法支持真实排查 | 失败运行不保留工件 | 运行工作区、故障状态、导出测试 |
| 宿主边界漂移 | WorldForge 开始承担服务或机器人职责 | 文档承诺正常运行时间、控制器安全或持久化存储 | 宿主应用边界声明和实现前的 ADR |
| 基准测试滥用 | 确定性契约数字变成夸大声明 | 报告缺少输入来源或声明边界 | 基准测试输入夹具、预算、证据包 |
| 提供方 API 变动 | 外部提供方变更静默破坏适配器 | 夹具仅覆盖正常路径 | 解析器夹具、版本/运行时清单、实时冒烟清单 |
| 覆盖率下限侵蚀 | 新守卫分支静默降低质量 | 运行框架覆盖率徘徊在阈值附近 | 为每个提供方/运行框架分支添加针对性测试 |

## 实现波次

### 第 0 波：将路线图转化为追踪器

目标：创建 GitHub Issue 骨架。

开一个追踪 Issue 代表每个工作流，加上下方列出的前十个实现 Issue。每个追踪 Issue 应链接子 Issue、依赖顺序、标签及所需发布证据。

本波次验证：

```bash
uv run mkdocs build --strict
```

### 第 1 波：提供方标准先于提供方增长

目标：防止未来的提供方工作变得零散。

实现：

- WF-PROV-001：提供方晋升门禁
- WF-PROV-002：提供方运行时清单模式
- WF-PROV-003：提供方合规性套件 v2

退出标准：

- 新提供方 Issue 模板可引用晋升状态、运行时清单和合规性帮助工具预期。
- 现有提供方可按矩阵审计，不改变行为。
- 默认测试保持无凭证。

### 第 2 波：携带证据的实时冒烟

目标：使实时提供方验证可复现且可附加到 Issue。

实现：

- WF-PROV-004：实时冒烟工件契约
- WF-PROV-005：可选运行时测试配置文件
- WF-OBS-001：提供方事件模式 v2（若首先需要运行关联字段）

退出标准：

- 可选实时冒烟可写出 `run_manifest.json`。
- 运行时缺失、凭证缺失和不支持的宿主状态以清晰原因跳过。
- 脱敏证据可附加到 GitHub Issue。

### 第 3 波：晋升现有真实提供方

目标：在添加新提供方名称之前，使现有最强提供方接口可靠。

实现：

- WF-LWM-001：LeWorldModel 稳定打分提供方
- WF-LEROBOT-001：LeRobot 稳定策略提供方
- WF-COSMOS-001：Cosmos-Policy 提供方生产加固

退出标准：

- 提供方文档、生成的目录、合规性帮助工具和冒烟清单一致。
- 每项已声明能力均有基于夹具的故障测试。
- 无提供方晋升向基础依赖集添加重型运行时包。

### 第 4 波：机器人组合

目标：使 policy+score 工作流足够成熟，适用于由宿主方持有的机器人实验室。

实现：

- WF-LEROBOT-002：具身转换器契约
- WF-GROOT-001：GR00T PolicyClient Beta 提供方
- WF-LWM-002：LeWorldModel 任务桥接包
- WF-HOST-003：机器人实验室操作员宿主（仅在转换器和运行证据契约存在后）

退出标准：

- 策略原始动作、打分候选动作、转换后的 `Action` 值、选定计划及回放工件可通过一个运行清单追溯。
- 除非由宿主应用提供，否则真实机器人执行保持禁用。

### 第 5 波：运维证据工作区

目标：使 CLI 优先的运行证据对提供方开发和本地运维有用。

实现：

- WF-HARNESS-001：运行框架运行工作区
- WF-HARNESS-002：提供方连接器工作区
- WF-HARNESS-003：实时运行检查器
- WF-HARNESS-004：报告对比与导出
- WF-HARNESS-005：提供方开发工作台

退出标准：

- 运行框架功能调用与 CLI/宿主示例相同的 API，读取相同的运行工件。
- 失败运行保留足够的数据以供 Issue 提交。
- Textual 保持为可选且隔离。

### 第 6 波：参考宿主与生产运维

目标：为用户提供可复制的生产形态，同时不将 WorldForge 变成托管平台。

实现：

- WF-HOST-001：批量评估宿主
- WF-HOST-002：服务宿主参考
- WF-OBS-002：可选 OpenTelemetry 导出器
- WF-OBS-003：可选指标导出器
- WF-OBS-004：日志配置与运行日志
- WF-OBS-005：健康状态、就绪性与故障手册
- 根据需要实现 WF-OPS-001 至 WF-OPS-004

退出标准：

- 宿主示例演示请求 ID、就绪性、类型化错误、预算、脱敏日志及工件导出。
- 发布证据可说明哪些可选提供方已测试、跳过或未配置。

## 路线图里程碑发布门禁

在将里程碑标记为完成前，使用此门禁：

| 门禁 | 所需信号 |
| --- | --- |
| 文档 | `uv run mkdocs build --strict` 通过，导航/SUMMARY 已同步。 |
| 生成的提供方文档 | 提供方元数据变更时，`uv run python scripts/generate_provider_docs.py --check` 通过。 |
| 单元测试 | 已变更模块的针对性测试通过。 |
| 完整检出测试 | `uv run pytest` 在确定性路径上通过。 |
| 运行框架覆盖率 | 运行框架或可选提供方分支变更时，`uv run --extra harness pytest --cov=src/worldforge --cov-report=term-missing --cov-fail-under=90` 通过。 |
| 包契约 | 包接口、可选导入、示例或测试变更时，`bash scripts/test_package.sh` 通过。 |
| 实时证据 | 可选提供方工作包含冒烟清单或明确的跳过原因。 |
| 安全 | 新字段的可观测面具有脱敏覆盖。 |

## 首批 Issue

首先开启这些 Issue；它们解锁了大部分后续工作。

| 顺序 | Issue | 为何优先 |
| --- | --- | --- |
| 1 | WF-PROV-001：提供方晋升门禁 | 防止嘈杂的提供方添加和状态漂移。 |
| 2 | WF-PROV-002：提供方运行时清单模式 | 为真实提供方和宿主应用创建共享运行时契约。 |
| 3 | WF-PROV-003：提供方合规性套件 v2 | 为每个提供方实现提供可复用的质量标准。 |
| 4 | WF-PROV-004：实时冒烟工件契约 | 使实时提供方验证有用且可调试。 |
| 5 | WF-LWM-001：LeWorldModel 稳定打分提供方 | 现有最高价值的真实打分路径。 |
| 6 | WF-LEROBOT-001：LeRobot 稳定策略提供方 | 现有最高价值的真实策略路径。 |
| 7 | WF-LEROBOT-002：具身转换器契约 | 正式机器人宿主应用的前提条件。 |
| 8 | WF-HARNESS-001：运行框架运行工作区 | 运行框架、CLI 和宿主应用的共同工件基础。 |
| 9 | WF-OBS-001：提供方事件模式 v2 | 监控和运行清单的共同可观测性基础。 |
| 10 | WF-PROVIDER-SELECT-001：下一提供方选型 RFC | 保持下一批提供方以证据为驱动。 |

## 待设计后再实施

- 内置多写者持久化。
- 作为默认产品面的托管仪表盘。
- 自动机器人控制器执行。
- 捆绑 torch/CUDA/机器人运行时依赖。
- 声称确定性评估套件衡量物理保真度。
- 仅暴露 `score` 或 `policy` 的提供方的 `plan` 能力。

## Issue 创建检查清单

从本路线图创建 Issue 前：

- [ ] 确认引用的文件仍然存在。
- [ ] 复制 Issue 的范围、超出范围说明、验收标准和验证命令。
- [ ] 在 Issue 正文中添加依赖关系。
- [ ] 尽可能使用现有模板：提供方适配器、评估/基准测试、文档或缺陷。
- [ ] 仅附加脱敏工件。
- [ ] 若 Issue 变更公共行为，在验收标准中包含文档和生成的提供方目录更新。

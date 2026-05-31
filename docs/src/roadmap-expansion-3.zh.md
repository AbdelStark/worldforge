# 路线图扩展 3

这是继原始提供方/平台轨道、延续计划以及前两批 30 个议题路线图扩展之后的第三批扩展。本批次刻意保持累加性：不重新开启已完成的质量、案例展示或功能工作，也不与前两次扩展中已关闭的议题重复。每个议题遵循与前几次扩展相同的模板（背景、问题/机遇、拟议范围、超出范围、验收标准、验证、参考）。

计划仍分为相同的三大流，每流各包含十个实现议题：

- 生产级质量、开发体验与文档
- 演示、端到端案例展示与使用场景
- 新功能

跨流依赖在行内注明，以确保工作顺序与底层基础元素的构建顺序一致。前几次扩展的共享约束保持不变：可选运行时由宿主方持有，提供方能力保持真实，确定性测试是契约信号而非物理保真度声明，公开工件必须安全可附加（除非明确标记为本地专用）。

## 流 1 — 生产级质量、开发体验与文档

目标：使公开层面更接近 1.0 就绪规范。添加采用者放心集成所需的门禁和契约——静态类型、锁定的导出层面、doctor JSON 保证、锚点和 CHANGELOG 完整性、运行时清单完整性、并发持久化边界、工作流文件检查、稳定错误代码以及 CHANGELOG 到发布说明的往返测试。

里程碑：`Roadmap: Quality`。

| # | 标题 | 优先级 | 工作量 |
|---|------|--------|--------|
| [#260](https://github.com/AbdelStark/worldforge/issues/260) | WF-PQDX3-001：为公开包层面添加静态类型检查门禁（Pyright） | p1 | M |
| [#261](https://github.com/AbdelStark/worldforge/issues/261) | WF-PQDX3-002：为公开 Python 导出层面添加快照测试 | p2 | S |
| [#262](https://github.com/AbdelStark/worldforge/issues/262) | WF-PQDX3-003：为 `worldforge doctor` 输出添加稳定 JSON 契约保证 | p1 | M |
| [#263](https://github.com/AbdelStark/worldforge/issues/263) | WF-PQDX3-004：添加文档交叉引用和锚点链接门禁 | p2 | S |
| [#264](https://github.com/AbdelStark/worldforge/issues/264) | WF-PQDX3-005：添加 CHANGELOG.md 结构格式门禁 | p2 | S |
| [#265](https://github.com/AbdelStark/worldforge/issues/265) | WF-PQDX3-006：对目录中每个提供方强制执行提供方运行时清单完整性 | p1 | S |
| [#266](https://github.com/AbdelStark/worldforge/issues/266) | WF-PQDX3-007：为单写入者边界添加并发持久化回归测试 | p1 | M |
| [#267](https://github.com/AbdelStark/worldforge/issues/267) | WF-PQDX3-008：为 GitHub Actions 工作流文件添加 actionlint 门禁 | p2 | S |
| [#268](https://github.com/AbdelStark/worldforge/issues/268) | WF-PQDX3-009：添加稳定错误代码注册表和文档索引 | p2 | M |
| [#269](https://github.com/AbdelStark/worldforge/issues/269) | WF-PQDX3-010：添加 CHANGELOG 到发布说明的往返测试 | p2 | S |

## 流 2 — 演示、端到端案例展示与使用场景

目标：将项目现有的层面转化为采用材料。添加录制的演示、笔记本、叙述式演练以及模板，将现有演示转化为面向新用户的连贯故事，包括已在运行真实机器人的运维人员。

里程碑：`Roadmap: Showcases`。

| # | 标题 | 优先级 | 工作量 |
|---|------|--------|--------|
| [#270](https://github.com/AbdelStark/worldforge/issues/270) | WF-DEMO3-001：发布首次运行工作流的 VHS 录制 CLI 导览 | p2 | M |
| [#271](https://github.com/AbdelStark/worldforge/issues/271) | WF-DEMO3-002：发布 Python API 的 Jupyter 笔记本演练 | p1 | M |
| [#272](https://github.com/AbdelStark/worldforge/issues/272) | WF-DEMO3-003：添加机器人案例展示键盘驱动导览画廊 | p2 | S |
| [#273](https://github.com/AbdelStark/worldforge/issues/273) | WF-DEMO3-004：添加从场景到发布凭证的叙述式演练 | p2 | M |
| [#274](https://github.com/AbdelStark/worldforge/issues/274) | WF-DEMO3-005：添加接入您的机器人 20 分钟引导演示 | p1 | M |
| [#275](https://github.com/AbdelStark/worldforge/issues/275) | WF-DEMO3-006：添加能力协议注册迷你演示 | p2 | S |
| [#276](https://github.com/AbdelStark/worldforge/issues/276) | WF-DEMO3-007：添加提供方迁移演练（从 BaseProvider 到能力协议） | p2 | S |
| [#277](https://github.com/AbdelStark/worldforge/issues/277) | WF-DEMO3-008：添加端到端事件响应分诊演练 | p1 | M |
| [#278](https://github.com/AbdelStark/worldforge/issues/278) | WF-DEMO3-009：添加跨 mock 提供方配置的基准测试扫描案例展示 | p2 | M |
| [#279](https://github.com/AbdelStark/worldforge/issues/279) | WF-DEMO3-010：添加外部采用案例研究模板与画廊 | p2 | S |

## 流 3 — 新功能

目标：在前几次扩展留下明显后续步骤的地方扩展框架能力。代价核算、命名快照、运行保留、能力感知差异、审计日志、场景继承、Prometheus 导出器、跟踪脱敏策略、非变更预览探针以及可插拔持久化后端接口。这些均不改变可选运行时边界，其中多项专为支持新的宿主方持有实现而设计，不将其拉入基础依赖。

里程碑：`Roadmap: Features`。

| # | 标题 | 优先级 | 工作量 |
|---|------|--------|--------|
| [#280](https://github.com/AbdelStark/worldforge/issues/280) | WF-FEAT3-001：添加提供方代价与使用量核算 | p1 | M |
| [#281](https://github.com/AbdelStark/worldforge/issues/281) | WF-FEAT3-002：添加命名世界快照的保存、列出、恢复和删除 | p1 | M |
| [#282](https://github.com/AbdelStark/worldforge/issues/282) | WF-FEAT3-003：通过 `worldforge runs prune` 添加运行工件保留策略 | p2 | M |
| [#283](https://github.com/AbdelStark/worldforge/issues/283) | WF-FEAT3-004：添加能力感知的对比报告差异 | p2 | M |
| [#284](https://github.com/AbdelStark/worldforge/issues/284) | WF-FEAT3-005：添加仅追加的世界审计日志工件 | p2 | M |
| [#285](https://github.com/AbdelStark/worldforge/issues/285) | WF-FEAT3-006：通过 `extends` 字段添加场景继承 | p2 | M |
| [#286](https://github.com/AbdelStark/worldforge/issues/286) | WF-FEAT3-007：在可选额外依赖后添加 Prometheus 指标导出器 | p2 | M |
| [#287](https://github.com/AbdelStark/worldforge/issues/287) | WF-FEAT3-008：添加工作流跟踪脱敏允许和拒绝策略规则 | p2 | S |
| [#288](https://github.com/AbdelStark/worldforge/issues/288) | WF-FEAT3-009：添加非变更提供方预览探针 | p2 | M |
| [#289](https://github.com/AbdelStark/worldforge/issues/289) | WF-FEAT3-010：添加以本地 JSON 为默认值的可插拔持久化后端接口 | p1 | M |

## 跨流依赖

- [#260](https://github.com/AbdelStark/worldforge/issues/260)（Pyright 门禁）→ [#261](https://github.com/AbdelStark/worldforge/issues/261)（导出快照）：静态检查下的类型化强制执行使快照测试也能捕获类型漂移。
- [#264](https://github.com/AbdelStark/worldforge/issues/264)（CHANGELOG 格式）→ [#269](https://github.com/AbdelStark/worldforge/issues/269)（往返测试）：发布说明往返测试以格式门禁的存在为前提。
- [#266](https://github.com/AbdelStark/worldforge/issues/266)（并发持久化）↔ [#289](https://github.com/AbdelStark/worldforge/issues/289)（持久化后端接口）：#266 中确定的并发写入契约是可插拔接口必须遵守的承诺。
- [#281](https://github.com/AbdelStark/worldforge/issues/281)（快照）← [#289](https://github.com/AbdelStark/worldforge/issues/289)：快照通过新的可插拔后端持久化，使未来宿主方持有的后端继承快照语义。
- [#280](https://github.com/AbdelStark/worldforge/issues/280)（代价核算）→ [#278](https://github.com/AbdelStark/worldforge/issues/278)（基准测试扫描）、[#286](https://github.com/AbdelStark/worldforge/issues/286)（Prometheus）：代价单位出现在扫描报告和 Prometheus 导出器中。
- [#285](https://github.com/AbdelStark/worldforge/issues/285)（场景继承）→ [#278](https://github.com/AbdelStark/worldforge/issues/278)（基准测试扫描）：扫描画廊使用继承共享基础配置。
- [#262](https://github.com/AbdelStark/worldforge/issues/262)（doctor JSON 契约）+ [#268](https://github.com/AbdelStark/worldforge/issues/268)（错误代码）→ [#277](https://github.com/AbdelStark/worldforge/issues/277)（事件分诊演练）：演练引用这两个稳定契约。
- [#264](https://github.com/AbdelStark/worldforge/issues/264)（CHANGELOG 格式）+ [#269](https://github.com/AbdelStark/worldforge/issues/269)（往返测试）→ [#273](https://github.com/AbdelStark/worldforge/issues/273)（场景到发布凭证演练）：演练到达由经验证的生成器组装的发布凭证草稿。

## 说明

- 标准每流 10 个议题的数量保持不变，无偏差。
- 优先级分布：8 × p1，22 × p2，0 × p0。前 1.0 工作目前无发布阻塞项；p1 议题是关键的成熟步骤。
- 工作量分布：11 × S，19 × M，0 × L。每个议题的规模适合单个专注的 PR；较大的功能（代价核算、持久化接口）通过推迟宿主方持有的实现有意保持在 M 级别。
- 复用的标签：`enhancement`、`documentation`、`roadmap`、能力/类别标签（`quality`、`testing`、`ci`、`persistence`、`observability`、`provider`、`harness` 等）、流标签（`stream: production-quality`、`stream: demos-showcases`、`stream: new-features`），以及在真正适用时使用的 `good first issue` / `help wanted`。
- 本次扩展新建的标签：`priority:p0`、`priority:p1`、`priority:p2`、`effort:s`、`effort:m`、`effort:l`、`roadmap: expansion-3`。
- 创建的里程碑：`Roadmap: Quality`（#1）、`Roadmap: Showcases`（#2）、`Roadmap: Features`（#3）。

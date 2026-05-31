# 路线图续篇

最后审阅日期：2026-05-01。

本文档定义了 WorldForge 第一个提供方/平台阶段完成后的下一阶段路线图，是下一批 GitHub Issue 的权威来源。前一阶段的提供方/平台路线图已作为基准完成：提供方晋级规则、运行时清单、一致性助手、运行清单、组件工作区、参考宿主、可观测性接收器及发布证据基础设施均已就位。续篇不应重复上述工作，而应让平台更难被误用、更易扩展，并在提出提供方或基准测试声明时更具可信度。

GitHub Issue 批次创建日期：2026-05-01。

| 流程 | 元跟踪 | 子 Issue 范围 |
| --- | --- | --- |
| 提供方证据与运行时队列 | [#127](https://github.com/AbdelStark/worldforge/issues/127) | [#130](https://github.com/AbdelStark/worldforge/issues/130), [#133](https://github.com/AbdelStark/worldforge/issues/133), [#134](https://github.com/AbdelStark/worldforge/issues/134), [#137](https://github.com/AbdelStark/worldforge/issues/137), [#138](https://github.com/AbdelStark/worldforge/issues/138), [#139](https://github.com/AbdelStark/worldforge/issues/139), [#143](https://github.com/AbdelStark/worldforge/issues/143), [#144](https://github.com/AbdelStark/worldforge/issues/144) |
| 评估证据与声明完整性 | [#128](https://github.com/AbdelStark/worldforge/issues/128) | [#132](https://github.com/AbdelStark/worldforge/issues/132), [#135](https://github.com/AbdelStark/worldforge/issues/135), [#136](https://github.com/AbdelStark/worldforge/issues/136), [#140](https://github.com/AbdelStark/worldforge/issues/140), [#145](https://github.com/AbdelStark/worldforge/issues/145), [#146](https://github.com/AbdelStark/worldforge/issues/146), [#147](https://github.com/AbdelStark/worldforge/issues/147), [#150](https://github.com/AbdelStark/worldforge/issues/150) |
| 运营商工作流与适配器编写 | [#129](https://github.com/AbdelStark/worldforge/issues/129) | [#131](https://github.com/AbdelStark/worldforge/issues/131), [#141](https://github.com/AbdelStark/worldforge/issues/141), [#142](https://github.com/AbdelStark/worldforge/issues/142), [#148](https://github.com/AbdelStark/worldforge/issues/148), [#149](https://github.com/AbdelStark/worldforge/issues/149), [#151](https://github.com/AbdelStark/worldforge/issues/151), [#152](https://github.com/AbdelStark/worldforge/issues/152), [#153](https://github.com/AbdelStark/worldforge/issues/153) |

## 判断

下一步的最佳方向并非增加更多提供方名称。WorldForge 已经拥有足够的覆盖面来验证架构是否严谨。下一阶段应集中于三条流程：

1. **提供方证据与运行时队列：** 通过可执行证据（而非目录愿景）来晋级或推迟下一批提供方。
2. **评估证据与声明完整性：** 使每项公开声明均可追溯到已保留的夹具、预算、报告和失败案例。
3. **运营商工作流与适配器编写：** 使正常路径和失败路径对贡献者和已准备好的宿主可重复执行，同时不将由宿主方持有的关注点纳入基础包。

此顺序可保护项目免受当前最大的两种风险：能力膨胀和无证据扩张。项目在尝试显得广泛之前，应先呈现为一个具有强契约的小型可靠集成层。

## 流程 A：提供方证据与运行时队列

元跟踪：[**WF-A0: 提供方证据与运行时队列**](https://github.com/AbdelStark/worldforge/issues/127)。

目标：使用运行时清单、注入式测试、已准备宿主的冒烟测试和生成文档，对下一批提供方进行选择、晋级或推迟。只有当提供方的能力表面明确且可执行时，该提供方才具有价值。

完成信号：

- 已选定的队列有一份书面选择记录，且活跃提供方实现候选不超过三个。
- 每个晋级的提供方都有夹具支撑的成功与失败测试、运行时清单覆盖、已准备宿主的冒烟测试命令，以及生成的提供方文档。
- 推迟的候选有明确的阻碍因素，而非占位脚手架行为。
- 所有提供方工作均不会向基础包添加 torch、机器人技术栈、检查点资产、仪表盘或 Web 框架。

| Issue | 切片 | 类型 | 依赖于 | 主要标签 |
| --- | --- | --- | --- | --- |
| [WF-A1 #130](https://github.com/AbdelStark/worldforge/issues/130) | 建立提供方队列选择记录 | AFK | none | `provider`, `research`, `roadmap` |
| [WF-A2 #133](https://github.com/AbdelStark/worldforge/issues/133) | 晋级 JEPA-WMS 已准备宿主打分证据 | AFK | WF-A1 | `provider`, `score`, `research` |
| [WF-A3 #137](https://github.com/AbdelStark/worldforge/issues/137) | 稳定公开 JEPA 打分适配器 | AFK | WF-A2 | `provider`, `score`, `research` |
| [WF-A4 #138](https://github.com/AbdelStark/worldforge/issues/138) | 将空间/3D 场景提供方边界移出当前范围 | HITL | WF-A1 | `provider`, `design` |
| [WF-A5 #143](https://github.com/AbdelStark/worldforge/issues/143) | 将场景工件夹具工作作为范围外关闭 | AFK | WF-A4 | `provider`, `artifacts` |
| [WF-A6 #139](https://github.com/AbdelStark/worldforge/issues/139) | 解决 Genie 运行时契约决策 | HITL | WF-A1 | `provider`, `research` |
| [WF-A8 #144](https://github.com/AbdelStark/worldforge/issues/144) | 构建提供方实时冒烟证据注册表 | AFK | WF-A2 | `provider`, `operations`, `artifacts` |

### WF-A1：建立提供方队列选择记录

选择记录：[提供方队列选择记录](./provider-cohort-selection.md)。

问题：如果新工作从知名度而非可调用能力、维护成本、夹具策略和冒烟可行性出发，提供方增长可能变成目录噪音。

范围：

- 在文档树下创建一份提供方队列选择记录。
- 依据现有评分标准，对 JEPA-WMS/公开 JEPA、Genie、空间/3D 场景边界、模拟器桥接及新具身策略栈进行评分。
- 为下一实现队列最多选择三个活跃候选。
- 为未达标的候选记录明确的推迟原因。

不在范围内：

- 不进行任何提供方实现。
- 不更改生成的提供方目录。
- 不更改 README 提供方表格。

验收标准：

- [ ] 记录须包含：候选名称、能力、上游运行时/API、运行时所有权、夹具策略、已准备宿主冒烟可行性、许可/维护风险及决策。
- [ ] 已选队列中活跃候选不超过三个。
- [ ] 推迟的候选包含具体的阻碍因素和重新审视触发条件。
- [ ] 记录链接至提供方晋级规则和提供方优先级评分标准。
- [ ] 公开提供方文档继续仅公布可执行行为。

验证：

```bash
uv run mkdocs build --strict
```

### WF-A2：晋级 JEPA-WMS 已准备宿主打分证据

问题：JEPA-WMS 只有在打分路径可针对真实上游运行时进行验证，同时将 PyTorch、检查点和任务预处理保持由宿主方持有的前提下，才具有价值。

范围：

- 在已准备宿主上验证所选的上游 `facebookresearch/jepa-wms` 加载路径。
- 在经过脱敏处理的运行清单中记录：运行时版本、模型名称、设备、张量形状摘要、候选数量、有限打分输出、最佳索引语义及打分方向。
- 为 checkout CI 保留确定性注入式运行时测试。
- 记录不支持的输入形状、缺失运行时、缺失检查点、非有限打分输出及设备回退。

不在范围内：

- 不在基础依赖中引入 torch 或 JEPA-WMS 包。
- 不公开 `predict` 或 `embed` 能力。
- 除非证据支持且文档/目录已更新，否则不更改自动注册逻辑。

验收标准：

- [ ] 已准备宿主冒烟测试写入 `run_manifest.json`，包含：提供方、能力、运行时清单、输入摘要、结果摘要、事件数量及安全张量形状摘要。
- [ ] 测试覆盖：成功、缺失运行时、缺失模型、张量形状异常、候选数量不匹配及非有限打分。
- [ ] 提供方事件和清单不含原始张量、凭证、宿主本地密钥或签名 URL。
- [ ] 文档说明决策后直接构造与目录的行为差异。
- [ ] 基础依赖集保持不变。

验证：

```bash
uv run pytest tests/test_jepa_wms_provider.py tests/test_provider_contracts.py
uv run python scripts/generate_provider_docs.py --check
uv run mkdocs build --strict
```

### WF-A3：稳定公开 JEPA 打分适配器

问题：公开的 `jepa` 适配器应保持实验性状态，除非它具有与 JEPA-WMS 相同证据契约支撑的明确定义打分表面。

范围：

- 围绕仅打分适配器，对 `jepa` 的配置、诊断、运行时清单、文档及失败类型进行对齐。
- 仅将历史脚手架变量保留为无值诊断元数据。
- 确保不支持的能力以明确错误方式失败，且不出现在提供方能力标志中。
- 为之前配置了脚手架预留的宿主添加迁移说明。

不在范围内：

- 不引入无单独契约的潜在展开或嵌入 API。
- 不将代理/模拟行为公布为真实的 JEPA 集成。
- 除非队列记录建议，否则不更改提供方名称。

验收标准：

- [ ] `jepa` 仅公布已实现的打分表面。
- [ ] 健康输出区分：模型名称缺失、可选依赖缺失、检查点/模型缺失及运行时输出异常。
- [ ] 文档解释为何 `JEPA_MODEL_PATH` 是历史元数据，而 `JEPA_MODEL_NAME` 控制真实运行时路径。
- [ ] 生成的提供方文档与提供方配置元数据一致。
- [ ] 一致性助手覆盖公开打分表面。

验证：

```bash
uv run pytest tests/test_jepa_provider.py tests/test_jepa_wms_provider.py tests/test_provider_catalog_docs.py
uv run python scripts/generate_provider_docs.py --check
uv run mkdocs build --strict
```

### WF-A4：定义空间/3D 场景提供方边界

设计说明：空间/3D 场景工件不属于当前以规划为中心的提供方能力面。

问题：场景与 3D 世界生成不同于视频生成、预测和规划。在定义工件契约之前添加提供方将模糊能力模型。

范围：

- 撰写设计记录，选择第一个空间/3D 场景运行时或 API 候选。
- 定义最小化 JSON 原生场景工件边界：单位、坐标系、资产引用、对象标识符、变换、媒体引用、出处及安全元数据。
- 决定该工作是否继续保持在当前提供方表面之外。
- 定义资产 URL、宿主本地路径和提供方元数据的脱敏规则。

不在范围内：

- 不进行任何提供方实现。
- 不在基础包中引入查看器、渲染器、模拟器或 3D 资产依赖。
- 不声明场景工件具有物理有效性。

验收标准：

- [ ] 设计记录说明已接受和已拒绝的运行时/API 候选。
- [ ] 场景工件边界为 JSON 原生，且无需可选依赖即可测试。
- [ ] 记录说明该工作是否保持推迟状态。
- [ ] 由宿主方持有的资产存储、渲染、模拟和许可职责有明确说明。
- [ ] 后续实现 Issue 可在不重新讨论能力语义的情况下创建。

验证：

```bash
uv run mkdocs build --strict
```

### WF-A5：实现场景工件夹具与验证

问题：若空间/3D 提供方推进，WorldForge 在编写任何运行时特定适配器代码之前需要夹具和验证器。

范围：

- 为有效场景工件、异常变换、无效单位、不安全资产引用及过大元数据添加夹具模式。
- 添加拒绝非 JSON 原生元数据和非有限数值的验证助手。
- 添加展示工件边界和安全 Issue 附件预期的文档。
- 将渲染、模拟和资产获取保持由宿主方持有。

不在范围内：

- 不进行实时提供方调用。
- 除验证所需的极小夹具外，不捆绑任何 3D 资产。
- 不更改基础运行时依赖。

验收标准：

- [ ] 夹具覆盖有效和无效的场景载荷。
- [ ] 验证拒绝：非有限数值、元组形状值、对象实例、不安全 URL 及宿主本地路径（除非标记为仅本地）。
- [ ] 文档说明工件能证明和不能证明的内容。
- [ ] 测试在干净的 checkout 中无需网络或可选包即可运行。

验证：

```bash
uv run pytest tests/test_provider_contracts.py tests/test_docs_site.py
uv run mkdocs build --strict
```

### WF-A6：解决 Genie 运行时契约决策

问题：Genie 仍是一个失败关闭的预留。它应获得一个具体的上游运行时/API 契约，或以精确原因保持推迟状态。

范围：

- 审查当前公开的 Genie 自动化/运行时选项。
- 选择一个明确契约或记录推迟决策。
- 若推迟，强化文档以说明重新审视触发条件并防止代理预期。
- 若选定，为夹具支撑的运行时行为编写实现 Issue。

不在范围内：

- 不将确定性代理呈现为真实的 Genie 行为。
- 在真实运行时/API 存在之前，不设置默认能力标志。
- 不在基础包中引入大型运行时、浏览器自动化栈或模型依赖。

验收标准：

- [ ] Issue 关闭时须有选定的运行时/API 契约或有记录的推迟决策。
- [ ] 文档在提供方、路线图和选择记录层面解释该决策。
- [ ] 若推迟，提供方健康状态和文档保持失败关闭且无值。
- [ ] 若选定，后续 Issue 说明夹具、冒烟命令、工件、失败模式及生成文档更新。

验证：

```bash
uv run pytest tests/test_remote_scaffold_providers.py tests/test_provider_catalog_docs.py
uv run mkdocs build --strict
```

### WF-A8：构建提供方实时冒烟证据注册表

注册表：[实时冒烟证据注册表](./live-smoke-evidence.md)。

问题：已准备宿主的冒烟测试结果目前按运行保存，但维护者需要一个轻量级注册表，记录哪些可选提供方有近期证据、哪些被跳过。

范围：

- 定义基于文档或生成的实时冒烟证据条目注册表。
- 记录：提供方、能力、命令、运行时清单、日期、版本、状态、工件路径、跳过原因及已知限制。
- 默认确保注册表安全可发布。
- 从提供方文档和发布证据链接至该注册表。

不在范围内：

- 默认情况下不设置需要凭证、GPU、检查点或付费 API 的 CI 任务。
- 不上传原始工件或密钥。
- 不声称冒烟证据是基准测试。

验收标准：

- [ ] 注册表条目依据小型模式进行验证。
- [ ] 缺少可选运行时和凭证的跳过情况作为一等状态处理。
- [ ] 发布证据可包含注册表而无需手动复制粘贴。
- [ ] 文档解释如何将经脱敏处理的运行清单附加到提供方 Issue。

验证：

```bash
uv run pytest tests/test_live_smoke_evidence.py tests/test_smoke_run_manifest.py
uv run mkdocs build --strict
```

## 流程 B：评估证据与声明完整性

元跟踪：[**WF-B0: 评估证据与声明完整性**](https://github.com/AbdelStark/worldforge/issues/128)。

目标：将评估和基准测试转变为可复现的证据，而非宽泛的质量声明。该框架可提供确定性契约信号、保留工件、预算及比较工具。在没有证据的情况下，不应暗示物理保真度或提供方优越性。

完成信号：

- 评估和基准测试输出携带出处、夹具身份、预算上下文和声明边界。
- 公开文档有一份声明-证据映射，说明哪些声明受支持、不受支持及已推迟。
- 发布证据可从保留的工件中生成，无需凭证。
- 失败和回归可供检查，而非隐藏在聚合分数背后。

| Issue | 切片 | 类型 | 依赖于 | 主要标签 |
| --- | --- | --- | --- | --- |
| [WF-B1 #132](https://github.com/AbdelStark/worldforge/issues/132) | 定义评估结果出处 v2 | AFK | none | `evaluation`, `artifacts`, `quality` |
| [WF-B2 #135](https://github.com/AbdelStark/worldforge/issues/135) | 构建能力夹具语料库 | AFK | WF-B1 | `evaluation`, `testing`, `provider` |
| [WF-B3 #136](https://github.com/AbdelStark/worldforge/issues/136) | 添加发布回归基准测试预设套件 | AFK | WF-B1 | `benchmark`, `release`, `quality` |
| [WF-B4 #140](https://github.com/AbdelStark/worldforge/issues/140) | 为公开文档创建声明-证据映射 | AFK | WF-B1 | `documentation`, `quality`, `release` |
| [WF-B5 #145](https://github.com/AbdelStark/worldforge/issues/145) | 生成可复现的评估证据包 | AFK | WF-B2, WF-B3 | `evaluation`, `benchmark`, `artifacts` |
| [WF-B6 #146](https://github.com/AbdelStark/worldforge/issues/146) | 从保留的基线校准基准测试预算 | AFK | WF-B3 | `benchmark`, `quality`, `release` |
| [WF-B7 #147](https://github.com/AbdelStark/worldforge/issues/147) | 为评估套件添加失败案例展示库 | AFK | WF-B2 | `evaluation`, `documentation`, `quality` |
| [WF-B8 #150](https://github.com/AbdelStark/worldforge/issues/150) | 添加跨提供方比较报告 | AFK | WF-B5 | `benchmark`, `evaluation`, `harness` |

### WF-B1：定义评估结果出处 v2

问题：评估结果需要足够的出处来支撑声明、复现失败，并在不依赖控制台日志的情况下比较运行。

范围：

- 为评估和基准测试输出定义结果出处信封。
- 包含：WorldForge 版本、命令、提供方、能力、输入夹具摘要、预算文件、运行时清单、事件数量、结果摘要、套件版本及声明边界备注。
- 保留向后兼容性，或为现有报告记录迁移行为。
- 在渲染工件之前验证有限数值指标和连贯的计数。

不在范围内：

- 不进行实时提供方执行。
- 不更改现有套件的打分语义。
- 不扩展物理保真度声明。

验收标准：

- [x] 评估和基准测试报告包含出处信封。
- [x] 无效指标、缺失套件名称、非有限值及计数不匹配在报告渲染前失败。
- [x] 现有 CLI 报告格式保持稳定或有文档化的迁移说明。
- [x] 文档解释在 Issue 和发布证据中应如何引用出处。

验证：

```bash
uv run pytest tests/test_provenance.py tests/test_evaluation_and_planning.py tests/test_benchmark.py
uv run mkdocs build --strict
```

### WF-B2：构建能力夹具语料库

问题：提供方和评估工作需要一个共享的夹具语料库，用于 score、policy、predict 和 embed 路径，而非每个测试使用临时载荷。

范围：

- 为每种能力添加包含成功和失败案例的小型 JSON 夹具。
- 包含：异常元数据、非有限数值、不安全工件引用、无效动作载荷及能力不匹配案例。
- 记录夹具所有权以及提供方应如何复用该语料库。
- 仅在必要时将二进制资产保持极小或用摘要/base64 表示。

不在范围内：

- 不引入大型数据集。
- 不下载检查点或媒体工件。
- 不使用实时提供方凭证。

验收标准：

- [x] 每种能力至少有一个有效夹具和两个无效边界夹具。
- [x] 夹具由一致性或评估测试使用。
- [x] 夹具文档说明数据是合成的、捕获的还是由宿主提供的。
- [x] 包契约保持小型且可安装。

验证：

```bash
uv run pytest tests/test_capability_fixtures.py tests/test_provider_contracts.py
bash scripts/test_package.sh
uv run mkdocs build --strict
```

### WF-B3：添加发布回归基准测试预设套件

问题：基准测试输入文件和预算文件已存在，但维护者需要命名的预设，将快速 checkout 回归检查与已准备宿主提供方证据分开。

范围：

- 为以下场景定义基准测试预设：checkout 安全模拟运行、提供方解析器开销、可选打分/策略已准备宿主运行及发布证据。
- 保持预设输入确定性且体积小。
- 记录命令、预期成功信号及允许预设失败的条件。
- 确保失败预算以非零退出，并保留足够的报告数据供排查。

不在范围内：

- 默认情况下 CI 不进行实时 API 调用。
- 不在没有保留上下文的情况下跨机器进行性能声明。
- 默认不设置付费提供方基准测试任务。

验收标准：

- [x] 预设可从 CLI 或文档化的 make 目标列出并运行。
- [x] Checkout 安全预设无需凭证、网络、GPU 或可选运行时即可运行。
- [x] 已准备宿主预设在缺少前提条件时以有类型的原因跳过或失败。
- [x] 预算违规包含：操作、指标、阈值、观测值及工件路径。

验证：

```bash
uv run pytest tests/test_benchmark.py tests/test_benchmark_presets.py tests/test_cli_help_snapshots.py
uv run worldforge benchmark --preset mock-smoke
uv run mkdocs build --strict
```

### WF-B4：为公开文档创建声明-证据映射

问题：公开文档应清晰表明哪些声明由确定性测试支撑、哪些需要已准备宿主证据、哪些是有意的非目标。

范围：

- 在文档中添加声明-证据映射。
- 将声明分类为：checkout 已测试、夹具已测试、已准备宿主冒烟已测试、发布门控、已推迟或不受支持。
- 将声明链接至命令、工件、测试、文档页面及已知限制。
- 包含非声明项：物理保真度、机器人安全认证、上游 SLA 所有权及服务级持久化。

不在范围内：

- 不提供新的基准测试数字。
- 不使用更广泛的营销语言。
- 不更改提供方能力标志。

验收标准：

- [x] 每项 README 级别的能力声明都有对应的证据类别。
- [x] 不受支持或已推迟的声明清晰可见且具体。
- [x] 文档将用户引导至保留的工件或命令，而非模糊的置信语言。
- [x] MkDocs 严格构建通过，导航与目录同步。

验证：

```bash
uv run mkdocs build --strict
uv run pytest tests/test_docs_site.py
```

### WF-B5：生成可复现的评估证据包

问题：发布和 Issue 排查需要一个单一证据包，汇集报告、清单、命令、预算、夹具摘要和跳过原因。

范围：

- 添加从选定运行创建评估证据目录的命令或脚本。
- 包含：JSON 和 Markdown 摘要、复制的输入夹具、预算文件、运行清单、事件日志及包内容清单。
- 默认脱敏或拒绝不安全的工件。
- 对于 checkout 安全运行，保持包生成确定性且无需凭证。

不在范围内：

- 不提供工件上传服务。
- 除非宿主明确请求，否则不进行实时提供方执行。
- 默认不包含原始密钥、签名 URL、原始张量或大型二进制输出。

验收标准：

- [x] 对于干净 checkout 中的模拟评估和基准测试运行，包生成成功。
- [x] 包清单包含文件摘要和安全附件标志。
- [x] 不安全或仅本地的工件被排除或明确标记。
- [x] 发布证据可链接至生成的包。

验证：

```bash
uv run pytest tests/test_evidence_bundle.py tests/test_harness_workspace.py tests/test_observability.py
uv run mkdocs build --strict
```

### WF-B6：从保留的基线校准基准测试预算

问题：预算只有在从保留的基线校准并通过明确审查路径更新时才有价值。

范围：

- 添加从保留的基准测试报告生成候选预算的工作流。
- 存储基线上下文：机器类别（如有）、Python 版本、命令、提供方、操作、样本数量及夹具摘要。
- 在替换发布预算文件之前要求人工审查。
- 记录允许更改预算的条件。

不在范围内：

- 不自动放宽发布门控。
- 不基于本地运行进行与机器无关的性能声明。
- 默认 CI 中不设置不稳定的实时提供方预算。

验收标准：

- [x] 候选预算生成记录来源报告摘要。
- [x] 预算差异显示：旧阈值、候选阈值、观测基线及理由字段。
- [x] 文档要求对阈值放宽进行审查。
- [x] 现有预算失败行为保持非零退出。

验证：

```bash
uv run pytest tests/test_benchmark.py tests/test_benchmark_budget_calibration.py
uv run mkdocs build --strict
```

### WF-B7：为评估套件添加失败案例展示库

问题：聚合分数会隐藏失败内容。用户需要有代表性的失败案例，展示输入、预期契约、观测结果及排查步骤。

范围：

- 为确定性评估套件添加失败案例展示库生成功能。
- 在适用情况下，为物理、规划、打分和策略提供紧凑示例。
- 保持示例经过脱敏处理且体积小。
- 记录在提交 Issue 或审查提供方变更时如何使用展示库。

不在范围内：

- 不提供重量级视觉仪表盘。
- 不引入大型媒体语料库。
- 不基于合成失败进行提供方质量排名。

验收标准：

- [x] 失败的评估报告包含带有夹具 ID 和预期契约备注的代表性案例。
- [x] 展示库导出为 JSON 和 Markdown。
- [x] 报告避免包含原始密钥、签名 URL、原始张量及宿主本地路径。
- [x] 文档说明展示库是确定性契约排查，而非保真度声明。

验证：

```bash
uv run pytest tests/test_evaluation_suites.py tests/test_evaluation_failure_gallery.py
uv run mkdocs build --strict
```

### WF-B8：添加跨提供方比较报告

问题：用户需要在不混淆能力不匹配与性能或质量的情况下，跨提供方和能力比较保留的运行。

范围：

- 扩展运行比较，按提供方、能力、操作、夹具摘要、预算和套件版本分组。
- 对不兼容的比较以明确错误拒绝。
- 导出适合 Issue 附件的 JSON、Markdown 和 CSV 报告。
- 显示缺失证据和跳过原因，而非静默忽略提供方。

不在范围内：

- 不提供公开排行榜。
- 不跨不同任务或能力进行排名。
- 默认不进行实时提供方执行。

验收标准：

- [x] 兼容运行以出处、指标增量、事件数量和预算状态进行比较。
- [x] 不兼容运行以能力、操作、夹具、预算或套件版本详情失败。
- [x] Markdown 输出包含声明边界语言。
- [x] CLI 比较路径使用相同的底层报告模型。

验证：

```bash
uv run pytest tests/test_harness_report_compare.py tests/test_benchmark.py tests/test_evaluation_suites.py
uv run mkdocs build --strict
```

## 流程 C：运营商工作流与适配器编写

元跟踪：[**WF-C0: 运营商工作流与适配器编写**](https://github.com/AbdelStark/worldforge/issues/129)。

目标：使 WorldForge 更易操作和扩展，同时不隐藏复杂性。贡献者应有从提供方想法到选择记录、脚手架、测试、文档、冒烟证据及 Issue 就绪工件的清晰路径。运营商应能够在不阅读源代码的情况下诊断本地运行。

完成信号：

- 适配器作者可以生成包含运行时清单、文档存根、夹具、测试和工作台检查的脚手架。
- 运营商可以从失败运行中导出经脱敏处理的 Issue 包。
- CLI 公开相同的操作工作流和恢复命令。
- 贡献者分类、标签和发布标签与路线图流程匹配。

| Issue | 切片 | 类型 | 依赖于 | 主要标签 |
| --- | --- | --- | --- | --- |
| [WF-C1 #141](https://github.com/AbdelStark/worldforge/issues/141) | 构建适配器作者工作台路径 | AFK | WF-A1 | `developer-experience`, `provider`, `harness` |
| [WF-C2 #142](https://github.com/AbdelStark/worldforge/issues/142) | 升级提供方脚手架生成以支持完整契约 | AFK | WF-C1 | `developer-experience`, `provider`, `testing` |
| [WF-C3 #148](https://github.com/AbdelStark/worldforge/issues/148) | 导出 Issue 就绪运行包 | AFK | WF-B5 | `operations`, `artifacts`, `observability` |
| [WF-C4 #149](https://github.com/AbdelStark/worldforge/issues/149) | 强化组件工作流以支持重复本地操作 | AFK | WF-C3 | `harness`, `operations`, `developer-experience` |
| [WF-C5 #151](https://github.com/AbdelStark/worldforge/issues/151) | 扩展参考宿主部署方案 | AFK | WF-C3 | `examples`, `operations`, `documentation` |
| [WF-C6 #152](https://github.com/AbdelStark/worldforge/issues/152) | 添加运营商操作手册演练命令 | AFK | WF-C5 | `operations`, `reliability`, `testing` |
| [WF-C7 #153](https://github.com/AbdelStark/worldforge/issues/153) | 添加本地状态预检和恢复检查 | AFK | WF-C6 | `persistence`, `operations`, `reliability` |
| [WF-C8 #131](https://github.com/AbdelStark/worldforge/issues/131) | 定义贡献者分类分类法和发布标签 | AFK | none | `roadmap`, `documentation`, `quality` |

### WF-C1：构建适配器作者工作台路径

问题：提供方作者需要一个从选择记录开始、以一致性检查、文档漂移检查和 Issue 就绪输出结束的引导式循环。

范围：

- 扩展提供方工作台路径以接受提供方候选或脚手架。
- 展示：所需的晋级证据、运行时清单状态、夹具覆盖、文档/目录漂移、一致性助手状态及脱敏检查。
- 生成适合 GitHub Issue 或 PR 描述的 Markdown。
- 保持实时调用为可选。

不在范围内：

- 不自动实现提供方。
- 不在没有明确标志的情况下进行实时 API 调用。
- 不为可选运行时安装依赖。

验收标准：

- [x] 工作台可在干净的 checkout 中针对 `mock` 及至少一个脚手架/候选运行。
- [x] 输出按晋级状态列出缺失证据。
- [x] Markdown 输出包含验证命令和安全工件引用。
- [x] TUI 和 CLI 工作台视图使用相同的非 Textual 流程逻辑。

验证：

```bash
uv run pytest tests/test_provider_workbench.py tests/test_harness_flows.py tests/test_harness_cli.py
uv run --extra harness pytest tests/test_harness_tui.py
uv run mkdocs build --strict
```

### WF-C2：升级提供方脚手架生成以支持完整契约

问题：脚手架生成器应创建正确的空契约表面，使新提供方工作从测试、文档、清单存根和失败模式开始，而非仅从适配器代码开始。

范围：

- 更新脚手架生成以产出：提供方文件、夹具占位符、测试、文档存根、运行时清单存根及工作台检查清单。
- 要求提供规划中的能力和实现状态。
- 默认生成失败关闭行为。
- 记录生成的文件和下一步验证命令。

不在范围内：

- 不自动注册脚手架提供方。
- 不生成声称具有真实运行时行为的代码。
- 不更改基础依赖。

验收标准：

- [x] 脚手架输出包含不支持能力调用和提供方配置元数据的测试。
- [x] 生成的清单存根明确标记为不完整，且不用作真实证据。
- [x] 生成的文档警告：在晋级标准通过之前，该提供方不可执行。
- [x] 运行脚手架命令不会覆盖现有文件，除非明确请求。

验证：

```bash
uv run pytest tests/test_scaffold_provider.py tests/test_provider_catalog_docs.py
uv run mkdocs build --strict
```

### WF-C3：导出 Issue 就绪运行包

问题：失败运行应生成一个小型包，使维护者无需请求原始日志、凭证或宿主本地状态即可检查。

范围：

- 添加从 `.worldforge/runs/<run-id>/` 导出经脱敏处理包的命令。
- 包含：运行清单、提供方事件、结果摘要、验证错误、报告导出及摘要清单。
- 脱敏或拒绝不安全字段。
- 打印简短的 Issue 模板部分，包含：命令、预期信号、观测到的失败、工件及安全附件备注。

不在范围内：

- 不从失败运行自动创建 GitHub Issue。
- 不包含原始提示词、原始张量、机器人序列号、签名 URL 或密钥。
- 不提供服务级工件存储。

验收标准：

- [x] 对于成功、失败、跳过和已取消的模拟运行，导出均成功。
- [x] 不安全元数据会导致明确错误或仅本地标记。
- [x] 包清单包含摘要和安全附件标志。
- [x] 文档解释导出后的首要排查步骤。

验证：

```bash
uv run pytest tests/test_issue_bundle_export.py tests/test_harness_workspace.py tests/test_observability.py
uv run mkdocs build --strict
```

### WF-C4：强化组件工作流以支持重复本地操作

问题：CLI 运行证据应支持重复工作流所需的历史记录、过滤、重新运行命令和清晰的失败恢复。

范围：

- 按提供方、能力、状态、日期和安全工件类型添加运行历史过滤。
- 从保留的清单生成重新运行命令。
- 显示 Issue 包导出和比较操作。
- 保持键盘优先导航和 Textual 导入隔离。

不在范围内：

- 不提供托管仪表盘。
- 不提供后台调度器。
- 除非用户明确启动，否则不进行实时提供方调用。

验收标准：

- [x] CLI 可在不使用可选模型运行时的情况下过滤和打开保留的运行。
- [x] 重新运行命令从经脱敏清单生成，且不包含密钥值。
- [x] 失败运行显示恢复命令和 Issue 包导出路径。
- [x] 测试覆盖流程逻辑，且不在 `worldforge.harness.tui` 外部导入 Textual。

验证：

```bash
uv run pytest tests/test_harness_flows.py tests/test_harness_workspace.py tests/test_harness_report_compare.py
uv run --extra harness pytest tests/test_harness_tui.py
uv run mkdocs build --strict
```

### WF-C5：扩展参考宿主部署方案

问题：参考宿主已存在，但用户需要更清晰的部署方案，说明 WorldForge 的职责、宿主的职责，以及在真实流量或机器人使用前如何验证配置。

范围：

- 为批量评估、标准库服务及机器人运营商宿主部署添加方案。
- 包含：环境模板、进程命令、就绪命令、冒烟命令、日志命令、证据导出命令及首要回滚/排查步骤。
- 将部署、鉴权、队列、存储、控制器集成及告警保持由宿主方持有。

不在范围内：

- 基础包中不引入 Kubernetes、云或仪表盘依赖。
- 不实现机器人控制器。
- 不声称提供生产级 SLA。

验收标准：

- [x] 每个方案包含：命令、预期成功信号、首要失败排查步骤及所有权边界。
- [x] 方案区分：checkout 安全、已准备宿主、需凭证、GPU 绑定及机器人实验室路径。
- [x] 仅在引入新提供方变量时跟踪 `.env.example` 更改。
- [x] 文档不暗示 WorldForge 拥有正常运行时间、安全认证或持久存储。

验证：

```bash
uv run pytest tests/test_docs_site.py tests/test_service_host.py tests/test_batch_eval_host.py tests/test_robotics_operator_host.py
uv run mkdocs build --strict
```

### WF-C6：添加运营商操作手册演练命令

问题：操作手册只有在运营商可以在没有真实提供方中断的情况下演练常见失败模式时才有价值。

范围：

- 为以下场景添加确定性演练命令：缺少凭证、缺少可选依赖、提供方输出异常、预算违规、本地世界状态损坏、工件过期及不安全事件元数据。
- 在适用时使演练写入运行清单或 Issue 包。
- 记录预期的失败信号和恢复步骤。
- 除非明确标记为已准备宿主，否则保持演练 checkout 安全。

不在范围内：

- 不提供混沌服务或长时间运行的守护进程。
- 不进行实时付费提供方故障注入。
- 不在没有明确临时状态目录的情况下修改用户世界数据。

验收标准：

- [x] 演练命令在使用 mock 或夹具的干净 checkout 中运行。
- [x] 每个演练都有文档化的预期失败和恢复命令。
- [x] 不安全元数据演练证明脱敏门控失败关闭。
- [x] 演练不在临时或文档化工作区外留下持久状态。

验证：

```bash
uv run pytest tests/test_operator_drills.py tests/test_provider_config.py tests/test_observability.py
uv run mkdocs build --strict
```

### WF-C7：添加本地状态预检和恢复检查

问题：本地 JSON 持久化设计上较为简单，但运营商仍需要针对损坏世界数据、不安全 ID、无效历史记录和过时运行工作区的清晰预检和恢复命令。

范围：

- 添加或扩展以下预检：世界状态目录、文件安全 ID、历史记录一致性、对象边界框、运行工作区清单及保留压力。
- 提供在删除或隔离无效文件之前导出诊断信息的恢复命令。
- 将多写入持久化保持在范围之外。

不在范围内：

- 不引入锁文件。
- 不引入 SQLite 或数据库适配器。
- 不静默强制转换无效的持久化状态。

验收标准：

- [x] 预检识别：损坏世界数据、遍历形状 ID、无效历史条目、过时运行工作区及不安全工件路径。
- [x] 恢复命令是明确的，不会静默删除用户数据。
- [x] 诊断信息默认可安全附加至 Issue。
- [x] 现有本地 JSON 行为仍具权威性。

验证：

```bash
uv run pytest tests/test_world_lifecycle.py tests/test_persistence*.py tests/test_harness_workspace.py
uv run mkdocs build --strict
```

### WF-C8：定义贡献者分类分类法和发布标签

问题：Issue 跟踪器应反映路线图流程，使贡献者能够识别提供方工作、证据工作、运营商工作、阻碍因素和发布候选范围。

范围：

- 记录路线图流程、能力、严重性和发布范围的标签分类法。
- 将 GitHub 标签与三个续篇流程对齐。
- 添加分类指南，说明 Issue 何时需要选择记录、设计记录、提供方晋级门控或发布证据。
- 如需要，更新贡献者文档和 Issue 模板。

不在范围内：

- 不在未经审查的情况下关闭或重写现有 Issue。
- 不引入项目管理自动化依赖。
- 不更改安全报告策略。

验收标准：

- [x] 三个路线图流程的标签已存在，或现有标签已明确映射至这些流程。
- [x] 贡献者文档解释如何分类提供方、证据和运营商工作流 Issue。
- [x] Issue 模板将提供方运行时工作路由至晋级标准和证据要求。
- [x] 安全敏感报告仍通过私有渠道而非公开 Issue 路由。

验证：

```bash
uv run pytest tests/test_docs_site.py
uv run mkdocs build --strict
```

## 依赖顺序

实际执行顺序为：

1. WF-A1 和 WF-C8 建立选择和分类规则。
2. WF-B1 为证据流程建立出处语言。
3. WF-A2、WF-A7、WF-B2 和 WF-B3 构建第一批可复用证据表面。
4. WF-A3、WF-A4、WF-A6、WF-B4、WF-C1 和 WF-C2 将标准转化为提供方和贡献者工作流。
5. WF-A5、WF-A8、WF-B5、WF-B6、WF-B7、WF-C3 和 WF-C4 使证据和失败案例可复用。
6. WF-B8、WF-C5、WF-C6 和 WF-C7 将结果转化为面向运营商的实践。

## Issue 创建检查清单

从本路线图创建 GitHub Issue 时：

- 首先创建三个元跟踪器。
- 按依赖顺序创建子 Issue，并在每个子 Issue 中包含父跟踪器编号。
- 使用本文件中的严格验收标准和验证命令。
- 不要创建缺少能力、运行时所有权、失败模式及文档/生成目录预期的提供方 Issue。
- 在设计记录被接受之前，不要将 HITL 设计 Issue 标记为可实现。
- Issue 正文中应明确说明：可选运行时、检查点、凭证、机器人控制器、持久化存储、遥测收集器及部署策略均由宿主方持有。

# 路线图扩展

本路线图将 WorldForge 的工作延伸至已完成的延续性轨道之外。Nano World Model 相关议题已另行分配，故本文档有意将其排除在外。计划分为三个主要方向，每个方向包含十个实现议题：

- 生产级质量、DevX 与文档
- 演示、端到端案例展示与使用场景
- 新功能

每个议题均设计为可独立推进的工作单元。共同规则依然适用：保持可选运行时由宿主方持有，保持提供方能力声明的真实性，维护可安全检出的验证路径，避免将确定性测试视为物理保真度的依据。

## 方向一：生产级质量、DevX 与文档

目标：在不将宿主方持有的运行时或部署责任纳入基础包的前提下，使 WorldForge 更易于信任、维护、发布、文档化并接受贡献。

### WF-PQDX-001：添加发布就绪证据命令

GitHub 议题：[#179](https://github.com/AbdelStark/worldforge/issues/179)

问题：发布检查已有文档记录，但操作人员仍需手动从多个命令中汇总证据。

工作范围：

- 添加一个发布就绪命令或脚本，执行已记录的可安全检出的关卡，并生成结构化摘要工件。
- 包含文档构建、提供方文档漂移、测试、包契约、依赖审计说明，以及可选的实况冒烟测试证据引用。
- 记录命令、时间戳、工具版本、状态，以及失败时的首步分类处理步骤。

超出范围：

- 不涉及发布、打标签、签名或凭据处理。
- 除非宿主方明确要求，否则不执行可选实况运行时。

验收标准：

- [ ] 单条命令可生成 JSON 和 Markdown 格式的发布就绪摘要。
- [ ] 摘要区分已通过、已失败、已跳过和由宿主方持有的检查项。
- [ ] 文档说明预期的成功信号和失败分类处理方式。
- [ ] 测试覆盖成功、关卡失败和跳过可选证据三条路径。

验证方式：

```bash
uv run pytest tests/test_release_evidence.py tests/test_docs_site.py
uv run mkdocs build --strict
```

### WF-PQDX-002：制定公共 API 稳定性与弃用策略

GitHub 议题：[#180](https://github.com/AbdelStark/worldforge/issues/180)

问题：WorldForge 尚未达到 1.0 版本，但已有真实用户和公开的适配器接口；贡献者在修改模型、CLI 命令和提供方契约之前需要清晰的兼容性策略。

工作范围：

- 文档化稳定、临时、实验性和内部 API 层级。
- 为 Python API、CLI 标志、提供方能力、文档页面和工件模式定义弃用通知规范。
- 添加测试或文档检查，使已弃用的接口可见。

超出范围：

- 不承诺 1.0 版本的语义稳定性。
- 不追溯支持已删除的私有辅助接口。

验收标准：

- [ ] 文档列出 API 层级及当前模块中的示例。
- [ ] 提供方能力和工件模式变更具有已记录的迁移路径。
- [ ] 破坏性变更在变更日志中有明确的预期说明。
- [ ] 贡献者能够判断某个议题是否需要弃用计划。

验证方式：

```bash
uv run pytest tests/test_docs_site.py tests/test_public_api.py
uv run mkdocs build --strict
```

### WF-PQDX-003：通过共享语料库强化提供方事件脱敏

GitHub 议题：[#181](https://github.com/AbdelStark/worldforge/issues/181)

问题：提供方事件是安全边界，但新的接收器和运行时适配器可能在没有共享恶意输入语料库的情况下导致脱敏退化。

工作范围：

- 为 Bearer 令牌、API 密钥、签名 URL、查询字符串、私有端点、宿主本地路径和密钥形式的元数据添加夹具语料库。
- 使 JSON 日志、指标、OpenTelemetry、Rerun、议题包和运行清单均经过同一语料库的检验。
- 将该语料库记录为未来事件接收器的契约。

超出范围：

- 不扫描用户工作区中的密钥。
- 不集成出站遥测服务。

验收标准：

- [ ] 共享夹具覆盖 URL、元数据、消息、目标和额外字段的脱敏。
- [ ] 现有事件接收器在测试中使用相同的语料库。
- [ ] 不安全的值在序列化前进行失败关闭或脱敏处理。
- [ ] 文档说明提供方事件仅在通过净化器检查后方可附加。

验证方式：

```bash
uv run pytest tests/test_observability.py tests/test_observability_opentelemetry.py tests/test_evidence_bundle.py tests/test_rerun_integration.py
uv run mkdocs build --strict
```

### WF-PQDX-004：为错误族群添加故障排查矩阵

GitHub 议题：[#182](https://github.com/AbdelStark/worldforge/issues/182)

问题：`WorldForgeError`、`WorldStateError` 和 `ProviderError` 语义明确，但用户需要一条从错误族群快速定位到责任方、命令、工件和恢复步骤的路径。

工作范围：

- 为公共错误族群和常见消息添加故障排查矩阵。
- 链接 CLI 命令、本地状态预检、提供方诊断、运行包和操作人员演练。
- 为每一行包含首步分类命令、预期工件和可能的责任方。

超出范围：

- 除非发现真正的契约缺口，否则不修改异常继承关系。
- 不提供会掩盖畸形状态或提供方失败的通用建议。

验收标准：

- [ ] 文档将每个公共错误族群映射到示例和首步分类步骤。
- [ ] CLI 和操作手册引用均为具体命令。
- [ ] 测试保护矩阵的存在和关键命令字符串。
- [ ] 涉及安全的失败仍路由至私密报告渠道。

验证方式：

```bash
uv run pytest tests/test_docs_site.py tests/test_helper_validations.py
uv run mkdocs build --strict
```

### WF-PQDX-005：构建 CLI 与公共命令的文档漂移检查器

GitHub 议题：[#183](https://github.com/AbdelStark/worldforge/issues/183)

问题：CLI 帮助快照、README 片段、MkDocs 页面和 AGENTS 指南可能随着命令演进而产生漂移。

工作范围：

- 添加一个检查器，将已记录的高层命令与解析器帮助信息和打包入口点进行比对。
- 覆盖 README、CLI 参考、示例、操作文档、操作手册和 AGENTS 命令列表。
- 提供清晰的失败报告，说明过时或缺失的命令。

超出范围：

- 不自动重写文档散文。
- 不对文档进行大范围格式化重构。

验收标准：

- [ ] 当已记录的命令不再存在时，检查器报告失败。
- [ ] 检查器为新命令族群中缺失的公共命令文档报告缺失。
- [ ] CI 或已记录的质量关卡包含该检查器。
- [ ] 测试覆盖命令过时和命令缺失两种情况。

验证方式：

```bash
uv run pytest tests/test_cli_help_snapshots.py tests/test_docs_site.py
uv run mkdocs build --strict
```

### WF-PQDX-006：为核心检出路径添加性能回归预算

GitHub 议题：[#184](https://github.com/AbdelStark/worldforge/issues/184)

问题：提供方基准测试已存在，但核心框架操作可能在没有专项可安全检出性能关卡的情况下出现性能下降。

工作范围：

- 为世界状态持久化、基准测试夹具加载、提供方目录诊断、证据包创建和报告渲染添加可复现的预算。
- 在请求时将结果保留在运行工作区下。
- 在收紧预算前记录机器环境注意事项和评审规则。

超出范围：

- 不提供公开排行榜或跨机器性能声明。
- 不将硬件专用运行时基准测试作为默认关卡。

验收标准：

- [ ] 核心性能预算在无需凭据或可选运行时的情况下执行。
- [ ] 失败时包含保存的 JSON 和首步分类指导。
- [ ] 预算校准保持仅限评审状态。
- [ ] 文档区分回归检测与产品性能声明。

验证方式：

```bash
uv run pytest tests/test_benchmark.py tests/test_benchmark_budget_calibration.py tests/test_docs_site.py
uv run mkdocs build --strict
```

### WF-PQDX-007：创建贡献者引导诊断工具

GitHub 议题：[#185](https://github.com/AbdelStark/worldforge/issues/185)

问题：新贡献者在开始工作前需要快速诊断 Python、uv、包扩展项、文档工具链、GitHub CLI 和可选运行时边界的状态。

工作范围：

- 添加一个贡献者诊断命令或脚本，用于检查本地开发前提条件。
- 报告 Python 版本、uv 可用性、可编辑安装就绪状态、文档依赖、GitHub CLI 认证状态和可选运行时跳过原因。
- 保持输出无敏感值，且可安全粘贴到公开议题中。

超出范围：

- 不安装依赖或密钥。
- 不假定可选运行时已存在。

验收标准：

- [ ] 诊断输出支持 JSON 和 Markdown 两种格式。
- [ ] 缺失的可选运行时视为跳过而非失败。
- [ ] 文档将贡献者设置失败引导至诊断工具。
- [ ] 测试通过夹具覆盖工具缺失、认证缺失和就绪三种状态。

验证方式：

```bash
uv run pytest tests/test_cli_doctor.py tests/test_docs_site.py
uv run mkdocs build --strict
```

### WF-PQDX-008：文档化供应链与工件完整性关卡

GitHub 议题：[#186](https://github.com/AbdelStark/worldforge/issues/186)

问题：包验证已存在，但发布读者需要针对 wheel 包、sdist、证据工件、哈希和未来签署的清晰完整性说明。

工作范围：

- 文档化当前的包契约和工件摘要接口。
- 在无需当前凭据的情况下，定义未来的 SBOM、溯源和签署预期。
- 链接发布证据、包契约、依赖审计和 GitHub 发布关卡。

超出范围：

- 不涉及生产签名服务。
- 除非单独规划，否则不进行可信发布迁移。

验收标准：

- [ ] 文档说明当前已验证的内容和尚待完成的工作。
- [ ] 发布检查清单包含哈希、包安装、依赖审计和证据链接。
- [ ] 不安全的工件和仅限本地的文件仍排除在公开包之外。
- [ ] 测试保护关键文档声明。

验证方式：

```bash
uv run pytest tests/test_package_contract_script.py tests/test_docs_site.py
uv run mkdocs build --strict
```

### WF-PQDX-009：强化跨平台包装器验证

GitHub 议题：[#187](https://github.com/AbdelStark/worldforge/issues/187)

问题：Shell 包装器和可选运行时命令在 macOS、Linux 或不同 Python 环境下最容易被破坏。

工作范围：

- 为可执行位、shebang 头、已记录的 `uv run` 调用和 Python 版本预期添加测试或静态检查。
- 覆盖机器人案例展示、LeWorldModel、GR00T、LeRobot 和包验证的脚本。
- 文档化宿主特定限制和回退命令。

超出范围：

- 除非经过明确验证，否则不声明 Windows 支持。
- 不在基础 CI 中安装可选运行时。

验收标准：

- [ ] 脚本可移植性检查在可安全检出的 CI 中运行。
- [ ] 包装器文档与实际命令和 Python 版本策略保持一致。
- [ ] 失败时指出确切的脚本和预期修复方式。
- [ ] 可选运行时命令保持由宿主方持有。

验证方式：

```bash
uv run pytest tests/test_leworldmodel_uv_tasks.py tests/test_robotics_showcase_ci.py tests/test_docs_site.py
uv run mkdocs build --strict
```

### WF-PQDX-010：开展文档信息架构审查

GitHub 议题：[#188](https://github.com/AbdelStark/worldforge/issues/188)

问题：文档增长迅速；提供方作者、操作人员、研究评估者和发布维护者需要更清晰的导航路径。

工作范围：

- 审查 MkDocs 导航、README 链接、快速入门、示例、操作手册、提供方文档和路线图页面。
- 在不删除技术细节的前提下，提出并实施更紧凑的导航结构。
- 添加文档测试以保护预期的读者路径。

超出范围：

- 不进行营销性改写。
- 不删除路线图历史或证据记录。

验收标准：

- [ ] 提供方作者、操作人员、评估/研究用户和发布维护者均有主要文档入口。
- [ ] 路线图历史可被发现，但不与当前工作混淆。
- [ ] 导航和 SUMMARY 保持同步。
- [ ] MkDocs 严格模式构建保持干净。

验证方式：

```bash
uv run pytest tests/test_docs_site.py
uv run mkdocs build --strict
```

## 方向二：演示、端到端案例展示与使用场景

目标：通过严肃、可复现的端到端演练，展示现有框架能力，在不过度声明模型保真度的情况下，端到端地证明工作流程。

### WF-DEMO-001：构建首次运行本地世界工作流

GitHub 议题：[#189](https://github.com/AbdelStark/worldforge/issues/189)

问题：用户可以运行许多命令，但从安装到持久化世界、预测再到导出的首次运行路径需要一个完整、精良的演练。

工作范围：

- 使用 mock 提供方和本地 JSON 持久化，添加可安全检出的首次运行演示。
- 保留命令输出、导出的世界 JSON、历史记录和预检结果。
- 在 README、快速入门、示例和 CLI 文档中链接该流程。

超出范围：

- 不依赖可选运行时或凭据。
- 不声明物理保真度。

验收标准：

- [ ] 单条已记录的命令或脚本可运行完整的首次运行工作流。
- [ ] 演示验证世界创建、对象变更、预测、导出和预检。
- [ ] 输出的确定性程度足以用于测试。
- [ ] 文档说明预期的成功信号和首步分类步骤。

验证方式：

```bash
uv run pytest tests/test_cli_world_commands.py tests/test_world_lifecycle.py tests/test_docs_site.py
uv run mkdocs build --strict
```

### WF-DEMO-002：添加从提供方诊断到议题包的演练

GitHub 议题：[#190](https://github.com/AbdelStark/worldforge/issues/190)

问题：诊断、运行工作区和议题包功能十分强大，但尚未作为一个完整的操作故事呈现。

工作范围：

- 添加一个演示，创建一次失败或跳过的提供方诊断运行，导出安全的议题包，并展示确切的工件树。
- 包含 JSON 和 Markdown 两种输出格式。
- 记录如何安全地将结果附加到公开议题中。

超出范围：

- 不使用真实的提供方凭据。
- 公开工件中不包含原始日志或仅限本地的文件。

验收标准：

- [ ] 演示创建保留的运行清单和议题包。
- [ ] 包的 `safe_to_attach` 行为得到断言。
- [ ] 文档包含命令、预期文件和失败分类处理方式。
- [ ] 测试覆盖演示路径。

验证方式：

```bash
uv run pytest tests/test_issue_bundle_export.py tests/test_harness_workspace.py tests/test_docs_site.py
uv run mkdocs build --strict
```

### WF-DEMO-003：创建机器人案例展示引导回放

GitHub 议题：[#191](https://github.com/AbdelStark/worldforge/issues/191)

问题：机器人案例展示拥有强大的运行时模块，但用户需要一个引导式回放工件，以解释策略结果、打分结果、候选动作选择和安全边界。

工作范围：

- 使用打包的确定性工件添加可安全检出的回放模式。
- 为选定的动作块、打分原理、mock 执行和 Rerun 工件引用渲染逐步摘要。
- 将真实的 PushT 运行时路径与回放路径分离。

超出范围：

- 不涉及机器人控制。
- 回放路径中不下载检查点。

验收标准：

- [ ] 回放无需 LeRobot、LeWorldModel、torch 或仿真依赖即可运行。
- [ ] 真实运行时命令仍记录为已准备好宿主的路径。
- [ ] 回放工件可安全附加。
- [ ] 测试覆盖回放清单和文档。

验证方式：

```bash
uv run pytest tests/test_robotics_showcase.py tests/test_rerun_integration.py tests/test_docs_site.py
uv run mkdocs build --strict
```

### WF-DEMO-004：添加提供方事件脱敏空运行案例展示

GitHub 议题：[#192](https://github.com/AbdelStark/worldforge/issues/192)

问题：用户需要一个安全的提供方事件脱敏空运行案例，以便在将诊断证据附加到 issue 或发布说明之前检查输出。

工作范围：

- 构建一个由夹具驱动的空运行，演练提供方事件的成功和失败处理逻辑。
- 保留经净化的运行清单、提供方事件和工件摘要。
- 文档化已准备好宿主的实况冒烟测试后续命令。

超出范围：

- 可安全检出模式下不进行付费 API 调用。
- 不在仓库中存储提供方持有的工件。

验收标准：

- [ ] 空运行覆盖已脱敏的提供方事件夹具路径。
- [ ] 签名 URL 和保留警告可见但已脱敏。
- [ ] 文档区分空运行证据与实况提供方证据。
- [ ] 测试覆盖案例展示工件。

验证方式：

```bash
uv run pytest tests/test_demo_showcases.py tests/test_cosmos_policy_smoke_script.py tests/test_docs_site.py
uv run mkdocs build --strict
```

### WF-DEMO-005：构建适配器作者旅程演示

GitHub 议题：[#193](https://github.com/AbdelStark/worldforge/issues/193)

问题：提供方作者拥有脚手架和工作台工具，但缺少一条从想法到脚手架再到证据缺口的可视化完整路径。

工作范围：

- 添加一个演示，将虚构的提供方脚手架到临时目录，运行生成的测试，运行工作台，并报告晋升阻碍项。
- 仅将生成的文件保留在临时目录或已记录的演示输出目录下。
- 在提供方编写文档中链接该旅程。

超出范围：

- 不声明演示提供方是真实的。
- 不在临时/演示输出之外修改仓库。

验收标准：

- [ ] 演示证明脚手架、生成的测试、文档存根、运行时清单存根和工作台报告均已就位。
- [ ] 输出明确标注提供方脚手架尚不完整。
- [ ] 测试断言生成的演示文件不会出现在受跟踪的源代码中。
- [ ] 文档说明如何将该路径适配到真实提供方。

验证方式：

```bash
uv run pytest tests/test_provider_scaffold_script.py tests/test_provider_workbench.py tests/test_docs_site.py
uv run mkdocs build --strict
```

### WF-DEMO-006：创建批量评估宿主演练

GitHub 议题：[#194](https://github.com/AbdelStark/worldforge/issues/194)

问题：批量评估宿主已存在，但用户需要一个从输入夹具到预算关卡再到保留证据的完整故事。

工作范围：

- 添加一个演练，通过批量宿主运行评估和基准测试作业。
- 保留报告 JSON、Markdown、CSV、预算结果、清单和重新运行命令。
- 包含一条受控的预算失败路径。

超出范围：

- 不涉及生产调度器或队列。
- 不使用远程提供方凭据。

验收标准：

- [ ] 演练覆盖通过评估和预算关卡失败两种情况。
- [ ] 保留的工件已列出且可安全附加。
- [ ] 文档展示重新运行和分类处理命令。
- [ ] 测试覆盖命令输出和清单结构。

验证方式：

```bash
uv run pytest tests/test_batch_eval_host.py tests/test_harness_workspace.py tests/test_docs_site.py
uv run mkdocs build --strict
```

### WF-DEMO-007：扩展标准库服务宿主使用场景

GitHub 议题：[#195](https://github.com/AbdelStark/worldforge/issues/195)

问题：服务宿主示例很有用，但应当端到端地演示就绪状态、提供方诊断、运行范围的日志和安全的请求生命周期。

工作范围：

- 扩展标准库宿主示例，加入就绪状态、诊断、一次 mock 请求、提供方事件和关闭行为。
- 为响应结构和日志脱敏添加夹具测试。
- 文档化部署边界和回滚步骤。

超出范围：

- 不涉及托管服务平台。
- 不添加超出宿主方指导范围的认证层。

验收标准：

- [ ] 示例在测试中可以启动、处理请求、发出净化事件并正常关闭。
- [ ] 就绪响应标识提供方和能力状态。
- [ ] 文档展示预期的成功信号和首步分类命令。
- [ ] 宿主方责任保持明确。

验证方式：

```bash
uv run pytest tests/test_service_host.py tests/test_run_logs.py tests/test_docs_site.py
uv run mkdocs build --strict
```

### WF-DEMO-008：添加 Rerun 视觉画廊案例展示

GitHub 议题：[#196](https://github.com/AbdelStark/worldforge/issues/196)

问题：Rerun 支持功能强大，但分散在各演示和机器人流程中；精选的画廊将使视觉证据更易于审查。

工作范围：

- 添加一个可安全检出的视觉画廊脚本，记录世界快照、规划、基准测试摘要和机器人回放层。
- 写入本地 `.rrd` 文件和 JSON 清单。
- 文档化如何打开该工件以及每个层的含义。

超出范围：

- 不要求远程查看器。
- 不依赖实况机器人或模型运行时。

验收标准：

- [ ] 画廊使用 `rerun` 扩展项运行，缺失时清晰降级。
- [ ] 清单列出每个视觉层和来源工件。
- [ ] 文档包含打开命令和故障排查说明。
- [ ] 测试在无需 GUI 的情况下覆盖清单生成。

验证方式：

```bash
uv run pytest tests/test_rerun_integration.py tests/test_robotics_showcase.py tests/test_docs_site.py
uv run mkdocs build --strict
```

### WF-DEMO-009：创建故障恢复实验室

GitHub 议题：[#197](https://github.com/AbdelStark/worldforge/issues/197)

问题：操作人员演练和预检已存在，但用户需要一个有目的的实验室，在不触碰真实用户状态的前提下学习故障恢复。

工作范围：

- 添加一个脚本化实验室，在临时工作区下运行选定的演练、本地状态预检、运行包导出和恢复预览命令。
- 包含世界状态损坏、不安全工件路径和凭据缺失三种场景。
- 保留实验室报告工件。

超出范围：

- 不修改真实的 `.worldforge` 状态。
- 不使用真实凭据或安装可选运行时。

验收标准：

- [ ] 实验室在临时工作区下可安全检出运行。
- [ ] 报告列出预期失败、观察到的信号和恢复命令。
- [ ] 不安全的工件保持排除或脱敏状态。
- [ ] 文档引导操作人员在发生故障前先使用实验室。

验证方式：

```bash
uv run pytest tests/test_operator_drills.py tests/test_persistence_preflight.py tests/test_docs_site.py
uv run mkdocs build --strict
```

### WF-DEMO-010：发布使用场景手册

GitHub 议题：[#198](https://github.com/AbdelStark/worldforge/issues/198)

问题：用户需要面向任务的入口点，将使用场景映射到命令、提供方、工件和边界。

工作范围：

- 添加一个手册页面，涵盖本地世界实验、提供方编写、评估证据、基准测试预算、提供方事件脱敏空运行、机器人回放和发布证据。
- 每个示例应包含命令、预期输出、工件、首步分类步骤和不适用场景说明。
- 在 README 和示例文档中链接各示例。

超出范围：

- 不新增运行时集成。
- 不添加装饰性登陆页面。

验收标准：

- [ ] 手册包含至少七个面向任务的示例。
- [ ] 每个示例均指明宿主方责任和证据工件。
- [ ] README 和示例文档指向手册。
- [ ] 文档测试保护示例列表。

验证方式：

```bash
uv run pytest tests/test_docs_site.py tests/test_examples_index.py
uv run mkdocs build --strict
```

## 方向三：新功能

目标：在保持提供方运行时可选、类型安全且可测试的前提下，添加使 WorldForge 作为 Python 集成层更有用的能力。

### WF-FEAT-001：通过入口点添加提供方包发现机制

GitHub 议题：[#199](https://github.com/AbdelStark/worldforge/issues/199)

问题：外部适配器包需要一种无需修改 WorldForge 仓库即可注册提供方的简洁方式。

工作范围：

- 设计并实现提供方工厂的 Python 入口点发现机制。
- 保持自动注册为可选启用，并安全处理缺失的可选依赖。
- 文档化包元数据、工厂契约和失败行为。

超出范围：

- 不涉及应用市场或插件注册服务。
- 不静默加载依赖检查或凭据检查失败的提供方。

验收标准：

- [x] 外部包可通过已记录的入口点暴露提供方工厂。
- [x] 发现过程以明确原因报告跳过的提供方。
- [x] 仓库内现有目录行为保持不变。
- [x] 测试覆盖有效入口点、缺失依赖、重复名称和禁用发现四种情况。

验证方式：

```bash
uv run pytest tests/test_provider_catalog.py tests/test_provider_config.py tests/test_provider_entry_points.py tests/test_docs_site.py
uv run mkdocs build --strict
```

### WF-FEAT-002：为世界与运行添加场景定义格式

GitHub 议题：[#200](https://github.com/AbdelStark/worldforge/issues/200)

问题：重复的世界设置和评估场景仍分散在示例、夹具和临时 Python 代码中。

工作范围：

- 为世界对象、动作、目标、提供方选型和预期工件定义 JSON 原生场景格式。
- 为可安全检出的场景添加加载器验证和 CLI 执行功能。
- 包含用于本地 mock 世界和评估运行的示例场景。

超出范围：

- 不从场景文件执行任意 Python 代码。
- 不使用仿真器专用模式。

验收标准：

- [ ] 场景文件有模式版本控制且为 JSON 原生格式。
- [ ] CLI 可验证并运行可安全检出的场景。
- [ ] 无效场景失败时有明确提示并通过测试验证。
- [ ] 文档说明场景与提供方夹具的区别。

验证方式：

```bash
uv run pytest tests/test_world_lifecycle.py tests/test_cli_world_commands.py tests/test_docs_site.py
uv run mkdocs build --strict
```

### WF-FEAT-003：添加评估套件编写 API

GitHub 议题：[#201](https://github.com/AbdelStark/worldforge/issues/201)

问题：内置套件已存在，但外部用户需要一种受支持的方式来编写、注册和报告自定义确定性评估套件。

工作范围：

- 为场景、指标、失败用例和报告工件添加公共编写 API。
- 文档化套件版本控制、溯源和声明边界。
- 提供一个小型自定义套件示例。

超出范围：

- 不涉及排行榜服务。
- 不将非确定性打分作为默认路径。

验收标准：

- [x] 用户无需触碰内部模块即可定义和运行自定义套件。
- [x] 自定义报告在适用情况下包含溯源和失败画廊。
- [x] 测试覆盖自定义套件成功和无效指标载荷两种情况。
- [x] 文档解释套件编写方式和不适用声明。

验证方式：

```bash
uv run pytest tests/test_evaluation_suites.py tests/test_evaluation_failure_gallery.py tests/test_docs_site.py
uv run mkdocs build --strict
```

### WF-FEAT-004：添加本地运行工件索引

GitHub 议题：[#202](https://github.com/AbdelStark/worldforge/issues/202)

问题：保留的运行工作区积累了有用的证据，但用户除了列出清单外，无法对其进行搜索或汇总。

工作范围：

- 为 `.worldforge/runs` 添加一个索引器，汇总提供方、能力、状态、安全工件类型、日期和失败原因。
- 提供 JSON、Markdown 和 CSV 三种输出格式。
- 保持索引为只读，并安全处理损坏或过期的运行目录。

超出范围：

- 不涉及数据库、后台进程或多写入者存储。
- 不索引原始不安全工件。

验收标准：

- [ ] 索引命令处理有效、过期和格式错误的运行工作区。
- [ ] 输出默认可安全附加。
- [ ] 过滤器支持提供方、能力、状态、日期和工件类型。
- [ ] 文档说明保留和清理的交互关系。

验证方式：

```bash
uv run pytest tests/test_harness_workspace.py tests/test_harness_cli.py tests/test_docs_site.py
uv run mkdocs build --strict
```

### WF-FEAT-005：添加提供方路由与回退策略

GitHub 议题：[#203](https://github.com/AbdelStark/worldforge/issues/203)

问题：用户常常需要先尝试一个提供方，再回退到另一个，但临时的回退逻辑可能掩盖能力不匹配或提供方失败。

工作范围：

- 为首选提供方、回退提供方、能力要求和失败处理添加类型化路由策略模型。
- 在各次尝试中保留提供方错误和事件溯源信息。
- 支持可安全检出的 mock 示例和文档。

超出范围：

- 不涉及负载均衡器、SLA 承诺或远程编排。
- 不允许回退掩盖格式错误的提供方输出。

验收标准：

- [ ] 路由在调用前验证能力兼容性。
- [ ] 失败的尝试发出经净化的事件，并在结果中保持可见。
- [ ] 策略行为在测试中具有确定性。
- [ ] 文档说明何时适合使用回退以及何时不适合。

验证方式：

```bash
uv run pytest tests/test_providers.py tests/test_provider_events.py tests/test_docs_site.py
uv run mkdocs build --strict
```

### WF-FEAT-006：添加动作候选生成辅助函数

GitHub 议题：[#204](https://github.com/AbdelStark/worldforge/issues/204)

问题：策略加打分的规划需要动作候选集，但宿主目前必须从头构建候选集。

工作范围：

- 为常见的候选模式（如笛卡尔偏移、目标对象邻近、交换动作和有界移动网格）添加类型化辅助函数。
- 保持辅助函数与提供方无关，且为 JSON 原生格式。
- 文档化辅助函数如何为 `score` 和 `policy+score` 工作流提供输入。

超出范围：

- 不涉及特定任务的图像预处理。
- 不重新解释机器人动作空间。

验收标准：

- [x] 候选辅助函数返回经验证的 `Action` 序列。
- [x] 无效边界和非有限输入明确报错。
- [x] 规划示例使用辅助函数，且不改变提供方能力声明。
- [x] 测试覆盖辅助函数输出和打分-规划集成。

验证方式：

```bash
uv run pytest tests/test_evaluation_and_planning.py tests/test_leworldmodel_provider.py tests/test_docs_site.py
uv run mkdocs build --strict
```

### WF-FEAT-007：添加夹具快照管理器

GitHub 议题：[#205](https://github.com/AbdelStark/worldforge/issues/205)

问题：提供方夹具、基准测试输入和场景工件需要一致的摘要计算、元数据管理和漂移检查。

工作范围：

- 为夹具清单、SHA-256 摘要、模式版本和更新审查输出添加管理器。
- 覆盖能力夹具、提供方载荷夹具、基准测试输入和未来的场景。
- 保持更新操作明确且可审查。

超出范围：

- 不涉及大型数据集存储。
- 不自动从远程提供方刷新夹具。

验收标准：

- [x] 夹具清单验证在夹具引用缺失、变更或不安全时失败。
- [x] 审查输出区分有意更新和漂移。
- [x] 文档说明何时应更新夹具。
- [x] 测试覆盖清单加载、摘要不匹配和不安全路径三种情况。

验证方式：

```bash
uv run pytest tests/test_capability_fixtures.py tests/test_provider_runtime_manifests.py tests/test_docs_site.py
uv run mkdocs build --strict
```

### WF-FEAT-008：添加世界状态差异与补丁工件

GitHub 议题：[#206](https://github.com/AbdelStark/worldforge/issues/206)

问题：世界历史记录和预测存储快照，但用户需要一个紧凑的工件来解释两个世界状态之间的变化。

工作范围：

- 为场景对象、元数据、步骤、历史摘要和包围盒添加 JSON 原生差异和补丁工件。
- 通过 CLI 和 Python 辅助函数暴露用于比较持久化世界或导出 JSON 的接口。
- 为文档和议题包提供安全的渲染方式。

超出范围：

- 不涉及并发合并系统。
- 不在无效状态上静默应用补丁。

验收标准：

- [ ] 差异输出有模式版本控制且为 JSON 原生格式。
- [ ] 补丁验证拒绝路径穿越形式的 ID、无效对象和不连贯的包围盒。
- [ ] CLI 可比较两个持久化或导出的世界。
- [ ] 测试覆盖添加、更新、删除、无效补丁和文档示例五种情况。

验证方式：

```bash
uv run pytest tests/test_world_lifecycle.py tests/test_cli_world_commands.py tests/test_docs_site.py
uv run mkdocs build --strict
```

### WF-FEAT-009：为运行添加静态 HTML 报告导出

GitHub 议题：[#207](https://github.com/AbdelStark/worldforge/issues/207)

问题：JSON 和 Markdown 运行工件很有用，但与非开发人员共享本地证据通常需要一份单一的静态 HTML 报告。

工作范围：

- 为评估、基准测试、比较和议题包摘要添加静态 HTML 导出功能。
- 保持 HTML 自包含、经净化，并从现有安全工件生成。
- 文档化何时使用 HTML 与 JSON/Markdown。

超出范围：

- 不涉及托管仪表板。
- 不涉及 JavaScript 密集型应用程序。

验收标准：

- [ ] HTML 导出适用于已保留的评估和基准测试运行。
- [ ] 不安全工件被排除或标记为仅限本地。
- [ ] 测试检查转义、安全链接和报告元数据。
- [ ] 文档包含文件打开工作流和限制说明。

验证方式：

```bash
uv run pytest tests/test_harness_report_compare.py tests/test_evidence_bundle.py tests/test_docs_site.py
uv run mkdocs build --strict
```

### WF-FEAT-010：添加提供方能力协商报告

GitHub 议题：[#208](https://github.com/AbdelStark/worldforge/issues/208)

问题：用户可以检查提供方能力，但没有报告能在工作流运行前解释一组提供方是否能够满足该工作流的需求。

工作范围：

- 为需要能力集（如仅生成、仅打分、策略加打分、传输或评估/基准测试预设）的工作流添加协商报告。
- 包含提供方就绪状态、缺失配置、缺失可选运行时、不支持的能力和推荐的下一步命令。
- 通过 CLI 和 Python 暴露报告功能。

超出范围：

- 不自动安装或设置凭据。
- 默认不执行回退。

验收标准：

- [x] 报告区分已注册、已配置、依赖就绪和能力兼容四种状态。
- [x] 策略加打分工作流同时指明策略提供方和打分提供方。
- [x] 输出支持 JSON 和 Markdown 两种格式。
- [x] 测试覆盖就绪、配置缺失、依赖缺失和能力不支持四种情况。

验证方式：

```bash
uv run pytest tests/test_capability_negotiation.py tests/test_cli_doctor.py tests/test_provider_profiles.py tests/test_runtime_profiles.py tests/test_docs_site.py
uv run mkdocs build --strict
```

## 议题创建说明

- Nano World Model 因已另行分配，故仍从本路线图中排除。
- 方向标签：
  - `stream: production-quality`
  - `stream: demos-showcases`
  - `stream: new-features`
- 议题正文应保留本文档中的问题描述、工作范围、超出范围、验收标准、验证方式和来源指针。

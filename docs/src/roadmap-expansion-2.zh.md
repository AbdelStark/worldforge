# 路线图扩展 2

这是继提供方/平台生产轨道完成、延续计划以及第一批 30 个议题路线图扩展之后的第二批扩展。本批次刻意保持累加性：不重新开启已完成的生产级或案例展示工作，也不与第一次扩展中仍处于开放状态的功能议题重复。

计划仍分为相同的三大流，每流各包含十个实现议题：

- 生产级质量、开发体验与文档
- 演示、端到端案例展示与使用场景
- 新功能

每个议题均可独立推进，但部分演示议题有意依赖现有功能工作，以确保演示层跟随真实的产品层，而非另辟平行路径。共享约束保持不变：可选运行时由宿主方持有，提供方能力保持真实，确定性测试是契约信号而非物理保真度声明，公开工件必须安全可附加（除非明确标记为本地专用）。

## 流 1：生产级质量、开发体验与文档

目标：随着公开层面从单命令演示扩展到外部提供方包、场景文件、报告工件和发布凭证，使项目更难被误用、更易维护。

### WF-PQDX2-001：建立工件模式归属与迁移规则

GitHub 议题：[#227](https://github.com/AbdelStark/worldforge/issues/227)

标签：`documentation`、`roadmap`、`quality`、`artifacts`、`developer-experience`、`stream: production-quality`

问题：WorldForge 现已拥有多个 JSON 原生工件族，包括运行清单、议题包、场景、世界差异、HTML 报告元数据、基准测试输入和凭证摘要。贡献者需要一份归属映射，说明哪些模式是公开的、谁负责维护、版本如何演进，以及何时需要迁移或兼容性测试。

范围：

- 清点所有公开或半公开工件模式，并将其关联到所属模块、文档页面、测试和 CLI 入口点。
- 为累加性变更、破坏性变更、仅渲染器变更以及私有实现元数据定义模式版本升级规则。
- 添加文档或测试守卫，当新增公开工件族却缺少归属和迁移说明时触发失败。
- 提供可接受的兼容性垫片示例以及明确的无需迁移决策示例。

超出范围：

- 不设全局模式注册表服务。
- 不为私有临时文件、缓存内部数据或本地专用非安全工件提供兼容性承诺。

验收标准：

- [x] 文档列出所有公开工件模式、所有者、版本字段和验证层面。
- [x] 贡献者能判断模式变更何时需要迁移说明、更新日志文本和测试。
- [x] 至少有一个自动化守卫能捕获公开工件缺失模式归属的情况。
- [x] 现有工件保持 JSON 原生格式，安全工件边界保持明确。

验证：

```bash
uv run pytest tests/test_docs_site.py tests/test_public_api.py
uv run mkdocs build --strict
```

### WF-PQDX2-002：添加文档代码片段执行守卫

GitHub 议题：[#228](https://github.com/AbdelStark/worldforge/issues/228)

标签：`documentation`、`roadmap`、`quality`、`testing`、`developer-experience`、`ci`、`stream: production-quality`

问题：命令漂移已受到检查，但 Python 片段和小型 JSON 示例仍可能在文档中悄然过时，尤其是涉及场景、提供方路由、外部提供方和报告渲染的相关内容。

范围：

- 为文档中精选的 Python 和 JSON 代码块添加可安全检出的片段守卫。
- 从高价值页面开始：Python API、场景、提供方路由、外部提供方、基准测试、凭证包和世界差异。
- 对需要凭据、可选运行时或预先准备好的宿主资源的片段，要求添加明确的跳过标记。
- 当片段执行失败时，报告文件名、标题、语言和失败原因。

超出范围：

- 不执行可能改变用户状态的 Shell 片段。
- 不安装可选运行时或使用凭据。

验收标准：

- [x] 精选 Python 片段可在临时工作区中执行。
- [x] 精选 JSON 片段能够解析，并在存在模式的情况下满足预期模式。
- [x] 跳过标记能区分宿主方持有、需要凭据和仅供示意的片段。
- [x] 文档说明贡献者如何将新片段添加到守卫中。

验证：

```bash
uv run pytest tests/test_docs_site.py tests/test_snippet_gate.py
uv run mkdocs build --strict
```

### WF-PQDX2-003：构建可选依赖导入边界审计

GitHub 议题：[#229](https://github.com/AbdelStark/worldforge/issues/229)

标签：`documentation`、`roadmap`、`quality`、`optional-dependency`、`testing`、`ci`、`stream: production-quality`

问题：可选运行时是核心边界，但新模块可能意外地从基础包路径导入 Textual、Rerun、torch、LeRobot、stable-worldmodel、GR00T 或 Cosmos-Policy 依赖。

范围：

- 对基础包模块、CLI 启动以及非 TUI 的 harness 模块添加静态和导入时审计。
- 覆盖已知的可选边界：`harness`、`rerun`、`leworldmodel`、`lerobot`、`gr00t` 和 `cosmos-policy`。
- 记录允许的导入位置以及可选集成的延迟导入模式。
- 将审计纳入发布就绪或质量门禁。

超出范围：

- 不移除已支持的额外依赖。
- 不使用伪存根隐藏缺失的可选依赖。

验收标准：

- [x] 在未安装可选运行时包的情况下，基础导入可正常成功。
- [x] 当可选依赖泄漏到基础代码时，审计以精确的模块路径报告失败。
- [x] 文档标明哪些模块可以直接导入各可选运行时。
- [x] 现有的可选冒烟测试命令保留其宿主方持有的依赖行为。

验证：

```bash
uv run pytest tests/test_import_boundaries.py tests/test_public_api.py tests/test_docs_site.py
uv run mkdocs build --strict
```

### WF-PQDX2-004：添加确定性测试数据与时间控制

GitHub 议题：[#230](https://github.com/AbdelStark/worldforge/issues/230)

标签：`documentation`、`roadmap`、`quality`、`testing`、`reliability`、`stream: production-quality`

问题：报告、清单、基准测试摘要和发布凭证通常包含时间戳、耗时、ID、排序和临时路径。若缺乏确定性控制，回归测试要么过于脆弱，要么过于宽松而无法捕获真实漂移。

范围：

- 为稳定时钟、临时工作区、确定性 ID 和有序工件输出添加共享夹具或辅助 API。
- 将其应用于运行清单、议题包、基准测试报告、场景运行和发布凭证测试。
- 说明何时适合使用精确快照测试，何时语义断言更有力。

超出范围：

- 不尝试使真实提供方延迟具有确定性。
- 不进行影响宿主方持有的可选运行时的全局猴子补丁。

验收标准：

- [x] 工件渲染器的测试避免本地路径、时钟和排序方面的不稳定。
- [x] 辅助工具可供未来的报告和演示测试复用。
- [x] 文档为贡献者说明确定性夹具策略。
- [x] 现有运行时计时字段在真实运行中仍保持真实。

验证：

```bash
uv run pytest tests/test_harness_workspace.py tests/test_evidence_bundle.py tests/test_release_evidence.py tests/test_docs_site.py
uv run mkdocs build --strict
```

### WF-PQDX2-005：创建提供方配置契约索引

GitHub 议题：[#231](https://github.com/AbdelStark/worldforge/issues/231)

标签：`documentation`、`roadmap`、`provider`、`quality`、`developer-experience`、`operations`、`stream: production-quality`

问题：提供方配置要求分散在生成的提供方文档、`.env` 示例、运行时配置文件、冒烟测试脚本和操作手册中。运维人员需要一个与实际提供方元数据生成或核对的索引。

范围：

- 添加提供方配置索引，覆盖环境变量、可选包、凭据门禁、预先准备好的宿主资源、默认超时以及首要诊断命令。
- 将索引与提供方配置文件、生成的文档、`.env.example` 和冒烟命令文档进行核对。
- 区分脚手架、夹具测试、预先准备好的宿主以及实时冒烟的凭证级别。

超出范围：

- 不存储密钥或宿主本地端点值。
- 不进行超出现有诊断和冒烟边界的真实提供方验证。

验收标准：

- [x] 目录中的每个提供方都有包含必需和可选输入的配置行。
- [x] 索引能标记提供方文档或 `.env.example` 的漂移。
- [x] 脚手架提供方明确标注为脚手架行为。
- [x] 文档从提供方编写、运维和支持页面链接到该索引。

验证：

```bash
uv run pytest tests/test_provider_docs.py tests/test_provider_profiles.py tests/test_docs_site.py
uv run python scripts/generate_provider_docs.py --check
uv run mkdocs build --strict
```

### WF-PQDX2-006：添加面向用户的错误消息回归覆盖

GitHub 议题：[#232](https://github.com/AbdelStark/worldforge/issues/232)

标签：`documentation`、`roadmap`、`quality`、`testing`、`developer-experience`、`reliability`、`stream: production-quality`

问题：WorldForge 会抛出明确的错误族，但随着代码演进，CLI 和提供方消息仍可能变得不清晰、丢失分诊命令或泄漏内部实现细节。

范围：

- 为公开 CLI 和 Python 错误消息添加回归语料库，涵盖格式错误的世界状态、无效场景、不支持的能力、缺失的提供方配置、不安全工件和预算失败。
- 要求消息包含所有者上下文、首要分诊步骤以及适用时的安全措辞。
- 仅对稳定的面向用户文本保留精确快照；对有意可变的值使用语义断言。

超出范围：

- 不进行异常层级的全面重写。
- 在明确请求开发者/调试路径时，不抑制堆栈跟踪。

验收标准：

- [x] 主要公开失败模式的错误消息具有回归覆盖。
- [x] 安全敏感的失败不会打印密钥、签名 URL 或宿主本地的不安全负载。
- [x] CLI 失败在存在恢复路径时指向具体命令或文档。
- [x] 测试区分公开消息契约与私有实现细节。

验证：

```bash
uv run pytest tests/test_cli_world_commands.py tests/test_scenarios.py tests/test_helper_validations.py tests/test_docs_site.py
uv run mkdocs build --strict
```

### WF-PQDX2-007：构建贡献者任务启动包

GitHub 议题：[#233](https://github.com/AbdelStark/worldforge/issues/233)

标签：`documentation`、`roadmap`、`developer-experience`、`quality`、`testing`、`stream: production-quality`

问题：议题正文已足够详细，但贡献者仍需将每个路线图切片转化为要检查的文件、要运行的命令、要更新的文档层面以及要附上的验收凭证。

范围：

- 为提供方工作、纯文档工作、演示工作流、工件/报告工作、评估工作和 CLI 变更添加任务启动模板。
- 每个启动包应列出可能涉及的文件、禁止的捷径、验证命令、凭证工件和评审清单。
- 从贡献文档和议题模板链接到各启动包。

超出范围：

- 不自动创建分支、指派或 GitHub Project 自动化。
- 不取代维护者在编辑前实际阅读代码的职责。

验收标准：

- [x] 至少存在六个启动包，且与当前仓库结构一致。
- [x] 启动包包含验证命令以及文档/更新日志预期。
- [x] 议题模板或贡献文档将贡献者引导至合适的启动包。
- [x] 测试守卫必需章节的存在。

验证：

```bash
uv run pytest tests/test_docs_site.py
uv run mkdocs build --strict
```

### WF-PQDX2-008：从凭证与议题组装发布说明

GitHub 议题：[#234](https://github.com/AbdelStark/worldforge/issues/234)

标签：`documentation`、`roadmap`、`release`、`developer-experience`、`artifacts`、`stream: production-quality`

问题：发布就绪可以证明门禁通过，但维护者仍需手动从更新日志条目、议题关闭记录、公开 API 变更和凭证工件中组装人类可读的发布说明。

范围：

- 添加发布说明草稿命令，收集已变更的公开层面、按标签关闭的议题、验证摘要、文档链接以及已知注意事项。
- 将输出保留为可由维护者编辑的 Markdown 草稿工件。
- 包含新增、变更、修复、文档、验证、兼容性说明和宿主方持有的可选运行时凭证等章节。

超出范围：

- 不自动发布 GitHub Release。
- 不变更标签签名或可信发布工作流。

验收标准：

- [x] 命令从本地更新日志和可选 GitHub 议题数据生成 Markdown 草稿。
- [x] 草稿包含验证凭证引用和注意事项，不过度声明运行时行为。
- [x] 缺失更新日志或缺失验证凭证时，清晰报告。
- [x] 文档说明维护者如何在发布前评审和编辑草稿。

验证：

```bash
uv run pytest tests/test_release_notes.py tests/test_release_evidence.py tests/test_docs_site.py
uv run mkdocs build --strict
```

### WF-PQDX2-009：添加依赖审计凭证工件

GitHub 议题：[#235](https://github.com/AbdelStark/worldforge/issues/235)

标签：`documentation`、`roadmap`、`quality`、`security`、`release`、`artifacts`、`stream: production-quality`

问题：本地安全审计命令已有文档，但其结果未以发布评审可引用的一致凭证格式保存。

范围：

- 围绕已记录的 `uv export` 加 `pip-audit` 流程，添加依赖审计凭证包装器。
- 保留命令、依赖集、工具版本、状态、漏洞摘要、忽略的公告理由和首要分诊步骤。
- 保持生成的 requirements 文件为临时文件，避免提交环境特定的输出。

超出范围：

- 不实施自动漏洞抑制策略。
- 不接入远程依赖扫描服务。

验收标准：

- [x] 审计凭证写出 JSON 和 Markdown 摘要。
- [x] 漏洞发现被保留，不泄漏宿主本地路径或凭据。
- [x] 发布就绪文档和包验证文档链接到审计工件。
- [x] 测试通过夹具覆盖正常、发现漏洞和工具不可用三种路径。

验证：

```bash
uv run pytest tests/test_dependency_audit_evidence.py tests/test_docs_site.py
uv run mkdocs build --strict
```

### WF-PQDX2-010：发布质量仪表板工件

GitHub 议题：[#236](https://github.com/AbdelStark/worldforge/issues/236)

标签：`documentation`、`roadmap`、`quality`、`ci`、`artifacts`、`developer-experience`、`stream: production-quality`

问题：各个质量门禁已单独存在，但维护者需要一个本地工件，能一目了然地展示文档、测试、覆盖率、命令漂移、提供方文档、片段、包检查、审计状态和已知可选跳过项。

范围：

- 添加质量仪表板生成器，读取现有门禁输出，生成 JSON 和 Markdown。
- 包含状态、命令行、时间戳、跳过的宿主方检查以及首个失败门禁。
- 从发布就绪、贡献文档和运维文档链接到仪表板输出。

超出范围：

- 不设托管仪表板或徽章服务。
- 不削弱现有的各个门禁。

验收标准：

- [x] 仪表板聚合现有门禁输出，不隐藏原始失败细节。
- [x] 输出区分失败、警告、跳过和未运行的检查。
- [x] 文档说明仪表板与发布凭证的区别。
- [x] 测试覆盖混合通过/失败/跳过的聚合情况。

验证：

```bash
uv run pytest tests/test_quality_dashboard.py tests/test_release_evidence.py tests/test_docs_site.py
uv run mkdocs build --strict
```

## 流 2：演示、端到端案例展示与使用场景

目标：将下一层能力转化为严肃、可复现的工作流。这些演示应端到端地证实实际的仓库层面，同时清晰标注对剩余功能工作的依赖。

### WF-DEMO2-001：构建外部提供方包演示

GitHub 议题：[#237](https://github.com/AbdelStark/worldforge/issues/237)

标签：`documentation`、`roadmap`、`examples`、`provider`、`developer-experience`、`optional-dependency`、`stream: demos-showcases`

依赖：[WF-FEAT-001 #199](https://github.com/AbdelStark/worldforge/issues/199)

问题：入口点发现机制使外部提供方包成为可能，但用户需要一个可安全检出的演示，展示包的结构、元数据、注册行为、跳过原因以及文档/测试循环，而无需发布真实的适配器。

范围：

- 在 examples 目录或生成的临时输出中添加演示外部提供方包。
- 展示提供方发现已启用、发现已禁用、重复提供方处理以及缺失可选依赖的报告。
- 保留一份可安全粘贴到议题中的演示报告。

超出范围：

- 不进行真实的 PyPI 发布。
- 不进行真实的远程提供方调用或需要凭据的调用。

验收标准：

- [x] 演示通过已记录的入口点证实外部包发现。
- [x] 缺失的可选依赖显示明确的跳过原因。
- [x] 生成的或示例包文件在正常演示运行期间不改变已跟踪的源代码。
- [x] 文档从外部提供方和提供方编写页面链接到该演示。

验证：

```bash
uv run pytest tests/test_provider_entry_points.py tests/test_provider_scaffold_script.py tests/test_docs_site.py
uv run mkdocs build --strict
```

### WF-DEMO2-002：创建自定义评估套件演练

GitHub 议题：[#238](https://github.com/AbdelStark/worldforge/issues/238)

标签：`documentation`、`roadmap`、`examples`、`evaluation`、`developer-experience`、`artifacts`、`stream: demos-showcases`

依赖：[WF-FEAT-003 #201](https://github.com/AbdelStark/worldforge/issues/201)

问题：内置评估套件已有文档，但外部用户需要完整路径来构建一个包含确定性指标、失败案例画廊、溯源和报告工件的小型自定义套件。

范围：

- 添加一个演练，定义自定义套件，针对 mock 提供方运行，渲染 JSON/Markdown/HTML 报告，并保留失败工件。
- 包含无效指标和失败案例示例，让用户看清边界。
- 说明自定义套件声明的框架方式。

超出范围：

- 不设排行榜或质量排名。
- 不将非确定性模型打分作为默认示例。

验收标准：

- [x] 演练在干净检出环境中无需凭据或可选运行时即可运行。
- [x] 自定义套件输出包含溯源和失败画廊行为。
- [x] 文档说明确定性契约信号框架。
- [x] 测试覆盖演练的工件集。

验证：

```bash
uv run pytest tests/test_evaluation_suites.py tests/test_evaluation_failure_gallery.py tests/test_docs_site.py
uv run mkdocs build --strict
```

### WF-DEMO2-003：添加策略与打分候选实验室

GitHub 议题：[#239](https://github.com/AbdelStark/worldforge/issues/239)

标签：`documentation`、`roadmap`、`examples`、`score`、`policy`、`robotics`、`stream: demos-showcases`

依赖：[WF-FEAT-006 #204](https://github.com/AbdelStark/worldforge/issues/204)

问题：策略加打分规划是机器人场景的核心，但用户需要一个受控实验室，展示候选动作生成、候选打分、已选动作、原始策略动作保留以及宿主方持有的动作转换边界。

范围：

- 使用确定性候选辅助工具以及 mock/注入式策略和打分层面，添加可安全检出的实验室。
- 保留候选表格、打分元数据、已选动作，以及在可用时保留 Rerun 或 HTML 工件。
- 从 LeRobot、GR00T、LeWorldModel、规划以及机器人文档链接到该实验室。

超出范围：

- 不涉及机器人控制器、仿真器、检查点下载或动作空间重新解释。
- 不声称确定性打分能证明物理性能。

验收标准：

- [x] 实验室展示从候选生成到打分以及策略加打分规划的完整流程。
- [x] 无效的候选边界和缺失转换器的情况可见且经过测试。
- [x] 文档说明预先准备好的宿主机器人运行与实验室的区别。
- [x] 输出工件可安全附加。

验证：

```bash
uv run pytest tests/test_evaluation_and_planning.py tests/test_leworldmodel_provider.py tests/test_lerobot_provider.py tests/test_docs_site.py
uv run mkdocs build --strict
```

### WF-DEMO2-004：添加夹具漂移评审演练

GitHub 议题：[#240](https://github.com/AbdelStark/worldforge/issues/240)

标签：`documentation`、`roadmap`、`examples`、`testing`、`artifacts`、`developer-experience`、`stream: demos-showcases`

依赖：[WF-FEAT-007 #205](https://github.com/AbdelStark/worldforge/issues/205)

问题：夹具清单和摘要仅在贡献者能区分有意变更与意外漂移时才有价值。

范围：

- 添加一个演练，引入受控的夹具变更，运行快照管理器，展示评审输出，并演示已审批更新路径。
- 覆盖提供方负载夹具、基准测试输入、场景夹具以及不安全路径拒绝。
- 除非用户明确运行更新命令，否则所有变更保留在临时/演示输出中。

超出范围：

- 不进行远程夹具刷新。
- 不存储大型数据集。

验收标准：

- [x] 演练能区分夹具缺失、摘要不匹配、模式变更和不安全路径。
- [x] 已审批的更新路径明确且可评审。
- [x] 文档从测试和提供方编写页面链接。
- [x] 测试覆盖演示而不改变已跟踪的夹具。

验证：

```bash
uv run pytest tests/test_capability_fixtures.py tests/test_provider_runtime_manifests.py tests/test_docs_site.py
uv run mkdocs build --strict
```

### WF-DEMO2-005：创建能力协商预检演示

GitHub 议题：[#241](https://github.com/AbdelStark/worldforge/issues/241)

标签：`documentation`、`roadmap`、`examples`、`provider`、`operations`、`stream: demos-showcases`

依赖：[WF-FEAT-010 #208](https://github.com/AbdelStark/worldforge/issues/208)

问题：当用户能看到协商报告如何在凭据、依赖或提供方能力就绪之前阻止错误的工作流启动时，协商报告才最有价值。

范围：

- 添加一个演示，为仅生成、仅转换、仅打分、策略加打分以及评估工作流运行协商。
- 包含就绪、配置缺失、依赖缺失、不支持的能力以及未注册的示例。
- 保留 JSON 和 Markdown 报告以及首要推荐命令。

超出范围：

- 不自动安装或配置凭据。
- 默认情况下不进行回退执行。

验收标准：

- [x] 演示可安全检出，并覆盖至少五种工作流形态。
- [x] 报告明确指出阻碍工作流的具体提供方/能力槽。
- [x] 文档在预先准备好的宿主冒烟测试前引导用户进行协商。
- [x] 测试覆盖演示报告夹具。

验证：

```bash
uv run pytest tests/test_capability_negotiation.py tests/test_cli_doctor.py tests/test_docs_site.py
uv run mkdocs build --strict
```

### WF-DEMO2-006：添加跨提供方具身策略重放对比

GitHub 议题：[#242](https://github.com/AbdelStark/worldforge/issues/242)

标签：`documentation`、`roadmap`、`examples`、`policy`、`robotics`、`harness`、`stream: demos-showcases`

依赖：[GR00T 重放追踪 #226](https://github.com/AbdelStark/worldforge/issues/226)

问题：LeRobot、GR00T 和 Cosmos-Policy 均暴露策略式动作块，但用户需要一个并排重放，在不假装这些提供方可互换的前提下，对比契约形态、就绪状态、原始动作保留和转换器要求。

范围：

- 添加基于夹具的 LeRobot、GR00T 和 Cosmos-Policy 策略输出对比重放。
- 展示公共策略契约字段和提供方特定的原始动作元数据。
- 包含静态报告输出，使缺失的转换器和预先准备好的宿主要求可见。

超出范围：

- 不进行跨提供方动作空间转换。
- 不进行机器人执行或提出控制器安全声明。

验收标准：

- [x] 重放在不抹去提供方特定字段的情况下对比提供方策略契约。
- [x] 缺失转换器的行为明确且经过测试。
- [x] 文档说明每个提供方的预先准备好的宿主实时冒烟后续步骤。
- [x] 对比工件可安全附加。

验证：

```bash
uv run pytest tests/test_lerobot_provider.py tests/test_gr00t_provider.py tests/test_cosmos_policy_provider.py tests/test_docs_site.py
uv run mkdocs build --strict
```

### WF-DEMO2-007：发布本地世界与运行的场景画廊

GitHub 议题：[#243](https://github.com/AbdelStark/worldforge/issues/243)

标签：`documentation`、`roadmap`、`examples`、`persistence`、`evaluation`、`predict`、`stream: demos-showcases`

依赖：[WF-FEAT-002 #200](https://github.com/AbdelStark/worldforge/issues/200)

问题：当用户能从一个涵盖世界设置、预测、预期工件、评估运行和失败案例的小型画廊出发时，场景文件将更有价值。

范围：

- 添加至少包含五个可安全检出场景的场景画廊。
- 包含成功的世界设置、失败的预期、无效动作、面向评估的设置以及报告/导出示例。
- 说明场景与提供方夹具和演示案例展示脚本的区别。

超出范围：

- 不进行任意 Python 执行。
- 不使用仿真器特定的场景模式。

验收标准：

- [x] 画廊场景可通过 CLI 验证并运行。
- [x] 失败场景经过有意标注和测试。
- [x] 文档展示预期工件和首要分诊步骤。
- [x] 场景示例保持 JSON 原生且具有确定性。

验证：

```bash
uv run pytest tests/test_scenarios.py tests/test_cli_world_commands.py tests/test_docs_site.py
uv run mkdocs build --strict
```

### WF-DEMO2-008：添加发布就绪演练案例展示

GitHub 议题：[#244](https://github.com/AbdelStark/worldforge/issues/244)

标签：`documentation`、`roadmap`、`examples`、`release`、`quality`、`artifacts`、`stream: demos-showcases`

问题：发布就绪和包检查已存在，但维护者需要一个无意外的演练，精确展示凭证、更新日志检查、文档构建、依赖审计、包验证以及已知的可选跳过项如何组合在一起。

范围：

- 添加可安全检出的发布演练命令或已记录的脚本路径，运行非发布的凭证组装。
- 包含受控失败模式和干净通过夹具。
- 从发布文档、质量文档、运维以及更新日志指南链接到该演练。

超出范围：

- 不创建标签、发布、可信发布或签名。
- 不执行预先准备好的宿主可选运行时，除非作为链接凭证提供。

验收标准：

- [x] 演练生成发布凭证工件而不发布任何内容。
- [x] 受控失败说明首个失败门禁和首要分诊命令。
- [x] 文档区分演练凭证与实际发布审批。
- [x] 测试覆盖通过、失败和跳过可选运行时凭证三种情况。

验证：

```bash
uv run pytest tests/test_release_evidence.py tests/test_package_contract_script.py tests/test_docs_site.py
uv run mkdocs build --strict
```

### WF-DEMO2-009：创建面向非开发者的凭证评审演示

GitHub 议题：[#245](https://github.com/AbdelStark/worldforge/issues/245)

标签：`documentation`、`roadmap`、`examples`、`artifacts`、`harness`、`evaluation`、`stream: demos-showcases`

问题：JSON 和 CLI 输出适合维护者，但议题评审者、研究合作者和发布读者通常需要无需本地命令即可理解结果的静态工件。

范围：

- 添加一个演示，从评估、基准测试、世界差异和议题包工件创建静态 HTML 凭证包。
- 包含简短的评审者指南，说明什么是凭证、什么是本地专用，以及哪些声明不被支持。
- 覆盖转义和安全链接行为。

超出范围：

- 不设托管仪表板或 JavaScript 应用。
- 不嵌入不安全的本地文件或原始提供方负载。

验收标准：

- [x] 演示生成包含 HTML、JSON 和 Markdown 指针的单一可评审工件集。
- [x] 不安全工件被排除或标记为本地专用。
- [x] 文档说明如何将工件附加到议题或发布评审中。
- [x] 测试覆盖转义和工件清单结构。

验证：

```bash
uv run pytest tests/test_harness_report_compare.py tests/test_evidence_bundle.py tests/test_docs_site.py
uv run mkdocs build --strict
```

### WF-DEMO2-010：构建提供方失败模式画廊

GitHub 议题：[#246](https://github.com/AbdelStark/worldforge/issues/246)

标签：`documentation`、`roadmap`、`examples`、`provider`、`reliability`、`operations`、`stream: demos-showcases`

问题：支持文档描述了失败类别，但用户从展示解析器错误、提供方错误、重试耗尽、配置缺失、不支持的能力以及不安全工件处理的具体夹具示例中学习更快。

范围：

- 添加基于夹具的提供方失败模式画廊，包含预期事件、错误、工件和首要分诊命令。
- 在适当情况下覆盖 mock、可选运行时和脚手架提供方案例。
- 所有示例均可在无凭据的情况下安全运行。

超出范围：

- 不对付费或需要凭据的提供方进行实时调用。
- 不存储原始提供方密钥或签名 URL。

验收标准：

- [x] 画廊涵盖至少八种提供方失败模式。
- [x] 每个条目包含预期信号、所有者、首要分诊步骤以及安全工件行为。
- [x] 文档从支持、提供方文档和故障排除页面链接。
- [x] 测试验证画廊条目与真实错误行为保持一致。

验证：

```bash
uv run pytest tests/test_provider_contracts.py tests/test_cosmos_policy_provider.py tests/test_docs_site.py
uv run mkdocs build --strict
```

## 流 3：新功能

目标：添加类型化的框架能力，强化外部适配器工作、组合工作流检查、场景复用、凭证评审以及宿主方持有的可选运行时操作。

### WF-FEAT2-001：为预先准备好的宿主添加提供方生命周期钩子

GitHub 议题：[#247](https://github.com/AbdelStark/worldforge/issues/247)

标签：`enhancement`、`roadmap`、`provider`、`operations`、`optional-dependency`、`stream: new-features`

问题：可选提供方集成通常需要宿主特定的预检、设置、预热和清理行为，但 WorldForge 目前将这些步骤视为脚本层面的关注点。

范围：

- 为提供方预检、预热、清理和就绪凭证添加类型化的生命周期钩子。
- 保持钩子可选且由提供方持有，对现有提供方采用安全的默认行为。
- 通过诊断暴露生命周期状态，不从基础路径导入可选运行时。

超出范围：

- 不安装依赖或提供凭据。
- 不设长期运行的守护进程生命周期管理器。

验收标准：

- [x] 提供方可以实现生命周期钩子而无需变更现有的能力方法。
- [x] 诊断报告生命周期就绪状态和跳过原因。
- [x] 钩子对缺失的可选依赖是安全的。
- [x] 测试覆盖无操作、就绪、跳过、失败和清理失败状态。

验证：

```bash
uv run pytest tests/test_provider_profiles.py tests/test_cli_doctor.py tests/test_docs_site.py
uv run mkdocs build --strict
```

### WF-FEAT2-002：添加多运行回归对比报告

GitHub 议题：[#248](https://github.com/AbdelStark/worldforge/issues/248)

标签：`enhancement`、`roadmap`、`benchmark`、`artifacts`、`evaluation`、`stream: new-features`

问题：对保留工件的运行对比已存在，但维护者需要面向回归的报告，跨预算、指标、失败和工件形态变化对比当前运行与基线运行。

范围：

- 为评估、基准测试和演示案例展示运行添加回归对比模式。
- 报告指标差值、预算状态变化、新增失败、已消除失败、工件变更和溯源差异。
- 在现有渲染器支持的情况下输出 JSON、Markdown 和 HTML。

超出范围：

- 不进行跨机器性能声明。
- 不自动更新基线。

验收标准：

- [x] 用户可以将候选运行与保留的基线运行进行对比。
- [x] 报告区分指标差值、预算违规和工件漂移。
- [x] 不安全工件仍从渲染报告中排除。
- [x] 测试覆盖改进、退步、缺失基线和不兼容模式四种情况。

验证：

```bash
uv run pytest tests/test_harness_report_compare.py tests/test_benchmark.py tests/test_docs_site.py
uv run mkdocs build --strict
```

### WF-FEAT2-003：添加场景参数矩阵

GitHub 议题：[#249](https://github.com/AbdelStark/worldforge/issues/249)

标签：`enhancement`、`roadmap`、`evaluation`、`persistence`、`testing`、`stream: new-features`

问题：场景适用于一个具体的世界设置，但用户需要一种安全方式来运行小型参数扫描，而无需嵌入 Python 代码或复制大量几乎相同的 JSON 文件。

范围：

- 为场景文件添加 JSON 原生参数矩阵扩展。
- 支持对对象位置、动作目标、提供方名称和预期工件值的有界替换。
- 生成每个用例的结果以及聚合报告。

超出范围：

- 不引入任意表达式语言。
- 不设分布式或长期运行的调度器。

验收标准：

- [x] 矩阵场景在执行前通过验证，并拒绝无界或非 JSON 原生的值。
- [x] CLI 在临时或已配置的工作区中运行每个用例。
- [x] 聚合输出报告通过/失败计数和失败用例详情。
- [x] 测试覆盖有效矩阵、无效替换、失败预期和文档示例。

验证：

```bash
uv run pytest tests/test_scenarios.py tests/test_cli_world_commands.py tests/test_docs_site.py
uv run mkdocs build --strict
```

### WF-FEAT2-004：添加评估数据集清单契约

GitHub 议题：[#250](https://github.com/AbdelStark/worldforge/issues/250)

标签：`enhancement`、`roadmap`、`evaluation`、`artifacts`、`security`、`stream: new-features`

问题：外部评估套件可能引用夹具、数据集或预先准备好的宿主资源，但 WorldForge 需要一个清单契约来记录溯源和安全性，而无需将大型数据拉入仓库。

范围：

- 添加数据集清单模型，用于本地夹具、远程引用、校验和、许可证说明、隐私/安全标志以及宿主方持有的获取步骤。
- 将清单与评估溯源和议题/发布凭证集成。
- 拒绝不安全路径和缺失必要溯源字段的情况。

超出范围：

- 不提供数据集下载器。
- 不在仓库中存储大型数据集。

验收标准：

- [x] 数据集清单为 JSON 原生、有模式版本且经过验证。
- [x] 评估报告可以引用数据集清单而无需嵌入数据集。
- [x] 不安全或规格不足的清单明确失败。
- [x] 文档说明许可证/溯源边界以及宿主方持有的资源。

验证：

```bash
uv run pytest tests/test_evaluation_suites.py tests/test_evidence_bundle.py tests/test_docs_site.py
uv run mkdocs build --strict
```

### WF-FEAT2-005：为外部适配器添加提供方契约 CLI

GitHub 议题：[#251](https://github.com/AbdelStark/worldforge/issues/251)

标签：`enhancement`、`roadmap`、`provider`、`testing`、`developer-experience`、`stream: new-features`

问题：测试用的提供方契约辅助工具已存在，但外部适配器作者需要一个 CLI，能针对已安装的提供方运行相关契约检查并生成可附加到议题的凭证。

范围：

- 为已注册的提供方或直接工厂路径添加 `worldforge provider contract` 命令。
- 根据声明的能力和提供方配置元数据选择检查项。
- 生成包含通过检查、跳过的宿主方检查、失败项和后续步骤的 JSON 和 Markdown 凭证。

超出范围：

- 不自动推广提供方。
- 除非宿主明确配置，否则不进行实时提供方调用。

验收标准：

- [x] CLI 能为 mock 和基于夹具的提供方运行契约检查。
- [x] 不支持或未实现的声明能力明确失败。
- [x] 输出可安全附加并包含验证命令。
- [x] 文档从提供方编写和外部提供方文档链接到该 CLI。

验证：

```bash
uv run pytest tests/test_provider_contracts.py tests/test_provider_entry_points.py tests/test_docs_site.py
uv run mkdocs build --strict
```

### WF-FEAT2-006：添加运行时资源清单与缓存策略辅助工具

GitHub 议题：[#252](https://github.com/AbdelStark/worldforge/issues/252)

标签：`enhancement`、`roadmap`、`optional-dependency`、`operations`、`artifacts`、`stream: new-features`

问题：预先准备好的宿主运行时依赖检查点、对象文件、Hugging Face 资源和缓存位置，但 WorldForge 缺少一个类型化清单来描述这些资源，而无需持有或下载它们。

范围：

- 添加运行时资源清单模型，用于路径、来源、修订版本、校验和、大小、缓存根目录、本地专用状态和重建命令。
- 将清单与可选冒烟报告和运行清单集成。
- 为 LeWorldModel、LeRobot、GR00T、Cosmos-Policy 以及未来的候选提供方记录缓存策略预期。

超出范围：

- 不提供资源下载管理器。
- 不提交检查点、数据集或生成的对象文件。

验收标准：

- [x] 运行时资源清单分别验证本地专用和可附加字段。
- [x] 可选冒烟输出可以引用清单而无需嵌入资源。
- [x] 文档说明缓存清理、重建以及凭证边界。
- [x] 测试覆盖有效、缺失、不安全和本地专用清单四种情况。

验证：

```bash
uv run pytest tests/test_runtime_profiles.py tests/test_robotics_showcase.py tests/test_docs_site.py
uv run mkdocs build --strict
```

### WF-FEAT2-007：添加非密钥配置文件

GitHub 议题：[#253](https://github.com/AbdelStark/worldforge/issues/253)

标签：`enhancement`、`roadmap`、`operations`、`provider`、`developer-experience`、`stream: new-features`

问题：用户反复提供提供方名称、工作区路径、超时、报告格式和预先准备好的宿主缓存设置，但 WorldForge 没有可安全共享的类型化非密钥配置文件。

范围：

- 为非密钥默认值添加 JSON 或 TOML 配置文件。
- 在安全的情况下支持提供方选择、工作区目录、输出格式、超时/重试预设以及可选运行时缓存根目录。
- 密钥和凭据仅保留在环境变量或宿主方持有的密钥存储中。

超出范围：

- 不设密钥管理器。
- 不设全局可变的服务配置。

验收标准：

- [x] 配置文件在适用情况下拒绝类似密钥的键和不安全路径。
- [x] CLI 命令可以选择使用配置文件而不改变现有默认值。
- [x] 配置文件溯源出现在运行清单中。
- [x] 文档说明哪些内容适合放入配置文件，哪些不适合。

验证：

```bash
uv run pytest tests/test_provider_config.py tests/test_harness_workspace.py tests/test_docs_site.py
uv run mkdocs build --strict
```

### WF-FEAT2-008：添加报告渲染器扩展点

GitHub 议题：[#254](https://github.com/AbdelStark/worldforge/issues/254)

标签：`enhancement`、`roadmap`、`artifacts`、`developer-experience`、`harness`、`stream: new-features`

问题：JSON、Markdown、CSV 和 HTML 报告覆盖了内置工作流，但外部套件和宿主应用需要一种受支持的方式来添加安全渲染器，而无需修改内部模块。

范围：

- 为安全报告格式和工件族添加渲染器注册 API。
- 验证渲染器元数据、声明的安全行为、支持的模式和输出媒体类型。
- 保持内置渲染器不变，使扩展失败明确可见。

超出范围：

- 不执行来自任意文件的不可信渲染器插件。
- 不设 Web 仪表板。

验收标准：

- [x] 外部代码可以为受支持的工件族注册渲染器。
- [x] 渲染器输出被标记为可安全附加或本地专用。
- [x] 无效的渲染器元数据明确失败。
- [x] 测试覆盖内置渲染器、自定义渲染器、重复格式和不安全输出四种情况。

验证：

```bash
uv run pytest tests/test_harness_report_compare.py tests/test_evidence_bundle.py tests/test_docs_site.py
uv run mkdocs build --strict
```

### WF-FEAT2-009：添加世界状态迁移预览工具

GitHub 议题：[#255](https://github.com/AbdelStark/worldforge/issues/255)

标签：`enhancement`、`roadmap`、`persistence`、`reliability`、`artifacts`、`stream: new-features`

问题：本地 JSON 持久化有意保持简单，但模式变更和导入的世界需要一条预览路径，在任何状态被重写之前展示将发生什么变化。

范围：

- 为持久化的世界和导出的世界 JSON 添加迁移预览命令。
- 报告模式版本、所需变更、无效字段、不安全 ID、边界框修正以及迁移是否可以安全应用。
- 将实际重写保留为明确的第二步（如已实现）。

超出范围：

- 不设并发迁移服务。
- 不静默修复格式错误的世界状态。

验收标准：

- [x] 默认情况下预览为只读，并在测试中作用于临时副本。
- [x] 无效状态报告确切的失败原因，而非静默强制转换。
- [x] 输出可安全附加到议题。
- [x] 文档说明导入/导出和本地持久化迁移边界。

验证：

```bash
uv run pytest tests/test_world_lifecycle.py tests/test_persistence_preflight.py tests/test_docs_site.py
uv run mkdocs build --strict
```

### WF-FEAT2-010：添加组合工作流跟踪工件

GitHub 议题：[#256](https://github.com/AbdelStark/worldforge/issues/256)

标签：`enhancement`、`roadmap`、`observability`、`artifacts`、`provider`、`stream: new-features`

问题：提供方事件描述单个操作，但策略加打分规划、批量评估、场景矩阵和演示案例展示等组合工作流需要一个紧凑的跟踪工件，以说明步骤顺序、提供方边界、工件和失败传播。

范围：

- 为组合操作添加 JSON 原生工作流跟踪模型。
- 记录步骤 ID、操作名称、提供方/能力槽、输入/输出工件引用、状态、计时、经过净化的错误摘要以及父子关系。
- 在现有集成支持的情况下，将跟踪渲染为 Markdown 以及可选的 Rerun/HTML 层。

超出范围：

- 不设分布式追踪后端。
- 不捕获原始提示词、张量、凭据或机器人控制器遥测。

验收标准：

- [x] 组合工作流可以生成跟踪工件而无需改变提供方能力语义。
- [x] 跟踪工件经过净化且有模式版本。
- [x] 失败传播可见，不隐藏原始提供方错误。
- [x] 测试覆盖成功、跳过、失败和嵌套工作流跟踪四种情况。

验证：

```bash
uv run pytest tests/test_provider_events.py tests/test_evaluation_and_planning.py tests/test_rerun_integration.py tests/test_docs_site.py
uv run mkdocs build --strict
```

## 议题创建说明

- 现有开放议题继续有效，并在本次扩展依赖它们时被引用。
- 流标签：
  - `stream: production-quality`
  - `stream: demos-showcases`
  - `stream: new-features`
- 批次标签：
  - `roadmap: expansion-2`
- 议题正文应保留本文档中的问题、范围、超出范围、验收标准、验证、依赖和来源指针。

# 贡献者任务起步

使用这些任务起步包，将一个 Issue 转化为有边界的贡献计划。它们并不能替代编辑前阅读代码和文档的过程，而是作为默认检查清单，列出需要检查的文件、应避免的捷径、需要运行的验证步骤，以及需要附上的证据工件。

在开启 Pull Request 之前，请选择最接近的任务起步。若一个 Issue 跨越多个任务起步，则采用各涉及面中更严格的验证和证据要求。

每个任务起步均有意包含文档与变更日志的预期，以确保用户可见的行为、公开指引和发布说明保持一致。

## 提供方适配器或运行时晋级

适用于提供方脚手架、运行时清单、能力晋级、提供方解析器修复、可选运行时冒烟测试，或提供方文档。

### 建议检查的文件

- `src/worldforge/providers/`
- `src/worldforge/providers/catalog.py`
- `src/worldforge/providers/runtime_manifests/`
- `src/worldforge/testing/`
- `tests/fixtures/providers/`
- `docs/src/providers/`
- `docs/src/provider-authoring-guide.md`
- `docs/src/provider-configuration-index.md`
- `.env.example`

### 常见需更新的文件

- 提供方实现、解析器、运行时清单及提供方专属测试。
- 通过 `scripts/generate_provider_docs.py` 生成的提供方文档。
- 当配置、命令或故障模式发生变化时，更新 `.env.example`、`docs/src/providers/<provider>.md`、`docs/src/operations.md` 及 `docs/src/playbooks.md`。
- 对于用户可见的行为或新贡献者约束，更新 `CHANGELOG.md` 和 `AGENTS.md`。

### 禁止的捷径

- 除非能力已端到端实现，否则不得声明 `predict`、`embed`、`score` 或 `policy`。
- 不得将可选运行时、机器人技术栈、检查点、数据集或 CUDA 包添加到基础依赖集中。
- 不得在缺少必要配置的情况下自动注册可选提供方。
- 不得将脚手架或确定性 mock 行为呈现为真实的上游集成。
- 不得提交凭据、签名 URL、私有端点、宿主本地路径、检查点或已下载资产。

### 验证命令

```bash
uv run pytest tests/test_provider_docs.py tests/test_provider_profiles.py tests/test_provider_contracts.py
uv run python scripts/generate_provider_docs.py --check
uv run python scripts/check_optional_import_boundaries.py
uv run mkdocs build --strict
```

准备好宿主或实时运行时的工作，还应指明提供方运行时清单中的冒烟命令，并附上经过脱敏处理的 `run_manifest.json` 或明确的阻塞说明。

### 证据工件

- `tests/fixtures/providers/` 下用于覆盖解析器和故障模式的夹具负载。
- 提供方契约测试输出及生成的提供方文档检查输出。
- 用于运行时晋级的脱敏 `run_manifest.json`、实时冒烟注册表条目，或明确的准备宿主阻塞说明。
- 更新后的提供方文档，包含命令、预期成功信号及首要排查步骤。

### 文档与变更日志预期

- 针对提供方行为变更，更新提供方文档和生成的目录表。
- 针对新增的公开环境变量，更新 `.env.example`。
- 当提供方变更影响公开行为或运维工作流时，更新 `docs/src/api/python.md`、`docs/src/architecture.md`、`docs/src/operations.md` 或 `docs/src/playbooks.md`。
- 为用户可见的变更添加 `CHANGELOG.md` 条目。

### 审查检查清单

- 能力元数据与已实现的行为一致。
- 缺少依赖项、缺少凭据、输入格式错误、上游输出格式错误及工件路径过期等情况均以公开错误的形式失败。
- 提供方事件和工件已脱敏处理。
- 测试覆盖了成功路径和已记录的故障模式。
- 文档未过度声明上游的保真度、可用性或物理安全性。

## 仅文档或公开接口

适用于 README、MkDocs 页面、贡献者文档、操作手册、路线图记录、命令示例，以及不改变运行时行为的公开措辞修正。

### 建议检查的文件

- `README.md`
- `CONTRIBUTING.md`
- `docs/src/`
- `mkdocs.yml`
- `docs/src/SUMMARY.md`
- `docs/src/docs-map.md`
- `CHANGELOG.md`
- `tests/test_docs_site.py`
- `scripts/check_docs_commands.py`
- `scripts/check_docs_snippets.py`

### 常见需更新的文件

- 所属文档页面及其链接的导航页面。
- 添加、删除或重命名页面时，更新 `mkdocs.yml` 和 `docs/src/SUMMARY.md`。
- 读者路径发生变化时，更新 `docs/src/docs-map.md`。
- 针对持久性公开文档契约，更新 `tests/test_docs_site.py`。
- 针对用户可见的文档或工作流新增，添加 `CHANGELOG.md` 条目。

### 禁止的捷径

- 不得手动编辑生成的提供方目录块。
- 不得添加在干净检出环境中已过时、无人维护或无法执行的示例命令。
- 在代码片段覆盖范围应适用时，不得将可执行的 Python 或 JSON 示例留为未标记状态。
- 不得利用文档声明超出现有证据范围的物理保真度、上游可用性或真实集成。

### 验证命令

```bash
uv run pytest tests/test_docs_site.py
uv run python scripts/check_docs_commands.py
uv run python scripts/check_docs_snippets.py
uv run mkdocs build --strict
```

### 证据工件

- 文档测试输出及严格模式 MkDocs 构建输出。
- 示例发生变更时，命令漂移和代码片段检查的输出。
- 截图为可选项，不能替代文档门控检查。

### 文档与变更日志预期

- 将新页面链接至 `mkdocs.yml`、`docs/src/SUMMARY.md` 以及相应的读者路径。
- 当导航或受众路由发生变化时，更新 `docs/src/docs-map.md`。
- 当文档变更影响公开工作流、验证门控或读者契约时，添加 `CHANGELOG.md` 条目。

### 审查检查清单

- 页面有唯一的所属契约，且不重复更深层的运维文档。
- 相对链接在严格模式 MkDocs 中可正常解析。
- 定义运维工作流的命令包含预期的成功信号或首要排查步骤。
- 公开措辞准确，避免夸大性声明。

## 演示或案例展示工作流

适用于检出即可运行的演示、打包演示入口点、案例展示工作流、手册配方，或准备宿主机器人学案例展示文档。

### 建议检查的文件

- `src/worldforge/demos/`
- `src/worldforge/harness/`
- `src/worldforge/smoke/`
- `scripts/demo_showcases.py`
- `scripts/robotics-showcase`
- `examples/`
- `docs/src/demo-showcases.md`
- `docs/src/use-case-cookbook.md`
- `docs/src/robotics-showcase.md`

### 常见需更新的文件

- 演示脚本、打包入口点、harness 流程元数据或检出即可运行的示例。
- 演示文档、手册配方、CLI 文档及操作手册。
- 覆盖工作流注册表、运行工作空间输出及已记录故障路径的测试。
- 当新工作流或命令成为公开贡献面的一部分时，更新 `CHANGELOG.md` 和 `AGENTS.md`。

### 禁止的捷径

- 检出即可运行的演示不得要求付费 API、GPU 运行时、检查点、机器人硬件或可选软件包。
- 不得将准备宿主的要求隐藏在看似检出即可运行的默认路径之后。
- 不得将未脱敏的宿主路径、私有端点、凭据或签名 URL 写入演示工件。
- 不得使用确定性夹具暗示真实的物理或媒体质量。

### 验证命令

```bash
uv run python scripts/demo_showcases.py list
uv run python scripts/demo_showcases.py run first-run --workspace-dir .worldforge/demo-showcases
uv run pytest tests/test_demo_showcases.py tests/test_harness_workspace.py
uv run mkdocs build --strict
```

准备宿主的演示应添加其仅健康检查或 `--json-only` 冒烟命令，并说明预期的跳过或通过状态。

### 证据工件

- 保存的运行工作空间，包含 `run_manifest.json`。
- 演示输出的 JSON、Markdown 或报告工件，标记为可安全附加。
- 可选运行时工作流的准备宿主冒烟清单或明确的跳过原因。

### 文档与变更日志预期

- 当命令或工件布局发生变化时，更新演示文档、手册配方、CLI 示例及操作手册。
- 当工作流成为读者路径时，更新 `docs/src/docs-map.md`。
- 为新增或实质性变更的工作流添加 `CHANGELOG.md` 条目。

### 审查检查清单

- 默认路径可在干净检出环境中运行，或明确声明了准备宿主的要求。
- 工作流写入确定性的、经脱敏处理的证据工件。
- 故障输出指明首要排查步骤。
- 可选依赖项保持由宿主方持有。

## 工件、报告或证据

适用于运行清单、证据包、Issue 包、发布证据、质量看板、静态 HTML 报告、运行索引、来源溯源、工件完整性或模式版本化输出。

### 建议检查的文件

- `src/worldforge/evidence_bundle.py`
- `src/worldforge/html_report.py`
- `src/worldforge/provenance.py`
- `src/worldforge/harness/workspace.py`
- `src/worldforge/harness/run_index.py`
- `src/worldforge/harness/report_compare.py`
- `src/worldforge/smoke/run_manifest.py`
- `scripts/generate_dependency_audit_evidence.py`
- `scripts/generate_quality_dashboard.py`
- `scripts/generate_release_evidence.py`
- `scripts/generate_release_notes.py`
- `docs/src/artifact-schemas.md`
- `docs/src/artifact-integrity.md`
- `docs/src/html-reports.md`
- `docs/src/run-index.md`

### 常见需更新的文件

- 工件模型、渲染器、验证器、确定性测试辅助工具及精确快照测试。
- 模式所有权文档及公开工件字段的 API 文档。
- 当工件生成成为运维工作流的一部分时，更新运维文档或操作手册。
- 针对模式、脱敏或发布门控变更，更新 `CHANGELOG.md` 和 `AGENTS.md`。

### 禁止的捷径

- 不得默默地强制转换无效的持久化或提供方提供的状态。
- 不得输出非 JSON 原生的元数据、元组形式的值、对象实例、非有限数字、凭据、签名 URL 或宿主本地路径。
- 不得在未验证底层数据模型的情况下更新渲染工件。
- 不得为了通过报告变更而削弱发布、软件包、覆盖率或工件完整性门控检查。

### 验证命令

```bash
uv run pytest tests/test_evidence_bundle.py tests/test_html_report.py tests/test_release_evidence.py
uv run pytest tests/test_harness_workspace.py tests/test_run_index.py tests/test_redaction_corpus.py
uv run pytest tests/test_quality_dashboard.py
uv run mkdocs build --strict
```

### 证据工件

- 稳定的 JSON、Markdown 或 HTML 夹具输出，在适用精确快照时使用确定性时钟、ID 和路径根。
- 针对每个面向日志或面向 Issue 的新字段，进行脱敏语料库覆盖。
- 当变更影响发布就绪性时，提供发布证据 JSON、质量看板输出或包输出。

### 文档与变更日志预期

- 针对新增或变更的公开工件族，更新 `docs/src/artifact-schemas.md`。
- 针对新字段、模式版本或迁移规则，更新工件专属文档及 API 文档。
- 为用户可见的工件、报告、模式或脱敏变更添加 `CHANGELOG.md` 条目。

### 审查检查清单

- 模式版本、所有者、验证器、文档入口点和测试保持一致。
- 精确快照使用确定性辅助工具，而非易变的时间戳、ID 或宿主路径。
- 公开错误消息和工件可安全附加。
- HTML 输出保持自包含，并对用户提供的文本进行转义处理。

## 评估或基准测试

适用于确定性评估套件、基准测试输入、预算、校准、支撑声明的报告、比较逻辑或评估失败画廊。

### 建议检查的文件

- `src/worldforge/evaluation/`
- `src/worldforge/benchmark.py`
- `src/worldforge/benchmark_calibration.py`
- `examples/benchmark-inputs.json`
- `examples/benchmark-budget.json`
- `docs/src/evaluation.md`
- `docs/src/benchmarking.md`
- `docs/src/claim-evidence-map.md`
- `docs/src/live-smoke-evidence.md`
- `tests/test_benchmark.py`

### 常见需更新的文件

- 评估套件、基准测试 harness、输入夹具、预算夹具、渲染器及测试。
- 当公开数字、门控检查或支持的能力形态发生变化时，更新声明到证据的文档。
- 当基准测试成为发布门控时，更新发布证据的接入。
- 为新增评估套件、基准测试操作、预算或报告行为添加 `CHANGELOG.md` 条目。

### 禁止的捷径

- 不得将确定性评估套件转化为物理保真度声明。
- 不得通过与已记录操作不同的能力进行基准测试。
- 不得在没有保存运行证据和说明理由的情况下更改预算。
- 不得在检出即可运行的基准测试中依赖实时可选运行时。

### 验证命令

```bash
uv run pytest tests/test_benchmark.py tests/test_evaluation_suites.py tests/test_evaluation_and_planning.py
uv run pytest tests/test_benchmark_budget_calibration.py
uv run worldforge benchmark --provider mock --operation predict --input-file examples/benchmark-inputs.json
uv run worldforge benchmark --provider mock --operation predict --budget-file examples/benchmark-budget.json
uv run mkdocs build --strict
```

### 证据工件

- 保存的基准测试 JSON、预算结果或校准报告。
- 确定性的输入夹具，当其支撑公开文档时需提交。
- 针对公开基准测试或评估声明，更新声明到证据的对应关系。

### 文档与变更日志预期

- 当行为或公开解释发生变化时，更新评估、基准测试、声明到证据以及发布门控文档。
- 仅在有测试证明夹具仍可正常加载的情况下，才更新 `examples/benchmark-inputs.json` 或 `examples/benchmark-budget.json`。
- 为用户可见的评估、基准测试或报告变更添加 `CHANGELOG.md` 条目。

### 审查检查清单

- 已明确指出提供方、能力、套件、预设、输入文件和预算文件。
- 指标为有限数字，内部一致，并从已验证的数据中渲染。
- 检出即可运行的测试保持确定性。
- 公开声明指向保存的证据，且不夸大运行时覆盖范围。

## CLI 或运维工作流

适用于 CLI 命令、公开错误行为、本地持久化命令、预检诊断、运维演练、运行清理、提供方诊断或恢复工作流。

### 建议检查的文件

- `src/worldforge/cli.py`
- `src/worldforge/framework.py`
- `src/worldforge/persistence_preflight.py`
- `src/worldforge/harness/`
- `src/worldforge/observability.py`
- `docs/src/cli.md`
- `docs/src/operations.md`
- `docs/src/playbooks.md`
- `docs/src/support.md`
- `tests/test_cli_help_snapshots.py`
- `tests/test_cli_world_commands.py`
- `tests/test_operator_drills.py`

### 常见需更新的文件

- CLI 解析器和命令处理器、公开 API 辅助工具、持久化或诊断辅助工具，以及 CLI 测试。
- 当命令文本有意变更时，更新帮助文本快照。
- CLI 文档、运维文档、操作手册、支持文档及故障排查矩阵。
- 为新命令、约束或故障边界，更新 `CHANGELOG.md` 和 `AGENTS.md`。

### 禁止的捷径

- 不得在 CLI 错误、日志、清单或 Issue 包中泄露凭据、签名 URL 查询字符串、私有端点或宿主本地路径。
- 不得在没有可见恢复工件的情况下静默修复损坏的世界状态。
- 不得在没有设计记录的情况下添加服务级别的持久化、锁文件或数据库依赖项。
- 不得在基础 CLI 导入中引入可选的 TUI、Rerun、torch、LeRobot、GR00T、Cosmos-Policy 或 LeWorldModel 运行时。

### 验证命令

```bash
uv run worldforge --help
uv run pytest tests/test_cli_help_snapshots.py tests/test_cli_world_commands.py tests/test_operator_drills.py
uv run python scripts/check_docs_commands.py
uv run python scripts/check_optional_import_boundaries.py
uv run mkdocs build --strict
```

### 证据工件

- CLI 测试输出、帮助文本快照更新或命令输出夹具。
- 当工作流生成运维证据时，提供脱敏的预检、诊断、运行索引或 Issue 包工件。
- 文档中包含首要排查命令及预期的成功或失败信号。

### 文档与变更日志预期

- 针对新命令或运维行为，更新 `docs/src/cli.md`、`docs/src/operations.md`、`docs/src/playbooks.md` 及 `docs/src/support.md`。
- 当命令行为公开或依赖某个公开 Python API 时，更新 `docs/src/api/python.md`。
- 为用户可见的 CLI 行为变更添加 `CHANGELOG.md` 条目。

### 审查检查清单

- CLI 错误包含命令所属上下文和首要排查步骤。
- 无效的公开输入以 `WorldForgeError` 失败；无效的持久化/提供方状态以 `WorldStateError` 失败；提供方/运行时故障以 `ProviderError` 失败。
- 帮助文本、文档命令和快照保持一致。
- 运维工件为 JSON 原生格式，可安全附加。

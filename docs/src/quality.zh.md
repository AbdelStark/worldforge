# 工程质量标准

WorldForge 将工程质量视为公开 API 的组成部分。提供方能力、包元数据、文档、测试和可选机器人运行时必须保持一致，确保用户能够清晰地了解已安装的内容、哪些是确定性的，以及哪些由宿主方持有。

## 参考基线

WorldForge 的质量规范以生产级 Python ML 框架应追踪的上游来源为基础：

- [Python 打包用户指南：`pyproject.toml` 元数据](https://packaging.python.org/specifications/declaring-project-metadata/)
  ——用于静态项目元数据、构建系统配置、SPDX 许可证元数据、入口点和依赖声明。
- [Python 打包用户指南：打包项目](https://packaging.python.org/tutorials/packaging-projects/)
  ——用于 `src` 布局打包和发行结构。
- [uv 包指南](https://docs.astral.sh/uv/guides/package/)——通过现代构建前端构建和发布包，同时保留后端契约。
- [pytest 良好集成实践](https://docs.pytest.org/en/stable/explanation/goodpractices.html)
  ——用于 `src` 布局的测试隔离和 `--import-mode=importlib`。
- [Ruff 代码检查配置](https://docs.astral.sh/ruff/linter/) 和
  [Ruff 格式化指南](https://docs.astral.sh/ruff/formatter/)——用于统一的快速代码检查与格式化工具链。
- [PEP 561](https://peps.python.org/pep-0561/) 和
  [类型分发规范](https://typing.python.org/en/latest/spec/distributing.html)——通过 `py.typed` 随包附带内联类型信息。
- [PyTorch 可复现性说明](https://docs.pytorch.org/docs/stable/notes/randomness.html)——用于诚实表述 ML 确定性边界：种子可在同一平台和版本内降低不确定性，但无法保证跨版本、跨设备或跨平台的精确结果。
- [scikit-learn 开发者指南](https://scikit-learn.org/dev/developers/develop.html)——用于稳定的公开导入、估计器风格的验证规范和显式的随机性契约。
- [Scientific Python SPEC 0](https://scientific-python.org/specs/spec-0000/)——要求科学 Python 项目记录支持窗口和依赖策略，而非让兼容性静默漂移。

## 项目规范

### 打包

- 包源码位于 `src/worldforge` 下，测试针对已安装/可导入的包语义运行，而非意外依赖仓库根路径的导入。
- `pyproject.toml` 是包元数据、Python 支持、脚本、可选扩展包、uv 包模式和工具配置的唯一事实来源。
- Wheel 仅包含运行时包文件。源代码发行版包含测试、文档、示例、脚本和发布元数据，以便下游用户检查和重新构建项目。
- `src/worldforge/py.typed` 是 wheel 契约的组成部分，移除它属于类型回归。
- 可选的 ML 和机器人运行时不纳入基础依赖集。`torch`、LeRobot、LeWorldModel、GR00T、CUDA、机器人控制器、检查点和数据集由宿主环境为具体的冒烟测试或案例展示提供。

### 测试

- `pytest` 使用 `--import-mode=importlib` 运行，确保测试不依赖隐式的 `sys.path` 修改。
- 测试夹具必须是确定性的，除非某个测试明确验证非确定性运行时的处理逻辑。
- 当工件测试和报告测试断言精确的 JSON 或 Markdown 快照时，应使用 `worldforge.testing.DeterministicClock`、`DeterministicIdFactory`、`deterministic_run_workspace`、`stable_snapshot` 和 `stable_json_dumps`。在比较文本之前，先对临时路径、生成的 ID 和已知的可变字段进行规范化处理。
- 精确快照适用于稳定的工件模式、渲染后面向用户的报告文本、命令片段、版本化清单和故障模板。对于真实的提供方延迟或吞吐量、宿主路径、当前 git 提交、实时时间戳、可选运行时告警，以及取决于宿主环境的其他值，请优先使用语义断言。
- 每种提供方能力必须同时具备正向契约测试和其所记录边界的故障模式测试。
- 可复用的提供方契约辅助工具必须使用显式异常，而非 Python `assert`，以防止适配器验证在优化模式下的 Python 中消失。
- 公开异常断言应对字面消息进行足够精确的匹配，以捕获回归，同时不依赖无关的文本。
- 公开 CLI 错误契约必须保留所有者上下文、初步排查步骤和安全措辞。回归测试仅对稳定消息断言精确文本；对于路径、时间、提供方端点和其他宿主方拥有的值，使用语义断言。
- `xfail` 是严格的。若某个测试开始通过，应进行调查，并将其晋升或移除。

### 代码检查与风格

- Ruff 负责 `src`、`tests`、`examples` 和 `scripts` 的格式兼容代码检查及导入排序。
- 强制执行的 Ruff 规则集涵盖推导式、返回值、简化、pytest 风格、性能陷阱以及 Ruff 原生正确性检查等类 bugbear 质量系列。
- 公开的 `__all__` 导出保持排序，确保公开 API 差异可读。
- 可变类元数据（如 Textual 的 `BINDINGS` 和 `SCREENS`）必须标注为 `ClassVar`，以将框架声明与实例状态分离。
- 测试使用直接的 `pytest` 导入，并在拆分复合断言有助于精准定位故障时进行拆分。

### ML 与机器人边界

- 仓库内的确定性套件是契约运行时，而非物理保真度的证据。
- 真实的机器人案例展示路径必须说明由哪个运行时负责预处理、检查点、观测、动作转换、安全检查和硬件执行。
- WorldForge 验证张量和动作边界；它不得对不匹配的动作空间进行填充、投影或重新解释。
- 打分提供方暴露 `score`，策略提供方暴露 `policy`，预测性世界模型暴露 `predict`。品牌宣传不得凌驾于可执行能力的真实性之上。
- 提供方事件是面向日志的记录。目标、消息和元数据在进入 JSON 日志、内存接收器或指标聚合之前必须保持脱敏处理。
- 下载的 PyTorch 权重文件默认通过 `torch.load(..., weights_only=True)` 加载。回退到 pickle 反序列化必须是显式的，且仅限于可信工件。

## 本地门禁

在发布行为、文档或发行包变更之前，从仓库根目录运行完整门禁：

```bash
uv lock --check
uv run ruff check src tests examples scripts
uv run ruff format --check src tests examples scripts
uv run python scripts/generate_provider_docs.py --check
uv run python scripts/check_docs_commands.py
uv run python scripts/check_docs_snippets.py
uv run python scripts/check_wrapper_portability.py
uv run python scripts/check_optional_import_boundaries.py
uv run python scripts/check_core_performance.py
uv run mkdocs build --strict
uv run pytest
uv run --extra harness pytest --cov=src/worldforge --cov-report=term-missing --cov-fail-under=90
bash scripts/test_package.sh
uv build --out-dir dist --clear --no-build-logs
```

本地门禁运行以下检查：锁文件校验、Ruff、生成的提供方文档漂移检查、已记录命令漂移检查、文档代码片段门禁、包装器可移植性检查、可选导入边界审计、检出安全的核心性能预算、严格模式 MkDocs 构建、完整 pytest、运行时覆盖率门禁、wheel/sdist 包契约以及发行包构建。文档代码片段门禁仅执行选定的 Python 片段，并仅解析选定的 JSON 片段；宿主方拥有的、需要凭据的和演示性示例需要显式的跳过标记。包装器可移植性检查验证脚本解释器（shebang）、可执行位、已记录的 `uv run` 命令以及 Python 3.13 要求，无需安装可选运行时。可选导入边界审计验证基础包导入、CLI 启动、`worldforge.rerun` 以及非 TUI 运行时模块不导入 Textual、Rerun、torch、stable-worldmodel、LeRobot、GR00T 或 Cosmos-Policy 包。允许的直接导入仅限于 `worldforge.harness.tui` 中的 Textual 以及已准备好宿主方冒烟模块中的 torch/stable-worldmodel；提供方适配器必须使用惰性导入或注入式运行时。核心性能预算门禁写入带有本地测量路径和声明边界的 JSON；它检测检出路径的回归，而非跨机器基准测试或可选运行时性能声明。在打发布标签之前，还需运行：

```bash
uv run python scripts/generate_dependency_audit_evidence.py
```

发布加固时，请使用 [运维](./operations.md) 中描述的依赖审计证据工作流。该工作流保留 JSON 和 Markdown 摘要，但不保留临时需求文件，并会在输出前清理原始详情的键和值。

如需在不发布的情况下预演发布准备情况，请运行：

```bash
uv run python scripts/release_readiness_drill.py
```

该演练会生成通过和受控失败的发布证据夹具，指出第一个失败的门禁和排查命令，并将可选运行时证据保留为显式的宿主方跳过项。这仅是质量预演；实际发布审批仍依赖当前的门禁输出、依赖审计证据、包验证和维护者评审。

若需要本地质量概览，请在发布证据、依赖审计证据和核心性能报告生成后，生成质量看板：

```bash
uv run python scripts/generate_quality_dashboard.py
```

看板默认写入 `.worldforge/quality-dashboard/quality-dashboard.json` 和 `.worldforge/quality-dashboard/quality-dashboard.md`。它读取已有的输出并将状态词汇规范化为 `passed`、`failed`、`warning`、`skipped` 和 `not-run`；它不执行门禁，也不替换原始工件。原始详情的键和值会在输出前被清理；被隐去后发生冲突的键会保留确定性后缀。发布证据用于发布声明和工件哈希，看板用于跨文档、测试、覆盖率、包检查、依赖审计、核心性能和宿主方可选跳过项的分支级别分类排查。

## 可选实时机器人 CI

常规 CI 工作流保持检出安全和确定性。真实的 LeRobot 加 LeWorldModel 推理运行在 `.github/workflows/robotics-showcase.yml` 中，因为它需要下载可选模型资产、构建或恢复 LeWorldModel 对象检查点，并运行宿主方拥有的运行时。

该工作流在每次拉取请求更新以及向 `main` 的推送时运行。它以非交互模式运行 `scripts/robotics-showcase`（`--json-only --no-tui --no-rerun`），然后验证 JSON 摘要和 `run_manifest.json` 中的健康提供方、成功的策略/打分事件、PushT 候选张量形状、打分数量和选定候选索引。

检查点缓存策略：

- 对 Hugging Face 策略下载、LeWorldModel 配置/权重资产、已构建的 LeWorldModel 对象检查点以及 uv 包缓存使用 `actions/cache`；
- 按操作系统、Python 3.13、uv 版本、LeRobot 版本、固定的 LeWorldModel Hugging Face 修订版本以及包装器/检查点构建器源文件对缓存进行键控；
- 将 `real-run.json`、`stdout.json` 和 `run_manifest.json` 作为短期保留的运行证据上传；
- 默认 CI 不上传检查点工件；使用 `actions/cache` 作为可复用的检查点机制。

# 贡献

WorldForge 的贡献应保持代码、测试、文档和智能体上下文的同步更新。

```bash
uv sync --group dev
uv lock --check
uv run ruff check src tests examples scripts
uv run ruff format --check src tests examples scripts
uv run python scripts/generate_provider_docs.py --check
uv run python scripts/check_docs_commands.py
uv run python scripts/check_docs_snippets.py
uv run python scripts/check_wrapper_portability.py
uv run python scripts/check_optional_import_boundaries.py
uv run python scripts/check_core_performance.py
uv run python scripts/generate_quality_dashboard.py
uv run mkdocs build --strict
uv run pytest
uv run --extra harness pytest --cov=src/worldforge --cov-report=term-missing --cov-fail-under=90
bash scripts/test_package.sh
uv build --out-dir dist --clear --no-build-logs
```

在打标签或发布包之前，还需运行 [运维](./operations.md) 中描述的锁定依赖审计流程。若在门禁启动前安装失败，请运行：

```bash
uv run python scripts/contributor_doctor.py --format markdown
uv run python scripts/contributor_doctor.py --format json
```

贡献者诊断工具会检查 Python 3.13、uv、源码树结构、文档工具、GitHub CLI 认证状态以及可选运行时跳过原因，无需安装依赖、读取密钥，也不假设 LeWorldModel、LeRobot、GR00T 或 Rerun 已存在。其 Markdown 输出可安全粘贴到公开 Issue 中。

`uv run python scripts/generate_provider_docs.py --check`、
`uv run python scripts/check_docs_commands.py`、`uv run python scripts/check_docs_snippets.py`、
`uv run python scripts/manage_fixture_snapshots.py --format markdown`、
`uv run python scripts/check_wrapper_portability.py`、
`uv run python scripts/check_optional_import_boundaries.py`，以及 `uv run mkdocs build --strict`
分别验证：生成的提供方文档、已记录命令的漂移、选定的可执行文档代码片段、夹具快照漂移、包装器可移植性、可选运行时导入边界，以及严格模式下的 MkDocs Material 站点。`bash scripts/test_package.sh` 在安装构建好的 wheel 并针对已安装包运行测试之前，先检查 wheel/sdist 的内容。发布工件的哈希值、质量看板和证据关联契约详见 [工件完整性](./artifact-integrity.md)。

### 文档代码片段标记

在受控的 Python 或 JSON 示例的围栏代码块之前，直接使用片段标记：

````markdown
<!-- worldforge-snippet: execute -->
```python
from worldforge import WorldForge
forge = WorldForge()
print(forge.providers())
```
````

JSON 块使用 `<!-- worldforge-snippet: parse -->`。门禁会解析通用 JSON，并对选定的场景和基准测试示例进行模式检查。对于不稳定的示例，请使用显式跳过标记，而不是留空不标注：

- `<!-- worldforge-snippet: skip-host-owned -->`：用于可选运行时、检查点、GPU 主机或已准备好的机器人环境。
- `<!-- worldforge-snippet: skip-credentialed -->`：用于付费提供方、私有端点或需要密钥的示例。
- `<!-- worldforge-snippet: skip-illustrative -->`：用于包含 `...` 等占位符、未定义宿主对象或有意不完整代码的片段。

在更改 Python API、场景、提供方路由、外部提供方、基准测试、工件或报告文档中的 Python 或 JSON 示例之前，请先运行 `uv run python scripts/check_docs_snippets.py`。

### 确定性工件测试

当测试比较精确的工件、报告或清单输出时，请使用 `worldforge.testing` 中的确定性辅助工具：

```python
from worldforge.testing import DeterministicIdFactory, stable_json_dumps, stable_snapshot

ids = DeterministicIdFactory()
snapshot = stable_snapshot(payload, path_roots={tmp_path: "<tmp>"})
assert stable_json_dumps(snapshot) == expected_json
```

精确快照适用于版本化的 JSON 工件模式、Issue 模板、渲染后的报告和稳定的 CLI 文本。对于真实的延迟或吞吐量测量、宿主路径、当前 git 元数据、实时时间戳、可选运行时告警文本，以及由已准备好的外部运行时所拥有的值，请优先使用语义断言。不要为宿主方拥有的冒烟测试全局替换时钟或随机性；应将确定性时钟或显式 ID 传入被测试的辅助工具或渲染器中。

在变更公开导入、CLI 标志、提供方能力或工件模式之前，请先通过 [公开 API 稳定性](./api-stability.md) 和 [工件模式](./artifact-schemas.md) 所有权映射对该接口进行分类。稳定和试验性接口需要提供弃用或迁移方案，除非该变更是为了修复安全漏洞、错误的能力声明或持久化状态不一致问题。

关键目录：

- `src/worldforge/models.py`：公开兼容门面与模型重导出。
- `src/worldforge/_model_utils.py`：共享 JSON 原生验证辅助工具和框架错误。
- `src/worldforge/scene_models.py`：几何、动作、场景对象、结构化目标与历史契约。
- `src/worldforge/capability_results.py`：嵌入、动作评分与具身策略结果契约。
- `src/worldforge/provider_models.py`：提供方面向契约的兼容门面。
- `src/worldforge/provider_profiles.py`、`provider_request_policy.py`、`provider_events.py`、`provider_diagnostics.py` 和 `provider_redaction.py`：聚焦的提供方契约，分别覆盖能力/配置元数据、重试/超时、事件、生命周期诊断和脱敏。
- `src/worldforge/framework.py`：运行时外观、提供方注册、持久化和诊断。
- `src/worldforge/framework_capabilities.py`：内部能力协议注册表和分发。
- `src/worldforge/_world.py`：可变世界状态、历史记录和规划。
- `src/worldforge/_world_prompt_seeders.py`：基于提示词的本地种子场景辅助工具。
- `src/worldforge/harness/tui_styles.py`：机器人案例展示报告使用的无 Textual 依赖 CSS 常量。
- `src/worldforge/providers/`：提供方接口、目录、适配器和脚手架。
- `src/worldforge/testing/`：可复用的提供方契约辅助工具、夹具加载器、运行时标记和确定性工件测试控件。
- `tests/fixtures/fixture-snapshots.json`：已追踪 JSON 夹具的清单；在有意修改夹具后，使用 `uv run python scripts/manage_fixture_snapshots.py --write` 更新该清单。
- `src/worldforge/evaluation/`：确定性的评估套件。
- `src/worldforge/benchmark.py`：提供方基准测试运行时。
- `src/worldforge/observability.py`：提供方事件接收器。
- `docs/src/`：用户文档、架构、操作手册、提供方页面和 API 说明。
- `tests/`：行为测试和回归测试。
- `examples/`：可运行示例和兼容性包装器。
- `scripts/`：文档生成、脚手架、包验证和可选冒烟测试。

提供方相关工作应在 `src/worldforge/providers/` 中进行。保持适配器能力的真实性，并为每条新支持的路径添加测试。

编辑代码之前，请先选取匹配的 [贡献者任务起始项](./task-starters.md)。起始项列表包含可能涉及的文件、禁止的快捷方式、验证命令、证据工件、文档/变更日志要求，以及提供方、纯文档、演示、工件、评估和 CLI 工作的评审清单项。

对于适配器包和仓库内提供方，请使用可复用的契约辅助工具：

```python
from worldforge.testing import assert_provider_contract

report = assert_provider_contract(provider)
print(report.exercised_operations)
```

具备打分能力的提供方必须通过提供方专属的打分夹具：

```python
report = assert_provider_contract(
    provider,
    score_info=score_fixture["info"],
    score_action_candidates=score_fixture["action_candidates"],
)
```

## 贡献者分类与标签

在开始工作之前，请使用标签明确 Issue 的路线图流和证据契约。

| 维度 | 标签 | 适用场景 |
| --- | --- | --- |
| 路线图流 | `stream: provider-evidence` | 提供方选型、运行时契约、提供方晋升、运行时清单、上游验证 |
| 路线图流 | `stream: evidence-integrity` | 评估、基准测试、预算、已保留的运行证据、发布证据、来源追溯、公开声明 |
| 路线图流 | `stream: ops-authoring` | 运维工作流、机器人案例展示证据、适配器编写循环、参考宿主、持久化、操作手册 |
| 能力 | `predict`、`embed`、`score`、`policy` | Issue 变更或验证该公开能力接口 |
| 严重程度 | `severity: blocking`、`severity: quality`、`type: hardening` | 发布阻塞项、质量回归、验证/脱敏/恢复加固 |
| 发布范围 | `release`、`release: provider-hardening-rc` | 发布流程或命名发布候选范围 |

提供方运行时 Issue 应使用提供方适配器模板、`stream: provider-evidence`、`provider`、声明的能力标签，以及相关的 `optional-dependency`、`robotics`、`security` 或 `research` 标签。新运行时系列或不明确的上游契约在实现之前需要一份选型记录。提供方晋升工作必须引用提供方编写指南晋升门禁、运行时清单、夹具、文档以及实时冒烟测试或明确的阻塞证据。

评估、基准测试、工件、预算、报告或声明类 Issue 应使用评估/基准测试模板，并标记 `stream: evidence-integrity`。发布候选或公开声明类 Issue 在关闭前需要已保留的运行证据、证据包或发布证据。

运维工作流 Issue 应使用 `stream: ops-authoring`，并视情况添加 `operations`、`harness`、`developer-experience`、`persistence`、`reliability` 或 `examples` 标签。Issue 应注明待运行的命令、预期成功信号、初步排查步骤和恢复命令。

架构、持久化边界、提供方选型或运行时所有权变更，在大范围实现之前需要一份设计记录或选型记录。

安全敏感的报告仍通过私有 Security 标签路由。请勿在公开 Issue 中披露漏洞、凭据、已签名 URL、私有端点或宿主本地工件。

在发布分支之前：

- 运行 [用户与运维人员操作手册](./playbooks.md) 中的完整发布门禁。
- 针对提供方行为变更，更新提供方文档和生成的目录表格。
- 针对公开 API 或异常变更，更新 [Python API](./api/python.md)。
- 针对新增流程或所有权边界，更新 [架构](./architecture.md)。
- 针对新增或变更的公开工件系列，更新 [工件模式](./artifact-schemas.md)。
- 针对新增的运维工作，更新 [运维](./operations.md) 和 [操作手册](./playbooks.md)。
- 针对用户可见的变更，更新 `CHANGELOG.md`。
- 当文档导航发生变更时，更新 `mkdocs.yml`。
- 针对新增命令、约束、注意事项或架构事实，更新 `AGENTS.md`。

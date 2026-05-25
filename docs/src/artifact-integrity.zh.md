# 工件完整性

在发布包、发布说明、提供方晋升或基准测试主张之前，WorldForge 发布工件必须能够从干净检出进行检查。当前完整性模型是 checkout 安全的：它在无需签名凭据或可选模型运行时的情况下，验证包内容、依赖项建议、生成的文档、命令漂移、封装器可移植性、核心性能预算、发布证据以及保留的工件摘要。

## 当前已验证项

| 验证面 | 当前门控 | 成功信号 | 首步排查 |
| --- | --- | --- | --- |
| 锁文件 | `uv lock --check` | 依赖项元数据已锁定 | 有意刷新锁元数据并检查差异 |
| Wheel 和 sdist 结构 | `bash scripts/test_package.sh` | wheel 在隔离的 venv 中安装成功；sdist 包含文档、测试、示例、脚本和元数据 | 检查 `scripts/check_distribution.py` 中缺失或禁止的条目 |
| 发行版元数据 | `uv run python scripts/check_distribution.py dist` | wheel 元数据包含 Python `>=3.13,<3.14`、MIT 许可证表达式、扩展项和控制台脚本 | 修复 `pyproject.toml` 或包含规则 |
| 依赖项建议 | `uv run python scripts/generate_dependency_audit_evidence.py` | JSON 和 Markdown 证据针对冻结导出的依赖项记录 `passed`、`findings`、`tool-unavailable` 或 `failed` 状态 | 检查 Markdown 建议表，并更新或记录依赖项决策 |
| 生成的提供方文档 | `uv run python scripts/generate_provider_docs.py --check` | 提供方目录文档与提供方元数据一致 | 重新生成文档，检查提供方配置文件变更，然后重新运行 |
| 文档命令漂移 | `uv run python scripts/check_docs_commands.py` | README、CLI 文档、示例、操作、Playbook 和 AGENTS 命令均可解析 | 修复过时的命令，或记录缺失的公共入口点 |
| 封装器可移植性 | `uv run python scripts/check_wrapper_portability.py` | 封装器具有预期的 shebang、可执行位、Python 3.13 uv 调用及文档 | 修复命名封装器或文档化命令 |
| 核心 checkout 性能 | `uv run python scripts/check_core_performance.py` | 报告中 checkout 安全的核心路径 `passed: true` | 检查失败行，在修改预算之前修复回归问题 |
| 发布就绪演练 | `uv run python scripts/release_readiness_drill.py` | 通过和受控失败的发布证据夹具写入 `.worldforge/release-readiness-drill/` | 检查第一个失败的门控并重新运行其排查命令 |
| 发布证据 | `uv run python scripts/generate_release_evidence.py --run-gates` | Markdown 和 JSON 摘要链接门控状态、工件、哈希值和冒烟测试清单 | 检查失败的门控行及其首步排查 |
| 质量仪表板 | `uv run python scripts/generate_quality_dashboard.py` | 本地 JSON 和 Markdown 汇总发布证据、依赖项审计、核心性能、跳过的宿主方检查、未运行的检查及第一个失败门控 | 检查原始失败详细信息部分，然后重新运行底层门控工件 |
| 发布说明草稿 | `uv run python scripts/generate_release_notes.py --release-evidence .worldforge/release-evidence/release-evidence.json` | 可供维护者编辑的 Markdown 链接变更日志条目、已关闭问题、验证证据、注意事项和宿主方持有的可选运行时证据 | 重新生成发布证据或修复 `CHANGELOG.md`，然后重新运行草稿命令 |
| 发布来源 | `.github/workflows/release.yml` 构建来源证明 | 标记发布构建上传发行版并请求 GitHub 工件来源 | 检查发布工作流运行和附加的 GitHub 证明 |
| 包发布身份 | `.github/workflows/release.yml` 具有 OIDC 权限的 PyPI 环境 | `uv publish dist/*` 从受保护的 `pypi` 环境运行 | 在打标签前验证发布环境和 PyPI 受信发布配置 |

## 哈希值与证据链接

在发布说明引用包或证据工件之前，先生成本地哈希值：

```bash
uv build --out-dir dist --clear --no-build-logs
shasum -a 256 dist/worldforge_ai-*.whl dist/worldforge_ai-*.tar.gz
bash scripts/test_package.sh
uv run python scripts/generate_dependency_audit_evidence.py
uv run python scripts/generate_release_evidence.py --run-gates \
  --artifact .worldforge/dependency-audit/dependency-audit.json \
  --artifact dist/worldforge_ai-<version>-py3-none-any.whl \
  --artifact dist/worldforge_ai-<version>.tar.gz
uv run python scripts/generate_quality_dashboard.py
```

依赖项审计封装器使用 `uv export --frozen --all-groups --no-emit-project --no-hashes` 加上 `uvx --from pip-audit pip-audit ... --format json`，并使用审计后删除的临时依赖项文件。发布证据 JSON 记录已链接工件的工件路径和 SHA-256 摘要。证据包、依赖项审计证据、运行清单、基准测试报告和冒烟测试清单应从发布说明中链接，而不是手动复制。在修改公开工件契约之前，请使用[工件结构定义](./artifact-schemas.md)来确认所属模块、版本字段、迁移规则和验证面。

质量仪表板读取现有的 JSON 输出，而不是运行门控。它适合用于单一本地审查页面，因为它区分 `failed`、`warning`、`skipped` 和 `not-run` 检查，并保留原始输出尾部。它不替代发布证据：发布证据仍然是工件哈希、已链接运行清单和明确限制的发布主张工件。

发布就绪演练是预演工件，而非发布批准：

```bash
uv run python scripts/release_readiness_drill.py \
  --workspace-dir .worldforge/release-readiness-drill
```

它写入通过和受控失败的发布证据夹具，记录宿主方持有的可选运行时跳过状态，并指出第一个失败的门控及其排查命令。它不会创建标签、发布包、创建 GitHub 发布、签名工件，也不替代从当前门控输出生成的真实发布证据。

在证据存在后起草发布说明：

```bash
uv run python scripts/generate_release_notes.py \
  --release-evidence .worldforge/release-evidence/release-evidence.json
```

草稿不是发布步骤。可以安全地附加用于审查，因为缺失的验证证据会被明确指出，宿主本地路径会被隐去，可选运行时主张仍限定在已链接的冒烟测试清单范围内。草稿状态同时使用 `validation_summary` 和逐行的 `validation_gates`，因此过期摘要不能隐藏单个失败的 gate 行。

不安全的工件不得出现在公开包中：`.env` 文件、凭据、签名 URL 查询字符串、检查点压缩包、下载的数据集、机器人控制器日志、本地缓存目录以及未隐去的提供方载荷。请使用 `worldforge runs bundle <run-id>` 或 `scripts/generate_evidence_bundle.py` 生成经过清理的 issue 和发布工件。

## 未来工作

以下是预期的未来加固步骤，而非当前发布主张：

- 为每个发布工件生成并发布 SBOM；
- 在发布签名工件之前定义签名密钥策略；
- 一旦报告能够直接解析具有凭据的发布工件，即从发布证据中链接 GitHub 证明。

在这些步骤实现之前，请勿主张签名工件、SBOM 覆盖，或高于发布工作流实际证明的 SLSA 级别。

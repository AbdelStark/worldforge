# 支持

WorldForge 的支持以尽力为原则，以可复现问题为前提。

在提交议题之前，请先运行：

```bash
uv sync --group dev
uv lock --check
uv run ruff check src tests examples scripts
uv run ruff format --check src tests examples scripts
uv run python scripts/generate_provider_docs.py --check
uv run mkdocs build --strict
uv run pytest
```

对于提供方配置问题，请附上：

```bash
uv run worldforge doctor
uv run worldforge provider info <provider>
```

在提交提供方配置议题之前，请先查阅[提供方配置索引](./provider-configuration-index.md)；该索引列出了每个目录提供方所需的环境变量、可选输入、宿主方持有的运行时包、已准备好宿主的资产、默认超时和首步诊断命令。
如果失败原因是解析器错误、提供方错误、重试耗尽、配置缺失、能力不支持、可选运行时设置问题、脚手架边界或不安全工件，请先对照[提供方失败模式画廊](./provider-failure-gallery.md)进行匹配。

以下内容可安全附加：提供方配置文件、诊断输出、提供方健康状态、运行时清单、`config_summary().to_dict()` 输出、冒烟测试 `run_manifest.json` 文件、基准测试报告和保留的 JSON 输入——前提是确认宿主特定的对象名称可公开分享。不得附加 `.env` 文件、原始提供方请求体、Bearer 令牌、带有查询字符串的已签名工件 URL、私有检查点文件、机器人控制器凭据，或在提供方事件脱敏之前捕获的日志。

对于可选运行时，请附上确切的包装命令、宿主操作系统、Python 版本、检查点或策略标识符，以及失败所在阶段：依赖导入、检查点加载、提供方调用或动作转换。

请使用以下渠道：

- GitHub Issues：用于可复现的缺陷、提供方提案、文档缺失，以及评估或基准测试问题。
- Security 标签页：用于安全漏洞。
- 保留的 JSON 输入、预算文件和报告：用于基准测试或评估声明。

请参阅规范的[支持策略](https://github.com/AbdelStark/worldforge/blob/main/SUPPORT.md)。

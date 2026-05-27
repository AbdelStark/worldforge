# 静态 HTML 报告

WorldForge 可以将评估报告、基准测试报告、运行比较结果及适合提交 Issue 的包，
导出为**自包含、经脱敏处理的 HTML 文档**。HTML 格式适用于以下场景：单个静态文件
需要发布到 Issue 正文、Slack 消息或发布审查邮件，且读者无需安装 WorldForge——
对于机器消费和代码审查，JSON 和 Markdown 仍是首选格式。

## 直接打开文件的工作流

```bash
# 评估报告 → HTML。
uv run worldforge eval --suite planning --provider mock --format html > report.html

# 基准测试报告 → HTML。
uv run worldforge benchmark --provider mock --operation predict \
    --iterations 5 --format html > benchmark.html

# 两次保留运行的比较 → HTML。
uv run worldforge runs compare path/to/run_a path/to/run_b \
    --format html --output review/compare.html

# 基线与候选版本的回归报告 → HTML。
uv run worldforge runs compare path/to/baseline path/to/candidate \
    --mode regression --format html --output review/regression.html

# 一次保留运行的适合 Issue 的包。
uv run worldforge runs bundle <run-id> --workspace-dir .worldforge \
    --format html > issue.html
```

在任意浏览器中打开生成的文件；它是自包含的——无外部 CSS、无 JavaScript、
无网络加载资产、无锚点链接。可以将其附加到 Issue、添加到发布审查邮件，
或与 `<workspace>/issue-bundles/<run-id>/` 下的 JSON/Markdown 同类文件一起预览。

`worldforge runs bundle` 始终在现有 `summary.md` 和 `issue.md` 文件旁边
同时写入 `summary.html` 和 `issue.html`；选择 `--format html` 只是将 `issue.html`
打印到标准输出。

若要生成一个将评估、基准测试、世界状态差异及 Issue 包证据合并为一个静态工件集、
适合非开发者审查的包：

```bash
uv run python scripts/demo_showcases.py run non-developer-evidence-review \
  --workspace-dir .worldforge/demo-showcases
```

仅在检查 `share_policy` 行后，再附加生成的 `review-package.html`、
`review-package.json` 和 `review-package.md`。相对安全的工件会链接到本地以供
检查；宿主本地路径、已签名 URL 及原始提供方负载标记为 `local-only` 或被排除，
不应上传到 Issue 或发布审查。

## 何时使用 HTML

- 受众为非开发者（发布审查读者、合作伙伴），需要渲染好的表格而无需安装工具。
- 单个工件需要被附加并离线查看。
- 报告需要在 Markdown 渲染不可靠的环境中分享（会去除表格的内部 Wiki、邮件客户端）。

## 何时不使用 HTML

- 读者是技术型人员，在 GitHub 或终端内阅读——Markdown 更简短、对 diff 友好，
  且渲染出相同的表格。
- 读者是脚本——JSON 或 CSV 是稳定的契约；HTML 是一种表现格式，其布局可能
  在不同发布版本之间发生变化。
- 输出需要在版本控制中跨运行进行 diff——Markdown 是稳定的文本格式；
  HTML 包含额外的标记。

## 限制

- HTML 输出仅用于展示。WorldForge 发布版本之间，其结构可能随渲染器的改进而变化。
  请将 JSON 视为持久契约；HTML 是对 JSON 负载的渲染结果。
- 渲染器从不生成 `<a href="…">` 锚点标签。清单字段中出现的 URL 以纯文本形式转义。
  这是有意为之——格式错误的清单无法向共享报告中注入数据窃取链接或 XSS 负载。
- HTML 读者不会下载或包含外部资产，即使源清单引用了它们。使用 `worldforge runs bundle`
  在分享时将安全工件与 HTML 打包在一起。
- 不安全的工件（过大的文件、不在安全附件列表中的后缀、宿主本地路径）会被列出
  但不会被嵌入。当包的 `safe_to_attach` 标志为 `false` 时，Issue 包 HTML 会显示
  警告横幅。

## 脱敏保证

- 所有用户提供的文本（提供方名称、命令、失败摘要、验证错误、运行标识符）
  在插入之前均通过带 `quote=True` 的 `html.escape` 进行转义。
  例如，字面名称为 `<script>` 的提供方在文档中渲染为 `&lt;script&gt;`。
- 渲染器在**所有**输出中均不生成 `<script>` 标签。测试对每种工件类型都断言了这一点。
- 渲染器在**所有**输出中均不生成 `<a>` 标签。测试对 Issue 包路径断言了这一点。
- HTML 文档声明 `lang="en"` 并仅使用内联样式；不包含 `<link rel="stylesheet">` 或
  `<script src="…">`。

## 公共 Python 接口

渲染器函数在顶层包重新导出：

```python
from worldforge import (
    render_evaluation_html,
    render_benchmark_html,
    render_comparison_html,
    render_evidence_bundle_html,
    render_issue_bundle_html,
)

# 也可通过 `EvaluationReport.to_html()` / `BenchmarkReport.to_html()`
# 以及每个报告类上的 `artifacts()` 字典使用。
```

`HTML_REPORT_SCHEMA_VERSION` 已暴露，供调用方在渲染器版本发生偏移时进行分支判断；
当前版本为 `1`。

## 渲染器扩展点

外部评估套件和宿主应用可以注册安全的渲染器，而无需修改 WorldForge 内部实现。
渲染器声明其工件族、输出格式、媒体类型、支持的模式 ID，以及其输出是否适合
附加或仅限本地使用。注册仅接受可调用渲染器；WorldForge 不从任意文件加载渲染器插件。

```python
from worldforge import ReportRenderer, register_report_renderer, render_report_artifact


register_report_renderer(
    ReportRenderer(
        artifact_family="comparison",
        output_format="summary",
        media_type="text/plain",
        supported_schemas=("comparison:2",),
        safe_to_attach=True,
        render=lambda payload: f"runs={payload['run_count']}",
    )
)

artifact = render_report_artifact("comparison", "summary", {"run_count": 2})
assert artifact.safe_to_attach is True
```

内置渲染器族包括 `comparison`、`evidence-bundle` 和 `issue-bundle`。
重复的族/格式注册会失败，除非调用方显式替换某个渲染器。
适合附加的渲染器输出在返回之前会被验证，以排除类密钥材料。

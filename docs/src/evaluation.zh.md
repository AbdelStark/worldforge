# 评估

WorldForge 内置了两个评估套件：

- `physics`：确定性的对象稳定性和动作响应检查
- `planning`：基于预测驱动的规划器，对重新定位、邻近放置和交换执行进行验证

## Python

```python
from worldforge.evaluation import EvaluationSuite

suite = EvaluationSuite.from_builtin("planning")
report = suite.run_report(["mock"], forge=forge)

print(report.results[0].passed)
print(report.to_json())
```

## 自定义套件编写

外部包无需继承内部模块即可定义确定性套件。自定义套件通过公开的 `EvaluationSuite.custom(...)` 创建，包含一个或多个 `EvaluationScenario` 对象。每个场景可以提供一个可调用的评估器，该评估器接收一个 `EvaluationContext` 并返回 `context.outcome(score=..., passed=..., metrics=...)`。

```python
from worldforge.evaluation import EvaluationContext, EvaluationScenario, EvaluationSuite


def check_empty_world(context: EvaluationContext):
    object_count = context.world.object_count
    return context.outcome(
        score=1.0,
        passed=object_count == 0,
        metrics={"object_count": object_count},
    )


suite = EvaluationSuite.custom(
    suite_id="custom-empty-world",
    name="Custom Empty World Evaluation",
    suite_version="custom-empty-world:1",
    claim_boundary=(
        "This custom suite is a deterministic checkout example, not a model-quality claim."
    ),
    scenarios=[
        EvaluationScenario.from_callable(
            name="empty-world-readable",
            description="Checks that a new world can be inspected.",
            evaluator=check_empty_world,
        )
    ],
)

EvaluationSuite.register("custom-empty-world", lambda: suite, replace=True)
report = EvaluationSuite.from_registered("custom-empty-world").run_report("mock", forge=forge)
print(report.provenance.suite_version)
print(report.artifacts()["failure_gallery.json"])
```

可调用对象也可以返回 `EvaluationResult` 或包含 `score`、`passed` 和 `metrics` 的 JSON 对象，但推荐使用 `context.outcome(...)` 路径，因为它会在场景边界处验证分数范围、布尔通过标志和 JSON 原生指标。元组形式的值、对象实例、非有限数字和非字符串指标键将引发 `WorldForgeError`，而不是被序列化到报告中。

自定义套件版本字符串由作者维护；使用稳定的值（如 `my-suite:1`），并在场景输入、指标或通过/失败语义发生变化时递增版本号。报告来源溯源会记录该套件版本、输入摘要、结果摘要、提供方列表、声明边界和指标语义。使用 `claim_boundary` 字段明确声明该套件不能证明什么。除非有独立证据支撑，否则不得将自定义套件用作排行榜、物理保真度、媒体质量、安全性或真实机器人性能的声明。

可参阅 `examples/custom_evaluation_suite.py` 获取检出即可运行的示例。如需保存完整的演示工件集，请运行：

```bash
uv run python scripts/demo_showcases.py run custom-evaluation-suite --workspace-dir .worldforge/demo-showcases --overwrite
```

该工作流在所选演示工作空间下写入报告 JSON、Markdown、CSV、HTML、`failure_gallery.json`、`failure_gallery.md` 及演练摘要。它包含一个受控的失败案例，以便审查者检查失败画廊的行为。声明边界保持明确：这是确定性的契约信号证据，而非模型质量、排行榜、物理保真度、安全性或机器人性能证据。

## CLI

```bash
uv run worldforge eval --suite physics --provider mock
uv run worldforge eval --suite planning --provider mock --format json
```

重复 `--provider` 可在一份报告中比较多个已注册的提供方。

当评估需要留下有清单支撑的证据包时，使用 `--run-workspace`：

```bash
uv run worldforge eval --suite planning --provider mock --run-workspace .worldforge
```

运行工作空间将 `run_manifest.json`、JSON/Markdown/CSV 报告及结果摘要存储在 `.worldforge/runs/<run-id>/` 下。

## 数据集清单

评估报告可以引用数据集清单，而无需存储或下载数据集：

```bash
uv run worldforge eval --suite planning --provider mock \
  --dataset-manifest examples/dataset-manifests/mock-evaluation-fixtures.json \
  --format json
```

数据集清单是 `schema_version: 1` 的 JSON 原生工件。它们记录本地夹具引用、稳定的远程引用、由宿主方持有的资产标识符、`sha256:<hex>` 校验和、许可证说明、来源所有者/来源/版本字段、隐私分类、安全审查标记以及由宿主方持有的获取步骤。本地夹具必须使用相对于仓库的安全路径，并与其校验和匹配；远程引用必须是不带签名查询字符串的稳定 `https` URI；由宿主方持有的资产必须使用 `asset_id` 加获取步骤，而非宿主本地路径。

评估来源溯源仅存储紧凑的 `dataset_manifests` 引用：清单 id、摘要、条目计数、许可证、隐私和安全摘要，以及当清单位于仓库内部时的安全清单路径。它不嵌入数据集条目或原始资产。证据包和 Issue 包复制受源代码管理的安全清单文件，而由宿主方持有的数据集、检查点和已准备的运行时资产则保留在仓库之外。

当套件存在失败时，JSON 和 Markdown 报告会包含紧凑的失败画廊。画廊也通过 `report.artifacts()` 以 `failure_gallery.json` 和 `failure_gallery.md` 的形式导出，用于附加到 Issue：

```python
gallery = report.failure_gallery()
print(gallery.to_markdown())
```

每个画廊案例记录夹具 id（如 `evaluation:planning:object-relocation`）、提供方、场景、分数、预期契约说明、观测摘要、小型指标预览和排查步骤。指标预览经过脱敏处理：密钥形式的值被脱敏，签名 URL 查询字符串被剥离，宿主本地路径被替换，类张量数组以摘要形式呈现而非原始复制。

如需将一个或多个保存的评估或基准测试运行打包以供 Issue 分类或发布审查，请生成检出安全的证据包：

```bash
uv run worldforge eval --suite planning --provider mock --run-workspace .worldforge
uv run worldforge benchmark --preset mock-smoke --run-workspace .worldforge
uv run worldforge runs bundle <run-id>
uv run python scripts/generate_evidence_bundle.py --workspace-dir .worldforge
```

证据包默认输出到 `.worldforge/evidence-bundles/<timestamp>/`，写入 `evidence_manifest.json` 和 `summary.md`。清单记录已复制的报告、运行清单、事件日志、预设输入和预算文件、夹具摘要、SHA-256 文件摘要及 `safe_to_attach` 标志。不支持的二进制工件、宿主本地绝对路径、签名 URL 和类密钥文本默认被排除或标记为仅限本地。

使用 `worldforge runs bundle <run-id>` 可导出单次运行的更小的 Issue 就绪归档。它在摘要清单和摘要旁边写入 `issue.md`，打印的 Issue 模板包含命令、预期信号、观测到的失败、可安全附加的说明及首要排查步骤。

## 报告格式

- Markdown：来源溯源部分、提供方摘要表、场景级别详情表
- JSON：`suite_id`、`suite`、`claim_boundary`、`metric_semantics`、`provider_summaries`、场景 `results`、`provenance` 信封，以及当存在失败场景时的 `failure_gallery`
- CSV：每个提供方/场景对占一行，包含序列化的指标负载（信封省略以保持表格与早期发布版本的导入兼容性）
- 失败画廊 JSON/Markdown：代表性的失败案例，包含夹具 id、预期契约说明、脱敏的指标预览和首要排查步骤

每份 JSON 和 Markdown 报告均携带明确的声明边界。内置套件是确定性的适配器契约检查；其分数不代表物理保真度、媒体质量、安全性或真实机器人性能。失败画廊遵循同样的边界：它们用于 Issue 分类和提供方审查调试，而非提供方质量排名。

## 来源溯源信封

通过 `EvaluationSuite.run_report()` 和 `worldforge eval` CLI 构建的报告携带一个 `provenance` 信封（`schema_version: 2`），以便在无需控制台日志的情况下审计声明、回归和发布证据：

| 字段 | 描述 |
| --- | --- |
| `schema_version` | 信封模式版本（当前为 `2`）。 |
| `kind` | `"evaluation"`。 |
| `suite_id`、`suite_version` | 套件标识符及契约版本（例如 `evaluation:1`）。 |
| `worldforge_version` | 生成报告的包版本。 |
| `created_at` | UTC ISO 时间戳。 |
| `command` | 通过 CLI 生成时的命令参数向量。 |
| `providers`、`capabilities` | 参与测试的提供方及其涵盖的能力。 |
| `runtime_manifests` | 可用时的提供方运行时清单引用。 |
| `dataset_manifests` | 报告引用的数据集清单的紧凑引用。 |
| `input_digest`、`result_digest` | 输入和结果的确定性 `sha256:<hex>` 摘要。 |
| `event_count` | 已发出的 `ProviderEvent` 计数。 |
| `claim_boundary`、`metric_semantics` | 与报告级别的声明文本相同。 |
| `notes` | 可选的自由格式备注。 |

如需在 Issue 或发布证据中引用某个结果，请粘贴 JSON 报告中的 `provenance` 块（或 Markdown 中的项目符号列表）。它携带了审查者将声明映射回 WorldForge 版本、套件契约和输入夹具所需的所有字段。

### 迁移

早期报告省略了 `provenance`。CSV 渲染器以及现有的 `suite_id`、`suite`、`claim_boundary`、`metric_semantics`、`provider_summaries` 和 `results` 键保持不变。使用 JSON 输出的工具应将 `provenance` 视为可选项，并在重新渲染历史报告时回退到现有字段。

## 能力检查

每个套件声明其所需的提供方能力。例如：

- `physics` 和 `planning` 需要 `predict`

当调用方要求提供方运行其无法满足的套件时，WorldForge 会引发 `WorldForgeError`。

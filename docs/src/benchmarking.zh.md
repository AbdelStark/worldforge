# 基准测试

WorldForge 内置了一个能力感知的基准测试 harness，适用于已注册的完整提供方及已注册的能力协议实现。它可以测量提供方的直接接口：`predict`、`embed`、`score` 和 `policy`。`plan` 仍是 WorldForge 的一个门面工作流，因此在需要规划路径延迟数据时，应直接对打分模型提供方和策略提供方进行基准测试。

## Python

<!-- worldforge-snippet: skip-illustrative -->
```python
from worldforge import ProviderBenchmarkHarness

harness = ProviderBenchmarkHarness(forge=forge)
report = harness.run(
    ["mock"],
    operations=["predict", "embed"],
    iterations=5,
    concurrency=2,
)

print(report.to_markdown())
```

如果安装了可选的 Rerun 集成，`RerunArtifactLogger.log_benchmark_report(report)` 会将同一份报告 JSON 以及每条结果的指标标量记录到 `.rrd` 检查工件中。

打分模型和策略提供方使用同一个基准测试运行器，由宿主方提供特定于提供方的输入：

<!-- worldforge-snippet: skip-illustrative -->
```python
from worldforge import BenchmarkInputs, ProviderBenchmarkHarness

inputs = BenchmarkInputs(
    score_info={
        "pixels": [[[[0.0]]]],
        "goal": [[[0.3, 0.5, 0.0]]],
        "action": [[[0.0, 0.5, 0.0]]],
    },
    score_action_candidates=[[[[0.0, 0.5, 0.0]], [[0.3, 0.5, 0.0]]]],
    policy_info={
        "observation": {
            "state": {"cube": [0.0, 0.5, 0.0]},
            "language": "move the cube",
        },
        "mode": "select_action",
    },
)

report = ProviderBenchmarkHarness(forge=forge).run(
    ["leworldmodel", "lerobot"],
    iterations=3,
    inputs=inputs,
)
```

## CLI

```bash
uv run worldforge benchmark --provider mock --iterations 5
uv run worldforge benchmark --provider mock --operation predict --format json
uv run worldforge benchmark --provider mock --operation embed --format markdown
uv run worldforge benchmark --provider mock --operation embed --input-file examples/benchmark-inputs.json
```

当基准测试数据需要有清单支撑的来源溯源时，使用 `--run-workspace`：

```bash
uv run worldforge benchmark \
  --provider mock \
  --operation predict \
  --iterations 5 \
  --run-workspace .worldforge
```

运行工作空间会将清单、JSON/Markdown/CSV 报告、结果摘要、预算判定结果（如提供）以及事件计数存储在 `.worldforge/runs/<run-id>/` 下。

在引用回归、发布声明或提供方变更之前，应先比较保存的基准测试运行结果：

```bash
uv run worldforge runs compare \
  .worldforge/runs/<baseline-run-id> \
  .worldforge/runs/<candidate-run-id> \
  --format markdown

uv run worldforge runs compare \
  .worldforge/runs/<baseline-run-id> \
  .worldforge/runs/<candidate-run-id> \
  --mode regression \
  --format html \
  --output .worldforge/runs/regression-comparison.html

uv run worldforge runs compare \
  .worldforge/runs/<baseline-run-id> \
  .worldforge/runs/<candidate-run-id> \
  --format csv \
  --output .worldforge/runs/benchmark-comparison.csv
```

`runs compare` 接受运行目录、`run_manifest.json` 文件或 `reports/report.json` 文件。它拒绝混合评估报告和基准测试报告，并在能力不匹配、操作不匹配、夹具摘要不匹配、预算不匹配或套件版本不匹配时停止运行。允许不同的提供方：只有在共享比较上下文匹配后，每个提供方才会成为独立的行。Markdown 以声明边界语言和共享上下文开头；JSON、Markdown 和 CSV 行包含指标增量、事件计数、预算状态、缺失证据、跳过原因、工件路径以及输入或预算来源溯源引用。输出结果足够稳定，可附加到 Issue 中，但它不是公开排行榜，也不是跨不同任务或能力的排名。

当第一次运行是保存的基线、第二次运行是候选时，使用 `--mode regression`。回归模式支持保存的基准测试、评估和演示案例展示运行。它以 JSON、Markdown、CSV 或 HTML 格式报告指标增量、预算状态变化、新增和已删除的故障、安全的工件漂移以及来源溯源差异。不安全的工件引用（如绝对路径、遍历形式路径、二进制/检查点后缀或原始私有工件）被计为已排除，不会渲染到比较报告中。回归报告仅作为审查工件：它不会自动更新基线或削弱预算。

当基准测试结果需要从保存的输入中重现时，使用 `--input-file`。文件可以直接包含输入字段，也可以包含一个 `inputs` 对象加上元数据。已提交的 `examples/benchmark-inputs.json` 夹具对 mock 提供方的 `predict` 和 `embed` 操作是检出即可运行的；score 和 policy 条目需要声明了相应能力的提供方。

<!-- worldforge-snippet: parse -->
```json
{
  "metadata": {
    "run": "release-smoke"
  },
  "inputs": {
    "prediction_action": {
      "type": "move_to",
      "parameters": {
        "target": { "x": 0.25, "y": 0.5, "z": 0.0 },
        "speed": 1.0
      }
    },
    "prediction_steps": 2,
    "embedding_text": "benchmark cube state",
    "score_info": {
      "pixels": [[[[0.0]]]],
      "goal": [[[0.3, 0.5, 0.0]]],
      "action": [[[0.0, 0.5, 0.0]]]
    },
    "score_action_candidates": [[[[0.0, 0.5, 0.0]], [[0.3, 0.5, 0.0]]]],
    "policy_info": {
      "observation": {
        "state": { "cube": [0.0, 0.5, 0.0] },
        "language": "move the cube"
      },
      "mode": "select_action"
    }
  }
}
```

省略的字段将保留确定性默认值。提供方专属的打分和策略输入应保持 JSON 原生，以便基准测试夹具可作为可附加证据保留。

使用 CLI 运行提供方-操作对比：

```bash
uv run worldforge benchmark --provider mock --operation predict --iterations 5
```

CLI 将规范的 JSON 报告写入 `.worldforge/reports/`。请将这些报告视同证据工件：只有在其背后的 JSON 被保存的情况下，才能引用其中的数字。

当基准测试运行是发布门控、回归检查或公开声明的一部分时，使用预算文件。预算选择器可以指定提供方和操作，也可以省略任一字段以将阈值应用于所有匹配的结果：

<!-- worldforge-snippet: parse -->
```json
{
  "budgets": [
    {
      "provider": "mock",
      "operation": "predict",
      "min_success_rate": 1.0,
      "max_error_count": 0,
      "max_retry_count": 0,
      "max_average_latency_ms": 250.0,
      "max_p95_latency_ms": 400.0,
      "min_throughput_per_second": 2.0
    }
  ]
}
```

```bash
uv run worldforge benchmark \
  --provider mock \
  --operation predict \
  --iterations 5 \
  --format json \
  --budget-file examples/benchmark-budget.json
```

使用 `--budget-file` 时，命令同时打印基准测试报告和门控报告。未通过门控检查时，将在打印违规项（如延迟、重试、错误计数、成功率或未匹配预算检查）后以非零状态退出。JSON 输出包含 `benchmark` 和 `gate` 对象；Markdown 打印两份报告；CSV 打印门控违规表。

## 预算校准

基准测试预算应从保存的基线报告中校准，而非依赖控制台记忆或一次性本地观测。从一个或多个已保存的基准测试 JSON 报告生成候选预算工件：

```bash
uv run worldforge benchmark --preset release-evidence --format json --run-workspace .worldforge
uv run python scripts/calibrate_benchmark_budgets.py \
  --report .worldforge/reports/benchmark-<timestamp>-<run-id>.json \
  --current-budget src/worldforge/benchmark_presets/_data/budget-release-evidence.json \
  --output .worldforge/benchmark-calibration/release-evidence-candidate \
  --machine-class "macos-arm64-local"
```

校准命令写入以下文件：

- `budget-calibration.json`：完整的来源溯源、基线上下文、来源报告摘要及差异。
- `candidate-budgets.json`：使用现有基准测试预算模式的可加载预算文件。
- `budget-calibration.md`：用于 Pull Request 或发布说明的人工审查报告。

成功信号：候选预算文件通过 `worldforge benchmark --budget-file` 使用的同一解析器加载，且每行差异均包含提供方、操作、旧阈值、候选阈值、观测基线和理由。该命令从不编辑当前预算文件。

阈值放宽需要人工审查。审查者在替换任何发布预算文件之前，应比较来源报告摘要、机器类别、Python 版本、命令、提供方、操作、样本计数、输入夹具摘要、旧阈值、候选阈值、观测基线和理由。仅当预算变更遵循有意的工作负载变更、提供方适配器变更、依赖项/运行时升级或已记录的机器类别变更时，方可允许。不允许通过变更预算来掩盖回归问题、创建与机器无关的性能声明，或向默认 CI 添加不稳定的实时提供方预算。

遇到意外候选值时的首要排查步骤：打开 `budget-calibration.md`，确认来源报告摘要与保存的基准测试 JSON 匹配，然后在同一机器类别上重新运行完全相同的基准测试命令，再考虑更改发布预算。

## 核心检出性能守护

使用核心性能门控来检测在干净检出环境中应保持低开销的框架路径中的回归问题：

```bash
uv run python scripts/check_core_performance.py \
  --workspace-dir .worldforge/core-performance \
  --output .worldforge/core-performance/core-performance.json
```

该命令针对本地毫秒级预算，测量世界状态持久化、基准测试输入夹具加载、提供方目录诊断、证据包创建和评估报告渲染。成功信号：JSON 报告中 `passed: true`，结果行包含测量的 `duration_ms` 和 `budget_ms`，保存的工作空间包含每个操作的工件路径。首要排查步骤：检查失败行，验证工件路径和已更改的代码路径，然后在更改预算之前修复回归问题。这些预算仅作为检出安全的回归守护，并非排行榜、跨机器声明或可选运行时基准测试。

## 报告内容

- 按提供方、按操作的成功与错误计数
- 从已发出的 `ProviderEvent` 记录中派生的重试总计
- 总挂钟时间和吞吐量
- 平均值、最小/最大值、p50 和 p95 延迟
- 序列化的提供方-操作事件聚合，便于深入检查
- 用于发布或声明导向阈值的可选预算门控结果

每份 JSON 和 Markdown 报告均包含 `claim_boundary` 和 `metric_semantics` 字段。基准测试 harness 是合成性的。它测量所选提供方适配器路径的操作延迟、重试次数和吞吐量；它不对媒体质量、物理保真度、安全性或生产负载容量进行打分。

## 预设

具名预设将确定性输入夹具、可选预算文件和运行时门控捆绑在一起，以便维护者无需每次重新推导输入和预算即可运行发布回归工作负载。目前随 wheel 分发的有五个预设，分为四个类别：

| 预设 | 类别 | 提供方 | 操作 | 迭代次数 | 失败容忍策略 |
| --- | --- | --- | --- | ---: | --- |
| `mock-smoke` | 检出即可运行 | `mock` | predict, embed | 5 | fail-on-violation |
| `parser-overhead` | 检出即可运行 | `mock` | predict, embed | 20 | fail-on-violation |
| `prepared-host` | 准备宿主 | `leworldmodel`, `lerobot`, `gr00t` | score, policy | 3 | skip-when-env-missing |
| `release-evidence` | 发布 | `mock` | predict, embed | 10 | fail-on-violation |

通过现有的 `benchmark` 子命令列出、查看和运行预设：

```bash
uv run worldforge benchmark --list-presets
uv run worldforge benchmark --show-preset release-evidence
uv run worldforge benchmark --preset mock-smoke
uv run worldforge benchmark --preset release-evidence --format json --run-workspace .worldforge
```

`--preset` 会覆盖 `--provider`、`--operation`、`--iterations`、`--concurrency`、`--input-file` 和 `--budget-file`。`--format` 和 `--run-workspace` 标志仍然适用。

### 失败容忍策略与跳过语义

- **fail-on-violation**（`mock-smoke`、`parser-overhead`、`release-evidence`）。预设无条件运行；预算违规以非零状态退出，并附带包含提供方、操作、指标、观测值、阈值和预算选择器的标准违规表。
- **skip-when-env-missing**（`remote-media-dryrun`、`prepared-host`）。每个有门控的预设通过 `worldforge.testing.runtime_profiles.provider_profile_skip_reason` 检查其所需的每个提供方运行时配置文件。如果没有满足条件的运行时被配置，预设将打印一个类型化的原因并以 0 状态退出；发布 CI 将此视为"此宿主上证据不可用"而非失败。

### 添加预设

`BenchmarkPreset` 是 `worldforge.benchmark_presets` 下的一个冻结数据类。向 `_BENCHMARK_PRESETS` 元组添加新条目，将匹配的 `inputs-*.json` 和（可选的）`budget-*.json` 一并存放在 `src/worldforge/benchmark_presets/_data/` 下，并在 `tests/test_benchmark_presets.py` 中添加覆盖。保持输入的确定性和小巧；二进制片段帧应通过 `frames_base64` 包含在 JSON 中，而非作为独立的媒体文件。

## 来源溯源信封

通过 `ProviderBenchmarkHarness.run()` 和 `worldforge benchmark` CLI 构建的报告携带一个 `provenance` 信封（`schema_version: 2`），以便在无需控制台日志的情况下重现、审计或引用某项声明：

| 字段 | 描述 |
| --- | --- |
| `schema_version` | 信封模式版本（当前为 `2`）。 |
| `kind` | `"benchmark"`。 |
| `suite_id`、`suite_version` | `"benchmark"` 及契约版本（例如 `benchmark:1`）。 |
| `worldforge_version` | 生成报告的包版本。 |
| `created_at` | UTC ISO 时间戳。 |
| `command` | 通过 CLI 生成时的命令参数向量。 |
| `providers`、`capabilities` | 参与测试的提供方及其涵盖的操作。 |
| `runtime_manifests` | 可用时的提供方运行时清单引用。 |
| `input_digest`、`result_digest` | 输入和结果的确定性 `sha256:<hex>` 摘要。 |
| `budget_file` | 运行了预算门控时的 `path`、`sha256:<hex>` 及 `metadata` 摘要。 |
| `event_count` | 已发出的 `ProviderEvent` 记录中 `request_count` 的总和。 |
| `claim_boundary`、`metric_semantics` | 与报告级别的声明文本相同。 |
| `notes` | 可选的自由格式备注。 |

引用基准测试数字时，应将信封（粘贴 JSON `provenance` 块或 Markdown 来源溯源部分）连同报告一起附在任何 Issue、发布说明或证据包中。信封有意重复了 `claim_boundary` 和 `metric_semantics`，以便单个块能携带某项声明的完整来源溯源信息。

### 迁移

早期报告省略了 `provenance`。CSV 渲染器、`claim_boundary`、`metric_semantics`、`run_metadata` 和 `results` 字段保持不变；`run_metadata.input_file` 和 `run_metadata.budget_file` 继续公开早期工具使用的原始十六进制摘要。新的使用方应优先使用信封中的 `input_digest`、`result_digest` 和 `budget_file` 字段，这些字段携带 `sha256:<hex>` 摘要和 `runtime_manifests` 映射。

# TheWorldHarness

TheWorldHarness 是一个可选的 Textual 终端界面（TUI），用于以可见、可检查的追踪方式运行 WorldForge 集成流程。它是展示提供方界面、规划、执行、持久化、诊断、基准测试和事件检查如何协同配合的默认集成参考实现。

这是一个本地工具。除非所选流程明确需要，否则不要求可选的 ML 运行时；当前流程使用确定性的可安全检出路径。

真实的机器人案例展示也使用 Textual 界面，但它通过 `scripts/robotics-showcase` 启动，而非通过可安全检出的框架流程。该命令首先运行真实的 LeRobot 策略加上真实的 LeWorldModel 检查点路径，然后打开一份独立报告，内容包含：流水线、运行时指标、分阶段展示、说明性机械臂动画、候选代价图、提供方事件和桌面回放。传入 `--tui-stage-delay <seconds>` 可调整展示节奏，传入 `--no-tui` 可保留纯终端报告。

## 安装边界

Textual 为可选依赖。基础包仅以 `httpx` 作为唯一运行时依赖。

```bash
uv run --extra harness worldforge-harness
uv run --extra harness worldforge-harness --flow lerobot
uv run --extra harness worldforge-harness --flow cosmos-policy
uv run --extra harness worldforge-harness --flow gr00t-replay
uv run --extra harness worldforge-harness --flow robotics-compare
uv run --extra harness worldforge-harness --flow diagnostics
uv run --extra harness worldforge-harness --flow workbench
uv run --extra harness worldforge-harness --flow eval
uv run --extra harness worldforge-harness --flow benchmark
uv run --extra harness worldforge-harness --flow runs
uv run worldforge harness --list
uv run worldforge harness --list --format json
uv run worldforge harness --connectors
uv run worldforge harness --connectors --format json
uv run worldforge harness --runs --provider mock --status failed --artifact-type json
```

已安装的包：

```bash
pip install "worldforge-ai[harness]"
worldforge-harness
```

不使用 `harness` 扩展时，元数据命令仍然可用：

```bash
uv run worldforge harness --list
uv run worldforge harness --list --format json
uv run worldforge harness --connectors --format json
uv run worldforge provider workbench mock
uv run worldforge provider workbench runway --format json
```

在未安装 Textual 的情况下启动 TUI 时，程序将退出并给出安装提示，而非在包导入时引入可选依赖。

## 当前流程

| 流程 | 提供方界面 | 可视化内容 |
| --- | --- | --- |
| `leworldmodel` | `score` | 确定性的 LeWorldModel 风格代价运行时、候选动作打分、打分规划、执行、持久化、重新加载、提供方事件。 |
| `lerobot` | `policy` 加打分提供方 | 确定性的 LeRobot 风格策略、动作转换、策略候选排序、执行、持久化、重新加载、提供方事件。 |
| `cosmos-policy` | `policy` | 通过真实提供方适配器回放已保存的 Cosmos-Policy ALOHA `/act` 请求，包含 json_numpy 50 x 14 动作校验、动作转换、提供方事件及脱敏回放工件。 |
| `gr00t-replay` | `policy` | 通过真实提供方适配器回放已保存的 GR00T N1.7 PolicyClient 请求，包含具名 eef/gripper/joint 张量校验、动作转换、提供方事件及脱敏回放工件。 |
| `robotics-compare` | 策略对比 | LeRobot、Cosmos-Policy 和 GR00T 回放路径按动作形状、已转换动作数量、提供方事件和脱敏工件进行并排对比，无需实时 GPU 服务器。 |
| `diagnostics` | 提供方目录加基准测试框架 | `doctor()` 提供方扫描、已注册/未注册提供方状态、跨 predict/reason/generate/transfer/embed 的 mock 基准测试矩阵、延迟/吞吐量对比、提供方事件。 |
| `workbench` | 提供方编写 | 稳定适配器和候选适配器的可安全检出提供方工作台证据、推进缺口、安全工件及校验命令。 |

运行 Cosmos 回放请执行 `uv run --extra harness worldforge-harness --flow cosmos-policy`。运行成功时应报告 `raw_action_shape: [50, 14]`、`translated_actions: 50` 及 `saved_replay_artifact: artifacts/cosmos-policy-replay.json`。若失败，请从保留的运行工作区开始排查：检查 `logs/provider-events.jsonl` 中的提供方阶段，以及 `artifacts/cosmos-policy-replay.json` 中保存的请求/响应/已转换动作工件。

运行 GR00T 回放请执行 `uv run --extra harness worldforge-harness --flow gr00t-replay`。运行成功时应报告 `translated_actions: 40`、`eef_9d`、`gripper_position` 和 `joint_position` 的原始张量形状，以及 `saved_replay_artifact: artifacts/gr00t-replay.json`。已提交的工件为确定性的可安全检出工件；实地 RTX A6000 验证仅作为来源说明，不存储 GPU 日志、检查点、私有端点或原始观测数据。若失败，请从保留的运行工作区开始排查：检查 `logs/provider-events.jsonl` 中的提供方事件/错误，以及 `artifacts/gr00t-replay.json` 中保存的回放请求/响应/已转换动作工件。

运行机器人对比请执行 `uv run --extra harness worldforge-harness --flow robotics-compare`。运行成功时应报告 `total_translated_actions: 92` 及 `comparison_artifact: artifacts/robotics-policy-comparison.json`。若失败，请优先检查 `logs/provider-events.jsonl` 和对比工件；回放工件保持可安全检出状态，不包含原始观测数据或检查点文件。

## 提供方连接器工作区

Providers 屏幕和 `worldforge harness --connectors --format json` 使用相同的无 Textual 就绪模型。每个已知提供方按 `configured`、`missing_credentials`、`missing_dependency`、`unhealthy` 或 `scaffold` 分组，并提供仅包含名称（不含值）的必需环境变量、可选运行时依赖名称、首个冒烟测试命令及排查步骤。

此界面有意只报告存在状态和配置状态，不打印环境变量值、令牌、端点、检查点路径或构造函数传入的密钥。

## 界面内容

TheWorldHarness 现在直接暴露 WorldForge 的主要界面：

- **Home（主页）**：快捷跳转卡片，以及最近的世界和保留的报告。
- **Worlds（世界）**：通过 `WorldForge` 创建、编辑、保存、派生、删除和预览本地 JSON 世界。
- **Providers（提供方）**：已注册提供方的能力矩阵、健康详情，以及可取消的 `mock.predict`。
- **Eval（评估）**：内置确定性评估套件，能力错误以强提示（hard toast）形式显示。
- **Benchmark（基准测试）**：提供方操作的延迟、重试和吞吐量运行，带实时采样。
- **Run Inspector（运行检查器）**：流程和报告的时间线、指标、脱敏提供方事件表、校验错误、记录及导出预览。

流程视图和报告视图均从测试中使用的同一结构化 `HarnessRun` 对象渲染。提供方、评估和基准测试屏幕调用与 CLI 相同的 Python API；报告工件使用规范的 JSON / Markdown / CSV 渲染器。

每次框架流程运行结束后，最终检查器状态保存于 `.worldforge/runs/<run-id>/results/inspector.json`，脱敏的提供方事件写入 `logs/provider-events.jsonl`，两份工件均在 `run_manifest.json` 中关联。若流程在提供方工作完成前失败，清单状态为 `failed` 而非停留在 `running`；检查器仍会记录命令、已编辑的校验错误及复现该运行所需的失败事件。

诊断、评估和基准测试屏幕与以下非 TUI 命令直接对应：

```bash
uv run worldforge doctor --registered-only
uv run worldforge provider list
uv run worldforge provider workbench mock
uv run worldforge harness --flow workbench
uv run worldforge benchmark --provider mock --iterations 2 --format json
uv run worldforge eval --suite planning --provider mock --format json
```

## 提供方工作台

`worldforge provider workbench <provider>` 是支撑框架提供方开发工作流的可安全检出适配器作者循环工具。它不导入 Textual，且除非显式传入 `--live`，否则不发起实时提供方调用。同一套无 Textual 报告模型也驱动着 `worldforge harness --flow workbench` TUI 路径。默认报告设计为可直接粘贴至 GitHub Issue 或 PR 描述中，包含：提供方概要、目标来源、必需能力符合性辅助工具、计划能力界面、运行时清单状态、夹具 JSON 状态、文档/目录漂移提示、安全脱敏的提供方事件状态、按未来状态分组的推进证据、安全工件引用及精确的校验命令。

```bash
uv run worldforge provider workbench mock
uv run worldforge provider workbench jepa-wms --format markdown
uv run worldforge provider workbench genie --format json
uv run worldforge provider workbench runway --format json
uv run worldforge provider workbench runway --live
uv run worldforge harness --flow workbench
```

对于 `mock` 等确定性本地提供方，工作台会调用已声明的能力辅助工具。对于 `genie` 和 `jepa-wms` 等脚手架或直接构造候选者，它会按推进状态列出缺失的证据，而非暗示该提供方已就绪。对于 HTTP 适配器，它会校验匹配的 `tests/fixtures/providers/<provider>_*.json` 文件或 Python 模块安全夹具前缀（如 `jepa_wms_*.json`），并列出提供方测试模块必须覆盖的能力辅助工具。对于 LeRobot 和 LeWorldModel 等宿主方持有的本地运行时，默认路径检查概要、健康状态、文档、运行时清单和夹具，而将注入式运行时/实时冒烟测试的执行留给预制主机。在提交提供方 PR 之前，请运行 `uv run python scripts/generate_provider_docs.py --check`，以确保概要元数据和生成的目录表保持同步。

已完成的可安全检出流程还会保留一个脱敏的运行工作区：

```text
.worldforge/runs/<run-id>/
|-- run_manifest.json
|-- inputs/
|-- results/
|-- reports/
|-- artifacts/
`-- logs/
```

运行 ID 按 UTC 时间排序且对文件系统安全（`YYYYMMDDTHHMMSSZ-xxxxxxxx`）。清单记录命令、提供方界面、状态、输入摘要、结果摘要、事件计数及相对工件路径。清单有意只存储摘要和报告渲染结果，不存储凭据、原始签名 URL 或提供方私有数据。

CLI 也可为评估和基准测试运行写入相同的目录结构：

```bash
uv run worldforge eval --suite planning --provider mock --run-workspace .worldforge
uv run worldforge benchmark --provider mock --operation predict --run-workspace .worldforge
uv run worldforge runs list
uv run worldforge runs compare .worldforge/runs/<run-a> .worldforge/runs/<run-b>
uv run worldforge runs cleanup --keep 20
uv run worldforge harness --runs --provider mock --capability predict --status failed
```

已完成的评估和基准测试 TUI 屏幕仍会在相对于活动状态目录的 `.worldforge/reports/` 下写入 JSON，供 Home 屏幕和 `Ctrl+P` 最近报告索引使用。当需要将清单、报告、日志和结果摘要整体作为 Issue 附件时，请使用运行工作区。Runs 屏幕和 `worldforge harness --runs` 直接读取保留的运行清单，无需可选的模型运行时。它们支持按提供方、能力、状态、创建日期和安全工件类型过滤；每行暴露脱敏的重新运行命令、Issue 打包导出命令，以及在运行类型支持的情况下提供对比命令。失败、跳过和已取消的行优先显示恢复命令：

```bash
uv run --extra harness worldforge-harness --flow runs
uv run worldforge harness --runs --status failed --artifact-type json --format json
uv run worldforge runs bundle <run-id> --workspace-dir .worldforge
```

使用 `runs compare --format json|markdown|csv|html` 可导出可安全附加的跨保留评估、基准测试或演示案例展示运行的对比报告。CLI 和框架对比路径共用同一套报告模型：兼容的跨提供方运行保留指标差异、事件计数、预算状态、夹具摘要、套件版本、缺失证据及跳过原因；若能力、操作、夹具、预算或套件上下文不匹配，则在写入对比报告前失败。当第一个路径为保留的基准，第二个路径为候选时，请添加 `--mode regression`；报告将标注指标差异、预算违规、新增或消除的失败项、安全工件漂移、来源差异及不安全工件排除情况，而不更新基准。

## 接口契约

TUI 与项目其余部分有意保持分离：

| 模块 | 依赖边界 |
| --- | --- |
| `worldforge.harness.models` | 仅包含数据类；无 Textual 导入。 |
| `worldforge.harness.flows` | 运行打包的演示并构建时间线、指标和记录数据；无 Textual 导入。 |
| `worldforge.harness.cli` | 无 Textual 时列出流程；仅在启动 TUI 时导入。 |
| `worldforge.harness.tui` | 唯一依赖 Textual 的模块。 |

TheWorldHarness 不替代 Python API 或命令行演示，而是使相同的流程可观测：已选候选、代价、动作路径、已保存的世界 ID、最终对象位置、提供方健康状态、基准测试延迟、基准测试吞吐量及提供方事件阶段。

## 交互模型

- `r`：运行所选流程。
- `1`：选择 LeWorldModel 打分规划。
- `2`：选择 LeRobot 策略加打分规划。
- `3`：选择 Cosmos-Policy ALOHA 回放。
- `4`：选择 GR00T DROID 回放。
- `5`：选择机器人策略回放对比。
- `6`：选择提供方诊断和基准测试对比。
- `7`：选择适配器作者工作台。
- `g w`：跳转到 Worlds。
- `g p`：跳转到 Providers。
- `g e`：跳转到 Eval。
- `g b`：跳转到 Benchmark。
- `g u`：跳转到 Runs。
- `Ctrl+P`：搜索静态命令，以及世界、提供方、最近的报告文件和保留的运行工作区。
- `Ctrl+T`：循环切换 `worldforge-dark`、`worldforge-light` 和 `worldforge-high-contrast` 主题。
- `q`：退出。

每次运行通过时间线逐阶段展示，然后从测试中使用的同一结构化 `HarnessRun` 数据填充检查器和记录面板。

## 主题

TheWorldHarness 注册了三套主题：

- `worldforge-dark`：默认深色工作区。
- `worldforge-light`：浅色终端变体。
- `worldforge-high-contrast`：适用于密集屏幕和色彩受限终端的高对比度变体。

Widget CSS 仅使用语义标记；原始颜色值位于 `worldforge.harness.theme` 中。

## 截图刷新

README 图片由确定性的框架状态重新生成。对应的刷新命令已记录在案：

```bash
scripts/regen-harness-screenshot.sh
```

该脚本初始化本地截图状态目录，通过 Textual 的测试框架驱动 Providers 屏幕，导出 SVG，并使用 `rsvg-convert` 渲染 README PNG 图片。

## 路线图

TheWorldHarness 正在从上述只读演示查看器演进为项目的前门交互工作区——以键盘操作为主、命令面板驱动，并作为如何用 Python 组合 WorldForge 的规范示例。相关工作分为六个里程碑（M0–M5），每个里程碑在 [`specs/`](https://github.com/AbdelStark/worldforge/tree/main/specs) 下都有已发布的规格三元组（`spec.md` + `plan.md` + `tasks.md`）：

| 里程碑 | 新增内容 |
| --- | --- |
| [M0 — 主题与外观重置](https://github.com/AbdelStark/worldforge/tree/main/specs/theworldharness-M0-theme-chrome) | 注册浅色/深色主题、语义 CSS 变量、顶栏时钟和面包屑导航。 |
| [M1 — 屏幕架构](https://github.com/AbdelStark/worldforge/tree/main/specs/theworldharness-M1-screen-architecture) | 应用拆分为具名 `Screen`、`push_screen` 导航、`?` 帮助浮层、`Ctrl+P` 系统命令。 |
| [M2 — Worlds CRUD](https://github.com/AbdelStark/worldforge/tree/main/specs/theworldharness-M2-worlds-crud) | 完全通过 TUI 调用公开的 `WorldForge` API 创建/编辑/保存/派生/删除世界。 |
| [M3 — 实时提供方](https://github.com/AbdelStark/worldforge/tree/main/specs/theworldharness-M3-live-providers) | `ProvidersScreen`，含能力矩阵及通过 Worker 流式传输的真实提供方调用；`Esc` 可取消。 |
| [M4 — 评估与基准测试](https://github.com/AbdelStark/worldforge/tree/main/specs/theworldharness-M4-eval-benchmark) | `EvalScreen` 和 `BenchmarkScreen`；能力不匹配以强提示形式显示；报告持久化到磁盘并可导出。 |
| [M5 — 打磨与案例展示](https://github.com/AbdelStark/worldforge/tree/main/specs/theworldharness-M5-polish-showcase) | 高对比度主题、动态命令面板提供方、最近项目、截图导出矩阵、README 截图刷新。 |

这些里程碑背后的意图和设计语言在公开[路线图](./roadmap.md)中作了概述。

# 使用场景手册

以下方案是 WorldForge 常见工作的可直接复制路径。每条方案均说明命令、预期输出、需保留的工件、首要排查步骤及非声明边界。当您需要为 Issue 或发布证据保留一次案例展示运行时，请使用对应的演示工作流。

### 方案 1：首次本地世界

| 字段 | 值 |
| --- | --- |
| 命令 | `uv run python scripts/demo_showcases.py run first-run --workspace-dir .worldforge/demo-showcases --overwrite` |
| 预期输出 | `status: passed`，一个模拟世界、一个对象、一次预测及预检状态 |
| 工件 | `.worldforge/demo-showcases/first-run/exported-world.json` |
| 首要排查步骤 | 运行 `uv run worldforge world preflight --state-dir .worldforge/demo-showcases/first-run/worlds` |
| 边界 | 仅限 mock 提供方；不声明物理保真度或真实运行时 |

### 方案 2：提供方诊断 Issue 包

| 字段 | 值 |
| --- | --- |
| 命令 | `uv run python scripts/demo_showcases.py run diagnostics-issue-bundle --workspace-dir .worldforge/demo-showcases --overwrite` |
| 预期输出 | 跳过的提供方诊断，`safe_to_attach: true` |
| 工件 | `.worldforge/demo-showcases/diagnostics-issue-bundle/issue-bundle/issue.md` |
| 首要排查步骤 | 打开 `evidence_manifest.json` 并确认 `safe_to_attach: true` |
| 边界 | 仅限夹具诊断；请勿粘贴原始提供方凭证或签名 URL |

### 方案 3：已准备宿主工作前的机器人重放

| 字段 | 值 |
| --- | --- |
| 命令 | `uv run python scripts/demo_showcases.py run robotics-replay --workspace-dir .worldforge/demo-showcases --overwrite` |
| 预期输出 | 选定的候选索引、候选代价、策略结果、打分结果及事件阶段 |
| 工件 | `.worldforge/demo-showcases/robotics-replay/robotics-replay-manifest.json` |
| 首要排查步骤 | 在运行 `scripts/robotics-showcase --health-only` 之前先运行 `uv run worldforge-demo-lerobot` |
| 边界 | 仅限确定性重放；机器人硬件、控制器、安全检查和检查点由宿主方持有 |

### 方案 4：提供方事件脱敏干运行

| 字段 | 值 |
| --- | --- |
| 命令 | `uv run python scripts/demo_showcases.py run provider-event-redaction-dry-run --workspace-dir .worldforge/demo-showcases --overwrite` |
| 预期输出 | 经脱敏处理的提供方事件夹具 |
| 工件 | `.worldforge/demo-showcases/provider-event-redaction-dry-run/provider-event-redaction-events.json` |
| 首要排查步骤 | 在实时冒烟测试前检查提供方事件的 `target`、`message` 和 `metadata` 是否经过脱敏处理 |
| 边界 | 仅限夹具支撑的干运行；不进行付费 API 调用，亦不保证工件保留 |

### 方案 5：适配器作者脚手架

| 字段 | 值 |
| --- | --- |
| 命令 | `uv run python scripts/demo_showcases.py run adapter-author --workspace-dir .worldforge/demo-showcases --overwrite` |
| 预期输出 | 生成的提供方、生成的测试、文档存根、运行时清单存根及工作台报告 |
| 工件 | `.worldforge/demo-showcases/adapter-author/generated-provider/` |
| 首要排查步骤 | 在晋级之前替换占位夹具并运行生成的提供方测试 |
| 边界 | 脚手架有意为失败关闭且不完整；它不是真实提供方行为的证据 |

### 方案 6：带预算失败的批量评估

| 字段 | 值 |
| --- | --- |
| 命令 | `uv run python scripts/demo_showcases.py run batch-eval --workspace-dir .worldforge/demo-showcases --overwrite` |
| 预期输出 | 评估任务通过，基准测试任务返回可控的 `exit_code: 1`，且两次运行均被保留 |
| 工件 | `.worldforge/demo-showcases/batch-eval/batch-host/runs/<run-id>/run_manifest.json` |
| 首要排查步骤 | 在更改阈值之前检查基准测试报告和复制的预算 |
| 边界 | 仅限 mock 提供方和不可能通过的预算；不涉及调度器、持久存储或发布预算声明 |

### 方案 7：标准库服务宿主冒烟测试

| 字段 | 值 |
| --- | --- |
| 命令 | `uv run python scripts/demo_showcases.py run service-host --workspace-dir .worldforge/demo-showcases --overwrite` |
| 预期输出 | 就绪状态为 `ready`，一次模拟预测请求被汇总，服务器关闭被记录 |
| 工件 | `.worldforge/demo-showcases/service-host/runs/<run-id>/results/summary.json` |
| 首要排查步骤 | 运行 `uv run python examples/hosts/service/app.py --provider mock --port 8080` 并检查 `/readyz` |
| 边界 | 仅限参考宿主；鉴权、部署、正常运行时间、仪表盘和回滚均由宿主方持有 |

### 方案 8：Rerun 展示库清单

| 字段 | 值 |
| --- | --- |
| 命令 | `uv run python scripts/demo_showcases.py run rerun-gallery --workspace-dir .worldforge/demo-showcases --overwrite` |
| 预期输出 | 因缺少 `rerun` 额外依赖而 `status: skipped`，并附展示库层清单 |
| 工件 | `.worldforge/demo-showcases/rerun-gallery/rerun-gallery-manifest.json` |
| 首要排查步骤 | 安装 `worldforge-ai[rerun]`，然后运行 `uv run --extra rerun worldforge-demo-rerun` |
| 边界 | 仅限 checkout 安全清单；可视化 `.rrd` 文件需要可选的 Rerun 运行时 |

### 方案 9：失败恢复实验室

| 字段 | 值 |
| --- | --- |
| 命令 | `uv run python scripts/demo_showcases.py run failure-lab --workspace-dir .worldforge/demo-showcases --overwrite` |
| 预期输出 | 凭证缺失、状态损坏、不安全元数据演练、预检及恢复命令 |
| 工件 | `.worldforge/demo-showcases/failure-lab/failure-lab-report.json` |
| 首要排查步骤 | 在操作真实 `.worldforge` 状态之前先阅读 `recovery_commands` |
| 边界 | 仅修改实验室工作区；不使用真实凭证、可选运行时或用户状态 |

### 方案 10：完整案例展示证据全扫描

| 字段 | 值 |
| --- | --- |
| 命令 | `uv run python scripts/demo_showcases.py run all --workspace-dir .worldforge/demo-showcases --format json --overwrite` |
| 预期输出 | 所有十个工作流报告 `passed` 或有意的 `skipped`，顶层状态为 `passed` |
| 工件 | `.worldforge/demo-showcases/<workflow>/runs/<run-id>/run_manifest.json` |
| 首要排查步骤 | 打开失败工作流的 `workflow-result.json`，再查看其保留的 `run_manifest.json` |
| 边界 | 仅限集成证据；可选运行时、提供方凭证、机器人及物理保真度声明均不在 checkout 路径内 |

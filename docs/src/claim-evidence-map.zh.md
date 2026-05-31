# 主张与证据对照图

Issue: [#140](https://github.com/AbdelStark/worldforge/issues/140)

状态：当前有效的公开证据图。

本页将 WorldForge 的公开主张与支持其的证据类别进行对应映射。在问题报告、发布证据或提供方晋升评审中引用 README 主张时，请参阅本页。本页不新增基准测试数据、不扩展提供方能力，也不将确定性检查转化为物理保真度主张。

## 证据类别

| 类别 | 含义 | 预期证据 |
| --- | --- | --- |
| `checkout-tested` | 无需凭据、网络、GPU 或可选模型运行时即可从干净检出运行。 | 本地 pytest、CLI、文档及包命令。 |
| `fixture-tested` | 由存放在仓库中的合成 JSON 夹具或录制的解析器夹具覆盖。 | `tests/fixtures/`、`worldforge.testing` 夹具、提供方解析器测试或契约辅助工具。 |
| `prepared-host smoke-tested` | 需要宿主方持有的凭据、检查点、可选运行时或机器人/模型资产。 | 一条文档化命令加上经过清理的 `run_manifest.json` 或冒烟测试注册表行。 |
| `release-gated` | 属于发布证据或 CI 质量门控的一部分。 | 覆盖率、包契约、基准测试预设、文档构建或发布证据报告。 |
| `deferred` | 设计或脚手架已存在，但可执行的公开行为被有意推迟。 | 明确的阻塞项、重新触发条件或关闭失败的脚手架文档。 |
| `unsupported` | WorldForge 不主张或不拥有此行为。 | 公开的非主张声明以及指向宿主方或上游负责人的首步路由。 |

## 能力主张

| 公开主张 | 证据类别 | 证据 | 命令或工件 | 边界 |
| --- | --- | --- | --- | --- |
| `predict` 是用于状态推演的提供方能力。 | `checkout-tested` | `tests/test_world_lifecycle.py`、`tests/test_provider_contracts.py`、`tests/test_capability_fixtures.py` | `uv run worldforge world predict <world-id> --object-id <object-id> --x 0.4 --y 0.5 --z 0` | 内置确定性检查不能证明物理保真度。 |
| `score` 为打分模型工作流对动作候选进行排序。 | `fixture-tested`；真实运行时使用 `prepared-host smoke-tested` | `tests/test_leworldmodel_provider.py`、`tests/test_jepa_provider.py`、`tests/test_jepa_wms_provider.py`、`tests/fixtures/providers/*score*` | `uv run worldforge-demo-leworldmodel`；`leworldmodel`、`jepa` 和 `jepa-wms` 的冒烟测试注册表行 | 张量、检查点、预处理和设备由宿主方持有。 |
| `policy` 返回具身特定的动作块。 | `fixture-tested`；真实运行时使用 `prepared-host smoke-tested` | `tests/test_lerobot_provider.py`、`tests/test_gr00t_provider.py`、`tests/test_provider_contracts.py` | `scripts/robotics-showcase --json-only --no-tui --no-rerun`；机器人 CI 中上传的 `run_manifest.json` | WorldForge 保留原始动作，并要求宿主方持有转换器才能执行动作。 |
| `embed` 是 mock 支持的窄能力接口。 | `checkout-tested` | `tests/test_provider_contracts.py`、`tests/test_capability_fixtures.py`、`tests/test_benchmark.py` | `uv run worldforge benchmark --preset parser-overhead` | 它是契约和适配器路径检查，而非通用嵌入质量主张。 |
| `plan` 是 WorldForge 对组合接口的门面封装。 | `checkout-tested` | `tests/test_evaluation_and_planning.py`、`tests/test_capability_dual_routing.py` | `uv run worldforge eval --suite planning --provider mock --format json` | 默认情况下，`plan` 不作为提供方持有的能力进行通告。 |

## 提供方与运行时主张

| 公开主张 | 证据类别 | 证据 | 命令或工件 | 边界 |
| --- | --- | --- | --- | --- |
| `mock` 提供方是稳定且确定性的。 | `checkout-tested`；`release-gated` | `tests/test_provider_contracts.py`、`tests/test_benchmark_presets.py` | `uv run worldforge benchmark --preset mock-smoke` | 合成提供方行为不是运行时保真度证据。 |
| Cosmos-Policy 是远程具身策略适配器。 | `fixture-tested`；已配置时使用 `prepared-host smoke-tested` | `tests/test_cosmos_policy_provider.py`、提供方文档、冒烟测试注册表 | `scripts/smoke_cosmos_policy.py --help` | 凭据、上游可用性、动作转换器和机器人安全由宿主方持有。 |
| LeWorldModel 暴露 `score` 能力。 | `fixture-tested`；`prepared-host smoke-tested` | `tests/test_leworldmodel_provider.py`、`tests/test_lerobot_leworldmodel_smoke_script.py`、冒烟测试注册表 | `scripts/robotics-showcase --json-only --no-tui --no-rerun` | `stable-worldmodel`、torch、检查点、张量和设备行为属于可选运行时关注事项。 |
| LeRobot 和 GR00T 暴露 `policy` 能力。 | `fixture-tested`；`prepared-host smoke-tested` | `tests/test_lerobot_provider.py`、`tests/test_gr00t_provider.py`、冒烟测试注册表 | LeRobot 使用 `scripts/robotics-showcase`；GR00T 设置使用 `scripts/smoke_gr00t_policy.py --help` | 机器人控制器、安全检查和动作转换器由宿主方持有。 |
| JEPA 是实验性的，仅支持 `score`。 | `fixture-tested`；仅在宿主方证据存在时使用 `prepared-host smoke-tested` | `tests/test_jepa_provider.py`、`tests/test_jepa_wms_provider.py`、运行时清单文档 | `uv run worldforge-smoke-jepa-wms --help` | Torch-hub 运行时、权重、预处理和许可证审查由宿主方持有。 |
| Genie 是脚手架占位。 | `deferred` | `tests/test_remote_scaffold_providers.py`、`docs/src/providers/genie.md` | Genie 提供方文档中的重新触发条件 | 不主张任何公开自动化 API 契约；脚手架行为保持关闭失败状态。 |
| Nano World Model 是候选项，而非提供方接口。 | `deferred` | `docs/src/provider-cohort-selection.md` | 在提出任何目录主张之前，请关注指定的候选 issue | 不导出或自动注册任何 `nanowm` 提供方。 |

## 工作流与工件主张

| 公开主张 | 证据类别 | 证据 | 命令或工件 | 边界 |
| --- | --- | --- | --- | --- |
| 评估报告包含来源信息和主张边界。 | `checkout-tested`；`release-gated` | `tests/test_provenance.py`、`tests/test_evaluation_and_planning.py`、`docs/src/evaluation.md` | `uv run worldforge eval --suite planning --provider mock --format json` | 分数是确定性的契约信号，而非物理或媒体质量指标。 |
| 评估报告可以引用数据集清单，而无需嵌入数据集本身。 | `checkout-tested`；`release-gated` | `tests/test_evaluation_suites.py`、`tests/test_evidence_bundle.py`、`docs/src/evaluation.md` | `uv run worldforge eval --suite planning --provider mock --dataset-manifest examples/dataset-manifests/mock-evaluation-fixtures.json --format json` | 清单记录来源、许可证、隐私、安全、校验和以及宿主方持有的获取步骤；数据集和已准备的资产存放于仓库之外。 |
| 失败的评估报告包含适合提交 issue 的失败图集。 | `checkout-tested`；`release-gated` | `tests/test_evaluation_failure_gallery.py`、`docs/src/evaluation.md`、`docs/src/api/python.md` | `uv run worldforge eval --suite planning --provider mock --format json` 加上 `report.artifacts()["failure_gallery.json"]` | 图集是经过清理的确定性契约分流工具，而非提供方排名或保真度证据。 |
| 基准测试报告包含来源信息、预算和预设门控。 | `checkout-tested`；`release-gated` | `tests/test_benchmark.py`、`tests/test_benchmark_presets.py`、`docs/src/benchmarking.md` | `uv run worldforge benchmark --preset release-evidence --format json --run-workspace .worldforge` | 计时数据是进程本地的适配器路径测量值，而非机器无关的性能主张。 |
| 基准测试预算变更保留了基准评审路径。 | `checkout-tested`；`release-gated` | `tests/test_benchmark_budget_calibration.py`、`scripts/calibrate_benchmark_budgets.py`、`docs/src/benchmarking.md` | `uv run python scripts/calibrate_benchmark_budgets.py --report .worldforge/reports/benchmark-<timestamp>-<run-id>.json --current-budget src/worldforge/benchmark_presets/_data/budget-release-evidence.json` | 候选预算是评审工件；它们不会自动削弱发布门控。 |
| 保留的运行对比在不创建排行榜的前提下对比兼容的提供方运行。 | `checkout-tested`；`release-gated` | `tests/test_harness_report_compare.py`、`tests/test_harness_workspace.py`、`docs/src/benchmarking.md` | `uv run worldforge runs compare .worldforge/runs/<baseline-run-id> .worldforge/runs/<candidate-run-id> --format markdown` | 当能力、操作、夹具摘要、预算或套件版本不匹配时，对比会失败；行数据是工件差异，而非跨任务的排名。 |
| 回归对比将候选运行与保留的基准进行比较。 | `checkout-tested`；`release-gated` | `tests/test_harness_report_compare.py`、`docs/src/benchmarking.md`、`docs/src/html-reports.md` | `uv run worldforge runs compare .worldforge/runs/<baseline-run-id> .worldforge/runs/<candidate-run-id> --mode regression --format markdown` | 报告指标差异、预算状态变更、新增和已移除的失败项、安全的工件漂移、来源差异以及不安全的工件排除；不自动更新基准。 |
| 评估证据包打包保留的运行。 | `checkout-tested`；`release-gated` | `tests/test_evidence_bundle.py`、`scripts/generate_evidence_bundle.py`、`docs/src/evaluation.md` | `uv run python scripts/generate_evidence_bundle.py --workspace-dir .worldforge` | 不安全、仅本地、已签名或二进制的工件会被排除或标记；该包不上传任何内容。 |
| 冒烟测试证据被索引到可发布的注册表中。 | `prepared-host smoke-tested`；`release-gated` | `tests/test_live_smoke_evidence.py`、`docs/src/live-smoke-evidence.json` | `uv run python scripts/generate_release_evidence.py --live-smoke-registry docs/src/live-smoke-evidence.json` | 缺失可选运行时或凭据是明确的跳过状态，而非静默遗漏。 |
| 安装扩展后，Rerun 记录经过清理的事件和工件。 | `checkout-tested`；机器人案例展示使用 `prepared-host smoke-tested` | `tests/test_rerun_integration.py`、`tests/test_robotics_showcase.py` | `uv run --extra rerun worldforge-demo-rerun`；`/tmp/worldforge-robotics-showcase/real-run.rrd` | Rerun 是可选的可观测性工具，而非提供方能力或基础依赖项。 |
| 机器人案例展示 TUI 是可选的，且与 Textual 隔离。 | `checkout-tested`；`release-gated` | `tests/test_robotics_showcase.py`、`tests/test_robotics_showcase_ci.py`、`tests/test_import_boundaries.py` | `scripts/robotics-showcase` | 非 TUI 机器人证据在不导入 Textual 的情况下仍可用。 |
| 本地 JSON 持久化是内置的权威存储。 | `checkout-tested` | `tests/test_world_lifecycle.py`、`tests/test_cli_world_commands.py`、持久化 ADR | `uv run worldforge world export <world-id> --output world.json` | 它不是并发多写入者数据库，也不是服务级持久化存储。 |
| 质量门控在 Python 3.13 上运行，包含覆盖率、文档、包和 lint 检查。 | `release-gated` | `.github/workflows/ci.yml`、`scripts/test_package.sh`、`docs/src/quality.md` | `uv run --extra harness pytest --cov=src/worldforge --cov-report=term-missing --cov-fail-under=90` | 通过门控不扩展运行时能力主张。 |

## 不支持的行为或非主张

| 非主张 | 证据类别 | 首步路由 |
| --- | --- | --- |
| 物理保真度、媒体质量、机器人安全认证或真实世界控制安全。 | `unsupported` | 将 WorldForge 报告仅视为适配器证据；请使用特定任务的宿主方评估和安全审查。 |
| 上游提供方 SLA、付费 API 可用性、速率限制、凭据管理或工件保留。 | `unsupported` | 检查提供方的上游状态、凭据和宿主方保留策略。 |
| 在 WorldForge 内部训练 LeWorldModel、JEPA、NanoWM、GR00T、LeRobot 或任何其他模型。 | `unsupported` | 使用上游训练仓库，并将工件存放于 WorldForge 基础包之外。 |
| 服务级持久化、数据库迁移、锁文件或多写入者存储。 | `unsupported` | 在引入宿主方存储之前，请遵循持久化适配器边界 ADR。 |
| 托管仪表板、遥测服务、队列、部署、认证或告警。 | `unsupported` | 在宿主应用中实现这些功能，并挂载经过清理的 WorldForge 运行工件。 |

## 使用说明

在问题报告或发布说明中引用时，请按主张引用对应行，并附上匹配的命令或工件。
预期成功信号为明确的测试通过计数、带有 `Status: passed` 的基准测试门控，或经验证的 `run_manifest.json`。若命令失败，首步排查应打开该行对应的文档页面，确认提供方属于以下哪种状态：checkout 安全、夹具支持、需要凭据、需要预备宿主机、已延迟，还是不支持。

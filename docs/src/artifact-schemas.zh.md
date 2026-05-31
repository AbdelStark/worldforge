# 工件结构定义

WorldForge 工件是可能跨进程传递的 JSON 原生记录：运行清单、证据包、场景、基准测试输入、报告元数据、世界差异及类似文件。每个公开或半公开的工件族在结构变更之前都需要一个所有者、一个版本字段、验证覆盖以及迁移决策。

私有临时文件、缓存内部文件、检查点文件、下载的数据集和仅本地的不安全工件不在此兼容性图的范围内。除非另有文档化的契约标记其为安全可附加，否则这些文件仍必须排除在公开包之外。

## 所有权图

| 工件族 | 版本字段 | 所有者与来源 | 验证面 | 文档与 CLI 接口 | 迁移所有者 |
| --- | --- | --- | --- | --- | --- |
| 世界状态 JSON | 通过 `SCHEMA_VERSION` 的 `schema_version` | `src/worldforge/_state.py` | `tests/test_world_lifecycle.py`、`tests/test_cli_world_commands.py` | `worldforge world ...`、[Operations](./operations.md) | 框架与持久化所有者 |
| 运行清单 | 通过 `RUN_MANIFEST_SCHEMA_VERSION` 的 `schema_version` | `src/worldforge/smoke/run_manifest.py` | `tests/test_smoke_run_manifest.py`、可选冒烟测试 | `--run-manifest`、[冒烟测试实时证据注册表](./live-smoke-evidence.md) | 可选运行时与冒烟测试所有者 |
| 运行工作区 | 通过 `RUN_WORKSPACE_SCHEMA_VERSION` 的 `schema_version` | `src/worldforge/harness/workspace.py` | `tests/test_harness_workspace.py`、`tests/test_harness_flows.py` | `worldforge runs ...`、[Run Artifact Index](./run-index.md) | Harness 工作区所有者 |
| 运行索引报告 | 通过 `RUN_INDEX_SCHEMA_VERSION` 的 `schema_version` | `src/worldforge/harness/run_index.py` | `tests/test_run_index.py` | `worldforge runs index`、[Run Artifact Index](./run-index.md) | Harness 工作区所有者 |
| 运行裁剪报告 | 通过 `RUNS_PRUNE_SCHEMA_VERSION` 的 `schema_version` | `src/worldforge/runs_prune.py` | `tests/test_runs_prune.py` | `worldforge runs prune`、[Run Artifact Index](./run-index.md) | Harness 工作区所有者 |
| 证据包与 issue 包 | 通过 `EVIDENCE_BUNDLE_SCHEMA_VERSION` 的 `schema_version` | `src/worldforge/evidence_bundle.py` | `tests/test_evidence_bundle.py`、`tests/test_redaction_corpus.py` | `worldforge runs bundle`、[工件完整性](./artifact-integrity.md) | 证据所有者 |
| 发布证据 JSON | 字面量 `1` 的 `schema_version` | `scripts/generate_release_evidence.py` | `tests/test_release_evidence.py` | `scripts/generate_release_evidence.py`、[工件完整性](./artifact-integrity.md) | 发布所有者 |
| 依赖项审计证据 | 通过 `DEPENDENCY_AUDIT_EVIDENCE_SCHEMA_VERSION` 的 `schema_version` | `scripts/generate_dependency_audit_evidence.py` | `tests/test_dependency_audit_evidence.py` | `scripts/generate_dependency_audit_evidence.py`、[工件完整性](./artifact-integrity.md) | 发布所有者 |
| 质量仪表板工件 | 通过 `QUALITY_DASHBOARD_SCHEMA_VERSION` 的 `schema_version` | `scripts/generate_quality_dashboard.py` | `tests/test_quality_dashboard.py` | `scripts/generate_quality_dashboard.py`、[工件完整性](./artifact-integrity.md) | 发布所有者 |
| 基准测试输入与预算 | 夹具载荷中的 `schema_version` | `src/worldforge/benchmark_inputs.py`、`src/worldforge/benchmark_budgets.py`、`src/worldforge/benchmark.py` | `tests/test_benchmark.py`、`tests/test_benchmark_presets.py` | `worldforge benchmark --input-file`、[Benchmarking](./benchmarking.md) | 基准测试所有者 |
| 基准测试校准报告 | 通过 `BENCHMARK_CALIBRATION_SCHEMA_VERSION` 的 `schema_version` | `src/worldforge/benchmark_calibration.py` | `tests/test_benchmark_budget_calibration.py` | `scripts/calibrate_benchmark_budgets.py`、[Benchmarking](./benchmarking.md) | 基准测试所有者 |
| 评估报告与来源信息 | 通过 `PROVENANCE_SCHEMA_VERSION` 的 `schema_version` | `src/worldforge/provenance.py`、`src/worldforge/evaluation/report.py` | `tests/test_evaluation_suites.py`、`tests/test_provenance.py` | `worldforge eval`、[Evaluation](./evaluation.md) | 评估所有者 |
| 数据集清单 | 通过 `DATASET_MANIFEST_SCHEMA_VERSION` 的 `schema_version` | `src/worldforge/dataset_manifests.py` | `tests/test_evaluation_suites.py`、`tests/test_evidence_bundle.py` | `worldforge eval --dataset-manifest`、[Evaluation](./evaluation.md) | 评估所有者 |
| 评估失败图集 | 通过 `EVALUATION_FAILURE_GALLERY_SCHEMA_VERSION` 的 `schema_version` | `src/worldforge/evaluation/failure_gallery.py` | `tests/test_evaluation_failure_gallery.py` | [Evaluation](./evaluation.md) | 评估所有者 |
| 能力夹具语料库 | 通过 `FIXTURE_SCHEMA_VERSION` 的 `schema_version` | `src/worldforge/testing/capability_fixtures.py` | `tests/test_capability_fixtures.py` | [Capability Fixture Corpus](./fixtures.md) | 测试所有者 |
| 夹具快照清单 | 通过 `FIXTURE_SNAPSHOT_MANIFEST_SCHEMA_VERSION` 的 `schema_version` | `src/worldforge/testing/fixture_snapshots.py` 和 `tests/fixtures/fixture-snapshots.json` | `tests/test_capability_fixtures.py` | `scripts/manage_fixture_snapshots.py`、[Capability Fixture Corpus](./fixtures.md) | 测试所有者 |
| 提供方运行时清单 | 通过 `MANIFEST_SCHEMA_VERSION` 的 `schema_version` | `src/worldforge/providers/runtime_manifest.py` 和 `src/worldforge/providers/runtime_manifests/*.json` | `tests/test_provider_runtime_manifests.py` | 生成的提供方文档、[Provider Authoring Guide](./provider-authoring-guide.md) | 提供方所有者 |
| 运行时资产清单与引用 | 通过 `RUNTIME_ASSET_MANIFEST_SCHEMA_VERSION` 的 `schema_version` | `src/worldforge/providers/runtime_manifest.py`、`src/worldforge/smoke/runtime_assets.py` | `tests/test_runtime_profiles.py`、`tests/test_robotics_showcase.py` | `run_manifest.runtime_assets`、[Operations](./operations.md) | 可选运行时与冒烟测试所有者 |
| 非密钥配置文件 | 通过 `CONFIG_PROFILE_SCHEMA_VERSION` 的 `schema_version` | `src/worldforge/config_profiles.py` | `tests/test_provider_config.py`、`tests/test_harness_workspace.py` | `worldforge eval --profile`、`worldforge benchmark --profile`、[Operations](./operations.md) | 操作与提供方所有者 |
| 提供方契约证据 | 通过 `PROVIDER_CONTRACT_EVIDENCE_SCHEMA_VERSION` 的 `schema_version` | `src/worldforge/provider_contracts.py` | `tests/test_provider_contracts.py`、`tests/test_provider_entry_points.py` | `worldforge provider contract`、[Provider Authoring Guide](./provider-authoring-guide.md)、[External Provider Packages](./external-providers.md) | 提供方所有者 |
| 能力协商报告 | 通过 `CAPABILITY_NEGOTIATION_SCHEMA_VERSION` 的 `schema_version` | `src/worldforge/capability_negotiation.py` | `tests/test_capability_negotiation.py` | `worldforge negotiate`、[Capability Negotiation](./capability-negotiation.md) | 提供方诊断所有者 |
| 场景文件与场景结果 | 通过 `SCENARIO_SCHEMA_VERSION` 的 `schema_version`（接受集合：`SCENARIO_SUPPORTED_SCHEMA_VERSIONS`；`extends` 要求 `SCENARIO_EXTENDS_MIN_SCHEMA_VERSION`） | `src/worldforge/scenarios.py` | `tests/test_scenarios.py`、`tests/test_scenario_inheritance.py` | `worldforge scenario ...`、[Scenario Definition Format](./scenarios.md) | 场景所有者 |
| 世界差异与补丁工件 | 通过 `WORLD_DIFF_SCHEMA_VERSION` 的 `schema_version` | `src/worldforge/world_diff.py` | `tests/test_world_diff.py` | `worldforge world diff`、[World State Diff And Patch](./world-diff.md) | 持久化所有者 |
| 世界迁移预览 | 通过 `WORLD_MIGRATION_PREVIEW_SCHEMA_VERSION` 的 `schema_version` | `src/worldforge/world_migration_preview.py` | `tests/test_world_lifecycle.py`、`tests/test_cli_world_commands.py` | `worldforge world migration-preview`、[Operations](./operations.md) | 持久化所有者 |
| 工作流追踪工件 | 通过 `WORKFLOW_TRACE_SCHEMA_VERSION` 的 `schema_version` | `src/worldforge/workflow_trace.py` | `tests/test_provider_events.py`、`tests/test_evaluation_and_planning.py`、`tests/test_rerun_integration.py` | 规划元数据、评估工件、Rerun 工件记录、[Operations](./operations.md) | 可观测性与工件所有者 |
| 静态 HTML 报告元数据 | 通过 `HTML_REPORT_SCHEMA_VERSION` 的 `schema_version` | `src/worldforge/html_report.py` | `tests/test_html_report.py` | `--format html`、[Static HTML Reports](./html-reports.md) | 报告渲染所有者 |
| 冒烟测试实时证据注册表 | 通过 `LIVE_SMOKE_EVIDENCE_SCHEMA_VERSION` 的 `schema_version` | `src/worldforge/live_smoke_evidence.py`、`docs/src/live-smoke-evidence.json` | `tests/test_live_smoke_evidence.py` | [冒烟测试实时证据注册表](./live-smoke-evidence.md) | 可选运行时与冒烟测试所有者 |
| 能力特定的回放工件 | 各族专属的 `schema_version` 常量 | `src/worldforge/harness/flows.py` | `tests/test_cosmos_policy_provider.py`、`tests/test_harness_flows.py` | [Robotics Replay Showcase](./robotics-showcase.md) | Harness 与机器人所有者 |

## 变更规则

使用最小兼容变更，确保旧工件仍然诚实可读。

| 变更类型 | 必需操作 |
| --- | --- |
| 可选字段新增（加法） | 若旧读取器能安全忽略该字段，则保持现有结构版本。添加证明字段缺席和存在两种行为的测试。当用户可能看到该字段时，在所属文档中提及。 |
| 必填字段新增（加法） | 升级结构版本，或提供代码和测试中明确说明的兼容默认值。若现有用户编写的工件需要处理，添加变更日志条目。 |
| 破坏性重命名、删除或类型变更 | 升级结构版本，除非存在读取器迁移，否则大声拒绝不支持的旧版本；更新本页及所属文档，并添加变更日志迁移说明。 |
| 仅渲染器的布局变更 | 若 JSON 载荷语义不变，则不升级源工件结构。仅在用户可见行为变化时更新渲染器测试和文档截图/示例。 |
| 私有实现元数据 | 尽量不出现在公开工件中。若必须出现在公开 JSON 记录中，请说明其是稳定、临时还是仅本地的。 |
| 安全或隐去修复 | 优先立即严格拒绝或隐去，而非向后兼容。在 PR 和变更日志中说明不安全的旧行为、迁移或恢复命令以及验证覆盖。 |

所有公开或半公开工件必须只包含字符串键、有限数字、列表、对象、布尔值、字符串和空值。不得将元组、对象实例、异常、原始张量、凭据、签名 URL 查询字符串、私有端点、检查点内容或宿主本地缓存载荷序列化到可附加的工件中。

## 迁移决策

每个工件 PR 在合并前应回答以下问题：

- 该工件是公开、半公开、仅本地还是私有的？
- 哪个模块拥有写入器和读取器？
- 当前的 `schema_version` 是什么，此次变更是否需要升级版本号？
- 若旧工件仍可读，哪个测试证明了该兼容性？
- 若旧工件被拒绝，用户会看到什么确切的错误提示和恢复路径？
- 当用户编写的文件受到影响时，文档和变更日志是否解释了迁移方法？
- 在 issue、发布、HTML、Rerun 或指标渲染之前，不安全字段是否被排除或标记为仅本地？

## 可接受的兼容性模式

- 读取器接受较旧的加法版本，并在验证之前填充有明确文档说明的默认值。
- 渲染器忽略未知的可选键，同时在原始工件中保留原始 JSON。
- 迁移预览命令默认情况下不重写用户文件，仅报告所需变更。
- 无迁移决策通过 `WorldStateError`、`WorldForgeError` 或 `ProviderError` 拒绝不支持的版本，并在错误信息中指出工件族、版本、所有者和首步排查命令。

不得静默强制转换无效的持久化状态、提供方输出或安全敏感的工件字段以保持旧工件可加载。

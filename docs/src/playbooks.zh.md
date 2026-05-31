# 用户与运维方操作手册

本手册面向从代码库检出运行 WorldForge、将其嵌入任务或服务，以及维护提供方适配器的人员。每本手册说明适用场景、需要运行的命令、成功的判断标准，以及失败时的排查方向。

WorldForge 仍然是一个库。它不负责部署、凭据存储、机器人安全、多写者持久化、仪表盘或工件留存。这些均属于宿主方的职责。

## 1. 初始化干净的代码库检出

在修改代码、审查提供方分支或复现已报告问题之前使用本节。

```bash
uv sync --group dev
uv lock --check
uv run worldforge doctor
uv run worldforge examples
uv run python scripts/generate_provider_docs.py --check
uv run python scripts/check_docs_commands.py
uv run python scripts/check_docs_snippets.py
uv run python scripts/check_wrapper_portability.py
uv run python scripts/check_optional_import_boundaries.py
uv run mkdocs build --strict
uv run pytest tests/test_cli_help_snapshots.py tests/test_provider_catalog_docs.py
```

成功信号：

- `doctor` 显示 `mock` 已注册，且仅在环境变量缺失时将可选提供方报告为未找到或未注册。
- 提供方文档已是最新状态。
- MkDocs Material 站点无警告地完成构建。
- 聚焦测试在不使用实时凭据的情况下通过。

失败时：

| 现象 | 首要检查项 | 可能的责任方 |
| --- | --- | --- |
| `uv lock --check` 失败 | 依赖文件已更改，但未刷新锁文件 | 贡献者 |
| 提供方文档偏移 | 运行 `uv run python scripts/generate_provider_docs.py` 并检查差异 | 贡献者 |
| 可选提供方意外出现在已注册列表中 | 检查本地 `.env` 和 shell 环境变量 | 运维方 |
| 测试尝试访问实时服务 | 替换为夹具、假传输层或注入式运行时 | 贡献者 |

### 1a. 保留检出安全的演示证据

当您需要为缺陷报告、路线图议题、发布说明或维护者审查提供可复现的演示运行，且不依赖凭据或可选运行时时，使用本节。

```bash
uv run python scripts/demo_showcases.py list
uv run python scripts/demo_showcases.py run all --workspace-dir .worldforge/demo-showcases --format json --overwrite
```

成功信号：顶层状态为 `passed`；各工作流状态为 `passed`，或因缺少可选扩展包而显示有意为之的 `skipped`。每个工作流会写入 `.worldforge/demo-showcases/<workflow>/workflow-result.json` 以及保留的 `.worldforge/demo-showcases/<workflow>/runs/<run-id>/run_manifest.json`。

失败时：

| 现象 | 首要检查项 | 可能的责任方 |
| --- | --- | --- |
| `first-run` 失败 | 运行 `uv run worldforge world preflight --state-dir .worldforge/demo-showcases/first-run/worlds` | 贡献者 |
| 诊断包不适合附件提交 | 打开 `issue-bundle/evidence_manifest.json` 并检查被排除的文件 | 报告方 |
| 机器人回放失败 | 运行 `uv run worldforge-demo-lerobot` 并检查提供方事件阶段 | 贡献者 |
| 提供方事件脱敏干运行泄露了查询字符串 | 检查 `provider-event-redaction-events.json` 及提供方事件脱敏语料库 | 贡献者 |
| 批量基准测试状态发生变化 | 在修改阈值前检查已复制的预算和基准测试报告 | 性能维护者 |

运行器不安装 LeRobot、LeWorldModel、GR00T、torch、Rerun、检查点、模拟器或提供方凭据。它不发起付费 API 调用、不控制硬件，也不声称具备物理保真度。

## 2. 选择正确的提供方接口

在编写应用代码或添加适配器之前使用本节。从操作需求出发，而不是从提供方名称出发。

| 需求 | 能力 | 首要命令 |
| --- | --- | --- |
| 根据动作推进世界状态 | `predict` | `uv run worldforge doctor --capability predict` |
| 对候选动作排序 | `score` | `uv run worldforge doctor --capability score` |
| 选择具身动作块 | `policy` | `uv run worldforge doctor --capability policy` |
| 对文本进行嵌入 | `embed` | `uv run worldforge doctor --capability embed` |

然后检查提供方档案：

```bash
uv run worldforge provider list
uv run worldforge provider info mock
uv run worldforge provider docs
```

成功信号：提供方恰好公告了您的工作流所调用的方法。如果工作流同时需要 policy 和 score，请分别配置一个 policy 提供方和一个 score 提供方，而不是强行让某一适配器声称其不具备的能力。

Python 集成可以使用已注册的完整提供方，也可以使用窄能力协议：

```python
from worldforge import ActionScoreResult, WorldForge


class LocalCost:
    name = "local-cost"
    profile = None

    def score_actions(self, *, info, action_candidates):
        return ActionScoreResult(provider=self.name, scores=[0.1], best_index=0)


forge = WorldForge(auto_register_remote=False)
forge.register_cost(LocalCost())
assert forge.doctor(capability="score", registered_only=True).provider_count == 1
```

## 3. 添加或晋级提供方适配器

适用于新提供方的开发工作，以及将脚手架晋级为真正适配器的场景。

```bash
uv run python scripts/scaffold_provider.py "Acme WM" \
  --taxonomy "JEPA latent predictive world model" \
  --implementation-status scaffold \
  --planned-capability score \
  --remote \
  --env-var ACME_WM_API_KEY
```

在将任何能力标志设置为 `True` 之前，需证明完整的契约：

- 在可能的情况下，在调用网络或模型之前对调用方输入进行验证。
- 上游输出通过显式辅助函数解析，格式错误的夹具会触发失败。
- 受支持的方法返回 `PredictionPayload`、`ActionScoreResult`、`ActionPolicyResult` 或 `EmbeddingResult`（视情况而定）。
- 不受支持的方法继承 `BaseProvider` 的 `ProviderError` 行为。
- `health()` 开销小，并能清晰报告缺失的凭据或可选依赖。
- 文档说明配置、运行时归属、输入形状、输出模式、限制、失败模式和冒烟路径。

如果集成仅涉及一个窄的本地接口，优先实现能力协议，而不是创建一个大部分为空的 `BaseProvider` 子类。使用 `register_cost`、`register_policy`、`register_predictor` 或 `register_embedder` 注册它；它仍会出现在 `providers()`、`provider_profile(...)`、`doctor(...)`、规划和基准测试路由中。

验证：

```bash
uv sync --group dev
uv run ruff check src tests examples scripts
uv run ruff format --check src tests examples scripts
uv run python scripts/generate_provider_docs.py --check
uv run pytest tests/test_provider_contracts.py tests/test_provider_catalog_docs.py
uv run --extra harness pytest --cov=src/worldforge --cov-report=term-missing --cov-fail-under=90
```

成功信号：提供方契约辅助函数对所有受支持的接口通过验证，每种已记录的失败模式都有对应的夹具或假运行时测试，且生成的提供方目录无偏移。

## 4. 诊断提供方可用性

当工作流提示某提供方未注册、不健康或缺少某项能力时使用本节。

```bash
uv run worldforge doctor
uv run worldforge doctor --registered-only
uv run worldforge doctor --capability score
uv run worldforge provider health
uv run worldforge provider info leworldmodel
```

结果解读：

- `doctor` 默认包含已知可选提供方，以便将缺失的配置清晰呈现。
- `--registered-only` 仅显示当前进程中已激活的提供方。
- 能力过滤是严格的。例如 `generation` 这样的拼写错误会触发框架错误，而不是返回空列表。
- 远程提供方通常通过环境变量注册；注入式提供方通过宿主代码注册。

失败时：

| 现象 | 可能原因 | 处理方式 |
| --- | --- | --- |
| 提供方未知 | 适配器不在目录中，或未手动注册 | 检查 `src/worldforge/providers/catalog.py` 或宿主注册逻辑 |
| 提供方已知但未注册 | 必要的环境变量缺失 | 加载 `.env`，导出变量，重启进程 |
| 提供方已注册但不健康 | 可选依赖、端点或凭据无效 | 查阅提供方专属文档和健康命令 |
| 提供方缺少某项能力 | 能力标志如实标记，工作流选择了错误的提供方 | 选择其他提供方，或端到端地实现该能力 |

### 4a. 排查错误类型

当议题、运行清单或运维日志报告了公开的 WorldForge 异常时，使用以下矩阵。不要捕获这些错误后用强制转换的状态继续运行；每种错误类型均指向具体的责任方和首要工件。

| 错误类型 | 常见现象 | 可能的责任方 | 首要命令 | 预期工件或信号 | 首要排查步骤 |
| --- | --- | --- | --- | --- | --- |
| `WorldForgeError` | 无效的公开输入、未知能力、不支持的输出格式、非有限数值、不安全的工件引用 | 调用方或贡献者 | `uv run worldforge doctor --registered-only` | 包含框架和提供方配置状态的 JSON 诊断信息 | 修复调用方输入，或为被拒绝的公开边界添加回归测试 |
| `WorldStateError` | 本地世界 JSON 损坏、路径遍历形式的世界 ID、无效的历史条目、不一致的对象包围盒 | 运维方负责本地状态；若由 CLI 写入则为贡献者 | `uv run worldforge world preflight --state-dir .worldforge/worlds --workspace-dir .worldforge --format json` | 包含 `status`、`safe_to_attach`、`error_count` 及恢复命令的 `worldforge-state-preflight.json` | 导出诊断信息，仅在审阅报告后隔离无效文件 |
| `ProviderError` | 缺少凭据、缺少可选依赖、上游响应格式错误、不支持的提供方能力、工件 URL 过期 | 首先由宿主运行时负责人处理；若解析器或文档有误则由适配器维护者处理 | `uv run worldforge provider info <provider>` | 脱敏的配置摘要、提供方档案、能力标志、生命周期状态、健康信息及有类型的提供方详情 | 附上经脱敏处理的运行清单或议题包；切勿粘贴原始凭据或签名 URL |
| 来自 `worldforge.testing` 的 `AssertionError` | 提供方一致性辅助函数报告契约失败 | 适配器贡献者 | `uv run pytest tests/test_provider_contracts.py -q` | 辅助函数明确指出缺失能力行为的失败信息 | 修复适配器或其夹具；不要用裸 `assert` 替换辅助函数检查 |
| 基准测试预算非零退出 | 基准测试门控未通过 JSON 预算检验 | 发布方或性能维护者 | `uv run worldforge benchmark --preset mock-smoke --run-workspace .worldforge --format json` | 保留了 `run_manifest.json`、报告 JSON 和预算状态的运行工作空间 | 在修改阈值之前，检查预算行和保留的输入 |
| MkDocs strict 警告 | 链接损坏、导航偏移或生成文档不匹配 | 文档贡献者 | `uv run mkdocs build --strict` | 指出问题页面或链接的严格构建输出 | 同步 `mkdocs.yml`、`docs/src/SUMMARY.md` 及源页面链接 |

公开议题应在可用时附上 `worldforge runs bundle <run-id>` 或 `scripts/generate_evidence_bundle.py` 的输出。涉及安全的故障仍需通过私有 Security 标签页提交。

### 4b. 在故障期间映射健康状态与就绪状态

当服务宿主、批处理任务或运维仪表盘需要决定是否向提供方支持的工作流发送流量时使用本节。请将进程存活性与提供方就绪性分开处理。

| 状态 | 现象 | 可能原因 | 首要命令 | 预期信号 | 上报节点 |
| --- | --- | --- | --- | --- | --- |
| 进程存活 | `GET /healthz` 成功，但提供方工作流可能仍会失败 | HTTP 进程正在运行；提供方路径尚未经过验证 | `curl -fsS http://127.0.0.1:8080/healthz` | JSON 状态为 `live`；不包含提供方字段 | 若进程宕机，联系宿主服务负责人 |
| 提供方未配置 | `/readyz` 返回 `provider_unconfigured`，或 `doctor` 显示该提供方不在已注册列表中 | 环境变量缺失、宿主注入缺失或提供方名称错误 | `uv run worldforge doctor --registered-only` | 所选提供方缺失；`registered_provider_count` 和 issues 字段说明了本地进程的情况 | 宿主部署方或凭据负责人 |
| 提供方不健康 | `/readyz` 返回 `provider_unhealthy`，或 `provider health` 报告 `healthy=false` | 可选运行时缺失、凭据错误、上游不可达，或提供方健康检查解析失败 | `uv run worldforge provider health <name>` | 健康详情指出缺失的环境变量、依赖、端点或经脱敏处理的上游错误 | 首先联系宿主运行时负责人；若详情有误或不安全，联系提供方适配器维护者 |
| 上游降级 | 提供方健康状态间歇性为 false，提供方事件显示重试、5xx、429 或预算耗尽 | 远程提供方故障、限流、凭据过期或宿主预算过紧 | `jq 'select(.phase=="retry" or .phase=="budget_exceeded") | {provider, operation, status_code, target, message}' .worldforge/runs/<run-id>/provider-events.jsonl` | 经脱敏处理的目标端点、重试次数、状态类别和 `budget_exceeded` 事件可定位失败操作 | 上游提供方支持团队或宿主 SRE；WorldForge 不负责上游 SLA |
| 工作流失败 | `/readyz` 保持 `ready`，但单个请求返回有类型的错误 | 世界状态格式错误、能力不支持、输入无效、解析器失败或工件过期 | `uv run worldforge provider info <name>` | 档案、能力标志、脱敏配置摘要、生命周期状态和健康信息揭示请求是否与提供方契约匹配 | 应用负责人处理无效输入；适配器维护者处理解析器/契约缺陷 |

标准库服务参考使用相同模型：`/healthz` 仅用于进程存活性探测，而 `/readyz` 返回 `ready`、`provider_unconfigured` 或 `provider_unhealthy`，以及 `accept` 或 `drain` 的流量决策。告警路由、呼叫策略、单次提供方调用之外的重试编排以及上游 SLA 归属，均属于宿主职责。

## 4c. 部署参考宿主

在将标准库服务宿主、批量评估宿主或机器人运维宿主移交给其他宿主进程负责人之前使用本节。

```bash
uv run python examples/hosts/service/app.py --provider mock --port 8080
uv run python examples/hosts/batch-eval/app.py benchmark --provider mock --operation predict --iterations 1
uv run python examples/hosts/robotics-operator/app.py review --sample-translator --approve-dry-run \
  --check workspace_clear --check emergency_stop_available --check operator_present --check controller_isolated
```

成功信号：服务宿主返回 `status: ready` 且 `traffic: accept` 的 `/readyz` 响应；批处理宿主打印 `status: passed` 和 `run_manifest`；机器人运维宿主打印 `status: passed`、`run_manifest` 及 `controller_executed: false`。

失败时：首先参考[参考宿主部署方案](./examples.md#reference-host-deployment-recipes)。该文档包含环境模板、进程命令、就绪检查命令、冒烟命令、日志命令、证据导出命令，以及适用于检出安全、已准备宿主、需凭据、绑定 GPU 和机器人实验室路径的首要回滚或排查步骤。部署、认证、队列、持久化存储、控制器集成、告警、正常运行时间和安全认证均属于宿主方职责。

## 4d. 排练运维故障演练

在依赖某份事故手册之前使用本节。这些演练是确定性的且检出安全的；每次演练会在临时或已记录的工作空间下写入保留的运行清单，并记录预期故障及恢复命令。

```bash
uv run worldforge drills list
uv run worldforge drills run missing-credentials --workspace-dir .worldforge/drills
uv run worldforge drills run unsafe-event-metadata --workspace-dir .worldforge/drills --bundle
uv run worldforge drills run all --workspace-dir .worldforge/drills
```

| 演练名称 | 预期故障 | 恢复命令 |
| --- | --- | --- |
| `missing-credentials` | 无值配置摘要中缺少必要的提供方凭据 | 加载所需环境变量，然后运行 `uv run worldforge provider health leworldmodel` |
| `missing-optional-dependency` | 可选运行时导入缺失 | 在已准备好的宿主上安装提供方可选运行时，然后重新运行其冒烟命令 |
| `malformed-provider-output` | 提供方解析器拒绝格式错误的夹具 | 附上经脱敏处理的夹具，修复解析器或上游契约 |
| `budget-violation` | 模拟基准测试违反了刻意设置为不可能达到的延迟预算 | 检查运行包，然后重新运行 `uv run worldforge benchmark --provider mock --operation predict --iterations 1` |
| `corrupted-world-state` | 格式错误的本地世界 JSON 文件触发 `WorldStateError` | 导出诊断信息，隔离损坏文件，然后重新创建或导入有效的世界 |
| `expired-artifact` | 工件描述符的过期时间戳已在过去 | 重新运行提供方工作流以刷新工件，然后导出新的议题包 |
| `unsafe-event-metadata` | 非 JSON 原生的事件元数据被拒绝，且形如密钥的字段被脱敏 | 删除对象或元组元数据，仅保留 JSON 原生字段，然后重新运行工作流 |

成功信号：演练命令以 `0` 退出，打印 `status: passed`，并写入一份状态为 `failed` 的运行清单（因为所排练的事故已被观测到）。使用 `--bundle` 时，命令还会写入 `.worldforge/drills/issue-bundles/<run-id>/issue.md`。

意外失败时：首先检查 `<workspace>/runs/<run-id>/results/drill.json`，然后在修改夹具之前运行 `uv run worldforge runs bundle <run-id> --workspace-dir <workspace>`。演练不得修改用户的世界；损坏状态的输入文件会写入演练运行的工作空间下。

## 5. 操作本地 JSON 持久化

适用于本地任务、演示、测试和单写者工作流。

CLI：

```bash
uv run worldforge world create lab --provider mock
uv run worldforge world create seeded-lab --provider mock --prompt "A kitchen with a mug"
uv run worldforge world add-object <world-id> cube --x 0 --y 0.5 --z 0 --object-id cube-1
uv run worldforge world update-object <world-id> cube-1 --x 0.2 --y 0.5 --z 0 --graspable true
uv run worldforge world predict <world-id> --object-id cube-1 --x 0.4 --y 0.5 --z 0
uv run worldforge world list
uv run worldforge world objects <world-id>
uv run worldforge world show <world-id>
uv run worldforge world history <world-id>
uv run worldforge world preflight --state-dir .worldforge/worlds --workspace-dir .worldforge
uv run worldforge world migration-preview <world-id> --state-dir .worldforge/worlds
uv run worldforge world migration-preview world.json --source-path
uv run worldforge world export <world-id> --output world.json
uv run worldforge world import world.json --new-id --name lab-copy
uv run worldforge world fork <world-id> --history-index 0 --name lab-start
uv run worldforge world delete <world-id>
```

Python：

```python
from worldforge import WorldForge

forge = WorldForge(state_dir=".worldforge/worlds")
world = forge.create_world("lab", provider="mock")
world_id = forge.save_world(world)

payload = forge.export_world(world_id)
restored = forge.import_world(payload, new_id=True, name="lab-copy")
forge.save_world(restored)
forge.delete_world(world_id)
```

成功信号：

- 世界 ID 是文件安全的本地标识符。
- 保存的 JSON 在覆盖目标文件之前会经过验证。
- CLI 的 create/import/fork/object/predict 命令与 Python 的 `save_world(...)` 使用相同的验证路径进行保存。
- object 的 add/update/remove 命令会追加带有类型化 `Action` 载荷的显式历史条目，且位置更新会以新姿态转换对象的包围盒。
- `world delete` 和 `WorldForge.delete_world(...)` 在解除本地 JSON 文件链接前验证世界 ID，并在文件已不存在时触发 `WorldStateError`。
- `world predict` 默认持久化提供方更新后的状态；使用 `--dry-run` 可在不替换本地 JSON 文件的情况下查看预测结果。
- 导入的状态会拒绝格式错误的场景对象、无效的历史记录、负数步骤以及路径遍历形式的 ID。
- `world preflight` 在不修改本地文件的情况下，报告损坏的世界 JSON、路径遍历形式的请求 ID、无效的历史条目、不一致的对象包围盒、陈旧的运行工作空间、不安全的工件路径以及留存压力。
- `world migration-preview` 在不修改本地文件的情况下，针对持久化世界或导出的 JSON，报告模式版本、所需变更、无效字段、不安全 ID、包围盒修正及 `can_apply_safely`。

恢复指南：

- 在移动或删除任何本地状态之前，运行 `uv run worldforge world preflight --state-dir .worldforge/worlds --workspace-dir .worldforge --format json > worldforge-state-preflight.json`。
- 在将模式重写应用于本地 JSON 之前，运行 `uv run worldforge world migration-preview <world-id> --state-dir .worldforge/worlds --format json > worldforge-migration-preview.json`；对于导出的世界 JSON 使用 `--source-path`。
- 若本地 JSON 已损坏，从宿主应用程序对导出世界 JSON 的备份中恢复。
- 若报告指出存在陈旧的运行工作空间或不安全的工件路径，在清单有效时导出运行包；否则在保留预检报告后隔离运行目录。
- 若仅存在留存压力问题，运行 `uv run worldforge runs cleanup --workspace-dir .worldforge --keep 20 --dry-run`，仅在事故或发布引用不再需要时才删除证据。
- 若多个 worker 需要写入，请将持久化迁移至具备锁定、迁移、备份和恢复演练的宿主方存储中。
- 未经[持久化适配器 ADR](./adr/0001-persistence-adapter-boundary.md) 批准，不得向 WorldForge 添加锁文件、SQLite 存储或服务适配器。

### 5b. 捕获运行作用域的提供方日志

当 CLI 任务、批处理宿主、服务请求或机器人案例展示运行需要可附加到议题、发布包或事故说明的提供方事件时使用本节。

对于一次失败的保留运行，在发布前导出议题就绪的包：

```bash
uv run worldforge runs list --status failed --artifact-type json
uv run worldforge runs bundle <run-id> \
  --workspace-dir .worldforge \
  --output .worldforge/issue-bundles/<run-id>
```

成功信号：`worldforge harness --runs` 列出失败运行，附带经脱敏处理的重新运行命令以及 Runs 屏幕中显示的相同 `worldforge runs bundle <run-id>` 恢复命令。bundle 命令写入 `evidence_manifest.json`、`summary.md` 和 `issue.md`，然后打印包含命令、预期信号、观测到的故障、工件列表、`safe_to_attach` 状态和首要排查步骤的简短议题模板。若 `safe_to_attach` 为 `false`，在附加任何内容之前请检查清单中被排除和 `local_only` 的条目。

```python
from pathlib import Path

from worldforge import WorldForge
from worldforge.observability import JsonLoggerSink, RunJsonLogSink, compose_event_handlers

run_id = "20260430T120000Z-provider-event"
log_path = Path(".worldforge") / "runs" / run_id / "provider-events.jsonl"

forge = WorldForge(
    event_handler=compose_event_handlers(
        JsonLoggerSink(extra_fields={"run_id": run_id, "host": "service"}),
        RunJsonLogSink(log_path, run_id=run_id, extra_fields={"host": "service"}),
    )
)
```

成功信号：

- `provider-events.jsonl` 中的每一行均为完整的 JSON 对象。
- 每条记录均包含 `event_type=provider_event`，且与宿主运行清单的 `run_id` 相同。
- `target` 值仅保留路由级上下文；URL 查询字符串和片段已被移除。
- `message`、`metadata` 及 sink 的 `extra_fields` 会对 bearer 令牌、API 密钥、签名、密码、签名 URL 和形如令牌的赋值进行脱敏处理。
- 宿主应用程序将 sink 注入 `WorldForge(event_handler=...)` 或提供方构造函数，而不是在 WorldForge 内部修改全局日志配置。

首要排查查询：

```bash
jq 'select(.phase=="failure") | {provider, operation, status_code, target, message}' \
  .worldforge/runs/<run-id>/provider-events.jsonl
jq 'select(.phase=="retry") | {provider, operation, attempt, max_attempts, status_code, target}' \
  .worldforge/runs/<run-id>/provider-events.jsonl
jq -s 'group_by(.provider,.operation)[] | {provider: .[0].provider, operation: .[0].operation, events: length}' \
  .worldforge/runs/<run-id>/provider-events.jsonl
```

对于可选的实时冒烟测试，将清单与事件日志保存在一起：

```bash
scripts/robotics-showcase \
  --json-output .worldforge/runs/<run-id>/real-run.json \
  --run-manifest .worldforge/runs/<run-id>/run_manifest.json
jq '{run_id, provider_profile, capability, status, event_count, artifact_paths}' \
  .worldforge/runs/<run-id>/run_manifest.json
```

失败时：

| 现象 | 首要检查项 | 可能的责任方 |
| --- | --- | --- |
| 未写入任何文件 | 确认宿主已将 `RunJsonLogSink` 传入活跃的事件处理器 | 宿主应用 |
| 记录中出现不同的 run ID | 对比 sink 构造与运行清单写入器 | 宿主应用 |
| 导出的日志中出现原始凭据 | 从自定义元数据或异常文本中移除原始值，并添加回归测试 | 贡献者 |
| 失败记录中没有状态码 | 检查提供方专属文档；本地依赖故障可能没有 HTTP 状态 | 运维方 |

## 6. 运行评估与基准测试

使用评估进行确定性的行为检查，使用基准测试检验适配器延迟和事件形状。两者均不代表物理保真度声明。

```bash
uv run worldforge eval --suite planning --provider mock --format markdown
uv run worldforge eval --suite physics --provider mock --format json
uv run worldforge eval --suite planning --provider mock \
  --dataset-manifest examples/dataset-manifests/mock-evaluation-fixtures.json \
  --format json
uv run worldforge benchmark --provider mock --iterations 5 --format markdown
uv run worldforge benchmark --provider mock --iterations 5 --format json
uv run worldforge benchmark --provider mock --operation embed --input-file examples/benchmark-inputs.json
uv run worldforge benchmark --provider mock --operation predict --budget-file examples/benchmark-budget.json
```

成功信号：

- 当提供方不支持所需能力时，套件会明确跳过或失败。
- 评估数据集清单以简洁的溯源引用标注；许可证、隐私、安全性、校验和以及由宿主方负责的获取步骤均被记录，但不复制数据集本身。
- 基准测试报告标明提供方、操作、通过/失败状态、延迟、重试次数以及针对 `predict`、`score`、`policy` 和 `embed` 等直接提供方接口的导出工件格式。
- 当成功率、错误次数、重试次数、延迟或吞吐量阈值出现退步时，基准测试预算文件以非零状态退出。
- `--input-file` 夹具可复现预测、嵌入、score 和 policy 运行的基准测试输入。已提交的夹具对 `mock` 的 `predict` 和 `embed` 是检出安全的；其 score 和 policy 字段是面向公告了相应能力的提供方的专属输入。
- 当基准测试输入文件和结果 JSON 被用于发布或论文声明时，由宿主方保存。

若分数发生变化，首先检查提供方能力、测试夹具变化、输入数据和重试事件。在不保留运行工件的情况下，不得围绕单次运行重写声明。

当保留的基准测试基线能够证明预算更新的合理性时，应生成审查工件，而不是直接编辑发布预算：

```bash
uv run python scripts/calibrate_benchmark_budgets.py \
  --report .worldforge/reports/benchmark-<timestamp>-<run-id>.json \
  --current-budget src/worldforge/benchmark_presets/_data/budget-release-evidence.json \
  --output .worldforge/benchmark-calibration/release-evidence-candidate
```

成功信号：`candidate-budgets.json` 通过基准测试预算解析器的加载，且 `budget-calibration.md` 显示源报告摘要、机器类型、旧阈值、候选阈值、观测到的基线及理由。遇到意外候选值时，首要排查步骤是在同一机器类型上重新运行已保留的基准测试命令并对比报告摘要，然后再放宽任何发布门控。

### 6a. 保留评估和基准测试报告

评估和基准测试 CLI 会将已完成的报告保留在活跃的运行工作区下：

```text
.worldforge/reports/eval-<suite>-<timestamp>-<run-id>.json
.worldforge/reports/benchmark-<timestamp>-<run-id>.json
```

JSON 由 `worldforge eval` 和 `worldforge benchmark` 命令使用的相同渲染器写入。每当基准测试或评估结果被引用于 PR、发布说明、论文或幻灯片时，请使用保留的报告路径。

若出现意外数字，首要排查步骤：打开保存的 JSON，确认提供方和操作/套件，然后使用相同的提供方和操作重新运行匹配的 CLI 命令。

### 6b. 记录 Rerun 检查工件

当您需要针对提供方事件、世界状态、规划和基准测试指标的可视化、带时间索引的检查工件时，使用 Rerun：

```bash
uv run --extra rerun worldforge-demo-rerun
uv run --extra rerun rerun .worldforge/rerun/worldforge-rerun-showcase.rrd
```

成功信号：`.rrd` 文件包含提供方事件文本日志、世界快照、规划载荷、3D 对象/目标标记以及模拟基准测试指标。首要排查步骤：通过 `uv run --extra rerun python -c "import rerun; print(rerun.__version__)"` 验证可选 SDK 是否可用。

对于真实的 PushT policy+score 案例展示，包装器默认写入 Rerun 工件：

```bash
scripts/robotics-showcase
uvx --from "rerun-sdk>=0.24,<0.32" rerun /tmp/worldforge-robotics-showcase/real-run.rrd
```

成功信号：记录包含候选目标点、选定的回放轨迹、打分条、延迟条、提供方事件、世界快照和规划载荷。若仅需要 TUI/JSON 工件，使用 `--no-rerun`。在机器人 TUI 中，按 `o` 可直接打开已持久化的 Rerun 录制。

## 7. 处理提供方工件

适用于可能附加到 issue 或发布说明的提供方输出和事件证据。

预检：

```bash
uv run worldforge doctor --capability score
uv run worldforge provider info leworldmodel
uv run worldforge provider health leworldmodel
```

操作规则：

- 创建类请求为单次尝试，除非提供方契约是幂等的。
- 健康检查、轮询和下载可通过 `ProviderRequestPolicy` 进行重试。
- `timeout_seconds` 是单次请求的超时时间；`max_elapsed_seconds` 是宿主对该操作（含重试、退避和轮询间隔）的工作流预算。
- 预算超出会触发 `ProviderBudgetExceededError` 并发出 `phase=="budget_exceeded"` 事件，以便告警能够区分宿主预算耗尽与上游 HTTP 故障。
- 提供方返回的工件引用在可附加证据中不得包含凭据、私有主机或原始签名 URL。
- 提供方返回的工件 URL 被视为不可信输入：默认仅允许 HTTP(S)、无内嵌凭据、无本地/私有/链路本地目标，并以最大字节上限流式传输。
- 签名 URL 和临时工件 URL 不是持久化存储。请在完成后立即将其下载或持久化到宿主方存储中。
- 提供方错误应包含操作和提供方上下文，但不得泄露凭据、bearer 令牌或签名 URL。
- 提供方事件的 `target` 值已为日志进行脱敏处理：用它来识别端点或工件路径，而非恢复完整的签名 URL。

若工件导出失败，检查提供方事件中的 `operation`、`phase`、`status_code`、`attempt` 和经脱敏处理的 `target`，然后在修复提供方输入或宿主配置后重新运行本地工作流。

## 8. 运行可选运行时冒烟测试

优先使用检出安全的演示。仅在具备模型、检查点、CUDA 或机器人技术栈以及任务专属预处理的宿主环境中使用真实运行时冒烟测试。

检出安全：

```bash
uv run pytest
uv run pytest -m "not live"
uv run worldforge-demo-leworldmodel
uv run worldforge-demo-lerobot
```

运行时 pytest 配置文件为选择加入制。用最小的真实标记集标注实时提供方测试，例如 `@pytest.mark.live`、`@pytest.mark.network`、`@pytest.mark.credentialed`、`@pytest.mark.gpu`、`@pytest.mark.robotics` 和 `@pytest.mark.provider_profile("leworldmodel")`。默认的 `uv run pytest` 会在标注的测试尝试访问实时端点、GPU、机器人技术栈、凭据或已下载的检查点之前将其跳过。

已准备宿主的提供方配置文件：

```bash
# Cosmos-Policy: requires COSMOS_POLICY_BASE_URL and a reachable ALOHA /act server.
COSMOS_POLICY_BASE_URL=http://127.0.0.1:8777 \
COSMOS_POLICY_ALLOW_LOCAL_BASE_URL=1 \
  uv run pytest -m "live and network and robotics and provider_profile" \
    --run-live --run-network --run-robotics --provider-profile cosmos-policy
# Expected success: pytest completes the selected live profile without failures.
# First triage: run `uv run worldforge provider health cosmos-policy` to confirm
# configuration only; use the smoke command below to verify `/act` reachability.

COSMOS_POLICY_BASE_URL=http://127.0.0.1:8777 \
COSMOS_POLICY_ALLOW_LOCAL_BASE_URL=1 \
  uv run worldforge-smoke-cosmos-policy \
    --health-only \
    --run-manifest .worldforge/runs/cosmos-policy-health/run_manifest.json
# Expected success: run_manifest.json records capability=policy with status=skipped.
# First triage: run `uv run worldforge provider health cosmos-policy` to confirm
# configuration only, then use the full `/act` smoke below for endpoint behavior.

COSMOS_POLICY_BASE_URL=http://127.0.0.1:8777 \
COSMOS_POLICY_ALLOW_LOCAL_BASE_URL=1 \
  uv run worldforge-smoke-cosmos-policy \
    --policy-info-json /path/to/policy_info.json \
    --translator /path/to/translator.py:translate_actions \
    --allow-translator-code \
    --run-manifest .worldforge/runs/cosmos-policy-live/run_manifest.json
# Expected success: run_manifest.json records capability=policy with status=passed.
# First triage: verify the `/act` server is reachable and recheck the translator path plus
# policy_info.json shape.

# Cosmos-Policy remote GPU checklist:
#
# 1. Use a prepared Linux/NVIDIA host that can run the upstream Cosmos-Policy server.
#    Current ALOHA Predict2 smokes should start from a 48 GB or larger GPU memory class unless
#    the upstream requirements are stricter.
# 2. Keep checkpoints, model approvals, CUDA, Docker, and Hugging Face/NVIDIA tokens on the host.
#    WorldForge should only see the `/act` endpoint and sanitized run evidence.
# 3. Prefer an SSH tunnel to `127.0.0.1:8777`. If the server is exposed directly, restrict
#    inbound TCP 8777 to the operator IP or VPN CIDR and set `COSMOS_POLICY_ALLOWED_HOSTS`.
# 4. Run health-only first. It validates WorldForge configuration only; it does not prove `/act`
#    inference because the targeted upstream server has no non-mutating health endpoint.
# 5. Run the full smoke with prepared ALOHA policy info and a trusted translator. Expected success
#    is `run_manifest.json` with capability=policy, status=passed, and a non-empty action shape
#    such as 50 x 14.
# 6. Preserve only sanitized evidence. Do not commit raw images, tokens, checkpoints, Docker
#    layers, or GPU logs with secrets. Hibernate or terminate the GPU host when finished.

# LeWorldModel: requires LEWORLDMODEL_POLICY or LEWM_POLICY and host-owned runtime deps.
LEWORLDMODEL_POLICY=pusht/lewm \
  uv run pytest -m "live and gpu and provider_profile" \
    --run-live --run-gpu --provider-profile leworldmodel

# GR00T: requires GROOT_POLICY_HOST and a reachable policy server.
GROOT_POLICY_HOST=127.0.0.1 \
  uv run pytest -m "live and network and robotics and provider_profile" \
    --run-live --run-network --run-robotics --provider-profile gr00t
# Expected success: pytest completes the selected live profile without failures.
# First triage: run `uv run worldforge provider health gr00t` to confirm client
# configuration and server reachability.

GROOT_POLICY_HOST=127.0.0.1 \
GROOT_POLICY_PORT=5555 \
  uv run --with msgpack --with pyzmq --with numpy python scripts/smoke_gr00t_policy.py \
    --health-only \
    --run-manifest .worldforge/runs/gr00t-health/run_manifest.json
# Expected success: run_manifest.json records capability=policy with status=skipped.
# First triage: confirm the remote PolicyClient server is reachable before sending
# observation data.

GROOT_POLICY_HOST=127.0.0.1 \
GROOT_POLICY_PORT=5555 \
  uv run --with msgpack --with pyzmq --with numpy python scripts/smoke_gr00t_policy.py \
    --policy-info-json /path/to/policy_info.json \
    --translator /path/to/translator.py:translate_actions \
    --allow-translator-code \
    --run-manifest .worldforge/runs/gr00t-live/run_manifest.json
# Expected success: run_manifest.json records capability=policy with status=passed.
# First triage: recheck the observation shape, translator import path, and remote
# server logs.

# LeRobot: requires LEROBOT_POLICY_PATH or LEROBOT_POLICY and host-owned policy deps.
LEROBOT_POLICY_PATH=lerobot/diffusion_pusht \
  uv run pytest -m "live and robotics and provider_profile" \
    --run-live --run-robotics --provider-profile lerobot
```

当未配合匹配的选择加入标志或提供方环境选择测试时，pytest 会报告跳过原因，并指出缺少的标志或环境变量。在结果被用作发布或议题证据时，请保存已准备宿主运行的标准输出/标准错误、JSON 摘要和提供方事件日志。

真实 LeWorldModel 检查点：

```bash
scripts/lewm-real \
  --checkpoint ~/.stable-wm/pusht/lewm_object.ckpt \
  --device cpu
```

等效的显式 `uv` 命令：

```bash
uv run --python 3.13 \
  --with "stable-worldmodel @ git+https://github.com/galilai-group/stable-worldmodel.git" \
  --with "datasets>=2.21" \
  --with "opencv-python" \
  --with "imageio" \
  lewm-real \
    --checkpoint ~/.stable-wm/pusht/lewm_object.ckpt \
    --device cpu
```

该包装器使用上游 `stable-worldmodel`、`datasets`、OpenCV 和 imageio 运行时要求运行 `uv run --python 3.13`，然后调用打包好的 `lewm-real` 别名。`stable-worldmodel` 是 `lucas-maes/le-wm` 使用的官方 LeWorldModel 加载/评估运行时；`LeWorldModelProvider` 通过 `stable_worldmodel.policy.AutoCostModel` 加载 LeWM 对象检查点。实时冒烟测试打印运行演示内容、可视化流水线、张量形状、延迟指标、提供方事件以及候选动作代价排行。若检查点、可选运行时或提供方健康检查缺失，程序在推理前以非零状态退出。使用 `--json-only` 获取机器可读的结果载荷，或使用 `--json-output lewm-real-summary.json` 在保留可视化输出的同时写入相同的运行数据。

实时冒烟测试使用确定性的合成 PushT 形状张量。它证明检查点可以加载并通过 WorldForge 提供方契约对候选动作进行打分；但不证明任务专属的预处理或机器人执行。

LeRobot 策略与 LeWorldModel 检查点打分回放：

```bash
scripts/robotics-showcase
```

案例展示包装器为该进程安装宿主方负责的可选运行时集，运行打包好的 PushT 桥接器，打开带有策略到打分流水线、运行时条、张量指标、分阶段揭示消息、示意性的动画机器人臂回放、全宽候选排行、提供方事件和桌面回放地图的 Textual 可视化报告，然后将完整的 JSON 摘要写入 `/tmp/worldforge-robotics-showcase/real-run.json`。使用 `--tui-stage-delay <seconds>` 调整揭示节奏，`--no-tui-animation` 禁用睡眠和臂部运动，`--no-tui` 获取纯终端报告，`--json-only` 用于自动化，`--health-only` 用于依赖预检。它请求 `lerobot[transformers-dep]==0.5.1` 以使 Python 3.13 策略导入路径在安装 LeWorldModel 运行时期间保持稳定，并从用户可见输出中过滤常见的 macOS 原生库重复类警告，同时保留运行时设备回退警告的可见性。`--health-only` 路径不会自动构建或下载缺失的 LeWorldModel 检查点；它报告检查点是否存在，并在推理前退出。设置 `WORLDFORGE_SHOW_RUNTIME_WARNINGS=1` 可查看原始的第三方标准错误输出。

已准备宿主的 CI 使用 `.github/workflows/robotics-showcase.yml` 在每次 pull request 更新和向 `main` 的推送时运行此路径。该工作流通过 `--json-only --no-tui --no-rerun` 保持非交互式运行，写入 JSON 摘要和 `run_manifest.json`，并验证真实的 `lerobot.policy` 和 `leworldmodel.score` 成功事件。使用 `actions/cache` 缓存 Hugging Face 策略下载、LeWorldModel 配置/权重资产和构建好的 LeWorldModel 对象检查点。检查点工件不予上传；普通 CI 工件应是运行证据，而不是可复用的检查点存储。

在替换任务观测、打分张量、转换器或候选桥接器时，使用底层运行器：

```bash
scripts/lewm-lerobot-real \
  --policy-path lerobot/diffusion_pusht \
  --policy-type diffusion \
  --checkpoint ~/.stable-wm/pusht/lewm_object.ckpt \
  --device cpu \
  --mode select_action \
  --observation-module /path/to/pusht_obs.py:build_observation \
  --score-info-npz /path/to/lewm_score_tensors.npz \
  --translator worldforge.smoke.lerobot_leworldmodel:translate_pusht_xy_actions \
  --candidate-builder /path/to/pusht_lewm_bridge.py:build_action_candidates \
  --expected-action-dim 10 \
  --expected-horizon 4
```

等效的显式 `uv` 命令：

```bash
uv run --python 3.13 \
  --with "stable-worldmodel @ git+https://github.com/galilai-group/stable-worldmodel.git" \
  --with "datasets>=2.21" \
  --with "huggingface_hub" \
  --with "hydra-core" \
  --with "omegaconf" \
  --with "matplotlib" \
  --with "transformers" \
  --with "lerobot[transformers-dep]==0.5.1" \
  --with "textual>=8.2,<9" \
  --with "pygame" \
  --with "opencv-python" \
  --with "imageio" \
  --with "pymunk" \
  --with "gymnasium" \
  --with "shapely" \
  worldforge-robotics-showcase --tui
```

底层运行器的等效显式 `uv` 命令：

```bash
uv run --python 3.13 \
  --with "stable-worldmodel @ git+https://github.com/galilai-group/stable-worldmodel.git" \
  --with "datasets>=2.21" \
  --with "opencv-python" \
  --with "imageio" \
  --with "lerobot[transformers-dep]==0.5.1" \
  lewm-lerobot-real \
    --policy-path lerobot/diffusion_pusht \
    --policy-type diffusion \
    --checkpoint ~/.stable-wm/pusht/lewm_object.ckpt \
    --device cpu \
    --mode select_action \
    --observation-module /path/to/pusht_obs.py:build_observation \
    --score-info-npz /path/to/lewm_score_tensors.npz \
    --translator worldforge.smoke.lerobot_leworldmodel:translate_pusht_xy_actions \
    --candidate-builder /path/to/pusht_lewm_bridge.py:build_action_candidates
```

此流程演示了机器人构建器的组合：LeRobot 提出策略候选动作，LeWorldModel 对检查点原生的候选张量进行排序，WorldForge 通过 `World.plan(..., planning_mode="policy+score")` 选择并模拟执行代价最低的动作块。打包好的 `scripts/robotics-showcase` 命令负责 PushT 演示桥接器；任何其他任务仍需由宿主方提供观测构建器和候选桥接器。如果 LeRobot 的原始动作维度或时间步长与 LeWorldModel 检查点契约不匹配，请提供任务专属的桥接器，而不是对动作进行填充或投影。

GR00T 和 LeRobot 实时冒烟测试：

```bash
uv run python scripts/smoke_gr00t_policy.py --help
uv run python scripts/smoke_lerobot_policy.py --help
```

成功信号：演示或冒烟测试说明其使用的是注入式确定性运行时、真实检查点推理、远程策略服务器、提供方事件、持久化还是重新加载。不得将注入式演示描述为真实的神经网络推理。

## 9. 准备发布版本或公开分支

在发布软件包、合并提供方工作或推送里程碑之前使用本节。

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
uv run mkdocs build --strict
uv run pytest
uv run --extra harness pytest --cov=src/worldforge --cov-report=term-missing --cov-fail-under=90
bash scripts/test_package.sh
uv build --out-dir dist --clear --no-build-logs
shasum -a 256 dist/worldforge_ai-*.whl dist/worldforge_ai-*.tar.gz
```

软件包契约检查两个分发工件：wheel 必须仅包含运行时软件包文件、`py.typed` 标记、能力协议、可观测能力包装器和控制台脚本；sdist 必须包含重建和审核源包所需的文档、测试、示例、脚本和发布元数据。

在声明发布就绪之前，使用保留的工作空间运行核心性能预算门控：

```bash
uv run python scripts/check_core_performance.py \
  --workspace-dir .worldforge/core-performance \
  --output .worldforge/core-performance/core-performance.json
```

成功信号：`core-performance.json` 的 `passed: true`，且包含世界持久化、基准测试夹具加载、提供方目录诊断、证据包创建和报告渲染的结果行。首要排查步骤：检查失败行的工件路径，并在放宽预算之前重新运行单个已更改的代码路径。该报告是本地回归守卫，不是公开的性能声明。

每当 shell 包装器、可选运行时冒烟命令或已记录的宿主命令发生变化时，运行包装器可移植性检查器：

```bash
uv run python scripts/check_wrapper_portability.py
```

成功信号：所有包装器行均通过，包括 `scripts/robotics-showcase`、LeWorldModel 包装器、GR00T 和 LeRobot 冒烟辅助工具以及 `scripts/test_package.sh`。首要排查步骤：在编辑相关文档之前，先修复失败报告中命名的确切脚本。

每当 Python 或 JSON 示例发生变化时，运行文档片段门控：

```bash
uv run python scripts/check_docs_snippets.py
```

成功信号：标注的 Python 片段在临时工作空间中执行，标注的 JSON 片段在受支持时被解析并进行模式检查，宿主方负责的、需凭据的或示意性的示例使用了明确的跳过标记。首要排查步骤：修复报告中指出的文件、标题和行，或应用正确的跳过标记。

每当基础导入、CLI 启动、非 TUI harness 模块或可选提供方模块发生变化时，运行可选导入边界审计：

```bash
uv run python scripts/check_optional_import_boundaries.py
```

成功信号：静态审计报告在允许的模块之外没有直接的可选运行时导入；导入时审计在不导入 Textual、Rerun、torch、stable-worldmodel、LeRobot、GR00T 或 Cosmos-Policy 包的情况下加载 `worldforge`、`worldforge.cli`、提供方模块和非 TUI harness 模块。首要排查步骤：将命名的导入移至报告所识别的提供方、冒烟测试、`worldforge.rerun` 或 `harness.tui` 边界之后。

然后生成锁定的依赖审计证据：

```bash
uv run python scripts/generate_dependency_audit_evidence.py
```

成功信号：`.worldforge/dependency-audit/dependency-audit.json` 和 `.worldforge/dependency-audit/dependency-audit.md` 存在，状态为 `passed`，且需求摘要说明临时需求文件未被保留。包装器使用 `uv export --frozen --all-groups --no-emit-project --no-hashes` 加上 `uvx --from pip-audit pip-audit ... --format json`；仅对经明确发布审查的例外情况使用 `--ignore-advisory ADVISORY=RATIONALE`。原始详情的键和值会在写入 JSON 或 Markdown 前被清理。遇到 `findings` 时的首要排查步骤：检查 Markdown 建议表，升级或记录依赖决策，然后重新运行。

最后生成发布就绪证据。该命令写入 `.worldforge/release-evidence/release-evidence.md` 和 `.worldforge/release-evidence/release-evidence.json`；当证据运行本身应执行检出安全门控时，添加 `--run-gates`。

```bash
uv run python scripts/generate_evidence_bundle.py \
  --workspace-dir .worldforge \
  --output .worldforge/evidence-bundles/release-candidate
uv run python scripts/generate_release_evidence.py \
  --run-gates \
  --live-smoke-registry docs/src/live-smoke-evidence.json \
  --run-manifest .worldforge/runs/<run-id>/run_manifest.json \
  --artifact .worldforge/dependency-audit/dependency-audit.json \
  --artifact .worldforge/evidence-bundles/release-candidate/evidence_manifest.json \
  --benchmark-artifact .worldforge/reports/benchmark-<timestamp>-<run-id>.json \
  --artifact dist/worldforge_ai-<version>-py3-none-any.whl
```

生成器不需要提供方凭据；没有关联清单的可选实时冒烟测试会被明确列为 `host-owned`，注册表记录缺少运行时和缺少凭据的跳过情况，已通过/失败/跳过的实时运行会链接回其保留的 `run_manifest.json` 文件和工件摘要。门控行明确标记为 `passed`、`failed` 或 `skipped`，并包含首要排查步骤。对于应随包一起传递的发布范围内的注意事项，使用 `--known-limitation`。

在证据工件存在之后，生成本地质量仪表盘：

```bash
uv run python scripts/generate_quality_dashboard.py
```

成功信号：`.worldforge/quality-dashboard/quality-dashboard.json` 和 `.worldforge/quality-dashboard/quality-dashboard.md` 存在，表格区分 `failed`、`warning`、`skipped` 和 `not-run` 行，且第一个失败门控指回底层输出的已清理原始详情。仪表盘读取现有门控输出，而不是运行它们；它会在写入 JSON 或 Markdown 前清理原始详情的键和值。它是本地速览审查索引；发布证据仍是包含哈希值、关联运行清单、可选运行时声明边界和已知限制的发布工件。

然后从更新日志、证据 JSON 和可选的已关闭议题元数据中创建可由维护者编辑的发布说明草稿：

```bash
mkdir -p .worldforge/release-notes
gh issue list --state closed --limit 200 \
  --json number,title,url,labels,closedAt,state \
  > .worldforge/release-notes/closed-issues.json
uv run python scripts/generate_release_notes.py \
  --release-evidence .worldforge/release-evidence/release-evidence.json \
  --issues-json .worldforge/release-notes/closed-issues.json \
  --known-caveat "No prepared-host live smoke was run for <provider>."
```

成功信号：`.worldforge/release-notes/release-notes-draft.md` 包含 `Added`、`Changed`、`Fixed`、`Docs`、`Validation`、`Compatibility Notes`、`Known Caveats` 和 `Host-Owned Optional Runtime Evidence` 章节。草稿是供发布编辑使用的原始材料，不是发布步骤本身：它不会创建 GitHub release 或标签、签署工件或编辑可信发布配置。草稿状态同时检查 `validation_summary` 和每个 `validation_gates` 行；失败的 gate 行会让草稿保持 `needs-validation-review`，直到从通过的 gate 重新生成发布证据。若草稿提示验证证据缺失，请先运行 `uv run python scripts/generate_release_evidence.py --run-gates`。当发布自动化在证据缺失时应失败，使用 `--require-validation-evidence`。草稿会在 Markdown 渲染前清理更新日志文本、已关闭议题元数据、发布证据文本和 `--known-caveat` 值。

成功信号：

- 从干净的检出开始，验证通过。
- 生成的提供方文档无偏移，Pages 站点以严格模式完成构建。
- 发布证据链接了验证预期、可选实时冒烟清单、基准测试工件、生成的证据包、依赖审计证据、分发工件、JSON 摘要、首要排查步骤和已知限制。
- 发布说明草稿链接了更新日志条目、按标签分类的已关闭议题、验证证据、兼容性说明、注意事项以及供维护者审查的宿主方可选运行时证据。
- README、文档、更新日志和 `AGENTS.md` 反映了公开行为。
- 没有可选运行时依赖、检查点、凭据、生成工件或 `.env` 文件被意外提交。

## 10. 排查事故与回归

在用户报告故障时作为第一站使用。对于提供方专属的解析器、重试、凭据、可选运行时、脚手架和不安全工件示例，在附上证据之前请交叉对照[提供方故障模式图册](./provider-failure-gallery.md)。

| 报告的故障 | 首要命令 | 需要捕获的证据 | 常规修复路径 |
| --- | --- | --- | --- |
| 提供方缺失 | `uv run worldforge doctor` | 已注册的提供方、必要的环境变量 | 环境配置或目录注册 |
| 提供方不健康 | `uv run worldforge provider health <name>` | 健康详情、可选依赖版本 | 宿主运行时设置或提供方健康代码 |
| 能力不支持 | `uv run worldforge doctor --capability <capability>` | 提供方档案和工作流调用 | 选择正确的提供方或实现该能力 |
| 持久化加载失败 | 用保存的 JSON 复现 `load_world` | 失败的 JSON、世界 ID、状态目录 | 从备份恢复或修复导入器验证逻辑 |
| 提供方工件导出失败 | 提供方事件和提供方专属文档 | 状态码、尝试次数、经脱敏处理的目标 | 解析器、重试策略、工件处理或宿主凭据 |
| 可选运行时冒烟测试失败 | 冒烟命令和 `--help` 输出 | 宿主操作系统、依赖路径、检查点路径 | 宿主运行时设置；不得向基础软件包添加重型依赖 |
| 覆盖率失败 | `uv run --extra harness pytest --cov=src/worldforge --cov-report=term-missing --cov-fail-under=90` | 缺少覆盖的代码行和已更改的文件 | 添加行为测试，尤其是错误路径 |

不要通过扩宽文档或放宽能力声明来掩盖故障。请修复契约，或明确说明限制所在。

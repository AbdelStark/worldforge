# 运维

WorldForge 是一个 Python 库加 CLI 工具。运维责任由导入它的宿主应用程序承担。本页记录了在服务、作业或提供方评估流水线中使用 WorldForge 的开发者所需了解的运行时假设和最低操作手册。

针对特定任务的操作手册，请参阅 [用户与运维人员操作手册](./playbooks.md)。该页面涵盖干净检出验证、提供方可用性、适配器晋升、持久化恢复、远程工件处理、可选运行时冒烟测试、基准测试和发布门禁。

## 运维模式

| 模式 | 适用场景 | 边界 |
| --- | --- | --- |
| 本地开发 | 示例、单元测试、适配器原型开发、确定性演示 | `mock` 提供方与本地 JSON 世界状态 |
| 提供方评估作业 | 夹具支持的提供方检查、基准测试、可选运行时冒烟测试 | 宿主方持有凭据、检查点、输出和运行工件 |
| 嵌入式服务/库使用 | 应用程序在更大系统中调用 WorldForge API | 宿主方持有请求 ID、遥测导出、持久化、作业重试和告警 |
| 真实机器人或模拟器循环 | 宿主方提供策略观测和动作转换器 | 宿主方持有安全联锁、控制器语义和具身特定的执行逻辑 |

宿主进程的最低启动预检命令：

```bash
uv run worldforge doctor --registered-only
uv run worldforge provider health
uv run worldforge provider info <provider> --format json
```

[参考宿主部署示例](./examples.md#reference-host-deployment-recipes) 涵盖了 stdlib 服务宿主、批量评估宿主和机器人运维宿主，包含环境模板、进程命令、就绪检查、冒烟命令、日志命令、证据导出命令、预期成功信号、初步排查或回滚步骤，以及所有权边界。这些示例区分了检出安全、已准备好宿主、已配置凭据、GPU 依赖和机器人实验室路径，但不将部署、认证、队列管理、持久化存储、控制器集成、告警、正常运行时间或安全认证纳入 WorldForge 的职责范围。

运维故障演练可通过 `worldforge drills` 启动。演练内容涵盖缺失凭据、缺失可选依赖、格式错误的提供方输出、预算超限、损坏的本地世界状态、过期工件以及不安全事件元数据，使用 mock 提供方或夹具进行模拟。演练运行结果写入 `.worldforge/drills/runs/<run-id>/` 下的清单，可使用 `--bundle` 导出问题包，生成的状态保存在所请求的临时或已记录的工作区中。

## 健康状态与就绪状态

宿主应用程序应将存活状态（liveness）与就绪状态（readiness）分开暴露。存活状态回答服务进程能否处理 HTTP 请求；就绪状态回答特定提供方支持的工作流是否应接收流量。

`examples/hosts/service/app.py` 中的 stdlib 参考宿主使用如下模型：

| 状态 | 来源 | 含义 | 典型 HTTP 端点 |
| --- | --- | --- | --- |
| 进程存活 | 服务处理器返回 `{"status": "live"}` | 进程和 Web 栈正在运行 | `GET /healthz` |
| 框架存活 | `WorldForge(...)` 可构造且 `doctor()` 可运行 | 库导入、本地状态路径和提供方注册表可用 | `GET /readyz` |
| 提供方已配置 | 提供方出现在 `forge.providers()` 中 | 必要的环境变量或宿主注入已注册该提供方 | `GET /readyz` |
| 提供方生命周期就绪 | `forge.provider_lifecycle_status(name).ready` 为 true | 提供方拥有的预检为 `no-op` 或 `ready`；跳过和失败的钩子在诊断中仍可见 | `GET /readyz` |
| 提供方健康 | `forge.provider_health(name).healthy` 为 true | 提供方的轻量健康检查通过 | `GET /readyz` |
| 工作流失败 | 提供方已配置且健康检查可能通过，但工作流返回了类型化错误 | 请求输入、上游响应、预算或工件处理失败 | 工作流响应体 |

参考宿主从 `GET /readyz` 返回以下就绪状态之一：

| `/readyz` 状态 | 流量决策 | 解释 |
| --- | --- | --- |
| `ready` | 接受 | 框架存活、所选提供方已注册、生命周期预检就绪或为空操作，且提供方健康检查通过。 |
| `provider_unconfigured` | 排空 | 框架存活，但所选提供方未在此进程中注册。 |
| `provider_unhealthy` | 排空 | 提供方已注册，但其健康检查报告缺少可选运行时、凭据错误、上游不可达或其他提供方拥有的故障详情。 |

在故障处理期间，以同样方式映射 CLI 诊断结果：

| 命令 | 就绪信号 |
| --- | --- |
| `uv run worldforge doctor --registered-only` | 已注册的提供方数量、健康提供方数量及本地配置问题。 |
| `uv run worldforge doctor --capability <capability>` | 是否有已知提供方能满足所请求的接口。 |
| `uv run worldforge provider health <name>` | 提供方专属的已配置/健康详情。 |
| `uv run worldforge provider info <name>` | 脱敏配置摘要，以及配置文件、能力、生命周期和健康状态。 |

生命周期诊断使用类型化的钩子状态：`no-op`、`ready`、`skipped`、`failed` 和 `teardown-failed`。当已准备好宿主方的提供方缺少必要的环境变量或宿主方拥有的可选依赖时，`skipped` 是预期结果；它是一个跳过原因，而非隐式的安装或凭据配置尝试。

WorldForge 报告本地提供方状态和适配器错误，不拥有上游提供方 SLA、部署负载均衡器、告警通道、单次提供方调用之外的重试编排或凭据轮换。

## 配置

配置来源于构造函数参数和 `.env.example` 中记录的环境变量。生成的 [提供方配置索引](./provider-configuration-index.md) 是跨提供方的规范化表格，涵盖必填输入、可选输入、宿主方拥有的包、已准备好宿主方的资产、默认请求超时、首要诊断命令和冒烟命令。

- `COSMOS_POLICY_BASE_URL` 启用可选的 Cosmos-Policy 具身策略适配器。
- `COSMOS_POLICY_API_TOKEN`、`COSMOS_POLICY_TIMEOUT_SECONDS`、`COSMOS_POLICY_EMBODIMENT_TAG`、
  `COSMOS_POLICY_MODEL`、`COSMOS_POLICY_RETURN_ALL_QUERY_RESULTS`、
  `COSMOS_POLICY_ALLOW_LOCAL_BASE_URL` 和 `COSMOS_POLICY_ALLOWED_HOSTS` 是可选的
  Cosmos-Policy `/act` 设置。
- `LEWORLDMODEL_POLICY` 或 `LEWM_POLICY` 启用可选的 LeWorldModel 适配器。
- `LEWORLDMODEL_CACHE_DIR` 覆盖 LeWorldModel 检查点根目录。
- `LEWORLDMODEL_REVISION` 固定案例展示自动构建缺失对象检查点时使用的 Hugging Face LeWM 提交版本。
- `LEWORLDMODEL_ASSET_CACHE_DIR` 覆盖检查点构建器的 Hugging Face 配置/权重缓存目录。
- `LEWORLDMODEL_DEVICE` 为 LeWorldModel 打分选择可选的 torch 设备。
- `GROOT_POLICY_HOST` 启用可选的 GR00T 具身策略适配器。
- `GROOT_POLICY_PORT` 默认为 `5555`。
- `GROOT_POLICY_TIMEOUT_MS` 默认为 `15000`。
- `GROOT_POLICY_API_TOKEN`、`GROOT_POLICY_STRICT` 和 `GROOT_EMBODIMENT_TAG` 是可选的 GR00T PolicyClient 设置。
- `LEROBOT_POLICY_PATH` 或 `LEROBOT_POLICY` 启用可选的 LeRobot 具身策略适配器。
- `LEROBOT_POLICY_TYPE`、`LEROBOT_DEVICE`、`LEROBOT_CACHE_DIR` 和 `LEROBOT_EMBODIMENT_TAG` 是可选的 LeRobot 设置。
- `JEPA_MODEL_NAME` 启用由上游 `facebookresearch/jepa-wms` torch-hub 路径支持的实验性仅打分 JEPA 适配器。
- `JEPA_MODEL_PATH` 仅为旧版脚手架元数据；它不使提供方可运行。
- `GENIE_API_KEY` 仅注册一个能力关闭的脚手架占位。
- `WORLDFORGE_ENABLE_SCAFFOLD_SURROGATES=1` 仅用于本地脚手架适配器测试；它不使 Genie 成为真实的提供方集成。

宿主进程启动时验证配置：

```bash
uv run worldforge doctor --registered-only
uv run worldforge provider health
```

## 运行时资产清单与缓存策略

已准备好宿主方的可选运行时通常依赖检查点文件、策略仓库、对象文件、服务端模型资产和缓存目录。WorldForge 将这些记录为运行时资产清单和安全的运行清单引用；它不下载、保留或上传这些资产。

运行时资产清单使用 `RUNTIME_ASSET_MANIFEST_SCHEMA_VERSION`。完整的本地清单可记录 `path`、`cache_root`、`source`、`revision`、`checksum`、`size_bytes`、`local_only`、`exists` 和 `rebuild_command`。运行清单仅将 `runtime_assets` 包含为可安全附加的引用。对于 `local_only: true` 的资产，引用会省略 `path` 和 `cache_root`，确保宿主本地检查点和缓存位置不会离开本机。

| 运行时系列 | 典型资产 | 缓存策略 | 重建或排查命令 | 证据边界 |
| --- | --- | --- | --- | --- |
| LeWorldModel | `*_object.ckpt`、Hugging Face `config.json` 和 `weights.pt`、`STABLEWM_HOME` 缓存 | 固定 `LEWORLDMODEL_REVISION`；将构建器下载保存在 `LEWORLDMODEL_ASSET_CACHE_DIR` 下；将对象检查点保存在 `STABLEWM_HOME` 或 `LEWORLDMODEL_CACHE_DIR` 下。 | `worldforge-build-leworldmodel-checkpoint --policy pusht/lewm --revision <pinned-sha>` | 运行清单引用检查点清单引用和重建命令，不包含检查点字节或宿主本地缓存根路径。 |
| LeRobot | 策略仓库 ID 或本地检查点目录、Hugging Face 缓存、具身转换器 | 保持 `LEROBOT_CACHE_DIR` 由宿主方持有，并与冒烟测试所用的策略版本对齐。 | `scripts/smoke_lerobot_policy.py --policy-path <repo-or-checkpoint> --device cpu` | 运行清单引用策略检查点引用；原始策略权重和本地策略路径保持仅本地。 |
| GR00T | 远程策略服务器、模型检查点、CUDA/TensorRT 运行时、具身资产 | 在 GPU 宿主上保留服务端缓存；WorldForge 应连接到服务器，而非同步检查点目录。 | `uv run python scripts/smoke_gr00t_policy.py --health-only --run-manifest <path>` | 证据记录服务器可达性和提供方事件，不包含检查点文件、GPU 日志或机器人控制器状态。 |
| Cosmos-Policy | ALOHA `/act` 服务器、Docker/CUDA 运行时、模型检查点、观测构建器、转换器 | 在已准备好的 GPU 宿主上保留 Docker 层、检查点和受限模型令牌。 | `uv run worldforge-smoke-cosmos-policy --health-only --run-manifest <path>` | 证据记录 `/act` 配置和脱敏的运行状态；检查点、原始观测和令牌由宿主方持有。 |
| 未来候选提供方 | 候选特定检查点、夹具、缓存和服务端资产 | 在晋升实时冒烟证据前，先添加运行时资产清单。 | 在提供方页面中记录重建或重新获取命令。 | 可用时附加引用和校验和；不附加仅本地路径或生成的资产。 |

清理也由宿主方负责。对相应运行时使用常规缓存工具，然后重新运行提供方健康命令和带 `--run-manifest` 的冒烟测试以保留最新证据。若缓存路径出现在 JSON 工件中，请视为缺陷：运行清单应包含 `runtime_assets` 引用，而非本地缓存路径。

## 非密钥配置文件

配置文件是可选的 JSON 或 TOML 文件，用于可重复的非密钥 CLI 默认值。其用途包括提供方选择、操作列表、输出格式、状态目录、运行工作区目录、超时/重试预设名称以及安全的相对可选运行时缓存根路径。

```json
{
  "schema_version": 1,
  "name": "local-mock",
  "providers": ["mock"],
  "operations": ["predict"],
  "run_workspace": ".worldforge/profiled-runs",
  "state_dir": ".worldforge/worlds",
  "output_format": "json",
  "timeout_preset": "checkout-safe",
  "retry_preset": "none",
  "runtime_cache_roots": {
    "leworldmodel": ".worldforge/cache/leworldmodel"
  }
}
```

配置文件只能作为显式 CLI 选项使用：

```bash
uv run worldforge benchmark --profile profiles/local-mock.json --iterations 1
uv run worldforge eval --profile profiles/local-mock.toml --suite planning
```

配置文件不得包含凭据、bearer 令牌、API 密钥、已签名 URL、`.env` 路径、绝对宿主本地路径或 `..` 路径遍历。请将密钥保存在环境变量或宿主方拥有的密钥存储中。已保留的评估和基准测试运行清单包含 `config_profile` 来源块，记录配置文件名称、安全的相对来源标签、SHA-256 摘要和已验证的非密钥默认值；配置文件本身不会被复制到运行证据中。

## 持久化

世界状态默认以本地 JSON 格式持久化在 `.worldforge/worlds` 下，或保存在传入 `WorldForge` 的 `state_dir` 路径下。

相同的本地存储也可通过 CLI 用于检出作业和运维人员交接：

```bash
uv run worldforge world create lab --provider mock
uv run worldforge world add-object <world-id> cube --x 0 --y 0.5 --z 0 --object-id cube-1
uv run worldforge world update-object <world-id> cube-1 --x 0.2 --y 0.5 --z 0
uv run worldforge world predict <world-id> --object-id cube-1 --x 0.4 --y 0.5 --z 0
uv run worldforge world list
uv run worldforge world objects <world-id>
uv run worldforge world history <world-id>
uv run worldforge world preflight --state-dir .worldforge/worlds --workspace-dir .worldforge
uv run worldforge world migration-preview <world-id> --state-dir .worldforge/worlds
uv run worldforge world migration-preview world.json --source-path
uv run worldforge world export <world-id> --output world.json
uv run worldforge world import world.json --new-id --name lab-copy
uv run worldforge world fork <world-id> --history-index 0 --name lab-start
uv run worldforge world delete <world-id>
```

该存储适用于本地开发、测试、示例和单写入工作流，不是并发数据库。需要多写入持久化的服务应将导出的世界有效负载存储在自己的数据库中，并使用自己的锁定、备份和保留策略。

持久化在本地 JSON 导入/导出之外明确由宿主方负责。原因在于边界清晰性：宿主应用程序拥有部署拓扑、持久性、锁定语义、备份策略和保留要求。WorldForge 不应暗示本地 JSON 存储无法保证的生产持久性。

ADR 0001，[持久化适配器边界](./adr/0001-persistence-adapter-boundary.md)，记录了未来 `WorldPersistenceAdapter` 边界以及任何持久化存储的验收标准。

支持的持久化不变量：

- 世界 ID 在任何读写操作之前都会被验证为文件安全的本地存储标识符。包含路径分隔符、遍历形式的 ID、空字符串和非字符串 ID 均被拒绝。
- CLI 对象变更和持久化预测会加载世界，应用类型化的 `SceneObject`、`SceneObjectPatch` 或 `Action` 值，追加类型化的历史条目，并通过 `save_world(...)` 写入。
- 位置补丁会将对象的包围盒随姿态一起平移，确保本地场景编辑不会在持久化快照中留下陈旧的空间边界。
- `world predict` 会保存提供方更新后的世界，除非提供了 `--dry-run`。
- `delete_world(...)` 和 `world delete` 在解除本地 JSON 链接之前会验证世界 ID，当所请求的世界已不存在时明确报错。
- 本地 JSON 导入会拒绝：格式错误的场景对象 ID、非对象状态有效负载、无效元数据、无效历史记录、负步骤数、来自未来步骤的历史条目、空历史摘要、格式错误的序列化动作以及无效的历史快照状态。
- `save_world(...)` 在写入前验证序列化的世界，并通过同目录下的临时文件以原子方式替换目标文件。
- `world preflight` 是只读的，不创建、重写、删除或静默强制转换状态。它报告缺失的状态目录、不安全的请求 ID、损坏的世界、无效历史记录、不一致的对象包围盒、陈旧的运行工作区、不安全的运行工件路径和保留压力。
- `world migration-preview` 是只读的，接受持久化的世界 ID 或带 `--source-path` 的持久化/导出 JSON 路径。它报告模式版本、所需变更、无效字段、不安全 ID、包围盒修正和 `can_apply_safely`，不会重写源文件。
- README 和运维文档声明多写入持久化由宿主方负责。
- 任何未来内置的持久化后端必须作为独立适配器引入，并附带自己的锁定、迁移和恢复文档。

本地状态预检是隔离用户数据之前的首要运维命令：

```bash
uv run worldforge world preflight \
  --state-dir .worldforge/worlds \
  --workspace-dir .worldforge \
  --world-id <world-id> \
  --retention-keep 20 \
  --format json > worldforge-state-preflight.json
```

成功信号：`status` 为 `passed`，`safe_to_attach` 为 `true`，`error_count` 为 `0`。警告状态允许存在于本地状态缺失或保留压力的情况；失败状态意味着至少一个世界文件、请求 ID、运行清单或工件引用需要运维人员处理。

报告中的恢复命令会在导出诊断后将无效文件移入 `.worldforge/quarantine/`，不运行 `rm` 或静默删除用户数据。对于保留压力，首要命令是 `uv run worldforge runs cleanup --workspace-dir .worldforge --keep 20 --dry-run`；仅在不再需要保留证据后才移除 `--dry-run`。

迁移预览是应用模式重写之前的状态审查命令：

```bash
uv run worldforge world migration-preview <world-id> \
  --state-dir .worldforge/worlds \
  --format json > worldforge-migration-preview.json
uv run worldforge world migration-preview world.json \
  --source-path \
  --format markdown > worldforge-migration-preview.md
```

成功信号：`safe_to_attach` 和 `read_only` 均为 `true`。`status: passed` 表示无需迁移。`status: migration-needed` 表示预览发现了模式默认值、旧版 `position` 到 `pose.position` 的变更，或可在显式重写之前审查的包围盒修正。`status: blocked` 表示无效字段或不安全 ID 必须在预览工具之外修复；WorldForge 不会静默修复格式错误的本地状态。

## 运行工作区

评估、基准测试和运行时作业可在 `.worldforge/runs/<run-id>/` 下保留检出安全的运行证据。这与本地 JSON 世界持久化是分开的：运行工作区是运维人员的证据包，而非数据库。

```bash
uv run worldforge eval --suite planning --provider mock --run-workspace .worldforge
uv run worldforge benchmark --provider mock --operation predict --run-workspace .worldforge
uv run worldforge runs list
uv run worldforge harness --runs --provider mock --status failed --artifact-type json
uv run worldforge runs bundle <run-id>
uv run worldforge runs cleanup --keep 20
```

每个运行目录包含 `run_manifest.json`、`inputs/`、`results/`、`reports/`、`artifacts/` 和 `logs/`。清单存储可排序的文件安全运行 ID、命令、提供方、操作、状态、输入摘要、结果摘要、事件数量和相对工件路径。

对于公开问题，请先运行 `worldforge runs bundle <run-id> --workspace-dir .worldforge`。该命令写入 `.worldforge/issue-bundles/<run-id>/evidence_manifest.json`、`summary.md` 和 `issue.md`，然后打印问题模板。成功信号：`safe_to_attach` 为 `true`，或清单明确列出了被排除/仅本地文件及原因。导出后的首要排查步骤：打开 `evidence_manifest.json`；若有任何被排除或仅本地的内容，请在附加包之前移除或替换不安全的工件。

对于重复的本地操作，在打开单个工件之前，请先使用 `worldforge runs list`。它无需可选模型运行时即可读取已保留的清单，按提供方、能力、状态、创建日期和安全工件类型进行筛选，并打印脱敏的重新运行、比较和问题包命令。失败、跳过和已取消的行会优先显示 `worldforge runs bundle <run-id>` 恢复命令。

保留策略由宿主方负责。`worldforge runs cleanup --keep <n>` 保留最新的运行 ID 并删除较旧的目录；在删除与故障或发布门禁相关的证据之前，请先使用 `--dry-run`。不要附加包含私有路径、提示词、凭据、已签名 URL 或提供方原生有效负载的原始宿主创建工件。

候选基准测试预算必须从已保留的基准测试报告生成，并在替换发布预算文件之前经过审查：

```bash
uv run python scripts/calibrate_benchmark_budgets.py \
  --report .worldforge/reports/benchmark-<timestamp>-<run-id>.json \
  --current-budget src/worldforge/benchmark_presets/_data/budget-release-evidence.json
```

成功信号是一份 `budget-calibration.md` 审查报告和一个可加载的 `candidate-budgets.json`；该命令不会自动削弱现有发布门禁。阈值宽松仅在具备已保留报告摘要、机器类别上下文、观测到的基准值和审查者说明的情况下方可进行。

## 可观测性

在 `WorldForge(event_handler=...)` 或提供方构建时附加提供方事件处理器。使用 `compose_event_handlers(...)` 将事件分发至：

- `JsonLoggerSink`：用于结构化 JSON 日志。
- `RunJsonLogSink`：用于绑定到某个运行 ID 的换行符分隔 JSON 文件。
- `ProviderMetricsSink`：用于请求、重试、错误和延迟聚合。
- `ProviderMetricsExporterSink`：用于可选的宿主方拥有的计数器和延迟直方图。
- `OpenTelemetryProviderEventSink`：用于可选的宿主方拥有的追踪 span。
- `InMemoryRecorderSink`：用于测试和本地调试。
- `RerunEventSink`：用于提供方事件的可选 Rerun 记录。

`ProviderEvent` 在到达这些接收器之前会对可观测字段进行脱敏处理：HTTP 目标保留协议、主机、端口和路径，但去除用户信息、查询字符串和片段；消息和元数据字段会隐去明显的 bearer 令牌、API 密钥、签名、密码和已签名 URL。宿主应用程序仍应避免在提供方异常消息或自定义元数据中放置原始凭据。

组合式工作流还可以产生 `WorkflowTrace` 工件。追踪是原生 JSON、带模式版本且默认可安全附加的；它记录步骤 ID、操作、提供方/能力槽、输入/输出工件引用、状态、可选时长、脱敏错误摘要和父子关系。规划在 `Plan.metadata["workflow_trace"]` 下存储追踪；评估报告导出 `workflow_trace.json` 和 `workflow_trace.md`；`RerunArtifactLogger.log_workflow_trace(...)` 可将同一追踪添加到可选的 Rerun 记录中。追踪不捕获原始提示词、张量、凭据、控制器遥测或分布式追踪后端状态。

宿主服务可在提供方适配器知晓关联 ID 时将其直接附加到 `ProviderEvent`，或在宿主方于适配器外部拥有关联 ID 时通过 `JsonLoggerSink(extra_fields=...)` 附加。可选事件字段为 `run_id`、`request_id`、`trace_id`、`span_id`、`artifact_id` 和 `input_digest`；它们是字符串，未设置时省略，并在接收器消费前进行脱敏。事件 `phase` 被规范化为小写，以便宿主可以过滤稳定的 `success`、`failure`、`retry` 和 `budget_exceeded` 值。

OpenTelemetry 导出是可选的。导入 `worldforge` 不会导入 OpenTelemetry，基础包也不安装 collector、SDK 或导出器。生产宿主可安装 `opentelemetry-api` 并让 `OpenTelemetryProviderEventSink()` 惰性解析当前追踪器，或注入其已配置好的追踪器：

```python
from worldforge import WorldForge
from worldforge.observability import OpenTelemetryProviderEventSink

forge = WorldForge(
    event_handler=OpenTelemetryProviderEventSink(
        tracer=host_tracer,
        extra_attributes={"service": "batch-eval"},
    )
)
```

每个提供方事件变为一个名为 `worldforge.provider.<provider>.<operation>.<phase>` 的 span。Span 属性限定于：提供方、操作、阶段、尝试次数、最大尝试次数、可选时长、可选关联 ID、HTTP 方法、HTTP 状态码、脱敏目标、状态类别、能力、脱敏消息和脱敏元数据 JSON。宿主不应将原始提示词、世界 ID、含查询字符串的目标 URL 或高基数业务元数据作为追踪属性。

指标导出同样是可选且无依赖的。`ProviderMetricsExporterSink` 接受任何具有 `increment_counter(...)` 和 `observe_histogram(...)` 方法的宿主导出器，生产服务因此可以将提供方事件桥接到 Prometheus、OpenTelemetry Metrics、StatsD 或内部 collector，而无需向基础包添加依赖。

```python
from worldforge import WorldForge
from worldforge.observability import ProviderMetricsExporterSink, compose_event_handlers

host_metrics_exporter = ...  # 由你的服务提供
forge = WorldForge(
    event_handler=compose_event_handlers(
        ProviderMetricsExporterSink(host_metrics_exporter),
    )
)
```

接收器发出以下指标：

| 指标 | 含义 |
| --- | --- |
| `worldforge_provider_events_total` | 每个提供方事件，包括重试。 |
| `worldforge_provider_operations_total` | 逻辑非重试结果，如 `success`、`failure` 和 `budget_exceeded`。 |
| `worldforge_provider_retries_total` | 仅重试事件，与逻辑操作总数分开统计。 |
| `worldforge_provider_errors_total` | 失败或超出预算的操作结果。 |
| `worldforge_provider_latency_ms` | 提供方包含时长时的事件 `duration_ms` 值。 |

标签限定于 `provider`、`operation`、`phase`、`status_class` 和 `capability`。`capability` 仅在匹配已知 WorldForge 能力时导出，否则变为 `unknown`。不要将原始目标 URL、提示词、元数据键、世界 ID、工件 ID、请求 ID 或用户/业务标识符作为指标标签，这些值基数高，且部分可能携带密钥。良好的首要告警是按提供方/操作划分的重试率或错误率阈值，以及按提供方/操作分组的 `worldforge_provider_latency_ms` 延迟百分位告警。

JSON 日志记录示例：

```json
{
  "artifact_id": "artifact-local-id",
  "attempt": 1,
  "duration_ms": 812.4,
  "event_type": "provider_event",
  "input_digest": "sha256:9fd7...",
  "max_attempts": 3,
  "message": "",
  "metadata": {"status": "submitted"},
  "method": "POST",
  "operation": "task create",
  "phase": "success",
  "provider": "cosmos-policy",
  "request_id": "host-request-id",
  "run_id": "20260430T120000Z-batch-eval",
  "span_id": "span-456",
  "status_code": 200,
  "target": "https://policy.example.test/act",
  "trace_id": "trace-123"
}
```

对于批量作业、运行时作业和发布证据，请附加宿主进程拥有的文件接收器：

```python
from pathlib import Path

from worldforge import WorldForge
from worldforge.observability import JsonLoggerSink, RunJsonLogSink, compose_event_handlers

run_id = "20260430T120000Z-batch-eval"
forge = WorldForge(
    event_handler=compose_event_handlers(
        JsonLoggerSink(extra_fields={"run_id": run_id}),
        RunJsonLogSink(
            Path(".worldforge") / "runs" / run_id / "provider-events.jsonl",
            run_id=run_id,
            extra_fields={"host": "batch-eval"},
        ),
    )
)
```

文件接收器会创建父目录，并在每个提供方事件后追加一个 JSON 对象。其配置的 `run_id` 优先于额外字段或适配器事件提供的任何 `run_id`，确保文件中的每一行都与相同的宿主运行清单关联。运维人员包可以关联 `manifest.json`、`provider-events.jsonl`、基准测试报告和已保留的工件，而无需依赖时间戳。额外字段会被验证为 JSON，并使用与提供方事件消息和元数据相同的可观测密钥规则进行脱敏。

可选的实时冒烟命令还可以写入脱敏的 `run_manifest.json`：

```bash
scripts/robotics-showcase \
  --json-output /tmp/worldforge-robotics-showcase/real-run.json \
  --run-manifest /tmp/worldforge-robotics-showcase/run_manifest.json
```

清单记录命令 argv、包版本、提供方配置文件、能力、无值的环境变量存在性、可用时的运行时清单 ID、输入夹具摘要、事件数量、结果摘要和工件路径。验证会拒绝原始密钥类字段和未脱敏的已签名 URL；工件 URL 存储时不含查询字符串或片段。

如需本地运行检查，请安装可选的 `rerun` 扩展包，并将事件和工件流式传输到 Rerun 记录中：

```bash
uv run --extra rerun worldforge-demo-rerun
```

预期成功信号：`.worldforge/rerun/worldforge-rerun-showcase.rrd` 存在，命令打印字节数，且记录在 Rerun 查看器中打开。首要排查步骤：运行 `uv run --extra rerun python -c "import rerun; print(rerun.__version__)"`。

## 机器人运维审查

`examples/hosts/robotics-operator/app.py` 中的检出宿主是针对策略加打分机器人运行的离线审查循环：

```bash
uv run python examples/hosts/robotics-operator/app.py review --sample-translator
```

默认情况下，它不与机器人控制器通信。它需要宿主进程中提供显式的动作转换器，记录检查清单和演习审批状态，并在 `.worldforge/robotics-operator/runs/<run-id>/` 下保留所选动作块、打分说明、提供方事件和回放工件。

WorldForge 仅证明其类型化的提供方、事件、回放和清单工件满足框架契约。实验室宿主仍负责具身转换器、控制器钩子、工作区安全、运维人员审批策略、紧急停止、硬件行为、部署就绪和安全认证。

## 故障模式

- 无效的调用方输入会抛出 `WorldForgeError`。
- 格式错误的持久化或提供方提供的状态会抛出 `WorldStateError`。
- 提供方运行时、传输层、凭据和上游故障会抛出 `ProviderError`。
- 缺少远程凭据会使提供方处于未注册状态，除非通过 `doctor()` 进行检查。
- 远程创建类请求默认单次尝试；健康检查、轮询和下载按照 `ProviderRequestPolicy` 进行重试。
- 提供方请求预算按操作设置。`timeout_seconds` 限制单次 HTTP 尝试；可选的 `max_elapsed_seconds` 限制包含重试、退避和任务轮询在内的整个操作时长。超出预算会抛出 `ProviderBudgetExceededError`，并在附加了事件处理器时发出 `budget_exceeded` 提供方事件。
- 熔断器由宿主方持有。服务可以统计 `ProviderMetricsSink` 中近期的 `failure`、`retry` 和 `budget_exceeded` 事件，停止向退化的提供方路由新工作，并在不让 WorldForge 拥有告警通道或上游 SLA 的情况下继续处理缓存/只读路径。
- LeWorldModel 打分在以下情况明确失败：可选依赖不可用、检查点无法加载、缺少必要的 `pixels`/`goal`/`action` 字段、动作候选形状不为 `(batch=1, samples, horizon, action_dim)`、返回的打分数量与候选样本数不匹配，或返回的打分不是有限值。
- GR00T 策略选择在以下情况明确失败：PolicyClient 依赖不可用、策略服务器不可达、观测数据格式错误、原始动作不兼容 JSON，或未提供宿主方拥有的动作转换器。
- LeRobot 策略选择在以下情况明确失败：LeRobot 依赖不可用、策略加载失败、观测数据格式错误、原始动作不兼容 JSON，或未提供宿主方拥有的动作转换器。

## 恢复

- 对于本地状态损坏，请从宿主应用程序对导出世界 JSON 的备份中恢复。
- 对于缺少凭据，请修复环境并重启宿主进程，以便重新运行提供方自动注册。
- 对于瞬时远程故障，请检查发出的 `ProviderEvent` 记录中的 `operation`、`phase`、`status_code`、`attempt` 和脱敏的 `target`。
- 对于 LeWorldModel 故障，请运行 `worldforge provider health leworldmodel`，验证 `stable-worldmodel`、`torch`、`opencv-python` 和 `imageio` 是否已安装在宿主环境中，然后确认配置的策略存在于 `$STABLEWM_HOME` 或 `LEWORLDMODEL_CACHE_DIR` 下。
- 如需冒烟测试真实的 LeWorldModel 检查点，请运行
  `scripts/lewm-real --checkpoint ~/.stable-wm/pusht/lewm_object.ckpt --device cpu`。这需要宿主方拥有的上游依赖和已提取的对象检查点。
- 如果你拥有 Hugging Face LeWM `config.json` 和 `weights.pt` 资产而非已提取的 `*_object.ckpt` 归档，请先使用以下命令构建对象检查点：

  ```bash
  uv run --python 3.13 \
    --with "stable-worldmodel @ git+https://github.com/galilai-group/stable-worldmodel.git" \
    --with "datasets>=2.21" \
    --with huggingface_hub \
    --with hydra-core \
    --with omegaconf \
    --with transformers \
    --with matplotlib \
    --with "opencv-python" \
    --with "imageio" \
    worldforge-build-leworldmodel-checkpoint \
      --stablewm-home ~/.stable-wm \
      --policy pusht/lewm \
      --revision 22b330c28c27ead4bfd1888615af1340e3fe9052
  ```

  `hydra-core`、`omegaconf` 和 `transformers` 是实例化官方 LeWM PushT 配置所必需的。在允许 Hydra 实例化任何内容之前，构建器会根据已知的官方 PushT LeWM 目标允许列表验证下载的配置，拒绝任何插值的 `_target_` 值，并拒绝允许列表之外的嵌套目标。默认修订版本是固定提交 `22b330c28c27ead4bfd1888615af1340e3fe9052`；传入 `--revision <40位提交SHA>` 或设置 `LEWORLDMODEL_REVISION` 以使用其他经过审计的不可变 Hugging Face 提交。构建器默认使用 `torch.load(..., weights_only=True)` 加载下载的 `weights.pt`；`--allow-unsafe-pickle` 仅适用于可信的旧版权重和较旧的 torch 环境。构建器默认将资产下载到 `~/.cache/worldforge/leworldmodel`，或在设置了 `LEWORLDMODEL_ASSET_CACHE_DIR` / `--asset-cache-dir` 时下载到指定位置，并将对象检查点写入 `$STABLEWM_HOME`。
- 如需在没有可选依赖的情况下演示 LeWorldModel 规划流程，请运行
  `uv run worldforge-demo-leworldmodel`。它使用真实的 `LeWorldModelProvider` 接口，注入确定性代价运行时，并演练打分规划、执行、持久化和重新加载。这不是真实的上游检查点推理运行；如需该路径，请使用 `lewm-real` 或 `worldforge-smoke-leworldmodel`。演示应报告 `uses_leworldmodel_provider: true`、`uses_worldforge_score_planning: true` 和 `uses_real_upstream_checkpoint: false`。
- 如需在没有可选依赖的情况下演示 LeRobot 策略加打分规划，请运行
  `uv run worldforge-demo-lerobot`。它使用真实的 `LeRobotPolicyProvider` 接口，注入确定性策略运行时，并演练策略选择、打分排序、执行、持久化和重新加载。这不是真实的 LeRobot 检查点推理运行。
- 如需运行真实的 LeRobot 加 LeWorldModel 案例展示，请使用 `scripts/robotics-showcase`。它会启动打包的 PushT 策略加打分桥，默认打开 Textual 报告，并写入 `/tmp/worldforge-robotics-showcase/real-run.rrd`（除非传入 `--no-rerun`）。完整演练详见 [机器人回放案例展示](./robotics-showcase.md)。
- 如需在 CI 中运行同一路径，请使用 `.github/workflows/robotics-showcase.yml`。它在每次拉取请求更新和向 `main` 的推送时运行 `scripts/robotics-showcase --json-only --no-tui --no-rerun`，验证真实的策略/打分事件，使用 `actions/cache` 缓存 Hugging Face 资产和 LeWorldModel 对象检查点，并将 JSON 摘要和 `run_manifest.json` 作为证据上传。检查点工件不上传。
- 如需冒烟测试真实的 GR00T 策略服务器，请在已准备好的 NVIDIA/Linux 宿主上安装或检出 NVIDIA Isaac-GR00T，准备宿主特定的观测夹具和动作转换器，然后运行
  `GROOT_POLICY_HOST=127.0.0.1 GROOT_POLICY_PORT=5555 uv run --with msgpack --with pyzmq --with numpy python scripts/smoke_gr00t_policy.py --health-only --run-manifest .worldforge/runs/gr00t-health/run_manifest.json`。
  `--health-only` 的预期成功信号：进程以 0 退出，运行清单记录 `capability=policy` 且 `status=skipped`。
  如需完整的策略请求，请运行
  `GROOT_POLICY_HOST=127.0.0.1 GROOT_POLICY_PORT=5555 uv run --with msgpack --with pyzmq --with numpy python scripts/smoke_gr00t_policy.py --policy-info-json /path/to/policy_info.json --translator /path/to/translator.py:translate_actions --allow-translator-code --run-manifest .worldforge/runs/gr00t-live/run_manifest.json`。
  预期成功信号：进程以 0 退出，运行清单记录 `capability=policy` 且 `status=passed`。首要排查步骤：运行 `uv run worldforge provider health gr00t` 确认客户端可以连接到远程 PolicyClient 服务器，然后重新检查观测夹具和转换器路径。
- 启动上游 GR00T 服务器需要兼容其 CUDA 和 TensorRT 依赖的 NVIDIA/Linux 运行时。在不支持的宿主上，将 WorldForge 指向已在运行的远程 GR00T 策略服务器。优先使用 SSH 隧道，如 `ssh -N -L 5555:127.0.0.1:5555 ubuntu@<gpu-host>`，或将服务器端口限制为运维人员 IP 或 VPN。冒烟测试完成后，请休眠或终止远程 GPU 实例。
- 如需冒烟测试真实的 Cosmos-Policy ALOHA 服务器，请在兼容的 Linux/NVIDIA 宿主上运行上游服务器，准备 ALOHA 策略信息和动作转换器，然后运行
  `COSMOS_POLICY_BASE_URL=http://127.0.0.1:8777 COSMOS_POLICY_ALLOW_LOCAL_BASE_URL=1 uv run worldforge-smoke-cosmos-policy --policy-info-json /path/to/policy_info.json --translator /path/to/translator.py:translate_actions --allow-translator-code --run-manifest .worldforge/runs/cosmos-policy-live/run_manifest.json`。
  如需仅配置路径，请运行
  `COSMOS_POLICY_BASE_URL=http://127.0.0.1:8777 COSMOS_POLICY_ALLOW_LOCAL_BASE_URL=1 uv run worldforge-smoke-cosmos-policy --health-only --run-manifest .worldforge/runs/cosmos-policy-health/run_manifest.json`。
  `--health-only` 仅验证 WorldForge 配置，因为目标上游服务器没有非变更性健康端点，且不调用 `/act`。
  `--health-only` 的预期成功信号：进程以 0 退出，运行清单记录 `capability=policy` 且 `status=skipped`。
  预期成功信号：进程以 0 退出，运行清单记录 `capability=policy` 且 `status=passed`。首要排查步骤：运行 `uv run worldforge provider health cosmos-policy` 确认配置，然后运行冒烟命令验证宿主可以连接到 `/act`。
  对于租用或实验室 GPU，请遵循 [Cosmos-Policy 远程 GPU 操作手册](./providers/cosmos-policy.md#remote-gpu-runbook)：在上游模型需要时使用已准备好的 48 GB 或更大的 Linux/NVIDIA 宿主，优先使用 SSH 隧道连接到端口 `8777`，将直接防火墙暴露限制为运维人员 IP 或 VPN CIDR，仅保留脱敏的清单/回放工件，并在完成后休眠或终止 GPU 宿主。
- pytest 实时运行时覆盖率是可选启用的。使用 `uv run pytest` 或 `uv run pytest -m "not live"` 进行确定性检出验证。已准备好的宿主可以使用 `live`、`network`、`credentialed`、`gpu`、`robotics` 和 `provider_profile` 等标记以及匹配的 `--run-*` 标志和 `--provider-profile <name>` 一次选择一个实时提供方配置文件。提供方专属命令详见 [运行可选运行时冒烟测试](./playbooks.md#8-run-optional-runtime-smokes)。

## 发布检查清单

在发布之前：

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

工件完整性契约记录在 [工件完整性](./artifact-integrity.md) 中，涵盖包哈希值、当前包/证据检查、不安全工件排除，以及目前尚未声明的未来 SBOM、来源追溯和证明工作。

然后生成锁定的依赖审计证据：

```bash
uv run python scripts/generate_dependency_audit_evidence.py
```

该包装器运行已记录的 `uv export --frozen --all-groups --no-emit-project --no-hashes` 加 `uvx --from pip-audit pip-audit ... --format json` 流程，使用审计后删除的临时需求文件。它写入 `.worldforge/dependency-audit/dependency-audit.json` 和 `.worldforge/dependency-audit/dependency-audit.md`，记录工具版本、依赖集摘要、漏洞概要、显式的 `--ignore-advisory ADVISORY=RATIONALE` 行、命令输出尾部和首要排查步骤。原始详情的键和值会在写入 JSON 或 Markdown 前被清理；被隐去后发生冲突的键会保留确定性后缀。成功信号：状态为 `passed`；发现、工具不可用和失败状态仍会留下可安全附加的证据。发现时的首要排查步骤：检查 Markdown 安全公告行，升级或记录依赖决策，然后重新运行审计。

本地门禁和可选冒烟测试完成后，生成发布就绪证据。该命令默认同时写入 Markdown 和 JSON 摘要；使用 `--run-gates` 时，证据运行本身会执行检出安全门禁，而非将其记录为跳过。

```bash
uv run python scripts/generate_release_evidence.py \
  --run-gates \
  --live-smoke-registry docs/src/live-smoke-evidence.json \
  --run-manifest .worldforge/runs/<run-id>/run_manifest.json \
  --artifact .worldforge/dependency-audit/dependency-audit.json \
  --benchmark-artifact .worldforge/reports/benchmark-<timestamp>-<run-id>.json \
  --artifact dist/worldforge_ai-<version>-py3-none-any.whl
```

报告默认输出至 `.worldforge/release-evidence/release-evidence.md`，JSON 摘要默认输出至 `.worldforge/release-evidence/release-evidence.json`。门禁行明确显示 `passed`、`failed` 或 `skipped`；每行包含命令、可用时的退出码和首要排查步骤。可选的实时提供方证据为 `host-owned`，除非关联了已准备好宿主方的 `run_manifest.json`。当发布说明或提供方晋升声明实时提供方覆盖时，请附加 Markdown 报告、JSON 摘要和关联的工件。

发布评审之前，请使用检出安全演练预演证据路径：

```bash
uv run python scripts/release_readiness_drill.py \
  --workspace-dir .worldforge/release-readiness-drill
```

演练写入 `.worldforge/release-readiness-drill/release-readiness-drill.json` 以及 Markdown 加清洁通过和受控失败的发布证据夹具。它解释第一个失败的门禁和首要排查命令，记录宿主方拥有的可选运行时跳过，且不发布、打标签、签名、创建 GitHub 发布或批准真实发布。使用它验证运维人员的工作流理解；使用 `scripts/generate_release_evidence.py --run-gates` 获取当前发布审批证据。

当需要分支的一站式质量概览时，生成本地质量看板：

```bash
uv run python scripts/generate_quality_dashboard.py
```

看板默认输出至 `.worldforge/quality-dashboard/quality-dashboard.json` 和 `.worldforge/quality-dashboard/quality-dashboard.md`。它读取已有的发布证据、依赖审计证据和核心性能 JSON；它不执行门禁。状态行使用 `passed`、`failed`、`warning`、`skipped` 和 `not-run`，保留已清理的原始失败输出尾部，列出已跳过的宿主方拥有的提供方检查，并指出第一个失败的门禁。原始详情的键和值会在写入 JSON 或 Markdown 前被清理；被隐去后发生冲突的键会保留确定性后缀，而不是丢弃条目。将其作为本地质量索引使用。发布证据仍是发布声明、工件哈希值、关联的 `run_manifest.json` 文件和已知限制的工件。

证据存在后，起草供维护者编辑的发布说明：

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

发布说明命令写入 `.worldforge/release-notes/release-notes-draft.md`。这仅是草稿工件：维护者在发布前必须编辑它，该命令不创建标签、GitHub 发布、签名或可信发布工件。成功信号：草稿包含新增、变更、修复、文档、验证、兼容性、注意事项和宿主方可选运行时等章节。草稿状态同时读取 `validation_summary` 和逐行的 `validation_gates`；任何失败的 gate 行都会让草稿保持 `needs-validation-review`，即使过期摘要声称失败数为零。验证缺失时的首要排查步骤：运行 `uv run python scripts/generate_release_evidence.py --run-gates` 并重新生成草稿。在发布脚本中使用 `--require-validation-evidence`，以便在证据 JSON 缺失或无效时使命令失败。更新日志条目、已关闭议题元数据、发布证据文本和 `--known-caveat` 值会在 Markdown 渲染前被清理，避免 token 赋值、Bearer 头、签名 URL 和宿主本地路径进入发布说明草稿。

`uv run python scripts/check_core_performance.py` 为世界持久化、基准测试夹具加载、提供方诊断、证据包创建和报告渲染写入检出安全的 JSON 报告。成功信号：`passed` 为 true，且当提供了 `--workspace-dir <path>` 时，每个结果行都有已保留的工件路径。首要排查步骤：在更改预算之前，检查失败行的测量路径并修复回归。这些预算是本地回归防护，不是跨机器或可选运行时的性能声明。

`uv run python scripts/check_wrapper_portability.py` 在不安装宿主方拥有的运行时的情况下检查 Shell 包装器和可选运行时冒烟命令。成功信号：`scripts/robotics-showcase`、`scripts/lewm-real`、`scripts/lewm-lerobot-real`、GR00T 和 LeRobot 冒烟辅助工具以及 `scripts/test_package.sh` 的报告均通过。首要排查步骤：修复命名脚本的 shebang、可执行位、已记录命令或 Python 3.13 uv 调用。

`uv run python scripts/check_optional_import_boundaries.py` 在不安装宿主方拥有的运行时的情况下检查可选运行时导入边界。成功信号：基础包导入、CLI 启动、`worldforge.rerun` 和非 TUI 运行时模块不加载 Textual、Rerun、torch、stable-worldmodel、LeRobot、GR00T 或 Cosmos-Policy 包，且静态源码检查仅在允许的提供方、冒烟测试、Rerun 或 `harness.tui` 模块中发现可选导入。首要排查步骤：将命名的导入移至报告中允许的惰性边界之后。

`uv run python scripts/check_docs_snippets.py` 执行公开文档中选定的 Python 片段，并解析选定的 JSON 片段。成功信号：报告通过且无片段失败，任何宿主方拥有的、需要凭据的或演示性片段均已显式跳过。首要排查步骤：在更改周边文档之前，修复报告中指出的文件、标题和行。

当发布或问题排查需要底层评估和基准测试工件时，请先生成独立的证据包：

```bash
uv run worldforge eval --suite planning --provider mock --run-workspace .worldforge
uv run worldforge benchmark --preset mock-smoke --run-workspace .worldforge
uv run python scripts/generate_evidence_bundle.py \
  --workspace-dir .worldforge \
  --output .worldforge/evidence-bundles/mock-planning
uv run python scripts/generate_release_evidence.py \
  --artifact .worldforge/evidence-bundles/mock-planning/evidence_manifest.json
```

成功信号：包写入 `evidence_manifest.json` 和 `summary.md`，每个包含的文件都有 `sha256:<hex>` 摘要，被排除的文件携带原因，如不支持的后缀、宿主本地路径或密钥类内容。失败时的首要排查步骤：检查运行的 `run_manifest.json`，在重新生成包之前移除或标记为仅本地的不安全工件。

标签触发的发布工作流在构建发行版或发布工件之前会重复完整的质量门禁。

同时更新 `CHANGELOG.md`、README 以及任何公开行为变更对应的提供方文档。

## 提供方加固标准

- 远程提供方非正常路径测试覆盖传输重试、格式错误的 JSON、错误动作载荷、缺少可选运行时、脱敏和提供方限制。
- 持久化仍记录为宿主方持有，除非专用的持久化适配器已完成设计。
- API 文档列出公开异常系列和提供方工作流故障模式。
- 剩余工作在提供方能力声明为完成之前，以可量化的退出标准进行追踪。

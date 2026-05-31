# 提供方配置索引

本索引由仓库内的提供方目录、提供方配置文件、请求策略和运行时清单生成。它是面向操作人员的契约，说明哪些输入可启用每个提供方、哪些可选包由宿主方持有、宿主方必须保留哪些资产，以及配置失败时应首先运行哪条命令。

证据级别：

- `scaffold`：仅为名称保留；不声明任何真实的运行时能力。
- `fixture-tested`：确定性的仓库内行为已由本地测试和夹具覆盖。
- `prepared-host`：WorldForge 附带运行时清单和冒烟命令，但宿主方需提供凭据、端点、可选包、检查点或机器人专用资产。
- `live-smoke`：已准备好的宿主已在[实况冒烟证据注册表](./live-smoke-evidence.md)中为该提供方和能力保留了净化后的运行清单。

WorldForge 不在本索引中存储密钥、宿主本地端点值、检查点存档或机器人控制器凭据。

<!-- provider-config-index:start -->
| 提供方 | 证据级别 | 必需输入 | 可选输入 | 可选包 | 已准备好宿主的资产 | 默认超时 | 首步诊断 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| [`mock`](providers/README.md) | `fixture-tested` | 无 | 无 | 无 | 无 | 无 | `uv run worldforge provider health mock` |
| [`cosmos-policy`](providers/cosmos-policy.md) | `prepared-host` | `COSMOS_POLICY_BASE_URL` | `COSMOS_POLICY_API_TOKEN`、`COSMOS_POLICY_TIMEOUT_SECONDS`、`COSMOS_POLICY_EMBODIMENT_TAG`、`COSMOS_POLICY_MODEL`、`COSMOS_POLICY_RETURN_ALL_QUERY_RESULTS`、`COSMOS_POLICY_ALLOW_LOCAL_BASE_URL`、`COSMOS_POLICY_ALLOWED_HOSTS` | nvidia/cosmos-policy 服务器 | Cosmos-Policy Docker/运行时环境<br>ALOHA 策略服务器<br>模型检查点<br>观测构建器<br>动作转换器 | 健康检查 10s x3；请求 600s x1；轮询 30s x3；下载 600s x3 | `uv run worldforge provider health cosmos-policy` |
| [`leworldmodel`](providers/leworldmodel.md) | `prepared-host` | `LEWORLDMODEL_POLICY` 或 `LEWM_POLICY` | `STABLEWM_HOME`、`LEWORLDMODEL_CACHE_DIR`、`LEWORLDMODEL_DEVICE` | torch<br>stable_worldmodel | LeWorldModel 检查点<br>检查点缓存<br>任务形状张量 | 无 | `uv run worldforge provider health leworldmodel` |
| [`gr00t`](providers/gr00t.md) | `prepared-host` | `GROOT_POLICY_HOST` | `GROOT_POLICY_PORT`、`GROOT_POLICY_TIMEOUT_MS`、`GROOT_POLICY_API_TOKEN`、`GROOT_POLICY_STRICT`、`GROOT_EMBODIMENT_TAG` | gr00t.policy.server_client<br>msgpack<br>numpy<br>pyzmq | GR00T 策略服务器<br>具身资产<br>动作转换器 | 无 | `uv run worldforge provider health gr00t` |
| [`lerobot`](providers/lerobot.md) | `prepared-host` | `LEROBOT_POLICY_PATH` 或 `LEROBOT_POLICY` | `LEROBOT_POLICY_TYPE`、`LEROBOT_DEVICE`、`LEROBOT_CACHE_DIR`、`LEROBOT_EMBODIMENT_TAG` | lerobot | 策略检查点<br>策略缓存<br>具身动作转换器 | 无 | `uv run worldforge provider health lerobot` |
| [`jepa`](providers/jepa.md) | `prepared-host` | `JEPA_MODEL_NAME` | `JEPA_DEVICE`、`JEPA_MODEL_PATH` | torch | JEPA-WMS 检查点<br>torch-hub 缓存<br>任务形状观测、目标和动作张量 | 无 | `uv run worldforge provider health jepa` |
| [`genie`](providers/genie.md) | `scaffold` | `GENIE_API_KEY` | 无 | 无 | 无 | 无 | `uv run worldforge provider health genie` |

## 已准备好宿主的冒烟命令

| 提供方 | 冒烟命令 | 凭据要求 | 运行时归属权 |
| --- | --- | --- | --- |
| `mock` | `not smoke-testable from WorldForge` | 无 | 仓库内确定性本地提供方 |
| `cosmos-policy` | `COSMOS_POLICY_BASE_URL=http://127.0.0.1:8777 COSMOS_POLICY_ALLOW_LOCAL_BASE_URL=1 uv run worldforge-smoke-cosmos-policy --policy-info-json /path/to/policy_info.json --translator /path/to/translator.py:translate_actions --allow-translator-code` | `COSMOS_POLICY_API_TOKEN` | WorldForge 验证 `/act` 请求/响应和规划组合；宿主方持有 Cosmos-Policy 可达性/CUDA/运行时、ALOHA 观测构建和将原始 14D 行转换为可执行 `Action` 对象的翻译工作 |
| `leworldmodel` | `scripts/lewm-real --checkpoint ~/.stable-wm/pusht/lewm_object.ckpt --device cpu` | 无 | 宿主方安装官方 LeWM 加载路径（`stable_worldmodel.policy.AutoCostModel`）、torch 和兼容的检查点 |
| `gr00t` | `GROOT_POLICY_HOST=127.0.0.1 GROOT_POLICY_PORT=5555 uv run --with msgpack --with pyzmq --with numpy python scripts/smoke_gr00t_policy.py --health-only --run-manifest .worldforge/runs/gr00t-health/run_manifest.json` | `GROOT_POLICY_API_TOKEN` | 宿主方运行或可访问 Isaac GR00T 策略服务器 |
| `lerobot` | `scripts/smoke_lerobot_policy.py --policy-path <repo-or-checkpoint> --device cpu` | 无 | 宿主方安装 LeRobot 和兼容的策略检查点 |
| `jepa` | `uv run --with torch worldforge-smoke-jepa-wms --model-name jepa_wm_pusht --device cpu` | 无 | 宿主方提供 torch、facebookresearch/jepa-wms 运行时依赖和任务预处理 |
| `genie` | `not smoke-testable from WorldForge` | `GENIE_API_KEY` | 能力失败关闭保留条目；Project Genie 没有受支持的自动化 API 契约 |
<!-- provider-config-index:end -->

生成块由以下命令检查：

```bash
uv run python scripts/generate_provider_docs.py --check
```

当提供方的配置文件、环境变量、运行时清单、冒烟命令或请求策略发生变更时，请重新生成本页面并在发布前检查差异。

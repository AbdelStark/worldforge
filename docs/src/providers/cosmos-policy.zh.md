# Cosmos-Policy 提供方

运行时能力：当提供方构造时传入宿主方 `action_translator` 时，具备 `policy` 能力

成熟度：`beta`

分类：具身策略 / 机器人动作模型

`cosmos-policy` 是一个对接宿主方持有的 NVIDIA Cosmos-Policy ALOHA 服务器的 HTTP 适配器。它将 ALOHA 观测数据和任务描述发送至 `/act` 端点，校验返回的动作序列块，保留原始策略输出，并要求宿主方提供转换器后才能返回可执行的 WorldForge `Action` 对象。

```text
ALOHA images + proprio + task text
  -> Cosmos-Policy /act
  -> raw 14D bimanual action chunks
  -> host action_translator
  -> ActionPolicyResult
```

本提供方是当前目录中唯一的 Cosmos 系列提供方。它是用于机器人动作选择的策略适配器，不是媒体或生成式模型适配器。

## 运行时所有权

WorldForge 负责：提供方注册、HTTP 请求策略、ALOHA 封装校验、响应结构校验、原始动作保留、规划组合，以及提供方事件。

宿主方负责：

- NVIDIA Cosmos-Policy 代码检出、Docker 镜像、CUDA 运行时及 GPU 主机
- 模型检查点及任何 Hugging Face / NVIDIA 访问配置
- 从传感器、模拟器状态或数据集行构造 ALOHA 观测数据
- 将原始 14 维双臂动作行转换为 WorldForge `Action` 对象
- 机器人执行、安全互锁、控制器语义及工件留存

WorldForge 从不启动 Cosmos-Policy、安装 CUDA 依赖，或直接驱动硬件。

## 配置

- `COSMOS_POLICY_BASE_URL`：自动注册所必需。示例：`https://cosmos-policy.example.com`。默认情况下屏蔽本地回环/私有端点。
- `COSMOS_POLICY_API_TOKEN`：可选的 Bearer 令牌，以 `Authorization: Bearer ...` 形式发送。
- `COSMOS_POLICY_TIMEOUT_SECONDS`：可选的策略请求超时时间，默认为 `600`。
- `COSMOS_POLICY_EMBODIMENT_TAG`：可选的结果元数据，默认为 `aloha`。
- `COSMOS_POLICY_MODEL`：可选的模型元数据，默认为 `nvidia/Cosmos-Policy-ALOHA-Predict2-2B`。
- `COSMOS_POLICY_RETURN_ALL_QUERY_RESULTS`：可选布尔值。设置后，向支持该 Cosmos-Policy 标志的服务器请求返回所有查询结果。
- `COSMOS_POLICY_ALLOW_LOCAL_BASE_URL`：可选布尔值。仅在受信任的本地回环、SSH 隧道或实验室内网服务器上设置为 `1`。
- `COSMOS_POLICY_ALLOWED_HOSTS`：可选的逗号分隔主机名白名单，适用于限制已配置策略端点的部署场景。支持 `*.example.com` 等 Shell 风格通配符。

URL 校验在预检阶段默认拒绝明显的本地回环/私有/链路本地目标。DNS 检查是 `httpx` 连接前的尽力校验，不会将 TCP 连接固定到已解析地址。当此区别至关重要时，请结合使用主机白名单和网络出口控制。

`COSMOS_POLICY_BASE_URL` 仅能满足端点可用性检查，尚不足以进行策略路由：未提供 `action_translator` 的提供方实例不会声明任何可执行的 `policy` 能力。

运行时清单：`src/worldforge/providers/runtime_manifests/cosmos-policy.json` 记录了所需端点、可选令牌/设置、宿主方持有的运行时工件、最低限度的冒烟测试命令及预期策略选择信号。

程序化构造方式：

```python
from worldforge.providers import CosmosPolicyProvider

provider = CosmosPolicyProvider(
    base_url="http://127.0.0.1:8777",
    allow_local_base_url=True,
    action_translator=translate_actions,
)
```

## 输入契约

```python
result = forge.select_actions(
    "cosmos-policy",
    info={
        "observation": {
            "primary_image": primary_image,
            "left_wrist_image": left_wrist_image,
            "right_wrist_image": right_wrist_image,
            "proprio": proprio,
        },
        "task_description": "put the cube into the bowl",
        "embodiment_tag": "aloha",
        "action_horizon": 16,
        "return_all_query_results": True,
    },
)
```

校验规则：

- `info["observation"]` 必须是非空 JSON 对象。
- ALOHA 观测数据必须包含 `primary_image`、`left_wrist_image`、`right_wrist_image` 和 `proprio`。
- `task_description` 必须是非空字符串，也可包含在观测数据中。
- `options` 若提供，必须是 JSON 对象，且不得与观测数据字段冲突。
- `return_all_query_results` 若在 `info` 中提供，必须是布尔值。
- `action_horizon` 若提供，必须是大于 0 的整数。
- 在返回 `ActionPolicyResult` 之前，必须提供宿主方的 `action_translator`。

## 响应契约

`/act` 响应必须包含：

```json
{
  "actions": [[0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0]]
}
```

WorldForge 校验：

- `actions` 是非空的矩形数值矩阵
- 每个动作行的维度与配置的动作维度一致，默认为 14
- `value_prediction` 若存在，必须是有限数值
- `all_actions` 若存在，必须是非空的候选动作矩阵列表
- `all_value_predictions` 若存在，必须是有限数值列表
- 未来图像预测字段以有界形状摘要的形式记录，而非直接复制至元数据

返回的元数据包含：模型标签、已选候选索引、候选数量、提供方信息、原始动作形状摘要及任务描述。原始未来图像张量不存储于公开元数据中。

## 动作转换

Cosmos-Policy ALOHA 动作是特定于具身形态的物理控制行。WorldForge 校验其形状，但不推断关节语义、夹爪含义、控制器时序或坐标系。该边界由宿主方转换器负责：

```python
from worldforge import Action

def translate_actions(raw_actions, info, provider_info):
    rows = raw_actions["actions"]
    return [
        Action.move_to(float(row[0]), float(row[1]), float(row[2]))
        for row in rows
    ]
```

转换器可返回：

- 单个动作序列块：`[Action.move_to(...), Action.move_to(...)]`
- 多个候选序列块：`[[Action.move_to(...)], [Action.move_to(...)] ]`

当服务器返回 `all_actions` 时，多候选模式适用于策略加打分的规划流程。

## 规划

仅策略规划：

```python
plan = world.plan(
    goal="put the cube into the bowl",
    provider="cosmos-policy",
    policy_info=policy_info,
    execution_provider="mock",
)
```

策略加打分规划：

```python
plan = world.plan(
    goal="choose the lowest-cost Cosmos-Policy candidate",
    policy_provider="cosmos-policy",
    score_provider="leworldmodel",
    policy_info=policy_info,
    score_info=lewm_info,
    execution_provider="mock",
)
```

WorldForge 在调用打分提供方前，会将已转换的策略候选序列化为 `Action.to_dict()` 载荷，除非通过 `score_action_candidates=...` 提供了模型原生的打分候选。

## 远程 GPU 操作手册

当 Cosmos-Policy 运行于租用或实验室 GPU 主机，而 WorldForge 运行于本地检出或独立操作主机时，请使用此流程。边界保持明确：NVIDIA 主机拥有服务器、检查点、CUDA 运行时、Hugging Face 或 NVIDIA 访问权限，以及机器人专属预处理；WorldForge 拥有请求、响应、动作形状校验、动作转换边界、提供方事件及冒烟测试清单。

### 1. 准备 GPU 主机

推荐主机规格：

- 当前 ALOHA Predict2 路径建议 48 GB 或更大的 GPU 显存。若上游 Cosmos-Policy 要求更高，以上游为准。
- Linux 主机，具备可用的 NVIDIA 驱动以及上游 Cosmos-Policy 检出所需的 CUDA/Docker 运行时。
- 访问所需检查点文件及任何受门控模型的审批。请将令牌保存于 GPU 主机或密钥管理器中，不得出现在 WorldForge 文档、提交记录、运行清单或提供方事件中。
- Cosmos-Policy 服务器监听 `/act`，通常在 TCP 端口 `8777`。
- 冒烟测试路径无需机器人硬件。冒烟测试发送预制的 ALOHA 观测数据并将返回的动作块转换为 WorldForge 动作。

成功信号：上游服务器进程正常运行，GPU 在主机上可见，服务器正在监听已配置的 `/act` 端口。

首要排查步骤：检查上游服务器日志，确认模型已完成加载，并使用平台常规 NVIDIA 工具确认主机 GPU 状态，再修改 WorldForge 代码。

### 2. 按需暴露端点

建议从操作主机到 GPU 主机使用 SSH 隧道：

```bash
ssh -N -L 8777:127.0.0.1:8777 <user>@<gpu-host>
```

然后将 WorldForge 指向本地并显式允许受信任的本地端点：

```bash
COSMOS_POLICY_BASE_URL=http://127.0.0.1:8777 \
COSMOS_POLICY_ALLOW_LOCAL_BASE_URL=1 \
  uv run worldforge provider health cosmos-policy
```

若必须使用公网或私网 URL，请将 TCP `8777` 的入站连接限制为操作主机 IP 或 VPN CIDR，并将 `COSMOS_POLICY_ALLOWED_HOSTS` 设置为确切的主机名或 IP。请勿将策略服务器对外完全开放。

### 3. 配置 WorldForge

| 设置项 | 是否必填 | 用途 |
| --- | --- | --- |
| `COSMOS_POLICY_BASE_URL` | 是 | 宿主方 `/act` 服务器的基础 URL。 |
| `COSMOS_POLICY_ALLOW_LOCAL_BASE_URL=1` | 仅用于隧道/实验室本地回环 | 允许受信任的本地回环、私有或实验室内网 URL。 |
| `COSMOS_POLICY_ALLOWED_HOSTS` | 建议对网络 URL 使用 | 将配置的端点限制为已知主机。 |
| `COSMOS_POLICY_API_TOKEN` | 可选 | 反向代理或受保护服务器的 Bearer 令牌。 |
| `COSMOS_POLICY_TIMEOUT_SECONDS` | 可选 | 首次推理较慢时的请求超时时间，默认为 `600`。 |

`COSMOS_POLICY_BASE_URL` 仅能满足端点可用性检查。提供方实例仍需宿主方的 `action_translator` 才能返回可执行的策略动作。

如需在 LeRobot、GR00T 和 Cosmos-Policy 之间进行可检出的策略回放对比，请运行 `uv run python scripts/demo_showcases.py run embodied-policy-replay-comparison`。在进入预制主机的 `uv run worldforge-smoke-cosmos-policy --help` 流程之前，使用报告检查 50 x 14 ALOHA 动作行、价值预测元数据及转换器阻塞情况。

### 4. 仅执行健康检查冒烟测试

预制主机可传入 `--health-only` 以在不发送策略请求的情况下验证 WorldForge 配置。由于 Cosmos-Policy 在本适配器所针对的服务器结构中未暴露非变更性的健康端点，健康检查仅确认配置；实时推理证据需通过 `select_actions(...)` 或下述完整冒烟测试命令获取。

```bash
COSMOS_POLICY_BASE_URL=http://127.0.0.1:8777 \
COSMOS_POLICY_ALLOW_LOCAL_BASE_URL=1 \
  uv run worldforge-smoke-cosmos-policy \
    --health-only \
    --run-manifest .worldforge/runs/cosmos-policy-health/run_manifest.json
```

预期成功信号：`run_manifest.json` 记录 `capability=policy`，`status=skipped`。

首要排查步骤：运行 `uv run worldforge provider health cosmos-policy` 确认配置，再检查隧道/防火墙连通性后发送完整 `/act` 请求。

### 5. 执行完整 `/act` 冒烟测试

完整冒烟测试需要准备好 ALOHA 策略信息并提供受信任的动作转换器。由于转换器为宿主方代码，该命令需要显式传入 `--allow-translator-code` 作为授权确认。

连接至正在运行的 Cosmos-Policy ALOHA 服务器：

```bash
COSMOS_POLICY_BASE_URL=http://127.0.0.1:8777 \
COSMOS_POLICY_ALLOW_LOCAL_BASE_URL=1 \
  uv run worldforge-smoke-cosmos-policy \
    --policy-info-json /path/to/policy_info.json \
    --translator /path/to/translator.py:translate_actions \
    --allow-translator-code \
    --run-manifest .worldforge/runs/cosmos-policy-live/run_manifest.json
```

预期成功信号：`run_manifest.json` 记录 `capability=policy`，`status=passed`，摘要包含非空的动作形状（如 `50 x 14`），且提供方事件已脱敏。

首要排查步骤：若配置正常但完整冒烟测试失败，请检查 GPU 服务器日志、`policy_info.json` 的 ALOHA 观测形状、转换器导入路径及原始动作形状。实地 RTX A6000 验证发现，真实的 Cosmos 响应可能使用 `json_numpy` 风格的动作行而非普通 JSON 行；WorldForge 在转换前会对该形状进行解码和校验。

冒烟测试可将脱敏的 `run_manifest.json` 写入文件，内容包含：仅记录值是否存在的环境变量状态、运行时清单 ID、输入夹具摘要、事件计数及结果摘要。该清单不存储令牌、原始图像张量、检查点字节或机器人控制器状态。

### 6. 关闭或保留证据

仅复制脱敏证据，如 `run_manifest.json`、提供方事件计数、结果摘要及可安全检出的小型回放工件。不得提交包含令牌的 GPU 日志、原始图像、原始未来张量、检查点文件、Docker 镜像层或已下载数据集。

冒烟测试完成后，休眠或终止 GPU 主机。云端计费通常在虚拟机运行期间持续产生费用，休眠状态的机器仍可能产生磁盘或公网 IP 费用。

## 实时冒烟测试证据

使用上述操作手册生成实时证据。已提交的回放工件应为脱敏且确定性的；除非原始运行时输出有意保留在仓库外，否则不应将其描述为已提交的实时 GPU 工件。

## 故障模式

- 缺少 `COSMOS_POLICY_BASE_URL` 将导致提供方未被注册。
- 缺少 `action_translator` 将触发 `ProviderError`。
- 格式错误的观测数据在调用策略服务器之前即告失败。
- 服务器不可达、HTTP 状态码非成功、JSON 无效或响应结构错误均以提供方错误形式失败。
- 非有限的原始动作值在返回 `ActionPolicyResult` 之前即告失败。
- 若打分提供方选择的候选索引超出已转换策略候选列表范围，策略加打分规划将失败。
- 运行上游 Cosmos-Policy 需要兼容的 Linux/NVIDIA 运行时。在不支持的主机上，应将 WorldForge 连接至远程服务器，而非尝试将 CUDA 依赖安装至 WorldForge 中。

## 测试

- `tests/test_cosmos_policy_provider.py` 涵盖：提供方契约检查、请求载荷形状、候选/价值保留、缺少转换器的失败情形、格式错误的观测数据、格式错误的响应、仅策略规划，以及策略加打分规划。
- `tests/test_cosmos_policy_smoke_script.py` 涵盖：在不需要 Cosmos-Policy、GPU 或网络访问的情况下测试实时冒烟测试入口点。

## 主要参考资料

- [NVIDIA Cosmos-Policy 代码](https://github.com/nvlabs/cosmos-policy)
- [NVIDIA Cosmos 文档](https://docs.nvidia.com/cosmos/latest/)

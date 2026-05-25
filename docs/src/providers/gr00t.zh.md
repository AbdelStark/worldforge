# GR00T 提供方

能力：`policy`

分类类别：具身策略 / VLA 动作模型

`gr00t` 封装了 NVIDIA Isaac GR00T 的策略客户端接口。GR00T 被建模为一个执行者：接收多模态观测数据和语言指令，然后返回机器人动作块。它不被建模为预测性世界模型、视频生成器或候选动作打分器。

```text
observation + language instruction
  -> GR00T policy client
  -> raw embodiment-specific action arrays
  -> host action_translator
  -> ActionPolicyResult
```

## 运行时所有权

WorldForge 负责：提供方注册、观测信封验证、原始动作保留、动作结果验证、规划组合以及提供方事件。

由宿主方持有：

- Isaac GR00T 安装及依赖项
- 可访问的策略服务器
- 模型检查点及特定机器人的运行时配置
- 来自传感器、模拟器或日志的观测数据
- 将原始策略数组转换为 WorldForge `Action` 对象的翻译逻辑
- 机器人执行、安全联锁及控制器集成

WorldForge 从不直接驱动硬件。

## 配置

- `GROOT_POLICY_HOST`：自动注册所必需。运行中的 GR00T 策略服务器的主机名或 IP 地址。
- `GROOT_POLICY_PORT`：可选，默认值为 `5555`。
- `GROOT_POLICY_TIMEOUT_MS`：可选，默认值为 `15000`。
- `GROOT_POLICY_API_TOKEN`：可选令牌，传递给策略客户端。
- `GROOT_POLICY_STRICT`：可选布尔值，默认为 `false`。
- `GROOT_EMBODIMENT_TAG`：机器人具身形态的可选元数据。

该适配器不会将 Isaac GR00T、PyTorch、CUDA、TensorRT、检查点或机器人运行时依赖项添加到 WorldForge 的基础安装中。

运行时清单：
`src/worldforge/providers/runtime_manifests/gr00t.json` 记录了策略服务器环境、可选客户端配置、由宿主方持有的策略/运行时工件、最小冒烟测试命令以及预期的策略客户端健康信号。

## 运行时契约

成熟度：`beta`。已准备好的宿主方在提供可访问的服务器、可选鉴权令牌、观测信封和动作翻译器后，可使用远程 PolicyClient 路径进行策略选择。WorldForge 默认不启动或监管本地 GR00T 运行时服务。

使用注入的测试客户端或由宿主方持有的客户端进行直接构建：

```python
from worldforge.providers import GrootPolicyClientProvider

provider = GrootPolicyClientProvider(
    policy_client=client,
    embodiment_tag="LIBERO_PANDA",
    action_translator=translate_actions,
)
```

注入或延迟创建的客户端必须暴露：

```python
get_action(observation, options=None) -> actions | (actions, info)
```

若未注入客户端，WorldForge 会延迟导入：

```python
from gr00t.policy.server_client import PolicyClient
```

并从 `GROOT_POLICY_*` 配置创建客户端。

如果完整的 Isaac GR00T 包在 WorldForge 进程中无法导入，提供方将回退到一个小型 ZMQ/msgpack 客户端，用于已文档化的 PolicyServer 协议。由于 NVIDIA 的完整 `gr00t` 运行时目前固定在 Python 3.10，而 WorldForge 运行在 Python 3.13，此回退对于常见的远程 GPU 形态非常有用。该回退仍需要宿主方安装以下可选客户端包：

```bash
GROOT_POLICY_HOST=127.0.0.1 \
GROOT_POLICY_PORT=5555 \
uv run --with msgpack --with pyzmq --with numpy python scripts/smoke_gr00t_policy.py \
  --health-only \
  --run-manifest .worldforge/runs/gr00t-health/run_manifest.json
```

GPU 服务器端仍需持有完整的 Isaac GR00T 安装、CUDA 运行时、检查点及特定机器人的依赖项。

## 输入契约

```python
result = forge.select_actions(
    "gr00t",
    info={
        "observation": {
            "video": {"front": video_array},
            "state": {"eef": state_array},
            "language": {"task": [["pick up the cube"]]},
        },
        "embodiment_tag": "LIBERO_PANDA",
        "action_horizon": 16,
        "options": {},
    },
)
```

验证规则：

- `info["observation"]` 必须是 JSON 对象。
- 观测数据必须至少包含 `video`、`state` 或 `language` 之一。
- `options` 若提供，必须是 JSON 对象。
- 带有 `tolist()` 方法的类张量值会被规范化，以用于元数据和原始动作保留。
- 在返回 `ActionPolicyResult` 之前，必须提供由宿主方提供的 `action_translator`。

`select_actions()` 发出的提供方事件包括：操作 `policy`、尝试次数 `1`、最大尝试次数 `1`、方法 `POLICYCLIENT.GET_ACTION`、脱敏后的目标、耗时、超时配置以及严格模式标志。消息、目标或元数据中的类令牌值在写入日志或运行清单之前会被脱敏处理。

## 动作翻译

GR00T 的动作是特定具身形态的物理动作数组。WorldForge 无法推断关节含义、夹爪语义、控制器时序或坐标系。翻译器负责该映射：

```python
from worldforge import Action

def translate_actions(raw_actions, info, provider_info):
    return [
        Action.move_to(0.3, 0.5, 0.0),
        Action.move_to(0.4, 0.5, 0.0),
    ]
```

翻译器可以返回：

- 单个动作块：`[Action.move_to(...), Action.move_to(...)]`
- 多个候选块：`[[Action.move_to(...)], [Action.move_to(...)] ]`

多个候选动作可用于策略与打分联合规划。

## 规划

仅使用策略的规划：

```python
plan = world.plan(
    goal="pick up the cube",
    provider="gr00t",
    policy_info=policy_info,
    execution_provider="mock",
)
```

策略与打分联合规划：

```python
plan = world.plan(
    goal="choose the lowest-cost policy candidate",
    policy_provider="gr00t",
    score_provider="leworldmodel",
    policy_info=policy_info,
    score_info=lewm_info,
    execution_provider="mock",
)
```

WorldForge 在调用打分提供方之前，会将策略候选动作序列化为 `Action.to_dict()` 载荷，除非 `score_action_candidates=...` 提供了模型原生候选动作。

如需在无需 GR00T、CUDA 或机器人控制器的情况下，以可安全检出的方式体验相同的策略+打分边界，请运行 `uv run python scripts/demo_showcases.py run policy-score-candidate-lab`。该实验室会使提供方特定的原始动作保持可见，并明确展示缺少翻译器时的行为。

如需跨 LeRobot、GR00T 和 Cosmos-Policy 的并排策略回放对比，请运行 `uv run python scripts/demo_showcases.py run embodied-policy-replay-comparison`。在进入已准备好的宿主方路径 `uv run python scripts/smoke_gr00t_policy.py --help` 之前，可通过报告检查 GR00T 命名张量和翻译器阻塞情况。

## 冒烟测试实证

连接到已运行的 GR00T 策略服务器：

```bash
GROOT_POLICY_HOST=127.0.0.1 \
GROOT_POLICY_PORT=5555 \
uv run --with msgpack --with pyzmq --with numpy python scripts/smoke_gr00t_policy.py \
  --policy-info-json /path/to/policy_info.json \
  --translator /path/to/translator.py:translate_actions \
  --allow-translator-code \
  --run-manifest .worldforge/runs/gr00t-live/run_manifest.json
```

`--translator` 会导入并执行本地 Python 代码。冒烟测试命令要求提供 `--allow-translator-code`，以便操作员明确选择运行受信任的翻译器代码。如果策略输入通过 `--observation-module` 创建，请在审核观测工厂代码后传入 `--allow-observation-code`。

已准备好的宿主方可在不发起策略请求的情况下运行配置和连通性检查：

```bash
GROOT_POLICY_HOST=127.0.0.1 \
GROOT_POLICY_PORT=5555 \
uv run --with msgpack --with pyzmq --with numpy python scripts/smoke_gr00t_policy.py \
  --health-only \
  --run-manifest .worldforge/runs/gr00t-health/run_manifest.json
```

从宿主方持有的 Isaac-GR00T 检出目录启动上游服务器：

```bash
uv run python scripts/smoke_gr00t_policy.py \
  --start-server \
  --gr00t-root /path/to/Isaac-GR00T \
  --model-path nvidia/GR00T-N1.6-3B \
  --embodiment-tag GR1 \
  --policy-info-json /path/to/policy_info.json \
  --translator /path/to/translator.py:translate_actions \
  --allow-translator-code \
  --run-manifest .worldforge/runs/gr00t-live/run_manifest.json
```

使用 `--start-server` 时，冒烟脚本会向 stderr 写入已清理的启动命令行：转发给服务器的密钥形参数和宿主本地路径会在显示前被隐去，但启动上游服务器时仍使用宿主方拥有的原始命令。

启动上游 Isaac GR00T 需要兼容的 NVIDIA/Linux 运行时，以满足 CUDA 和 TensorRT 的依赖要求。在不受支持的宿主机上，请将 WorldForge 连接到已运行的远程策略服务器。

对于远程 GPU，请尽量将 GR00T 服务器保持私有，并通过 SSH 隧道连接：

```bash
ssh -N -L 5555:127.0.0.1:5555 ubuntu@<gpu-host>
```

如果必须使用直接网络连接，请将服务器端口限制为操作员 IP 或 VPN。不要将 GR00T 策略服务器公开暴露在公共互联网上。

预期成功信号：

- `--health-only`：运行清单记录 `capability=policy`，状态为 `status=skipped`。
- 完整冒烟测试（`--policy-info-json` 或 `--observation-json` 加 `--translator`）：运行清单记录 `capability=policy`，状态为 `status=passed`。

首要排查步骤：

- 运行 `uv run worldforge provider health gr00t` 以确认客户端配置和服务器可达性，然后重新运行带 `--run-manifest` 的冒烟测试命令，以便为失败生成脱敏摘要。

冒烟测试可以写入一个脱敏的 `run_manifest.json`，其中包含：无值的环境变量存在性、运行时清单 ID、输入夹具摘要、事件计数和结果摘要。清单不存储令牌、原始传感器张量、检查点字节或机器人控制器状态。冒烟测试完成后，请休眠或终止远程 GPU 实例。

## 故障模式

- 缺少 `GROOT_POLICY_HOST` 会导致提供方未被注册。
- 缺少 `gr00t.policy.server_client.PolicyClient` 会由 `health()` 报告。
- 策略服务器不可达或 ping 失败会由 `health()` 报告，且不会泄露令牌。
- 缺少 `action_translator` 会以 `ProviderError` 失败。
- 格式错误的观测数据在调用策略客户端之前即会失败。
- 不兼容 JSON 的原始动作或提供方信息在返回 `ActionPolicyResult` 之前即会失败。
- 策略推理失败会被包装为 `ProviderError`。
- 在不受支持的宿主机上启动上游服务器可能在 WorldForge 连接之前就已失败。
- 若打分提供方选择了策略候选列表范围之外的索引，策略+打分规划将失败。

## 测试

- `tests/test_gr00t_provider.py` 涵盖注入客户端的契约检查、事件发射、格式错误的输入、缺少翻译器、健康检查失败、仅策略规划以及策略+打分规划。
- `tests/test_gr00t_smoke_script.py` 涵盖冒烟脚本输入加载和服务器预检验证，无需 Isaac GR00T 或 GPU。

## 主要参考资料

- [NVIDIA Isaac GR00T 代码](https://github.com/NVIDIA/Isaac-GR00T)

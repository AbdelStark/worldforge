# LeRobot 提供方

能力：`policy`

分类类别：具身策略 / 模仿学习与强化学习动作模型

`lerobot` 封装了 Hugging Face LeRobot 的 `PreTrainedPolicy` 接口。LeRobot 被建模为一个执行者：接收机器人观测数据并返回动作张量。它不被建模为预测性世界模型、视频生成器或候选动作打分器。

```text
observation + optional task language
  -> LeRobot policy
  -> raw embodiment-specific action tensors
  -> host action_translator
  -> ActionPolicyResult
```

## 运行时所有权

WorldForge 负责：提供方注册、策略调用信封验证、原始动作保留、动作结果验证、规划组合以及提供方事件。

由宿主方持有：

- LeRobot 安装及特定机器人的依赖项
- Hugging Face 仓库 ID 或本地检查点目录
- 观测数据的构建与预处理
- 将原始策略张量转换为 WorldForge `Action` 对象的翻译逻辑
- 机器人执行、安全联锁及控制器集成

WorldForge 从不直接驱动硬件。

## 配置

- `LEROBOT_POLICY_PATH` 或 `LEROBOT_POLICY`：自动注册所必需。值为 Hugging Face 仓库 ID 或本地检查点目录，例如 `lerobot/act_aloha_sim_transfer_cube_human`。
- `LEROBOT_POLICY_TYPE`：可选的策略类提示。支持的值包括 `act`、`diffusion`、`tdmpc`、`vqbet`、`pi0`、`pi0fast`、`sac` 和 `smolvla`。
- `LEROBOT_DEVICE`：可选的设备字符串，传递给 `policy.to(...)`，默认为 `cpu`。
- `LEROBOT_CACHE_DIR`：可选的 Hugging Face 缓存目录。
- `LEROBOT_EMBODIMENT_TAG`：机器人具身形态的可选元数据。

该适配器不会将 LeRobot、PyTorch、NumPy、检查点、仿真包或机器人运行时依赖项添加到 WorldForge 的基础安装中。

运行时清单：
`src/worldforge/providers/runtime_manifests/lerobot.json` 记录了策略路径别名、可选的设备/缓存配置、由宿主方持有的检查点和翻译器工件、最小冒烟测试命令以及预期的策略选择信号。

## 运行时契约

使用注入的测试策略或由宿主方持有的策略进行直接构建：

```python
from worldforge.providers import LeRobotPolicyProvider

provider = LeRobotPolicyProvider(
    policy=policy,
    embodiment_tag="aloha",
    action_translator=translate_actions,
)
```

注入或延迟加载的策略必须暴露：

```python
policy.select_action(observation) -> action_tensor              # required
policy.predict_action_chunk(observation) -> action_chunk_tensor # optional
policy.reset()                                                  # optional
```

支持的加载模式如下（均为显式）：

- 注入 `policy=...`，用于测试或宿主方管理的运行时
- 注入 `policy_loader=...`，用于宿主方自定义加载
- `PreTrainedPolicy.from_pretrained(...)`，使用配置的路径加载
- 设置 `LEROBOT_POLICY_TYPE` 后，使用类型化的策略类加载

若未注入策略，WorldForge 会延迟导入 `PreTrainedPolicy` 并加载已配置的检查点。如果设置了 `LEROBOT_POLICY_TYPE`，则在调用 `from_pretrained(...)` 之前会先解析具体的策略类。

加载后，适配器会在相应方法存在时依次调用 `policy.to(device)`、`policy.eval()`、`policy.requires_grad_(False)` 和 `policy.reset()`。默认设备为 `cpu`；宿主方必须通过 `LEROBOT_DEVICE` 或 `device=` 显式选择 `cuda`、`mps` 或其他特定运行时设备。

## 输入契约

```python
result = forge.select_actions(
    "lerobot",
    info={
        "observation": {
            "observation.state": state_tensor_or_array,
            "observation.images.top": image_tensor_or_array,
            "task": "pick up the red cube",
        },
        "embodiment_tag": "aloha",
        "action_horizon": 16,
        "options": {},
        "mode": "select_action",
    },
)
```

验证规则：

- `info["observation"]` 必须是非空 JSON 对象。
- 观测数据键应遵循 LeRobot 约定，例如 `observation.state`、`observation.images.<camera>` 和 `task`。
- `info["options"]` 若提供，必须是 JSON 对象。
- `info["mode"]` 为 `select_action` 或 `predict_chunk`。
- `predict_chunk` 要求策略实现 `predict_action_chunk`。
- 带有 `tolist()` 方法的类张量值会被规范化，以用于元数据和原始动作保留。
- 在返回 `ActionPolicyResult` 之前，必须提供由宿主方提供的 `action_translator`。
- 结果元数据包含 `loader_mode` 以及有界的 `raw_action_summary`，其中含有类型、可用时的矩形形状以及适合运行报告的简短预览。

## 动作翻译

LeRobot 动作张量是特定具身形态的：7 自由度机械臂、双臂配置、移动底盘或自定义机器人可能均采用不同的动作编码方式。翻译器负责该映射：

```python
from worldforge import Action

def translate_actions(raw_actions, info, provider_info):
    tensor = raw_actions.tolist() if hasattr(raw_actions, "tolist") else raw_actions
    return [
        Action.move_to(float(x), float(y), float(z))
        for (x, y, z) in tensor[0]
    ]
```

翻译器可以返回：

- 单个动作块：`[Action.move_to(...), Action.move_to(...)]`
- 多个候选块：`[[Action.move_to(...)], [Action.move_to(...)] ]`

多个候选动作可用于策略与打分联合规划。

当翻译器具有已知的机器人或任务边界时，可使用 `EmbodimentTranslatorContract` 和 `EmbodimentActionTranslator`：

```python
from worldforge import Action
from worldforge.providers import EmbodimentActionTranslator, EmbodimentTranslatorContract

contract = EmbodimentTranslatorContract(
    embodiment_tag="aloha",
    action_dim=3,
    action_horizon=16,
    metadata={"controller": "host-owned", "units": "meters"},
)

def translate_actions(raw_actions, info, provider_info):
    tensor = raw_actions.tolist() if hasattr(raw_actions, "tolist") else raw_actions
    return [Action.move_to(float(x), float(y), float(z)) for (x, y, z) in tensor]

translator = EmbodimentActionTranslator(contract, translate_actions)
```

该契约会验证传入的 `embodiment_tag`、矩形数值原始动作、有限值、可选的动作维度、可选的时域长度、JSON 原生元数据以及返回的候选动作数量。对于未知的具身形态标签或形状不匹配的情况，它会在规划之前失败，而不是填充、投影或静默丢弃策略输出。提供方会在 `ActionPolicyResult.metadata` 中存储 `translator_contract` 摘要，使运行工件能够引用已验证的翻译边界，而无需包含机器人凭据或控制器状态。

打包的 PushT 机器人案例展示使用此包装器处理其可视化的 `x, y` 翻译，而独立的 LeWorldModel 候选构建器则持有检查点原生的 10 维打分张量。宿主方应遵循相同的分离原则：WorldForge 负责验证边界并保留溯源信息；宿主代码负责预处理、控制器语义、安全联锁以及任何硬件执行。

## 规划

仅使用策略的规划：

```python
plan = world.plan(
    goal="pick up the red cube",
    provider="lerobot",
    policy_info=policy_info,
    execution_provider="mock",
)
```

策略与打分联合规划：

```python
plan = world.plan(
    goal="choose the lowest-cost policy candidate",
    policy_provider="lerobot",
    score_provider="leworldmodel",
    policy_info=policy_info,
    score_info=lewm_info,
    execution_provider="mock",
)
```

WorldForge 在调用打分提供方之前，会将策略候选动作序列化为 `Action.to_dict()` 载荷，除非 `score_action_candidates=...` 提供了模型原生候选动作。

如需在无需 LeRobot、检查点或机器人控制的情况下，以可安全检出的方式体验候选排名循环，请运行 `uv run python scripts/demo_showcases.py run policy-score-candidate-lab`。该实验室展示了生成的候选动作、原始策略动作保留、选定动作元数据、无效候选边界以及缺少翻译器时的失败处理。

如需跨 LeRobot、GR00T 和 Cosmos-Policy 的并排策略回放对比，请运行 `uv run python scripts/demo_showcases.py run embodied-policy-replay-comparison`。在进入已准备好的宿主方路径 `uv run python scripts/smoke_lerobot_policy.py --help` 之前，可通过报告检查 LeRobot 原始张量形状和翻译器阻塞情况。

## 运行时检查

可安全检出的端到端演示：

```bash
uv run worldforge-demo-lerobot
uv run worldforge-demo-lerobot --json-only
```

该演示将确定性策略注入到真实的 `LeRobotPolicyProvider` 中，无需 LeRobot、torch 或检查点即可验证 WorldForge 策略+打分路径。

真实策略冒烟测试：

```bash
uv run python scripts/smoke_lerobot_policy.py \
  --policy-path lerobot/act_aloha_sim_transfer_cube_human \
  --observation-module /path/to/obs.py:build_observation \
  --translator /path/to/translator.py:translate_actions \
  --device cpu
```

这需要宿主方安装的 LeRobot、策略检查点、观测数据源以及特定具身形态的动作翻译器。

LeRobot + LeWorldModel 机器人回放案例展示：

```bash
scripts/robotics-showcase
```

这是打包的 PushT 案例展示中 `worldforge-demo-lerobot` 的真实检查点版本。完整的可运行上下文见 [CLI 参考](../cli.md)、[示例与 CLI 命令](../examples.md) 以及 [机器人回放案例展示](../robotics-showcase.md)。

## 故障模式

- 同时缺少 `LEROBOT_POLICY_PATH` 和 `LEROBOT_POLICY` 会导致提供方未被注册。
- 缺少 `lerobot` 或 `PreTrainedPolicy` 会由 `health()` 报告。
- 看起来像本地路径但实际不存在的检查点路径会在运行时导入之前由 `health()` 报告。
- 不支持的 `LEROBOT_POLICY_TYPE` 值会在提供方构建期间失败。
- 策略类解析或检查点加载失败会被包装为 `ProviderError`。
- 缺少 `action_translator` 会以 `ProviderError` 失败。
- 有契约的翻译器会在以下情况失败：未知的具身形态标签、非有限的原始动作值、原始动作形状不匹配以及候选动作数量不匹配。
- 格式错误的观测数据、选项或模式在调用策略之前即会失败。
- 对不支持 `predict_action_chunk` 的策略请求 `mode="predict_chunk"` 会显式失败。
- 不兼容 JSON 的原始动作或提供方信息在返回 `ActionPolicyResult` 之前即会失败。
- 策略推理失败会被包装为 `ProviderError`。

## 测试

- `tests/test_lerobot_provider.py` 涵盖注入策略的契约检查、事件发射、格式错误的输入、缺少翻译器、未配置时的健康状态、环境配置、延迟导入、select/predict_chunk 模式、reset 委托、自动注册、翻译器契约以及策略+打分规划。
- `tests/test_lerobot_e2e_demo.py` 涵盖完整的可安全检出演示。
- `tests/test_lerobot_smoke_script.py` 涵盖冒烟脚本输入加载、可调用对象解析及验证，无需 LeRobot 或 GPU。
- `tests/test_lerobot_leworldmodel_smoke_script.py` 和 `tests/test_robotics_showcase.py` 涵盖组合真实运行时的运行器、打包的案例展示默认值、动态候选桥接行为以及 JSON 输出。

## 主要参考资料

- [Hugging Face LeRobot 代码](https://github.com/huggingface/lerobot)
- [LeRobot 策略文档](https://huggingface.co/docs/lerobot/bring_your_own_policies)
- [LeRobot PushT 扩散策略](https://huggingface.co/lerobot/diffusion_pusht)

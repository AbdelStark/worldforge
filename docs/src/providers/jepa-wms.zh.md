# JEPA-WMS 提供方候选

能力：直接构造 `score` 候选

分类：JEPA 潜在预测世界模型

`jepa-wms` 是针对 [`facebookresearch/jepa-wms`](https://github.com/facebookresearch/jepa-wms) 未来工作的候选脚手架。它的存在是为了在公开的提供方注册表中不声称运行时支持的前提下，明确规划中的打分模型提供方能力契约。

该提供方有意未从 `worldforge.providers` 导出，未出现在 `PROVIDER_CATALOG` 中，也未进行自动注册。测试和宿主方实验可直接导入 `worldforge.providers.jepa_wms.JEPAWMSProvider`。

## 晋升规则

在集成满足以下条件之前，不得导出或自动注册此提供方：

- 针对真实权重的经过验证的上游运行时路径
- 已记录的检查点、设备、任务族及批处理限制
- JEPA-WMS 候选张量与 WorldForge `Action` 序列之间的稳定映射
- 覆盖格式错误输入、上游错误及无效输出的夹具
- 不隐藏可选依赖要求的实时冒烟测试路径

当前决策：将 `jepa-wms` 保持为直接构造候选。即使准备好的宿主成功运行了下方的冒烟测试命令，在提交经过检查的真实运行时证据（针对所选上游模型和任务族）之前，WorldForge 不应自动注册它。

打包的运行时清单 `jepa-wms:schema-1` 仅用于使已准备宿主的冒烟测试证明可被机器读取。它不会使 `jepa-wms` 成为目录提供方、导出提供方或自动注册的运行时。

## 运行时归属

WorldForge 负责候选提供方外壳、打分结果验证、事件发射及打分规划测试。

宿主方负责：

- PyTorch 和 JEPA-WMS 依赖
- 模型下载与检查点兼容性
- 可选的 torch-hub 加载
- 观测值、目标、动作历史及候选动作的预处理
- 模型原生动作与 WorldForge `Action` 对象之间的映射

WorldForge 不会将 JEPA-WMS、torch、数据集、检查点或模拟器依赖添加到其基础包中。

## 直接构造

注入运行时：

```python
from worldforge.providers.jepa_wms import JEPAWMSProvider

provider = JEPAWMSProvider(
    model_path="/models/jepa-wms/checkpoint.pt",
    runtime=test_or_host_runtime,
)
```

注入的运行时必须是可调用的，或暴露以下接口：

```python
score_actions(*, model_path: str, info: dict, action_candidates: object) -> object
```

Torch-hub 运行时：

```python
from worldforge.providers.jepa_wms import JEPAWMSProvider

provider = JEPAWMSProvider.from_torch_hub(
    model_name="jepa_wm_pusht",
    device="cpu",
)
```

torch-hub 运行时懒惰导入 torch 并加载：

```python
model, preprocessor = torch.hub.load(
    "facebookresearch/jepa-wms",
    "jepa_wm_pusht",
)
```

它优先委托给模型原生的打分方法（若存在）。若加载的模型未暴露打分方法，则使用规划形状：

```text
observation -> model.encode(..., act=True) -> z_init
goal        -> model.encode(..., act=False) -> z_goal
actions     -> model.unroll(z_init, act_suffix=actions)
score       -> latent L1/L2 distance between final predicted latent and goal latent
```

## 输入契约

打分所需输入：

- `info["observation"]`：类张量对象或至少具有两个维度的矩形嵌套有限数值序列
- `info["goal"]`：类张量对象或至少具有两个维度的矩形嵌套有限数值序列
- `info["action_history"]`：可选的类张量对象或至少具有两个维度的矩形嵌套有限数值序列
- `action_candidates`：形状为 `(batch, samples, horizon, action_dim)` 的类张量对象或矩形嵌套有限数值序列

torch-hub 运行时支持恰好一个批次，每个样本返回一个分数。批量打分语义在公开的 `ActionScoreResult` 契约中尚未定义。

`score_info` 键：

- `observation`：上游模型接受的观测载荷
- `goal`：上游模型接受的目标载荷
- `objective`：可选，默认为 `l2`；也支持 `l1`
- `actions_are_normalized`：可选，默认为 `true`。仅当加载的预处理器暴露 `normalize_actions(...)` 时才设为 `false`。该值必须是 JSON 布尔值，而非字符串。

## 运行时响应契约

成功：

```json
{
  "scores": [0.4, 0.12, 0.9],
  "lower_is_better": true,
  "metadata": {
    "score_units": "latent_cost"
  }
}
```

失败：

```json
{
  "error": {
    "type": "checkpoint_expired",
    "message": "checkpoint artifact is expired or unavailable"
  }
}
```

`best_index` 为可选项。若省略，WorldForge 将根据 `scores` 和 `lower_is_better` 推导该值。失败响应将转换为 `ProviderError` 并发射失败事件。

## 规划

候选提供方可手动注册，用于本地打分规划实验：

```python
forge = WorldForge(auto_register_remote=False)
forge.register_provider(provider)

plan = world.plan(
    goal="choose the lowest latent-distance candidate",
    provider="jepa-wms",
    candidate_actions=[candidate_a, candidate_b],
    score_info=score_info,
    score_action_candidates=action_candidate_tensor,
    execution_provider="mock",
)
```

在满足晋升规则之前，请勿将其作为公开的 jepa-wms 支持对外宣传。

## 已准备宿主冒烟测试

已准备好的宿主可验证由宿主方持有的 torch-hub 路径，并保留可安全用于问题上报的证明：

```bash
uv run --with torch worldforge-smoke-jepa-wms \
  --model-name jepa_wm_pusht \
  --device cpu \
  --json-output .worldforge/runs/jepa-wms-live/results/summary.json \
  --run-manifest .worldforge/runs/jepa-wms-live/run_manifest.json
```

该命令仅在运行时导入 `torch`，调用 `JEPAWMSProvider.from_torch_hub(...)`，对合成的观测值、目标、动作历史和候选动作张量进行打分，并写入经脱敏的 `run_manifest.json`。清单包含无值的环境变量存在性记录、输入形状、运行时清单 id、输入摘要、结果摘要、运行时版本字段（如 torch 版本/模型类）、事件计数，以及包含候选数量、分数方向、最优索引和最优分数的打分摘要。

冒烟测试命令不会为用户下载或固定检查点。宿主方仍须负责兼容的 `facebookresearch/jepa-wms` 运行时、模型名称、检查点可用性、设备选择以及任务预处理。

## 失败模式

- 模型路径缺失导致提供方构造或健康检查失败。
- 运行时缺失使健康状态保持不健康。
- 运行时错误载荷转换为 `ProviderError`。
- 观测值或目标字段缺失，将在调用运行时前失败。
- 参差不齐的嵌套数组、非有限值、不支持的候选动作形状、多批次张量及分数数量不匹配，均会明确失败。
- torch-hub 加载器缺失、不支持的目标函数、动作归一化失败及意外的运行时异常，均被包装为 `ProviderError`。

## 测试

- `tests/test_jepa_wms_provider.py` 覆盖了注入运行时打分、torch-hub 运行时行为、格式错误输入、运行时错误载荷、非有限分数、分数数量不匹配、提供方契约检查、打分规划、提供方事件，以及已准备宿主冒烟测试清单契约。
- `tests/fixtures/providers/jepa_wms_*.json` 存储契约夹具。

## 主要参考资料

- [facebookresearch/jepa-wms](https://github.com/facebookresearch/jepa-wms)
- [V-JEPA 2 论文](https://arxiv.org/abs/2506.09985)

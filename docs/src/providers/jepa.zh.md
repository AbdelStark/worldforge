# JEPA 提供方

能力：`score`

分类类别：JEPA 潜在预测世界模型

`jepa` 是公开的、仅限打分的 JEPA 适配器。首个运行时接口故意保持精简：它使用上游 JEPA-WM 模型对候选动作张量进行打分，并返回 `ActionScoreResult`。它不暴露 `predict`、`embed` 或 `policy`。

## 提供方选型 RFC

决策：使用 [`facebookresearch/jepa-wms`](https://github.com/facebookresearch/jepa-wms) 作为首个公开的 JEPA 运行时路径，通过 `torch.hub.load("facebookresearch/jepa-wms", model_name)` 调用。

选择该接口的原因：

- 上游仓库发布了 JEPA-WM 检查点和 torch-hub 模型入口点；
- 上游规划接口本质上是一个候选动作代价模型，因此 `score` 是诚实的 WorldForge 能力声明；
- WorldForge 已通过 `jepa-wms` 直接构建候选，拥有打分规划契约和运行实证；
- `predict` 和 `embed` 需要独立的潜在展开或表征契约，目前尚不稳定，不适合默认暴露。

上游文档中记录的初始模型名称包括 `jepa_wm_pusht`、`jepa_wm_droid`、`jepa_wm_metaworld`、`jepa_wm_pointmaze` 和 `jepa_wm_wall`。除非宿主方已验证其他任务族，否则请使用 `jepa_wm_pusht` 作为最小公开冒烟路径。

## 运行时所有权

WorldForge 负责：

- 提供方注册和打分能力声明；
- 运行时调用之前的输入形状验证；
- 打分结果验证、最优索引选择和提供方事件；
- 打分规划集成和契约测试。

由宿主方持有：

- 安装 PyTorch 和上游 JEPA-WMS 依赖项；
- 下载兼容的检查点及任何可选的编码器资产；
- 选择 `JEPA_MODEL_NAME`；
- 将观测数据、目标、动作历史和候选动作转换为任务形状的张量；
- 为选定的模型、检查点和任务保留实时冒烟测试实证。

WorldForge 不会将 PyTorch、JEPA-WMS、数据集、检查点、模拟器或机器人预处理依赖项添加到其基础包中。

## 配置

必填：

- `JEPA_MODEL_NAME`：上游 torch-hub 模型名称，例如 `jepa_wm_pusht`。

可选：

- `JEPA_DEVICE`：传递给 torch-hub 运行时的设备，例如 `cpu` 或 `cuda`。
- `JEPA_MODEL_PATH`：旧版脚手架变量。仅作为无值的诊断元数据保留，供此前配置了关闭脚手架的用户参考。它不会使提供方可运行；请改为设置 `JEPA_MODEL_NAME`。

## 运行时契约

适配器延迟加载：

```python
model, preprocessor = torch.hub.load(
    "facebookresearch/jepa-wms",
    "jepa_wm_pusht",
)
```

它首先委托给模型原生的打分方法（如 `score_actions(...)`）。若加载的模型未暴露打分方法，则使用与 [`jepa-wms`](./jepa-wms.md) 候选中相同的潜在距离回退方案。

必填的打分输入：

- `info["observation"]`：类张量对象或至少具有两个维度的矩形嵌套有限数值序列；
- `info["goal"]`：类张量对象或至少具有两个维度的矩形嵌套有限数值序列；
- `info["action_history"]`：可选的类张量对象或至少具有两个维度的矩形嵌套有限数值序列；
- `action_candidates`：形状为 `(batch, samples, horizon, action_dim)` 的类张量对象或矩形嵌套有限数值序列。

公开适配器恰好支持一个批次，并对每个候选样本返回一个分数。分数默认为代价：值越小越好。

## 从脚手架迁移

在此适配器之前，`jepa` 是一个由 `JEPA_MODEL_PATH` 控制的能力关闭保留位。该确定性代理路径不再是公开 `jepa` 提供方的一部分。需要旧版候选壳体的测试或宿主方实验应直接从 `worldforge.providers.jepa_wms` 构建 `JEPAWMSProvider`。

迁移清单：

- 将 `JEPA_MODEL_PATH=/path/to/old/scaffold` 替换为 `JEPA_MODEL_NAME=jepa_wm_pusht` 或其他已验证的上游 torch-hub 模型名称；
- 将检查点路径和任务资产保留在宿主方配置中，而非问题安全的诊断载荷中；
- 在专用 `jepa` 冒烟测试命令出现之前，使用 `worldforge-smoke-jepa-wms` 保留实时运行时实证。

## 测试

```bash
uv run pytest tests/test_jepa_provider.py tests/test_provider_catalog_docs.py
uv run python scripts/generate_provider_docs.py --check
uv run mkdocs build --strict
```

## 主要参考资料

- [facebookresearch/jepa-wms](https://github.com/facebookresearch/jepa-wms)
- [facebook/jepa-wms Hugging Face 模型仓库](https://huggingface.co/facebook/jepa-wms)

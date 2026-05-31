# 能力协议快速入门

能力协议是为已拥有本地函数、模型封装器或服务客户端的宿主应用提供的轻量注册路径。当单个进程内对象无需完整提供方包即可完成打分、选择、预测或嵌入时，请使用此路径。

当适配器需要目录注册、自定义健康检查、凭证处理、生成的提供方文档或多个由提供方持有的表面时，请使用 `BaseProvider` 子类。当宿主应用持有运行时且只需将一个窄能力插入 `WorldForge` 时，请使用能力协议。

可运行的小型演示位于 `examples/capability_protocols_mini.py`。

```bash
uv run python examples/capability_protocols_mini.py
```

该脚本注册三个普通 Python 对象：

- `LocalPredictor` 实现 `predict(...)` 并返回 `PredictionPayload`。
- `LocalPolicy` 实现 `select_actions(...)` 并返回包含候选动作计划的 `ActionPolicyResult`。
- `LocalCost` 实现 `score_actions(...)` 并返回 `ActionScoreResult`。

每个对象声明一个非空的 `name` 和可选的 `ProviderProfileSpec`。无需继承任何子类：

<!-- worldforge-snippet: skip-illustrative -->
```python
forge = WorldForge(auto_register_remote=False, discover_entry_points=False)
forge.register_predictor(LocalPredictor())
forge.register_policy(LocalPolicy())
forge.register_cost(LocalCost())
```

注册后，这些对象可以像提供方支撑的表面一样按名称解析。演示创建一个默认预测提供方为 `local-predictor` 的世界，然后请求 `World.plan(...)` 将策略提案与基于打分的排名组合在一起：

<!-- worldforge-snippet: skip-illustrative -->
```python
plan = world.plan(
    goal="keep the blue cube near the origin",
    policy_provider="local-policy",
    policy_info={"object_id": "cube-1"},
    score_provider="local-cost",
    score_info={"goal": "stay near origin"},
)
```

生成的规划是确定性 JSON，其元数据展示了组合路径：

<!-- worldforge-snippet: skip-illustrative -->
```json
{
  "metadata": {
    "planning_mode": "policy+score",
    "policy_provider": "local-policy",
    "score_provider": "local-cost"
  }
}
```

保持协议实现精简。在边界处验证调用方输入，为能力返回精确的 WorldForge 结果类型，并将可选运行时、凭证、检查点和遥测导出保持由宿主方持有。

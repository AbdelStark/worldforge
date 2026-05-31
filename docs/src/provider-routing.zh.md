# 提供方路由与回退

WorldForge 提供了一个类型化的路由辅助工具，用于优先尝试首选提供方，并在调用失败时按优先级列表依次尝试备选提供方。该辅助工具在每次尝试前验证能力兼容性，保留可观测能力包装器发出的底层提供方事件，并将完整的尝试历史返回给调用方。失败情况绝不会被静默掩盖。

## 适合使用回退的场景

- **可选提供方**：宿主在离线开发时注册了 mock 提供方，并在运行时存在时配置预制宿主提供方。路由优先选择运行时提供方，并在检出时该适配器缺失的情况下回退到 mock。
- **瞬时远程故障**：远程提供方返回了其自身重试策略无法消化的可重试状态码。路由记录该故障并尝试下一个提供方，从而避免偶发的网络抖动破坏批量评估。
- **跨宿主可移植性**：相同的工作流在具有不同提供方组合的机器上运行。确定性的首选 + 回退链使调用路径在各宿主间保持可预测。

## 不适合使用回退的场景

- **正确性敏感的契约**：下游流水线依赖于所选提供方的特定语义（特定的世界模型、特定的策略网络）。静默回退到其他提供方会在不通知调用方的情况下改变结果。此时应选定单一提供方，并让调用暴露其错误。
- **计费敏感的操作**：使用另一个付费提供方重试会成倍增加成本。请配置单一提供方并暴露其故障。
- **机器人控制循环**：确定性的提供方选择比容错更重要。控制循环中的回退会隐藏是哪个模型产生了动作；应让其响亮地失败，以便运维人员决定是否重新介入。
- **格式错误的提供方输出**：路由辅助工具不会掩盖契约验证错误。将模式无效数据传入可观测能力包装器的适配器会触发 ``ProviderError``；该链将此失败记录为普通的失败尝试，并尝试下一个提供方，但格式错误的输出永远不会到达调用方。

## 公开接口

`worldforge.provider_routing`（在顶层包中重新导出）：

| 符号 | 用途 |
| --- | --- |
| `ProviderRoutingPolicy` | 冻结策略：能力 + 首选提供方 + 回退列表 + 能力检查开关 + 操作标签 |
| `RoutingAttempt` | 链中的一个步骤：提供方、能力、状态，以及可选的原因 / 错误类型 / 脱敏消息 |
| `RoutingResult` | 结果：选定的提供方、成功标志、完整的尝试历史、返回值 |
| `ROUTING_ATTEMPT_STATUSES` | 枚举状态：`succeeded`、`failed`、`skipped-not-registered`、`skipped-incompatible` |
| `route_capability(policy, forge, *, invoke)` | 尝试整条链，返回第一次成功的结果 |

`route_capability` 是确定性的。提供方按 `(preferred, *fallbacks)` 的顺序依次尝试，链在第一次成功时停止。每个未注册或能力不兼容的提供方被记录为跳过的尝试，**不会**触发调用；只有已注册且能力兼容的提供方才会被传入 ``invoke``。``invoke`` 抛出的任何异常都会被捕获为 `failed` 尝试，记录异常类名和经过脱敏的 ``str(exc)``，然后链继续执行。

## 示例

<!-- worldforge-snippet: execute -->
```python
from worldforge import Action, ProviderRoutingPolicy, WorldForge, route_capability

forge = WorldForge()
# Forge 始终自动注册 `mock`。预制宿主提供方仅在必需环境存在时注册。

policy = ProviderRoutingPolicy(
    capability="predict",
    preferred="local-predictor",
    fallbacks=("mock",),
    operation="prediction-fallback",
)

result = route_capability(
    policy,
    forge,
    invoke=lambda name: forge.predict(
        world_state={"objects": {}},
        action=Action(type="noop", target="world"),
        provider=name,
    ),
)

if not result.succeeded:
    raise RuntimeError(
        "no provider in chain satisfied predict(): "
        + ", ".join(
            f"{a.provider}={a.status}" for a in result.attempts
        )
    )

print(f"chosen={result.chosen} via_chain={[a.provider for a in result.attempts]}")
prediction = result.value
```

当首选提供方在宿主上未配置时，尝试历史为其记录 `skipped-not-registered`，链继续执行到 ``mock``——不发起任何远程调用。

## 事件与溯源

`route_capability` **不会**自行发出 `ProviderEvent` 对象。由 `forge.predict(...)`、`forge.embed(...)`、打分或策略调用内部的可观测能力包装器产生的事件会原样保留，并流经附加到 forge 的 ``event_handler``。``RoutingResult.attempts`` 元组是这些单次调用事件的链级配套记录。

`attempts` 中的失败尝试携带：

- ``status="failed"``
- ``error_type``：异常类名（例如 ``"ProviderError"``、``"ProviderBudgetExceededError"``）
- ``error_message``：经过脱敏的 ``str(exc)``。适配器仍然有责任抛出已脱敏的提供方错误，但路由尝试是面向工件的记录，因此在序列化前会防御性地移除常见 bearer token、API key、secret 赋值以及签名 URL 查询参数形状。

## 验证门控

路由输入在构造时进行验证：

- ``capability`` 必须是 ``CAPABILITY_NAMES`` 之一
- ``preferred`` 必须是非空的提供方名称
- ``fallbacks`` 必须是非空提供方名称的序列
- 链（``preferred + fallbacks``）不得包含重复项
- ``require_capability`` 必须是 ``bool`` 类型
- ``operation`` 必须是非空字符串
- `RoutingResult` 的所有尝试必须与结果能力一致
- 成功结果必须包含一个最终的成功尝试、匹配的选定提供方以及返回值
- 失败结果不得携带选定提供方、陈旧返回值或成功尝试

每个违规都会触发 ``WorldForgeError``，使配置错误在策略构造时暴露，而不是在调度路径中。

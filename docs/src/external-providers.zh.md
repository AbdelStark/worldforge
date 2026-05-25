# 外部提供方包

外部适配器包无需修改 WorldForge 仓库即可注册 WorldForge 提供方。WorldForge 在构造时通过 ``worldforge.providers`` Python 入口点组来发现它们。

## 入口点声明

在您的包的 ``pyproject.toml`` 中添加一条条目：

```toml
[project.entry-points."worldforge.providers"]
my-policy = "my_pkg.adapters:make_my_policy_provider"
```

入口点的**名称**（``my-policy``）是 WorldForge 在 ``providers()``、``doctor()`` 及基准测试/评估报告中呈现的提供方名称。**值**（``my_pkg.adapters:make_my_policy_provider``）是一个完全限定的可调用对象，返回一个 :class:`~worldforge.providers.base.BaseProvider`。

## 工厂契约

被引用的可调用对象接受一个可选的关键字参数，并返回一个 `BaseProvider`：

<!-- worldforge-snippet: skip-illustrative -->
```python
from worldforge.providers import BaseProvider, ProviderProfileSpec
from worldforge import ProviderCapabilities


def make_my_policy_provider(*, event_handler=None) -> BaseProvider:
    return MyPolicyProvider(event_handler=event_handler)
```

三条规则：

1. 提供方的 ``name`` 属性必须与入口点名称一致。当两者不一致时，WorldForge 会在 ``ProviderCatalogEntry.create()`` 中触发 ``WorldForgeError``，从而防止用户可见输出中出现意外的名称冲突。
2. 工厂必须返回 ``BaseProvider`` 的子类。返回其他类型时，将在条目被调用时以类型化错误拒绝。
3. 提供方遵循与仓库内提供方相同的环境门控自动注册规则：``configured()`` 必须返回 ``True``，提供方才会被自动注册。宿主仍可通过 ``forge.register_provider(...)`` 显式注册未配置的提供方。

## 契约 CLI

在为外部适配器提交议题或 PR 之前，运行提供方契约 CLI：

```bash
uv run worldforge provider contract my-policy --format json
uv run worldforge provider contract --factory my_pkg.adapters:make_my_policy_provider --format markdown
```

该命令接受已注册的提供方名称或直接的 ``module:factory`` 路径。它输出包含提供方元数据、已通过检查、已跳过的宿主方检查、失败项、后续步骤和验证命令的安全可附加 JSON 或 Markdown 证据。

WorldForge 默认不调用非本地提供方的能力。已配置的远程、机器人或可选运行时提供方会将这些能力检查记录为已跳过，直到宿主在已准备好的机器上使用 ``--live`` 重新运行。当 score 或 policy 适配器需要提供方原生的夹具载荷时，使用 ``--score-info``、``--score-candidates`` 和 ``--policy-info``。

## 失败行为

发现过程不会导致宿主崩溃。每个无法被包装的入口点都会以类型化的原因记录下来：

| 原因 | 示例说明 |
| --- | --- |
| 模块导入失败（缺少可选依赖） | ``missing dependency: No module named 'torch'`` |
| 加载的值不可调用 | ``entry point did not resolve to a callable`` |
| 名称与仓库内提供方冲突 | ``duplicate name (in-repo provider already registered)`` |
| 两个入口点共享同一名称 | ``duplicate name (already discovered earlier in this group)`` |
| 加载器抛出任何其他异常 | ``load failed: <message>`` |
| 工厂在构造时抛出异常 | ``factory raised: <message>`` |

完整报告可通过 ``WorldForge.entry_point_discovery()`` 获取：

<!-- worldforge-snippet: execute -->
```python
from worldforge import WorldForge

forge = WorldForge()
report = forge.entry_point_discovery()
print(report.discovered_count, "external providers discovered")
for skip in report.skipped:
    print(f"skipped {skip.name}: {skip.reason}")
```

## 检出安全的包演示

当您希望在不发布或全局安装任何内容的情况下获得完整的包形状示例时，运行演示工作流：

```bash
uv run python scripts/demo_showcases.py run external-provider-package --workspace-dir .worldforge/demo-showcases --overwrite
```

它会在演示工作空间下写入一个临时包，包含 `pyproject.toml`、提供方工厂和包本地测试。保留的 `external-provider-discovery.json` 展示了成功的发现过程、显式禁用发现的行为、重复仓库内提供方名称的处理，以及缺少可选依赖的跳过原因。该输出可安全附加，但它仅是包形状证据；不代表 PyPI 发布、实时提供方调用或晋级证据。

## 禁用发现

有两种方式可关闭发现：

1. **构造函数标志**：``WorldForge(discover_entry_points=False)`` 完全跳过发现。
2. **环境变量**：将 ``WORLDFORGE_DISABLE_ENTRY_POINTS`` 设置为非空值，对进程中的所有 forge 产生相同效果。当第三方包因无关原因被安装时，托管环境使用此方式保持 CI 运行的确定性。

禁用发现后，``forge.entry_point_discovery().enabled`` 为 ``False``，且不会注册任何外部提供方。

## 稳定性

此接口**处于试验阶段**。入口点组名称和发现报告的形状在当前版本中是稳定的，但 ``EntryPointSkip.reason`` 字符串是供人类阅读的诊断信息，而非机器可解析的契约。请将其视为日志消息处理。

## 相关公开 API

| 符号 | 用途 |
| --- | --- |
| ``worldforge.ENTRY_POINT_GROUP`` | 入口点组名称（``worldforge.providers``）。 |
| ``worldforge.ENTRY_POINT_DISABLE_ENV_VAR`` | 禁用环境变量的名称。 |
| ``worldforge.discover_entry_point_providers`` | 在不实例化 forge 的情况下运行发现。 |
| ``worldforge.EntryPointDiscoveryReport`` | 包含运行摘要的冻结数据类。 |
| ``worldforge.EntryPointSkip`` | 单条跳过记录（名称、值、原因）。 |
| ``WorldForge.entry_point_discovery()`` | 在构造时捕获的报告。 |

## 验证

```bash
uv run pytest tests/test_provider_entry_points.py tests/test_provider_catalog.py
uv run pytest tests/test_provider_contracts.py
uv run mkdocs build --strict
```

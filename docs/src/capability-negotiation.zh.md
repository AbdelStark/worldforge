# 能力协商报告

WorldForge 可以在任何工作流运行之前报告——当前已注册和已知的提供方能否满足某组能力要求。该报告在以下场景中非常有用：排查 CI 失败、在运行评估套件前选择宿主，或选择已同时准备好策略和打分提供方的基准测试预设。

## 工作流

WorldForge 开箱即支持以下工作流形态：

| 工作流 | 所需能力 |
| --- | --- |
| `predict-only` | predict |
| `score-only` | score |
| `policy-only` | policy |
| `embed-only` | embed |
| `policy-plus-score` | policy, score |
| `evaluation-physics` | predict |
| `evaluation-planning` | predict |

`evaluation-*` 工作流与内置评估套件所需的能力一一对应。宿主可通过 `WorldForge.register_provider()` 注册额外的提供方，协商报告会自动将其纳入。

## CLI

```bash
uv run worldforge negotiate --list
uv run worldforge negotiate --workflow policy-plus-score
uv run worldforge negotiate --workflow score-only --format json
uv run worldforge negotiate                                # 一次性检查所有工作流
```

当至少一个工作流处于 `BLOCKED` 状态时，CLI 以非零退出码退出，可用作发布证据运行前的 CI 守卫。输出格式：

- **Markdown**（默认）：一张按工作流显示状态的表格，列出每个候选提供方的注册情况、能力、配置、健康状态、就绪状态，以及当前无法服务该能力时的有类型原因，末尾附"推荐操作"。
- **JSON**：稳定的机器可读格式，适合附加到运行清单。

如需运行一个保留了就绪、配置缺失、依赖缺失、不支持及未注册示例的 checkout 安全预检演示，请执行：

```bash
uv run python scripts/demo_showcases.py run capability-negotiation-preflight --workspace-dir .worldforge/demo-showcases --overwrite
```

该工作流在所选演示工作区下写入 JSON 和 Markdown 协商报告，并记录推荐的首要命令，无需安装依赖、配置凭证或执行回退工作流。

## Python

```python
from worldforge import (
    list_workflow_names,
    negotiate_capabilities,
    WorldForge,
)

forge = WorldForge()
report = negotiate_capabilities(["policy-plus-score"], forge=forge)
for negotiation in report.workflows:
    print(negotiation.workflow.name, "ready" if negotiation.ready else "blocked")
    for action in negotiation.recommended_actions:
        print("  →", action)
```

公开表面（[公开 API 稳定性](./api-stability.md) 下的临时版本）：

| 符号 | 用途 |
| --- | --- |
| `WorkflowSpec` | 描述一个命名工作流的冻结数据类。 |
| `WorkflowNegotiation` | 针对当前 forge 协商一个工作流的结果。 |
| `CapabilityRequirement` | 包含所有候选提供方的一个能力槽位。 |
| `CapabilityProviderStatus` | 单个提供方针对一个能力的就绪状态。 |
| `CapabilityNegotiationReport` | 覆盖一个或多个工作流的顶层报告。 |
| `list_workflows`, `list_workflow_names`, `get_workflow` | 注册表辅助函数。 |
| `negotiate_capabilities` | 执行能力协商。 |
| `CAPABILITY_NEGOTIATION_SCHEMA_VERSION` | 当前为 `1`。 |

## 就绪状态

| 状态 | 含义 |
| --- | --- |
| `ready` | 提供方已注册、已配置、健康，且支持该能力。 |
| `missing-config` | 提供方支持该能力，但其运行时配置缺少必需的环境变量（例如 `LEWORLDMODEL_POLICY`）。 |
| `missing-dependency` | 提供方已注册且已配置，但健康检查不健康（例如某个可选运行时不可达）。 |
| `unsupported` | 提供方在目录中，但不公布该能力。 |
| `not-registered` | 提供方在目录中且可满足该能力，但当前未在此 forge 上注册。 |

## 推荐操作

每个被阻塞的能力会产生一条具体的推荐信息。示例：

- `Configure provider 'leworldmodel' to serve capability 'score': provider profile 'leworldmodel' is not configured: missing LEWORLDMODEL_POLICY.`
- `Register or configure a provider that supports capability 'score'.`

这些是人类可读的诊断信息，不是机器可解析的命令字符串。实际配置请参考对应的提供方文档页面。

## 验证

```bash
uv run pytest tests/test_capability_negotiation.py tests/test_cli_doctor.py tests/test_provider_profiles.py tests/test_runtime_profiles.py
uv run mkdocs build --strict
```

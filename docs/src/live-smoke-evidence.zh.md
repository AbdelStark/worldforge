# 冒烟测试实时证据注册表

Issue: [#144](https://github.com/AbdelStark/worldforge/issues/144)。

冒烟测试实时证据注册表是可选提供方冒烟测试的可发布索引。它记录哪些提供方拥有最近经过清理的清单、哪些被跳过以及跳过原因。它不是基准测试，也不主张模型质量、物理保真度或机器人安全性。

注册表 JSON：[`live-smoke-evidence.json`](./live-smoke-evidence.json)。

## 条目契约

每条记录包含：

| 字段 | 契约 |
| --- | --- |
| `provider` | 提供方配置文件或候选名称。 |
| `capability` | 一项 WorldForge 能力，例如 `predict`、`score` 或 `policy`。 |
| `command` | 在预备宿主机上运行的冒烟测试命令。不得内联密钥。 |
| `runtime_manifest` | 运行时清单 ID，例如 `leworldmodel:schema-1`；若不存在则为 `null`。 |
| `date` | 注册表决策日期，格式为 `YYYY-MM-DD`。 |
| `version` | 该注册表行所用的 WorldForge 包版本。 |
| `status` | `passed`、`failed`、`not_run`、`skipped_missing_runtime`、`skipped_missing_credentials` 或 `skipped_not_configured`。 |
| `artifact_path` | 通过或失败证据对应的经过清理的 `run_manifest.json` 或工件路径；其他情况为 `null`。 |
| `skip_reason` | 跳过或未运行条目必填。 |
| `known_limitations` | 明确注意事项和宿主方责任的列表。 |

在测试或发布工具中验证注册表：

```python
from worldforge import validate_live_smoke_registry

registry = validate_live_smoke_registry(payload)
```

验证器会拒绝以下内容：签名 URL、URL 查询字符串、片段、明显的密钥材料、类似密钥的元数据键、重复的提供方/能力行、缺失跳过原因，以及通过或失败证据缺失工件路径。

## 状态语义

- `passed`：预备宿主机运行了该命令并保留了经过清理的清单。
- `failed`：预备宿主机运行了该命令并保留了经过清理的失败清单。
- `not_run`：命令存在，但本次发布未尝试或链接任何运行。
- `skipped_missing_runtime`：宿主机缺少冒烟测试所需的可选运行时、检查点、端点、设备或服务器。
- `skipped_missing_credentials`：宿主机缺少所需的提供方凭据。
- `skipped_not_configured`：该提供方在本次发布中被有意设置为不配置。

跳过行也是证据。它们防止发布说明和问题报告静默遗漏当前宿主机上无法运行的可选提供方。

## 将清单附加到问题报告

当预备宿主机冒烟测试通过时，附上经过清理的 `run_manifest.json` 以及它所链接的任何 checkout 安全的小型摘要。不得附加：

- 原始凭据或环境变量转储；
- 签名工件 URL 或带查询字符串的 URL；
- 原始张量、媒体二进制文件、检查点、模型权重或机器人控制器日志；
- 宿主本地绝对路径，除非问题明确记录仅本地证据；
- 将冒烟测试声称为基准测试或物理保真度证明的主张。

若冒烟测试被跳过，附上注册表行，或粘贴提供方名称、状态、命令、跳过原因和已知限制。这足以说明阻塞因素是缺少凭据、缺少可选运行时，还是有意的发布决策。

## 发布证据

`scripts/generate_release_evidence.py` 默认包含注册表：

```bash
uv run python scripts/generate_release_evidence.py \
  --live-smoke-registry docs/src/live-smoke-evidence.json \
  --output .worldforge/release-evidence/release-evidence.md
```

发布证据仍可链接单独的 `--run-manifest` 文件。注册表是汇总展示面；运行清单是每次运行的证据。

# 运行工件索引

`worldforge runs index` 以只读方式遍历 `<workspace-dir>/runs/`，并输出每个保存的运行工作空间的脱敏摘要。对于拥有大量保存运行记录的宿主来说，该索引是 `worldforge runs list` 的补充工具：过滤器可按提供方、能力、状态、日期范围或安全工件类型缩小视图范围，三种输出格式（JSON、Markdown、CSV）便于将证据附加到 Issue、粘贴到发布说明或通过管道输入电子表格。

## 使用场景

- 您拥有数十甚至数百个保存的运行工作空间，需要找出匹配特定提供方、能力或状态的那些。
- 您希望生成一个可安全附加的单一工件，以摘要形式呈现某个发布窗口内的情况——用于 PR 正文的 Markdown 表格、用于分类电子表格的 CSV，或用于脚本化后处理的 JSON。
- 您希望在运行 `worldforge runs cleanup` 之前发现过时或损坏的运行目录。

## 不适用场景

- 您只有一两个保存的运行记录——`worldforge runs list` 更简便。
- 您需要的是单次运行的内容，而非跨运行的摘要——请改用 `worldforge runs bundle <run-id>`。
- 您需要长期运行的守护进程、多宿主索引或共享数据库。WorldForge 有意不提供这些功能；索引器在每次调用时重新遍历文件系统，从不持久化自身状态。

## 快速参考

```bash
# 默认将 JSON 输出到标准输出。
uv run worldforge runs index --workspace-dir .worldforge

# 用于 Issue 正文的 Markdown 表格。
uv run worldforge runs index --workspace-dir .worldforge --format markdown

# 用于分类电子表格的 CSV，写入文件。
uv run worldforge runs index --workspace-dir .worldforge \
    --format csv --output review/runs.csv

# 筛选过去一周内失败的 Cosmos-Policy 运行。
uv run worldforge runs index --workspace-dir .worldforge \
    --provider cosmos-policy --status failed --created-from 2026-04-29
```

所有过滤器均为可选，并以 AND 语义组合。提供方匹配采用子字符串加不区分大小写的方式；能力、状态和工件类型匹配则为精确匹配。

## 输出结构

所有格式包含相同的字段。JSON 信封如下：

```json
{
  "schema_version": 1,
  "workspace_dir": ".worldforge",
  "generated_at": "2026-05-06T12:00:00Z",
  "filter_applied": {"provider": null, "capability": null, "status": null,
                      "created_from": null, "created_to": null,
                      "artifact_type": null},
  "entry_count": 7,
  "issue_count": 1,
  "entries": [/* RunHistoryRecord 行 */],
  "issues": [/* RunIndexIssue 行 */]
}
```

Markdown 在标头中包含 `workspace`、`generated_at`、`schema_version` 及当前过滤条件，随后是条目表和问题部分。CSV 每条条目输出一行，列名为 `run_id, kind, status, provider, capability, created_at, artifact_count, safe_artifact_types, event_count, failure_summary, path`。

## 过时或损坏工作空间的问题行

遍历器在遇到损坏的运行目录时不会中止，而是将每个问题记录到 `issues` 列表中，并附上以下类型化原因之一：

| 原因 | 含义 |
| --- | --- |
| `manifest-missing` | 运行目录中没有 `run_manifest.json` |
| `manifest-unreadable` | 读取清单时发生操作系统错误（权限问题、损坏的符号链接） |
| `manifest-invalid-json` | 清单文件存在但不是有效的 JSON |
| `manifest-not-object` | 清单可解析但不是 JSON 对象 |

每个问题携带一个简短的 `detail` 字符串供排查。问题记录中不包含原始清单内容，仅包含目录路径和机器可读的原因。

## 保留策略与清理交互

索引器是只读的，不删除或重写任何内容。两个配套命令可用于回收磁盘空间：

- `worldforge runs cleanup --workspace-dir <dir> --keep N` — 删除超过最新 `--keep` 个数量的最旧工作空间，不考虑时间。快速批量清理。
- `worldforge runs prune --workspace-dir <dir>` — 应用类型化的保留策略（`--max-age-days`、`--keep-latest`、可重复的 `--family <kind>`），默认启用显式试运行。`--apply` 才会实际删除。当您希望保留每种类型的近期运行，但有选择地清理较旧的 `eval` 或 `benchmark` 目录时，请使用此命令。24 小时安全窗口会阻止删除非常新的运行，除非您传入 `--max-age-days=0`。

两种推荐工作流：

1. **清理前审计。** 运行 `runs index --format markdown` 并将表格附加到清理 Issue 中。获得批准后，运行 `runs prune --apply --max-age-days 30 --keep-latest 10`（或 `runs cleanup`），然后重新运行 `runs index` 以确认仅保留了应保留的运行。
2. **过时目录分类。** 如果 `issues` 列表非空，请在清理之前逐一调查每个 `run_dir`。`runs cleanup` 和 `runs prune` 仅对 `<workspace>/runs/` 下的工作空间进行操作；没有清单的损坏目录可能需要手动删除。

`runs prune` 接受 `--retention-profile <path>`，指向一个非密钥的配置文件，该文件声明了一个 `runs_retention` 块（`max_age_days`、`keep_latest`、`families`）。以任何 argparse 形式传入的 CLI 标志（`--max-age-days 7` 或 `--max-age-days=7`）仍然会覆盖配置文件的值。

`keep_latest` **的作用范围限定于 family 过滤器**：当设置了 `--family eval` 时，策略保留匹配 `kind=eval` 的最新 `keep_latest` 个运行，而非所有类型中最新的 `keep_latest` 个运行。这避免了更新的非匹配运行静默占用为过滤 family 保留的保留槽位的意外情况。没有 `--family` 标志时，`keep_latest` 是全局的。

`runs prune` 仅删除解析到 `<workspace>/runs/` 根目录下的路径（指向该目录树外部的符号链接会被路径检查捕获，而不会被追踪删除）。`--apply` 期间 `shutil.rmtree` 的失败会被包装为 `WorldForgeError`，以便 CLI 调用方看到稳定的错误信封而非回溯信息。

## 公开 Python 接口

无需通过 CLI 即可获取相同的数据：

```python
from pathlib import Path
from worldforge.harness.run_history import RunHistoryFilter
from worldforge.harness.run_index import build_run_index

index = build_run_index(
    Path(".worldforge"),
    filters=RunHistoryFilter.from_strings(provider="cosmos-policy", status="failed"),
)
print(index.to_markdown())
```

`build_run_index()` 是只读的、确定性的，并且能容忍缺失或格式错误的运行目录——它不会因损坏的工作空间而引发异常。

## 验证

索引器不会生成包含原始提供方输出的可安全附加工件。只有经过脱敏处理的清单字段、安全工件后缀元数据和失败摘要才会进入索引。需要原始工件的宿主仍应使用 `worldforge runs bundle`（脱敏处理 + SHA-256 摘要）或直接复制运行目录。

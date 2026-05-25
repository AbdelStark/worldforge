# 世界状态差异与补丁

WorldForge 可将两个持久化或导出的世界快照对比生成带结构版本的 JSON 原生差异，并将该差异提升为可干净应用于基准快照的补丁。该工件位于 `worldforge.world_diff`，并通过 CLI 的 `worldforge world diff` 命令对外暴露。

## 适用场景

- 一次运行保留了世界快照，而后续测试产生了不同的快照——向操作人员展示结构化差异。
- 两台宿主机运行了相同场景，却产生了细微不同的世界——将差异附加到问题报告中。
- 将预期的世界转换记录为补丁，并在测试中断言 `apply_patch(base, patch) == expected`。

## 不适用场景

- 跨多个写入者的并发编辑。补丁是针对单一基准的顺序应用——不存在三方合并或冲突解决层，此为设计上的明确边界。
- 静默应用格式错误的补丁。每次 `apply_patch` 操作都会通过 `SceneObject`、`Position` 和 `BBox` 对结果对象进行验证，因此路径遍历形式的 ID、不一致的包围框或格式错误的姿态载荷会抛出 `WorldStateError`，而不是产生损坏的状态。

## CLI

两种模式：持久化世界 ID（默认）或显式 JSON 路径。

```bash
# 对比默认状态目录中的两个持久化世界。
uv run worldforge world diff alpha-id beta-id --format markdown

# 对比两个导出的 JSON 文件（例如通过 `worldforge world export` 捕获的文件）。
uv run worldforge world diff a.json b.json \
    --source-path --target-path --format json > diff.json
```

当 `--source-path` 和 `--target-path` 只设置了其中一个时，CLI 会以非零状态退出；这两个标志必须同时使用。

## 差异载荷

<!-- worldforge-snippet: skip-illustrative -->
```json
{
  "schema_version": 1,
  "source_label": "alpha-id",
  "target_label": "beta-id",
  "field_changes": [
    {"field": "step", "before": 0, "after": 7}
  ],
  "object_changes": [
    {"kind": "added", "object_id": "obj_mug_1", "before": null,
     "after": {"id": "obj_mug_1", "name": "mug", "pose": {...}, "bbox": {...}}}
  ],
  "history_summary": {"source": 1, "target": 7}
}
```

`field_changes` 涵盖顶层世界字段（`name`、`provider`、`description`、`step`、`metadata`）。`object_changes` 涵盖场景对象的添加/删除/更新，并附带完整的前后载荷——消费方无需重新读取源文件即可获得足够信息来渲染并排视图。

## Python 接口

<!-- worldforge-snippet: skip-illustrative -->
```python
from pathlib import Path
from worldforge import (
    diff_worlds,
    diff_worlds_from_paths,
    WorldPatch,
    apply_patch,
)

# 对比两个 World 实例或 JSON 字典。
diff = diff_worlds(world_a.to_dict(), world_b.to_dict())
print(diff.to_markdown())

# 或对比两个磁盘上的世界文件（持久化或导出的）。
diff = diff_worlds_from_paths(Path("a.json"), Path("b.json"))

# 提升为补丁并应用到基准快照。
patch = WorldPatch.from_diff(diff)
new_state = apply_patch(world_a.to_dict(), patch)
```

差异是只读的——两个输入均不会被修改。`apply_patch` 返回一个新字典，原始对象保持不变。

## 夹具与差异的区别

`tests/fixtures/providers/` 下的提供方夹具用于捕获提供方的输入和输出，以进行适配器契约测试。世界差异捕获的是*世界快照*的变化——它们存在于用户工作区（或问题附件）中，而非仓库内，也不属于任何提供方契约的一部分。差异是调试工件，而非规格说明。

## 验证保证

- `WorldDiff.schema_version` 为 `1`，结构变更时版本号将递增。
- `WorldFieldChange.field` 被限制为一个有类型的集合（`WORLD_FIELD_NAMES`）；未知字段在构造时会抛出 `WorldForgeError`。
- `ObjectChange.kind` 被限制为 `added | removed | updated`。
- 若 `ObjectChange.object_id` 为空、包含 `/` 或 `\`，或等于 `.` / `..`，则会被拒绝——这与 WorldForge 对持久化世界 ID 所应用的路径遍历规则一致。
- `apply_patch` 会拒绝以下情况：路径遍历形式的对象 ID、不一致的包围框（最小值大于最大值）、格式错误的姿态载荷、尝试添加已存在的 ID、尝试删除或更新不存在的 ID，以及非整数或负数的 `step` 值。

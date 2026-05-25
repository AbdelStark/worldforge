# 场景定义格式

WorldForge 内置了一种 JSON 原生场景格式及对应的运行器，可驱动单个 `WorldForge` 实例按照声明式配方执行：指定一个提供方、一个初始场景、一个有序动作序列，以及一组预期工件。场景让团队能够将可复现的世界配置记录在单个可安全检出的文件中，而无需将 Python 辅助代码分散于示例和临时测试夹具中。

## 适用场景

- **上手指引**：用一条 `worldforge scenario run examples/scenarios/spawn-and-move.json` 命令替代专门编写的 Python 代码。
- **回归捕获**：当某个可安全检出的测试能复现一个缺陷时，将其转化为场景格式，使任何贡献者无需导入内部模块即可重新运行。
- **文档说明**：`expected_artifacts` 字段同时充当预期结果的人类可读说明。

## 场景与提供方夹具的区别

提供方夹具位于 `tests/fixtures/providers/` 目录下，用于隔离测试适配器契约——它们为 `assert_provider_contract()` 捕获提供方的输入/输出对。场景则通过公开 API 调用（`create_world`、`add_object`、`predict`）驱动完整的 `WorldForge` 实例，是*端到端行为的配方*，而非适配器级别的测试数据。场景可引用任何已注册的提供方；夹具的范围限定于单个适配器。

## 场景示例库

`examples/scenarios/` 目录下的可安全检出示例库为贡献者提供了本地世界及场景结果工件的小型起点：

| 场景 | 意图 | 预期工件 | 首要排查步骤 |
| --- | --- | --- | --- |
| `cube-on-table.json` | 成功的世界配置 | 包含一个对象和两个 mock 步骤的通过 JSON 结果 | 检查初始方块位姿及 mock 提供方配置 |
| `spawn-and-move.json` | 生成加预测工作流 | 包含两个对象和两个步骤的通过结果 | 检查 `spawn_object` 边界框及后续预测步骤 |
| `expected-failure-object-count.json` | 故意失败的预期 | `scenario run` 返回非零结果，预期行为 `passed: false` | 在修改场景之前确认不匹配是预期行为 |
| `invalid-action-missing-target.json` | 无效动作边界 | `scenario validate` 通过，`scenario run` 因缺少 `z` 而失败 | 检查 `actions[0].parameters` 中缺少的坐标 |
| `evaluation-readiness.json` | 面向评估的配置 | 包含两个静态对象且 `step=0` 的通过结果 | 在修改评估代码之前检查初始世界对象载荷 |
| `report-export-basic.json` | 报告/导出示例 | 适合作为 `--output` 附件的通过 JSON 或 Markdown 结果 | 在检查世界导出之前比较场景结果 JSON |
| `inheritance/base.json`、`child-a.json`、`child-b.json` | 场景继承（`extends`） | 基础场景可独立通过；子场景继承世界配置并覆盖动作/预期 | 先运行基础场景以确认共享配置，再调试子场景 |

通过与任何本地场景相同的 CLI 接口运行示例库：

```bash
uv run worldforge scenario validate examples/scenarios/report-export-basic.json
uv run worldforge scenario run examples/scenarios/report-export-basic.json \
    --state-dir .worldforge/scenario-gallery/report-export --format markdown \
    --output .worldforge/scenario-gallery/report-export.md
```

故意失败和无效的示例是有意为之的。它们通过 `metadata.expected_failure` 或 `metadata.expected_cli_error` 进行标记，以便测试能够验证失败模式，而无需削弱正常的 CLI 契约。

## 结构定义（版本 2）

最小场景结构与版本 1 保持不变；版本号提升仅新增了可选的顶层字段 `extends`，详见[场景继承](#场景继承-extends)部分。声明 `schema_version: 1` 的文件可继续正常校验，但不能使用 `extends`。


<!-- worldforge-snippet: parse -->
```json
{
  "schema_version": 1,
  "id": "spawn-and-move",
  "name": "Spawn a mug and predict a move",
  "description": "Start with one cube, spawn a mug, then run a predict step.",
  "provider": "mock",
  "world": {
    "name": "spawn-and-move-world",
    "objects": [
      {
        "name": "cube",
        "position": {"x": 0.0, "y": 0.5, "z": 0.0},
        "bbox": {
          "min": {"x": -0.05, "y": 0.45, "z": -0.05},
          "max": {"x":  0.05, "y": 0.55, "z":  0.05}
        }
      }
    ]
  },
  "actions": [
    {
      "kind": "spawn_object",
      "parameters": {
        "name": "mug",
        "x": 0.25, "y": 0.8, "z": 0.0,
        "bbox": {
          "min": {"x": 0.20, "y": 0.75, "z": -0.05},
          "max": {"x": 0.30, "y": 0.85, "z":  0.05}
        }
      }
    },
    {
      "kind": "predict",
      "parameters": {"x": 0.4, "y": 0.5, "z": 0.0, "steps": 1}
    }
  ],
  "expected_artifacts": [
    {"label": "object_count", "kind": "object_count", "value": 2},
    {"label": "step_count",   "kind": "step",          "value": 2}
  ],
  "metadata": {}
}
```

### 动作类型

| `kind` | 效果 | 必填参数 |
| --- | --- | --- |
| `predict` | 调用 `World.predict(Action.move_to(x,y,z), steps)` | `x`、`y`、`z`；可选 `speed`、`steps`、`provider` |
| `move_to` | 与 `predict` 相同，但接受 `object_id` 用于定向移动 | `x`、`y`、`z`；可选 `object_id`、`speed`、`steps` |
| `spawn_object` | 调用 `World.predict(Action.spawn_object(...))` | `name`、`x`、`y`、`z`；可选 `bbox` |

每种类型最终都会以类型化的 `Action` 调用 `World.predict`；场景中声明的提供方为默认值，但每个步骤可通过 `parameters.provider` 覆盖。

### 预期工件类型

| `kind` | 说明 |
| --- | --- |
| `object_count` | 运行结束后比较 `World.object_count` |
| `step` | 运行结束后比较 `World.step` |
| `object_position` | 查找 `value.object_id` 并在 `value.tolerance` 范围内比较位置 |

预期未满足不会抛出异常；结果中会以 `passed: false` 行的形式显示，由调用方（CI 门控、人工审阅者、脚本检查）决定是否将运行判定为失败。

## 场景继承（`extends`）

结构版本 2 新增了一个可选的顶层字段 `extends`，子场景可借此复用基础文件，无需复制其完整配置。基础场景本身仍可作为独立场景单独运行。

<!-- worldforge-snippet: skip-illustrative -->
```json
{
  "schema_version": 2,
  "extends": "./base.json",
  "id": "lab-setup-child-a",
  "name": "Lab setup child A",
  "actions": [
    {"kind": "predict", "parameters": {"x": 0.25, "y": 0.5, "z": 0.0, "steps": 2}}
  ],
  "expected_artifacts": [
    {"label": "object_count", "kind": "object_count", "value": 1},
    {"label": "step_count", "kind": "step", "value": 2}
  ]
}
```

### 合并语义

- **顶层替换，无深度合并。** 若子场景声明了某个顶层键（例如 `world`、`actions`、`expected_artifacts`、`metadata`），子场景的值将整体替换父场景的值。若仅需调整 `world.objects` 中的某个对象，子场景须复制完整的 `world` 块。
- **子场景优先冲突。** 两个文件中均存在的相同键以子场景的值为准；子场景未声明的键保留父场景的值。
- **仅支持单一父场景。** `extends` 是字符串，而非列表。
- **路径相对于子场景文件解析。** 绝对路径会被拒绝，`extends` 值中包含任何 `..` 路径段时，路径在解析前即会被拒绝，以防止子场景逃离其所在的场景目录。若需在同级文件间共享基础场景，请将父场景整理至共享子目录中。
- **继承在矩阵展开之前执行。** 子场景可引入 `matrix` 块、覆盖继承而来的矩阵，或原样继承父场景的矩阵。

### 校验规则

| 规则 | 行为 |
| --- | --- |
| 父文件不存在 | `WorldForgeError`，并附有错误引用路径 |
| `extends` 为绝对路径 | `WorldForgeError`，必须使用相对路径 |
| `extends` 路径含任意 `..` 段 | `WorldForgeError`——同级文件必须在不遍历父目录的情况下可达 |
| `extends` 为空、键值为 null 或非字符串 | `WorldForgeError`（`extends: null` 视为格式错误，而非缺省） |
| `schema_version` 为 `bool`、`float` 或任何非 `int` 类型 | `WorldForgeError`（`True`、`2.0`、`"2"` 均被拒绝） |
| `schema_version: 1` 的文件中使用了 `extends` | `WorldForgeError`（需要结构版本 2） |
| `extends` 链中存在循环 | `WorldForgeError`，并列出错误链 |
| 链深度超过 `SCENARIO_MAX_EXTENDS_DEPTH` | `WorldForgeError` |
| 向 `parse_scenario`（字典，无路径）传入 `extends` | `WorldForgeError`——请使用 `load_scenario(<path>)` |

`examples/scenarios/inheritance/` 目录下的示例库提供了一个基础场景和两个子场景，用于端到端验证上述规则：

```bash
uv run worldforge scenario run examples/scenarios/inheritance/base.json
uv run worldforge scenario run examples/scenarios/inheritance/child-a.json
uv run worldforge scenario run examples/scenarios/inheritance/child-b.json
```

## 场景参数矩阵

当同一场景需要在小范围内扫描运行时，可添加顶层 `matrix` 对象。`matrix.parameters` 的值为 JSON 原生数组，笛卡尔积必须在 `max_cases` 之内，且占位符必须占据完整的 JSON 值（如 `"${target_x}"`），为整值占位符。不支持 `"cube-${target_x}"` 这样的部分插值，且不提供表达式语言。

<!-- worldforge-snippet: parse -->
```json
{
  "schema_version": 1,
  "id": "target-sweep",
  "name": "Target sweep",
  "description": "Run the same checkout-safe scenario against two target positions.",
  "provider": "${provider_name}",
  "world": {
    "name": "target-sweep-world",
    "objects": [
      {
        "name": "cube",
        "position": {"x": "${object_x}", "y": 0.5, "z": 0.0},
        "bbox": {
          "min": {"x": -0.05, "y": 0.45, "z": -0.05},
          "max": {"x":  0.05, "y": 0.55, "z":  0.05}
        }
      }
    ]
  },
  "actions": [
    {
      "kind": "predict",
      "parameters": {
        "provider": "${provider_name}",
        "x": "${target_x}",
        "y": 0.5,
        "z": 0.0,
        "steps": 2
      }
    }
  ],
  "expected_artifacts": [
    {"label": "object_count", "kind": "object_count", "value": 1},
    {"label": "step_count", "kind": "step", "value": "${expected_step}"}
  ],
  "matrix": {
    "max_cases": 4,
    "parameters": {
      "expected_step": [2],
      "object_x": [0.0],
      "provider_name": ["mock"],
      "target_x": [0.25, 0.5]
    }
  },
  "metadata": {}
}
```

支持占位符的位置经过了有意限制：

| 位置 | 用途 |
| --- | --- |
| `provider` | 选择场景提供方名称 |
| `actions[*].parameters.provider` | 覆盖步骤级提供方名称 |
| `world.objects[*].position` 及 `.position.x/y/z` | 扫描对象位置 |
| `actions[*].parameters.x/y/z` | 扫描动作目标 |
| `expected_artifacts[*].value` 及其后代 | 扫描预期工件值 |

`worldforge scenario validate <path>` 在执行前展开并校验每个用例。`worldforge scenario run <path>` 在已配置的 `--state-dir` 中为每个用例创建一个具体场景，然后返回聚合字段 `case_count`、`passed_case_count`、`failed_case_count` 和 `failed_cases`。任何用例失败时，命令退出码为非零。

## CLI

```bash
# 校验场景而不运行。
uv run worldforge scenario validate examples/scenarios/cube-on-table.json

# 端到端运行场景。
uv run worldforge scenario run examples/scenarios/spawn-and-move.json \
    --state-dir .worldforge/worlds --format json
```

若任何预期未满足，`worldforge scenario run` 以非零退出码退出，因此该命令适合作为 CI 门控。使用 `--output PATH` 可将结果写入文件而非标准输出。

## Python 接口

<!-- worldforge-snippet: skip-illustrative -->
```python
from pathlib import Path
from worldforge import WorldForge, load_scenario, run_scenario

forge = WorldForge()
scenario = load_scenario(Path("examples/scenarios/cube-on-table.json"))
result = run_scenario(forge, scenario)
if not result.all_expectations_passed():
    raise RuntimeError(
        "scenario expectations failed: "
        + ", ".join(
            f"{c.label}={c.observed!r}≠{c.expected!r}"
            for c in result.expectation_checks
            if not c.passed
        )
    )
```

## 超出范围

- **不支持任意 Python 执行。** 场景文件仅为 JSON——不能导入代码、求值表达式或引用其他文件。每种动作类型都是类型化的 `Action` 构造器；新增类型需要通过带测试的代码变更来实现。
- **不包含模拟器专属结构定义。** 该格式与提供方无关。具身形态专属或模拟器专属的配置不属于场景的一部分；实时提供方必须从各自的宿主环境中读取这些设置。
- **不允许静默失败。** 无效场景在解析时通过 `WorldForgeError` 大声报错，并附有错误文件和字段的路径。失败的预期在 `ScenarioResult.expectation_checks` 中以明确的前后值对形式呈现。

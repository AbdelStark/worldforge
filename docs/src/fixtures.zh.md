# 能力夹具语料库

WorldForge 附带一个小型的、已打包的规范输入夹具语料库，涵盖每种提供方能力——`predict`、`embed`、`score` 和 `policy`。合规测试、评估套件及提供方作者可复用该语料库，而无需在每个测试文件中手动构造载荷。

语料库位于 `src/worldforge/testing/fixtures/`，并通过 `worldforge.testing` 的公开测试 API 暴露（因此它是 wheel 包的一部分，无需在检出时进行路径发现）。

## 基数

语料库为每种能力提供：

- 恰好一个 `valid_baseline.json`，代表最小但切实可行的公开输入；
- 至少两个 `invalid_<reason>.json` 夹具，分别命名不同的边界失败情况。

这保证了四个有效基线和至少八个无效边界夹具，使每个合规辅助工具无需重新推导载荷即可被执行。

## 信封格式

每个夹具文件是一个 JSON 对象，包含 `schema_version: 1` 及以下键：

| 字段 | 描述 |
| --- | --- |
| `id` | `<capability>.<name>`，与文件路径匹配（如 `predict.valid_baseline`）。 |
| `capability` | `predict`、`embed`、`score`、`policy` 之一。 |
| `data_class` | `synthetic`（手工编写）、`captured`（从真实提供方/运行记录）或 `host-supplied`（由集成方在运行时提供；文件附带示例）。 |
| `expected` | `valid` 或 `invalid`。 |
| `expected_error_pattern` | 针对 `WorldForgeError` 抛出的错误消息的正则提示。无效夹具必填，有效夹具须为 `null`。 |
| `description` | 说明该夹具测试内容的一句话注释。 |
| `payload` | 特定于能力的字典，其键直接映射到对应 `assert_*_conformance()` 的关键字参数。 |

完整的贡献者章程——包括所有权、何时添加新夹具以及不应放入语料库的内容——位于
[`src/worldforge/testing/fixtures/README.md`](https://github.com/AbdelStark/worldforge/blob/main/src/worldforge/testing/fixtures/README.md)。

## 加载夹具

```python
from worldforge.testing import (
    iter_capability_fixtures,
    load_capability_fixture,
)

baseline = load_capability_fixture("score", "valid_baseline")
score_info = baseline.payload["info"]
candidates = baseline.payload["action_candidates"]

for fixture in iter_capability_fixtures("policy"):
    print(fixture.id, fixture.expected, fixture.description)
```

可从 `worldforge.testing` 重新导出的辅助工具：

| 符号 | 用途 |
| --- | --- |
| `CAPABILITY_FIXTURE_NAMES` | 语料库涵盖的能力名称元组。 |
| `CapabilityFixture` | 加载器返回的冻结数据类。 |
| `FIXTURE_SCHEMA_VERSION` | 当前为 `1`；仅在进行加载器迁移时递增。 |
| `list_fixture_names(capability)` | 某能力的已排序文件名（不含扩展名）。 |
| `load_capability_fixture(capability, name)` | 验证并返回一个夹具。 |
| `iter_capability_fixtures(capability)` | 遍历某能力的已验证夹具。 |
| `iter_all_fixtures()` | 遍历语料库中的所有夹具。 |

## 在合规测试中使用夹具

`payload` 键与 `assert_*_conformance()` 的关键字参数一一对应，因此夹具可直接流入现有辅助工具：

```python
from worldforge import Action, MockProvider
from worldforge.testing import (
    assert_embed_conformance,
    assert_predict_conformance,
    load_capability_fixture,
)

provider = MockProvider()

predict_fx = load_capability_fixture("predict", "valid_baseline")
assert_predict_conformance(
    provider,
    world_state=predict_fx.payload["world_state"],
    action=Action.from_dict(predict_fx.payload["action"]),
    steps=predict_fx.payload["steps"],
)

embed_fx = load_capability_fixture("embed", "valid_baseline")
assert_embed_conformance(provider, text=embed_fx.payload["text"])
```

对于无效夹具，调用方可将 `expected_error_pattern` 编译为正则表达式，并断言对应的 API 接口抛出带有匹配消息的 `WorldForgeError`。部分无效夹具记录了框架尚未强制执行的契约声明；这些夹具仍然随包发布，以便未来的验证器可以锁定它们，描述字段中详细说明了相关情况。

## 数据所有权

夹具由评估/质量团队与确定性评估套件共同维护。它们被设计为：

- **默认合成** — 手工编写的 JSON 结构，用于测试公开输入边界。
- **体积小巧** — 仅 JSON；二进制视频帧以 `frames_base64` 字符串内联，而非以媒体文件形式发布。
- **尽可能与提供方无关** — 特定于提供方的结构（如针对 LeRobot 与 GR00T 的 `policy_info` 变体）仅在有不止一个消费方受益时才放入此处；否则应保留在 `tests/fixtures/providers/` 中，与用于解析器和重试测试的提供方夹具放在一起。

已捕获的载荷（`data_class: "captured"`）在复现真实 bug 或回归问题，且已对秘密、签名 URL、宿主路径及专有内容完成脱敏处理时，方可被接受。宿主方提供的载荷（`data_class: "host-supplied"`）随包附带合成占位符；`description` 字段记录了集成方应替换的内容。

## 快照清单

WorldForge 还通过 `tests/fixtures/fixture-snapshots.json` 追踪受源代码管理的 JSON 夹具。该清单记录了每个夹具路径、夹具类型、schema 版本、字节大小及 `sha256:<hex>` 摘要，涵盖：

- `src/worldforge/testing/fixtures/` 下已打包的能力夹具；
- `tests/fixtures/providers/` 下的提供方载荷夹具；
- `examples/*benchmark*.json` 下的基准测试夹具；
- `examples/scenarios/` 下的场景文件。

更改上述任何文件后，请检查清单：

```bash
uv run python scripts/manage_fixture_snapshots.py --format markdown
```

当清单条目指向受管理根目录之外、使用绝对路径、包含 `..` 或反斜杠路径段、引用了缺失文件，或存在摘要/大小/schema 不匹配时，验证失败。审查输出将正常偏差标记为 `changed`。若夹具更新属于有意为之，请在审查前将条目标记为 `"review_status": "intended-update"`（`intended-update`），以便报告区分已批准的夹具变更与意外偏差。默认检查对于 intended-update 仍然以非零状态退出；仅在已检查清单差异和夹具差异的人工审查工作流中使用 `--allow-intended-updates`。

夹具更改被接受后，请明确刷新清单：

```bash
uv run python scripts/manage_fixture_snapshots.py --write
```

如需在检出环境中演练审查输出，请运行：

```bash
uv run python scripts/demo_showcases.py run fixture-drift-review --workspace-dir .worldforge/demo-showcases --overwrite
```

该工作流会创建一个临时夹具树，包含提供方载荷、基准测试和场景夹具，然后保留针对夹具缺失、摘要偏差、schema 版本偏差、不安全路径及 `intended-update` 审查情况的报告。它还会写入一个刷新后的临时清单，以展示已批准的更新路径。它不会修改已提交的 `tests/fixtures/fixture-snapshots.json`。

请勿使用快照管理器获取远程提供方载荷、刷新数据集或存储大型媒体工件。仅在夹具用于锁定公开契约、复现 bug，或提供在 git 中安全审查的微型文档化场景/基准测试输入时，才添加或更新夹具。

## 验证

```bash
uv run pytest tests/test_capability_fixtures.py tests/test_provider_contracts.py
uv run python scripts/manage_fixture_snapshots.py --format markdown
bash scripts/test_package.sh
uv run mkdocs build --strict
```

# 空间场景工件边界

决策日期：2026-05-05。

Issue：[#138](https://github.com/AbdelStark/worldforge/issues/138)。

状态：设计已接受；提供方实现暂缓。

本记录定义了在添加任何空间或三维场景提供方之前，WorldForge 最低限度的场景工件边界。它不新增提供方、查看器、渲染器、模拟器桥接、资产存储或新能力。

## 决策

WorldForge 将仅在场景工件契约具备夹具覆盖和校验之后，才将空间和三维世界生成作为未来的 `generate` 界面。首个实现候选类别是 OpenLRM 风格的本地三维重建或生成运行时，可输出宿主方持有的场景资产。这是工件校验的候选类别，而非公开的提供方承诺。

本阶段不修改提供方目录行。未来的提供方在能够返回已校验的场景工件，并在不将 GPU 运行时、查看器、检查点或资产依赖引入基础包的前提下保留脱敏证据时，方可暴露 `generate` 能力。

## 候选决策

| 候选方案 | 决策 | 原因 |
| --- | --- | --- |
| OpenLRM 风格的本地三维重建或生成运行时 | 接受为首个工件契约候选类别 | 公开研究运行时是场景输出的合理来源，但 WorldForge 应在选定某个适配器之前先校验工件结构。 |
| World Labs Marble 风格的托管空间世界产品 | 拒绝用于本实现路径 | 产品输出可能与分类体系相关，但当前仓库证据中不存在 WorldForge 可调用的自动化契约。 |
| 模拟器桥接 | 拒绝用于本提供方边界 | 模拟器是一个宿主进程，拥有控制器、资产和安全所有权，其本身并非媒体生成器提供方。 |
| Cosmos、Runway 及其他视频 API | 拒绝用于本工件边界 | 生成的视频是媒体工件，而非具有可检查几何形状、变换和资产引用的持久化场景。 |
| Genie 风格的交互式世界生成 | 推迟至 Genie 契约决策 | Genie 在具体运行时或 API 契约出现之前仍作为独立的失败封闭脚手架保留。 |

## 场景工件结构

可安全检出的工件是一个包含以下顶层字段的 JSON 对象：

| 字段 | 是否必填 | 契约 |
| --- | --- | --- |
| `schema_version` | 是 | 字符串版本号。首个夹具结构版本为 `1`。 |
| `kind` | 是 | 字面值 `worldforge.scene_artifact`。 |
| `provider` | 是 | 生成该工件的提供方名称。夹具可使用 `fixture`。 |
| `capability` | 是 | 生成型场景工件的字面值为 `generate`。 |
| `units` | 是 | 世界距离单位。初始有效值：`meter`、`centimeter`、`millimeter`、`unitless`。 |
| `coordinate_frame` | 是 | 定义 `up_axis`、`forward_axis` 和 `handedness` 的 JSON 对象。 |
| `objects` | 是 | 包含稳定 ID、变换、可选边界和资产引用的场景对象列表。 |
| `assets` | 是 | 引用的外部或本地资产列表，每项包含安全标识和摘要元数据。 |
| `media` | 否 | 可选的预览图、缩略图或相机路径渲染。仅作为证据辅助，非必要内容。 |
| `provenance` | 是 | 运行时、命令、输入摘要、结果摘要、事件计数和限制说明。 |
| `metadata` | 否 | 少量 JSON 原生元数据，不得包含密钥或宿主本地路径。 |

该工件有意为描述性的，不证明物理有效性、碰撞正确性、渲染质量、抓取可行性或模拟器兼容性。

## 坐标与变换契约

`coordinate_frame` 包含：

```json
{
  "up_axis": "z",
  "forward_axis": "x",
  "handedness": "right"
}
```

有效轴为 `x`、`y` 和 `z`。`up_axis` 与 `forward_axis` 必须不同。有效的 `handedness` 值为 `left` 和 `right`。

每个场景对象包含：

```json
{
  "id": "block-1",
  "label": "block",
  "transform": {
    "translation": [0.0, 0.0, 0.0],
    "rotation_quat": [0.0, 0.0, 0.0, 1.0],
    "scale": [1.0, 1.0, 1.0]
  },
  "bbox": {
    "min": [-0.05, -0.05, 0.0],
    "max": [0.05, 0.05, 0.1]
  },
  "asset_refs": ["mesh-block-1"],
  "metadata": {
    "role": "fixture"
  }
}
```

变换必须使用有限数值三元组，`rotation_quat` 除外，后者须包含四个有限数值。缩放值必须有限且大于零。边界框为可选项，但若存在，每个 `min` 坐标必须小于或等于对应的 `max` 坐标。

## 资产与媒体引用

资产和媒体引用是安全的描述符，而非存储保证：

```json
{
  "id": "mesh-block-1",
  "role": "mesh",
  "mime_type": "model/gltf+json",
  "uri": "artifacts/block-1.gltf",
  "digest": "sha256:0123456789abcdef",
  "size_bytes": 2048,
  "local_only": false
}
```

规则：

- `id`、`role` 和 `digest` 为必填项。
- `uri` 为可选项。若出现在公开工件中，必须为相对路径或不含用户信息、查询字符串或片段标识符的 `https` URL。
- 宿主本地绝对路径、`file://` URI、回环 URL、私有网络 URL 和签名 URL 不得出现在可发布工件中。
- `local_only: true` 可被宿主运行清单用于指向本地留存资产，但准备提交至 Issue 的打包件必须将本地路径替换为安全的相对工件路径或摘要。
- `size_bytes` 若存在，必须是非负整数。

## 来源信息

`provenance` 应足以在没有控制台日志的情况下复现或排查场景工件问题：

```json
{
  "runtime_manifest": "src/worldforge/providers/runtime_manifests/example-scene.json",
  "command": "worldforge-smoke-example-scene --input prompt.json",
  "input_digest": "sha256:input",
  "result_digest": "sha256:result",
  "event_count": 4,
  "limitations": [
    "fixture-only artifact",
    "does not certify physical validity"
  ]
}
```

在准备 Issue 打包件时，命令中可省略宿主本地绝对路径。运行时版本、模型名称和设备标签在非密钥的情况下允许保留。

## 脱敏规则

校验器和 Issue 打包导出器应拒绝或脱敏以下内容：

- Bearer 令牌、API 密钥、签名 URL 查询字符串、片段标识符和用户信息；
- 可发布工件中的宿主本地绝对路径、主目录路径和 `file://` URI；
- 包含类似密钥术语（如 `token`、`secret`、`key` 或 `signature`）的提供方元数据键；
- 对象实例、元组、非有限数值、字节及其他非 JSON 原生值；
- 可能隐藏运行时转储、原始张量、二进制数据块或无界日志的过大元数据。

脱敏操作必须保留足以排查工件问题的上下文：提供方名称、对象 ID、资产角色、安全 URI 路径、摘要、大小及失败原因。

## 校验辅助工具

WorldForge 为夹具和适配器测试提供了一个可安全检出的校验器：

```python
from worldforge import validate_scene_artifact

artifact = validate_scene_artifact(payload)
```

校验器返回 JSON 原生副本，并在场景工件进入文档、运行清单或 Issue 打包件之前触发 `WorldForgeError`。它拒绝非有限数值、元组形状值、对象实例、格式错误的变换、无效单位、重复标识符、类密钥元数据键、过大元数据、路径遍历、签名 URL、公开 `http` URL，以及未显式标记为 `local_only: true` 的宿主本地路径。

## 安全的 Issue 附件

准备提交至 Issue 的场景工件应包含 JSON 描述符及相对路径引用的少量留存夹具资产，不应包含：

- 未通过 `validate_scene_artifact` 的原始提供方输出；
- 宿主本地绝对路径，除非该 Issue 明确记录的是仅本地的运行清单；
- 签名 URL、查询字符串、API 密钥、令牌或私有网络 URL；
- 许可证或留存策略不明确的生成网格、纹理、点云、高斯喷溅或预览；
- 声称场景具有物理有效性、模拟器就绪、无碰撞或机器人可执行等属性。

当排查工作需要大型或仅限本地的资产时，请先附上脱敏描述符，并单独概述留存资产的摘要、角色、大小及宿主端存储位置。

## 宿主方职责

宿主方负责：

- 安装并获得三维运行时、GPU 栈、查看器、渲染器、模拟器及转换工具的许可；
- 下载并留存生成的网格、点云、高斯喷溅、纹理、预览、相机路径及检查点；
- 将提供方原生输出转换为 JSON 场景工件；
- 校验下游模拟器、碰撞、物理或机器人的相关假设；
- 决定仅限本地的证据是否可以发布。

WorldForge 负责：

- JSON 原生工件结构定义和校验辅助工具；
- 提供方事件脱敏边界；
- 有效和格式错误工件的夹具覆盖；
- 防止场景工件被作为物理保真度证据呈现的文档。

## #143 的后续契约

后续夹具和校验 Issue 可在不修改能力语义的情况下推进，应添加：

- 一个有效的最小场景工件夹具；
- 格式错误的变换、无效单位、不安全资产引用、非有限数值、非原生元数据及过大元数据夹具；
- 在干净检出环境中拒绝不安全可发布工件的校验器；
- 展示如何将脱敏场景工件附加至提供方 Issue 的文档。

在上述工作落地之前，空间和三维场景提供方继续处于暂缓状态。

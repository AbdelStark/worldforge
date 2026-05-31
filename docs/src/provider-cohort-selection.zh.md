# 提供方批次选型记录

决策日期：2026-05-05。

议题：[#130](https://github.com/AbdelStark/worldforge/issues/130)。

本记录在不改变提供方目录条目、生成的提供方文档、README 提供方表格或公共能力声明的前提下，选定下一批提供方证据批次。其存在目的是防止提供方增长演变为目录噪音。

请结合以下文档使用：

- [提供方优先级评估标准](./provider-platform-roadmap.md#provider-prioritization-rubric)
- [提供方晋升矩阵](./provider-platform-roadmap.md#provider-promotion-matrix)
- [提供方编写晋升关卡](./provider-authoring-guide.md#step-3-apply-the-promotion-gate)
- [提供方目录规则](./providers/README.md#capability-model)

## 评审输入

选型使用路线图议题正文、当前提供方文档、当前 GitHub 议题状态，以及来自 2026-05-05 的轻量上游核查。上游核查有意保持浅层：足以为批次打分，但不足以声明运行时支持。

| 来源 | 使用的信号 |
| --- | --- |
| [`facebookresearch/jepa-wms`](https://github.com/facebookresearch/jepa-wms) | JEPA-WMS 物理规划研究的公共 Python 仓库；GitHub 许可证检测报告为 `Other`；评审时最后更新于 2026-05-04。 |
| [`simchowitzlabpublic/nano-world-model`](https://github.com/simchowitzlabpublic/nano-world-model) | 用于动作条件视频世界模型和 MPC 风格规划的公共 Python 仓库；MIT 许可证；评审时最后更新于 2026-05-05。 |
| [`Physical-Intelligence/openpi`](https://github.com/Physical-Intelligence/openpi) | 公共 Python 具身策略栈；Apache-2.0 许可证；对未来的策略工作有参考价值，但不属于打分/预测世界模型边界。 |
| [`3DTopia/OpenLRM`](https://github.com/3DTopia/OpenLRM) | 公共 Python 3D 重建/生成项目；Apache-2.0 许可证；对场景工件有参考价值，但不是选定的 WorldForge 提供方 API。 |
| GitHub 仓库搜索 Genie 世界模型实现 | 返回的是第三方仓库，而非受支持的自动化 API 或官方运行时契约。 |
| [Nano World Model 议题 #158](https://github.com/AbdelStark/worldforge/issues/158) | 关于 NanoWM 适配性、宿主方持有运行时风险以及可能的 WorldForge 打分优先契约的现有议题级研究。 |

## 评分方法

每个候选者按提供方平台路线图中的八项标准评分：用户价值、能力清晰度、上游成熟度、运行时可行性、夹具策略、冒烟可行性、维护负担和安全/密钥风险。每项标准得 0、1 或 2 分。

解读：

- `12-16`：符合下一批实现批次的条件。
- `8-11`：保持为 RFC、直接构建候选或契约设计议题。
- `<8`：延期；不添加目录接口。

## 候选者评分卡

| 候选者 | 能力 | 上游运行时/API | 运行时归属权 | 夹具策略 | 已准备好宿主冒烟可行性 | 许可证/维护风险 | 得分 | 决策 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| JEPA-WMS 及公共 `jepa` 打分路径 | `score` | 通过宿主方持有的 torch-hub/运行时加载使用 `facebookresearch/jepa-wms` | 宿主方持有 torch、检查点、设备、模型名称和任务预处理 | 注入式运行时测试、打分输出夹具、运行时响应验证、提供方契约辅助函数 | 通过现有 JEPA-WMS 已准备好宿主冒烟路径（一旦清单证据被捕获）具有可信度 | 中等：活跃的公共仓库，但 GitHub 未将许可证分类为 SPDX；稳定晋升前请核实条款 | 12 | 活跃批次。完成 [#133](https://github.com/AbdelStark/worldforge/issues/133)，然后完成 [#137](https://github.com/AbdelStark/worldforge/issues/137)。 |
| Nano World Model 打分候选 | 首先是 `score`；`predict` 仅在建立独立契约后 | `simchowitzlabpublic/nano-world-model` 动作条件滚动和 MPC/CEM 规划代码 | 宿主方持有 NanoWM 检出目录、PyTorch/CUDA 或设备栈、配置、VAE/检查点、数据集和预处理 | 从注入式运行时协议和有限嵌套 JSON 原生候选张量开始；检出测试中无 torch 导入 | 可行，但仅在运行时/API 侦察证明 Python 3.13 下存在可导入或子进程边界后 | 中等：MIT 和活跃公共仓库，但运行时栈沉重，API 可能由脚本/配置驱动 | 10 | 活跃设计候选，非公共提供方实现。使用 [#158](https://github.com/AbdelStark/worldforge/issues/158) 进行运行时/API 侦察，然后再声明任何目录条目。 |
| 空间/3D 场景提供方族群 | 不在当前提供方表面内 | 无单一选定 API；OpenLRM/I-Scene 风格项目仅为研究信号 | 宿主方将持有 GPU/运行时包、模型权重、资产保留、查看器和单位约定 | 尚未就绪；首先需要与规划相关的状态契约和格式错误载荷覆盖 | 在选定一个具体 API 和工件模式之前不具可信度 | 中至高：快速迭代的项目、大型工件、不明确的场景单位语义 | 7 | 延期。在实现前通过 [#138](https://github.com/AbdelStark/worldforge/issues/138) 重新评估。 |
| Genie 运行时/API 决策 | 当前无能力主张 | 在当前项目文档/搜索中未找到支持的自动化 API 或官方可调用运行时；当前 `genie` 保持为脚手架 | 如果出现真实规划契约，宿主方将持有凭据/运行时/工件保留 | 仅脚手架测试；在上游契约选定之前没有真实的解析器夹具 | 目前不具可信度 | 高：上游契约不明确，过度声明风险高 | 5 | 延期。在存在具体的运行时或 API 契约之前，保持 `genie` 失败关闭。 |
| 仿真器桥接 | 未来的 `predict` 或宿主工作流（视桥接类型而定） | 未选定仿真器桥接契约 | 宿主方持有仿真器进程、资产、控制器、安全策略和持久化存储 | 尚未就绪；首先需要场景/状态边界和宿主方持有的进程模型 | 在状态/工件模式存在之前，作为提供方冒烟测试不具可信度 | 高：仿真器设置和控制器假设可能泄漏到核心中 | 6 | 延期。在空间/场景边界和状态工件夹具存在后重新评估。 |
| LeRobot 和 GR00T 之外的新具身策略栈 | `policy` | 候选族群包括 OpenPI 风格和 OpenVLA 风格栈，非打分/预测提供方 | 宿主方持有检查点、机器人运行时、动作转换器、安全性和实验室流程 | 通过注入式策略输出可行，但动作转换和安全审查占主导 | 仅限已准备好宿主且成本高昂；默认无可安全检出的机器人证据 | 中至高：沉重的运行时和机器人安全负担 | 8 | 延期。在新增其他策略运行时之前，先完成现有 LeRobot/GR00T 证据和操作人员工作流。 |

## 活跃批次

选定的批次包含两项活跃工作，且不扩展公共目录：

1. **JEPA-WMS/公共 JEPA 打分证据。** 完成 [#133](https://github.com/AbdelStark/worldforge/issues/133)，然后完成 [#137](https://github.com/AbdelStark/worldforge/issues/137)。首要实现重点是打分结果证据、运行时清单覆盖、有限输出验证、JSON 原生元数据和明确的失败类型化。
2. **Nano World Model 打分候选侦察。** 使用 [#158](https://github.com/AbdelStark/worldforge/issues/158) 进行宿主方持有的可选运行时契约设计。在存在真实可调用的打分边界、夹具、事件脱敏和已准备好宿主的冒烟路径之前，它不是提供方目录条目。

本活跃批次有意排除新的脚手架保留条目。

## 延期候选者

| 候选者 | 具体阻碍 | 重新评估触发条件 |
| --- | --- | --- |
| Genie 运行时/API | 未找到 WorldForge 可封装的受支持自动化 API 或官方运行时契约的文档。 | 一个受维护的上游运行时或托管 API，以有许可证、输入、输出和冒烟证据的可调用规划契约形式出现。 |
| 空间/3D 场景提供方 | 不属于当前以规划为中心的提供方能力面。 | 只有在存在具体的类型化规划契约和夹具集时才重新评估。 |
| 仿真器桥接 | 仿真器进程归属权、场景/状态转换、资产保留和安全边界尚未达到提供方就绪状态。 | 场景/状态工件具有稳定模式，且宿主方持有的仿真器进程设计已存在。 |
| 新具身策略栈 | 现有的 LeRobot 和 GR00T 路径仍需更强的证据、工作台和操作人员手册覆盖。 | 提供方实况冒烟证据注册表和适配器工作台路径使策略晋升可重复。 |
| NanoWM `predict` 接口 | 打分是唯一合理的首个契约。视觉滚动尚未被类型化为 WorldForge 预测载荷。 | 打分路径已被证明，且独立设计记录了预测形态、保真度限制和验证夹具。 |

## 公共声明护栏

- 生成的提供方目录不因本记录而改变。
- README 提供方表格不因本记录而改变。
- `genie` 保持能力失败关闭的脚手架状态。
- `jepa-wms` 在运行时行为和冒烟证据可信之前，保持为直接构建候选。
- `nanowm` 不是包、目录、文档索引或自动注册策略中的提供方名称。
- 延期候选者不得仅以保留名称为由添加为占位符。

## 推荐议题顺序

除非维护者明确调整优先级，否则按以下顺序执行：

1. 通过 [#130](https://github.com/AbdelStark/worldforge/issues/130) 关闭本选型记录。
2. 完成 [#133](https://github.com/AbdelStark/worldforge/issues/133)，因为它是得分最高的新证据路径，并解锁 [#137](https://github.com/AbdelStark/worldforge/issues/137) 和 [#144](https://github.com/AbdelStark/worldforge/issues/144)。
3. 仅在 [#133](https://github.com/AbdelStark/worldforge/issues/133) 建立证据后完成 [#137](https://github.com/AbdelStark/worldforge/issues/137)。
4. 在 [#158](https://github.com/AbdelStark/worldforge/issues/158) 证明可调用的打分边界之前，将其视为设计/侦察议题。
5. 在上述阻碍项解除之前，不启动 [#138](https://github.com/AbdelStark/worldforge/issues/138)、[#139](https://github.com/AbdelStark/worldforge/issues/139)、[#143](https://github.com/AbdelStark/worldforge/issues/143) 或新的策略/提供方扩展。

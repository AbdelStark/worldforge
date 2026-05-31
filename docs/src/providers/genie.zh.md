# Genie 提供方

状态：脚手架。

WorldForge 将 `genie` 保留为一个失败关闭的提供方预留位。它不宣传任何公开能力，也不是真正的 Google DeepMind Genie 或 Project Genie 集成。

## 推迟决策

决策日期：2026-05-01。

任何未来面向 Genie 的接口都需要自动化可调用并可测试的受支持上游运行时或 API 契约。Google DeepMind 将 Genie 3 描述为面向实时交互环境的通用世界模型，2026 年 1 月的 Project Genie 公告将 Project Genie 描述为面向美国 Google AI Ultra 订阅用户的实验性研究原型 Web 应用。这些来源描述的是一种交互式产品体验，而非受支持的自动化 API、SDK、规划契约、认证契约或可冒烟测试的运行时边界。

在这些边界确立之前，WorldForge 不得将确定性的本地代理行为呈现为 Genie 实现。将该提供方保持为 `scaffold` 是准确的生产行为。

重新评估触发条件：维护中的上游 API、SDK 或本地运行时须发布具有已记录认证、输入、输出、失败模式、许可证及冒烟测试证明的面向规划的契约。仅有 Web 端交互式原型不足以更改提供方能力标志。

参考资料：

- [Genie 3 - Google DeepMind](https://deepmind.google/models/genie/)
- [Project Genie 公告 - Google 博客](https://blog.google/innovation-and-ai/models-and-research/google-deepmind/project-genie/)

## 当前契约

| 字段 | 值 |
| --- | --- |
| 提供方名称 | `genie` |
| 成熟度 | `scaffold` |
| 公开能力 | 无 |
| 自动注册信号 | `GENIE_API_KEY` |
| 运行时归属 | 暂无；未来的运行时/API 须由宿主方持有 |
| 工件类型 | 无 |

设置 `GENIE_API_KEY` 仅使预留位对诊断和就绪接口可见。它不会使任何能力方法可调用。所有能力方法保持失败关闭状态，除非为本地适配器测试设置了 `WORLDFORGE_ENABLE_SCAFFOLD_SURROGATES=1`。

代理选择性启用仅用于测试共享提供方管道。不得将其用于基准测试、演示、发布证明或声称 Genie 运行时行为的问题证明。

## 晋升要求

仅当 PR 能够命名并验证一个具体的上游契约时，才可替换此脚手架：

- 受支持的 API、SDK 或本地运行时入口点；
- 具有经过脱敏 `config_summary()` 输出的认证与配置字段；
- 提示词、可选图像/状态输入、时长及控制项的精确输入契约；
- 返回的工件 schema、MIME/类型提示、过期行为及留存期望；
- 认证错误、验证错误、容量不可用、超时及不支持工件的类型化失败模式；
- 针对成功和失败载荷的夹具支撑解析器测试；
- 写入经脱敏 `run_manifest.json` 的可选已准备宿主冒烟测试命令。

若上游接口仍为无受支持自动化契约的交互式 Web 原型，该提供方应保持 `scaffold` 状态。

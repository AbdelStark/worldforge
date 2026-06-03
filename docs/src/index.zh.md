---
hide:
  - navigation
  - toc
---

# WorldForge

**用于构建面向物理 AI 系统的、基于世界模型的工作流的框架（harness）。**

WorldForge 面向物理 AI 应用的构建者，是 Stable World Model 等「模型训练」栈的对位补充：它帮助机器人
与物理 AI 构建者在世界模型之上**组合、评估并基准测试**工作流，从而为具体任务挑选最合适的提供方与配置，
而不是去训练这些模型。整个框架围绕一个主干循环组织：用动作条件化的预测世界模型，在潜空间中对动作
候选进行规划与打分。

[快速上手](./quickstart.md){ .md-button .md-button--primary }
[阅读简介](./introduction.md){ .md-button }

## 下一步去哪里

<div class="grid cards" markdown>

- **快速开始**

    安装 WorldForge，创建一个世界，并端到端运行 mock 提供方。

    [快速开始](./quickstart.md)

- **CLI 参考**

    查找具体的 CLI 命令或可选运行时冒烟测试。

    [CLI 参考](./cli.md)

- **架构**

    了解各模块的职责以及规划流水线。

    [架构](./architecture.md)

- **提供方编写**

    依照能力契约新增或晋升一个提供方适配器。

    [提供方编写指南](./provider-authoring-guide.md)

- **文档导航**

    沿着完整的阅读路径浏览每个章节。

    [文档导航](./docs-map.md)

- **证据与评估**

    了解各项主张如何映射到确定性、可复现的证据。

    [评估](./evaluation.md)

</div>

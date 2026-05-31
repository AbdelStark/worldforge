# 文档导图

本页作为公开文档的读者路径导图。它使路线图历史保持可发现，同时将活跃工作引导至持有可执行契约的页面。

## 读者路径

| 读者 | 从这里开始 | 然后使用 | 成功信号 |
| --- | --- | --- | --- |
| 首次本地使用者 | [快速开始](./quickstart.md) | [CLI 参考](./cli.md)、[示例与 CLI 命令](./examples.md) | mock 世界、提供方诊断或可安全检出的演示在本地运行成功 |
| 提供方作者 | [提供方编写指南](./provider-authoring-guide.md) | [提供方](./providers/README.md)、[提供方配置索引](./provider-configuration-index.md)、[提供方失败模式画廊](./provider-failure-gallery.md)、[能力夹具语料库](./fixtures.md)、[公开 API 稳定性](./api-stability.md) | 提供方能力、配置文件、夹具、文档和测试保持一致 |
| 运维人员 | [运维](./operations.md) | [提供方配置索引](./provider-configuration-index.md)、[用户与运维操作手册](./playbooks.md)、[安全](./security.md)、[工件完整性](./artifact-integrity.md) | 诊断、运行清单、安全包和恢复命令均可用 |
| 评估者或研究用户 | [评估](./evaluation.md) | [基准测试](./benchmarking.md)、[声明与凭证映射](./claim-evidence-map.md)、[工件模式](./artifact-schemas.md)、[实时冒烟凭证注册表](./live-smoke-evidence.md) | 声明指向已保留的报告和清晰的声明边界 |
| 演示或案例展示用户 | [示例与 CLI 命令](./examples.md) | [演示案例展示工作流](./demo-showcases.md)、[使用场景手册](./use-case-cookbook.md)、[机器人重放案例展示](./robotics-showcase.md)、[Rerun 集成](./rerun.md) | 可安全检出的演示或预先准备好的宿主展示命令生成工件 |
| 发布维护者 | [工程质量](./quality.md) | [工件完整性](./artifact-integrity.md)、[工件模式](./artifact-schemas.md)、[运维](./operations.md)、[更新日志](./changelog.md) | 本地门禁、包检查、审计、质量仪表板、凭证 JSON、模式归属以及发布说明对齐一致 |
| 贡献者 | [贡献指南](./contributing.md) | [贡献者任务启动包](./task-starters.md)、[文档导图](./docs-map.md)、[工程质量](./quality.md) | 议题范围、涉及文件、验证命令、凭证工件、文档更新和评审清单均明确 |

## 路线图历史

路线图页面保持公开，因为它们记录了项目选择某一方向的原因。它们不是活跃议题状态或可执行文档的替代品。

| 页面 | 作用 |
| --- | --- |
| [路线图](./roadmap.md) | 当前顶层公开方向及历史轨道链接 |
| [路线图扩展 2](./roadmap-expansion-2.md) | 第二批 30 个议题扩展记录，涵盖工件治理、外部提供方演示、场景复用和组合工作流跟踪 |
| [路线图扩展](./roadmap-expansion.md) | 为当前生产、演示和功能流创建的 30 个议题扩展记录 |
| [路线图延续](./roadmap-continuation.md) | 早期延续计划和已完成的协调说明 |
| [提供方与平台路线图](./provider-platform-roadmap.md) | 前期提供方-平台跟踪表和凭证历史 |

活跃工作应在 GitHub 议题中跟踪。当路线图条目改变公开行为时，请更新所属文档页面、更新日志、测试，以及在读者路径发生变化时更新本导图。

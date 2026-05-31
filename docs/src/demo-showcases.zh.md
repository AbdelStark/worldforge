# 演示案例展示工作流

`scripts/demo_showcases.py` 是当前案例展示路线图流的可安全检出演示证据运行器。它组合了现有的 WorldForge 示例、诊断、保留运行工作区、问题包、回放夹具以及宿主示例，无需安装可选模型运行时、调用付费提供方、打开 GUI 或控制机器人。

```bash
uv run python scripts/demo_showcases.py list
uv run python scripts/demo_showcases.py run all --workspace-dir .worldforge/demo-showcases
uv run python scripts/demo_showcases.py run first-run --format json --overwrite
```

预期成功信号：命令以 `0` 退出，报告 `status: passed`，并为每个选定的工作流写入一个 `run_manifest.json` 以及 `results/summary.json` 和 `reports/summary.md`。首步排查：打开失败工作流的 `workflow-result.json`，然后检查引用的保留运行清单。

## 工件布局

默认工作区为 `.worldforge/demo-showcases/`。

| 路径 | 用途 | 安全附件说明 |
| --- | --- | --- |
| `<workflow>/workflow-result.json` | 简短的机器可读工作流结果 | `safe_to_attach` 为 `true` 时安全 |
| `<workflow>/runs/<run-id>/run_manifest.json` | 保留的命令、提供方、操作、状态、工件 | 按构造安全；不含原始密钥或签名 URL |
| `<workflow>/runs/<run-id>/results/summary.json` | 完整工作流摘要 | 除非工作流另有标记，否则安全 |
| `<workflow>/runs/<run-id>/reports/summary.md` | 含声明边界和首步排查的人类可读摘要 | 除非工作流另有标记，否则安全 |
| `<workflow>/issue-bundle/` | 诊断工作流的问题就绪证据包 | 仅在 `evidence_manifest.json` 说明 `safe_to_attach: true` 时附加 |

## 工作流矩阵

| 工作流 | 问题 | 命令 | 预期输出 | 主要工件 | 首步排查 |
| --- | ---: | --- | --- | --- | --- |
| `first-run` | #189 | `uv run python scripts/demo_showcases.py run first-run` | mock 世界创建、对象添加、预测记录、导出和预检写入 | `first-run/exported-world.json` 和 `first-run/preflight.json` | 运行 `uv run worldforge world preflight --state-dir <demo>/worlds` |
| `diagnostics-issue-bundle` | #190 | `uv run python scripts/demo_showcases.py run diagnostics-issue-bundle` | 跳过的提供方诊断已保留并打包 | `diagnostics-issue-bundle/issue-bundle/issue.md` | 附加前检查 `evidence_manifest.json` |
| `robotics-replay` | #191 | `uv run python scripts/demo_showcases.py run robotics-replay` | 确定性策略加打分回放摘要 | `robotics-replay/robotics-replay-manifest.json` | 在执行已准备宿主命令前运行 `uv run worldforge-demo-lerobot` |
| `provider-event-redaction-dry-run` | #192 | `uv run python scripts/demo_showcases.py run provider-event-redaction-dry-run` | 已脱敏的提供方事件夹具 | `provider-event-redaction-dry-run/provider-event-redaction-events.json` | 在任何实时冒烟测试前检查已脱敏的提供方事件目标 |
| `adapter-author` | #193 | `uv run python scripts/demo_showcases.py run adapter-author` | 提供方脚手架已生成于演示输出下，晋升阻碍已报告 | `adapter-author/generated-provider/` | 替换占位夹具，然后运行生成的提供方测试 |
| `batch-eval` | #194 | `uv run python scripts/demo_showcases.py run batch-eval` | 评估成功和受控基准测试预算失败已保留 | `batch-eval/batch-host/runs/<run-id>/run_manifest.json` | 更改预算前检查失败的基准测试清单 |
| `service-host` | #195 | `uv run python scripts/demo_showcases.py run service-host` | stdlib 服务宿主就绪状态和一个 mock 请求摘要 | `service-host/runs/<run-id>/results/summary.json` | 运行 `uv run python examples/hosts/service/app.py --help` 并检查 `/readyz` |
| `rerun-gallery` | #196 | `uv run python scripts/demo_showcases.py run rerun-gallery` | 仅含清单的 Rerun 图库，附缺少扩展状态 | `rerun-gallery/rerun-gallery-manifest.json` | 在打开 `.rrd` 文件前安装 `rerun` 扩展 |
| `failure-lab` | #197 | `uv run python scripts/demo_showcases.py run failure-lab` | 独立故障演练、预检和恢复命令 | `failure-lab/failure-lab-report.json` | 在操作真实 `.worldforge` 状态前阅读 `recovery_commands` |
| `use-case-cookbook` | #198 | `uv run python scripts/demo_showcases.py run use-case-cookbook` | 食谱数量和文档工件引用 | `docs/src/use-case-cookbook.md` | 打开与失败命令和工件匹配的食谱 |
| `external-provider-package` | #237 | `uv run python scripts/demo_showcases.py run external-provider-package` | 临时外部提供方包已生成，入口点发现报告已保留 | `external-provider-package/external-provider-discovery.json` | 检查发现报告，然后在发布前运行生成的包测试 |
| `custom-evaluation-suite` | #238 | `uv run python scripts/demo_showcases.py run custom-evaluation-suite` | 自定义评估套件运行含来源、一次受控失败和报告工件 | `custom-evaluation-suite/custom-eval-artifacts/` | 打开 `markdown`，然后检查 `failure_gallery.md` 中的受控失败案例 |
| `policy-score-candidate-lab` | #239 | `uv run python scripts/demo_showcases.py run policy-score-candidate-lab` | 确定性动作候选由打分提供方排序，原始策略动作已保留 | `policy-score-candidate-lab/policy-score-candidate-lab.json` | 验证所选行与 `score_result.best_index` 匹配 |
| `fixture-drift-review` | #240 | `uv run python scripts/demo_showcases.py run fixture-drift-review` | 临时夹具清单审查，含缺失、更改、模式变更、不安全和预期更新情况 | `fixture-drift-review/fixture-drift-review.md` | 在批准预期清单更新前检查每个夹具差异 |
| `capability-negotiation-preflight` | #241 | `uv run python scripts/demo_showcases.py run capability-negotiation-preflight` | 就绪、缺少配置、缺少依赖、不支持和未注册预检情况的协商报告 | `capability-negotiation-preflight/capability-negotiation/preflight-report.md` | 针对被阻塞的能力槽遵循第一条推荐操作 |
| `embodied-policy-replay-comparison` | #242 | `uv run python scripts/demo_showcases.py run embodied-policy-replay-comparison` | LeRobot、GR00T 和 Cosmos-Policy 回放契约并排，含提供方专属原始动作字段 | `embodied-policy-replay-comparison/embodied-policy-replay-comparison.md` | 在运行已准备宿主冒烟测试前检查原始字段和缺少转换器的阻碍 |
| `non-developer-evidence-review` | #245 | `uv run python scripts/demo_showcases.py run non-developer-evidence-review` | 评估、基准测试、世界差异和问题包证据的静态 HTML/JSON/Markdown 审查包 | `non-developer-evidence-review/non-developer-evidence-review/review-package.html` | 仅附加审查包，将本地专属行排除在问题上传之外 |
| `provider-failure-gallery` | #246 | `uv run python scripts/demo_showcases.py run provider-failure-gallery` | 夹具支持的提供方失败图库，含预期事件、错误、安全工件、负责人和首步排查命令 | `provider-failure-gallery/provider-failure-gallery/provider-failure-gallery.md` | 附加证据前将失败的提供方信号与某行匹配 |

## 运行时边界

这些工作流证明 WorldForge 集成层和工件契约，而非上游模型质量或物理执行能力。可选运行时仍由宿主方持有：

- LeWorldModel、LeRobot、GR00T、torch、检查点、仿真器和机器人控制器不由此运行器安装。
- 提供方事件脱敏路径使用夹具支持的事件，不进行付费 API 调用。
- Rerun 在可安全检出路径中以清单表示；`.rrd` 生成仍需要 `rerun` 扩展或已准备好宿主的机器人运行。
- 由适配器开发工作流生成的提供方脚手架是刻意不完整的，在真实夹具、运行时清单、文档和测试通过之前不得注册或晋升。
- 演示生成的外部提供方包位于所选工作区下，仅证明包形状和发现行为；它们不会被发布、全局安装或视为真实适配器证据。
- 自定义评估套件输出是确定性的适配器契约证据。其受控失败案例演示了报告和失败图库处理，不代表提供方质量或物理保真度。
- 策略加打分候选实验室使用本地确定性提供方展示候选生成、打分、原始动作保留、转换器边界以及安全工件形状。它不是机器人控制器、仿真器、检查点运行或物理性能声明。
- 夹具漂移审查工作流仅修改所选演示工作区。它演示了审查状态和已批准的更新路径；不刷新远程夹具或重写已提交的快照清单。
- 能力协商预检工作流仅报告阻碍。它不安装可选依赖、配置凭据或执行回退工作流。
- 具身策略回放比较分别保留 LeRobot、GR00T 和 Cosmos-Policy 的动作形状。它不执行跨提供方动作转换，不联系实时 GPU 服务器，也不声明控制器安全性。
- 非开发者证据审查包仅转义显示文本和链接相对安全工件。宿主本地路径、签名 URL 和原始提供方载荷被标记为仅本地或排除在外；该包不托管仪表盘或执行 JavaScript。
- 提供方失败图库由夹具支持。它不调用付费 API、安装可选运行时、保留签名 URL，也不将脚手架提供方行转化为集成声明。
- 批量工作流中的基准测试失败是受控的预算失败，以便在不更改生产阈值的情况下测试问题和发布证据路径。

有关面向任务的命令，请参阅[用例食谱](./use-case-cookbook.md)。

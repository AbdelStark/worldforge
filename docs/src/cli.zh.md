# CLI 参考

WorldForge 提供一套本地优先的命令行工具，涵盖提供方诊断、持久化的模拟世界状态、评估、基准测试、打包示例以及可选的可视化界面。所有命令均与库所使用的相同类型化 Python 接口交互。

请以 `uv run worldforge --help` 及各子命令的 `--help` 输出作为解析器的准确契约。本页是面向运维人员的稳定命令映射。

## 发现命令

```bash
uv run worldforge --help
uv run worldforge examples
uv run worldforge examples --format json
```

贡献者环境配置及静态发布支持检查：

```bash
uv run python scripts/contributor_doctor.py --format markdown
uv run python scripts/contributor_doctor.py --format json
uv run python scripts/check_docs_commands.py
uv run python scripts/check_wrapper_portability.py
uv run python scripts/check_core_performance.py
```

`contributor_doctor.py` 将缺失的必需工具报告为配置失败，将可选运行时依赖报告为跳过，将缺失的 GitHub CLI 认证报告为发布警告而非本地验证失败。

运维故障演练：

```bash
uv run worldforge drills list
uv run worldforge drills run missing-credentials --workspace-dir .worldforge/drills
uv run worldforge drills run unsafe-event-metadata --workspace-dir .worldforge/drills --bundle
```

演练命令界面默认为签出安全状态。每次运行均会保存清单，记录预期的失败及恢复命令，并将生成的状态限制在所请求的临时或文档化工作区内。

## 提供方诊断

```bash
uv run worldforge doctor --registered-only
uv run worldforge provider list
uv run worldforge provider info mock
uv run worldforge provider contract mock --format json
uv run worldforge provider docs
uv run worldforge provider health mock
uv run worldforge negotiate --list
uv run worldforge negotiate --workflow policy-plus-score
```

当某个提供方缺失时，请优先使用 `doctor` 命令排查。LeWorldModel、LeRobot、GR00T 和 Cosmos-Policy 等可选提供方仅在宿主方配置了相应的环境变量和运行时后才会自动注册。`worldforge negotiate` 回答"在运行之前，我的提供方能否满足该工作流的需求？"这一更高层次的问题——请参阅[能力协商](./capability-negotiation.md)。

## 本地世界状态

```bash
uv run worldforge world create lab --provider mock
uv run worldforge world list
uv run worldforge world show <world-id>
uv run worldforge world objects <world-id>
uv run worldforge world history <world-id>
uv run worldforge world preflight --state-dir .worldforge/worlds --workspace-dir .worldforge
uv run worldforge world migration-preview <world-id> --state-dir .worldforge/worlds
uv run worldforge world migration-preview world.json --source-path
uv run worldforge world export <world-id> --output world.json
uv run worldforge world import world.json --new-id --name imported-lab
uv run worldforge world fork <world-id> --name forked-lab
uv run worldforge world delete <world-id>
uv run worldforge world diff <source-id> <target-id>
uv run worldforge scenario validate examples/scenarios/cube-on-table.json
uv run worldforge scenario run examples/scenarios/spawn-and-move.json --state-dir .worldforge/worlds
```

世界 ID 是本地 JSON 文件的文件名（不含扩展名）。包含路径分隔符或路径遍历形式的输入会在访问文件系统之前被拒绝。

`world preflight` 为只读操作，用于检查世界状态目录、所请求的 `--world-id` 值、损坏的世界 JSON、无效的历史条目、对象包围盒一致性、已保存的运行清单、过期的运行目录、不安全的工件路径以及运行保留压力。JSON 输出默认可安全附加；当发现错误级别的状态时，命令以非零状态码退出。

`world migration-preview` 同样为只读操作。它接受持久化的世界 ID 或指向持久化/导出世界 JSON 的 `--source-path`，然后报告世界模式版本、所需的规范化变更、无效字段、不安全的 ID、包围盒修正、`can_apply_safely` 标志以及首个排查步骤。该命令不会重写状态；实际迁移仍需作为显式的后续步骤执行。

## 场景变更与预测

```bash
uv run worldforge world add-object <world-id> cube --x 0 --y 0.5 --z 0 --object-id cube-1
uv run worldforge world update-object <world-id> cube-1 --x 0.2 --y 0.5 --z 0
uv run worldforge world remove-object <world-id> cube-1
uv run worldforge world predict <world-id> --object-id cube-1 --x 0.4 --y 0.5 --z 0
uv run worldforge predict kitchen --provider mock --x 0.3 --y 0.8 --z 0.0 --steps 2
```

场景变更会追加类型化的历史条目。位置补丁会随姿态一并平移包围盒，预测操作则在提供方返回下一状态后追加提供方动作条目。

## 评估

```bash
uv run worldforge eval --suite physics --provider mock
uv run worldforge eval --suite planning --provider mock --format json
```

内置评估套件是确定性的契约检查，适用于适配器回归测试，而非物理保真度、媒体质量或真实世界安全性的声明依据。

## 基准测试

```bash
uv run worldforge benchmark --provider mock --iterations 5 --format json
uv run worldforge benchmark --provider mock --operation embed --input-file examples/benchmark-inputs.json
uv run worldforge benchmark --provider mock --operation predict --budget-file examples/benchmark-budget.json
```

预算文件可使延迟、吞吐量、成功率、重试次数和错误次数超限时以非零状态码退出。在发布说明、论文或公开声明中使用数据前，请务必保存基准测试工件。

## 机器人案例展示 TUI

```bash
scripts/robotics-showcase
scripts/robotics-showcase --no-tui
uv run worldforge runs list --status failed --artifact-type json
```

机器人案例展示报告是可选的 Textual 驱动界面，在保持 Textual 不进入基础包的同时，可视化预制宿主上的 LeRobot 与 LeWorldModel policy+score 运行。运行历史命令无需 Textual 即可使用，并会输出脱敏的恢复信息。

预期成功信号：所选流程达到已完成的运行工作区，检查器显示其已保存的工件路径。对于 `cosmos-policy`，回放应报告 `raw_action_shape: [50, 14]`、`translated_actions: 50` 及 `saved_replay_artifact: artifacts/cosmos-policy-replay.json`。对于 `gr00t-replay`，预期结果为 `translated_actions: 40` 及 `saved_replay_artifact: artifacts/gr00t-replay.json`。对于 `robotics-compare`，预期结果为 `total_translated_actions: 92` 及 `comparison_artifact: artifacts/robotics-policy-comparison.json`。首个排查步骤：打开已保存的运行工作区，检查 `logs/provider-events.jsonl` 以及特定流程的工件（`artifacts/cosmos-policy-replay.json`、`artifacts/gr00t-replay.json` 或 `artifacts/robotics-policy-comparison.json`）；如需检查实时提供方就绪状态，请运行 `uv run worldforge harness --connectors --format json`。

## 打包演示

签出安全演示使用注入的确定性运行时：

```bash
uv run worldforge-demo-leworldmodel
uv run worldforge-demo-lerobot
uv run --extra rerun worldforge-demo-rerun
uv run python scripts/demo_showcases.py list
uv run python scripts/demo_showcases.py run all --workspace-dir .worldforge/demo-showcases
```

这些演示无需安装可选模型运行时或下载检查点，即可验证 WorldForge 的提供方适配器、规划、执行、持久化、重载和事件路径。Rerun 演示需要 `rerun` 扩展，并将事件、世界状态、规划、三维对象框和基准测试指标记录到 `.rrd` 工件中。演示案例运行器保存十个由问题追踪驱动的工作流，包含 `run_manifest.json`、JSON 摘要、Markdown 摘要、安全的问题包以及首个排查步骤。详见[演示案例工作流](./demo-showcases.md)和[用例示例手册](./use-case-cookbook.md)。

## 可选运行时冒烟测试

真实 LeWorldModel 检查点打分：

```bash
scripts/lewm-real --checkpoint ~/.stable-wm/pusht/lewm_object.ckpt --device cpu
```

LeRobot 策略加 LeWorldModel 检查点打分回放：

```bash
scripts/robotics-showcase --health-only
scripts/robotics-showcase
uvx --from "rerun-sdk>=0.24,<0.32" rerun /tmp/worldforge-robotics-showcase/real-run.rrd
```

不启动 Textual 报告界面，直接打开运行的 TensorBoard 日志——适用于非交互式验证或从 shell 启动 TensorBoard：

```bash
uv run worldforge-open-tensorboard --logdir .worldforge/tensorboard/<run>
uv run worldforge-open-tensorboard --logdir .worldforge/tensorboard/<run> --probe --no-browser
```

完整参数说明请参阅 [TensorBoard 集成](./tensorboard.md)。

实时 GR00T 和 LeRobot 策略冒烟测试辅助工具：

```bash
uv run worldforge-smoke-cosmos-policy --help
uv run worldforge-smoke-jepa-wms --help
uv run worldforge-smoke-lerobot-leworldmodel --help
uv run python scripts/smoke_gr00t_policy.py --help
uv run python scripts/smoke_lerobot_policy.py --help
```

可选运行时命令需要宿主方自行提供运行时、检查点、凭证、观测数据和任务专用的动作转换器。WorldForge 不会将这些依赖添加到基础包中，也不会将注入的演示视为真实的上游推理结果。

更多详情：

- [机器人回放案例展示](./robotics-showcase.md)
- [机器人回放案例](./robotics-showcase.md)
- [示例与 CLI 命令](./examples.md)
- [用户与运维人员操作手册](./playbooks.md)

# WorldForge

<p align="center">
  <img
    alt="WorldForge banner with two robot mascots under a violet night sky"
    src="./docs/src/assets/img/worldforge-readme-banner.png"
    width="100%"
  />
</p>

<div align="center">

### 🌐 &nbsp; [English](./README.md) &nbsp; · &nbsp; **简体中文**

**面向物理 AI 的世界模型规划循环 harness。**

WorldForge 是 Stable World Model 等「模型训练」栈的对位补充：那些栈帮助研究者*训练*世界模型，
WorldForge 帮助机器人与物理 AI 构建者在世界模型之上*组合、评估并基准测试*工作流，从而为具体任务
挑选提供方与配置。

整个框架围绕一个主干循环：**用动作条件化的预测世界模型，在潜空间中对动作候选进行规划与打分。**
检查点、凭据、机器人控制器与部署仍由宿主方持有。

Python **3.13** · MIT · 唯一运行时依赖 `httpx` · [PyPI: `worldforge-ai`](https://pypi.org/project/worldforge-ai/)

[![CI](https://img.shields.io/github/actions/workflow/status/AbdelStark/worldforge/ci.yml?branch=main&label=CI&style=for-the-badge)](https://github.com/AbdelStark/worldforge/actions/workflows/ci.yml)
[![Docs](https://img.shields.io/github/actions/workflow/status/AbdelStark/worldforge/pages.yml?branch=main&label=docs&style=for-the-badge)](https://abdelstark.github.io/worldforge/)
[![Python](https://img.shields.io/badge/python-3.13-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://github.com/AbdelStark/worldforge/blob/main/pyproject.toml)
[![PyPI](https://img.shields.io/pypi/v/worldforge-ai?style=for-the-badge&label=pypi&color=3f7cac)](https://pypi.org/project/worldforge-ai/)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg?style=for-the-badge)](./LICENSE)
[![Coverage](https://img.shields.io/badge/coverage-%E2%89%A590%25-brightgreen?style=for-the-badge)](./.github/workflows/ci.yml)
[![Typed](https://img.shields.io/badge/typed-py.typed-3f7cac?style=for-the-badge)](./src/worldforge/py.typed)
[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json&style=for-the-badge)](https://github.com/astral-sh/ruff)
[![uv](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/uv/main/assets/badge/v0.json&style=for-the-badge)](https://github.com/astral-sh/uv)
[![Status: pre-1.0](https://img.shields.io/badge/status-pre--1.0%20beta-orange?style=for-the-badge)](#项目状态)

[**快速开始**](#快速开始) ·
[**文档**](https://abdelstark.github.io/worldforge/) ·
[**文档导航**](https://abdelstark.github.io/worldforge/docs-map/) ·
[**提供方**](#提供方接口) ·
[**架构**](#架构) ·
[**贡献**](#贡献) ·
[**支持**](./SUPPORT.md) ·
[**安全**](./SECURITY.md)

</div>

```text
observe
  → policy 提出候选动作
  → predict 展开未来  /  score 作为代价预言机排序
  → LatentMPCController 选出最低代价动作块   （CEM、滚动时域）
  → 执行、评估、再规划
```

世界模型保持为纯预言机。控制器保持为纯优化器。每个适配器只声明它真正实现了的能力。

## 快速开始

```bash
uv add worldforge-ai
# 或：pip install worldforge-ai
```

```python
from worldforge import Action, LatentMPCController, PlannerConfig, WorldForge

forge = WorldForge()

# 在 JSON 世界状态字典上做动作条件化的前向动力学。
prediction = forge.predict(
    {"scene": {"objects": {}}},
    Action.move_to(0.3, 0.8, 0.0),
    provider="mock",
)

# 潜空间 MPC：采样时域、打分、保留精英、返回代价最低的动作块。
plan = LatentMPCController(
    forge=forge,
    score_provider="mock",
    config=PlannerConfig(
        horizon=1,
        num_samples=64,
        num_iterations=5,
        num_elites=8,
        action_parameter_bounds={"x": (-1.0, 1.0), "y": (-1.0, 1.0), "z": (-1.0, 1.0)},
        seed=0,
    ),
).plan_step(
    observation_info={"point": [0.0, 0.8, 0.0]},
    goal_info={"target": [0.3, 0.8, 0.0]},
)

print(prediction.physics_score, plan.best_score, plan.actions[0])
```

`mock` 提供方不需要凭据、GPU、检查点或机器人。成功的标志是得到一个物理分数，以及一个在滚动时域下
选出最低代价动作的规划结果。

```bash
uv run worldforge doctor --registered-only
uv run python examples/latent_mpc_planning.py
uv run worldforge predict kitchen --provider mock --x 0.3 --y 0.8 --z 0.0 --steps 2
uv run worldforge eval --suite planning --provider mock --format json
uv run worldforge benchmark --provider mock --operation predict --operation embed
```

可选 extra：`uv add "worldforge-ai[harness]"`（Textual 机器人报告）、
`uv add "worldforge-ai[rerun]"`（事件/工件记录）、
`uv add "worldforge-ai[tensorboard]"`（LeWorldModel 检查点检视）。

仅支持 Python 3.13。从源安装：`uv add "worldforge-ai @ git+https://github.com/AbdelStark/worldforge"`。
本地检出：`git clone https://github.com/AbdelStark/worldforge.git && cd worldforge && uv sync --group dev`。

<details>
<summary><strong>CLI 接口</strong> — 诊断、契约、评估与预算闸门</summary>

```bash
uv run worldforge examples
uv run worldforge provider list
uv run worldforge provider info mock
uv run worldforge provider contract mock --format json
uv run worldforge negotiate --list
uv run worldforge benchmark --provider mock --operation embed --input-file examples/benchmark-inputs.json
uv run worldforge benchmark --provider mock --operation predict --budget-file examples/benchmark-budget.json
```

`eval` 与 `benchmark` 用于比较配置。预算文件把成功率、延迟与吞吐阈值变成非零退出的 CLI 闸门。

完整参考：[Python API](https://abdelstark.github.io/worldforge/api/python/) ·
[CLI](https://abdelstark.github.io/worldforge/cli/) ·
[示例](https://abdelstark.github.io/worldforge/examples/)

</details>

## 机器人案例展示

门面级机器人演示将 [Hugging Face LeRobot](https://github.com/huggingface/lerobot) 策略与
[LeWorldModel](https://github.com/lucas-maes/le-wm) 检查点组合起来。LeRobot 提出 PushT 动作候选，
WorldForge 将其桥接到 LeWorldModel 原生张量，LeWorldModel 打分，WorldForge 选出最低代价动作块并做
本地 mock 回放。

这是仿真/回放规划：真实的策略推理、真实的打分模型推理、类型化组合、候选排序与可视化回放。硬件控制、
安全互锁、机器人控制器与任务预处理仍由宿主方持有。

若需要不接真实机器人的决策证据，Go2 Air ControlBench 轨迹回放会对公开 DecisionTrace 夹具重新排序，
并报告相对最佳反事实指令的原生里程计 regret。它不导入 DimOS、Unitree SDK，也不连接硬件：

```bash
uv run python examples/go2-controlbench-decisiontrace/run.py
```

<div align="center">
<table>
  <tr>
    <td width="50%">
      <img src="./docs/src/assets/img/robotics-showcase-lerobot-leworldmodel-2.png" alt="WorldForge 机器人案例展示 TUI：流水线、运行时指标与张量契约" width="100%" />
      <br />
      <sub><strong>流水线：</strong>真实策略、真实打分检查点、WorldForge 规划器、本地 mock 回放。</sub>
    </td>
    <td width="50%">
      <img src="./docs/src/assets/img/robotics-showcase-lerobot-leworldmodel-1.png" alt="WorldForge 机器人案例展示 TUI：机械臂示意、候选排序与桌面回放" width="100%" />
      <br />
      <sub><strong>决策：</strong>候选排序、机械臂示意、固定桌面回放。</sub>
    </td>
  </tr>
</table>
</div>

```bash
scripts/robotics-showcase
uv run python scripts/demo_showcases.py run all --workspace-dir .worldforge/demo-showcases
```

第一条命令默认打开分步揭示的 Textual 报告，写入
`/tmp/worldforge-robotics-showcase/real-run.json`，并记录
`/tmp/worldforge-robotics-showcase/real-run.rrd`。在 TUI 中按 `o` 打开 Rerun。
`--no-tui` 输出终端报告；`--json-only` 用于自动化；`--health-only` 是非变更的预检。
用 `--lewm-revision <40-char-commit-sha>` 钉住自动构建的 LeWorldModel 资产。

第二条命令可在干净检出中运行，不需要凭据或可选模型运行时。

走读：[机器人回放展示](https://abdelstark.github.io/worldforge/robotics-showcase/) ·
[技术深潜](https://abdelstark.github.io/worldforge/robotics-showcase-deep-dive/) ·
[Rerun](https://abdelstark.github.io/worldforge/rerun/) ·
[演示工作流](https://abdelstark.github.io/worldforge/demo-showcases/)

<details>
<summary><strong>TUI、Rerun 与线上 CI</strong></summary>

```bash
scripts/robotics-showcase --no-tui
uv run --extra rerun worldforge-demo-rerun
uvx --from "rerun-sdk>=0.24,<0.32" rerun /tmp/worldforge-robotics-showcase/real-run.rrd
```

Rerun 是可选的可观测 extra，不是提供方能力，也不在基础依赖中。干净检出演示会记录事件、快照、规划、
轨迹与基准指标。机器人案例展示记录真实的 PushT 策略+打分运行。

`.github/workflows/robotics-showcase.yml` 在拉取请求与 `main` 上以
`scripts/robotics-showcase --json-only --no-tui --no-rerun` 运行。它缓存 Hugging Face 与
LeWorldModel 资产；CI 上传 JSON 与 `run_manifest.json` 证据，不上传检查点。

</details>

## 能力模型

「能力」命名的是适配器真正支持的操作，而不是上游模型的品牌。未知名称会报错。未实现的调用会报错。
空结果不能代替「未实现」。

| 能力 | 契约 | 示例提供方 |
| --- | --- | --- |
| `predict` | `状态 + 动作 → 预测状态` | `mock` |
| `score` | `观测 + 目标 + 候选 → 排序后的候选` | `leworldmodel`、`mock` |
| `policy` | `观测 + 指令 → 动作块` | `lerobot`、`gr00t`、`cosmos-policy` |
| `embed` | 观测 → 嵌入向量 | `mock` |
| `plan` | 已组合接口上的门面 | WorldForge / `LatentMPCController` |

既可以注册完整的 `BaseProvider`，也可以注册狭窄的 `Cost`、`Policy`、`Predictor` 或 `Embedder`
协议实现。协议路径只有一个 `name`、可选的 profile 元数据，以及所声明能力背后的那一个方法。

LeWorldModel 是打分提供方，不是视频生成器。Cosmos-Policy、GR00T 与 LeRobot 是策略提供方，不是预测式
世界模型。规划主干组合这些狭窄接口，而不是把每个运行时都当成通用媒体或对话模型。

## 提供方接口

| 提供方 | 成熟度 | 能力接口 | 注册触发 | 运行时所有权 |
| --- | --- | --- | --- | --- |
| `mock` | `stable` | `predict`、`score`、`embed` | 始终注册 | 仓库内的确定性本地提供方 |
| [`cosmos-policy`](https://abdelstark.github.io/worldforge/providers/cosmos-policy/) | `beta` | 无（`policy` 需要宿主方提供 `action_translator`） | `COSMOS_POLICY_BASE_URL` | WorldForge 校验 `/act` 的请求/响应与规划组合；宿主方负责 Cosmos-Policy 的可达性/CUDA/运行时、ALOHA 观测构建，以及将原始 14 维行转换为可执行的 `Action` 对象 |
| [`leworldmodel`](https://abdelstark.github.io/worldforge/providers/leworldmodel/) | `stable` | `score` | `LEWORLDMODEL_POLICY` 或 `LEWM_POLICY` | 宿主方安装官方 LeWM 加载路径（`stable_worldmodel.policy.AutoCostModel`）、torch 以及兼容检查点 |
| [`gr00t`](https://abdelstark.github.io/worldforge/providers/gr00t/) | `beta` | `policy` | `GROOT_POLICY_HOST` | 宿主方运行或访问 Isaac GR00T 策略服务器 |
| [`lerobot`](https://abdelstark.github.io/worldforge/providers/lerobot/) | `stable` | `policy` | `LEROBOT_POLICY_PATH` 或 `LEROBOT_POLICY` | 宿主方安装 LeRobot 以及兼容的策略检查点 |
| [`jepa`](https://abdelstark.github.io/worldforge/providers/jepa/) | `experimental` | `score` | `JEPA_MODEL_NAME` | 宿主方提供 torch、facebookresearch/jepa-wms 运行时依赖以及任务预处理 |
| [`genie`](https://abdelstark.github.io/worldforge/providers/genie/) | `scaffold` | 脚手架 | `GENIE_API_KEY` | 能力失败即关闭的预留位；Project Genie 没有受支持的自动化 API 契约 |

`jepa` 是面向宿主方持有的 `facebookresearch/jepa-wms` torch-hub 运行时的仅打分适配器。
`genie` 仍是能力关闭的预留位。可执行脚手架候选项在拥有经过验证的运行时路径、类型化解析器覆盖、
请求限制与文档之前，都不会进入软件包导出与自动注册。

## 架构

```text
┌──────────────────────────────────────────────────────────┐
│  宿主应用 / CLI                                           │
└────────────────────────────┬─────────────────────────────┘
                             │
                             ▼
┌──────────────────────────────────────────────────────────┐
│  WorldForge                                              │
│  目录 · 能力分发 · 诊断 · 评估                             │
│                                                          │
│     LatentMPCController   （CEM / 滚动时域）               │
└──────────────┬─────────────────────────────┬─────────────┘
               │ score / predict / policy    │
               ▼                             ▼
┌───────────────────────────┐    ┌─────────────────────────┐
│  提供方适配器              │    │  类型化结果              │
│  契约 · 校验 · 事件        │───▶│  分数、规划、载荷        │
└──────────────┬────────────┘    └─────────────────────────┘
               │
               ▼
┌──────────────────────────────────────────────────────────┐
│  上游运行时（宿主方持有）                                   │
│  mock · LeWorldModel · LeRobot · GR00T · Cosmos-Policy   │
└──────────────────────────────────────────────────────────┘
```

没有符号化的 `World` 运行时，也没有内置世界存储。规划在普通 JSON 世界状态字典上运行。持久化、机器人
执行与可选 ML 运行时由宿主方持有。

| WorldForge 负责 | 宿主方负责 |
| --- | --- |
| 能力契约、校验、失败即关闭的分发 | 凭据、端点、检查点、CUDA |
| CEM / 滚动时域优化器 | 动作空间映射、预处理、安全互锁 |
| 评估、基准、诊断、轨迹 | 经验任务声明、机器人控制、遥测 |

## 项目状态

WorldForge 目前是 **pre-1.0 beta**（`0.5.0`）。公共 API 在契约需要收紧时仍可能变化；破坏性变更会记入
[changelog](./CHANGELOG.md)。

| 这是 | 这不是 |
| --- | --- |
| 面向提供方规划循环的集成层 | 托管服务、模型 API 或训练框架 |
| 类型化、失败即关闭的能力与可记录运行 | 对物理保真或机器人安全的声明 |
| 可在干净检出运行的 `mock`，外加宿主方持有的可选运行时 | 基础依赖中的 torch / LeRobot / GR00T / CUDA |
| 评估与基准的*契约* harness | 排行榜或媒体质量指标 |

[声明-证据对照表](https://abdelstark.github.io/worldforge/claim-evidence-map/) 把 README 级能力与运行时
声明对应到测试、命令、工件与非声明。

## 开发

```bash
uv sync --group dev
uv lock --check
uv run ruff check src tests examples scripts
uv run ruff format --check src tests examples scripts
uv run python scripts/generate_provider_docs.py --check
uv run python scripts/check_docs_commands.py
uv run python scripts/check_docs_snippets.py
uv run python scripts/check_wrapper_portability.py
uv run python scripts/check_optional_import_boundaries.py
uv run python scripts/check_core_performance.py
uv run mkdocs build --strict
uv run pytest
uv run --extra harness pytest --cov=src/worldforge --cov-report=term-missing --cov-fail-under=90
bash scripts/test_package.sh
uv build --out-dir dist --clear --no-build-logs
```

打标签之前，还需运行锁定依赖审计，并生成发布证据、发布说明草稿与质量仪表盘。原始细节会脱敏，使宿主
本地路径、签名 URL 与密钥形态的键不会进入可附带输出。扩展闸门与排查步骤见
[操作手册](https://abdelstark.github.io/worldforge/playbooks/#9-prepare-a-release-or-public-branch)。
如果在闸门开始之前本地环境搭建失败，请运行
`uv run python scripts/contributor_doctor.py --format markdown`。

```bash
uv run python scripts/scaffold_provider.py "Acme WM" \
  --taxonomy "JEPA latent predictive world model" \
  --implementation-status scaffold \
  --planned-capability score
```

贡献者指南：[CONTRIBUTING.md](./CONTRIBUTING.md)。仓库智能体上下文：[AGENTS.md](./AGENTS.md)。

## 引用 WorldForge

```bibtex
@software{worldforge,
  title   = {WorldForge: An integration layer for physical-AI world models},
  author  = {AbdelStark and {WorldForge contributors}},
  year    = {2026},
  url     = {https://github.com/AbdelStark/worldforge},
  version = {0.5.0}
}
```

## 贡献

欢迎提交 issue、参与讨论与发起拉取请求。请阅读 [CONTRIBUTING.md](./CONTRIBUTING.md)，并在发送补丁之前
为非琐碎改动先开一个 issue。提供方相关工作请从
[提供方编写指南](https://abdelstark.github.io/worldforge/provider-authoring-guide/)与
[操作手册](https://abdelstark.github.io/worldforge/playbooks/)开始。外部采用方可以通过
[采用案例研究模板](./docs/src/adoption-case-studies/README.md)分享集成故事。

## 许可证

WorldForge 基于 [MIT 许可证](./LICENSE) 发布。

## 资源

| 资源 | 链接 |
| --- | --- |
| 文档 | <https://abdelstark.github.io/worldforge/> |
| 快速开始 | <https://abdelstark.github.io/worldforge/quickstart/> |
| 架构 | <https://abdelstark.github.io/worldforge/architecture/> |
| 操作手册 | <https://abdelstark.github.io/worldforge/playbooks/> |
| 提供方编写 | <https://abdelstark.github.io/worldforge/provider-authoring-guide/> |
| 世界模型分类法 | <https://abdelstark.github.io/worldforge/world-model-taxonomy/> |
| Rerun | <https://abdelstark.github.io/worldforge/rerun/> |
| 质量 | <https://abdelstark.github.io/worldforge/quality/> |
| 声明证据 | <https://abdelstark.github.io/worldforge/claim-evidence-map/> |
| 贡献 | [CONTRIBUTING.md](./CONTRIBUTING.md) |
| 安全 | [SECURITY.md](./SECURITY.md) |
| 仓库 | <https://github.com/AbdelStark/worldforge> |
| Issues | <https://github.com/AbdelStark/worldforge/issues> |

## 贡献者

完整名单见英文版 [README.md](./README.md#contributors)（由 all-contributors 自动维护）。

由 [Abdel](https://github.com/AbdelStark) 与 WorldForge 社区用心打造。

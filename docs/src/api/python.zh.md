# Python API

有关兼容性等级、弃用预期以及工件模式迁移规则，请参阅
[公共 API 稳定性](../api-stability.md)。

## 入口点

<!-- worldforge-snippet: execute -->
```python
from worldforge import (
    Action,
    ActionPolicyResult,
    ActionScoreResult,
    BenchmarkBudget,
    Cost,
    Policy,
    load_benchmark_inputs,
    RunnableModel,
    WorldForge,
)
```

## `WorldForge`

顶层框架对象，负责：

- 提供方注册
- 世界状态的创建与持久化
- 预测、嵌入、动作打分及动作策略辅助功能
- 提供方配置文件与环境诊断

常用检查辅助方法：

<!-- worldforge-snippet: execute -->
```python
from worldforge import Action, WorldForge

forge = WorldForge()

profiles = forge.builtin_provider_profiles()
doctor = forge.doctor()

print(profiles[0].supported_tasks)
print(doctor.issues)
```

提供方能力过滤器严格执行。有效的能力名称为 `predict`、`embed`、`plan`、`score` 和 `policy`；未知名称会抛出
`WorldForgeError`，而不会因拼写错误而返回空结果。

## 能力协议

提供方适配器仍可继承 `BaseProvider`，但轻量级集成也可以注册单个能力对象。
该对象声明一个非空的 `name`、可选的 `ProviderProfileSpec`，以及与其实现的能力
恰好对应的方法。

<!-- worldforge-snippet: execute -->
```python
from worldforge import ActionScoreResult, WorldForge
from worldforge.providers import ProviderProfileSpec


class LocalCost:
    name = "local-cost"
    profile = ProviderProfileSpec(description="Local score model")

    def score_actions(self, *, info, action_candidates):
        return ActionScoreResult(provider=self.name, scores=[0.2, 0.7], best_index=0)


forge = WorldForge()
forge.register_cost(LocalCost())

result = forge.score_actions(cost="local-cost", info={}, action_candidates=[{}, {}])
print(result.best_index)
```

同样的模式适用于 `register_policy`、`register_predictor` 和 `register_embedder`。
`forge.register(...)` 通过协议成员关系分发纯对象，而
`RunnableModel(...)` 可将多个能力实现组合在一起。已注册的协议实现将出现在
`providers()`、`provider_profile(...)`、`doctor(...)`、规划以及基准测试框架中。

有关注册进程内纯对象的策略+打分可运行示例，请参阅
[能力协议快速入门](../capability-protocols-quickstart.md)。

能力协议实现和 `BaseProvider` 子类还可以暴露由提供方持有的
`preflight`、`warmup` 和 `teardown` 钩子，这些钩子返回 `ProviderLifecycleResult`。
诊断功能通过 `doctor()` 和 `provider_lifecycle_status(...)` 公开聚合后的
`ProviderLifecycleStatus`，而不改变能力方法契约。

## 持久化

```python
from worldforge import WorldForge

forge = WorldForge(state_dir=".worldforge/worlds")
world = forge.create_world("lab", provider="mock")
world_id = forge.save_world(world)

payload = forge.export_world(world_id)
copy = forge.import_world(payload, new_id=True, name="lab-copy")
copy_id = forge.save_world(copy)

forge.delete_world(world_id)
print(forge.list_worlds(), copy_id)
```

`save_world(...)`、`load_world(...)`、`import_world(...)`、`fork_world(...)` 和
`delete_world(...)` 在操作文件系统之前均会验证世界状态标识符。删除操作仅移除
文件安全的世界状态 ID 所对应的本地 JSON 文件；访问不存在的世界状态时会抛出
`WorldStateError`，而不会被视为成功的空操作。

## 可观测性

<!-- worldforge-snippet: skip-illustrative -->
```python
import logging
from pathlib import Path

from worldforge import WorldForge
from worldforge.workflow_trace import workflow_trace_from_provider_events
from worldforge.observability import (
    JsonLoggerSink,
    ProviderMetricsExporterSink,
    OpenTelemetryProviderEventSink,
    ProviderMetricsSink,
    RunJsonLogSink,
    compose_event_handlers,
)
from worldforge.rerun import RerunArtifactLogger, RerunEventSink, RerunRecordingConfig, RerunSession

run_id = "demo-run"
metrics = ProviderMetricsSink()
host_metrics_exporter = ...  # supplied by your service
forge = WorldForge(
    event_handler=compose_event_handlers(
        JsonLoggerSink(logger=logging.getLogger("demo.worldforge"), extra_fields={"run_id": run_id}),
        RunJsonLogSink(Path(".worldforge") / "runs" / run_id / "provider-events.jsonl", run_id),
        ProviderMetricsExporterSink(host_metrics_exporter),
        metrics,
    )
)

world = forge.create_world_from_prompt("cube", provider="mock")
world.predict(Action(type="move_to", parameters={"target": {"x": 0.2, "y": 0.5, "z": 0.0}}))
print(metrics.get("mock", "predict").to_dict())
```

提供方事件默认对日志安全。`target` 字段保留端点或工件路径上下文，
但会去除 URL 用户信息、查询字符串和片段；消息、元数据及 Sink 附加字段会
脱敏明显的 Bearer 令牌、API 密钥、签名、密码和已签名 URL。`RunJsonLogSink`
每行追加一个 JSON 对象，并为每条记录标记 `run_id` 以便与运行清单关联。
`OpenTelemetryProviderEventSink` 为可选项，接受注入的宿主追踪器，因此基础包
不会导入 OpenTelemetry 或配置收集器。`ProviderMetricsExporterSink` 同样为可选项，
接受由宿主方持有的指标导出器，该导出器具有针对提供方、操作、阶段、状态类别
和能力的有界标签。

组合操作可以发出安全的工作流追踪工件。`Plan.metadata["workflow_trace"]`
记录规划步骤，评估报告导出 `workflow_trace.json` 和 `workflow_trace.md`，
而 `workflow_trace_from_provider_events(...)` 可将发出的 `ProviderEvent` 记录
压缩为带模式版本的追踪，而不存储原始提示词、张量、凭据或控制器遥测数据。

Rerun 可作为可选的可观测性和工件层使用：

<!-- worldforge-snippet: skip-host-owned -->
```python
session = RerunSession(RerunRecordingConfig(save_path=".worldforge/rerun/run.rrd"))
rerun_events = RerunEventSink(session=session)
artifacts = RerunArtifactLogger(session=session)

forge = WorldForge(event_handler=rerun_events)
world = forge.create_world("lab", provider="mock")
plan = world.plan("move the first object right")

artifacts.log_world(world)
artifacts.log_plan(plan)
artifacts.log_workflow_trace(plan.metadata["workflow_trace"])
session.close()
```

通过 `worldforge-ai[rerun]` 安装。Rerun 不是提供方，不声明 WorldForge 能力。

## 动作打分

暴露 `score` 能力的提供方可以对候选动作序列进行排序，而无需声明支持预测或策略能力。LeWorldModel 使用此路径，因为其上游运行时是一个 JEPA 代价模型。

<!-- worldforge-snippet: skip-host-owned -->
```python
from worldforge import WorldForge

forge = WorldForge()
result = forge.score_actions(
    "leworldmodel",
    info={
        "pixels": [[[0.0, 0.1, 0.2]]],
        "goal": [[[0.8, 0.9, 1.0]]],
        "action": [[[0.0, 0.0, 0.0]]],
    },
    action_candidates=[
        [
            [[0.0], [0.1], [0.2]],
            [[0.3], [0.2], [0.1]],
        ]
    ],
)

print(result.best_index, result.best_score)
```

`ActionScoreResult` 验证分数是否有限，暴露 `best_index` 和 `best_score`，
并要求 `best_index` 与 `lower_is_better` 匹配，使调用方无需从提供方专属文档中推断分数方向。
元数据必须为 JSON 原生类型：字典键为字符串，数值为有限数，对象实例或元组
将被拒绝而不会被静默强制转换。

规划器可以在调用方提供与每个已打分候选项相对应的 WorldForge 动作时，
使用相同的打分接口。默认情况下，这些动作会被序列化后传递给打分提供方。
当打分器期望提供方原生张量或潜在候选负载时，请显式传递 `score_action_candidates`：

```python
from worldforge import action_candidates_to_score_payload, bounded_move_grid_candidates

candidate_actions = bounded_move_grid_candidates(
    x_bounds=(0.1, 0.7),
    y_bounds=(0.5, 0.5),
    z_bounds=(0.0, 0.0),
    x_steps=3,
    y_steps=1,
    z_steps=1,
)
plan = world.plan(
    goal="choose the lowest-cost LeWorldModel action",
    provider="leworldmodel",
    planner="leworldmodel-mpc",
    candidate_actions=candidate_actions,
    score_info=info,
    score_action_candidates=action_candidates_to_score_payload(candidate_actions),
    execution_provider="mock",
)

print(plan.actions, plan.metadata["score_result"]["best_index"])
```

基于打分的规划不会要求打分提供方预测状态。`Plan.predicted_states` 保持为空，
打分详情存储在 `Plan.metadata` 中，当打分提供方未实现 `predict()` 时，
`execute_plan(...)` 使用 `execution_provider`。规划器要求每个候选动作计划对应一个
分数；分数数量不匹配会在返回计划之前失败。

候选辅助函数与提供方无关，返回经验证的 `Action` 序列。使用
`cartesian_offset_candidates(...)` 获取相对移动候选项，`object_near_candidates(...)`
获取参照物相对位置，`swap_action_candidates(...)` 获取两对象交换候选项，
`bounded_move_grid_candidates(...)` 获取包含端点的笛卡尔网格。这些函数不预处理图像、
不推断提供方原生张量、不重新解释机器人动作空间；当打分提供方需要任务专属张量
而非序列化 `Action` 负载时，请显式传递 `score_action_candidates`。

若要运行保留原始策略动作、对生成候选项进行排序，并展示无效边界及缺少转换器
失败情况的策略+打分候选实验室（checkout 安全），请执行：

```bash
uv run python scripts/demo_showcases.py run policy-score-candidate-lab --workspace-dir .worldforge/demo-showcases --overwrite
```

## 动作策略

暴露 `policy` 能力的提供方可从观测中选取可执行的动作块。
NVIDIA Isaac GR00T 使用此接口，因为它是一个具身视觉-语言-动作（VLA）策略，
而非预测式世界模型。

```python
result = forge.select_actions(
    "gr00t",
    info={
        "observation": {
            "video": {"front": video_array},
            "state": {"eef": state_array},
            "language": {"task": [["pick up the cube"]]},
        },
        "embodiment_tag": "LIBERO_PANDA",
        "action_horizon": 16,
    },
)

print(result.actions, result.raw_actions)
```

`ActionPolicyResult` 验证提供方至少返回一个 WorldForge `Action`，
保留提供方原生原始动作用于调试，并可携带多个候选动作块供下游打分使用。
保留的原始动作和元数据必须为 JSON 原生类型，以便运行工件可以序列化，
而不出现隐藏的编码器行为。

仅策略规划：

```python
plan = world.plan(
    goal="pick up the cube",
    provider="gr00t",
    policy_info=policy_info,
    execution_provider="mock",
)
```

策略加打分规划：

```python
plan = world.plan(
    goal="choose the lowest-cost policy candidate",
    policy_provider="gr00t",
    score_provider="leworldmodel",
    policy_info=policy_info,
    score_info=lewm_info,
    execution_provider="mock",
)
```

默认情况下，WorldForge 在调用打分提供方之前，将策略候选项序列化为
`Action.to_dict()` 负载列表。当打分器需要提供方原生张量或潜在候选格式时，
请传递 `score_action_candidates`。宿主方仍然负责具身专属的动作转换
以及任何模型原生映射。

## `World`

有状态的运行时对象，负责：

- 场景对象管理
- 预测
- 比较
- 使用启发式字符串或类型化 `StructuredGoal` 进行规划
- 评估

示例：

```python
from worldforge import Position, StructuredGoal

plan = world.plan(
    goal_spec=StructuredGoal.object_at(
        object_name="red_mug",
        position=Position(0.3, 0.8, 0.0),
    )
)
```

类型化结构化目标涵盖：

- `StructuredGoal.object_at(...)`
- `StructuredGoal.object_near(...)`
- `StructuredGoal.spawn_object(...)`
- `StructuredGoal.swap_objects(...)`

## 评估

```python
from worldforge.evaluation import EvaluationSuite

print(EvaluationSuite.builtin_names())

suite = EvaluationSuite.from_builtin("planning")
report = suite.run_report(["mock"], forge=forge)
print(report.results[0].passed)
print(report.to_markdown())

gallery = report.failure_gallery()
print(gallery.to_json())
```

失败的报告通过 `failure_gallery()` 以及
`report.artifacts()["failure_gallery.json"]` / `["failure_gallery.md"]`
暴露具有代表性的、经脱敏处理的典型案例。该画廊用于确定性的契约分类，
不对提供方进行排名，也不声明物理保真度。

自定义确定性评估套件使用相同的公共报告路径：

```python
from worldforge.evaluation import EvaluationContext, EvaluationScenario, EvaluationSuite


def check_world(context: EvaluationContext):
    return context.outcome(
        score=1.0,
        passed=context.world.object_count == 0,
        metrics={"object_count": context.world.object_count},
    )


custom = EvaluationSuite.custom(
    suite_id="custom-empty-world",
    name="Custom Empty World Evaluation",
    suite_version="custom-empty-world:1",
    claim_boundary="Checkout-safe custom example; not a model-quality claim.",
    scenarios=[
        EvaluationScenario.from_callable(
            name="empty-world-readable",
            description="Checks that a new world can be inspected.",
            evaluator=check_world,
        )
    ],
)
report = custom.run_report("mock", forge=forge)
print(report.provenance.suite_version)
```

`EvaluationSuite.register(...)` 和 `EvaluationSuite.from_registered(...)` 提供
进程级注册表，供希望为自定义评估套件命名的宿主应用使用。

## 基准测试

```python
from worldforge import BenchmarkBudget, ProviderBenchmarkHarness, load_benchmark_inputs

harness = ProviderBenchmarkHarness(forge=forge)
inputs = load_benchmark_inputs(
    {
        "embedding_text": "benchmark cube state",
    }
)
report = harness.run(
    ["mock"],
    operations=["predict", "embed"],
    iterations=5,
    inputs=inputs,
)
print(report.to_json())

budget = BenchmarkBudget.from_dict({"max_p95_latency_ms": 25.0})
print(report.evaluate_budgets([budget]).passed)
```

## 提供方契约测试

```python
from worldforge.providers import MockProvider
from worldforge.testing import assert_provider_contract

report = assert_provider_contract(MockProvider())
print(report.to_dict())
```

对于打分提供方，请传递提供方专属的打分负载，以便辅助方法能够调用
`score_actions(...)`：

```python
report = assert_provider_contract(
    provider,
    score_info={"observation": [[0.0]], "goal": [[1.0]]},
    score_action_candidates=[[[[0.0]]]],
)
```

对于策略提供方，请传递提供方专属的策略观测数据：

```python
report = assert_provider_contract(provider, policy_info=policy_info)
```

## 公共失败模式

WorldForge 为运行时工作流提供三个公共异常族：

- `WorldForgeError`：无效的调用方输入、无效的模型值、不支持的格式以及无效的
  本地配置值，包括用于持久化查找的非文件安全世界状态 ID。
- `WorldStateError`：格式错误的持久化状态或提供方提供的世界状态，无法安全还原
  或应用，包括无效的场景对象映射和无效的历史记录条目。
- `ProviderError`：提供方凭据、传输故障、不支持的提供方操作、格式错误的上游响应、
  提供方专属输入限制、可选依赖故障以及格式错误的模型打分或策略输出。

面向提供方的工作流在返回部分结果之前会失败：

```python
from worldforge import Action, WorldForge
from worldforge.providers import ProviderError

forge = WorldForge()
world = forge.create_world_from_prompt("a cube on a table")

try:
    prediction = world.predict(
        Action(type="move", target="cube", parameters={"dx": 0.1, "dy": 0.0, "dz": 0.0}),
        provider="mock",
    )
except ProviderError as exc:
    # Inspect emitted ProviderEvent records for transport status and attempts.
    raise
```

重要的边界检查：

- `Position`、`Rotation`、请求策略、提供方事件、嵌入向量、打分结果、策略结果以及
  预测负载指标拒绝非有限数值。
- `Action.parameters`、`SceneObject.metadata`、提供方事件元数据、打分元数据、
  策略原始动作、策略元数据以及预测负载状态/元数据拒绝非 JSON 原生值，而不是
  接受那些仅在持久化时才会失败的对象实例。
- 评估和基准测试结果对象在渲染 JSON、Markdown 或 CSV 工件之前，会验证有限指标、
  分数范围、连贯计数以及 JSON 原生指标。
- `World.add_object(...)` 拒绝重复的场景对象 ID。
- 导入的或由提供方提供的世界状态拒绝与嵌入式对象 ID 不一致的场景对象键。
- LeWorldModel 打分要求 `pixels`、`goal` 和 `action` 信息字段，动作候选项的形状为
  `(batch=1, samples, horizon, action_dim)`，可选的 `stable_worldmodel` 和 `torch`
  运行时依赖，每个候选样本返回一个分数，且模型分数必须为有限数。

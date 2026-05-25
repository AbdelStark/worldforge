# Cosmos 提供方

能力：`generate`

分类：物理 AI 视频/世界生成适配器

`cosmos` 是一个 HTTP 适配器，用于对接可达的 NVIDIA Cosmos NIM 部署。它向 `/v1/infer` 发送文本、图像或视频条件生成请求，并返回经过验证的 `VideoClip`。

```text
prompt + GenerationOptions
  -> Cosmos /v1/infer
  -> base64 video response
  -> VideoClip
```

WorldForge 将 Cosmos 视为媒体生成提供方。它不暴露 `predict`、`score` 或 `policy`，因为该适配器不会返回经过验证的 WorldForge 状态转换、候选代价或可执行的动作块。

## 运行时归属

WorldForge 负责请求构造、类型化超时/重试策略、响应验证、视频解码以及提供方事件。

宿主方负责：

- Cosmos 部署与端点可达性
- 可选的 NVIDIA 持有人令牌
- 端点后端的模型可用性
- 生成工件的持久化
- 端点周边的运营遥测与告警

## 配置

- `COSMOS_BASE_URL`：自动注册所必需。示例：`http://localhost:8000`。
- `NVIDIA_API_KEY`：可选的持有人令牌，以 `Authorization: Bearer ...` 形式发送。

运行时清单：
`src/worldforge/providers/runtime_manifests/cosmos.json` 记录了所需端点、可选持有人令牌、由宿主方持有的工件、最小实时冒烟测试命令，以及预期的健康信号。

程序化构造：

```python
from worldforge.providers import CosmosProvider

provider = CosmosProvider(base_url="http://localhost:8000")
```

## 请求契约

```python
from worldforge import GenerationOptions

clip = forge.generate(
    "a robot arm moves a mug across a table",
    provider="cosmos",
    duration_seconds=3.0,
    options=GenerationOptions(
        image="/path/to/initial-frame.png",
        size="1280x720",
        fps=24,
        seed=4,
    ),
)
```

生成规则：

- `duration_seconds` 必须大于 0。
- 输出宽高从 `GenerationOptions.size` 或 `GenerationOptions.ratio` 解析；两者均须大于 0 且为 8 的倍数。
- `fps` 必须大于 0。
- `image` 和 `video` 选项将被转换为 data URI，或直接作为 URI 传递。
- 若提供了 `negative_prompt`、`seed` 和 `extras`，将被透传。

模式：

- 无输入媒体：`text2world`
- `options.image`：`image2world`
- `options.video`：`video2world`

## 响应契约

Cosmos 响应必须包含：

```json
{
  "b64_video": "...",
  "seed": 4,
  "upsampled_prompt": "..."
}
```

WorldForge 验证：

- `b64_video` 为非空的 base64 字符串
- `seed` 若存在，须为整数
- `upsampled_prompt` 若存在，须为字符串
- 解码后的字节作为 `VideoClip.frames[0]` 返回

返回的元数据包含提供方名称、提示词、模式、seed、上采样提示词、模型、内容类型及 base URL。

## 请求策略

`CosmosProvider` 使用 `ProviderRequestPolicy.remote_defaults(...)`：

- 创建式生成请求默认为单次尝试
- 健康检查使用退避重试
- 请求超时默认为 300 秒（可覆盖）

健康检查和生成 HTTP 调用均会发射提供方事件。`operation`、`phase`、`status_code`、`attempt` 及经脱敏的 `target` 展示了失败是否由认证响应、传输超时、可重试的健康读取或成功请求引起，同时不暴露持有人令牌或响应体中的秘密。

若宿主方需要不同的超时或重试行为，请传入自定义的 `request_policy=`。

## 失败模式

- `COSMOS_BASE_URL` 缺失时，提供方不会被注册。
- 若 `/v1/health/ready` 不可达、返回格式错误的 JSON，或缺少必需的字符串 `status` 字段，健康检查失败。首要排查步骤：在同一主机上使用 `curl "$COSMOS_BASE_URL/v1/health/ready"` 直接验证端点。
- 若时长、尺寸或 FPS 输入无效，生成失败。
- 若上游响应缺少 `b64_video` 或返回无效 base64，生成失败。
- 当 Cosmos 返回失败/错误状态载荷时，生成以任务失败消息告终。
- 当 Cosmos 返回工件 URL 而非内联 `b64_video` 时，生成以不支持工件消息告终；该适配器有意不持久化或下载提供方持有的工件 URL。
- HTTP 传输失败及非成功状态码将作为 `ProviderError` 抛出。

## 实时冒烟测试证明

已准备好的宿主方可在不更改默认 CI 的情况下运行真实的生成冒烟测试：

```bash
COSMOS_BASE_URL=http://localhost:8000 \
  uv run worldforge-smoke-cosmos \
    --output .worldforge/runs/cosmos-live/artifacts/cosmos.mp4 \
    --summary-json .worldforge/runs/cosmos-live/results/summary.json \
    --run-manifest .worldforge/runs/cosmos-live/run_manifest.json
```

冒烟测试将生成的视频字节写入请求的工件路径，并可写入经脱敏的 `run_manifest.json`，其中包含无值的环境变量存在性记录、运行时清单 id、事件计数、输入形状摘要、结果摘要及工件路径。宿主方负责留存生成的媒体；若用于发布或问题证明，请立即将工件从临时存储复制出来。

工件生命周期假设：只有在宿主方持久化了本地输出路径后，Cosmos 媒体证明才是持久的。若媒体工作流失败，请首先使用 `uv run worldforge provider health cosmos` 进行排查；若健康检查通过，请检查类型化提供方错误，查看是否存在格式错误的内联媒体、失败任务载荷或不支持的工件引用。

## 测试

- `tests/test_remote_video_providers.py` 覆盖了 Cosmos 健康检查解析、生成成功、格式错误的健康载荷、格式错误的生成载荷、无效 seed、失败任务载荷、不支持的工件载荷、认证失败、超时事件元数据以及尺寸验证。
- `tests/test_cosmos_smoke_script.py` 覆盖了不发起网络请求的手动实时冒烟测试入口点。
- `tests/fixtures/providers/cosmos_*.json` 存储解析器测试使用的响应夹具。

## 主要参考资料

- [NVIDIA Cosmos 文档](https://docs.nvidia.com/cosmos/latest/)
- [NVIDIA Cosmos Predict2.5 代码](https://github.com/nvidia-cosmos/cosmos-predict2.5)

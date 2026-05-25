# Runway 提供方

能力：`generate`、`transfer`

成熟度：`beta`

分类：远程视频生成与转换适配器

`runway` 是一个 HTTP 适配器，用于对接 Runway 的图像转视频、文本转视频兼容、视频转视频及任务轮询 API。它负责创建任务、轮询直至完成、下载首个输出，并返回经过验证的 `VideoClip`。

```text
prompt/options or input VideoClip
  -> Runway task creation
  -> task polling
  -> artifact download
  -> VideoClip
```

WorldForge 将 Runway 视为媒体提供方。它不暴露 `predict`、`score` 或 `policy`，因为该适配器不会返回经过验证的 WorldForge 状态转换、动作代价或可执行的动作块。

## 运行时归属

WorldForge 负责请求构造、类型化超时/重试策略、任务响应验证、工件下载验证以及提供方事件。

宿主方负责：

- Runway 凭据
- 端点策略与 API 限制
- 提示词/媒体输入
- URL 过期后的工件留存
- 运营遥测与用量限制

## 配置

- `RUNWAYML_API_SECRET`：自动注册的首选凭据。
- `RUNWAY_API_SECRET`：旧版凭据别名。
- `RUNWAYML_BASE_URL`：可选的 API 端点覆盖；默认为 `https://api.dev.runwayml.com`。
- `RUNWAYML_ALLOW_LOCAL_ARTIFACT_URLS`：可选的仅限测试的逃生舱口。若未设置，Runway 任务输出 URL 若指向 localhost、私有地址、链路本地、保留地址、多播或无法解析的本地目标，将在下载前被拒绝。
- `RUNWAYML_RESOLVE_ARTIFACT_DNS`：使用自定义 HTTP 传输时，可选的工件 URL DNS 检查覆盖。自动模式下，普通 HTTP 客户端执行 DNS 检查，确定性离线传输则跳过系统 DNS。

运行时清单：
`src/worldforge/providers/runtime_manifests/runway.json` 记录了凭据别名、可选端点覆盖、由宿主方持有的工件留存、最小实时冒烟测试命令，以及预期的 Runway 任务信号。

程序化构造：

```python
from worldforge.providers import RunwayProvider

provider = RunwayProvider(
    poll_interval_seconds=6.0,
    max_polls=60,
)
```

实时冒烟测试证明：

```bash
RUNWAYML_API_SECRET=<secret> \
  uv run worldforge-smoke-runway \
    --capability generate \
    --output .worldforge/runs/runway-live/artifacts/runway.mp4 \
    --run-manifest .worldforge/runs/runway-live/run_manifest.json
```

使用 `--capability transfer` 加 `--input-video` 可单独测试视频转视频功能。冒烟测试摘要和清单中保存了任务存在状态、本地工件路径，以及去除查询字符串和片段后的工件 URL。

## generate 能力契约

```python
from worldforge import GenerationOptions

clip = forge.generate(
    "a lab robot moves a cube",
    provider="runway",
    duration_seconds=5.0,
    options=GenerationOptions(
        image="/path/to/initial-frame.png",
        ratio="1280:720",
        model="gen4.5",
        seed=7,
    ),
)
```

生成规则：

- `duration_seconds` 必须大于 0。
- 时长将映射到 Runway 的 2–10 秒请求范围内。
- 默认模型为 `gen4.5`；目录当前记录的已知可选模型名称包括 `gen4.5`、`gen4_turbo`、`veo3.1`、`veo3.1_fast` 和 `gen4_aleph`。
- `GenerationOptions.ratio` 必须使用 `WIDTH:HEIGHT` 格式，宽高均须为正整数。
- `options.video` 在调用 `generate(...)` 时会被拒绝；视频输入请使用 `transfer(...)`。
- `image` 若提供，将作为 `promptImage` 传入。
- `extras` 将被透传至任务创建载荷。

## transfer 能力契约

```python
transferred = forge.transfer(
    clip,
    provider="runway",
    width=1280,
    height=720,
    fps=24,
    prompt="Re-render the clip with better lighting while preserving motion.",
    options=GenerationOptions(reference_images=["/path/to/reference.png"]),
)
```

transfer 规则：

- `width`、`height` 和 `fps` 均须大于 0。
- 输入视频从 `options.video` 中获取（若已提供），否则来自源 `VideoClip`。
- `reference_images` 将作为 Runway 参考图像。
- 若未通过 `options.model` 指定，默认 transfer 模型为 `gen4_aleph`。
- Runway 模型/版本限制可能随上游变更；基准测试输入与冒烟测试证明应绑定至结果摘要中使用的确切模型。

## 任务与工件契约

Runway 任务创建响应必须包含非空的任务 `id`。

任务轮询响应必须包含：

- 非空的 `status`
- 若响应中返回了 id，该 id 须与请求的任务匹配
- 任务成功时，`output` 为非空 URL 列表

终态任务行为：

- `SUCCEEDED`：下载第一个输出 URL
- `FAILED` 或 `CANCELLED`：抛出 `ProviderError` 并附带返回的失败详情
- 超过 `max_polls` 后超时：抛出 `ProviderError`

工件下载接受视频内容类型和 `application/octet-stream`。明确的非视频内容类型（如 `text/html`）将被拒绝。空下载将明确失败。下载以流式传输方式进行，并有硬性大小上限；`Content-Length` 超过该上限时，在读取响应体前即告失败。过期或不可用的工件 URL 将作为提供方错误返回。

Runway 输出 URL 可能是临时签名 URL。WorldForge 仅在验证 URL 使用 HTTP(S)、不含嵌入凭据、且不指向本地/私有基础设施（除非宿主方为可信本地测试明确选择启用）后，才将原始 URL 用于即时下载。WorldForge 随后在不保留查询字符串或片段的情况下记录 `artifact_url` 元数据。若媒体用于问题证明、基准测试比较或发布说明，请立即持久化已下载的字节。若工件已过期，请重新运行任务，而非尝试从日志或清单重建签名 URL。

工件生命周期假设：只有在宿主方写入或复制了本地工件路径后，下载的字节才是持久的。Runway 媒体失败的首要排查命令为：`uv run worldforge provider health runway`。若健康检查通过，请检查提供方事件中 `operation=="artifact download"` 及经过脱敏的 `target` 值，并在 URL 过期时重新运行任务。

两种能力各自提供了独立的基准测试输入夹具：

```bash
uv run worldforge benchmark --provider runway --operation generate \
  --input-file examples/runway-generate-benchmark-inputs.json
uv run worldforge benchmark --provider runway --operation transfer \
  --input-file examples/runway-transfer-benchmark-inputs.json
```

## 请求策略

`RunwayProvider` 使用 `ProviderRequestPolicy.remote_defaults(...)`：

- 任务创建请求默认为单次尝试
- 健康检查、轮询和下载使用退避重试
- 请求超时默认为 120 秒（可覆盖）

若宿主方需要不同的超时或重试行为，请传入自定义的 `request_policy=`。

## 失败模式

- `RUNWAYML_API_SECRET` 和 `RUNWAY_API_SECRET` 均缺失时，提供方不会被注册。
- 凭据无效或载荷同时缺少 `id` 和 `name` 时，组织健康检查失败。
- 响应缺少非空任务 id 时，任务创建失败。
- 状态载荷格式错误或响应 id 与请求任务不匹配时，轮询失败。
- 成功完成的任务若无输出 URL，将明确失败。
- 本地/私有/链路本地工件 URL 在下载前即告失败，除非设置了 `RUNWAYML_ALLOW_LOCAL_ARTIFACT_URLS=1` 或在构造函数中选择启用（用于可信本地测试部署）。
- 需要主机名到 IP 验证的自定义网络传输应设置 `RUNWAYML_RESOLVE_ARTIFACT_DNS=1` 或使用构造函数覆盖；离线确定性传输可保留自动模式。
- 过期、不可用、空或内容类型错误的工件在返回 `VideoClip` 前即告失败。
- 超大工件在检查 `Content-Length` 或流式传输响应体时失败。
- 结果元数据和运行清单仅保留经脱敏的工件 URL；签名查询字符串和片段不予保留。
- 无效的比例、时长、尺寸、FPS、轮询间隔或轮询次数，将在请求构造前或构造期间失败。

## 测试

- `tests/test_remote_video_providers.py` 覆盖了组织解析、任务创建与轮询、失败任务、部分输出、过期工件、内容类型拒绝、transfer 行为以及输入验证。
- `tests/fixtures/providers/runway_*.json` 存储任务和组织响应夹具。

## 主要参考资料

- [Runway API 参考文档](https://docs.dev.runwayml.com/api)
- [Runway API 输入参数](https://docs.dev.runwayml.com/assets/inputs/)

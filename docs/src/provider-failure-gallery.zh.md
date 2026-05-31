# 提供方故障模式图册

本图册将常见的提供方故障映射到具体的夹具支撑信号。它用于议题排查和适配器审查，不用于对实时提供方进行质量排名。

运行检出安全的工件生成器：

```bash
uv run python scripts/demo_showcases.py run provider-failure-gallery \
  --workspace-dir .worldforge/demo-showcases
```

预期成功信号：命令以 `0` 退出，并写入 `provider-failure-gallery/provider-failure-gallery.json` 和 `provider-failure-gallery/provider-failure-gallery.md`。首要排查步骤：找到匹配的行，运行其首要排查命令，并仅附上该行指定的安全工件。

| 故障模式 | 提供方接口 | 预期信号 | 责任方 | 首要排查命令 | 安全工件行为 |
| --- | --- | --- | --- | --- | --- |
| 无效的预测状态 | mock 契约夹具 | `invalid world state` 契约失败 | 适配器贡献者 | `uv run pytest tests/test_provider_contracts.py -q` | 仅附上提供方契约 JSON 或 Markdown |
| 不安全的提供方事件元数据 | 提供方事件一致性 | 事件 sink 前拒绝 `secret material` | 适配器贡献者和安全审查者 | `uv run pytest tests/test_provider_contracts.py -q` | 脱敏处理前将原始事件日志仅保留在本地 |
| 分数数量不匹配 | LeWorldModel 打分边界 | `returned 2 score(s) for 3 candidate` | 打分适配器维护者 | `uv run pytest tests/test_leworldmodel_provider.py -k score_count -q` | 附上经脱敏的分数元数据；不要附上张量 |
| 格式错误的打分请求载荷 | LeWorldModel 打分边界 | `four-dimensional` 验证错误 | 打分适配器维护者 | `uv run pytest tests/test_leworldmodel_provider.py -k malformed_payload -q` | 仅附上小型 JSON 夹具；宿主张量留在本地 |
| 缺失具身动作转换器 | Cosmos-Policy 策略边界 | `provide action_translator` | 预制宿主负责人 | `uv run worldforge provider info cosmos-policy` | 附上配置摘要和形状元数据，不附上观测 |
| 不安全的本地/私有端点 | Cosmos-Policy 配置 | `local/private destination` | 宿主运行时负责人和安全审查者 | `uv run pytest tests/test_cosmos_policy_provider.py -k local_base_url -q` | 不附上私有主机名或 bearer token |
| 格式错误的 json_numpy 动作形状 | Cosmos-Policy 响应解析器 | `action_dim must be 14` | 策略适配器维护者 | `uv run pytest tests/test_cosmos_policy_provider.py -k json_numpy_action_dim -q` | 仅附上有界形状元数据，不附上观测 |
| 可选运行时包缺失 | 已准备宿主的可选提供方 | 带有设置提示的不健康提供方信息 | 已准备宿主负责人 | `uv run worldforge provider info gr00t` | 仅附上运行时清单和经脱敏处理的提供方信息 |
| 脚手架提供方保持失败关闭 | Genie 脚手架契约 | 已配置的脚手架，没有任何已执行的操作 | 提供方维护者 | `uv run worldforge provider contract genie --format json` | 附上契约输出；不得声称真实的 Genie 集成 |

## 边界

- 本图册为检出安全的。它不调用付费 API、不使用凭据、不安装可选运行时，也不下载检查点。
- 提供方事件、健康输出、议题包和契约报告在附加之前必须保持脱敏处理。
- 原始提供方请求体、签名工件 URL、`.env` 文件、私有检查点和宿主本地载荷路径仅保留在本地。
- 脚手架提供方以故障边界的形式展示。失败关闭的脚手架行不是真实提供方集成的证据。

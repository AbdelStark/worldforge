# 更新日志

规范的更新日志位于仓库根目录：

[CHANGELOG.md](https://github.com/AbdelStark/worldforge/blob/main/CHANGELOG.md)

每项用户可见的变更都应在发布前记录在那里。能力变更、可选运行时行为、提供方文档、评估语义、基准测试语义以及发布流程变更均属于用户可见的内容。

如需发布评审，请从更新日志和发布凭证生成草稿：

```bash
uv run python scripts/generate_release_notes.py \
  --release-evidence .worldforge/release-evidence/release-evidence.json
```

草稿是可由维护者编辑的源材料。在发布 GitHub Release 前对其进行评审和编辑，不要将缺失的验证凭证、宿主方持有的可选运行时行、或生成的措辞视为最终发布审批。草稿输入会在 Markdown 渲染前被清理，避免 token 赋值、Bearer 头、签名 URL 和宿主本地路径进入发布说明。

更改更新日志中发布流程文本时，请在起草说明前先演练凭证路径：

```bash
uv run python scripts/release_readiness_drill.py
```

演练不进行发布。它展示了在维护者运行真实发布凭证门禁之前，干净通过的凭证、受控失败、宿主方持有的可选运行时跳过以及首要分诊命令应如何呈现。

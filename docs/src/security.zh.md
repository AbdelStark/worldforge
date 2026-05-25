# 安全

安全报告以私密方式处理。请勿就漏洞开启公开议题。

请使用仓库的 Security 选项卡报告漏洞：

```text
https://github.com/AbdelStark/worldforge/security
```

WorldForge 负责 Python 框架、提供方适配器边界、打包工作流以及已发布的源代码分发。宿主方持有的可选运行时、CUDA 栈、机器人控制器、检查点、数据集、凭据以及第三方提供方服务均不在基础包的安全边界之内。

提供方诊断设计为无值安全。`config_summary()` 仅报告字段名称、存在状态、来源、验证状态和密钥分类，不返回原始值。提供方事件和健康状态详情会对常见的 Bearer/API 密钥/密码/签名形态进行脱敏，并在序列化前从 URL 中去除查询字符串。宿主方仍应避免将原始密钥放入自定义异常消息、工件元数据或议题附件中。

脱敏回归由 `tests/fixtures/redaction/provider_event_corpus.json` 中的共享语料库守护。新的提供方事件接收器、运行清单、议题包、Rerun 层、指标导出器以及 OpenTelemetry 桥接器，在其输出被认为可安全附加之前，应对该语料库进行测试。

有关范围、响应目标和支持版本，请参阅规范的
[安全策略](https://github.com/AbdelStark/worldforge/blob/main/SECURITY.md)。

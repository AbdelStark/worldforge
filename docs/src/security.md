# Security

Security reports are handled privately. Do not open public issues for vulnerabilities.

Use the repository Security tab to report a vulnerability:

```text
https://github.com/AbdelStark/worldforge/security
```

WorldForge owns the Python framework, provider adapter boundaries, packaging workflows, and
released source distributions. Host-owned optional runtimes, CUDA stacks, robot controllers,
checkpoints, datasets, credentials, and third-party provider services remain outside the base
package security boundary.

Provider diagnostics are designed to be value-free. `config_summary()` reports field names,
presence, source, validation status, and secret classification without returning raw values.
Provider events and health details redact common bearer/API key/password/signature shapes and strip
query strings from URLs before serialization. Hosts should still avoid putting raw secrets into
custom exception messages, artifact metadata, or issue attachments.

For scope, response targets, and supported versions, see the canonical
[Security Policy](https://github.com/AbdelStark/worldforge/blob/main/SECURITY.md).

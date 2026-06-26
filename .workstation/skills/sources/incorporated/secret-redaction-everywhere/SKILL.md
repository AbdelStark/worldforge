---
name: secret-redaction-everywhere
description: "Trigger: working with provider events, logs, metadata, or artifacts. Teaches redaction at every boundary."
license: Apache-2.0
metadata:
  author: "openhands"
  version: "1.0"
---

# Secret Redaction Everywhere

## Activation Contract

Use this skill when:
- Creating provider events with metadata
- Setting up logging for provider operations
- Working with artifact metadata
- Creating workflow traces
- Setting up UI transcripts
- Implementing redaction for sensitive data

## Hard Rules

- Redact secrets BEFORE entering events, logs, exceptions, transcripts, persisted state, result metadata
- Sanitizing only the log is NOT enough
- Redact: bearer tokens, API keys, signed URL query strings, credentials
- Preserve: provider name, operation, status, sanitized host, elapsed time
- Implement centralized redaction module
- Redact at boundaries: events, results, traces, artifacts, UI, logs

## Decision Gates

| Need | Action |
|------|--------|
| Create provider events | Redact metadata before emitting events |
| Setup logging | Add redaction to logging configuration |
| Work with artifacts | Redact artifact metadata |
| Implement workflow tracing | Redact trace data |

## Execution Steps

1. Create redaction module for sensitive data patterns
2. Apply redaction at every boundary
3. Validate redaction rules are comprehensive
4. Test redaction with various sensitive data types
5. Ensure redaction preserves necessary information
6. Document redaction rules and patterns

## Output Contract

- Redaction module implementation
- Redaction rules and patterns
- Test coverage for redaction
- Documentation for sensitive data handling

## References

- `AGENTS.md` - Redaction requirements
- `CONTRIBUTING.md` - Security rules

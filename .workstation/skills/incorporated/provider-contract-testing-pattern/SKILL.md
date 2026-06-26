---
name: provider-contract-testing-pattern
description: "Trigger: testing provider adapters. Teaches provider contract testing as discipline."
license: Apache-2.0
metadata:
  author: "openhands"
  version: "1.0"
---

# Provider Contract Testing Pattern

## Activation Contract

Use this skill when:
- Testing provider adapters
- Writing provider contract tests
- Reviewing provider implementation compliance
- Setting up provider validation
- Teaching provider testing patterns

## Hard Rules

- Every capability claim needs: contract test, fixture test, error path test, event redaction test
- Use `worldforge/testing` helpers for testing
- DO NOT rely on Python assert statements
- Test all capabilities published by `ProviderCapabilities`
- Validate all provider inputs and outputs

## Decision Gates

| Need | Action |
|------|--------|
| Test provider | Use provider contract testing pattern |
| Review tests | Check compliance with contract tests |
| Setup testing | Use testing helpers |
| Document tests | Include contract requirements |

## Execution Steps

1. Write contract test using `assert_provider_contract`
2. Add fixture tests for each capability
3. Add error path tests for malformed inputs
4. Test event redaction for sensitive data
5. Validate all published capabilities

## Output Contract

- Provider contract test coverage
- Fixture tests for all capabilities
- Error path test coverage
- Event redaction test coverage

## References

- `AGENTS.md` - Provider contract testing
- `CONTRIBUTING.md` - Provider testing rules

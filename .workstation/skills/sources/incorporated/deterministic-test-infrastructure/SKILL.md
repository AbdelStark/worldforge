---
name: deterministic-test-infrastructure
description: "Trigger: tests that compare output or track time. Teaches deterministic test helpers."
license: Apache-2.0
metadata:
  author: "openhands"
  version: "1.0"
---

# Deterministic Test Infrastructure

## Activation Contract

Use this skill when:
- Writing tests that compare output or track time
- Setting up deterministic test behavior
- Managing test snapshots
- Controlling test timing
- Teaching deterministic testing patterns

## Hard Rules

- Use `DeterministicClock` instead of `datetime.now()`
- Use `DeterministicIdFactory` for IDs
- Use `stable_snapshot` for output comparison
- Use `stable_json_dumps` for JSON
- Replace random inputs with deterministic fixtures

## Decision Gates

| Need | Action |
|------|--------|
| Control timing | Use DeterministicClock |
| Control IDs | Use DeterministicIdFactory |
| Compare output | Use stable_snapshot |
| Serialize JSON | Use stable_json_dumps |

## Execution Steps

1. For time-dependent tests, inject `DeterministicClock`
2. For ID-dependent tests, inject `DeterministicIdFactory`
3. For output comparison, wrap with `stable_snapshot`
4. For JSON serialization, use `stable_json_dumps`
5. Document deterministic behavior

## Output Contract

- Deterministic test setup
- Controlled test behavior
- Deterministic output comparison
- Consistent JSON serialization

## References

- `AGENTS.md` - Deterministic test requirements
- `CONTRIBUTING.md` - Test determinism rules

---
name: fixture-snapshot-discipline
description: "Trigger: creating or reviewing test fixtures. Teaches fixture as contract."
license: Apache-2.0
metadata:
  author: "openhands"
  version: "1.0"
---

# Fixture Snapshot Discipline

## Activation Contract

Use this skill when:
- Creating or modifying test fixtures
- Reviewing fixture changes
- Setting up deterministic tests
- Managing test snapshot files
- Troubleshooting test inconsistencies

## Hard Rules

- Fixtures are CONTRACTS - when they drift from reality, the contract is broken
- Use `worldforge/testing` helpers for deterministic tests
- Custom helpers must match production behavior
- DO NOT create fixtures without compliance requirements

## Decision Gates

| Need | Action |
|------|--------|
| Create fixture | Use worldforge/testing helpers |
| Modify fixture | Validate contract compliance |
| Review fixture | Check snapshot integrity |
| Manage snapshots | Use manage_fixture_snapshots.py |

## Execution Steps

1. Use `worldforge/testing.DeterministicClock` and `DeterministicIdFactory`
2. Use `worldforge/testing.stable_snapshot` and `stable_json_dumps`
3. Store fixtures in `tests/fixtures/` directories
4. Validate fixtures with `manage_fixture_snapshots.py`
5. Update snapshots with explicit intent

## Output Contract

- Compliant fixture files
- Deterministic test helpers
- Snapshot management
- Fixture integrity validation

## References

- `AGENTS.md` - Fixture contract requirements
- `CONTRIBUTING.md` - Test fixture rules

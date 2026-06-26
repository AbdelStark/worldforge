---
name: json-native-contract
description: "Trigger: creating public models, persistence, or provider output. Teaches JSON-native as contract."
license: Apache-2.0
metadata:
  author: "openhands"
  version: "1.0"
---

# JSON-Native Contract

## Activation Contract

Use this skill when:
- Creating public models, persistence, or provider output
- Setting up JSON validation for public interfaces
- Working with action parameters or scene metadata
- Implementing validation for inherited exceptions
- Setting up parameter validation
- Working with provider events or diagnostics

## Hard Rules

- Only these types are allowed: strings, finite numbers, lists, dicts, booleans, null
- Validate at CONSTRUCTION TIME, not serialization
- `WorldStateError` for malformed persisted/provider state
- `WorldForgeError` for invalid caller input
- DO NOT silently coerce - loud failure is preferable
- Never allow tuples, object instances, bytes, NaN, Infinity

## Decision Gates

| Need | Action |
|------|--------|
| Create JSON validation | Setup boundary validation |
| Work with public models | Ensure JSON-native compliance |
| Test validation failures | Add validation test cases |
| Document validation | Create validation documentation |

## Execution Steps

1. Setup JSON-native validation system
2. Add validation at public input boundaries
3. Implement validation for all public interfaces
4. Test validation with various invalid inputs
5. Ensure validation preserves necessary information

## Output Contract

- JSON-native validation implementation
- Validation rules and patterns
- Test coverage for validation
- Documentation for JSON validation

## References

- `AGENTS.md` - JSON-native requirements
- `CONTRIBUTING.md` - Public interface rules

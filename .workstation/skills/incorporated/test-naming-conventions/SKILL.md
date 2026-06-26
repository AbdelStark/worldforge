---
name: test-naming-conventions
description: "Trigger: writing new tests. Teaches test names as documentation."
license: Apache-2.0
metadata:
  author: "openhands"
  version: "1.0"
---

# Test Naming Conventions

## Activation Contract

Use this skill when:
- Writing new test functions
- Reviewing test names
- Setting up test structure
- Teaching test naming conventions
- Organizing test files

## Hard Rules

- Test names are DOCUMENTATION
- Format: test_<subject>_<behavior>
- Return type hints: -> None:
- Use tmp_path for filesystem tests
- Use monkeypatch for environment variables
- Private mocks: class _MockProvider(BaseProvider):

## Decision Gates

| Need | Action |
|------|--------|
| Write tests | Follow test_<subject>_<behavior> format |
| Review tests | Check naming convention compliance |
| Set up tests | Use appropriate fixtures and helpers |
| Document tests | Include behavior and subject information |

## Execution Steps

1. Define subject: what is being tested
2. Define behavior: what is expected
3. Format as test_<subject>_<behavior>
4. Add return type hint -> None:
5. Use appropriate fixtures for test setup
6. Document test with clear name

## Output Contract

- Well-named test functions
- Consistent naming across tests
- Well-documented test suite

## References

- `AGENTS.md` - Test naming conventions
- `CONTRIBUTING.md` - Test documentation requirements

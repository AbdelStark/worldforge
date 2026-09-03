---
name: optional-runtime-host-owned
description: "Trigger: adding optional integrations. Teaches the host-owned dependency boundary pattern."
license: Apache-2.0
metadata:
  author: "openhands"
  version: "1.0"
---

# Optional Runtime Host-Owned

## Activation Contract

Use this skill when:
- Adding optional runtime integrations
- Choosing between optional and host-owned dependencies
- Setting up optional runtime support
- Debugging optional runtime integration issues
- Teaching teams about dependency management patterns

## Hard Rules

- Base package MUST only have `httpx` as runtime dependency
- DO NOT add heavy integrations to base dependencies
- Optional runtimes are HOST-OWNED - user provides the runtime
- Use extras for optional dependencies
- Keep base package installable anywhere

## Decision Gates

| Need | Action |
|------|--------|
| Add optional runtime | Use extras in pyproject.toml |
| Debug integration | Check import boundaries |
| Setup runtime | Follow script smoke testing patterns |

## Execution Steps

1. Keep base package minimal and installable anywhere
2. Put heavy integrations behind extras
3. Use smoke scripts to validate adapter paths
4. Enforce import boundaries with scripts
5. Document optional runtime setup

## Output Contract

- Pyproject.toml with proper extras structure
- Import boundary check script
- Smoke test for optional runtime
- Documentation for optional runtime setup

## References

- `AGENTS.md` - Optional runtime requirements
- `CONTRIBUTING.md` - Optional dependency rules

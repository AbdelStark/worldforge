---
name: coderabbit-review-routing
description: "Trigger: configuring, debugging, or working with CodeRabbit AI reviews. Teaches path-based review routing."
license: Apache-2.0
metadata:
  author: "openhands"
  version: "1.0"
---

# CodeRabbit Review Routing

## Activation Contract

Use this skill when:
- Configuring CodeRabbit AI reviews for repository security boundaries
- Debugging review routing issues in AI code review systems
- Teaching teams how to configure path-specific AI review instructions
- Setting up AI reviewer reviews for CodeRabbit integration

## Hard Rules

- CodeRabbit is configured as a REVIEW PARTNER, not a linter
- `path_instructions` in `.coderabbit.yaml` teach the AI reviewer what matters in each code area
- DO NOT modify the core CodeRabbit configuration logic
- All path instructions must follow the trust boundary identification pattern

## Decision Gates

| Need | Action |
|------|--------|
| Configure CodeRabbit review routing | Create `.coderabbit.yaml` with `path_instructions` |
| Debug review routing issues | Check `.coderabbit.yaml` path filters and instructions |
| Teach review routing | Show the pattern of trust boundary identification and instruction specification |

## Execution Steps

1. Create `.coderabbit.yaml` with `path_instructions` section
2. Identify trust boundaries in your codebase
3. For each boundary, create a path entry with instructions
4. Configure `knowledge_base.code_guidelines` to pull from team standards
5. Set auto-review triggers for your branch patterns
6. Enable relevant linting tools

## Output Contract

- Returns `.coderabbit.yaml` configuration file
- Documented path instruction examples
- Clear instructions for setting up trust boundaries

## References

- `AGENTS.md` - Agent guidelines for review routing

---
name: task-starter-workflow
description: "Trigger: picking up an issue or starting a contribution. Teaches pre-flight checklists."
license: Apache-2.0
metadata:
  author: "openhands"
  version: "1.0"
---

# Task Starter Workflow

## Activation Contract

Use this skill when:
- Picking up an issue or starting a contribution
- Selecting the right validation approach
- Setting up validation checks
- Running validation commands
- Attaching evidence artifacts
- Reviewing validation results
- Saving validation results

## Hard Rules

- Pick the STRICTEST validation if issue spans multiple starters
- Run ALL validation commands before opening PR
- Attach evidence artifacts for every PR
- Update docs/changelog for user-visible changes
- DO NOT skip validation

## Decision Gates

| Need | Action |
|------|--------|
| Pick starter | Match issue type to starter pack |
| Run validation | Execute ALL validation commands |
| Attach artifacts | Collect and attach evidence artifacts |
| Save results | Run validation gates |
| Update docs | Update docs/changelog for user-visible changes |

## Execution Steps

1. Pick the STRICTEST starter (focus, provider, docs, public, release)
2. Read starter checklist from `docs/src/task-starters.md`
3. Run ALL validation commands listed in starter
4. Collect all evidence artifacts
5. Save validation results
6. Update docs/changelog for user-visible changes
7. Open PR with evidence attached

## Output Contract

- Validation results
- Evidence artifacts
- Updated docs/changelog
- Successful PR opening with evidence

## References

- `AGENTS.md` - Task starter workflow
- `CONTRIBUTING.md` - Validation requirements

---
name: spec-triad-pattern
description: "Trigger: planning multi-task features. Teaches the spec/plan/tasks triad for feature agreements."
license: Apache-2.0
metadata:
  author: "openhands"
  version: "1.0"
---

# Spec Triad Pattern

## Activation Contract

Use this skill when:
- Planning multi-task features
- Creating feature agreements
- Setting up feature directories
- Documenting feature scope and implementation
- Managing feature progression

## Hard Rules

- Each multi-task feature gets a directory under `specs/`
- Three files per feature: `spec.md`, `plan.md`, `tasks.md`
- Specs are LIVING documents - update as scope changes
- Specs are the source of truth for what was agreed
- DO NOT skip specs for multi-task features

## Decision Gates

| Need | Action |
|------|--------|
| Plan multi-task feature | Create specs directory with triad |
| Update feature scope | Update spec document |
| Track decisions | Store in spec files |
| Retrieve past decisions | Check spec files |

## Execution Steps

1. Create `specs/` directory if it doesn't exist
2. For each feature:
   - Create `spec.md` (problem, scope, success criteria)
   - Create `plan.md` (implementation approach, staging, dependencies)
   - Create `tasks.md` (work units, acceptance criteria)
3. Reference specs in PR descriptions
4. Update specs when scope changes
5. Keep specs current with implementation progress

## Output Contract

- Specs directory structure
- Completed feature triad (spec, plan, tasks)
- Tracked decisions
- Updated PR descriptions with spec references

## References

- `AGENTS.md` - Feature planning and specs
- `CONTRIBUTING.md` - Feature workflows

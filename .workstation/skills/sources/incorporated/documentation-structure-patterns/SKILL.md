---
name: documentation-structure-patterns
description: "Trigger: writing documentation pages. Teaches playbook structure and doc templates."
license: Apache-2.0
metadata:
  author: "openhands"
  version: "1.0"
---

# Documentation Structure Patterns

## Activation Contract

Use this skill when:
- Writing documentation pages
- Setting up playbook structure
- Creating documentation templates
- Organizing documentation
- Reviewing documentation structure

## Hard Rules

- Every playbook section follows: trigger, commands, success signal, failure table
- Code blocks must be executable or marked as host-owned
- Use tables for decision matrices, command references, triage

## Decision Gates

| Need | Action |
|------|--------|
| Write playbook | Follow section template |
| Structure docs | Use numbered sections with subsections |
| Create templates | Follow playbook structure |
| Organize docs | Use consistent structure patterns |

## Execution Steps

1. For every section: trigger condition, commands, success signal, failure table
2. Use numbered sections with subsections
3. Create dense content blocks
4. Use tables for important relationships

## Output Contract

- Structured documentation pages
- Consistent playbook sections
- Organized documentation
- Templates for documentation creation

## References

- `AGENTS.md` - Documentation structure
- `CONTRIBUTING.md` - Documentation requirements

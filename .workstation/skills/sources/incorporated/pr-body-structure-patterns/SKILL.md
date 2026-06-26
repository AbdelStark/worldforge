---
name: pr-body-structure-patterns
description: "Trigger: writing PR descriptions. Teaches PR structure for squash-merge."
tags: ["git", "pull-requests", "squash-merge", "structure", "low"]
---

# PR Body Structure Patterns

## Title

- Imperative mood: "Add" not "Added"
- Under ~70 characters
- No `Co-Authored-By` or AI attribution
- PR number appended by GitHub

## Body

- Describe user-visible changes
- Link related issues
- Reference spec if applicable
- Include evidence artifacts

## Squash-Merge

- PR title becomes commit message
- Commits on same branch are squashed
- Review feedback: new commits (NOT amending)

## Anti-Patterns

- `Update README.md` — too vague
- `Fixed bug` — not imperative
- `Changes to provider` — meaningless

## Good Examples

```
feat: add LatentMPCController
Harden Go2 ControlBench trace validation (#339)
Sanitize release notes draft inputs
Enforce score result direction invariant
```

## Sharp Edges

| Symptom | Cause | Fix |
|---------|-------|-----|
| Commit message unclear | PR title vague | Use imperative + specific verb |
| Too many commits | Not squashing | Squash before merge |
| Review feedback lost | Amending commits | Add new commits |

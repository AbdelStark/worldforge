---
name: branching-scheme-patterns
description: "Trigger: creating branches or reviewing branch strategy. Teaches branching conventions."
tags: ["git", "branching", "squash-merge", "topic-branches", "low"]
---

# Branching Scheme Patterns

## Branch Naming

From CI config and CONTRIBUTING.md:
- `feat/<short-description>`
- `fix/<short-description>`
- `docs/<short-description>`
- `chore/<short-description>`
- `integration/<short-description>`

## Squash-Merge Is Default

- PR title becomes commit message
- Commits on same branch are squashed
- No long-lived feature branches
- Branches are disposable

## Rules

1. Topic branch: `git checkout -b feat/<short-description>`
2. Direct pushes to `main` reserved for maintainers
3. PR title: imperative, under ~70 chars
4. Review feedback: new commits on same branch (NOT amending)

## Commit History Story

Recent commits tell a story of progressive hardening:
```
Harden → Sanitize → Enforce → Reject → Normalize → Tighten
```

## Sharp Edges

| Symptom | Cause | Fix |
|---------|-------|-----|
| PR title not imperative | Wrong format | Use "Add" not "Added" |
| Branch too long-lived | Feature branch kept | Squash and delete |
| Commits not squashable | Too many unrelated changes | Split into work units |

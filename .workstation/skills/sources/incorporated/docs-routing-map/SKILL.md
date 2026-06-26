---
name: docs-routing-map
description: "Trigger: deciding where to put documentation changes. Teaches docs routing rules."
tags: ["docs", "documentation", "routing", "structure", "low"]
---

# Docs Routing Map

## Where to Put Changes

| Change Type | Where |
|-------------|-------|
| Front-door story, common commands | `README.md` |
| New components, flows, ownership | `docs/src/architecture.md` |
| Operator/maintainer runbooks | `docs/src/playbooks.md` |
| Provider-specific config/limits | `docs/src/providers/<provider>.md` |
| Public API and exceptions | `docs/src/api/python.md` |
| User-visible changes | `CHANGELOG.md` |
| Agent constraints/gotchas | `AGENTS.md` |
| CLI help/output changes | `docs/src/cli.md`, help snapshots |
| Navigation changes | `mkdocs.yml` + `docs/src/SUMMARY.md` |

## Rules

1. Generated provider catalog blocks: NEVER hand-edit, regenerate from metadata
2. Commands must be executable or explicitly marked host-owned/credentialed/illustrative
3. `mkdocs build --strict` is the final docs gate — warnings are release blockers
4. Every new workflow needs: command, success signal, first triage step

## Documentation Template

Each playbook section follows:

1. "Use this when..." — trigger condition
2. Code block — exact commands
3. "Success signal:" — what success looks like
4. "If it fails:" — table of symptoms/checks/owners

## Sharp Edges

| Symptom | Cause | Fix |
|---------|-------|-----|
| MkDocs strict warning | Bad link/nav/SUMMARY drift | Fix source page and sync nav |
| Provider table changes disappear | Edited generated block | Change metadata and regenerate |
| CLI snapshot fails | Help text changed | Update test intentionally |

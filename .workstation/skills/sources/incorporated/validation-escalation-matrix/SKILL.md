---
name: validation-escalation-matrix
description: "Trigger: deciding validation scope. Teaches when to escalate validation."
tags: ["testing", "validation", "escalation", "gates", "medium"]
---

# Validation Escalation Matrix

## Matrix

| Change Scope | Validation Layer | Commands |
|-------------|-----------------|----------|
| Single test fix | Focused | `ruff check`, `pytest tests/test_target.py` |
| Provider behavior | Provider | provider pytest + contract + provider-doc check |
| Docs/catalog | Docs | `generate_provider_docs.py --check`, `mkdocs build --strict` |
| Public API | Public gate | lock + ruff + docs + pytest + coverage + package + build |
| Release | Full gate | public gate + dependency audit |

## Escalation Triggers

1. Narrow test passes but broad claim → escalate
2. Provider behavior changes → add contract tests
3. Public API changes → full gate mandatory
4. Release preparation → full gate + audit

## Rules

1. Don't run full gate for every commit — wastes time
2. Escalate when claim exceeds test scope
3. `uv lock --check` is always first
4. Coverage gate: `--cov-fail-under=90` — never lower

## Sharp Edges

| Symptom | Cause | Fix |
|---------|-------|-----|
| Full gate too slow | Running for every commit | Use focused gate |
| Claim not backed | Narrow test for broad claim | Escalate validation |
| Coverage fails | New branch lacks tests | Add failure-path tests |

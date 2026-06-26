---
name: skill-body-length-contracts
description: "Trigger: creating or reviewing skills. Teaches LLM-first skill length constraints."
tags: ["convention", "skills", "length", "frontmatter", "low"]
---

# Skill Body Length Contracts

## Length Limits

| Target | Max | Hard Max |
|--------|-----|----------|
| 180-450 tokens | 700 tokens | 1000 tokens |

## Frontmatter

```yaml
---
name: skill-name
description: "Trigger: when to use. What it teaches."
tags: ["category", "topic", "complexity"]
license: Apache-2.0
metadata:
  author: "username"
  version: "1.0"
---
```

## Description Rules

1. One physical line, quoted, YAML-safe
2. Include trigger words FIRST
3. <=160 chars recommended, <=250 chars max

## Section Order

1. Activation Contract (when to use)
2. Hard Rules (non-negotiable)
3. Decision Gates (when to choose which)
4. Execution Steps (how to do it)
5. Output Contract (what to return)
6. References (links to local files)

## Supporting Material

- Code templates → `assets/`
- Conceptual detail → `references/`
- Long explanation → move out of SKILL.md

## Sharp Edges

| Symptom | Cause | Fix |
|---------|-------|-----|
| Skill too long | Supporting material in body | Move to assets/ or references/ |
| Missing trigger words | Description vague | Add trigger words to description |
| Wrong section order | Not LLM-first | Follow section order template |

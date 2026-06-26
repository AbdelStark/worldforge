---
name: workstation-navigation
description: "Trigger: agent needs to find or load a skill from the workstation. Teaches the optimal search path with minimal re-reads."
tags: ["convention", "workstation", "navigation", "meta", "low"]
---

# Workstation Navigation

## The Gate

Before searching, check: **do I already know this?**

```
1. Am I looking for a specific skill name?  → Go directly to sources/<origin>/<name>/SKILL.md
2. Am I looking by topic/category?          → List the category dir, pick the match
3. Am I exploring what exists?              → List sources/ or a category, don't read SKILL.md files
```

Never read SKILL.md files "just to see what's there." List first, read only when you need the content.

## Directory as Lookup Table

```
skills/
├── all/                  → 58 skills (alphabetical, everything)
├── incorporated/         → 30 skills (ours, from repo wisdom)
├── codex/                → 7 skills (WorldForge project)
├── testing/              → 10 skills (test/validation)
├── review/               → 7 skills (code review)
├── provider/             → 5 skills (adapters/capabilities)
├── git/                  → 6 skills (commits/PRs/branches)
├── convention/           → 6 skills (style/contracts/patterns)
├── sdd/                  → 11 skills (spec-driven dev)
├── docs/                 → 4 skills (documentation)
├── workflow/             → 3 skills (triage/compliance)
├── security/             → 1 skill  (redaction/secrets)
└── sources/              → Canonical content (edit here)
    ├── worldforge/       → From .codex/skills/
    ├── gentle-ai/        → From opencode
    └── incorporated/     → Created here
```

## Search Protocol

| Need | Action |
|------|--------|
| Specific skill by name | `ls skills/sources/*/<name>/SKILL.md` → read it |
| Skills for a topic | `ls skills/<category>/` → pick match → read SKILL.md |
| Check if skill exists | `ls skills/all/` → name match |
| Browse incorporated | `ls skills/incorporated/` |
| Find by tag | grep frontmatter: `grep -r "tags:.*<tag>" skills/sources/*/SKILL.md` |

## Cache Rule

If you read a SKILL.md this session, don't re-read it. You have the content.

If the session is fresh and you need a skill, read it ONCE. The workstation is stable — skills don't change mid-session.

## Avoid

- Reading multiple SKILL.md files to "explore" — list dirs instead
- Re-reading a skill you just loaded
- Searching all/ when you know the category
- Reading sources/ when you want to browse — use the category symlinks

## Sharp Edges

| Symptom | Cause | Fix |
|---------|-------|-----|
| Agent reads 10 skills to find one | Exploring instead of listing | List dir first, read only the match |
| Skill re-read every turn | No cache awareness | Track what you already loaded |
| Wrong category picked | Ignored tags | Check frontmatter tags before reading body |

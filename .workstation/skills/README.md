# Workstation Skills Catalog

Organized skill library for AI agent workflows. Unix-like structure with symlinks, category references, and tags.

> **For agents**: Load `workstation-navigation` FIRST — it teaches how to find skills without re-reading them. The directory is the lookup table; list before reading.

## How It Works

```
skills/
├── all/                  → Every skill (symlinks to sources/)
├── <category>/           → Filtered view (symlinks to sources/)
├── sources/              → Canonical content (edit here)
│   ├── <origin>/         → Skills grouped by origin
│   └── incorporated/     → Skills created from repo wisdom
└── config/               → Configuration file references
```

**The directory IS the lookup table.** List to discover, read SKILL.md only when you need the content.

## Quick Discovery

```bash
# List all categories
ls skills/

# List all skills
ls skills/all/

# List skills in a category
ls skills/testing/

# Find a skill by name
ls skills/all/ | grep <partial-name>

# Find skills by tag
grep -rl "tags:.*<tag>" skills/sources/*/SKILL.md
```

## Categories

Run `ls skills/` for current categories. Each directory is a category with symlinks.

## Tag System

Each skill has YAML frontmatter with `tags:` field (Markdown_TAG compatible):

```yaml
---
name: skill-name
description: "Trigger: when to use. What it teaches."
tags: ["category", "topic1", "topic2", "complexity"]
---
```

## Hierarchy

- `all/` = everything
- `incorporated/` = skills created here (not from original sources)
- `<category>/` = filtered view of relevant skills

## Rules

- All symlinks are relative (portable)
- `sources/` contains canonical content — edit there, not symlinks
- `config/` references repo-level configuration files

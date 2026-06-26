# Workstation

AI agent workstation for the WorldForge repository.

## Skills

The `skills/` directory contains an organized library of AI agent skills:

- **Categories**: `ls skills/` — each directory is a category
- **All skills**: `ls skills/all/` — everything in one place
- **Symlink-based**: categories reference `sources/` without duplication
- **Tags**: YAML frontmatter enables filtering by topic and complexity

See `skills/README.md` for the full catalog.

## Quick Start

```bash
# Load navigation skill first
cat .workstation/skills/sources/incorporated/workstation-navigation/SKILL.md

# Browse all skills
ls .workstation/skills/all/

# List by category
ls .workstation/skills/testing/
```

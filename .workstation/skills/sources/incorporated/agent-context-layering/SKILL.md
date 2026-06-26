---
name: agent-context-layering
description: "Trigger: updating agent-facing docs. Teaches layering protocol by consumption speed."
license: Apache-2.0
metadata:
  author: "openhands"
  version: "1.0"
---

# Agent Context Layering

## Activation Contract

Use this skill when:
- Updating agent-facing documentation
- Managing documentation layers
- Teaching agent documentation patterns
- Organizing agent information
- Refreshing agent context after compaction

## Hard Rules

- Three layers: Compact, Full, Skills
- Compact layer = quick decisions (CLAUDE.md)
- Full layer = deep work (AGENTS.md)  
- Skills = repeated workflows (.codex/skills/)
- Facts must be consistent across layers
- References must point to local files

## Decision Gates

| Need | Action |
|------|--------|
| Create documentation | Follow layering protocol |
| Update documentation | Ensure consistency across layers |
| Refresh context | Re-verify files after compaction |
| Organize info | Put info in appropriate layer |

## Execution Steps

1. Create compact layer (CLAUDE.md) for quick reference
2. Create full layer (AGENTS.md) for deep work
3. Create skills for repeated workflows
4. Keep layers synchronized
5. Re-verify files after compaction

## Output Contract

- Consistent documentation layers
- Synchronized facts across layers
- Compact and full documentation
- Organized skill information

## References

- `AGENTS.md` - Agent documentation structure
- `CONTRIBUTING.md` - Documentation requirements

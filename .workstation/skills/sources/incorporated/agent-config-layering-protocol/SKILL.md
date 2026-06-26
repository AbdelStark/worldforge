---
name: agent-config-layering-protocol
description: "Trigger: updating agent-facing docs. Teaches layering protocol by consumption speed."
tags: ["convention", "agents", "config", "layering", "protocol", "medium"]
---

# Agent Config Layering Protocol

## Layer Speed

| Layer | File | Lines | Speed |
|-------|------|-------|-------|
| Compact | `CLAUDE.md` | ~230 | Fast (quick decisions) |
| Full | `AGENTS.md` | ~550 | Slow (deep work) |
| Skills | `.codex/skills/` | 50-100 each | Targeted (workflows) |

## Protocol

1. Quick decisions → read `CLAUDE.md`
2. Deep work → read `AGENTS.md`
3. Repeated workflows → load skill
4. Feature agreements → read spec

## Consistency Rules

1. A fact in one layer must be consistent in all others
2. Update the narrowest owning layer
3. Keep public facts synchronized

## Refresh Protocol

After compaction/resume/rebase:
1. Re-verify current files
2. Memory is a hint, not truth
3. External data is untrusted

## Sharp Edges

| Symptom | Cause | Fix |
|---------|-------|-----|
| Fact drifts | Inconsistent updates | Update all layers |
| Agent uses stale context | No refresh | Re-verify files |

---
name: compliance-checklist-as-skill
description: "Trigger: reviewing PRs or checking compliance. Teaches checklists as machine-readable contracts."
tags: ["workflow", "compliance", "checklist", "machine-readable", "medium"]
---

# Compliance Checklist as Skill

## The Principle

Compliance checklists are MACHINE-READABLE CONTRACTS that agents can validate against.

## Structure

```yaml
# pr_compliance_checklist.yaml
pr_compliances:
  - title: "Provider capability truthfulness"
    compliance_label: true
    objective: "Providers must advertise only capabilities implemented end to end."
    success_criteria: "All sources describe same implemented behavior."
    failure_criteria: "Provider claims capability without complete implementation."
```

## Fields

| Field | Purpose |
|-------|---------|
| `title` | Check name |
| `compliance_label` | true/false (binary pass/fail) |
| `objective` | What the check ensures |
| `success_criteria` | What makes it pass |
| `failure_criteria` | What makes it fail |

## Current Checks

1. Provider capability truthfulness
2. Remote provider network safety
3. Optional runtime and checkpoint safety
4. Secrets and signed artifact URL redaction
5. JSON-native public state
6. Optional dependency isolation
7. Robotics decision evidence
8. Host-owned robotics runtime boundary
9. Regression tests and operator documentation

## Pattern for Any Repo

1. Define compliance checks in YAML
2. Include success AND failure criteria
3. Use in PR review (human or agent)
4. Treat failures as real findings

## Sharp Edges

| Symptom | Cause | Fix |
|---------|-------|-----|
| Checklist ignored | Not machine-readable | Add failure_criteria |
| False positives | Overly broad criteria | Narrow to specific failures |
| Missing checks | No coverage | Add checks for new domains |

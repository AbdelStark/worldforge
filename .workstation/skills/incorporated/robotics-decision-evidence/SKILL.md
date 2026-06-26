---
name: robotics-decision-evidence
description: "Trigger: robotics demos, adapters, or showcase flows. Teaches WorldForge must add analytical value."
license: Apache-2.0
metadata:
  author: "openhands"
  version: "1.0"
---

# Robotics Decision Evidence

## Activation Contract

Use this skill when:
- Creating robotics demos or showcase flows
- Adding robotics providers or adapters
- Teaching teams about robotics integration
- Setting up robotics provider validation
- Troubleshooting robotics integration

## Hard Rules

- WorldForge must choose, score, explain, compare robot decisions
- If robotics change only logs decisions without scores/rationale - OUT OF SCOPE
- Must show why WorldForge belongs in the decision loop
- Host-owned robotics runtime boundary is mandatory
- Replay/simulator artifacts are UNTRUSTED INPUTS

## Decision Gates

| Need | Action |
|------|--------|
| Create robotics demo | Show decision evidence (scores, rationale, outcomes) |
| Add robotics provider | Validate host-owned boundary compliance |
| Setup validation | Implement robotics compliance checks |
| Review integration | Verify analytical value addition |

## Execution Steps

1. Validate host-owned robotics runtime boundary
2. Set up deterministic controls for runtime integration
3. Create compliance validation for robotics demo
4. Implement threshold gating for runtime validation
5. Document robotics integration patterns

## Output Contract

- Robotics compliance checklist
- Host-owned boundary validation
- Deterministic runtime integration
- Compliance check implementation

## References

- `AGENTS.md` - Robotics integration requirements
- `CONTRIBUTING.md` - Optional runtime rules

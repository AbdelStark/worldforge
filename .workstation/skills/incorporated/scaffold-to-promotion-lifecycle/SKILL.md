---
name: scaffold-to-promotion-lifecycle
description: "Trigger: taking provider from scaffold to promoted status. Teaches quality gate lifecycle."
license: Apache-2.0
metadata:
  author: "openhands"
  version: "1.0"
---

# Scaffold to Promotion Lifecycle

## Activation Contract

Use this skill when:
- Developing provider from scaffold
- Promoting scaffold to production provider
- Setting up provider quality gates
- Validating provider compliance
- Teaching provider development lifecycle

## Hard Rules

- Scaffold has UNADVERTISED capabilities
- Promotion is a QUALITY GATE
- DO NOT auto-register without required configuration
- Hosted catalog only when env vars present

## Decision Gates

| Need | Action |
|------|--------|
| Develop scaffold | Follow scaffold-to-promotion pattern |
| Promote provider | Validate compliance checklist |
| Regenerate catalog | Run generate_provider_docs.py --check |
| Publish provider | Validate provider compliance |

## Execution Steps

1. Create scaffold using scaffold_provider.py
2. Implement required methods with typed returns
3. Add contract tests for each capability
4. Update provider documentation
5. Regenerate provider catalog
6. Validate compliance with checklist
7. Promote to advertised capabilities

## Output Contract

- Scaffold provider
- Implemented provider
- Tested and documented provider
- Promoted and advertised provider
- Validated compliance checklist

## References

- `AGENTS.md` - Provider promotion lifecycle
- `CONTRIBUTING.md` - Provider quality gates

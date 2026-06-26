---
name: ci-supply-chain-awareness
description: "Trigger: modifying CI workflows or dependencies. Teaches CI as supply-chain sensitive."
license: Apache-2.0
metadata:
  author: "openhands"
  version: "1.0"
---

# CI Supply-Chain Awareness

## Activation Contract

Use this skill when:
- Modifying CI workflows or dependencies
- Understanding CI as supply-chain component
- Setting up CI security controls
- Auditing CI supply chain
- Teaching CI supply-chain best practices

## Hard Rules

- CI is the TRUST LAYER that validates every contribution
- Treat CI as supply-chain sensitive
- Always pin versions in CI (actions/checkout@v4, actions/setup-python@v5)
- Use minimal permissions in CI
- Implement concurrency controls
- DO NOT weaken existing gates

## Decision Gates

| Need | Action |
|------|--------|
| Modify CI workflow | Keep minimal permissions, pin versions |
| Audit CI supply chain | Check version pinning and permissions |
| Setup CI security | Implement supply-chain controls |
| Teach CI best practices | Document version pinning and permissions |

## Execution Steps

1. Always pin versions in CI files
2. Use minimal permissions required
3. Implement concurrency controls
4. Keep version pinning consistent
5. Document CI security requirements
6. Audit CI for supply-chain risks
7. Implement CI security controls

## Output Contract

- Secured CI workflows
- Pinned version requirements
- Minimal permission configurations
- Supply-chain audit results

## References

- `AGENTS.md` - CI security requirements
- `CONTRIBUTING.md` - CI supply-chain rules

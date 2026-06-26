---
name: provider-capability-truthfulness
description: "Trigger: adding, modifying, or reviewing provider adapters. Core principle: capabilities must be truthful."
license: Apache-2.0
metadata:
  author: "openhands"
  version: "1.0"
---

# Provider Capability Truthfulness

## Activation Contract

Use this skill when:
- Adding new provider adapters
- Modifying existing provider capabilities
- Reviewing provider implementation compliance
- Adding provider capability tests
- Setting up provider capability documentation
- Troubleshooting provider capability issues

## Hard Rules

- A provider that claims `predict` but only does `score` is a TRUST VIOLATION
- ONLY these five capabilities are valid: `predict`, `score`, `policy`, `embed`, `plan`
- `ProviderCapabilities()` is fail-closed - no capabilities by default
- Each capability must be implemented END TO END with typed returns
- Marketing names are UNTRUSTED - capability labels come from observed behavior

## Decision Gates

| Need | Action |
|------|--------|
| Review provider capabilities | Check `ProviderCapabilities()` declaration |
| Add provider capability tests | Add contract tests for each capability |
| Document capability issues | Update provider docs and catalog |
| Verify implementation | Run provider contract testing |

## Execution Steps

1. Verify `ProviderCapabilities()` declaration matches implemented methods
2. Add contract tests for each advertised capability
3. Test error paths for each capability
4. Verify provider events conform to structure
5. Update provider documentation
6. Regenerate provider catalog

## Output Contract

- Provider capability compliance report
- Contract test failures by capability
- Documentation gaps by capability
- Catalog verification report

## References

- `AGENTS.md` - Provider capabilities and contracts
- `CONTRIBUTING.md` - Provider rules

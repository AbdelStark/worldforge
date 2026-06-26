---
name: validation-gate-layers
description: "Trigger: deciding which validation gates to run. Teaches layered validation from focused to full."
license: Apache-2.0
metadata:
  author: "openhands"
  version: "1.0"
---

# Validation Gate Layers

## Activation Contract

Use this skill when:
- Deciding which validation gates to run for different change types
- Optimizing CI pipeline efficiency vs safety trade-offs
- Teaching teams about validation gate strategy
- Setting up validation gates for new components
- Troubleshooting CI validation issues

## Hard Rules

- ALWAYS run `uv lock --check` first - dependency drift blocks everything
- Coverage gate: `--cov-fail-under=90` - never lower it, add tests instead
- CI runs 3 parallel jobs: quality, tests, package
- Narrow gates when changing isolated concerns
- Full gate mandatory for public API changes

## Decision Gates

| Change Scope | Validation Layer | Commands |
|-------------|-----------------|----------|
| Single file change | Focused | `ruff check`, `pytest tests/test_target.py` |
| Provider changes | Provider | provider pytest + fixtures + contract helper |
| Docs/catalog changes | Docs | generate_provider_docs.py --check, mkdocs build --strict |
| Public API changes | Public gate | lock + ruff + docs + pytest + coverage + package + build |
| Release preparation | Full gate | public gate + dependency audit |

## Escalation Triggers

1. Narrow test passes but broad claim → escalate to public gate
2. Provider behavior changes → add contract tests + provider-doc check
3. Public API changes → full gate mandatory
4. Release preparation → full gate + dependency audit

## Execution Steps

1. Identify change scope and test impact
2. Choose appropriate validation layer based on scope
3. Run validation commands for that layer
4. Escalate when claim exceeds test scope
5. Always validate with `uv lock --check` first

## Output Contract

- Returns validation layer recommendation for given change scope
- Provides command list for each validation layer
- Documents escalation rules for claim vs test mismatch

## References

- `AGENTS.md` - CI validation gates and testing strategy
- `CONTRIBUTING.md` - validation requirements

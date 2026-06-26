---
name: pr-agent-review-patterns
description: "Trigger: configuring PR-Agent (Codium) reviews. Teaches review agent configuration as knowledge transfer."
license: Apache-2.0
metadata:
  author: "openhands"
  version: "1.0"
---

# PR-Agent Review Patterns

## Activation Contract

Use this skill when:
- Configuring PR-Agent (Codium) reviews to teach the reviewer what the repo values
- Setting up AI review agent configuration in PR workflows
- Documenting review guidelines for PR systems
- Teaching how to configure review agent behavior based on team standards

## Hard Rules

- PR-Agent (Codium) uses `issues_user_guidelines` to teach the reviewer what this repo values
- This is essentially a SKILL for the review agent
- DO NOT modify the core PR-Agent configuration logic
- All guidelines should be review-focused and value-based

## Decision Gates

| Need | Action |
|------|--------|
| Configure PR-Agent review | Create `.pr_agent.toml` with `review_agent.demand_self_review` and `issues_user_guidelines` |
| Debug review agent issues | Check `issues_user_guidelines` content and agent behavior |
| Document review patterns | Show how to document review guidelines for PR systems |

## Execution Steps

1. Create `.pr_agent.toml` with `[review_agent]` section
2. Set `demand_self_review = true` for quality review
3. Set `approve_pr_on_self_review = false` to prevent auto-approval
4. Write `issues_user_guidelines` with team values and priorities
5. Configure `compliance_user_guidelines` to tie to team standards
6. Exclude WIP/Draft PRs and dependabot branches

## Output Contract

- Returns `.pr_agent.toml` configuration file
- Documented `issues_user_guidelines` pattern
- Clear instructions for configuring review guidelines

## References

- `AGENTS.md` - Agent guidelines for review patterns

---
name: commit-message-discipline
description: "Trigger: writing commit messages. Teaches conventional commits and imperative style patterns."
license: Apache-2.0
metadata:
  author: "openhands"
  version: "1.0"
---

# Commit Message Discipline

## Activation Contract

Use this skill when:
- Writing commit messages following repository conventions
- Teaching teams about conventional commit format
- Reviewing commit messages for consistency
- Setting up git commit hooks or pre-commit checks
- Migrating legacy commit history to conventional format

## Hard Rules

- Commit messages MUST follow: `<type>(<scope>): <description>`
- Description MUST be in IMPERATIVE mood (present tense) - "Add" not "Added"
- Keep commit messages under 72 characters recommended, max 80
- DO NOT end commit messages with a period
- Scope is optional for cross-cutting changes
- PR title becomes squash-merge commit message

## Decision Gates

| Need | Action |
|------|--------|
| Teach commit discipline | Show conventional commit format examples |
| Review commit messages | Check IMPERATIVE mood and format compliance |
| Set up pre-commit hooks | Configure commit message validation |
| Migrate legacy history | Apply reformatting rules to legacy commits |

## Execution Steps

1. Define acceptable types: feat, fix, refactor, chore, docs
2. Create scope list for common components
3. Write domain-specific verb mapping:
   - `Harden` - security/reliability improvement
   - `Sanitize` - redaction/cleanup
   - `Enforce` - contract/coherence validation
   - `Add` - new feature/demo
   - `Tune` - configuration adjustment
4. Create commit message template with examples
5. Set up git hooks to validate format and length

## Output Contract

- Returns commit message style guide
- Provides examples of good and bad commit messages
- Includes domain-specific verb mapping
- Sets up pre-commit validation

## References

- `AGENTS.md` - Commit guidelines and patterns
- `CONTRIBUTING.md` - Contribution requirements

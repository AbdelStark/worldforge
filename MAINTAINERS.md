# Maintainers

WorldForge is currently maintained by:

| Name | GitHub | Areas |
| --- | --- | --- |
| Abdel | [@AbdelStark](https://github.com/AbdelStark) | Overall project direction, releases, provider contracts, optional-runtime boundaries |

## Review Expectations

- Capability changes must include tests that exercise the advertised surface end to end.
- Provider adapters must document runtime ownership, input/output contracts, failure modes, and
  validation commands.
- Evaluation and benchmark changes must preserve claim boundaries and reproducible artifacts.
- Public docs should state the command to run, the expected success signal, and the first triage
  step.

## Release Ownership

Only maintainers should cut release tags, publish distributions, or change trusted-publishing
configuration. Release candidates should pass the full release gate in `docs/src/playbooks.md`
locally or in CI before a tag is
pushed.

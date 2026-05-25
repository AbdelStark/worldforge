# Security Policy

WorldForge is pre-1.0 software. Security reports are welcome and triaged on a
best-effort basis.

## Reporting a vulnerability

**Please do not open public issues for security reports.** Use GitHub's private
vulnerability reporting:

1. Go to the [repository Security tab](https://github.com/AbdelStark/worldforge/security).
2. Click **Report a vulnerability**.
3. Fill in the advisory form with a clear reproducer and the affected commit /
   release.

If you cannot use GitHub Security Advisories, open a private thread with
[@AbdelStark](https://github.com/AbdelStark) on GitHub and we'll route from there.

## Scope

In scope:

- Source code under `src/worldforge/` shipped via the `worldforge-ai` PyPI
  package.
- Packaging workflows under `.github/workflows/` that produce the release
  artifacts.
- Provider adapters and their public input / output boundaries.

Out of scope:

- Host-owned optional runtimes (LeWorldModel, LeRobot, GR00T, torch, CUDA, robot
  controllers) and any checkpoints, datasets, or credentials they depend on.
  WorldForge does not bundle, download, or execute these; security for those
  stacks is the upstream project's responsibility.
- Third-party services reached by provider adapters (Cosmos, Runway, JEPA,
  Genie). Report issues with those services upstream.
- Denial-of-service or resource-exhaustion scenarios that require attacker-owned
  inputs to adapters already under attacker control.

## Response targets

Because WorldForge is a small pre-1.0 project with volunteer maintenance:

- Acknowledgement: within 7 days.
- Initial assessment (triage / reproducer confirmation): within 14 days.
- Fix or mitigation: negotiated per report; critical issues get priority.

There is no formal SLA. Coordinated disclosure windows are reasonable on request.

## Supported versions

Security fixes target `main`. The most recent `0.x` minor release on PyPI
receives fixes on a best-effort basis until superseded. Older `0.x` versions
do not receive backports.

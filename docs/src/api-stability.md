# Public API Stability

WorldForge is still pre-1.0, but several surfaces are public enough that contributors need a clear
change policy. This policy sets review expectations; it is not a 1.0 compatibility promise.

## API Tiers

| Tier | Examples | Change policy |
| --- | --- | --- |
| Stable | `WorldForge`, `World`, domain models in `worldforge.models`, capability protocols, `WorldForgeError`, `WorldStateError`, `ProviderError`, generated provider docs, documented CLI commands | Keep source-compatible when practical. Breaking changes need a changelog entry, migration note, and at least one release cycle of deprecation unless a security or correctness issue requires an immediate break. |
| Provisional | Evaluation report schemas, benchmark input and budget schemas, run workspace manifests, evidence bundles, provider workbench reports, optional host scripts | Schema changes need a version bump or explicit migration note. Keep old fields readable where that does not preserve invalid state. |
| Experimental | `jepa-wms` direct-construction candidate, scaffold provider reservations, optional robotics wrappers, prepared-host live smokes, Rerun visual artifacts | May change faster, but docs must keep capability and runtime ownership honest. Experimental status does not allow secret leakage or silent coercion. |
| Internal | Private helpers, generated implementation details, test-only fixtures, non-exported parser helpers, TUI internals outside documented harness APIs | Can change without deprecation. Do not import these from downstream code. |

## Deprecation Rules

Deprecation is required when a change affects a stable public import, constructor argument, model
field, exception family, CLI command or flag, provider capability, provider profile field, artifact
schema, or documented file layout. In review notes, call this out explicitly as an artifact schema
migration.

Every deprecation plan should include:

- the old surface and the replacement surface;
- the first release where warnings or docs notices appear;
- the earliest release where removal may happen;
- the validation command that proves both old and new paths during the transition;
- the changelog entry that describes user action.

Immediate removal is allowed only for security exposure, persisted-state incoherence, false provider
capability claims, or behavior that cannot be maintained without corrupting user artifacts. In that
case, the PR must state the reason, the failure mode, and the migration command or manual recovery
step.

## Provider And Artifact Migrations

Provider changes must preserve truthful capability advertising. Removing or renaming a capability,
changing a provider profile status, or changing runtime ownership needs a migration note in the
provider page and changelog. Scaffold adapters must not be promoted by wording alone; promotion
requires parser tests, contract tests, runtime evidence, and documentation updates.

Artifact schemas must remain JSON-native and versioned when they leave a single process. The
[Artifact Schemas](./artifact-schemas.md) ownership map lists the current public and semi-public
families, version fields, owners, validation surfaces, and migration rules. Readers should reject
malformed or unsupported schema versions loudly instead of silently coercing invalid state.

## Changelog Expectations

Use the changelog for any public behavior change, including:

- breaking API, CLI, provider, or artifact-schema changes;
- new deprecations and removal dates;
- migration commands or manual recovery steps;
- changed validation gates;
- changed optional runtime requirements.

Small typo fixes and internal-only refactors do not need changelog entries unless they affect public
docs, generated artifacts, or user-visible commands.

## Contributor Checklist

Before merging a public API change, answer these questions in the PR:

- Is the touched surface stable, provisional, experimental, or internal?
- Does the change need a deprecation notice or schema version bump?
- Do docs and changelog explain the migration?
- Do tests cover both the old compatibility path and the new behavior when applicable?
- Does provider capability advertising remain truthful?
- Are malformed persisted/provider states rejected explicitly?

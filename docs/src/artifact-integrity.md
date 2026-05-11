# Artifact Integrity

WorldForge release artifacts must be inspectable from a clean checkout before a package, release
note, provider promotion, or benchmark claim is published. The current integrity model is
checkout-safe: it validates package contents, dependency advisories, generated docs, command drift,
wrapper portability, core performance budgets, release evidence, and preserved artifact digests
without requiring signing credentials or optional model runtimes.

## Verified Today

| Surface | Current gate | Success signal | First triage step |
| --- | --- | --- | --- |
| Lockfile | `uv lock --check` | dependency metadata is already locked | refresh lock metadata intentionally and inspect the diff |
| Wheel and sdist shape | `bash scripts/test_package.sh` | wheel installs in an isolated venv; sdist contains docs, tests, examples, scripts, and metadata | inspect `scripts/check_distribution.py` for the missing or forbidden entry |
| Distribution metadata | `uv run python scripts/check_distribution.py dist` | wheel metadata has Python `>=3.13,<3.14`, MIT license expression, extras, and console scripts | fix `pyproject.toml` or package include rules |
| Dependency advisories | `uv run python scripts/generate_dependency_audit_evidence.py` | JSON and Markdown evidence record `passed`, `findings`, `tool-unavailable`, or `failed` status against the frozen exported requirements | inspect the Markdown advisory table and update or document the dependency decision |
| Generated provider docs | `uv run python scripts/generate_provider_docs.py --check` | provider catalog docs match provider metadata | regenerate docs, inspect provider profile changes, then rerun |
| Documented command drift | `uv run python scripts/check_docs_commands.py` | README, CLI docs, examples, operations, playbooks, and AGENTS commands resolve | fix the stale command or document the missing public entry point |
| Wrapper portability | `uv run python scripts/check_wrapper_portability.py` | wrappers have expected shebangs, executable bits, Python 3.13 uv invocations, and docs | fix the named wrapper or documented command |
| Core checkout performance | `uv run python scripts/check_core_performance.py` | report has `passed: true` for checkout-safe core paths | inspect the failing row and fix the regression before changing budgets |
| Release evidence | `uv run python scripts/generate_release_evidence.py --run-gates` | Markdown and JSON summaries link gate status, artifacts, hashes, and live-smoke manifests | inspect the failed gate row and its first triage step |
| Quality dashboard | `uv run python scripts/generate_quality_dashboard.py` | local JSON and Markdown summarize release evidence, dependency audit, core performance, skipped host-owned checks, not-run checks, and first failed gate | inspect the raw failure details section, then rerun the underlying gate artifact |
| Release notes draft | `uv run python scripts/generate_release_notes.py --release-evidence .worldforge/release-evidence/release-evidence.json` | maintainer-editable Markdown links changelog entries, closed issues, validation evidence, caveats, and host-owned optional runtime evidence | regenerate release evidence or fix `CHANGELOG.md`, then rerun the draft command |
| Release provenance | `.github/workflows/release.yml` build provenance attestation | tagged release builds upload distributions and request GitHub artifact provenance | inspect the release workflow run and attached GitHub attestation |
| Package publish identity | `.github/workflows/release.yml` PyPI environment with OIDC permissions | `uv publish dist/*` runs from the protected `pypi` environment | verify the release environment and PyPI trusted publishing configuration before tagging |

## Hashes And Evidence Links

Before a release note cites package or evidence artifacts, generate local hashes:

```bash
uv build --out-dir dist --clear --no-build-logs
shasum -a 256 dist/worldforge_ai-*.whl dist/worldforge_ai-*.tar.gz
bash scripts/test_package.sh
uv run python scripts/generate_dependency_audit_evidence.py
uv run python scripts/generate_release_evidence.py --run-gates \
  --artifact .worldforge/dependency-audit/dependency-audit.json \
  --artifact dist/worldforge_ai-<version>-py3-none-any.whl \
  --artifact dist/worldforge_ai-<version>.tar.gz
uv run python scripts/generate_quality_dashboard.py
```

The dependency-audit wrapper uses `uv export --frozen --all-groups --no-emit-project --no-hashes`
plus `uvx --from pip-audit pip-audit ... --format json` with a temporary requirements file that is
removed after the audit. The release evidence JSON records artifact paths and SHA-256 digests for
linked artifacts. Evidence bundles, dependency-audit evidence, run manifests, benchmark reports,
and live-smoke manifests should be linked from release notes instead of copied by hand. Use
[Artifact Schemas](./artifact-schemas.md) to identify the owning module, version field, migration
rule, and validation surface before changing a public artifact contract.

The quality dashboard reads existing JSON outputs instead of running gates. It is useful for a
single local review page because it distinguishes `failed`, `warning`, `skipped`, and `not-run`
checks and preserves raw output tails. It does not replace release evidence: release evidence is
still the release-claim artifact for artifact hashes, linked run manifests, and explicit
limitations.

Draft release notes after evidence exists:

```bash
uv run python scripts/generate_release_notes.py \
  --release-evidence .worldforge/release-evidence/release-evidence.json
```

The draft is not a publishing step. It is safe to attach for review because missing validation
evidence is called out explicitly, host-local paths are redacted, and optional runtime claims remain
scoped to linked live-smoke manifests.

Unsafe artifacts stay out of public bundles: `.env` files, credentials, signed URL query strings,
checkpoint archives, downloaded datasets, robot-controller logs, local cache directories, and
unredacted provider payloads. Use `worldforge runs bundle <run-id>` or
`scripts/generate_evidence_bundle.py` for sanitized issue and release artifacts.

## Future Work

These are expected future hardening steps, not current release claims:

- generate and publish an SBOM for each release artifact;
- define a signing key policy before publishing signed artifacts;
- link GitHub attestations from release evidence once the report can resolve credentialed release
  artifacts directly.

Until those steps are implemented, do not claim signed artifacts, SBOM coverage, or a stronger SLSA
level than the release workflow actually proves.

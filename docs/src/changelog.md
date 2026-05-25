# Changelog

The canonical changelog lives in the repository root:

[CHANGELOG.md](https://github.com/AbdelStark/worldforge/blob/main/CHANGELOG.md)

Every user-visible change should be recorded there before release. Capability changes, optional
runtime behavior, provider documentation, evaluation semantics, benchmark semantics, and release
process changes are user-visible.

For release review, generate a draft from the changelog and release evidence:

```bash
uv run python scripts/generate_release_notes.py \
  --release-evidence .worldforge/release-evidence/release-evidence.json
```

The draft is maintainer-editable source material. Review and edit it before publishing a GitHub
release, and do not treat missing validation evidence, host-owned optional runtime rows, or
generated wording as final release approval.

When changing release-process text in the changelog, rehearse the evidence path before drafting
notes:

```bash
uv run python scripts/release_readiness_drill.py
```

The drill is non-publishing. It shows how clean-pass evidence, controlled failures, host-owned
optional-runtime skips, and first-triage commands should appear before maintainers run the real
release evidence gates.

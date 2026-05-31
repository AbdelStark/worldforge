from __future__ import annotations

import importlib.util
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

from worldforge.testing import DeterministicClock

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "generate_release_notes.py"
SPEC = importlib.util.spec_from_file_location("generate_release_notes", SCRIPT)
assert SPEC is not None
generate_release_notes = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules["generate_release_notes"] = generate_release_notes
SPEC.loader.exec_module(generate_release_notes)
build_release_notes_draft = generate_release_notes.build_release_notes_draft
main = generate_release_notes.main


def test_release_notes_draft_collects_changelog_issues_and_evidence(tmp_path: Path) -> None:
    changelog = tmp_path / "CHANGELOG.md"
    changelog.write_text(
        """# Changelog

## Unreleased

### Added

- Added `scripts/generate_release_notes.py` for maintainer-edited release notes drafts.
- Added `docs/src/operations.md` release-note review instructions.

### Changed

- Changed provider evidence summaries for `src/worldforge/providers/catalog.py`.

### Fixed

- Fixed CLI error redaction for signed URLs.

## 0.1.0
""",
        encoding="utf-8",
    )
    evidence = tmp_path / "release-evidence.json"
    evidence.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "validation_summary": {
                    "passed": 2,
                    "failed": 0,
                    "skipped": 1,
                    "host-owned": 0,
                },
                "validation_gates": [
                    {
                        "name": "Docs",
                        "status": "passed",
                        "command": "uv run mkdocs build --strict",
                        "triage_step": "fix docs",
                    }
                ],
                "benchmark_artifacts": [
                    {
                        "path": ".worldforge/reports/benchmark.json",
                        "sha256": "sha256:abc",
                    }
                ],
                "release_artifacts": [
                    {
                        "path": "/Users/alice/private/dist/worldforge.whl",
                        "sha256": "sha256:def",
                    }
                ],
                "live_provider_evidence": [
                    {
                        "provider": "leworldmodel",
                        "status": "passed",
                        "manifests": [{"path": ".worldforge/runs/leworldmodel/run_manifest.json"}],
                        "reason": "",
                    },
                    {
                        "provider": "gr00t",
                        "status": "host-owned",
                        "manifests": [],
                        "reason": "missing host-owned configuration: GROOT_POLICY_HOST",
                    },
                ],
                "extra_live_provider_evidence": [],
                "known_limitations": ["No Cosmos-Policy live run."],
                "claim_boundary": "Checkout-safe gates do not prove live provider availability.",
            }
        ),
        encoding="utf-8",
    )
    issues = tmp_path / "issues.json"
    issues.write_text(
        json.dumps(
            [
                {
                    "number": 234,
                    "title": "Add release notes assembly",
                    "url": "https://github.com/AbdelStark/worldforge/issues/234",
                    "labels": [{"name": "release"}, {"name": "artifacts"}],
                    "closedAt": "2026-05-11T00:00:00Z",
                }
            ]
        ),
        encoding="utf-8",
    )

    draft = build_release_notes_draft(
        changelog_path=changelog,
        release_evidence_path=evidence,
        issues_json_path=issues,
        known_caveats=("Release manager must edit final wording.",),
        now_utc=DeterministicClock(start=datetime(2026, 5, 11, tzinfo=UTC)).now,
    )

    assert draft.status == "ready-for-maintainer-review"
    assert draft.warnings == ()
    assert "# WorldForge Release Notes Draft" in draft.markdown
    for heading in (
        "## Added",
        "## Changed",
        "## Fixed",
        "## Docs",
        "## Validation",
        "## Compatibility Notes",
        "## Host-Owned Optional Runtime Evidence",
    ):
        assert heading in draft.markdown
    assert "#234 Add release notes assembly" in draft.markdown
    assert "### `release`" in draft.markdown
    assert "`passed`=2" in draft.markdown
    assert ".worldforge/reports/benchmark.json" in draft.markdown
    assert "| `leworldmodel` | passed | 1 manifest(s) |" in draft.markdown
    assert "| `gr00t` | host-owned | missing host-owned configuration: GROOT_POLICY_HOST |" in (
        draft.markdown
    )
    assert "does not publish a GitHub release" in draft.markdown
    assert "No Cosmos-Policy live run." in draft.markdown
    assert "<host-local-path>" in draft.markdown
    assert "/Users/alice" not in draft.markdown


def test_release_notes_draft_uses_failed_gate_rows_for_status(tmp_path: Path) -> None:
    changelog = tmp_path / "CHANGELOG.md"
    changelog.write_text(
        """# Changelog

## Unreleased

### Fixed

- Fixed release evidence status handling.
""",
        encoding="utf-8",
    )
    evidence = tmp_path / "release-evidence.json"
    evidence.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "validation_summary": {
                    "passed": 1,
                    "failed": 0,
                    "skipped": 0,
                    "host-owned": 0,
                },
                "validation_gates": [
                    {
                        "name": "Tests",
                        "status": "failed",
                        "command": "uv run pytest",
                        "triage_step": "fix tests",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    draft = build_release_notes_draft(
        changelog_path=changelog,
        release_evidence_path=evidence,
        now_utc=DeterministicClock(start=datetime(2026, 5, 11, tzinfo=UTC)).now,
    )

    assert draft.status == "needs-validation-review"
    assert "- Draft status: `needs-validation-review`" in draft.markdown
    assert "| Tests | failed | `uv run pytest` | fix tests |" in draft.markdown


def test_release_notes_draft_handles_malformed_validation_shapes(tmp_path: Path) -> None:
    changelog = tmp_path / "CHANGELOG.md"
    changelog.write_text(
        """# Changelog

## Unreleased

### Fixed

- Fixed malformed validation evidence rendering.
""",
        encoding="utf-8",
    )
    evidence = tmp_path / "release-evidence.json"
    evidence.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "validation_summary": ["not", "a", "dict"],
                "validation_gates": {"not": "a list"},
            }
        ),
        encoding="utf-8",
    )

    draft = build_release_notes_draft(
        changelog_path=changelog,
        release_evidence_path=evidence,
        now_utc=DeterministicClock(start=datetime(2026, 5, 11, tzinfo=UTC)).now,
    )

    assert draft.status == "ready-for-maintainer-review"
    assert "`passed`=0" in draft.markdown
    assert "| none | missing |  | regenerate release evidence |" in draft.markdown


def test_release_notes_draft_handles_malformed_host_owned_evidence_rows(
    tmp_path: Path,
) -> None:
    changelog = tmp_path / "CHANGELOG.md"
    changelog.write_text(
        """# Changelog

## Unreleased

### Changed

- Changed optional runtime release note rendering.
""",
        encoding="utf-8",
    )
    evidence = tmp_path / "release-evidence.json"
    evidence.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "validation_summary": {
                    "passed": 1,
                    "failed": 0,
                    "skipped": 0,
                    "host-owned": 0,
                },
                "validation_gates": [
                    {
                        "name": "Docs",
                        "status": "passed",
                        "command": "uv run mkdocs build --strict",
                        "triage_step": "fix docs",
                    }
                ],
                "live_provider_evidence": {"provider": "ignored"},
                "extra_live_provider_evidence": [
                    "ignored",
                    {
                        "provider": "cosmos-policy",
                        "status": "needs-review",
                        "manifests": {"not": "a list"},
                        "reason": "",
                    },
                ],
            }
        ),
        encoding="utf-8",
    )

    draft = build_release_notes_draft(
        changelog_path=changelog,
        release_evidence_path=evidence,
        now_utc=DeterministicClock(start=datetime(2026, 5, 11, tzinfo=UTC)).now,
    )

    assert draft.status == "ready-for-maintainer-review"
    assert "| `cosmos-policy` | needs-review | no evidence detail |" in draft.markdown
    assert "| `ignored` |" not in draft.markdown


def test_release_notes_draft_redacts_secret_shapes_from_all_user_inputs(tmp_path: Path) -> None:
    changelog = tmp_path / "CHANGELOG.md"
    changelog.write_text(
        """# Changelog

## Unreleased

### Fixed

- Fixed release path token=changelog-secret at /var/folders/private/log.
""",
        encoding="utf-8",
    )
    evidence = tmp_path / "release-evidence.json"
    evidence.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "validation_summary": {
                    "passed": 1,
                    "failed": 0,
                    "skipped": 0,
                    "host-owned": 0,
                },
                "validation_gates": [
                    {
                        "name": "Gate token=gate-secret",
                        "status": "passed",
                        "command": "uv run pytest token=command-secret",
                        "triage_step": "inspect /var/folders/private/gate token=triage-secret",
                    }
                ],
                "known_limitations": [
                    "limitation Authorization: Bearer limitation-secret at /tmp/private/log"
                ],
                "claim_boundary": "claim secret=claim-secret at /var/folders/private/claim",
                "live_provider_evidence": [
                    {
                        "provider": "leworldmodel",
                        "status": "host-owned",
                        "manifests": [],
                        "reason": "skip token=provider-secret at /private/tmp/provider",
                    }
                ],
                "extra_live_provider_evidence": [],
            }
        ),
        encoding="utf-8",
    )
    issues = tmp_path / "issues.json"
    issues.write_text(
        json.dumps(
            [
                {
                    "number": 1,
                    "title": "issue token=issue-secret at /var/folders/private/issue",
                    "url": "https://github.com/AbdelStark/worldforge/issues/1?token=url-secret",
                    "labels": [{"name": "release token=label-secret"}],
                    "closedAt": "2026-05-11T00:00:00Z",
                }
            ]
        ),
        encoding="utf-8",
    )

    draft = build_release_notes_draft(
        changelog_path=changelog,
        release_evidence_path=evidence,
        issues_json_path=issues,
        known_caveats=("caveat token=caveat-secret at /var/folders/private/caveat",),
        now_utc=DeterministicClock(start=datetime(2026, 5, 11, tzinfo=UTC)).now,
    )

    for secret in (
        "changelog-secret",
        "gate-secret",
        "command-secret",
        "triage-secret",
        "limitation-secret",
        "claim-secret",
        "provider-secret",
        "issue-secret",
        "url-secret",
        "label-secret",
        "caveat-secret",
    ):
        assert secret not in draft.markdown
    for host_path in ("/var/folders/private", "/tmp/private", "/private/tmp"):
        assert host_path not in draft.markdown
    assert "token=[redacted]" in draft.markdown
    assert "secret=[redacted]" in draft.markdown
    assert "Authorization: [redacted] [redacted]" in draft.markdown
    assert "<host-local-path>" in draft.markdown
    assert "[redacted-url]" in draft.markdown


def test_release_notes_main_reports_missing_validation_evidence(
    tmp_path: Path,
    capsys,
) -> None:
    changelog = tmp_path / "CHANGELOG.md"
    changelog.write_text(
        """# Changelog

## Unreleased

### Added

- Added a release note draft command.
""",
        encoding="utf-8",
    )
    output = tmp_path / "draft.md"

    result = main(
        [
            "--changelog",
            str(changelog),
            "--release-evidence",
            str(tmp_path / "missing-release-evidence.json"),
            "--output",
            str(output),
        ]
    )

    captured = capsys.readouterr()
    draft = output.read_text(encoding="utf-8")
    assert result == 0
    assert "wrote <host-local-path>/draft.md" in captured.out
    assert "warning: Validation evidence missing" in captured.err
    assert "Validation evidence missing" in draft
    assert "uv run python scripts/generate_release_evidence.py --run-gates" in draft
    assert "needs-validation-evidence" in draft


def test_release_notes_main_can_require_validation_evidence(tmp_path: Path) -> None:
    changelog = tmp_path / "CHANGELOG.md"
    changelog.write_text(
        """# Changelog

## Unreleased

### Added

- Added a release note draft command.
""",
        encoding="utf-8",
    )

    result = main(
        [
            "--changelog",
            str(changelog),
            "--release-evidence",
            str(tmp_path / "missing-release-evidence.json"),
            "--output",
            str(tmp_path / "draft.md"),
            "--require-validation-evidence",
        ]
    )

    assert result == 1


def test_release_notes_main_reports_missing_changelog(tmp_path: Path, capsys) -> None:
    output = tmp_path / "draft.md"

    result = main(
        [
            "--changelog",
            str(tmp_path / "missing-changelog.md"),
            "--output",
            str(output),
        ]
    )

    captured = capsys.readouterr()
    assert result == 1
    assert "release notes error: Missing changelog" in captured.err
    assert "restore CHANGELOG.md" in captured.err
    assert not output.exists()

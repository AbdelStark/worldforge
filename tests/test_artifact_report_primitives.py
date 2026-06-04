from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path

from worldforge.artifact_report_primitives import (
    OBSERVABLE_REPORT_TEXT_REDACTION,
    RELEASE_NOTES_TEXT_REDACTION,
    display_report_path,
    isoformat_utc,
    sanitize_report_json,
    sanitize_report_text,
)


def test_sanitize_report_json_preserves_colliding_redacted_keys() -> None:
    payload = {
        "/Users/alice/private/token=alpha": "first",
        "/private/tmp/token=beta": "second",
        "https://example.test/a?token=gamma": "third",
        "nested": [{"stderr": "wrote /Users/alice/private/out.json token=delta"}],
    }

    sanitized = sanitize_report_json(payload)
    rendered = json.dumps(sanitized, sort_keys=True)

    assert "/Users/alice" not in rendered
    assert "/private/tmp" not in rendered
    assert "alpha" not in rendered
    assert "beta" not in rendered
    assert "gamma" not in rendered
    assert "https://example.test/a?token=gamma" not in rendered
    assert "<host-local-path>" in sanitized
    assert "<host-local-path>#2" in sanitized
    assert "[redacted-url]" in sanitized
    assert "first" in rendered
    assert "second" in rendered
    assert "third" in rendered


def test_observable_report_text_redaction_matches_release_evidence_policy() -> None:
    text = (
        "failed Authorization: Bearer stderr-secret at "
        "https://example.test/artifact.json?token=download-secret "
        "from /Users/alice/private/out.json"
    )

    sanitized = sanitize_report_text(text, redaction=OBSERVABLE_REPORT_TEXT_REDACTION)

    assert "stderr-secret" not in sanitized
    assert "download-secret" not in sanitized
    assert "/Users/alice" not in sanitized
    assert "https://example.test/artifact.json" in sanitized
    assert "<host-local-path>" in sanitized


def test_release_notes_policy_redacts_signed_urls_and_tmp_paths() -> None:
    sanitized = sanitize_report_text(
        "see /tmp/worldforge/run.log and https://example.test/a?token=download-secret",
        redaction=RELEASE_NOTES_TEXT_REDACTION,
    )

    assert sanitized == "see <host-local-path> and [redacted-url]"


def test_display_report_path_uses_repo_relative_or_host_placeholder(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    inside = root / "reports" / "evidence.json"
    outside = tmp_path / "other" / "secret.json"

    assert display_report_path(inside, root=root) == "reports/evidence.json"
    assert display_report_path(outside, root=root) == "<host-local-path>/secret.json"


def test_isoformat_utc_normalizes_naive_and_offset_datetimes() -> None:
    assert isoformat_utc(datetime(2026, 1, 2, 3, 4, 5, 123, tzinfo=UTC)) == (
        "2026-01-02T03:04:05+00:00"
    )
    assert isoformat_utc(datetime(2026, 1, 2, 3, 4, 5)) == "2026-01-02T03:04:05+00:00"
    offset = timezone(timedelta(hours=2))
    assert isoformat_utc(datetime(2026, 1, 2, 5, 4, 5, tzinfo=offset)) == (
        "2026-01-02T03:04:05+00:00"
    )
